"""Private grid-cell analysis service + the public discoveries feed.

/analysis/*  - the AI's controlled tools over individual cells. Requires the header
               X-Analysis-Token matching the ANALYSIS_TOKEN environment variable. With no token
               configured the service is disabled (503), so raw cells are never public by accident.
/discoveries - public: verified findings and cell outlines for the map; never time series.
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from ..analysis import investigator, tools
from ..analysis.grid import GridError

router = APIRouter()


def warm_cache() -> None:
    """Run the investigation once in the background at start-up, so the first /discoveries
    request answers from cache instead of racing the request timeout on a slow host."""
    import threading

    def work():
        try:
            investigator.investigate()
        except Exception as exc:  # noqa: BLE001 - grid missing or bad: /discoveries will report it
            logging.getLogger(__name__).warning("discoveries warm-up skipped: %s", exc)

    threading.Thread(target=work, name="discoveries-warmup", daemon=True).start()


def require_token(x_analysis_token: str | None = Header(default=None)) -> None:
    expected = os.getenv("ANALYSIS_TOKEN", "")
    if not expected:
        raise HTTPException(503, "The grid-cell analysis service is disabled (no ANALYSIS_TOKEN configured)")
    if not x_analysis_token or not secrets.compare_digest(x_analysis_token, expected):
        raise HTTPException(401, "Missing or wrong X-Analysis-Token")


def _run(fn, *args, **kwargs):
    try:
        return tools.finite(fn(*args, **kwargs))
    except tools.ToolError as exc:
        raise HTTPException(422, str(exc)) from None
    except (GridError, OSError) as exc:
        raise HTTPException(503, f"Grid data unavailable: {exc}") from None


private = APIRouter(prefix="/analysis", dependencies=[Depends(require_token)], tags=["analysis (private)"])


@private.get("/tools")
def list_tools() -> dict:
    """Tool descriptions, ready for an agent's function-calling setup."""
    return {"tools": tools.TOOL_SPECS}


@private.get("/cells")
def cells() -> dict:
    return _run(tools.list_cells)


@private.get("/cells/{cell_id}/series")
def cell_series(cell_id: str) -> dict:
    return _run(tools.cell_series, cell_id)


@private.get("/cells/{cell_id}/trend")
def cell_trend(cell_id: str) -> dict:
    return _run(tools.cell_trend, cell_id)


@private.get("/trends")
def all_trends() -> dict:
    return _run(tools.all_cell_trends)


@private.get("/localized")
def localized() -> dict:
    return _run(tools.localized_differences)


@private.get("/seasonal")
def seasonal(target: str = Query(..., max_length=40), season: str = Query(..., pattern="^(DJF|MAM|JJA|SON)$")) -> dict:
    return _run(tools.seasonal_trend, target, season)


@private.get("/anomalies")
def anomalies(cell_id: str | None = Query(None, max_length=10), threshold: float = Query(3.5, ge=2, le=10)) -> dict:
    return _run(tools.anomalies, cell_id, threshold)


@private.get("/region-vs-cells")
def region_vs_cells(region: str = Query(..., max_length=40)) -> dict:
    return _run(tools.region_vs_cells, region)


@private.get("/investigate")
def investigate() -> dict:
    """The full investigation report, with every piece of evidence."""
    return _run(investigator.investigate)


@router.get("/discoveries", tags=["discoveries"])
def discoveries() -> dict:
    """Public: findings and cell outlines only (no measurements), for highlighting on the map."""
    return _run(investigator.public_discoveries)


router.include_router(private)
