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

import numpy as np
import pymannkendall as mk
from scipy.stats import norm

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


def sen_slope_ci(values, alpha: float = ALPHA, period: int = 12) -> dict | None:
    """Seasonal Sen's slope (per year) with its Mann-Kendall-based (1 - alpha) confidence interval.

    Gilbert (1987) / Hirsch et al. (1982): pool every within-season pairwise slope (each step is one
    year), take ranks (N - C)/2 and (N + C)/2 + 1 with C = z(1 - alpha/2) * sqrt(Var S), where Var S
    is pymannkendall's seasonal test variance. The median equals pymannkendall's seasonal Sen slope.
    Missing months are skipped, never filled.
    """
    x = np.array([np.nan if v is None else float(v) for v in values])
    slopes = []
    for season in range(period):
        xs = x[season::period]
        for i in range(len(xs)):
            if np.isnan(xs[i]):
                continue
            for j in range(i + 1, len(xs)):
                if not np.isnan(xs[j]):
                    slopes.append((xs[j] - xs[i]) / (j - i))
    if len(slopes) < 10:
        return None
    slopes = np.sort(np.array(slopes))
    n = len(slopes)
    var_s = float(mk.seasonal_test(x, period=period).var_s)
    c = norm.ppf(1 - alpha / 2) * np.sqrt(var_s)
    ranks = np.arange(1, n + 1)
    return {"slope_per_year": float(np.median(slopes)),
            "ci_low_per_year": float(np.interp((n - c) / 2, ranks, slopes)),
            "ci_high_per_year": float(np.interp((n + c) / 2 + 1, ranks, slopes)),
            "ci_level": 1 - alpha, "pairs": n,
            "ci_method": "Seasonal Sen's slope CI from Mann-Kendall variance (Gilbert 1987)"}


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
    ci = sen_slope_ci(c.values) or {}
    return {**c.public(), "method": "Seasonal Mann-Kendall + seasonal Sen's slope (per month x 12)",
            **result, **{k: ci[k] for k in ("ci_low_per_year", "ci_high_per_year", "ci_level") if k in ci},
            "valid_months": sum(v is not None for v in c.values), "halves": [{"period": [a, b], **(_trend(v) or {"status": "insufficient data"})}
                                 for a, b, v in (first, second)]}


@lru_cache(maxsize=1)
def _all_cell_trends_cached(sha: str) -> dict:
    grid = load_grid()
    rows = []
    for c in grid.cells.values():
        t = _trend(c.values)
        if t is not None:
            ci = sen_slope_ci(c.values) or {}
            rows.append({**c.public(), **t, "ci_low_per_year": ci.get("ci_low_per_year"),
                         "ci_high_per_year": ci.get("ci_high_per_year"),
                         "valid_months": sum(v is not None for v in c.values)})
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


REGION_IDS = ("phoenix_study_area", *QUARTER_REGION.values())


def region_stats() -> dict:
    """Published regional trends plus the Sen's slope confidence interval for each region."""
    out = {}
    for rid in REGION_IDS:
        series = _regional_series(rid)
        out[rid] = {**_regional_trend(rid), **(sen_slope_ci(series) or {}),
                    "valid_months": sum(v is not None for v in series), "months": len(series)}
        out[rid]["slope_per_year"] = _regional_trend(rid)["slope_per_year"]  # the published value
    return {"alpha": ALPHA, "regions": out}


def region_difference(region_a: str, region_b: str) -> dict:
    """Direct test: do two regions' trends differ? Seasonal MK on the monthly difference A - B."""
    if region_a not in REGION_IDS or region_b not in REGION_IDS or region_a == region_b:
        raise ToolError(f"choose two different regions from {list(REGION_IDS)}")
    a, b = _regional_series(region_a), _regional_series(region_b)
    diff = [None if (x is None or y is None) else x - y for x, y in zip(a, b)]
    t = _trend(diff)
    if t is None:
        raise ToolError("not enough overlapping months")
    ci = sen_slope_ci(diff) or {}
    return {"region_a": region_a, "region_b": region_b,
            "method": "Seasonal Mann-Kendall + seasonal Sen's slope on the monthly difference (A minus B)",
            "difference_slope_per_year": t["slope_per_year"], "p": t["p"], "tau": t["tau"],
            "significant": t["p"] < ALPHA, "ci_low_per_year": ci.get("ci_low_per_year"),
            "ci_high_per_year": ci.get("ci_high_per_year"), "ci_level": 1 - ALPHA,
            "months_used": sum(v is not None for v in diff),
            "interpretation": ("The two trends differ significantly" if t["p"] < ALPHA else
                               "No significant difference between the two trends was detected")
                              + f" (p = {t['p']:.2g}). This is a historical comparison, not a cause."}


TOOL_SPECS = [
    {"name": "list_cells", "description": "List every grid cell (id, location, quarter, valid months).", "params": {}},
    {"name": "cell_series", "description": "QC'd monthly values of one cell (None = failed QC).", "params": {"cell_id": "str"}},
    {"name": "cell_trend", "description": "Seasonal Mann-Kendall trend of one cell, with both halves.", "params": {"cell_id": "str"}},
    {"name": "all_cell_trends", "description": "Trend of every cell with Benjamini-Hochberg q-values.", "params": {}},
    {"name": "localized_differences", "description": "Cells warming faster/slower than their quarter (FDR, halves challenge).", "params": {}},
    {"name": "seasonal_trend", "description": "Trend of yearly seasonal means for a cell or region.", "params": {"target": "cell id or region id", "season": "DJF|MAM|JJA|SON"}},
    {"name": "anomalies", "description": "Unusual months by robust z (exploratory).", "params": {"cell_id": "optional str", "threshold": "float"}},
    {"name": "region_stats", "description": "Regional trends with Sen's slope confidence intervals.", "params": {}},
    {"name": "region_difference", "description": "Direct test of whether two regions' trends differ.", "params": {"region_a": "str", "region_b": "str"}},
    {"name": "region_vs_cells", "description": "Regional trend versus the distribution of its cells' trends.", "params": {"region_id": "str"}},
]
TOOLS = {"list_cells": list_cells, "cell_series": cell_series, "cell_trend": cell_trend,
         "all_cell_trends": all_cell_trends, "localized_differences": localized_differences,
         "seasonal_trend": seasonal_trend, "anomalies": anomalies, "region_vs_cells": region_vs_cells,
         "region_stats": region_stats, "region_difference": region_difference}


def finite(obj):
    """JSON-safe copy (no NaN/inf)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [finite(v) for v in obj]
    return obj
