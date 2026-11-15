"""Ask the Climate Detective: every answer is built from tool output, with no language model."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from earth_system_trend.analysis import ask, tools
from earth_system_trend.api.app import app

pytestmark = pytest.mark.unit
CTX = {"year": 2024, "month": "7", "cell": "r10_c03", "region": "all"}


def test_cell_value_is_exactly_the_export():
    a = ask.ask("How hot was this cell in July 2024?", CTX)
    with Path("data/processed/grid_cells.csv").open() as fh:
        row = next(r for r in csv.DictReader(fh) if r["cell_id"] == "r10_c03" and r["date"] == "2024-07")
    assert a["kind"] == "value" and f"{float(row['value']):.1f} °C" in a["headline"] and a["cells"] == ["r10_c03"]


def test_trend_answer_matches_the_tool():
    t = tools.cell_trend("r05_c07")
    a = ask.ask("How fast is r05_c07 warming?")
    assert f"{t['slope_per_year']:+.3f}" in a["headline"]
    assert a["stats"][1]["value"] == f"{t['ci_low_per_year']:+.3f} to {t['ci_high_per_year']:+.3f}"


def test_region_comparison_uses_the_direct_test():
    d = tools.region_difference("phoenix_northwest", "phoenix_southeast")
    a = ask.ask("Compare the northwest and southeast")
    assert a["kind"] == "compare" and f"{abs(d['difference_slope_per_year']):.3f}" in a["headline"]


def test_yes_no_follows_the_data_not_the_question():
    no = ask.ask("Is Tempe warming faster than Glendale?")
    yes = ask.ask("Is Glendale warming faster than Tempe?")
    assert no["headline"].startswith("No.") and yes["headline"].startswith("Yes.")


def test_fastest_cell_is_the_top_of_the_corrected_ranking():
    top = max(tools.all_cell_trends()["cells"], key=lambda r: r["slope_per_year"])
    assert top["id"] in ask.ask("Which cell warmed the most?")["headline"]


@pytest.mark.parametrize("question, kind", [
    ("Do summer nights warm faster than winter nights?", "seasons"),
    ("What was unusual in 2023?", "unusual"),
    ("Which neighbourhoods warm faster than their quarter?", "hotspots"),
    ("Will Phoenix be hotter in 2050?", "forecast"),
    ("Why is the southeast warming faster?", "cause"),
    ("What is land surface temperature?", "background"),
    ("how many months are missing", "coverage"),
    ("tell me a joke", "help"),
])
def test_routing(question, kind):
    assert ask.ask(question, CTX)["kind"] == kind


def test_missing_values_are_never_filled():
    grid_missing = next((c, i) for c, cell in ask.load_grid().cells.items() for i, v in enumerate(cell.values) if v is None)
    cid, i = grid_missing
    month = ask.load_grid().months[i]
    a = ask.ask(f"How warm was {cid} in {ask.MONTHS[int(month[5:]) - 1]} {month[:4]}?")
    assert a["kind"] == "no_data" and "never filled" in a["headline"]


def test_endpoint(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "false")
    with TestClient(app) as c:
        assert c.get("/ask/status").json()["enabled"] is True
        r = c.post("/ask", json={"question": "Is Tempe warming faster than Glendale?", "context": CTX})
        assert r.status_code == 200 and r.json()["status"] == "answered" and len(r.json()["stats"]) == 4
        assert c.post("/ask", json={"question": ""}).status_code == 422
        assert c.post("/ask", json={"question": "x" * 601}).status_code == 422


def test_no_language_model_in_the_engine():
    src = Path("src/earth_system_trend/analysis/ask.py").read_text()
    assert "openai" not in src and "gemini" not in src.lower().replace("never calls gemini", "")


def test_halves_answer_separates_gaps_from_real_change():
    from earth_system_trend.analysis.investigator import h1_widespread
    a = ask.ask("Which cells lose their warming in one half of the record?")
    both = h1_widespread()["evidence"]["warming_in_both_halves"]
    assert a["kind"] == "halves" and a["stats"][0]["value"].startswith(f"{both} of")


def test_questions_needing_outside_data_say_so():
    a = ask.ask("Do these cells coincide with areas that urbanised after 2003?")
    assert a["kind"] == "outside_data" and "doesn't have" in a["headline"] and a["cells"]
    assert ask.ask("Do the fastest cells cluster together?")["kind"] == "cluster"
