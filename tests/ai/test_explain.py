"""A4: explain() joins A1 (client), A2 (retries) and A3 (checks). Never raises.

HTTP is replaced by httpx.MockTransport; no test reaches the real Gemini API.
"""

import copy
import json
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from earth_system_trend.ai import ai_setup
from earth_system_trend.ai import explain as explain_mod
from earth_system_trend.ai.ai_checks import check_explanation
from earth_system_trend.ai.explain import (
    FALLBACK_UNAVAILABLE,
    PROMPT_VERSION,
    build_messages,
    explain,
    fallback_text,
    p_text,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]
RESULT_FILES = sorted([ROOT / "results" / "results.json", *(ROOT / "results" / "regions").glob("*.json")])
SECRET = "test-only-key"


STUDY_AREA = ROOT / "results" / "results.json"


def load(path=STUDY_AREA):
    data = json.loads(Path(path).read_text())
    data.pop("explanation", None)
    data.pop("explanation_source", None)
    return data


def variant(**trend):
    results = load()
    results["trend"].update(trend)
    return results


RESULTS = load()  # study area: slope about 0.00771 degC/month, p about 7e-11, increasing
GOOD_REPLY = (
    "From 2003-01 to 2024-12, nighttime land surface temperature in the Phoenix study area rose "
    "by about 0.00771 degC per month (0.0926 degC per year). The increase is statistically "
    "significant (p < 0.001)."
)


def completion(content):
    return httpx.Response(200, json={
        "id": "offline", "object": "chat.completion", "created": 0, "model": "test-flash",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": content}}],
    })


@pytest.fixture(autouse=True)
def no_gemini_env(monkeypatch):
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def gemini(monkeypatch):
    """Turn AI on with a scripted HTTP transport. Returns the list of requests made."""
    state = {"requests": [], "closed": 0}

    def install(*outcomes):
        script = list(outcomes)

        def respond(request):
            state["requests"].append(request)
            outcome = script.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        class TrackedOpenAI(OpenAI):
            def close(self):
                state["closed"] += 1
                super().close()

        def sdk(**kwargs):
            return TrackedOpenAI(
                http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kwargs)

        monkeypatch.setattr(ai_setup, "OpenAI", sdk)
        monkeypatch.setenv("GEMINI_API_KEY", SECRET)
        monkeypatch.setenv("GEMINI_MODEL", "test-flash")
        return state

    return install


def run(results=RESULTS):
    return explain(results, sleep=lambda _: None)


def sent_messages(state):
    return json.loads(state["requests"][0].content)["messages"]


# --- AI path ----------------------------------------------------------------------------

def test_checked_ai_reply_is_returned_as_ai(gemini):
    state = gemini(completion(f"  {GOOD_REPLY}\n"))
    assert run() == {"text": GOOD_REPLY, "source": "ai"}
    assert len(state["requests"]) == 1
    assert state["closed"] == 1  # the client built for this call is released


def test_prompt_carries_preformatted_facts_and_rules(gemini):
    state = gemini(completion(GOOD_REPLY))
    run()
    system, user = sent_messages(state)
    assert system["role"] == "system" and user["role"] == "user"
    for rule in ("only the numbers", "cause", "forecast", "advice", "air temperature", "plain text"):
        assert rule in system["content"].lower()
    facts = user["content"]
    for fact in ("Phoenix study area", "2003-01", "2024-12", "0.00771 degC/month",
                 "0.0926 degC/year", "p < 0.001", "Statistically significant: yes",
                 "Direction: increasing", "Seasonal Mann-Kendall"):
        assert fact in facts


def test_every_number_in_the_prompt_facts_passes_the_checks():
    """Anything the model copies from the facts block must be accepted by A3."""
    for path in RESULT_FILES:
        results = load(path)
        facts = build_messages(results)[1]["content"]
        problems = check_explanation(facts, results).problems
        assert not [p for p in problems if p.startswith(("number", "date"))], (path.name, problems)


@pytest.mark.parametrize("bad_reply, reason", [
    ("Temperatures rose 3.5 degC per year, a significant increase.", "number"),
    ("It rose because of urban growth; significant (p < 0.001).", "cause"),
    ("It is rising and will keep rising; significant.", "forecast"),
    ("**Rising**, but not statistically significant.", "significance"),
])
def test_reply_failing_checks_falls_back_and_logs_why(gemini, caplog, bad_reply, reason):
    gemini(completion(bad_reply))
    with caplog.at_level("WARNING", logger=explain_mod.__name__):
        answer = run()
    assert answer == {"text": fallback_text(RESULTS), "source": "fallback"}
    assert "rejected" in caplog.text and reason in caplog.text


@pytest.mark.parametrize("content", [None, "", "   "])
def test_empty_reply_falls_back(gemini, content):
    gemini(completion(content))
    assert run()["source"] == "fallback"


