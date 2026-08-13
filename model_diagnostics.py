"""
model_diagnostics.py
====================
Tests whether the carbon stock models are as good as their scores suggest.

Runs six diagnostics:

  1. Feature cardinality       — are any predictors acting as region labels?
  2. Target correlations       — how related are the soil predictors to SOC?
  3. Permutation importance    — honest importance on held-out data
  4. Below-ground ablation     — what happens when bd_gcm3 is removed?
  5. Spatial block CV          — scores when neighbouring cells cannot leak
  6. Baseline comparison       — how much better than predicting the mean?

Nothing is modified. This only reads and reports.

Usage (from the project root, with .venv active):
    python model_diagnostics.py
"""

import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, train_test_split

# ── Config ────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

ROOT = Path(os.getenv("PROJECT_ROOT", SCRIPT_DIR))
DATA = ROOT / "IIRS" / "Carbon_Stocks"
OUT_FILE = DATA / "diagnostics_report.txt"

RANDOM_STATE = 42
N_BLOCKS = 8          # spatial grid is N_BLOCKS x N_BLOCKS
CV_FOLDS = 5

NPP_COL = "Agricultur"
SOC_COL = "SOC_mean"

NDVI_COLS = ["NDVI_Jun24", "NDVI_Jul24", "NDVI_Aug24", "NDVI_Sep24",
             "NDVI_Oct24", "NDVI_Nov24", "NDVI_Dec24", "NDVI_Jan25",
             "NDVI_Feb25", "NDVI_Mar25", "NDVI_Apr25", "NDVI_May25"]

BG_FEATURES = ["agri_class", "DEM_mean", "Slope_mean",
               "sand_pct", "clay_pct", "bd_gcm3"]

