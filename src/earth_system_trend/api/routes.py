"""J6-J8, J11: the data endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings
from .files import read_or_http_error
from .regions import all_regions, find_region
from .validation import RegionParam

router = APIRouter()


@router.get("/results")
def get_results() -> dict:
    """The whole main results file."""
    return read_or_http_error(get_settings().results_path).model_dump()


@router.get("/regions")
def get_regions() -> dict:
    """Every region with its id, label and trend (for the dropdown and comparison)."""
    return {"regions": [
        {"region_id": r.region_id, "region": r.region, "variable": r.variable,
         "units": r.units, "period": r.period.model_dump(), "trend": r.trend.model_dump()}
        for r in all_regions(get_settings())
    ]}


@router.get("/series")
def get_series(region: RegionParam = None) -> dict:
    """The monthly values for one region (default: the main one), for the chart."""
    r = find_region(all_regions(get_settings()), region)
    return {"region_id": r.region_id, "region": r.region, "variable": r.variable,
            "units": r.units, "period": r.period.model_dump(),
            "series": [p.model_dump() for p in r.series]}


@router.get("/trend")
def get_trend(region: RegionParam = None) -> dict:
    """The trend numbers and the plain-language explanation for one region."""
    r = find_region(all_regions(get_settings()), region)
    return {"region_id": r.region_id, "region": r.region, "variable": r.variable,
            "units": r.units, "period": r.period.model_dump(), "trend": r.trend.model_dump(),
            "explanation": r.explanation, "explanation_source": r.explanation_source,
            "source": r.source, "method": r.method}
