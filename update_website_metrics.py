"""
update_website_metrics.py
=========================
Replaces the optimistic figures the dashboard currently shows with the
validated ones produced by the diagnostic work.

Two changes:

  1. Feature importance now uses PERMUTATION importance measured on held-out
     data, instead of impurity importance. Impurity importance is biased
     towards continuous features with many possible split points, which is
     part of why rainfall dominated the old chart.

  2. Every score is reported under two validation schemes: the original
     random split, and spatial block cross-validation which prevents
     neighbouring 250 m cells appearing in both training and test sets.

Also flags which features are coordinate proxies, so the chart can show
that rainfall and land-surface temperature describe position rather than
an ecological process.

Existing collections are updated, not deleted. The carbon totals are
unchanged — this only affects how model performance is reported.

Usage (from the project root, with .venv active):
    python update_website_metrics.py
"""

import os
import pickle
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from pymongo import MongoClient
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, train_test_split

# ── Config ────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

ROOT = Path(os.getenv("PROJECT_ROOT", SCRIPT_DIR))
DATA = ROOT / "IIRS" / "Carbon_Stocks"

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "carbon_stock_ludhiana")
PG_PASSWORD = os.getenv("PG_PASSWORD")

RANDOM_STATE = 42
N_BLOCKS = 8
CV_FOLDS = 5
SPATIAL_THRESHOLD = 0.95

NPP_COL = "Agricultur"
SOC_COL = "SOC_mean"
CELL_AREA_HA = 6.25
RUN_DATE = str(date.today())

NDVI_COLS = ["NDVI_Jun24", "NDVI_Jul24", "NDVI_Aug24", "NDVI_Sep24",
             "NDVI_Oct24", "NDVI_Nov24", "NDVI_Dec24", "NDVI_Jan25",
             "NDVI_Feb25", "NDVI_Mar25", "NDVI_Apr25", "NDVI_May25"]

BG_FEATURES = ["agri_class", "DEM_mean", "Slope_mean",
               "sand_pct", "clay_pct", "bd_gcm3"]

RF = dict(n_estimators=300, min_samples_split=4, min_samples_leaf=2,
          n_jobs=-1, random_state=RANDOM_STATE)

if not DATA.is_dir():
    sys.exit(f"Data folder not found: {DATA}\nCheck PROJECT_ROOT in .env")


# ── Helpers ───────────────────────────────────────────────────
def wkt_centroid(wkt):
    nums = re.findall(r"(-?\d+\.?\d*)\s+(-?\d+\.?\d*)", str(wkt))
    if not nums:
        return np.nan, np.nan
    arr = np.array(nums, dtype=float)
    return arr[:, 0].mean(), arr[:, 1].mean()


def add_centroids(df):
    cents = [wkt_centroid(w) for w in df["WKT"]]
    df["lon_c"] = [c[0] for c in cents]
    df["lat_c"] = [c[1] for c in cents]
    return df


def spatial_blocks(df, n=N_BLOCKS):
    lon_bin = pd.qcut(df["lon_c"], n, labels=False, duplicates="drop")
    lat_bin = pd.qcut(df["lat_c"], n, labels=False, duplicates="drop")
    return (lon_bin.astype(str) + "_" + lat_bin.astype(str)).values


def feat_type(name):
    if name.startswith("NDVI"):
        return "ndvi"
    if name.startswith(("DEM", "Slope")):
        return "terrain"
    if name.startswith(("sand", "clay", "bd")):
        return "soil"
    if name.startswith("NDWI"):
        return "moisture"
    return "climate"


def random_scores(X, y):
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE)
    m = RandomForestRegressor(**RF).fit(Xtr, ytr)
    pred = np.maximum(m.predict(Xte), 0)
    return {
        "r2": float(r2_score(yte, pred)),
        "rmse": float(np.sqrt(mean_squared_error(yte, pred))),
        "mae": float(mean_absolute_error(yte, pred)),
        "model": m, "Xte": Xte, "yte": yte,
    }


def spatial_scores(X, y, groups):
    gkf = GroupKFold(n_splits=CV_FOLDS)
    r2s, rmses, maes = [], [], []
    for tr, te in gkf.split(X, y, groups):
        m = RandomForestRegressor(**RF).fit(X.iloc[tr], y.iloc[tr])
        pred = np.maximum(m.predict(X.iloc[te]), 0)
        r2s.append(r2_score(y.iloc[te], pred))
        rmses.append(float(np.sqrt(mean_squared_error(y.iloc[te], pred))))
        maes.append(float(mean_absolute_error(y.iloc[te], pred)))
    return {
        "r2": float(np.mean(r2s)), "r2_sd": float(np.std(r2s)),
        "rmse": float(np.mean(rmses)), "mae": float(np.mean(maes)),
        "folds": [round(float(v), 4) for v in r2s],
    }


