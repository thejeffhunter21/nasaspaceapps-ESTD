"""A2: retry policy around GeminiClient.complete().

A1 makes exactly one request (SDK retries are off). A2 decides what to do when it fails:

- Transient failures (408, 429, 5xx, timeouts, dropped connections) are retried with
  capped exponential backoff, at most `max_attempts` requests in total.
- A 429 whose Retry-After is longer than `max_delay_s` (e.g. daily quota used up) stops
  at once, so the caller falls back instead of hanging.
- Setup problems (401/403 bad key, 404 bad model) raise GeminiSetupError without retry.
- Anything else (e.g. 400/422, our request is wrong) raises GeminiUnavailableError
  without retry.

Errors and logs carry only the HTTP status, never the provider's response body.
The caller (the explanation layer) catches both error types and uses its fallback text.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from openai import APIConnectionError, APIStatusError
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

from earth_system_trend.ai.ai_setup import GeminiClient, GeminiSetupError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
AUTH_STATUS = frozenset({401, 403})


class GeminiUnavailableError(RuntimeError):
    """Gemini gave no usable reply. Use the deterministic fallback explanation."""

    def __init__(self, message: str, *, attempts: int, status: int | None) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.status = status  # last HTTP status, or None for timeout / no connection


@dataclass(frozen=True)
class RetryPolicy:
    """Worst case with defaults: 3 requests x 15 s timeout + 1 s + 2 s of waiting."""

    max_attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 8.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_s < 0 or self.max_delay_s < 0:
            raise ValueError("delays must not be negative")

    def backoff(self, attempt: int) -> float:
        """Wait after failed attempt number `attempt` (1-based): base, 2x base, ... capped."""
        return min(self.base_delay_s * 2 ** (attempt - 1), self.max_delay_s)


DEFAULT_POLICY = RetryPolicy()


def complete_with_retry(
    client: GeminiClient,
    messages: list[ChatCompletionMessageParam],
    *,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ChatCompletion:
    """Call client.complete() under `policy`.

    Returns the completion, or raises GeminiSetupError (fix configuration) or
    GeminiUnavailableError (gave up; use the fallback). `policy` defaults to DEFAULT_POLICY.
    """
    policy = policy or DEFAULT_POLICY
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return client.complete(messages)
        except GeminiSetupError:
            raise  # A1's 404: retrying cannot fix a wrong model or endpoint
        except APIStatusError as exc:
            status = exc.status_code
            if status in AUTH_STATUS:
                raise GeminiSetupError(
                    f"Gemini rejected the request with HTTP {status}: check GEMINI_API_KEY."
                ) from None
            if status not in RETRYABLE_STATUS:
                raise GeminiUnavailableError(
                    f"Gemini returned HTTP {status}; not retried.", attempts=attempt, status=status
                ) from None
            wait = _retry_after(exc)
            if wait is not None and wait > policy.max_delay_s:
                raise GeminiUnavailableError(
                    f"Gemini rate limit: asked to wait {wait:g}s, more than the "
                    f"{policy.max_delay_s:g}s limit; not retried.",
                    attempts=attempt,
                    status=status,
                ) from None
            reason = f"HTTP {status}"
        except APIConnectionError as exc:  # includes APITimeoutError
            status, wait = None, None
            reason = type(exc).__name__

        if attempt == policy.max_attempts:
            raise GeminiUnavailableError(
                f"Gemini unavailable after {attempt} attempts (last: {reason}).",
                attempts=attempt,
                status=status,
            ) from None
        delay = wait if wait is not None else policy.backoff(attempt)
        logger.warning(
            "Gemini attempt %d/%d failed (%s); retrying in %.1fs",
            attempt, policy.max_attempts, reason, delay,
        )
        sleep(delay)

    raise AssertionError("unreachable")  # pragma: no cover


def _retry_after(exc: APIStatusError) -> float | None:
    """Seconds from a numeric Retry-After header; None if absent or not a number."""
    value = exc.response.headers.get("retry-after")
    try:
        seconds = float(value) if value is not None else None
    except ValueError:
        return None  # HTTP-date form: use normal backoff
    return seconds if seconds is not None and seconds >= 0 else None
