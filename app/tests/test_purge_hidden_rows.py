from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ.setdefault('STAGE4_DB_PATH', str(Path(_BOOT.name) / 'purge.sqlite3'))
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'purge-token')
os.environ.setdefault('GEMINI_API_KEY', 'purge-gemini')
os.environ.setdefault('ADMIN_USER_ID', '1')
os.environ.setdefault('GROUP_CHAT_ID', '-1001')

from finance_db import FinanceDB  # noqa: E402

_spec = importlib.util.spec_from_file_location('purge_hidden_rows', ROOT / 'tools' / 'purge_hidden_rows.py')
purge_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(purge_tool)

# Tables other feature modules create lazily; the tool needs them to exist.
LAZY_TABLES = """
CREATE TABLE IF NOT EXISTS financial_documents(document_id TEXT PRIMARY KEY, pending_id TEXT,
  document_type TEXT NOT NULL DEFAULT 'OTHER', event_date_shamsi TEXT, description TEXT,
  amount INTEGER NOT NULL DEFAULT 0, raw_text TEXT, status TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS financial_document_links(
  document_id TEXT NOT NULL REFERENCES financial_documents(document_id), entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(document_id, entity_type, entity_id));
CREATE TABLE IF NOT EXISTS payment_allocations(allocation_id TEXT PRIMARY KEY,
  received_payment_id TEXT NOT NULL REFERENCES received_payments(received_payment_id),
  installment_id TEXT NOT NULL REFERENCES installments(installment_id),
  amount INTEGER NOT NULL CHECK(amount > 0), created_at TEXT NOT NULL,
  UNIQUE(received_payment_id, installment_id));
CREATE TABLE IF NOT EXISTS rich_ui_hidden_reviews(pending_id TEXT PRIMARY KEY,
  hidden INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS transaction_lifecycle(pending_id TEXT PRIMARY KEY REFERENCES pending_items(pending_id),
  state TEXT NOT NULL CHECK(state IN ('ACTIVE','REJECTED','PURGED')), effects_json TEXT NOT NULL,
  rejected_json TEXT NOT NULL DEFAULT '[]', contract_json TEXT NOT NULL DEFAULT '[]', payload_json TEXT NOT NULL,
  message_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS expense_payment_links(link_id TEXT PRIMARY KEY, expense_id TEXT NOT NULL,
  payment_id TEXT, transaction_id TEXT, cheque_id TEXT, source_pending_id TEXT,
  amount INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
"""
NOW = '2026-09-30T10:00:00'
PLACEHOLDERS = {'method': 'CASH'}


def _add(con, table, **values):
    """Insert a row, filling every other required column with a harmless placeholder."""
    for _cid, name, kind, notnull, default, _pk in con.execute(f'pragma table_info({table})').fetchall():
        if name in values or not notnull or default is not None:
            continue
        values[name] = PLACEHOLDERS.get(name, 0 if 'INT' in (kind or '').upper() else (
            '{}' if name.endswith('_json') else NOW if name.endswith('_at') else 'x'))
    names = ', '.join(values)
    con.execute(f'insert into {table}({names}) values ({", ".join("?" * len(values))})', tuple(values.values()))


