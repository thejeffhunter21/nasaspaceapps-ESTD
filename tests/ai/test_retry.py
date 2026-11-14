"""A2: retry policy around GeminiClient.complete(), exercised through the real SDK.

Only HTTP is replaced (httpx.MockTransport). Sleeping is injected, so no test waits.
"""

import traceback

import httpx
import pytest
from openai import OpenAI

from earth_system_trend.ai import ai_retry, ai_setup
from earth_system_trend.ai.ai_retry import GeminiUnavailableError, RetryPolicy, complete_with_retry
from earth_system_trend.ai.ai_setup import GeminiSetupError

pytestmark = pytest.mark.unit
MESSAGES = [{"role": "user", "content": "Phrase only the supplied facts."}]
SECRET = "test-only-key"
OK = httpx.Response(200, json={
    "id": "offline-completion", "object": "chat.completion", "created": 0,
    "model": "test-flash", "choices": [{
        "index": 0, "message": {"role": "assistant", "content": "Verified facts."},
        "finish_reason": "stop",
    }],
})


def error(status, headers=None):
    # The body echoes the key, so tests can prove A2 never surfaces provider bodies.
    return httpx.Response(status, headers=headers, json={"error": {"message": SECRET}})


@pytest.fixture
def gemini(monkeypatch):
    """Build a real GeminiClient whose HTTP answers come from a scripted list."""
    clients = []
    requests = []

    def install(*outcomes):
        script = list(outcomes)

        def respond(request):
            requests.append(request)
            outcome = script.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        def sdk(**kwargs):
            client = OpenAI(http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kwargs)
            clients.append(client)
            return client

        monkeypatch.setattr(ai_setup, "OpenAI", sdk)
        monkeypatch.setenv("GEMINI_API_KEY", SECRET)
        monkeypatch.setenv("GEMINI_MODEL", "test-flash")
        return ai_setup.build_client(), requests

    yield install
    for client in clients:
        client.close()


@pytest.fixture
def sleeps():
    waited = []
    return waited


def run(client, sleeps, policy=None):
    return complete_with_retry(client, MESSAGES, policy=policy, sleep=sleeps.append)


def test_success_first_try_makes_one_request_and_never_sleeps(gemini, sleeps):
    client, requests = gemini(OK)
    reply = run(client, sleeps)
    assert reply.choices[0].message.content == "Verified facts."
    assert len(requests) == 1
    assert sleeps == []


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_transient_status_is_retried_then_succeeds(gemini, sleeps, status):
    client, requests = gemini(error(status), OK)
    assert run(client, sleeps).choices[0].message.content == "Verified facts."
    assert len(requests) == 2
    assert sleeps == [1.0]


@pytest.mark.parametrize("failure", [
    httpx.ReadTimeout("slow"),
    httpx.ConnectError("offline"),
])
def test_timeout_and_connection_errors_are_retried(gemini, sleeps, failure):
    client, requests = gemini(failure, OK)
    assert run(client, sleeps).choices[0].message.content == "Verified facts."
    assert len(requests) == 2


def test_gives_up_after_max_attempts_with_exponential_backoff(gemini, sleeps):
    client, requests = gemini(error(500), error(502), error(503))
    with pytest.raises(GeminiUnavailableError) as caught:
        run(client, sleeps)
    assert len(requests) == 3
    assert sleeps == [1.0, 2.0]
    assert caught.value.attempts == 3
    assert caught.value.status == 503
    assert "3 attempts" in str(caught.value)


def test_backoff_is_capped(gemini, sleeps):
    client, _ = gemini(*[error(503)] * 6)
    policy = RetryPolicy(max_attempts=6, base_delay_s=1.0, max_delay_s=4.0)
    with pytest.raises(GeminiUnavailableError):
        run(client, sleeps, policy)
    assert sleeps == [1.0, 2.0, 4.0, 4.0, 4.0]


def test_short_retry_after_header_is_honoured(gemini, sleeps):
    client, requests = gemini(error(429, {"retry-after": "3"}), OK)
    run(client, sleeps)
    assert len(requests) == 2
    assert sleeps == [3.0]


def test_long_retry_after_stops_immediately_instead_of_waiting(gemini, sleeps):
    """A quota reset can be minutes away: give up so the caller falls back now."""
    client, requests = gemini(error(429, {"retry-after": "60"}), OK)
    with pytest.raises(GeminiUnavailableError) as caught:
        run(client, sleeps)
    assert len(requests) == 1
    assert sleeps == []
    assert caught.value.status == 429
    assert "rate limit" in str(caught.value).lower()


def test_unparseable_retry_after_falls_back_to_backoff(gemini, sleeps):
    client, _ = gemini(error(429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}), OK)
    run(client, sleeps)
    assert sleeps == [1.0]


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_are_setup_errors_without_retry(gemini, sleeps, status):
    client, requests = gemini(error(status), OK)
    with pytest.raises(GeminiSetupError, match="GEMINI_API_KEY") as caught:
        run(client, sleeps)
    assert str(status) in str(caught.value)
    assert len(requests) == 1
    assert sleeps == []


def test_404_setup_error_from_a1_is_not_retried(gemini, sleeps):
    client, requests = gemini(error(404), OK)
    with pytest.raises(GeminiSetupError, match="GEMINI_MODEL"):
        run(client, sleeps)
    assert len(requests) == 1


@pytest.mark.parametrize("status", [400, 422])
def test_bad_request_is_not_retried(gemini, sleeps, status):
    client, requests = gemini(error(status), OK)
    with pytest.raises(GeminiUnavailableError) as caught:
        run(client, sleeps)
    assert len(requests) == 1
    assert sleeps == []
    assert caught.value.status == status
    assert caught.value.attempts == 1


@pytest.mark.parametrize("statuses, expected", [
    ([500, 500, 500], GeminiUnavailableError),
    ([401], GeminiSetupError),
    ([400], GeminiUnavailableError),
])
def test_no_secret_or_provider_body_in_errors_or_logs(gemini, sleeps, caplog, statuses, expected):
    client, _ = gemini(*[error(s) for s in statuses])
    with pytest.raises(expected) as caught:
        run(client, sleeps)
    assert SECRET not in "".join(traceback.format_exception(caught.value))
    assert SECRET not in caplog.text


def test_each_retry_is_logged_with_status_only(gemini, sleeps, caplog):
    client, _ = gemini(error(503), OK)
    with caplog.at_level("WARNING", logger=ai_retry.__name__):
        run(client, sleeps)
    assert "attempt 1/3" in caplog.text
    assert "503" in caplog.text


def test_default_policy_bounds_total_wait():
    policy = RetryPolicy()
    assert policy.max_attempts == 3
    assert policy.max_delay_s <= 10


@pytest.mark.parametrize("kwargs", [
    {"max_attempts": 0}, {"base_delay_s": -1}, {"max_delay_s": -1},
])
def test_invalid_policy_is_rejected(kwargs):
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)