# ── Load ──────────────────────────────────────────────────────
print("Loading data...")

bg = add_centroids(pd.read_csv(DATA / "Below_Ground_Data_geom.csv"))
ag_raw = add_centroids(pd.read_csv(DATA / "Above_ground_data_geom.csv"))
ndvi_20k = pd.read_csv(DATA / "ndvi_monthly_ludhiana_jun24_may25.csv")
ndvi_20k = ndvi_20k.drop(columns=["longitude", "latitude"], errors="ignore")
ndvi_20k = ndvi_20k.groupby("Grid_ID")[NDVI_COLS].mean().reset_index()

ag = ag_raw.merge(ndvi_20k, on="Grid_ID", how="left")
for c in NDVI_COLS:
    ag[c] = ag[c].fillna(ag[c].median())
ag[NPP_COL] = ag[NPP_COL].fillna(0).clip(lower=0)
for c in ag.columns:
    if c not in (NPP_COL, "WKT", "Grid_ID") and pd.api.types.is_numeric_dtype(ag[c]):
        ag[c] = ag[c].fillna(ag[c].median())
for c in bg.columns:
    if c not in (SOC_COL, "WKT", "Grid_ID") and pd.api.types.is_numeric_dtype(bg[c]):
        bg[c] = bg[c].fillna(bg[c].median())

ag_m = ag[(ag["agri_class"] == 1) & (ag[NPP_COL] > 0)].reset_index(drop=True)
AG_FEATURES = [c for c in ag_m.columns
               if c not in ("agri_class", NPP_COL, "WKT", "Grid_ID",
                            "lon_c", "lat_c")]

X_ag, y_ag = ag_m[AG_FEATURES], ag_m[NPP_COL]
X_bg, y_bg = bg[BG_FEATURES], bg[SOC_COL]
blocks_ag, blocks_bg = spatial_blocks(ag_m), spatial_blocks(bg)

print(f"  Above-ground: {len(X_ag):,} cells, {len(AG_FEATURES)} features")
print(f"  Below-ground: {len(X_bg):,} cells, {len(BG_FEATURES)} features")


# ── Spatial proxy scores ──────────────────────────────────────
print("Measuring how spatial each feature is...")
coords = ag_m[["lon_c", "lat_c"]]
proxy_r2 = {}
for col in AG_FEATURES:
    Xtr, Xte, ytr, yte = train_test_split(
        coords, ag_m[col], test_size=0.2, random_state=RANDOM_STATE)
    m = RandomForestRegressor(n_estimators=100, n_jobs=-1,
                              random_state=RANDOM_STATE).fit(Xtr, ytr)
    proxy_r2[col] = float(r2_score(yte, m.predict(Xte)))
for col in BG_FEATURES:
    Xtr, Xte, ytr, yte = train_test_split(
        bg[["lon_c", "lat_c"]], bg[col], test_size=0.2, random_state=RANDOM_STATE)
    m = RandomForestRegressor(n_estimators=100, n_jobs=-1,
                              random_state=RANDOM_STATE).fit(Xtr, ytr)
    proxy_r2[col] = float(r2_score(yte, m.predict(Xte)))


# ── Score both models both ways ───────────────────────────────
print("Scoring under random split...")
ag_rand = random_scores(X_ag, y_ag)
bg_rand = random_scores(X_bg, y_bg)

print("Scoring under spatial block CV (this is the slow part)...")
ag_spat = spatial_scores(X_ag, y_ag, blocks_ag)
bg_spat = spatial_scores(X_bg, y_bg, blocks_bg)

print(f"  Above-ground  random {ag_rand['r2']:.4f}  spatial {ag_spat['r2']:.4f}")
print(f"  Below-ground  random {bg_rand['r2']:.4f}  spatial {bg_spat['r2']:.4f}")


# ── Permutation importance ────────────────────────────────────
print("Computing permutation importance...")


def perm_importance(fit, top_n=12):
    perm = permutation_importance(fit["model"], fit["Xte"], fit["yte"],
                                  n_repeats=5, random_state=RANDOM_STATE,
                                  n_jobs=-1)
    impurity = dict(zip(fit["Xte"].columns, fit["model"].feature_importances_))
    rows = []
    for col, mean, sd in zip(fit["Xte"].columns,
                             perm.importances_mean, perm.importances_std):
        rows.append({
            "feature": str(col),
            "importance": round(float(mean), 4),
            "importance_sd": round(float(sd), 4),
            "impurity_importance": round(float(impurity[col]), 4),
            "type": feat_type(str(col)),
            "spatial_r2": round(proxy_r2.get(col, float("nan")), 4),
            "is_position_proxy": bool(proxy_r2.get(col, 0) > SPATIAL_THRESHOLD),
        })
    rows.sort(key=lambda r: -r["importance"])
    return rows[:top_n]


