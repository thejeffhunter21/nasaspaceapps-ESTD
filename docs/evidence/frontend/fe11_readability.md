# FE-11 readability checks

Checked November 14, 2026 against local FE-11 code based on `main` at
`b762e921b857fb0df8ece44316c1b15b67c3f626`. Backend: https://estd-api.onrender.com.
The public dashboard has not been redeployed with this unreviewed branch.

## Observed browser checks

Browser: Codex in-app browser. These observations do not substitute for native
Chrome and Safari release checks.

| Check | Observed result |
| --- | --- |
| Phone, 375 × 812 | Document width 375; no horizontal page overflow. All three cards stack, each 343 px wide. Title, period and explanation wrap. Chart retains readable month ticks, variable/units and missing-data wording. |
| Desktop, 1440 × 900 | Document width 1440. Three cards share one row, each 416 px wide, with the same top coordinate. |
| Region keyboard interaction | Arrow keys and Enter selected northwest; heading, slope, observations and explanation updated to northwest. |
| Focus | Shift+Tab from Region focused Refresh data; native focus shadow was visible (3.2 px ring). |
| Provenance keyboard interaction | Enter opened Source, method and definitions and exposed supplied source/method/period and definitions. |
| Non-color meaning | Direction and significance are written in words. Chart accessible name includes region, variable, period, units, direction, slope, significance criterion and number of missing months. |
| Contrast spot check | In the observed native dark theme, text RGB(237,235,232) on background RGB(23,22,20) has 15.20:1 contrast. Captions inherit 0.6 opacity; compositing gives 6.11:1. This is a spot check, not an audit of all states/themes. |

Native Chrome could not be controlled: multiple installed copies initially caused
ambiguity; selecting `/Applications/Google Chrome.app` timed out. Safari access
reported **Computer Use permissions are not granted**. No Chrome/Safari success
is claimed. Teammates should run the same selection/refresh/expander journey on
both browsers before release. Test at phone and desktop widths, with keyboard
navigation and each supported appearance theme. Screen-reader behavior beyond
accessible-name inspection remains unverified.

## Automated evidence

- The five new slope-format tests initially failed because `display_slope` did
  not exist, then passed after implementation. They cover positive, negative,
  zero and very small slopes without changing stored precision or sign.
- `uv run --locked pytest tests/frontend -q`: **108 passed**.
- `uv run --locked pytest -q`: **536 passed**.
- `uv run --locked ruff check .` and `git diff --check`: passed.
- `uv run --locked python scripts/verify_frontend_snapshot.py --api-url https://estd-api.onrender.com --out /tmp/estd-fe11-snapshot.json`: **PASS** for all five regions. Chart times/values/gaps, supplied explanation/provenance and formatted cards agree with API and approved snapshot.

The verifier's expected card display now uses six significant figures. Its raw
CSV/API/statistic comparisons remain unchanged. No observations, calculations,
explanations, significance decisions or network/recovery behavior were changed.

VERDICT: PASS for implementation, regression, live agreement and in-app responsive checks.
Native Chrome/Safari acceptance remains pending due to unavailable computer permissions.
