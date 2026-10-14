"""Record what a user action changed in SQLite, so it can be undone and redone.

While a user action runs on the main (Tk) thread, every ``FinanceDB.tx()``
block is watched: SQLite's authorizer tells us which tables the block is about
to write, and when the block finishes the rows of those tables are compared
with their last committed state. That gives the exact rows an action changed,
whichever screen or service made the change, with no per-screen instrumentation.

Undo writes the earlier rows back and redo writes the later rows again, in one
transaction, after checking that the rows still look exactly as the action left
them. If anything changed in between, the undo is refused with a Persian
message and nothing is written. Every restore adds an ``audit_log`` entry and,
for the tables the Sheets mirror follows, a ``sync_queue`` row, so an undo is
as traceable and as visible to the mirror as the action it reverses. Nothing
is ever physically deleted: a row an action *inserted* is undone by marking it
cancelled or voided, exactly as the app's own delete does.

What is deliberately not undone: hard deletes and inserts into tables with no
soft-cancel meaning. Such an action is still recorded, as not undoable, so
that pressing Undo says so plainly instead of silently reversing an older step.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Callable

from action_history import HistoryAction, UndoRefused

log = logging.getLogger(__name__)

#: Tables whose changes are bookkeeping about a change, never part of one.
IGNORED_TABLES = frozenset({
    'audit_log', 'sync_queue', 'integration_events', 'rich_change_history',
    'reminder_log', 'app_meta', 'settings', 'sqlite_sequence', 'learned_rules',
    'attachments', 'receipt_analyses',
})
#: Columns rewritten by background work or on every write; never compared.
VOLATILE_COLUMNS = frozenset({'updated_at', 'sync_status'})
#: Tables the Sheets mirror follows, and the entity name its queue uses.
SYNC_ENTITY = {
    'transactions': 'transaction', 'expenses': 'expense',
    'payments': 'payment', 'cheques': 'cheque',
}

_NOW = object()
#: How an *inserted* row is undone: the same soft state the app's own delete uses.
SOFT_CANCEL: dict[str, dict[str, Any]] = {
    'transaction_lifecycle': {'state': 'ACTIVE'},
    'transactions': {'status': 'VOIDED', 'deleted_at': _NOW},
    'expenses': {'status': 'CANCELLED', 'deleted_at': _NOW},
    'payments': {'status': 'CANCELLED'},
    'cheques': {'status': 'CANCELLED'},
    'loans': {'status': 'CANCELLED'},
    'loan_installments': {'status': 'CANCELLED'},
    'sales': {'status': 'CANCELLED'},
    'installments': {'status': 'CANCELLED'},
    'reminders': {'status': 'CANCELLED'},
    'rich_phase_items': {'active': 0},
    'rich_price_items': {'active': 0},
    'rich_price_components': {'active': 0},
}
_CANCELLED_STATES = frozenset({'VOIDED', 'CANCELLED', 'DELETED'})

_NOUN = {
    'transactions': 'تراکنش', 'expenses': 'هزینه', 'cheques': 'چک', 'payments': 'پرداخت',
    'loans': 'وام', 'sales': 'قرارداد فروش', 'reconciliations': 'تطبیق بانک',
    'units': 'واحد', 'financial_postings': 'ثبت مالی', 'loan_installments': 'قسط وام',
    'installments': 'قسط فروش', 'construction_phases': 'فاز',
    'rich_phase_items': 'ردیف فاز', 'rich_price_items': 'قیمت',
    'rich_price_components': 'جزء قیمت', 'receivables': 'مطالبه',
    'received_payments': 'دریافتی', 'pending_items': 'ردیف ثبت دیتا',
    'telegram_messages': 'پیام', 'posting_revisions': 'اصلاحیهٔ ثبت',
    'phase_progress_v163': 'پیشرفت فاز',
}
_NOUN_PRIORITY = tuple(_NOUN)


@dataclass(frozen=True)
class RowChange:
    """One row an action changed: ``before``/``after`` are None for insert/delete."""

    table: str
    pk_columns: tuple[str, ...]
    pk: tuple
    op: str
    before: dict | None
    after: dict | None


@dataclass
class _Step:
    table: str
    pk_columns: tuple[str, ...]
    pk: tuple
    expect: dict
    target: dict


_STATE = SimpleNamespace(sink=None, gate=lambda: True, original_tx=None)
_LOCAL = threading.local()


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


#: Cache columns a screen recomputes from other rows; never recorded, compared or restored.
VOLATILE_BY_TABLE: dict[str, frozenset[str]] = {
    'rich_phase_items': frozenset({'total_actual'}),
}
#: Statuses the app re-derives on every read (from dates and paid amounts). A move
#: between them is not something the user did, so it is neither recorded nor
#: compared; only leaving or entering the cancelled state is.
DERIVED_STATUSES: dict[str, frozenset[str]] = {
    'loan_installments': frozenset({'UPCOMING', 'DUE', 'PARTIALLY_PAID', 'PAID', 'OVERDUE'}),
    'installments': frozenset({'UPCOMING', 'DUE', 'PARTIALLY_PAID', 'PAID', 'OVERDUE'}),
    'sales': frozenset({'ACTIVE', 'COMPLETED'}),
}
#: Rows the app itself creates on reads; they are never part of a user action.
IGNORED_INSERT_TABLES = frozenset({'reminders'})
#: An action touching more rows than this is recorded as not undoable, without keeping the rows.
MAX_ROWS = 2000


def _stable(row: dict, table: str = '') -> dict:
    skip = VOLATILE_COLUMNS | VOLATILE_BY_TABLE.get(table, frozenset())
    kept = {key: value for key, value in row.items() if key not in skip}
    derived = DERIVED_STATUSES.get(table)
    if derived and kept.get('status') in derived:
        kept['status'] = 'LIVE'
    return kept


def _digits(number: int) -> str:
    return str(number).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


# ------------------------------------------------------------------ reading
def _columns(con: sqlite3.Connection, table: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    info = con.execute(f'PRAGMA table_info("{table}")').fetchall()
    names = tuple(row[1] for row in info)
    pk = tuple(name for _order, name in sorted((row[5], row[1]) for row in info if row[5]))
    return pk, names


def _read_table(con: sqlite3.Connection, table: str, pk_columns: tuple[str, ...]) -> dict[tuple, dict]:
    rows = {}
    for row in con.execute(f'SELECT * FROM "{table}"').fetchall():
        record = dict(row)
        rows[tuple(record[column] for column in pk_columns)] = record
    return rows


def diff_tables(db_path: str, con: sqlite3.Connection, tables: list[str]) -> list[RowChange]:
    """Compare each table's committed state with what ``con`` sees now."""
    changes: list[RowChange] = []
    reader = sqlite3.connect(db_path, timeout=5)
    reader.row_factory = sqlite3.Row
    try:
        for table in tables:
            pk_columns, _names = _columns(con, table)
            if not pk_columns:
                continue
            before = _read_table(reader, table, pk_columns)
            after = _read_table(con, table, pk_columns)
            for key in list(after) + [key for key in before if key not in after]:
                old, new = before.get(key), after.get(key)
                if old is None and new is not None:
                    if table not in IGNORED_INSERT_TABLES:
                        changes.append(RowChange(table, pk_columns, key, 'INSERT', None, new))
                elif new is None and old is not None:
                    changes.append(RowChange(table, pk_columns, key, 'DELETE', old, None))
                elif old is not None and new is not None and _stable(old, table) != _stable(new, table):
                    changes.append(RowChange(table, pk_columns, key, 'UPDATE', old, new))
    finally:
        reader.close()
    return changes


