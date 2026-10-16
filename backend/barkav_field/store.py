"""FD-02: local database for field entries (receipts and daily reports).

SQLite file plus an images folder. Images are written as files; the database keeps
only their relative path and SHA-256. `seen_remote` records which remote items were
already read, so a second pull never duplicates an entry.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS receipts (
    id TEXT PRIMARY KEY,
    caption TEXT NOT NULL DEFAULT '',
    received_at TEXT NOT NULL,
    image_path TEXT NOT NULL,
    image_sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_reports (
    id TEXT PRIMARY KEY,
    report_date TEXT NOT NULL,
    body TEXT NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports(report_date);
CREATE TABLE IF NOT EXISTS seen_remote (
    remote_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    entry_id TEXT NOT NULL,
    seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_items (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('new', 'under_review', 'approved', 'rejected')),
    title TEXT NOT NULL DEFAULT '',
    transaction_type TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    document_kind TEXT CHECK (document_kind IN ('financial', 'non_financial')),
    note TEXT NOT NULL DEFAULT '',
    decided_by TEXT,
    decided_at TEXT,
    updated_at TEXT NOT NULL
);
"""

DOCUMENT_KINDS = ("financial", "non_financial")
DECISIONS = {"approve": "approved", "reject": "rejected"}
DECIDERS = ("phone", "desktop")


class ReviewError(ValueError):
    """A review step is not allowed in the item's current state, or its data is invalid."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_classification(data: dict | None) -> dict | None:
    """Return the classification fields, or None when the title, type or document kind is missing."""
    if not data:
        return None
    title = str(data.get("title", "")).strip()
    transaction_type = str(data.get("transaction_type", "")).strip()
    document_kind = str(data.get("document_kind", "")).strip()
    if not title or not transaction_type or document_kind not in DOCUMENT_KINDS:
        return None
    return {
        "title": title,
        "transaction_type": transaction_type,
        "category": str(data.get("category", "")).strip(),
        "document_kind": document_kind,
        "note": str(data.get("note", "")).strip(),
    }


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.images_dir = self.data_dir / "images"
        self.db_path = self.data_dir / "field.sqlite3"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.db_path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    # receipts ---------------------------------------------------------------

    def add_receipt(self, *, receipt_id: str, caption: str, received_at: str, image_bytes: bytes) -> bool:
        """Store one receipt. Returns False if the id already exists (no duplicate)."""
        digest = hashlib.sha256(image_bytes).hexdigest()
        relative = f"images/{receipt_id}.jpg"
        target = self.data_dir / relative
        with self._connect() as con:
            if con.execute("SELECT 1 FROM receipts WHERE id=?", (receipt_id,)).fetchone():
                return False
            target.write_bytes(image_bytes)
            con.execute(
                "INSERT INTO receipts(id, caption, received_at, image_path, image_sha256, imported_at) VALUES(?,?,?,?,?,?)",
                (receipt_id, caption, received_at, relative, digest, _now()),
            )
        return True

    def list_receipts(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, caption, received_at, image_sha256, imported_at FROM receipts ORDER BY received_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # daily reports ------------------------------------------------------------

    def add_daily_report(self, *, report_id: str, report_date: str, body: str) -> bool:
        with self._connect() as con:
            if con.execute("SELECT 1 FROM daily_reports WHERE id=?", (report_id,)).fetchone():
                return False
            con.execute(
                "INSERT INTO daily_reports(id, report_date, body, imported_at) VALUES(?,?,?,?)",
                (report_id, report_date, body, _now()),
            )
        return True

    def list_daily_reports(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, report_date, body, imported_at FROM daily_reports ORDER BY report_date DESC, imported_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # remote bookkeeping -------------------------------------------------------

    def is_seen(self, remote_id: str) -> bool:
        with self._connect() as con:
            return con.execute("SELECT 1 FROM seen_remote WHERE remote_id=?", (remote_id,)).fetchone() is not None

    def mark_seen(self, *, remote_id: str, kind: str, entry_id: str) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT OR IGNORE INTO seen_remote(remote_id, kind, entry_id, seen_at) VALUES(?,?,?,?)",
                (remote_id, kind, entry_id, _now()),
            )

    # review queue (FD-12) -----------------------------------------------------

    def create_review_item(self, *, item_id: str, classification: dict | None = None) -> bool:
        """Create the review item for a receipt. It starts under review only if the classification is complete."""
        values = _clean_classification(classification)
        with self._connect() as con:
            if con.execute("SELECT 1 FROM review_items WHERE id=?", (item_id,)).fetchone():
                return False
            con.execute(
                "INSERT INTO review_items(id, status, title, transaction_type, category, document_kind, note, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (
                    item_id,
                    "under_review" if values else "new",
                    values["title"] if values else "",
                    values["transaction_type"] if values else "",
                    values["category"] if values else "",
                    values["document_kind"] if values else None,
                    values["note"] if values else "",
                    _now(),
                ),
            )
        return True

    def classify(
        self,
        item_id: str,
        *,
        title: str,
        transaction_type: str,
        document_kind: str,
        category: str = "",
        note: str = "",
    ) -> None:
        """Save the wizard answers and move a new or under-review item to under review."""
        values = _clean_classification(
            {"title": title, "transaction_type": transaction_type, "document_kind": document_kind,
             "category": category, "note": note}
        )
        if values is None:
            raise ReviewError("عنوان، نوع تراکنش و نوع سند (مالی یا غیرمالی) لازم است.")
        with self._connect() as con:
            row = con.execute("SELECT status FROM review_items WHERE id=?", (item_id,)).fetchone()
            if row is None:
                raise ReviewError("ورودی پیدا نشد.")
            if row["status"] not in ("new", "under_review"):
                raise ReviewError("این ورودی دیگر قابل ویرایش نیست.")
            con.execute(
                "UPDATE review_items SET status='under_review', title=?, transaction_type=?, category=?,"
                " document_kind=?, note=?, updated_at=? WHERE id=?",
                (values["title"], values["transaction_type"], values["category"], values["document_kind"],
                 values["note"], _now(), item_id),
            )

    def decide(self, item_id: str, *, decision: str, decided_by: str, decided_at: str) -> bool:
        """Approve or reject an item under review. The first decision wins; a later one returns False."""
        if decision not in DECISIONS:
            raise ReviewError("تصمیم نامعتبر است.")
        if decided_by not in DECIDERS:
            raise ReviewError("تصمیم‌گیرنده نامعتبر است.")
        with self._connect() as con:
            row = con.execute("SELECT status FROM review_items WHERE id=?", (item_id,)).fetchone()
            if row is None:
                raise ReviewError("ورودی پیدا نشد.")
            if row["status"] in ("approved", "rejected"):
                return False
            if row["status"] != "under_review":
                raise ReviewError("ابتدا ورودی باید دسته‌بندی و ثبت شود.")
            con.execute(
                "UPDATE review_items SET status=?, decided_by=?, decided_at=?, updated_at=? WHERE id=?",
                (DECISIONS[decision], decided_by, decided_at, _now(), item_id),
            )
        return True

    def list_review_items(self, status: str | None = None) -> list[dict]:
        sql = (
            "SELECT id, status, title, transaction_type, category, document_kind, note,"
            " decided_by, decided_at, updated_at FROM review_items"
        )
        args: tuple = ()
        if status:
            sql += " WHERE status=?"
            args = (status,)
        sql += " ORDER BY updated_at DESC"
        with self._connect() as con:
            rows = con.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
