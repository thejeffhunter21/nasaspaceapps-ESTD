"""A9: try the real Gemini path on the committed results, without changing them.

  uv run python scripts/try_ai_explanations.py            # all five regions
  uv run python scripts/try_ai_explanations.py --fresh    # ignore cached replies
  uv run python scripts/try_ai_explanations.py --region phoenix_northwest

For each region: build the facts, ask Gemini (A1/A2, within the A6 daily cap), run the A3
checks, and print the reply with ACCEPTED / REJECTED and the reasons. A report is saved to
data/cache/ai_trial_report.json (git-ignored; never contains the key).

Results files are never written. Approved replies are cached (A6), so a later pipeline run
(see docs/ai.md, "Building the results") writes them without calling Gemini again.
Only scripts/try_ai_explanations.py loads .env; this module reads the environment as given.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from earth_system_trend.ai.ai_cache import ExplanationStore
from earth_system_trend.ai.explain import PROMPT_VERSION, explain_detailed

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORT = "data/cache/ai_trial_report.json"


def result_files() -> dict[str, Path]:
    files = {"phoenix_study_area": ROOT / "results" / "results.json"}
    for path in sorted((ROOT / "results" / "regions").glob("*.json")):
        files[path.stem] = path
    return files


def main(argv: list[str] | None = None, *, sleep: Callable[[float], None] = time.sleep) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", action="append", help="region id (repeatable); default all")
    parser.add_argument("--fresh", action="store_true", help="ignore cached replies")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="where to save the JSON report")
    args = parser.parse_args(argv)

    for name in ("GEMINI_API_KEY", "GEMINI_MODEL"):
        if not os.getenv(name, "").strip():
            print(f"{name} is not set. Put GEMINI_API_KEY and GEMINI_MODEL in .env (never "
                  f"commit it), then run again. No request was made.")
            return 2

    files = result_files()
    wanted = args.region or list(files)
    unknown = [r for r in wanted if r not in files]
    if unknown:
        print(f"Unknown region: {', '.join(unknown)}. Choose from: {', '.join(files)}")
        return 2

    rows = []
    for region_id in wanted:
        results = json.loads(files[region_id].read_text(encoding="utf-8"))
        results.pop("explanation", None)
        results.pop("explanation_source", None)
        outcome = explain_detailed(results, sleep=sleep, use_cache=not args.fresh)
        verdict = {"ai": "ACCEPTED"}.get(outcome.source,
                                         "REJECTED" if outcome.problems else "FALLBACK")
        print(f"\n== {region_id}: {verdict} ({outcome.reason})")
        if outcome.reply:
            print(f"   reply: {outcome.reply}")
        for problem in outcome.problems:
            print(f"   - {problem}")
        rows.append({"region_id": region_id, "source": outcome.source, "reason": outcome.reason,
                     "reply": outcome.reply, "problems": list(outcome.problems),
                     "chars": len(outcome.reply or "")})

    accepted = sum(r["source"] == "ai" for r in rows)
    usage = ExplanationStore.from_env()._data["usage"]
    report = {
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": os.getenv("GEMINI_MODEL", "").strip(),
        "prompt_version": PROMPT_VERSION,
        "fresh": args.fresh,
        "total": len(rows),
        "accepted": accepted,
        "requests_today": usage.get("calls", 0),
        "regions": rows,
    }
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n{accepted} of {len(rows)} accepted. Requests to Gemini today: "
          f"{report['requests_today']}. Report: {path}")
    print("Results files were not changed.")
    return 0