def test_reply_without_choices_falls_back(gemini):
    gemini(httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0,
                                     "model": "test-flash", "choices": []}))
    assert run()["source"] == "fallback"


# --- failures never raise ---------------------------------------------------------------

def test_no_key_uses_fallback_without_any_request(monkeypatch):
    called = []
    monkeypatch.setattr(ai_setup, "OpenAI", lambda **kw: called.append(kw))
    assert run() == {"text": fallback_text(RESULTS), "source": "fallback"}
    assert called == []


def test_key_without_model_is_logged_and_falls_back(monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    with caplog.at_level("ERROR", logger=explain_mod.__name__):
        assert run()["source"] == "fallback"
    assert "GEMINI_MODEL" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("outcomes", [
    [httpx.Response(503, json={"error": {"message": SECRET}})] * 3,
    [httpx.ReadTimeout("slow")] * 3,
    [httpx.Response(401, json={"error": {"message": SECRET}})],
    [httpx.Response(404, json={"error": {"message": SECRET}})],
    [httpx.Response(400, json={"error": {"message": SECRET}})],
])
def test_gemini_failures_fall_back_without_leaking(gemini, caplog, outcomes):
    state = gemini(*outcomes)
    with caplog.at_level("WARNING"):
        answer = run()
    assert answer["source"] == "fallback"
    assert len(state["requests"]) == len(outcomes)
    assert state["closed"] == 1
    assert SECRET not in caplog.text


def test_retry_then_success_is_ai(gemini):
    state = gemini(httpx.Response(503), completion(GOOD_REPLY))
    assert run()["source"] == "ai"
    assert len(state["requests"]) == 2


@pytest.mark.parametrize("results", [None, {}, {"trend": {}}, {"region": "x"}])
def test_malformed_results_never_raise_and_skip_the_model(gemini, results):
    state = gemini(completion(GOOD_REPLY))
    assert run(results) == {"text": FALLBACK_UNAVAILABLE, "source": "fallback"}
    assert state["requests"] == []


def test_unexpected_error_inside_explain_is_contained(gemini, monkeypatch):
    gemini(completion(GOOD_REPLY))
    monkeypatch.setattr(explain_mod, "check_explanation", lambda *a: 1 / 0)
    assert run()["source"] == "fallback"


def test_input_is_not_modified(gemini):
    gemini(completion(GOOD_REPLY))
    before = copy.deepcopy(RESULTS)
    run(RESULTS)
    assert RESULTS == before


# --- fallback text ----------------------------------------------------------------------

@pytest.mark.parametrize("path", RESULT_FILES, ids=lambda p: p.stem)
def test_fallback_passes_checks_on_every_real_results_file(path):
    results = load(path)
    text = fallback_text(results)
    assert check_explanation(text, results).ok, check_explanation(text, results).problems
    assert "degC per month" in text and "p < 0.001" in text


def test_fallback_mentions_missing_months_when_there_are_gaps():
    results = load(ROOT / "results" / "regions" / "phoenix_southeast.json")
    assert "3 of 264 months" in fallback_text(results)
    assert "missing" not in fallback_text(RESULTS)  # study area has no gaps


@pytest.mark.parametrize("trend, word", [
    ({"slope": -0.004, "p": 0.002, "tau": -0.21, "trend": "decreasing"}, "fell"),
    ({"slope": 0.0011, "p": 0.05, "tau": 0.03, "trend": "no trend"}, "not statistically significant"),
    ({"slope": 0.0011, "p": 0.31, "tau": 0.03, "trend": "no trend"}, "not proof of no change"),
])
def test_fallback_wording_matches_each_outcome_and_passes_checks(trend, word):
    results = variant(**trend)
    text = fallback_text(results)
    assert word in text
    assert check_explanation(text, results).ok, check_explanation(text, results).problems


@pytest.mark.parametrize("results", [None, {}, {"trend": {"slope": "x"}}])
def test_fallback_never_raises(results):
    assert fallback_text(results) == FALLBACK_UNAVAILABLE


@pytest.mark.parametrize("p, expected", [
    (0.0, "p < 0.001"), (4e-06, "p < 0.001"), (0.0123, "p = 0.0123"), (0.31, "p = 0.31"),
    (0.0499996, "p = 0.0499996"),  # rounding to 0.05 would contradict "significant"
    (0.05, "p = 0.05"),
])
def test_p_text(p, expected):
    assert p_text(p) == expected


def test_prompt_is_versioned_file():
    assert PROMPT_VERSION == "v1"
    prompt = ROOT / "src" / "earth_system_trend" / "ai" / "prompts" / "explain_v1.txt"
    assert prompt.is_file()
    assert build_messages(RESULTS)[0]["content"] == prompt.read_text(encoding="utf-8").strip()
