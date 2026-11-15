"""Frontend API access: bounded requests and validated, region-specific caches."""

import re
from urllib.parse import urlsplit

import requests
import streamlit as st
from pydantic import BaseModel, Field, ValidationError

from earth_system_trend.contract import Results, SeriesPoint, Trend

DEFAULT_API_URL = "https://estd-api.onrender.com"


class ApiError(ValueError):
    """A safe, user-readable API connection or payload failure."""

    def __init__(self, message: str, *, kind: str = "invalid_response"):
        super().__init__(message)
        self.kind = kind


def require_observations(payload) -> None:
    """Treat empty or all-null series as unavailable, without inserting values."""
    points = payload.get("series") if isinstance(payload, dict) else None
    if isinstance(points, list) and (
        not points or all(
            isinstance(point, dict) and "value" in point and point["value"] is None
            for point in points
        )
    ):
        raise ApiError(
            "No measured values are available. Retry or choose another region; missing values stay missing.",
            kind="empty",
        )


def fetch_results(api_url: str) -> dict:
    """Validate configuration, then cache by normalized API base URL."""
    return _fetch_results(_base_url(api_url))


def _base_url(api_url: str) -> str:
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
        raise ApiError(
            "Ask the demo owner to check the API address, or use sample data.", kind="configuration",
        )
    return base_url


def clear_results_cache(api_url: str, region_id: str | None = None) -> None:
    """Let a user pick up a backend deployment before the 60-second expiry."""
    base_url = api_url.strip().rstrip("/")
    _fetch_results.clear(base_url)
    _fetch_regions.clear(base_url)
    _region_payload.clear(base_url)
    _fetch_region_directory.clear(base_url)
    if region_id:
        _fetch_region_results.clear(base_url, region_id)
        _fetch_region_anomaly.clear(base_url, region_id)


class _RegionOption(BaseModel):
    region_id: str = Field(pattern=r"^[a-z0-9_]+$")
    region: str = Field(min_length=1)


class _RegionDirectory(BaseModel):
    regions: list[_RegionOption] = Field(min_length=1)


def fetch_regions(api_url: str) -> list[dict]:
    """Return only the region IDs and labels supplied by the API."""
    return _fetch_regions(_base_url(api_url))


def fetch_region_trends(api_url: str) -> dict[str, dict]:
    """Trend summaries per region from the same cached /regions response; {} if absent."""
    try:
        return _fetch_region_directory(_base_url(api_url))
    except ApiError:
        return {}


@st.cache_data(ttl=60, max_entries=16, show_spinner=False)
def _fetch_regions(base_url: str) -> list[dict]:
    payload = _region_payload(base_url)
    if isinstance(payload, dict) and payload.get("regions") == []:
        raise ApiError("No study regions are available yet. Retry or use sample data.", kind="empty_regions")
    try:
        directory = _RegionDirectory.model_validate(payload)
    except ValidationError:
        raise ApiError("The API returned an invalid region list. Try again or use sample data.") from None
    ids = [region.region_id for region in directory.regions]
    if len(ids) != len(set(ids)):
        raise ApiError("The API returned duplicate region IDs. Try again or use sample data.")
    return [region.model_dump() for region in directory.regions]


@st.cache_data(ttl=60, max_entries=16, show_spinner=False)
def _region_payload(base_url: str):
    with requests.Session() as session:
        health = _get_json(session, f"{base_url}/health")
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise ApiError("The API is not ready. Try again or use sample data.", kind="server")
        return _get_json(session, f"{base_url}/regions")


@st.cache_data(ttl=60, max_entries=16, show_spinner=False)
def _fetch_region_directory(base_url: str) -> dict[str, dict]:
    """Keep only well-formed supplied trends; the comparison view is optional."""
    payload = _region_payload(base_url)
    regions = payload.get("regions") if isinstance(payload, dict) else None
    trends = {}
    for region in regions if isinstance(regions, list) else []:
        try:
            option = _RegionOption.model_validate(region)
            trend = Trend.model_validate(region["trend"])
        except (ValidationError, KeyError, TypeError):
            continue
        trends[option.region_id] = {"region": option.region, **trend.model_dump()}
    return trends


def fetch_region_anomaly(api_url: str, region_id: str, times: tuple[str, ...]) -> tuple | None:
    """Optional /anomaly values aligned to the displayed months; None hides the view."""
    try:
        values = _fetch_region_anomaly(_base_url(api_url), region_id)
    except ApiError:
        return None
    if values is None or tuple(time for time, _ in values) != times:
        return None
    return tuple(value for _, value in values)


