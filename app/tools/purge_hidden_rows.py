"""Permanently remove deleted / hidden rows from a BARKAV project database.

Review cards that were rejected or hidden, and ledger rows that were cancelled,
voided or deleted, stay in the file forever because the app only soft-deletes.
This removes them (and the rows that only hang off them) so the database holds
what is registered now. Close BARKAV and the Telegram bot first.

    python tools/purge_hidden_rows.py                  # dry run on a throw-away COPY
    python tools/purge_hidden_rows.py --apply          # back up next to the database, then purge
    python tools/purge_hidden_rows.py --empty-income --empty-cheques
    python tools/purge_hidden_rows.py --test-sale SALE-XXXX --test-cheque CHQ-XXXX

What counts as deleted / hidden:
  pending_items      REJECTED, or hidden in rich_ui_hidden_reviews (never an item
                     still waiting for review, never one a live posting needs)
  postings, documents, payments, transactions, expenses
                     marked DELETED / CANCELLED / VOIDED (or deleted_at set), except
                     a transaction or expense a live record still points at (kept)
  rows that only hang off those: attachments, receipt_analyses, integration_events,
  posting_revisions, telegram_messages, sync_queue, links

--empty-income empties the «درآمد» tab: every sale, whichever its status, with what
hangs off it (see --test-sale below). --empty-cheques removes every cheque. Both
also remove the ledger transactions those receipts and cheques created; a
cheque a live posting or payment still uses stops the run before anything
changes.

Test data you name is removed too: --test-sale deletes that whole sale (its
installments, received payments, allocations, reminders and attachments) and,
like cancelling it in the app, sets its unit back from SOLD to AVAILABLE;
--test-sale-payments deletes only the received payments of a sale (the sale and
its installments stay, and installments still saying "paid" are listed);
--test-cheque deletes that cheque. The voided transactions they pointed at go
with them.

Never touched: audit_log, rich_change_history, reminders, settings, prices, budget
tables and every file on disk (the orphaned file list is saved next to the backup).

The real run makes a verified backup (in .barkav-migration-backups next to the database), deletes in ONE transaction (children before
parents) and rolls everything back if a reference would break or a live record
would change. A re-import of the same Telegram export brings removed messages
back as new review items.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[1]

SET_STATEMENTS = [
    "create temp table purge_pending(id text primary key)",
    "create temp table purge_posting(id text primary key)",
    "create temp table purge_doc(id text primary key)",
    "create temp table purge_pay(id text primary key)",
    "create temp table purge_rcv(id text primary key)",
    "create temp table purge_chq(id text primary key)",
    "create temp table purge_sale(id text primary key)",
    "create temp table purge_inst(id text primary key)",
    "create temp table purge_tx(id text primary key)",
    "create temp table purge_exp(id text primary key)",
    """insert into purge_pending
       select p.pending_id from pending_items p
       where (p.status='REJECTED'
              or p.pending_id in (select pending_id from rich_ui_hidden_reviews where hidden=1))
         and p.status not in ('PENDING_REVIEW','NEEDS_REVIEW','EDIT_PENDING','LINKED')
         and p.pending_id not in (select pending_id from financial_postings
                                  where pending_id is not null and status<>'DELETED' and deleted_at is null)
         and p.pending_id not in (select pending_id from financial_documents
                                  where pending_id is not null and status<>'DELETED')""",
    """insert into purge_posting
       select posting_id from financial_postings
       where status='DELETED' or deleted_at is not null
          or pending_id in (select id from purge_pending)""",
    """insert into purge_doc
       select document_id from financial_documents
       where status='DELETED' and (pending_id is null or pending_id in (select id from purge_pending))""",
    "insert into purge_pay select payment_id from payments where status='CANCELLED'",
    # Test receipts / cheques are added by build_sets() before the two statements below.
]

TRANSACTION_STATEMENTS = [
    "insert into purge_tx select transaction_id from transactions where status='VOIDED' or deleted_at is not null",
    # what the removed receipts, sales and cheques posted to the ledger goes with them, live or voided
    "insert or ignore into purge_tx select transaction_id from received_payments"
    " where received_payment_id in (select id from purge_rcv) and transaction_id is not null",
    "insert or ignore into purge_tx select transaction_id from transactions where sale_id in (select id from purge_sale)",
    "insert or ignore into purge_tx select cash_transaction_id from cheques"
    " where cheque_id in (select id from purge_chq) and cash_transaction_id is not null",
    # a voided transaction that a live record still points at must stay
    """delete from purge_tx where id in (
           select transaction_id from received_payments
               where transaction_id is not null and received_payment_id not in (select id from purge_rcv)
           union select cash_transaction_id from cheques
               where cash_transaction_id is not null and cheque_id not in (select id from purge_chq)
           union select transaction_id from loan_installments where transaction_id is not null
           union select related_transaction_id from receivables where related_transaction_id is not null
           union select transaction_id from payments
               where transaction_id is not null and payment_id not in (select id from purge_pay)
           union select transaction_id from financial_postings
               where transaction_id is not null and posting_id not in (select id from purge_posting))""",
    "insert into purge_exp select expense_id from expenses where status='CANCELLED' or deleted_at is not null",
    """delete from purge_exp where id in (
           select expense_id from cheques
               where expense_id is not null and cheque_id not in (select id from purge_chq)
           union select expense_id from payments
               where expense_id is not null and payment_id not in (select id from purge_pay)
           union select expense_id from financial_postings
               where expense_id is not null and posting_id not in (select id from purge_posting)
           union select expense_id from transactions
               where expense_id is not null and transaction_id not in (select id from purge_tx))""",
]

DELETES = [
    ("expense_payment_links",
     "delete from expense_payment_links where source_pending_id in (select id from purge_pending)"
     " or expense_id in (select id from purge_exp) or payment_id in (select id from purge_pay)"
     " or transaction_id in (select id from purge_tx) or cheque_id in (select id from purge_chq)"),
    ("reminder_log",
     "delete from reminder_log where reminder_id in (select reminder_id from reminders where entity_id in"
     " (select id from purge_inst union select id from purge_chq union select id from purge_sale))"),
    ("reminders",
     "delete from reminders where entity_id in"
     " (select id from purge_inst union select id from purge_chq union select id from purge_sale)"),
    ("payment_allocations",
     "delete from payment_allocations where received_payment_id in (select id from purge_rcv)"
     " or installment_id in (select id from purge_inst)"),
    ("received_payments", "delete from received_payments where received_payment_id in (select id from purge_rcv)"),
    ("installments", "delete from installments where installment_id in (select id from purge_inst)"),
    ("financial_postings", "delete from financial_postings where posting_id in (select id from purge_posting)"),
    ("payments", "delete from payments where payment_id in (select id from purge_pay)"),
    ("financial_document_links", "delete from financial_document_links where document_id in (select id from purge_doc)"),
    ("attachments",
     "delete from attachments where (entity_type='PENDING' and entity_id in (select id from purge_pending))"
     " or (entity_type='EXPENSE' and entity_id in (select id from purge_exp))"
     " or (entity_type='TRANSACTION' and entity_id in (select id from purge_tx))"
     " or (entity_type='SALE_PAYMENT' and entity_id in (select id from purge_rcv))"
     " or (entity_type='SALE' and entity_id in (select id from purge_sale))"
     " or (entity_type='DOCUMENT' and entity_id in (select id from purge_doc))"),
    ("financial_documents", "delete from financial_documents where document_id in (select id from purge_doc)"),
    ("cheques", "delete from cheques where cheque_id in (select id from purge_chq)"),
    ("transactions", "delete from transactions where transaction_id in (select id from purge_tx)"),
    ("expenses", "delete from expenses where expense_id in (select id from purge_exp)"),
    ("sales", "delete from sales where sale_id in (select id from purge_sale)"),
    ("integration_events", "delete from integration_events where pending_id in (select id from purge_pending)"),
    ("posting_revisions", "delete from posting_revisions where pending_id in (select id from purge_pending)"),
    ("receipt_analyses", "delete from receipt_analyses where pending_id in (select id from purge_pending)"),
    ("sync_queue",
     "delete from sync_queue where entity_id in (select id from purge_pending union select id from purge_pay"
     " union select id from purge_tx union select id from purge_exp union select id from purge_posting"
     " union select id from purge_rcv union select id from purge_chq union select id from purge_sale"
     " union select id from purge_inst)"),
    ("telegram_messages",
     "delete from telegram_messages where exists (select 1 from pending_items p"
     " join purge_pending x on x.id=p.pending_id"
     " where p.telegram_chat_id=telegram_messages.chat_id and p.telegram_message_id=telegram_messages.message_id)"
     " or (state in ('REJECTED','DELETED') and not exists (select 1 from pending_items p"
     " where p.telegram_chat_id=telegram_messages.chat_id and p.telegram_message_id=telegram_messages.message_id"
     " and p.pending_id not in (select id from purge_pending)))"),
    ("rich_ui_hidden_reviews", "delete from rich_ui_hidden_reviews where pending_id in (select id from purge_pending)"),
    ("transaction_lifecycle", "delete from transaction_lifecycle where pending_id in (select id from purge_pending)"),
    ("pending_items", "delete from pending_items where pending_id in (select id from purge_pending)"),
]

# Created only once a newer version of the app has opened the project; skipped when absent.
OPTIONAL_TABLES = ("transaction_lifecycle",)

# Records that must be exactly the same before and after; rows being purged are excluded.
LIVE_COUNTS = {
    "pending waiting for review":
        "select count(*) from pending_items where status in ('PENDING_REVIEW','NEEDS_REVIEW','EDIT_PENDING')",
    "pending approved":
        "select count(*) from pending_items where status='APPROVED' and pending_id not in (select id from purge_pending)",
    "expenses":
        "select count(*) from expenses where status<>'CANCELLED' and expense_id not in (select id from purge_exp)",
    "transactions":
        "select count(*) from transactions where status<>'VOIDED' and transaction_id not in (select id from purge_tx)",
    "postings":
        "select count(*) from financial_postings where status<>'DELETED' and posting_id not in (select id from purge_posting)",
    "payments":
        "select count(*) from payments where status<>'CANCELLED' and payment_id not in (select id from purge_pay)",
    "cheques": "select count(*) from cheques where cheque_id not in (select id from purge_chq)",
    "sales": "select count(*) from sales where sale_id not in (select id from purge_sale)",
    "installments": "select count(*) from installments where installment_id not in (select id from purge_inst)",
    "received_payments":
        "select count(*) from received_payments where received_payment_id not in (select id from purge_rcv)",
}


REQUIRED_TABLES = (
    "pending_items", "telegram_messages", "attachments", "receipt_analyses", "integration_events",
    "posting_revisions", "financial_documents", "financial_document_links", "financial_postings",
    "payments", "expenses", "transactions", "cheques", "received_payments", "payment_allocations",
    "sales", "installments", "sync_queue", "rich_ui_hidden_reviews", "expense_payment_links",
    "loan_installments", "receivables", "reminders", "reminder_log", "units",
)


def _project_db(project_id: str | None) -> Path:
    registry = json.loads((APP / 'data' / 'project_registry.json').read_text(encoding='utf-8'))
    projects = registry.get('projects') or []
    wanted = project_id or registry.get('active_project_id') or (projects[0]['project_id'] if projects else '')
    for project in projects:
        if project.get('project_id') == wanted:
            return Path(project['db_path'])
    raise SystemExit(f'Project {wanted!r} is not in data/project_registry.json')


def build_sets(con: sqlite3.Connection, sale_payments: tuple[str, ...] = (), cheques: tuple[str, ...] = (),
               sales: tuple[str, ...] = (), *, all_sales: bool = False, all_cheques: bool = False) -> None:
    for sql in SET_STATEMENTS:
        con.execute(sql)
    if all_sales:
        sales = tuple(row[0] for row in con.execute("select sale_id from sales"))
    if all_cheques:
        cheques = tuple(row[0] for row in con.execute("select cheque_id from cheques"))
    for sale_id in sales:
        if con.execute("select 1 from sales where sale_id=?", (sale_id,)).fetchone() is None:
            raise ValueError(f"unknown sale {sale_id!r}")
        con.execute("insert or ignore into purge_sale values (?)", (sale_id,))
        con.execute("insert or ignore into purge_inst select installment_id from installments where sale_id=?",
                    (sale_id,))
        con.execute("insert or ignore into purge_rcv select received_payment_id from received_payments where sale_id=?",
                    (sale_id,))
    for sale_id in sale_payments:
        if con.execute("select 1 from sales where sale_id=?", (sale_id,)).fetchone() is None:
            raise ValueError(f"unknown sale {sale_id!r}")
        con.execute("insert or ignore into purge_rcv select received_payment_id from received_payments where sale_id=?",
                    (sale_id,))
    for cheque_id in cheques:
        if con.execute("select 1 from cheques where cheque_id=?", (cheque_id,)).fetchone() is None:
            raise ValueError(f"unknown cheque {cheque_id!r}")
        con.execute("insert or ignore into purge_chq values (?)", (cheque_id,))
    for sql in TRANSACTION_STATEMENTS:
        con.execute(sql)


def orphan_files(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(
        "select local_path from attachments where local_path is not null and local_path<>'' and ("
        " (entity_type='PENDING' and entity_id in (select id from purge_pending))"
        " or (entity_type='EXPENSE' and entity_id in (select id from purge_exp))"
        " or (entity_type='TRANSACTION' and entity_id in (select id from purge_tx))"
        " or (entity_type='SALE_PAYMENT' and entity_id in (select id from purge_rcv))"
        " or (entity_type='SALE' and entity_id in (select id from purge_sale))"
        " or (entity_type='DOCUMENT' and entity_id in (select id from purge_doc)))").fetchall()
    return sorted({row[0] for row in rows})


def purge(con: sqlite3.Connection, sale_payments: tuple[str, ...] = (), cheques: tuple[str, ...] = (),
          sales: tuple[str, ...] = (), *, all_sales: bool = False, all_cheques: bool = False):
    """Delete inside the caller's open transaction. Raises on any problem; the caller rolls back."""
    present = {row[0] for row in con.execute("select name from sqlite_master where type='table'")}
    missing = [table for table in REQUIRED_TABLES if table not in present]
    if missing:
        raise RuntimeError(f"the database has no table(s) {missing}; open the project in BARKAV once, then retry")
    build_sets(con, sale_payments, cheques, sales, all_sales=all_sales, all_cheques=all_cheques)
    before = {label: con.execute(sql).fetchone()[0] for label, sql in LIVE_COUNTS.items()}
    files = orphan_files(con)

    deleted: dict[str, int] = {}
    # Like cancelling a sale in the app: free its unit, unless another live sale still holds it.
    freed = con.execute(
        "update units set status='AVAILABLE', updated_at=? where status='SOLD' and unit_id in"
        " (select unit_id from sales where sale_id in (select id from purge_sale)) and unit_id not in"
        " (select unit_id from sales where sale_id not in (select id from purge_sale) and status<>'CANCELLED')",
        (datetime.now().isoformat(timespec='seconds'),)).rowcount
    for table, sql in DELETES:
        if table in OPTIONAL_TABLES and table not in present:
            continue
        try:
            deleted[table] = con.execute(sql).rowcount
        except sqlite3.IntegrityError as exc:
            raise RuntimeError(f"deleting from {table} would break a reference: {exc}") from exc

    broken = con.execute("pragma foreign_key_check").fetchall()
    if broken:
        raise RuntimeError(f"foreign_key_check found {len(broken)} broken references, e.g. {broken[:3]}")
    after = {label: con.execute(sql).fetchone()[0] for label, sql in LIVE_COUNTS.items()}
    changed = {label: (before[label], after[label]) for label in before if before[label] != after[label]}

    if freed:
        deleted["units set back to AVAILABLE"] = freed
    notes = []
    for sale_id in sale_payments:
        for row in con.execute(
                "select installment_id, status, coalesce(paid_amount, 0) from installments where sale_id=? "
                "and (coalesce(paid_amount, 0) > 0 or status in ('PAID','PARTIALLY_PAID'))", (sale_id,)):
            notes.append(f"installment {row[0]} of {sale_id} still says {row[1]} (paid_amount {row[2]}) "
                         "but its receipts were removed")
    return deleted, changed, files, notes


