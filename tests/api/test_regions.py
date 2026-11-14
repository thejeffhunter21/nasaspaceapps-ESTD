"""J11: /regions lists every region; ?region= finds one by id or label."""

import logging

import pytest

pytestmark = pytest.mark.unit


def test_lists_ids(regions_client):
    ids = [r["region_id"] for r in regions_client.get("/regions").json()["regions"]]
    assert ids == ["example_region", "north_box", "south_box"]


def test_mock_mode_has_one_region(client):
    assert len(client.get("/regions").json()["regions"]) == 1


@pytest.mark.parametrize("query", ["south_box", "SOUTH BOX", "South box"])
def test_match_id_or_label(regions_client, query):
    body = regions_client.get("/trend", params={"region": query}).json()
    assert body["region_id"] == "south_box"
    assert body["trend"]["trend"] == "no trend"


def test_unknown_region_lists_valid_ids(regions_client):
    response = regions_client.get("/series", params={"region": "atlantis"})
    assert response.status_code == 404
    assert "north_box" in response.json()["detail"]


def test_broken_file_skipped_with_warning(regions_client, caplog):
    with caplog.at_level(logging.WARNING):
        regions_client.get("/regions")
    assert "zz_broken" in caplog.text
