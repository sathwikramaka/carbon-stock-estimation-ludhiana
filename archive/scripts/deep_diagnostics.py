"""
deep_diagnostics.py
===================
Follow-up investigation into the two findings from model_diagnostics.py:

  PART A — Is the soil data a lookup table?
           sand, clay and bulk density all correlate ~0.9 with SOC, which is
           not how real soil behaves. Tests whether all four properties come
           from a small set of repeated mapping units.

  PART B — Is Rabi_Preci really about rainfall?
           Tests whether rainfall is a smooth spatial surface that the model
           uses as a stand-in for geographic position.

Nothing is modified. This only reads and reports.

Usage (from the project root, with .venv active):
    python deep_diagnostics.py
"""

import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score
from sklearn.model_selection import train_test_split

SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

ROOT = Path(os.getenv("PROJECT_ROOT", SCRIPT_DIR))
DATA = ROOT / "IIRS" / "Carbon_Stocks"
OUT_FILE = DATA / "deep_diagnostics_report.txt"

RANDOM_STATE = 42
NPP_COL = "Agricultur"
SOC_COL = "SOC_mean"

NDVI_COLS = ["NDVI_Jun24", "NDVI_Jul24", "NDVI_Aug24", "NDVI_Sep24",
             "NDVI_Oct24", "NDVI_Nov24", "NDVI_Dec24", "NDVI_Jan25",
             "NDVI_Feb25", "NDVI_Mar25", "NDVI_Apr25", "NDVI_May25"]

SOIL_COLS = ["sand_pct", "clay_pct", "bd_gcm3"]

RF = dict(n_estimators=200, min_samples_split=4, min_samples_leaf=2,
          n_jobs=-1, random_state=RANDOM_STATE)

if not DATA.is_dir():
    sys.exit(f"Data folder not found: {DATA}\nCheck PROJECT_ROOT in .env")

lines = []


def say(text=""):
    print(text)
    lines.append(text)


def header(text):
    say()
    say("=" * 72)
    say(f"  {text}")
    say("=" * 72)


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


def quick_r2(X, y):
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE)
    m = RandomForestRegressor(**RF).fit(Xtr, ytr)
    return r2_score(yte, np.maximum(m.predict(Xte), 0))


# ══════════════════════════════════════════════════════════════
header("LOADING")

bg = add_centroids(pd.read_csv(DATA / "Below_Ground_Data_geom.csv"))
ag_raw = add_centroids(pd.read_csv(DATA / "Above_ground_data_geom.csv"))
ndvi = pd.read_csv(DATA / "ndvi_monthly_ludhiana_jun24_may25.csv")
ndvi = ndvi.drop(columns=["longitude", "latitude"], errors="ignore")
ndvi = ndvi.groupby("Grid_ID")[NDVI_COLS].mean().reset_index()

ag = ag_raw.merge(ndvi, on="Grid_ID", how="left")
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

say(f"Below-ground rows: {len(bg):,}")
say(f"Above-ground modelling rows: {len(ag_m):,}")


# ══════════════════════════════════════════════════════════════
#  PART A — IS THE SOIL DATA A LOOKUP TABLE?
# ══════════════════════════════════════════════════════════════
header("A1. HOW MANY DISTINCT SOIL PROFILES ARE THERE?")

say("If the soil layers come from a polygon map, many grid cells will share")
say("exactly the same sand/clay/bulk-density combination. Real per-pixel soil")
say("data would give nearly as many combinations as cells.")
say()

for cols, label in [(SOIL_COLS, "sand + clay + bd"),
                    (SOIL_COLS + [SOC_COL], "sand + clay + bd + SOC")]:
    combos = bg[cols].round(4).drop_duplicates()
    pct = 100 * len(combos) / len(bg)
    say(f"{label:<26} {len(combos):>7,} distinct  ({pct:>5.2f}% of {len(bg):,} cells)")

say()
for c in SOIL_COLS + [SOC_COL]:
    say(f"  {c:<12} {bg[c].nunique():>7,} unique values")

