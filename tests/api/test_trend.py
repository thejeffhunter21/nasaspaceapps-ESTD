"""J8: /trend gives the numbers and the explanation."""

import pytest

from .conftest import FIXTURES

pytestmark = pytest.mark.unit


def test_trend_and_explanation(client):
    body = client.get("/trend").json()
    assert set(body["trend"]) == {"slope", "slope_unit", "p", "tau", "trend"}
    assert body["explanation"]
    assert body["explanation_source"] in ("ai", "fallback")
    assert body["source"] and body["method"]


def test_broken_file_is_500(client, monkeypatch):
    monkeypatch.setenv("RESULTS_PATH", str(FIXTURES / "api" / "broken.json"))
    assert client.get("/trend").status_code == 500
