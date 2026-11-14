"""Shared test setup. Tests never call OpenAI or NASA."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_services(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
