"""A10: Gemini is called only when live calls are switched on (GEMINI_LIVE or allow_live=True).

A key in the environment is not enough. Approved replies in the cache are still reused.
"""

import json
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from earth_system_trend.ai import ai_setup
from earth_system_trend.ai.explain import explain_detailed, fallback_text, live_calls_enabled
from earth_system_trend.contract import load_results
from earth_system_trend.pipeline import run as pipeline

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]
RESULTS = json.loads((ROOT / "results" / "results.json").read_text())
GOOD = ("In the Phoenix study area, nighttime land surface temperature rose by about 0.00771 "
        "degC per month (0.0926 degC per year); statistically significant (p < 0.001).")


@pytest.fixture
def key_and_mock(monkeypatch):
    """Key and model set, Gemini mocked - but GEMINI_LIVE left unset."""
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "test-flash",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": GOOD}}],
        })

    monkeypatch.setattr(ai_setup, "OpenAI", lambda **kw: OpenAI(
        http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kw))
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-flash")
    return requests


def detailed(**kw):
    return explain_detailed(RESULTS, sleep=lambda _: None, **kw)


def test_tests_start_with_live_calls_off():
    assert not live_calls_enabled()


def test_key_alone_does_not_call_gemini(key_and_mock):
    out = detailed()
    assert key_and_mock == []
    assert out.source == "fallback" and out.text == fallback_text(RESULTS)
    assert "GEMINI_LIVE" in out.reason


@pytest.mark.parametrize("value, on", [
    ("1", True), ("true", True), ("YES", True), ("on", True),
    ("0", False), ("false", False), ("", False), ("maybe", False),
])
def test_switch_values(monkeypatch, value, on):
    monkeypatch.setenv("GEMINI_LIVE", value)
    assert live_calls_enabled() is on


def test_switch_on_calls_gemini(key_and_mock, monkeypatch):
    monkeypatch.setenv("GEMINI_LIVE", "1")
    assert detailed().source == "ai"
    assert len(key_and_mock) == 1


def test_allow_live_argument_overrides_the_environment(key_and_mock):
    assert detailed(allow_live=True).source == "ai"
    assert len(key_and_mock) == 1


def test_allow_live_false_blocks_even_when_switched_on(key_and_mock, monkeypatch):
    monkeypatch.setenv("GEMINI_LIVE", "1")
    assert detailed(allow_live=False).source == "fallback"
    assert key_and_mock == []


def test_cached_reply_is_used_with_live_calls_off(key_and_mock):
    detailed(allow_live=True)  # approved and cached
    out = detailed()  # live off
    assert (out.source, out.reason, out.text) == ("ai", "cached", GOOD)
    assert len(key_and_mock) == 1


def test_pipeline_does_not_call_gemini_without_the_switch(key_and_mock, tmp_path):
    out = tmp_path / "results.json"
    assert pipeline.main(["--stub", "--csv", str(tmp_path / "t.csv"), "--out", str(out)]) == 0
    assert key_and_mock == []
    assert load_results(out).explanation_source == "fallback"
