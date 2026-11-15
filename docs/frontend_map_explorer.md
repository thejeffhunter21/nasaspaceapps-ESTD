# Map explorer (web/)

One page built around a fixed 3D map of the Phoenix study window. It is a static site (HTML, CSS,
JavaScript with deck.gl 9.4.1 vendored in `web/vendor/`, MIT licence) served by the existing API
at **`/app/`** (`/explore` redirects there). The Streamlit dashboard in `app/` is unchanged and
stays available as a fallback.

```
USE_MOCK=false uv run --locked uvicorn earth_system_trend.api.app:app --port 8000
# open http://127.0.0.1:8000/app/
```

Every merge to `main` deploys it with the API. The only request outside the API is the Esri World
Light Gray basemap (no key). Without it the map still shows the grid, freeways (Natural Earth,
`web/assets/`) and all data.

## What it shows

1. **Map, fixed camera, one column per 0.05° cell (192).** The year slider covers 2003–2024. The
   month picker has January to December plus an annual average. Playback has a speed setting and
   prefetches the next frame. It pauses when the tab is hidden or the map scrolls away.
2. **Layers.** Each layer has its own scale and legend:
   - Temperature: 0–40 °C columns.
   - Anomaly: ±4 °C, diverging. The baseline is the same cell's mean for that calendar month.
   - Warming rate: 0–0.2 °C/yr. Cells that are not significant after FDR correction are faded.
   - Coverage: valid months in the selected year, 0–12.
   Cells with no valid value are drawn as an outline only.
3. **Cell inspector.** Click a cell to see:
   - Its value and anomaly for the period, and valid months that year.
   - Its 2003–2024 trend with a 95% confidence interval.
   - The FDR q-value and valid months overall.
4. **Region filter.** All, NW, NE, SW or SE. The other quarters are dimmed.
5. **Scroll split.** The four quarters move outward to their own panels, each showing:
   - Warming per year with its 95% CI, p and τ.
   - Yearly anomaly bars.
   - The selected period's quarter average and valid months.
6. **Compare.** Any two periods side by side, plus a difference map and regional ΔT.
   **Region test:** a direct seasonal Mann-Kendall test on the monthly difference between two
   quarters (`/region-compare`).
7. **Coverage.** Valid cell-months per cell across all 264 months (50,276 of 50,688, 99.2%).
8. **Ask the Climate Detective.** A question box (with example chips) sends the question to
   `POST /ask`. The answer card shows a large headline, up to four coloured stat tiles, short
   details, the method, which tools computed it, and a button that outlines the answer's cells
   on the map. No language model runs: see `docs/analysis_service.md`.
9. **What the AI found on its own.** Compact cards (status, title, one-line summary, "Show on
   map", "Ask: <next question>"). Evidence, method and caveats fold away under "How we know".
10. **Share and export.** All view state is kept in the URL hash: year, month, layer, region,
    cell, finding and the compare periods, so a copied link reopens the same view. "Download
    CSV" exports the current frame with a metadata line.
11. **Footer.** One line of limits (not a forecast; surface, not air, temperature; annual mean
    only with 12 months; gaps never filled) and credits. The older story sections (method,
    findings table, data facts, limits) and the separate Climate Detective block were removed
    to keep the page focused; their numbers remain available through the question box and API.

Colours: Turbo ramp for temperature, a saturated diverging ramp for anomalies, Plasma for
warming rate, Viridis for coverage; one colour per quarter (NW teal, NE violet, SW amber,
SE pink) and a blue–violet–pink–orange accent gradient.

## Endpoints the page uses

| Endpoint | Returns |
| --- | --- |
| `/regions`, `/series`, `/anomaly` | Existing regional contract (unchanged; byte-identical to `main`) |
| `/map-frame?year=&month=` | One period: per cell `value`, `anomaly`, `valid_months_in_year`. `month` is `1`–`12` or `avg` (needs all 12 months) |
| `/map-static` | Per cell: id, centre, quarter, footprint, trend, CI, p, q, direction, valid months |
| `/region-stats` | Published quarter slopes with Sen's slope 95% CI and valid months |
| `/region-compare?a=&b=` | Direct test on the monthly difference A − B |
| `/discoveries` | Verified findings with full fields plus a one-line `summary`; no raw series |
| `POST /ask` | Answer to a free-text question: `headline`, `stats`, `details`, `method`, `caveat`, `cells`, `tools_used`, `kind` |

## Data rules

- Cells reach the browser one period at a time. The full grid file stays on the server, and
  `web/` never references it.
- A missing month stays missing. An annual value needs all 12 months.
- Transitions between frames are eased for readability; only the settled frame is data.
- No secrets in the page or the URL. The private `/analysis/*` service is never called from
  the browser.
- Not built yet (deliberately not faked): notebook, PDF export, onboarding tour, and 1 km cells
  (see `docs/data_request_1km.md`).
