"""Turn the Data layer's per-cell export into web/data/grid.json for the map explorer.

Input: data/processed/grid_cells.csv with columns
    cell_id, lat, lon, quarter, date, value
one row per cell per month (2003-01 .. 2024-12), value in degC after the qc-v1 rules,
EMPTY when the cell failed quality control. Nothing is filled in or interpolated here.

Checks (any failure stops with exit code 1 and writes nothing):
  - every cell has every month exactly once, dates sorted and continuous
  - cell centres sit on the 0.05 degree grid inside the study window, and `quarter`
    matches the -112.0 / 33.5 split
  - values are finite and physically plausible for nighttime LST (-30..60 degC)
  - for every month where a published regional value exists, the cosine-latitude weighted
    mean of the accepted cells reproduces timeseries*.csv within --tolerance (default 0.01 degC).
    (Months the Data layer left blank under the 80% area rule are reported, not compared.)

  uv run --locked python scripts/build_grid_json.py
  uv run --locked python scripts/build_grid_json.py --csv path/to/grid_cells.csv --check-only
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEST, SOUTH, EAST, NORTH, MID_LON, MID_LAT, CELL = -112.4, 33.2, -111.6, 33.8, -112.0, 33.5, 0.05
SERIES = {"ALL": "timeseries.csv", "NW": "timeseries_phoenix_northwest.csv",
          "NE": "timeseries_phoenix_northeast.csv", "SW": "timeseries_phoenix_southwest.csv",
          "SE": "timeseries_phoenix_southeast.csv"}


class GridError(ValueError):
    pass


def months_between(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= end:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def read_grid(path: Path) -> tuple[list[str], dict]:
    cells: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        need = {"cell_id", "lat", "lon", "quarter", "date", "value"}
        if not reader.fieldnames or not need <= set(reader.fieldnames):
            raise GridError(f"columns must include {sorted(need)}, got {reader.fieldnames}")
        for n, row in enumerate(reader, start=2):
            cid = row["cell_id"].strip()
            lat, lon, quarter = float(row["lat"]), float(row["lon"]), row["quarter"].strip().upper()
            cell = cells.setdefault(cid, {"id": cid, "lat": lat, "lon": lon, "quarter": quarter, "v": {}})
            if (cell["lat"], cell["lon"], cell["quarter"]) != (lat, lon, quarter):
                raise GridError(f"line {n}: {cid} changes position or quarter")
            date = row["date"].strip()[:7]
            if date in cell["v"]:
                raise GridError(f"line {n}: {cid} {date} appears twice")
            raw = row["value"].strip()
            if raw == "":
                cell["v"][date] = None
            else:
                value = float(raw)
                if not math.isfinite(value) or not -30 <= value <= 60:
                    raise GridError(f"line {n}: {cid} {date} value {raw} is not plausible nighttime LST")
                cell["v"][date] = value
    if not cells:
        raise GridError("no rows")
    all_dates = sorted({d for c in cells.values() for d in c["v"]})
    months = months_between(all_dates[0], all_dates[-1])
    for cell in cells.values():
        if sorted(cell["v"]) != months:
            raise GridError(f"{cell['id']} does not have every month {months[0]}..{months[-1]} exactly once")
        lat, lon = cell["lat"], cell["lon"]
        if not (WEST < lon < EAST and SOUTH < lat < NORTH):
            raise GridError(f"{cell['id']} centre {lat},{lon} is outside the study window")
        for value, origin in ((lon, WEST), (lat, SOUTH)):
            offset = (value - origin) / CELL - 0.5
            if abs(offset - round(offset)) > 0.02:
                raise GridError(f"{cell['id']} centre {lat},{lon} is not on the 0.05 degree grid")
        expected = ("N" if lat > MID_LAT else "S") + ("W" if lon < MID_LON else "E")
        if cell["quarter"] != expected:
            raise GridError(f"{cell['id']} is labelled {cell['quarter']} but sits in {expected}")
    return months, cells


def read_series(name: str) -> dict[str, float | None]:
    with open(ROOT / "data/processed" / name, newline="", encoding="utf-8") as handle:
        return {row["date"][:7]: (float(row["value"]) if row["value"].strip() else None)
                for row in csv.DictReader(handle)}


def compare_with_regions(months: list[str], cells: dict, tolerance: float,
                         published_series: dict | None = None) -> dict:
    """published_series (tests only) maps ALL/NW/NE/SW/SE to {date: value}; default reads the CSVs."""
    report = {}
    for key, name in SERIES.items():
        members = [c for c in cells.values() if key == "ALL" or c["quarter"] == key]
        published = published_series[key] if published_series else read_series(name)
        worst, compared, skipped = 0.0, 0, []
        for date in months:
            ref = published.get(date)
            accepted = [(c["v"][date], math.cos(math.radians(c["lat"]))) for c in members
                        if c["v"][date] is not None]
            if ref is None or not accepted:
                skipped.append(date)
                continue
            mean = sum(v * w for v, w in accepted) / sum(w for _, w in accepted)
            worst = max(worst, abs(mean - ref))
            compared += 1
            if abs(mean - ref) > tolerance:
                raise GridError(f"{key} {date}: cell mean {mean:.4f} vs published {ref:.4f} degC "
                                f"(tolerance {tolerance}); the cells are not the published data")
        report[key] = {"cells": len(members), "months_compared": compared,
                       "max_abs_diff_degC": round(worst, 5), "not_compared": skipped}
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, default=ROOT / "data/processed/grid_cells.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "web/data/grid.json")
    parser.add_argument("--tolerance", type=float, default=0.01)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        months, cells = read_grid(args.csv)
        report = compare_with_regions(months, cells, args.tolerance)
    except (GridError, OSError, ValueError, KeyError) as exc:
        print(f"grid check FAILED: {exc}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(args.csv.read_bytes()).hexdigest()
    payload = {
        "schema": 1,
        "source": "NASA MOD11C3 v061 LST_Night_CMG, per-cell qc-v1 values from the Data layer",
        "data_version": "phoenix-qc-v1.0",
        "input_sha256": digest,
        "cell_size_deg": CELL,
        "months": months,
        "cells": [{"id": c["id"], "lat": c["lat"], "lon": c["lon"], "quarter": c["quarter"],
                   "values": [None if c["v"][d] is None else round(c["v"][d], 3) for d in months]}
                  for c in sorted(cells.values(), key=lambda c: (-c["lat"], c["lon"]))],
        "checks": report,
    }
    print(json.dumps({"cells": len(cells), "months": len(months), "input_sha256": digest, "checks": report}, indent=2))
    if not args.check_only:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
