"""FE-10: review the displayed story against the AI owner's result contract."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.review_frontend_story import review_result

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def result():
    return json.loads((ROOT / "results/results.json").read_text())


def test_current_real_result_passes_without_rewriting_explanation(result):
    before = deepcopy(result)
    review = review_result(result)
    assert review["passed"] is True
    assert review["issues"] == []
    assert review["explanation"] == result["explanation"]
    assert review["explanation_source"] == result["explanation_source"]
    assert review["word_count"] < 120
    assert result == before


@pytest.mark.parametrize("problem", ["method", "significance", "cause", "number", "sample", "product"])
def test_inconsistent_story_is_rejected(result, problem):
    if problem == "method":
        result["method"] = "Mann-Kendall test (original) with Sen's slope"
    elif problem == "significance":
        result["trend"]["p"] = 0.5
    elif problem == "cause":
        result["explanation"] += " This happened because of urbanization."
    elif problem == "number":
        result["explanation"] += " Temperature increased by 999 degrees."
    elif problem == "sample":
        result["source"] = "Mock data (not real NASA data)"
    elif problem == "product":
        result["explanation"] += " These are daily air temperatures."
    review = review_result(result)
    assert review["passed"] is False
    assert review["issues"]
