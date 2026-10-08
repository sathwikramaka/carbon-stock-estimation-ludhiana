"""estimators.py — statistical estimators shared by the pipeline notebook and the tests.

Kept separate from config.py (constants, keys, QC, loaders) so each function
can be unit-tested in isolation. Every function is pure: arrays in, numbers out.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

Z95 = 1.959964


# ── Design-based estimation from a simple random sample ───────
def srs_total(y, N: int) -> dict:
    """Expansion estimator of a population total from an SRS without replacement.

    T = N * mean(y),  SE = N * sqrt((1 - n/N) * s^2 / n)
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    if n < 2 or n > N:
        raise ValueError("need 2 <= n <= N")
    T = N * y.mean()
    se = N * np.sqrt((1 - n / N) * y.var(ddof=1) / n)
    return {"estimate": float(T), "se": float(se), "ci95": [float(T - Z95 * se), float(T + Z95 * se)], "n": int(n)}


def srs_ratio(y, x, N: int) -> dict:
    """Ratio estimator R = sum(y) / sum(x) with its linearised SRS standard error."""
    y, x = np.asarray(y, dtype=float), np.asarray(x, dtype=float)
    n = y.size
    R = y.sum() / x.sum()
    e = y - R * x
    se = np.sqrt((1 - n / N) * e.var(ddof=1) / n) / x.mean()
    return {"estimate": float(R), "se": float(se), "ci95": [float(R - Z95 * se), float(R + Z95 * se)], "n": int(n)}


def ratio_total(y, x, N: int, X_total: float) -> dict:
    """Ratio estimator of a total when the auxiliary total X is known exactly.

    T = R * X with R = sum(y) / sum(x) from the sample; SE = X * SE(R).
    More precise than the expansion estimator when y is roughly proportional to x.
    """
    r = srs_ratio(y, x, N)
    T, se = r["estimate"] * X_total, r["se"] * X_total
    return {"estimate": float(T), "se": float(se), "ci95": [float(T - Z95 * se), float(T + Z95 * se)], "n": r["n"]}


def scale(est: dict, k: float, ndigits: int = 4) -> dict:
    """Rescale an estimate dict (e.g. tC -> MtC) and round it."""
    out = dict(est)
    out["estimate"] = round(est["estimate"] * k, ndigits)
    out["se"] = round(est["se"] * k, ndigits)
    out["ci95"] = [round(v * k, ndigits) for v in est["ci95"]]
    return out


# ── Spatial interpolation for unsampled cells ─────────────────
def to_metres(lon, lat, lat0: float = 30.8):
    """Local equirectangular projection; adequate over a 1-degree district."""
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    return np.c_[lon * 111_320.0 * np.cos(np.radians(lat0)), lat * 110_574.0]


def idw(src_xy, src_v, dst_xy, k: int = 8, power: float = 2.0) -> np.ndarray:
    """Inverse-distance-weighted mean of the k nearest source values.

    A destination that coincides with a source returns that source's value.
    """
    src_v = np.asarray(src_v, float)
    k = min(k, src_v.size)
    d, i = cKDTree(src_xy).query(dst_xy, k=k)
    d = np.atleast_2d(d)
    i = np.atleast_2d(i)
    exact = d[:, 0] == 0
    w = 1.0 / np.maximum(d, 1e-9) ** power
    out = (w * src_v[i]).sum(axis=1) / w.sum(axis=1)
    out[exact] = src_v[i[exact, 0]]
    return out


def idw_cv(xy, v, k: int = 8, power: float = 2.0, folds: int = 5, seed: int = 42) -> dict:
    """Random k-fold validation of IDW.

    Random folds suit this use because the cells being filled are interleaved
    with the sample (a random 30% of the grid), so held-out points sit among
    training points much as the real targets do. Training on 80% of the sample
    makes the check slightly pessimistic (24% vs 30% source density).
    """
    v = np.asarray(v, float)
    rng = np.random.default_rng(seed)
    fold = rng.integers(0, folds, v.size)
    pred = np.empty_like(v)
    for f in range(folds):
        te = fold == f
        pred[te] = idw(xy[~te], v[~te], xy[te], k=k, power=power)
    resid = v - pred
    return {"r2": float(1 - (resid ** 2).sum() / ((v - v.mean()) ** 2).sum()),
            "rmse": float(np.sqrt((resid ** 2).mean())), "mae": float(np.abs(resid).mean()),
            "bias": float(resid.mean()), "n": int(v.size), "k": k, "power": power, "folds": folds}


