"""FE-04: connection modes and explicit recovery, with HTTP mocked offline."""

import json
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.unit
APP = Path(__file__).resolve().parents[2] / "app/streamlit_app.py"


@pytest.fixture
def backend(monkeypatch):
    payload = json.loads((APP.parent / "fixtures/results.mock.json").read_text())
    payload.update(region="Phoenix study area", source="NASA MODIS test fixture")
    state = {"payload": payload, "fail": False, "calls": []}

    def get(session, url, **kwargs):
        state["calls"].append(url)
        if state["fail"]:
            raise requests.Timeout()
        result = requests.Response()
        result.status_code = 200
        body = {"status": "ok"} if url.endswith("/health") else state["payload"]
        result._content = json.dumps(body).encode()
        return result

    monkeypatch.setenv("API_URL", "https://backend.example")
    monkeypatch.setattr(requests.Session, "get", get)
    return state


def test_connected_results_render_and_rerun_uses_cache(backend):
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.subheader[0].value == "Phoenix study area"
    assert any("Connected to API" in item.value for item in app.caption)
    assert not app.warning
    assert app.text[0].value == backend["payload"]["explanation"]
    app.run()
    assert not app.exception
    assert backend["calls"] == ["https://backend.example/health", "https://backend.example/results"]


def test_connected_mock_results_keep_sample_label(backend):
    backend["payload"].update(region="Example Region", source="Mock data")
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert any("Sample data" in item.value for item in app.warning)
    assert any("Connected to API" in item.value for item in app.caption)


def test_failure_offers_sample_without_automatically_substituting(backend):
    backend["fail"] = True
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.error
    assert not app.metric
    assert not app.get("plotly_chart")
    assert len(backend["calls"]) == 2
    sample_button = next(button for button in app.button if button.label == "Use sample data")
    sample_button.click().run()
    assert not app.exception
    assert app.subheader[0].value == "Example Region"
    assert any("Sample data" in item.value for item in app.warning)
    assert len(backend["calls"]) == 2  # Choice must not wait through another failed connection.

    backend["fail"] = False
    next(button for button in app.button if button.label == "Retry API").click().run()
    assert not app.exception
    assert app.subheader[0].value == "Phoenix study area"
    assert not app.warning
    assert len(backend["calls"]) == 4


def test_default_url_is_the_supplied_live_service(backend, monkeypatch):
    monkeypatch.delenv("API_URL")
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert backend["calls"] == [
        "https://estd-api.onrender.com/health", "https://estd-api.onrender.com/results",
    ]


def test_refresh_loads_changed_results_from_the_same_host(backend):
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    backend["payload"] = dict(backend["payload"], region="Updated study area")
    next(button for button in app.button if button.label == "Refresh data").click().run()
    assert not app.exception
    assert app.subheader[0].value == "Updated study area"
    assert len(backend["calls"]) == 4
