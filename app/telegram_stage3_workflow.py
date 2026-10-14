from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from finance_db import FinanceDB
from financial_posting import FinancialPostingService, PostingResult
from telegram_workflow import ReviewResult, TelegramReviewWorkflow


@dataclass(frozen=True)
class Stage3Approval:
    review: ReviewResult
    posting: PostingResult


class TelegramStage3Workflow(TelegramReviewWorkflow):
    """Stage 3 application flow.

    Receive/reject/edit behavior remains the proven Stage 2 flow. Approval is
    upgraded to an atomic SQLite financial posting. Google Sheets is still not
    written in this stage.
    """

    def __init__(self, db: FinanceDB):
        super().__init__(db)
        self.poster = FinancialPostingService(db)

    def approve_and_post(self, pending_id: str, *, actor_id: str | None = None) -> Stage3Approval:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        if item["status"] == "REJECTED":
            raise ValueError("مورد ردشده را ابتدا باید بازگشایی/ویرایش کنید.")

        posting = self.poster.post_pending(pending_id, actor_id=actor_id)
        refreshed = self.db.get_pending_item(pending_id)
        review = ReviewResult(pending_id, "APPROVED", refreshed["payload"] if refreshed else item["payload"])
        return Stage3Approval(review=review, posting=posting)
