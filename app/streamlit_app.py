"""Public version of the Carbon Stock Intelligence dashboard (Streamlit Community Cloud).

The page is the Flask dashboard's own frontend (IIRS/Carbon_Stocks/carbon_project/
frontend), served without a Flask server: the pipeline results are embedded in the
page, and frontend/static/static_api.js answers every /api/* request from them with
the same JSON the Flask backend returns. Nothing here computes a number; it shows
what IIRS/Scrpit/02_carbon_pipeline.ipynb wrote to IIRS/Carbon_Stocks/results/.

    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "IIRS" / "Carbon_Stocks" / "results"
FRONTEND = ROOT / "IIRS" / "Carbon_Stocks" / "carbon_project" / "frontend"
NEEDED = ("district_summary.json", "model_metrics.json", "ndvi_monthly.json", "carbon_cells.parquet")
PAGE_HEIGHT = 1000


def _rounded(s: pd.Series, nd: int) -> list:
    v = s.astype(float).round(nd)
    return [None if pd.isna(x) else (int(x) if nd == 0 else float(x)) for x in v]


def _codes(s: pd.Series) -> tuple[list[int], list[str]]:
    labels = sorted(s.dropna().astype(str).unique())
    lookup = {lab: i for i, lab in enumerate(labels)}
    return [lookup[str(x)] for x in s], labels


def build_page(results: Path = RESULTS, frontend: Path = FRONTEND) -> str:
    """The frontend HTML with its scripts and the pipeline results inlined."""
    read = lambda name: json.loads((results / name).read_text(encoding="utf-8"))  # noqa: E731
    cells = pd.read_parquet(results / "carbon_cells.parquet")
    cells = cells.sort_values("cell_id", kind="stable").reset_index(drop=True)   # same order as the Flask API
    soc_src, soc_labels = _codes(cells["soc_source"])
    npp_src, npp_labels = _codes(cells["npp_source"])
    data = {
        "summary": read("district_summary.json"),
        "metrics": read("model_metrics.json"),
        "ndvi": read("ndvi_monthly.json"),
        "soc_sources": soc_labels,
        "npp_sources": npp_labels,
        "cells": {
            "r": cells["grid_row"].astype(int).tolist(), "c": cells["grid_col"].astype(int).tolist(),
            "a": _rounded(cells["agri_class"], 0), "g": _rounded(cells["Ag/NonAg_m"], 3),
            "e": _rounded(cells["DEM_mean"], 1), "sl": _rounded(cells["Slope_mean"], 2),
            "st": cells["soil_status"].map({"full": 0, "partial": 1, "nodata": 2}).astype(int).tolist(),
            "w": _rounded(cells["w_soil"], 3), "bd": _rounded(cells["bd_gcm3_rec"], 3),
            "sg": _rounded(cells["soc_gkg"], 3), "so": _rounded(cells["soc_stock_tc_ha"], 3), "ss": soc_src,
            "np": _rounded(cells["npp_flux_tc_ha_yr"], 4), "ns": npp_src,
        },
    }
    payload = json.dumps(data, separators=(",", ":"), default=float).replace("</", "<\\/")

    html = (frontend / "templates" / "index.html").read_text(encoding="utf-8")
    shim = (frontend / "static" / "static_api.js").read_text(encoding="utf-8")
    main = (frontend / "static" / "main.js").read_text(encoding="utf-8")
    start = html.index('<script src="/static/main.js')
    end = html.index("</script>", start) + len("</script>")
    scripts = (f"<script>window.__CARBON_DATA__={payload};</script>\n"
               f"<script>\n{shim}\n</script>\n<script>\n{main}\n</script>")
    return html[:start] + scripts + html[end:]


@st.cache_data(show_spinner="Loading results…")
def cached_page(stamp: float) -> str:          # stamp: results modification time, invalidates the cache
    return build_page()


st.set_page_config(page_title="Carbon Stock Intelligence — Ludhiana", page_icon="🛰", layout="wide",
                   initial_sidebar_state="collapsed")
st.html("""<style>
  header[data-testid="stHeader"], footer {display:none}
  .block-container, [data-testid="stMainBlockContainer"] {padding:0 !important; max-width:100% !important}
  [data-testid="stAppViewContainer"], .stApp {background:#020509}
  iframe {border:0; display:block}
</style>""")

missing = [f for f in NEEDED if not (RESULTS / f).exists()]
if missing:
    st.error(f"Results not found ({', '.join(missing)}). Run IIRS/Scrpit/02_carbon_pipeline.ipynb first.")
    st.stop()

stamp = max((RESULTS / f).stat().st_mtime for f in NEEDED)
st.iframe(cached_page(stamp), height=PAGE_HEIGHT)
