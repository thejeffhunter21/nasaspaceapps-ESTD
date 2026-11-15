"""3D Phoenix map (deck.gl via pydeck): one bar per supplied month in each study quarter.

Bars are real monthly values from the results files, never invented: a missing month has
no bar. Inside a quarter, bars are laid out as a calendar (years west to east, months north
to south) so they can be read; their position inside the quarter is not a location.
Freeway lines are Natural Earth (public domain), stored in app/assets so they work offline.
The street basemap is CARTO dark tiles, loaded by the viewer's browser when online.
"""

from __future__ import annotations

import json
from pathlib import Path

import pydeck as pdk

# Study window and quarter split from docs/data_card.md.
WEST, SOUTH, EAST, NORTH = -112.4, 33.2, -111.6, 33.8
MID_LON, MID_LAT = -112.0, 33.5
QUARTER_BOUNDS = {
    "NW": (WEST, MID_LAT, MID_LON, NORTH),
    "NE": (MID_LON, MID_LAT, EAST, NORTH),
    "SW": (WEST, SOUTH, MID_LON, MID_LAT),
    "SE": (MID_LON, SOUTH, EAST, MID_LAT),
}
QUARTER_NAMES = {"NW": "Northwest", "NE": "Northeast", "SW": "Southwest", "SE": "Southeast"}
PLACES = (("Downtown Phoenix", -112.074, 33.4484), ("Tempe", -111.940, 33.4255),
          ("Glendale", -112.186, 33.5387), ("Scottsdale", -111.926, 33.4942))
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
ASSET = Path(__file__).resolve().parent / "assets/phoenix_freeways.json"
BASEMAP = "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json"
METRES_PER_DEG_C = 95  # bar height scale
# Glyphs for map labels, including the degree sign (deck.gl defaults to ASCII only).
CHARS = pdk.types.String(" ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:+-°·–")
FONT = pdk.types.String("Helvetica Neue, Arial, sans-serif")


def _anomaly_color(value: float | None, temp: float) -> list[int]:
    """Blue (cooler than that month's average) to orange-red (warmer); heat scale if absent."""
    if value is None:
        t = max(0.0, min(1.0, (temp - 5) / 30))
        return [int(60 + 195 * t), int(140 - 40 * t), int(255 - 200 * t), 235]
    t = max(-1.0, min(1.0, value / 2.5))
    if t >= 0:
        return [int(40 + 215 * t), int(60 + 80 * t), int(110 - 60 * t), 240]
    t = -t
    return [int(40 + 20 * t), int(60 + 120 * t), int(110 + 145 * t), 240]


def month_bars(quarters: dict[str, dict]) -> list[dict]:
    """One record per observed month. quarters: short -> {region_id, label, times, values, anomaly}."""
    bars = []
    for short, data in quarters.items():
        west, south, east, north = QUARTER_BOUNDS[short]
        years = sorted({t[:4] for t in data["times"]})
        pad_x, pad_y = (east - west) * 0.08, (north - south) * 0.1
        step_x = (east - west - 2 * pad_x) / max(len(years), 1)
        step_y = (north - south - 2 * pad_y) / 12
        anomaly = data.get("anomaly") or (None,) * len(data["times"])
        for time, value, anom in zip(data["times"], data["values"], anomaly):
            if value is None:
                continue  # a missing month stays missing: no bar
            col, row = years.index(time[:4]), int(time[5:7]) - 1
            bars.append({
                "region_id": data["region_id"], "label": data["label"], "quarter": short,
                "lon": west + pad_x + (col + 0.5) * step_x,
                "lat": north - pad_y - (row + 0.5) * step_y,
                "height": max(value, 0.0) * METRES_PER_DEG_C + 60,
                "color": _anomaly_color(anom, value),
                "when": f"{MONTHS[row]} {time[:4]}",
                "temp": f"{value:.2f} °C",
                "anom": "" if anom is None else f"{anom:+.2f} °C vs the usual {MONTHS[row]}",
            })
    return bars


def latest_bars(quarters: dict[str, dict]) -> list[dict]:
    """One tall bar per quarter: its most recent observed month (Dec 2024 in this snapshot)."""
    bars = []
    for short, data in quarters.items():
        west, south, east, north = QUARTER_BOUNDS[short]
        latest = next(((t, v) for t, v in zip(reversed(data["times"]), reversed(data["values"]))
                       if v is not None), None)
        if latest is None:
            continue
        time, value = latest
        index = data["times"].index(time)
        anomaly = (data.get("anomaly") or (None,) * len(data["times"]))[index]
        month = MONTHS[int(time[5:7]) - 1]
        bars.append({
            "region_id": data["region_id"], "label": data["label"], "quarter": short,
            "lon": (west + east) / 2, "lat": (south + north) / 2,
            "height": max(value, 0.0) * METRES_PER_DEG_C * 9 + 400,
            "color": _anomaly_color(anomaly, value),
            "when": f"{month} {time[:4]} (latest month)",
            "temp": f"{value:.2f} °C",
            "anom": "" if anomaly is None else f"{anomaly:+.2f} °C vs the usual {month}",
            "text": f"{QUARTER_NAMES[short]}  {value:.1f} °C · {month} {time[:4]}",
        })
    return bars


