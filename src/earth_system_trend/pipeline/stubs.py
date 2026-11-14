"""Stand-ins for the AI layer's functions, with the same signatures.

run_trend is a real seasonal Mann-Kendall test (so the demo shows real
statistics before the AI layer delivers). Seasonal, because monthly temperature
has a big yearly cycle that hides the trend from the plain test: on the Phoenix
data the plain test says "no trend" while the seasonal test finds warming. explain is a fallback that only uses the numbers.
"""

from __future__ import annotations

import numpy as np
import pymannkendall as mk

METHOD = "Seasonal Mann-Kendall test (12-month period) with seasonal Sen's slope"


def run_trend(values: list[float | None], method: str = "seasonal", alpha: float = 0.05) -> dict:
    """Trend of monthly values in order (None = missing month). Slope is per month.

    Same signature as the AI layer's run_trend. slope_unit is filled in by the pipeline.
    """
    data = np.array([np.nan if v is None else v for v in values], dtype=float)
    result = mk.seasonal_test(data, period=12)  # slope comes out per year
    return {
        "slope": round(float(result.slope) / 12, 6),  # contract: per month
        "slope_unit": "per month",
        "p": round(float(result.p), 6),
        "tau": round(float(result.Tau), 4),
        "trend": result.trend,  # "increasing" | "decreasing" | "no trend"
    }


def explain(results: dict) -> dict:
    """Same shape as the AI layer's explain: {"text": ..., "source": "fallback"}. Never raises."""
    return {"text": fallback_text(results), "source": "fallback"}


def forecast(values: list[float | None], months: int = 12) -> dict | None:
    """Stand-in for the AI layer's forecast: none until theirs lands."""
    return None


def fallback_text(results: dict) -> str:
    """Plain summary from the numbers only. Never raises."""
    try:
        t = results["trend"]
        sig = "statistically significant" if t["p"] < 0.05 else "not statistically significant"
        per_year = t["slope"] * 12
        p_text = "p < 0.001" if t["p"] < 0.001 else f"p = {t['p']:.3g}"
        return (f"From {results['period']['start']} to {results['period']['end']}, "
                f"{results['variable'].lower()} in {results['region']} shows {t['trend']} "
                f"(about {per_year:+.3g} {results['units']} per year). "
                f"The trend is {sig} ({p_text}).")
    except Exception:  # noqa: BLE001 - must never raise
        return "An automatic summary is not available for this result."
