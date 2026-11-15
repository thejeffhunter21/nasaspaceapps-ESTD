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

- The page shows regional results only: `/regions`, `/series`, `/anomaly`.
- The per-cell dataset never reaches the browser. The page reads `/discoveries`, which carries
  the AI investigator's findings with statuses (supported / exploratory) and cell outlines only;
  choosing a discovery outlines its cells on the map. See `docs/analysis_service.md`.
- A missing month stays missing. An annual average needs all 12 months.
- Basemap: Esri World Street Map (no key). CARTO raster tiles now require an API key.
