"""API test helpers: a client, and settings pointed at committed fixtures."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from earth_system_trend.api.app import app

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")
    monkeypatch.setenv("RESULTS_PATH", str(FIXTURES / "api" / "results.json"))
    return TestClient(app)


@pytest.fixture
def regions_client(monkeypatch, client):
    monkeypatch.setenv("USE_MOCK", "false")
    monkeypatch.setenv("REGIONS_DIR", str(FIXTURES / "regions"))
    return client
