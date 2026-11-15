"""Check a running API from the outside: is it up, and is it serving what we expect?

Used by scripts/smoke_test.py (the live Render API) and scripts/backup_run.py (the
offline copy on a laptop). Plain HTTP only, so it works against any running server.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

MOCK_REGION = "Example Region"

# One line per check: path, expected status, keys the JSON answer must contain.
# Adding an endpoint is one line here.
CHECKS: list[tuple[str, int, tuple[str, ...]]] = [
    ("/health", 200, ("status",)),
    ("/", 200, ("name", "try")),
    ("/results", 200, ("region_id", "series", "trend", "explanation", "explanation_source")),
    ("/regions", 200, ("regions",)),
    ("/series", 200, ("region_id", "units", "series")),
    ("/trend", 200, ("trend", "explanation", "explanation_source", "source", "method")),
    ("/demo", 200, ("cases",)),
    ("/version", 200, ("commit",)),
    ("/series?region=not_a_region", 404, ("detail",)),
    ("/series?region=%3Cscript%3E", 422, ("detail",)),
]


@dataclass
class CheckResult:
    path: str
    ok: bool
    message: str


def wait_until_up(base_url: str, timeout_s: float = 120, session=None) -> bool:
    """Poll /health until it answers 200. Render's free tier can take ~50 s to wake."""
    session = session or requests.Session()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if session.get(base_url + "/health", timeout=10).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(2)
    return False


def run_checks(base_url: str, *, expect_real: bool = False, session=None) -> list[CheckResult]:
    """Run every check against base_url and return one result per check."""
    base_url = base_url.rstrip("/")
    session = session or requests.Session()
    results = []
    for path, status, keys in CHECKS:
        results.append(_check(session, base_url, path, status, keys))
    regions = _json(session, base_url + "/regions")
    if isinstance(regions, dict):
        for region in regions.get("regions", []):
            rid = region.get("region_id")
            results.append(_check(session, base_url, f"/trend?region={rid}", 200, ("trend",)))
            results.append(_check(session, base_url, f"/series?region={rid}", 200, ("series",)))
    if expect_real:
        results.append(check_real_data(base_url, session=session))
        for region in (regions or {}).get("regions", []):
            rid = region.get("region_id")
            results.append(_check(session, base_url, f"/anomaly?region={rid}", 200,
                                  ("series", "baseline")))
    return results


def check_real_data(base_url: str, session=None) -> CheckResult:
    """Pass only if the server is up and serves real (not mock or stub) results."""
    session = session or requests.Session()
    base_url = base_url.rstrip("/")
    try:
        if session.get(base_url + "/health", timeout=30).status_code != 200:
            return CheckResult("real data", False, "/health is not answering 200")
        body = session.get(base_url + "/results", timeout=30).json()
    except (requests.RequestException, ValueError) as exc:
        return CheckResult("real data", False, f"could not read /results ({exc})")
    region = body.get("region", "")
    if region == MOCK_REGION or "mock" in str(body.get("source", "")).lower():
        return CheckResult("real data", False, "serving MOCK data (set USE_MOCK=false)")
    if "stub" in str(body.get("method", "")).lower():
        return CheckResult("real data", False, "results were built with stub functions")
    months = len(body.get("series", []))
    return CheckResult("real data", True, f"{region}, {months} months, {body.get('method', '')}")


def _check(session, base_url, path, status, keys) -> CheckResult:
    try:
        response = session.get(base_url + path, timeout=30)
    except requests.RequestException as exc:
        return CheckResult(path, False, f"no answer ({type(exc).__name__})")
    if response.status_code != status:
        return CheckResult(path, False, f"status {response.status_code}, expected {status}")
    try:
        body = response.json()
    except ValueError:
        return CheckResult(path, False, "answer is not JSON")
    missing = [k for k in keys if k not in body]
    if missing:
        return CheckResult(path, False, f"missing keys: {', '.join(missing)}")
    return CheckResult(path, True, f"status {status}")


def _json(session, url):
    try:
        return session.get(url, timeout=30).json()
    except (requests.RequestException, ValueError):
        return None
