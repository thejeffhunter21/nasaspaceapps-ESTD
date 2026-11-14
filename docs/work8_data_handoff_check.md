# Work 8: data handoff integration check

Core data-handoff checks pass for all five Phoenix study area regions. No data, statistics, method or application code was changed by this review. The anomaly view remains pending with frontend/backend.

Checked source snapshot: `d5f531af4cbb3c01bac999819339be8da30aab79`. API: `https://estd-api.onrender.com`. Check time: `2026-11-14T23:32:37.230197+00:00`. Data version: `phoenix-qc-v1.0`.

## Results

| Check | Outcome |
|---|---|
| Five supported regions | Correct IDs and Phoenix study area labels |
| Source | MOD11C3.061, nighttime LST field, DOI and qc-v1 version present for all five |
| Measurement / units / period | Nighttime land surface temperature; degC; 2003-01 to 2024-12; slope degC/month |
| Series / trend identity | Region, variable, units and period agree for every paired response |
| Monthly observations | Every date and pipeline-rounded value matches the checked CSV snapshot |
| Missing values | All eight subregion gaps preserved as nulls; full area has no gaps |
| Statistics and explanations | Match the checked saved result; current explanation guards pass |
| P-value precision | Positive p-values retained; earlier rounded-to-zero deployment issue absent |
| Unsupported city | Tucson returns 404 on both /series and /trend |
| Unknown region ID | not_a_real_region returns 404 on both endpoints |
| Invalid input | <invalid> returns 422 on both endpoints |
| Region label lookup | Uppercase Phoenix study area northwest resolves correctly on both endpoints |
| Frontend component replay | All five captured live responses produce matching headings, chart traces, cards, source/method captions and explanations |
| Gap rendering instruction | Plotly trace retains all null positions and connectgaps=False for all five regions |
| Existing frontend/API tests | 116 passed |

## What was checked in the frontend

The current app was run in Streamlit AppTest with captured real catalog, series and trend responses, replayed deterministically through its requests client. Each of the five regions was selected. Every chart x/y value, heading, slope/p/direction card, explanation, source/method label and connection label matched the same selected region. No sample warning appeared for these real-data responses.

These are component-level checks, not a new browser visual review. They verify chart data and configuration but do not establish responsive layout, hover behavior or visible gap width at every zoom level. Existing mocked frontend/API tests separately exercise switching, cache behavior and specific failure states. Captured response digests and per-check results are in the JSON evidence.

All live explanations were labeled fallback at the check time, and the frontend correctly displayed Automatic summary (AI unavailable). This is a functioning deterministic explanation path. It does not establish that a live conversational AI interface is connected. Previously reviewed answers to the 17 evidence questions remain a separate model-answer evaluation.

## Remaining items and owners

| Item | Owner | Status / next check |
|---|---|---|
| Anomaly view | Frontend/backend | Pending: no anomaly control in checked frontend and no anomaly option/route in live OpenAPI. Once implemented, compare all 264 dates/values for all five regions with anomaly CSVs and preserve gaps. Spot checks: whole-area January 2003 approximately +2.1392 C; northwest May 2024 null. |
| Conversational chat | AI/backend/frontend | Not integrated in checked dashboard: no chat input or chat route documented by current OpenAPI. Track separately if it remains part of the demo scope. |
| Actual AI-generated explanation path | AI/backend | Fallback is correctly labeled. Check a real approved AI response if enabling that provider path for the demo. |
| Final visual review | Frontend + Data | Recheck the current local/deployed frontend after the anomaly control lands; do not treat captured-response tests as browser QA. |

No unsupported location silently received Phoenix values in the tested live requests. Optional unavailable features are recorded as pending; they are not presented as completed checks.

## Reproduction and evidence

Run the repository's frontend/API checks:

```sh
uv run --locked pytest tests/frontend tests/api -q
```

For a new deployment, capture /regions, then /series?region=<id> and /trend?region=<id> for each supported region. Compare source/measurement/units/period/region fields, every monthly date/value and all null positions against the selected input snapshot. Confirm unsupported requests return 404 and malformed input returns 422. Repeat frontend region switches against those same responses and check the chart traces and text together.

Related arithmetic check: [monthly_trend_verification.md](monthly_trend_verification.md). Machine-readable work-8 results: [work8_data_handoff_check.json](evidence/work8_data_handoff_check.json).

Live API replies do not expose verified deployment-commit provenance. Agreement with a checked source/data snapshot is a numerical/content comparison, not proof of the binary running on Render. The API's four-decimal input rounding and statistical assumptions remain described in the earlier trend verification report.
