"""A8: the data team's question bank (docs/ai_question_tests.json) against the AI layer.

The app has no question-answering interface (frontend plan: no free-text AI chat this sprint),
so the conversational cases are not run. What is tested here:
  1. the bank, its evidence and the trend verification still match the committed data;
  2. every numeric expected fact, recomputed from the CSVs;
  3. the trend case's condition: stored results = independently verified result, same input
     hash, named method, degC/month;
  4. a Gemini reply containing each applicable case's forbidden claim is rejected (A3);
  5. every region's explanation conveys its own region, period, measurement and units.
Results are recorded in docs/ai_question_results.md.
"""

import csv
import hashlib
import json
import math
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from earth_system_trend.ai import ai_setup
from earth_system_trend.ai.ai_checks import check_explanation
from earth_system_trend.ai.explain import explain
from earth_system_trend.ai.trend import METHODS

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]
DOCS = ROOT / "docs"
DATA = ROOT / "data" / "processed"
BANK = json.loads((DOCS / "ai_question_tests.json").read_text())
EVIDENCE = json.loads((DOCS / BANK["evidence_file"]).read_text())
VERIFIED = json.loads((DOCS / "evidence" / "monthly_trend_verification.json").read_text())
CASES = {case["id"]: case for case in BANK["cases"]}
REGIONS = {r["region_id"]: r for r in EVIDENCE["regions"]}
COVERAGE_ID = {rid: r["coverage_baseline_region_id"] for rid, r in REGIONS.items()}


def results_path(region_id):
    if region_id == "phoenix_study_area":
        return ROOT / "results" / "results.json"
    return ROOT / "results" / "regions" / f"{region_id}.json"


def results(region_id):
    data = json.loads(results_path(region_id).read_text())
    data.pop("explanation", None)
    data.pop("explanation_source", None)
    return data


def series(region_id):
    with open(ROOT / REGIONS[region_id]["raw_file"]) as f:
        return {r["date"]: float(r["value"]) if r["value"].strip() else None
                for r in csv.DictReader(f)}


def climatology():
    with open(DATA / "climatology.csv") as f:
        return {(r["region"], int(r["month"])): (float(r["mean"]), int(r["count"]))
                for r in csv.DictReader(f)}


def coverage(region_id, date):
    with open(DATA / "coverage.csv") as f:
        return next(r for r in csv.DictReader(f)
                    if r["region"] == COVERAGE_ID[region_id] and r["date"] == date)


def close(a, b, case):
    return abs(a - b) <= case["numeric_tolerance_c"]


# --- 1. bank, evidence and verification agree with the data -----------------------------

def test_bank_is_well_formed():
    assert BANK["case_count"] == len(BANK["cases"]) == len(CASES) == 17
    assert {c["region_id"] for c in BANK["cases"]} <= set(REGIONS)
    for case in BANK["cases"]:
        assert case["question"] and case["must_convey"] and case["must_not_claim"], case["id"]


def test_one_data_version_everywhere():
    version = BANK["data_version"]
    assert EVIDENCE["data_version"] == VERIFIED["data_version"] == version
    for region_id in REGIONS:
        assert version in json.loads(results_path(region_id).read_text())["source"]


@pytest.mark.parametrize("path, expected", sorted(EVIDENCE["input_sha256"].items()))
def test_evidence_hashes_still_match_the_files(path, expected):
    """If the data changes, the bank and evidence must be rebuilt together (README step 2)."""
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected


# --- 2. numeric expected facts, recomputed from the CSVs --------------------------------

def test_period_case():
    facts, values = CASES["period"]["expected_facts"], series("phoenix_study_area")
    assert (min(values), max(values)) == (facts["start"], facts["end"])
    assert len(values) == facts["calendar_positions"]
    assert sum(v is not None for v in values.values()) == facts["valid_months"]


@pytest.mark.parametrize("case_id", ["exact_observation", "region_switch"])
def test_observation_cases(case_id):
    case = CASES[case_id]
    facts = case["expected_facts"]
    assert close(series(case["region_id"])[facts["date"]], facts["value_c"], case)


