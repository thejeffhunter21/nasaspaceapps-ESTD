"""J9: only our dashboard may call the API from a browser, and only GET."""

import pytest

pytestmark = pytest.mark.unit
ALLOWED = "http://localhost:8501"  # default CORS_ORIGINS


def test_allowed_origin(client):
    response = client.get("/health", headers={"Origin": ALLOWED})
    assert response.headers["access-control-allow-origin"] == ALLOWED


def test_other_origin_gets_nothing(client):
    response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_only_get(client):
    response = client.options("/results", headers={
        "Origin": ALLOWED, "Access-Control-Request-Method": "POST"})
    assert response.status_code == 400
    assert client.post("/results").status_code == 405
