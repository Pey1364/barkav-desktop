"""WR-08: the review queue of the current desktop application (finance database).

Implements `ReceiptQueue` by calling FinanceDB.create_pending_from_web (DB-02). This is
the only web_receipts module that imports the finance database. When the new version
arrives, write a sibling adapter with the same method and leave this file as it is.
"""

from __future__ import annotations

from pathlib import Path

from finance_db import FinanceDB


class FinanceDBReceiptQueue:
    def __init__(self, db: FinanceDB):
        self.db = db

    @classmethod
    def open(cls, db_path: str | Path) -> "FinanceDBReceiptQueue":
        return cls(FinanceDB(str(db_path)))

    def add_receipt(
        self,
        *,
        receipt_id: str,
        caption: str,
        received_at: str,
        image_path: str,
        image_sha256: str,
    ) -> tuple[str, bool]:
        return self.db.create_pending_from_web(
            receipt_id=receipt_id,
            caption=caption,
            received_at=received_at,
            image_path=image_path,
            image_sha256=image_sha256,
        )