def _pending(con, pid, status, message_id, hidden=None):
    _add(con, 'pending_items', pending_id=pid, telegram_chat_id=-1, telegram_message_id=message_id, status=status)
    _add(con, 'telegram_messages', chat_id=-1, message_id=message_id, state=status if status != 'APPROVED' else 'APPROVED')
    _add(con, 'attachments', entity_type='PENDING', entity_id=pid, local_path=f'{pid}.jpg')
    if hidden is not None:
        _add(con, 'rich_ui_hidden_reviews', pending_id=pid, hidden=hidden, updated_at=NOW)


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / 'project.sqlite3'
    FinanceDB(path)
    con = sqlite3.connect(path, isolation_level=None)
    con.executescript(LAZY_TABLES)

    # review cards: two gone (rejected / approved-then-hidden), three that must stay
    _pending(con, 'PEN-REJ', 'REJECTED', 1, hidden=1)
    _pending(con, 'PEN-HID', 'APPROVED', 2, hidden=1)
    _pending(con, 'PEN-OPEN', 'PENDING_REVIEW', 3, hidden=0)
    _pending(con, 'PEN-OK', 'APPROVED', 4, hidden=0)
    _pending(con, 'PEN-EDIT', 'EDIT_PENDING', 5, hidden=0)
    _pending(con, 'PEN-HIDOPEN', 'NEEDS_REVIEW', 6, hidden=1)   # hidden but still waiting: never purged
    _pending(con, 'PEN-LIVEHID', 'APPROVED', 7, hidden=1)       # hidden, but a live posting needs it
    _add(con, 'receipt_analyses', pending_id='PEN-REJ', status='REJECTED')
    _add(con, 'transaction_lifecycle', pending_id='PEN-REJ', state='REJECTED')
    _add(con, 'transaction_lifecycle', pending_id='PEN-OK', state='ACTIVE')

    # one live expense (needs PEN-EDIT) and one cancelled one
    _add(con, 'expenses', expense_id='EX-LIVE', status='PAID', final_amount=10)
    _add(con, 'transactions', transaction_id='TX-LIVE', status='POSTED', expense_id='EX-LIVE', direction='OUT', amount=10)
    _add(con, 'payments', payment_id='PAY-LIVE', expense_id='EX-LIVE', status='COMPLETED', transaction_id='TX-LIVE')
    _add(con, 'financial_postings', posting_id='POST-LIVE', pending_id='PEN-EDIT', status='ACTIVE',
         expense_id='EX-LIVE', transaction_id='TX-LIVE')
    _add(con, 'financial_postings', posting_id='POST-LIVE2', pending_id='PEN-LIVEHID', status='ACTIVE',
         expense_id='EX-LIVE', transaction_id='TX-LIVE')
    _add(con, 'expenses', expense_id='EX-GONE', status='CANCELLED', final_amount=5, deleted_at=NOW)
    _add(con, 'transactions', transaction_id='TX-GONE', status='VOIDED', expense_id='EX-GONE', direction='OUT',
         amount=5, deleted_at=NOW)
    _add(con, 'payments', payment_id='PAY-GONE', expense_id='EX-GONE', status='CANCELLED', transaction_id='TX-GONE')
    _add(con, 'financial_postings', posting_id='POST-GONE', pending_id='PEN-HID', status='DELETED',
         expense_id='EX-GONE', transaction_id='TX-GONE', deleted_at=NOW)

    # a sale whose receipts and cash cheque are backed by voided transactions
    _add(con, 'units', unit_id='UNIT-1', unit_number='1', status='SOLD')
    _add(con, 'sales', sale_id='SALE-T', unit_id='UNIT-1', buyer_name='b', status='ACTIVE')
    _add(con, 'installments', installment_id='INS-1', sale_id='SALE-T', status='PAID', paid_amount=7)
    _add(con, 'reminders', reminder_id='REM-1', entity_type='INSTALLMENT', entity_id='INS-1', status='SCHEDULED')
    _add(con, 'reminder_log', reminder_id='REM-1', channel='TELEGRAM', success=1)
    _add(con, 'attachments', entity_type='SALE', entity_id='SALE-T', local_path='sale-t.pdf')
    # a real sale that has nothing to do with the test data and must survive every run
    _add(con, 'units', unit_id='UNIT-2', unit_number='2', status='SOLD')
    _add(con, 'sales', sale_id='SALE-KEEP', unit_id='UNIT-2', buyer_name='k', status='ACTIVE')
    _add(con, 'installments', installment_id='INS-KEEP', sale_id='SALE-KEEP', status='UPCOMING')
    _add(con, 'reminders', reminder_id='REM-KEEP', entity_type='INSTALLMENT', entity_id='INS-KEEP', status='SCHEDULED')
    _add(con, 'reminder_log', reminder_id='REM-KEEP', channel='TELEGRAM', success=1)
    _add(con, 'attachments', entity_type='SALE', entity_id='SALE-KEEP', local_path='sale-keep.pdf')
    for index in (1, 2):
        _add(con, 'transactions', transaction_id=f'TX-RCV{index}', status='VOIDED', direction='IN', amount=7, deleted_at=NOW)
        _add(con, 'received_payments', received_payment_id=f'RCV-{index}', sale_id='SALE-T',
             transaction_id=f'TX-RCV{index}', amount=7, status='MATCHED')
    _add(con, 'payment_allocations', allocation_id='ALLOC-1', received_payment_id='RCV-1',
         installment_id='INS-1', amount=7)
    _add(con, 'attachments', entity_type='SALE_PAYMENT', entity_id='RCV-1', local_path='rcv1.jpg')
    _add(con, 'transactions', transaction_id='TX-CHQ', status='VOIDED', direction='OUT', amount=3, deleted_at=NOW)
    _add(con, 'cheques', cheque_id='CHQ-T', status='CASHED', cash_transaction_id='TX-CHQ', amount=3)
    con.close()
    return path


