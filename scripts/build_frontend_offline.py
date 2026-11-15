"""Build a macOS Apple-silicon/Python 3.12 offline bundle while online.

uv run --locked python -m scripts.build_frontend_offline --out /tmp/estd-offline
Requires uv and internet while building; the resulting launcher installs locally.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import tarfile
from pathlib import Path

from app.offline_snapshot import REGION_IDS, load_snapshot

ROOT = Path(__file__).resolve().parents[1]
START = '''#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PIP_DISABLE_PIP_VERSION_CHECK=1
python3.12 - <<'VERIFY'
import hashlib, json
from pathlib import Path
root = Path.cwd()
manifest = json.loads((root / "bundle_manifest.json").read_text())
for name, digest in manifest["files"].items():
    path = (root / name).resolve()
    if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit(f"Bundle integrity check failed: {name}")
print("Bundle integrity: PASS")
VERIFY
if [ ! -x .venv/bin/python ]; then
    python3.12 -m venv .venv
fi
.venv/bin/python -m pip install --no-index --find-links wheelhouse --require-hashes -r requirements-offline.txt
.venv/bin/python -m pip install --no-index --no-deps wheelhouse/earth_system_trend-*.whl
exec .venv/bin/python scripts/run_frontend_offline.py "$@"
'''


def prepare_payload(root: Path, out: Path) -> None:
    """Copy an allowlist, never a checkout's secrets, caches or virtual environment."""
    load_snapshot(root)
    out.mkdir(parents=True, exist_ok=False)
    paths = [*root.joinpath("app").glob("*.py"),
             root / "app/fixtures/results.mock.json", root / ".streamlit/config.toml",
             root / "app/assets/phoenix_freeways.json",
             root / "scripts/run_frontend_offline.py",
             root / "docs/evidence/data_freeze_manifest.json", root / "docs/data_card.md",
             root / "docs/data_quality_report.md", root / "docs/frontend_offline.md"]
    paths += [root / ("results/results.json" if rid == REGION_IDS[0]
                      else f"results/regions/{rid}.json") for rid in REGION_IDS]
    for path in paths:
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Payload file escapes source checkout")
        target = out / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    (out / "START_OFFLINE.command").write_text(START)
    (out / "START_OFFLINE.command").chmod(0o755)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        parser.error("build this bundle on the target Apple-silicon Mac")
    out = args.out.resolve()
    if out.is_relative_to(ROOT):
        parser.error("output must be outside the checkout")
    if out.with_suffix(".tar.gz").exists():
        parser.error("archive already exists; choose a new output name")
    prepare_payload(ROOT, out)
    wheels = out / "wheelhouse"
    wheels.mkdir()
    subprocess.run(["uv", "export", "--locked", "--no-default-groups", "--group", "frontend",
                    "--no-emit-project", "--format", "requirements-txt", "--quiet",
                    "--output-file", str(out / "requirements-offline.txt")], cwd=ROOT, check=True)
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(wheels)], cwd=ROOT, check=True)
    subprocess.run(["uv", "run", "--isolated", "--no-project", "--python", "3.12",
                    "--with", "pip==26.2.1", "python", "-m", "pip", "download",
                    "--only-binary=:all:", "--require-hashes", "--dest", str(wheels),
                    "--requirement", str(out / "requirements-offline.txt")], check=True)
    manifest = {"platform": "macOS arm64", "python": "3.12", "macos_builder": platform.mac_ver()[0],
                "source_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "note": "Includes working-tree frontend changes; file hashes identify exact contents.",
                "files": {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(out.rglob("*")) if p.is_file()}}
    (out / "bundle_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    archive = out.with_suffix(".tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(out, arcname=out.name)
    print(json.dumps({"archive": str(archive), "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                      "wheels": len(list(wheels.glob("*.whl")))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
