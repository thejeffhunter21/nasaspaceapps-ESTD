"""J5, J9: the FastAPI app. Run: uv run uvicorn earth_system_trend.api.app:app --reload"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import get_settings
from .routes import router

app = FastAPI(title="Earth System Trend Detective API", version="1.0.0")

# Only our dashboard may call the API from a browser, and only to read.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Is the server up? Used by Render and the uptime check."""
    return {"status": "ok"}


app.include_router(router)