# ------------------------------------------------------------ transaction hook
_AUTH_OK = getattr(sqlite3, 'SQLITE_OK', 0)
_AUTH_WRITES = frozenset({
    getattr(sqlite3, 'SQLITE_INSERT', 18),
    getattr(sqlite3, 'SQLITE_UPDATE', 23),
    getattr(sqlite3, 'SQLITE_DELETE', 9),
})


def _writes_collector(touched: set[str]) -> Callable[..., int]:
    def authorizer(action, table, _column, _database, _source):
        if action in _AUTH_WRITES and table:
            touched.add(str(table))
        return _AUTH_OK

    return authorizer


def _watching() -> bool:
    if _STATE.sink is None or getattr(_LOCAL, 'suspended', False):
        return False
    if threading.current_thread() is not threading.main_thread():
        return False
    try:
        return bool(_STATE.gate())
    except Exception:  # a broken gate must never affect a database write
        return False


@contextmanager
def _journaling_tx(self):
    if self._session_state().get('writer') is not None:
        with _STATE.original_tx(self) as con:
            yield con
        return
    with _STATE.original_tx(self) as con:
        touched: set[str] = set()
        started = None
        if _watching():
            try:
                started = con.total_changes
                con.set_authorizer(_writes_collector(touched))
            except Exception:
                log.exception('Row journal could not start; this write is not recorded')
                started = None
        yield con
        changes: list[RowChange] = []
        if started is not None:
            # Runs before the commit, and must never raise: an error here would
            # roll back a write the user asked for.
            try:
                con.set_authorizer(None)
                tables = sorted(name for name in touched if name not in IGNORED_TABLES)
                if tables and con.total_changes != started:
                    changes = diff_tables(self.db_path, con, tables)
            except Exception:
                log.exception('Row journal could not compare rows; this write is not recorded')
                changes = []
    if changes:
        try:
            _STATE.sink(self, changes)
        except Exception:
            log.exception('Row journal sink failed')


