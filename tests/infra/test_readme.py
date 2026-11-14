"""B12: the README has every section a stranger needs, and its links point at real files."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]
README = (ROOT / "README.md").read_text()
REQUIRED = ["What it does", "Quick start", "How it fits together", "Build the results", "API",
            "Settings", "Deploy", "Tests", "Backup run", "Data and credits"]


@pytest.mark.parametrize("heading", REQUIRED)
def test_has_heading(heading):
    assert re.search(rf"^## {re.escape(heading)}$", README, re.MULTILINE)


def test_no_placeholders_left():
    assert "(coming" not in README


def test_local_links_exist():
    for target in re.findall(r"\]\(((?:docs|app|scripts)/[^)#]+)\)", README):
        assert (ROOT / target).exists(), target


def test_settings_table_lists_every_setting():
    from earth_system_trend.config import DEFAULTS

    for name in DEFAULTS:
        if name != "MOCK_PATH":
            assert f"`{name}`" in README, name


def test_commands_point_at_real_modules():
    assert (ROOT / "scripts" / "backup_run.py").exists()
    assert (ROOT / "scripts" / "smoke_test.py").exists()
    assert (ROOT / "app" / "streamlit_app.py").exists()
