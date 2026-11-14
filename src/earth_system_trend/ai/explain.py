"""A4: explain(results) -> {"text": ..., "source": "ai" | "fallback"}. Never raises.

Flow: results -> facts (numbers formatted here, by code) -> prompt -> Gemini through A2's
retries -> A3 checks -> AI text if it passes, otherwise fallback_text() built from the numbers.

AI is used only when GEMINI_API_KEY and GEMINI_MODEL are set (A1). Without a key, or on any
failure, the fallback is returned and the reason is logged (never the key or provider body).

A6: text that passed the checks is cached by prompt version + facts and reused (re-checked) on
the next run, even without a key. Every request to Gemini spends one call from the daily cap.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from importlib.resources import files
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

from earth_system_trend.ai.ai_cache import CappedClient, ExplanationStore, cache_key
from earth_system_trend.ai.ai_checks import ALPHA, check_explanation, is_significant
from earth_system_trend.ai.ai_retry import GeminiUnavailableError, RetryPolicy, complete_with_retry
from earth_system_trend.ai.ai_setup import GeminiSetupError, build_client

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
FALLBACK_UNAVAILABLE = "An automatic summary is not available for this result."


def explain(
    results: Any,
    *,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, str]:
    """Return {"text", "source"}; source is "ai" only for a reply that passed the A3 checks."""
    fallback = {"text": fallback_text(results), "source": "fallback"}
    try:
        messages = build_messages(results)
    except Exception:  # noqa: BLE001 - incomplete results: nothing safe to ask the model
        logger.warning("explain: results incomplete; using fallback")
        return fallback

    store = ExplanationStore.from_env()
    key = cache_key(messages, PROMPT_VERSION)
    cached = _cached_text(store, key, results)
    if cached:
        return {"text": cached, "source": "ai"}

    try:
        client = build_client()
    except GeminiSetupError as exc:
        logger.error("explain: Gemini setup error (%s); using fallback", exc)
        return fallback
    if client is None:
        return fallback  # AI disabled (no GEMINI_API_KEY)

    try:
        capped = CappedClient(client, store)
        reply = complete_with_retry(capped, messages, policy=policy, sleep=sleep)
        text = _reply_text(reply)
        if not text:
            logger.warning("explain: Gemini returned no text; using fallback")
            return fallback
        check = check_explanation(text, results)
        if not check.ok:
            logger.warning("explain: AI text rejected by checks: %s", "; ".join(check.problems))
            return fallback
        store.put(key, text, model=client.model, prompt_version=PROMPT_VERSION)
        return {"text": text, "source": "ai"}
    except (GeminiSetupError, GeminiUnavailableError) as exc:
        logger.warning("explain: %s; using fallback", exc)
        return fallback
    except Exception as exc:  # noqa: BLE001 - explain must never raise
        logger.warning("explain: unexpected %s; using fallback", type(exc).__name__)
        return fallback
    finally:
        client.close()


def _cached_text(store: ExplanationStore, key: str, results: Any) -> str | None:
    """Cached AI text for these exact facts, if it still passes today's checks."""
    try:
        text = store.get(key)
        if text is None:
            return None
        check = check_explanation(text, results)
        if check.ok:
            return text
        logger.warning("explain: cached AI text no longer passes checks (%s); asking again",
                       "; ".join(check.problems))
        store.drop(key)
    except Exception as exc:  # noqa: BLE001 - the cache must never break explain
        logger.warning("explain: cache lookup failed (%s)", type(exc).__name__)
    return None


def build_messages(results: Mapping[str, Any]) -> list[ChatCompletionMessageParam]:
    """System prompt (versioned file) + a facts block whose numbers code has already formatted."""
    trend = results["trend"]
    slope, p, tau = float(trend["slope"]), float(trend["p"]), float(trend["tau"])
    units = str(results["units"])
    series = list(results["series"])
    valid = sum(point.get("value") is not None for point in series)
    facts = "\n".join([
        f"Region: {results['region']}",
        f"Variable: {results['variable']} (monthly, satellite)",
        f"Period: {results['period']['start']} to {results['period']['end']}",
        f"Valid months: {valid} of {len(series)}",
        f"Direction: {trend['trend']}",
        f"Slope: {_num(slope)} {units}/month ({_num(slope * 12)} {units}/year)",
        (f"Statistically significant: {'yes' if is_significant(p) else 'no'} "
         f"({p_text(p)}; threshold {ALPHA})"),
        f"Kendall's tau: {_num(tau)}",
        f"Method: {results['method']}",
        f"Source: {results['source']}",
    ])
    return [
        {"role": "system", "content": _prompt()},
        {"role": "user", "content": f"Facts:\n{facts}"},
    ]


def fallback_text(results: Any) -> str:
    """Plain summary built only from the numbers. Passes A3 by construction. Never raises."""
    try:
        trend = results["trend"]
        slope, p = float(trend["slope"]), float(trend["p"])
        direction = str(trend["trend"])
        units = str(results["units"])
        start, end = results["period"]["start"], results["period"]["end"]
        series = list(results["series"])
        missing = sum(point.get("value") is None for point in series)
        subject = f"{str(results['variable']).lower()} in {results['region']}"

        if direction in ("increasing", "decreasing"):
            verb = "rose" if direction == "increasing" else "fell"
            text = (f"From {start} to {end}, {subject} {verb} by about {_num(abs(slope))} "
                    f"{units} per month ({_num(abs(slope) * 12)} {units} per year). ")
            text += ("This trend is statistically significant" if is_significant(p)
                     else "This trend is not statistically significant")
            text += f" ({p_text(p)})."
        else:
            text = (f"From {start} to {end}, the change in {subject} is not statistically "
                    f"significant ({p_text(p)}). This means there is not enough evidence of a "
                    f"trend; it is not proof of no change.")
        if missing:
            text += (f" {missing} of {len(series)} months are missing and were left as gaps, "
                     f"not filled in.")
        return text
    except Exception:  # noqa: BLE001 - must never raise
        return FALLBACK_UNAVAILABLE


def p_text(p: float) -> str:
    """'p < 0.001' for tiny p; otherwise 3 significant figures, more if rounding would
    cross the 0.05 threshold (e.g. 0.0499996 must not read as 0.05)."""
    if p < 0.001:
        return "p < 0.001"
    shown = _num(p)
    if is_significant(float(shown)) != is_significant(p):
        shown = f"{p:.6g}"
    return f"p = {shown}"


def _num(x: float) -> str:
    return f"{x:.3g}"


def _prompt() -> str:
    path = files("earth_system_trend.ai") / "prompts" / f"explain_{PROMPT_VERSION}.txt"
    return path.read_text(encoding="utf-8").strip()


def _reply_text(reply: Any) -> str:
    if not reply.choices:
        return ""
    content = reply.choices[0].message.content
    return " ".join(content.split()) if content else ""
