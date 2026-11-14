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
