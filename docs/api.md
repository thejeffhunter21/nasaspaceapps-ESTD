# API reference

Base URL: **https://estd-api.onrender.com** (interactive version: `/docs`).
All endpoints are GET and return JSON. The first request after about 15 quiet minutes can take
about 50 seconds while Render's free tier wakes up.

`region` is optional everywhere (leave it out for the whole study area). It accepts the id
(`phoenix_northwest`) or the label (`Phoenix study area northwest`), any case.

| Region id | Label |
|---|---|
| `phoenix_study_area` | Phoenix study area |
| `phoenix_northeast` | Phoenix study area northeast |
| `phoenix_northwest` | Phoenix study area northwest |
| `phoenix_southeast` | Phoenix study area southeast |
| `phoenix_southwest` | Phoenix study area southwest |

## Endpoints

| Endpoint | Returns |
|---|---|
| `/` | Name, status and links to try |
| `/health` | `{"status": "ok"}` |
| `/version` | `{"commit": "<git sha>"}` of the live deploy |
| `/regions` | `{"regions": [{region_id, region, variable, units, period, trend}]}` |
| `/series?region=<id>` | `{region_id, region, variable, units, period, series: [{time, value}]}` |
| `/anomaly?region=<id>` | `{region_id, region, variable, units, period, baseline_period, series: [{time, value}], baseline: [{month, mean, count}]}` |
| `/trend?region=<id>` | `{region_id, region, variable, units, period, trend, explanation, explanation_source, source, method, forecast}` |
| `/results` | The whole results file for the study area (contract fields) |
| `/demo` | `{"cases": [{id, label, description, region_id, region, trend}]}` |

Field meanings: [contract.md](contract.md).

## Examples

`GET /series?region=phoenix_northwest`

```json
{
  "region_id": "phoenix_northwest",
  "region": "Phoenix study area northwest",
  "variable": "Nighttime land surface temperature",
  "units": "degC",
  "period": {"start": "2003-01", "end": "2024-12"},
  "series": [
    {"time": "2003-01", "value": 8.1389},
    {"time": "2003-02", "value": 7.1799},
    "... 264 months; a missing month is {\"time\": \"2024-05\", \"value\": null}"
  ]
}
```

`GET /anomaly?region=phoenix_northwest`: the same 264 months as `/series`, as the difference
from that region's 2003-2024 average for the same calendar month (°C). `null` exactly where
`/series` is `null`. `baseline` is the average temperature used for each calendar month and how
many years went into it.

```json
{
  "region_id": "phoenix_northwest",
  "region": "Phoenix study area northwest",
  "variable": "Nighttime land surface temperature",
  "units": "degC",
  "period": {"start": "2003-01", "end": "2024-12"},
  "baseline_period": {"start": "2003-01", "end": "2024-12"},
  "series": [
    {"time": "2003-01", "value": 2.2825},
    {"time": "2003-02", "value": -0.7008},
    "...",
    {"time": "2024-04", "value": 0.972},
    {"time": "2024-05", "value": null},
    {"time": "2024-06", "value": 2.7396}
  ],
  "baseline": [
    {"month": 1, "mean": 5.8564, "count": 22},
    {"month": 2, "mean": 7.8807, "count": 22},
    "... 12 months"
  ]
}
```

`GET /trend?region=phoenix_northwest`

```json
{
  "region_id": "phoenix_northwest",
  "region": "Phoenix study area northwest",
  "variable": "Nighttime land surface temperature",
  "units": "degC",
  "period": {"start": "2003-01", "end": "2024-12"},
  "trend": {"slope": 0.00755, "slope_unit": "degC/month", "p": 3.275e-10, "tau": 0.2795,
            "trend": "increasing"},
  "explanation": "From 2003-01 to 2024-12, nighttime land surface temperature in Phoenix study area northwest rose by about 0.00755 degC per month (0.0906 degC per year). This trend is statistically significant (p < 0.001). 1 of 264 months are missing and were left as gaps, not filled in.",
  "explanation_source": "fallback",
  "source": "NASA Terra/MODIS MOD11C3.061 ...; data version phoenix-qc-v1.0",
  "method": "Seasonal Mann-Kendall test (12-month period) with seasonal Sen's slope",
  "forecast": null
}
```

Display notes for the dashboard: show `degC` as °C and `degC/month` as °C/month; show p below
0.001 as "p < 0.001"; label `explanation_source: "fallback"` as "Automatic summary".

## Errors

| Status | When | Body |
|---|---|---|
| 404 | Unknown region | `{"detail": "Unknown region 'x'. Valid ids: ..."}` |
| 404 | No results file, or no anomaly data for that region | `{"detail": "..."}` |
| 422 | Bad `region` text (over 100 characters or odd symbols) | validation details |
| 429 | Over `RATE_LIMIT_PER_MINUTE` requests in a minute | `Retry-After` header gives the seconds to wait |
| 500 | A results file on the server is broken | which field is wrong |
| 504 | The request took longer than `REQUEST_TIMEOUT_S` | `{"detail": "The request took too long."}` |
