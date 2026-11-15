# Phoenix study area: processed-data freeze

Freeze ID: **phoenix-qc-v1.0-handoff-1**. Data version remains **phoenix-qc-v1.0**;
no observations, gaps, baselines or saved model results were changed by this handoff.
The checked source snapshot is commit `bc2230307e0871db7ab7ee40f7466a4ee59602bf`.
This is the work-10 data handoff, not full application or deployment sign-off.

## What is frozen

`docs/evidence/data_freeze_manifest.json` records SHA-256 checksums and byte counts
for 24 processed-data and supporting handoff files. It separately records 14 analysis
reference files, including saved results, method code and dependency versions.
Frontend development can continue without changing the numerical data freeze.
An intentional analysis change requires reviewing the reference snapshot, not silently
overwriting its checksums.

The five regions each contain 264 calendar positions, January 2003–December 2024.
There are eight missing subregion values, 1,320 coverage records and 60 baseline rows.
The study-area CSV has no missing values. API ID `phoenix_study_area` corresponds to
`phoenix` in the climatology and coverage files.

The measurement is NASA MOD11C3.061 clear-sky nighttime land surface temperature
in degrees Celsius. It is not air temperature or a future-weather forecast.
Anomaly equals the value minus that region's valid 2003–2024 mean for the same
calendar month. Preserve gaps; do not replace them with zeros or interpolate them.
See `docs/data_card.md` for study bounds, source and quality-control details.

## Verify before integration or a demo

From the repository root, with Python 3.12:

```sh
python scripts/verify_data_freeze.py
python scripts/verify_data_freeze.py --include-analysis --out /tmp/data-freeze-check.json
```

These commands need no network, credentials, AI service or NASA download.
They read files and compare hashes; they do not regenerate results.
The first command checks the data handoff; the second also checks the recorded
analysis reference. A nonzero exit means a checked file is missing or changed.
File integrity alone does not certify scientific validity or live UI behavior.

`docs/evidence/data_freeze_validation.json` records the local snapshot checks,
all five saved-result comparisons, and independent monthly-trend verification.
Coverage counts and dates agree with the raw series; saved values match the documented
four-decimal preprocessing. The method is seasonal Mann–Kendall and seasonal Sen's
slope as documented in `docs/ai.md`; do not describe it as generally corrected for
serial correlation.

## Remaining integration checks

- Visually check the frontend raw/anomaly toggle for all five regions, including
  correct anomaly axis labels, preserved gaps and source/baseline wording.
- Record final deployed frontend/backend versions and repeat live comparisons
  after any relevant deployment change. The local freeze report is not a new live test.
- Confirm unsupported locations are handled clearly. If chat or forecasting is
  unavailable, keep those features out of the demonstrated capabilities.
- Rehearse the offline demo on two laptops using this same data and analysis snapshot.

Do not start a new NASA extraction or add daily prediction data for this monthly
handoff. For an intentional data correction, review the changed values and provenance,
update the appropriate source manifests and version, rerun numerical verification,
and create a new reviewed freeze record. Never refresh hashes merely to hide a failure.
