"""Build web/assets/phoenix_urban_area.json: the Phoenix metro outline used to shape the map base.

Source: Natural Earth 1:10m "Urban areas" (public domain), the built-up extent mapped from
MODIS satellite data around 2002-2003. Download ne_10m_urban_areas.geojson from
https://github.com/nvkelso/natural-earth-vector/tree/master/geojson and run:

    uv run python scripts/build_phoenix_outline.py path/to/ne_10m_urban_areas.geojson

Output: the outline clipped to each map quarter (for the quarter slabs) and the ids of the grid
cells whose centre lies inside it. Visual only: no data or statistic depends on it.
Pure Python (Sutherland-Hodgman clipping, ray-casting point test); no new dependency.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W, S, E, N = -112.4, 33.2, -111.6, 33.8
MID_LON, MID_LAT = -112.0, 33.5
QUARTERS = {"NW": (W, MID_LAT, MID_LON, N), "NE": (MID_LON, MID_LAT, E, N),
            "SW": (W, S, MID_LON, MID_LAT), "SE": (MID_LON, S, E, MID_LAT)}


def _rings(geom: dict) -> list[list[list[float]]]:
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return [poly[0] for poly in polys]  # outer rings; holes are ignored for a fill outline


def _bbox(ring):
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def clip(ring, box):
    """Sutherland-Hodgman clip of a polygon ring against an axis-aligned box."""
    w, s, e, n = box
    edges = [(lambda p: p[0] >= w, lambda a, b: _ix(a, b, x=w)), (lambda p: p[0] <= e, lambda a, b: _ix(a, b, x=e)),
             (lambda p: p[1] >= s, lambda a, b: _ix(a, b, y=s)), (lambda p: p[1] <= n, lambda a, b: _ix(a, b, y=n))]
    out = ring[:-1] if ring[0] == ring[-1] else ring[:]
    for inside, cross in edges:
        if not out:
            break
        src, out = out, []
        for i, cur in enumerate(src):
            prev = src[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
    return out


def _ix(a, b, x=None, y=None):
    if x is not None:
        t = (x - a[0]) / (b[0] - a[0])
        return [x, a[1] + t * (b[1] - a[1])]
    t = (y - a[1]) / (b[1] - a[1])
    return [a[0] + t * (b[0] - a[0]), y]


def inside(pt, ring) -> bool:
    x, y, hit = pt[0], pt[1], False
    for i in range(len(ring)):
        (x1, y1), (x2, y2) = ring[i - 1], ring[i]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def build(source: Path) -> dict:
    data = json.loads(source.read_text(encoding="utf-8"))
    rings = []
    for f in data["features"]:
        for ring in _rings(f["geometry"]):
            bw, bs, be, bn = _bbox(ring)
            if bw < E and be > W and bs < N and bn > S:
                rings.append(ring)
    with (ROOT / "data/processed/grid_cells.csv").open(encoding="utf-8") as fh:
        centres = {r["cell_id"]: (float(r["lon"]), float(r["lat"])) for r in csv.DictReader(fh)}
    inside_ids = sorted(cid for cid, pt in centres.items() if any(inside(pt, r) for r in rings))
    quarters = {}
    for q, box in QUARTERS.items():
        parts = [[[round(x, 4), round(y, 4)] for x, y in clip(r, box)] for r in rings]
        quarters[q] = [p for p in parts if len(p) >= 3]
    return {"source": "Natural Earth 1:10m Urban areas (public domain); built-up extent from MODIS, c. 2002-2003",
            "note": "Visual outline only. All 192 cells are analysed; cells outside the outline are drawn faded.",
            "inside_cells": inside_ids, "quarters": quarters}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = build(Path(sys.argv[1]))
    path = ROOT / "web/assets/phoenix_urban_area.json"
    path.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{path}: {len(out['inside_cells'])} cells inside; " + ", ".join(f"{q} {len(v)} part(s)" for q, v in out["quarters"].items()))