@st.cache_data(ttl=60, max_entries=64, show_spinner=False)
def _fetch_region_anomaly(base_url: str, region_id: str):
    try:
        with requests.Session() as session:
            payload = _get_json(session, f"{base_url}/anomaly", {"region": region_id})
    except ApiError:
        return None  # optional view: cache the absence instead of retrying every rerun
    if not isinstance(payload, dict) or payload.get("region_id") != region_id:
        return None
    try:
        points = [SeriesPoint.model_validate(point) for point in payload["series"]]
    except (ValidationError, KeyError, TypeError):
        return None
    return tuple((point.time, point.value) for point in points)


def fetch_region_results(api_url: str, region_id: str) -> dict:
    """Load one complete region; never return half of a series/trend pair."""
    if not isinstance(region_id, str) or not re.fullmatch(r"[a-z0-9_]+", region_id):
        raise ApiError("Refresh the region list and choose an available region.", kind="selection")
    return _fetch_region_results(_base_url(api_url), region_id)


@st.cache_data(ttl=60, max_entries=64, show_spinner=False)
def _fetch_region_results(base_url: str, region_id: str) -> dict:
    with requests.Session() as session:
        params = {"region": region_id}
        series = _get_json(session, f"{base_url}/series", params)
        require_observations(series)
        trend = _get_json(session, f"{base_url}/trend", params)
    fields = ("region_id", "region", "variable", "units", "period")
    if (
        not isinstance(series, dict) or not isinstance(trend, dict)
        or series.get("region_id") != region_id
        or any(series.get(field) != trend.get(field) for field in fields)
    ):
        raise ApiError("The API returned mismatched region data. Retry this region.")
    payload = {**trend, "series": series.get("series")}
    try:
        Results.model_validate(payload)
    except ValidationError:
        raise ApiError("The API returned invalid results. Try again or use sample data.") from None
    return payload


@st.cache_data(ttl=60, max_entries=16, show_spinner=False)
def _fetch_results(base_url: str) -> dict:
    """Wake the service first; cache only successfully validated results."""
    with requests.Session() as session:
        health = _get_json(session, f"{base_url}/health")
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise ApiError("The API is not ready. Try again or use sample data.", kind="server")
        payload = _get_json(session, f"{base_url}/results")
    require_observations(payload)
    try:
        Results.model_validate(payload)
    except ValidationError:
        raise ApiError("The API returned invalid results. Try again or use sample data.") from None
    return payload


def _get_json(session: requests.Session, url: str, params: dict | None = None):
    """At most two attempts per endpoint; no SDK or adapter retry layer."""
    for attempt in range(2):
        try:
            response = session.get(url, params=params, timeout=(5, 45), allow_redirects=False)
        except requests.Timeout:
            if attempt == 0:
                continue
            raise ApiError(
                "The API did not respond after two attempts. It may be waking up. Retry or use sample data.",
                kind="timeout",
            ) from None
        except requests.ConnectionError:
            if attempt == 0:
                continue
            raise ApiError(
                "Check your connection, then retry or use the local sample preview.", kind="connection",
            ) from None
        except requests.RequestException:
            raise ApiError(
                "Could not connect to the API. Try again or use sample data.", kind="connection",
            ) from None
        if response.status_code != 200:
            if attempt == 0 and (response.status_code == 429 or 500 <= response.status_code < 600):
                continue
            if response.status_code == 404:
                raise ApiError(
                    "No data is available for this region (HTTP 404). Refresh regions or choose another.",
                    kind="not_found",
                )
            if response.status_code == 422:
                raise ApiError(
                    "Refresh the available regions and choose one again (HTTP 422).", kind="selection",
                )
            if response.status_code == 429:
                raise ApiError("Too many requests (HTTP 429). Wait briefly, then retry.", kind="rate_limit")
            if response.status_code >= 500:
                raise ApiError(
                    f"The server could not load results (HTTP {response.status_code}). "
                    "Retry; if this continues, report it to the backend owner.", kind="server",
                )
            raise ApiError(f"API request failed (HTTP {response.status_code}). Try again or use sample data.")
        try:
            return response.json()
        except ValueError:
            raise ApiError("The API returned invalid JSON. Try again or use sample data.") from None
