"""The web explorer's AI Climate Detective must say exactly what the AI layer's code says."""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit

QUESTIONS = [
    "Which region of Phoenix warmed fastest?", "Compare Northeast and Southwest Phoenix.",
    "Has Phoenix warmed significantly since 2003?", "Has Phoenix warming accelerated since 2014?",
    "Which region is hottest?", "Is Tucson warming?", "Predict Phoenix warming",
    "compare northwest and southeast", "Has Phoenix warming accelerated since 2010?",
    "Is Phoenix getting warmer from 2003 to 2024?", "Which region warmed most?",
    "Show me the trend", "", "northeast vs southwest", "Is the southeast warming?",
    "Has Phoenix warmed since 1999?", "What causes warming?",
    "Find a warming pattern that regional averages might hide.",
    "Compare a local observation with its regional average.",
    "Can a regional average hide local warming?",
]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_investigations_match_the_ai_code():
    built = load("build_detective_json", ROOT / "scripts/build_detective_json.py").build()
    committed = json.loads((ROOT / "web/data/detective.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(built, ensure_ascii=False)), (
        "web/data/detective.json is stale: run scripts/build_detective_json.py")
    assert "Gemini is not used" in committed["mode"]
    assert [i["intent"] for i in committed["investigations"]] == ["hidden_pattern", "rank", "local_vs_region", "acceleration"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_web_question_matching_agrees_with_python():
    from app.climate_detective import interpret_question

    script = ("const {interpretQuestion} = require(process.argv[1]);"
              "console.log(JSON.stringify(JSON.parse(process.argv[2]).map(interpretQuestion)));")
    out = subprocess.run(["node", "-e", script, str(ROOT / "web/detective.js"), json.dumps(QUESTIONS)],
                         check=True, capture_output=True, text=True).stdout
    assert json.loads(out) == [interpret_question(q) for q in QUESTIONS]
