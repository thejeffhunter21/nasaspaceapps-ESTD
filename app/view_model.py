"""Map the results contract to frontend values without recomputing evidence."""

from dataclasses import dataclass

from earth_system_trend.contract import Results


@dataclass(frozen=True)
class ResultsView:
    region_id: str
    region_label: str
    variable: str
    units: str
    period_label: str
    times: tuple[str, ...]
    values: tuple[float | None, ...]
    slope: float
    slope_unit: str
    p: float
    tau: float
    direction: str
    significant: bool
    explanation: str
    explanation_source: str
    source: str
    method: str
    is_sample: bool
    anomaly: tuple[float | None, ...] | None = None
    baseline: tuple[tuple[int, float], ...] | None = None

    @property
    def display_units(self) -> str:
        return "°C" if self.units == "degC" else self.units

    @property
    def display_slope_unit(self) -> str:
        return "°C/month" if self.slope_unit == "degC/month" else self.slope_unit

    @property
    def display_slope(self) -> str:
        """Six significant figures for cards; retain the raw slope for evidence."""
        return format(self.slope, ".6g") if self.slope else str(self.slope)

    @property
    def display_p(self) -> str:
        return "p < 0.001" if self.p < 0.001 else str(self.p)

    @property
    def months_total(self) -> int:
        return len(self.values)

    @property
    def months_observed(self) -> int:
        return sum(value is not None for value in self.values)

    @property
    def years_label(self) -> str:
        """Calendar span of the supplied series, e.g. 22 for 2003-01..2024-12."""
        return f"{self.months_total / 12:.0f}" if self.months_total % 12 == 0 else (
            f"{self.months_total / 12:.1f}")

    @property
    def baseline_label(self) -> str:
        """Years the supplied anomaly baseline covers (the full stated period)."""
        return f"{self.times[0][:4]}–{self.times[-1][:4]}" if self.times else ""

    @property
    def per_year_slope(self) -> float:
        """Annual display = supplied monthly slope x 12; always labelled as such."""
        return self.slope * 12

    @property
    def period_change_estimate(self) -> float:
        """Slope x months in the period: a trend-line estimate, not a measured difference."""
        return self.slope * self.months_total

    @property
    def seasonal_swing(self) -> float | None:
        """Gap between the warmest and coolest calendar-month baseline means, if supplied."""
        if not self.baseline:
            return None
        means = [mean for _, mean in self.baseline]
        return max(means) - min(means)


def build_view_model(payload: dict) -> ResultsView:
    """Validate contract v1.0; retain nulls, precision, units and supplied text.

    This accepts a decoded /results response or the frontend sample fixture.
    Invalid payloads raise ValidationError rather than creating display defaults.
    Sample markers identify synthetic data; their absence does not verify provenance.
    """
    result = Results.model_validate(payload)
    return ResultsView(
        region_id=result.region_id,
        region_label=result.region,
        variable=result.variable,
        units=result.units,
        period_label=f"{result.period.start} to {result.period.end}",
        times=tuple(point.time for point in result.series),
        values=tuple(point.value for point in result.series),
        slope=result.trend.slope,
        slope_unit=result.trend.slope_unit,
        p=result.trend.p,
        tau=result.trend.tau,
        direction=result.trend.trend,
        significant=result.trend.p < 0.05,
        explanation=result.explanation,
        explanation_source=result.explanation_source,
        source=result.source,
        method=result.method,
        is_sample=(
            "mock" in result.source.casefold()
            or result.region.strip().casefold() == "example region"
        ),
        anomaly=(tuple(point.value for point in result.anomaly)
                 if result.anomaly is not None else None),
        baseline=(tuple((b.month, b.mean) for b in result.baseline)
                  if result.baseline else None),
    )
