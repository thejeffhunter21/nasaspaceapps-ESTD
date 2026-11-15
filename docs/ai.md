# AI layer: trend method, checks and explanations

Rule: **code computes every number; the AI only writes words.** The trend statistics come from a
fixed statistical test. Gemini may only rephrase them, and its text is shown only if it passes
the explanation checks.

Data version described here: phoenix-qc-v1.0 (see [data_card.md](data_card.md),
[data_quality_report.md](data_quality_report.md)). Results shape: [contract.md](contract.md).

## Trend method

**Seasonal Mann-Kendall test (12-month period) with seasonal Sen's slope**, via
`pymannkendall.seasonal_test(values, period=12)`, alpha = 0.05. This exact string is written to
`method` in every results file.

How it works: the 264 monthly values are arranged as 22 years x 12 calendar months. Each
calendar month is compared only with the same month in other years (January with January, and so
on). The 12 Mann-Kendall scores are summed into one test. The slope is the median of all
same-month pairwise slopes `(x[year j] - x[year i]) / (j - i)`.

### Why seasonal, not the plain test

Nighttime surface temperature in Phoenix swings by about 24 degC over a year (study-area
calendar-month means: January 5.6 degC, July 30.0 degC). That cycle hides
the long-term change from the plain (original) Mann-Kendall test:

| Study area, 2003-01..2024-12 | Result | p |
|---|---|---|
| Plain Mann-Kendall | no trend | 0.199 |
| Seasonal Mann-Kendall | increasing | 7.0e-11 |

Results from the plain test must not be relabelled as seasonal, or the other way round.

### Raw values or anomalies

The trend is run on the raw monthly temperatures (`timeseries*.csv`). Running it on the anomaly
files (`anomaly*.csv`) gives the identical slope, p and tau: subtracting one constant per calendar
month does not change any same-month comparison. Anomalies are for display, not a second result.

## Slope units

`seasonal_test` reports the slope **per year**, because its time step is one full 12-month
cycle. The contract requires **per month**, so the AI layer divides by 12:

```
slope_per_month = seasonal_test(...).slope / 12      # slope_unit = "<units>/month", e.g. degC/month
```

Checked for all five regions: an independent seasonal Sen's slope calculation matches the
library to 1e-12, and the stored slope equals per-year / 12 (study area: 0.09255 degC/year ->
0.007713 degC/month). On a synthetic series with a known slope of 0.0100 degC/month plus a
10 degC seasonal cycle, noise and three gaps, `run_trend` returns 0.0097.

Displays that show a per-year or per-decade figure must label it and compute it as slope x 12
(or x 120) from the stored per-month value.

## Missing months

- Every region keeps all 264 calendar positions. A missing month is `None` in Python, an empty
  cell in the CSV and `null` in JSON. It is never interpolated, filled with zero, or dropped.
- Keeping the position matters: the 22 x 12 grid is built by position, so dropping a gap would
  slide every later month into the wrong calendar column. On qc-v1 that would change the
  southeast slope from 0.0089 to 0.0149 degC/month.
- Inside the test, each calendar month skips only its own missing years. The other 11 months are
  unaffected, and pairwise slopes keep the true year gap `(j - i)`.

Expected gaps in qc-v1 (all below the 80% valid-area rule): northwest 2024-05; northeast
2007-07, 2023-07; southwest 2007-07, 2010-07; southeast 2012-07, 2017-07, 2024-06.

## Significance

- Significant only if **p < 0.05**, compared on the unrounded p. p = 0.05 is not significant.
- "Not significant" means the test found insufficient evidence of a trend, not that the change
  is zero.
