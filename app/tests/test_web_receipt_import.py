"""WR-06 to WR-09 and DB-01, DB-02: import of web receipts into the review queue.

All databases here are temporary files. Photos are generated in memory.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from finance_db import FinanceDB
from web_receipts.importer import import_received
from web_receipts.inbox import list_received, store_receipt
from web_receipts.legacy_queue import FinanceDBReceiptQueue

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "web_receipts"


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 40), (10, 20, 30)).save(out, format="PNG")
    return out.getvalue()


class FakeQueue:
    """Stands in for the review queue. Remembers receipts like the real one does."""

    def __init__(self, fail_ids: set[str] | None = None):
        self.rows: dict[str, str] = {}
        self.calls = 0
        self.fail_ids = fail_ids or set()

    def add_receipt(self, *, receipt_id, caption, received_at, image_path, image_sha256):
        self.calls += 1
        if receipt_id in self.fail_ids:
            raise RuntimeError("queue unavailable")
        if receipt_id in self.rows:
            return self.rows[receipt_id], False
        pending_id = f"PEN-{len(self.rows) + 1}"
        self.rows[receipt_id] = pending_id
        return pending_id, True


# --- importer with a fake queue --------------------------------------------------------

def test_import_moves_each_receipt_once_and_archives_the_photo(tmp_path: Path):
    inbox = tmp_path / "inbox"
    archive = tmp_path / "archive"
    stored = store_receipt(inbox, _png(), "بابت آجر")
    queue = FakeQueue()

    report = import_received(inbox_dir=inbox, archive_dir=archive, queue=queue)

    assert report.imported == [stored.receipt_id]
    assert report.failed == []
    archived = archive / f"{stored.receipt_id}.jpg"
    assert archived.is_file()
    assert hashlib.sha256(archived.read_bytes()).hexdigest() == hashlib.sha256(
        (stored.folder / "receipt.jpg").read_bytes()
    ).hexdigest()
    meta = json.loads((stored.folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["state"] == "IMPORTED"
    assert meta["pending_id"] == "PEN-1"
    assert meta["schema_version"] == 1


def test_second_run_does_not_import_again(tmp_path: Path):
    inbox = tmp_path / "inbox"
    store_receipt(inbox, _png(), "")
    queue = FakeQueue()
    import_received(inbox_dir=inbox, archive_dir=tmp_path / "archive", queue=queue)

    report = import_received(inbox_dir=inbox, archive_dir=tmp_path / "archive", queue=queue)

    assert report.total == 0
    assert queue.calls == 1


def test_interrupted_run_recovers_without_duplicates(tmp_path: Path):
    """The queue already has the receipt, but the inbox item still says RECEIVED."""
    inbox = tmp_path / "inbox"
    stored = store_receipt(inbox, _png(), "")
    queue = FakeQueue()
    import_received(inbox_dir=inbox, archive_dir=tmp_path / "archive", queue=queue)
    meta_path = stored.folder / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["state"] = "RECEIVED"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    report = import_received(inbox_dir=inbox, archive_dir=tmp_path / "archive", queue=queue)

    assert report.already_in_queue == [stored.receipt_id]
    assert report.imported == []
    assert list(queue.rows) == [stored.receipt_id]
    assert json.loads(meta_path.read_text(encoding="utf-8"))["state"] == "IMPORTED"


def test_one_failing_item_does_not_stop_the_batch(tmp_path: Path):
    inbox = tmp_path / "inbox"
    bad = store_receipt(inbox, _png(), "one")
    good = store_receipt(inbox, _png(), "two")
    queue = FakeQueue(fail_ids={bad.receipt_id})

    report = import_received(inbox_dir=inbox, archive_dir=tmp_path / "archive", queue=queue)

    assert report.imported == [good.receipt_id]
    assert report.failed == [(bad.receipt_id, "RuntimeError")]
    still = json.loads((bad.folder / "meta.json").read_text(encoding="utf-8"))
    assert still["state"] == "RECEIVED"


# --- DB-02 through WR-08 on a temporary database ---------------------------------------

@pytest.fixture()
def db(tmp_path: Path) -> FinanceDB:
    return FinanceDB(tmp_path / "project.sqlite3")


def _count(db: FinanceDB, sql: str, params: tuple = ()) -> int:
    with db.read() as con:
        return int(con.execute(sql, params).fetchone()[0])


def test_web_receipt_becomes_a_pending_row_and_nothing_financial(db: FinanceDB, tmp_path: Path):
    queue = FinanceDBReceiptQueue(db)
    financial_tables = ("expenses", "transactions", "financial_postings", "payments", "cheques")
    before = {t: _count(db, f"SELECT COUNT(*) FROM {t}") for t in financial_tables}

    pending_id, created = queue.add_receipt(
        receipt_id="20261014-120000-aaaa1111",
        caption="بابت آجر",
        received_at="2026-10-14T12:00:00+00:00",
        image_path=str(tmp_path / "x.jpg"),
        image_sha256="0" * 64,
    )

    assert created is True
    row = db.get_pending_item(pending_id)
    assert row["status"] == "NEEDS_REVIEW"
    assert row["telegram_chat_id"] == 0
    assert row["telegram_message_id"] < 0
    with db.read() as con:
        source, ext = con.execute(
            "SELECT source, external_ref FROM pending_items WHERE pending_id=?", (pending_id,)
        ).fetchone()
    assert (source, ext) == ("WEB", "20261014-120000-aaaa1111")
    assert _count(db, "SELECT COUNT(*) FROM receipt_analyses WHERE pending_id=?", (pending_id,)) == 1
    assert _count(db, "SELECT COUNT(*) FROM attachments WHERE entity_type='PENDING' AND entity_id=?", (pending_id,)) == 1
    assert {t: _count(db, f"SELECT COUNT(*) FROM {t}") for t in financial_tables} == before


def test_same_receipt_twice_gives_one_row(db: FinanceDB, tmp_path: Path):
    queue = FinanceDBReceiptQueue(db)
    kwargs = dict(receipt_id="R-1", caption="", received_at="", image_path="p", image_sha256="h")
    first = queue.add_receipt(**kwargs)
    second = queue.add_receipt(**kwargs)

    assert first == (first[0], True)
    assert second == (first[0], False)
    assert _count(db, "SELECT COUNT(*) FROM pending_items WHERE external_ref='R-1'") == 1


def test_web_message_ids_are_distinct_and_negative(db: FinanceDB):
    queue = FinanceDBReceiptQueue(db)
    a, _ = queue.add_receipt(receipt_id="A", caption="", received_at="", image_path="p", image_sha256="h")
    b, _ = queue.add_receipt(receipt_id="B", caption="", received_at="", image_path="p", image_sha256="h")

    ids = [db.get_pending_item(a)["telegram_message_id"], db.get_pending_item(b)["telegram_message_id"]]
    assert ids[0] != ids[1]
    assert all(i < 0 for i in ids)


def test_telegram_rows_are_untouched_by_web_receipts(db: FinanceDB, tmp_path: Path):
    tg_pending = db.create_or_replace_pending(
        telegram_chat_id=-1001234567890,
        telegram_message_id=5,
        detected_type="EXPENSE",
        payload={"detected_type": "EXPENSE"},
        status="PENDING_REVIEW",
    )
    queue = FinanceDBReceiptQueue(db)
    queue.add_receipt(receipt_id="W-1", caption="", received_at="", image_path="p", image_sha256="h")

    row = db.get_pending_item(tg_pending)
    assert row["status"] == "PENDING_REVIEW"
    with db.read() as con:
        source, ext = con.execute("SELECT source, external_ref FROM pending_items WHERE pending_id=?", (tg_pending,)).fetchone()
    assert (source, ext) == ("TELEGRAM", None)


def test_upgrade_adds_columns_to_an_old_pending_table_and_keeps_its_rows(tmp_path: Path):
    """DB-01 on a database that was created before the web channel existed."""
    path = tmp_path / "old.sqlite3"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE pending_items (
            pending_id TEXT PRIMARY KEY,
            telegram_chat_id INTEGER NOT NULL,
            telegram_message_id INTEGER NOT NULL,
            detected_type TEXT,
            payload_json TEXT NOT NULL,
            confidence REAL,
            status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(telegram_chat_id, telegram_message_id)
        );
        INSERT INTO pending_items VALUES('PEN-OLD', -100, 7, 'EXPENSE', '{}', NULL, 'PENDING_REVIEW', 'x', 'x');
        """
    )
    con.commit()
    con.close()

    db = FinanceDB(path)
    with db.read() as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(pending_items)").fetchall()}
        old = c.execute("SELECT source, external_ref FROM pending_items WHERE pending_id='PEN-OLD'").fetchone()
    assert {"source", "external_ref"} <= cols
    assert tuple(old) == ("TELEGRAM", None)

    FinanceDB(path)  # running the migration again changes nothing
    queue = FinanceDBReceiptQueue(db)
    _, created = queue.add_receipt(receipt_id="NEW", caption="", received_at="", image_path="p", image_sha256="h")
    assert created is True


