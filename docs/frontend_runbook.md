# Frontend setup and release handoff (FE-13)

For Avid-arch and reviewers: these are the dashboard's setup and recovery steps.
The public page is https://estd-frontend.onrender.com. The separate API is
https://estd-api.onrender.com; interactive backend docs are at `/docs`.

## Start from a clean checkout

Prerequisites: Git, Python 3.12 and uv. Run commands from the repository root.
No NASA credentials or Gemini key are needed to display existing API results.

```sh
git clone https://github.com/thejeffhunter21/nasaspaceapps-ESTD.git
cd nasaspaceapps-ESTD
uv sync --locked --no-default-groups --group frontend
uv run --no-sync streamlit run app/streamlit_app.py
```

Open http://localhost:8501. The frontend-only install includes the project's
runtime dependencies and the frontend group; it omits data-download/dev groups.
`--no-sync` uses that installed environment without reintroducing default groups.
For development/testing, use the full `uv sync --locked` instead.
Stop the server with Ctrl+C. If port 8501 is occupied, append `--server.port 8502`
to the Streamlit command and open that port.

## Choose the backend explicitly

| Mode | Start command | Expected page |
| --- | --- | --- |
| Live API | `API_URL=https://estd-api.onrender.com uv run --no-sync streamlit run app/streamlit_app.py` | Connection: Live API; Phoenix study area and four subregions; real 2003-2024 data |
| Local API | `API_URL=http://127.0.0.1:8000 uv run --no-sync streamlit run app/streamlit_app.py` | Connection: Live API means an HTTP API connection, even when that API runs locally |
| Synthetic preview | `API_URL= uv run --no-sync streamlit run app/streamlit_app.py` | Connection: Offline preview; Example Region; prominent Sample data warning; no API requests |

To supply the local API in a separate terminal, from the same repository:

```sh
USE_MOCK=false uv run --no-sync uvicorn earth_system_trend.api.app:app --host 127.0.0.1 --port 8000
```

This reads the committed real results. Omit `USE_MOCK=false` only if you intentionally
want the API's default mock, which the frontend must label Sample data. Starting
uvicorn alone does not change where an already-running dashboard sends requests;
set `API_URL` and restart Streamlit. Change both URL and port if 8000 is occupied.
The existing backend backup launcher and two-laptop offline rehearsal remain FE-14.

`API_URL` can also be set in the root `.env`; exported process variables take
precedence. An explicitly empty `API_URL` selects the synthetic preview. Keep
credentials out of Git and screenshots. These shell examples use macOS/Linux
syntax; on PowerShell set `$env:API_URL` before running the same uv command.

## Origin settings

`app/api_client.py` uses Python `requests` in the Streamlit server. The browser
connects to Streamlit; it does not directly fetch the backend in this implementation.
No backend CORS change is needed for these server-to-server requests. Keep
Streamlit's existing CORS/XSRF defaults. Do not set backend origins to `*` to solve
a dashboard connection failure. If a later client makes browser-side API calls,
coordinate its exact origin with backend; that is a separate integration change.

## Short acceptance/recovery check

1. Open the page, confirm Live API, no Sample data warning, and the 2003-01 to
   2024-12 period. Inspect monthly °C, slope °C/month and p < 0.001.
2. Select northwest. Title, cards, chart, supplied explanation and provenance
   must all belong to northwest; May 2024 stays a gap. Switch back and Refresh data.
3. Open Source, method and definitions. Confirm the supplied MOD11C3.061 source,
   qc-v1 version and seasonal test. Fallback explanations are labeled Automatic summary.
4. Use the keyboard for Region and the provenance expander. Check phone/desktop
   layout. Native Chrome/Safari and full screen-reader review remain outstanding.
5. For failure states, run the existing mocked suite below. Do not disrupt the
   shared API to provoke a 404/500. A failed request clears old evidence and offers
   Retry API and Use sample data. Sample fallback is explicit and visibly synthetic.

Cold starts can be slow: the client permits 45-second read timeouts and one
transient retry per endpoint; this is not a 45-second total-page guarantee.
Successful results are cached for 60 seconds. Refresh data reloads the selected
region. Persistent 404: refresh regions; 422: reselect from returned IDs; 5xx:
retry and report to backend; timeout: allow wake-up, retry or choose labeled sample.
Never interpret missing values as zero or use the sample for scientific claims.

## Verification and release

After a full `uv sync --locked`:

```sh
uv run --locked pytest tests/frontend -q
uv run --locked ruff check .
uv run --locked python scripts/verify_frontend_snapshot.py --api-url https://estd-api.onrender.com --out /tmp/frontend-snapshot.json
uv run --locked python scripts/review_frontend_story.py --api-url https://estd-api.onrender.com --out /tmp/frontend-story.json
```

The Render frontend uses Python 3.12.15, uv 0.11.32 and the frontend-only install
above. Its service, start command, environment and current release identity are
recorded in [deployment instructions](frontend_deployment.md). Auto-deploy is off;
only deploy reviewed, merged work manually. Then wait for Render's deploy status
`live`, check `/_stcore/health` returns `ok`, and repeat the public acceptance path.
Frontend `.env`/local changes are not automatically deployed. Backend releases
are independent. A documentation-only update with unchanged runtime inputs does
not require a frontend redeploy.

[Freeze checklist and limits](frontend_demo_freeze.md) ·
[desktop screenshot](evidence/frontend/fe12_desktop.jpg) ·
[chart and source screenshot](evidence/frontend/fe12_provenance.jpg) ·
[phone cards](evidence/frontend/fe12_phone_cards.jpg) ·
[phone chart](evidence/frontend/fe12_phone_chart.jpg).
These are FE-12 captures of the same frozen runtime; FE-13 does not change UI code.
The PR is the handoff for teammate review; receipt or teammate sign-off is not claimed.
