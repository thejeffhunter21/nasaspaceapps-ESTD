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


def _with_anomaly(values):
    import json
    data = json.loads((FIXTURES / "valid.json").read_text())
    data["anomaly"] = [{"time": p["time"], "value": v} for p, v in zip(data["series"], values)]
    return data


def test_anomaly_must_line_up_with_series():
    import json
    data = json.loads((FIXTURES / "valid.json").read_text())
    good = _with_anomaly([None if p["value"] is None else 0.1 for p in data["series"]])
    Results.model_validate(good)
    shifted = _with_anomaly([0.1] * len(data["series"]))
    shifted["anomaly"][0]["time"] = "1999-01"
    with pytest.raises(ValueError, match="same months"):
        Results.model_validate(shifted)


def test_anomaly_null_exactly_where_series_null():
    import json
    data = json.loads((FIXTURES / "valid.json").read_text())
    wrong = _with_anomaly([0.1] * len(data["series"]))  # fills a missing month
    if any(p["value"] is None for p in data["series"]):
        with pytest.raises(ValueError, match="null exactly"):
            Results.model_validate(wrong)
    else:
        wrong["anomaly"][0]["value"] = None
        with pytest.raises(ValueError, match="null exactly"):
            Results.model_validate(wrong)
