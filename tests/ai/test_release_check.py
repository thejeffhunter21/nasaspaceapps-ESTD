"""A11: AI release check - the frozen results, their explanations and the offline demo.

Nothing here reaches Gemini or the network: the release check itself forces AI off and blocks
sockets, and tests/conftest.py strips any key.
"""

import copy
import json
import socket
from pathlib import Path

import pytest

from earth_system_trend.ai import ai_release
from earth_system_trend.ai import explain as ai_explain

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]
EVIDENCE = ROOT / "docs" / "evidence" / "ai" / "a11_release_check.json"
REGION_IDS = ["phoenix_study_area", "phoenix_northeast", "phoenix_northwest",
              "phoenix_southeast", "phoenix_southwest"]


@pytest.fixture(scope="module")
def committed():
    return ai_release.load_committed(ROOT)


@pytest.fixture(scope="module")
def rebuilt():
    return ai_release.rebuild_offline(ROOT)


# --- inventory --------------------------------------------------------------------------

def test_committed_results_cover_all_five_regions(committed):
    assert sorted(committed) == sorted(REGION_IDS)
    paths = ai_release.result_paths(ROOT)
    assert paths["phoenix_study_area"] == ROOT / "results" / "results.json"
    assert paths["phoenix_northwest"] == ROOT / "results" / "regions" / "phoenix_northwest.json"


# --- offline rebuild --------------------------------------------------------------------

def test_offline_rebuild_matches_every_committed_file(committed, rebuilt):
    assert sorted(rebuilt.results) == sorted(REGION_IDS)
    assert rebuilt.network_attempts == 0
    for region_id in REGION_IDS:
        assert ai_release.rebuild_differences(committed[region_id],
                                              rebuilt.results[region_id]) == []


def test_rebuild_difference_names_the_changed_field(committed, rebuilt):
    tampered = copy.deepcopy(committed["phoenix_northwest"])
    tampered["trend"]["p"] = round(tampered["trend"]["p"], 4)  # a rounded p is not the result
    diffs = ai_release.rebuild_differences(tampered, rebuilt.results["phoenix_northwest"])
    assert diffs == ["trend"]


def test_ai_text_is_not_required_to_be_reproduced_offline(committed, rebuilt):
    # Approved AI text cannot be regenerated without Gemini, so only its explanation fields
    # are exempt from the byte-for-byte comparison; every number must still match.
    with_ai = copy.deepcopy(committed["phoenix_southeast"])
    with_ai["explanation"] = "Some approved Gemini text about Phoenix southeast."
    with_ai["explanation_source"] = "ai"
    assert ai_release.rebuild_differences(with_ai, rebuilt.results["phoenix_southeast"]) == []
    with_ai["trend"]["slope"] *= 2
    assert ai_release.rebuild_differences(
        with_ai, rebuilt.results["phoenix_southeast"]) == ["trend"]


# --- explanation provenance -------------------------------------------------------------

def test_every_committed_explanation_belongs_to_its_result(committed):
    for region_id in REGION_IDS:
        assert ai_release.explanation_problems(committed[region_id]) == [], region_id


def test_fallback_text_must_be_exactly_what_its_numbers_produce(committed):
    stale = copy.deepcopy(committed["phoenix_northeast"])
    stale["trend"]["slope"] = stale["trend"]["slope"] * 1.5  # text left from an older result
    problems = ai_release.explanation_problems(stale)
    assert any("does not match the fallback" in p for p in problems)


def test_explanation_from_another_region_is_rejected(committed):
    swapped = copy.deepcopy(committed["phoenix_northeast"])
    swapped["explanation"] = committed["phoenix_southwest"]["explanation"]
    assert ai_release.explanation_problems(swapped)


def test_ai_text_must_pass_checks_and_name_its_region(committed):
    result = copy.deepcopy(committed["phoenix_northwest"])
    result["explanation_source"] = "ai"
    result["explanation"] = ("Nighttime land surface temperature rose by about 0.00755 degC "
                             "per month from 2003-01 to 2024-12 (p < 0.001).")
    problems = ai_release.explanation_problems(result)
    assert any("does not name the selected region" in p for p in problems)

    result["explanation"] = ("In the northwest box of the Phoenix study area, nighttime land "
                             "surface temperature rose by about 0.00755 degC per month from "
                             "2003-01 to 2024-12. This is statistically significant "
                             "(p < 0.001). 1 of 264 months is missing and was left as a gap.")
    assert ai_release.explanation_problems(result) == []

    result["explanation"] += " Cities will get hotter because of urban growth."
    assert ai_release.explanation_problems(result)


