"""FD-02: local database for field entries (receipts and daily reports).

SQLite file plus an images folder. Images are written as files; the database keeps
only their relative path and SHA-256. `seen_remote` records which remote items were
already read, so a second pull never duplicates an entry.
"""

from __future__ import annotations

import hashlib
import json
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
    imported_at TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{}'
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
    event_date TEXT NOT NULL DEFAULT '',
    amount TEXT NOT NULL DEFAULT '',
    decided_by TEXT,
    decided_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sent_at TEXT
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('quick', 'detailed')),
    caption TEXT NOT NULL DEFAULT '',
    received_at TEXT NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS document_images (
    document_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    image_sha256 TEXT NOT NULL,
    PRIMARY KEY (document_id, position)
);
"""

DOCUMENT_MODES = ("quick", "detailed")
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
        "event_date": str(data.get("event_date", "")).strip(),
        "amount": str(data.get("amount", "")).strip(),
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
            self._migrate(con)

    @staticmethod
    def _migrate(con: sqlite3.Connection) -> None:
        """Add columns that older databases do not have yet. Idempotent."""
        columns = {row["name"] for row in con.execute("PRAGMA table_info(daily_reports)")}
        if "details" not in columns:
            con.execute("ALTER TABLE daily_reports ADD COLUMN details TEXT NOT NULL DEFAULT '{}'")
        review_columns = {row["name"] for row in con.execute("PRAGMA table_info(review_items)")}
        for column in ("event_date", "amount"):
            if column not in review_columns:
                con.execute(f"ALTER TABLE review_items ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")

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

    def add_daily_report(self, *, report_id: str, report_date: str, body: str, details: dict | None = None) -> bool:
        with self._connect() as con:
            if con.execute("SELECT 1 FROM daily_reports WHERE id=?", (report_id,)).fetchone():
                return False
            con.execute(
                "INSERT INTO daily_reports(id, report_date, body, imported_at, details) VALUES(?,?,?,?,?)",
                (report_id, report_date, body, _now(), json.dumps(details or {}, ensure_ascii=False)),
            )
        return True

    def list_daily_reports(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, report_date, body, imported_at, details FROM daily_reports"
                " ORDER BY report_date DESC, imported_at DESC"
            ).fetchall()
        return [{**dict(r), "details": json.loads(r["details"] or "{}")} for r in rows]

    # documents (FD-13) ----------------------------------------------------------

    def add_document(self, *, document_id: str, mode: str, caption: str, received_at: str, images: list[bytes]) -> bool:
        """Store a document with its photos in order. Returns False if the id already exists."""
        if mode not in DOCUMENT_MODES:
            raise ValueError("document mode must be quick or detailed")
        if not images:
            raise ValueError("a document needs at least one photo")
        with self._connect() as con:
            if con.execute("SELECT 1 FROM documents WHERE id=?", (document_id,)).fetchone():
                return False
            con.execute(
                "INSERT INTO documents(id, mode, caption, received_at, imported_at) VALUES(?,?,?,?,?)",
                (document_id, mode, caption, received_at, _now()),
            )
            for position, image in enumerate(images, start=1):
                relative = f"images/{document_id}-{position}.jpg"
                (self.data_dir / relative).write_bytes(image)
                con.execute(
                    "INSERT INTO document_images(document_id, position, image_path, image_sha256) VALUES(?,?,?,?)",
                    (document_id, position, relative, hashlib.sha256(image).hexdigest()),
                )
        return True

    def document_image_path(self, document_id: str, position: int) -> Path | None:
        """Absolute path of one stored photo, or None. The path comes from the database only."""
        with self._connect() as con:
            row = con.execute(
                "SELECT image_path FROM document_images WHERE document_id=? AND position=?",
                (document_id, position),
            ).fetchone()
        return (self.data_dir / row["image_path"]) if row else None

    def list_documents(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT d.id, d.mode, d.caption, d.received_at, d.imported_at,"
                " (SELECT COUNT(*) FROM document_images i WHERE i.document_id = d.id) AS image_count"
                " FROM documents d ORDER BY d.received_at DESC"
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
                "INSERT INTO review_items(id, status, title, transaction_type, category, document_kind, note,"
                " event_date, amount, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    item_id,
                    "under_review" if values else "new",
                    values["title"] if values else "",
                    values["transaction_type"] if values else "",
                    values["category"] if values else "",
                    values["document_kind"] if values else None,
                    values["note"] if values else "",
                    values["event_date"] if values else "",
                    values["amount"] if values else "",
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
        event_date: str = "",
        amount: str = "",
    ) -> None:
        """Save the wizard answers and move a new or under-review item to under review."""
        values = _clean_classification(
            {"title": title, "transaction_type": transaction_type, "document_kind": document_kind,
             "category": category, "note": note, "event_date": event_date, "amount": amount}
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
                " document_kind=?, note=?, event_date=?, amount=?, updated_at=? WHERE id=?",
                (values["title"], values["transaction_type"], values["category"], values["document_kind"],
                 values["note"], values["event_date"], values["amount"], _now(), item_id),
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
            if decided_by == "desktop":
                # The phone must learn the outcome: queue it for the next pull to publish.
                payload = {"kind": "review_status", "item_id": item_id, "status": DECISIONS[decision],
                           "decided_at": decided_at}
                con.execute(
                    "INSERT INTO outbox(kind, payload, created_at) VALUES(?,?,?)",
                    ("review_status", json.dumps(payload, ensure_ascii=False), _now()),
                )
        return True

    def pending_outbox(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute("SELECT id, kind, payload FROM outbox WHERE sent_at IS NULL ORDER BY id").fetchall()
        return [{"id": row["id"], "kind": row["kind"], "payload": json.loads(row["payload"])} for row in rows]

    def mark_outbox_sent(self, outbox_id: int) -> None:
        with self._connect() as con:
            con.execute("UPDATE outbox SET sent_at=? WHERE id=?", (_now(), outbox_id))

    def get_review_item(self, item_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT id, status, title, transaction_type, category, document_kind, note, event_date, amount,"
                " decided_by, decided_at, updated_at FROM review_items WHERE id=?",
                (item_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_review_items(self, status: str | None = None) -> list[dict]:
        sql = (
            "SELECT id, status, title, transaction_type, category, document_kind, note, event_date, amount,"
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
