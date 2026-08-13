"""
rebuild_honest_models.py
========================
Builds a second set of models that exclude features acting as coordinate
proxies, and compares them against the originals.

Background: deep_diagnostics.py showed that rainfall and land-surface
temperature are almost perfectly reconstructible from longitude and latitude
(R2 > 0.999). They are smooth interpolated surfaces carrying no information
at 250 m resolution. A model relying on them learns geographic position, not
an ecological process — which is why coordinates alone outscored the full
22-feature model.

This script:
  1. Measures how spatial each feature is, and splits them into two sets.
  2. Trains a "process" model on locally-varying features only.
  3. Evaluates everything under spatial block cross-validation.
  4. Recomputes district carbon under both models.
  5. Writes a comparison table for the report.

The original models and outputs are NOT overwritten. New files carry the
suffix _honest.

Usage (from the project root, with .venv active):
    python rebuild_honest_models.py
"""

import os
import pickle
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, train_test_split

SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

ROOT = Path(os.getenv("PROJECT_ROOT", SCRIPT_DIR))
DATA = ROOT / "IIRS" / "Carbon_Stocks"
OUT_FILE = DATA / "honest_model_report.txt"

RANDOM_STATE = 42
N_BLOCKS = 8
CV_FOLDS = 5

# A feature this predictable from coordinates alone carries no local detail.
SPATIAL_THRESHOLD = 0.95

NPP_COL = "Agricultur"
SOC_COL = "SOC_mean"

NDVI_COLS = ["NDVI_Jun24", "NDVI_Jul24", "NDVI_Aug24", "NDVI_Sep24",
             "NDVI_Oct24", "NDVI_Nov24", "NDVI_Dec24", "NDVI_Jan25",
             "NDVI_Feb25", "NDVI_Mar25", "NDVI_Apr25", "NDVI_May25"]

BG_FEATURES = ["agri_class", "DEM_mean", "Slope_mean",
               "sand_pct", "clay_pct", "bd_gcm3"]

CELL_AREA_HA = 6.25
NPP_TO_AGC = 0.47
SOC_DEPTH_CM = 30

RF = dict(n_estimators=300, min_samples_split=4, min_samples_leaf=2,
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


def spatial_blocks(df, n=N_BLOCKS):
    lon_bin = pd.qcut(df["lon_c"], n, labels=False, duplicates="drop")
    lat_bin = pd.qcut(df["lat_c"], n, labels=False, duplicates="drop")
    return (lon_bin.astype(str) + "_" + lat_bin.astype(str)).values


def random_split_scores(X, y):
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE)
    m = RandomForestRegressor(**RF).fit(Xtr, ytr)
    pred = np.maximum(m.predict(Xte), 0)
    return (r2_score(yte, pred),
            float(np.sqrt(mean_squared_error(yte, pred))),
            float(mean_absolute_error(yte, pred)))


def block_cv_scores(X, y, groups):
    gkf = GroupKFold(n_splits=CV_FOLDS)
    r2s, rmses, maes = [], [], []
    for tr, te in gkf.split(X, y, groups):
        m = RandomForestRegressor(**RF).fit(X.iloc[tr], y.iloc[tr])
        pred = np.maximum(m.predict(X.iloc[te]), 0)
        r2s.append(r2_score(y.iloc[te], pred))
        rmses.append(float(np.sqrt(mean_squared_error(y.iloc[te], pred))))
        maes.append(float(mean_absolute_error(y.iloc[te], pred)))
    return np.mean(r2s), np.std(r2s), np.mean(rmses), np.mean(maes)


# ══════════════════════════════════════════════════════════════
header("LOADING AND PREPARING DATA")

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

ALL_AG_FEATURES = [c for c in ag_m.columns
                   if c not in ("agri_class", NPP_COL, "WKT", "Grid_ID",
                                "lon_c", "lat_c")]

blocks_ag = spatial_blocks(ag_m)
blocks_bg = spatial_blocks(bg)

say(f"Above-ground modelling cells: {len(ag_m):,}")
say(f"Below-ground modelling cells: {len(bg):,}")
say(f"Candidate above-ground features: {len(ALL_AG_FEATURES)}")


# ══════════════════════════════════════════════════════════════
header("1. HOW SPATIAL IS EACH FEATURE?")

say("Each feature is fitted from longitude and latitude alone. A score near")
say("1.00 means the feature is a smooth geographic surface: it tells the model")
say("where a cell is, not what is happening there.")
say()
say(f"Features scoring above {SPATIAL_THRESHOLD} are excluded from the process model.")
say()

