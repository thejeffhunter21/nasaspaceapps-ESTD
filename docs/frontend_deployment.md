# FE-10 frontend deployment and demo

Deployment status: **prepared; not deployed**. Render is available but was not
installed/connected in this chat when this handoff was prepared. No public frontend
URL or hosting account changes are claimed. The existing public API is
https://estd-api.onrender.com; it is not the dashboard.

## Separate Render frontend service

Use the custom Blueprint path `deploy/frontend.render.yaml` in the Jeff repository.
The service uses Render's native Python runtime, not the root backend Dockerfile.
The Blueprint selects the free plan and `main`, with automatic deployment disabled
so releases remain deliberate. It leaves the existing backend service alone.
Review and merge this PR before selecting its Blueprint file from `main`.

The configuration pins Python 3.12.15 and uv 0.11.32, installs the locked frontend
and runtime dependencies without data/dev groups, and sets the backend URL:

```sh
uv sync --locked --no-default-groups --group frontend
```

Start command (Render provides `PORT`):

```sh
uv run --no-sync streamlit run app/streamlit_app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true --browser.gatherUsageStats false
```

Environment: `API_URL=https://estd-api.onrender.com`. No Gemini key is needed by
the frontend. Health path: `/_stcore/health`. Keep Streamlit's default CORS and XSRF
settings. The Python service calls the API, rather than browser JavaScript.

The manifest was validated against the [official Render Blueprint schema](https://render.com/schema/render.yaml.json).
Configuration fields and version pins follow the [Blueprint reference](https://render.com/docs/blueprint-spec)
and [Python runtime documentation](https://render.com/docs/python-version).

After account connection and deployment, record the actual service URL and release
commit here. Check its health endpoint, then open the public page and exercise the
five-region selector, refresh, chart, explanation and metadata. A local health
check does not substitute for that public verification. Both services may need time
to wake up; keep the page's loading and retry guidance visible during a demo.

## Short real-data walkthrough

1. Select **Phoenix study area**. Confirm Live API, 2003-01 to 2024-12, and no
   Sample data warning. These are monthly nighttime land surface temperatures.
2. Read direction, slope in °C/month, and `p < 0.001`. Significance uses the raw
   p-value; the slope describes the stated historical period.
3. Inspect the observations, then switch to **Phoenix study area northwest**.
   Its missing May 2024 observation stays a gap. Cards and text switch together.
4. Read the supplied explanation and its source label. Expand source, method and
   definitions to show MOD11C3.061, LST_Night_CMG, the snapshot version, and the
   seasonal Mann-Kendall / seasonal Sen method.
5. State the limits: a study-area box is not a city boundary; land surface
   temperature is not air temperature; this historical trend does not establish
   a cause or forecast future temperatures. Switch back to the main area.

## Reproduce the explanation review

```sh
uv run --locked python scripts/review_frontend_story.py --out /tmp/fe10-local.json
uv run --locked python scripts/review_frontend_story.py --api-url https://estd-api.onrender.com --out /tmp/fe10-live.json
```

The read-only command validates all five result contracts, applies the AI owner's
existing deterministic text/statistic guardrails, and requires the documented
seasonal method, monthly Celsius units, real-data markers and fewer than 120 words.
It neither calls a model nor rewrites explanations. A passing report is a bounded
consistency check, not scientific or teammate approval of every sentence.
`docs/evidence/frontend/fe10_story_review.json` records the live review with the
checked checkout, script hash, supplied text, method and statistics. FE-09 retains
independent snapshot and chart-to-API verification.
