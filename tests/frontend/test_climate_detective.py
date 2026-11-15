"""Guided investigations use local observations and preserve the existing dashboard."""
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from climate_detective import QUESTIONS, interpret_question, load_evidence, run_discovery


@pytest.mark.parametrize("question,intent", list(zip(QUESTIONS.values(),
                          ("hidden_pattern", "rank", "local_vs_region", "acceleration"), strict=True)))
def test_workflows(question, intent):
    assert interpret_question(question) == intent
    result = run_discovery(intent, load_evidence())
    figure, finding, rows = result["figure"], result["finding"], result["rows"]
    assert figure.to_json() and finding and rows
    if intent == "rank":
        assert "southeast" in rows[0]["Region"]
        assert "does not establish" in finding
    elif intent in ("hidden_pattern", "local_vs_region"):
        assert result["metadata"]["Cells examined"] == 192
        assert result["metadata"]["Cell-month positions retrieved"] == 50688
        assert rows[0]["Cell ID"] == result["metadata"]["Selected cell"]
        assert rows[0]["Slope difference (°C/year)"] == pytest.approx(
            rows[0]["Slope (°C/year)"] - rows[1]["Slope (°C/year)"])
        assert "exploratory" in result["challenge"]
        assert "not established" in result["conclusion"]
        assert any(value is None for trace in figure.data for value in trace.y)
    elif intent == "acceleration":
        assert "Inconclusive" in finding
        assert [row["Valid months"] for row in rows] == [132, 132]
        assert rows[0]["Period"] == "2003-01 to 2013-12"
        assert rows[1]["Period"] == "2014-01 to 2024-12"


@pytest.mark.parametrize("question", (
    "Which region is hottest?", "Is Tucson warming?", "Predict Phoenix warming",
    "Compare Boston and Phoenix", "Has Phoenix warmed since 2020?",
    "Compare Northeast and Southeast", "Has Northeast warming accelerated since 2014?",
    "Has warming accelerated since 2000?", "Show rainfall in Phoenix",
))
def test_reject_unsupported(question):
    assert interpret_question(question) is None


def test_offline_ui():
    path = Path(__file__).resolve().parents[2] / "app/streamlit_app.py"
    app = AppTest.from_file(str(path), default_timeout=10).run()
    assert not app.exception
    original_charts = len(app.get("plotly_chart"))
    for label, question in QUESTIONS.items():
        app.button(key=f"detective_{label}").click().run()
        assert app.text_input(key="detective_question").value == question
        app.button(key="detective_submit").click().run()
        assert not app.exception
        assert len(app.get("plotly_chart")) == original_charts + 1
        assert any("Key finding" in item.value for item in app.markdown)
    app.text_input(key="detective_question").set_value("Which region is hottest?")
    app.button(key="detective_submit").click().run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == original_charts


def test_missing_evidence_does_not_break_dashboard(monkeypatch):
    import climate_detective

    def unavailable():
        raise OSError("Missing results")

    monkeypatch.setattr(climate_detective, "load_evidence", unavailable)
    path = Path(__file__).resolve().parents[2] / "app/streamlit_app.py"
    app = AppTest.from_file(str(path), default_timeout=10).run()
    app.text_input(key="detective_question").set_value(next(iter(QUESTIONS.values())))
    app.button(key="detective_submit").click().run()
    assert not app.exception
    assert any("Local investigation evidence" in item.value for item in app.warning)
    assert app.get("plotly_chart")


def test_grid_missing_or_invalid_uses_visible_regional_fallback(monkeypatch):
    import climate_detective

    def invalid(*args):
        raise ValueError("Unapproved file")

    monkeypatch.setattr(climate_detective, "retrieve_cells", invalid)
    result = run_discovery("hidden_pattern", load_evidence())
    assert "Grid status" in result["metadata"]
    assert "Cells examined" not in result["metadata"]
    assert all("Cell ID" not in row for row in result["rows"])
    assert "regional warming rate" in result["finding"]


def test_grid_provenance_rejects_tampering():
    from discovery_evidence import retrieve_cells

    processed = Path(__file__).resolve().parents[2] / "data/processed"
    content = (processed / "grid_cells.csv").read_bytes()
    manifest = (processed / "grid_cells_manifest.json").read_bytes()
    with pytest.raises(ValueError, match="provenance"):
        retrieve_cells(content + b"\n", manifest)


def test_cells_preserve_calendar_gaps_and_selection_is_reproducible():
    from discovery_evidence import calculate_cell_trends, retrieve_cells, select_cell

    from earth_system_trend.ai.trend import run_trend

    processed = Path(__file__).resolve().parents[2] / "data/processed"
    cells, manifest = retrieve_cells((processed / "grid_cells.csv").read_bytes(),
                                    (processed / "grid_cells_manifest.json").read_bytes())
    assert sum(p["value"] is None for c in cells.values() for p in c["series"]) == 412
    assert all(len(c["series"]) == 264 for c in cells.values())
    trends = calculate_cell_trends(cells)
    cell, trend, region, delta = select_cell(cells, trends, load_evidence())
    assert trend == run_trend([p["value"] for p in cell["series"]], method="seasonal")
    assert delta == pytest.approx((trend["slope"] - region["trend"]["slope"]) * 12)
    assert len(cells) == manifest["validation"]["cells"]
