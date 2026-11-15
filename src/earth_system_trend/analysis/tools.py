"""Statistical tools over individual grid cells (the AI's controlled access to the granular data).

Every tool reads the validated grid (grid.load_grid), returns plain dicts with the cell ids it
used, and never changes an observation. Trend tests reuse the AI layer's run_trend (seasonal
Mann-Kendall + seasonal Sen's slope). Whenever many cells are tested together, p-values are
adjusted with Benjamini-Hochberg (false discovery rate); both raw p and q are reported.
"""

from __future__ import annotations

import json
import math
import os
import statistics
from functools import lru_cache
from pathlib import Path

import pymannkendall as mk

from ..ai.trend import TrendInputError, run_trend
from .grid import QUARTER_REGION, Grid, load_grid

ALPHA = 0.05
SEASONS = {"DJF": (12, 1, 2), "MAM": (3, 4, 5), "JJA": (6, 7, 8), "SON": (9, 10, 11)}
SEASON_NAMES = {"DJF": "winter (Dec–Feb)", "MAM": "spring (Mar–May)", "JJA": "summer (Jun–Aug)",
                "SON": "autumn (Sep–Nov)"}


class ToolError(ValueError):
    """A request the tools cannot answer (unknown cell, bad season, too little data)."""


# ---------------------------------------------------------------- helpers
def bh_qvalues(pvalues: list[float]) -> list[float]:
    """Benjamini-Hochberg adjusted p-values (q), same order as the input."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    q = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvalues[i] * m / rank)
        q[i] = running
    return q


def _cell(grid: Grid, cell_id: str):
    try:
        return grid.cells[cell_id]
    except KeyError:
        raise ToolError(f"unknown cell {cell_id!r}") from None


def _trend(values) -> dict | None:
    try:
        t = run_trend(list(values), method="seasonal")
    except (TrendInputError, ValueError):
        return None
    return {"slope_per_year": t["slope"] * 12, "p": t["p"], "tau": t["tau"], "direction": t["trend"]}


def _halves(grid: Grid, values):
    """Split at the middle January (2003-2013 / 2014-2024) for consistency checks."""
    mid = grid.months.index(f"{int(grid.months[0][:4]) + len(grid.months) // 24}-01")
    return (grid.months[0], grid.months[mid - 1], values[:mid]), (grid.months[mid], grid.months[-1], values[mid:])


@lru_cache(maxsize=4)
def _regional_series(region_id: str) -> tuple[float | None, ...]:
    """The published regional series (results files the API serves), aligned with grid months."""
    regions_dir = Path(os.getenv("REGIONS_DIR", "results/regions"))
    path = (Path(os.getenv("RESULTS_PATH_REAL", "results/results.json")) if region_id == "phoenix_study_area"
            else regions_dir / f"{region_id}.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    by_time = {p["time"]: p["value"] for p in data["series"]}
    return tuple(by_time.get(m) for m in load_grid().months)


def _regional_trend(region_id: str) -> dict:
    regions_dir = Path(os.getenv("REGIONS_DIR", "results/regions"))
    path = (Path(os.getenv("RESULTS_PATH_REAL", "results/results.json")) if region_id == "phoenix_study_area"
            else regions_dir / f"{region_id}.json")
    t = json.loads(path.read_text(encoding="utf-8"))["trend"]
    return {"slope_per_year": t["slope"] * 12, "p": t["p"], "tau": t["tau"], "direction": t["trend"]}


# ---------------------------------------------------------------- tools
def list_cells() -> dict:
    grid = load_grid()
    return {"provenance": grid.describe(), "cells": [
        {**c.public(), "valid_months": sum(v is not None for v in c.values)} for c in grid.cells.values()]}


def cell_series(cell_id: str) -> dict:
    """The QC'd monthly values of one cell, exactly as exported (None = failed QC)."""
    grid = load_grid()
    c = _cell(grid, cell_id)
    return {**c.public(), "months": list(grid.months), "values": list(c.values), "units": "degC",
            "missing_months": [m for m, v in zip(grid.months, c.values) if v is None],
            "provenance": grid.describe()}


