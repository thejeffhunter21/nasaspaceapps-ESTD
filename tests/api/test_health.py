"""J5: the server says it is up."""

import pytest

pytestmark = pytest.mark.unit


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
