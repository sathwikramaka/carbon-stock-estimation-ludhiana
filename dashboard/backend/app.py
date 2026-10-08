"""
app.py — Ludhiana carbon dashboard backend
==========================================

Serves the dashboard and a small JSON API. Every number it returns is read from
what notebooks/02_carbon_pipeline.ipynb wrote (results/) or from the databases
loaded from those files by notebooks/03_publish_databases.ipynb. Nothing here
contains a figure of its own.

Data source, set by DB_MODE in the project .env:

  files  (default)  results/*.json and results/carbon_cells.csv — no database needed
  local             PostgreSQL/PostGIS + MongoDB on this machine
  cloud             Supabase + MongoDB Atlas

In local/cloud mode any database error falls back to the files, and the
response says so in its "source" field.

Run:  python app.py   then open http://localhost:5000
"""
from __future__ import annotations

import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

BASE_DIR = Path(__file__).resolve().parent


def find_root(start: Path) -> Path:
    """Project root = first ancestor holding config.py (or .env)."""
    for folder in [start, *start.parents]:
        if (folder / "config.py").exists() or (folder / ".env").exists():
            return folder
    return start


ROOT = find_root(BASE_DIR)
if (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env")
RESULTS = Path(os.getenv("RESULTS_DIR", ROOT / "results"))
DB_MODE = os.getenv("DB_MODE", "files").strip().lower()

app = Flask(__name__,
            template_folder=str(BASE_DIR.parent / "frontend" / "templates"),
            static_folder=str(BASE_DIR.parent / "frontend" / "static"))
CORS(app, origins=[o.strip() for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:5000").split(",") if o.strip()])

MAX_LIMIT = 3000
MAX_AREA_HALF_WIDTH_DEG = 0.1
MAX_PER_PAGE = 500
GRID_HALF_STEP = 0.002245788210302635 / 2 + 1e-4   # half a cell, plus rounding slack on stored centroids


# ── File store (single source of truth) ───────────────────────
class ResultsMissing(RuntimeError):
    pass


def _read_json(name: str) -> dict:
    p = RESULTS / name
    if not p.exists():
        raise ResultsMissing(f"{p} not found — run notebooks/02_carbon_pipeline.ipynb")
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _cells():
    """Per-cell table, loaded once. pandas is imported lazily so routes that
    never touch cells do not need it."""
    import pandas as pd

    p = RESULTS / "carbon_cells.csv"
    if not p.exists():
        raise ResultsMissing(f"{p} not found — run notebooks/02_carbon_pipeline.ipynb")
    return pd.read_csv(p).sort_values("cell_id", kind="stable").reset_index(drop=True)


_RING = re.compile(r"\(\(\((.*?)\)\)\)")


def _wkt_to_geojson(wkt: str) -> dict:
    ring = [[float(a), float(b)] for a, b in (p.split() for p in _RING.search(wkt).group(1).split(","))]
    return {"type": "Polygon", "coordinates": [ring]}


def _num(v, nd=4):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, nd)


def _props(r) -> dict:
    g = r.get
    return {
        "cell_id": g("cell_id"),
        "agri": int(g("agri_class")) if _num(g("agri_class")) is not None else None,
        "agnonag": _num(g("Ag/NonAg_m"), 3),
        "dem": _num(g("DEM_mean"), 1),
        "slope": _num(g("Slope_mean"), 2),
        "soil_status": g("soil_status"),
        "w_soil": _num(g("w_soil"), 3),
        "bd": _num(g("bd_gcm3_rec"), 3),
        "soc_gkg": _num(g("soc_gkg"), 3),
        "soc": _num(g("soc_stock_tc_ha"), 3),
        "soc_source": g("soc_source"),
        "npp": _num(g("npp_flux_tc_ha_yr"), 4),
        "npp_source": g("npp_source"),
    }


def files_geojson(limit=None, bbox=None, seed=0) -> list:
    df = _cells()
    if bbox:
        # cells whose square intersects the box, as PostGIS `&&` does in database mode
        x0, y0, x1, y1 = bbox
        h = GRID_HALF_STEP
        df = df[(df.lon + h >= x0) & (df.lon - h <= x1) & (df.lat + h >= y0) & (df.lat - h <= y1)].head(MAX_LIMIT)
    else:
        df = df.sample(n=min(limit, len(df)), random_state=seed)
    return [{"type": "Feature", "geometry": _wkt_to_geojson(r["WKT"]), "properties": _props(r)}
            for r in df.to_dict(orient="records")]


def files_page(page: int, per_page: int) -> dict:
    df = _cells()
    cols = ["cell_id", "agri_class", "soil_status", "soc_gkg", "soc_stock_tc_ha", "soc_source",
            "npp_flux_tc_ha_yr", "npp_source"]
    chunk = df.iloc[(page - 1) * per_page: page * per_page][cols]
    recs = [{k: (_num(v) if isinstance(v, float) else v) for k, v in r.items()} for r in chunk.to_dict(orient="records")]
    return {"records": recs, "total": int(len(df)), "page": page, "per_page": per_page}


# ── Database store ─────────────────────────────────────────────
def _pg_url() -> tuple[str, str]:
    from urllib.parse import quote_plus
    pre = "SUPABASE" if DB_MODE == "cloud" else "PG"
    user = os.getenv(f"{pre}_USER", "postgres")
    pwd = quote_plus(os.getenv(f"{pre}_PASSWORD", ""))
    host = os.getenv(f"{pre}_HOST", "localhost")
    port = os.getenv(f"{pre}_PORT", "5432")
    db = os.getenv(f"{pre}_DB", "postgres")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}", ("require" if DB_MODE == "cloud" else "prefer")


def pg():
    import psycopg2
    url, ssl = _pg_url()
    return psycopg2.connect(url, sslmode=ssl, connect_timeout=5)


@lru_cache(maxsize=1)
def _mongo_client():
    """One client per process: MongoClient holds its own connection pool."""
    from pymongo import MongoClient
    uri = os.getenv("ATLAS_URI" if DB_MODE == "cloud" else "MONGO_URI", "mongodb://localhost:27017/")
    return MongoClient(uri, serverSelectionTimeoutMS=5000)


def mdb():
    return _mongo_client()[os.getenv("MONGO_DB", "carbon_stock_ludhiana")]


def _need(doc, what):
    """Treat an empty collection as a database failure, so the response is labelled files-fallback."""
    if not doc:
        raise LookupError(f"{what} is empty in the database")
    return doc


CELL_COLS = ("cell_id, agri_class, agnonag_m, dem_mean, slope_mean, soil_status, w_soil, bd_gcm3_rec, "
             "soc_gkg, soc_stock_tc_ha, soc_source, npp_flux_tc_ha_yr, npp_source")
CELL_KEYS = ["cell_id", "agri_class", "Ag/NonAg_m", "DEM_mean", "Slope_mean", "soil_status", "w_soil",
             "bd_gcm3_rec", "soc_gkg", "soc_stock_tc_ha", "soc_source", "npp_flux_tc_ha_yr", "npp_source"]


def db_geojson(limit=None, bbox=None) -> list:
    conn = pg()
    try:
        cur = conn.cursor()
        if bbox:
            cur.execute(f"SELECT ST_AsGeoJSON(geom), {CELL_COLS} FROM grid_cells "
                        "WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326) LIMIT %s", (*bbox, MAX_LIMIT))
        else:
            cur.execute(f"SELECT ST_AsGeoJSON(geom), {CELL_COLS} FROM grid_cells ORDER BY random() LIMIT %s", (limit,))
        rows = cur.fetchall()
        if not bbox:
            _need(rows, "grid_cells")                        # empty table -> serve the files instead
    finally:
        conn.close()
    return [{"type": "Feature", "geometry": json.loads(r[0]), "properties": _props(dict(zip(CELL_KEYS, r[1:])))}
            for r in rows]


def with_fallback(db_fn, file_fn):
    """Run db_fn in database modes, file_fn otherwise or on database failure."""
    if DB_MODE in ("local", "cloud"):
        try:
            return db_fn(), DB_MODE
        except Exception as exc:  # noqa: BLE001 — any DB failure falls back to the files
            app.logger.warning("database unavailable (%s); serving results files", exc.__class__.__name__)
            return file_fn(), "files-fallback"
    return file_fn(), "files"


# ── Routes ─────────────────────────────────────────────────────
@app.errorhandler(ResultsMissing)
def _missing(exc):
    return jsonify({"error": str(exc)}), 503


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def api_health():
    status = {"db_mode": DB_MODE, "results_dir": str(RESULTS),
              "results_files": sorted(p.name for p in RESULTS.glob("*")) if RESULTS.exists() else []}
    if DB_MODE in ("local", "cloud"):
        for name, fn in [("postgres", lambda: pg().close()), ("mongodb", lambda: mdb().command("ping"))]:
            try:
                fn()
                status[name] = "ok"
            except Exception as exc:  # noqa: BLE001
                status[name] = f"down: {exc.__class__.__name__}"
    return jsonify(status)


@app.route("/api/summary")
def api_summary():
    doc, src = with_fallback(
        lambda: _need(mdb()["district_summary"].find_one({}, {"_id": 0}, sort=[("run_date", -1)]), "district_summary"),
        lambda: _read_json("district_summary.json"))
    return jsonify({**doc, "source": src})


@app.route("/api/metrics")
def api_metrics():
    doc, src = with_fallback(
        lambda: _need(mdb()["model_metrics"].find_one({}, {"_id": 0}, sort=[("run_date", -1)]), "model_metrics"),
        lambda: _read_json("model_metrics.json"))
    return jsonify({**doc, "source": src})


@app.route("/api/ndvi")
def api_ndvi():
    docs, src = with_fallback(
        lambda: _need(list(mdb()["ndvi_monthly"].find({}, {"_id": 0}).sort("sort_order", 1)), "ndvi_monthly"),
        lambda: _read_json("ndvi_monthly.json"))
    return jsonify(docs)


@app.route("/api/geojson")
def api_geojson():
    try:
        limit = int(request.args.get("limit", 1200))
    except ValueError:
        return jsonify({"error": "limit must be an integer"}), 400
    if not 1 <= limit <= MAX_LIMIT:
        return jsonify({"error": f"limit must be between 1 and {MAX_LIMIT}"}), 400
    feats, src = with_fallback(lambda: db_geojson(limit=limit), lambda: files_geojson(limit=limit))
    return jsonify({"type": "FeatureCollection", "features": feats, "total": len(feats), "source": src})


@app.route("/api/geojson/area")
def api_geojson_area():
    """Cells inside a box around a point: /api/geojson/area?lat=30.82&lng=75.84&size=0.045"""
    try:
        lat = float(request.args.get("lat", 30.82))
        lng = float(request.args.get("lng", 75.84))
        size = float(request.args.get("size", 0.045))
    except (TypeError, ValueError):
        return jsonify({"error": "lat, lng and size must be numbers"}), 400
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or not math.isfinite(size):
        return jsonify({"error": "lat/lng outside valid ranges"}), 400
    size = max(0.005, min(size, MAX_AREA_HALF_WIDTH_DEG))
    bbox = (lng - size, lat - size, lng + size, lat + size)
    feats, src = with_fallback(lambda: db_geojson(bbox=bbox), lambda: files_geojson(bbox=bbox))
    return jsonify({"type": "FeatureCollection", "features": feats, "total": len(feats), "source": src,
                    "bbox": {"min_lng": bbox[0], "min_lat": bbox[1], "max_lng": bbox[2], "max_lat": bbox[3]}})


@app.route("/api/carbon")
def api_carbon():
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 100))
    except ValueError:
        return jsonify({"error": "page and per_page must be integers"}), 400
    if page < 1 or not 1 <= per_page <= MAX_PER_PAGE:
        return jsonify({"error": f"page >= 1 and 1 <= per_page <= {MAX_PER_PAGE}"}), 400

    def db_page():
        col = mdb()["cells"]
        proj = {"_id": 0, "cell_id": 1, "agri_class": 1, "soil_status": 1, "soc_gkg": 1, "soc_stock_tc_ha": 1,
                "soc_source": 1, "npp_flux_tc_ha_yr": 1, "npp_source": 1}
        total = _need(col.count_documents({}), "cells")      # empty collection -> serve the files instead
        recs = list(col.find({}, proj).sort("cell_id", 1).skip((page - 1) * per_page).limit(per_page))
        return {"records": recs, "total": total, "page": page, "per_page": per_page}

    out, src = with_fallback(db_page, lambda: files_page(page, per_page))
    return jsonify({**out, "source": src})


if __name__ == "__main__":
    print(f"\n  Ludhiana carbon dashboard -> http://localhost:5000   (data: {DB_MODE}, results: {RESULTS})\n")
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1", port=int(os.getenv("PORT", "5000")))
