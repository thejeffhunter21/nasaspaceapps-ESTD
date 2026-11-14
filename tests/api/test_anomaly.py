"""/anomaly: the Data layer's anomalies per region, same months as /series, nulls kept."""

import json

import pytest

from .conftest import FIXTURES

pytestmark = pytest.mark.unit


@pytest.fixture
def anomaly_client(client, monkeypatch, tmp_path):
    data = json.loads((FIXTURES / "api" / "results.json").read_text())
    data["anomaly"] = [{"time": p["time"], "value": None if p["value"] is None else 0.5}
                       for p in data["series"]]
    data["baseline"] = [{"month": m, "mean": 10.0 + m, "count": 22} for m in range(1, 13)]
    path = tmp_path / "results.json"
    path.write_text(json.dumps(data))
    monkeypatch.setenv("RESULTS_PATH", str(path))
    return client, data


def test_returns_anomaly_and_baseline(anomaly_client):
    client, data = anomaly_client
    body = client.get("/anomaly").json()
    assert body["series"] == data["anomaly"]
    assert [p["time"] for p in body["series"]] == [p["time"] for p in data["series"]]
    assert len(body["baseline"]) == 12 and body["baseline"][0] == {"month": 1, "mean": 11.0,
                                                                    "count": 22}
    assert body["units"] == data["units"]


def test_no_anomaly_is_404(client):
    response = client.get("/anomaly")
    assert response.status_code == 404
    assert "No anomaly data" in response.json()["detail"]


def test_bad_region_input(client):
    assert client.get("/anomaly", params={"region": "<b>"}).status_code == 422
