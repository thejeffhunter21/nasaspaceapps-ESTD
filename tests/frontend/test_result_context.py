"""FE-06: distinguish connection mode, sample data and explanation source."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.frontend.test_api_page import backend as backend  # noqa: PLC0414 - re-export fixture

pytestmark = pytest.mark.unit
APP = Path(__file__).resolve().parents[2] / "app/streamlit_app.py"
FALLBACK_LABEL = "Automatic summary"


def captions(app):
    return [item.value for item in app.caption]


def test_offline_sample_and_fallback_are_independently_labeled():
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert "Connection: Offline preview" in captions(app)
    assert any("Sample data" in item.value for item in app.warning)
    assert FALLBACK_LABEL in captions(app)
    assert "Connection: Live API" not in captions(app)


def test_live_non_mock_ai_explanation_and_supplied_metadata(backend):
    backend["payload"].update(explanation_source="ai", source="Supplied source credit",
                             method="Supplied statistical method")
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert "Connection: Live API" in captions(app)
    assert not app.warning
    assert "AI-assisted explanation" in captions(app)
    assert FALLBACK_LABEL not in captions(app)
    assert app.text[0].value == backend["payload"]["explanation"]
    details = app.expander[0]
    assert details.label == "Source, method and definitions"
    assert [c.value for c in details.caption] == [
        "Source: Supplied source credit", "Method: Supplied statistical method",
        "Period: 2003-01 to 2005-12",
    ]


def test_live_mock_data_keeps_sample_warning_and_fallback_label(backend):
    backend["payload"].update(region="Example Region", source="Mock data")
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert "Connection: Live API" in captions(app)
    assert any("Sample data" in item.value for item in app.warning)
    assert FALLBACK_LABEL in captions(app)


def test_sample_recovery_and_retry_update_connection_indicators(backend):
    backend["fail"] = True
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert "Connection: Live API" not in captions(app)
    next(b for b in app.button if b.label == "Use sample data").click().run()
    assert not app.exception
    assert "Connection: Offline preview" in captions(app)
    assert any("Sample data" in item.value for item in app.warning)
    backend["fail"] = False
    next(b for b in app.button if b.label == "Retry API").click().run()
    assert not app.exception
    assert "Connection: Live API" in captions(app)
    assert "Connection: Offline preview" not in captions(app)
    assert not app.warning
