"""Validated local grid retrieval and deterministic exploratory cell selection."""

import csv
import hashlib
import io
import json
import math

import streamlit as st

from earth_system_trend.ai.trend import TrendInputError, run_trend

QUARTERS = {"NE": "northeast", "NW": "northwest", "SE": "southeast", "SW": "southwest"}
MONTHS = tuple(f"{y}-{m:02d}" for y in range(2003, 2025) for m in range(1, 13))


@st.cache_data(max_entries=2, show_spinner=False)
def retrieve_cells(csv_bytes, manifest_bytes):
    """Cache by exact dataset bytes; reject malformed or unapproved evidence."""
    manifest = json.loads(manifest_bytes)
    if (hashlib.sha256(csv_bytes).hexdigest() != manifest["sha256"]
            or manifest["data_version"] != "phoenix-qc-v1.0"
            or manifest["units"] != "degC"):
        raise ValueError("Grid provenance verification failed")
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8")))
    if set(reader.fieldnames or ()) != {"cell_id", "lat", "lon", "quarter", "date", "value"}:
        raise ValueError("Unexpected cell columns")
    cells = {}
    missing = 0
    for row in reader:
        lat, lon = float(row["lat"]), float(row["lon"])
        quarter = ("N" if lat >= 33.5 else "S") + ("E" if lon >= -112.0 else "W")
        if not (33.2 < lat < 33.8 and -112.4 < lon < -111.6 and row["quarter"] == quarter):
            raise ValueError("Cell location does not match the Phoenix registry")
        meta = {"cell_id": row["cell_id"], "lat": lat, "lon": lon, "quarter": quarter}
        cell = cells.setdefault(row["cell_id"], {**meta, "series": []})
        if any(cell[k] != v for k, v in meta.items()):
            raise ValueError("Cell metadata changes within series")
        value = float(row["value"]) if row["value"] else None
        if value is not None and not math.isfinite(value):
            raise ValueError("Nonfinite cell measurement")
        missing += value is None
        cell["series"].append({"time": row["date"], "value": value})
    if (len(cells) != manifest["validation"]["cells"]
            or missing != manifest["validation"]["empty_cell_months"]
            or any(tuple(p["time"] for p in c["series"]) != MONTHS for c in cells.values())):
        raise ValueError("Cell calendar or coverage disagrees with manifest")
    return cells, manifest


@st.cache_data(max_entries=2, show_spinner=False)
def calculate_cell_trends(cells):
    """Every eligible cell uses the existing seasonal method, with gaps retained."""
    eligible = {}
    for cell_id, cell in cells.items():
        try:
            eligible[cell_id] = run_trend([p["value"] for p in cell["series"]], method="seasonal")
        except TrendInputError:
            continue
    return eligible


def select_cell(cells, trends, regions):
    """Exploratory maximum positive cell-minus-quarter slope; stable tie ordering."""
    candidates = []
    for cell_id in sorted(trends):
        cell = cells[cell_id]
        region = regions[f"phoenix_{QUARTERS[cell['quarter']]}"]
        difference = (trends[cell_id]["slope"] - region["trend"]["slope"]) * 12
        candidates.append((difference, cell_id, region))
    if not candidates:
        raise ValueError("No cells have sufficient seasonal coverage")
    difference, cell_id, region = max(candidates, key=lambda item: item[0])
    return cells[cell_id], trends[cell_id], region, difference
