"""FE-04: read the main-area API with bounded retries and success-only caching."""

from urllib.parse import urlsplit

import requests
import streamlit as st
from pydantic import ValidationError

from earth_system_trend.contract import Results

DEFAULT_API_URL = "https://estd-api.onrender.com"


class ApiError(ValueError):
    """A safe, user-readable API connection or payload failure."""


def fetch_results(api_url: str) -> dict:
    """Validate configuration, then cache by normalized API base URL."""
    base_url = api_url.strip().rstrip("/")
    try:
        parsed = urlsplit(base_url)
        valid = (
            parsed.scheme in ("http", "https") and parsed.hostname
            and not (parsed.username or parsed.password or parsed.query or parsed.fragment)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ApiError("API connection is not configured correctly. Use sample data or check API_URL.")
    return _fetch_results(base_url)


def clear_results_cache(api_url: str) -> None:
    """Let a user pick up a backend deployment before the 60-second expiry."""
    _fetch_results.clear(api_url.strip().rstrip("/"))


@st.cache_data(ttl=60, max_entries=16, show_spinner=False)
def _fetch_results(base_url: str) -> dict:
    """Wake the service first; cache only successfully validated results."""
    with requests.Session() as session:
        health = _get_json(session, f"{base_url}/health")
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise ApiError("The API is not ready. Try again or use sample data.")
        payload = _get_json(session, f"{base_url}/results")
    try:
        Results.model_validate(payload)
    except ValidationError:
        raise ApiError("The API returned invalid results. Try again or use sample data.") from None
    return payload


def _get_json(session: requests.Session, url: str):
    """At most two attempts per endpoint; no SDK or adapter retry layer."""
    for attempt in range(2):
        try:
            response = session.get(url, timeout=(5, 45), allow_redirects=False)
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 0:
                continue
            raise ApiError("The API did not respond after two attempts. Try again or use sample data.") from None
        except requests.RequestException:
            raise ApiError("Could not connect to the API. Try again or use sample data.") from None
        if response.status_code != 200:
            if attempt == 0 and (response.status_code == 429 or 500 <= response.status_code < 600):
                continue
            raise ApiError(f"API request failed (HTTP {response.status_code}). Try again or use sample data.")
        try:
            return response.json()
        except ValueError:
            raise ApiError("The API returned invalid JSON. Try again or use sample data.") from None
