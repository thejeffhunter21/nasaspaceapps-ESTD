"""B8: the smoke test prints PASS / FAIL per endpoint and exits 0 only if all pass."""

import importlib.util
from pathlib import Path

import pytest

from tests.stub_server import healthy_api, serve

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_checks_pass(capsys):
    with serve(healthy_api()) as url:
        assert load_script("smoke_test").main([url, "--expect-real", "--wait", "5"]) == 0
    out = capsys.readouterr().out
    assert "PASS  /health" in out and "FAIL" not in out


def test_health_500_fails(capsys):
    routes = {**healthy_api(), "/health": (500, {"detail": "boom"})}
    with serve(routes) as url:
        assert load_script("smoke_test").main([url, "--wait", "3"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_expect_real_fails_on_mock(capsys):
    with serve(healthy_api(region="Example Region", source="Mock data")) as url:
        assert load_script("smoke_test").main([url, "--expect-real", "--wait", "5"]) == 1
    assert "MOCK" in capsys.readouterr().out


def test_broken_endpoint_named_in_output(capsys):
    routes = {**healthy_api(), "/trend": (500, {"detail": "broken"})}
    with serve(routes) as url:
        assert load_script("smoke_test").main([url, "--wait", "5"]) == 1
    assert "FAIL  /trend " in capsys.readouterr().out
