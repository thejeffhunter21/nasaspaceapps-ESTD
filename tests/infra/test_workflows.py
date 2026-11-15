"""B11: deploy only after tests, fail loudly without the hook, uptime every 10 minutes."""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit
WF = Path(__file__).parents[2] / ".github" / "workflows"


def load(name):
    data = yaml.safe_load((WF / name).read_text())
    return data, data.get("on") or data.get(True)  # YAML reads a bare "on" as True


def test_deploy_needs_tests_and_runs_on_main():
    data, triggers = load("deploy.yml")
    assert triggers["push"]["branches"] == ["main"]
    assert data["jobs"]["deploy"]["needs"] == "test"
    assert "pytest" in str(data["jobs"]["test"]["steps"])


def test_deploy_fails_loudly_without_hook():
    text = (WF / "deploy.yml").read_text()
    assert "secrets.RENDER_DEPLOY_HOOK" in text
    assert 'if [ -z "$RENDER_DEPLOY_HOOK" ]' in text and "exit 1" in text
    assert "api.render.com/deploy" not in text  # the hook URL itself is never committed


def test_deploy_waits_for_this_commit_then_smoke_tests():
    text = (WF / "deploy.yml").read_text()
    assert "/version" in text and "GITHUB_SHA" in text
    assert "smoke_test.py" in text and "--expect-real" in text


def test_uptime_every_ten_minutes():
    _, triggers = load("uptime.yml")
    assert triggers["schedule"][0]["cron"] == "*/10 * * * *"
    assert "workflow_dispatch" in triggers
