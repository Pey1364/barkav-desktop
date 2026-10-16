"""FD-03 and FD-04: local read API for the desktop screen and the PWA.

Routes (all under /api/v1):
    GET  /health                          status
    GET  /receipts                        stored receipts, newest first (no image bytes)
    GET  /documents                       stored documents with their photo counts (FD-13)
    GET  /documents/{id}/images/{n}       one stored photo (JPEG)
    GET  /daily-reports                   stored daily reports, newest first
    GET  /review-items?status=            review queue (FD-12), optional status filter
    POST /review-items/{id}/classify      save the wizard answers; moves the item under review
    POST /review-items/{id}/decision      approve or reject an item under review (desktop)

Entries are created only by the pull (FD-05), never directly through the API. The review
routes change only the review state of an existing item; they never create a receipt.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .store import ReviewError, Store


class ClassifyBody(BaseModel):
    title: str
    transaction_type: str
    document_kind: str
    category: str = ""
    note: str = ""
    event_date: str = ""
    amount: str = ""


class DecisionBody(BaseModel):
    decision: str


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

    @app.get("/api/v1/documents")
    def documents() -> list[dict]:
        return app.state.store.list_documents()

    @app.get("/api/v1/documents/{document_id}/images/{position}")
    def document_image(document_id: str, position: int) -> FileResponse:
        path = app.state.store.document_image_path(document_id, position)
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail="photo not found")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/v1/daily-reports")
    def daily_reports() -> list[dict]:
        return app.state.store.list_daily_reports()

    @app.get("/api/v1/review-items")
    def review_items(status: str | None = None) -> list[dict]:
        return app.state.store.list_review_items(status)

    @app.post("/api/v1/review-items/{item_id}/classify")
    def classify(item_id: str, body: ClassifyBody) -> dict:
        try:
            app.state.store.classify(item_id, **body.model_dump())
        except ReviewError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/v1/review-items/{item_id}/decision")
    def decide(item_id: str, body: DecisionBody) -> dict:
        try:
            changed = app.state.store.decide(
                item_id,
                decision=body.decision,
                decided_by="desktop",
                decided_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        except ReviewError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "changed": changed}

    return app
