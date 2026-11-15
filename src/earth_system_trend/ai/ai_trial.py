"""A9/A10: try the Gemini path on the committed results, without changing them.

  uv run python scripts/try_ai_explanations.py              # DRY RUN (default): no request
  uv run python scripts/try_ai_explanations.py --ping       # one tiny request, no project data
  uv run python scripts/try_ai_explanations.py --live       # real run: sends each region's facts
  uv run python scripts/try_ai_explanations.py --live --fresh --region phoenix_northwest

- Dry run: prints the exact facts block each region would send and any cached approved reply.
  Needs no key and makes no request.
- Ping: checks GEMINI_API_KEY/GEMINI_MODEL with one tiny request ("ping" -> "OK"). Sends no
  results data. Counts against the daily cap. No retry.
- Live: for each region, ask Gemini (A1/A2, within the A6 cap), run the checks (A3 + region
  name), and print ACCEPTED / REJECTED with the reasons. --fresh ignores cached replies.

Every mode saves a report to data/cache/ai_trial_report.json (git-ignored, never the key).
Results files are never written. Approved replies are cached (A6), so a later pipeline run
writes them without calling Gemini (see docs/ai.md). Only scripts/try_ai_explanations.py loads
.env; this module reads the environment as given.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from earth_system_trend.ai.ai_cache import CappedClient, ExplanationStore
from earth_system_trend.ai.ai_retry import GeminiUnavailableError, RetryPolicy, complete_with_retry
from earth_system_trend.ai.ai_setup import GeminiSetupError, build_client
from earth_system_trend.ai.explain import PROMPT_VERSION, build_messages, explain_detailed

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORT = "data/cache/ai_trial_report.json"
PING_MESSAGES = [
    {"role": "system", "content": "Reply with exactly: OK"},
    {"role": "user", "content": "ping"},
]


def result_files() -> dict[str, Path]:
    files = {"phoenix_study_area": ROOT / "results" / "results.json"}
    for path in sorted((ROOT / "results" / "regions").glob("*.json")):
        files[path.stem] = path
    return files


def main(argv: list[str] | None = None, *, sleep: Callable[[float], None] = time.sleep) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="real run: send each region's facts")
    mode.add_argument("--ping", action="store_true", help="one tiny request, no project data")
    parser.add_argument("--region", action="append", help="region id (repeatable); default all")
    parser.add_argument("--fresh", action="store_true", help="with --live: ignore cached replies")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="where to save the JSON report")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    if args.fresh and not args.live:
        print("--fresh only applies with --live. No request was made.")
        return 2

    if args.live or args.ping:
        for name in ("GEMINI_API_KEY", "GEMINI_MODEL"):
            if not os.getenv(name, "").strip():
                print(f"{name} is not set. Put GEMINI_API_KEY and GEMINI_MODEL in .env (never "
                      f"commit it), then run again. No request was made.")
                return 2
    if args.ping:
        return _ping(sleep)

    files = result_files()
    wanted = args.region or list(files)
    unknown = [r for r in wanted if r not in files]
    if unknown:
        print(f"Unknown region: {', '.join(unknown)}. Choose from: {', '.join(files)}")
        return 2

    rows = [_live_row(rid, files[rid], args.fresh, sleep) if args.live
            else _dry_row(rid, files[rid]) for rid in wanted]
    accepted = sum(r["source"] == "ai" for r in rows)
    report = {
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "live" if args.live else "dry-run",
        "model": os.getenv("GEMINI_MODEL", "").strip(),
        "prompt_version": PROMPT_VERSION,
        "fresh": args.fresh,
        "total": len(rows),
        "accepted": accepted,
        "requests_today": ExplanationStore.from_env().usage_today(),
        "regions": rows,
    }
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.live:
        print(f"\n{accepted} of {len(rows)} accepted. Requests to Gemini today: "
              f"{report['requests_today']}. Report: {path}")
    else:
        print(f"\nDRY RUN: no request was made. Run with --live to send these facts. "
              f"Report: {path}")
    print("Results files were not changed.")
    return 0


def _load(path: Path) -> dict:
    results = json.loads(path.read_text(encoding="utf-8"))
    results.pop("explanation", None)
    results.pop("explanation_source", None)
    return results


def _dry_row(region_id: str, path: Path) -> dict:
    results = _load(path)
    print(f"\n== {region_id}: DRY RUN (no request)")
    print("   facts that --live would send (prompt " + PROMPT_VERSION + "):")
    for line in build_messages(results)[1]["content"].splitlines()[1:]:
        print(f"     {line}")
    outcome = explain_detailed(results, allow_live=False)  # cache lookup only, never a request
    if outcome.reason == "cached":
        print(f"   cached reply (would be used): {outcome.text}")
    return {"region_id": region_id, "source": outcome.source, "reason": outcome.reason,
            "reply": outcome.reply, "problems": [], "chars": len(outcome.reply or "")}


def _live_row(region_id: str, path: Path, fresh: bool, sleep: Callable[[float], None]) -> dict:
    outcome = explain_detailed(_load(path), sleep=sleep, use_cache=not fresh, allow_live=True)
    verdict = {"ai": "ACCEPTED"}.get(outcome.source, "REJECTED" if outcome.problems else "FALLBACK")
    print(f"\n== {region_id}: {verdict} ({outcome.reason})")
    if outcome.reply:
        print(f"   reply: {outcome.reply}")
    for problem in outcome.problems:
        print(f"   - {problem}")
    return {"region_id": region_id, "source": outcome.source, "reason": outcome.reason,
            "reply": outcome.reply, "problems": list(outcome.problems),
            "chars": len(outcome.reply or "")}


def _ping(sleep: Callable[[float], None]) -> int:
    try:
        client = build_client()
    except GeminiSetupError as exc:
        print(f"PING FAILED: {exc}")
        return 1
    if client is None:  # unreachable after the key check, kept for safety
        print("PING FAILED: no GEMINI_API_KEY")
        return 2
    start = time.monotonic()
    try:
        reply = complete_with_retry(CappedClient(client, ExplanationStore.from_env()),
                                    PING_MESSAGES, policy=RetryPolicy(max_attempts=1), sleep=sleep)
    except (GeminiSetupError, GeminiUnavailableError) as exc:
        print(f"PING FAILED: {exc}")
        return 1
    finally:
        client.close()
    ms = int((time.monotonic() - start) * 1000)
    text = (reply.choices[0].message.content or "").strip() if reply.choices else ""
    if not text:
        print(f"PING FAILED: {client.model} answered with no text")
        return 1
    print(f"PING OK: {client.model} answered {text[:20]!r} in {ms} ms. No project data was sent.")
    return 0