def _counts(path):
    con = sqlite3.connect(path)
    tables = ('pending_items', 'telegram_messages', 'attachments', 'expenses', 'transactions', 'payments',
              'financial_postings', 'received_payments', 'payment_allocations', 'cheques', 'sales', 'installments')
    counts = {table: con.execute(f'select count(*) from {table}').fetchone()[0] for table in tables}
    con.close()
    return counts


def _ids(path, sql):
    con = sqlite3.connect(path)
    found = {row[0] for row in con.execute(sql)}
    con.close()
    return found


def _run(path, sale_payments=(), cheques=(), sales=(), **flags):
    con = sqlite3.connect(path, isolation_level=None)
    con.execute('pragma foreign_keys=on')
    con.execute('begin immediate')
    result = purge_tool.purge(con, sale_payments, cheques, sales, **flags)
    con.commit()
    con.close()
    return result


def test_rejected_and_hidden_rows_go_and_everything_still_live_stays(db):
    deleted, changed, files, notes = _run(db)

    assert changed == {}
    assert _ids(db, 'select pending_id from pending_items') == {'PEN-OPEN', 'PEN-OK', 'PEN-EDIT', 'PEN-HIDOPEN', 'PEN-LIVEHID'}
    assert _ids(db, 'select message_id from telegram_messages') == {3, 4, 5, 6, 7}
    assert _ids(db, "select entity_id from attachments where entity_type='PENDING'") == {'PEN-OPEN', 'PEN-OK', 'PEN-EDIT', 'PEN-HIDOPEN', 'PEN-LIVEHID'}
    assert _ids(db, 'select pending_id from receipt_analyses') == set()
    assert _ids(db, 'select pending_id from transaction_lifecycle') == {'PEN-OK'}
    assert _ids(db, 'select pending_id from rich_ui_hidden_reviews') == {'PEN-OPEN', 'PEN-OK', 'PEN-EDIT', 'PEN-HIDOPEN', 'PEN-LIVEHID'}
    assert _ids(db, 'select expense_id from expenses') == {'EX-LIVE'}
    assert _ids(db, 'select payment_id from payments') == {'PAY-LIVE'}
    assert _ids(db, 'select posting_id from financial_postings') == {'POST-LIVE', 'POST-LIVE2'}
    assert {'TX-LIVE'} <= _ids(db, 'select transaction_id from transactions')
    assert 'TX-GONE' not in _ids(db, 'select transaction_id from transactions')
    assert sorted(files) == ['PEN-HID.jpg', 'PEN-REJ.jpg']


def test_voided_transactions_that_live_records_use_stay_unless_the_test_data_is_named(db):
    _run(db)

    assert {'TX-RCV1', 'TX-RCV2', 'TX-CHQ'} <= _ids(db, 'select transaction_id from transactions')
    assert _ids(db, 'select received_payment_id from received_payments') == {'RCV-1', 'RCV-2'}
    assert _ids(db, 'select cheque_id from cheques') == {'CHQ-T'}


def test_named_test_receipts_and_cheque_are_removed_with_their_voided_transactions(db):
    deleted, changed, files, notes = _run(db, sale_payments=('SALE-T',), cheques=('CHQ-T',))

    assert changed == {}
    assert _ids(db, 'select received_payment_id from received_payments') == set()
    assert _ids(db, 'select allocation_id from payment_allocations') == set()
    assert _ids(db, 'select cheque_id from cheques') == set()
    assert _ids(db, 'select transaction_id from transactions') == {'TX-LIVE'}
    assert _ids(db, "select entity_id from attachments where entity_type='SALE_PAYMENT'") == set()
    assert 'rcv1.jpg' in files
    # the sale itself is not what was named here: it stays, and the stale installment is called out
    assert _ids(db, 'select sale_id from sales') == {'SALE-T', 'SALE-KEEP'}
    assert _ids(db, 'select installment_id from installments') == {'INS-1', 'INS-KEEP'}
    assert any('INS-1' in note and 'PAID' in note for note in notes)


