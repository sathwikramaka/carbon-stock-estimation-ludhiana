"""
app.py  —  Carbon Stock Intelligence  v10
==========================================
Serves the Ludhiana carbon stock dashboard.

Database configuration comes from the .env file in the project root.
No passwords appear in this file.

  DB_MODE=local   ->  PostgreSQL + MongoDB running on this machine
  DB_MODE=cloud   ->  Supabase + MongoDB Atlas

Run with:
    python app.py
Then open http://localhost:5000
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import psycopg2, psycopg2.extras
from pymongo import MongoClient
from urllib.parse import quote_plus
from dotenv import load_dotenv
from pathlib import Path
import json, os

# ── APP ───────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR.parent / "frontend" / "templates"),
    static_folder=str(BASE_DIR.parent / "frontend" / "static"),
)
CORS(app)


# ── LOAD .env ─────────────────────────────────────────────────
# Walk up the folder tree until a .env file is found.
def find_env(start: Path):
    for folder in [start, *start.parents]:
        candidate = folder / ".env"
        if candidate.exists():
            return candidate
    return None

ENV_PATH = find_env(BASE_DIR)
if ENV_PATH:
    load_dotenv(ENV_PATH)
    print(f"Loaded config from {ENV_PATH}")
else:
    print("WARNING: no .env file found — falling back to defaults.")


# ── DATABASE CONFIG ───────────────────────────────────────────
DB_MODE = os.getenv("DB_MODE", "local").strip().lower()

if DB_MODE == "cloud":
    PG_URL = (
        f"postgresql://{os.getenv('SUPABASE_USER', '')}:"
        f"{quote_plus(os.getenv('SUPABASE_PASSWORD', ''))}@"
        f"{os.getenv('SUPABASE_HOST', '')}:"
        f"{os.getenv('SUPABASE_PORT', '6543')}/"
        f"{os.getenv('SUPABASE_DB', 'postgres')}"
    )
    PG_SSL = "require"
    MDB_URI = os.getenv("ATLAS_URI", "")
else:
    PG_URL = (
        f"postgresql://{os.getenv('PG_USER', 'postgres')}:"
        f"{quote_plus(os.getenv('PG_PASSWORD', ''))}@"
        f"{os.getenv('PG_HOST', 'localhost')}:"
        f"{os.getenv('PG_PORT', '5432')}/"
        f"{os.getenv('PG_DB', 'postgres')}"
    )
    PG_SSL = "prefer"
    MDB_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

MDB_DB = os.getenv("MONGO_DB", "carbon_stock_ludhiana")
print(f"DB_MODE = {DB_MODE}")


def pg():
    return psycopg2.connect(PG_URL, sslmode=PG_SSL)


def mdb():
    return MongoClient(MDB_URI, serverSelectionTimeoutMS=8000)[MDB_DB]


# ── FALLBACK FIGURES ──────────────────────────────────────────
# Used only when a database is unreachable. These match the
# all-cells run (Step 8), not the older test-set extrapolation.
FALLBACK_SUMMARY = {
    # Headline result: soil organic carbon stock, 0-30 cm.
    "total_million_tc":  5.0871,
    "bgc_million_tc":    5.0871,
    "bgc_pct":         100.0,

    # Annual above-ground carbon assimilation from MODIS NPP. Reported
    # separately: this is a flux in MtC/yr, not a stock, and summing it
    # with soil carbon would combine different units and time dimensions.
    "agc_million_tc_per_year": 4.3317,
    "agc_million_tc":    0.0,
    "agc_pct":           0.0,

    "ag_r2":             0.5426,
    "bg_r2":             0.9665,
    "ag_r2_spatial":     0.4028,
    "bg_r2_spatial":     0.9481,
    "ag_rmse":         448.597,
    "bg_rmse":           0.139,
    "total_cells":       64545,
    "agri_cells":        52809,
    "source":            "fallback",
}


# ── SHARED HELPERS ────────────────────────────────────────────
def load_carbon():
    """Load all carbon predictions from MongoDB, keyed by Grid_ID."""
    carbon = {}
    try:
        db = mdb()
        for doc in db["all_predictions"].find(
            {}, {"_id": 0, "Grid_ID": 1, "AGC_tC_ha": 1,
                 "BGC_tC_ha": 1, "Predicted_NPP": 1, "Total_C_tC_ha": 1}
        ):
            gid = doc.get("Grid_ID")
            if gid is not None:
                carbon[int(gid)] = {
                    "agc": round(float(doc.get("AGC_tC_ha", 0) or 0), 4),
                    "bgc": round(float(doc.get("BGC_tC_ha", 0) or 0), 4),
                    "npp": round(float(doc.get("Predicted_NPP", 0) or 0), 1),
                    "tot": round(float(doc.get("Total_C_tC_ha", 0) or 0), 4),
                }
        print(f"Loaded {len(carbon):,} carbon records from MongoDB")
    except Exception as e:
        print("MongoDB error in load_carbon:", e)
    return carbon


def build_features(rows, carbon):
    """Convert PostGIS rows plus the carbon dict into GeoJSON features."""
    features = []
    for row in rows:
        geom_str, gid, agri, agnonag, dem, slope, sand, clay, bd = row
        if not geom_str:
            continue
        c = carbon.get(int(gid), {})
        features.append({
            "type": "Feature",
            "geometry": json.loads(geom_str),
            "properties": {
                "grid_id":    gid,
                "agri":       agri,
                "agnonag":    round(float(agnonag or 0), 4),
                "dem":        round(float(dem or 0), 1),
                "slope":      round(float(slope or 0), 2),
                "sand":       round(float(sand or 0), 1),
                "clay":       round(float(clay or 0), 1),
                "bd":         round(float(bd or 0), 2),
                "agc":        c.get("agc", 0),
                "bgc":        c.get("bgc", 0),
                "npp":        c.get("npp", 0),
                "tot":        c.get("tot", 0),
                "has_carbon": 1 if c else 0,
            }
        })
    return features


# ── SERVE WEBSITE ─────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── /api/health ───────────────────────────────────────────────
@app.route("/api/health")
def api_health():
    """Quick check that both databases are reachable and populated."""
    status = {"db_mode": DB_MODE, "postgres": "down", "mongodb": "down"}
    try:
        conn = pg()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM grid_cells")
        status["grid_cells"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM district_summary")
        status["district_summary_rows"] = cur.fetchone()[0]
        cur.close(); conn.close()
        status["postgres"] = "ok"
    except Exception as e:
        status["postgres_error"] = str(e)
    try:
        db = mdb()
        status["collections"] = {
            name: db[name].count_documents({})
            for name in sorted(db.list_collection_names())
        }
        status["mongodb"] = "ok"
    except Exception as e:
        status["mongodb_error"] = str(e)
    return jsonify(status)


# ── /api/summary ──────────────────────────────────────────────
@app.route("/api/summary")
def api_summary():
    try:
        conn = pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM district_summary ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            d = dict(row)
            payload = dict(FALLBACK_SUMMARY)
            payload.update({
                "total_million_tc": d.get("total_million_tc"),
                "agc_million_tc":   d.get("agc_million_tc"),
                "bgc_million_tc":   d.get("bgc_million_tc"),
                "agc_pct":          d.get("agc_pct"),
                "bgc_pct":          d.get("bgc_pct"),
                "ag_r2":            d.get("ag_r2"),
                "bg_r2":            d.get("bg_r2"),
                "ag_rmse":          d.get("ag_rmse"),
                "bg_rmse":          d.get("bg_rmse"),
                "source":           "database",
            })
            # Cell counts live in MongoDB's metadata document.
            try:
                meta = mdb()["model_metadata"].find_one({}, {"_id": 0})
                if meta:
                    payload["total_cells"] = meta.get("unique_cells",
                                                      payload["total_cells"])
                    payload["agri_cells"] = meta.get("agri_cells",
                                                     payload["agri_cells"])
            except Exception:
                pass
            return jsonify(payload)
    except Exception as e:
        print("PostgreSQL summary error:", e)
    return jsonify(FALLBACK_SUMMARY)


# ── /api/geojson ──────────────────────────────────────────────
@app.route("/api/geojson")
def api_geojson():
    limit = min(int(request.args.get("limit", 1200)), 3000)
    carbon = load_carbon()
    try:
        conn = pg(); cur = conn.cursor()
        cur.execute("""
            SELECT ST_AsGeoJSON(geom), grid_id, agri_class,
                   agnonag_m, dem_mean, slope_mean,
                   sand_pct, clay_pct, bd_gcm3
            FROM grid_cells
            ORDER BY RANDOM()
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall(); cur.close(); conn.close()
    except Exception as e:
        print("PostgreSQL geojson error:", e)
        return jsonify({"type": "FeatureCollection", "features": [], "error": str(e)})

    features = build_features(rows, carbon)
    return jsonify({"type": "FeatureCollection",
                    "features": features, "total": len(features)})


