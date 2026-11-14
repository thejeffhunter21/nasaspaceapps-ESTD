"""FE-02: sample evidence must be visibly identified on the page."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.unit
APP = Path(__file__).resolve().parents[2] / "app/streamlit_app.py"


def test_sample_page_uses_fixture_region_and_period_even_outside_repo(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert any("Sample data" in item.value for item in app.warning)
    assert app.subheader[0].value == "Example Region"
    assert any("2003-01 to 2005-12" in item.value for item in app.caption)
    app.run()
    assert not app.exception
