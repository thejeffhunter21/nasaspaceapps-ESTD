"""J4: the loader returns the model or a clear ContractError."""

from pathlib import Path

import pytest

from earth_system_trend.api.files import read_results
from earth_system_trend.contract import ContractError, Results

pytestmark = pytest.mark.unit
FIX = Path(__file__).parents[1] / "fixtures"


def test_valid_file_returns_model():
    assert isinstance(read_results(FIX / "api" / "results.json"), Results)


def test_missing_file():
    with pytest.raises(ContractError, match="file not found"):
        read_results(FIX / "api" / "missing.json")


def test_bad_json_reports_line():
    with pytest.raises(ContractError, match="line"):
        read_results(FIX / "contract" / "not_json.json")
