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
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
