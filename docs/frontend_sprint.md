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
| FE-07 | Design every state | To do |
| FE-08 | Test the whole interaction | To do |
| FE-09 | Verify the real snapshot | To do |
| FE-10 | Complete the real-data story | To do |
| FE-11 | Make it readable everywhere | To do |
| FE-12 | Freeze a dependable demo | To do |
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
