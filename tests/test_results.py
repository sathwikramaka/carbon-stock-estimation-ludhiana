"""Published results (results/) — the single source the dashboard reads."""
import json
import re

import pandas as pd
import pytest

import config as C
from conftest import FRONTEND, ROOT, needs_cells, needs_results


@needs_results
def test_summary_schema_and_intervals(summary):
    for path in [("soil", "stock_mtc"), ("npp", "flux_mtc_per_year")]:
        est = summary[path[0]][path[1]]
        assert est["estimate"] > 0
        if summary["mode"] == "v1-interim":
            lo, hi = est["ci95"]
            assert lo < est["estimate"] < hi
    assert summary["caveats"] and summary["previous_published"]


@needs_results
def test_flux_and_stock_never_combined(summary):
    text = json.dumps(summary).lower()
    assert not re.search(r"total_c\b|total_million_tc|stock_plus_flux", text)


@needs_results
def test_mod17_cross_check_present(summary):
    crop = summary["crop_yield_crosscheck"]
    assert crop["total_mtc_p05_p95"][0] < crop["total_mtc_median"] < crop["total_mtc_p05_p95"][1]
    assert 0 < crop["mod17_over_crop_ratio"] < 1


@needs_results
def test_npp_scale_applied(summary):
    # MOD17 DN/1000 gives ~1 tC/ha/yr; the old DN/100 gave ~10
    if summary["mode"] == "v1-interim":
        assert summary["npp"]["mean_rate_tc_ha_yr"]["estimate"] < 3


@needs_cells
@needs_results
def test_cells_table(summary):
    cells = pd.read_csv(C.RESULTS / "carbon_cells.csv")
    assert cells.cell_id.is_unique
    assert len(cells) == summary["grid"]["cells"]
    assert set(cells.soc_source.unique()) <= {"observed", "interpolated", "no soil data"}
    if summary["mode"] == "v1-interim":
        lo, hi = summary["soil"]["stock_mtc"]["ci95"]
        assert lo <= cells.soc_stock_tc.sum() / 1e6 <= hi


OLD_FIGURES = ["4.3554", "3.7085", "0.9492", "0.4226", "64,545", "64545", "52,809", "52809", "19,801", "19801", "12,474"]


def test_no_hardcoded_figures_in_dashboard():
    hits = []
    for p in [FRONTEND / "static" / "main.js", FRONTEND / "templates" / "index.html",
              ROOT / "dashboard" / "backend" / "app.py"]:
        text = p.read_text(encoding="utf-8")
        hits += [f"{p.name}: {f}" for f in OLD_FIGURES if f in text]
    assert not hits, hits


def test_dashboard_never_keys_on_grid_id():
    for p in [FRONTEND / "static" / "main.js", ROOT / "dashboard" / "backend" / "app.py"]:
        text = p.read_text(encoding="utf-8")
        assert "grid_id" not in text and "Grid_ID" not in text, p.name


def test_no_keyless_google_tiles():
    js = (FRONTEND / "static" / "main.js").read_text(encoding="utf-8")
    assert "google.com/vt" not in js


@needs_results
def test_soil_area_is_a_census(summary):
    if summary["mode"] == "v1-interim":
        assert summary["soil"]["soil_area_ha"]["se"] == 0.0


@needs_results
def test_soil_density_is_a_stock_in_t_per_ha(summary):
    """F14: SoilGrids ocs 0-30 cm is ~31 t/ha in Ludhiana. ~13 t/ha means SOC_mean was misread as SOC content."""
    assert 20 < summary["soil"]["mean_density_tc_ha"]["estimate"] < 45
