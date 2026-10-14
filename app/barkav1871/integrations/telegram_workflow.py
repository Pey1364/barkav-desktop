from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from barkav1871.services import FinanceDB
from .edit_normalizer import normalize_financial_edit


@dataclass(frozen=True)
class ReviewResult:
    pending_id: str
    state: str
    payload: dict[str, Any]


class TelegramReviewWorkflow:
    """Canonical application review layer.

    This layer deliberately does NOT create financial Expenses/Transactions yet.
    It proves the Telegram -> Pending -> private approval/reject/edit lifecycle
    without touching Google Sheets or production balances.
    """

    def __init__(self, db: FinanceDB):
        self.db = db

    def receive_message(self, *, chat_id: int, message_id: int, raw_text: str,
                        content_type: str, message_date: str,
                        analysis: dict[str, Any]) -> ReviewResult:
        inserted = self.db.register_telegram_message(
            chat_id=chat_id,
            message_id=message_id,
            raw_text=raw_text,
            content_type=content_type,
            message_date=message_date,
            state="RECEIVED",
        )

        existing = self.db.get_pending_by_message(chat_id, message_id)
        if not inserted and existing:
            return ReviewResult(existing["pending_id"], existing["status"], existing["payload"])

        detected_type = str(analysis.get("detected_type") or "UNKNOWN")
        confidence = analysis.get("confidence")
        status = "NEEDS_REVIEW" if detected_type == "UNKNOWN" else "PENDING_REVIEW"
        pending_id = self.db.create_or_replace_pending(
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
            detected_type=detected_type,
            payload=analysis,
            confidence=float(confidence) if confidence is not None else None,
            status=status,
        )
        self.db.update_telegram_message(
            chat_id=chat_id,
            message_id=message_id,
            state=status,
        )
        return ReviewResult(pending_id, status, analysis)

    def approve(self, pending_id: str) -> ReviewResult:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        if item["status"] == "APPROVED":
            return ReviewResult(pending_id, "APPROVED", item["payload"])
        if item["status"] == "REJECTED":
            raise ValueError("rejected item cannot be approved without reopening")

        self.db.update_pending(pending_id, status="APPROVED")
        self.db.update_telegram_message(
            chat_id=item["telegram_chat_id"],
            message_id=item["telegram_message_id"],
            state="APPROVED",
        )
        return ReviewResult(pending_id, "APPROVED", item["payload"])

    def reject(self, pending_id: str) -> ReviewResult:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        if item["status"] == "REJECTED":
            return ReviewResult(pending_id, "REJECTED", item["payload"])
        self.db.update_pending(pending_id, status="REJECTED")
        self.db.update_telegram_message(
            chat_id=item["telegram_chat_id"],
            message_id=item["telegram_message_id"],
            state="REJECTED",
        )
        return ReviewResult(pending_id, "REJECTED", item["payload"])

    def begin_edit(self, pending_id: str) -> ReviewResult:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        if item["status"] in {"APPROVED", "REJECTED"}:
            raise ValueError("Pending items can be edited only before final decision")
        self.db.update_pending(pending_id, status="NEEDS_REVIEW")
        self.db.update_telegram_message(
            chat_id=item["telegram_chat_id"],
            message_id=item["telegram_message_id"],
            state="NEEDS_REVIEW",
        )
        return ReviewResult(pending_id, "NEEDS_REVIEW", item["payload"])

    def apply_edit(self, pending_id: str, changes: dict[str, Any]) -> ReviewResult:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        payload = normalize_financial_edit(dict(item["payload"]), changes)
        detected_type = str(payload.get("detected_type") or item.get("detected_type") or "UNKNOWN")
        self.db.update_pending(
            pending_id,
            payload=payload,
            detected_type=detected_type,
            status="PENDING_REVIEW",
        )
        self.db.update_telegram_message(
            chat_id=item["telegram_chat_id"],
            message_id=item["telegram_message_id"],
            state="PENDING_REVIEW",
        )
        return ReviewResult(pending_id, "PENDING_REVIEW", payload)

    def mark_private_review_message(self, pending_id: str, private_message_id: int) -> None:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        self.db.update_telegram_message(
            chat_id=item["telegram_chat_id"],
            message_id=item["telegram_message_id"],
            private_review_message_id=private_message_id,
        )

    def mark_reaction(self, pending_id: str, checked: bool) -> None:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        self.db.update_telegram_message(
            chat_id=item["telegram_chat_id"],
            message_id=item["telegram_message_id"],
            reaction_state="CHECKED" if checked else "NONE",
        )
