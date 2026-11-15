"""Offline backup: run the whole demo on this laptop, with no wifi and no Render.

  uv run python scripts/backup_run.py                 # API + dashboard, opens the browser
  uv run python scripts/backup_run.py --no-dashboard  # API only, then check it

It starts the API from the committed results/ files (USE_MOCK=false), checks that
it serves real data, then starts the dashboard pointed at it. No NASA, OpenAI or
Gemini calls are made. Press Ctrl+C to stop everything.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import requests

from earth_system_trend.live_check import check_real_data, run_checks, wait_until_up

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(line_buffering=True)  # show progress lines straight away
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--port", type=int, default=8000, help="API port (default 8000)")
    parser.add_argument("--dashboard-port", type=int, default=8501)
    parser.add_argument("--no-dashboard", action="store_true", help="start only the API")
    args = parser.parse_args(argv)

    if not (ROOT / "results" / "results.json").exists():
        print("FAIL  results/results.json is missing. Build it first:\n"
              "      uv run python -m earth_system_trend.pipeline.run --all-regions")
        return 1

    base = f"http://127.0.0.1:{args.port}"
    env = {**os.environ, "USE_MOCK": "false", "CORS_ORIGINS": "*",
           "RATE_LIMIT_PER_MINUTE": "0"}
    procs: list[subprocess.Popen] = []
    try:
        print(f"Starting the API on {base} (offline, real data) ...")
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "earth_system_trend.api.app:app",
             "--host", "127.0.0.1", "--port", str(args.port)], cwd=ROOT, env=env))
        if not wait_until_up(base, 60):
            print("FAIL  the API did not start (is the port already in use?)")
            return 1
        real = check_real_data(base)
        print(f"{'PASS' if real.ok else 'FAIL'}  real data: {real.message}")
        if not real.ok:
            return 1

        if args.no_dashboard:
            failed = [r for r in run_checks(base) if not r.ok]
            for r in failed:
                print(f"FAIL  {r.path}: {r.message}")
            print("All endpoints OK." if not failed else f"{len(failed)} checks failed.")
            if failed:
                return 1
            print("API running. Press Ctrl+C to stop.")
            procs[0].wait()
            return 0

        print(f"Starting the dashboard on http://localhost:{args.dashboard_port} ...")
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app/streamlit_app.py",
             "--server.port", str(args.dashboard_port), "--server.headless", "true",
             "--browser.gatherUsageStats", "false"],
            cwd=ROOT, env={**env, "API_URL": base}))
        dashboard = f"http://localhost:{args.dashboard_port}"
        if wait_for(dashboard + "/_stcore/health", 60):
            webbrowser.open(dashboard)
            print(f"Demo running at {dashboard}. Press Ctrl+C to stop.")
        else:
            print(f"The dashboard is slow to start; open {dashboard} yourself.")
        procs[-1].wait()
        return 0
    except KeyboardInterrupt:
        print("\nStopping ...")
        return 0
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()


def wait_for(url: str, timeout_s: float) -> bool:
    """True once url answers 200 (used for the dashboard's health check)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if requests.get(url, timeout=5).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


if __name__ == "__main__":
    sys.exit(main())