n_profiles = len(bg[SOIL_COLS].round(4).drop_duplicates())
if n_profiles < len(bg) * 0.05:
    say()
    say("VERDICT: very few distinct soil profiles. The soil layers behave like")
    say("         a polygon map, not per-pixel measurements.")
else:
    say()
    say("VERDICT: soil values vary widely across cells; not an obvious lookup.")


header("A2. HOW DO THE SOIL VARIABLES RELATE TO EACH OTHER?")

say("In real soil, sand and clay are strongly NEGATIVELY correlated (more of")
say("one means less of the other), and sand is negatively related to organic")
say("carbon. Positive correlations everywhere mean the layers are not")
say("independent measurements.")
say()

corr = bg[SOIL_COLS + [SOC_COL]].corr()
say("            " + "".join(f"{c:>12}" for c in corr.columns))
for i in corr.index:
    say(f"{i:<12}" + "".join(f"{corr.loc[i, j]:>12.4f}" for j in corr.columns))

sand_clay = corr.loc["sand_pct", "clay_pct"]
say()
say(f"sand vs clay correlation = {sand_clay:+.4f}")
if sand_clay > 0.5:
    say("  Expected roughly -0.5 to -0.9 for real texture data.")
    say("  A strong positive value means these are not true texture fractions,")
    say("  or all layers were interpolated from the same coarse surface.")


header("A3. CAN A SINGLE SOIL VARIABLE REPLACE THE WHOLE MODEL?")

say("If one predictor alone reaches nearly the full R2, the other features add")
say("nothing and the model is a one-to-one mapping, not a learned relationship.")
say()

y_bg = bg[SOC_COL]
say(f"{'predictors':<34}{'R2':>10}")
say("-" * 44)
for cols, label in [
    (SOIL_COLS + ["agri_class", "DEM_mean", "Slope_mean"], "full feature set"),
    (SOIL_COLS,        "sand + clay + bd only"),
    (["bd_gcm3"],      "bulk density alone"),
    (["clay_pct"],     "clay alone"),
    (["sand_pct"],     "sand alone"),
    (["lon_c", "lat_c"], "longitude + latitude only"),
]:
    say(f"{label:<34}{quick_r2(bg[cols], y_bg):>10.4f}")

say()
say("If 'longitude + latitude only' scores highly, the model is mostly")
say("learning WHERE a cell is, not what its soil is like.")


header("A4. IS SOC ALREADY AVAILABLE FOR ALL 64,545 CELLS?")

say("If the full-district export already contains SOC, no prediction is needed")
say("at all and the machine-learning step adds nothing to the carbon estimate.")
say()

bgd_all = pd.read_csv(DATA / "BGD_for_all_grids(GEOM).csv", nrows=5)
cols_all = list(bgd_all.columns)
say(f"Columns in BGD_for_all_grids(GEOM).csv:")
for c in cols_all:
    say(f"   {c}")

soc_present = any("soc" in c.lower() for c in cols_all)
say()
if soc_present:
    say("VERDICT: SOC IS present in the full grid export. The model is")
    say("         predicting something you already have. This is the single")
    say("         most important thing to address in the report.")
else:
    say("VERDICT: SOC is NOT in the full grid export, so prediction is needed")
    say("         to extend from 20,000 sampled cells to all cells. The model")
    say("         has a real job, even if its score is inflated.")


# ══════════════════════════════════════════════════════════════
#  PART B — IS RABI_PRECI REALLY ABOUT RAINFALL?
# ══════════════════════════════════════════════════════════════
header("B1. WHAT DOES THE RAINFALL VARIABLE ACTUALLY LOOK LIKE?")

rp = ag_m["Rabi_Preci"]
say(f"  count        {len(rp):,}")
say(f"  unique       {rp.nunique():,}")
say(f"  min          {rp.min():.4f}")
say(f"  max          {rp.max():.4f}")
say(f"  mean         {rp.mean():.4f}")
say(f"  std          {rp.std():.4f}")
say(f"  range/mean   {(rp.max() - rp.min()) / rp.mean() * 100:.1f}%")
say()
say("Rabi season is roughly November to April. Typical Punjab winter rainfall")
say("is 40-100 mm. Check whether the units and magnitude look plausible.")
say()
say("Kharif_Pre for comparison:")
kp = ag_m["Kharif_Pre"]
say(f"  min {kp.min():.2f}   max {kp.max():.2f}   mean {kp.mean():.2f}   std {kp.std():.2f}")