# ── /api/geojson/area ─────────────────────────────────────────
@app.route("/api/geojson/area")
def api_geojson_area():
    """All cells within a bounding box around a clicked point.

    /api/geojson/area?lat=30.82&lng=75.84&size=0.045
    size is the half-width in degrees; 0.045 is roughly 5 km.
    """
    try:
        lat  = float(request.args.get("lat", 30.82))
        lng  = float(request.args.get("lng", 75.84))
        size = float(request.args.get("size", 0.045))
    except (TypeError, ValueError):
        return jsonify({"type": "FeatureCollection", "features": [],
                        "error": "Invalid lat/lng/size"})

    min_lng, max_lng = lng - size, lng + size
    min_lat, max_lat = lat - size, lat + size
    carbon = load_carbon()

    try:
        conn = pg(); cur = conn.cursor()
        cur.execute("""
            SELECT ST_AsGeoJSON(geom), grid_id, agri_class,
                   agnonag_m, dem_mean, slope_mean,
                   sand_pct, clay_pct, bd_gcm3
            FROM grid_cells
            WHERE ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        """, (min_lng, min_lat, max_lng, max_lat))
        rows = cur.fetchall(); cur.close(); conn.close()
    except Exception as e:
        print("PostgreSQL area error:", e)
        return jsonify({"type": "FeatureCollection", "features": [], "error": str(e)})

    features = build_features(rows, carbon)
    print(f"Area query: lat={lat} lng={lng} size={size} -> {len(features)} cells")
    return jsonify({
        "type": "FeatureCollection",
        "features": features,
        "total": len(features),
        "bbox": {"min_lat": min_lat, "max_lat": max_lat,
                 "min_lng": min_lng, "max_lng": max_lng},
    })


