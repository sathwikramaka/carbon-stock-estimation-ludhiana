"""Backend API (files mode, validation, database fallback)."""
import json
import shutil

import pytest

import config as C
from conftest import load_app, needs_cells, needs_results


@pytest.fixture(scope="module")
def client():
    if not (C.RESULTS / "carbon_cells.csv").exists():
        pytest.skip("run notebooks/02_carbon_pipeline.ipynb first")
    return load_app(C.RESULTS).app.test_client()


def test_summary_and_metrics(client):
    s = client.get("/api/summary")
    assert s.status_code == 200 and s.get_json()["source"] == "files"
    assert "stock_mtc" in s.get_json()["soil"]
    assert client.get("/api/metrics").status_code == 200
    nd = client.get("/api/ndvi").get_json()
    assert len(nd) == 12 and [d["sort_order"] for d in nd] == list(range(12))


@pytest.mark.parametrize("q", ["abc", "-1", "0", "100000"])
def test_geojson_limit_validation(client, q):
    assert client.get(f"/api/geojson?limit={q}").status_code == 400


def test_geojson_features_carry_cell_id(client):
    gj = client.get("/api/geojson?limit=50").get_json()
    assert len(gj["features"]) == 50
    p = gj["features"][0]["properties"]
    assert p["cell_id"].startswith("r") and {"soc", "npp", "soc_source", "npp_source"} <= set(p)
    assert gj["features"][0]["geometry"]["type"] == "Polygon"


def test_area_is_clamped(client):
    r = client.get("/api/geojson/area?lat=30.82&lng=75.84&size=90").get_json()
    assert (r["bbox"]["max_lat"] - r["bbox"]["min_lat"]) / 2 <= 0.1 + 1e-9
    assert client.get("/api/geojson/area?lat=abc").status_code == 400
    assert client.get("/api/geojson/area?lat=95&lng=75").status_code == 400


@pytest.mark.parametrize("q", ["page=0", "per_page=0", "per_page=501", "page=x"])
def test_carbon_paging_validation(client, q):
    assert client.get(f"/api/carbon?{q}").status_code == 400


def test_carbon_page(client):
    r = client.get("/api/carbon?page=2&per_page=25").get_json()
    assert len(r["records"]) == 25 and len({x["cell_id"] for x in r["records"]}) == 25
    summary = json.loads((C.RESULTS / "district_summary.json").read_text())
    assert r["total"] == summary["grid"]["cells"]          # 66,700 in v1, 71,197 in v2


def test_missing_results_returns_503(tmp_path):
    c = load_app(tmp_path).app.test_client()
    r = c.get("/api/summary")
    assert r.status_code == 503 and "02_carbon_pipeline" in r.get_json()["error"]


def test_database_failure_falls_back_to_files(tmp_path):
    if not (C.RESULTS / "district_summary.json").exists():
        pytest.skip("run notebooks/02_carbon_pipeline.ipynb first")
    for f in ["district_summary.json", "model_metrics.json", "ndvi_monthly.json"]:
        shutil.copy(C.RESULTS / f, tmp_path / f)
    mod = load_app(tmp_path, mode="local")

    def broken():
        raise ConnectionError("no database here")

    mod.pg = mod.mdb = broken
    r = mod.app.test_client().get("/api/summary").get_json()
    assert r["source"] == "files-fallback"


def test_empty_database_collection_is_labelled_fallback(tmp_path):
    if not (C.RESULTS / "district_summary.json").exists():
        pytest.skip("run notebooks/02_carbon_pipeline.ipynb first")
    shutil.copy(C.RESULTS / "district_summary.json", tmp_path / "district_summary.json")
    mod = load_app(tmp_path, mode="local")

    class EmptyCollection:
        def find_one(self, *a, **k):
            return None

    mod.mdb = lambda: {"district_summary": EmptyCollection()}
    assert mod.app.test_client().get("/api/summary").get_json()["source"] == "files-fallback"