def test_a_named_test_sale_goes_whole_and_its_unit_is_freed_like_a_cancellation(db):
    deleted, changed, files, notes = _run(db, cheques=('CHQ-T',), sales=('SALE-T',))

    assert changed == {}
    assert notes == []
    assert _ids(db, 'select sale_id from sales') == {'SALE-KEEP'}
    assert _ids(db, 'select installment_id from installments') == {'INS-KEEP'}
    assert _ids(db, 'select received_payment_id from received_payments') == set()
    assert _ids(db, 'select allocation_id from payment_allocations') == set()
    assert _ids(db, 'select reminder_id from reminders') == {'REM-KEEP'}
    assert _ids(db, 'select reminder_id from reminder_log') == {'REM-KEEP'}
    assert _ids(db, "select entity_id from attachments where entity_type='SALE'") == {'SALE-KEEP'}
    assert {'sale-t.pdf', 'rcv1.jpg'} <= set(files) and 'sale-keep.pdf' not in files
    assert _ids(db, 'select transaction_id from transactions') == {'TX-LIVE'}
    assert _ids(db, "select unit_id from units where status='AVAILABLE' and unit_id like 'UNIT-%'") == {'UNIT-1'}
    assert _ids(db, "select unit_id from units where status='SOLD'") == {'UNIT-2'}
    assert deleted['units set back to AVAILABLE'] == 1


def test_a_unit_another_live_sale_still_holds_is_not_freed(db):
    con = sqlite3.connect(db, isolation_level=None)
    _add(con, 'sales', sale_id='SALE-SHARED', unit_id='UNIT-1', buyer_name='s', status='ACTIVE')
    con.close()

    _run(db, sales=('SALE-T',))

    assert _ids(db, "select status from units where unit_id='UNIT-1'") == {'SOLD'}


def test_a_failure_part_way_rolls_every_deletion_back(db, monkeypatch):
    before = _counts(db)
    monkeypatch.setattr(purge_tool, 'DELETES', purge_tool.DELETES + [('sales', 'delete from sales')])
    con = sqlite3.connect(db, isolation_level=None)
    con.execute('pragma foreign_keys=on')
    con.execute('begin immediate')

    with pytest.raises(RuntimeError, match='sales'):
        purge_tool.purge(con)
    con.rollback()
    con.close()

    assert _counts(db) == before


def test_unknown_test_ids_are_refused(db):
    con = sqlite3.connect(db, isolation_level=None)
    con.execute('begin immediate')

    with pytest.raises(ValueError, match='NOPE'):
        purge_tool.purge(con, ('NOPE',), ())
    con.rollback()
    con.close()


def test_dry_run_reports_but_never_touches_the_database(db, capsys):
    before = _counts(db)

    assert purge_tool.dry_run(db, ('SALE-T',), ('CHQ-T',)) == 0

    assert _counts(db) == before
    assert 'pending_items' in capsys.readouterr().out


def test_apply_needs_a_person_at_a_terminal(db, monkeypatch):
    before = _counts(db)
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: False)

    assert purge_tool.apply(db, (), ()) == 2
    assert _counts(db) == before


def test_a_database_missing_a_table_the_tool_needs_is_refused_untouched(tmp_path):
    path = tmp_path / 'bare.sqlite3'
    FinanceDB(path)
    con = sqlite3.connect(path, isolation_level=None)
    con.execute('begin immediate')

    with pytest.raises(RuntimeError, match='no table'):
        purge_tool.purge(con)
    con.rollback()
    con.close()


def test_apply_backs_up_next_to_the_database_then_purges(db, monkeypatch, capsys):
    before = _counts(db)
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr('builtins.input', lambda _prompt='': 'PURGE')

    assert purge_tool.apply(db, ('SALE-T',), ('CHQ-T',)) == 0

    backups = list((db.parent / '.barkav-migration-backups').glob('before_purge_*.sqlite3'))
    assert len(backups) == 1 and _counts(backups[0]) == before
    assert _ids(db, 'select pending_id from pending_items') == {
        'PEN-OPEN', 'PEN-OK', 'PEN-EDIT', 'PEN-HIDOPEN', 'PEN-LIVEHID'}
    assert _ids(db, 'select cheque_id from cheques') == set()
    listing = next((db.parent / '.barkav-migration-backups').glob('orphan_files_*.txt'))
    assert 'PEN-REJ.jpg' in listing.read_text(encoding='utf-8')


def test_apply_does_nothing_unless_purge_is_typed(db, monkeypatch):
    before = _counts(db)
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr('builtins.input', lambda _prompt='': 'yes')

    assert purge_tool.apply(db, (), ()) == 2
    assert _counts(db) == before
    assert not (db.parent / '.barkav-migration-backups').exists()


