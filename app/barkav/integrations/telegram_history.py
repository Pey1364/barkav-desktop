from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from local_fallback_parser import analyze_locally
from revenue_service import gregorian_to_shamsi
from telegram_workflow import TelegramReviewWorkflow

# Synthetic namespace reserved for Telegram Desktop imports. It deliberately
# cannot collide with real Telegram supergroup ids.
_IMPORT_CHAT_BASE = -8_900_000_000_000_000
_MONEY_WORDS = (
    "تومان", "تومن", "ریال", "میلیون", "میلیارد", "هزار", "پرداخت", "واریز",
    "خرید", "هزینه", "فاکتور", "رسید", "چک", "وام", "قسط", "اقساط", "تنخواه",
    "دریافت", "تسویه", "پیش پرداخت", "پیش‌پرداخت",
)
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class HistoryImportResult:
    chats: int
    scanned: int
    candidates: int
    created: int
    duplicates: int
    skipped: int
    pending_ids: tuple[str, ...]
    media_candidates: int = 0
    text_candidates: int = 0
    media_missing: int = 0
    media_pending_ids: tuple[str, ...] = ()


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                out.append(str(item.get("text") or ""))
        return "".join(out)
    if isinstance(value, dict):
        return str(value.get("text") or "")
    return ""


def _iter_chats(data: dict[str, Any]) -> Iterable[dict[str, Any]]:
    if isinstance(data.get("messages"), list):
        yield data
        return
    chats = data.get("chats") or {}
    if isinstance(chats, dict):
        for chat in chats.get("list") or []:
            if isinstance(chat, dict) and isinstance(chat.get("messages"), list):
                yield chat


def _synthetic_chat_id(chat: dict[str, Any], source: Path) -> int:
    raw = f"{chat.get('id','')}|{chat.get('name','')}|{source.resolve()}"
    n = int(hashlib.sha1(raw.encode("utf-8")).hexdigest()[:11], 16)
    return _IMPORT_CHAT_BASE - (n % 900_000_000_000)


def _message_datetime(msg: dict[str, Any]) -> datetime:
    raw = str(msg.get("date") or "").strip()
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            pass
    raw_ts = str(msg.get("date_unixtime") or "").strip()
    if raw_ts:
        try:
            return datetime.fromtimestamp(int(raw_ts))
        except Exception:
            pass
    return datetime.now()


def _media_value(msg: dict[str, Any]) -> str:
    """Return a Telegram Desktop export relative media path when present."""
    for key in ("photo", "file"):
        value = msg.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for sub in ("path", "file", "name"):
                v = value.get(sub)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return ""


def _resolve_media(json_path: Path, raw: str) -> Path | None:
    if not raw:
        return None
    cleaned = raw.replace("\\", "/")
    p = Path(cleaned)
    candidates = [p] if p.is_absolute() else [json_path.parent / p, json_path.parent / cleaned]
    for c in candidates:
        try:
            if c.exists() and c.is_file():
                return c.resolve()
        except Exception:
            pass
    return None


def _is_image(path: Path | None, msg: dict[str, Any]) -> bool:
    if path and path.suffix.lower() in _IMAGE_SUFFIXES:
        return True
    mt = str(msg.get("mime_type") or "").lower()
    return mt.startswith("image/") or bool(msg.get("photo"))


def _likely_financial_text(text: str, analysis: dict[str, Any]) -> bool:
    if not text.strip():
        return False
    amount = int(analysis.get("amount") or analysis.get("final_amount") or 0)
    detected = str(analysis.get("detected_type") or "UNKNOWN").upper()
    if amount > 0 or detected not in {"", "UNKNOWN", "NONE"}:
        return True
    t = text.replace("ي", "ی").replace("ك", "ک").lower()
    if any(w in t for w in _MONEY_WORDS):
        return True
    # Long/grouped numeric strings are often payment amounts or tracking data;
    # queue them for review rather than dropping them before AI sees them.
    return bool(re.search(r"(?<!\d)(?:\d{1,3}(?:[,،]\d{3})+|\d{6,13})(?!\d)", t))


