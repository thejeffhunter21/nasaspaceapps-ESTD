"""J6: /results serves the file, or a clear 404 / 500."""

import json

import pytest

from .conftest import FIXTURES

pytestmark = pytest.mark.unit


def test_serves_the_file(client):
    response = client.get("/results")
    assert response.status_code == 200
    assert response.json() == json.loads((FIXTURES / "api" / "results.json").read_text())


def test_missing_file_is_404(client, monkeypatch):
    monkeypatch.setenv("RESULTS_PATH", str(FIXTURES / "api" / "missing.json"))
    assert client.get("/results").status_code == 404


def test_broken_file_is_500(client, monkeypatch):
    monkeypatch.setenv("RESULTS_PATH", str(FIXTURES / "api" / "broken.json"))
    response = client.get("/results")
    assert response.status_code == 500
    assert "trend.p" in response.json()["detail"]
