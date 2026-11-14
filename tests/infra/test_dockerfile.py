"""B9: the Docker image builds the API safely and the same way every time."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]


def test_dockerignore_excludes_secrets_and_bulk():
    ignored = (ROOT / ".dockerignore").read_text().splitlines()
    for entry in (".env", ".git", "data", "tests"):
        assert entry in ignored


def test_uvicorn_runs_with_proxy_headers():
    assert "--proxy-headers" in (ROOT / "Dockerfile").read_text()


def test_uv_image_pinned_to_exact_version():
    tag = re.search(r"ghcr.io/astral-sh/uv:(\S+)", (ROOT / "Dockerfile").read_text()).group(1)
    assert re.fullmatch(r"\d+\.\d+\.\d+", tag), f"uv image tag {tag!r} is not an exact version"


def test_image_includes_every_runtime_file():
    text = (ROOT / "Dockerfile").read_text()
    for needed in ("COPY src", "COPY results.mock.json", "COPY results"):
        assert needed in text


def test_ci_builds_the_image():
    assert "docker build" in (ROOT / ".github" / "workflows" / "ci.yml").read_text()
