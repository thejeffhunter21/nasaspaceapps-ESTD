# Frontend sprint board

Frontend work follows the supplied **ESTD One Day Frontend Sprint Plan** (November 14, 2026).
Each ticket gets one focused PR. Start the next ticket only after the user authorizes it.
Statuses: To do, Doing, Review, Done. Review means changes are available for teammate review;
it does not imply teammate approval or that outstanding coordination is complete.

| Ticket | Scope | Status |
| --- | --- | --- |
| FE-01 | Start the app and board | Review |
| FE-02 | Lock the screen and data shape | Review |
| FE-03 | Show the evidence | Review |
| FE-04 | Connect the live mock API | Review |
| FE-05 | Switch regions safely | Review |
| FE-06 | Explain what people see | Review |
| FE-07 | Design every state | Review |
| FE-08 | Test the whole interaction | Review |
| FE-09 | Verify the real snapshot | Review |
| FE-10 | Complete the real-data story | To do |
| FE-11 | Make it readable everywhere | Review (Chrome/Safari checks pending) |
| FE-12 | Freeze a dependable demo | Review (native-browser checks pending) |
| FE-13 | Fix and document | To do |
| FE-14 | Rehearse without Wi-Fi | To do |
| FE-15 | Deliver and keep a buffer | To do |

## FE-01: local app shell

Run from the repository root with the project's Python 3.12 environment:

```sh
uv sync --locked
uv run --locked streamlit run app/streamlit_app.py
```

Open http://localhost:8501. The page shows the project title, the Phoenix historical
surface-temperature scope, and an explicit notice that observations and results are
not loaded. Stop the server with Ctrl+C.

Streamlit is already in the shared `frontend` dependency group, installed by default;
no dependency or lockfile change is needed. The shell starts without a backend,
processed data, `.env`, or API keys. It does not read results or call an API.

### Review and verification

- Headless smoke check: run `AppTest.from_file("app/streamlit_app.py").run()` using
  `streamlit.testing.v1.AppTest`; confirm the title renders without exceptions.
- Local server check: start the app and confirm `/_stcore/health` returns `ok`.
- Regression and lint: `uv run --locked pytest -q` and `uv run --locked ruff check .`.
- Short demo: start the command above, open the local URL, and show the title and
  unloaded-data notice. Data mapping and sample fixtures begin in FE-02.

Observed on November 14, 2026: the AppTest smoke check rendered and reran without
exceptions; the local server health check returned `ok`; all 67 existing tests
passed; repository lint and diff whitespace checks passed. Browser visual review
and teammate review are still pending.

### Coordination still pending

- Frontend implementation: Coby; teammate reviewer not yet assigned.
- Hosting owner: awaiting confirmation with Syed (Avid-arch), the repository's
  infrastructure owner. No teammate confirmation or deployment has occurred.
- Hosting URL and deployment command: awaiting the hosting handoff.
- Keep FE-01 in Review until the PR is reviewed and hosting ownership is confirmed.

## FE-02: screen and data shape

The page now reads `app/fixtures/results.mock.json`, a frontend-owned copy of the
agreed root mock. It keeps all 36 positions from 2003-01 to 2005-12, including the
null at 2004-03. Keeping the fixture under `app/` lets the preview run without
shipping test files. It is synthetic data, not the Phoenix 2003-2024 snapshot.
The page labels it **Sample data** and derives its region and period from the file.

### Single-page sketch for teammate review

Read from top to bottom on desktop or phone:

```text
Earth System Trend Detective
Data-mode label (Sample data for the current preview)
Question: how has the selected region's surface temperature changed?
Region label (fixed when only one region is available)
Variable, units, period
Trend summary: direction, per-month slope, significance
Monthly observations chart: time/value, null months remain gaps
Supplied plain-language explanation
Source and method (collapsible)
```

FE-02 renders the title, sample label, region, variable, units and period only.
FE-03 adds the evidence chart, cards and supplied explanation. Region selection,
API requests and explanatory metadata UI remain in their assigned later tickets.
The sketch is proposed for PR review; no teammate design sign-off is claimed.

### Adapter boundary

`app/view_model.py::build_view_model(payload)` accepts decoded results JSON and
validates it with the existing shared `Results` model. It returns one immutable
`ResultsView`; page components should consume that view instead of remapping JSON.

