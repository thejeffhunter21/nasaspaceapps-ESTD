"""FE-14: portable payload excludes secrets and retains approved result bytes."""
import hashlib
from pathlib import Path

import pytest

from scripts.build_frontend_offline import prepare_payload

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def test_payload_preserves_approved_files_and_excludes_secrets(tmp_path):
    out = tmp_path / "payload"
    prepare_payload(ROOT, out)
    assert (out / "app/streamlit_app.py").exists()
    for path in (ROOT / "results").rglob("*.json"):
        other = out / path.relative_to(ROOT)
        assert hashlib.sha256(other.read_bytes()).digest() == hashlib.sha256(path.read_bytes()).digest()
    assert not (out / ".env").exists()
    assert not (out / ".git").exists()
    assert not (out / ".venv").exists()
    assert "--no-index" in (out / "START_OFFLINE.command").read_text()
    assert "--require-hashes" in (out / "START_OFFLINE.command").read_text()
    with pytest.raises(FileExistsError):
        prepare_payload(ROOT, out)
