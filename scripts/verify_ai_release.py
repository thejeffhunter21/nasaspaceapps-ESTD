"""A11: AI release check before the offline rehearsal. Never calls Gemini or the network.

Run from the repository root:
  uv run --locked python scripts/verify_ai_release.py
  uv run --locked python scripts/verify_ai_release.py --out docs/evidence/ai/a11_release_check.json

Checks that every committed results file rebuilds exactly with AI off and sockets blocked,
that each explanation belongs to its own result, and that the API, dashboard and backup
launcher cannot reach the AI layer or a model SDK. Results files are never rewritten.
Exit code 0 = PASS, 1 = FAIL.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from earth_system_trend.ai.ai_release import release_check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, help="save the evidence JSON here")
    args = parser.parse_args(argv)

    report = release_check(args.root.resolve())
    for region in report["regions"]:
        mark = "PASS" if region["passed"] else "FAIL"
        print(f"{mark}  {region['region_id']}: {region['explanation_source']} explanation")
        for diff in region["rebuild_differences"]:
            print(f"      differs from the offline rebuild: {diff}")
        for problem in region["explanation_problems"]:
            print(f"      explanation: {problem}")
    isolation = report["runtime_isolation"]
    print(f"{'FAIL' if isolation['violations'] else 'PASS'}  demo runtime isolation: "
          f"{len(isolation['scanned'])} modules scanned")
    for violation in isolation["violations"]:
        print(f"      {violation['module']} imports {violation['import']}")
    print(f"{'PASS' if report['network_attempts'] == 0 else 'FAIL'}  network attempts during "
          f"rebuild: {report['network_attempts']}")
    print(f"{report['status']}  AI release check")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        print(f"saved {args.out}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
