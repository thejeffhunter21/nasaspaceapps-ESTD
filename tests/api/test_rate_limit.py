"""J12: over the limit gives 429 + Retry-After, /health is exempt, slow requests give 504."""

import time

import pytest

from earth_system_trend.api import middleware
from earth_system_trend.api.app import app

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    monkeypatch.setattr(middleware, "limiter", middleware.RateLimiter())


def test_limit_off_in_tests_by_default(client):
    assert all(client.get("/trend").status_code == 200 for _ in range(30))


def test_over_the_limit_is_429(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    codes = [client.get("/trend").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    response = client.get("/series")
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 60


def test_health_home_version_are_exempt(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    for path in ("/health", "/", "/version"):
        assert all(client.get(path).status_code == 200 for _ in range(5))


def test_window_slides():
    limiter = middleware.RateLimiter()
    assert limiter.check("a", 1, now=0.0) is None
    assert limiter.check("a", 1, now=30.0) == pytest.approx(30.0)
    assert limiter.check("a", 1, now=60.5) is None  # a minute later: allowed again
    assert limiter.check("b", 1, now=30.0) is None  # other visitors are separate


def test_idle_visitors_forgotten():
    limiter = middleware.RateLimiter()
    limiter.check("old", 5, now=0.0)
    limiter.check("new", 5, now=100.0)
    limiter.forget_idle(now=100.0)
    assert set(limiter.hits) == {"new"}


def test_slow_request_is_504(client, monkeypatch):
    @app.get("/_slow_test_route")
    def slow():
        time.sleep(0.5)
        return {"ok": True}

    monkeypatch.setenv("REQUEST_TIMEOUT_S", "0.1")
    try:
        assert client.get("/_slow_test_route").status_code == 504
    finally:
        app.router.routes = [r for r in app.router.routes
                             if getattr(r, "path", "") != "/_slow_test_route"]