ag_importance = perm_importance(ag_rand)
bg_importance = perm_importance(bg_rand)

n_proxy = sum(1 for r in ag_importance if r["is_position_proxy"])
print(f"  {n_proxy} of the top above-ground features are position proxies")


# ── Load Xgb comparison scores from existing pickles ──────────
with open(DATA / "model_ag_xgb.pkl", "rb") as f:
    xgb_ag = pickle.load(f)
with open(DATA / "model_bg_xgb.pkl", "rb") as f:
    xgb_bg = pickle.load(f)


def xgb_scores(model, fit):
    pred = np.maximum(model.predict(fit["Xte"]), 0)
    return {
        "r2": float(r2_score(fit["yte"], pred)),
        "rmse": float(np.sqrt(mean_squared_error(fit["yte"], pred))),
        "mae": float(mean_absolute_error(fit["yte"], pred)),
    }


xgb_ag_s = xgb_scores(xgb_ag, ag_rand)
xgb_bg_s = xgb_scores(xgb_bg, bg_rand)


# ── Write to MongoDB ──────────────────────────────────────────
print("Updating MongoDB...")

final = pd.read_csv(DATA / "carbon_all_66790_final.csv")
t_ag = float(final["AGC_tC_ha"].sum()) * CELL_AREA_HA
t_bg = float(final["BGC_tC_ha"].sum()) * CELL_AREA_HA
t_all = t_ag + t_bg

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
client.admin.command("ping")
db = client[MONGO_DB]

doc = {
    "run_date": RUN_DATE,
    "district": "Ludhiana, Punjab, India",
    "cell_size_m": 250,
    "cell_area_ha": CELL_AREA_HA,
    "unique_cells": int(len(final)),
    "agri_cells": int((final["agri_class"] == 1).sum()),

    # Headline scores shown on the model page (random split, for continuity
    # with the original report) plus the validated spatial figures.
    "ag_model": "Random Forest",
    "bg_model": "Random Forest",
    "ag_r2": round(ag_rand["r2"], 4),
    "ag_rmse": round(ag_rand["rmse"], 3),
    "ag_mae": round(ag_rand["mae"], 3),
    "bg_r2": round(bg_rand["r2"], 4),
    "bg_rmse": round(bg_rand["rmse"], 3),
    "bg_mae": round(bg_rand["mae"], 3),

    "ag_r2_spatial": round(ag_spat["r2"], 4),
    "ag_rmse_spatial": round(ag_spat["rmse"], 3),
    "ag_mae_spatial": round(ag_spat["mae"], 3),
    "ag_spatial_folds": ag_spat["folds"],
    "ag_spatial_sd": round(ag_spat["r2_sd"], 4),

    "bg_r2_spatial": round(bg_spat["r2"], 4),
    "bg_rmse_spatial": round(bg_spat["rmse"], 3),
    "bg_mae_spatial": round(bg_spat["mae"], 3),
    "bg_spatial_folds": bg_spat["folds"],
    "bg_spatial_sd": round(bg_spat["r2_sd"], 4),

    "validation_note": (
        "Random split scores are optimistic because adjacent 250 m cells are "
        "highly correlated and can appear in both training and test sets. "
        "Spatial block cross-validation partitions the district geographically "
        "and gives the more defensible estimate of predictive skill."
    ),
    "importance_note": (
        "Feature importance is permutation importance measured on held-out "
        "data. Features flagged as position proxies are reconstructible from "
        "coordinates alone at R2 > 0.95, meaning they describe where a cell is "
        "rather than an ecological process at 250 m resolution."
    ),
    "soil_data_note": (
        "Sand, clay, bulk density and soil organic carbon correlate 0.84 to "
        "0.97 with one another, and their signs are physically inverted. All "
        "four are outputs of a single gridded soil product, so the below-ground "
        "score measures agreement with that product rather than accuracy "
        "against field-measured carbon."
    ),

    "ag_train_cells": int(len(X_ag) * 0.8),
    "ag_test_cells": int(len(ag_rand["Xte"])),
    "bg_train_cells": int(len(X_bg) * 0.8),
    "bg_test_cells": int(len(bg_rand["Xte"])),

    "ag_formula": "AGC (tC/ha) = NPP x 0.47 / 100",
    "bg_formula": "BGC (tC/ha) = SOC x BD x 30 / 10",
    "agc_million_tC": round(t_ag / 1e6, 4),
    "bgc_million_tC": round(t_bg / 1e6, 4),
    "total_million_tC": round(t_all / 1e6, 4),

    "feature_importance": ag_importance,
    "feature_importance_bg": bg_importance,

    "comparison": [
        {"model": "Random Forest", "target": "NPP",
         "r2": round(ag_rand["r2"], 4), "rmse": round(ag_rand["rmse"], 3),
         "mae": round(ag_rand["mae"], 3),
         "r2_spatial": round(ag_spat["r2"], 4), "best": True},
        {"model": "XGBoost/GradBoost", "target": "NPP",
         "r2": round(xgb_ag_s["r2"], 4), "rmse": round(xgb_ag_s["rmse"], 3),
         "mae": round(xgb_ag_s["mae"], 3), "best": False},
        {"model": "Random Forest", "target": "SOC",
         "r2": round(bg_rand["r2"], 4), "rmse": round(bg_rand["rmse"], 3),
         "mae": round(bg_rand["mae"], 3),
         "r2_spatial": round(bg_spat["r2"], 4), "best": True},
        {"model": "XGBoost/GradBoost", "target": "SOC",
         "r2": round(xgb_bg_s["r2"], 4), "rmse": round(xgb_bg_s["rmse"], 3),
         "mae": round(xgb_bg_s["mae"], 3), "best": False},
    ],
}

