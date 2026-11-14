# Phoenix study area data quality report

Data version: phoenix-qc-v1.0. The coverage file is copied unchanged from the QC freeze associated with reference PR #59. All input raw CSVs match the previously delivered qc-v1 files.

## Coverage and missing months

Each region has 264 calendar positions from January 2003 through December 2024. A monthly value requires at least 80% accepted cosine-latitude-weighted area. The coverage denominator is the fixed total cell area of that region.

| Region | Valid months | Missing months | Lowest valid-area fraction across all months |
|---|---:|---:|---:|
| phoenix | 264 | 0 | 81.26% |
| phoenix_northwest | 263 | 1 | 75.01% |
| phoenix_northeast | 262 | 2 | 72.92% |
| phoenix_southwest | 262 | 2 | 77.09% |
| phoenix_southeast | 261 | 3 | 68.75% |

| Region | Missing month | Accepted cells / total | Accepted weighted area |
|---|---|---:|---:|
| phoenix_northwest | 2024-05 | 36 / 48 | 75.01% |
| phoenix_northeast | 2007-07 | 35 / 48 | 72.92% |
| phoenix_northeast | 2023-07 | 38 / 48 | 79.16% |
| phoenix_southwest | 2007-07 | 37 / 48 | 77.09% |
| phoenix_southwest | 2010-07 | 38 / 48 | 79.16% |
| phoenix_southeast | 2012-07 | 33 / 48 | 68.75% |
| phoenix_southeast | 2017-07 | 37 / 48 | 77.08% |
| phoenix_southeast | 2024-06 | 38 / 48 | 79.19% |

## Validation performed

- coverage.csv SHA-256 matches the qc-v1 freeze manifest.
- 1,320 unique region/month records: 5 regions x 264 months, with complete calendars.
- Area fractions are finite and between 0 and 1; accepted-cell counts are valid integers within regional bounds.
- Every value below 80% coverage corresponds to exactly one empty raw CSV value, and every empty raw value has coverage below 80%.
- The four subregion accepted-cell counts sum to the whole-window count for every month.
- All five input CSV SHA-256 hashes match qc-v1. The eight gap dates match the freeze record.

These checks validate the delivered coverage record and its consistency with the CSVs. They do not constitute an independent rerun of the original HDF4 retrieval or every pixel-level QC calculation.

## Handoff rules

Backend: keep all monthly dates and encode missing values as null. Do not interpolate, fill with zero, or drop rows before seasonal grouping. Rebuild saved trend/explanation results from the same CSV version.

Frontend: show missing values as gaps with a reason such as "Insufficient valid area (<80%)". Coverage is area completeness, not statistical confidence or a probability. Use the detailed file for exact fractions; percentages above are rounded for display.

AI: preserve calendar alignment and use the selected trend method's explicit eligibility rules. A loader's minimum sample count does not by itself establish scientific adequacy. Document slope units, seasonality and serial-dependence treatment.

coverage.csv uses region ID phoenix for the whole study window. Map this to phoenix_study_area if that is the application's canonical ID. Subregion IDs are unchanged.

## Limitations

The data describe clear-sky nighttime surface temperature over a fixed study rectangle, not 2 m air temperature or official city boundaries. Clouds, changing observation times, and varying accepted spatial area can affect the sample. The reported <=1 K retrieval-error class does not guarantee total accuracy <=1 K. The 80% area rule is a project QC choice, not a NASA-mandated threshold. This report does not establish a final trend, a causal mechanism or a weather forecast.
