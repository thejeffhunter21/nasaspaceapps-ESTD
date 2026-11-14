"""FE-02/03: identify sample data and display the supplied evidence."""

import json
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


def test_evidence_cards_chart_and_plain_text_match_sample():
    payload = json.loads((APP.parent / "fixtures/results.mock.json").read_text())
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    cards = {metric.label: metric.value for metric in app.metric}
    assert cards == {
        "Slope (°C/month)": "0.021",
        "p-value": "0.012",
        "Direction": "increasing",
    }
    assert any(item.value == "Statistically significant (p < 0.05)." for item in app.caption)
    assert app.text[0].value == payload["explanation"]
    chart = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert chart["data"][0]["y"][14] is None
    assert chart["data"][0]["connectgaps"] is False


def test_zero_slope_and_boundary_p_are_displayed_without_significance(monkeypatch):
    fixture = APP.parent / "fixtures/results.mock.json"
    payload = json.loads(fixture.read_text())
    payload["trend"].update(slope=0.0, p=0.05, trend="no trend")
    payload["explanation"] = "**Supplied text** <b>must stay literal</b>."
    original_read = Path.read_text

    def read_sample(path, *args, **kwargs):
        if path == fixture:
            return json.dumps(payload)
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_sample)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert {metric.label: metric.value for metric in app.metric} == {
        "Slope (°C/month)": "0.0", "p-value": "0.05", "Direction": "no trend",
    }
    assert any(item.value == "Not statistically significant (p >= 0.05)." for item in app.caption)
    assert app.text[0].value == "**Supplied text** <b>must stay literal</b>."
