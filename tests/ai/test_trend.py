"""A5: run_trend(values, method, alpha) - the AI layer's trend test.

Contract: slope per month, slope_unit, p (unrounded), tau, trend. Missing months are None and
keep their calendar positions.
"""

import json
import math
from pathlib import Path

import numpy as np
import pymannkendall as mk
import pytest

from earth_system_trend.ai.trend import (
    MIN_VALID_MONTHS,
    MIN_YEARS_PER_CALENDAR_MONTH,
    TrendInputError,
    run_trend,
)
from earth_system_trend.contract import Trend
from earth_system_trend.pipeline import stubs

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]
RESULT_FILES = {
    "study_area": ROOT / "results" / "results.json",
    **{r: ROOT / "results" / "regions" / f"phoenix_{r}.json"
       for r in ("northwest", "northeast", "southwest", "southeast")},
}
KEYS = {"slope", "slope_unit", "p", "tau", "trend"}


def series(name):
    return [p["value"] for p in json.loads(RESULT_FILES[name].read_text())["series"]]


def synthetic(slope=0.01, n=264, gaps=(54, 162, 245), noise=0.3, seed=0):
    """Known per-month slope + 10 degC seasonal cycle + noise + missing months."""
    rng = np.random.default_rng(seed)
    i = np.arange(n)
    x = 20 + slope * i + 10 * np.sin(2 * np.pi * i / 12) + rng.normal(0, noise, n)
    return [None if k in gaps else float(v) for k, v in enumerate(x)]


# --- shape ------------------------------------------------------------------------------

@pytest.mark.parametrize("method", ["seasonal", "original"])
def test_output_has_exactly_the_contract_keys_and_validates(method):
    out = run_trend(series("southeast"), method=method)
    assert set(out) == KEYS
    assert out["slope_unit"] == "per month"
    assert all(math.isfinite(out[k]) for k in ("slope", "p", "tau"))
    Trend.model_validate(out)


def test_input_is_not_modified():
    values = series("northeast")
    before = list(values)
    run_trend(values)
    assert values == before


# --- real data --------------------------------------------------------------------------

@pytest.mark.parametrize("name", RESULT_FILES)
def test_matches_the_pipeline_stub_on_real_data_but_p_is_not_rounded(name):
    values = series(name)
    ours, stub = run_trend(values), stubs.run_trend(values)
    assert ours["trend"] == stub["trend"] == "increasing"
    assert abs(ours["slope"] - stub["slope"]) < 1e-6  # stub rounds slope to 6 dp
    assert abs(ours["tau"] - stub["tau"]) < 1e-4  # stub rounds tau to 4 dp
    assert 0 < ours["p"] < 1e-5  # stub stores 0.0 or 4e-06


@pytest.mark.parametrize("name, expected", [
    ("study_area", 7.02e-11), ("northeast", 3.80e-06), ("southeast", 2.78e-14),
])
def test_unrounded_p_values(name, expected):
    assert math.isclose(run_trend(series(name))["p"], expected, rel_tol=0.01)


def test_p_matches_the_library_where_the_library_is_precise():
    values = series("northeast")
    lib = mk.seasonal_test(np.array([np.nan if v is None else v for v in values]), period=12)
    assert math.isclose(run_trend(values)["p"], lib.p, rel_tol=1e-6)


def test_seasonal_finds_the_warming_the_plain_test_misses():
    values = series("study_area")
    assert run_trend(values, method="seasonal")["trend"] == "increasing"
    plain = run_trend(values, method="original")
    assert plain["trend"] == "no trend"
    assert math.isclose(plain["p"], 0.199, abs_tol=0.001)


@pytest.mark.parametrize("name", ["northwest", "southwest", "southeast"])
def test_gaps_keep_their_positions(name):
    values = series(name)
    kept = run_trend(values)["slope"]
    dropped = [v for v in values if v is not None]
    shifted = run_trend(dropped + [None] * (len(values) - len(dropped)))["slope"]
    assert abs(kept - shifted) > 0.001  # dropping gaps would move months into wrong columns


# --- known answers ----------------------------------------------------------------------

def test_recovers_a_known_seasonal_slope_per_month():
    out = run_trend(synthetic(slope=0.01))
    assert out["trend"] == "increasing"
    assert abs(out["slope"] - 0.01) < 0.0005


def test_recovers_a_known_decreasing_slope():
    out = run_trend(synthetic(slope=-0.008, seed=1))
    assert out["trend"] == "decreasing"
    assert out["tau"] < 0
    assert abs(out["slope"] + 0.008) < 0.0005


