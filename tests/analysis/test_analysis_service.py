"""Private grid-cell analysis: access control, statistics rules and the public discoveries feed."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from earth_system_trend.analysis import tools
from earth_system_trend.analysis.grid import load_grid
from earth_system_trend.api.app import app

pytestmark = pytest.mark.unit
TOKEN = {"X-Analysis-Token": "t0ken"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ANALYSIS_TOKEN", "t0ken")
    monkeypatch.setenv("USE_MOCK", "false")
    with TestClient(app) as c:
        yield c


def test_private_tools_need_the_token(client, monkeypatch):
    assert client.get("/analysis/cells").status_code == 401
    assert client.get("/analysis/cells", headers={"X-Analysis-Token": "nope"}).status_code == 401
    assert client.get("/analysis/cells", headers=TOKEN).status_code == 200
    monkeypatch.setenv("ANALYSIS_TOKEN", "")
    assert client.get("/analysis/cells", headers=TOKEN).status_code == 503  # disabled, never open


def test_grid_is_read_only_and_matches_the_manifest():
    grid = load_grid()
    manifest = json.loads(Path("data/processed/grid_cells_manifest.json").read_text())
    assert grid.sha256 == manifest["sha256"] and len(grid.cells) == 192 and len(grid.months) == 264
    assert sum(v is None for c in grid.cells.values() for v in c.values) == manifest["validation"]["empty_cell_months"]


def test_cell_series_is_exactly_the_export(client):
    series = client.get("/analysis/cells/r00_c00/series", headers=TOKEN).json()
    assert series["values"][0] == pytest.approx(8.230000000000018) and len(series["values"]) == 264


def test_benjamini_hochberg():
    assert tools.bh_qvalues([0.01, 0.04, 0.03, 0.5]) == pytest.approx([0.04, 0.0533333, 0.0533333, 0.5])


def test_unknown_inputs_are_rejected(client):
    assert client.get("/analysis/cells/zz/trend", headers=TOKEN).status_code == 422
    assert client.get("/analysis/seasonal?target=r00_c00&season=XYZ", headers=TOKEN).status_code == 422


def test_public_discoveries_have_statuses_and_no_measurements(client):
    d = client.get("/discoveries").json()
    assert {f["status"] for f in d["findings"]} <= {"supported", "exploratory", "not_supported"}
    assert any(f["status"] == "exploratory" for f in d["findings"])  # discoveries are labelled, not all "true"
    for f in d["findings"]:
        assert set(f) == {"id", "hypothesis", "status", "statement", "challenge", "highlight", "cells"}
        for cell in f["cells"]:
            assert set(cell) <= {"id", "lat", "lon", "quarter", "footprint", "metric", "q", "month"}
    local = next(f for f in d["findings"] if f["id"] == "local-faster")
    assert local["status"] == "supported" and all(c["q"] < 0.05 for c in local["cells"])


def test_supported_local_cells_pass_correction_and_challenge():
    rows = tools.localized_differences()["cells"]
    supported = [r for r in rows if r["q"] < 0.05 and r["consistent_in_both_halves"]]
    assert supported and all(r["p"] <= r["q"] for r in supported)
