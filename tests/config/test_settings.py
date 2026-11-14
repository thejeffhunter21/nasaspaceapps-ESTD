"""J3: settings come from the environment, with safe defaults."""

from pathlib import Path

import pytest

from earth_system_trend.config import get_settings

pytestmark = pytest.mark.unit
NAMES = ["USE_MOCK", "RESULTS_PATH", "REGIONS_DIR", "CORS_ORIGINS",
         "REQUEST_TIMEOUT_S", "RATE_LIMIT_PER_MINUTE"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


def test_mock_is_the_default():
    s = get_settings()
    assert s.use_mock is True
    assert s.results_path == Path("results.mock.json")
    assert s.regions_dir is None


def test_each_call_rereads_environment(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "false")
    s = get_settings()
    assert s.use_mock is False
    assert s.results_path == Path("results/results.json")
    assert s.regions_dir == Path("results/regions")


def test_cors_origins_list(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.app, https://b.app")
    assert get_settings().cors_origins == ["https://a.app", "https://b.app"]


@pytest.mark.parametrize("name, attr, default", [
    ("REQUEST_TIMEOUT_S", "request_timeout_s", 10.0),
    ("RATE_LIMIT_PER_MINUTE", "rate_limit_per_minute", 60),
])
@pytest.mark.parametrize("bad", ["abc", "-5"])
def test_bad_number_falls_back(monkeypatch, name, attr, default, bad):
    monkeypatch.setenv(name, bad)
    assert getattr(get_settings(), attr) == default
