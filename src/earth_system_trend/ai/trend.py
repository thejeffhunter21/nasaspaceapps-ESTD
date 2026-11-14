"""A5: run_trend(values, method, alpha) - the AI layer's trend test (contract signature).

values: the full monthly calendar in order, None (or NaN) for a missing month. Gaps are never
dropped: positions decide which calendar month and year each value belongs to.

method:
  "seasonal" (default) - Seasonal Mann-Kendall (12-month period) + seasonal Sen's slope.
                         Compares each calendar month only with the same month in other years.
                         The library slope is per year; divided by 12 here to give per month.
  "original"           - plain Mann-Kendall + Sen's slope, already per month (one step = one month).

Returns {"slope", "slope_unit", "p", "tau", "trend"}, unrounded. slope_unit is "per month"; the
pipeline replaces it with "<units>/month". trend is "increasing"/"decreasing" only if p < alpha.
See docs/ai.md for the method, eligibility and serial-dependence notes.
"""

from __future__ import annotations

import math
from numbers import Real
from typing import Any

import numpy as np
import pymannkendall as mk
from scipy.stats import norm

from earth_system_trend.ai.ai_checks import ALPHA, is_significant

PERIOD = 12
MIN_VALID_MONTHS = 24  # same floor as pipeline/timeseries.py
MIN_YEARS_PER_CALENDAR_MONTH = 10  # seasonal test: every calendar month needs this many years
METHODS = {
    "seasonal": "Seasonal Mann-Kendall test (12-month period) with seasonal Sen's slope",
    "original": "Mann-Kendall test (original) with Sen's slope",
}


class TrendInputError(ValueError):
    """The series cannot be tested: bad values or not enough data for the method."""


def run_trend(values: list[Any], method: str = "seasonal", alpha: float = ALPHA) -> dict:
    """Trend of a monthly series. Raises TrendInputError / ValueError on unusable input."""
    if method not in METHODS:
        raise ValueError(f"method must be one of {sorted(METHODS)}, not {method!r}")
    if not (isinstance(alpha, Real) and 0 < alpha < 1):
        raise ValueError(f"alpha must be between 0 and 1 (exclusive), not {alpha!r}")

    x = _to_array(values)
    _check_eligible(x, method)

    if method == "seasonal":
        result = mk.seasonal_test(x, period=PERIOD, alpha=alpha)
        slope = float(result.slope) / PERIOD  # library: per 12-month cycle -> per month
    else:
        result = mk.original_test(x, alpha=alpha)
        slope = float(result.slope)  # one step = one month already

    z = float(result.z)
    p = float(2 * norm.sf(abs(z)))  # precise for tiny p (library's 1 - cdf underflows to 0)
    if is_significant(p, alpha):
        trend = "increasing" if z > 0 else "decreasing"
    else:
        trend = "no trend"
    return {
        "slope": slope + 0.0,  # + 0.0 turns -0.0 into 0.0
        "slope_unit": "per month",
        "p": p,
        "tau": float(result.Tau) + 0.0,
        "trend": trend,
    }


def _to_array(values: list[Any]) -> np.ndarray:
    out = np.empty(len(values), dtype=float)
    for i, v in enumerate(values):
        if v is None:
            out[i] = np.nan
        elif isinstance(v, bool) or not isinstance(v, Real):
            raise TrendInputError(f"value at position {i} is not a number: {v!r}")
        elif math.isnan(v):
            out[i] = np.nan
        elif math.isinf(v):
            raise TrendInputError(f"value at position {i} is infinite")
        else:
            out[i] = float(v)
    return out


def _check_eligible(x: np.ndarray, method: str) -> None:
    valid = int(np.sum(~np.isnan(x)))
    if valid < MIN_VALID_MONTHS:
        raise TrendInputError(f"not enough data: {valid} valid months, need {MIN_VALID_MONTHS}")
    if method == "seasonal":
        for month in range(PERIOD):  # position 0 is the series' first month
            years = int(np.sum(~np.isnan(x[month::PERIOD])))
            if years < MIN_YEARS_PER_CALENDAR_MONTH:
                raise TrendInputError(
                    f"calendar month {month + 1} (counting from the series start) has {years} "
                    f"valid years, need {MIN_YEARS_PER_CALENDAR_MONTH} for the seasonal test"
                )
