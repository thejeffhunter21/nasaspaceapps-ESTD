"""J5: the server says it is up."""

import pytest

pytestmark = pytest.mark.unit


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_page_points_to_endpoints(client):
    body = client.get("/").json()
    assert body["status"] == "ok"
    assert "/regions" in body["try"] and body["docs"] == "/docs"


def test_version_reports_live_commit(client, monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    assert client.get("/version").json() == {"commit": "abc123"}
    monkeypatch.delenv("RENDER_GIT_COMMIT")
    assert client.get("/version").json() == {"commit": "unknown"}