RF_PARAMS = dict(n_estimators=200, min_samples_split=4, min_samples_leaf=2,
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


# ── Load data with geometry retained ──────────────────────────
header("LOADING DATA")

ag_raw = pd.read_csv(DATA / "Above_ground_data_geom.csv")
bg_raw = pd.read_csv(DATA / "Below_Ground_Data_geom.csv")
ndvi = pd.read_csv(DATA / "ndvi_monthly_ludhiana_jun24_may25.csv")

ndvi = ndvi.drop(columns=["longitude", "latitude"], errors="ignore")
ndvi = ndvi.groupby("Grid_ID")[NDVI_COLS].mean().reset_index()

ag = ag_raw.merge(ndvi, on="Grid_ID", how="left")
for col in NDVI_COLS:
    ag[col] = ag[col].fillna(ag[col].median())

ag[NPP_COL] = ag[NPP_COL].fillna(0).clip(lower=0)
for col in ag.columns:
    if col not in (NPP_COL, "WKT", "Grid_ID") and pd.api.types.is_numeric_dtype(ag[col]):
        ag[col] = ag[col].fillna(ag[col].median())
for col in bg_raw.columns:
    if col not in (SOC_COL, "WKT", "Grid_ID") and pd.api.types.is_numeric_dtype(bg_raw[col]):
        bg_raw[col] = bg_raw[col].fillna(bg_raw[col].median())

say(f"Above-ground rows: {len(ag):,}")
say(f"Below-ground rows: {len(bg_raw):,}")


def wkt_centroid(wkt):
    """Rough polygon centroid: mean of all coordinate pairs in the WKT string."""
    nums = re.findall(r"(-?\d+\.?\d*)\s+(-?\d+\.?\d*)", str(wkt))
    if not nums:
        return np.nan, np.nan
    arr = np.array(nums, dtype=float)
    return arr[:, 0].mean(), arr[:, 1].mean()


for df in (ag, bg_raw):
    cents = [wkt_centroid(w) for w in df["WKT"]]
    df["lon_c"] = [c[0] for c in cents]
    df["lat_c"] = [c[1] for c in cents]

say(f"Centroids parsed. Lon range {ag['lon_c'].min():.3f} to {ag['lon_c'].max():.3f}, "
    f"lat range {ag['lat_c'].min():.3f} to {ag['lat_c'].max():.3f}")


def spatial_blocks(df, n=N_BLOCKS):
    """Assign each row to one of n x n spatial blocks."""
    lon_bin = pd.qcut(df["lon_c"], n, labels=False, duplicates="drop")
    lat_bin = pd.qcut(df["lat_c"], n, labels=False, duplicates="drop")
    return (lon_bin.astype(str) + "_" + lat_bin.astype(str)).values


# Build modelling frames
ag_model = ag[ag["agri_class"] == 1]
ag_model = ag_model[ag_model[NPP_COL] > 0].reset_index(drop=True)
AG_FEATURES = [c for c in ag_model.columns
               if c not in ("agri_class", NPP_COL, "WKT", "Grid_ID", "lon_c", "lat_c")]

X_ag, y_ag = ag_model[AG_FEATURES], ag_model[NPP_COL]
X_bg, y_bg = bg_raw[BG_FEATURES], bg_raw[SOC_COL]

blocks_ag = spatial_blocks(ag_model)
blocks_bg = spatial_blocks(bg_raw)

say(f"AG modelling rows: {len(X_ag):,}  features: {len(AG_FEATURES)}")
say(f"BG modelling rows: {len(X_bg):,}  features: {len(BG_FEATURES)}")


# ── 1. Feature cardinality ────────────────────────────────────
header("1. FEATURE CARDINALITY — is any predictor a regional label?")

say("A feature with very few distinct values across 20,000 cells is a coarse")
say("raster. A tree can use it to identify *where* a cell is rather than what")
say("it is like, which looks like skill but does not generalise.")
say()
say(f"{'Feature':<16}{'unique':>10}{'unique %':>11}{'std':>12}{'verdict':>16}")
say("-" * 66)

card_rows = []
for col in AG_FEATURES:
    n_uniq = int(X_ag[col].nunique())
    pct = 100 * n_uniq / len(X_ag)
    std = float(X_ag[col].std())
    if pct < 1:
        verdict = "COARSE - suspect"
    elif pct < 10:
        verdict = "low variety"
    else:
        verdict = "ok"
    card_rows.append((col, n_uniq, pct, std, verdict))

for col, n_uniq, pct, std, verdict in sorted(card_rows, key=lambda r: r[2]):
    say(f"{col:<16}{n_uniq:>10,}{pct:>10.2f}%{std:>12.4f}{verdict:>16}")


# ── 2. Correlations with the targets ──────────────────────────
header("2. CORRELATION WITH TARGET — is SOC being predicted from itself?")

say("sand_pct, clay_pct, bd_gcm3 and SOC_mean usually come from the same")
say("gridded soil product, where bulk density is derived from organic carbon")
say("by a pedotransfer function. If so, the predictors are not independent")
say("measurements and the R2 is inflated.")
say()
say(f"{'BG feature':<16}{'corr with SOC':>16}")
say("-" * 32)
for col in BG_FEATURES:
    r = float(np.corrcoef(X_bg[col], y_bg)[0, 1])
    flag = "  <-- very strong" if abs(r) > 0.8 else ("  <-- strong" if abs(r) > 0.6 else "")
    say(f"{col:<16}{r:>16.4f}{flag}")

say()
say(f"{'AG feature':<16}{'corr with NPP':>16}")
say("-" * 32)
ag_corrs = sorted(((c, float(np.corrcoef(X_ag[c], y_ag)[0, 1])) for c in AG_FEATURES),
                  key=lambda x: -abs(x[1]))
for col, r in ag_corrs[:8]:
    say(f"{col:<16}{r:>16.4f}")


# ── 3. Permutation importance ─────────────────────────────────
header("3. PERMUTATION IMPORTANCE — honest importance on held-out data")

say("The dashboard chart uses impurity importance, which is biased towards")
say("continuous features with many split points. Permutation importance")
say("measures how much test performance actually drops when a feature is")
say("shuffled. Large gaps between the two rankings mean the chart misleads.")

for name, X, y in [("ABOVE-GROUND (NPP)", X_ag, y_ag),
                   ("BELOW-GROUND (SOC)", X_bg, y_bg)]:
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE)
    model = RandomForestRegressor(**RF_PARAMS).fit(Xtr, ytr)

    imp_impurity = dict(zip(X.columns, model.feature_importances_))
    perm = permutation_importance(model, Xte, yte, n_repeats=5,
                                  random_state=RANDOM_STATE, n_jobs=-1)
    imp_perm = dict(zip(X.columns, perm.importances_mean))

    say()
    say(f"{name}")
    say(f"{'feature':<16}{'impurity':>12}{'permutation':>14}{'note':>22}")
    say("-" * 64)
    for col in sorted(X.columns, key=lambda c: -imp_perm[c])[:10]:
        gap = ""
        rank_imp = sorted(X.columns, key=lambda c: -imp_impurity[c]).index(col)
        rank_perm = sorted(X.columns, key=lambda c: -imp_perm[c]).index(col)
        if abs(rank_imp - rank_perm) >= 3:
            gap = f"rank {rank_imp+1} -> {rank_perm+1}"
        say(f"{col:<16}{imp_impurity[col]:>12.4f}{imp_perm[col]:>14.4f}{gap:>22}")


# ── 4. Below-ground ablation ──────────────────────────────────
header("4. BELOW-GROUND ABLATION — how much of the 0.97 is bulk density?")

say("bd_gcm3 is used twice: as a predictor of SOC, and as a multiplier in")
say("BGC = SOC x BD x 30 / 10. If removing it collapses the score, the model")
say("was largely reading the carbon signal back out of the soil product.")
say()

Xtr, Xte, ytr, yte = train_test_split(
    X_bg, y_bg, test_size=0.2, random_state=RANDOM_STATE)

ablations = {
    "all features":            BG_FEATURES,
    "without bd_gcm3":         [c for c in BG_FEATURES if c != "bd_gcm3"],
    "without sand/clay/bd":    ["agri_class", "DEM_mean", "Slope_mean"],
    "only terrain":            ["DEM_mean", "Slope_mean"],
}

