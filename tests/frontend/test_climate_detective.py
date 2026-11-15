"""Offline evidence and UI regression checks for the guided investigation."""
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from climate_detective import (
    QUESTIONS,
    interpret_question,
    investigate,
    load_investigation_data,
)


@pytest.mark.parametrize("question,intent", list(zip(QUESTIONS, (
    "rank_regions", "compare_regions", "describe_trend", "test_hypothesis"), strict=True)))
def test_investigations(question, intent):
    assert interpret_question(question) == intent
    fig, finding, rows = investigate(intent, load_investigation_data())
    assert fig.to_json()
    assert rows and finding
    if intent == "test_hypothesis":
        assert "Inconclusive" in finding
        assert [r["Valid months"] for r in rows] == [132, 132]
    if intent == "rank_regions":
        assert "southeast" in rows[0]["Region"]
        assert "does not establish" in finding
    if intent == "compare_regions":
        assert any(v is None for trace in fig.data for v in trace.y)
        assert rows[0]["Slope (°C/year)"] < rows[1]["Slope (°C/year)"]


@pytest.mark.parametrize("question", [
    "Which region is hottest?", "Is Tucson warming?", "Compare Boston and Phoenix",
    "Has Phoenix warmed since 2020?", "Has warming accelerated since 2000?",
    "Show rainfall in Phoenix", "Compare Northeast and Southeast",
    "Has northeast warming accelerated since 2014?", "Predict Phoenix warming",
])
def test_unsupported(question):
    assert interpret_question(question) is None


def test_ui_offline(monkeypatch):
    monkeypatch.setenv("API_URL", "")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[2] / "app/streamlit_app.py")).run()
    assert not app.exception
    for question in QUESTIONS:
        app.text_input(key="detective_question").set_value(question)
        app.button(key="detective_submit").click().run()
        assert not app.exception
        assert len(app.get("plotly_chart")) == 2  # investigation + original dashboard
        assert any("Key finding" in m.value for m in app.markdown)
    app.text_input(key="detective_question").set_value("Which region is hottest?")
    app.button(key="detective_submit").click().run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 1
