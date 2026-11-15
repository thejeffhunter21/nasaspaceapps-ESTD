"""A6: explanation cache and daily call cap, exercised through explain() with mocked HTTP."""

import json
import os
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from earth_system_trend.ai import ai_cache, ai_setup
from earth_system_trend.ai import explain as explain_mod
from earth_system_trend.ai.ai_cache import DEFAULT_DAILY_CAP, ExplanationStore, cache_key
from earth_system_trend.ai.explain import build_messages, explain, fallback_text

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]
SECRET = "test-only-key"


def load(name="results.json"):
    path = ROOT / "results" / name if name == "results.json" else ROOT / "results" / "regions" / name
    data = json.loads(path.read_text())
    data.pop("explanation", None)
    data.pop("explanation_source", None)
    return data


RESULTS = load()
OTHER = load("phoenix_southeast.json")
GOOD = ("From 2003-01 to 2024-12, nighttime land surface temperature in the Phoenix study area "
        "rose by about 0.00771 degC per month (0.0926 degC per year). The increase is "
        "statistically significant (p < 0.001).")
GOOD_SE = ("Nighttime land surface temperature in Phoenix southeast rose by about 0.00889 degC "
           "per month from 2003-01 to 2024-12; this is statistically significant (p < 0.001).")


def completion(content):
    return httpx.Response(200, json={
        "id": "x", "object": "chat.completion", "created": 0, "model": "test-flash",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": content}}],
    })


@pytest.fixture
def gemini(monkeypatch):
    """AI on, answers scripted. Returns the list of requests sent after this install."""

    def install(*outcomes, key=True):
        script = list(outcomes)
        requests = []

        def respond(request):
            requests.append(request)
            outcome = script.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(ai_setup, "OpenAI", lambda **kw: OpenAI(
            http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kw))
        if key:
            monkeypatch.setenv("GEMINI_API_KEY", SECRET)
        else:
            monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_MODEL", "test-flash")
        return requests

    return install


def run(results=RESULTS):
    return explain(results, sleep=lambda _: None)


def cache_file():
    return Path(os.environ["EXPLAIN_CACHE_PATH"])


# --- cache ------------------------------------------------------------------------------

def test_second_call_with_same_results_uses_cache_without_a_request(gemini):
    requests = gemini(completion(GOOD))
    assert run() == {"text": GOOD, "source": "ai"}
    assert run() == {"text": GOOD, "source": "ai"}
    assert len(requests) == 1


def test_different_results_are_a_cache_miss(gemini):
    requests = gemini(completion(GOOD), completion(GOOD_SE))
    assert run(RESULTS)["text"] == GOOD
    assert run(OTHER)["text"] == GOOD_SE
    assert len(requests) == 2


def test_cache_key_depends_on_prompt_version_and_facts():
    messages = build_messages(RESULTS)
    key = cache_key(messages, "v1")
    assert key == cache_key(build_messages(RESULTS), "v1")
    assert key != cache_key(build_messages(OTHER), "v1")
    assert key != cache_key(messages, "v2")


def test_cached_text_is_reused_offline_without_a_key(gemini):
    gemini(completion(GOOD))
    run()
    requests = gemini(key=False)
    assert run() == {"text": GOOD, "source": "ai"}
    assert requests == []


def test_cached_text_is_rechecked_and_dropped_if_it_no_longer_passes(gemini, monkeypatch):
    gemini(completion(GOOD))
    run()
    monkeypatch.setattr(explain_mod, "check_explanation",
                        lambda text, results: type("R", (), {"ok": False, "problems": ("x",)})())
    requests = gemini(completion(GOOD))
    assert run()["source"] == "fallback"
    assert len(requests) == 1  # stale entry ignored, model asked again


@pytest.mark.parametrize("outcomes", [
    [completion("It rose 3.5 degC per year; significant.")],  # rejected by checks
    [httpx.Response(503)] * 3,  # Gemini unavailable
    [completion("")],  # empty
])
def test_only_checked_ai_text_is_cached(gemini, outcomes):
    gemini(*outcomes)
    assert run()["source"] == "fallback"
    assert not cache_file().exists() or json.loads(cache_file().read_text())["explanations"] == {}


def test_cache_file_records_metadata_and_never_the_key(gemini):
    gemini(completion(GOOD))
    run()
    data = json.loads(cache_file().read_text())
    (entry,) = data["explanations"].values()
    assert entry["text"] == GOOD
    assert entry["prompt_version"] == "v1"
    assert entry["model"] == "test-flash"
    assert entry["created"]
    assert SECRET not in cache_file().read_text()