def test_region_switch_value_differs_from_the_whole_area():
    facts = CASES["region_switch"]["expected_facts"]
    whole = series("phoenix_study_area")[facts["date"]]
    assert abs(whole - facts["value_c"]) > 0.1  # reusing the whole-area value would be wrong


def test_missing_month_case():
    case = CASES["missing_month"]
    facts, rid = case["expected_facts"], case["region_id"]
    assert series(rid)[facts["date"]] is None
    row = coverage(rid, facts["date"])
    assert int(row["accepted_cells"]) == facts["accepted_cells"]
    assert REGIONS[rid]["grid_cells"] == facts["total_cells"]
    assert math.isclose(float(row["area_fraction"]), facts["area_fraction"], rel_tol=1e-12)
    assert facts["area_fraction"] < facts["required_area_fraction"]
    assert results(rid)["series"][[p["time"] for p in results(rid)["series"]].index(
        facts["date"])]["value"] is None  # kept as null in the served results


def test_missing_comparison_case():
    facts = CASES["missing_comparison"]["expected_facts"]
    counts = {rid: sum(v is None for v in series(rid).values()) for rid in REGIONS}
    assert counts["phoenix_study_area"] == facts["whole_area_missing"]
    for box in ("northwest", "northeast", "southwest", "southeast"):
        assert counts[f"phoenix_{box}"] == facts[f"{box}_missing"]


def test_anomaly_calculation_case():
    case = CASES["anomaly_calculation"]
    facts = case["expected_facts"]
    mean, count = climatology()[("phoenix", 1)]
    raw = series("phoenix_study_area")["2003-01"]
    assert close(raw, facts["raw_c"], case)
    assert close(mean, facts["january_baseline_mean_c"], case) and count == facts["baseline_count"]
    assert close(raw - mean, facts["anomaly_c"], case)


def test_baseline_count_case():
    case = CASES["baseline_count"]
    facts, rid = case["expected_facts"], case["region_id"]
    month = facts["calendar_month"]
    assert climatology()[(COVERAGE_ID[rid], month)][1] == facts["baseline_count"]
    missing = [d for d, v in series(rid).items() if v is None and int(d[5:]) == month]
    assert missing == facts["missing_julys"]


def test_outside_period_and_supported_regions():
    assert max(series("phoenix_study_area")) == CASES["outside_period"]["expected_facts"][
        "last_loaded_month"]
    assert sorted(CASES["unsupported_location"]["expected_facts"]["supported_region_ids"]) == \
        sorted(REGIONS)


# --- 3. trend case: a separately validated, matching result ------------------------------

@pytest.mark.parametrize("region_id", sorted(REGIONS))
def test_trend_case_condition_is_met(region_id):
    verified = next(r for r in VERIFIED["regions"] if r["region_id"] == region_id)
    stored = results(region_id)
    raw_file = REGIONS[region_id]["raw_file"]
    current_hash = hashlib.sha256((ROOT / raw_file).read_bytes()).hexdigest()
    assert verified["input_sha256"] == REGIONS[region_id]["raw_sha256"] == current_hash
    assert verified["method"] == stored["method"] == METHODS["seasonal"]
    assert stored["trend"]["slope_unit"] == "degC/month"
    independent = verified["independent_on_pipeline_input"]
    assert stored["trend"]["trend"] == independent["trend"]
    for key in ("slope", "p", "tau"):
        assert math.isclose(stored["trend"][key], independent[key], rel_tol=1e-9), key


# --- 4. forbidden claims cannot get through the AI layer --------------------------------

