"""Public Streamlit app: it must embed the dashboard frontend with the current results."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "IIRS" / "Carbon_Stocks" / "results"
pytest.importorskip("streamlit")
needs_results = pytest.mark.skipif(not (RESULTS / "carbon_cells.parquet").exists(), reason="run 02_carbon_pipeline first")


@needs_results
def test_page_embeds_frontend_and_results():
    sys.path.insert(0, str(ROOT / "app"))
    from streamlit_app import build_page

    html = build_page()
    assert "Carbon Stock" in html and "Intelligence System" in html
    assert '<script src="/static/main.js' not in html          # scripts are inlined
    start = html.index("window.__CARBON_DATA__=") + len("window.__CARBON_DATA__=")
    data = json.loads(html[start:html.index(";</script>", start)].replace("<\\/", "</"))
    summary = json.loads((RESULTS / "district_summary.json").read_text())
    assert data["summary"]["soil"]["stock_mtc"]["estimate"] == summary["soil"]["stock_mtc"]["estimate"]
    assert len(data["cells"]["r"]) == summary["grid"]["cells"]
    assert len({len(v) for v in data["cells"].values()}) == 1   # every column has one value per cell


@needs_results
def test_streamlit_app_runs():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error
