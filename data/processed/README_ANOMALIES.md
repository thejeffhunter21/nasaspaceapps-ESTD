# Phoenix monthly temperature anomalies

Data version: phoenix-qc-v1.0. Source: NASA Terra/MODIS MOD11C3.061 nighttime land surface temperature.
Dataset DOI: https://doi.org/10.5067/MODIS/MOD11C3.061
Reference QC data PR: https://github.com/nergisRahimzade/NASA-Space-Apps-Challenges-2026---Be-an-Earth-System-Trend-Detective/pull/59
Raw CSV handoff: https://github.com/thejeffhunter21/nasaspaceapps-ESTD/pull/7

## Calculation

For each region, average all valid Januaries from 2003-2024, then all valid Februaries, and so on.
Anomaly for a month = its QC-screened monthly temperature minus that region's mean for the same calendar month.
Use at least two valid baseline samples. All delivered groups have 20-22 samples.
Missing raw values remain missing anomalies. No interpolation or zero filling is used.

Units: degrees Celsius of temperature difference. Positive means warmer than the region's corresponding calendar-month baseline; negative means cooler. This is a project-specific 22-year baseline, not a standard 30-year climate normal.

## Five anomaly CSVs

All five use date,value and preserve 264 monthly positions from 2003-01 through 2024-12.

| File | Region | Valid / missing |
|---|---|---|
| anomaly.csv | Whole Phoenix study window | 264 / 0 |
| anomaly_phoenix_northwest.csv | Northwest | 263 / 1 |
| anomaly_phoenix_northeast.csv | Northeast | 262 / 2 |
| anomaly_phoenix_southwest.csv | Southwest | 262 / 2 |
| anomaly_phoenix_southeast.csv | Southeast | 261 / 3 |

date is YYYY-MM. value is a numeric anomaly in degrees Celsius, or an empty CSV cell for missing data. Use null in JSON.

## Baseline file

climatology.csv has 60 rows: 5 regions x 12 calendar months.
- region: phoenix for the whole study area, or the corresponding phoenix_* subregion ID.
- month: integer 1-12.
- mean: the region's mean raw temperature for that month, in degrees Celsius.
- count: number of valid baseline observations used.

Whole-area region ID mapping: climatology's phoenix refers to timeseries.csv / anomaly.csv; map it to phoenix_study_area if that is the backend's canonical ID.
Reduced counts: northwest May=21; northeast July=20; southwest July=20; southeast June=21 and July=20. All other groups have 22 samples.

## Scope and quality

The study window is west -112.4, south 33.2, east -111.6, north 33.8 degrees. Four boxes split at longitude -112.0 and latitude 33.5.
Input temperatures use the reviewed qc-v1 mask and at least 80% valid regional area. Anomalies inherit the raw data's clear-sky, coverage and observation-time limitations.
Anomaly values are not air temperature, daily extremes, future forecasts or significance-test results. Baseline subtraction removes the average seasonal cycle but does not establish that a trend is significant.

## Verification and integration

The archived qc-v1 anomaly and baseline files were independently checked against the exact raw CSVs delivered in PR #7. Every baseline mean/count and every nonmissing anomaly agrees within 1e-12 degrees Celsius. Each calendar-month anomaly mean is zero within that tolerance. Output bytes preserve the frozen manifest's checksums.
manifest_anomalies.json records input/output hashes, baseline counts, missing months and validation differences.

For GitHub, put the five anomaly CSVs and climatology.csv alongside the raw CSVs in data/processed/. This package's README_ANOMALIES.md and manifest_anomalies.json have distinct names to preserve the raw-data README and manifest.
Frontend toggle: raw reads timeseries*.csv, anomaly reads matching anomaly*.csv. Label the anomaly axis "Nighttime surface temperature anomaly (degrees C)" and show the 2003-2024 calendar-month baseline.
AI owns the trend method and significance analysis. Do not mix raw and anomaly results under the same variable label. Full-record baseline means are for descriptive trend exploration; a separate predictive backtest would need training-only baselines.
