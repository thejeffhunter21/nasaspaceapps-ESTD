"""FE-02: preserve the API evidence at the display boundary."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.view_model import build_view_model

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def payload():
    return json.loads((ROOT / "app/fixtures/results.mock.json").read_text())


def test_frontend_fixture_is_an_exact_copy_with_the_original_gap(payload):
    assert payload == json.loads((ROOT / "results.mock.json").read_text())
    assert len(payload["series"]) == 36
    assert [p["time"] for p in payload["series"] if p["value"] is None] == ["2004-03"]


def test_maps_contract_fields_without_changing_statistics_or_input(payload):
    before = deepcopy(payload)
    view = build_view_model(payload)
    assert (view.region_id, view.region_label) == ("example_region", "Example Region")
    assert (view.variable, view.units) == ("Land surface temperature", "degC")
    assert view.period_label == "2003-01 to 2005-12"
    assert (view.slope, view.slope_unit, view.p, view.tau, view.direction) == (
        0.021, "degC/month", 0.012, 0.29, "increasing",
    )
    assert view.significant is True
    assert view.explanation == payload["explanation"]
    assert view.explanation_source == "fallback"
    assert view.source == "Mock data (not real NASA data)"
    assert view.method == "Mann-Kendall test (original) with Sen's slope"
    assert payload == before


def test_preserves_month_order_gap_and_zero(payload):
    payload["series"][0]["value"] = 0
    view = build_view_model(payload)
    assert len(view.times) == len(view.values) == 36
    assert view.times[0] == "2003-01"
    assert view.times[-1] == "2005-12"
    assert view.values[0] == 0
    assert (view.times[14], view.values[14]) == ("2004-03", None)
    assert view.values[15] == 27.97


@pytest.mark.parametrize("p, significant", [(0.0499999, True), (0.05, False), (0.050001, False)])
def test_significance_uses_unrounded_p(payload, p, significant):
    payload["trend"]["p"] = p
    assert build_view_model(payload).significant is significant


@pytest.mark.parametrize("region, source, sample", [
    ("Example Region", "NASA MODIS", True),
    ("Phoenix northwest", "MOCK data", True),
    ("Phoenix northwest", "NASA MODIS", False),
])
def test_sample_detection_uses_contract_markers(payload, region, source, sample):
    payload.update(region=region, source=source)
    assert build_view_model(payload).is_sample is sample


def test_rejects_malformed_contract_instead_of_defaulting_missing_stats_to_zero(payload):
    del payload["trend"]["p"]
    with pytest.raises(ValidationError):
        build_view_model(payload)