# ── /api/ndvi ─────────────────────────────────────────────────
@app.route("/api/ndvi")
def api_ndvi():
    try:
        docs = list(mdb()["ndvi_summary"].find({}, {"_id": 0}).sort("sort_order", 1))
        if docs:
            return jsonify(docs)
    except Exception as e:
        print("MongoDB ndvi error:", e)
    months = ["Jun 24", "Jul 24", "Aug 24", "Sep 24", "Oct 24", "Nov 24",
              "Dec 24", "Jan 25", "Feb 25", "Mar 25", "Apr 25", "May 25"]
    vals = [0.175, 0.246, 0.754, 0.712, 0.469, 0.193,
            0.338, 0.558, 0.714, 0.663, 0.312, 0.217]
    seasons = ["Kharif"] * 6 + ["Rabi"] * 6
    return jsonify([{"month": m, "median_ndvi": v, "season": s, "sort_order": i}
                    for i, (m, v, s) in enumerate(zip(months, vals, seasons))])


# ── /api/carbon ───────────────────────────────────────────────
@app.route("/api/carbon")
def api_carbon():
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(int(request.args.get("per_page", 100)), 500)
    skip     = (page - 1) * per_page
    try:
        col   = mdb()["all_predictions"]
        total = col.count_documents({})
        docs  = list(col.find(
            {}, {"_id": 0, "Grid_ID": 1, "AGC_tC_ha": 1, "BGC_tC_ha": 1,
                 "Predicted_NPP": 1, "Predicted_SOC": 1, "Total_C_tC_ha": 1,
                 "agri_class": 1, "source": 1}
        ).skip(skip).limit(per_page))
        records = [{
            "cell_index":    d.get("Grid_ID", 0),
            "agc_tC_ha":     round(float(d.get("AGC_tC_ha", 0) or 0), 4),
            "bgc_tC_ha":     round(float(d.get("BGC_tC_ha", 0) or 0), 4),
            "predicted_npp": round(float(d.get("Predicted_NPP", 0) or 0), 2),
            "predicted_soc": round(float(d.get("Predicted_SOC", 0) or 0), 4),
            "total_c":       round(float(d.get("Total_C_tC_ha", 0) or 0), 4),
            "agri_class":    d.get("agri_class", 0),
            "source":        d.get("source", ""),
        } for d in docs]
        return jsonify({"ag": records, "bg": records,
                        "ag_total": total, "bg_total": total,
                        "page": page, "per_page": per_page})
    except Exception as e:
        print("MongoDB carbon error:", e)
        return jsonify({"ag": [], "bg": [], "ag_total": 0, "bg_total": 0})


