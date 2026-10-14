from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from finance_db import FinanceDB
from financial_posting import FinancialPostingService, PostingResult
from telegram_workflow import ReviewResult, TelegramReviewWorkflow


@dataclass(frozen=True)
class Stage5Approval:
    review: ReviewResult
    posting: PostingResult


class TelegramStage5Workflow(TelegramReviewWorkflow):
    """Stage 5 flow: create + approve + revise + soft-delete approved postings."""

    def __init__(self, db: FinanceDB):
        super().__init__(db)
        self.poster = FinancialPostingService(db)

    def approve_and_post(self, pending_id: str, *, actor_id: str | None = None) -> Stage5Approval:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        if item["status"] == "REJECTED":
            raise ValueError("مورد ردشده را ابتدا باید بازگشایی/ویرایش کنید.")
        posting = self.poster.post_pending(pending_id, actor_id=actor_id)
        refreshed = self.db.get_pending_item(pending_id)
        review = ReviewResult(pending_id, "APPROVED", refreshed["payload"] if refreshed else item["payload"])
        return Stage5Approval(review=review, posting=posting)

    def begin_posted_revision(self, pending_id: str, new_payload: dict[str, Any], *,
                              source: str = "PRIVATE_EDIT", actor_id: str | None = None) -> dict[str, Any]:
        return self.db.begin_posting_revision(
            pending_id=pending_id,
            new_payload=new_payload,
            source=source,
            actor_id=actor_id,
        )

    def approve_posted_revision(self, pending_id: str, *, actor_id: str | None = None) -> PostingResult:
        return self.poster.revise_pending(pending_id, actor_id=actor_id)

    def reject_posted_revision(self, pending_id: str, *, actor_id: str | None = None) -> dict[str, Any]:
        return self.db.reject_posting_revision(
            pending_id=pending_id,
            source="TELEGRAM_EDIT",
            actor_id=actor_id,
        )

    def delete_posting(self, pending_id: str, *, actor_id: str | None = None, reason: str = "") -> PostingResult:
        return self.poster.delete_pending(pending_id, actor_id=actor_id, reason=reason)

    def begin_preapproval_edit(self, pending_id: str) -> ReviewResult:
        return super().begin_edit(pending_id)

    def apply_preapproval_edit(self, pending_id: str, changes: dict[str, Any]) -> ReviewResult:
        return super().apply_edit(pending_id, changes)
