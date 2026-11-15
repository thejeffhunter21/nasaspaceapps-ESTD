"""Public endpoints for the map explorer (new; existing endpoints are unchanged).

/map-frame      one period's value per grid cell (a single month, or an annual mean that needs all
                12 months). The full per-cell dataset stays on the server; only the requested frame
                is sent, so the browser never downloads the 50,688-row file.
/map-static     per-cell long-term trend (seasonal Sen's slope + CI, BH q-value) and coverage.
/region-stats   published regional trends plus Sen's slope confidence intervals.
/region-compare direct test of whether two regions' trends differ (seasonal MK on A - B).
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

from ..analysis import tools
from ..analysis.grid import GridError, load_grid

router = APIRouter(tags=["explorer"])
BASELINE = "the same cell's 2003–2024 mean for that calendar month (all valid years)"


def _guard(fn, *args):
    try:
        return tools.finite(fn(*args))
    except tools.ToolError as exc:
        raise HTTPException(422, str(exc)) from None
    except (GridError, OSError) as exc:
        raise HTTPException(503, f"Cell data unavailable: {exc}") from None


@lru_cache(maxsize=1)
def _baselines(sha: str) -> dict:
    """Per cell: calendar-month means and the mean of complete-year annual means (anomaly baselines)."""
    grid = load_grid()
    out = {}
    for c in grid.cells.values():
        by_month = {m: [v for t, v in zip(grid.months, c.values) if int(t[5:7]) == m and v is not None]
                    for m in range(1, 13)}
        monthly = {m: (sum(vs) / len(vs) if vs else None) for m, vs in by_month.items()}
        annual = []
        for year in sorted({t[:4] for t in grid.months}):
            vals = [v for t, v in zip(grid.months, c.values) if t[:4] == year]
            if len(vals) == 12 and all(v is not None for v in vals):
                annual.append(sum(vals) / 12)
        out[c.id] = {"monthly": monthly, "annual": sum(annual) / len(annual) if annual else None}
    return out


@lru_cache(maxsize=512)
def _frame(sha: str, year: int, month: str) -> dict:
    grid = load_grid()
    base = _baselines(sha)
    idx = {t: i for i, t in enumerate(grid.months)}
    year_keys = [f"{year}-{m:02d}" for m in range(1, 13)]
    if not all(k in idx for k in year_keys):
        raise tools.ToolError(f"year must be within {grid.months[0][:4]}–{grid.months[-1][:4]}")
    cells = []
    for c in grid.cells.values():
        year_vals = [c.values[idx[k]] for k in year_keys]
        valid = sum(v is not None for v in year_vals)
        if month == "avg":
            value = sum(year_vals) / 12 if valid == 12 else None
            ref = base[c.id]["annual"]
        else:
            value = year_vals[int(month) - 1]
            ref = base[c.id]["monthly"][int(month)]
        cells.append({"id": c.id, "value": value,
                      "anomaly": None if value is None or ref is None else value - ref,
                      "valid_months_in_year": valid})
    label = f"{year} annual average" if month == "avg" else f"{year}-{int(month):02d}"
    return {"period": label, "year": year, "month": month, "units": "degC",
            "annual_rule": "An annual average is shown only when all 12 months are valid.",
            "anomaly_baseline": BASELINE if month != "avg" else
            "the same cell's mean of all complete-year annual averages, 2003–2024",
            "source": "NASA MOD11C3 v061 LST_Night_CMG, qc-v1 (missing = failed quality control)",
            "data_version": grid.data_version, "cells": cells}


@router.get("/map-frame")
def map_frame(year: int = Query(..., ge=1900, le=2100),
              month: str = Query(..., pattern="^(avg|[1-9]|1[0-2])$")) -> dict:
    return _guard(lambda: _frame(load_grid().sha256, year, month))


@lru_cache(maxsize=1)
def _static(sha: str) -> dict:
    grid = load_grid()
    trends = {r["id"]: r for r in tools.all_cell_trends()["cells"]}
    cells = []
    for c in grid.cells.values():
        t = trends.get(c.id, {})
        cells.append({**c.public(), "valid_months": sum(v is not None for v in c.values),
                      "months": len(grid.months), **{k: t.get(k) for k in (
                          "slope_per_year", "ci_low_per_year", "ci_high_per_year", "p", "q",
                          "significant_fdr", "direction")}})
    return {"cell_size_deg": grid.cell_size_deg, "period": [grid.months[0], grid.months[-1]],
            "method": "Seasonal Mann-Kendall + seasonal Sen's slope per cell (95% CI); "
                      "Benjamini-Hochberg q across all cells",
            "data_version": grid.data_version, "sha256": grid.sha256, "cells": cells}


@router.get("/map-static")
def map_static() -> dict:
    return _guard(lambda: _static(load_grid().sha256))


@router.get("/region-stats")
def region_stats() -> dict:
    return _guard(tools.region_stats)


@router.get("/region-compare")
def region_compare(a: str = Query(..., max_length=40), b: str = Query(..., max_length=40)) -> dict:
    return _guard(tools.region_difference, a, b)


@lru_cache(maxsize=256)
def _cell_years(sha: str, cell_id: str) -> dict:
    """One cell's yearly means (complete years only) and anomalies: derived values for a chart,
    not the monthly record (which stays on the server)."""
    grid = load_grid()
    if cell_id not in grid.cells:
        raise tools.ToolError(f"unknown cell {cell_id!r}")
    c = grid.cells[cell_id]
    base = _baselines(sha)[cell_id]["annual"]
    years = []
    for year in sorted({t[:4] for t in grid.months}):
        vals = [v for t, v in zip(grid.months, c.values) if t[:4] == year]
        valid = sum(v is not None for v in vals)
        mean = sum(vals) / 12 if valid == 12 else None
        years.append({"year": int(year), "value": mean, "valid_months": valid,
                      "anomaly": None if mean is None or base is None else mean - base})
    slope = tools.cell_trend(cell_id)["slope_per_year"]
    mid = (years[0]["year"] + years[-1]["year"]) / 2
    resid = sorted(y["anomaly"] - slope * (y["year"] - mid) for y in years if y["anomaly"] is not None)
    intercept = resid[len(resid) // 2] if len(resid) % 2 else (resid[len(resid) // 2 - 1] + resid[len(resid) // 2]) / 2
    return {"id": cell_id, "units": "degC", "baseline": "mean of this cell's complete-year annual averages, 2003–2024",
            "annual_rule": "A year is shown only when all 12 months are valid.",
            "trend_line": {"slope_per_year": slope, "centre_year": mid, "intercept": intercept,
                           "method": "Seasonal Sen's slope through the median residual of the yearly anomalies"},
            "years": years}


@router.get("/cell-years")
def cell_years(id: str = Query(..., pattern=r"^r\d{2}_c\d{2}$")) -> dict:
    return _guard(lambda: _cell_years(load_grid().sha256, id))