# --- WR-07/WR-09 with the real queue ---------------------------------------------------

def test_manual_import_command_uses_the_project_archive_folder(tmp_path: Path, capsys):
    from web_receipts.import_inbox import main

    inbox = tmp_path / "inbox"
    stored = store_receipt(inbox, _png(), "بابت خرید")
    db_path = tmp_path / "project" / "project.sqlite3"
    db_path.parent.mkdir()

    code = main(["--db", str(db_path), "--inbox", str(inbox)])

    assert code == 0
    assert (db_path.parent / "receipt_archive" / "web" / f"{stored.receipt_id}.jpg").is_file()
    db = FinanceDB(db_path)
    assert _count(db, "SELECT COUNT(*) FROM pending_items WHERE external_ref=?", (stored.receipt_id,)) == 1


def test_dry_run_does_not_create_a_database(tmp_path: Path, capsys):
    from web_receipts.import_inbox import main

    inbox = tmp_path / "inbox"
    store_receipt(inbox, _png(), "")
    code = main(["--dry-run", "--inbox", str(inbox)])

    assert code == 0
    assert "1 رسید" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.sqlite3"))


# --- architecture guard (WR-06 boundary) -----------------------------------------------

FORBIDDEN_FOR_CORE = ("finance_db", "tkinter", "dashboard", "barkav", "telegram", "legacy_queue")


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names.add(("." * node.level) + module)
    return names


@pytest.mark.parametrize("module", ["inbox.py", "server.py", "cert.py", "ports.py", "importer.py", "run_local.py"])
def test_core_modules_do_not_depend_on_the_desktop_or_the_database(module: str):
    for name in _imports_of(PACKAGE_DIR / module):
        for forbidden in FORBIDDEN_FOR_CORE:
            assert forbidden not in name, f"{module} imports {name}"


def test_importer_depends_only_on_the_inbox_and_the_port():
    names = _imports_of(PACKAGE_DIR / "importer.py")
    local = {n for n in names if n.startswith(".")}
    assert local == {".inbox", ".ports"}
