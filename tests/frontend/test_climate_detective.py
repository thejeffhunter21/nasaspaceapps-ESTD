"""Guided investigations use local observations and preserve the existing dashboard."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.climate_detective import QUESTIONS, interpret_question, investigate, load_evidence


@pytest.mark.parametrize("question,intent", list(zip(QUESTIONS.values(),
                          ("rank", "compare", "trend", "acceleration"), strict=True)))
def test_workflows(question, intent):
    assert interpret_question(question) == intent
    figure, finding, rows = investigate(intent, load_evidence())
    assert figure.to_json() and finding and rows
    if intent == "rank":
        assert "southeast" in rows[0]["Region"]
        assert "does not establish" in finding
    elif intent == "compare":
        assert any(value is None for trace in figure.data for value in trace.y)
        assert "no statistical comparison" in finding
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
    app = AppTest.from_file(str(path)).run()
    assert not app.exception
    original_charts = len(app.get("plotly_chart"))
    for question in QUESTIONS.values():
        app.text_input(key="detective_question").set_value(question)
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
    app = AppTest.from_file(str(path)).run()
    app.text_input(key="detective_question").set_value(next(iter(QUESTIONS.values())))
    app.button(key="detective_submit").click().run()
    assert not app.exception
    assert any("Local investigation evidence" in item.value for item in app.warning)
    assert app.get("plotly_chart")