def _freeways() -> list[dict]:
    try:
        return json.loads(ASSET.read_text(encoding="utf-8"))["paths"]
    except (OSError, ValueError, KeyError):
        return []  # decoration only; the map still works without it


def build_deck(quarters: dict[str, dict], selected_quarter: str | None, mode: str) -> pdk.Deck:
    bars = latest_bars(quarters) if mode == "latest" else month_bars(quarters)
    footprints = [{
        "region_id": quarters[q]["region_id"], "label": quarters[q]["label"], "quarter": q,
        "polygon": [[w, s], [e, s], [e, n], [w, n]],
        "fill": [255, 200, 87, 38] if q == selected_quarter else [98, 140, 255, 14],
        "when": "Click to open this quarter", "temp": "", "anom": "",
    } for q, (w, s, e, n) in QUARTER_BOUNDS.items() if q in quarters]
    outline = [{"path": [[WEST, SOUTH], [EAST, SOUTH], [EAST, NORTH], [WEST, NORTH], [WEST, SOUTH]]},
               {"path": [[MID_LON, SOUTH], [MID_LON, NORTH]]},
               {"path": [[WEST, MID_LAT], [EAST, MID_LAT]]}]
    selected = [f for f in footprints if f["quarter"] == selected_quarter]
    roads = _freeways()
    layers = [
        pdk.Layer("PathLayer", roads, id="freeway-glow", get_path="path", get_width=900,
                  width_min_pixels=5, get_color=[255, 138, 61, 45], pickable=False),
        pdk.Layer("PathLayer", roads, id="freeways", get_path="path", get_width=180,
                  width_min_pixels=1.5, get_color=[255, 170, 90, 210], pickable=False),
        pdk.Layer("PolygonLayer", footprints, id="quarters", get_polygon="polygon",
                  get_fill_color="fill", stroked=False, pickable=True, auto_highlight=True,
                  highlight_color=[255, 200, 87, 60]),
        pdk.Layer("PathLayer", outline, id="study-outline", get_path="path", get_width=120,
                  width_min_pixels=1.2, get_color=[255, 200, 87, 150], pickable=False),
        pdk.Layer("PathLayer", [{"path": f["polygon"] + [f["polygon"][0]]} for f in selected],
                  id="selected-outline", get_path="path", get_width=260, width_min_pixels=2.5,
                  get_color=[255, 200, 87, 255], pickable=False),
        pdk.Layer("ColumnLayer", bars, id="bars", get_position=["lon", "lat"],
                  get_elevation="height", elevation_scale=1, radius=330 if mode != "latest" else 2300,
                  disk_resolution=4 if mode != "latest" else 24, extruded=True,
                  get_fill_color="color", pickable=True, auto_highlight=True,
                  highlight_color=[255, 255, 255, 200], material={"ambient": 0.6, "diffuse": 0.6,
                                                                  "shininess": 40}),
        pdk.Layer("TextLayer", [{"text": QUARTER_NAMES[q].upper(), "lon": lon, "lat": lat}
                                for q, (lon, lat) in {
                                    "NW": (WEST + 0.06, NORTH + 0.025), "NE": (EAST - 0.06, NORTH + 0.025),
                                    "SW": (WEST + 0.06, SOUTH - 0.025), "SE": (EAST - 0.06, SOUTH - 0.025),
                                }.items() if q in quarters],
                  id="quarter-labels", get_position=["lon", "lat"], get_text="text", get_size=14,
                  get_color=[255, 200, 87, 255], character_set=CHARS, font_family=FONT, pickable=False),
        pdk.Layer("ScatterplotLayer", [{"lon": x, "lat": y} for _, x, y in PLACES], id="places",
                  get_position=["lon", "lat"], get_radius=380, radius_min_pixels=3,
                  get_fill_color=[234, 238, 249, 220], pickable=False),
        pdk.Layer("TextLayer", [{"text": name, "lon": x, "lat": y} for name, x, y in PLACES],
                  id="place-labels", get_position=["lon", "lat"], get_text="text", get_size=12,
                  get_color=[234, 238, 249, 230], get_pixel_offset=[0, -14], pickable=False,
                  character_set=CHARS, font_family=FONT),
    ]
    if mode == "latest":
        layers.append(pdk.Layer(
            "TextLayer", bars, id="latest-labels", get_position=["lon", "lat", "height"],
            get_text="text", get_size=16, get_color=[255, 255, 255, 255],
            get_pixel_offset=[0, -18], pickable=False, character_set=CHARS, font_family=FONT,
            outline_width=3, outline_color=[10, 15, 30, 255],
            font_settings={"sdf": True, "fontSize": 64, "buffer": 6}))
    return pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(longitude=-112.0, latitude=33.43, zoom=9.0, pitch=52,
                                         bearing=-18, max_pitch=75),
        map_style=BASEMAP,
        map_provider="carto",
        tooltip={"html": "<b>{label}</b><br/>{when}<br/>{temp}<br/>{anom}",
                 "style": {"backgroundColor": "#121A30", "color": "#EAEEF9", "fontSize": "13px",
                           "border": "1px solid #FFC857", "borderRadius": "10px"}},
    )
