# Grid-cell analysis service (private) and AI discoveries

Two resolutions of the same NASA data:

| Who | Sees | Where |
| --- | --- | --- |
| People (the map explorer at `/app/`) | Whole study area, four quarters, regional averages, trends, significance | `/regions`, `/series`, `/anomaly` |
| The AI investigator | All 192 quality-controlled 0.05° cells × 264 months | `/analysis/*` (private) |
| People, for verified findings | Statements, statuses and cell outlines, **never measurements** | `/discoveries` (public) |

## Data

`data/processed/grid_cells.csv` from the Data layer (PR #53). `analysis/grid.py` loads it
read-only and refuses to analyse if: the SHA-256 differs from `grid_cells_manifest.json`; any cell
lacks a month or repeats one; a centre is off the 0.05° grid or in the wrong quarter; a value is
implausible; or the cosine-latitude weighted cell means fail to reproduce the published regional
series. Failed-QC cell-months stay `None`. Nothing is filled, smoothed or changed.

## Private tools (`/analysis/*`)

Require header `X-Analysis-Token` equal to the `ANALYSIS_TOKEN` environment variable (set it in
Render; leave unset to disable the service, which then answers 503). `GET /analysis/tools` lists
them in a function-calling friendly format.

| Endpoint | What it does |
| --- | --- |
| `/analysis/cells`, `/analysis/cells/{id}/series` | Cell list; one cell's QC'd values |
| `/analysis/cells/{id}/trend` | Seasonal Mann-Kendall + seasonal Sen's slope, plus both halves |
| `/analysis/trends` | Every cell's trend with Benjamini-Hochberg q-values |
| `/analysis/localized` | Cell minus its quarter's published series: faster/slower warming, BH-corrected, halves challenge |
| `/analysis/seasonal?target=&season=` | Trend of yearly seasonal means (complete seasons only) |
| `/analysis/anomalies` | Robust z (median/MAD per calendar month); always exploratory |
| `/analysis/region-vs-cells?region=` | Regional trend versus the spread of its cells' trends |
| `/analysis/investigate` | Full investigation report with all evidence |

## AI investigator

`analysis/investigator.py` works hypothesis by hypothesis: it calls the tools, applies corrections
for testing many cells or seasons, then challenges each result (most often: does the direction hold
in both 2003–2013 and 2014–2024?). A finding is **supported** only if it is significant after
correction *and* survives its challenge; otherwise it is **exploratory**. Thresholds were fixed
before the results were seen. It is deterministic (no language model at run time, matching the AI
layer's release); the tool specs are ready for an LLM agent to call later.

Caveats reported with every result: surface not air temperature; serial correlation makes p and q
optimistic; neighbouring cells are spatially correlated; historical description, not a forecast.
