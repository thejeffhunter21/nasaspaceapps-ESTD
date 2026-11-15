"""B13 / J15: the pipeline's output is served by the real API server, end to end.

Runs the pipeline with --stub (fake CSV, no AI key), starts uvicorn on those files,
and calls every endpoint over HTTP. Each answer must match the files the pipeline wrote.
"""

import json
import os
import socket
import subprocess
import sys

import pytest
import requests

from earth_system_trend.contract import Results
from earth_system_trend.live_check import run_checks, wait_until_up
from earth_system_trend.pipeline.run import main as pipeline
from earth_system_trend.pipeline.run import make_stub_csv

pytestmark = pytest.mark.integration


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def served(tmp_path):
    data = tmp_path / "data"
    make_stub_csv(data / "timeseries.csv")
    make_stub_csv(data / "timeseries_north_box.csv", seed=7)
    (data / "regions.json").write_text(json.dumps([{"id": "north_box", "label": "North box"}]))
    out = tmp_path / "results" / "results.json"
    code = pipeline(["--csv", str(data / "timeseries.csv"), "--out", str(out), "--all-regions",
                     "--regions-file", str(data / "regions.json"),
                     "--region-id", "test_area", "--region", "Test area"])
    assert code == 0
    port = free_port()
    env = {**os.environ, "USE_MOCK": "false", "RESULTS_PATH": str(out),
           "REGIONS_DIR": str(out.parent / "regions"), "RATE_LIMIT_PER_MINUTE": "0"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "earth_system_trend.api.app:app",
                               "--host", "127.0.0.1", "--port", str(port)], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        assert wait_until_up(base, 30), "API did not start"
        yield base, out
    finally:
        server.terminate()
        server.wait(timeout=10)


def test_every_endpoint_passes(served):
    base, _ = served
    failed = [f"{r.path}: {r.message}" for r in run_checks(base) if not r.ok]
    assert not failed, failed


def test_answers_match_the_files(served):
    base, out = served
    written = json.loads(out.read_text())
    for key in ("forecast", "anomaly", "baseline"):
        if written.get(key) is None:
            written.pop(key, None)  # /results leaves out empty optional blocks
    assert requests.get(base + "/results", timeout=10).json() == written
    Results.model_validate(written)
    region = json.loads((out.parent / "regions" / "north_box.json").read_text())
    series = requests.get(base + "/series", params={"region": "north_box"}, timeout=10).json()
    assert series["series"] == region["series"]
    trend = requests.get(base + "/trend", params={"region": "North box"}, timeout=10).json()
    assert trend["trend"] == region["trend"]
    assert trend["explanation_source"] == "fallback"  # no AI key in tests
    ids = [r["region_id"] for r in requests.get(base + "/regions", timeout=10).json()["regions"]]
    assert ids == ["test_area", "north_box"]
