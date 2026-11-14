# Results contract (v1.0)

One shape for every results file. The pipeline writes it, the API serves it,
the dashboard reads it. Code version: `src/earth_system_trend/contract.py`.
Example: `results.mock.json` (fake data, region "Example Region").

## Files

| File | When |
|---|---|
| `results.mock.json` | `USE_MOCK=true` (default). Fake data so everyone can build from hour 1 |
| `results/results.json` | Real data, whole study area |
| `results/regions/<region_id>.json` | Real data, one per sub-region |

## Fields

| Field | Type | Meaning |
|---|---|---|
| region_id | string | lowercase id, e.g. `phoenix_northwest`. Use in `?region=` |
| region | string | label shown to people |
| variable | string | e.g. "Land surface temperature" |
| units | string | units of `value`, e.g. "degC" |
| period.start / period.end | "YYYY-MM" | must equal the first and last `series[].time` |
| series | list | one point per month, in order, no repeats |
| series[].time | "YYYY-MM" | the month |
| series[].value | number or null | null = missing month (never NaN) |
| trend.slope | number | change **per month**, in `trend.slope_unit` |
| trend.slope_unit | string | e.g. "degC/month" |
| trend.p | number 0..1 | p-value. Significant if < 0.05 |
| trend.tau | number -1..1 | Kendall's tau |
| trend.trend | string | "increasing", "decreasing" or "no trend" |
| explanation | string | plain-language summary; only uses numbers in this file |
| explanation_source | string | "ai" or "fallback" (fallback = AI failed, text built from the numbers) |
| source | string | where the data came from, e.g. NASA MODIS MOD11C3.061 |
| method | string | exact trend test, e.g. "Mann-Kendall test (original) with Sen's slope" |

Unknown fields are rejected. Fewer than 24 valid months: the pipeline does not write a file.

## Functions from the AI layer (agreed at T+0)

- `run_trend(values: list[float | None]) -> dict` with `slope` (per month), `slope_unit`, `p`, `tau`, `trend`.
- `explain(results: dict) -> str`. Never raises. On failure returns a fixed fallback sentence.

## Data layer CSV

`data/processed/timeseries.csv` (and `timeseries_<region_id>.csv`): columns `time` (YYYY-MM) and `value`.
