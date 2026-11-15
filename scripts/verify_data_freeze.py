"""Verify the frozen processed-data handoff without network or AI calls.

Run from the repository root:
  python scripts/verify_data_freeze.py
  python scripts/verify_data_freeze.py --include-analysis --out /tmp/data-freeze-check.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def verify_files(root: Path, entries: list[dict]) -> list[dict]:
    results = []
    for item in entries:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Manifest contains a non-relative file path")
        path = root / relative
        try:
            data = path.read_bytes()
        except OSError:
            results.append({"path": item["path"], "pass": False, "reason": "missing_or_unreadable"})
            continue
        actual = hashlib.sha256(data).hexdigest()
        passed = actual == item["sha256"] and len(data) == item["bytes"]
        results.append({"path": item["path"], "pass": passed,
                        "actual_sha256": actual, "actual_bytes": len(data)})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--include-analysis", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    path = args.manifest or root / "docs/evidence/data_freeze_manifest.json"
    manifest = json.loads(path.read_text())
    if manifest["schema_version"] != "1.0" or not manifest["data_files"]:
        raise ValueError("Unsupported or empty freeze manifest")
    paths = [r["path"] for r in manifest["data_files"]]
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate paths in freeze manifest")
    data_checks = verify_files(root, manifest["data_files"])
    analysis_checks = (verify_files(root, manifest["analysis_reference_files"])
                       if args.include_analysis else [])
    data_pass = all(r["pass"] for r in data_checks)
    analysis_pass = all(r["pass"] for r in analysis_checks) if args.include_analysis else None
    report = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "freeze_id": manifest["freeze_id"], "data_version": manifest["data_version"],
        "source_commit": manifest["source_commit"],
        "data_files_pass": data_pass, "analysis_reference_pass": analysis_pass,
        "data_file_checks": data_checks, "analysis_reference_checks": analysis_checks,
        "integration_signoff": "Not determined by file integrity; review the pending list in docs/data_freeze.md",
    }
    passed = data_pass and analysis_pass is not False
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"freeze_id": report["freeze_id"], "data_files": len(data_checks),
                      "analysis_reference_files": len(analysis_checks), "pass": passed,
                      "failures": [r["path"] for r in data_checks + analysis_checks if not r["pass"]]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
