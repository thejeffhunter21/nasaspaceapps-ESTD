"""The results contract: the one shape every layer agrees on.

The pipeline writes files in this shape, the API serves them, and the
dashboard reads them. Both backend halves import this file and nothing else
from each other. Human-readable version: docs/contract.md.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CONTRACT_VERSION = "1.0"
MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"  # YYYY-MM

TrendWord = Literal["increasing", "decreasing", "no trend"]
ExplanationSource = Literal["ai", "fallback"]


class _Strict(BaseModel):
    # Unknown fields are an error, so typos are caught instead of ignored.
    model_config = ConfigDict(extra="forbid")


class Period(_Strict):
    start: str = Field(pattern=MONTH)
    end: str = Field(pattern=MONTH)


class SeriesPoint(_Strict):
    time: str = Field(pattern=MONTH)
    value: float | None = Field(description="null for a missing month")

    @field_validator("value")
    @classmethod
    def finite(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("value must be a real number (no NaN or infinity); use null")
        return v


class Trend(_Strict):
    slope: float = Field(description="change per month, in slope_unit")
    slope_unit: str = Field(min_length=1, description='e.g. "degC/month"')
    p: float = Field(ge=0, le=1, description="p-value; significant if < 0.05")
    tau: float = Field(ge=-1, le=1, description="Kendall's tau")
    trend: TrendWord

    @field_validator("slope", "p", "tau")
    @classmethod
    def finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("must be a real number (no NaN or infinity)")
        return v


class ForecastPoint(_Strict):
    time: str = Field(pattern=MONTH)
    value: float
    low: float
    high: float

    @model_validator(mode="after")
    def band_contains_value(self) -> ForecastPoint:
        if not (self.low <= self.value <= self.high):
            raise ValueError("forecast needs low <= value <= high")
        return self


class Forecast(_Strict):
    """Optional (AI layer). Code makes the numbers; it assumes the past pattern continues."""

    method: str = Field(min_length=1, description='e.g. "Holt-Winters (12-month season)"')
    months: int = Field(ge=1)
    points: list[ForecastPoint] = Field(min_length=1)
    backtest_mae: float | None = Field(default=None, ge=0)
    beats_baseline: bool | None = None
    note: str = Field(min_length=1, description="caveat shown with the forecast")


class Results(_Strict):
    region_id: str = Field(pattern=r"^[a-z0-9_]+$", description="use in ?region=")
    region: str = Field(min_length=1, description="label shown to people")
    variable: str = Field(min_length=1)
    units: str = Field(min_length=1)
    period: Period
    series: list[SeriesPoint] = Field(min_length=1)
    trend: Trend
    explanation: str = Field(min_length=1)
    explanation_source: ExplanationSource
    source: str = Field(min_length=1, description="where the data came from")
    method: str = Field(min_length=1, description="exact trend test used")
    forecast: Forecast | None = None  # optional, main region only

    @model_validator(mode="after")
    def series_matches_period(self) -> Results:
        times = [point.time for point in self.series]
        if times != sorted(set(times)):
            raise ValueError("series times must be in order with no repeats")
        if (times[0], times[-1]) != (self.period.start, self.period.end):
            raise ValueError(
                f"period {self.period.start}..{self.period.end} must match the first and "
                f"last series time {times[0]}..{times[-1]}"
            )
        return self


class ContractError(ValueError):
    """A results file is missing, is not JSON, or does not match the contract."""


def load_results(path: str | Path) -> Results:
    """Read and check a results file. Raises ContractError with a readable message."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ContractError(f"{path}: file not found") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractError(f"{path}: not valid JSON (line {exc.lineno}: {exc.msg})") from exc
    try:
        return Results.model_validate(data)
    except ValidationError as exc:
        raise ContractError(f"{path} does not match the contract:\n{_errors(exc)}") from exc


def _errors(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        where = ".".join(str(part) for part in err["loc"]) or "(file)"
        lines.append(f"  - {where}: {re.sub(r'^Value error, ', '', err['msg'])}")
    return "\n".join(lines)