def test_a_project_the_newer_app_has_not_opened_yet_has_no_lifecycle_table(db):
    con = sqlite3.connect(db, isolation_level=None)
    con.execute('drop table transaction_lifecycle')
    con.close()

    deleted, changed, files, notes = _run(db)

    assert changed == {}
    assert 'transaction_lifecycle' not in deleted
    assert 'PEN-REJ' not in _ids(db, 'select pending_id from pending_items')


def _more(path, fn):
    con = sqlite3.connect(path, isolation_level=None)
    fn(con)
    con.close()


def test_empty_income_removes_every_sale_and_what_it_posted_but_no_other_record(db):
    def extra(con):
        _add(con, 'units', unit_id='UNIT-3', unit_number='3')
        _add(con, 'sales', sale_id='SALE-CANC', unit_id='UNIT-3', buyer_name='c', status='CANCELLED')
        _add(con, 'installments', installment_id='INS-CANC', sale_id='SALE-CANC', status='CANCELLED')
        _add(con, 'transactions', transaction_id='TX-LIVEIN', status='POSTED', direction='IN', amount=9, sale_id='SALE-KEEP')
        _add(con, 'received_payments', received_payment_id='RCV-LIVE', sale_id='SALE-KEEP',
             transaction_id='TX-LIVEIN', amount=9, status='MATCHED')
        # reachable only through the receipt (no sale_id on it), and only through the sale (no receipt)
        _add(con, 'transactions', transaction_id='TX-VIA-RCV', status='POSTED', direction='IN', amount=8)
        _add(con, 'received_payments', received_payment_id='RCV-LIVE2', sale_id='SALE-KEEP',
             transaction_id='TX-VIA-RCV', amount=8, status='MATCHED')
        _add(con, 'transactions', transaction_id='TX-VIA-SALE', status='POSTED', direction='IN', amount=6, sale_id='SALE-CANC')
    _more(db, extra)

    deleted, changed, files, notes = _run(db, all_sales=True)

    assert changed == {}
    assert _ids(db, 'select sale_id from sales') == set()
    assert _ids(db, 'select installment_id from installments') == set()
    assert _ids(db, 'select received_payment_id from received_payments') == set()
    assert _ids(db, 'select reminder_id from reminders') == set()
    assert _ids(db, "select entity_id from attachments where entity_type in ('SALE','SALE_PAYMENT')") == set()
    # the live receipt's ledger row goes too; the cheque, its cash transaction and the live expense stay
    assert _ids(db, 'select transaction_id from transactions') == {'TX-LIVE', 'TX-CHQ'}
    assert _ids(db, 'select cheque_id from cheques') == {'CHQ-T'}
    assert _ids(db, "select unit_id from units where status='SOLD'") == set()
    assert deleted['units set back to AVAILABLE'] == 2


def test_empty_cheques_removes_every_cheque_and_its_cash_transaction(db):
    def extra(con):
        _add(con, 'cheques', cheque_id='CHQ-2', status='ISSUED', amount=4)
        _add(con, 'transactions', transaction_id='TX-CASH3', status='POSTED', direction='OUT', amount=5)
        _add(con, 'cheques', cheque_id='CHQ-3', status='CASHED', cash_transaction_id='TX-CASH3', amount=5)
    _more(db, extra)

    deleted, changed, files, notes = _run(db, all_cheques=True)

    assert changed == {}
    assert _ids(db, 'select cheque_id from cheques') == set()
    assert _ids(db, 'select transaction_id from transactions where transaction_id like "TX-CHQ" or transaction_id like "TX-CASH%"') == set()
    assert 'TX-LIVE' in _ids(db, 'select transaction_id from transactions')
    assert _ids(db, 'select received_payment_id from received_payments') == {'RCV-1', 'RCV-2'}


def test_a_cheque_a_live_payment_still_uses_stops_the_whole_run_untouched(db):
    def extra(con):
        _add(con, 'cheques', cheque_id='CHQ-USED', status='ISSUED', amount=4)
        _add(con, 'payments', payment_id='PAY-CHQ', expense_id='EX-LIVE', status='COMPLETED', cheque_id='CHQ-USED')
    _more(db, extra)
    before = _counts(db)
    con = sqlite3.connect(db, isolation_level=None)
    con.execute('pragma foreign_keys=on')
    con.execute('begin immediate')

    with pytest.raises(RuntimeError, match='cheques'):
        purge_tool.purge(con, all_cheques=True)
    con.rollback()
    con.close()

    assert _counts(db) == before
