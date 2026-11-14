"""AI tests: keep the explanation cache and call counter in a temp folder, never in the repo."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_ai_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("EXPLAIN_CACHE_PATH", str(tmp_path / "ai_cache" / "explanations.json"))
    monkeypatch.delenv("AI_DAILY_CALL_CAP", raising=False)
