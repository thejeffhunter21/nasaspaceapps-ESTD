"""A11: AI release check for the frozen results and the offline demo. Never calls Gemini.

Three things the sprint plan needs from the AI layer after feature freeze (G4) and before the
no-Wi-Fi rehearsal (G5), none of which the trend or story reviewers already prove:

1. Rebuild: every committed results file is exactly what the pipeline produces from the
   qc-v1 CSVs with AI switched off and the network blocked. Approved AI text cannot be
   regenerated offline, so for an "ai" explanation only its two explanation fields are exempt.
2. Provenance: each explanation belongs to the result it sits in. A fallback must equal
   fallback_text() of that result's own numbers; AI text must pass the A3 checks and name the
   selected region (A10).
3. Isolation: the API, dashboard and backup launcher cannot reach model clients or SDKs.
   Only the deterministic trend and validation modules may run in the guided demo.

scripts/verify_ai_release.py runs release_check() and saves the evidence file.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import os
import socket
import subprocess
import tempfile
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from earth_system_trend.ai.explain import PROMPT_VERSION, _ai_problems, fallback_text

MAIN_REGION = "phoenix_study_area"
SOURCES = ("ai", "fallback")
# Explanation fields that cannot be reproduced offline when the committed text came from Gemini.
_AI_ONLY_FIELDS = ("explanation", "explanation_source")
# Runtime entry points of the demo (live and offline): API, dashboard, backup launcher.
RUNTIME_ENTRIES = ("src/earth_system_trend/api/app.py", "app/streamlit_app.py",
                   "scripts/backup_run.py")
_PACKAGE = "earth_system_trend"
_DETERMINISTIC = (f"{_PACKAGE}.ai.trend", f"{_PACKAGE}.ai.ai_checks")
_FORBIDDEN = (f"{_PACKAGE}.ai", "openai", "google.genai", "google.generativeai")
AI_OFF = {"GEMINI_API_KEY": "", "GEMINI_LIVE": "0", "AI_DAILY_CALL_CAP": "0"}


# --- committed results ------------------------------------------------------------------

def result_paths(root: Path) -> dict[str, Path]:
    """region_id -> committed results file: the main area plus every region in regions.json."""
    root = Path(root)
    paths = {MAIN_REGION: root / "results" / "results.json"}
    regions = json.loads((root / "data" / "processed" / "regions.json").read_text("utf-8"))
    for region in regions:
        paths[region["id"]] = root / "results" / "regions" / f"{region['id']}.json"
    return paths


def load_committed(root: Path) -> dict[str, dict[str, Any]]:
    return {rid: json.loads(path.read_text("utf-8")) for rid, path in result_paths(root).items()}


def result_hashes(root: Path) -> dict[str, str]:
    """Repo-relative path -> SHA-256 of each committed results file, with LF line endings
    (as stored in git), so a Windows checkout with CRLF gets the same hash as CI."""
    root = Path(root)
    return {path.relative_to(root).as_posix():
            hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for path in result_paths(root).values()}


# --- AI off, network blocked ------------------------------------------------------------

@contextmanager
def ai_off() -> Iterator[None]:
    """No key, live calls off, daily cap 0 and an empty cache; the environment is restored."""
    names = (*AI_OFF, "EXPLAIN_CACHE_PATH")
    saved = {name: os.environ.get(name) for name in names}
    with tempfile.TemporaryDirectory() as tmp:
        os.environ.update(AI_OFF)
        os.environ["EXPLAIN_CACHE_PATH"] = str(Path(tmp) / "explanations.json")
        try:
            yield
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


@contextmanager
def no_network() -> Iterator[list[str]]:
    """Make every outgoing socket connection fail; yields the list of attempted addresses."""
    attempts: list[str] = []
    originals = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection)

    def refuse(address: Any) -> OSError:
        attempts.append(repr(address))
        return OSError(f"network blocked by the AI release check: {address!r}")

    def connect(self: socket.socket, address: Any) -> None:
        raise refuse(address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        raise refuse(address)

    def create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        raise refuse(address)

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    socket.create_connection = create_connection  # type: ignore[assignment]
    try:
        yield attempts
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection = originals


# --- 1. rebuild -------------------------------------------------------------------------

@dataclass(frozen=True)
class Rebuild:
    results: dict[str, dict[str, Any]]  # region_id -> results as JSON-ready dict
    network_attempts: int


def rebuild_offline(root: Path) -> Rebuild:
    """Build every region from the processed CSVs as the pipeline does, AI off, no network."""
    from earth_system_trend.pipeline import run as pipeline  # imports this package's explain

    root = Path(root)
    processed = root / "data" / "processed"
    labels = {MAIN_REGION: pipeline.DEFAULTS["region"]}
    labels |= {r["id"]: r["label"]
               for r in json.loads((processed / "regions.json").read_text("utf-8"))}
    built: dict[str, dict[str, Any]] = {}
    with ai_off(), no_network() as attempts:
        for region_id, label in labels.items():
            main = region_id == MAIN_REGION
            csv = processed / ("timeseries.csv" if main else f"timeseries_{region_id}.csv")
            results = pipeline.build(
                csv, region_id=region_id, region=label, variable=pipeline.DEFAULTS["variable"],
                units=pipeline.DEFAULTS["units"], source=pipeline.DEFAULTS["source"],
                forecast_on=main)
            built[region_id] = json.loads(json.dumps(results.model_dump(), ensure_ascii=False))
    return Rebuild(built, len(attempts))


def rebuild_differences(committed: dict[str, Any], rebuilt: dict[str, Any]) -> list[str]:
    """Top-level fields where the committed file differs from the offline rebuild."""
    skip = _AI_ONLY_FIELDS if committed.get("explanation_source") == "ai" else ()
    keys = sorted((set(committed) | set(rebuilt)) - set(skip))
    differences = []
    for key in keys:
        left, right = committed.get(key), rebuilt.get(key)
        if key == "trend" and isinstance(left, dict) and isinstance(right, dict):
            # scipy/platform differences can shift tiny p-values by one floating-point bit.
            # No absolute tolerance: rounding a tiny p-value to zero must still fail.
            left, right = dict(left), dict(right)
            if (isinstance(left.get("p"), (int, float))
                    and isinstance(right.get("p"), (int, float))
                    and math.isclose(left["p"], right["p"], rel_tol=1e-14, abs_tol=0.0)):
                left["p"] = right["p"]
        if left != right:
            differences.append(key)
    return differences


# --- 2. provenance ----------------------------------------------------------------------

def explanation_problems(result: dict[str, Any]) -> list[str]:
    """Why this explanation does not belong to this result ([] if it does)."""
    source, text = result.get("explanation_source"), str(result.get("explanation", ""))
    if source not in SOURCES:
        return [f"explanation_source must be one of {SOURCES}, not {source!r}"]
    problems: list[str] = []
    if source == "fallback" and text != fallback_text(copy.deepcopy(result)):
        problems.append("explanation does not match the fallback text built from this "
                        "result's own numbers")
    problems += [p for p in _ai_problems(text, result) if p not in problems]
    return problems


# --- 3. isolation -----------------------------------------------------------------------

def runtime_isolation(root: Path, entries: tuple[str, ...] = RUNTIME_ENTRIES) -> dict[str, Any]:
    """Follow imports from the demo's entry points; report any that reach AI code or a model SDK.

    Follows the package (absolute and relative imports, parent __init__ files) and the
    dashboard's sibling modules; third-party packages are only matched by name.
    """
    root = Path(root)
    src = root / "src"
    todo = [root / e for e in entries if (root / e).exists()]
    seen: set[Path] = set()
    violations: list[dict[str, str]] = []

    def rel(path: Path) -> str:
        return path.relative_to(root).as_posix()

    def module_file(dotted: str) -> list[Path]:
        """The file for a package module plus its parent packages' __init__ files."""
        parts = dotted.split(".")
        found = [src.joinpath(*parts[:i], "__init__.py") for i in range(1, len(parts))]
        for candidate in (src.joinpath(*parts).with_suffix(".py"),
                          src.joinpath(*parts, "__init__.py")):
            if candidate.exists():
                found.append(candidate)
                break
        return [f for f in found if f.exists()]

    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    try:
                        package = path.relative_to(src).with_suffix("").parts[:-1]
                    except ValueError:
                        continue  # relative import outside the package: nothing to follow
                    if path.name == "__init__.py":
                        package = path.relative_to(src).parts[:-1]
                    package = package[:len(package) - node.level + 1]
                    base = ".".join([*package, *([base] if base else [])])
                names = [base] + [f"{base}.{alias.name}" for alias in node.names]
            else:
                continue
            for name in names:
                if not name:
                    continue
                deterministic = any(name == f or name.startswith(f + ".")
                                    for f in _DETERMINISTIC)
                if (not deterministic
                        and any(name == f or name.startswith(f + ".") for f in _FORBIDDEN)):
                    violations.append({"module": rel(path), "import": name})
                elif name == _PACKAGE or name.startswith(_PACKAGE + "."):
                    todo += [f for f in module_file(name) if f not in seen]
                else:
                    sibling = path.with_name(name.split(".")[0] + ".py")
                    if sibling.exists() and sibling != path:
                        todo.append(sibling)
    unique = {(v["module"], v["import"]): v for v in violations}
    return {"entries": [e for e in entries if (root / e).exists()],
            "scanned": sorted(rel(p) for p in seen),
            "violations": [unique[k] for k in sorted(unique)]}


