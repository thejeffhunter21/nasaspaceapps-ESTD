# Data request: 1 km cell export (MOD11A2 v061) for the AI investigator

**For:** Data layer (Hayley) · **Used by:** private analysis service only (`/analysis/*`)

The current grid is MOD11C3 at 0.05° (≈5 km): 192 cells. MOD11C3 has no finer pixels, so more
individualized cells need a different NASA product. MOD11A2 v061 (8-day, 1 km) over the same
window gives about 30 × 60 ≈ 18,000 cells. The public map stays at 0.05°.

## What to export

Use the same file shape as `grid_cells.csv`, as a new file `grid_cells_1km.csv`:

```
cell_id,lat,lon,quarter,date,value
```

- `cell_id`: `rRRR_cCCC` (3-digit row and column, row 0 = north).
- `lat`, `lon`: pixel centre in degrees (reproject from sinusoidal; state the method).
- `quarter`: NW / NE / SW / SE using the same split at −112.0° / 33.5°.
- `date`: `YYYY-MM`, 2003-01 to 2024-12, one row per cell per month, including months that are
  missing.
- `value`: monthly mean nighttime LST in °C, or empty when missing.

## QC and monthly aggregation (please confirm or edit)

1. Use `LST_Night_1km`. Keep only 8-day composites whose `QC_Night` says "LST produced, good
   quality", or "other quality" with average LST error ≤ 1 K. These are the same rules as
   phoenix-qc-v1.0, where they apply.
2. Assign each 8-day composite to the month that contains its start date. Alternatively, weight
   by days in each month; say which you used.
3. A monthly value needs at least 2 valid composites. Otherwise leave it empty. Never fill or
   interpolate a missing month.
4. Convert from Kelvin with scale 0.02, then −273.15.

## Manifest (`grid_cells_1km_manifest.json`)

```json
{
  "file": "grid_cells_1km.csv",
  "sha256": "<sha256 of the CSV as committed>",
  "product": "MOD11A2.061",
  "variable": "LST_Night_1km",
  "cell_size_deg": 0.00833,
  "qc_policy": "<short description, version>",
  "monthly_rule": "<assignment rule, minimum composites>",
  "reproduces_regional_series": false,
  "rows": 0,
  "cells": 0
}
```

`reproduces_regional_series` must be `false`, because 1 km means will not equal the 0.05°
regional series. The loader then skips that check and records why.

## Size

Expect about 18,000 cells × 264 months ≈ 4.8 M rows, roughly 150 MB as CSV. If that is too
big for git, send it as gzip or Parquet and we will add a reader. Do not commit it to `web/`.

## Ready-to-send message

> Hey Hayley! Your grid_cells export is working great: it reproduces all 5 regional series
> exactly. Could you do a second export at 1 km for the AI investigator? Use MOD11A2 v061
> LST_Night_1km, same window, same columns as grid_cells.csv, monthly 2003–2024, with missing
> months left empty. The QC and monthly rules plus the manifest fields are in
> docs/data_request_1km.md. The one new manifest field is `"reproduces_regional_series": false`.
> No rush before the freeze: the service already accepts any cell size.
