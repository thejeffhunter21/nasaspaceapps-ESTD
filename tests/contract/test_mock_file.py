"""J2: the mock file everyone builds against is valid and obviously fake."""

from pathlib import Path

import pytest

from earth_system_trend.contract import load_results

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]


def test_mock_file_is_valid_and_long_enough():
    results = load_results(ROOT / "results.mock.json")
    assert len(results.series) >= 24
    assert results.region == "Example Region"
    assert "mock" in results.source.lower()
