"""FE-10: review all displayed explanations without generating new text.

uv run --locked python scripts/review_frontend_story.py --out /tmp/story.json
Add --api-url https://estd-api.onrender.com for the deployed results.
Uses the AI owner's deterministic checks; no model service is called.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import requests
from pydantic import ValidationError

from earth_system_trend.ai.ai_checks import check_explanation
from earth_system_trend.ai.trend import METHODS
from earth_system_trend.contract import Results

REGIONS = ("phoenix_study_area", "phoenix_northwest", "phoenix_northeast",
           "phoenix_southwest", "phoenix_southeast")


def review_result(payload: dict) -> dict:
    """Check the same result's method, text and statistics; never rewrite it."""
    try:
        result = Results.model_validate(payload)
    except ValidationError:
        return {"passed": False, "issues": ["Invalid results contract"]}
    issues = list(check_explanation(result.explanation, result.model_dump()).problems)
    if result.method != METHODS["seasonal"]:
        issues.append("Method differs from the AI owner's documented seasonal method")
    if "mock" in result.source.casefold() or result.region.casefold() == "example region":
        issues.append("Sample data cannot complete the real-data story")
    if result.units != "degC" or result.trend.slope_unit != "degC/month":
        issues.append("Measurement units differ from the monthly Celsius contract")
    if len(result.explanation.split()) >= 120:
        issues.append("Explanation must stay under 120 words")
    return {"region_id": result.region_id, "region": result.region,
            "period": result.period.model_dump(), "method": result.method,
            "trend": result.trend.model_dump(), "source": result.source,
            "explanation_source": result.explanation_source, "explanation": result.explanation,
            "word_count": len(result.explanation.split()), "issues": issues, "passed": not issues}


def get_json(session, base_url, endpoint, region_id):
    response = session.get(f"{base_url.rstrip('/')}/{endpoint}",
                           params={"region": region_id}, timeout=(5, 45))
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--api-url")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    report = {"checked_at_utc": datetime.now(UTC).isoformat(), "api_url": args.api_url,
              "checked_checkout_commit": subprocess.check_output(
                  ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
              "reviewer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "method_reference": "docs/ai.md and earth_system_trend.ai.trend.METHODS['seasonal']",
              "status": "FAIL", "regions": []}
    try:
        with requests.Session() as session:
            for region_id in REGIONS:
                if args.api_url:
                    series = get_json(session, args.api_url, "series", region_id)
                    trend = get_json(session, args.api_url, "trend", region_id)
                    fields = ("region_id", "region", "variable", "units", "period")
                    if series.get("region_id") != region_id or any(series.get(k) != trend.get(k) for k in fields):
                        raise ValueError(f"{region_id}: mismatched series/trend metadata")
                    payload = {**trend, "series": series["series"]}
                else:
                    path = (root / "results/results.json" if region_id == REGIONS[0]
                            else root / f"results/regions/{region_id}.json")
                    payload = json.loads(path.read_text())
                report["regions"].append(review_result(payload))
        if all(region["passed"] for region in report["regions"]):
            report["status"] = "PASS"
    except (OSError, ValueError, KeyError, requests.RequestException) as exc:
        report["error"] = str(exc)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "regions": len(report["regions"]), "out": str(args.out)}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
