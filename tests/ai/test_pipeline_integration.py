"""A7: the pipeline uses the AI layer (A4 explain, A5 run_trend) end to end.

No test reaches Gemini: tests/conftest.py strips the key; AI replies here are mocked.
"""

import json
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from earth_system_trend.ai import ai_setup
from earth_system_trend.ai import explain as ai_explain
from earth_system_trend.ai import trend as ai_trend
from earth_system_trend.ai.ai_checks import check_explanation
from earth_system_trend.contract import load_results
from earth_system_trend.pipeline import run as pipeline

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]
COMMITTED = sorted([ROOT / "results" / "results.json", *(ROOT / "results" / "regions").glob("*.json")])


def stub_run(tmp_path, *extra):
    out = tmp_path / "results.json"
    code = pipeline.main(["--stub", "--csv", str(tmp_path / "t.csv"), "--out", str(out), *extra])
    return code, out


def mock_gemini(monkeypatch, content):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "test-flash",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
        })

    monkeypatch.setattr(ai_setup, "OpenAI", lambda **kw: OpenAI(
        http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kw))
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-flash")
    return requests


# --- wiring -----------------------------------------------------------------------------

def test_pipeline_imports_the_ai_layer_not_the_stubs():
    assert pipeline.run_trend is ai_trend.run_trend
    assert pipeline.explain is ai_explain.explain
    assert pipeline.fallback_text is ai_explain.fallback_text
    assert pipeline.METHOD == ai_trend.METHODS["seasonal"]


def test_tests_cannot_reach_gemini():
    import os
    assert not os.environ.get("GEMINI_API_KEY")
    assert "data/cache" not in os.environ["EXPLAIN_CACHE_PATH"]


# --- runs -------------------------------------------------------------------------------

def test_stub_run_without_key_writes_a5_numbers_and_a4_fallback(tmp_path):
    code, out = stub_run(tmp_path)
    assert code == 0
    results = load_results(out)
    values = [p.value for p in results.series]
    expected = ai_trend.run_trend(values)
    assert results.trend.p == expected["p"] > 0  # unrounded
    assert results.trend.slope == expected["slope"]
    assert results.trend.slope_unit == "degC/month"
    assert results.method == ai_trend.METHODS["seasonal"]
    assert results.explanation_source == "fallback"
    assert results.explanation == ai_explain.fallback_text(results.model_dump())
    assert check_explanation(results.explanation, results.model_dump()).ok


def test_checked_gemini_reply_is_written_as_ai(tmp_path, monkeypatch):
    _, out = stub_run(tmp_path)  # first run without AI, to learn the numbers
    draft = load_results(out).model_dump()
    reply = ai_explain.fallback_text(draft).replace("This trend is", "The change is")
    requests = mock_gemini(monkeypatch, reply)
    assert stub_run(tmp_path, "--force")[0] == 0
    results = load_results(out)
    assert results.explanation_source == "ai"
    assert results.explanation == reply
    assert len(requests) == 1


def test_rejected_gemini_reply_is_written_as_fallback(tmp_path, monkeypatch):
    mock_gemini(monkeypatch, "Temperatures soared 4.2 degC per year because of asphalt.")
    code, out = stub_run(tmp_path)
    assert code == 0
    assert load_results(out).explanation_source == "fallback"


def test_ineligible_region_is_skipped_and_others_are_still_written(tmp_path, caplog):
    rows = ["time,value"]
    for i in range(264):
        year, month = 2003 + i // 12, i % 12 + 1
        missing = month == 7 and year < 2016  # 13 Julys gone: 9 valid, need 10
        rows.append(f"{year}-{month:02d},{'' if missing else 20 + 0.01 * i + (month % 6)}")
    (tmp_path / "timeseries_bad.csv").write_text("\n".join(rows) + "\n")
    regions = tmp_path / "regions.json"
    regions.write_text(json.dumps([{"id": "bad", "label": "Bad region"}]))
    out = tmp_path / "results.json"
    pipeline.make_stub_csv(tmp_path / "timeseries.csv")
    with caplog.at_level("ERROR"):
        code = pipeline.main(["--csv", str(tmp_path / "timeseries.csv"), "--out", str(out),
                              "--all-regions", "--regions-file", str(regions)])
    assert code == 1
    assert out.exists()  # main region still built
    assert not (tmp_path / "regions" / "bad.json").exists()
    assert "region bad failed" in caplog.text and "calendar month 7" in caplog.text


# --- committed results ------------------------------------------------------------------

@pytest.mark.parametrize("path", COMMITTED, ids=lambda p: p.stem)
def test_committed_results_come_from_the_ai_layer(path):
    results = load_results(path)
    data = results.model_dump()
    expected = ai_trend.run_trend([p.value for p in results.series])
    assert {k: data["trend"][k] for k in ("slope", "p", "tau", "trend")} == \
        {k: expected[k] for k in ("slope", "p", "tau", "trend")}
    assert data["trend"]["p"] > 0
    assert results.method == ai_trend.METHODS["seasonal"]
    assert check_explanation(results.explanation, data).ok
    if results.explanation_source == "fallback":
        assert results.explanation == ai_explain.fallback_text(data)
