"""One command: CSV -> trend -> explanation -> checked results file.

  uv run python -m earth_system_trend.pipeline.run                 # main area
  uv run python -m earth_system_trend.pipeline.run --all-regions   # + every sub-region
  uv run python -m earth_system_trend.pipeline.run --stub          # fake CSV, no Data layer needed
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import sys
from pathlib import Path

# The ONE place the AI layer's functions are imported.
from ..ai.explain import explain, fallback_text  # A4 (A6 cache + cap inside)
from ..ai.trend import METHODS, run_trend  # A5
from ..contract import Results
from .stubs import forecast  # no AI-layer forecast this sprint: returns None
from .timeseries import SeriesError, load_series

log = logging.getLogger("pipeline")

METHOD = METHODS["seasonal"]  # run_trend's default method; written to results["method"]

DEFAULTS = {
    "csv": "data/processed/timeseries.csv",
    "out": "results/results.json",
    "regions_file": "data/processed/regions.json",
    "region_id": "study_area",
    "region": "Study area",
    "variable": "Nighttime land surface temperature",
    "units": "degC",
    "source": ("NASA Terra/MODIS MOD11C3.061 monthly nighttime land surface temperature (LST_Night_CMG), 0.05 deg grid "
               "(LP DAAC, doi:10.5067/MODIS/MOD11C3.061)"),
}


def build(csv: Path, *, region_id: str, region: str, variable: str, units: str,
          source: str, forecast_on: bool = False) -> Results:
    months, values = load_series(csv)
    log.info("loaded %s: %d months", csv, len(months))
    trend = dict(run_trend(values))
    trend["slope_unit"] = f"{units}/month"  # the pipeline knows the units, the AI layer doesn't
    log.info("trend: %s (p=%s)", trend["trend"], trend["p"])
    draft = {"region_id": region_id, "region": region, "variable": variable, "units": units,
             "period": {"start": months[0], "end": months[-1]},
             "series": [{"time": t, "value": v} for t, v in zip(months, values)],
             "trend": trend, "source": source, "method": METHOD}
    try:
        fc = forecast(values, months=12) if forecast_on else None
    except Exception as exc:  # noqa: BLE001 - a forecast problem never stops the results
        log.warning("forecast failed: %s", exc)
        fc = None
    if fc is not None:
        draft["forecast"] = fc
    try:
        answer = explain(draft) or {}
        text, source_kind = answer.get("text", ""), answer.get("source", "fallback")
    except Exception as exc:  # noqa: BLE001 - the AI step must never stop the pipeline
        log.warning("explain failed: %s", exc)
        text, source_kind = "", "fallback"
    if not text or not text.strip() or source_kind not in ("ai", "fallback"):
        text, source_kind = fallback_text(draft), "fallback"
    log.info("explanation (%s): %d chars", source_kind, len(text))
    return Results.model_validate({**draft, "explanation": text,
                                   "explanation_source": source_kind})


def write(results: Results, out: Path) -> None:
    """Write via a temp file, so a crash never leaves half a file."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(results.model_dump(), indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, out)
    log.info("wrote %s", out)


def make_stub_csv(path: Path, seed: int = 42) -> None:
    """Fake data: seasonal wave + slow warming + noise, 2003-01..2024-12."""
    rng = random.Random(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["time,value"]
    i = 0
    for year in range(2003, 2025):
        for month in range(1, 13):
            value = 25 + 9 * math.sin(2 * math.pi * (month - 4) / 12) + 0.012 * i + rng.gauss(0, 0.8)
            lines.append(f"{year}-{month:02d},{value:.3f}")
            i += 1
    path.write_text("\n".join(lines) + "\n")
    log.info("wrote stub CSV %s", path)


def up_to_date(csv: Path, out: Path) -> bool:
    return out.exists() and out.stat().st_mtime >= csv.stat().st_mtime


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    for name in ("csv", "out", "region_id", "region", "variable", "units", "source", "regions_file"):
        p.add_argument("--" + name.replace("_", "-"), default=DEFAULTS[name])
    p.add_argument("--stub", action="store_true", help="write a fake CSV first if none exists")
    p.add_argument("--force", action="store_true", help="rebuild even if output is newer")
    p.add_argument("--all-regions", action="store_true", help="also build every sub-region")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    csv, out = Path(args.csv), Path(args.out)
    if args.stub and not csv.exists():
        make_stub_csv(csv)
    common = {"variable": args.variable, "units": args.units, "source": args.source}
    failed = 0
    jobs = [(csv, out, args.region_id, args.region)]
    if args.all_regions:
        regions_file = Path(args.regions_file)
        if not regions_file.exists():
            log.error("%s not found (need [{\"id\": ..., \"label\": ...}])", regions_file)
            return 1
        for r in json.loads(regions_file.read_text()):
            jobs.append((csv.with_name(f"timeseries_{r['id']}.csv"),
                         out.parent / "regions" / f"{r['id']}.json", r["id"], r["label"]))
    for job_csv, job_out, rid, label in jobs:
        try:
            if not args.force and job_csv.exists() and up_to_date(job_csv, job_out):
                log.info("skip %s (up to date; --force to rebuild)", rid)
                continue
            main_region = job_out == out
            write(build(job_csv, region_id=rid, region=label, forecast_on=main_region, **common),
                  job_out)
        except (SeriesError, ValueError) as exc:
            failed += 1
            log.error("region %s failed: %s", rid, exc)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
