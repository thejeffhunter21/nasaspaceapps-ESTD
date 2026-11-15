"""Map explorer: served by the API, and the grid converter refuses anything it can't verify."""

import csv
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from earth_system_trend.api.app import app

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit


def load_converter():
    from earth_system_trend.analysis import grid

    return grid


def test_page_and_assets_are_served_without_rate_limit():
    with TestClient(app) as client:
        page = client.get("/app/")
        assert page.status_code == 200 and "Are Phoenix nights getting warmer?" in page.text
        for asset in ("app.js", "styles.css", "vendor/deck.gl-9.4.1.min.js", "assets/phoenix_freeways.json"):
            assert client.get(f"/app/{asset}").status_code == 200, asset
        assert client.get("/explore", follow_redirects=False).headers["location"] == "/app/"
        assert client.get("/").json()["status"] == "ok"  # the API home is unchanged


def test_raw_grid_cells_are_never_in_the_public_web_folder():
    """The per-cell dataset is server-side only (private /analysis service)."""
    public = [p.name for p in (ROOT / "web").rglob("*") if p.is_file()]
    assert not any("grid" in name for name in public), public
    with TestClient(app) as client:
        assert client.get("/app/data/grid.json").status_code == 404


def test_page_never_offers_a_live_or_forecast_claim():
    text = (ROOT / "web/index.html").read_text() + (ROOT / "web/app.js").read_text()
    assert "Not a forecast" in text
    assert "annual mean only with all 12 months" in text


def _write(tmp_path, rows):
    path = tmp_path / "grid_cells.csv"
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["cell_id", "lat", "lon", "quarter", "date", "value"])
        writer.writerows(rows)
    return path


def _cells(months, value=lambda c, d: 20.0):
    rows = []
    for cid, lat, lon, q in (("a", 33.775, -112.375, "NW"), ("b", 33.775, -111.625, "NE"),
                             ("c", 33.225, -112.375, "SW"), ("d", 33.225, -111.625, "SE")):
        rows += [[cid, lat, lon, q, d, value(cid, d)] for d in months]
    return rows


def _published(months, rows):
    by = {}
    for cid, lat, _lon, q, d, v in rows:
        if v != "":
            by.setdefault(("ALL", d), []).append((v, lat))
            by.setdefault((q, d), []).append((v, lat))
    out = {}
    for key in ("ALL", "NW", "NE", "SW", "SE"):
        out[key] = {}
        for d in months:
            vals = by.get((key, d))
            out[key][d] = (sum(v * math.cos(math.radians(la)) for v, la in vals)
                           / sum(math.cos(math.radians(la)) for _, la in vals)) if vals else None
    return out


def test_converter_accepts_consistent_cells_and_keeps_gaps(tmp_path):
    conv = load_converter()
    months = ["2003-01", "2003-02", "2003-03"]
    rows = _cells(months, lambda c, d: "" if (c, d) == ("b", "2003-02") else 20.0 + months.index(d))
    months_out, cells = conv.read_cells(_write(tmp_path, rows))
    assert months_out == months and cells["b"]["v"]["2003-02"] is None
    report = conv.compare_with_regions(months_out, cells, _published(months, rows), 0.01)
    assert report["NE"]["not_compared"] == ["2003-02"]


@pytest.mark.parametrize("problem", ["duplicate", "missing_month", "wrong_quarter", "off_grid", "implausible"])
def test_converter_rejects_bad_exports(tmp_path, problem):
    conv = load_converter()
    months = ["2003-01", "2003-02"]
    rows = _cells(months)
    if problem == "duplicate":
        rows.append(rows[0])
    elif problem == "missing_month":
        rows = [r for r in rows if not (r[0] == "a" and r[4] == "2003-02")]
    elif problem == "wrong_quarter":
        rows = [[*r[:3], "SE", *r[4:]] if r[0] == "a" else r for r in rows]
    elif problem == "off_grid":
        rows = [[r[0], 33.76, *r[2:]] if r[0] == "a" else r for r in rows]
    else:
        rows[0][5] = 999
    with pytest.raises(conv.GridError):
        conv.read_cells(_write(tmp_path, rows))


def test_converter_rejects_cells_that_do_not_reproduce_published_series(tmp_path):
    conv = load_converter()
    months = ["2003-01"]
    rows = _cells(months)
    published = _published(months, rows)
    published["NW"]["2003-01"] += 0.5
    months_out, cells = conv.read_cells(_write(tmp_path, rows))
    with pytest.raises(conv.GridError, match="not the published data"):
        conv.compare_with_regions(months_out, cells, published, 0.01)


