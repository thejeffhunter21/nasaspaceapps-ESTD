"""Read the backend/data team's frozen real results without any network access."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from earth_system_trend.contract import Results

REGION_IDS = ("phoenix_study_area", "phoenix_northwest", "phoenix_northeast",
              "phoenix_southwest", "phoenix_southeast")


class SnapshotError(ValueError):
    """Missing, changed or invalid approved snapshot."""


@dataclass(frozen=True)
class OfflineSnapshot:
    freeze_id: str
    data_version: str
    results: dict[str, dict]

    @property
    def regions(self):
        return [{"region_id": rid, "region": payload["region"]}
                for rid, payload in self.results.items()]


def load_snapshot(root: Path | str) -> OfflineSnapshot:
    """Require exact delivered result hashes, contract validity and real provenance."""
    root = Path(root).resolve()
    try:
        manifest = json.loads((root / "docs/evidence/data_freeze_manifest.json").read_text())
        if (manifest["schema_version"] != "1.0"
                or manifest["freeze_id"] != "phoenix-qc-v1.0-handoff-1"
                or manifest["data_version"] != "phoenix-qc-v1.0"):
            raise ValueError("Unapproved freeze")
        entries = manifest["analysis_reference_files"]
        hashes = {entry["path"]: entry for entry in entries}
        if len(hashes) != len(entries):
            raise ValueError("Duplicate reference")
        results = {}
        for rid in REGION_IDS:
            relative = ("results/results.json" if rid == REGION_IDS[0]
                        else f"results/regions/{rid}.json")
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Snapshot escapes bundle")
            data = path.read_bytes()
            entry = hashes[relative]
            if hashlib.sha256(data).hexdigest() != entry["sha256"] or len(data) != entry["bytes"]:
                raise ValueError("Changed snapshot")
            payload = json.loads(data)
            result = Results.model_validate(payload)
            if (result.region_id != rid or "mock" in result.source.casefold()
                    or result.region.casefold() == "example region"
                    or manifest["data_version"] not in result.source):
                raise ValueError("Not the approved real region")
            results[rid] = payload
        return OfflineSnapshot(manifest["freeze_id"], manifest["data_version"], results)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SnapshotError(
            "The approved offline snapshot is missing or changed. Restore the complete bundle and retry."
        ) from exc
