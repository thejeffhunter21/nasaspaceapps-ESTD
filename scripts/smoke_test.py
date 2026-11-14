"""Smoke test: check every endpoint of a running API and print PASS / FAIL.

  uv run python scripts/smoke_test.py                                  # live Render API
  uv run python scripts/smoke_test.py https://estd-api.onrender.com --expect-real
  uv run python scripts/smoke_test.py http://localhost:8000

Exit code 0 only if every check passes. --expect-real also fails on mock or stub data.
"""

from __future__ import annotations

import argparse
import sys

from earth_system_trend.live_check import run_checks, wait_until_up

DEFAULT_URL = "https://estd-api.onrender.com"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(line_buffering=True)  # show progress lines straight away
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("base_url", nargs="?", default=DEFAULT_URL)
    parser.add_argument("--expect-real", action="store_true",
                        help="fail if the API serves mock or stub data")
    parser.add_argument("--wait", type=float, default=120,
                        help="seconds to wait for the server to wake up (default 120)")
    args = parser.parse_args(argv)
    base = args.base_url.rstrip("/")

    print(f"Checking {base} ...")
    if not wait_until_up(base, args.wait):
        print(f"FAIL  /health did not answer within {args.wait:.0f} s")
        return 1
    results = run_checks(base, expect_real=args.expect_real)
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.path:<40} {r.message}")
    failed = sum(not r.ok for r in results)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
