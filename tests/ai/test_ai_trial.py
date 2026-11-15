"""A9: explain_detailed() and the live-trial tool, with Gemini mocked. No real request is made."""

import hashlib
import json
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from earth_system_trend.ai import ai_setup, ai_trial
from earth_system_trend.ai.explain import explain, explain_detailed, fallback_text

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]
STUDY = ROOT / "results" / "results.json"
FILES = sorted([STUDY, *(ROOT / "results" / "regions").glob("*.json")])
SECRET = "test-only-key"


def load(path=STUDY):
    data = json.loads(Path(path).read_text())
    data.pop("explanation", None)
    data.pop("explanation_source", None)
    return data


RESULTS = load()
GOOD = ("From 2003-01 to 2024-12, nighttime land surface temperature in the Phoenix study area "
        "rose by about 0.00771 degC per month (0.0926 degC per year). This is statistically "
        "significant (p < 0.001).")
BAD = "Temperatures soared 4.2 degC per year because of asphalt."
# No numbers or place names: valid for every region (all five are increasing, p < 0.001).
GENERIC = "Nighttime land surface temperature is rising; this is statistically significant."


@pytest.fixture
def gemini(monkeypatch):
    def install(*replies, model="test-flash"):
        script = list(replies)
        requests = []

        def respond(request):
            requests.append(request)
            item = script.pop(0) if script else GENERIC
            if isinstance(item, httpx.Response):
                return item
            return httpx.Response(200, json={
                "id": "x", "object": "chat.completion", "created": 0, "model": model,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": item}}],
            })

        monkeypatch.setattr(ai_setup, "OpenAI", lambda **kw: OpenAI(
            http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kw))
        monkeypatch.setenv("GEMINI_API_KEY", SECRET)
        monkeypatch.setenv("GEMINI_MODEL", model)
        return requests

    return install


def detailed(results=RESULTS, **kw):
    return explain_detailed(results, sleep=lambda _: None, **kw)


# --- explain_detailed -------------------------------------------------------------------

def test_accepted_reply_details(gemini):
    gemini(GOOD)
    out = detailed()
    assert (out.text, out.source, out.reason) == (GOOD, "ai", "accepted")
    assert out.reply == GOOD and out.problems == ()


def test_rejected_reply_keeps_the_reply_and_reasons(gemini):
    gemini(BAD)
    out = detailed()
    assert out.source == "fallback" and out.text == fallback_text(RESULTS)
    assert out.reason == "rejected by checks"
    assert out.reply == BAD
    assert any("cause" in p for p in out.problems) and any("number" in p for p in out.problems)


def test_cached_reply_is_reported_as_cached(gemini):
    requests = gemini(GOOD)
    detailed()
    out = detailed()
    assert (out.source, out.reason, len(requests)) == ("ai", "cached", 1)


def test_use_cache_false_asks_again_and_still_stores(gemini):
    requests = gemini(GOOD, GOOD)
    detailed()
    out = detailed(use_cache=False)
    assert (out.reason, len(requests)) == ("accepted", 2)
    assert detailed().reason == "cached"


def test_no_key_reason():
    out = detailed()
    assert (out.source, out.reply) == ("fallback", None)
    assert "GEMINI_API_KEY" in out.reason


def test_unavailable_reason(gemini):
    gemini(*[httpx.Response(503)] * 3)
    out = detailed()
    assert out.source == "fallback" and "unavailable" in out.reason.lower()


def test_empty_reply_reason(gemini):
    gemini("   ")
    assert detailed().reason == "no text"


def test_incomplete_results_reason():
    assert detailed({}).reason == "results incomplete"


def test_explain_still_returns_only_text_and_source(gemini):
    gemini(GOOD)
    assert explain(RESULTS, sleep=lambda _: None) == {"text": GOOD, "source": "ai"}


# --- trial tool -------------------------------------------------------------------------

def hashes():
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in FILES}


def test_trial_refuses_without_key_and_makes_no_request(capsys, tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(ai_setup, "OpenAI", lambda **kw: called.append(kw))
    assert ai_trial.main(["--report", str(tmp_path / "r.json")]) == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().out
    assert called == [] and not (tmp_path / "r.json").exists()


def test_trial_refuses_without_model(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    assert ai_trial.main(["--report", str(tmp_path / "r.json")]) == 2
    assert "GEMINI_MODEL" in capsys.readouterr().out


def test_trial_reports_every_region_and_never_touches_results(gemini, capsys, tmp_path):
    before = hashes()
    requests = gemini(GOOD, BAD, BAD, BAD, BAD)  # study area first, then the four boxes
    report_path = tmp_path / "report.json"
    assert ai_trial.main(["--report", str(report_path)]) == 0
    assert hashes() == before  # results files untouched
    assert len(requests) == 5
    report = json.loads(report_path.read_text())
    assert report["model"] == "test-flash" and report["prompt_version"] == "v1"
    assert report["total"] == 5 and report["accepted"] == 1
    by_id = {r["region_id"]: r for r in report["regions"]}
    assert by_id["phoenix_study_area"]["source"] == "ai"
    assert by_id["phoenix_northwest"]["reason"] == "rejected by checks"
    assert by_id["phoenix_northwest"]["reply"] == BAD and by_id["phoenix_northwest"]["problems"]
    out = capsys.readouterr().out
    assert "1 of 5 accepted" in out and "REJECTED" in out and "ACCEPTED" in out
    assert SECRET not in report_path.read_text() and SECRET not in out


def test_trial_uses_cache_unless_fresh(gemini, tmp_path):
    requests = gemini()
    ai_trial.main(["--report", str(tmp_path / "a.json")])
    ai_trial.main(["--report", str(tmp_path / "b.json")])
    assert len(requests) == 5  # second run: all cached
    assert {r["reason"] for r in json.loads((tmp_path / "b.json").read_text())["regions"]} == \
        {"cached"}
    ai_trial.main(["--fresh", "--report", str(tmp_path / "c.json")])
    assert len(requests) == 10


def test_trial_respects_the_daily_cap(gemini, tmp_path, monkeypatch):
    monkeypatch.setenv("AI_DAILY_CALL_CAP", "0")
    requests = gemini()
    assert ai_trial.main(["--report", str(tmp_path / "r.json")]) == 0
    assert requests == []
    report = json.loads((tmp_path / "r.json").read_text())
    assert report["accepted"] == 0
    assert all("cap" in r["reason"] for r in report["regions"])


def test_trial_can_run_one_region(gemini, tmp_path):
    requests = gemini()
    ai_trial.main(["--region", "phoenix_southeast", "--report", str(tmp_path / "r.json")])
    report = json.loads((tmp_path / "r.json").read_text())
    assert [r["region_id"] for r in report["regions"]] == ["phoenix_southeast"]
    assert len(requests) == 1


def test_unknown_region_is_an_error(gemini, tmp_path, capsys):
    gemini()
    assert ai_trial.main(["--region", "tucson", "--report", str(tmp_path / "r.json")]) == 2
    assert "tucson" in capsys.readouterr().out


def test_default_report_path_is_git_ignored():
    import subprocess
    out = subprocess.run(["git", "check-ignore", ai_trial.DEFAULT_REPORT], cwd=ROOT,
                         capture_output=True, text=True, check=False)
    assert out.returncode == 0