def test_unknown_explanation_source_is_rejected(committed):
    result = copy.deepcopy(committed["phoenix_study_area"])
    result["explanation_source"] = "manual"
    assert any("explanation_source" in p for p in ai_release.explanation_problems(result))


# --- AI off and network blocked ---------------------------------------------------------

def test_ai_off_forces_fallback_even_with_a_key_and_live_switch(monkeypatch, committed):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-flash")
    monkeypatch.setenv("GEMINI_LIVE", "1")
    draft = {k: v for k, v in committed["phoenix_northwest"].items()
             if k not in ("explanation", "explanation_source")}
    with ai_release.ai_off():
        answer = ai_explain.explain(draft)
    assert answer["source"] == "fallback"
    # the caller's environment is restored afterwards
    import os
    assert os.environ["GEMINI_API_KEY"] == "test-only-key"
    assert os.environ["GEMINI_LIVE"] == "1"


def test_no_network_blocks_and_counts_connections():
    with ai_release.no_network() as attempts:
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", 9), timeout=1)
        with pytest.raises(OSError):
            socket.socket().connect(("127.0.0.1", 9))
    assert len(attempts) == 2
    assert socket.socket.connect is not None  # restored (a real call would no longer raise ours)


# --- runtime isolation ------------------------------------------------------------------

def test_demo_runtime_cannot_reach_the_ai_layer_or_gemini():
    report = ai_release.runtime_isolation(ROOT)
    assert report["violations"] == []
    scanned = set(report["scanned"])
    for module in ("app/streamlit_app.py", "app/api_client.py",
                   "src/earth_system_trend/api/app.py", "src/earth_system_trend/api/routes.py",
                   "scripts/backup_run.py"):
        assert module in scanned


def test_isolation_follows_imports_into_the_package(tmp_path):
    pkg = tmp_path / "src" / "earth_system_trend"
    (pkg / "api").mkdir(parents=True)
    (pkg / "ai").mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "ai" / "__init__.py").write_text("")
    (pkg / "ai" / "explain.py").write_text("import openai\n")
    (pkg / "api" / "__init__.py").write_text("")
    (pkg / "api" / "app.py").write_text("from .helper import x\n")
    (pkg / "api" / "helper.py").write_text("from ..ai.explain import explain\nx = 1\n")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "streamlit_app.py").write_text("import view\n")
    (tmp_path / "app" / "view.py").write_text("from openai import OpenAI\n")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "backup_run.py").write_text("import requests\n")

    report = ai_release.runtime_isolation(tmp_path)
    found = {(v["module"], v["import"]) for v in report["violations"]}
    assert ("src/earth_system_trend/api/helper.py", "earth_system_trend.ai.explain") in found
    assert ("app/view.py", "openai") in found
    assert "src/earth_system_trend/ai/explain.py" not in report["scanned"]  # stopped at the edge


# --- the whole check and its evidence ---------------------------------------------------

def test_release_check_passes_on_the_committed_results():
    report = ai_release.release_check(ROOT)
    assert report["status"] == "PASS", report
    assert report["network_attempts"] == 0
    assert report["ai_mode"].startswith("off")
    assert report["prompt_version"] == ai_explain.PROMPT_VERSION
    assert {r["region_id"] for r in report["regions"]} == set(REGION_IDS)
    assert all(r["passed"] for r in report["regions"])
    assert report["explanation_sources"] == {"fallback": 5}


def test_script_writes_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "sentinel-key-must-not-leak")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "verify_ai_release", ROOT / "scripts" / "verify_ai_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = tmp_path / "check.json"
    assert module.main(["--root", str(ROOT), "--out", str(out)]) == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["status"] == "PASS"
    assert saved["result_sha256"] == ai_release.result_hashes(ROOT)
    assert "sentinel-key-must-not-leak" not in out.read_text(encoding="utf-8")


def test_committed_evidence_describes_the_committed_results():
    """If any results file changes, re-run scripts/verify_ai_release.py and commit the output."""
    saved = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert saved["status"] == "PASS"
    assert saved["result_sha256"] == ai_release.result_hashes(ROOT)