def report(deleted: dict[str, int], files: list[str], notes: list[str]) -> None:
    print("\nrows removed per table")
    for table, count in deleted.items():
        print(f"  {table:26} {count:6}")
    print(f"  {'files left on disk':26} {len(files):6}  (attachments of removed rows; files are NOT deleted)")
    for note in notes:
        print("NOTE:", note)


def _open(path: Path, *, read_only: bool = False, timeout: float = 5) -> sqlite3.Connection:
    target = path.resolve().as_uri() + ("?mode=ro" if read_only else "")
    return sqlite3.connect(target, uri=True, timeout=timeout, isolation_level=None)


def dry_run(db_path: Path, sale_payments: tuple[str, ...], cheques: tuple[str, ...],
            sales: tuple[str, ...] = (), *, all_sales: bool = False, all_cheques: bool = False) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / 'copy.sqlite3'
        source, con = _open(db_path, read_only=True), _open(copy)
        source.backup(con)
        source.close()
        con.execute("pragma foreign_keys=on")
        con.execute("begin immediate")
        try:
            deleted, changed, files, notes = purge(con, sale_payments, cheques, sales, all_sales=all_sales, all_cheques=all_cheques)
        except (RuntimeError, ValueError, sqlite3.DatabaseError) as exc:
            con.close()
            print("DRY RUN FAILED (nothing changed):", exc)
            return 1
        con.rollback()
        con.close()
    report(deleted, files, notes)
    if changed:
        print("\nWARNING - live records would change, the real run would refuse:", changed)
        return 1
    print("\nDry run OK on a copy: live records unchanged, no broken references.")
    print("The real database was not touched.")
    return 0


