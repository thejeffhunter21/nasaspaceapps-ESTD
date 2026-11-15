"""FE-08: exercise Streamlit through the real FastAPI routes, entirely offline."""

import json
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import requests
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app/streamlit_app.py"


@pytest.fixture
def offline_backend(monkeypatch, tmp_path):
    main = json.loads((ROOT / "app/fixtures/results.mock.json").read_text())
    main.update(region_id="phoenix_study_area", region="Phoenix study area",
                explanation="The main-area trend is increasing and statistically significant.")
    main["trend"]["p"] = 3.3e-10
    north = deepcopy(main)
    north.update(region_id="phoenix_northwest", region="Phoenix study area northwest",
                 explanation="Supplied northwest explanation.")
    north["trend"].update(slope=-0.01, p=0.25, trend="no trend")
    north["series"][0]["value"] = 13.5
    main_file = tmp_path / "main.json"
    regions_dir = tmp_path / "regions"
    regions_dir.mkdir()
    north_file = regions_dir / "north.json"
    main_file.write_text(json.dumps(main))
    north_file.write_text(json.dumps(north))
    monkeypatch.setenv("USE_MOCK", "false")
    monkeypatch.setenv("RESULTS_PATH", str(main_file))
    monkeypatch.setenv("REGIONS_DIR", str(regions_dir))
    monkeypatch.setenv("API_URL", "http://testserver")

    from earth_system_trend.api.app import app as api

    with TestClient(api) as client:
        calls = []

        def bridge(session, url, **kwargs):
            parsed = urlsplit(url)
            assert parsed.netloc == "testserver"
            calls.append((parsed.path, kwargs.get("params")))
            return client.get(parsed.path, params=kwargs.get("params"))

        monkeypatch.setattr(requests.Session, "get", bridge)
        yield {"main": main, "north": north, "north_file": north_file,
               "client": client, "calls": calls}


def test_offline_backend_page_matches_json_through_switch_and_cache(offline_backend):
    backend = offline_backend
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert not app.error
    assert app.selectbox[0].options == ["Phoenix study area", "Phoenix study area northwest"]
    assert {m.label: m.value for m in app.metric} == {
        "Slope (°C/month)": "0.021", "p-value": "p < 0.001", "Direction": "increasing",
    }
    assert any("Sample data" in w.value for w in app.warning)
    assert "Automatic summary (AI unavailable)" in [c.value for c in app.caption]

    app.selectbox[0].select("phoenix_northwest").run()
    assert not app.exception
    assert not app.error
    series = backend["client"].get("/series", params={"region": "phoenix_northwest"}).json()
    trend = backend["client"].get("/trend", params={"region": "phoenix_northwest"}).json()
    chart = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert chart["data"][0]["x"] == [p["time"] for p in series["series"]]
    assert chart["data"][0]["y"] == [p["value"] for p in series["series"]]
    assert chart["data"][0]["y"][14] is None
    assert chart["data"][0]["connectgaps"] is False
    assert app.text[0].value == trend["explanation"]
    assert {m.label: m.value for m in app.metric} == {
        "Slope (°C/month)": "-0.01", "p-value": "0.25", "Direction": "no trend",
    }
    assert len(backend["calls"]) == 6
    app.selectbox[0].select("phoenix_study_area").run()
    assert not app.exception
    assert app.subheader[0].value == "Phoenix study area"
    assert len(backend["calls"]) == 6


def test_backend_404_clears_old_evidence_then_refresh_recovers(offline_backend):
    backend = offline_backend
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    backend["north_file"].unlink()  # Simulate a deployment removing a listed region.
    app.selectbox[0].select("phoenix_northwest").run()
    assert not app.exception
    assert app.error[0].proto.title == "No data for this region"
    assert not app.metric
    assert not app.get("plotly_chart")
    assert not app.text
    next(b for b in app.button if b.label == "Refresh regions").click().run()
    assert not app.exception
    assert not app.error
    assert not app.selectbox
    assert app.subheader[0].value == "Phoenix study area"
