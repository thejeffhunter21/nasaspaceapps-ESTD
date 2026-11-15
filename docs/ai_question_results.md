# AI question-bank results

Record for [ai_question_tests.json](ai_question_tests.json) (step 5 of
[README_AI_EVIDENCE.md](README_AI_EVIDENCE.md)).

- Data version: phoenix-qc-v1.0. Method: Seasonal Mann-Kendall test (12-month period) with
  seasonal Sen's slope (`ai/trend.py`).
- Run on 2026-11-14 at `main` d5f531a + branch `feature/ESD-Step8-AI`. No Gemini or OpenAI
  request was made; AI replies were mocked.
- Reproduce: `uv run --locked pytest tests/ai/test_question_bank.py -q`

## What was and was not run

The app has **no question-answering interface**. The frontend plan excludes "free-text AI chat"
this sprint; the AI layer writes one summary per region (`explain()`). So the conversational
cases were **not run** as conversations, and no chatbot answer has been evaluated.

What was run, for every case:

1. **Expected facts** recomputed from the committed CSVs, coverage and baseline files, and the
   evidence file's input hashes checked against the data.
2. **Summary safety:** a mocked Gemini reply making the case's forbidden claim is sent through
   `explain()`. Pass = the A3 checks reject it and the fallback is shown.
3. **Summary content:** every region's summary names its own region, the period,
   "nighttime land surface temperature", degC per month, significance and missing months.

## Results

| Case | Role | Region | Expected facts | Forbidden claim in a summary | Rejected because |
|---|---|---|---|---|---|
| `measurement` | general | study area | n/a (wording) | Pass | wrong product: air temperature |
| `period` | general | study area | Pass | Pass | current claim: "current", "live measurements" |
| `exact_observation` | general | study area | Pass | Pass | number 7.76 not in results; "day" (data is monthly) |
| `missing_month` | general | northwest | Pass | Pass | gap 2024-05 not described as missing; number 0 |
| `missing_comparison` | general | study area | Pass | Pass | place: mentions northwest in a whole-area summary |
| `anomaly_calculation` | general | study area | Pass | Not applicable | summaries do not cite anomalies (anomaly view) |
| `positive_anomaly` | general | study area | n/a (wording) | Not applicable | summaries do not cite anomalies (anomaly view) |
| `baseline_count` | general | northeast | Pass | Not applicable | summaries do not cite baselines (anomaly view) |
| `region_switch` | general | northeast | Pass | Pass | number 0.00771 is the whole-area slope, not northeast's |
| `outside_period` | general | study area | Pass | Pass | date 2026-07 not in data; number 31 |
| `tomorrow` | farmer | study area | n/a (wording) | Pass | forecast claim: "will", "tomorrow" |
| `unsupported_location` | general | study area | Pass | Pass | place: Tucson |
| `trend_significance` | general | all five | Pass (see below) | Pass | number 0.5 not in results |
| `cause` | city planner | study area | n/a (wording) | Pass | cause claim: "caused" |
| `drainage` | engineer | study area | n/a (wording) | Pass | advice: "drainage", "capacity"; number 25 |
| `irrigation` | farmer | study area | n/a (wording) | Pass | advice: "irrigation"; number 400 |
| `planning_priority` | city planner | study area | n/a (wording) | Pass | place: street-level; advice: "shade"; number 1.5 |

**Trend case.** The case passes on its conditional path: a separately validated, matching result.
For all five regions the stored trend equals the data team's independent calculation
([monthly_trend_verification.json](evidence/monthly_trend_verification.json), to 1 part in 1e9),
with the same input SHA-256, the named method and degC/month units. Example (study area): slope
0.0077125 degC/month, p 7.02e-11, increasing. As the verification notes, numerical agreement is
not approval of every assumption of the method (see [ai.md](ai.md), serial dependence).

**Summary content.** Pass for all five regions (fallback summaries; no key in tests).

## Changes made for this run (A3)

The bank exposed claims the checks did not catch. A3 now also rejects:

- naming another box (compass name), another city, or street-level places;
- mentioning a missing month's date without saying it is missing;
- a whole number that does not round from a real value of at least 0.5 (e.g. "0 degC" no longer
  matches p close to 0); exact values such as "0 missing months" still pass;
- calling the data current or live;
- "day"/"days" (the data is monthly) and "drainage", "capacity", "shade" (advice).

## Limits

- Conversational behaviour (history, follow-ups, refusals such as "Tucson is not supported") is
  untested because no conversational interface exists.
- The checks are pattern-based. Whole numbers are matched by value, not meaning (a reply saying
  "1 degC" passes if the region has exactly 1 missing month). Paraphrased causes or advice
  without the listed words can still pass.
- No live Gemini output has been evaluated; the prompt has only been tested with mocked replies.
