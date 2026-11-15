"""J5, J9: the FastAPI app. Run: uv run uvicorn earth_system_trend.api.app:app --reload"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import get_settings
from .middleware import add_protection
from .routes import router

app = FastAPI(title="Earth System Trend Detective API", version="1.0.0")

# Only our dashboard may call the API from a browser, and only to read.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)
add_protection(app)  # J12: rate limit + timeout


@app.get("/")
def home() -> dict:
    """What a person sees when they open the bare URL: what this is and where to go."""
    return {
        "name": "Earth System Trend Detective API",
        "status": "ok",
        "try": ["/regions", "/series?region=phoenix_study_area",
                "/trend?region=phoenix_study_area", "/results", "/demo", "/health"],
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict:
    """Is the server up? Used by Render and the uptime check."""
    return {"status": "ok"}


@app.get("/version")
def version() -> dict:
    """Which commit is live (Render sets RENDER_GIT_COMMIT). The deploy workflow waits on it."""
    return {"commit": os.getenv("RENDER_GIT_COMMIT") or "unknown"}


app.include_router(router)
