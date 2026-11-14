# AI layer: trend method, checks and explanations

Rule: **code computes every number; the AI only writes words.** The trend statistics come from a
fixed statistical test. Gemini may only rephrase them, and its text is shown only if it passes
the explanation checks.

Data version described here: phoenix-qc-v1.0 (see [data_card.md](data_card.md),
[data_quality_report.md](data_quality_report.md)). Results shape: [contract.md](contract.md).

## Trend method

**Seasonal Mann-Kendall test (12-month period) with seasonal Sen's slope**, via
`pymannkendall.seasonal_test(values, period=12)`, alpha = 0.05. This exact string is written to
`method` in every results file.

How it works: the 264 monthly values are arranged as 22 years x 12 calendar months. Each
calendar month is compared only with the same month in other years (January with January, and so
on). The 12 Mann-Kendall scores are summed into one test. The slope is the median of all
same-month pairwise slopes `(x[year j] - x[year i]) / (j - i)`.

### Why seasonal, not the plain test

Nighttime surface temperature in Phoenix swings by about 24 degC over a year (study-area
calendar-month means: January 5.6 degC, July 30.0 degC). That cycle hides
the long-term change from the plain (original) Mann-Kendall test:

| Study area, 2003-01..2024-12 | Result | p |
|---|---|---|
| Plain Mann-Kendall | no trend | 0.199 |
| Seasonal Mann-Kendall | increasing | 7.0e-11 |

Results from the plain test must not be relabelled as seasonal, or the other way round.

### Raw values or anomalies

The trend is run on the raw monthly temperatures (`timeseries*.csv`). Running it on the anomaly
files (`anomaly*.csv`) gives the identical slope, p and tau: subtracting one constant per calendar
month does not change any same-month comparison. Anomalies are for display, not a second result.

## Slope units

`seasonal_test` reports the slope **per year**, because its time step is one full 12-month
cycle. The contract requires **per month**, so the AI layer divides by 12:

```
slope_per_month = seasonal_test(...).slope / 12      # slope_unit = "<units>/month", e.g. degC/month
```

Checked for all five regions: an independent seasonal Sen's slope calculation matches the
library to 1e-12, and the stored slope equals per-year / 12 (study area: 0.09255 degC/year ->
0.007713 degC/month). On a synthetic series with a known slope of 0.0100 degC/month plus a
10 degC seasonal cycle, noise and three gaps, `run_trend` returns 0.0097.

Displays that show a per-year or per-decade figure must label it and compute it as slope x 12
(or x 120) from the stored per-month value.

## Missing months

- Every region keeps all 264 calendar positions. A missing month is `None` in Python, an empty
  cell in the CSV and `null` in JSON. It is never interpolated, filled with zero, or dropped.
- Keeping the position matters: the 22 x 12 grid is built by position, so dropping a gap would
  slide every later month into the wrong calendar column. On qc-v1 that would change the
  southeast slope from 0.0089 to 0.0149 degC/month.
- Inside the test, each calendar month skips only its own missing years. The other 11 months are
  unaffected, and pairwise slopes keep the true year gap `(j - i)`.

Expected gaps in qc-v1 (all below the 80% valid-area rule): northwest 2024-05; northeast
2007-07, 2023-07; southwest 2007-07, 2010-07; southeast 2012-07, 2017-07, 2024-06.

## Significance

- Significant only if **p < 0.05**, compared on the unrounded p. p = 0.05 is not significant.
- "Not significant" means the test found insufficient evidence of a trend, not that the change
  is zero.
- Known issue: results files currently store p rounded to 6 decimals, so very small values
  appear as `0.0`. This does not change any significance decision on qc-v1 (the largest p is
  3.8e-06), but the frontend plan asks for the unrounded value.

## Serial dependence

The seasonal test assumes the years within each calendar month are independent, and that the 12
months can be summed as independent tests. Neither correction is applied in the reported
results. Sensitivity check on qc-v1:

| Region | Seasonal p (reported) | Hirsch-Slack corrected p | Trend after correction |
|---|---|---|---|
| Study area | 7.0e-11 | 3.2e-05 | increasing |
| Northwest | 3.3e-10 | 8.4e-05 | increasing |
| Northeast | 3.8e-06 | 5.3e-04 | increasing |
| Southwest | 3.0e-10 | 7.3e-05 | increasing |
| Southeast | 2.8e-14 | 7.7e-05 | increasing |

The Hirsch-Slack correction (`pymannkendall.correlated_seasonal_test`) allows for correlation
between calendar months. It makes p larger in every region, but all five stay significant at
p < 0.001. Year-to-year correlation within a calendar month, after removing each month's linear
trend, is slightly negative (mean lag-1 r about -0.10), so it does not inflate significance.
**Conclusion: the reported direction and significance hold with or without the correction.** The
reported p-values are from the uncorrected test and are smaller than the corrected ones.

## Eligibility

- Current rule: the pipeline writes no results file for a series with fewer than 24 valid months
  (`pipeline/timeseries.py`).
- That rule alone does not establish that the seasonal test is adequate. qc-v1 easily exceeds it:
  every calendar month has 20-22 valid years in every region.
- Open decision for the AI layer: a per-calendar-month minimum (for example, at least 10 valid
  years in every calendar month) before the seasonal test is reported. Until it is agreed, the
  24-month rule is the only one enforced.

## Explanations

| Unit | File | What it does |
|---|---|---|
| A1 | `ai/ai_setup.py` | Builds the Gemini client from `GEMINI_API_KEY` and `GEMINI_MODEL`. No key: AI is off and the fallback is used. A 404 (wrong model or endpoint) fails at once. |
| A2 | `ai/ai_retry.py` | Retries timeouts, dropped connections, 408, 429 and 5xx up to 3 attempts (1 s, 2 s waits; 8 s cap). A long Retry-After, a bad key (401/403) or a bad request stops at once. Errors and logs never include the provider's response body. |
| A3 | `ai/ai_checks.py` | `check_explanation(text, results)` rejects text with numbers or dates not derived from the results, wrong significance wording, a direction that contradicts the trend, causes, forecasts, advice, the wrong product (air temperature, daily) or unit (Fahrenheit), or more than 600 characters. Never raises; anything it cannot check fails. |
| A4 (next) | | `explain()`: prompt from the results, call through A2, check with A3, return `{"text", "source": "ai"}` or the fallback. |

The fallback text (`pipeline/stubs.py: fallback_text`) is built from the numbers only and passes
the A3 checks on every committed results file.

The checks are pattern-based. They catch the common ways a model drifts but cannot fully
understand meaning (a paraphrased cause can slip through), so they are a safety net, not proof.

## What the results do not say

Monthly clear-sky nighttime land surface temperature over a fixed rectangle. Not 2 m air
temperature, not daily extremes, not city boundaries. A trend is not a cause and not a forecast.

## Verification log

Run on 2026-11-14 against qc-v1 (`main` at 004c47f). All passed:

- All five CSVs: 264 rows, 2003-01..2024-12, gaps as listed above; the pipeline loader keeps every
  position.
- Results JSON: nulls at the same months; re-running `run_trend` reproduces every stored trend.
- `climatology.csv`: means and counts equal the 2003-2024 calendar-month means of the raw CSVs;
  every anomaly equals raw minus the same-month mean (difference 0.0); each month's anomalies
  average 0.
- Manifest checksums match; a month is blank exactly when its valid area is below 80%.
- Slope units and the serial-dependence sensitivity above.
