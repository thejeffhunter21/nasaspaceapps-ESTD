"""A1: Gemini through the existing OpenAI SDK, with no startup API call.

Call build_client() after the application's environment has been loaded.
None means AI is disabled: the caller should use its deterministic fallback.
This low-level adapter leaves retries and explanation validation to later units.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from openai import NotFoundError, OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class GeminiSetupError(ValueError):
    """Gemini configuration needs correction; retrying will not fix it."""


@dataclass
class GeminiClient:
    """One configured SDK client; no credentials in its representation."""

    _client: OpenAI = field(repr=False)
    model: str

    def complete(self, messages: list[ChatCompletionMessageParam]) -> ChatCompletion:
        """Make one request; translate 404 without exposing the provider body."""
        try:
            return self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                reasoning_effort="low",
            )
        except NotFoundError:
            raise GeminiSetupError(
                "Gemini returned HTTP 404: check GEMINI_MODEL and the Gemini API endpoint."
            ) from None

    def close(self) -> None:
        """Release the underlying SDK HTTP connection pool."""
        self._client.close()


def build_client() -> GeminiClient | None:
    """Read GEMINI_API_KEY and GEMINI_MODEL; never borrow OPENAI_API_KEY.

    A missing key disables AI. With a key present, an explicit model is required
    so deployment controls the model rather than relying on a stale default.
    No model-list or completion probe runs here.
    """
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    model = os.getenv("GEMINI_MODEL", "").strip()
    if not model:
        raise GeminiSetupError("Set GEMINI_MODEL to a compatible Gemini Flash model.")
    return GeminiClient(
        _client=OpenAI(
            api_key=key,
            base_url=GEMINI_BASE_URL,
            max_retries=0,  # A2 owns retries; 404 must always fail immediately.
            timeout=15.0,
        ),
        model=model,
    )
