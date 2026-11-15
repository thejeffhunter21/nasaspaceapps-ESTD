"""Export the approved qc-v1 nighttime cube as a map CSV and verify its rollups."""

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from netCDF4 import Dataset, num2date

VERSION = "phoenix-qc-v1.0"
SOURCE_COMMIT = "aef91f193d5a3b0f7c89e8107821cd564e6f1e20"
REFERENCE_REPO = (
    "https://github.com/nergisRahimzade/"
    "NASA-Space-Apps-Challenges-2026---Be-an-Earth-System-Trend-Detective"
)
SOURCE_SHA256 = "04406bfbce48c7ec2531c3d9b375bf9c3b8b496b7b02a20ae69239a09aa692e2"
MONTHS = tuple(f"{year}-{month:02d}" for year in range(2003, 2025) for month in range(1, 13))
REGIONS = {
    "all": "phoenix",
    "NW": "phoenix_northwest",
    "NE": "phoenix_northeast",
    "SW": "phoenix_southwest",
    "SE": "phoenix_southeast",
}
FIELDS = ("cell_id", "lat", "lon", "quarter", "date", "value")
MIN_COVERAGE = 0.8


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_grid(source, target):
    with Dataset(source) as cube, target.open("w", encoding="utf-8", newline="") as stream:
        cube.set_auto_mask(False)
        temperature = cube["lst_night"]
        if cube.data_version != VERSION or temperature.units != "degC":
            raise ValueError("Unexpected dataset version or temperature unit")
        if temperature.dimensions != ("time", "lat", "lon") or temperature.shape != (264, 12, 16):
            raise ValueError("Unexpected cube dimensions")
        time = cube["time"]
        dates = tuple(d.strftime("%Y-%m") for d in num2date(time[:], time.units, time.calendar))
        if dates != MONTHS:
            raise ValueError("Unexpected month sequence")
        latitudes = cube["lat"][:]
        longitudes = cube["lon"][:]
        lat_order = sorted(range(len(latitudes)), key=lambda index: -latitudes[index])
        lon_order = sorted(range(len(longitudes)), key=lambda index: longitudes[index])
        values = temperature[:]
        accepted = cube["qc_accepted"][:]
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(FIELDS)
        for row, i in enumerate(lat_order):
            lat = float(latitudes[i])
            for col, j in enumerate(lon_order):
                lon = float(longitudes[j])
                quarter = ("N" if lat >= 33.5 else "S") + ("E" if lon >= -112.0 else "W")
                cell_id = f"r{row:02d}_c{col:02d}"
                for t, date in enumerate(dates):
                    value = float(values[t, i, j])
                    mask = int(accepted[t, i, j])
                    if mask not in (0, 1) or bool(mask) != math.isfinite(value):
                        raise ValueError(f"QC mask disagrees with temperature at {cell_id}, {date}")
                    writer.writerow(
                        (cell_id, f"{lat:.3f}", f"{lon:.3f}", quarter, date, repr(value) if mask else "")
                    )


