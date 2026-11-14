# Frontend sprint board

Frontend work follows the supplied **ESTD One Day Frontend Sprint Plan** (November 14, 2026).
Each ticket gets one focused PR. Start the next ticket only after the user authorizes it.
Statuses: To do, Doing, Review, Done. Review means changes are available for teammate review;
it does not imply teammate approval or that outstanding coordination is complete.

| Ticket | Scope | Status |
| --- | --- | --- |
| FE-01 | Start the app and board | Review |
| FE-02 | Lock the screen and data shape | To do |
| FE-03 | Show the evidence | To do |
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
