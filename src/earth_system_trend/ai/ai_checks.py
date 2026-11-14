"""A3: check an AI-written explanation against the results it describes.

Rule: code computes every number; the AI only writes words. An explanation passes only if

- every number in it can be derived from the results (allowing for the rounding shown),
- every YYYY-MM date in it is a month in the data, and the only bare years are the period bounds,
- its significance wording matches p (significant means p < 0.05, unrounded; p = 0.05 is not),
- its direction words do not contradict the trend,
- it names no cause, makes no forecast and gives no advice (the data supports none of these),
- it does not describe a different product (air temperature, daily data) or unit (Fahrenheit),
- it is non-empty and at most MAX_CHARS characters.

check_explanation() never raises: anything it cannot check fails closed, so the caller
uses the deterministic fallback text instead.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

ALPHA = 0.05
MAX_CHARS = 600
# Conventional cut-offs and confidence levels a correct sentence may quote.
STANDARD_NUMBERS = (0.05, 0.01, 0.001, 5.0, 95.0, 12.0)

_DATE = re.compile(r"\b(\d{4})-(\d{2})\b")
_NUMBER = re.compile(r"(?<![\w.])[+\-−]?(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
_YEAR = re.compile(r"^(19|20)\d{2}$")

_SIGNIFICANCE = re.compile(r"\b(in|non-?)?significan\w*", re.IGNORECASE)
_NEGATION_BEFORE = re.compile(
    r"\b(not|no|isn't|is not|wasn't|was not|without)\b(\s+\w+)?\s*$", re.IGNORECASE
)
_NEGATION_WORD = re.compile(r"\b(no|not|neither|nor|without|isn't|wasn't)\b", re.IGNORECASE)

_UP = re.compile(r"\b(increas\w*|warm\w*|ris(?:e|es|ing|en)|rose|higher|hott\w*)\b", re.IGNORECASE)
_DOWN = re.compile(r"\b(decreas\w*|cool\w*|declin\w*|fall\w*|fell|drop\w*|lower\w*)\b",
                   re.IGNORECASE)

_BANNED = {
    "cause": re.compile(
        r"\b(because|due to|caus\w*|driven by|attribut\w*|result(?:s|ed)? (?:of|from)|"
        r"climate change|global warming|heat island|urbani[sz]ation)\b", re.IGNORECASE),
    "forecast": re.compile(
        r"\b(will|forecast\w*|predict\w*|project(?:ed|ion|ions)|future|tomorrow|"
        r"next (?:week|month|year|decade|summer|winter))\b", re.IGNORECASE),
    "advice": re.compile(
        r"\b(should|must|ought|recommend\w*|advis\w*|irrigat\w*)\b", re.IGNORECASE),
}
_FAHRENHEIT = re.compile(r"°\s*F\b|\bfahrenheit\b|\bdeg(?:rees?)?\s*F\b", re.IGNORECASE)


@dataclass(frozen=True)
class CheckResult:
    """problems is empty when the explanation may be shown."""

    problems: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.problems


def is_significant(p: float, alpha: float = ALPHA) -> bool:
    """Strictly below alpha, compared on the unrounded p-value."""
    return p < alpha


def check_explanation(text: Any, results: Any) -> CheckResult:
    """Return every reason `text` must not be shown for `results`. Never raises."""
    if not isinstance(text, str) or not text.strip():
        return CheckResult(("explanation is empty",))
    try:
        facts = _Facts.from_results(results)
    except Exception as exc:  # noqa: BLE001 - fail closed on anything unexpected
        return CheckResult((f"results cannot be checked ({type(exc).__name__})",))

    problems: list[str] = []
    if len(text) > MAX_CHARS:
        problems.append(f"explanation is too long ({len(text)} > {MAX_CHARS} characters)")
    problems += _check_dates_and_numbers(text, facts)
    problems += _check_significance(text, facts)
    problems += _check_direction(text, facts)
    for label, pattern in _BANNED.items():
        found = sorted({m.group(0).lower() for m in pattern.finditer(text)})
        if found:
            problems.append(f"{label} claim not supported by the data: {', '.join(found)}")
    problems += _check_product(text, facts)
    return CheckResult(tuple(problems))


@dataclass(frozen=True)
class _Facts:
    numbers: tuple[float, ...]
    months: frozenset[str]
    years: frozenset[str]
    p: float
    trend: str
    variable: str

    @classmethod
    def from_results(cls, results: Mapping[str, Any]) -> _Facts:
        trend = results["trend"]
        slope, p, tau = float(trend["slope"]), float(trend["p"]), float(trend["tau"])
        if not all(math.isfinite(x) for x in (slope, p, tau)):
            raise ValueError("non-finite statistic")
        direction = str(trend["trend"])
        series = list(results["series"])
        months = [str(point["time"]) for point in series]
        n = len(months)
        n_valid = sum(point.get("value") is not None for point in series)
        start, end = str(results["period"]["start"]), str(results["period"]["end"])
        first_year, last_year = int(start[:4]), int(end[:4])

        numbers = [
            slope, slope * 12, slope * 120, slope * n, slope * (n - 1),  # per month/year/decade/period
            p, tau, n, n_valid, n - n_valid,
            last_year - first_year, last_year - first_year + 1,  # e.g. "21 years" / "22 years"
            *STANDARD_NUMBERS,
        ]
        for key in ("region", "variable", "units", "source", "method"):
            numbers += [float(m.group(1)) for m in _NUMBER.finditer(str(results.get(key, "")))]
        numbers += [float(m.group(1)) for m in _NUMBER.finditer(str(trend.get("slope_unit", "")))]
        return cls(
            numbers=tuple(abs(x) for x in numbers),
            months=frozenset(months) | {start, end},
            years=frozenset({start[:4], end[:4]}),
            p=p,
            trend=direction,
            variable=str(results.get("variable", "")),
        )


def _check_dates_and_numbers(text: str, facts: _Facts) -> list[str]:
    problems = []
    bad_dates = sorted({m.group(0) for m in _DATE.finditer(text)} - facts.months)
    if bad_dates:
        problems.append(f"date not in the data: {', '.join(bad_dates)}")
    without_dates = _DATE.sub(" ", text)

    bad_numbers = []
    for match in _NUMBER.finditer(without_dates):
        token = match.group(1)
        if _YEAR.match(token):
            if token not in facts.years:
                bad_numbers.append(token)
        elif not _grounded(token, facts.numbers):
            bad_numbers.append(token)
    if bad_numbers:
        problems.append(f"number not in the results: {', '.join(dict.fromkeys(bad_numbers))}")
    return problems


def _grounded(token: str, allowed: tuple[float, ...]) -> bool:
    """True if `token`, read at its shown precision, is a rounding of an allowed value."""
    value = float(token)
    if "e" in token.lower():
        return any(math.isclose(value, a, rel_tol=0.05) for a in allowed)
    decimals = len(token.split(".")[1]) if "." in token else 0
    tolerance = 0.5 * 10 ** -decimals + 1e-12
    return any(abs(value - a) <= tolerance for a in allowed)


def _check_significance(text: str, facts: _Facts) -> list[str]:
    significant = is_significant(facts.p)
    problems = []
    for match in _SIGNIFICANCE.finditer(text):
        before = text[max(0, match.start() - 40):match.start()]
        negated = bool(match.group(1)) or bool(_NEGATION_BEFORE.search(before))
        if significant and negated:
            problems.append(f"significance: says not significant but p = {facts.p:g} < {ALPHA}")
            break
        if not significant and not negated:
            problems.append(f"significance: says significant but p = {facts.p:g} >= {ALPHA}")
            break
    return problems


def _check_direction(text: str, facts: _Facts) -> list[str]:
    if facts.trend == "increasing":
        wrong = [m.group(0) for m in _DOWN.finditer(text)]
    elif facts.trend == "decreasing":
        wrong = [m.group(0) for m in _UP.finditer(text)]
    else:  # "no trend": any direction word must be negated just before it
        wrong = [
            m.group(0)
            for pattern in (_UP, _DOWN)
            for m in pattern.finditer(text)
            if not _NEGATION_WORD.search(" ".join(text[:m.start()].split()[-4:]))
        ]
    if not wrong:
        return []
    words = ", ".join(dict.fromkeys(w.lower() for w in wrong))
    return [f"direction contradicts trend '{facts.trend}': {words}"]


def _check_product(text: str, facts: _Facts) -> list[str]:
    problems = []
    lower = text.lower()
    if "air temperature" in lower and "air" not in facts.variable.lower():
        problems.append("wrong product: data is land surface temperature, not air temperature")
    if re.search(r"\bdaily\b", lower):
        problems.append("wrong product: data is monthly, not daily")
    if _FAHRENHEIT.search(text):
        problems.append("wrong unit: Fahrenheit is not in the results")
    return problems
