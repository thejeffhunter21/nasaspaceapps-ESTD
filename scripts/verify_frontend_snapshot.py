"""FE-09: verify the approved CSV -> saved/API result -> frontend snapshot.

Offline: uv run --locked python scripts/verify_frontend_snapshot.py --out /tmp/snapshot.json
Add --api-url https://estd-api.onrender.com to check all five live regions and the page.
Reads processed files only; never rebuilds results or calls an AI/NASA service.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import requests
from pydantic import ValidationError

from earth_system_trend.contract import Results

VERSION = "phoenix-qc-v1.0"
CALENDAR = [f"{year}-{month:02d}" for year in range(2003, 2025) for month in range(1, 13)]
EXPECTED_GAPS = {
    "phoenix_study_area": [],
    "phoenix_northwest": ["2024-05"],
    "phoenix_northeast": ["2007-07", "2023-07"],
    "phoenix_southwest": ["2007-07", "2010-07"],
    "phoenix_southeast": ["2012-07", "2017-07", "2024-06"],
}


class SnapshotMismatch(ValueError):
    """The approved files, result or display do not agree."""


def require(condition, message):
    if not condition:
        raise SnapshotMismatch(message)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_name(region_id):
    return "timeseries.csv" if region_id == "phoenix_study_area" else f"timeseries_{region_id}.csv"


def read_points(path):
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))
    require(reader.fieldnames == ["date", "value"], f"{path.name}: unexpected CSV columns")
    points = [{"time": row["date"], "value": float(row["value"]) if row["value"] else None}
              for row in reader]
    require(all(p["value"] is None or math.isfinite(p["value"]) for p in points),
            f"{path.name}: non-finite CSV observation")
    return points


def check_calendar(region_id, points):
    require([p["time"] for p in points] == CALENDAR, f"{region_id}: calendar mismatch")
    missing = [p["time"] for p in points if p["value"] is None]
    require(missing == EXPECTED_GAPS[region_id], f"{region_id}: missing dates mismatch")
    return missing


def check_local_snapshot(root: Path) -> dict:
    data = root / "data/processed"
    manifest_path = data / "manifest.json"
    quality_path = data / "data_quality_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    quality = json.loads(quality_path.read_text())
    require(manifest["data_version"] == quality["data_version"] == VERSION, "snapshot version mismatch")
    require(quality["threshold_area_fraction"] == 0.8, "coverage threshold mismatch")
    hashes = {}
    expected = {item["filename"]: item["sha256"] for item in manifest["files"]}
    require(set(expected) == {csv_name(rid) for rid in EXPECTED_GAPS}, "manifest file set mismatch")
    for name, digest in expected.items():
        path = data / name
        require(sha256(path) == digest, f"{name}: CSV hash mismatch")
        hashes[f"data/processed/{name}"] = digest
    require({item["filename"]: item["sha256"] for item in quality["input_files"]} == expected,
            "data/quality manifest hash disagreement")
    for item in quality["files"]:
        require(sha256(root / item["path"]) == item["sha256"], f"{item['path']}: sidecar hash mismatch")
        hashes[item["path"]] = item["sha256"]
    with (data / "coverage.csv").open() as stream:
        coverage_rows = list(csv.DictReader(stream))
    coverage = {(row["region"], row["date"]): row for row in coverage_rows}
    require(len(coverage) == len(coverage_rows) == quality["coverage_records"] == 1320,
            "coverage calendar count/uniqueness mismatch")
    quality_regions = {row["region"]: row for row in quality["regions"]}
    regions = {}
    for region_id in EXPECTED_GAPS:
        points = read_points(data / csv_name(region_id))
        missing = check_calendar(region_id, points)
        data_id = "phoenix" if region_id == "phoenix_study_area" else region_id
        require(manifest["regions"][data_id]["rows"] == len(points), f"{region_id}: manifest rows mismatch")
        require(manifest["regions"][data_id]["missing_dates"] == missing, f"{region_id}: manifest gaps mismatch")
        q = quality_regions[data_id]
        require(q["valid_months"] == len(points) - len(missing), f"{region_id}: valid count mismatch")
        require([row["date"] for row in q["missing_details"]] == missing, f"{region_id}: quality gaps mismatch")
        for point in points:
            row = coverage.get((data_id, point["time"]))
            require(row is not None, f"{region_id}: missing coverage record")
            fraction = float(row["area_fraction"])
            require(math.isfinite(fraction) and 0 <= fraction <= 1, f"{region_id}: invalid coverage")
            require((fraction < 0.8) == (point["value"] is None), f"{region_id}: coverage/gap mismatch")
        regions[region_id] = {"csv": csv_name(region_id), "positions": len(points),
                              "valid_months": len(points) - len(missing), "missing_dates": missing}
    return {"data_version": VERSION, "source_reference": manifest["source_reference"],
            "manifest_sha256": sha256(manifest_path), "quality_manifest_sha256": sha256(quality_path),
            "file_hashes": hashes, "coverage_records": len(coverage), "regions": regions}


def compare_region(region_id, points, series, trend) -> dict:
    check_calendar(region_id, points)
    require(isinstance(series, dict) and isinstance(trend, dict), f"{region_id}: invalid API response")
    payload = {**trend, "series": series.get("series")}
    try:
        Results.model_validate(payload)
    except ValidationError as exc:
        raise SnapshotMismatch(f"{region_id}: invalid results contract") from exc
    require(series.get("region_id") == trend.get("region_id") == region_id, f"{region_id}: ID mismatch")
    for field in ("region", "variable", "units", "period"):
        require(series.get(field) == trend.get(field), f"{region_id}: {field} mismatch")
    require(series["units"] == "degC" and trend["trend"]["slope_unit"] == "degC/month",
            f"{region_id}: unit mismatch")
    source = trend["source"]
    require("mock" not in source.casefold() and "example region" != trend["region"].casefold(),
            f"{region_id}: sample data cannot verify a real snapshot")
    require(all(token in source for token in (VERSION, "MOD11C3.061", "LST_Night_CMG",
                                              "10.5067/MODIS/MOD11C3.061")),
            f"{region_id}: source/version mismatch")
    require("nighttime" in series["variable"].casefold() and "surface temperature" in series["variable"].casefold(),
            f"{region_id}: measurement mismatch")
    missing = check_calendar(region_id, series["series"])
    differences = []
    for raw, actual in zip(points, series["series"]):
        if raw["value"] is None:
            require(actual["value"] is None, f"{region_id}: gap was filled")
        else:
            require(actual["value"] is not None and math.isclose(actual["value"], round(raw["value"], 4),
                    rel_tol=0, abs_tol=1e-12), f"{region_id}: CSV/API value mismatch at {raw['time']}")
            differences.append(abs(actual["value"] - raw["value"]))
    sample_indices = sorted({0, len(points) // 2, len(points) - 1,
                             *[i for i, point in enumerate(points) if point["value"] is None]})
    return {"region_id": region_id, "region": series["region"], "period": series["period"],
            "positions": len(points), "valid_months": len(points) - len(missing), "missing_dates": missing,
            "units": series["units"], "slope_unit": trend["trend"]["slope_unit"],
            "source": source, "method": trend["method"], "trend": trend["trend"],
            "csv_to_api_rule": "round(value, 4), preserving nulls (documented pipeline preprocessing)",
            "csv_to_api_max_abs_difference": max(differences), "api_matches_rounded_csv": True,
            "sample_values": [{"time": points[i]["time"], "csv_value": points[i]["value"],
                               "result_value": series["series"][i]["value"]} for i in sample_indices]}


def split_result(result):
    return ({key: result[key] for key in ("region_id", "region", "variable", "units", "period", "series")},
            {key: value for key, value in result.items() if key != "series"})


def get_json(session, url, region_id):
    response = session.get(url, params={"region": region_id}, timeout=(5, 45))
    response.raise_for_status()
    return response.json()


def check_page(page, region_id, series, trend):
    require(not page.exception and not page.error, f"{region_id}: frontend did not render")
    require(page.subheader[0].value == series["region"], f"{region_id}: page region mismatch")
    require(not page.warning, f"{region_id}: real snapshot has a sample warning")
    chart = json.loads(page.get("plotly_chart")[0].proto.spec)["data"][0]
    require(chart["x"] == [p["time"] for p in series["series"]], f"{region_id}: plotted calendar mismatch")
    require(chart["y"] == [p["value"] for p in series["series"]], f"{region_id}: plotted values mismatch")
    require(chart["connectgaps"] is False, f"{region_id}: chart connects missing months")
    require(page.text[0].value == trend["explanation"], f"{region_id}: explanation mismatch")
    cards = {metric.label: metric.value for metric in page.metric}
    expected_p = "p < 0.001" if trend["trend"]["p"] < 0.001 else str(trend["trend"]["p"])
    require(cards == {"Slope (°C/month)": str(trend["trend"]["slope"]),
                      "p-value": expected_p, "Direction": trend["trend"]["trend"]},
            f"{region_id}: displayed statistics mismatch")
    captions = [caption.value for caption in page.caption]
    require(f"Source: {trend['source']}" in captions and f"Method: {trend['method']}" in captions,
            f"{region_id}: displayed provenance mismatch")
    return {"plotted_series_matches_api": True, "gaps_preserved": True,
            "statistics_match_api": True, "explanation_and_provenance_match_api": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--api-url")
    args = parser.parse_args()
    root = args.root.resolve()
    report = {"checked_at_utc": datetime.now(UTC).isoformat(), "status": "FAIL",
              "checked_checkout_commit": subprocess.check_output(
                  ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
              "verifier_sha256": sha256(Path(__file__)), "api_url": args.api_url,
              "scope": "Approved processed snapshot, saved/API results and frontend; no raw NASA/pixel QC rerun"}
    try:
        report["snapshot"] = check_local_snapshot(root)
        report["regions"] = []
        page = None
        if args.api_url:
            import os

            from streamlit.testing.v1 import AppTest

            os.environ["API_URL"] = args.api_url
            page = AppTest.from_file(str(root / "app/streamlit_app.py")).run(timeout=210)
            require(not page.exception and not page.error and page.selectbox,
                    "The live frontend did not render its region selector")
        with requests.Session() as session:
            for region_id in EXPECTED_GAPS:
                points = read_points(root / "data/processed" / csv_name(region_id))
                result_path = (root / "results/results.json" if region_id == "phoenix_study_area"
                               else root / f"results/regions/{region_id}.json")
                saved = json.loads(result_path.read_text())
                record = compare_region(region_id, points, *split_result(saved))
                record["saved_result_sha256"] = sha256(result_path)
                if args.api_url:
                    base = args.api_url.rstrip("/")
                    series = get_json(session, f"{base}/series", region_id)
                    trend = get_json(session, f"{base}/trend", region_id)
                    live = compare_region(region_id, points, series, trend)
                    for key in ("slope", "p", "tau"):
                        require(math.isclose(saved["trend"][key], trend["trend"][key],
                                rel_tol=1e-12, abs_tol=1e-300), f"{region_id}: saved/live {key} mismatch")
                    require(saved["trend"]["trend"] == trend["trend"]["trend"], f"{region_id}: saved/live direction mismatch")
                    require(saved["method"] == trend["method"], f"{region_id}: saved/live method mismatch")
                    record["live"] = {
                        "api_matches_rounded_csv": live["api_matches_rounded_csv"],
                        "statistics_and_method_match_saved": True,
                        "csv_to_api_max_abs_difference": live["csv_to_api_max_abs_difference"],
                        "series_sha256": hashlib.sha256(json.dumps(series["series"], sort_keys=True).encode()).hexdigest(),
                    }
                    page.selectbox[0].select(region_id).run(timeout=210)
                    record["frontend"] = check_page(page, region_id, series, trend)
                report["regions"].append(record)
        report["status"] = "PASS"
    except (SnapshotMismatch, OSError, ValueError, KeyError, requests.RequestException) as exc:
        report["error"] = str(exc)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "report": str(args.out), "error": report.get("error")}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