def test_original_method_slope_is_per_month_on_a_series_without_a_cycle():
    rng = np.random.default_rng(2)
    values = [float(0.02 * i + rng.normal(0, 0.2)) for i in range(120)]
    values[30] = None
    out = run_trend(values, method="original")
    assert out["trend"] == "increasing"
    assert abs(out["slope"] - 0.02) < 0.001


def test_no_trend_in_pure_noise_with_a_cycle():
    out = run_trend(synthetic(slope=0.0, noise=1.0, seed=3))
    assert out["trend"] == "no trend"
    assert out["p"] >= 0.05


def test_flat_series_has_no_trend():
    out = run_trend([15.0] * 264)
    assert out == {"slope": 0.0, "slope_unit": "per month", "p": 1.0, "tau": 0.0,
                   "trend": "no trend"}


# --- significance rule ------------------------------------------------------------------

@pytest.mark.parametrize("name", RESULT_FILES)
@pytest.mark.parametrize("method", ["seasonal", "original"])
def test_direction_word_follows_strict_p_below_alpha(name, method):
    out = run_trend(series(name), method=method)
    assert (out["trend"] != "no trend") == (out["p"] < 0.05)
    if out["trend"] != "no trend":
        assert (out["trend"] == "increasing") == (out["tau"] > 0)


def test_alpha_is_used():
    values = series("study_area")  # p is about 7e-11
    assert run_trend(values, alpha=1e-6)["trend"] == "increasing"
    assert run_trend(values, alpha=1e-12)["trend"] == "no trend"


def test_p_equal_to_alpha_is_not_significant():
    values = series("study_area")
    p = run_trend(values)["p"]
    assert run_trend(values, alpha=p)["trend"] == "no trend"


# --- eligibility and bad input ----------------------------------------------------------

def test_too_few_valid_months_is_rejected():
    values = synthetic()[:MIN_VALID_MONTHS - 1]
    with pytest.raises(TrendInputError, match="valid months"):
        run_trend(values, method="original")


def test_calendar_month_with_too_few_years_is_rejected_for_seasonal():
    values = synthetic(gaps=())  # default gaps include two Julys
    july = range(6, 264, 12)
    for k in list(july)[:22 - MIN_YEARS_PER_CALENDAR_MONTH + 1]:
        values[k] = None  # leaves MIN_YEARS_PER_CALENDAR_MONTH - 1 valid Julys
    with pytest.raises(TrendInputError, match="calendar month 7"):
        run_trend(values)
    run_trend(values, method="original")  # the plain test has no per-month rule


def test_calendar_month_at_the_minimum_is_accepted():
    values = synthetic(gaps=())  # default gaps include two Julys
    for k in list(range(6, 264, 12))[:22 - MIN_YEARS_PER_CALENDAR_MONTH]:
        values[k] = None
    assert run_trend(values)["trend"] == "increasing"


def test_numpy_nan_counts_as_missing():
    values = synthetic()
    with_nan = [math.nan if v is None else v for v in values]
    assert run_trend(with_nan) == run_trend(values)


@pytest.mark.parametrize("bad", [math.inf, -math.inf, "warm", True])
def test_non_numeric_or_infinite_values_are_rejected(bad):
    values = synthetic()
    values[10] = bad
    with pytest.raises(TrendInputError, match="position 10"):
        run_trend(values)


@pytest.mark.parametrize("kwargs, match", [
    ({"method": "hamed_rao"}, "method"),
    ({"alpha": 0}, "alpha"), ({"alpha": 1}, "alpha"), ({"alpha": -0.1}, "alpha"),
])
def test_bad_arguments_are_rejected(kwargs, match):
    with pytest.raises(ValueError, match=match):
        run_trend(synthetic(), **kwargs)


def test_trend_input_error_is_a_value_error():
    assert issubclass(TrendInputError, ValueError)


# --- fits the rest of the AI layer ------------------------------------------------------

@pytest.mark.parametrize("name", RESULT_FILES)
def test_results_built_from_a5_still_explain_and_pass_checks(name):
    """When the pipeline switches to A5 (unrounded p), A4's fallback must still pass A3."""
    from earth_system_trend.ai.ai_checks import check_explanation
    from earth_system_trend.ai.explain import build_messages, fallback_text

    results = json.loads(RESULT_FILES[name].read_text())
    trend = run_trend(series(name))
    results["trend"] = {**trend, "slope_unit": f"{results['units']}/month"}
    text = fallback_text(results)
    assert check_explanation(text, results).ok, check_explanation(text, results).problems
    assert "p < 0.001" in text
    build_messages(results)  # prompt facts can be built from A5 output
