# Phoenix monthly nighttime land surface temperature

Source: NASA Terra/MODIS MOD11C3.061 (LP DAAC).
Dataset DOI: https://doi.org/10.5067/MODIS/MOD11C3.061
Data version: phoenix-qc-v1.0, associated with reference repository PR #59.
Reference: https://github.com/nergisRahimzade/NASA-Space-Apps-Challenges-2026---Be-an-Earth-System-Trend-Detective/pull/59

## Files and columns

Each CSV has the columns `date,value`, with 264 monthly rows from 2003-01 through 2024-12.
- `date`: calendar month, YYYY-MM.
- `value`: area-weighted monthly nighttime land surface temperature in degrees Celsius.
- Empty value: insufficient valid area under the QC policy. Preserve the month; use null in JSON. Do not replace with zero or remove the date.

| File | Area | Missing values |
|---|---|---:|
| timeseries.csv | Whole study window | 0 |
| timeseries_phoenix_northwest.csv | Northwest | 1 |
| timeseries_phoenix_northeast.csv | Northeast | 2 |
| timeseries_phoenix_southwest.csv | Southwest | 2 |
| timeseries_phoenix_southeast.csv | Southeast | 3 |

## Spatial definition

Fixed study rectangle in geographic coordinates: west -112.4, south 33.2, east -111.6, north 33.8 degrees. This is a study window, not an official city boundary.
Four subregions split at longitude -112.0 and latitude 33.5. Source grid: 0.05 degrees; 192 whole-window cells and 48 per subregion. Regional means use cosine-latitude area weights.

## Quality control

qc-v1 accepts produced retrieval QA codes 0/1, reported LST error class <=1 K, positive valid land, and at least one valid clear night. At least 80% of the fixed region's weighted cell area must be valid. The reported-error and coverage thresholds do not guarantee total error <=1 K. Clear-sky and observation-time sampling limitations remain.

Missing months:
- Northwest: 2024-05.
- Northeast: 2007-07, 2023-07.
- Southwest: 2007-07, 2010-07.
- Southeast: 2012-07, 2017-07, 2024-06.

These are raw monthly temperature series after QC, not anomalies or trend statistics. They measure surface temperature, not air temperature. The AI owner should preserve calendar positions, document the trend method, and validate slope units.

## Verification

The five CSVs were copied byte-for-byte from the existing processed data. All SHA-256 checksums match the qc-v1 freeze manifest. Headers, complete ordered calendars, finite numeric values, and exact missing dates were checked. See manifest.json for hashes and source reference.
