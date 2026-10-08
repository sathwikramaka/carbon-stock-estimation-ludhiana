"""Shared fixtures. Tests that need the raw exports or pipeline results skip
cleanly when those files are absent (e.g. a fresh clone before running
notebooks/02_carbon_pipeline.ipynb)."""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config as C  # noqa: E402

BACKEND = C.DASHBOARD / "backend"
FRONTEND = C.DASHBOARD / "frontend"
RAW = ["BGD_for_all_grids(GEOM).csv", "AGD_for_all_grids_geom.csv",
       "Below_Ground_Data_geom.csv", "Above_ground_data_geom.csv"]

needs_raw = pytest.mark.skipif(not all((C.RAW / f).exists() for f in RAW), reason="raw exports not present")
needs_results = pytest.mark.skipif(not (C.RESULTS / "district_summary.json").exists(),
                                   reason="run notebooks/02_carbon_pipeline.ipynb first")
needs_cells = pytest.mark.skipif(not (C.RESULTS / "carbon_cells.csv").exists(),
                                 reason="run notebooks/02_carbon_pipeline.ipynb first")


@pytest.fixture(scope="session")
def grid():
    return C.load_grid()


@pytest.fixture(scope="session")
def summary():
    return json.loads((C.RESULTS / "district_summary.json").read_text())


def load_app(results_dir: Path, mode: str = "files"):
    """Import backend/app.py fresh with a given data mode and results folder."""
    os.environ["DB_MODE"] = mode
    os.environ["RESULTS_DIR"] = str(results_dir)
    spec = importlib.util.spec_from_file_location(f"carbon_app_{mode}_{abs(hash(results_dir))}", BACKEND / "app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.app.config["TESTING"] = True
    return mod
