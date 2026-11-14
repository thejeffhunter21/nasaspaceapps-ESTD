"""FE-03: observations, missing months and units survive chart serialization."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.charts import monthly_chart
from app.view_model import build_view_model

pytestmark = pytest.mark.unit
FIXTURE = Path(__file__).resolve().parents[2] / "app/fixtures/results.mock.json"


@pytest.fixture
def view():
    return build_view_model(json.loads(FIXTURE.read_text()))


def test_serialized_chart_keeps_calendar_gap_and_only_observation_trace(view):
    chart = json.loads(monthly_chart(view).to_json())
    assert len(chart["data"]) == 1  # A slope alone cannot define a fitted line.
    trace = chart["data"][0]
    assert len(trace["x"]) == len(trace["y"]) == 36
    assert trace["x"][0] == "2003-01"
    assert trace["x"][-1] == "2005-12"
    assert trace["x"][14] == "2004-03"
    assert trace["y"][13:16] == [24.65, None, 27.97]
    assert trace["connectgaps"] is False
    assert trace["mode"] == "lines+markers"


def test_chart_labels_month_hover_and_supplied_units(view):
    chart = monthly_chart(view)
    assert chart.layout.xaxis.type == "date"
    assert chart.layout.xaxis.title.text == "Month"
    assert chart.layout.yaxis.title.text == "Land surface temperature (degC)"
    assert "%{x|%Y-%m}" in chart.data[0].hovertemplate
    assert "degC" in chart.data[0].hovertemplate


def test_chart_preserves_zero_and_negative_observations(view):
    view = replace(view, values=(0.0, -2.5, *view.values[2:]))
    chart = monthly_chart(view)
    assert chart.data[0].y[:2] == (0.0, -2.5)
