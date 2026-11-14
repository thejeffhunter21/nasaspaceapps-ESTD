# Monthly AI evidence and question checks

## What these files do

ai_evidence.json provides verified facts for the Phoenix study area and its four boxes: source, period, units, input CSV hashes, regional baselines/counts, missing dates, coverage, example observations and measurement limits.

ai_question_tests.json defines 17 review questions, expected facts, required qualifications and forbidden claims. These are manual/implementation-independent evaluation cases, not an executable test runner. Actual chatbot answers have not been evaluated.

## How to use

1. Put these three files directly in docs/ on a new data branch. Do not upload their containing folder inside docs/.
2. AI/backend: check the input SHA-256 hashes against the served dataset before using this evidence. If data changes, rebuild evidence and expected answers together. Region ID phoenix_study_area maps to phoenix in climatology.csv and coverage.csv.
3. AI: supply the selected region's relevant evidence to your answer logic. Load the corresponding raw/anomaly CSV for questions beyond the included examples; this JSON does not contain every observation.
4. Submit each question through the actual chat/answer implementation, preserving region_id and any history. Compare its answer with expected_facts, must_convey and must_not_claim. Temperature tolerance is 0.0001 degrees Celsius to allow the current API's four-decimal display rounding.
5. Record case ID, answer, pass/fail, issue, data version and method. Backend checks the loading behavior; AI reviews scientific wording and unsupported claims.
6. Trend significance is intentionally conditional: the data owner has not validated the final statistical results in this package. Attach separately validated results using the same source hashes, exact method and slope units. Do not treat a copied live API response as verification of the method.

## Validation completed

All raw/anomaly/coverage/baseline input hashes matched the delivered snapshots. All 1,320 calendar positions and eight gap positions agree. Every baseline mean/count and every valid anomaly was independently checked to within 1e-12 degrees Celsius. JSON is valid and contains no NaN or Infinity. The expected numerical answer examples were verified from those inputs.

## Remaining part of PDF block 8:00-10:00

Give the files to AI/backend and review their data loading together. The earlier live API check found all five 264-month calendars and eight nulls preserved, with values rounded to four decimals. A new deployment still needs its own snapshot check. Run and record the question cases when the answer interface is ready. Preparing the case file does not mean those cases passed against the application.