header("B2. IS RAINFALL JUST A MAP OF WHERE YOU ARE?")

say("Fitting rainfall from longitude and latitude alone. A very high R2 means")
say("rainfall is a smooth geographic surface with no local detail, so the")
say("model can use it as a substitute for coordinates.")
say()

coords = ag_m[["lon_c", "lat_c"]]
for col in ["Rabi_Preci", "Kharif_Pre", "DEM_mean", "LST_Sept20", "NDVI_May25"]:
    say(f"  {col:<14} predicted from lon/lat:  R2 = {quick_r2(coords, ag_m[col]):.4f}")

say()
say("Values near 1.00 indicate a purely spatial surface. Values near 0.5 or")
say("lower indicate the variable carries genuine local information.")


header("B3. DOES RAINFALL BEAT PLAIN COORDINATES AT PREDICTING NPP?")

say("If a model given only longitude and latitude does about as well as the")
say("full model, then the apparent skill is geographic position, not process.")
say()

AG_FEATURES = [c for c in ag_m.columns
               if c not in ("agri_class", NPP_COL, "WKT", "Grid_ID", "lon_c", "lat_c")]
y_ag = ag_m[NPP_COL]

say(f"{'predictors':<40}{'R2':>10}")
say("-" * 50)
tests = [
    (AG_FEATURES,                                    "full feature set"),
    (["lon_c", "lat_c"],                             "longitude + latitude only"),
    (["Rabi_Preci"],                                 "Rabi_Preci alone"),
    (["Rabi_Preci", "Kharif_Pre"],                   "both rainfall variables"),
    ([c for c in AG_FEATURES if "Preci" not in c and "Pre" != c[-3:]],
                                                     "full set MINUS rainfall"),
    (NDVI_COLS,                                      "NDVI only (12 months)"),
    (["DEM_mean", "Slope_mean"],                     "terrain only"),
]
for cols, label in tests:
    cols = [c for c in cols if c in ag_m.columns]
    if not cols:
        continue
    say(f"{label:<40}{quick_r2(ag_m[cols], y_ag):>10.4f}")


header("B4. WHAT IS NPP CORRELATED WITH GEOGRAPHICALLY?")

say("Correlation of the target and key predictors with raw position. Strong")
say("correlations here mean the whole dataset has a district-wide gradient")
say("that several variables are independently tracking.")
say()
say(f"{'variable':<16}{'vs longitude':>16}{'vs latitude':>14}")
say("-" * 46)
for col in [NPP_COL, "Rabi_Preci", "Kharif_Pre", "DEM_mean", "LST_Sept20"]:
    rl = float(np.corrcoef(ag_m[col], ag_m["lon_c"])[0, 1])
    rt = float(np.corrcoef(ag_m[col], ag_m["lat_c"])[0, 1])
    say(f"{col:<16}{rl:>16.4f}{rt:>14.4f}")


# ══════════════════════════════════════════════════════════════
header("SUMMARY")

say("Read the verdicts above in this order:")
say()
say("A1/A2  If soil profiles are few and sand/clay correlate positively, the")
say("       soil layers are one coarse product, not independent measurements.")
say()
say("A3     If a single variable or plain coordinates reach nearly the full")
say("       R2, the below-ground model is a lookup, not a learned relationship.")
say()
say("A4     If SOC is already in the full grid file, the prediction step is")
say("       unnecessary for the carbon estimate and should be reframed as a")
say("       validation exercise rather than a requirement.")
say()
say("B2/B3  If rainfall is ~1.00 predictable from coordinates, and coordinates")
say("       alone rival the full model, then Rabi_Preci is a position proxy.")
say("       The fix is not better rainfall data; it is stating that the model")
say("       captures a spatial gradient rather than a rainfall-yield process.")

OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
say()
say(f"Report saved to {OUT_FILE}")