def verify_grid(path, processed):
    """Read the exported bytes back and compare their weighted rollups with the frozen files."""
    groups = defaultdict(list)
    cells = {}
    dates_by_cell = defaultdict(list)
    missing = 0
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("Unexpected CSV columns")
        for row in reader:
            cell, month, quarter = row["cell_id"], row["date"], row["quarter"]
            coords = (float(row["lat"]), float(row["lon"]), quarter)
            if cells.setdefault(cell, coords) != coords:
                raise ValueError(f"Cell metadata changed for {cell}")
            dates_by_cell[cell].append(month)
            value = float(row["value"]) if row["value"] else None
            if value is not None and not math.isfinite(value):
                raise ValueError(f"Non-finite value at {cell}, {month}")
            missing += value is None
            weight = math.cos(math.radians(coords[0]))
            groups["all", month].append((weight, value))
            groups[quarter, month].append((weight, value))
    if len(cells) != 192 or any(tuple(dates) != MONTHS for dates in dates_by_cell.values()):
        raise ValueError("Expected every month once per cell")
    for i in range(12):
        for j in range(16):
            lat, lon, quarter = cells[f"r{i:02d}_c{j:02d}"]
            expected_quarter = ("N" if i < 6 else "S") + ("W" if j < 8 else "E")
            expected = (round(33.775 - i * 0.05, 3), round(-112.375 + j * 0.05, 3))
            if (lat, lon) != expected or quarter != expected_quarter:
                raise ValueError(f"Wrong cell centre or quarter for r{i:02d}_c{j:02d}")
    if missing != 412:
        raise ValueError(f"Expected 412 failed cell-months from qc-v1, found {missing}")

    with (processed / "coverage.csv").open(encoding="utf-8", newline="") as stream:
        coverage = {(r["region"], r["date"]): r for r in csv.DictReader(stream)}
    regional_gaps = {}
    greatest_error = 0.0
    for key, region in REGIONS.items():
        name = "timeseries.csv" if key == "all" else f"timeseries_{region}.csv"
        with (processed / name).open(encoding="utf-8", newline="") as stream:
            expected_rows = list(csv.DictReader(stream))
        if tuple(r["date"] for r in expected_rows) != MONTHS:
            raise ValueError(f"Unexpected reference dates in {name}")
        gaps = 0
        for row in expected_rows:
            month = row["date"]
            pairs = groups[key, month]
            accepted = [(w, v) for w, v in pairs if v is not None]
            area = math.fsum(w for w, _ in accepted)
            fraction = area / math.fsum(w for w, _ in pairs)
            reference = coverage[region, month]
            if len(accepted) != int(reference["accepted_cells"]) or not math.isclose(
                fraction, float(reference["area_fraction"]), rel_tol=0, abs_tol=1e-12
            ):
                raise ValueError(f"Coverage mismatch in {name}, {month}")
            if (fraction < MIN_COVERAGE) != (row["value"] == ""):
                raise ValueError(f"Regional gap mismatch in {name}, {month}")
            if row["value"] == "":
                gaps += 1
                continue
            actual = math.fsum(w * v for w, v in accepted) / area
            error = abs(actual - float(row["value"]))
            if error > 1e-12:
                raise ValueError(f"Regional temperature mismatch in {name}, {month}: {error}")
            greatest_error = max(greatest_error, error)
        regional_gaps[region] = gaps
    return {
        "cells": len(cells),
        "cells_per_quarter": dict(sorted(Counter(c[2] for c in cells.values()).items())),
        "months_per_cell": len(MONTHS),
        "rows": len(cells) * len(MONTHS),
        "empty_cell_months": missing,
        "regional_months_checked": len(MONTHS) * len(REGIONS),
        "regional_gaps": regional_gaps,
        "max_abs_regional_difference_degC": greatest_error,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Frozen clean_qc.nc from reference PR #59")
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    if sha256(args.source) != SOURCE_SHA256:
        raise ValueError("Input does not match the frozen clean_qc.nc SHA-256")
    with TemporaryDirectory(dir=args.processed) as directory:
        staged = Path(directory) / "grid_cells.csv"
        write_grid(args.source, staged)
        summary = verify_grid(staged, args.processed)
        manifest = {
            "data_version": VERSION,
            "filename": staged.name,
            "bytes": staged.stat().st_size,
            "sha256": sha256(staged),
            "source": {
                "reference_pr": f"{REFERENCE_REPO}/pull/59",
                "source_commit": SOURCE_COMMIT,
                "file": "data/processed/clean_qc.nc",
                "sha256": SOURCE_SHA256,
                "freeze_manifest": "docs/evidence/day17/freeze_manifest.json",
                "cube_builder": "scripts/freeze_data.py",
                "variable": "lst_night",
                "mask": "qc_accepted",
            },
            "export_script": "scripts/export_grid_cells.py",
            "units": "degC",
            "period": [MONTHS[0], MONTHS[-1]],
            "cell_id": "Zero-based rNN_cNN, row from north and column from west",
            "missing_value": "Empty when qc_accepted=0; no fill or interpolation",
            "quarter_boundaries": {"latitude": 33.5, "longitude": -112.0},
            "region_min_accepted_area_fraction": MIN_COVERAGE,
            "validation": summary,
        }
        metadata = Path(directory) / "grid_cells_manifest.json"
        metadata.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        staged.replace(args.processed / staged.name)
        metadata.replace(args.processed / metadata.name)
    print(json.dumps({"sha256": manifest["sha256"], **summary}, indent=2))


if __name__ == "__main__":
    main()
