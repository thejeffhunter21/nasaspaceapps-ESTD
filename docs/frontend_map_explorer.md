# Map explorer (web/)

The new front end: one page built around a fixed 3D map of the Phoenix study window. It is a
static site (HTML, CSS, JavaScript with deck.gl 9.4.1 vendored in `web/vendor/`, MIT licence)
served by the existing API at **`/app/`** (`/explore` redirects there). The Streamlit dashboard
in `app/` is unchanged and stays available as a fallback.

```
USE_MOCK=false uv run --locked uvicorn earth_system_trend.api.app:app --port 8000
# open http://127.0.0.1:8000/app/
```

Because the page is served by the API, every merge to `main` deploys it with the API. No CDN is
needed: the only network request outside the API is the Esri World Light Gray basemap (no key), and without it the map
still shows the study grid, freeways (Natural Earth, `web/assets/`) and all data.

## What it shows

1. **Map, fixed camera.** Year slider (years in the data, 2003–2024) and month picker
   (January–December or annual average). One fixed 0–40 °C scale for colour and height.
2. **Scroll split.** Scrolling moves the four quarters (split at −112.0° / 33.5°) outward to
   their own corners; scrolling back up reverses it. With `prefers-reduced-motion` it jumps.
3. **Quarter panels.** Warming per year (backend slope × 12), significance, p, τ, yearly mean
   anomaly bars (years with all 12 months), the selected period's quarter average and the
   warmest month. The fastest significant warming quarter gets a subtle accent.
4. **Story.** Seasonal Mann-Kendall method (diagram drawn from the real whole-area anomalies),
   findings table from `/regions`, NASA data facts, limits, credits.

## Data rules

- Numbers come from `/regions`, `/series` and `/anomaly`, or from `web/data/grid.json`.
- A missing month stays missing. An annual average needs all 12 months; otherwise the cell or
  quarter shows as missing.
- **Per-cell columns need the Data layer's export.** Until `web/data/grid.json` exists, each
  quarter is shaded by its real regional average with a visible "Showing quarter averages"
  notice, and the 0.05° grid is drawn as outlines only. No cell values are estimated.

## Adding the per-cell data

1. Data layer exports `data/processed/grid_cells.csv`: `cell_id, lat, lon, quarter, date, value`,
   one row per cell per month (192 × 264), value in °C after qc-v1, empty when the cell failed.
2. `uv run --locked python scripts/build_grid_json.py`
   It refuses the file (and writes nothing) unless every cell has every month once, sits on the
   0.05° grid inside the window with the right quarter, has plausible values, and the
   cosine-latitude weighted mean of accepted cells reproduces every published regional month
   (`timeseries*.csv`) within 0.01 °C. On success it writes `web/data/grid.json` with the input
   SHA-256 and the comparison report.
3. Commit `grid_cells.csv` and `web/data/grid.json` together. The page switches to per-cell
   columns automatically.