# One crafted Gemini reply per applicable case, each making that case's forbidden claim.
FORBIDDEN_REPLIES = [
    ("measurement", ("These are air temperature observations for the Phoenix study area, rising "
                    "about 0.00771 degC per month; statistically significant (p < 0.001).")),
    ("period", ("These are current live measurements; the Phoenix study area is rising; "
               "statistically significant (p < 0.001).")),
    ("exact_observation", ("The hottest day in 2003-01 was 7.76 degC; temperature is rising; "
                          "statistically significant (p < 0.001).")),
    ("missing_month", ("Northwest temperature was 0 degC in 2024-05, and it is rising; "
                      "statistically significant (p < 0.001).")),
    ("missing_comparison", ("The northwest box has a gap, so the whole study area is missing "
                           "too; rising; statistically significant (p < 0.001).")),
    ("region_switch", ("Phoenix study area northeast rose by about 0.00771 degC per month; "
                      "statistically significant (p < 0.001).")),
    ("outside_period", ("In 2026-07 the study area reached 31 degC; rising; statistically "
                       "significant (p < 0.001).")),
    ("tomorrow", ("Rising about 0.00771 degC per month, so it will be hot tomorrow on your farm; "
                 "statistically significant (p < 0.001).")),
    ("unsupported_location", ("In Tucson, nighttime land surface temperature rose by about "
                             "0.00771 degC per month; statistically significant (p < 0.001).")),
    ("trend_significance", "The study area warmed significantly by 0.5 degC per year."),
    ("cause", ("New buildings caused the warming of about 0.00771 degC per month; statistically "
              "significant (p < 0.001).")),
    ("drainage", ("Rising about 0.00771 degC per month; increase drainage capacity by 25 percent; "
                 "statistically significant (p < 0.001).")),
    ("irrigation", ("Rising about 0.00771 degC per month; apply 400 litres of extra irrigation; "
                   "statistically significant (p < 0.001).")),
    ("planning_priority", ("Shade Van Buren Street first; it would cool by 1.5 degC; rising, "
                          "statistically significant (p < 0.001).")),
]
NOT_FOR_SUMMARIES = {"anomaly_calculation", "positive_anomaly", "baseline_count"}


def test_every_case_is_either_covered_or_marked_not_applicable():
    covered = {case_id for case_id, _ in FORBIDDEN_REPLIES}
    assert covered | NOT_FOR_SUMMARIES == set(CASES)
    assert not covered & NOT_FOR_SUMMARIES


@pytest.fixture
def gemini_says(monkeypatch):
    def install(content):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={
                "id": "x", "object": "chat.completion", "created": 0, "model": "test-flash",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": content}}],
            })

        monkeypatch.setattr(ai_setup, "OpenAI", lambda **kw: OpenAI(
            http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kw))
        monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
        monkeypatch.setenv("GEMINI_MODEL", "test-flash")
        monkeypatch.setenv("GEMINI_LIVE", "1")
        return requests

    return install


@pytest.mark.parametrize("case_id, reply", FORBIDDEN_REPLIES, ids=[c for c, _ in FORBIDDEN_REPLIES])
def test_forbidden_claim_is_rejected(case_id, reply, gemini_says):
    region = results(CASES[case_id]["region_id"])
    assert not check_explanation(reply, region).ok
    requests = gemini_says(reply)
    answer = explain(region, sleep=lambda _: None)
    assert len(requests) == 1
    assert answer["source"] == "fallback"
    assert answer["text"] != reply


# --- 5. what every region's explanation must convey -------------------------------------

@pytest.mark.parametrize("region_id", sorted(REGIONS))
def test_explanation_conveys_selected_region_period_measurement_and_units(region_id):
    region = results(region_id)
    text = explain(region)["text"]  # no key in tests: the fallback summary
    assert region["region"] in text  # the selected region, not the whole area
    assert region["period"]["start"] in text and region["period"]["end"] in text
    assert "nighttime land surface temperature" in text.lower()
    assert "degC per month" in text
    assert "statistically significant" in text and "p < 0.001" in text
    missing = sum(p["value"] is None for p in region["series"])
    assert (f"{missing} of 264 months are missing" in text) == bool(missing)
    assert check_explanation(text, region).ok


# --- record -----------------------------------------------------------------------------

def test_results_record_lists_every_case():
    record = (DOCS / "ai_question_results.md").read_text()
    for case_id in CASES:
        assert f"`{case_id}`" in record, case_id
    assert BANK["data_version"] in record
