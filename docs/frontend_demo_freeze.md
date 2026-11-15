# FE-12 demo freeze candidate

## Frozen core

The release candidate is `78fae30c4fef0e0d504762ecbc13ad7b9469b5a0` on `main`,
including merged FE-10, FE-11, the final data freeze and the AI team's A10 update.
The FE-12 PR records evidence and release handoff; it does not add product features.

Freeze scope: five API-supplied regions, historical monthly nighttime surface
observations for 2003-01 through 2024-12, direction/slope/significance, supplied
explanation, and source/method/period. Keep the region selector, Refresh data,
chart tools, provenance expander and failure recovery actions. No unfinished
map, anomaly, comparison, forecast, chat or demo-story controls are exposed.
Do not introduce optional views during this freeze; their presence on the backend
alone is not frontend acceptance.

G4 in the supplied plan is the T+18 feature freeze. The sprint start time was
never recorded, so no claim is made that a wall-clock T+18 deadline was met.
From this handoff, treat the core scope above as frozen. Only user-authorized,
agreed bug fixes should change it; rerun affected checks and update evidence after
any release change. Teammate review remains the approval gate.

## G4 review

| Item | Evidence / disposition |
| --- | --- |
| Core interaction and failure recovery | Full offline suite: 590 passed. Existing frontend tests cover region switching, cache/refresh, errors, explicit sample recovery, missing data and literal explanations. |
| Verified real observations | `evidence/frontend/fe12_snapshot_check.json`: all five regions pass CSV/manifest, saved/API and AppTest agreement. All eight approved missing observations remain gaps. |
| Explanation/statistic consistency | `evidence/frontend/fe12_story_review.json`: all five pass the AI owner's deterministic guards, seasonal method and real-data requirements; no model was called. |
| Scientific display | Per-month °C, raw p-value significance threshold, p < 0.001, supplied seasonal method, sample labels and text explanations retained. |
| Readability | Merged FE-11 cards/axes/accessible description; native Chrome/Safari checks still outstanding (see known limits). |
| Unfinished controls | Entry point reviewed: no optional-feature placeholders or disabled/unwired product controls. No removal was necessary. |
| Feature freeze | Core scope documented above; no feature code or dependency changes in FE-12. |

No critical core-path UI failure was found in these checks. This is a tested
candidate, not a claim that every browser, assistive technology or network
condition is supported. Native-browser review remains open.

## Known limits and handoff

- Native Chrome/Safari and full screen-reader verification remain outstanding;
  FE-11's native computer-control permission blocker was not resolved. In-app
  responsive checks do not substitute for those checks.
- Render free services can sleep. Open the dashboard before presenting; allow
  the loading/retry path to work. A live backend connection is not live NASA
  measurement retrieval. The frontend caches successful results for 60 seconds.
- `API_URL=` is a clearly labeled synthetic preview, not the real-data offline
  backup. Two-laptop no-Wi-Fi rehearsal and recording remain FE-14 work.
- Dataset is monthly nighttime MODIS land surface temperature for study-area
  boxes, not daily air temperature or city-boundary measurements. Historical
  significance establishes neither a cause nor a future forecast.
- The API can be redeployed independently. Evidence is timestamped agreement,
  not a guarantee the API will keep serving the same bytes. Before presenting,
  rerun both live commands below if the backend/data/AI delivery changes.
- Auto-deploy is off. Future approved frontend releases require a deliberate
  manual deployment, followed by public health and browser checks.
- Render uses default TCP readiness. `/_stcore/health` is available for direct
  HTTP checks; the reference Blueprint's HTTP probe is not linked to the service.

## Recheck this candidate

```sh
git checkout 78fae30c4fef0e0d504762ecbc13ad7b9469b5a0
uv sync --locked
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked python scripts/verify_frontend_snapshot.py --api-url https://estd-api.onrender.com --out /tmp/fe12-snapshot.json
uv run --locked python scripts/review_frontend_story.py --api-url https://estd-api.onrender.com --out /tmp/fe12-story.json
```

Run these in a clean checkout; preserve any uncommitted work before changing refs.
Rehearse the short walkthrough in `frontend_deployment.md`: main region, northwest
and its missing month, supplied explanation, then source/method and limits.


## Public release and screenshots

The existing free Render frontend was manually deployed from the already merged
candidate commit above; no PR was merged by the agent. Deploy
`dep-dbshq13bc2fs73bjsjb0` became `live` at 2026-11-15T02:47:51Z (November 14,
Pacific). The public health endpoint returned `ok` afterward. No error-level
runtime logs were returned in the checked post-live window. Automatic deploys
remain off. The backend service was not changed.

Public browser checks confirmed Live API and real main/northwest evidence,
compact slope cards, p < 0.001, all five selector entries, keyboard region
selection, supplied explanation and source/seasonal method. Captures below are
viewport sections of the deployed page, not altered design mockups.

| Capture | Context |
| --- | --- |
| [Desktop overview](evidence/frontend/fe12_desktop.jpg) | Main study area and three aligned cards, 1440 × 1000 |
| [Chart and provenance](evidence/frontend/fe12_provenance.jpg) | Main observations, Automatic summary, expanded source and method |
| [Phone cards](evidence/frontend/fe12_phone_cards.jpg) | Northwest, stacked cards, 375 × 812 |
| [Phone chart](evidence/frontend/fe12_phone_chart.jpg) | Northwest observations, labels, gap guidance and explanation |

`evidence/frontend/fe12_release.json` records release identity, bounded verification,
screenshot descriptions, artifact hashes and hashes of the app sources/lockfile.
The freeze is ready for teammate review; native-browser acceptance is still pending.

VERDICT: PASS for the frozen core checks and public release evidence;
Chrome/Safari acceptance remains outstanding.
