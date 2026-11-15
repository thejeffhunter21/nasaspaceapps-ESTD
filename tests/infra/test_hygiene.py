"""B2: secrets and junk never reach GitHub."""

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                         check=False)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    return out.stdout.splitlines()


def test_gitignore_lists_secrets_and_raw_data():
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    for entry in (".env", ".venv/", "data/raw/"):
        assert entry in ignored


def test_no_junk_or_env_files_tracked():
    files = tracked_files()
    assert not [f for f in files if f.endswith(".DS_Store") or Path(f).name == ".env"]


def test_no_key_shaped_strings_tracked():
    pattern = re.compile(r"(sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35})")
    hits = []
    for name in tracked_files():
        path = ROOT / name
        text_file = path.suffix in {".json", ".py", ".md", ".txt", ".yml", ".yaml", ".toml",
                                    ".example"}
        if text_file and pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            hits.append(name)
    assert not hits, f"possible API key in: {hits}"
