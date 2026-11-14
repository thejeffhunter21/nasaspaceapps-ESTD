"""J11: every region we have data for, and finding one by id or label."""

from __future__ import annotations

import logging

from fastapi import HTTPException

from ..config import Settings
from ..contract import ContractError, Results
from .files import read_or_http_error, read_results

logger = logging.getLogger(__name__)


def all_regions(settings: Settings) -> list[Results]:
    """The main results first, then each sub-region file. Broken files are skipped."""
    regions = [read_or_http_error(settings.results_path)]
    if settings.regions_dir is not None and settings.regions_dir.is_dir():
        for path in sorted(settings.regions_dir.glob("*.json")):
            try:
                results = read_results(path)
            except ContractError as exc:
                logger.warning("Skipping broken region file: %s", exc)
                continue
            if all(r.region_id != results.region_id for r in regions):
                regions.append(results)
    return regions


def find_region(regions: list[Results], query: str | None) -> Results:
    """The region whose id or label matches (any case). None means the main one."""
    if query is None:
        return regions[0]
    wanted = query.strip().lower()
    for results in regions:
        if wanted in (results.region_id.lower(), results.region.lower()):
            return results
    valid = ", ".join(r.region_id for r in regions)
    raise HTTPException(status_code=404, detail=f"Unknown region '{query}'. Valid ids: {valid}")
