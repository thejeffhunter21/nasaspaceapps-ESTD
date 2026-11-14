"""A3: explanation checks. The AI writes words; every number must come from the results."""

import json
from pathlib import Path

import pytest

from earth_system_trend.ai.ai_checks import MAX_CHARS, check_explanation, is_significant
from earth_system_trend.pipeline.stubs import fallback_text

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]


def make_results(slope=0.007713, p=0.0, tau=0.2893, trend="increasing"):
    """Shaped like results/results.json: 2003-01..2024-12, one missing month."""
    series = [
        {"time": f"{y}-{m:02d}", "value": 20.0 + 0.01 * i}
        for i, (y, m) in enumerate((y, m) for y in range(2003, 2025) for m in range(1, 13))
    ]
    series[50]["value"] = None
    return {
        "region_id": "phoenix_study_area",
        "region": "Phoenix study area",
        "variable": "Nighttime land surface temperature",
        "units": "degC",
        "period": {"start": "2003-01", "end": "2024-12"},
        "series": series,
        "trend": {"slope": slope, "slope_unit": "degC/month", "p": p, "tau": tau, "trend": trend},
        "source": "NASA Terra/MODIS MOD11C3.061 monthly nighttime land surface temperature "
                  "(LST_Night_CMG), 0.05 deg grid, doi:10.5067/MODIS/MOD11C3.061",
        "method": "Seasonal Mann-Kendall test (12-month period) with seasonal Sen's slope",
    }


RESULTS = make_results()
NOT_SIG = make_results(slope=0.0011, p=0.05, tau=0.03, trend="no trend")
DECREASING = make_results(slope=-0.004, p=0.002, tau=-0.21, trend="decreasing")

GOOD = (
    "From 2003-01 to 2024-12, nighttime land surface temperature in the Phoenix study area "
    "rose by about 0.0077 degC per month (roughly 0.093 degC per year, about 2 degC over the "
    "22 years). The increase is statistically significant (p < 0.001, Kendall's tau 0.29) "
    "under a Seasonal Mann-Kendall test."
)


def problems(text, results=RESULTS):
    return " | ".join(check_explanation(text, results).problems)


# --- honest text passes ---------------------------------------------------------------

def test_grounded_explanation_passes():
    check = check_explanation(GOOD, RESULTS)
    assert check.ok, check.problems
    assert check.problems == ()


@pytest.mark.parametrize("path", sorted(
    [ROOT / "results" / "results.json", *(ROOT / "results" / "regions").glob("*.json")]
), ids=lambda p: p.stem)
def test_pipeline_fallback_text_passes_on_every_real_results_file(path):
    """The checks must never reject the deterministic text built from the same numbers."""
    results = json.loads(path.read_text())
    check = check_explanation(fallback_text(results), results)
    assert check.ok, check.problems


def test_not_significant_wording_passes_when_p_is_not_below_alpha():
    text = ("Between 2003-01 and 2024-12 there was no clear warming or cooling trend: the change "
            "of about 0.0011 degC per month is not statistically significant (p = 0.05).")
    assert check_explanation(text, NOT_SIG).ok, problems(text, NOT_SIG)


def test_decreasing_trend_with_matching_words_passes():
    text = ("Temperature fell by about 0.004 degC per month (0.048 degC per year); "
            "the decrease is statistically significant (p = 0.002).")
    assert check_explanation(text, DECREASING).ok, problems(text, DECREASING)


# --- numbers and dates ------------------------------------------------------------------

@pytest.mark.parametrize("text, bad", [
    ("Temperature rose 3.5 degC per year, a significant increase.", "3.5"),
    ("Temperature rose 0.2 degC per year, a significant increase.", "0.2"),
    ("It is significant at 99.9% confidence and rising.", "99.9"),
])
def test_invented_numbers_are_rejected(text, bad):
    assert bad in problems(text)


def test_rounding_tolerance_matches_shown_precision():
    # 0.0926 is slope x 12 = 0.092556 rounded to 4 places; 0.0930 claims more precision.
    assert problems("Rising about 0.0926 degC per year; significant.") == ""
    assert "0.0930" in problems("Rising about 0.0930 degC per year; significant.")


def test_sign_is_not_double_counted_as_a_number():
    assert problems("Rising about +0.0926 degC per year; significant.") == ""