# ── Crop-yield cross-check on NPP ─────────────────────────────
def crop_npp_tc_ha(yield_t_ha, dry_frac, residue_ratio, root_shoot, carbon_frac):
    """Annual crop NPP (tC/ha) from harvested yield.

    harvested dry matter x (1 + above-ground residue ratio) x (1 + root:shoot) x carbon fraction.
    Factors follow IPCC (2019) Vol. 4 Table 11.1a. This counts carbon that ends
    up in harvest, residue and roots, so it is a lower bound on true NPP
    (exudates, turnover and losses before harvest are excluded).
    """
    return yield_t_ha * dry_frac * (1 + residue_ratio) * (1 + root_shoot) * carbon_frac


def crop_npp_monte_carlo(crops: dict, n: int = 20_000, seed: int = 42) -> dict:
    """Propagate parameter uncertainty through crop_npp_tc_ha for several crops.

    crops = {name: {"area_ha", "yield_t_ha", "yield_rel_sd", "dry_frac",
                    "residue_ratio", "residue_rel_sd", "root_shoot", "root_shoot_rel_sd"}}
    Carbon fraction ~ Uniform(0.42, 0.47) shared across crops.
    """
    rng = np.random.default_rng(seed)
    cf = rng.uniform(0.42, 0.47, n)
    total = np.zeros(n)
    per_crop = {}
    for name, p in crops.items():
        y = rng.normal(p["yield_t_ha"], p["yield_t_ha"] * p["yield_rel_sd"], n).clip(min=0)
        r = rng.normal(p["residue_ratio"], p["residue_ratio"] * p["residue_rel_sd"], n).clip(min=0)
        rs = rng.normal(p["root_shoot"], p["root_shoot"] * p["root_shoot_rel_sd"], n).clip(min=0)
        c_ha = crop_npp_tc_ha(y, p["dry_frac"], r, rs, cf)
        total += c_ha * p["area_ha"]
        per_crop[name] = {"tc_ha_median": float(np.median(c_ha)),
                          "tc_ha_p05_p95": [float(np.percentile(c_ha, 5)), float(np.percentile(c_ha, 95))]}
    return {"total_mtc_median": float(np.median(total) / 1e6),
            "total_mtc_p05_p95": [float(np.percentile(total, 5) / 1e6), float(np.percentile(total, 95) / 1e6)],
            "per_crop": per_crop, "draws": n}


# ── v2 census totals ──────────────────────────────────────────
def census_totals(cells: pd.DataFrame) -> dict:
    """District totals from clean v2 inputs, where every cell is observed.

    Expects columns: cell_area_ha, in_district_frac, soil_valid_frac,
    ocs_030_t_ha (SoilGrids ocs 0-30 cm, t/ha over valid soil), soc_030 (g/kg),
    bdod_030 (g/cm3), cfvo_030 (vol %), npp_gc_m2_yr, npp_valid_frac.
    Masked cells carry NaN and contribute nothing; partially valid cells
    contribute their valid area only. The headline stock uses ocs, the
    product's own stock prediction; soil_stock_computed_tc rebuilds it from
    SOC x BD x 30 x (1 - coarse) as a sensitivity.
    """
    area_in = cells["cell_area_ha"] * cells["in_district_frac"]
    soil_area = area_in * cells["soil_valid_frac"]
    dens = cells["ocs_030_t_ha"]
    stock = (dens * soil_area).fillna(0)
    dens_c = cells["soc_030"] * cells["bdod_030"] * 30 * (1 - cells["cfvo_030"] / 100) / 10
    npp_area = area_in * cells["npp_valid_frac"]
    flux = (cells["npp_gc_m2_yr"] / 100 * npp_area).fillna(0)
    return {
        "area_in_district_ha": float(area_in.sum()),
        "soil_area_ha": float(soil_area.where(dens.notna(), 0).sum()),
        "soil_stock_tc": float(stock.sum()),
        "soil_stock_computed_tc": float((dens_c * soil_area).fillna(0).sum()),
        "npp_area_ha": float(npp_area.where(cells["npp_gc_m2_yr"].notna(), 0).sum()),
        "npp_flux_tc_yr": float(flux.sum()),
    }