def apply(db_path: Path, sale_payments: tuple[str, ...], cheques: tuple[str, ...],
          sales: tuple[str, ...] = (), *, all_sales: bool = False, all_cheques: bool = False) -> int:
    if not sys.stdin.isatty():
        print("Refusing: --apply needs an interactive terminal so a person confirms it.")
        return 2
    print(f"Database: {db_path}")
    print("Close BARKAV and the Telegram bot first. This permanently deletes rows.")
    if input("Type PURGE to continue: ").strip() != "PURGE":
        print("Cancelled.")
        return 2

    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    # Next to the database itself (outside the repo), wherever this script is run from.
    backups = db_path.parent / '.barkav-migration-backups'
    backups.mkdir(exist_ok=True)
    backup = backups / f"before_purge_{stamp}{db_path.suffix}"
    source, target = _open(db_path, read_only=True), sqlite3.connect(backup)
    source.backup(target)
    source.close()
    target.close()
    check = _open(backup, read_only=True)
    healthy = check.execute("pragma integrity_check").fetchone()[0] == "ok"
    check.close()
    if not healthy:
        print("Backup failed its integrity check; stopping. Nothing was changed.")
        return 1
    print("Backup written and verified:", backup)

    con = _open(db_path)
    con.execute("pragma foreign_keys=on")
    try:
        con.execute("begin immediate")
    except sqlite3.OperationalError as exc:
        con.close()
        print("Database is busy - close BARKAV and try again:", exc)
        return 1
    try:
        deleted, changed, files, notes = purge(con, sale_payments, cheques, sales, all_sales=all_sales, all_cheques=all_cheques)
        if changed:
            raise RuntimeError(f"live records would change: {changed}")
        if con.execute("pragma integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("integrity_check failed")
    except (RuntimeError, ValueError, sqlite3.DatabaseError) as exc:
        con.rollback()
        con.close()
        print("ROLLED BACK, database unchanged:", exc)
        return 1
    con.commit()
    con.execute("pragma wal_checkpoint(truncate)")
    con.close()

    listing = backups / f"orphan_files_{stamp}.txt"
    listing.write_text("\n".join(files), encoding='utf-8')
    report(deleted, files, notes)
    print("\nDone. Backup:", backup)
    print("Orphan file list:", listing)
    print("To undo: close BARKAV and replace the database with the backup file.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--project', help='project id (default: the active or first project)')
    parser.add_argument('--db', type=Path, help='database file (default: the project database)')
    parser.add_argument('--apply', action='store_true', help='back up the database, then delete for real')
    parser.add_argument('--test-sale-payments', action='append', default=[], metavar='SALE_ID',
                        help='also delete all received payments of this test sale (repeatable)')
    parser.add_argument('--test-sale', action='append', default=[], metavar='SALE_ID',
                        help='also delete this whole test sale: installments, receipts, reminders (repeatable)')
    parser.add_argument('--test-cheque', action='append', default=[], metavar='CHEQUE_ID',
                        help='also delete this test cheque (repeatable)')
    parser.add_argument('--empty-income', action='store_true',
                        help='delete every sale with its installments, receipts, reminders and attachments')
    parser.add_argument('--empty-cheques', action='store_true', help='delete every cheque')
    args = parser.parse_args()
    db_path = args.db or _project_db(args.project)
    if not db_path.exists():
        print("Database not found:", db_path)
        return 2
    payments, cheques, sales = tuple(args.test_sale_payments), tuple(args.test_cheque), tuple(args.test_sale)
    flags = {'all_sales': args.empty_income, 'all_cheques': args.empty_cheques}
    if args.apply:
        return apply(db_path, payments, cheques, sales, **flags)
    return dry_run(db_path, payments, cheques, sales, **flags)


if __name__ == '__main__':
    raise SystemExit(main())
