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
| trend.slope | number | change **per month**, in `trend.slope_unit`. The seasonal test gives per year; the AI layer divides by 12 (see [ai.md](ai.md#slope-units)) |
| trend.slope_unit | string | e.g. "degC/month" |
| trend.p | number 0..1 | p-value. Significant only if p < 0.05 (strict: p = 0.05 is not significant) |
| trend.tau | number -1..1 | Kendall's tau |
| trend.trend | string | "increasing", "decreasing" or "no trend" |
| explanation | string | plain-language summary; only uses numbers in this file |
| explanation_source | string | "ai" or "fallback" (fallback = AI failed, text built from the numbers) |
| source | string | where the data came from, e.g. NASA MODIS MOD11C3.061 |
| method | string | exact trend test, e.g. "Seasonal Mann-Kendall test (12-month period) with seasonal Sen's slope" |
| forecast | object or absent | optional, main region only. Omitted from `/results` when there is none |
| forecast.method | string | e.g. "Holt-Winters (12-month season)" |
| forecast.months | integer >= 1 | months ahead |
| forecast.points[] | list | `time` (YYYY-MM), `value`, `low`, `high`; `low <= value <= high` |
| forecast.backtest_mae | number >= 0 or null | error on held-out past months |
| forecast.beats_baseline | bool or null | whether it beat a simple baseline in the backtest |
| forecast.note | string | caveat shown with the forecast |

Unknown fields are rejected. Fewer than 24 valid months: the pipeline does not write a file.

## Functions from the AI layer

Agreed at T+0 and updated to the AI layer guide. The pipeline imports them in one place
(`pipeline/run.py`); until the AI layer's versions land, `pipeline/stubs.py` provides them.

- `run_trend(values: list[float | None], method: str = "seasonal", alpha: float = 0.05) -> dict`
  returns `slope` (per month), `slope_unit`, `p`, `tau`, `trend`. `values` is the full monthly
  calendar in order, with `None` for missing months (never dropped). The pipeline fills in
  `slope_unit` from `units`.
- `explain(results: dict) -> {"text": str, "source": "ai" | "fallback"}`. Never raises. AI text is
  shown only if it passes the explanation checks; otherwise `source` is `"fallback"` and the text
  is built from the numbers.
- `forecast(values: list[float | None], months: int = 12) -> dict | None`. Optional; `None` means
  no forecast block.

Method, missing-value handling and checks: [ai.md](ai.md).

## Data layer CSV

`data/processed/timeseries.csv` (and `timeseries_<region_id>.csv`): columns `date` (YYYY-MM) and
`value`, one row for every month 2003-01..2024-12; an empty `value` cell is a missing month.
The loader also accepts `time` as the date column. Details: [data_card.md](data_card.md),
[data_quality_report.md](data_quality_report.md).
