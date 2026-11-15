# Grid-cell analysis service (private) and AI discoveries

Two levels of access to the same NASA data:

| Who | Sees | Where |
| --- | --- | --- |
| People (map explorer at `/app/`) | Regional results; one period of cell values at a time; per-cell trends with CI | `/regions`, `/series`, `/anomaly`, `/map-frame`, `/map-static`, `/region-stats`, `/region-compare` |
| The AI investigator | Every cell × every month, with analysis tools | `/analysis/*` (private, token) |
| People, for verified findings | Statements, statuses, evidence text, cell outlines; no raw series | `/discoveries` |

## Data

`data/processed/grid_cells.csv` comes from the Data layer (PR #53). `analysis/grid.py` loads it
read-only and refuses to analyse if any of these checks fail:

- The SHA-256 differs from `grid_cells_manifest.json`.
- Any cell lacks a month or repeats one.
- A centre is off the grid (`cell_size_deg` from the manifest) or in the wrong quarter.
- A value is implausible.
- The cosine-latitude weighted cell means fail to reproduce the published regional series
  (tolerance 1e-4). This check is skipped only when the manifest says
  `reproduces_regional_series: false`, for example a finer grid. The skip is recorded in the
  provenance.

Failed-QC cell-months stay `None`. Nothing is filled, smoothed or changed. The loader works at
any resolution, so a 1 km export (see `docs/data_request_1km.md`) drops in without code changes.

## Statistics

- Seasonal Mann-Kendall and seasonal Sen's slope (pymannkendall, through the AI team's
  `run_trend`).
- **Sen's slope 95% CI** (Gilbert 1987): pool the within-season pairwise slopes, then
  C = z·√Var(S) using the seasonal test's variance. The bounds are the slopes at ranks (N−C)/2
  and (N+C)/2 + 1. The median equals the published slope exactly; a test checks this.
- **Region vs region:** seasonal Mann-Kendall on the monthly difference A − B. This tests the
  difference directly instead of comparing two separate p-values.
- Benjamini-Hochberg q-values across the 192 cells.

## Private tools (`/analysis/*`)

These require the header `X-Analysis-Token` to equal the `ANALYSIS_TOKEN` environment variable.
Set the token in Render. If it is unset the service answers 503; a wrong token gets 401.
`GET /analysis/tools` lists the tools in a function-calling format.

| Endpoint | What it does |
| --- | --- |
| `/analysis/cells`, `/analysis/cells/{id}/series` | Cell list; one cell's QC'd values |
| `/analysis/cells/{id}/trend` | Trend, 95% CI, valid months, both halves |
| `/analysis/trends` | Every cell's trend with CI and BH q-values |
| `/analysis/localized` | Cell minus its quarter's published series: faster or slower warming, BH-corrected, halves challenge |
| `/analysis/seasonal?target=&season=` | Trend of yearly seasonal means (complete seasons only) |
| `/analysis/anomalies` | Robust z (median/MAD per calendar month); always exploratory |
| `/analysis/region-vs-cells?region=` | Regional trend versus the spread of its cells' trends |
| `/analysis/region-stats`, `/analysis/region-difference?a=&b=` | Same as the public endpoints, as tools |
| `/analysis/investigate` | Full investigation report with all evidence |

## AI investigator

`analysis/investigator.py` works through one hypothesis at a time:

1. It calls the tools.
2. It applies corrections for testing many cells or seasons.
3. It challenges each result. The usual challenge: does the direction hold in both 2003–2013
   and 2014–2024?

A finding is **supported** only if it is significant after correction *and* survives its
challenge; otherwise it is **exploratory**. Thresholds were fixed before the results were seen.
The investigator is deterministic (no language model at run time).

Each public discovery carries: title, hypothesis, status, observation, location, period, source,
variable, method, evidence text, sample size, confidence, limitations, next question, and the
cell outlines.

Caveats reported with every result:
- This is surface temperature, not air temperature.
- Serial correlation makes p and q optimistic.
- Neighbouring cells are spatially correlated.
- This is a historical description, not a forecast.