# ── /api/metrics ──────────────────────────────────────────────
@app.route("/api/metrics")
def api_metrics():
    fallback = {
        "ag_r2": 0.5426, "ag_rmse": 448.597, "ag_mae": 314.795,
        "bg_r2": 0.9665, "bg_rmse": 1.392,   "bg_mae": 1.012,
        "ag_train_cells": 10081, "ag_test_cells": 2521,
        "bg_train_cells": 16000, "bg_test_cells": 4000,
        "feature_importance": [
            {"feature": "Rabi_Preci", "importance": 0.3702, "type": "climate"},
            {"feature": "DEM_mean",   "importance": 0.1050, "type": "terrain"},
            {"feature": "LST_Sept20", "importance": 0.0550, "type": "climate"},
            {"feature": "NDVI_May25", "importance": 0.0423, "type": "ndvi"},
            {"feature": "Rabi_LST_2", "importance": 0.0340, "type": "climate"},
            {"feature": "NDVI_Jan25", "importance": 0.0333, "type": "ndvi"},
            {"feature": "NDVI_Aug24", "importance": 0.0325, "type": "ndvi"},
            {"feature": "NDVI_Feb25", "importance": 0.0260, "type": "ndvi"},
            {"feature": "NDVI_Oct24", "importance": 0.0260, "type": "ndvi"},
            {"feature": "NDVI_Apr25", "importance": 0.0250, "type": "ndvi"},
        ],
        "comparison": [
            {"model": "Random Forest", "target": "NPP", "r2": 0.5426,
             "rmse": 448.597, "mae": 314.795, "best": True},
            {"model": "GradientBoost", "target": "NPP", "r2": 0.5250,
             "rmse": 457.103, "mae": 326.766, "best": False},
            {"model": "Random Forest", "target": "SOC", "r2": 0.9665,
             "rmse": 1.392, "mae": 1.012, "best": True},
            {"model": "GradientBoost", "target": "SOC", "r2": 0.9639,
             "rmse": 1.445, "mae": 1.063, "best": False},
        ],
    }
    try:
        doc = mdb()["model_metadata"].find_one({}, {"_id": 0})
        if doc:
            # Merge, so a partial document never blanks the charts.
            merged = dict(fallback)
            merged.update({k: v for k, v in doc.items() if v not in (None, [], {})})
            return jsonify(merged)
    except Exception as e:
        print("MongoDB metrics error:", e)
    return jsonify(fallback)


# ── START ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  Carbon Intelligence  ->  http://localhost:5000")
    print(f"  Database mode: {DB_MODE}")
    print("=" * 50 + "\n")
    app.run(debug=True, port=5000)