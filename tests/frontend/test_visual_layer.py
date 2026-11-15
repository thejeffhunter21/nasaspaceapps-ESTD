"""Redesign: new views render supplied numbers only, keep gaps blank and label derived figures."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
import requests

from app import theme
from app.api_client import fetch_region_anomaly, fetch_region_trends
from app.charts import anomaly_heatmap, region_comparison_chart
from app.view_model import build_view_model

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def real_view():
    return build_view_model(json.loads((ROOT / "results/regions/phoenix_southeast.json").read_text()))


def test_derived_figures_are_labelled_slope_multiples(real_view):
    assert real_view.per_year_slope == pytest.approx(real_view.slope * 12)
    assert real_view.period_change_estimate == pytest.approx(real_view.slope * 264)
    assert (real_view.months_total, real_view.months_observed) == (264, 261)
    html = theme.facts_html(real_view)
    assert "&times; 12" in html and "not a measured difference" in html
    assert "3 missing months left as gaps, never filled in." in html


def test_heatmap_uses_supplied_anomaly_and_keeps_gaps_blank(real_view):
    figure = anomaly_heatmap(real_view)
    z = figure.data[0].z
    years = list(figure.data[0].y)
    assert len(years) == 22 and all(len(row) == 12 for row in z)
    assert z[years.index("2012")][6] is None  # 2012-07 is a known gap in this box
    supplied = dict(zip(real_view.times, real_view.anomaly))
    assert z[years.index("2003")][0] == supplied["2003-01"]
    assert figure.data[0].hoverongaps is False


def test_heatmap_hidden_without_supplied_anomaly(real_view):
    assert anomaly_heatmap(replace(real_view, anomaly=None)) is None


def test_comparison_and_quarter_map_show_supplied_slopes_with_words():
    trends = {}
    for rid in ("phoenix_study_area", "phoenix_northwest", "phoenix_northeast",
                "phoenix_southwest", "phoenix_southeast"):
        path = ROOT / ("results/results.json" if rid == "phoenix_study_area"
                       else f"results/regions/{rid}.json")
        data = json.loads(path.read_text())
        trends[rid] = {"region": data["region"], **data["trend"]}
    chart = region_comparison_chart(trends, "phoenix_southeast")
    assert sorted(chart.data[0].x) == sorted(t["slope"] for t in trends.values())
    assert all("significant" in label for label in chart.data[0].text)
    html = theme.quarter_map_html(trends, "phoenix_southeast")
    assert html.count('class="estd-tile') == 4 and html.count("estd-tile on") == 1
    assert "slope &times; 12" in html
    assert region_comparison_chart({"a": trends["phoenix_northwest"]}, "a") is None
    assert theme.quarter_map_html({"x": trends["phoenix_northwest"]}, "x") is None


def test_verdict_wording_follows_supplied_significance(real_view):
    assert "statistically significant" in theme.verdict_html(real_view)
    flat = replace(real_view, p=0.05, significant=False)
    assert "not proof of no change" in theme.verdict_html(flat)
    sample = replace(real_view, is_sample=True)
    assert "not NASA observations" in theme.verdict_html(sample)


def test_section_text_is_escaped():
    assert "<b>" not in theme.section_html("<b>k</b>", "<b>t</b>", "<script>x</script>")


def _response(body, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode()
    return result


def test_anomaly_client_rejects_misaligned_months_and_failures(monkeypatch):
    times = ("2003-01", "2003-02")
    good = {"region_id": "r", "series": [{"time": "2003-01", "value": 1.5},
                                         {"time": "2003-02", "value": None}]}
    monkeypatch.setattr(requests.Session, "get", lambda *a, **k: _response(good))
    assert fetch_region_anomaly("https://api.example", "r", times) == (1.5, None)
    assert fetch_region_anomaly("https://api.example", "r", ("2003-01",)) is None
    monkeypatch.setattr(requests.Session, "get", lambda *a, **k: _response({}, 404))
    assert fetch_region_anomaly("https://api2.example", "r", times) is None


def test_region_trends_skip_malformed_entries(monkeypatch):
    regions = {"regions": [
        {"region_id": "a", "region": "A", "trend": {"slope": 0.01, "slope_unit": "degC/month",
                                                   "p": 0.01, "tau": 0.3, "trend": "increasing"}},
        {"region_id": "b", "region": "B"},
    ]}

    def get(session, url, **kwargs):
        return _response({"status": "ok"} if url.endswith("/health") else regions)

    monkeypatch.setattr(requests.Session, "get", get)
    trends = fetch_region_trends("https://api.example")
    assert list(trends) == ["a"] and trends["a"]["slope"] == 0.01


def test_anomaly_switch_matches_data_csvs_for_all_regions_offline():
    """DAT check: every date/value (and gap) per region vs anomaly*.csv and timeseries*.csv."""
    import subprocess
    import sys

    done = subprocess.run([sys.executable, str(ROOT / "scripts/verify_anomaly_view.py"), "--offline"],
                          check=False, capture_output=True, text=True, timeout=300, cwd=ROOT)
    report = json.loads(done.stdout)
    assert done.returncode == 0 and report["pass"], done.stdout[-2000:]
    assert report["regions"]["phoenix_study_area"]["first_anomaly"] == ["2003-01", 2.1392]
    assert report["regions"]["phoenix_study_area"]["first_temperature"] == ["2003-01", 7.7619]
    assert report["regions"]["phoenix_northwest"]["anomaly_gaps"] == ["2024-05"]


def _quarters():
    from app import map3d

    quarters = {}
    for short, name in map3d.QUARTER_NAMES.items():
        data = json.loads((ROOT / f"results/regions/phoenix_{name.lower()}.json").read_text())
        view = build_view_model(data)
        quarters[short] = {"region_id": view.region_id, "label": view.region_label,
                           "times": view.times, "values": view.values, "anomaly": view.anomaly}
    return quarters


def test_map_has_one_bar_per_observed_month_and_none_for_gaps():
    from app import map3d

    quarters = _quarters()
    bars = map3d.month_bars(quarters)
    assert len(bars) == 4 * 264 - 8  # the eight known quarter gaps have no bar
    nw = [b for b in bars if b["quarter"] == "NW"]
    assert "May 2024" not in {b["when"] for b in nw}
    for bar in bars:
        west, south, east, north = map3d.QUARTER_BOUNDS[bar["quarter"]]
        assert west < bar["lon"] < east and south < bar["lat"] < north
    sw = next(b for b in bars if b["quarter"] == "SW" and b["when"] == "Oct 2015")
    assert sw["temp"] == "20.15 °C" and sw["anom"].startswith("+1.83 °C")


def test_latest_mode_uses_newest_observed_month_and_deck_builds():
    from app import map3d

    quarters = _quarters()
    latest = map3d.latest_bars(quarters)
    assert {b["quarter"] for b in latest} == {"NW", "NE", "SW", "SE"}
    assert all("Dec 2024" in b["when"] for b in latest)
    deck = json.loads(map3d.build_deck(quarters, "SE", "months").to_json())
    ids = {layer["id"] for layer in deck["layers"]}
    assert {"bars", "quarters", "freeways"} <= ids
    assert map3d.build_deck(quarters, None, "latest")