@pytest.mark.parametrize("content", ["{not json", "[]", '{"explanations": 5}'])
def test_corrupt_cache_file_is_ignored_and_rewritten(gemini, caplog, content):
    cache_file().parent.mkdir(parents=True, exist_ok=True)
    cache_file().write_text(content)
    requests = gemini(completion(GOOD))
    with caplog.at_level("WARNING"):
        assert run()["source"] == "ai"
    assert len(requests) == 1
    assert "cache" in caplog.text.lower()
    assert json.loads(cache_file().read_text())["explanations"]


def test_unwritable_cache_never_breaks_explain(gemini, monkeypatch, tmp_path, caplog):
    blocker = tmp_path / "a_file"
    blocker.write_text("x")
    monkeypatch.setenv("EXPLAIN_CACHE_PATH", str(blocker / "explanations.json"))
    gemini(completion(GOOD))
    with caplog.at_level("WARNING"):
        assert run() == {"text": GOOD, "source": "ai"}
    assert "cache" in caplog.text.lower()


# --- daily call cap ---------------------------------------------------------------------

def test_default_cap(monkeypatch):
    assert ExplanationStore(cache_file()).daily_cap() == DEFAULT_DAILY_CAP == 50


@pytest.mark.parametrize("value, expected", [("7", 7), ("0", 0), ("-3", 50), ("lots", 50)])
def test_cap_setting_is_read_safely(monkeypatch, value, expected):
    monkeypatch.setenv("AI_DAILY_CALL_CAP", value)
    assert ExplanationStore(cache_file()).daily_cap() == expected


def test_cap_counts_every_request_including_retries(gemini, monkeypatch, caplog):
    monkeypatch.setenv("AI_DAILY_CALL_CAP", "2")
    requests = gemini(httpx.Response(503), httpx.Response(503), completion(GOOD))
    with caplog.at_level("WARNING"):
        assert run()["source"] == "fallback"
    assert len(requests) == 2  # the third attempt was not sent
    assert "cap" in caplog.text.lower()


def test_cap_reached_blocks_new_requests_but_not_cached_text(gemini, monkeypatch):
    monkeypatch.setenv("AI_DAILY_CALL_CAP", "1")
    requests = gemini(completion(GOOD), completion(GOOD_SE))
    assert run(RESULTS)["source"] == "ai"
    assert run(OTHER)["source"] == "fallback"  # would need a second request
    assert run(RESULTS)["source"] == "ai"  # cache hit costs nothing
    assert len(requests) == 1


def test_cap_zero_turns_ai_off(gemini, monkeypatch):
    monkeypatch.setenv("AI_DAILY_CALL_CAP", "0")
    requests = gemini(completion(GOOD))
    assert run() == {"text": fallback_text(RESULTS), "source": "fallback"}
    assert requests == []


def test_count_persists_across_runs_and_resets_on_a_new_utc_day(gemini, monkeypatch):
    monkeypatch.setenv("AI_DAILY_CALL_CAP", "1")
    monkeypatch.setattr(ai_cache, "_today", lambda: "2026-11-14")
    requests = gemini(completion(GOOD), completion(GOOD_SE))
    run(RESULTS)
    assert json.loads(cache_file().read_text())["usage"] == {"date": "2026-11-14", "calls": 1}
    assert run(OTHER)["source"] == "fallback"
    monkeypatch.setattr(ai_cache, "_today", lambda: "2026-11-15")
    assert run(OTHER)["source"] == "ai"
    assert len(requests) == 2
    assert json.loads(cache_file().read_text())["usage"] == {"date": "2026-11-15", "calls": 1}


def test_requests_are_counted_even_when_they_fail(gemini, monkeypatch):
    monkeypatch.setattr(ai_cache, "_today", lambda: "2026-11-14")
    gemini(httpx.Response(503), httpx.Response(503), httpx.Response(503))
    run()
    assert json.loads(cache_file().read_text())["usage"]["calls"] == 3


def test_tests_never_write_the_real_cache(gemini):
    """During tests the cache resolves to a temp folder; the real file (which may exist from a
    local pipeline or trial run) is never read or written."""
    real = ROOT / ai_cache.DEFAULT_CACHE_PATH
    before = real.read_bytes() if real.exists() else None
    assert ExplanationStore.from_env().path.resolve() != real.resolve()
    assert "ai_cache" in os.environ["EXPLAIN_CACHE_PATH"]
    gemini(completion(GOOD))
    run()  # writes an approved reply to the cache
    assert cache_file().exists()  # ...in the temp folder
    assert (real.read_bytes() if real.exists() else None) == before
