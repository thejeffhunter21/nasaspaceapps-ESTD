"""Every setting the API reads, in one place.

Values come from environment variables (a local .env file, or Render's
dashboard). get_settings() re-reads the environment on every call, so a test
can change a variable with monkeypatch and see it straight away.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # never overrides variables that are already set

DEFAULTS = {
    "USE_MOCK": "true",
    "RESULTS_PATH": "results/results.json",
    "MOCK_PATH": "results.mock.json",
    "REGIONS_DIR": "results/regions",
    "CORS_ORIGINS": "http://localhost:8501",
    "REQUEST_TIMEOUT_S": "10",
    "RATE_LIMIT_PER_MINUTE": "60",
}


@dataclass(frozen=True)
class Settings:
    use_mock: bool
    results_path: Path  # the file /results serves (mock file when use_mock)
    regions_dir: Path | None  # None in mock mode: only the mock region exists
    cors_origins: list[str]
    request_timeout_s: float
    rate_limit_per_minute: int


def get_settings() -> Settings:
    use_mock = _bool("USE_MOCK")
    results = os.getenv("RESULTS_PATH")
    if not results:
        results = DEFAULTS["MOCK_PATH"] if use_mock else DEFAULTS["RESULTS_PATH"]
    return Settings(
        use_mock=use_mock,
        results_path=Path(results),
        regions_dir=None if use_mock else Path(os.getenv("REGIONS_DIR") or DEFAULTS["REGIONS_DIR"]),
        cors_origins=[o.strip() for o in _get("CORS_ORIGINS").split(",") if o.strip()],
        request_timeout_s=_number("REQUEST_TIMEOUT_S", float),
        rate_limit_per_minute=_number("RATE_LIMIT_PER_MINUTE", int),
    )


def _get(name: str) -> str:
    return os.getenv(name) or DEFAULTS[name]


def _bool(name: str) -> bool:
    return _get(name).strip().lower() not in ("false", "0", "no", "off")


def _number(name: str, kind: type):
    try:
        value = kind(_get(name))
    except ValueError:
        return kind(DEFAULTS[name])
    return value if value >= 0 else kind(DEFAULTS[name])