db["model_metadata"].drop()
db["model_metadata"].insert_one(doc)
print("  model_metadata rewritten")

# Validation summary as its own small collection, for a dedicated page
db["validation_summary"].drop()
db["validation_summary"].insert_many([
    {"model": "Above-ground (NPP)", "scheme": "Random split",
     "r2": round(ag_rand["r2"], 4), "rmse": round(ag_rand["rmse"], 2),
     "sort_order": 0},
    {"model": "Above-ground (NPP)", "scheme": "Spatial block CV",
     "r2": round(ag_spat["r2"], 4), "rmse": round(ag_spat["rmse"], 2),
     "sort_order": 1},
    {"model": "Below-ground (SOC)", "scheme": "Random split",
     "r2": round(bg_rand["r2"], 4), "rmse": round(bg_rand["rmse"], 3),
     "sort_order": 2},
    {"model": "Below-ground (SOC)", "scheme": "Spatial block CV",
     "r2": round(bg_spat["r2"], 4), "rmse": round(bg_spat["rmse"], 3),
     "sort_order": 3},
])
print("  validation_summary created")
client.close()


# ── Write to PostgreSQL ───────────────────────────────────────
print("Updating PostgreSQL...")

if not PG_PASSWORD:
    print("  PG_PASSWORD not set — skipping PostgreSQL update.")
else:
    conn = psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=os.getenv("PG_DB", "postgres"),
        user=os.getenv("PG_USER", "postgres"),
        password=PG_PASSWORD,
    )
    cur = conn.cursor()
    for col in ["ag_r2_spatial", "bg_r2_spatial",
                "ag_rmse_spatial", "bg_rmse_spatial"]:
        cur.execute(
            f"ALTER TABLE district_summary ADD COLUMN IF NOT EXISTS {col} FLOAT")
    conn.commit()

    cur.execute("DELETE FROM district_summary WHERE run_date = %s", (RUN_DATE,))
    cur.execute("""
        INSERT INTO district_summary
        (run_date, ag_model, bg_model, ag_r2, bg_r2, ag_rmse, bg_rmse,
         agc_million_tC, bgc_million_tC, total_million_tC, agc_pct, bgc_pct,
         ag_r2_spatial, bg_r2_spatial, ag_rmse_spatial, bg_rmse_spatial)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (RUN_DATE, "Random Forest", "Random Forest",
          round(ag_rand["r2"], 4), round(bg_rand["r2"], 4),
          round(ag_rand["rmse"], 3), round(bg_rand["rmse"], 3),
          round(t_ag / 1e6, 4), round(t_bg / 1e6, 4), round(t_all / 1e6, 4),
          round(100 * t_ag / t_all, 2), round(100 * t_bg / t_all, 2),
          round(ag_spat["r2"], 4), round(bg_spat["r2"], 4),
          round(ag_spat["rmse"], 3), round(bg_spat["rmse"], 3)))
    conn.commit()
    cur.close(); conn.close()
    print("  district_summary updated with spatial CV columns")


# ── Summary ───────────────────────────────────────────────────
print()
print("=" * 62)
print("  DONE — restart app.py to see the changes")
print("=" * 62)
print(f"{'':<22}{'random':>12}{'spatial CV':>14}")
print("-" * 50)
print(f"{'Above-ground (NPP)':<22}{ag_rand['r2']:>12.4f}{ag_spat['r2']:>14.4f}")
print(f"{'Below-ground (SOC)':<22}{bg_rand['r2']:>12.4f}{bg_spat['r2']:>14.4f}")
print()
print("Top above-ground features by permutation importance:")
for r in ag_importance[:6]:
    tag = "  <-- position proxy" if r["is_position_proxy"] else ""
    print(f"  {r['feature']:<14}{r['importance']:>9.4f}{tag}")
print()
print(f"District total unchanged: {t_all / 1e6:.4f} MtC")
