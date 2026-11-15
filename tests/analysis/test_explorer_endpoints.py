"""Public explorer endpoints: one frame at a time, exact values, documented baselines, valid stats."""

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from earth_system_trend.analysis import tools
from earth_system_trend.api.app import app

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def raw():
    with open(ROOT / "data/processed/grid_cells.csv", newline="") as f:
        return {(r["cell_id"], r["date"]): (float(r["value"]) if r["value"] else None) for r in csv.DictReader(f)}


def test_frame_values_are_exactly_the_export(client, raw):
    frame = client.get("/map-frame", params={"year": 2012, "month": 7}).json()
    assert len(frame["cells"]) == 192
    assert "calendar month" in frame["anomaly_baseline"]
    for cell in frame["cells"]:
        assert cell["value"] == raw[(cell["id"], "2012-07")]  # None stays None
    assert "values" not in frame  # a single frame, never the full series


def test_annual_frame_needs_all_twelve_months(client, raw):
    frame = client.get("/map-frame", params={"year": 2024, "month": "avg"}).json()
    for cell in frame["cells"]:
        months = [raw[(cell["id"], f"2024-{m:02d}")] for m in range(1, 13)]
        if any(v is None for v in months):
            assert cell["value"] is None
        else:
            assert cell["value"] == pytest.approx(sum(months) / 12)


def test_frame_rejects_out_of_range(client):
    assert client.get("/map-frame", params={"year": 1999, "month": 1}).status_code == 422
    assert client.get("/map-frame", params={"year": 2010, "month": "13"}).status_code == 422


def test_static_has_trend_ci_and_coverage(client):
    cells = client.get("/map-static").json()["cells"]
    assert len(cells) == 192
    for c in cells:
        assert c["ci_low_per_year"] <= c["slope_per_year"] <= c["ci_high_per_year"]
        assert 0 <= c["valid_months"] <= c["months"] == 264


def test_sen_ci_median_matches_published_slope():
    stats = tools.region_stats()["regions"]["phoenix_study_area"]
    assert stats["ci_low_per_year"] < stats["slope_per_year"] < stats["ci_high_per_year"]
    series = tools._regional_series("phoenix_study_area")
    assert tools.sen_slope_ci(series)["slope_per_year"] == pytest.approx(stats["slope_per_year"])


def test_region_compare_is_a_direct_test(client):
    r = client.get("/region-compare", params={"a": "phoenix_southeast", "b": "phoenix_northeast"}).json()
    assert r["significant"] and "difference" in r["method"]
    assert client.get("/region-compare", params={"a": "phoenix_southeast", "b": "phoenix_southeast"}).status_code == 422


def test_cell_years_are_complete_year_means_of_the_export(client):
    import csv
    r = client.get("/cell-years?id=r10_c03")
    assert r.status_code == 200
    body = r.json()
    with open("data/processed/grid_cells.csv") as fh:
        rows = [x for x in csv.DictReader(fh) if x["cell_id"] == "r10_c03"]
    for y in body["years"]:
        vals = [float(x["value"]) for x in rows if x["date"].startswith(str(y["year"])) and x["value"]]
        assert y["valid_months"] == len(vals)
        assert (y["value"] is None) == (len(vals) < 12)
        if y["value"] is not None:
            assert abs(y["value"] - sum(vals) / 12) < 1e-9
    assert client.get("/cell-years?id=r99_c99").status_code == 422
    assert client.get("/cell-years?id=../x").status_code == 422
    assert "series" not in body and len(body["years"]) == 22
