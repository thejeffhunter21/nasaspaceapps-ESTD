"""B1: the project installs, is pinned to Python 3.12, and its lock file is current."""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]


def test_package_imports():
    import earth_system_trend.api.app
    import earth_system_trend.pipeline.run  # noqa: F401


def test_python_pinned_to_312():
    assert (ROOT / ".python-version").read_text().strip() == "3.12"
    assert sys.version_info[:2] == (3, 12)
    assert ">=3.12" in tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
        "requires-python"]


def test_lock_file_matches_pyproject():
    result = subprocess.run(["uv", "lock", "--check"], cwd=ROOT, capture_output=True, text=True,
                            check=False)
    assert result.returncode == 0, result.stderr
