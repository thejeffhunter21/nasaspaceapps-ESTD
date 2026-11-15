# FE-10 frontend deployment and demo

Deployment status: **live** as of November 14, 2026 (Pacific).

- Dashboard: https://estd-frontend.onrender.com
- Render service: `srv-dbsfr5rl550s738bm9s0` in the confirmed **earth system trend** workspace.
- Current deployment: `dep-dbshq13bc2fs73bjsjb0`, status `live`, finished 2026-11-15T02:47:51Z.
- Release commit: `78fae30c4fef0e0d504762ecbc13ad7b9469b5a0` from `main`, including
  FE-11, the final data freeze and the AI team's A10 update.
- FE-12 freeze evidence and known limits: [demo freeze handoff](frontend_demo_freeze.md).
- Backend: https://estd-api.onrender.com (separate service).

Created directly through the connected Render tool as one free Python web service.
Automatic deploys are off; releasing later merged work requires a manual deploy.
No pull request was merged as part of deployment.

## Separate Render frontend service

The custom Blueprint path `deploy/frontend.render.yaml` in the Jeff repository
is a reproducible configuration reference; it is not linked to the live service.
The service uses Render's native Python runtime, not the root backend Dockerfile.
The Blueprint selects the free plan and `main`, with automatic deployment disabled
so releases remain deliberate. It leaves the existing backend service alone.
Do not apply it as a second service. Any future Blueprint adoption should explicitly
reconcile ownership with the existing service to avoid duplicates.

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

Public verification: Render reported `live`; `/_stcore/health` returned `ok`.
The public browser displayed Live API, the main area's real 2003-01 to 2024-12
chart/cards, `p < 0.001`, Automatic summary, and supplied source/seasonal method.
All five selector options were present. Switching to northwest updated the chart,
statistics and explanation together, including the one missing-month statement;
Refresh data completed successfully. No Sample data warning appeared.

The direct-creation tool does not expose `healthCheckPath`, so the live service
uses Render's default TCP readiness checks. The Blueprint proposes HTTP readiness
at `/_stcore/health`; that endpoint was verified publicly but is not configured as
the service's platform probe. Both services may need time to wake up; keep the
page's loading and retry guidance visible during a demo.

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
