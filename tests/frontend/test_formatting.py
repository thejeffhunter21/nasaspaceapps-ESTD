"""FE-08: human-readable formatting must leave raw scientific values intact."""

import json
from pathlib import Path

import pytest

from app.charts import monthly_chart
from app.view_model import build_view_model

pytestmark = pytest.mark.unit
FIXTURE = Path(__file__).resolve().parents[2] / "app/fixtures/results.mock.json"


@pytest.mark.parametrize("p, label, significant", [
    (0.0, "p < 0.001", True), (3.3e-10, "p < 0.001", True),
    (0.0009999, "p < 0.001", True), (0.001, "0.001", True),
    (0.0499999, "0.0499999", True), (0.05, "0.05", False), (1.0, "1.0", False),
])
def test_p_formatting_preserves_raw_value_and_threshold_decision(p, label, significant):
    payload = json.loads(FIXTURE.read_text())
    payload["trend"]["p"] = p
    view = build_view_model(payload)
    assert view.display_p == label
    assert view.p == p
    assert view.significant is significant
    assert payload["trend"]["p"] == p


@pytest.mark.parametrize("unit, slope_unit, display, slope_display", [
    ("degC", "degC/month", "°C", "°C/month"),
    ("K", "K/month", "K", "K/month"),
])
def test_unit_labels_and_chart_hover_preserve_raw_units(unit, slope_unit, display, slope_display):
    payload = json.loads(FIXTURE.read_text())
    payload["units"] = unit
    payload["trend"]["slope_unit"] = slope_unit
    view = build_view_model(payload)
    assert (view.display_units, view.display_slope_unit) == (display, slope_display)
    assert (view.units, view.slope_unit) == (unit, slope_unit)
    chart = monthly_chart(view)
    assert chart.layout.yaxis.title.text == f"Land surface temperature ({display})"
    assert display in chart.data[0].hovertemplate
    assert chart.data[0].y[14] is None


@pytest.mark.parametrize("slope, display", [
    (0.0077125000000000015, "0.0077125"),
    (-0.0075514705882352845, "-0.00755147"),
    (0.0, "0.0"), (1e-12, "1e-12"), (-1e-12, "-1e-12"),
])
def test_slope_display_is_compact_without_losing_raw_precision(slope, display):
    payload = json.loads(FIXTURE.read_text())
    payload["trend"]["slope"] = slope
    view = build_view_model(payload)
    assert view.display_slope == display
    assert view.slope == slope
    assert payload["trend"]["slope"] == slope
