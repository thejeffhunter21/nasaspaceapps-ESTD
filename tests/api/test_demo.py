"""J13: three demo stories picked from the regions; each names a usable region_id."""

import pytest

pytestmark = pytest.mark.unit


def test_three_stories_from_regions(regions_client):
    cases = regions_client.get("/demo").json()["cases"]
    assert cases[0]["id"] == "whole_area"
    ids = {r["region_id"] for r in regions_client.get("/regions").json()["regions"]}
    for case in cases:
        assert case["region_id"] in ids
        assert case["label"] and case["description"]
        assert regions_client.get("/trend", params={"region": case["region_id"]}).status_code == 200


def test_mock_mode_has_one_story(client):
    cases = client.get("/demo").json()["cases"]
    assert len(cases) == 1 and cases[0]["region_id"] == "example_region"


def test_no_regions_is_404(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RESULTS_PATH", str(tmp_path / "missing.json"))
    assert client.get("/demo").status_code == 404


def test_fastest_and_slowest_picked():
    from earth_system_trend.api.demo import pick_stories
    from earth_system_trend.contract import load_results
    from tests.api.conftest import FIXTURES

    base = load_results(FIXTURES / "api" / "results.json")
    def region(rid, slope):
        return base.model_copy(update={"region_id": rid, "region": rid.title(),
                                       "trend": base.trend.model_copy(update={"slope": slope})})
    stories = pick_stories([base, region("a", 0.01), region("b", 0.03), region("c", 0.02)])
    assert [(s["id"], s["region_id"]) for s in stories] == [
        ("whole_area", base.region_id), ("fastest", "b"), ("slowest", "a")]
    assert "+0.36" in stories[1]["description"]  # 0.03 per month = 0.36 per year
