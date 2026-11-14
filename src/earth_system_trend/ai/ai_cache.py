"""A6: explanation cache and daily Gemini call cap, kept in one local JSON file.

File: EXPLAIN_CACHE_PATH (default data/cache/explanations.json, git-ignored):

    {"explanations": {<key>: {"text", "model", "prompt_version", "created"}},
     "usage": {"date": "YYYY-MM-DD" (UTC), "calls": n}}

- Cache: key = SHA-256 of the prompt version + the exact messages sent. Only text that passed
  the A3 checks is stored; explain() re-checks it on reuse. Works without an API key, so an
  offline re-run reuses approved text. To refresh, delete the file or bump the prompt version.
- Cap: AI_DAILY_CALL_CAP (default 50) limits HTTP requests to Gemini per UTC day, retries
  included. A request over the cap is not sent. 0 turns AI off.
- Never raises: an unreadable or unwritable file is logged and treated as empty.
  The file never holds the API key or provider error text.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

from earth_system_trend.ai.ai_retry import GeminiUnavailableError
from earth_system_trend.ai.ai_setup import GeminiClient

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = "data/cache/explanations.json"
DEFAULT_DAILY_CAP = 50


def cache_key(messages: list[ChatCompletionMessageParam], prompt_version: str) -> str:
    payload = json.dumps({"prompt_version": prompt_version, "messages": messages},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


class ExplanationStore:
    """Cache entries and today's call count. All failures are logged, never raised."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._data = self._load()

    @classmethod
    def from_env(cls) -> ExplanationStore:
        return cls(os.getenv("EXPLAIN_CACHE_PATH", "").strip() or DEFAULT_CACHE_PATH)

    @staticmethod
    def daily_cap() -> int:
        raw = os.getenv("AI_DAILY_CALL_CAP", "").strip()
        try:
            cap = int(raw) if raw else DEFAULT_DAILY_CAP
        except ValueError:
            return DEFAULT_DAILY_CAP
        return cap if cap >= 0 else DEFAULT_DAILY_CAP

    # --- cache ----------------------------------------------------------------------------

    def get(self, key: str) -> str | None:
        entry = self._data["explanations"].get(key)
        text = entry.get("text") if isinstance(entry, dict) else None
        return text if isinstance(text, str) and text.strip() else None

    def put(self, key: str, text: str, *, model: str, prompt_version: str) -> None:
        self._data["explanations"][key] = {
            "text": text,
            "model": model,
            "prompt_version": prompt_version,
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self._save()

    def drop(self, key: str) -> None:
        if self._data["explanations"].pop(key, None) is not None:
            self._save()

    # --- daily cap ------------------------------------------------------------------------

    def spend(self) -> bool:
        """Count one request against today's cap. False (nothing counted) if the cap is reached."""
        today = _today()
        usage = self._data["usage"]
        if usage.get("date") != today or not isinstance(usage.get("calls"), int):
            usage.clear()
            usage.update({"date": today, "calls": 0})
        if usage["calls"] >= self.daily_cap():
            return False
        usage["calls"] += 1
        self._save()  # persisted before the request, so a crash still counts it
        return True

    # --- file -----------------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        empty: dict[str, Any] = {"explanations": {}, "usage": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return empty
        except (OSError, ValueError) as exc:
            logger.warning("explanation cache unreadable (%s); starting empty", type(exc).__name__)
            return empty
        if not (isinstance(data, dict) and isinstance(data.get("explanations"), dict)
                and isinstance(data.get("usage", {}), dict)):
            logger.warning("explanation cache has the wrong shape; starting empty")
            return empty
        return {"explanations": data["explanations"], "usage": data.get("usage", {})}

    def _save(self) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(self._data, indent=1, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)  # atomic: never leaves a half-written cache
        except OSError as exc:
            logger.warning("explanation cache not saved (%s)", type(exc).__name__)


class CappedClient:
    """Wraps A1's client: every request first spends one call from the daily cap."""

    def __init__(self, client: GeminiClient, store: ExplanationStore) -> None:
        self._client = client
        self._store = store

    @property
    def model(self) -> str:
        return self._client.model

    def complete(self, messages: list[ChatCompletionMessageParam]) -> ChatCompletion:
        if not self._store.spend():
            raise GeminiUnavailableError(
                f"AI daily call cap ({self._store.daily_cap()}) reached; request not sent",
                attempts=0,
                status=None,
            )
        return self._client.complete(messages)

    def close(self) -> None:
        self._client.close()
