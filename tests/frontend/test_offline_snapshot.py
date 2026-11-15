"""FE-14: approved real snapshots work without an API or fabricated labels."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.offline_snapshot import SnapshotError, load_snapshot

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def snapshot(tmp_path):
    shutil.copytree(ROOT / "results", tmp_path / "results")
    path = tmp_path / "docs/evidence"
    path.mkdir(parents=True)
    shutil.copy(ROOT / "docs/evidence/data_freeze_manifest.json", path)
    return tmp_path


def test_all_five_results_match_approved_files(snapshot):
    bundle = load_snapshot(snapshot)
    assert bundle.freeze_id == "phoenix-qc-v1.0-handoff-1"
    assert len(bundle.results) == 5
    for rid, payload in bundle.results.items():
        path = "results/results.json" if rid == "phoenix_study_area" else f"results/regions/{rid}.json"
        assert payload == json.loads((snapshot / path).read_text())

    # Verify the 8 expected missing months across the 5 verified regions
    expected_gaps = {
        "phoenix_study_area": [],
        "phoenix_northwest": ["2024-05"],
        "phoenix_northeast": ["2007-07", "2023-07"],
        "phoenix_southwest": ["2007-07", "2010-07"],
        "phoenix_southeast": ["2012-07", "2017-07", "2024-06"],
    }
    for rid, gaps in expected_gaps.items():
        payload = bundle.results[rid]
        assert len(payload["series"]) == 264
        actual_gaps = [p["time"] for p in payload["series"] if p["value"] is None]
        assert actual_gaps == gaps, f"Gaps mismatch for {rid}: expected {gaps}, got {actual_gaps}"


@pytest.mark.parametrize("problem", ["missing", "changed", "sample", "region", "manifest"])
def test_invalid_snapshot_fails_closed(snapshot, problem):
    path = snapshot / "results/results.json"
    manifest_path = snapshot / "docs/evidence/data_freeze_manifest.json"
    if problem == "missing":
        path.unlink()
    elif problem == "changed":
        path.write_text(path.read_text() + " ")
    elif problem == "manifest":
        manifest_path.write_text("{}")
    else:
        payload = json.loads(path.read_text())
        payload["source" if problem == "sample" else "region_id"] = (
            "Mock data" if problem == "sample" else "phoenix_northwest")
        path.write_text(json.dumps(payload))
        manifest = json.loads(manifest_path.read_text())
        entry = next(x for x in manifest["analysis_reference_files"] if x["path"] == "results/results.json")
        entry.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
        manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(SnapshotError):
        load_snapshot(snapshot)


def test_offline_page_overrides_live_api_and_switches_without_http(snapshot, monkeypatch):
    monkeypatch.setenv("OFFLINE_SNAPSHOT_DIR", str(snapshot))
    monkeypatch.setenv("API_URL", "https://must-not-be-called.invalid")
    app = AppTest.from_file(str(ROOT / "app/streamlit_app.py")).run()
    assert not app.exception and not app.error and not app.warning
    captions = [c.value for c in app.caption]
    assert "Connection: Offline snapshot" in captions
    assert any("phoenix-qc-v1.0-handoff-1" in c for c in captions)
    assert "Connection: Live API" not in captions
    assert not any(b.label in ("Refresh data", "Retry API") for b in app.button)
    app.selectbox[0].select("phoenix_northwest").run()
    assert not app.exception and not app.error
    payload = load_snapshot(snapshot).results["phoenix_northwest"]
    assert app.subheader[0].value == payload["region"]
    chart = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert chart["data"][0]["y"] == [p["value"] for p in payload["series"]]
    assert chart["data"][0]["connectgaps"] is False
    assert app.text[0].value == payload["explanation"]
    (snapshot / "results/results.json").unlink()
    app.run()
    assert not app.exception and app.error
    assert not app.metric and not app.get("plotly_chart")
    assert [b.label for b in app.button if not (b.key or "").startswith("detective_")] == [
        "Retry snapshot"
    ]


@pytest.mark.parametrize("region_id,expected_gaps", [
    ("phoenix_study_area", 0),
    ("phoenix_northwest", 1),
    ("phoenix_northeast", 2),
    ("phoenix_southwest", 2),
    ("phoenix_southeast", 3),
])
def test_offline_page_switches_all_five_regions(snapshot, monkeypatch, region_id, expected_gaps):
    monkeypatch.setenv("OFFLINE_SNAPSHOT_DIR", str(snapshot))
    monkeypatch.setenv("API_URL", "https://must-not-be-called.invalid")
    app = AppTest.from_file(str(ROOT / "app/streamlit_app.py")).run()
    assert not app.exception and not app.error and not app.warning
    if region_id != "phoenix_study_area":
        app.selectbox[0].select(region_id).run()
        assert not app.exception and not app.error
    payload = load_snapshot(snapshot).results[region_id]
    assert app.subheader[0].value == payload["region"]
    chart = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert len(chart["data"][0]["y"]) == 264
    assert chart["data"][0]["connectgaps"] is False
    assert sum(v is None for v in chart["data"][0]["y"]) == expected_gaps
    assert app.text[0].value == payload["explanation"]
    assert "Automatic summary (AI unavailable)" in [c.value for c in app.caption]
