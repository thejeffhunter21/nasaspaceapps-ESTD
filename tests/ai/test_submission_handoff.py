"""A12: the submission handoff must describe the committed results, not an older snapshot.

If a results file changes, re-run the four checks in docs/ai_submission.md and update the table.
"""

import json
from pathlib import Path

import pytest

from earth_system_trend.ai import ai_release

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]
EVIDENCE = ROOT / "docs" / "evidence" / "ai"
HANDOFF = (ROOT / "docs" / "ai_submission.md").read_text(encoding="utf-8")
LABELS = {"phoenix_study_area": "Phoenix study area", "phoenix_northwest": "Northwest",
          "phoenix_northeast": "Northeast", "phoenix_southwest": "Southwest",
          "phoenix_southeast": "Southeast"}


def load(name):
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def table_row(label):
    return next(line for line in HANDOFF.splitlines() if line.startswith(f"| {label} |"))


def test_all_four_release_checks_passed_at_the_same_commit():
    trend = load("a12_trend_verification.json")
    files = load("a12_story_review_files.json")
    live = load("a12_story_review_live.json")
    release = load("a12_release_check.json")
    assert trend["offline_numerical_checks_pass"] is True
    assert trend["live_checks_pass"] is True
    assert files["status"] == live["status"] == release["status"] == "PASS"
    commits = {trend["source_commit"], files["checked_checkout_commit"],
               live["checked_checkout_commit"], release["checked_checkout_commit"]}
    assert len(commits) == 1
    assert next(iter(commits)) in HANDOFF


def test_evidence_still_describes_the_committed_results():
    assert load("a12_release_check.json")["result_sha256"] == ai_release.result_hashes(ROOT)


def test_handoff_table_matches_the_committed_results():
    for region_id, result in ai_release.load_committed(ROOT).items():
        row = table_row(LABELS[region_id])
        trend = result["trend"]
        missing = [p["time"] for p in result["series"] if p["value"] is None]
        assert f"| {trend['slope']:.3g} | {trend['slope'] * 12:.3g} |" in row, region_id
        assert f"({trend['p']:.2e})" in row, region_id
        assert f"| {trend['trend']} |" in row, region_id
        assert all(month in row for month in missing), region_id
        shown = "automatic summary" if result["explanation_source"] == "fallback" else "AI"
        assert row.rstrip().endswith(f"| {shown} |"), region_id


def test_handoff_says_no_ai_text_only_while_that_is_true():
    sources = {r["explanation_source"] for r in ai_release.load_committed(ROOT).values()}
    assert ("AI text is not used in this release" in HANDOFF) == (sources == {"fallback"})


def test_readme_describes_what_the_app_shows():
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    app = (ROOT / "app" / "streamlit_app.py").read_text(encoding="utf-8")
    for label in ("Automatic summary", "AI-assisted explanation"):
        assert f'"{label}"' in app and f'"{label}"' in readme  # the labels the dashboard uses
    sources = {r["explanation_source"] for r in ai_release.load_committed(ROOT).values()}
    claims_no_ai = "The committed results contain no Gemini text" in readme
    assert claims_no_ai == (sources == {"fallback"})
    assert "GEMINI_LIVE=1" in readme  # a key alone never calls Gemini (A10)


def test_evidence_contains_no_local_paths():
    for path in EVIDENCE.glob("a12_*.json"):
        text = path.read_text(encoding="utf-8")
        assert "AppData" not in text and ":\\\\Users" not in text and "/home/" not in text, path