say(f"{'feature set':<24}{'R2':>10}{'RMSE':>10}{'MAE':>10}")
say("-" * 54)
ablation_scores = {}
for label, feats in ablations.items():
    m = RandomForestRegressor(**RF_PARAMS).fit(Xtr[feats], ytr)
    pred = np.maximum(m.predict(Xte[feats]), 0)
    r2 = r2_score(yte, pred)
    ablation_scores[label] = r2
    say(f"{label:<24}{r2:>10.4f}"
        f"{np.sqrt(mean_squared_error(yte, pred)):>10.3f}"
        f"{mean_absolute_error(yte, pred):>10.3f}")

drop = ablation_scores["all features"] - ablation_scores["without bd_gcm3"]
say()
say(f"Removing bd_gcm3 changes R2 by {drop:+.4f}")
if drop > 0.25:
    say("VERDICT: bulk density carries most of the signal. The 0.97 is")
    say("         substantially circular and must be reported with that caveat.")
elif drop > 0.10:
    say("VERDICT: bulk density carries a meaningful share of the signal.")
else:
    say("VERDICT: the score does not depend heavily on bulk density alone.")
    say("         Leakage may still come from sand/clay sharing a source.")


# ── 5. Spatial block cross-validation ─────────────────────────
header("5. SPATIAL BLOCK CV — scores when neighbours cannot leak")

say("A random split puts adjacent 250 m cells in both train and test. Because")
say("neighbouring cells are nearly identical, the model can look up an answer")
say("it has already seen. Blocking by geography removes that shortcut and")
say("gives the score you would get on genuinely new ground.")
say()


def block_cv(X, y, groups, label):
    gkf = GroupKFold(n_splits=CV_FOLDS)
    scores = []
    for tr, te in gkf.split(X, y, groups):
        m = RandomForestRegressor(**RF_PARAMS).fit(X.iloc[tr], y.iloc[tr])
        pred = np.maximum(m.predict(X.iloc[te]), 0)
        scores.append(r2_score(y.iloc[te], pred))
    scores = np.array(scores)
    say(f"{label:<22} folds: " + "  ".join(f"{s:.4f}" for s in scores))
    say(f"{'':<22} mean R2 = {scores.mean():.4f}  (sd {scores.std():.4f})")
    return scores.mean()


# Random split for comparison
def random_split_r2(X, y):
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE)
    m = RandomForestRegressor(**RF_PARAMS).fit(Xtr, ytr)
    return r2_score(yte, np.maximum(m.predict(Xte), 0))


ag_random = random_split_r2(X_ag, y_ag)
bg_random = random_split_r2(X_bg, y_bg)

ag_spatial = block_cv(X_ag, y_ag, blocks_ag, "Above-ground (NPP)")
say()
bg_spatial = block_cv(X_bg, y_bg, blocks_bg, "Below-ground (SOC)")

say()
say(f"{'model':<22}{'random split':>15}{'spatial CV':>13}{'inflation':>12}")
say("-" * 62)
say(f"{'Above-ground (NPP)':<22}{ag_random:>15.4f}{ag_spatial:>13.4f}"
    f"{ag_random - ag_spatial:>+12.4f}")
say(f"{'Below-ground (SOC)':<22}{bg_random:>15.4f}{bg_spatial:>13.4f}"
    f"{bg_random - bg_spatial:>+12.4f}")
say()
say("The spatial CV column is the number to report as honest predictive skill.")


# ── 6. Baseline comparison ────────────────────────────────────
header("6. BASELINE — how much better than guessing the mean?")

say("R2 of 0 means no better than always predicting the average. A model with")
say("a high R2 on a low-variance target may still be nearly useless.")
say()
say(f"{'model':<22}{'model R2':>12}{'baseline R2':>14}{'target sd':>12}")
say("-" * 60)

for label, X, y, spatial in [("Above-ground (NPP)", X_ag, y_ag, ag_spatial),
                             ("Below-ground (SOC)", X_bg, y_bg, bg_spatial)]:
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE)
    dummy = DummyRegressor(strategy="mean").fit(Xtr, ytr)
    say(f"{label:<22}{spatial:>12.4f}"
        f"{r2_score(yte, dummy.predict(Xte)):>14.4f}{float(y.std()):>12.4f}")


# ── Summary ───────────────────────────────────────────────────
header("WHAT TO DO WITH THIS")

say("1. Report the spatial CV scores as your headline model performance, and")
say("   the random-split scores alongside them as the optimistic case. Stating")
say("   both, with the reason for the gap, is stronger than quoting one number.")
say()
say("2. If the bd_gcm3 ablation showed a large drop, say plainly in the report")
say("   that the below-ground R2 is inflated by shared provenance between the")
say("   soil predictors and the SOC target, and that bulk density additionally")
say("   appears in the carbon conversion formula.")
say()
say("3. If any feature came out as COARSE in section 1, it is acting as a")
say("   regional identifier. Either drop it and re-check the score, or state")
say("   that its apparent importance reflects spatial position, not process.")
say()
say("4. The district carbon total is 96% below-ground, so corrections to the")
say("   above-ground model will barely move it. Effort belongs on the SOC side.")

OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
say()
say(f"Report saved to {OUT_FILE}")
