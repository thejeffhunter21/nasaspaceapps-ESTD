# Monthly trend verification

Numerical verification passes for all five Phoenix study area regions. The documented AI function, committed results and live API agree with an independent seasonal Mann-Kendall and seasonal Sen calculation on the actual pipeline inputs.

Checked source commit: `24f7d0bac2ebd1e43d9dbb57d134db7968acebfb`. Data version: `phoenix-qc-v1.0`. Live responses captured at `2026-11-14T23:18:15.470014+00:00`. The local working copy used by the running frontend was not changed.

## Regional comparison

All rows have 264 calendar positions. Slopes below are degrees Celsius per month/year; p-values are from the documented uncorrected seasonal test. Values here are rounded only for readability; full precision is retained in the JSON report.

| Region | Missing months | Slope (C/month) | Slope (C/year) | p-value | Code / stored / live |
|---|---:|---:|---:|---:|---|
| phoenix_study_area | 0 | 0.007712500 | 0.09255000 | 7.022636e-11 | Match |
| phoenix_northwest | 1 | 0.007551471 | 0.09061765 | 3.275029e-10 | Match |
| phoenix_northeast | 2 | 0.005289583 | 0.06347500 | 3.799507e-06 | Match |
| phoenix_southwest | 2 | 0.007761667 | 0.09314000 | 2.979983e-10 | Match |
| phoenix_southeast | 3 | 0.008890625 | 0.10668750 | 2.780312e-14 | Match |

All five results are classified as increasing at alpha = 0.05 by this implemented method. This is conditional on the named method and its assumptions; numerical agreement is not scientific approval of every assumption.

## Independent checks

The reference implementation explicitly forms all valid same-calendar-month pairs. It calculates the score, tie-corrected variance, tau, continuity-corrected z and two-sided p using `math.erfc`. It independently takes the median of same-month pairwise slopes using original year-index gaps, then divides the per-year slope by 12. It does not call pyMannKendall or SciPy for those reference calculations.

- All five raw CSV hashes match the delivered data manifest.
- All calendars and eight missing positions survive CSV loading, stored JSON and live /series output.
- Independent slopes, p-values, tau and classifications match the current AI function and stored results. Method labels and degC/month units match.
- Positive and negative known-slope synthetic cases recover +0.010 and -0.008 C/month with a seasonal cycle and gaps, including a missing first month. A flat seasonal case gives no trend. A case with only nine valid Julys is rejected by the project's ten-year-per-month rule. These four cases are synthetic, not NASA measurements.
- Raw/anomaly full-precision trends agree within numerical tolerance, as expected for subtracting one fixed baseline constant per calendar month.
- Dropping missing rows changes seasonal alignment; the report records the resulting wrong slopes as a diagnostic. Missing dates must remain present.
- Live unknown-region request returns 404. All five live p-values are now positive and unrounded; the earlier p=0 deployment issue was not present during this check.
- Existing AI trend and pipeline integration tests: **62 passed**. Ruff passed for the added verification script. No Gemini/OpenAI requests were used for numerical verification or those tests.

## Input rounding is analytical preprocessing

The current CSV loader rounds temperature values to four decimal places **before** running the trend test. This is not only a frontend display change. We checked both the full-precision CSVs and the rounded pipeline inputs.

The largest raw-to-pipeline temperature change is below 0.00005 C. The largest seasonal-slope change is 6.55038863e-07 C/month. No regional direction or significance classification changes in this comparison. The report preserves both sets of statistics. If input precision policy changes, regenerate statistics, saved explanations and the numerical report together.

## Correlation sensitivity and limits

The reported method is `pymannkendall.seasonal_test(..., period=12)` with seasonal Sen slope. It is not `correlated_seasonal_test`. Current docs/ai.md explicitly describes the reported method and its uncorrected assumptions.

As a secondary library comparison, `correlated_seasonal_test(period=12)` produces:

| Region | Correlated-seasonal p | Direction |
|---|---:|---|
| phoenix_study_area | 3.244768e-05 | increasing |
| phoenix_northwest | 8.388855e-05 | increasing |
| phoenix_northeast | 5.282028e-04 | increasing |
| phoenix_southwest | 7.336530e-05 | increasing |
| phoenix_southeast | 7.645502e-05 | increasing |

This sensitivity comparison uses the library implementation; its covariance calculation was not independently reimplemented here. It addresses correlation between seasonal components and is not a general guarantee against year-to-year serial dependence. A slightly negative average lag correlation is not proof of independence. The AI owner retains responsibility for the final method and interpretation. Do not rename the reported test as correlation-corrected on the basis of this comparison.

Other limits: the data concern clear-sky nighttime surface temperature, not air temperature; observation-time and sampling biases remain. This review does not validate causal attribution, forecasting, the 17 conversational question cases or frontend rendering. Live numerical matches do not prove a particular deployment commit because the API does not expose verified code provenance.

## Reproduce

From the repository root, using the locked project dependencies:

```sh
uv run --locked python scripts/verify_monthly_trends.py --source-commit <checked-commit> --out /tmp/monthly_trend_verification.json
```

Add `--api-url https://estd-api.onrender.com` for a fresh live comparison. Supply the actual checked checkout commit, not this report's historical commit when running on changed code. The command exits nonzero on a numerical or live mismatch; it writes only its report and does not rebuild results or call an AI service. Source code and input hashes are recorded in the report. A later API deployment requires a new timestamped run.

For the existing method tests:

```sh
uv run --locked pytest tests/ai/test_trend.py tests/ai/test_pipeline_integration.py -q
```

Machine-readable evidence: [monthly_trend_verification.json](evidence/monthly_trend_verification.json).

Primary implementation references: [pyMannKendall source](https://github.com/mmhs013/pyMannKendall/blob/v1.4.3/pymannkendall/pymannkendall.py) and [project method document](ai.md). The environment used pyMannKendall 1.4.3, NumPy 2.5.4 and SciPy 1.18.1, matching the checked lockfile versions.