def test_page_reads_one_frame_at_a_time_and_never_the_raw_file():
    js = (ROOT / "web/app.js").read_text()
    assert "/map-frame?year=" in js and "grid_cells" not in js.replace("grid_cells.csv sha256", "")
    assert "only the settled frame is data" in js  # eased transitions are labelled, never presented as data


def test_share_links_never_carry_secrets():
    js = (ROOT / "web/app.js").read_text()
    assert "ANALYSIS_TOKEN" not in js and "X-Analysis-Token" not in js


def test_tour_methodology_and_outline_are_wired():
    html = (ROOT / "web/index.html").read_text()
    assert 'src="tour.js"' in html and "data-tour-start" in html
    assert 'id="method"' in html and 'id="provenance"' in html and "doi:10.5067" not in html  # DOI is built in app.js
    tour = (ROOT / "web/tour.js").read_text()
    assert tour.count("title:") == 6 and "There is no saved notebook yet" in tour
    import json
    outline = json.loads((ROOT / "web/assets/phoenix_urban_area.json").read_text())
    assert set(outline["quarters"]) == {"NW", "NE", "SW", "SE"} and len(outline["inside_cells"]) == 88
    assert "visual" in outline["note"].lower()


def test_nav_png_and_keyboard_are_wired():
    html = (ROOT / "web/index.html").read_text()
    js = (ROOT / "web/app.js").read_text()
    assert 'id="case-nav"' in html and 'data-go="map"' in html and 'id="png"' in html
    assert 'tabindex="0"' in html and 'id="cell-live"' in html
    assert "function downloadPng" in js and "function onMapKey" in js and "function setupNav" in js


def test_map_first_layout_keeps_one_map_and_moves_the_science_into_drawers():
    """One map; regions, Compare and Data information open from it; only the AI section stays below."""
    html = (ROOT / "web/index.html").read_text()
    js = (ROOT / "web/app.js").read_text()
    for control in ('id="tb-info"', 'id="tb-compare"', 'id="tb-legend"', 'id="tb-reset"'):
        assert control in html
    assert 'id="info-drawer" hidden' in html and 'id="compare-drawer" hidden' in html
    story = html[html.index('<main id="story"'):]
    assert 'id="discoveries"' in story and 'id="ask"' in story
    for moved in ('id="method"', 'id="provenance"', 'id="coverage"', 'id="compare"', 'id="findings-body"'):
        assert moved in html and moved not in story          # still available, no longer a page section
    assert html.count('id="map"') == 1
    assert "function renderRegionPanel" in js and "function resetView" in js and "function openDrawer" in js
    assert 'id="panels"' in html and "function placePanels" in js    # the scroll split and its quarter panels stay
    # Reset view clears temporary selections only: it never touches year, month or layer.
    reset = js[js.index("function resetView"):js.index("function setupChrome")]
    assert 'region: "all"' in reset and "cell: null" in reset and "finding: null" in reset
    assert "year" not in reset and "month" not in reset and "layer:" not in reset
    assert "outline only, not a measurement" in js           # AI highlights are labelled apart from data


def test_discovery_engine_scripts_the_workflow_but_never_the_numbers():
    """The prototype engine hard-codes the workflow and routing; every value is read from the API."""
    html = (ROOT / "web/index.html").read_text()
    js = (ROOT / "web/app.js").read_text()
    assert "AI Scientific Discovery Engine" in html and "Prototype Discovery Engine" in html
    assert "deterministic investigation workflows" in html      # the disclosure stays visible
    engine = js[js.index("function detectDemoIntent"):js.index("function buildDiscoveries")]
    for intent in ("hidden_pattern", "rank_regions", "local_vs_region", "trend_acceleration", "unsupported"):
        assert intent in engine
    assert "INCONCLUSIVE" in engine and "No vector database or language model runs here" in engine
    assert "/region-compare" in engine and "/cell-years" in engine     # real tests, not typed-in results
    import re
    # no result typed in: no cell ids and no trend-sized decimals (0.0xx / 0.1xx) appear in the engine code
    assert not re.search(r"r\d{2}_c\d{2}", engine)
    assert not re.search(r"[+−-]0\.[01]\d{2}", engine)
