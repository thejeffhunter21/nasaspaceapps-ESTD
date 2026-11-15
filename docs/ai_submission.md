# AI layer: submission handoff

For the submission owner and judges. This is what the AI layer delivers in the release, how it was
verified and what it does not claim. Method details are in [ai.md](ai.md).

**Release checked:** `main` at `6318c556dbb970613798f5d3570cda2093ec24e4`, data version
`phoenix-qc-v1.0`, verified on 2026-11-15 (UTC) against both the committed files and the
deployed API (`https://estd-api.onrender.com`).

## What the AI layer does

1. **Trend test.** A seasonal Mann-Kendall test with seasonal Sen's slope on 264 monthly values
   (2003-01 to 2024-12) for each of five regions. The p-value is unrounded and is compared
   strictly with 0.05. Missing months stay as gaps; nothing is filled in.
2. **Explanation.** One short plain-language paragraph per region. It is either an automatic
   summary built by code from the numbers or Gemini text that passed the safety checks. The
   checks reject wrong numbers, wrong significance wording, causes, forecasts, advice and the
   wrong region.

The dashboard and the API only display these stored results. They never run the test, write
text or call Gemini.

## Results in this release

| Region | °C per month | °C per year (×12) | p | Direction | Missing months | Explanation |
|---|---|---|---|---|---|---|
| Phoenix study area | 0.00771 | 0.0926 | < 0.001 (7.02e-11) | increasing | 0 | automatic summary |
| Northwest | 0.00755 | 0.0906 | < 0.001 (3.28e-10) | increasing | 1: 2024-05 | automatic summary |
| Northeast | 0.00529 | 0.0635 | < 0.001 (3.80e-06) | increasing | 2: 2007-07, 2023-07 | automatic summary |
| Southwest | 0.00776 | 0.0931 | < 0.001 (2.98e-10) | increasing | 2: 2007-07, 2010-07 | automatic summary |
| Southeast | 0.00889 | 0.107 | < 0.001 (2.78e-14) | increasing | 3: 2012-07, 2017-07, 2024-06 | automatic summary |

All five trends are increasing and statistically significant. The eight missing months are the
expected gaps of the approved snapshot.

**AI text is not used in this release.** All five explanations are automatic summaries and the
dashboard labels them "Automatic summary". The Gemini path is built and tested
(prompt v2, safety checks, cache, daily cap, opt-in live switch), but the v2 trial was not run
before the feature freeze, so no Gemini text was approved for the demo.

## How it was verified

All four checks passed at the release commit, run on a clean checkout with LF line endings
(the files as stored in git). The full test suite passed there too: 606 tests.

| Check | What it proves | Evidence |
|---|---|---|
| Trend arithmetic (data team's verifier) | An independent same-month calculation reproduces every stored slope and p. Inputs match the data manifest. The live API serves the same numbers, and an unknown region returns 404. | [a12_trend_verification.json](evidence/ai/a12_trend_verification.json) |
| Story review, files | Each committed explanation passes the checks, uses the seasonal method and real data, and stays under 120 words. | [a12_story_review_files.json](evidence/ai/a12_story_review_files.json) |
| Story review, live API | The same review on what the deployed API serves. | [a12_story_review_live.json](evidence/ai/a12_story_review_live.json) |
| AI release check (A11) | The results rebuild exactly with AI off and the network blocked. Each explanation belongs to its own result. The API, dashboard and backup launcher cannot reach the AI layer or Gemini. | [a12_release_check.json](evidence/ai/a12_release_check.json) |

To repeat the checks (no Gemini calls; drop `--api-url` to stay offline):

```bash
uv run --locked python scripts/verify_monthly_trends.py --source-commit "$(git rev-parse HEAD)" \
  --out /tmp/trend.json --api-url https://estd-api.onrender.com
uv run --locked python scripts/review_frontend_story.py --out /tmp/story.json
uv run --locked python scripts/verify_ai_release.py --out /tmp/release.json
```

On Windows, run them on a checkout with `core.autocrlf=false`. The data-hash checks compare
exact file bytes, so a CRLF checkout fails them even though the data is unchanged.

## What it does not claim

- This is monthly clear-sky **nighttime land surface temperature** from MODIS, averaged over a fixed
  rectangle around Phoenix (0.05° grid, about 5 km). It is not air temperature, not daily
  extremes and not street level.
- A trend is not a cause and not a forecast. Nothing here predicts future temperatures or gives
  irrigation, health or engineering advice.
- "Statistically significant" means the trend is unlikely to be chance under the test's
  assumptions. The serial-dependence sensitivity check is in [ai.md](ai.md#serial-dependence).
- Answers for the planner, farmer and engineer rehearsal questions are in
  [ai.md](ai.md#rehearsal-answers-sprint-plan-fe-15).

## AI-use statement

The README's "AI use" credit states this. The same wording can go on the submission form:

> AI tools helped write code and documentation. Every explanation in the app is an automatic
> summary written by code from the computed numbers, labeled "Automatic summary". The pipeline
> can optionally use Google Gemini to word explanations. It keeps that text only if it passes
> automated checks of numbers, wording and claims, and labels it "AI-assisted explanation". The
> committed results contain no Gemini text, and nothing calls Gemini while the app runs.
