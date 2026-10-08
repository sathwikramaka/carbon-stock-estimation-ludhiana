"""Smoke test for the public Streamlit app: it must render every tab from results/ without errors."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytest.importorskip("streamlit")
pytest.importorskip("pydeck")


@pytest.mark.skipif(not (ROOT / "results" / "carbon_cells.parquet").exists(), reason="run 02_carbon_pipeline first")
def test_streamlit_app_runs():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    assert "How much carbon" in at.title[0].value
    assert len(at.tabs) == 5
