"""
fix_mongo_for_website.py
========================
Rewrites two MongoDB collections so their field names match what the
website's app.py expects:

  ndvi_summary    needs  month, median_ndvi, season, sort_order
  model_metadata  needs  feature_importance[] and comparison[]

Everything is recomputed from the saved models and CSV files, so this runs
standalone — no notebook kernel state required.

Usage (from the project root, with .venv active):
    python fix_mongo_for_website.py
"""

import os
import pickle
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error

# ── Config ────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

ROOT = Path(os.getenv("PROJECT_ROOT", SCRIPT_DIR))
DATA = ROOT / "IIRS" / "Carbon_Stocks"

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "carbon_stock_ludhiana")

CELL_AREA_HA = 6.25
RUN_DATE = str(date.today())

NDVI_COLS = ["NDVI_Jun24", "NDVI_Jul24", "NDVI_Aug24", "NDVI_Sep24",
             "NDVI_Oct24", "NDVI_Nov24", "NDVI_Dec24", "NDVI_Jan25",
             "NDVI_Feb25", "NDVI_Mar25", "NDVI_Apr25", "NDVI_May25"]

MONTH_LABELS = ["Jun 24", "Jul 24", "Aug 24", "Sep 24", "Oct 24", "Nov 24",
                "Dec 24", "Jan 25", "Feb 25", "Mar 25", "Apr 25", "May 25"]

if not DATA.is_dir():
    sys.exit(f"Data folder not found: {DATA}\nCheck PROJECT_ROOT in .env")

print(f"Data folder: {DATA}")


# ── Load test data and models ─────────────────────────────────
X_ag_test = pd.read_csv(DATA / "ag_X_test.csv")
y_ag_test = pd.read_csv(DATA / "ag_y_test.csv").squeeze()
X_bg_test = pd.read_csv(DATA / "bg_X_test.csv")
y_bg_test = pd.read_csv(DATA / "bg_y_test.csv").squeeze()
X_ag_train = pd.read_csv(DATA / "ag_X_train.csv")
X_bg_train = pd.read_csv(DATA / "bg_X_train.csv")

with open(DATA / "model_ag_rf.pkl", "rb") as f:  rf_ag = pickle.load(f)
with open(DATA / "model_ag_xgb.pkl", "rb") as f: xgb_ag = pickle.load(f)
with open(DATA / "model_bg_rf.pkl", "rb") as f:  rf_bg = pickle.load(f)
with open(DATA / "model_bg_xgb.pkl", "rb") as f: xgb_bg = pickle.load(f)


def score(model, X, y, label, target):
    pred = np.maximum(model.predict(X), 0)
    return {
        "label": label,
        "target": target,
        "R2": float(r2_score(y, pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y, pred))),
        "MAE": float(mean_absolute_error(y, pred)),
        "_model": model,
        "_X": X,
    }


results = [
    score(rf_ag,  X_ag_test, y_ag_test, "Random Forest",     "NPP"),
    score(xgb_ag, X_ag_test, y_ag_test, "XGBoost/GradBoost", "NPP"),
    score(rf_bg,  X_bg_test, y_bg_test, "Random Forest",     "SOC"),
    score(xgb_bg, X_bg_test, y_bg_test, "XGBoost/GradBoost", "SOC"),
]

best_ag = max((r for r in results if r["target"] == "NPP"), key=lambda x: x["R2"])
best_bg = max((r for r in results if r["target"] == "SOC"), key=lambda x: x["R2"])

print(f"Best AG: {best_ag['label']}  R2={best_ag['R2']:.4f}")
print(f"Best BG: {best_bg['label']}  R2={best_bg['R2']:.4f}")


# ── Connect ───────────────────────────────────────────────────
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
client.admin.command("ping")
db = client[MONGO_DB]
print(f"Connected to {MONGO_DB}")


# ── ndvi_summary ──────────────────────────────────────────────
ndvi = pd.read_csv(DATA / "ndvi_monthly_ludhiana_all_66790.csv")

ndvi_docs = []
for i, col in enumerate(NDVI_COLS):
    if col not in ndvi.columns:
        continue
    ndvi_docs.append({
        "month":       MONTH_LABELS[i],
        "median_ndvi": round(float(ndvi[col].median(skipna=True)), 4),
        "mean_ndvi":   round(float(ndvi[col].mean(skipna=True)), 4),
        "min_ndvi":    round(float(ndvi[col].min(skipna=True)), 4),
        "max_ndvi":    round(float(ndvi[col].max(skipna=True)), 4),
        "season":      "Kharif" if i < 6 else "Rabi",
        "sort_order":  i,
        "run_date":    RUN_DATE,
    })

db["ndvi_summary"].drop()
db["ndvi_summary"].insert_many(ndvi_docs)
print(f"  ndvi_summary  : {len(ndvi_docs)} documents")


# ── model_metadata ────────────────────────────────────────────
final = pd.read_csv(DATA / "carbon_all_66790_final.csv")
t_ag = float(final["AGC_tC_ha"].sum()) * CELL_AREA_HA
t_bg = float(final["BGC_tC_ha"].sum()) * CELL_AREA_HA
t_all = t_ag + t_bg


def feat_type(name: str) -> str:
    if name.startswith("NDVI"):
        return "ndvi"
    if name.startswith(("DEM", "Slope")):
        return "terrain"
    if name.startswith(("sand", "clay", "bd")):
        return "soil"
    return "climate"


importances = sorted(
    zip(best_ag["_X"].columns, best_ag["_model"].feature_importances_),
    key=lambda x: -x[1],
)[:10]

db["model_metadata"].drop()
db["model_metadata"].insert_one({
    "run_date": RUN_DATE,
    "district": "Ludhiana, Punjab, India",
    "cell_size_m": 250,
    "cell_area_ha": CELL_AREA_HA,
    "unique_cells": int(len(final)),
    "agri_cells": int((final["agri_class"] == 1).sum()),

    "ag_model": best_ag["label"],
    "bg_model": best_bg["label"],
    "ag_r2":   round(best_ag["R2"], 4),
    "ag_rmse": round(best_ag["RMSE"], 3),
    "ag_mae":  round(best_ag["MAE"], 3),
    "bg_r2":   round(best_bg["R2"], 4),
    "bg_rmse": round(best_bg["RMSE"], 3),
    "bg_mae":  round(best_bg["MAE"], 3),

    "ag_train_cells": int(len(X_ag_train)),
    "ag_test_cells":  int(len(X_ag_test)),
    "bg_train_cells": int(len(X_bg_train)),
    "bg_test_cells":  int(len(X_bg_test)),

    "ag_formula": "AGC (tC/ha) = NPP x 0.47 / 100",
    "bg_formula": "BGC (tC/ha) = SOC x BD x 30 / 10",
    "agc_million_tC":   round(t_ag / 1e6, 4),
    "bgc_million_tC":   round(t_bg / 1e6, 4),
    "total_million_tC": round(t_all / 1e6, 4),

    "feature_importance": [
        {"feature": str(f), "importance": round(float(v), 4), "type": feat_type(str(f))}
        for f, v in importances
    ],
    "comparison": [
        {"model": r["label"], "target": r["target"],
         "r2": round(r["R2"], 4), "rmse": round(r["RMSE"], 3),
         "mae": round(r["MAE"], 3),
         "best": bool(r is best_ag or r is best_bg)}
        for r in results
    ],
})
print("  model_metadata: 1 document (with feature_importance and comparison)")

print("\nCollection counts:")
for name in sorted(db.list_collection_names()):
    print(f"  {name:<18} {db[name].count_documents({}):>7,}")

client.close()
print("\nDone.")