| Contract input | Frontend value |
| --- | --- |
| `region_id`, `region` | Request ID, display label |
| `variable`, `units`, `period` | Supplied variable/units and start-to-end label |
| `series[].time`, `series[].value` | Ordered time/value tuples; null stays `None` |
| `trend.slope`, `slope_unit`, `p`, `tau`, `trend` | Unrounded statistics, supplied units and direction |
| `trend.p` | Significant only when the unrounded value is below 0.05 |
| `explanation`, `explanation_source` | Supplied text and source, unchanged |
| `source`, `method` | Supplied provenance and exact method, unchanged |
| Source contains `mock`, or region is `Example Region` | Sample-data flag (case-insensitive) |

No trend calculation, annualization, date filtering or gap filling occurs here.
Absence of sample markers does not prove real-data provenance. Contract errors
raise validation errors; page-level failure and recovery states belong to FE-07.

### Contract decisions and pending handoffs

- Current `docs/contract.md` v1.0 and `contract.py` agree on API series key `time`.
  The frontend consumes results JSON, not Data CSVs, so any CSV `date` conversion
  belongs at the pipeline boundary.
- Current contract requires non-null trend statistics and three direction labels.
  Insufficient-data/null-statistic payloads need Jeff's contract agreement before
  frontend integration; the adapter does not invent zeros or a fourth label.
- Current contract supplies source/method/period, but no snapshot ID or coverage
  fields. Their delivery remains a backend/data handoff for real-data verification.
- API URL was supplied during FE-04 (see below); frontend host, deployment command
  and reviewer remain unconfirmed.

### Verification

Run `uv run --locked pytest tests/frontend -m unit -q`. The checks cover exact
fixture parity, the missing month, zero preservation, mapping and unchanged input,
unrounded significance at the 0.05 boundary, sample markers, malformed statistics,
and page render/rerun from outside the repository working directory.

## FE-03: show the evidence

The sample page now shows slope in its supplied per-month unit, p-value and
direction cards, followed by the monthly observation chart and supplied explanation.
Significance uses the adapter's unrounded comparison with 0.05 and is stated in
words. The explanation uses `st.text`, preserving literal text without Markdown
or HTML interpretation.

`app/charts.py::monthly_chart(view)` creates one observation trace with month hover
dates and the supplied variable/units on the axes. Plotly is already in the shared
frontend dependencies. Every month is retained; `connectgaps=False` leaves a visible
break at 2004-03. Zero and negative observations remain values. No fitted line is
derived from the slope. Chart zoom does not recompute the full-period statistics.

Run `uv run --locked pytest tests/frontend -m unit -q` to verify chart serialization,
null and zero handling, labels, cards, significance at p = 0.05, and literal
explanation rendering. Local browser inspection confirmed the missing-month gap,
labeled axes and supplied explanation. Teammate review remains pending.

Demo: run the existing Streamlit command, identify the sample-data warning and
Example Region period, read the cards, then inspect the break between February
and April 2004 and the explanation below the chart. Live API access starts in
FE-04; no API requests or AI calls are added here.

## FE-04: live API connection

The frontend defaults to `https://estd-api.onrender.com`, supplied by backend.
Run the existing command from the repository root to connect:

```sh
uv run --locked streamlit run app/streamlit_app.py
```

Override `API_URL` in the environment or the repository-root `.env` to select
another backend. To run a local backend, for example:

```sh
API_URL=http://localhost:8000 uv run --locked streamlit run app/streamlit_app.py
```

Set `API_URL` to an empty string for the local sample preview without networking:

```sh
API_URL= uv run --locked streamlit run app/streamlit_app.py
```

`app/api_client.py` owns all frontend HTTP access. On a cache miss it calls
`/health` first, then `/results` for the main study area. Each endpoint has a
5-second connect timeout and a 45-second read timeout, with at most one retry
for a timeout, connection error, HTTP 429 or HTTP 5xx. These are per-request
timeouts, not an overall page deadline. Other HTTP errors, invalid JSON and
invalid contract payloads fail without retrying. Error messages omit raw server
details. A spinner is visible during loading.

Only successfully validated results are cached, for 60 seconds and at most 16
API URLs. Host caches remain separate. **Refresh data** clears the current URL's
entry and reloads it immediately, useful when backend changes from mock to real
results. No automatic background polling is performed.