- A5 (`ai/trend.py`) returns p unrounded and computes it as `2 * norm.sf(|z|)`, which stays
  accurate for tiny values (the library's `1 - cdf` loses precision and can reach exactly 0).
  qc-v1 p-values: study area 7.0e-11, northwest 3.3e-10, northeast 3.8e-06, southwest 3.0e-10,
  southeast 2.8e-14.
- The pipeline uses A5 (A7), so the committed results files store this unrounded p.

## Serial dependence

The seasonal test assumes the years within each calendar month are independent, and that the 12
months can be summed as independent tests. Neither correction is applied in the reported
results. Sensitivity check on qc-v1:

| Region | Seasonal p (reported) | Hirsch-Slack corrected p | Trend after correction |
|---|---|---|---|
| Study area | 7.0e-11 | 3.2e-05 | increasing |
| Northwest | 3.3e-10 | 8.4e-05 | increasing |
| Northeast | 3.8e-06 | 5.3e-04 | increasing |
| Southwest | 3.0e-10 | 7.3e-05 | increasing |
| Southeast | 2.8e-14 | 7.7e-05 | increasing |

The Hirsch-Slack correction (`pymannkendall.correlated_seasonal_test`) allows for correlation
between calendar months. It makes p larger in every region, but all five stay significant at
p < 0.001. Year-to-year correlation within a calendar month, after removing each month's linear
trend, is slightly negative (mean lag-1 r about -0.10), so it does not inflate significance.
**Conclusion: the reported direction and significance hold with or without the correction.** The
reported p-values are from the uncorrected test and are smaller than the corrected ones.

## Eligibility

- Current rule: the pipeline writes no results file for a series with fewer than 24 valid months
  (`pipeline/timeseries.py`).
- That rule alone does not establish that the seasonal test is adequate. qc-v1 easily exceeds it:
  every calendar month has 20-22 valid years in every region.
- A5 rule (`ai/trend.py`): `run_trend` raises `TrendInputError` unless the series has at least
  24 valid months and, for the seasonal test, **at least 10 valid years in every calendar
  month** (`MIN_YEARS_PER_CALENDAR_MONTH`). With fewer, a calendar month contributes too few
  pairs to the test and slope to be meaningful. qc-v1 passes in every region (lowest: 20 years).
- Calendar months are counted from the series' first month. Pipeline series start at the period
  start (January for qc-v1), so position 1 is January.
- Non-numbers, booleans and infinite values are rejected; `None` and NaN are missing months.

## Explanations

| Unit | File | What it does |
|---|---|---|
| A1 | `ai/ai_setup.py` | Builds the Gemini client from `GEMINI_API_KEY` and `GEMINI_MODEL`. No key: AI is off and the fallback is used. A 404 (wrong model or endpoint) fails at once. |
| A2 | `ai/ai_retry.py` | Retries timeouts, dropped connections, 408, 429 and 5xx up to 3 attempts (1 s, 2 s waits; 8 s cap). A long Retry-After, a bad key (401/403) or a bad request stops at once. Errors and logs never include the provider's response body. |
| A3 | `ai/ai_checks.py` | `check_explanation(text, results)` rejects text with numbers or dates not derived from the results, wrong significance wording, a direction that contradicts the trend, causes, forecasts, advice, the wrong product (air temperature, daily) or unit (Fahrenheit), or more than 600 characters. Never raises; anything it cannot check fails. Since A8 it also rejects other places (other boxes, other cities, street level), a missing month's date not described as missing, whole numbers that do not round from a real value, and claims that the data is current. |
| A4 | `ai/explain.py`, `ai/prompts/explain_v1.txt` | `explain(results)` returns `{"text", "source"}` and never raises. Facts are formatted by code (slope per month and per year to 3 significant figures, `p < 0.001` for tiny p), sent with the versioned prompt through A2, and checked by A3. Only a reply that passes is `"ai"`; no key, setup errors, Gemini failures, empty replies and rejected replies all return the fallback, with the reason logged. |
| A5 | `ai/trend.py` | `run_trend(values, method="seasonal", alpha=0.05)`: seasonal (default) or original Mann-Kendall with Sen's slope, slope per month, unrounded p, strict p < alpha, eligibility rules above. Replaces the pipeline stub. |
| A6 | `ai/ai_cache.py` | Cache and daily cap. AI text that passed A3 is stored in `EXPLAIN_CACHE_PATH` (default `data/cache/explanations.json`, git-ignored), keyed by SHA-256 of the prompt version + exact facts, and re-checked on reuse; works without a key, so offline re-runs keep approved AI text. `AI_DAILY_CALL_CAP` (default 50, 0 = AI off) limits requests to Gemini per UTC day, retries included; a request over the cap is not sent and the fallback is used. Unreadable or unwritable cache files are logged, never raised. To refresh text, delete the file or bump the prompt version. |
| A7 | `pipeline/run.py` (import switch), `tests/conftest.py` | The pipeline uses A4-A6; committed results regenerated (unrounded p, A4 fallback text). Shared test setup strips `GEMINI_API_KEY`/`GEMINI_MODEL` and isolates the cache, because `config.py` loads `.env`. `tests/ai/test_pipeline_integration.py` checks the wiring and that every committed results file matches A5 and passes A3. |
| A8 | `tests/ai/test_question_bank.py`, `docs/ai_question_results.md` | Runs the data team's 17-case question bank against the AI layer: expected facts recomputed from the data, evidence hashes checked, the trend case met by the independently verified result, and a mocked Gemini reply with each applicable case's forbidden claim rejected. The conversational cases are not run: there is no chat interface this sprint. |
| A9 | `ai/explain.py` (`explain_detailed`), `ai/ai_trial.py`, `scripts/try_ai_explanations.py` | `explain_detailed()` returns the reason, raw reply and A3 problems behind each outcome (`explain()` is unchanged). The trial tool runs the real Gemini path on the committed results, prints each reply as ACCEPTED/REJECTED with reasons and saves `data/cache/ai_trial_report.json`; it never writes results files. |
| A10 | `ai/explain.py`, `ai/prompts/explain_v2.txt`, `ai/ai_trial.py` | Prompt v2 (`PROMPT_VERSION = "v2"`): plain-language facts ("Change: about X per month", missing months, p-value; no slope, tau, method or source text), and AI text must name the selected region. Gemini is called only when `GEMINI_LIVE=1` (or `allow_live=True`); a key alone is not enough, and cached approved replies are still reused. The trial tool defaults to a dry run (no request); `--ping` sends one tiny request with no project data; `--live` sends the facts. |
| A11 | `ai/ai_release.py`, `scripts/verify_ai_release.py` | Release check before the offline rehearsal; never calls Gemini. Rebuilds all five results with AI off and sockets blocked and requires them to match the committed files (approved `"ai"` text is exempt only in its two explanation fields). A fallback must equal `fallback_text()` of its own numbers; AI text must pass A3 and name its region. The API, dashboard and `backup_run.py` must not import the AI layer or a model SDK. Evidence: `docs/evidence/ai/a11_release_check.json`. |
| A12 | `docs/ai_submission.md`, `docs/evidence/ai/a12_*.json` | Submission handoff: the four checks (trend arithmetic, story review on files and live API, A11) re-run at the release commit on an LF checkout, all PASS; per-region results table, limits and a suggested AI-use statement. `tests/ai/test_submission_handoff.py` fails if the results change and the handoff is not updated. |

The fallback text (`ai/explain.py: fallback_text`) is built from the numbers only and passes the
A3 checks on every committed results file. Example (southeast): "From 2003-01 to 2024-12,
nighttime land surface temperature in Phoenix southeast rose by about 0.00889 degC per month
(0.107 degC per year). This trend is statistically significant (p < 0.001). 3 of 264 months are
missing and were left as gaps, not filled in."

Prompt changes go in a new file (`explain_v2.txt`) with `PROMPT_VERSION` bumped, never by editing
`explain_v1.txt` in place.

The checks are pattern-based. They catch the common ways a model drifts but cannot fully
understand meaning (a paraphrased cause can slip through), so they are a safety net, not proof.

## Building the results

Since A7 the pipeline (`pipeline/run.py`) imports `run_trend` and `METHOD` from A5 and `explain`
and `fallback_text` from A4; only `forecast` still comes from `pipeline/stubs.py` (returns
`None`). A region that fails eligibility (`TrendInputError`) is logged and skipped; the other
regions are still written and the command exits 1.

Rebuild all five results files from the qc-v1 CSVs (run from the repo root):

```bash
SRC="NASA Terra/MODIS MOD11C3.061 monthly nighttime land surface temperature (LST_Night_CMG), 0.05 deg grid, LP DAAC, doi:10.5067/MODIS/MOD11C3.061; data version phoenix-qc-v1.0"
uv run --locked python -m earth_system_trend.pipeline.run --all-regions --force \
  --region-id phoenix_study_area --region "Phoenix study area" --source "$SRC"
```

- Without `GEMINI_API_KEY` (or with `GEMINI_API_KEY= AI_DAILY_CALL_CAP=0` in front of the command)
  every explanation is the fallback: reproducible, no data leaves the machine.
- With a key, `GEMINI_MODEL` and `GEMINI_LIVE=1`, each region makes at most 3 requests; checked
  replies are written as `"ai"` and cached (A6), so a re-run costs nothing. Without
  `GEMINI_LIVE`, only already-cached approved replies are used.
- The committed qc-v1 results were built without a key (all `"fallback"`).

## Trying Gemini

Gemini is never called unless you ask: live calls need `GEMINI_LIVE=1` (pipeline) or the trial
tool's `--live`. A key in `.env` alone does nothing. All tests are mocked.

```bash
# .env (git-ignored): GEMINI_API_KEY=... and GEMINI_MODEL=<a Gemini Flash model>
uv run python scripts/try_ai_explanations.py              # DRY RUN: shows the facts, no request
uv run python scripts/try_ai_explanations.py --ping       # 1 tiny request, no project data
uv run python scripts/try_ai_explanations.py --live       # sends each region's facts
uv run python scripts/try_ai_explanations.py --live --fresh --region phoenix_northwest
```

- Dry run: prints the exact facts block each region would send (prompt v2) and any cached
  approved reply. No key needed.
- Ping: checks the key and model with one request ("ping" -> "OK"), no retry, counts against
  `AI_DAILY_CALL_CAP`. No results data is sent.
- Live: at most 3 requests per region. Prints ACCEPTED (passed A3 and names the region) or
  REJECTED with the reasons, and saves `data/cache/ai_trial_report.json` (never the key).
  Results files are never written.
- If the replies are good, run the pipeline command in "Building the results" **without**
  `GEMINI_LIVE`: approved replies come from the cache, so no request is made, and the results
  get `"explanation_source": "ai"`.
- Prompt changes go in a new `explain_vN.txt` with `PROMPT_VERSION` bumped; this changes the
  cache key, so a new `--live` run is needed.

Trial log: v1 on 2026-11-15 (gemini-3.5-flash-lite) - 5 of 5 accepted, numbers correct, but the
study-area reply did not name its region, none gave p or missing months, and two used "slope"
or "Kendall's tau".

v2 run on 2026-11-15 at 03:41 UTC (gemini-3.5-flash-lite, `--live`, approved by the AI owner).
All 5 replies were accepted, using 5 requests with no retries. Every number matched the results,
and every reply named its region and gave p (< 0.001) and the number of missing months. None
used "slope" or "tau" or claimed a cause, a forecast or advice. The v1 problems are fixed.

Some flaws pass the checks: "There were 1 missing months" (northwest), "There were 0 missing
months" (study area, where "all 264 months present" reads better), and "threshold 0.05" copied
from the facts block (northeast, southwest). The replies add little over the fallback text,
which says the same in cleaner English.

Decision: the committed results keep the fallback text. Using the Gemini text would change
results after the G4 freeze, so the frontend owner would have to agree and redo their snapshot
and story checks. The approved replies are cached only on the machine that ran the trial
(`data/cache/`, git-ignored). If the team adopts them, a pipeline rebuild without `GEMINI_LIVE`
reuses that cache with no new requests. A11, A12 and the README would then need updating.

## Release check (A11)

Run before the no-Wi-Fi rehearsal, and again whenever a results file changes:

```bash
uv run --locked python scripts/verify_ai_release.py --out docs/evidence/ai/a11_release_check.json
```

- **Rebuild:** each committed results file must equal what the pipeline builds from the qc-v1
  CSVs with AI off (no key, `GEMINI_LIVE=0`, cap 0, empty cache) and every socket connection
  blocked. This proves the frozen snapshot needs no Gemini or network to reproduce.
- **Provenance:** a `"fallback"` explanation must be exactly `fallback_text()` of the same
  file's numbers, so text left over from an older or different region's result fails. An `"ai"`
  explanation must pass the A3 checks and name the selected region.
- **Isolation:** imports are followed from `api/app.py`, `app/streamlit_app.py` and
  `scripts/backup_run.py`. None may reach `earth_system_trend.ai` or `openai`, so neither the live
  nor the offline demo can call Gemini. Only the pipeline and the trial tool use the AI layer.
- **Evidence:** the JSON records the commit, the SHA-256 of each results file (LF line endings,
  as stored in git), every explanation and the scanned modules. A test fails if a results file
  changes without the check being re-run.

Run on 2026-11-14: PASS. All five explanations are `"fallback"`, all five rebuild exactly, no
network attempts, 17 runtime modules scanned with no AI or model-SDK import.

## Rehearsal answers (sprint plan, FE-15)

The same verified snapshot backs all three role questions. The dashboard shows the evidence; these
are the limits the presenter states, in line with what the A3 checks forbid the AI text to claim.

- **City planner:** "What changed in Phoenix nighttime surface temperature between 2003 and
  2024?" Show the main area: nighttime land surface temperature rose by about 0.00771 degC per
  month (0.0926 degC per year; p < 0.001, seasonal Mann-Kendall), with all 264 months
  present. Then show a subregion and its missing months. It is a historical trend, not a cause and not a forecast.
- **Farmer:** "Does this tell me when to irrigate tomorrow?" No. It is monthly satellite
  surface temperature history, averaged over a box. It gives no weather for tomorrow and no
  irrigation amounts or timing.
- **Engineer:** "Can I use this to predict street-level heat or drainage losses?" No. The grid
  is 0.05 degrees (about 5 km), averaged over a study rectangle, so it says nothing at street
  level. It is land surface temperature, not air temperature, and it identifies no causes. It
  supports no site-specific engineering prediction.

## What the results do not say

Monthly clear-sky nighttime land surface temperature over a fixed rectangle. Not 2 m air
temperature, not daily extremes, not city boundaries. A trend is not a cause and not a forecast.

## Verification log

Run on 2026-11-14 against qc-v1 (`main` at 004c47f). All passed:

- All five CSVs: 264 rows, 2003-01..2024-12, gaps as listed above; the pipeline loader keeps every
  position.
- Results JSON: nulls at the same months; re-running `run_trend` reproduces every stored trend.
- `climatology.csv`: means and counts equal the 2003-2024 calendar-month means of the raw CSVs;
  every anomaly equals raw minus the same-month mean (difference 0.0); each month's anomalies
  average 0.
- Manifest checksums match; a month is blank exactly when its valid area is below 80%.
- Slope units and the serial-dependence sensitivity above.

## Guided Climate Detective runtime

The Streamlit guided demo now reuses `ai.trend` and `ai.ai_checks` for deterministic seasonal
statistics. The release import scan allows these two modules and follows their imports, while
continuing to reject model clients and SDKs. It does not permit runtime Gemini requests.
Offline rebuild comparison permits only relative p-value differences up to 1e-14 (no absolute
tolerance), accounting for machine precision across SciPy/platform versions; every other
statistical field remains exact. Rounding a tiny p-value to zero still fails verification.