def cell_trend(cell_id: str) -> dict:
    grid = load_grid()
    c = _cell(grid, cell_id)
    result = _trend(c.values)
    if result is None:
        raise ToolError(f"{cell_id} has too few valid months for the seasonal test")
    first, second = _halves(grid, c.values)
    return {**c.public(), "method": "Seasonal Mann-Kendall + seasonal Sen's slope (per month x 12)",
            **result, "halves": [{"period": [a, b], **(_trend(v) or {"status": "insufficient data"})}
                                 for a, b, v in (first, second)]}


@lru_cache(maxsize=1)
def _all_cell_trends_cached(sha: str) -> dict:
    grid = load_grid()
    rows = []
    for c in grid.cells.values():
        t = _trend(c.values)
        if t is not None:
            rows.append({**c.public(), **t})
    qs = bh_qvalues([r["p"] for r in rows])
    for r, q in zip(rows, qs):
        r["q"] = q
        r["significant_fdr"] = q < ALPHA
    return {"method": "Seasonal Mann-Kendall per cell; Benjamini-Hochberg FDR across cells",
            "alpha": ALPHA, "tested": len(rows), "untestable": len(grid.cells) - len(rows), "cells": rows}


def all_cell_trends() -> dict:
    return _all_cell_trends_cached(load_grid().sha256)


@lru_cache(maxsize=1)
def _localized_cached(sha: str) -> dict:
    """Does a cell warm faster or slower than its own quarter? Test the difference series."""
    grid = load_grid()
    rows = []
    for c in grid.cells.values():
        regional = _regional_series(c.region_id)
        diff = [None if (v is None or r is None) else v - r for v, r in zip(c.values, regional)]
        t = _trend(diff)
        if t is None:
            continue
        first, second = _halves(grid, diff)
        h1, h2 = _trend(first[2]), _trend(second[2])
        same_sign = bool(h1 and h2 and h1["slope_per_year"] * t["slope_per_year"] > 0
                         and h2["slope_per_year"] * t["slope_per_year"] > 0)
        rows.append({**c.public(), "region_id": c.region_id, "diff_slope_per_year": t["slope_per_year"],
                     "p": t["p"], "tau": t["tau"],
                     "halves": [h1 and h1["slope_per_year"], h2 and h2["slope_per_year"]],
                     "consistent_in_both_halves": same_sign})
    qs = bh_qvalues([r["p"] for r in rows])
    for r, q in zip(rows, qs):
        r["q"] = q
    return {"method": "Seasonal Mann-Kendall on (cell minus its published quarter series); "
                      "Benjamini-Hochberg FDR across cells; challenge: same sign in 2003-2013 and 2014-2024",
            "alpha": ALPHA, "tested": len(rows), "cells": rows}


def localized_differences() -> dict:
    return _localized_cached(load_grid().sha256)


def seasonal_trend(target: str, season: str) -> dict:
    """Trend of yearly seasonal means (only years with every month of the season valid)."""
    if season not in SEASONS:
        raise ToolError(f"season must be one of {sorted(SEASONS)}")
    grid = load_grid()
    if target in grid.cells:
        values, label = grid.cells[target].values, target
    elif target in (*QUARTER_REGION.values(), "phoenix_study_area"):
        values, label = _regional_series(target), target
    else:
        raise ToolError(f"unknown target {target!r}")
    by = dict(zip(grid.months, values))
    years, means = [], []
    for year in range(int(grid.months[0][:4]), int(grid.months[-1][:4]) + 1):
        keys = [f"{year - 1 if (season == 'DJF' and m == 12) else year}-{m:02d}" for m in SEASONS[season]]
        vals = [by.get(k) for k in keys]
        if all(v is not None for v in vals):
            years.append(year)
            means.append(sum(vals) / len(vals))
    if len(means) < 10:
        raise ToolError(f"{label} {season}: only {len(means)} complete seasons")
    r = mk.original_test(means)
    return {"target": label, "season": season, "season_name": SEASON_NAMES[season],
            "method": "Mann-Kendall + Sen's slope on yearly seasonal means (complete seasons only)",
            "years_used": years, "slope_per_year": float(r.slope), "p": float(r.p),
            "tau": float(r.Tau), "direction": r.trend if r.p < ALPHA else "no trend"}