If connection fails, the page shows a useful error with **Retry API** and
**Use sample data**. Sample data is an explicit choice, not a silent substitute.
Choosing it does not trigger another failed API call; it uses the frontend fixture
and keeps the Sample data label visible. **Retry API** then returns to the API.
Successful API responses still receive the Sample data label when their source or
region identifies them as mock. “Connected to API” describes the connection; it
does not independently verify the dataset's provenance.

### Verification and live observation

Offline frontend checks mock HTTP and cover request order/timeouts, single retries,
success-only caching, URL isolation, manual refresh, invalid JSON/contract payloads,
and explicit sample/retry interaction. They do not require the deployed API.

On November 14, 2026, the deployed `/health` returned `status: ok`. An initial
`/results` read contained the Example Region mock with 36 positions and one null.
During the live check the backend switched to Phoenix study area; both AppTest
and browser inspection showed a successful API connection, nighttime land surface
temperature for 2003-01 to 2024-12, slope 0.007713 degC/month, p 0.0 and increasing
direction, as supplied by the API. This confirms connection/rendering; FE-09 owns
independent snapshot verification.

No backend, contract, AI, hosting or dependency changes are part of FE-04. Region
switching remains FE-05. The deployed frontend URL still needs a hosting handoff;
these checks run the frontend locally against the deployed backend. Streamlit's
Python process makes these requests, so browser CORS is not involved in this path.

## FE-05: switch regions safely

The page now wakes `/health`, reads `/regions`, and requests `/series` and `/trend`
with the selected `region_id` in the `region` query parameter. The dropdown displays
the API's labels and sends its IDs. Only returned regions are offered. With one
region (including the local sample), the page shows a fixed region heading instead
of a selector. Changing API host resets the previous host's region selection.

The region list is cached by normalized API URL for 60 seconds. A complete selected
result is cached by API URL and region ID for 60 seconds, up to 64 entries. It is
assembled only after both endpoints succeed, agree on ID/label/variable/units/period,
match the requested region ID, and validate against the shared results contract.
Empty/invalid directories and duplicate IDs fail visibly. Failed or mismatched
responses are not cached. The older whole-main-area `fetch_results` helper remains
available, but region rendering uses the paired endpoints so one flow handles the
main area and all subregions.

The previous evidence block is cleared before loading. The new title, period,
chart, cards, explanation, source and method are then rendered from the same
complete result. A failed switch shows the recovery actions without leaving the
previous region's chart or statistics under the new selection. Source and method
are displayed below the chart; explanatory definitions remain FE-06.

**Refresh data** clears the current directory and selected region's result without
flushing unrelated hosts/regions. Returning to a recently loaded region uses its
own cached pair. Existing timeout/retry and explicit sample fallback behavior is
retained.

### Verification and live observation

Run `uv run --locked pytest tests/frontend -m unit -q`. New checks cover two-region
switching across chart values/dates/units, cards, explanation, period, source and
method; switching back from cache; failed switches; a single fixed region; host
changes; query IDs; cache isolation/refresh; wrong requested IDs; paired metadata
mismatches; and invalid or duplicate directory entries.

On November 14, 2026, the live frontend listed Phoenix study area and all four
subregions. Switching to Phoenix northwest rendered 264 monthly positions and the
2024-05 null gap. The API supplied slope 0.007551 degC/month, p 0.0, increasing,
the phoenix-qc-v1.0 source and the seasonal Mann-Kendall/Sen method. This verifies
selection and rendering; independent dataset verification remains FE-09.

Demo: run the existing Streamlit command, switch between the main study area and
Phoenix northwest, inspect the updated evidence and northwest gap, then switch
back. Teammate review remains pending. No backend, AI, contract, dependency or
hosting changes are included; FE-06 has not started.

## FE-06: explain what people see

The explanation remains the supplied plain text. Its source now controls a visible
label: `fallback` displays exactly **Automatic summary (AI unavailable)**; `ai`
displays **AI-assisted explanation**. The frontend does not generate or rewrite the
text.

Connection and dataset labels are independent. A successful response shows
**Connection: Live API**, including when the API is serving mock data. A local
fixture shows **Connection: Offline preview**. The existing **Sample data** warning
continues to identify synthetic observations in either connection mode. Offline
preview is a local sample file, not an approved real-data snapshot; that packaging
remains FE-14.

