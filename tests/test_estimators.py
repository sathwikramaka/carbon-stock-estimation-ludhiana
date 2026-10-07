"""Statistical estimators (estimators.py)."""
import numpy as np
import pandas as pd
import pytest

import estimators as E


def test_srs_total_coverage():
    rng = np.random.default_rng(0)
    pop = rng.gamma(2.0, 3.0, 5_000)
    hits = 0
    for _ in range(400):
        est = E.srs_total(rng.choice(pop, 500, replace=False), pop.size)
        hits += est["ci95"][0] <= pop.sum() <= est["ci95"][1]
    assert 0.92 <= hits / 400 <= 0.98


def test_srs_total_census_has_zero_se():
    y = np.arange(10.0)
    est = E.srs_total(y, 10)
    assert est["estimate"] == pytest.approx(45.0) and est["se"] == pytest.approx(0.0)


def test_srs_ratio():
    rng = np.random.default_rng(1)
    x = rng.uniform(1, 2, 3000)
    y = 4.0 * x + rng.normal(0, 0.1, 3000)
    est = E.srs_ratio(y[:600], x[:600], 3000)
    assert est["ci95"][0] < 4.0 < est["ci95"][1] + 0.01


def test_idw_exact_and_bounded():
    xy = np.array([[0, 0], [10, 0], [0, 10], [10, 10.0]])
    v = np.array([1.0, 2.0, 3.0, 4.0])
    assert E.idw(xy, v, xy[:1], k=4)[0] == 1.0
    mid = E.idw(xy, v, np.array([[5, 5.0]]), k=4)[0]
    assert mid == pytest.approx(2.5) and v.min() <= mid <= v.max()


def test_crop_npp_matches_ipcc_arithmetic():
    # 5 t/ha wheat, 0.89 dry, residue ratio 1.3, root:shoot 0.23, 0.45 C
    assert E.crop_npp_tc_ha(5.0, 0.89, 1.3, 0.23, 0.45) == pytest.approx(5.0 * 0.89 * 2.3 * 1.23 * 0.45)


def test_census_totals_area_weighting():
    cells = pd.DataFrame({
        "cell_area_ha": [10.0, 10.0, 10.0], "in_district_frac": [1.0, 0.5, 1.0],
        "soil_valid_frac": [1.0, 1.0, 0.0], "soc_030": [3.0, 3.0, np.nan], "bdod_030": [1.5, 1.5, np.nan],
        "cfvo_030": [0.0, 0.0, np.nan], "npp_gc_m2_yr": [100.0, -50.0, np.nan], "npp_valid_frac": [1.0, 1.0, 0.0]})
    t = E.census_totals(cells)
    assert t["soil_stock_tc"] == pytest.approx(13.5 * 10 + 13.5 * 5)
    assert t["soil_area_ha"] == pytest.approx(15.0)
    assert t["npp_flux_tc_yr"] == pytest.approx(1.0 * 10 - 0.5 * 5)      # negatives kept


def test_idw_more_neighbours_than_sources():
    xy = np.array([[0, 0], [10, 0.0]])
    assert E.idw(xy, np.array([1.0, 3.0]), np.array([[5, 0.0]]), k=8)[0] == pytest.approx(2.0)


def test_ratio_total_with_known_auxiliary_total():
    rng = np.random.default_rng(2)
    x = rng.uniform(1, 2, 4000)
    y = 3.0 * x * rng.normal(1, 0.05, 4000)
    idx = rng.choice(4000, 800, replace=False)
    est = E.ratio_total(y[idx], x[idx], 4000, x.sum())
    assert est["ci95"][0] <= y.sum() <= est["ci95"][1]
    assert est["se"] < E.srs_total(y[idx], 4000)["se"]
