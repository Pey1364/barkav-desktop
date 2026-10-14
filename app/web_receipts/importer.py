"""WR-07: moves received web receipts into the review queue.

For each item in the inbox the importer:
1. copies the photo into the archive folder and computes its SHA-256 hash,
2. asks the queue to add the receipt (idempotent on receipt_id),
3. marks the inbox item IMPORTED, storing the pending_id.

If step 2 fails, the item stays RECEIVED and the next run tries again. If the process
stops after step 2 but before step 3, the next run finds the existing pending row and
only marks the item. Nothing is imported twice.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .inbox import list_received, mark_imported
from .ports import ReceiptQueue


@dataclass
class ImportReport:
    imported: list[str] = field(default_factory=list)
    already_in_queue: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.imported) + len(self.already_in_queue) + len(self.failed)


def import_received(*, inbox_dir: Path, archive_dir: Path, queue: ReceiptQueue) -> ImportReport:
    report = ImportReport()
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)

    for item in list_received(Path(inbox_dir)):
        receipt_id = str(item["receipt_id"])
        folder = Path(item["folder"])
        try:
            source = folder / "receipt.jpg"
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            target = archive_dir / f"{receipt_id}.jpg"
            if not target.exists():
                shutil.copyfile(source, target)
            pending_id, created = queue.add_receipt(
                receipt_id=receipt_id,
                caption=str(item.get("caption", "")),
                received_at=str(item.get("received_at", "")),
                image_path=str(target),
                image_sha256=digest,
            )
        except Exception as exc:  # one bad item must not stop the rest of the batch
            report.failed.append((receipt_id, type(exc).__name__))
            continue

        mark_imported(folder, pending_id)
        if created:
            report.imported.append(receipt_id)
        else:
            report.already_in_queue.append(receipt_id)
    return report