def install(sink: Callable[[Any, list[RowChange]], None],
            gate: Callable[[], bool] | None = None) -> None:
    """Start recording. ``sink(db, changes)`` receives each committed block's changes.

    ``gate`` says whether a write happening right now is a user action worth
    recording; it is asked once per write, on the main thread only.
    """
    from finance_db import FinanceDB

    if _STATE.original_tx is None:
        _STATE.original_tx = FinanceDB.tx
    _STATE.sink = sink
    _STATE.gate = gate or (lambda: True)
    FinanceDB.tx = _journaling_tx


def uninstall() -> None:
    from finance_db import FinanceDB

    if _STATE.original_tx is not None:
        FinanceDB.tx = _STATE.original_tx
        _STATE.original_tx = None
    _STATE.sink = None
    _STATE.gate = lambda: True


@contextmanager
def suspended():
    """Writes made inside are not recorded (undo and redo write this way)."""
    previous = getattr(_LOCAL, 'suspended', False)
    _LOCAL.suspended = True
    try:
        yield
    finally:
        _LOCAL.suspended = previous


# ------------------------------------------------------------------ actions
def _soft_cancelled(change: RowChange) -> dict | None:
    rules = SOFT_CANCEL.get(change.table)
    if rules is None or change.after is None:
        return None
    row = dict(change.after)
    for column, value in rules.items():
        if column in row:
            row[column] = _now() if value is _NOW else value
    return row


def _not_undoable_reason(changes: list[RowChange]) -> str:
    for change in changes:
        if change.table=='transaction_lifecycle':
            if (change.after or {}).get('state')=='PURGED':return 'حذف کامل قابل بازگردانی نیست.'
            if change.op=='INSERT' and (change.after or {}).get('state')=='ACTIVE':return 'تأیید ثبت از طریق رد رکورد برگشت داده می‌شود.'
    if any(change.table=='transaction_lifecycle' and (change.after or {}).get('contract_json') not in (None,'[]') for change in changes):
        return 'این عملیات رسید قرارداد هم دارد؛ از بازگردانی ثبت دیتا استفاده کنید.'
    if any(change.op == 'DELETE' for change in changes):
        return 'ردیف‌هایی به‌طور کامل حذف شده‌اند.'
    for change in changes:
        if change.op == 'INSERT' and _soft_cancelled(change) is None:
            return 'رکوردی ساخته شده که لغو امن ندارد.'
    return ''


def _is_removal(change: RowChange) -> bool:
    """True when the change deletes, cancels, voids or deactivates its row."""
    if change.op == 'DELETE':
        return True
    if change.op != 'UPDATE' or change.after is None:
        return False
    before = change.before or {}
    after = change.after
    if str(after.get('status') or '') in _CANCELLED_STATES and str(before.get('status') or '') not in _CANCELLED_STATES:
        return True
    if after.get('deleted_at') and not before.get('deleted_at'):
        return True
    return 'active' in after and after.get('active') == 0 and bool(before.get('active'))