# --- all of it --------------------------------------------------------------------------

def release_check(root: Path) -> dict[str, Any]:
    """Run 1-3 on the committed results; status is PASS only if everything passes."""
    root = Path(root)
    committed = load_committed(root)
    rebuild = rebuild_offline(root)
    paths = result_paths(root)
    regions = []
    for region_id, result in committed.items():
        diffs = (rebuild_differences(result, rebuild.results[region_id])
                 if region_id in rebuild.results else ["not rebuilt"])
        problems = explanation_problems(result)
        regions.append({
            "region_id": region_id, "region": result.get("region"),
            "file": paths[region_id].relative_to(root).as_posix(),
            "explanation_source": result.get("explanation_source"),
            "explanation": result.get("explanation"),
            "method": result.get("method"), "trend": result.get("trend"),
            "rebuild_differences": diffs, "explanation_problems": problems,
            "passed": not diffs and not problems})
    isolation = runtime_isolation(root)
    passed = (all(r["passed"] for r in regions) and not isolation["violations"]
              and rebuild.network_attempts == 0)
    return {
        "check": "A11 AI release check",
        "checked_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "checked_checkout_commit": _git_head(root),
        "status": "PASS" if passed else "FAIL",
        "ai_mode": "off: no GEMINI_API_KEY, GEMINI_LIVE=0, AI_DAILY_CALL_CAP=0, empty cache",
        "network_attempts": rebuild.network_attempts,
        "prompt_version": PROMPT_VERSION,
        "explanation_sources": dict(Counter(r["explanation_source"] for r in regions)),
        "result_sha256": result_hashes(root),
        "regions": regions,
        "runtime_isolation": isolation,
    }


def _git_head(root: Path) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                              text=True, check=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