def import_telegram_export(db, json_path: str | Path, *, receipt_service=None) -> HistoryImportResult:
    """Import Telegram Desktop JSON with a recall-first policy.

    Critical Stage 15 rule: media is NEVER discarded merely because the local
    text parser cannot find an amount/type. Every exported photo/image is
    archived and queued for AI Vision review. Text-only chatter is filtered by a
    broad financial heuristic to avoid flooding the approval center.

    No financial posting happens automatically.
    """
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("ساختار JSON تلگرام معتبر نیست.")

    workflow = TelegramReviewWorkflow(db)
    scanned = candidates = created = duplicates = skipped = chat_count = 0
    media_candidates = text_candidates = media_missing = 0
    pending_ids: list[str] = []
    media_pending_ids: list[str] = []

    archive_dir = path.parent / ".peymaan_import_archive"
    if receipt_service is None:
        archive_dir.mkdir(parents=True, exist_ok=True)

    for chat in _iter_chats(data):
        chat_count += 1
        chat_id = _synthetic_chat_id(chat, path)
        chat_name = str(chat.get("name") or "Telegram export")
        for idx, msg in enumerate(chat.get("messages") or [], 1):
            if not isinstance(msg, dict) or str(msg.get("type") or "message") != "message":
                continue
            scanned += 1
            text = _flatten_text(msg.get("text")).strip()
            analysis = analyze_locally(text)
            media_raw = _media_value(msg)
            media_path = _resolve_media(path, media_raw)
            has_media_ref = bool(media_raw)
            image_media = _is_image(media_path, msg) if has_media_ref else False

            if has_media_ref:
                candidate = True
                media_candidates += 1
            else:
                candidate = _likely_financial_text(text, analysis)
                if candidate:
                    text_candidates += 1
            if not candidate:
                skipped += 1
                continue

            candidates += 1
            try:
                message_id = int(msg.get("id") or idx)
            except Exception:
                message_id = idx
            was_existing = db.get_telegram_message(chat_id, message_id) is not None
            dt = _message_datetime(msg)
            shamsi_date = gregorian_to_shamsi(dt.date())
            message_date = f"{shamsi_date} {dt:%H:%M}"

            analysis = dict(analysis)
            analysis["event_date_shamsi"] = shamsi_date
            analysis["historical_import"] = True
            analysis["telegram_export_chat"] = chat_name
            analysis["telegram_export_sender"] = str(msg.get("from") or msg.get("actor") or "")
            if has_media_ref and str(analysis.get("detected_type") or "UNKNOWN").upper() == "UNKNOWN":
                analysis["detected_type"] = "DOCUMENT"
                analysis["document_type"] = "OTHER"
                analysis["confidence"] = min(float(analysis.get("confidence") or 0), 0.25)
            note = str(analysis.get("notes") or "").strip()
            extra = "Imported from Telegram Desktop JSON"
            if has_media_ref:
                extra += " | Media queued for AI Vision"
            analysis["notes"] = (note + (" | " if note else "") + extra).strip()

            content_type = "HISTORICAL_IMAGE" if has_media_ref and image_media else ("HISTORICAL_MEDIA" if has_media_ref else "HISTORICAL_TEXT")
            review = workflow.receive_message(
                chat_id=chat_id,
                message_id=message_id,
                raw_text=text,
                content_type=content_type,
                message_date=message_date,
                analysis=analysis,
            )
            pending_ids.append(review.pending_id)
            if was_existing:
                duplicates += 1
            else:
                created += 1

            if has_media_ref:
                if media_path is None:
                    media_missing += 1
                    db.update_pending(review.pending_id, status="NEEDS_REVIEW")
                    db.upsert_receipt_analysis(
                        pending_id=review.pending_id, provider="MEDIA_FILE_MISSING", document_type="OTHER",
                        field_confidences={}, conflicts=[{
                            "field": "media", "severity": "HIGH",
                            "message": "فایل رسانه در کنار JSON پیدا نشد؛ هنگام Export گزینه دانلود رسانه‌ها را فعال کن.",
                            "export_path": media_raw,
                        }], status="NEEDS_REVIEW",
                    )
                    continue

                try:
                    if receipt_service is not None:
                        archived, digest = receipt_service.archive_file(media_path)
                    else:
                        digest = hashlib.sha256(media_path.read_bytes()).hexdigest()
                        archived = archive_dir / f"{digest[:16]}_{media_path.name}"
                        if not archived.exists():
                            shutil.copy2(media_path, archived)
                    mime = str(msg.get("mime_type") or mimetypes.guess_type(str(archived))[0] or "application/octet-stream")
                    db.attach_file_to_pending(
                        pending_id=review.pending_id, local_path=str(archived), mime_type=mime,
                        document_type="RECEIPT" if image_media else "DOCUMENT",
                    )
                    provider = "PENDING_VISION" if image_media else "PENDING_DOCUMENT_REVIEW"
                    db.upsert_receipt_analysis(
                        pending_id=review.pending_id, provider=provider,
                        document_type="OTHER", image_path=str(archived) if image_media else None,
                        image_sha256=digest, field_confidences={}, conflicts=[], status="NEEDS_REVIEW",
                    )
                    db.update_pending(review.pending_id, status="NEEDS_REVIEW")
                    if image_media:
                        media_pending_ids.append(review.pending_id)
                except Exception as exc:
                    media_missing += 1
                    db.update_pending(review.pending_id, status="NEEDS_REVIEW")
                    db.upsert_receipt_analysis(
                        pending_id=review.pending_id, provider="MEDIA_ARCHIVE_FAILED", document_type="OTHER",
                        field_confidences={}, conflicts=[{
                            "field": "media", "severity": "HIGH",
                            "message": f"آرشیو فایل رسانه شکست خورد: {exc.__class__.__name__}",
                        }], status="NEEDS_REVIEW",
                    )

    if chat_count == 0:
        raise ValueError("هیچ گفت‌وگوی دارای messages در فایل JSON پیدا نشد. خروجی را با فرمت JSON از Telegram Desktop بگیر.")
    return HistoryImportResult(
        chats=chat_count,
        scanned=scanned,
        candidates=candidates,
        created=created,
        duplicates=duplicates,
        skipped=skipped,
        pending_ids=tuple(pending_ids),
        media_candidates=media_candidates,
        text_candidates=text_candidates,
        media_missing=media_missing,
        media_pending_ids=tuple(media_pending_ids),
    )


def list_imported_pending(db, limit: int = 20) -> list[dict[str, Any]]:
    with db.read() as con:
        rows = con.execute(
            """SELECT p.*,t.raw_text,t.message_date FROM pending_items p
               JOIN telegram_messages t ON t.chat_id=p.telegram_chat_id AND t.message_id=p.telegram_message_id
               WHERE p.telegram_chat_id<=? AND p.status IN ('PENDING_REVIEW','NEEDS_REVIEW')
               ORDER BY t.message_date,p.created_at LIMIT ?""",
            (_IMPORT_CHAT_BASE, int(limit)),
        ).fetchall()
    out=[]
    for row in rows:
        d=dict(row)
        try:d['payload']=json.loads(d.get('payload_json') or '{}')
        except Exception:d['payload']={}
        out.append(d)
    return out
