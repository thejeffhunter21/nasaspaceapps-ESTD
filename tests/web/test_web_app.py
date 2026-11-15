"""Map explorer: served by the API, and the grid converter refuses anything it can't verify."""

import csv
import json
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from earth_system_trend.api.app import app

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit


def load_converter():
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_grid_json", ROOT / "scripts/build_grid_json.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_page_and_assets_are_served_without_rate_limit():
    with TestClient(app) as client:
        page = client.get("/app/")
        assert page.status_code == 200 and "Are Phoenix nights getting warmer?" in page.text
        for asset in ("app.js", "styles.css", "vendor/deck.gl-9.4.1.min.js", "assets/phoenix_freeways.json"):
            assert client.get(f"/app/{asset}").status_code == 200, asset
        assert client.get("/explore", follow_redirects=False).headers["location"] == "/app/"
        assert client.get("/").json()["status"] == "ok"  # the API home is unchanged


def test_no_grid_file_is_committed_without_the_data_layer_export():
    grid = ROOT / "web/data/grid.json"
    if grid.exists():  # once real data lands it must carry its provenance and checks
        payload = json.loads(grid.read_text())
        assert payload["data_version"] == "phoenix-qc-v1.0" and "input_sha256" in payload
        assert all(check["max_abs_diff_degC"] <= 0.01 for check in payload["checks"].values())


def test_page_never_offers_a_live_or_forecast_claim():
    text = (ROOT / "web/index.html").read_text() + (ROOT / "web/app.js").read_text()
    assert "Not a forecast" in text and "nothing is filled in" in text.lower()
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
    months_out, cells = conv.read_grid(_write(tmp_path, rows))
    assert months_out == months and cells["b"]["v"]["2003-02"] is None
    report = conv.compare_with_regions(months_out, cells, 0.01, _published(months, rows))
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
        conv.read_grid(_write(tmp_path, rows))


def test_converter_rejects_cells_that_do_not_reproduce_published_series(tmp_path):
    conv = load_converter()
    months = ["2003-01"]
    rows = _cells(months)
    published = _published(months, rows)
    published["NW"]["2003-01"] += 0.5
    months_out, cells = conv.read_grid(_write(tmp_path, rows))
    with pytest.raises(conv.GridError, match="not the published data"):
        conv.compare_with_regions(months_out, cells, 0.01, published)
