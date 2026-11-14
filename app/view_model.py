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
    )
