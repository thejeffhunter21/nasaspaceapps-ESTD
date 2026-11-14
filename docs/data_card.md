# Phoenix study area monthly nighttime surface temperature

| Field | Specification |
|---|---|
| Dataset | NASA Terra/MODIS MOD11C3.061, archived by LP DAAC |
| DOI | https://doi.org/10.5067/MODIS/MOD11C3.061 |
| Source field | LST_Night_CMG |
| Measurement | Monthly clear-sky nighttime land surface temperature |
| Grid | 0.05 degrees; whole study window 12 x 16 cells |
| Period | 2003-01 through 2024-12; 264 month positions |
| Bounds (degrees) | West -112.4, south 33.2, east -111.6, north 33.8 |
| Subregions | Northwest, northeast, southwest, southeast; split at -112.0 longitude / 33.5 latitude; 48 cells each |
| CRS | Geographic latitude/longitude, EPSG:4326 |
| Raw output unit | Degrees Celsius |
| Anomaly output unit | Degrees Celsius difference |
| Baseline | Region-specific calendar-month mean over valid 2003-2024 values; 20-22 samples per group |
| Data version | phoenix-qc-v1.0 |

## Processing and QC

Mask packed LST fill value 0 and out-of-range values before scaling once: raw * 0.02 - 273.15 gives degrees Celsius. For this monthly product, retain produced QA codes 0/1 and the reported LST-error class <=1 K; require positive valid land and at least one valid clear night. Preserve other-quality warnings. Average accepted cells with cosine-latitude weights and require at least 80% accepted weighted area per regional month. Keep dates with missing values when the threshold is not met.

Anomaly = monthly temperature minus the same region's corresponding calendar-month baseline mean. The baseline needs at least two valid values; current delivered groups have 20-22. Full-period means describe this project record, not a standard 30-year climate normal.

## Data dictionary

| File | Column | Meaning |
|---|---|---|
| timeseries*.csv | date | Calendar month, YYYY-MM |
| timeseries*.csv | value | QC-screened regional monthly temperature, degrees Celsius; empty when missing |
| anomaly*.csv | date | Same calendar as corresponding timeseries CSV |
| anomaly*.csv | value | Temperature difference from calendar-month baseline; empty when input is missing |
| climatology.csv | region | phoenix for whole window, or phoenix_* subregion |
| climatology.csv | month | Calendar-month integer 1-12 |
| climatology.csv | mean | Valid raw-temperature mean over 2003-2024, degrees Celsius |
| climatology.csv | count | Number of valid values contributing to mean |
| coverage.csv | region | Same IDs as climatology.csv |
| coverage.csv | date | Calendar month, YYYY-MM |
| coverage.csv | accepted_cells | Integer number of cells passing the QC mask |
| coverage.csv | area_fraction | Accepted cosine-weighted cell area / fixed total regional cell area, from 0 to 1 |

The whole-window ID phoenix maps to phoenix_study_area where used by the API. A coverage fraction is not a quality score, confidence interval or land-cover percentage.

## Provenance and interpretation

Reference QC freeze: https://github.com/nergisRahimzade/NASA-Space-Apps-Challenges-2026---Be-an-Earth-System-Trend-Detective/pull/59

Raw CSV handoff: https://github.com/thejeffhunter21/nasaspaceapps-ESTD/pull/7

Anomaly handoff: PR #14, with file locations corrected in PR #16 of this repository.

Source product specification: https://ladsweb.modaps.eosdis.nasa.gov/filespec/MODIS/61/MOD11C3

See ../data/processed/manifest.json and manifest_anomalies.json for original file hashes, plus data_quality_manifest.json for coverage provenance and verification. See data_quality_report.md for exact missing months and sample limitations. Pin the generating code/data versions before regenerating results. The trend method and significance results are owned by AI and are not frozen by this data card.