def anomalies(cell_id: str | None = None, threshold: float = 3.5, limit: int = 20) -> dict:
    """Months far from that cell's usual value for the calendar month (robust z, median/MAD).

    Descriptive only: an unusual month is a lead to check, not a statistical finding.
    """
    grid = load_grid()
    cells = [_cell(grid, cell_id)] if cell_id else list(grid.cells.values())
    found = []
    for c in cells:
        for month in range(1, 13):
            idx = [i for i, m in enumerate(grid.months) if int(m[5:7]) == month and c.values[i] is not None]
            vals = [c.values[i] for i in idx]
            if len(vals) < 10:
                continue
            med = statistics.median(vals)
            mad = statistics.median(abs(v - med) for v in vals) * 1.4826
            if mad == 0:
                continue
            for i in idx:
                z = (c.values[i] - med) / mad
                if abs(z) >= threshold:
                    found.append({**c.public(), "month": grid.months[i], "value": c.values[i],
                                  "calendar_month_median": med, "robust_z": z})
    found.sort(key=lambda a: -abs(a["robust_z"]))
    return {"method": "Robust z = (value - calendar-month median) / (1.4826 x MAD), per cell",
            "threshold": threshold, "status": "exploratory", "count": len(found), "anomalies": found[:limit]}


def region_vs_cells(region_id: str) -> dict:
    """How well does a regional average describe the cells underneath it?"""
    grid = load_grid()
    if region_id == "phoenix_study_area":
        members = set(grid.cells)
    elif region_id in QUARTER_REGION.values():
        members = {cid for cid, c in grid.cells.items() if c.region_id == region_id}
    else:
        raise ToolError(f"unknown region {region_id!r}")
    rows = [r for r in all_cell_trends()["cells"] if r["id"] in members]
    slopes = sorted(r["slope_per_year"] for r in rows)
    quart = statistics.quantiles(slopes, n=4)
    return {"region_id": region_id, "regional_trend": _regional_trend(region_id), "cells_tested": len(rows),
            "cell_slope_per_year": {"min": slopes[0], "q1": quart[0], "median": quart[1], "q3": quart[2],
                                    "max": slopes[-1], "spread_max_minus_min": slopes[-1] - slopes[0]},
            "cells_significant_warming_fdr": sum(r["significant_fdr"] and r["slope_per_year"] > 0 for r in rows),
            "cells_significant_cooling_fdr": sum(r["significant_fdr"] and r["slope_per_year"] < 0 for r in rows),
            "slowest_cells": [r["id"] for r in sorted(rows, key=lambda r: r["slope_per_year"])[:3]],
            "fastest_cells": [r["id"] for r in sorted(rows, key=lambda r: -r["slope_per_year"])[:3]]}


TOOL_SPECS = [
    {"name": "list_cells", "description": "List every grid cell (id, location, quarter, valid months).", "params": {}},
    {"name": "cell_series", "description": "QC'd monthly values of one cell (None = failed QC).", "params": {"cell_id": "str"}},
    {"name": "cell_trend", "description": "Seasonal Mann-Kendall trend of one cell, with both halves.", "params": {"cell_id": "str"}},
    {"name": "all_cell_trends", "description": "Trend of every cell with Benjamini-Hochberg q-values.", "params": {}},
    {"name": "localized_differences", "description": "Cells warming faster/slower than their quarter (FDR, halves challenge).", "params": {}},
    {"name": "seasonal_trend", "description": "Trend of yearly seasonal means for a cell or region.", "params": {"target": "cell id or region id", "season": "DJF|MAM|JJA|SON"}},
    {"name": "anomalies", "description": "Unusual months by robust z (exploratory).", "params": {"cell_id": "optional str", "threshold": "float"}},
    {"name": "region_vs_cells", "description": "Regional trend versus the distribution of its cells' trends.", "params": {"region_id": "str"}},
]
TOOLS = {"list_cells": list_cells, "cell_series": cell_series, "cell_trend": cell_trend,
         "all_cell_trends": all_cell_trends, "localized_differences": localized_differences,
         "seasonal_trend": seasonal_trend, "anomalies": anomalies, "region_vs_cells": region_vs_cells}


def finite(obj):
    """JSON-safe copy (no NaN/inf)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [finite(v) for v in obj]
    return obj
