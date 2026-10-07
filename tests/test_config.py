"""Keys, units and soil quality control (config.py)."""
import numpy as np
import pandas as pd
import pytest

import config as C
from conftest import needs_raw


def test_unit_chain_mod17():
    # DN x 0.0001 kgC/m2 -> x1000 gC/m2 -> /100 tC/ha
    assert C.NPP_DN_TO_GC_M2_YR == pytest.approx(C.NPP_DN_SCALE_KGC_M2 * 1000)
    assert C.NPP_DN_TO_TC_HA_YR == pytest.approx(C.NPP_DN_TO_GC_M2_YR / 100)
    assert "0.47" not in C.AG_FORMULA


def test_soc_stock_formula():
    assert C.soc_stock_tc_ha(3.0, 1.5) == pytest.approx(13.5)        # 3 g/kg x 1.5 g/cm3 x 30 cm / 10
    assert C.soc_stock_tc_ha(3.0, 1.5, coarse_frac=0.1) == pytest.approx(12.15)
    assert sum(C.SOILGRIDS_DEPTH_WEIGHTS) == pytest.approx(1.0)


def test_soil_qc_classes_and_recovery():
    qc = C.soil_qc([1.50, 1.45, 1.20, 0.30, 0.0])
    assert qc.soil_status.tolist() == ["full", "full", "partial", "partial", "nodata"]
    w = qc.w_soil.to_numpy()
    assert w[0] == 1.0 and w[2] == pytest.approx(1.20 / C.BD_REF) and w[4] == 0.0
    assert qc.w_reliable.tolist() == [True, True, True, False, False]
    true_sand = 37.0
    rec = C.undilute([true_sand * w[2]], [w[2]])
    assert rec[0] == pytest.approx(true_sand)
    assert np.isnan(C.undilute([0.0], [0.0])[0])


def test_partial_cell_stock_does_not_depend_on_w():
    """(ocs/w) * w * A = ocs_diluted * A, so tiny w adds no instability to totals."""
    ocs_true, area = 30.8, 5.35
    for w in [0.9, 0.3, 0.02]:
        ocs_dil, bd_dil = ocs_true * w, C.BD_REF * w
        ww = C.soil_qc([bd_dil]).w_soil.iloc[0]
        stock = C.undilute([ocs_dil], [ww])[0] * ww * area
        assert stock == pytest.approx(ocs_dil * area)


def test_lattice_round_trip():
    rows, cols = [13609, 13798, 13700], [33549, 33549, 33900]
    geo = C.lattice_geometry(rows, cols)
    assert "np.float" not in geo.WKT[0]
    back = C.grid_rowcol(geo.WKT)
    assert back.grid_row.tolist() == rows and back.grid_col.tolist() == cols
    assert C.cell_key(rows, cols).tolist() == ["r13609_c33549", "r13798_c33549", "r13700_c33900"]


def test_off_lattice_polygon_rejected():
    wkt = "MULTIPOLYGON (((75.0001 30.0,75.0001 30.0022,75.0023 30.0022,75.0023 30.0,75.0001 30.0)))"
    with pytest.raises(ValueError):
        C.grid_rowcol([wkt])


def test_spatial_blocks():
    lon, lat = np.linspace(75, 76, 100), np.linspace(30, 31, 100)
    b = C.spatial_blocks(lon, lat, n=4)
    assert set(np.unique(b)) <= set(range(16)) and len(np.unique(b)) == 4


@needs_raw
def test_grid_loads_every_cell_with_unique_keys(grid):
    assert len(grid) == C.N_GRID_CELLS
    assert grid.cell_id.is_unique
    # Grid_ID is kept for the NDVI join only and is NOT unique: proof it was never a key
    assert grid.Grid_ID.nunique() < len(grid)


@needs_raw
def test_geodesic_area(grid):
    assert grid.cell_area_ha.mean() == pytest.approx(5.35, abs=0.01)
    assert grid.cell_area_ha.sum() < C.OFFICIAL_AREA_HA


@needs_raw
def test_samples_are_all_kept_and_inside_grid(grid):
    s = C.load_samples()
    assert len(s) == 20_000                     # the old loader dropped 199 real cells
    assert s.cell_id.isin(grid.cell_id).all()
    assert s.ocs_raw_t_ha.median() == pytest.approx(30.8, abs=1.0)   # SoilGrids ocs t/ha (F14), not g/kg or dg/kg


@needs_raw
def test_qc_restores_physical_correlations(grid):
    ok = grid[grid.soil_status != "nodata"]
    sand = C.undilute(ok.sand_pct, ok.w_soil)
    clay = C.undilute(ok.clay_pct, ok.w_soil)
    assert np.corrcoef(grid.sand_pct, grid.clay_pct)[0, 1] > 0.5     # the artefact
    assert np.corrcoef(sand, clay)[0, 1] < -0.3                      # after repair


@needs_raw
def test_ndvi_attached_only_where_attributable(grid):
    nd = C.load_ndvi(grid)
    assert len(nd) == len(grid) and nd.cell_id.is_unique
    ambiguous = grid.Grid_ID.map(grid.Grid_ID.value_counts()) > 1
    assert nd.loc[ambiguous.to_numpy(), C.NDVI_COLS].isna().all().all()


def test_v2_grid_matches_boundary_areas():
    g = C.build_grid_v2()
    assert g.cell_id.is_unique and set(g.cell_id.str[:1]) == {"r"}
    for b, area in [(C.BOUNDARY_DEFAULT, 369_961), (C.BOUNDARY_CHECK, 358_482)]:
        assert (g.cell_area_ha * g[f"in_{b}"]).sum() == pytest.approx(area, rel=1e-3)
    assert g.in_district_frac.between(0, 1).all()
