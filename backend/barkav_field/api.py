"""FD-03 and FD-04: local read API for the desktop screen and the PWA.

Routes (all under /api/v1):
    GET /health            status
    GET /receipts          stored receipts, newest first (no image bytes)
    GET /daily-reports     stored daily reports, newest first

Entries are created only by the pull (FD-05), never directly through the API.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from .store import Store


def create_app(data_dir: Path) -> FastAPI:
    store = Store(Path(data_dir))
    app = FastAPI(title="BARKAV Field API", version="1")
    app.state.store = store

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"ok": True, "api": 1}

    @app.get("/api/v1/receipts")
    def receipts() -> list[dict]:
        return app.state.store.list_receipts()

    @app.get("/api/v1/daily-reports")
    def daily_reports() -> list[dict]:
        return app.state.store.list_daily_reports()

    return app
