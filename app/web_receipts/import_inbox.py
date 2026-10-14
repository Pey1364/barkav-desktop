"""WR-09: manual import of web receipts into the review queue.

    python -m web_receipts.import_inbox --db <path to the project database> [--dry-run]

The import is started by a person, never on a timer. `--dry-run` only lists what would
be imported and does not open the database. The archive folder is `receipt_archive/web`
next to the database file, so web photos stay apart from Telegram attachments.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .inbox import list_received
from .importer import import_received

APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INBOX = APP_DIR / "data" / "web_receipts" / "inbox"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import web receipts into the review queue.")
    parser.add_argument("--db", type=Path, help="project database file (required unless --dry-run)")
    parser.add_argument("--inbox", type=Path, default=DEFAULT_INBOX, help="inbox folder")
    parser.add_argument("--dry-run", action="store_true", help="list items without writing")
    args = parser.parse_args(argv)

    if args.dry_run:
        items = list_received(args.inbox)
        print(f"{len(items)} رسید در انتظار وارد کردن است.")
        for item in items:
            print(f"  {item['receipt_id']}  {item.get('received_at', '')}")
        return 0

    if args.db is None:
        parser.error("--db is required unless --dry-run is used")

    from .legacy_queue import FinanceDBReceiptQueue

    queue = FinanceDBReceiptQueue.open(args.db)
    archive = Path(args.db).resolve().parent / "receipt_archive" / "web"
    report = import_received(inbox_dir=args.inbox, archive_dir=archive, queue=queue)
    print(f"وارد شد: {len(report.imported)}")
    print(f"قبلاً در صف بود: {len(report.already_in_queue)}")
    print(f"ناموفق: {len(report.failed)}")
    for receipt_id, error in report.failed:
        print(f"  {receipt_id}: {error}")
    return 0 if not report.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
