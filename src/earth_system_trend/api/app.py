"""J5, J9: the FastAPI app. Run: uv run uvicorn earth_system_trend.api.app:app --reload"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from ..config import get_settings
from .analysis import router as analysis_router
from .analysis import warm_cache
from .explorer import router as explorer_router
from .middleware import add_protection
from .routes import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    warm_cache()  # compute the grid-cell discoveries in the background at start-up
    yield


app = FastAPI(title="Earth System Trend Detective API", version="1.0.0", lifespan=lifespan)

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
app.include_router(analysis_router)
app.include_router(explorer_router)

# The map explorer (web/): a static page that reads the endpoints above from the same server.
WEB_DIR = Path(os.getenv("WEB_DIR", "web"))
if WEB_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")

    @app.get("/explore", include_in_schema=False)
    def explore() -> RedirectResponse:
        return RedirectResponse("/app/")
