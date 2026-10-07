"""config.py — single source of truth for constants, keys, quality control and loaders.

Every number that changes a published figure lives here. Notebooks import from
this module and never re-declare a constant. See AUDIT.md for the reasoning
behind each rule and docs/DATA_DICTIONARY.md for column provenance.

    from config import (DATA, RESULTS, cell_key, cell_areas_ha, load_grid,
                        load_samples, soil_qc, NPP_DN_TO_TC_HA_YR, ...)
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "IIRS" / "Carbon_Stocks"
RESULTS = ROOT / "results"

RANDOM_STATE = 42

# ── Grid definition ───────────────────────────────────────────
# The export grid is a regular EPSG:4326 lattice of 0.002245788210302635 deg
# squares (250 m at the equator) whose corners sit on exact integer multiples
# of the step from (0, 0) -- the lattice Earth Engine's coveringGrid produces
# for EPSG:4326 scaled by the step. A cell's lower-left corner therefore gives
# absolute integer indices row = ymin/step, col = xmin/step, and the key
# 'r{row}_c{col}' is unique, deterministic and reproducible inside Earth
# Engine. It replaces Grid_ID, a uniform random integer in [0, 1e6) with 2,155
# birthday collisions that cannot identify a cell (AUDIT.md, finding F2).
GRID_STEP_DEG = 0.002245788210302635
N_GRID_CELLS = 66_700

# Official district area, Census of India 2011. The current grid sums to
# ~356,894 ha, i.e. it does not cover the whole district. Re-extraction must
# clip to an authoritative boundary (AUDIT.md, finding F9).
OFFICIAL_AREA_HA = 376_700

# ── Units: SoilGrids 2.0 (as found in the existing export) ────
# soc arrives in dg/kg (SoilGrids native, conversion factor 10).
# bdod arrives already rescaled to g/cm3, sand/clay already in %.
SOC_DGKG_TO_GKG = 0.1
SOC_DEPTH_CM = 30
# SoilGrids has no 0-30 cm layer. A 0-30 cm value is the thickness-weighted
# mean of the three standard intervals. Used by the re-extraction notebook;
# the existing export does not record which interval it used (finding F7).
SOILGRIDS_DEPTHS = ("0-5cm", "5-15cm", "15-30cm")
SOILGRIDS_DEPTH_WEIGHTS = (5 / 30, 10 / 30, 15 / 30)

# SOC stock (tC/ha) = SOC (g/kg) x BD (g/cm3) x depth (cm) x (1 - coarse frac) / 10
def soc_stock_tc_ha(soc_gkg, bd_gcm3, depth_cm=SOC_DEPTH_CM, coarse_frac=0.0):
    return np.asarray(soc_gkg) * np.asarray(bd_gcm3) * depth_cm * (1 - np.asarray(coarse_frac)) / 10.0

# ── Units: MODIS MOD17A3HGF v6.1 annual NPP ───────────────────
# Stored DN x 0.0001 = kgC/m2/yr  ->  DN x 0.1 = gC/m2/yr  ->  /100 = tC/ha/yr.
# The column `Agricultur` holds raw DN (77% exact integers, range -3687..2846).
# The old pipeline divided DN by 100, treating DN as gC/m2: 10x too high
# (AUDIT.md, finding F3). MOD17 NPP is already carbon: no 0.47 factor.
NPP_DN_SCALE_KGC_M2 = 1e-4
NPP_DN_TO_GC_M2_YR = 0.1
NPP_DN_TO_TC_HA_YR = 1e-3

CO2_PER_C = 44 / 12

AG_FORMULA = "NPP flux (tC/ha/yr) = MOD17 DN x 0.0001 kgC/m2 x 10 = DN / 1000"
BG_FORMULA = "SOC stock (tC/ha) = SOC (g/kg) x BD (g/cm3) x 30 cm / 10"

# ── Soil quality control: unmasked-nodata dilution ────────────
# The export averaged masked SoilGrids pixels as zeros, so a cell that is a
# fraction w valid reports w x (true value) in every soil band (finding F1).
# BD is near-constant where valid (median 1.50, sd 0.024 g/cm3), which makes
# w = BD / BD_REF a precise estimate of the valid fraction.
BD_VALID_MIN = 1.40      # below this a cell is partially diluted
BD_REF = 1.50            # median BD of undiluted cells (checked in 01_data_audit)
W_RELIABLE = 0.50        # repaired per-cell *values* are trusted only above this valid fraction


def soil_qc(bd_gcm3) -> pd.DataFrame:
    """Classify every cell and estimate its valid-soil fraction w.

    soil_status: "full" (BD >= 1.40, w = 1), "partial" (0 < BD < 1.40,
    w = BD / BD_REF) or "nodata" (BD = 0, w = 0).

    Every partial cell counts towards totals: its stock contribution
    (SOC/w)(BD/w) * 3 * w * area = SOC_diluted * BD_REF * 3 * area does not
    depend on w, so a small w adds no instability. `w_reliable` marks cells
    whose *repaired per-cell values* (SOC/w) are precise enough to use as
    interpolation sources or to display (relative error of w ~0.016 / w).
    """
    bd = pd.Series(np.asarray(bd_gcm3, dtype=float))
    status = np.where(bd >= BD_VALID_MIN, "full", np.where(bd > 0, "partial", "nodata"))
    w = np.where(status == "full", 1.0, np.where(status == "partial", (bd / BD_REF).clip(upper=1.0), 0.0))
    return pd.DataFrame({"soil_status": status, "w_soil": w, "w_reliable": w >= W_RELIABLE})


def undilute(values, w):
    """Recover band values in partially diluted cells: value / w, NaN where w == 0."""
    v = np.asarray(values, dtype=float)
    w = np.asarray(w, dtype=float)
    out = np.full_like(v, np.nan)
    ok = w > 0
    out[ok] = v[ok] / w[ok]
    return out


# ── Cell key and area ─────────────────────────────────────────
_RING = re.compile(r"\(\(\((.*?)\)\)\)")


def _ring(wkt: str):
    m = _RING.search(str(wkt))
    if not m:
        raise ValueError(f"cannot parse WKT polygon ring: {str(wkt)[:60]}")
    pts = np.array([p.split() for p in m.group(1).split(",")], dtype=float)
    return pts[:, 0], pts[:, 1]


def grid_rowcol(wkt) -> pd.DataFrame:
    """Integer grid row/col and centroid of each polygon, asserting exact lattice fit."""
    rows, cols, lons, lats = [], [], [], []
    for w in pd.Series(wkt).to_numpy():
        x, y = _ring(w)
        c = x.min() / GRID_STEP_DEG
        r = y.min() / GRID_STEP_DEG
        if abs(c - round(c)) > 1e-6 or abs(r - round(r)) > 1e-6:
            raise ValueError(f"polygon does not sit on the export lattice: {str(w)[:60]}")
        rows.append(int(round(r)))
        cols.append(int(round(c)))
        lons.append(x.min() + GRID_STEP_DEG / 2)
        lats.append(y.min() + GRID_STEP_DEG / 2)
    return pd.DataFrame({"grid_row": rows, "grid_col": cols, "lon": lons, "lat": lats})


def cell_key(row, col) -> pd.Series:
    """Deterministic cell identifier from absolute lattice indices, e.g. 'r13798_c33549'."""
    return ("r" + pd.Series(row).astype(int).astype(str)
            + "_c" + pd.Series(col).astype(int).astype(str))


def cell_areas_ha(wkt) -> np.ndarray:
    """Geodesic area (ha) of each polygon on the WGS84 ellipsoid.

    At ~30.8 N a 0.0022458 deg cell is ~249.7 m N-S by ~214.5 m E-W, mean
    ~5.35 ha, not 6.25 ha.
    """
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    out = np.empty(len(wkt))
    for i, w in enumerate(pd.Series(wkt).to_numpy()):
        x, y = _ring(w)
        a, _ = geod.polygon_area_perimeter(x, y)
        out[i] = abs(a) / 1e4
    return out


def assert_unique(df: pd.DataFrame, key: str = "cell_id") -> pd.DataFrame:
    dup = df[key].duplicated().sum()
    if dup:
        raise AssertionError(f"{dup} duplicate {key} values")
    return df


# ── Loaders ───────────────────────────────────────────────────
def load_grid(data: Path = DATA) -> pd.DataFrame:
    """All 66,700 grid cells with key, centroid, area, soil QC and covariates.

    BGD and AGD exports are row-aligned (identical WKT order, verified in
    01_data_audit). Nothing is dropped. Grid_ID is kept only for joining the
    NDVI export, which carries no geometry; it is never used as an identity.
    """
    bgd = pd.read_csv(data / "BGD_for_all_grids(GEOM).csv").rename(columns={"BD_g_cm3": "bd_gcm3"})
    agd = pd.read_csv(data / "AGD_for_all_grids_geom.csv").rename(columns={
        "Kharif_Pea": "Kharif_pea", "Rabi Peak": "Rabi_Peak_", "NDWI_Khari": "Kharif_Lud"})
    if not (bgd["WKT"].values == agd["WKT"].values).all():
        raise AssertionError("BGD and AGD exports are not row-aligned")
    geo = grid_rowcol(bgd["WKT"])
    g = pd.concat([geo, bgd.reset_index(drop=True)], axis=1)
    for c in ["Kharif_pea", "Kharif_Pre", "LST_Sept20", "Rabi_LST_2", "Rabi_Peak_",
              "Rabi_Preci", "Kharif_Lud", "NDWI_Rabi_"]:
        g[c] = agd[c].to_numpy()
    g.insert(0, "cell_id", cell_key(g["grid_row"], g["grid_col"]).to_numpy())
    g["cell_area_ha"] = cell_areas_ha(g["WKT"])
    g = pd.concat([g, soil_qc(g["bd_gcm3"])], axis=1)
    if len(g) != N_GRID_CELLS:
        raise AssertionError(f"expected {N_GRID_CELLS} cells, found {len(g)}")
    return assert_unique(g)


def load_samples(data: Path = DATA) -> pd.DataFrame:
    """The 20,000-cell random sample with SOC (g/kg) and raw MOD17 NPP DN.

    Below- and above-ground sample files are row-aligned. No row is dropped:
    the old drop_duplicates('Grid_ID') deleted 199 real cells per file.
    """
    bg = pd.read_csv(data / "Below_Ground_Data_geom.csv")
    ag = pd.read_csv(data / "Above_ground_data_geom.csv")
    if not (bg["WKT"].values == ag["WKT"].values).all():
        raise AssertionError("sample files are not row-aligned")
    geo = grid_rowcol(bg["WKT"])
    s = pd.DataFrame({
        "cell_id": cell_key(geo["grid_row"], geo["grid_col"]).to_numpy(),
        "soc_gkg_raw": bg["SOC_mean"].to_numpy() * SOC_DGKG_TO_GKG,
        "npp_dn": ag["Agricultur"].to_numpy(),
    })
    return assert_unique(s)


def load_ndvi(grid: pd.DataFrame, data: Path = DATA) -> pd.DataFrame:
    """Monthly NDVI attached by Grid_ID only where that ID is unique in the grid.

    The NDVI export has no geometry, so cells whose Grid_ID collides with
    another cell's cannot be attributed and are left missing.
    """
    nd = pd.read_csv(data / "ndvi_monthly_ludhiana_all_66790.csv")
    counts = grid["Grid_ID"].value_counts()
    unique_ids = counts[counts == 1].index
    nd = nd[nd["Grid_ID"].isin(unique_ids)]
    out = grid[["cell_id", "Grid_ID"]].merge(nd, on="Grid_ID", how="left")
    return out.drop(columns="Grid_ID")


NDVI_COLS = ["NDVI_Jun24", "NDVI_Jul24", "NDVI_Aug24", "NDVI_Sep24", "NDVI_Oct24",
             "NDVI_Nov24", "NDVI_Dec24", "NDVI_Jan25", "NDVI_Feb25", "NDVI_Mar25",
             "NDVI_Apr25", "NDVI_May25"]

# Interpolated climate layers that are >0.95 reconstructible from lon/lat at
# this scale (finding F6). Excluded from process models.
POSITION_PROXIES = ["Kharif_Pre", "LST_Sept20", "Rabi_Preci", "Rabi_LST_2"]


# ── Validation helpers ────────────────────────────────────────
N_BLOCKS = 8          # 8 x 8 geographic blocks (~12 km E-W x 6 km N-S here) for spatial cross-validation
N_FOLDS = 5


def spatial_blocks(lon, lat, n: int = N_BLOCKS) -> np.ndarray:
    """Block label for GroupKFold: an n x n partition of the lon/lat extent."""
    bx = pd.cut(pd.Series(lon), n, labels=False).to_numpy()
    by = pd.cut(pd.Series(lat), n, labels=False).to_numpy()
    return bx * n + by


def lattice_geometry(row, col) -> pd.DataFrame:
    """Centroid and WKT polygon of lattice cells from their absolute indices (inverse of grid_rowcol)."""
    r = np.asarray(row, dtype=float)
    c = np.asarray(col, dtype=float)
    x0, y0 = c * GRID_STEP_DEG, r * GRID_STEP_DEG
    x1, y1 = x0 + GRID_STEP_DEG, y0 + GRID_STEP_DEG
    wkt = [f"MULTIPOLYGON ((({a!r} {b!r},{a!r} {d!r},{e!r} {d!r},{e!r} {b!r},{a!r} {b!r})))"
           for a, b, e, d in zip(x0.tolist(), y0.tolist(), x1.tolist(), y1.tolist())]
    return pd.DataFrame({"lon": x0 + GRID_STEP_DEG / 2, "lat": y0 + GRID_STEP_DEG / 2, "WKT": wkt})


# ── v2 grid from official boundaries ──────────────────────────
BOUNDARIES = DATA / "boundaries"
BOUNDARY_DEFAULT = "ludhiana_geoboundaries_adm2"      # geoBoundaries gbOpen ADM2, 3,700 km2
BOUNDARY_CHECK = "ludhiana_census2011_datameet"       # Census 2011 polygon, sensitivity only


def load_boundary(name: str = BOUNDARY_DEFAULT):
    """Shapely geometry of a district boundary stored in IIRS/Carbon_Stocks/boundaries/."""
    import json
    from shapely.geometry import shape
    gj = json.loads((BOUNDARIES / f"{name}.geojson").read_text())
    return shape(gj["features"][0]["geometry"]).buffer(0)


def build_grid_v2(boundaries=(BOUNDARY_DEFAULT, BOUNDARY_CHECK)) -> pd.DataFrame:
    """Every lattice cell touching any of the boundaries, with geodesic area and,
    for each boundary, the fraction of the cell inside it (in_<name>)."""
    import shapely
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    geoms = {b: load_boundary(b) for b in boundaries}
    union = shapely.union_all(list(geoms.values()))
    x0, y0, x1, y1 = union.bounds
    s = GRID_STEP_DEG
    cols = np.arange(int(np.floor(x0 / s)), int(np.ceil(x1 / s)))
    rows = np.arange(int(np.floor(y0 / s)), int(np.ceil(y1 / s)))
    cc, rr = np.meshgrid(cols, rows)
    cc, rr = cc.ravel(), rr.ravel()
    boxes = shapely.box(cc * s, rr * s, (cc + 1) * s, (rr + 1) * s)
    shapely.prepare(union)
    keep = shapely.intersects(union, boxes)
    cc, rr, boxes = cc[keep], rr[keep], boxes[keep]

    def geod_area(gs):
        return np.array([abs(geod.geometry_area_perimeter(g)[0]) / 1e4 if not g.is_empty else 0.0 for g in gs])

    out = pd.DataFrame({"cell_id": cell_key(rr, cc).to_numpy(), "grid_row": rr, "grid_col": cc})
    out["cell_area_ha"] = geod_area(boxes)
    for name, g in geoms.items():
        out[f"in_{name}"] = (geod_area(shapely.intersection(boxes, g)) / out["cell_area_ha"]).clip(0, 1)
    out["in_district_frac"] = out[f"in_{boundaries[0]}"]
    return assert_unique(out)
