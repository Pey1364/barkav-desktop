"""WR-06: the boundary between web receipt intake and the approval queue.

The importer depends only on this protocol. The desktop application implements it
today (WR-08, on the legacy finance database). When the new version arrives, a second
implementation can be added without changing the importer, the server or the page.
"""

from __future__ import annotations

from typing import Protocol


class ReceiptQueue(Protocol):
    def add_receipt(
        self,
        *,
        receipt_id: str,
        caption: str,
        received_at: str,
        image_path: str,
        image_sha256: str,
    ) -> tuple[str, bool]:
        """Add one receipt to the review queue.

        Returns (pending_id, created). Calling it again for the same receipt_id must
        return the existing pending_id with created=False. It must never create a
        financial row.
        """
        ...
