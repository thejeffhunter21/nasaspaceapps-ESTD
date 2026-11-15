"""Load the Data layer's per-cell export, read-only, with the checks that make it trustworthy.

Source: data/processed/grid_cells.csv (Hayley's PR #53): one row per 0.05 degree MODIS MOD11C3
cell per month, value in degC after the qc-v1 rules, EMPTY when the cell failed quality control.
This module never fills, interpolates, rounds or otherwise changes a value.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

WEST, SOUTH, EAST, NORTH, MID_LON, MID_LAT, CELL = -112.4, 33.2, -111.6, 33.8, -112.0, 33.5, 0.05
QUARTER_REGION = {"NW": "phoenix_northwest", "NE": "phoenix_northeast",
                  "SW": "phoenix_southwest", "SE": "phoenix_southeast"}


class GridError(ValueError):
    """The export is missing, changed or inconsistent; nothing is analysed."""


@dataclass(frozen=True)
class Cell:
    id: str
    lat: float
    lon: float
    quarter: str
    values: tuple[float | None, ...]  # aligned with Grid.months; None = failed QC

    @property
    def region_id(self) -> str:
        return QUARTER_REGION[self.quarter]

    def footprint(self) -> list[list[float]]:
        h = CELL / 2
        return [[self.lon - h, self.lat - h], [self.lon + h, self.lat - h],
                [self.lon + h, self.lat + h], [self.lon - h, self.lat + h]]

    def public(self) -> dict:
        """What may leave the private service: location only, never the time series."""
        return {"id": self.id, "lat": self.lat, "lon": self.lon, "quarter": self.quarter,
                "footprint": self.footprint()}


@dataclass(frozen=True)
class Grid:
    months: tuple[str, ...]
    cells: dict[str, Cell]
    sha256: str
    path: str
    data_version: str
    provenance: dict = field(default_factory=dict)

    def describe(self) -> dict:
        return {"file": self.path, "sha256": self.sha256, "data_version": self.data_version,
                "cells": len(self.cells), "months": len(self.months),
                "period": [self.months[0], self.months[-1]], "source": self.provenance}


def months_between(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= end:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def read_cells(path: Path) -> tuple[list[str], dict]:
    """Parse and validate. Returns (months, {cell_id: {"lat","lon","quarter","v": {date: value}}})."""
    cells: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        need = {"cell_id", "lat", "lon", "quarter", "date", "value"}
        if not reader.fieldnames or not need <= set(reader.fieldnames):
            raise GridError(f"columns must include {sorted(need)}, got {reader.fieldnames}")
        for n, row in enumerate(reader, start=2):
            cid = row["cell_id"].strip()
            lat, lon, quarter = float(row["lat"]), float(row["lon"]), row["quarter"].strip().upper()
            cell = cells.setdefault(cid, {"lat": lat, "lon": lon, "quarter": quarter, "v": {}})
            if (cell["lat"], cell["lon"], cell["quarter"]) != (lat, lon, quarter):
                raise GridError(f"line {n}: {cid} changes position or quarter")
            date = row["date"].strip()[:7]
            if date in cell["v"]:
                raise GridError(f"line {n}: {cid} {date} appears twice")
            raw = row["value"].strip()
            if raw == "":
                cell["v"][date] = None
                continue
            value = float(raw)
            if not math.isfinite(value) or not -30 <= value <= 60:
                raise GridError(f"line {n}: {cid} {date} value {raw} is not plausible nighttime LST")
            cell["v"][date] = value
    if not cells:
        raise GridError("no rows")
    dates = sorted({d for c in cells.values() for d in c["v"]})
    months = months_between(dates[0], dates[-1])
    for cid, cell in cells.items():
        if sorted(cell["v"]) != months:
            raise GridError(f"{cid} does not have every month {months[0]}..{months[-1]} exactly once")
        lat, lon = cell["lat"], cell["lon"]
        if not (WEST < lon < EAST and SOUTH < lat < NORTH):
            raise GridError(f"{cid} centre {lat},{lon} is outside the study window")
        for value, origin in ((lon, WEST), (lat, SOUTH)):
            offset = (value - origin) / CELL - 0.5
            if abs(offset - round(offset)) > 0.02:
                raise GridError(f"{cid} centre {lat},{lon} is not on the 0.05 degree grid")
        expected = ("N" if lat > MID_LAT else "S") + ("W" if lon < MID_LON else "E")
        if cell["quarter"] != expected:
            raise GridError(f"{cid} is labelled {cell['quarter']} but sits in {expected}")
    return months, cells


def weighted_mean(values_and_lats) -> float | None:
    pairs = [(v, math.cos(math.radians(lat))) for v, lat in values_and_lats if v is not None]
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs) if pairs else None


def compare_with_regions(months, cells, published: dict[str, dict], tolerance: float = 0.01) -> dict:
    """Cell means must reproduce every published regional month (published: key -> {date: value})."""
    report = {}
    for key, series in published.items():
        members = [c for c in cells.values() if key == "ALL" or c["quarter"] == key]
        worst, compared, skipped = 0.0, 0, []
        for date in months:
            ref = series.get(date)
            mean = weighted_mean((c["v"][date], c["lat"]) for c in members)
            if ref is None or mean is None:
                skipped.append(date)
                continue
            worst = max(worst, abs(mean - ref))
            compared += 1
            if abs(mean - ref) > tolerance:
                raise GridError(f"{key} {date}: cell mean {mean:.4f} vs published {ref:.4f} degC; "
                                "the cells are not the published data")
        report[key] = {"cells": len(members), "months_compared": compared,
                       "max_abs_diff_degC": worst, "not_compared": skipped}
    return report


def _published_from_results(results_dir: Path, main_file: Path) -> dict[str, dict]:
    """Regional series as the API serves them (results files), keyed ALL/NW/NE/SW/SE."""
    out = {}
    files = {"ALL": main_file, **{q: results_dir / f"{rid}.json" for q, rid in QUARTER_REGION.items()}}
    for key, path in files.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        out[key] = {p["time"]: p["value"] for p in data["series"]}
    return out


@lru_cache(maxsize=2)
def _load(path: str, manifest: str, results_dir: str, main_file: str) -> Grid:
    p = Path(path)
    if not p.is_file():
        raise GridError(f"{path} is not available; the analysis service is disabled")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    meta = {}
    if Path(manifest).is_file():
        meta = json.loads(Path(manifest).read_text(encoding="utf-8"))
        if meta.get("sha256") and meta["sha256"] != digest:
            raise GridError("grid_cells.csv does not match its manifest sha256; refusing to analyse")
    months, raw = read_cells(p)
    # Results files store values rounded to 4 decimals, so allow 5e-5 + float noise.
    compare_with_regions(months, raw, _published_from_results(Path(results_dir), Path(main_file)), 1e-4)
    cells = {cid: Cell(cid, c["lat"], c["lon"], c["quarter"], tuple(c["v"][d] for d in months))
             for cid, c in sorted(raw.items())}
    return Grid(tuple(months), cells, digest, path, meta.get("data_version", "unknown"),
                meta.get("source", {}))


def load_grid() -> Grid:
    return _load(os.getenv("GRID_CELLS_PATH", "data/processed/grid_cells.csv"),
                 os.getenv("GRID_MANIFEST_PATH", "data/processed/grid_cells_manifest.json"),
                 os.getenv("REGIONS_DIR", "results/regions"),
                 os.getenv("RESULTS_PATH_REAL", "results/results.json"))