The collapsible **Source, method and definitions** panel follows the explanation.
It displays the selected response's source, exact method and period, without
hardcoding a NASA product or statistical method. It defines slope using the
supplied unit and full stated period, and explains the p-value and strict 0.05
significance threshold. The text distinguishes insufficient evidence from proof
of no change and identifies slope as a historical estimate rather than a forecast.

Verification: `uv run --locked pytest tests/frontend -m unit -q` covers offline
sample/fallback labels, API mock data, non-mock API responses with an AI explanation,
supplied metadata in the panel, and connection-label changes after sample recovery
and retry. Existing chart and region consistency checks remain in place.

Demo: load the live page, read its connection and explanation labels, and expand
the details panel. Run with `API_URL=` for the distinct Offline preview plus Sample
data labels. Teammate review remains pending; FE-07 has not started.

## FE-07: reliable loading and failure states

The existing connection and selected-region spinners remain around network work.
The evidence block is cleared before loading, so loading or failure cannot leave
the previous region's chart and statistics displayed as the current result.

| State | Visible message and recovery |
| --- | --- |
| Empty series or every value null | No observations available; retry, choose another region or explicitly use sample data |
| Empty region directory | No regions available; retry, refresh regions or use sample data |
| HTTP 404 | No data for this region; refresh the region list or choose another region |
| HTTP 422 | Region selection needs updating; refresh available regions and select again |
| HTTP 5xx | The data service is unavailable; retry and report persistent failures to backend |
| Timeout after the one retry | The data service is taking too long; server wake-up guidance and retry/sample actions |
| Connection failure | Cannot reach the data service; check connectivity and retry/use local sample |
| HTTP 429 after the one retry | The data service is busy; wait briefly and retry |
| Invalid JSON, contract fields or paired metadata | The data response could not be read; retry or explicitly choose sample data |
| Invalid API address | The data connection needs setup; ask the demo owner to check the address |
| Missing, unreadable, invalid JSON/encoding or invalid-contract sample file | The sample preview is unavailable; Retry preview and Retry API when a backend is configured |

`ApiError.kind` carries the state without passing raw HTTP response bodies or
file exception details into the page. **Refresh regions** clears the directory
and current region cache; a region removed by a deployment can be replaced from
the refreshed list. **Retry preview** rereads a restored sample file. Sample
fallback remains explicit and labeled; a broken sample does not prevent reconnecting
to the API.

An empty/all-null series never becomes zero. Individual missing months still stay
as gaps, and valid zero/negative observations remain valid observations. The current
shared contract still requires non-null statistics: unsupported null-statistic
responses show a malformed-response state instead of fabricated zero cards.
No new insufficient-data schema is introduced by the frontend.

Verification: `uv run --locked pytest tests/frontend -m unit -q`. New mocked states
cover empty/all-null series, no regions, 404/422/500, timeout, invalid JSON, null
statistics, and sample-file failures. Interaction checks exercise timeout retry,
region refresh after a stale selection, preview retry after restoring the file,
and API recovery even when both the initial request and local sample fail. A
loading-context check verifies HTTP operations run inside the native spinners.

No backend, AI, contract, dependency or hosting changes are included. Teammate
review remains pending; FE-08 has not started.

## FE-08: test the whole interaction

The frontend suite now checks formatting boundaries and drives Streamlit through
the actual FastAPI routes in memory. The in-process backend uses temporary files
derived from the frontend's synthetic fixture, not NASA observations. HTTP is
bridged to FastAPI's TestClient; normal tests do not contact Render, NASA or Gemini.
The existing frontend fixture blocks unmocked network requests.

The backend handoff's display requirements are now applied consistently:

- API `degC` and `degC/month` render as `°C` and `°C/month` in the page, cards,
  axes, hover text and accessible description. Raw API units stay unchanged.
- A p-value strictly below 0.001 displays `p < 0.001`; 0.001 and larger values
  retain their numeric display. Significance still uses the unrounded raw p-value
  against 0.05. Boundary cases and tiny/zero p-values have dedicated unit checks.
- The newer backend handoff supersedes the earlier long fallback caption:
  `explanation_source=fallback` now displays **Automatic summary**. Explanation text
  remains literal and unchanged. AI and sample/connection labels remain distinct.

### Repeatable offline checks

```sh
uv run --locked pytest tests/frontend -m unit -q
uv run --locked pytest tests/frontend -m integration -q
uv run --locked pytest -q
uv run --locked ruff check .
```

