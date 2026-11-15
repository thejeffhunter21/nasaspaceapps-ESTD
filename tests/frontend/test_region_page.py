"""FE-05: selection changes one complete evidence block, never a partial result."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.unit
APP = Path(__file__).resolve().parents[2] / "app/streamlit_app.py"


@pytest.fixture
def regional_backend(monkeypatch):
    north = json.loads((APP.parent / "fixtures/results.mock.json").read_text())
    north.update(region_id="north", region="North", source="North source", method="North method",
                 explanation="North explanation")
    south = deepcopy(north)
    south.update(region_id="south", region="South", source="South source", method="South method",
                 explanation="South explanation", units="K")
    south["trend"].update(slope=-0.03, p=0.6, trend="decreasing")
    for point in south["series"]:
        point["time"] = str(int(point["time"][:4]) + 3) + point["time"][4:]
    south["series"][0]["value"] = 260.0
    south["period"] = {"start": "2006-01", "end": "2008-12"}
    state = {"regions": [north, south], "fail_region": None, "calls": []}

    def get(session, url, **kwargs):
        endpoint = url.rsplit("/", 1)[-1]
        region_id = (kwargs.get("params") or {}).get("region")
        state["calls"].append((endpoint, region_id))
        result = requests.Response()
        result.status_code = 200
        if endpoint == "health":
            body = {"status": "ok"}
        elif endpoint == "regions":
            body = {"regions": state["regions"]}
        else:
            selected = next(r for r in state["regions"] if r["region_id"] == region_id)
            if region_id == state["fail_region"]:
                result.status_code = 503
            if endpoint == "series":
                body = {k: selected[k] for k in (
                    "region_id", "region", "variable", "units", "period", "series",
                )}
            else:
                body = {k: v for k, v in selected.items() if k != "series"}
        result._content = json.dumps(body).encode()
        return result

    monkeypatch.setenv("API_URL", "https://regions.example")
    monkeypatch.setattr(requests.Session, "get", get)
    return state


def test_switch_updates_chart_cards_explanation_period_source_and_method(regional_backend):
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.subheader[0].value == "North"
    assert app.selectbox[0].options == ["North", "South"]
    app.selectbox[0].select("south").run()
    assert not app.exception
    assert app.subheader[0].value == "South"
    assert {m.label: m.value for m in app.metric} == {
        "Slope (°C/month)": "-0.03", "p-value": "0.6", "Direction": "decreasing",
    }
    assert app.text[0].value == "South explanation"
    assert any("2006-01 to 2008-12" in c.value and "(K)" in c.value for c in app.caption)
    assert any("South source" in c.value for c in app.caption)
    assert any("South method" in c.value for c in app.caption)
    chart = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert chart["data"][0]["x"][0] == "2006-01"
    assert chart["data"][0]["y"][0] == 260.0
    assert chart["layout"]["yaxis"]["title"]["text"].endswith("(K)")
    assert regional_backend["calls"] == [
        ("health", None), ("regions", None), ("series", "north"), ("trend", "north"),
        ("anomaly", "north"), ("series", "south"), ("trend", "south"), ("anomaly", "south"),
    ]
    app.selectbox[0].select("north").run()
    assert not app.exception
    assert app.subheader[0].value == "North"
    assert app.text[0].value == "North explanation"
    assert len(regional_backend["calls"]) == 8


def test_failed_switch_removes_previous_evidence(regional_backend):
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.metric
    regional_backend["fail_region"] = "south"
    app.selectbox[0].select("south").run()
    assert not app.exception
    assert app.error
    assert not app.metric
    assert not app.get("plotly_chart")
    assert not app.text
    assert not any("North source" in c.value for c in app.caption)


def test_single_region_has_fixed_label_and_no_selector(regional_backend):
    regional_backend["regions"] = regional_backend["regions"][:1]
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.subheader[0].value == "North"
    assert not app.selectbox


def test_host_change_resets_previous_region_selection(regional_backend, monkeypatch):
    app = AppTest.from_file(str(APP)).run()
    app.selectbox[0].select("south").run()
    assert not app.exception
    assert app.subheader[0].value == "South"
    monkeypatch.setenv("API_URL", "https://other-regions.example")
    app.run()
    assert not app.exception
    assert app.selectbox[0].value == "north"
    assert app.subheader[0].value == "North"
    assert app.text[0].value == "North explanation"
