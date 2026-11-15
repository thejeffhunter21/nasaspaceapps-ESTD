"""Shared test setup. Tests never call OpenAI, Gemini or NASA."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_services(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # config.py loads .env, so a developer's real Gemini key could otherwise reach a test.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_LIVE", raising=False)  # live AI calls are opt-in
    # Never read or write the real explanation cache / daily call counter.
    monkeypatch.setenv("EXPLAIN_CACHE_PATH", str(tmp_path / "ai_cache" / "explanations.json"))
    monkeypatch.delenv("AI_DAILY_CALL_CAP", raising=False)
    # J12: no rate limit in tests unless a test sets one.
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