Observed on November 14, 2026: 91 frontend unit tests and two frontend integration
tests passed (93 total); the full repository suite passed 393 tests; lint and
whitespace checks passed. Existing CI already runs the complete suite, including
these checks, without a workflow change.

The integration journey verifies the formatted main result, updated region labels,
region switching, exact chart-to-JSON agreement, preserved null gap, supplied
explanation, and return-to-cache. A second journey removes a previously listed
region from the temporary backend, checks that the resulting 404 clears old
evidence, then refreshes the region list and recovers to the main area.

### G2 live comparison evidence

`docs/evidence/frontend/fe08_live_check.json` records the point-in-time comparison
against the deployed `/series` and `/trend` responses for `phoenix_study_area` and
`phoenix_northwest`. It includes selected IDs/labels, period, raw statistics,
displayed cards, units, null months, source/method, explanation source and a hash
of the returned series. All plotted times/values, supplied explanation and metadata
were asserted against separate live JSON reads through the frontend AppTest run.

Both regions had 264 positions; northwest retained the 2024-05 null. The API now
returns unrounded p-values (main approximately 7.02e-11; northwest approximately
3.28e-10), both displayed as `p < 0.001`. The new region labels and Automatic summary
caption were observed. The local preview server was restarted with the new display
properties loaded.

This is API/frontend agreement, not independent dataset QC or a hosting deployment.
FE-09 retains real-snapshot verification. No backend, AI, shared contract,
dependency or hosting changes are included. Teammate review remains pending;
FE-09 has not started.

## FE-09: verify the real snapshot

The read-only command `scripts/verify_frontend_snapshot.py` checks the delivered
`phoenix-qc-v1.0` handoff before comparing saved results, API responses and the page.
The handoff uses `data/processed/manifest.json` and `data_quality_manifest.json`;
there is no `docs/data_manifest.json` in this delivery.

The command verifies all five CSV SHA-256 hashes, agreement between the two
manifests, and the coverage/data-card/quality-report hashes. It checks the full
2003-01 through 2024-12 calendar for each region and all 1,320 unique coverage
records. Coverage below the documented 80% weighted-area threshold must correspond
exactly to a missing observation. Data ID `phoenix` explicitly maps to the API's
`phoenix_study_area`; subregion IDs are unchanged.

| API region ID | Calendar positions | Valid observations | Missing months |
| --- | ---: | ---: | --- |
| phoenix_study_area | 264 | 264 | None |
| phoenix_northwest | 264 | 263 | 2024-05 |
| phoenix_northeast | 264 | 262 | 2007-07, 2023-07 |
| phoenix_southwest | 264 | 262 | 2007-07, 2010-07 |
| phoenix_southeast | 264 | 261 | 2012-07, 2017-07, 2024-06 |

### Precision and provenance boundary

The CSVs retain full precision; the existing pipeline rounds temperature inputs
to four decimals before trend calculation and JSON output. This is documented in
`docs/monthly_trend_verification.md`, not a new frontend operation. The verifier
independently requires every result value to equal that rounded CSV value within
1e-12, retaining nulls. Observed maximum raw-CSV/API differences were below
0.00005 °C in every region. No CSV value, trend, explanation or API file is changed.

Real-result checks reject mock/example markers and require the supplied source to
identify the qc-v1 version, MOD11C3.061, LST_Night_CMG and dataset DOI. Variable and
units must identify nighttime surface temperature in degC, with degC/month slopes.
Saved and live statistics and method must agree. The page must plot exactly the
API times/values with gaps, show matching cards and supplied explanation/provenance,
and carry no Sample data warning.

### Reproduce

Local files and saved results only (no network):

```sh
uv run --locked python scripts/verify_frontend_snapshot.py --out /tmp/fe09-local.json
```

All five live API regions plus Streamlit AppTest rendering:

```sh
uv run --locked python scripts/verify_frontend_snapshot.py --api-url https://estd-api.onrender.com --out /tmp/fe09-live.json
```

The command writes its report and exits nonzero on a mismatch. Ordinary frontend
tests remain offline. Ten verifier tests cover the approved snapshot and rejection
of changed file bytes, changed calendar/gap/value, mock source, units and period.

Observed on November 14, 2026: local and live verification passed for all five
regions; 103 frontend tests, 403 total repository tests, lint and whitespace checks
passed. `docs/evidence/frontend/fe09_snapshot_check.json` records the timestamp,
checked checkout, verifier hash, source checkout reference, snapshot ID, manifests,
CSV/sidecar hashes, per-region sample values, rounding differences and frontend
agreement checks. All eight approved missing observations remained gaps.

