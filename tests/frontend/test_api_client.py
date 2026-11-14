"""FE-04: bounded requests and validated success-only caching."""

import json
from pathlib import Path

import pytest
import requests

from app.api_client import ApiError, fetch_results

pytestmark = pytest.mark.unit
FIXTURE = Path(__file__).resolve().parents[2] / "app/fixtures/results.mock.json"


def response(payload, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    return result


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text())


def install(monkeypatch, outcomes):
    calls = []
    remaining = iter(outcomes)

    def get(session, url, **kwargs):
        calls.append((url, kwargs))
        outcome = next(remaining)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(requests.Session, "get", get)
    return calls


def test_health_before_results_and_repeat_load_uses_url_cache(monkeypatch, payload):
    calls = install(monkeypatch, [response({"status": "ok"}), response(payload)])
    assert fetch_results("https://api.example") == payload
    assert fetch_results("https://api.example") == payload
    assert [url for url, _ in calls] == ["https://api.example/health", "https://api.example/results"]
    assert all(options["timeout"] == (5, 45) for _, options in calls)


def test_cache_does_not_mix_api_hosts(monkeypatch, payload):
    other = dict(payload, region="Another sample region")
    calls = install(monkeypatch, [
        response({"status": "ok"}), response(payload),
        response({"status": "ok"}), response(other),
    ])
    assert fetch_results("https://one.example")["region"] == "Example Region"
    assert fetch_results("https://two.example")["region"] == "Another sample region"
    assert len(calls) == 4


@pytest.mark.parametrize("error", [requests.Timeout(), requests.ConnectionError()])
def test_health_transient_failure_retries_once_then_continues(monkeypatch, payload, error):
    calls = install(monkeypatch, [error, response({"status": "ok"}), response(payload)])
    assert fetch_results("https://api.example/") == payload
    assert [url.rsplit("/", 1)[-1] for url, _ in calls] == ["health", "health", "results"]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_results_transient_status_retries_once(monkeypatch, payload, status):
    calls = install(monkeypatch, [
        response({"status": "ok"}), response({}, status), response(payload),
    ])
    assert fetch_results("https://api.example") == payload
    assert len(calls) == 3


def test_failure_is_bounded_and_not_cached(monkeypatch, payload):
    calls = install(monkeypatch, [
        requests.Timeout(), requests.Timeout(),
        response({"status": "ok"}), response(payload),
    ])
    with pytest.raises(ApiError):
        fetch_results("https://api.example")
    assert len(calls) == 2
    assert fetch_results("https://api.example") == payload
    assert len(calls) == 4


@pytest.mark.parametrize("status", [404, 422])
def test_permanent_http_failure_does_not_retry_or_expose_response(monkeypatch, status):
    calls = install(monkeypatch, [response({"detail": "private server detail"}, status)])
    with pytest.raises(ApiError) as caught:
        fetch_results("https://api.example")
    assert len(calls) == 1
    assert str(status) in str(caught.value)
    assert "private server detail" not in str(caught.value)


@pytest.mark.parametrize("bad_payload", [{}, {"series": []}, "not an object"])
def test_invalid_results_are_not_cached(monkeypatch, payload, bad_payload):
    calls = install(monkeypatch, [
        response({"status": "ok"}), response(bad_payload),
        response({"status": "ok"}), response(payload),
    ])
    with pytest.raises(ApiError):
        fetch_results("https://api.example")
    assert fetch_results("https://api.example") == payload
    assert len(calls) == 4


def test_bad_health_does_not_load_results(monkeypatch):
    calls = install(monkeypatch, [response({"status": "unhealthy"})])
    with pytest.raises(ApiError):
        fetch_results("https://api.example")
    assert len(calls) == 1


@pytest.mark.parametrize("url", ["", "ftp://api.example", "https://api.example?key=hidden"])
def test_bad_configuration_makes_no_request(monkeypatch, url):
    calls = install(monkeypatch, [])
    with pytest.raises(ApiError):
        fetch_results(url)
    assert not calls


def test_refresh_removes_only_the_selected_url_cache(monkeypatch, payload):
    from app.api_client import clear_results_cache

    updated = dict(payload, region="Updated region")
    calls = install(monkeypatch, [
        response({"status": "ok"}), response(payload),
        response({"status": "ok"}), response(payload),
        response({"status": "ok"}), response(updated),
    ])
    fetch_results("https://one.example")
    fetch_results("https://two.example")
    clear_results_cache("https://one.example/")
    assert fetch_results("https://one.example")["region"] == "Updated region"
    assert fetch_results("https://two.example")["region"] == "Example Region"
    assert len(calls) == 6


def test_invalid_json_is_not_retried_or_cached(monkeypatch, payload):
    bad = response(None)
    bad._content = b"not JSON"
    calls = install(monkeypatch, [
        response({"status": "ok"}), bad,
        response({"status": "ok"}), response(payload),
    ])
    with pytest.raises(ApiError, match="invalid JSON"):
        fetch_results("https://api.example")
    assert len(calls) == 2
    assert fetch_results("https://api.example") == payload


def test_results_timeout_stops_after_the_single_retry(monkeypatch):
    calls = install(monkeypatch, [
        response({"status": "ok"}), requests.Timeout(), requests.Timeout(),
    ])
    with pytest.raises(ApiError):
        fetch_results("https://api.example")
    assert len(calls) == 3