def describe(changes: list[RowChange]) -> str:
    """A short Persian name for the action, like «حذف ۳ تراکنش»."""
    tables = {change.table for change in changes}
    main = next((name for name in _NOUN_PRIORITY if name in tables), sorted(tables)[0])
    own = [change for change in changes if change.table == main]
    if any(_is_removal(change) for change in own):
        verb = 'حذف'
    elif all(change.op == 'INSERT' for change in own):
        verb = 'افزودن'
    else:
        verb = 'ویرایش'
    noun = _NOUN.get(main, 'رکورد')
    count = len(own)
    return f'{verb} {_digits(count)} {noun}' if count > 1 else f'{verb} {noun}'


def _steps(changes: list[RowChange]) -> tuple[list[_Step], list[_Step]]:
    undo: list[_Step] = []
    redo: list[_Step] = []
    for change in changes:
        if change.op == 'UPDATE':
            undo.append(_Step(change.table, change.pk_columns, change.pk, change.after, change.before))
            redo.append(_Step(change.table, change.pk_columns, change.pk, change.before, change.after))
        else:
            cancelled = _soft_cancelled(change)
            undo.append(_Step(change.table, change.pk_columns, change.pk, change.after, cancelled))
            redo.append(_Step(change.table, change.pk_columns, change.pk, cancelled, change.after))
    return list(reversed(undo)), redo


def _fetch(con: sqlite3.Connection, step: _Step) -> dict | None:
    where = ' AND '.join(f'"{column}"=?' for column in step.pk_columns)
    row = con.execute(f'SELECT * FROM "{step.table}" WHERE {where}', step.pk).fetchone()
    return dict(row) if row is not None else None


def _write(db, con: sqlite3.Connection, step: _Step, current: dict, kind: str) -> None:
    _pk, names = _columns(con, step.table)
    assignments = {
        column: step.target[column] for column in names
        if column in step.target and column not in step.pk_columns and column not in VOLATILE_COLUMNS
        and column not in VOLATILE_BY_TABLE.get(step.table, frozenset())
    }
    if 'updated_at' in names:
        assignments['updated_at'] = _now()
    if 'sync_status' in names:
        assignments['sync_status'] = 'PENDING'
    where = ' AND '.join(f'"{column}"=?' for column in step.pk_columns)
    con.execute(
        f'UPDATE "{step.table}" SET ' + ','.join(f'"{column}"=?' for column in assignments)
        + f' WHERE {where}',
        [*assignments.values(), *step.pk],
    )
    entity_id = ':'.join(str(part) for part in step.pk)
    db._audit(con, step.table, entity_id, kind, 'GUI_UNDO', current, step.target, None)
    if step.table in SYNC_ENTITY:
        db._enqueue_sync(con, SYNC_ENTITY[step.table], entity_id, 'UPDATE', step.target)


def apply_steps(db, steps: list[_Step], kind: str) -> None:
    """Write ``steps`` in one transaction, or refuse and write nothing."""
    with suspended():
        with db.tx() as con:
            for step in steps:
                current = _fetch(con, step)
                if current is None or _stable(current, step.table) != _stable(step.expect, step.table):
                    raise UndoRefused('ردیف‌ها پس از این عملیات دوباره تغییر کرده‌اند.')
                _write(db, con, step, current, kind)


def build_action(db, changes: list[RowChange], label: str | None = None) -> HistoryAction | None:
    """Turn one action's row changes into a history entry (None when nothing real changed)."""
    if not changes:
        return None
    label = label or describe(changes)
    if len(changes) > MAX_ROWS:
        return HistoryAction(label, lambda: None, lambda: None, undoable=False,
                             reason='تعداد ردیف‌های این عملیات بیش از حد مجاز برای بازگردانی است.')
    reason = _not_undoable_reason(changes)
    if reason:
        return HistoryAction(label, lambda: None, lambda: None, undoable=False, reason=reason)
    undo_steps, redo_steps = _steps(changes)
    return HistoryAction(
        label,
        lambda: apply_steps(db, undo_steps, 'UNDO'),
        lambda: apply_steps(db, redo_steps, 'REDO'),
    )