This verifies the approved processed handoff through the frontend. It does not
rerun NASA retrieval or pixel-level QC, approve causal interpretation, or prove a
deployment commit (the API does not expose code provenance). No dashboard behavior,
backend, AI, shared contract, dependencies or hosting is changed. Teammate review
remains pending; FE-10 has not started.


## FE-11: make it readable everywhere

Trend cards use three equal-width native Streamlit columns that stack on phones.
The slope card displays six significant figures (scientific notation for tiny
values), preserving its raw value and sign. For example, the main real result
now displays `0.0077125` rather than `0.0077125000000000015`. No statistics or
significance decisions are recomputed.

The chart keeps its variable/units and month axes, adds automatic label margins,
limits date tick crowding and uses a 14 px chart font. Its accessible description
now includes direction, slope, significance in words and missing-month count.
The existing plain-text explanation, visible significance caption, source/method
and sample warnings remain intact. Native focus styling and theme are retained.

Observed at 375 px and 1440 px: no page overflow; stacked phone cards and equal
desktop cards; keyboard region switching, refresh-button focus and Enter access
to provenance worked. Contrast was spot-checked in the observed dark theme.
All 108 frontend tests and 536 repository tests passed, lint/whitespace checks
passed, and the live snapshot verifier passed all five regions after accounting
for the new display precision. See `docs/evidence/frontend/fe11_readability.md`.

Native Chrome/Safari testing remains outstanding because native computer control
was unavailable. Keep this ticket in Review until those browser checks and teammate
review are complete. The branch starts from the latest fetched main including the
final data freeze. It has not been merged or deployed; FE-12 has not started.
## FE-10: complete the real-data story

The read-only `scripts/review_frontend_story.py` reviews all five saved or live
region explanations against the AI owner's existing deterministic guardrails and
seasonal method reference. It retains the supplied text, statistics and source
labels, rejects mock data, and records a reproducible evidence report. Seven new
tests cover the valid result and contradictory method, significance, causal claim,
number, product wording and sample provenance.

The live review passed for all five regions. The demo walkthrough and a separate
native Python Render Blueprint are documented in `docs/frontend_deployment.md`.
The Blueprint passes Render's official schema, and its frontend-only installation,
start command and health endpoint have been exercised locally.

Verification on November 14, 2026: all 502 repository tests passed, including the
seven new review tests; repository lint and whitespace checks passed.

**Deployment verified:** https://estd-frontend.onrender.com is live on the free
Render Python service in the user-confirmed earth system trend workspace. It runs
`main` commit `b762e921b857fb0df8ece44316c1b15b67c3f626`, including the final data
freeze. Public health, real-data rendering, all five region options, northwest
switching, refresh, explanation and source/method were checked. Auto-deploy is off;
future approved releases need a manual deploy. Direct creation uses default TCP
readiness; see the deployment handoff for its difference from the reference Blueprint.

This ticket stays in Review for teammates. The PR changes review tooling, evidence
and deployment documentation/configuration; it does not change dashboard behavior,
backend or AI logic. FE-11 has not started.


## FE-12: freeze a dependable demo

The frozen core candidate is main commit `78fae30c4fef0e0d504762ecbc13ad7b9469b5a0`,
including merged FE-10/11 and teammate data/AI updates. The existing public frontend
was manually deployed to this commit and verified live. This PR adds freeze
handoff documentation, desktop/phone screenshots and fresh evidence; no product
features, data, backend/AI logic or dependencies are changed.

Fresh verification passed: 590 repository tests, Ruff, all-five-region live
snapshot/API/page agreement and all-five explanation consistency checks. The
public page displays the compact cards, real observations, supplied explanation
and provenance. No unfinished optional controls were exposed; none needed removal.

`docs/frontend_demo_freeze.md` records the G4 checklist, immutable release identity,
artifact/source hashes, scope freeze, known limits, reproduction commands and
screenshots. No critical core-path failure was found in these checks. Native
Chrome/Safari acceptance and teammate sign-off remain pending. The sprint start
was never recorded, so a T+18 wall-clock deadline is not claimed.

Keep core feature work frozen; only agreed, user-authorized bug fixes should alter
this candidate and require fresh affected checks. FE-13 has not started.
