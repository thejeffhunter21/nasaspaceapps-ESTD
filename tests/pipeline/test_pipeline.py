"""Pipeline: CSV checks, a stub run makes a valid file, skip / --force, regions."""

import json
import os
import time

import pytest

from earth_system_trend.contract import load_results
from earth_system_trend.pipeline.run import main, make_stub_csv
from earth_system_trend.pipeline.timeseries import SeriesError, load_series

pytestmark = pytest.mark.unit


def csv(tmp_path, text, name="t.csv"):
    path = tmp_path / name
    path.write_text(text)
    return path


def months(n, start=2003):
    return [f"{start + i // 12}-{i % 12 + 1:02d}" for i in range(n)]


def test_fills_gap_and_sorts(tmp_path):
    rows = [f"{m},{i}" for i, m in enumerate(months(30))]
    del rows[5]
    rows.reverse()
    got_months, values = load_series(csv(tmp_path, "time,value\n" + "\n".join(rows)))
    assert got_months[:7] == months(7)
    assert values[5] is None and len(values) == 30


@pytest.mark.parametrize("text, words", [
    ("time,val\n2003-01,1", "missing column 'value'"),
    ("time,value\nbanana,1", "unreadable date"),
    ("time,value\n2003-01,1\n2003-01,2", "duplicate month"),
    ("time,value\n" + "\n".join(f"{m},1" for m in months(10)), "not enough data"),
])
def test_bad_csv(tmp_path, text, words):
    with pytest.raises(SeriesError, match=words):
        load_series(csv(tmp_path, text))


def test_missing_file(tmp_path):
    with pytest.raises(SeriesError, match="file not found"):
        load_series(tmp_path / "nope.csv")


def test_stub_run_writes_valid_file(tmp_path):
    out = tmp_path / "results.json"
    assert main(["--stub", "--csv", str(tmp_path / "t.csv"), "--out", str(out)]) == 0
    results = load_results(out)
    assert results.trend.trend == "increasing"
    assert results.explanation_source == "fallback"
    assert len(results.series) == 22 * 12


def test_second_run_skipped_unless_force(tmp_path, caplog):
    c, out = tmp_path / "t.csv", tmp_path / "r.json"
    make_stub_csv(c)
    main(["--csv", str(c), "--out", str(out)])
    first = out.stat().st_mtime
    time.sleep(0.05)
    main(["--csv", str(c), "--out", str(out)])
    assert out.stat().st_mtime == first
    main(["--csv", str(c), "--out", str(out), "--force"])
    assert out.stat().st_mtime > first


def test_all_regions(tmp_path):
    c = tmp_path / "timeseries.csv"
    make_stub_csv(c)
    make_stub_csv(tmp_path / "timeseries_north.csv", seed=1)
    (tmp_path / "regions.json").write_text(json.dumps(
        [{"id": "north", "label": "North box"}, {"id": "ghost", "label": "Ghost"}]))
    out = tmp_path / "results" / "results.json"
    code = main(["--csv", str(c), "--out", str(out), "--all-regions",
                 "--regions-file", str(tmp_path / "regions.json")])
    assert code == 1  # ghost has no CSV
    assert load_results(out.parent / "regions" / "north.json").region == "North box"
    assert not os.path.exists(out.parent / "regions" / "ghost.json")


def test_accepts_old_date_column(tmp_path):
    text = "date,value\n" + "\n".join(f"{m},{i}" for i, m in enumerate(months(24)))
    assert len(load_series(csv(tmp_path, text))[0]) == 24
