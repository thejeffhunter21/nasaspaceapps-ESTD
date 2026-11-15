"""Start the approved snapshot directly, without a local or remote API."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.offline_snapshot import SnapshotError, load_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--check", action="store_true", help="verify files and exit")
    args = parser.parse_args()
    try:
        snapshot = load_snapshot(ROOT)
    except SnapshotError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    print(json.dumps({"freeze_id": snapshot.freeze_id, "regions": list(snapshot.results),
                      "mode": "Offline snapshot"}), flush=True)
    if args.check:
        return 0
    env = {**os.environ, "API_URL": "", "OFFLINE_SNAPSHOT_DIR": str(ROOT)}
    os.chdir(ROOT)
    os.execve(sys.executable, [sys.executable, "-m", "streamlit", "run",
                              str(ROOT / "app/streamlit_app.py"),
                              "--server.address", "127.0.0.1", "--server.port", str(args.port),
                              "--server.headless", "true", "--browser.gatherUsageStats", "false"], env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
