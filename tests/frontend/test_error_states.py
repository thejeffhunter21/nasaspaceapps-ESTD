"""FE-07: useful states and recovery without fabricated data or tracebacks."""

import json
from contextlib import contextmanager
from pathlib import Path

import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.unit
APP = Path(__file__).resolve().parents[2] / "app/streamlit_app.py"
SAMPLE = APP.parent / "fixtures/results.mock.json"


@pytest.fixture
def service(monkeypatch):
    payload = json.loads(SAMPLE.read_text())
    payload.update(region_id="north", region="North")
    state = {"payload": payload, "problem": None, "calls": []}

    def get(session, url, **kwargs):
        endpoint = url.rsplit("/", 1)[-1]
        state["calls"].append(endpoint)
        problem = state["problem"]
        if endpoint == "series" and problem == "timeout":
            raise requests.Timeout()
        if endpoint == "series" and problem == "connection":
            raise requests.ConnectionError()
        result = requests.Response()
        result.status_code = 200
        if endpoint == "health":
            body = {"status": "ok"}
        elif endpoint == "regions":
            body = {"regions": [] if problem == "no_regions" else [state["payload"]]}
        elif endpoint == "series":
            body = {k: state["payload"][k] for k in (
                "region_id", "region", "variable", "units", "period", "series",
            )}
            if problem == "empty":
                body["series"] = []
            elif problem == "all_missing":
                body["series"] = [dict(point, value=None) for point in body["series"]]
            elif isinstance(problem, int):
                result.status_code = problem
                body = {"detail": "private backend details"}
            elif problem == "json":
                result._content = b"not-json"
                return result
        else:
            body = {k: v for k, v in state["payload"].items() if k != "series"}
            if problem == "null_stats":
                body = dict(body, trend=dict(body["trend"], slope=None, p=None))
        result._content = json.dumps(body).encode()
        return result

    monkeypatch.setenv("API_URL", "https://states.example")
    monkeypatch.setattr(requests.Session, "get", get)
    return state


@pytest.mark.parametrize("problem, headline", [
    ("empty", "No observations available"),
    ("all_missing", "No observations available"),
    ("no_regions", "No regions available"),
    (404, "No data for this region"),
    (422, "Region selection needs updating"),
    (500, "The data service is unavailable"),
    (429, "The data service is busy"),
    ("timeout", "The data service is taking too long"),
    ("connection", "Cannot reach the data service"),
    ("json", "The data response could not be read"),
    ("null_stats", "The data response could not be read"),
])
def test_failure_has_specific_headline_actions_and_no_evidence(service, problem, headline):
    service["problem"] = problem
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.error[0].proto.title == headline
    assert "private backend details" not in app.error[0].value
    assert {b.label for b in app.button} >= {"Retry API", "Use sample data"}
    assert not app.metric
    assert not app.get("plotly_chart")

    assert not app.text
    if problem in (404, 422):
        assert "Refresh regions" in [b.label for b in app.button]


def test_retry_restores_valid_data_after_timeout(service):
    service["problem"] = "timeout"
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.error
    service["problem"] = None
    next(b for b in app.button if b.label == "Retry API").click().run()
    assert not app.exception
    assert not app.error
    assert app.subheader[0].value == "North"


def test_network_operations_run_inside_loading_indicators(service, monkeypatch):
    real_spinner = st.spinner
    real_get = requests.Session.get
    active = []

    @contextmanager
    def observe_spinner(*args, **kwargs):
        with real_spinner(*args, **kwargs):
            active.append(args[0])
            try:
                yield
            finally:
                active.pop()

    def get_while_loading(*args, **kwargs):
        assert active, "HTTP requests must not leave the page without a loading indicator"
        return real_get(*args, **kwargs)

    monkeypatch.setattr(st, "spinner", observe_spinner)
    monkeypatch.setattr(requests.Session, "get", get_while_loading)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert not app.error
    assert service["calls"] == ["health", "regions", "series", "trend", "anomaly"]
    assert app.metric


def test_invalid_api_address_has_setup_guidance_without_network(service, monkeypatch):
    monkeypatch.setenv("API_URL", "invalid-address")
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.error[0].proto.title == "The data connection needs setup"
    assert not service["calls"]
    assert not app.metric


def test_refresh_regions_recovers_from_unknown_region(service):
    service["problem"] = 404
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.error
    service["problem"] = None
    service["payload"] = dict(service["payload"], region_id="replacement", region="Replacement")
    next(b for b in app.button if b.label == "Refresh regions").click().run()
    assert not app.exception
    assert not app.error
    assert app.subheader[0].value == "Replacement"
    assert service["calls"].count("regions") == 2


@pytest.mark.parametrize("problem", ["missing", "json", "encoding", "contract"])
def test_broken_sample_has_recovery_without_traceback(monkeypatch, problem):
    original_read = Path.read_text

    def read_sample(path, *args, **kwargs):
        if path == SAMPLE:
            if problem == "missing":
                raise FileNotFoundError("private path details")
            if problem == "encoding":
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")
            return "not-json" if problem == "json" else "{}"
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_sample)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.error[0].proto.title == "The sample preview is unavailable"
    assert "private path details" not in app.error[0].value
    assert "Retry preview" in [b.label for b in app.button]
    assert not app.metric
    assert not app.get("plotly_chart")

    monkeypatch.setattr(Path, "read_text", original_read)
    next(b for b in app.button if b.label == "Retry preview").click().run()
    assert not app.exception
    assert not app.error
    assert app.subheader[0].value == "Example Region"


def test_broken_sample_after_api_failure_still_has_working_recovery(service, monkeypatch):
    service["problem"] = "timeout"
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    original_read = Path.read_text

    def missing_sample(path, *args, **kwargs):
        if path == SAMPLE:
            raise FileNotFoundError("private path details")
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", missing_sample)
    next(b for b in app.button if b.label == "Use sample data").click().run()
    assert not app.exception
    assert app.error[0].proto.title == "The sample preview is unavailable"
    assert [b.label for b in app.button].count("Retry API") == 1
    service["problem"] = None
    next(b for b in app.button if b.label == "Retry API").click().run()
    assert not app.exception
    assert not app.error
    assert app.subheader[0].value == "North"
