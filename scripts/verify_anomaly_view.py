"""Check the dashboard's Temperature/Anomaly switch against the Data layer's CSVs.

Drives the real page (Streamlit AppTest) for all five regions, switches to Anomaly and back,
and compares every plotted date and value with data/processed/anomaly*.csv and
timeseries*.csv, including missing months. Uses an API (default: local) or, with
--offline, the approved offline snapshot. Prints a JSON report; exit code 1 on any failure.

  USE_MOCK=false uv run --locked uvicorn earth_system_trend.api.app:app --port 8000
  uv run --locked python scripts/verify_anomaly_view.py --api http://127.0.0.1:8000
  uv run --locked python scripts/verify_anomaly_view.py --offline
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app/streamlit_app.py"
TOLERANCE = 5e-5  # results files store values rounded to 4 decimals
REGIONS = {
    "phoenix_study_area": "",
    "phoenix_northwest": "_phoenix_northwest",
    "phoenix_northeast": "_phoenix_northeast",
    "phoenix_southwest": "_phoenix_southwest",
    "phoenix_southeast": "_phoenix_southeast",
}


def read_csv(name: str) -> list[tuple[str, float | None]]:
    with open(ROOT / "data/processed" / name, newline="") as handle:
        return [(row["date"], float(row["value"]) if row["value"].strip() else None)
                for row in csv.DictReader(handle)]


def compare(plotted_x, plotted_y, expected) -> list[str]:
    problems = []
    if len(plotted_x) != len(expected):
        problems.append(f"{len(plotted_x)} plotted positions, CSV has {len(expected)}")
    for x, y, (date, value) in zip(plotted_x, plotted_y, expected):
        if x != date:
            problems.append(f"date {x} != CSV {date}")
        elif value is None and y is not None:
            problems.append(f"{date}: CSV gap plotted as {y}")
        elif value is not None and (y is None or not math.isclose(y, value, abs_tol=TOLERANCE)):
            problems.append(f"{date}: plotted {y} != CSV {value}")
    return problems[:10]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--offline", action="store_true", help="use the approved offline snapshot")
    args = parser.parse_args()
    os.environ["API_URL"] = "" if args.offline else args.api
    os.environ["OFFLINE_SNAPSHOT_DIR"] = str(ROOT) if args.offline else ""
    sys.path.insert(0, str(ROOT))
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP), default_timeout=120).run()
    report = {"mode": "offline snapshot" if args.offline else f"API {args.api}", "regions": {}}
    ok = not app.exception and not app.error
    for region_id, suffix in REGIONS.items():
        app.selectbox[0].select(region_id).run()
        next(r for r in app.radio if r.label == "Show").set_value("Anomaly").run()
        spec = json.loads(app.get("plotly_chart")[0].proto.spec)
        trace, layout = spec["data"][0], spec["layout"]
        anomaly_csv = read_csv(f"anomaly{suffix}.csv")
        zero_line = any(s.get("type") == "line" and s.get("y0") == 0 == s.get("y1")
                        for s in layout.get("shapes", []))
        a_problems = compare(trace["x"], trace["y"], anomaly_csv)
        title = layout["title"]["text"]
        y_title = layout["yaxis"]["title"]["text"]
        a_gaps = [x for x, y in zip(trace["x"], trace["y"]) if y is None]
        next(r for r in app.radio if r.label == "Show").set_value("Temperature").run()
        spec = json.loads(app.get("plotly_chart")[0].proto.spec)
        t_trace = spec["data"][0]
        t_problems = compare(t_trace["x"], t_trace["y"], read_csv(f"timeseries{suffix}.csv"))
        label = app.subheader[0].value
        checks = {
            "heading": label,
            "chart_title": title,
            "title_matches_region": title.startswith(label + ":"),
            "anomaly_y_axis": y_title,
            "anomaly_units_degC": "(°C)" in y_title and "(°C)" in title,
            "baseline_2003_2024_calendar_month_mean": "2003–2024 calendar-month mean" in title,
            "zero_line": zero_line,
            "anomaly_positions": len(trace["x"]),
            "anomaly_gaps": a_gaps,
            "anomaly_mismatches": a_problems,
            "temperature_mismatches": t_problems,
            "first_anomaly": [trace["x"][0], trace["y"][0]],
            "first_temperature": [t_trace["x"][0], t_trace["y"][0]],
            "page_errors": [str(e.value) for e in app.exception] + [e.value for e in app.error],
        }
        passed = (checks["title_matches_region"] and checks["anomaly_units_degC"]
                  and checks["baseline_2003_2024_calendar_month_mean"] and zero_line
                  and len(trace["x"]) == 264 and not a_problems and not t_problems
                  and not checks["page_errors"])
        checks["pass"] = passed
        ok = ok and passed
        report["regions"][region_id] = checks
    report["pass"] = ok
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
