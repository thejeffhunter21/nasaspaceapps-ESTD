"""Independently verify monthly trend arithmetic, units and optional live results.

Run from the repository root:
  uv run --locked python scripts/verify_monthly_trends.py --source-commit COMMIT \
      --out docs/evidence/monthly_trend_verification.json
Add --api-url https://estd-api.onrender.com for a timestamped live comparison.
No AI services are called and no results files are rewritten.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import math
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pymannkendall as mk
import scipy

from earth_system_trend.ai.trend import METHODS, TrendInputError, run_trend
from earth_system_trend.pipeline.timeseries import load_series

REGIONS = ["phoenix_study_area", "phoenix_northwest", "phoenix_northeast",
           "phoenix_southwest", "phoenix_southeast"]
CALENDAR = [f"{year}-{month:02d}" for year in range(2003, 2025) for month in range(1, 13)]


def independent_seasonal(values: list[float | None]) -> dict:
    """Explicit same-month pairs; no Mann-Kendall or SciPy implementation calls.

    Ties use the standard variance correction. Missing years retain their original
    indices for the Sen slope denominator. Seasonal scores/variances are summed
    under the uncorrelated-season assumption of the implemented seasonal test.
    """
    score = 0
    variance = 0.0
    denominator = 0
    slopes = []
    counts = []
    for month in range(12):
        observed = [(i // 12, float(value)) for i, value in enumerate(values)
                    if i % 12 == month and value is not None and math.isfinite(value)]
        n = len(observed)
        counts.append(n)
        denominator += n * (n - 1) // 2
        ties = Counter(v for _, v in observed)
        variance += (n * (n - 1) * (2 * n + 5)
                     - sum(t * (t - 1) * (2 * t + 5) for t in ties.values())) / 18
        for i, (year_i, value_i) in enumerate(observed):
            for year_j, value_j in observed[i + 1:]:
                difference = value_j - value_i
                score += (difference > 0) - (difference < 0)
                slopes.append(difference / (year_j - year_i))
    z = (score - (1 if score > 0 else -1)) / math.sqrt(variance) if score and variance else 0.0
    p = math.erfc(abs(z) / math.sqrt(2))
    per_year = statistics.median(slopes)
    return {"slope": per_year / 12, "slope_per_year": per_year,
            "slope_per_decade": per_year * 10, "p": p,
            "tau": score / denominator if denominator else 0.0,
            "trend": ("increasing" if score > 0 else "decreasing") if p < 0.05 else "no trend",
            "score": score, "variance": variance, "calendar_month_counts": counts}


def agrees(expected: dict, actual: dict, *, rounded: bool = False) -> bool:
    if rounded:
        return (actual["trend"] == expected["trend"]
                and abs(actual["slope"] - expected["slope"]) <= 0.0000005 + 1e-15
                and abs(actual["tau"] - expected["tau"]) <= 0.00005 + 1e-15
                and abs(actual["p"] - expected["p"]) <= 0.0000005 + 1e-15)
    return (actual["trend"] == expected["trend"]
            and math.isclose(actual["slope"], expected["slope"], rel_tol=1e-12, abs_tol=1e-12)
            and math.isclose(actual["tau"], expected["tau"], rel_tol=1e-12, abs_tol=1e-12)
            and math.isclose(actual["p"], expected["p"], rel_tol=1e-10, abs_tol=1e-300))


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--api-url")
    args = parser.parse_args()
    root = args.root.resolve()
    data_manifest = json.loads((root / "data/processed/manifest.json").read_text())
    expected_hashes = {r["filename"]: r["sha256"] for r in data_manifest["files"]}
    records = []
    for rid in REGIONS:
        suffix = "" if rid == "phoenix_study_area" else "_" + rid
        raw_path = root / "data/processed" / f"timeseries{suffix}.csv"
        anomaly_path = root / "data/processed" / f"anomaly{suffix}.csv"
        if hashlib.sha256(raw_path.read_bytes()).hexdigest() != expected_hashes[raw_path.name]:
            raise ValueError(f"{rid}: input differs from the data manifest")
        with raw_path.open() as stream:
            raw_rows = list(csv.DictReader(stream))
        raw_values = [float(row["value"]) if row["value"] else None for row in raw_rows]
        dates, values = load_series(raw_path)
        if dates != CALENDAR or [r["date"] for r in raw_rows] != CALENDAR:
            raise ValueError(f"{rid}: calendar mismatch")
        nulls = [d for d, v in zip(dates, values) if v is None]
        if nulls != [r["date"] for r in raw_rows if not r["value"]]:
            raise ValueError(f"{rid}: loader changed missing positions")
        reference = independent_seasonal(values)
        project = run_trend(values)
        result_path = (root / "results/results.json" if rid == "phoenix_study_area"
                       else root / "results/regions" / f"{rid}.json")
        stored = json.loads(result_path.read_text())
        with anomaly_path.open() as stream:
            anomaly_rows = list(csv.DictReader(stream))
        anomaly_values = [float(r["value"]) if r["value"] else None for r in anomaly_rows]
        if [r["date"] for r in anomaly_rows] != dates:
            raise ValueError(f"{rid}: anomaly calendar mismatch")
        full_precision = independent_seasonal(raw_values)
        anomaly_reference = independent_seasonal(anomaly_values)
        # Baseline subtraction preserves same-month differences on unrounded data.
        anomaly_equivalence = agrees(full_precision, anomaly_reference)
        x = np.array([np.nan if v is None else v for v in values])
        corrected = mk.correlated_seasonal_test(x, period=12)
        stored_series_match = ([(p["time"], p["value"]) for p in stored["series"]]
                               == list(zip(dates, values)))
        stored_match = agrees(reference, stored["trend"])
        rounded_match = agrees(reference, stored["trend"], rounded=True)
        loader_difference = max(abs(a - b) for a, b in zip(raw_values, values) if a is not None)
        dropped = [v for v in values if v is not None]
        shifted = independent_seasonal(dropped) if nulls else reference
        records.append({
            "region_id": rid, "input_file": str(raw_path.relative_to(root)),
            "input_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            "calendar_positions": len(values), "valid_months": len(values) - len(nulls),
            "missing_dates": nulls, "method": METHODS["seasonal"],
            "independent_on_pipeline_input": reference,
            "independent_on_full_precision_csv": full_precision,
            "project_function": project, "stored_trend": stored["trend"],
            "checks": {"independent_matches_project": agrees(reference, project),
                       "stored_matches_independent": stored_match,
                       "stored_matches_legacy_rounding": rounded_match,
                       "stored_series_matches_loader": stored_series_match,
                       "stored_slope_unit_correct": stored["trend"]["slope_unit"] == "degC/month",
                       "stored_method_correct": stored["method"] == METHODS["seasonal"],
                       "full_precision_anomaly_equivalent": anomaly_equivalence},
            "input_rounding": {"loader_decimal_places": 4, "maximum_value_change_c": loader_difference,
                               "slope_change_c_per_month": reference["slope"] - full_precision["slope"],
                               "p_change": reference["p"] - full_precision["p"]},
            "gap_dropping_diagnostic_slope_c_per_month": shifted["slope"],
            "correlated_seasonal_library_sensitivity": {
                "function": "pymannkendall.correlated_seasonal_test(period=12)",
                "p": float(corrected.p), "trend": corrected.trend,
                "note": "Library sensitivity comparison, not an independent verification of its covariance correction or a general serial-dependence guarantee."},
        })
    synthetic = []
    for name, slope, gaps in [("positive_with_gaps", 0.01, {0, 54, 245}),
                              ("negative_with_gaps", -0.008, {54, 162, 245}),
                              ("flat_with_seasonal_cycle", 0.0, {54, 162})]:
        values = [None if i in gaps else 20 + slope * i + (i % 12) * 2.0 for i in range(264)]
        actual = run_trend(values)
        independent = independent_seasonal(values)
        passed = abs(actual["slope"] - slope) < 1e-12 and agrees(independent, actual)
        expected_direction = "increasing" if slope > 0 else "decreasing" if slope < 0 else "no trend"
        passed = passed and actual["trend"] == expected_direction
        synthetic.append({"case": name, "synthetic_not_nasa_data": True,
                          "expected_slope_c_per_month": slope, "actual": actual, "passed": passed})
    insufficient = [None if i % 12 == 6 and i // 12 < 13 else 20 + 0.01 * i for i in range(264)]
    try:
        run_trend(insufficient)
        eligibility_pass = False
    except TrendInputError:
        eligibility_pass = True
    synthetic.append({"case": "nine_valid_julys_is_rejected", "synthetic_not_nasa_data": True,
                      "passed": eligibility_pass})

    api_checks = []
    unknown = None
    if args.api_url:
        base_url = args.api_url.rstrip("/")

        def check_live(record: dict) -> dict:
            rid = record["region_id"]
            query = urllib.parse.urlencode({"region": rid})
            result = {"region_id": rid}
            try:
                series = get_json(base_url + "/series?" + query)
                trend = get_json(base_url + "/trend?" + query)
                reference = record["independent_on_pipeline_input"]
                _, expected_values = load_series(root / record["input_file"])
                result.update({
                    "method": trend.get("method"), "label": trend.get("region"),
                    "live_trend": trend["trend"], "explanation_source": trend.get("explanation_source"),
                    "calendar_and_values_match_pipeline_input": (
                        [(p["time"], p["value"]) for p in series["series"]]
                        == list(zip(CALENDAR, expected_values))),
                    "trend_matches_current_calculation": agrees(reference, trend["trend"]),
                    "trend_matches_legacy_rounding": agrees(reference, trend["trend"], rounded=True),
                    "method_matches": trend.get("method") == METHODS["seasonal"],
                    "slope_unit_matches": trend["trend"].get("slope_unit") == "degC/month",
                    "positive_p_preserved": trend["trend"]["p"] > 0,
                })
                result["status"] = ("matches_current_calculation" if result["trend_matches_current_calculation"]
                                    else "legacy_rounding" if result["trend_matches_legacy_rounding"] else "mismatch")
            except (OSError, ValueError, KeyError) as exc:
                result.update({"status": "unavailable_or_invalid", "error": str(exc)})
            return result

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            api_checks = list(pool.map(check_live, records))
        try:
            get_json(base_url + "/series?region=not_a_real_region")
            unknown = {"expected_status": 404, "actual_status": 200}
        except urllib.error.HTTPError as exc:
            unknown = {"expected_status": 404, "actual_status": exc.code}
        except OSError as exc:
            unknown = {"expected_status": 404, "error": str(exc)}

    # Rounding compatibility is reported separately and does not pass the strict check.
    offline_pass = (all(all(r["checks"].values()) for r in records)
                    and all(t["passed"] for t in synthetic))
    live_pass = (all(r.get("calendar_and_values_match_pipeline_input")
                     and r.get("trend_matches_current_calculation") and r.get("method_matches")
                     and r.get("slope_unit_matches") and r.get("positive_p_preserved") for r in api_checks)
                 and unknown is not None and unknown.get("actual_status") == 404) if args.api_url else None
    report = {"schema_version": "1.0", "checked_at_utc": datetime.now(UTC).isoformat(),
              "source_commit": args.source_commit, "data_version": data_manifest["data_version"],
              "verification_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "dependencies": {"python": sys.version.split()[0], "numpy": np.__version__,
                               "scipy": scipy.__version__, "pymannkendall": mk.__version__},
              "reference_method": "Explicit same-calendar-month score, tie-corrected variance, continuity correction, math.erfc p, and median year-index pair slopes / 12",
              "source_files_sha256": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in [
                  "src/earth_system_trend/ai/trend.py", "src/earth_system_trend/pipeline/run.py",
                  "src/earth_system_trend/pipeline/timeseries.py", "uv.lock"]},
              "offline_numerical_checks_pass": offline_pass,
              "live_api_url": args.api_url, "live_checks_pass": live_pass,
              "regions": records, "synthetic_checks": synthetic,
              "live_regions": api_checks, "unknown_region": unknown,
              "limits": ["This verifies numerical implementation of the documented uncorrected seasonal test, not that its statistical assumptions hold.",
                         "Correlated seasonal sensitivity is library-only and does not establish general robustness to year-to-year serial dependence.",
                         "Live responses have no verified deployment commit; matching values cannot establish binary/code provenance.",
                         "No AI-generated answer, causal claim, forecast or frontend interaction is evaluated here."]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"source_commit": args.source_commit, "offline_pass": offline_pass,
                      "live_pass": live_pass, "report": str(args.out),
                      "live_statuses": [r.get("status") for r in api_checks]}))
    return 0 if offline_pass and live_pass is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
