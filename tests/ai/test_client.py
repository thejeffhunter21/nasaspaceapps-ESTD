"""A1: exercise the real SDK against an in-memory HTTP transport."""

import json
import traceback

import httpx
import pytest
from openai import APIStatusError, OpenAI

from earth_system_trend.ai import ai_setup

pytestmark = pytest.mark.unit
MESSAGES = [{"role": "user", "content": "Phrase only the supplied facts."}]


@pytest.fixture(autouse=True)
def clean_gemini_env(monkeypatch):
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def transport(monkeypatch):
    """Replace only HTTP; retain SDK serialization and status handling."""
    clients = []
    requests = []

    def install(status=200):
        def respond(request):
            requests.append(request)
            if status != 200:
                return httpx.Response(status, json={"error": {"message": "test-only-key"}})
            return httpx.Response(200, json={
                "id": "offline-completion", "object": "chat.completion", "created": 0,
                "model": "test-flash", "choices": [{
                    "index": 0, "message": {"role": "assistant", "content": "Verified facts."},
                    "finish_reason": "stop",
                }],
            })

        def sdk(**kwargs):
            client = OpenAI(http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kwargs)
            clients.append(client)
            return client

        monkeypatch.setattr(ai_setup, "OpenAI", sdk)
        return requests

    yield install
    for client in clients:
        client.close()


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_gemini_key_disables_client_even_with_openai_key(monkeypatch, transport, key):
    requests = transport()
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-openai-key")
    if key is not None:
        monkeypatch.setenv("GEMINI_API_KEY", key)
    assert ai_setup.build_client() is None
    assert requests == []


@pytest.mark.parametrize("model", [None, "", "   "])
def test_key_requires_explicit_model_without_network(monkeypatch, transport, model):
    requests = transport()
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    if model is not None:
        monkeypatch.setenv("GEMINI_MODEL", model)
    with pytest.raises(ai_setup.GeminiSetupError, match="GEMINI_MODEL"):
        ai_setup.build_client()
    assert requests == []


def test_request_uses_gemini_key_model_endpoint_and_low_reasoning(monkeypatch, transport):
    requests = transport()
    monkeypatch.setenv("GEMINI_API_KEY", " test-only-key ")
    monkeypatch.setenv("GEMINI_MODEL", " test-flash ")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unrelated.example/")
    client = ai_setup.build_client()
    assert requests == []  # construction must not make a paid probe
    reply = client.complete(MESSAGES)
    assert reply.choices[0].message.content == "Verified facts."
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert request.headers["authorization"] == "Bearer test-only-key"
    assert json.loads(request.content) == {
        "model": "test-flash", "messages": MESSAGES, "reasoning_effort": "low",
    }
    assert "test-only-key" not in repr(client)


def test_404_is_a_clear_setup_error_without_retry_or_secret(monkeypatch, transport, caplog):
    requests = transport(404)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    monkeypatch.setenv("GEMINI_MODEL", "unknown-model")
    with pytest.raises(ai_setup.GeminiSetupError) as caught:
        ai_setup.build_client().complete(MESSAGES)
    assert len(requests) == 1
    assert "404" in str(caught.value)
    assert "GEMINI_MODEL" in str(caught.value)
    assert "endpoint" in str(caught.value).lower()
    assert "test-only-key" not in "".join(traceback.format_exception(caught.value))
    assert "test-only-key" not in caplog.text


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_other_http_errors_remain_available_to_later_fallback_layer(monkeypatch, transport, status):
    requests = transport(status)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-flash")
    with pytest.raises(APIStatusError) as caught:
        ai_setup.build_client().complete(MESSAGES)
    assert caught.value.status_code == status
    assert len(requests) == 1  # A2 will own retry policy, not the SDK
