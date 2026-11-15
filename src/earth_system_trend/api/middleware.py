"""J12: protect the API. Each visitor gets a request budget, and no request hangs.

- Rate limit: at most RATE_LIMIT_PER_MINUTE requests per visitor (IP) per minute.
  Over the limit -> 429 with Retry-After. 0 turns the limit off (tests, offline backup).
- Timeout: a request slower than REQUEST_TIMEOUT_S -> 504.
/health, / and /version are never limited, so Render and the uptime check always get through.
Settings are read on every request, so a changed variable applies straight away.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..config import get_settings

EXEMPT = {"/health", "/", "/version"}
# The grid-cell investigation is computed once (seconds on a slow host) and then cached.
SLOW_CACHED = {"/discoveries", "/analysis/investigate", "/map-static"}
WINDOW_S = 60.0


class RateLimiter:
    """Remembers each visitor's request times for the last minute (in memory)."""

    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.calls = 0

    def check(self, key: str, limit: int, now: float) -> float | None:
        """None if allowed; otherwise seconds until the visitor may try again."""
        self.calls += 1
        if self.calls % 1000 == 0:
            self.forget_idle(now)
        times = self.hits[key]
        while times and now - times[0] >= WINDOW_S:
            times.popleft()
        if len(times) >= limit:
            return WINDOW_S - (now - times[0])
        times.append(now)
        return None

    def forget_idle(self, now: float) -> None:
        """Drop visitors with no requests in the last minute, so memory stays small."""
        for key in [k for k, t in self.hits.items() if not t or now - t[-1] >= WINDOW_S]:
            del self.hits[key]


limiter = RateLimiter()


def add_protection(app: FastAPI) -> None:
    @app.middleware("http")
    async def protect(request: Request, call_next):
        settings = get_settings()
        if (request.url.path not in EXEMPT and not request.url.path.startswith("/app/")
                and settings.rate_limit_per_minute > 0):
            visitor = request.client.host if request.client else "unknown"
            wait = limiter.check(visitor, settings.rate_limit_per_minute, time.monotonic())
            if wait is not None:
                retry = max(1, math.ceil(wait))
                return JSONResponse(
                    {"detail": f"Too many requests. Try again in {retry} s."},
                    status_code=429, headers={"Retry-After": str(retry)})
        if request.url.path in SLOW_CACHED:
            return await call_next(request)
        try:
            return await asyncio.wait_for(call_next(request), timeout=settings.request_timeout_s)
        except TimeoutError:
            return JSONResponse({"detail": "The request took too long."}, status_code=504)
