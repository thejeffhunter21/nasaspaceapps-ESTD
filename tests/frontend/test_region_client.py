"""FE-05: region caches and paired endpoints must preserve one region's evidence."""

import json
from pathlib import Path

import pytest

from app.api_client import ApiError, fetch_region_results, fetch_regions
from tests.frontend.test_api_client import install, response

pytestmark = pytest.mark.unit
FIXTURE = Path(__file__).resolve().parents[2] / "app/fixtures/results.mock.json"


def payload(region_id="north", region="North"):
    return dict(json.loads(FIXTURE.read_text()), region_id=region_id, region=region)


def halves(result):
    series = {key: result[key] for key in (
        "region_id", "region", "variable", "units", "period", "series",
    )}
    trend = {key: value for key, value in result.items() if key != "series"}
    return series, trend


def test_directory_wakes_api_and_caches_returned_ids_labels(monkeypatch):
    calls = install(monkeypatch, [response({"status": "ok"}), response({"regions": [payload()]})])
    assert fetch_regions("https://api.example/") == [{"region_id": "north", "region": "North"}]
    assert fetch_regions("https://api.example") == [{"region_id": "north", "region": "North"}]
    assert [url for url, _ in calls] == ["https://api.example/health", "https://api.example/regions"]


def test_region_id_is_sent_to_both_endpoints_and_caches_stay_separate(monkeypatch):
    north, south = payload(), payload("south", "South")
    calls = install(monkeypatch, [response(item) for item in (*halves(north), *halves(south))])
    assert fetch_region_results("https://api.example", "north")["region"] == "North"
    assert fetch_region_results("https://api.example", "south")["region"] == "South"
    assert fetch_region_results("https://api.example", "north")["region"] == "North"
    assert [options["params"] for _, options in calls] == [
        {"region": "north"}, {"region": "north"}, {"region": "south"}, {"region": "south"},
    ]
    assert [url.rsplit("/", 1)[-1] for url, _ in calls] == ["series", "trend", "series", "trend"]


@pytest.mark.parametrize("field, changed", [
    ("region_id", "south"), ("region", "South"), ("units", "K"),
    ("variable", "Different variable"), ("period", {"start": "2004-01", "end": "2005-12"}),
])
def test_mixed_metadata_is_rejected_and_never_cached(monkeypatch, field, changed):
    series, trend = halves(payload())
    bad_trend = dict(trend, **{field: changed})
    calls = install(monkeypatch, [response(item) for item in (series, bad_trend, series, trend)])
    with pytest.raises(ApiError):
        fetch_region_results("https://api.example", "north")
    assert fetch_region_results("https://api.example", "north")["region"] == "North"
    assert len(calls) == 4


def test_matching_pair_for_the_wrong_requested_region_is_rejected(monkeypatch):
    install(monkeypatch, [response(item) for item in halves(payload("south", "South"))])
    with pytest.raises(ApiError):
        fetch_region_results("https://api.example", "north")


@pytest.mark.parametrize("regions", [[], [{"region": "No ID"}], [payload(), payload()]])
def test_empty_invalid_and_duplicate_region_catalogs_fail(monkeypatch, regions):
    install(monkeypatch, [response({"status": "ok"}), response({"regions": regions})])
    with pytest.raises(ApiError):
        fetch_regions("https://api.example")


def test_region_cache_does_not_cross_api_hosts(monkeypatch):
    calls = install(monkeypatch, [response(item) for item in (
        *halves(payload()), *halves(payload("north", "Other host north")),
    )])
    assert fetch_region_results("https://one.example", "north")["region"] == "North"
    assert fetch_region_results("https://two.example", "north")["region"] == "Other host north"
    assert len(calls) == 4


def test_refresh_invalidates_selected_region_without_flushing_others(monkeypatch):
    from app.api_client import clear_results_cache

    calls = install(monkeypatch, [response(item) for item in (
        *halves(payload()), *halves(payload("south", "South")),
        *halves(payload("north", "Other host north")), *halves(payload("north", "Updated north")),
    )])
    fetch_region_results("https://one.example", "north")
    fetch_region_results("https://one.example", "south")
    fetch_region_results("https://two.example", "north")
    clear_results_cache("https://one.example", "north")
    assert fetch_region_results("https://one.example", "north")["region"] == "Updated north"
    assert fetch_region_results("https://one.example", "south")["region"] == "South"
    assert fetch_region_results("https://two.example", "north")["region"] == "Other host north"
    assert len(calls) == 8
