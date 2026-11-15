# FE-14 offline snapshot rehearsal

This frontend backup reads the five approved real results directly. It does not
start an API, run statistics, call Gemini/NASA, or require a CDN. It displays
**Connection: Offline snapshot** and the freeze ID, retains the supplied source,
method and explanation, and preserves all missing months. An invalid or changed
result fails closed with Retry snapshot; it cannot fall through to the live API.

## Prepare while connected

The tested transferable bundle targets **macOS 14 or later on Apple silicon,
Python 3.12** (the included SciPy wheel requires macOS 14). Install
Python 3.12 on both laptops before going offline (including its bundled pip/venv).
The bundle includes compiled wheels for the build Mac's compatible platform;
other macOS releases might need their own build. Do not assume Intel/Windows
compatibility. uv is needed on the build Mac, but not to run the package.

From a clean review checkout with the normal development environment installed:

```sh
uv run --locked python -m scripts.build_frontend_offline --out /tmp/estd-offline
```

This verifies the five backend/data-team result hashes, copies only frontend code,
approved JSONs and provenance/docs, exports locked frontend/runtime requirements,
builds the project wheel and downloads compatible dependency wheels. It excludes
`.env`, credentials, `.git`, caches and existing virtual environments. Keep the
archive and its printed SHA-256 together. Transfer the archive by USB or AirDrop;
the wheelhouse and recording should not be committed to Git.

## Run without Wi-Fi (both laptops)

Extract `estd-offline.tar.gz`, then from the extracted folder:

```sh
sh START_OFFLINE.command --check
sh START_OFFLINE.command
```

The first invocation creates `.venv` using preinstalled `python3.12`, installs the
included wheels with `--no-index` and locked hashes, and verifies the approved
results. No registry/cache is required. The second starts only a loopback
Streamlit server. Open http://127.0.0.1:8501. Stop with Ctrl+C. If occupied, run
`sh START_OFFLINE.command --port 8514` and open that port. Python is a prerequisite,
not included in the archive. Do the installation check before travelling.

In a prepared repository environment, the equivalent launcher is:

```sh
uv run --offline --no-sync python scripts/run_frontend_offline.py
```

Do not use `API_URL=` alone: that is the distinct synthetic Example Region preview.
`OFFLINE_SNAPSHOT_DIR` selects a bundle root with the result files and delivered
freeze manifest; it takes precedence over API_URL. The launcher supplies it.

## Rehearse the same story

1. Disable Wi-Fi and other external network connections on each laptop. Leave
   loopback networking available for the local browser/server. Record OS/Python,
   bundle SHA-256 and the observed result for each physical laptop.
2. Confirm Offline snapshot and `phoenix-qc-v1.0-handoff-1`, Phoenix study area,
   2003-01 to 2024-12, slope `0.0077125 °C/month`, p < 0.001 and increasing.
3. Switch to northwest: slope `0.00755147 °C/month`; May 2024 stays missing.
   Read the supplied explanation, then expand source/method/period.
4. Explain that this is historical monthly nighttime surface temperature, not
   air temperature, an irrigation prescription, a causal analysis or a forecast.
5. Repeat the switch and return on laptop 2, using the exact same archive.
   Record a short clip from the offline page and play the saved clip with Wi-Fi
   still off. No account, remote font or external asset should be required.

### Three role questions and verified rehearsal answers

* **City Planner:** *"What changed in Phoenix nighttime surface temperature between 2003 and 2024?"*
  * **Evidence:** Whole Phoenix study area shows an increasing trend with Sen's slope of `+0.0077125 °C/month` (approx. `+0.0926 °C/year`), Kendall's tau `0.180`, and `p < 0.001` (statistically significant at `p < 0.05`).
  * **Provenance:** NASA Terra/MODIS MOD11C3.061 monthly nighttime land surface temperature at 0.05° resolution across 264 calendar positions (2003-01 to 2024-12). Subregions show consistent warming trends with 8 expected missing months (Northwest: 1 gap; Northeast: 2 gaps; Southwest: 2 gaps; Southeast: 3 gaps) correctly retained as visible gaps.

* **Farmer:** *"Does this tell me when to irrigate tomorrow?"*
  * **Boundary:** No. This dataset is a retrospective monthly aggregate of historical nighttime ground surface heat, not tomorrow's weather forecast, soil moisture measurement, or evapotranspiration index.
  * **Explanation:** It provides multi-decadal climatological context on nocturnal urban heat accumulation, but cannot prescribe day-to-day agricultural irrigation timing.

* **Engineer:** *"Can I use this to predict street-level heat or drainage losses?"*
  * **Boundary:** No. The spatial resolution is a regional 0.05° grid average (roughly 5 × 5 km per cell), not parcel- or street-scale.
  * **Explanation:** It does not model microclimate pavement materials, localized shade, urban street canyons, or stormwater hydraulic conveyance. The observed trend describes broad regional surface warmth without site-specific causal engineering predictions.

A process-level network-blocked test on one Mac is useful evidence, but does not
substitute for two physical laptops with their external connections disabled.
Do not mark G5 passed until both laptop records and clip playback are observed.

## Recorded rehearsal and remaining G5 checks

On November 14, 2026 (local time), a fresh package environment installed all 56
included wheels with pip's cache disabled and all networking denied by a macOS
sandbox. The integrity preflight and approved snapshot check passed. The first Mac
uses Apple silicon, macOS 27.0 and Python 3.12.15. Python itself is not bundled.

The packaged environment rendered all five regions in AppTest with all networking
denied. Each region retained 264 monthly positions; gap counts were 0/1/2/2/3 in
main/northwest/northeast/southwest/southeast order. Plotted values, source, method
and supplied explanation matched the approved files. The browser rendered main
and northwest from a server permitted loopback connections only. Its 95 observed
DOM-linked script/style/image/font references were local; this asset inventory
is not an exhaustive browser network trace. See `docs/evidence/frontend/fe14_*.json`.

The separate 16-second MP4 is a screenshot walkthrough of the actual local page,
not a continuous screen recording or evidence of physical Wi-Fi being disabled.
All 384 frames decoded successfully. Opening and playing it on the rehearsal
laptops remains pending. Copy this clip alongside the archive before disconnecting.

| G5 evidence | Status |
| --- | --- |
| Fresh offline dependency installation, first Mac | Passed with networking denied |
| Five-region approved snapshot/page agreement | Passed with networking denied |
| First physical laptop with Wi-Fi/external links off | Pending |
| Second physical laptop, user confirmed Apple silicon | Pending; confirm macOS/Python prerequisites |
| Same archive and story on both physical laptops | Pending |
| Saved clip plays with Wi-Fi off | Pending |

The archive and clip names, sizes and SHA-256 hashes are recorded in
`docs/evidence/frontend/fe14_package.json`. Transfer both files rather than the
installed `.venv`. G5 is pending; this ticket's PR stays draft for review.

Frontend verification passed 123 tests and repository lint. The full suite had
610 passes and four failures in `tests/ai/test_release_check.py`. The same four
failures reproduce on untouched main `6318c556dbb970613798f5d3570cda2093ec24e4`:
recomputed p-values differ from saved results in their last floating-point bits
(for example, main `7.022635523002321e-11` saved versus `7.02263552300232e-11`
recomputed). The AI owner must resolve that exact-equality release check. This
frontend task preserves every approved result byte and does not regenerate data,
statistics or explanations. No deployment or external teammate message was made.