coords = ag_m[["lon_c", "lat_c"]]
spatial_score = {}
for col in ALL_AG_FEATURES:
    Xtr, Xte, ytr, yte = train_test_split(
        coords, ag_m[col], test_size=0.2, random_state=RANDOM_STATE)
    m = RandomForestRegressor(n_estimators=100, n_jobs=-1,
                              random_state=RANDOM_STATE).fit(Xtr, ytr)
    spatial_score[col] = r2_score(yte, m.predict(Xte))

say(f"{'feature':<16}{'spatial R2':>14}   decision")
say("-" * 52)
PROCESS_FEATURES, PROXY_FEATURES = [], []
for col in sorted(ALL_AG_FEATURES, key=lambda c: -spatial_score[c]):
    if spatial_score[col] > SPATIAL_THRESHOLD:
        PROXY_FEATURES.append(col)
        decision = "EXCLUDE - position proxy"
    else:
        PROCESS_FEATURES.append(col)
        decision = "keep"
    say(f"{col:<16}{spatial_score[col]:>14.4f}   {decision}")

say()
say(f"Excluded: {len(PROXY_FEATURES)}  ->  {', '.join(PROXY_FEATURES)}")
say(f"Retained: {len(PROCESS_FEATURES)}")


# ══════════════════════════════════════════════════════════════
header("2. ABOVE-GROUND MODEL COMPARISON")

y_ag = ag_m[NPP_COL]

ag_variants = {
    "Original (all features)":   ALL_AG_FEATURES,
    "Process only (no proxies)": PROCESS_FEATURES,
    "Coordinates only":          ["lon_c", "lat_c"],
}

say(f"{'model':<28}{'random R2':>12}{'spatial R2':>12}{'RMSE':>10}{'MAE':>10}")
say("-" * 72)

ag_results = {}
for label, feats in ag_variants.items():
    X = ag_m[feats]
    r2_rand, _, _ = random_split_scores(X, y_ag)
    r2_sp, sd_sp, rmse_sp, mae_sp = block_cv_scores(X, y_ag, blocks_ag)
    ag_results[label] = dict(random=r2_rand, spatial=r2_sp, sd=sd_sp,
                             rmse=rmse_sp, mae=mae_sp, features=feats)
    say(f"{label:<28}{r2_rand:>12.4f}{r2_sp:>12.4f}{rmse_sp:>10.2f}{mae_sp:>10.2f}")

say()
say("The spatial column is the honest score. Compare each model against")
say("'Coordinates only': a model that cannot beat two numbers describing")
say("position has not learned anything about vegetation or climate.")

orig = ag_results["Original (all features)"]["spatial"]
proc = ag_results["Process only (no proxies)"]["spatial"]
crd = ag_results["Coordinates only"]["spatial"]

say()
if orig < crd:
    say(f"FINDING: the original model ({orig:.4f}) scores BELOW coordinates")
    say(f"         alone ({crd:.4f}). Its apparent skill is spatial position.")
if proc > crd:
    say(f"FINDING: the process model ({proc:.4f}) beats coordinates ({crd:.4f}),")
    say("         so the retained features carry real local information.")
else:
    say(f"FINDING: the process model ({proc:.4f}) does not beat coordinates")
    say(f"         ({crd:.4f}). Above-ground NPP is not well predicted by the")
    say("         available 250 m covariates. This is a legitimate result to")
    say("         report, not a failure to hide.")


# ══════════════════════════════════════════════════════════════
header("3. BELOW-GROUND MODEL COMPARISON")

say("The soil predictors correlate 0.84-0.97 with each other and with SOC,")
say("and the signs are physically inverted (sand and clay should oppose each")
say("other; bulk density should fall as organic carbon rises). This points to")
say("all four layers being outputs of one gridded soil product built from a")
say("shared covariate stack, rather than independent measurements.")
say()

y_bg = bg[SOC_COL]
bg_variants = {
    "Original (all features)": BG_FEATURES,
    "Without bulk density":    [c for c in BG_FEATURES if c != "bd_gcm3"],
    "Terrain + class only":    ["agri_class", "DEM_mean", "Slope_mean"],
    "Coordinates only":        ["lon_c", "lat_c"],
}

say(f"{'model':<28}{'random R2':>12}{'spatial R2':>12}{'RMSE':>10}{'MAE':>10}")
say("-" * 72)

bg_results = {}
for label, feats in bg_variants.items():
    X = bg[feats]
    r2_rand, _, _ = random_split_scores(X, y_bg)
    r2_sp, sd_sp, rmse_sp, mae_sp = block_cv_scores(X, y_bg, blocks_bg)
    bg_results[label] = dict(random=r2_rand, spatial=r2_sp,
                             rmse=rmse_sp, mae=mae_sp, features=feats)
    say(f"{label:<28}{r2_rand:>12.4f}{r2_sp:>12.4f}{rmse_sp:>10.3f}{mae_sp:>10.3f}")

