"""J1: the contract accepts a good file and rejects each kind of broken file."""

from pathlib import Path

import pytest

from earth_system_trend.contract import ContractError, Results, load_results

pytestmark = pytest.mark.unit
FIXTURES = Path(__file__).parents[1] / "fixtures" / "contract"


def test_valid_file_passes():
    results = load_results(FIXTURES / "valid.json")
    assert isinstance(results, Results)
    assert results.trend.trend == "increasing"


@pytest.mark.parametrize("name, words", [
    ("broken_p_out_of_range", "trend.p"),
    ("broken_tau_out_of_range", "trend.tau"),
    ("broken_bad_trend_word", "trend.trend"),
    ("broken_times_unsorted", "in order"),
    ("broken_times_repeated", "no repeats"),
    ("broken_period_mismatch", "must match"),
    ("broken_missing_trend", "trend"),
    ("broken_bad_source", "explanation_source"),
    ("broken_nan", "NaN"),
    ("broken_infinity", "infinity"),
])
def test_broken_file_fails_with_clear_message(name, words):
    with pytest.raises(ContractError, match=words):
        load_results(FIXTURES / f"{name}.json")


def test_missing_file():
    with pytest.raises(ContractError, match="file not found"):
        load_results(FIXTURES / "nope.json")


def test_bad_json_reports_line():
    with pytest.raises(ContractError, match="line 1"):
        load_results(FIXTURES / "not_json.json")


def test_unknown_field_rejected(tmp_path):
    import json
    data = json.loads((FIXTURES / "valid.json").read_text())
    data["slpoe"] = 1
    path = tmp_path / "r.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ContractError, match="slpoe"):
        load_results(path)
