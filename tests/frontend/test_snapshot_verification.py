"""FE-09: reject snapshot drift before calling frontend evidence verified."""

import csv
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.verify_frontend_snapshot import (
    EXPECTED_GAPS,
    SnapshotMismatch,
    check_local_snapshot,
    compare_region,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def raw_points(region_id):
    name = "timeseries.csv" if region_id == "phoenix_study_area" else f"timeseries_{region_id}.csv"
    with (ROOT / "data/processed" / name).open() as stream:
        return [{"time": row["date"], "value": float(row["value"]) if row["value"] else None}
                for row in csv.DictReader(stream)]


@pytest.fixture
def regional_response():
    region_id = "phoenix_northwest"
    points = raw_points(region_id)
    with (ROOT / f"results/regions/{region_id}.json").open() as stream:
        result = json.load(stream)
    series = {key: result[key] for key in (
        "region_id", "region", "variable", "units", "period", "series",
    )}
    trend = {key: value for key, value in result.items() if key != "series"}
    return region_id, points, series, trend


def test_local_snapshot_matches_approved_hashes_calendars_and_gaps():
    snapshot = check_local_snapshot(ROOT)
    assert snapshot["data_version"] == "phoenix-qc-v1.0"
    assert len(snapshot["regions"]) == 5
    assert sum(len(row["missing_dates"]) for row in snapshot["regions"].values()) == 8
    assert snapshot["regions"]["phoenix_study_area"]["valid_months"] == 264
    assert snapshot["regions"]["phoenix_northwest"]["missing_dates"] == ["2024-05"]
    assert snapshot["coverage_records"] == 1320


def test_changed_csv_bytes_are_rejected(monkeypatch):
    original_read = Path.read_bytes

    def changed(path):
        data = original_read(path)
        return data + b"\n" if path.name == "timeseries.csv" else data

    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(SnapshotMismatch, match="hash"):
        check_local_snapshot(ROOT)


def test_approved_csv_api_rounding_and_null_gap_are_verified(regional_response):
    region_id, points, series, trend = regional_response
    record = compare_region(region_id, points, series, trend)
    assert record["positions"] == 264
    assert record["missing_dates"] == ["2024-05"]
    assert record["valid_months"] == 263
    assert record["csv_to_api_max_abs_difference"] <= 0.00005
    assert record["api_matches_rounded_csv"] is True


@pytest.mark.parametrize("problem", ["value", "filled_gap", "dropped_month", "units", "mock", "period"])
def test_bad_api_snapshot_is_rejected(regional_response, problem):
    region_id, points, series, trend = deepcopy(regional_response)
    if problem == "value":
        series["series"][0]["value"] += 0.001
    elif problem == "filled_gap":
        next(point for point in series["series"] if point["value"] is None)["value"] = 0
    elif problem == "dropped_month":
        series["series"] = [p for p in series["series"] if p["value"] is not None]
    elif problem == "units":
        series["units"] = trend["units"] = "K"
    elif problem == "mock":
        trend["source"] = "Mock data, phoenix-qc-v1.0"
    elif problem == "period":
        series["period"]["start"] = "2004-01"
    with pytest.raises(SnapshotMismatch):
        compare_region(region_id, points, series, trend)


def test_changed_expected_gap_is_rejected(regional_response):
    region_id, points, series, trend = deepcopy(regional_response)
    gap = next(point for point in points if point["value"] is None)
    gap["value"] = 1.0
    with pytest.raises(SnapshotMismatch):
        compare_region(region_id, points, series, trend)
    assert EXPECTED_GAPS[region_id] == ["2024-05"]