say()
say("Below-ground scores hold up under spatial validation, so the model is")
say("not simply memorising neighbours. What the score measures is agreement")
say("with one soil product, not accuracy against field-measured carbon.")


# ══════════════════════════════════════════════════════════════
header("4. DOES ANY OF THIS CHANGE THE CARBON ESTIMATE?")

say("Above-ground carbon is ~4% of the district total, so even a large change")
say("in the NPP model moves the headline figure very little. This section")
say("quantifies that instead of assuming it.")
say()

# Train each AG variant, predict on its own held-out split, get mean AGC
say(f"{'above-ground model':<28}{'mean AGC (tC/ha)':>20}{'implied district AGC':>24}")
say("-" * 74)

GENUINE_CELLS = round(50402 * 12602 / 16252)
agc_by_model = {}
for label, info in ag_results.items():
    X = ag_m[info["features"]]
    Xtr, Xte, ytr, yte = train_test_split(
        X, y_ag, test_size=0.2, random_state=RANDOM_STATE)
    m = RandomForestRegressor(**RF).fit(Xtr, ytr)
    pred = np.maximum(m.predict(Xte), 0)
    mean_agc = float((pred * NPP_TO_AGC / 100).mean())
    district = mean_agc * GENUINE_CELLS * CELL_AREA_HA / 1e6
    agc_by_model[label] = district
    say(f"{label:<28}{mean_agc:>20.4f}{district:>21.4f} MtC")

spread = max(agc_by_model.values()) - min(agc_by_model.values())
say()
say(f"Spread across all three above-ground models: {spread:.4f} MtC")

final = pd.read_csv(DATA / "carbon_all_66790_final.csv")
t_bg = float(final["BGC_tC_ha"].sum()) * CELL_AREA_HA / 1e6
t_ag = float(final["AGC_tC_ha"].sum()) * CELL_AREA_HA / 1e6
say(f"Reported district total: {t_ag + t_bg:.4f} MtC "
    f"(above-ground {t_ag:.4f}, below-ground {t_bg:.4f})")
say(f"Worst-case shift from changing the above-ground model: "
    f"{100 * spread / (t_ag + t_bg):.2f}% of the total")


# ══════════════════════════════════════════════════════════════
header("5. SAVING THE PROCESS MODEL")

X_proc = ag_m[PROCESS_FEATURES]
model_proc = RandomForestRegressor(**RF).fit(X_proc, y_ag)
with open(DATA / "model_ag_rf_honest.pkl", "wb") as f:
    pickle.dump(model_proc, f)

pd.DataFrame({
    "feature": PROCESS_FEATURES,
    "importance": model_proc.feature_importances_,
    "spatial_r2": [spatial_score[c] for c in PROCESS_FEATURES],
}).sort_values("importance", ascending=False).to_csv(
    DATA / "feature_importance_honest.csv", index=False)

say(f"Saved model_ag_rf_honest.pkl        ({len(PROCESS_FEATURES)} features)")
say("Saved feature_importance_honest.csv")
say()
say("The original models are untouched. Report both, with the reason for the")
say("difference — that is a stronger result than either number alone.")


# ══════════════════════════════════════════════════════════════
header("TABLE FOR THE REPORT")

say("Model performance under two validation schemes")
say()
say(f"{'Model':<34}{'Random split':>14}{'Spatial CV':>13}")
say("-" * 61)
say(f"{'Above-ground, all features':<34}"
    f"{ag_results['Original (all features)']['random']:>14.4f}"
    f"{ag_results['Original (all features)']['spatial']:>13.4f}")
say(f"{'Above-ground, process features':<34}"
    f"{ag_results['Process only (no proxies)']['random']:>14.4f}"
    f"{ag_results['Process only (no proxies)']['spatial']:>13.4f}")
say(f"{'Above-ground, coordinates only':<34}"
    f"{ag_results['Coordinates only']['random']:>14.4f}"
    f"{ag_results['Coordinates only']['spatial']:>13.4f}")
say(f"{'Below-ground, all features':<34}"
    f"{bg_results['Original (all features)']['random']:>14.4f}"
    f"{bg_results['Original (all features)']['spatial']:>13.4f}")
say(f"{'Below-ground, terrain only':<34}"
    f"{bg_results['Terrain + class only']['random']:>14.4f}"
    f"{bg_results['Terrain + class only']['spatial']:>13.4f}")

OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
say()
say(f"Report saved to {OUT_FILE}")
