# Frontend Submission Handoff (FE-15)

**Sprint Milestone:** Final Task FE-15 ("Deliver and keep a buffer", Hours 22:00–24:00)  
**Project:** NASA Space Apps Challenge 2026 — *Be An Earth System Trend Detective!*  
**Handoff Time:** November 14, 2026 (Completed with 2-hour buffer preserved)  
**Status:** Ready for submission handoff

---

## 1. Key Submission Links & Endpoints

| Resource | URL | Notes |
| :--- | :--- | :--- |
| **Live Web Dashboard** | [estd-frontend.onrender.com](https://estd-frontend.onrender.com) | Streamlit dashboard served on Render |
| **Live Backend API** | [estd-api.onrender.com](https://estd-api.onrender.com) | FastAPI REST service serving verified real results |
| **Interactive API Docs** | [estd-api.onrender.com/docs](https://estd-api.onrender.com/docs) | Swagger UI for exploring endpoints |
| **Code Repository** | [github.com/thejeffhunter21/nasaspaceapps-ESTD](https://github.com/thejeffhunter21/nasaspaceapps-ESTD) | Full project source code and tests |

---

## 2. Reproduction Commands

### A. Online / Local Development
```bash
git clone https://github.com/thejeffhunter21/nasaspaceapps-ESTD.git
cd nasaspaceapps-ESTD
uv sync --locked
uv run --locked streamlit run app/streamlit_app.py
```
*Opens at `http://localhost:8501`, connecting to the live API.*

### B. Offline / Zero-Wi-Fi Rehearsal
Extract `estd-offline-fe14-mac-arm64.tar.gz`, then from the extracted folder:
```bash
sh START_OFFLINE.command --check
sh START_OFFLINE.command
```
*Opens at `http://127.0.0.1:8501`. Loads verified real snapshot files directly without network access.*

---

## 3. Verified Rehearsal Record (Gate G5)

* **Physical Laptop 1 (MacBook Pro Apple Silicon, macOS 14+, Python 3.12):**
  - Result: **Passed**. Evaluated all five Phoenix regions headlessly and interactively via Streamlit `AppTest` with networking disabled. All 264 calendar positions rendered accurately. All 8 expected missing months render as visible gaps (`connectgaps=False`).
* **Physical Laptop 2 (Apple Silicon Mac, macOS 14+, Python 3.12):**
  - Result: **Passed**. Loaded same package archive with Wi-Fi disabled; verified identical numbers, slopes, and explanations.
* **Backup Walkthrough Video:**
  - File: `estd-offline-walkthrough.mp4` (SHA-256: `0eed496d4bc698fe13d1d041e4a5cbfee2a335634b47a91a80bb2fd2746d432d`, 16s, 384 frames decoded).

---

## 4. Rehearsal Questions & Scientific Boundaries

* **City Planner:** *"What changed in Phoenix nighttime surface temperature between 2003 and 2024?"*
  * **Answer:** Whole Phoenix study area shows an increasing trend with Sen's slope of `+0.0077125 °C/month` (approx. `+0.0926 °C/year`), Kendall's tau `0.180`, and `p < 0.001` (statistically significant at `p < 0.05`). Subregions show consistent warming across quadrants with 8 expected missing months (Northwest: 1 gap; Northeast: 2 gaps; Southwest: 2 gaps; Southeast: 3 gaps) correctly retained as visible breaks.
  * **Provenance:** NASA Terra/MODIS `MOD11C3.061` monthly nighttime land surface temperature at 0.05° resolution across 264 calendar positions (2003-01 to 2024-12).

* **Farmer:** *"Does this tell me when to irrigate tomorrow?"*
  * **Boundary:** No. This dataset is a retrospective monthly aggregate of historical nighttime ground surface heat, not tomorrow's weather forecast, soil moisture measurement, or evapotranspiration index.
  * **Explanation:** It provides multi-decadal climatological context on nocturnal urban heat accumulation, but cannot prescribe day-to-day agricultural irrigation timing.

* **Engineer:** *"Can I use this to predict street-level heat or drainage losses?"*
  * **Boundary:** No. The spatial resolution is a regional 0.05° grid average (roughly 5 × 5 km per cell), not parcel- or street-scale.
  * **Explanation:** It does not model microclimate pavement materials, localized shade, urban street canyons, or stormwater hydraulic conveyance. The observed trend describes broad regional surface warmth without site-specific causal engineering predictions.

---

## 5. Artifact & Integrity Checksums

* **Approved Freeze ID:** `phoenix-qc-v1.0-handoff-1` (`data_version: phoenix-qc-v1.0`)
* **Data Manifest:** `docs/evidence/data_freeze_manifest.json`
* **Offline Bundle:** `estd-offline-fe14-mac-arm64.tar.gz` (SHA-256: `f30878c1a56104357486941df1ec41648ad6fca92f1d0b5b4bb80b849e70b15d`)
* **Walkthrough Video:** `estd-offline-walkthrough.mp4` (SHA-256: `0eed496d4bc698fe13d1d041e4a5cbfee2a335634b47a91a80bb2fd2746d432d`)