def test_dates_outside_the_data_are_rejected():
    assert "2030-01" in problems("Rising since 2003-01 and by 2030-01 it is significant.")


def test_years_other_than_period_bounds_are_rejected():
    assert "2010" in problems("Rising strongly since 2010; significant.")


def test_numbers_from_source_and_method_are_allowed():
    text = ("Based on MODIS MOD11C3.061 at 0.05 deg and a 12-month Seasonal Mann-Kendall test, "
            "temperature is rising; the trend is significant.")
    assert problems(text) == ""


def test_fahrenheit_conversion_is_rejected():
    assert "unit" in problems("Rising about 0.17 °F per year; significant.").lower()


# --- significance -----------------------------------------------------------------------

@pytest.mark.parametrize("p, expected", [
    (0.0, True), (0.049, True), (0.0499999, True), (0.05, False), (0.051, False), (0.9, False),
])
def test_is_significant_uses_strict_less_than_on_unrounded_p(p, expected):
    assert is_significant(p) is expected


def test_claiming_significance_when_p_equals_alpha_is_rejected():
    text = "A statistically significant warming trend (p = 0.05)."
    assert "significan" in problems(text, NOT_SIG)


def test_denying_significance_when_p_is_small_is_rejected():
    assert "significan" in problems("Rising, but not statistically significant.")


@pytest.mark.parametrize("text", ["insignificant", "non-significant", "isn't significant"])
def test_negated_forms_are_recognised(text):
    assert problems(f"The change is {text}.", NOT_SIG) == ""


# --- direction --------------------------------------------------------------------------

@pytest.mark.parametrize("word", ["cooling", "decreasing", "falling", "declined"])
def test_increasing_trend_cannot_be_described_as_going_down(word):
    assert "direction" in problems(f"Temperature is {word}; significant.")


@pytest.mark.parametrize("word", ["warming", "increasing", "rising"])
def test_decreasing_trend_cannot_be_described_as_going_up(word):
    assert "direction" in problems(f"Temperature is {word}; significant.", DECREASING)


def test_no_trend_cannot_claim_a_direction():
    text = "There is a warming trend, not statistically significant."
    assert "direction" in problems("A clear warming trend; not significant.", NOT_SIG)
    assert problems(text, NOT_SIG)  # "warming trend" stated as fact


# --- claims the data cannot support (frontend plan rules) --------------------------------

@pytest.mark.parametrize("phrase", [
    "due to urban growth", "because of climate change", "caused by asphalt",
    "driven by the urban heat island", "attributed to development",
])
def test_causes_are_rejected(phrase):
    assert "cause" in problems(f"Temperature is rising {phrase}; significant.")


@pytest.mark.parametrize("phrase", [
    "and will keep rising", "and is forecast to rise", "and we predict more heat",
    "and next year will be hotter", "in the future too",
])
def test_forecasts_are_rejected(phrase):
    assert "forecast" in problems(f"Temperature is rising {phrase}; significant.")


@pytest.mark.parametrize("phrase", [
    "Planners should add shade.", "Farmers must irrigate earlier.", "We recommend cool roofs.",
])
def test_advice_is_rejected(phrase):
    assert "advice" in problems(f"Temperature is rising; significant. {phrase}")


@pytest.mark.parametrize("phrase", ["air temperature", "daily"])
def test_wrong_data_product_is_rejected(phrase):
    assert "product" in problems(f"The {phrase} trend is rising; significant.")


# --- shape and robustness ---------------------------------------------------------------

@pytest.mark.parametrize("text", ["", "   ", None, 42])
def test_empty_or_non_text_is_rejected(text):
    check = check_explanation(text, RESULTS)
    assert not check.ok
    assert "empty" in " ".join(check.problems)


def test_too_long_is_rejected():
    text = "Temperature is rising; significant. " * (MAX_CHARS // 30)
    assert len(text) > MAX_CHARS
    assert "long" in problems(text)


@pytest.mark.parametrize("results", [{}, {"trend": {}}, None, {"trend": {"p": "x"}}])
def test_malformed_results_fail_closed_without_raising(results):
    check = check_explanation(GOOD, results)
    assert not check.ok
    assert check.problems


def test_all_problems_are_reported_together():
    text = "Cooling 3.5 degC per year due to traffic; it will continue. Not significant."
    found = problems(text)
    for word in ("3.5", "direction", "cause", "forecast", "significan"):
        assert word in found
