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
| FE-04 | Connect the live mock API | To do |
| FE-05 | Switch regions safely | To do |
| FE-06 | Explain what people see | To do |
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
- API URL, frontend host, deployment command and reviewer remain unconfirmed.

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
