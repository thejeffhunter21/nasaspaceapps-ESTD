"""J14: the offline backup checks it is serving real data before the demo starts."""

import pytest

from earth_system_trend.live_check import check_real_data
from tests.stub_server import healthy_api, serve

pytestmark = pytest.mark.unit


def test_real_region_passes():
    with serve(healthy_api()) as url:
        result = check_real_data(url)
    assert result.ok and "Phoenix study area" in result.message


def test_example_region_fails():
    with serve(healthy_api(region="Example Region")) as url:
        result = check_real_data(url)
    assert not result.ok and "MOCK" in result.message


def test_stub_method_fails():
    with serve(healthy_api(method="stub")) as url:
        assert not check_real_data(url).ok


def test_health_down_fails():
    routes = {**healthy_api(), "/health": (503, {"detail": "down"})}
    with serve(routes) as url:
        result = check_real_data(url)
    assert not result.ok and "/health" in result.message


def test_nothing_listening_fails():
    assert not check_real_data("http://127.0.0.1:9").ok


def test_backup_script_refuses_without_results(tmp_path, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    script = Path(__file__).parents[2] / "scripts" / "backup_run.py"
    spec = importlib.util.spec_from_file_location("backup_run", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    assert module.main(["--no-dashboard"]) == 1
    assert "results/results.json is missing" in capsys.readouterr().out
