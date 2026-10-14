"""«انتقال به دردست بررسی»: take approved records back to the review queue.

An approved Data Entry record has done two things: its status says APPROVED
and its approval posted rows into the ledger (expenses, payments, transactions,
cheques, documents, loan and sale rows, reminders, a payment on a contract).
Rejecting such a record already knows how to take all of that back, but it ends
in the rejected pile, from where "restore" can only bring the old posting back.
Returning it to review ends somewhere else: the record is an ordinary pending
one again, with the payload it was approved with, and approving it posts afresh.

It is the lifecycle's own reversal that does the taking back (_reverse), so what
a record's approval changed is undone the same way a rejection undoes it, in one
SQL transaction, with the same audit and sync rows and the same refusals when a
later record depends on it. What differs is the end state:

* the posting row is deleted, not just marked DELETED. financial_postings has
  one row per pending id for good (UNIQUE), and posting a record that already
  has one - the deleted one included - is refused on purpose ("a deleted posting
  must not be revived by approving again"), so a row left behind would make the
  record impossible to approve. The row is written to the audit log first;
* the lifecycle snapshot is dropped, because nothing is left to restore and a
  stale one would stop the next approval;
* the review item keeps its payload and gets its message, hidden flag and
  receipt analysis back in the "needs review" state.

A record can also be in between: deleted for good from Data Entry (rejected,
purged, hidden) while the posting its approval made is still active and so are
its rows. That is what a deletion leaves when its snapshot was empty, as it was
for records approved before snapshots existed. The Data Entry row cannot be
seen, but the ledger row shows in the Transactions tab with the record's id on
it. Returning such a record reads the live rows from the posting, takes them
back, and brings the record itself, with its payload and receipts, back into
review.

A table row can also have no Data Entry record at all: expenses and manual
transactions entered by older versions went straight into the ledger. Those
cannot be reversed from a snapshot that was never taken, so the group of rows
the entry made is read from the ledger, written down as if it were a snapshot,
turned into a pending record carrying the same figures, and returned like any
other approved record. Only shapes whose whole effect is certain are accepted
(an expense with cash or transfer payments, or one standalone transaction);
cheques, loans, sales, documents and anything linked to something else are
refused with a message instead of being guessed at.

Undo and Redo are the same two moves the other way round. Undoing a move approves
the records it returned to review once more, oldest first and all or none,
through the approval the screens use (the caller hands it over), so the rows are
posted afresh and snapshotted like any approval; redoing returns them to review
again. Undo refuses, with a sentence that says why, when a record is not waiting
in review any more or was edited there since: approving it then would not be
taking the move back.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from finance_db import _now
from transaction_lifecycle import (CHEQUE_HINT, LifecycleDecision, TransactionLifecycle, is_new_resolution,
                                   is_resolution_payload)

SOURCE = 'GUI_REVIEW_RETURN'
#: Synthetic Telegram chat that owns the review records made from old rows
#: (the GUI's other manual records use -175, -180, -182 and -187 the same way).
LEGACY_CHAT_ID = -187
LEGACY_SOURCE = 'LEGACY_REVIEW_187'

MENU_LABEL = 'انتقال به دردست بررسی'

#: A copy of the project database is made before a move changes it, next to the
#: database; the newest few are kept.
BACKUP_FOLDER = '.barkav-review-backups'
BACKUP_KEEP = 5

#: Row keys that make an old row something other than a plain expense or
#: transaction; their effects are not certain enough to reverse from the ledger.
_COMPLEX_KEYS = ('cheque_id', 'loan_id', 'loan_installment_id', 'sale_id',
                 'received_payment_id', 'document_id')

UNSUPPORTED = ('این ردیف قدیمی از نوع هزینه یا تراکنش ساده نیست؛ '
               'برای انتقال آن به دردست بررسی تعیین تکلیف دستی لازم است.')

#: The entity name receipts hang on for each ledger table an entry writes.
ATTACHMENT_ENTITY = {'expenses': 'EXPENSE', 'transactions': 'TRANSACTION',
                     'payments': 'PAYMENT', 'cheques': 'CHEQUE'}


@dataclass
class MoveResult:
    """What one «انتقال به دردست بررسی» did, by pending id."""

    moved: list[str] = field(default_factory=list)      # approved records returned to review
    created: list[str] = field(default_factory=list)    # review records made from old rows
    already: list[str] = field(default_factory=list)    # were under review already
    #: What each moved record held when it went to review: Undo approves exactly that.
    payloads: dict[str, dict] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.moved)


@dataclass
class MovePlan:
    """What a selection would do, worked out without changing anything."""

    sources: list[str] = field(default_factory=list)        # records that would return to review
    revived: list[str] = field(default_factory=list)        # of those, deleted ones whose rows are still live
    already: list[str] = field(default_factory=list)        # records under review already
    scopes: list['LegacyScope'] = field(default_factory=list)  # old rows that would be given a record first
    dependents: list[str] = field(default_factory=list)     # records that would go back with them

    @property
    def nothing_to_do(self) -> bool:
        return not self.sources and not self.scopes


@dataclass(frozen=True)
class LegacyScope:
    """The ledger rows one old entry made, as the snapshot it never had."""

    key: str                       # 'expense:EX1' / 'transaction:TX1', to count a group once
    rows: tuple                    # effect rows, in posting order
    payload: dict
    text: str


def _effect(table: str, pk: str, row) -> dict:
    row = dict(row)
    return {'table': table, 'pk': [pk], 'key': [row[pk]], 'before': None, 'after': row}


class ReviewReturn(TransactionLifecycle):
    """TransactionLifecycle plus the way back to review."""

    def __init__(self, db, *, source: str = SOURCE, actor_id: str = 'GUI'):
        super().__init__(db, source=source, actor_id=actor_id)

    # ------------------------------------------------------------ one record
    def _order(self, pids: Iterable[str]) -> list[str]:
        """Newest first: a later record can lean on an earlier one (a cheque
        settled by a second receipt), so the dependent one goes back first."""

        pids = list(pids)
        if not pids:
            return []
        with self.db.read() as con:
            order = {row['pending_id']: (row['created_at'], row['position']) for row in con.execute(
                'SELECT pending_id,created_at,rowid AS position FROM pending_items WHERE pending_id IN ('
                + ','.join('?' for _ in pids) + ')', pids)}
        return sorted(pids, key=lambda pid: order.get(pid, ('', 0)), reverse=True)

    def _return_one(self, pid: str) -> bool:
        """Returns False when the record was under review already."""

        prior_contracts = self._contracts(pid)
        try:
            with self.db.atomic() as con:
                item = self.db.get_pending_item(pid)
                if not item:
                    raise KeyError(pid)
                status = item['status']
                if status in ('PENDING_REVIEW', 'NEEDS_REVIEW'):
                    return False
                record = self.get(pid, con)
                if (record and record['state'] == 'ACTIVE' and status in ('APPROVED', 'EDIT_PENDING')
                        and is_new_resolution(item['payload'])):
                    self.drop_stale_snapshot(pid, record, con)
                    record = None
                live = self._live_posting(pid, con)
                # A resolution has no ledger rows; going back to review gives the cheque the
                # state it had before the record changed it.
                resolution = (status in ('APPROVED', 'EDIT_PENDING') and not record
                              and is_resolution_payload(item['payload']))
                if status in ('APPROVED', 'EDIT_PENDING'):
                    if record and record['state'] != 'ACTIVE':
                        raise ValueError('ردیف ردشده فقط با «بازگردانی» برمی‌گردد.')
                    effects = json.loads(record['effects_json']) if record else []
                elif status == 'REJECTED' and live:
                    # Deleted from Data Entry, but the posting that approval made is
                    # still active, and so are its rows: the deletion never took
                    # them back (its snapshot is empty). They are read from the
                    # posting, as for a record approved before snapshots existed.
                    effects = []
                else:
                    raise ValueError('فقط ردیف تأییدشده را می‌توان به دردست بررسی برد؛ '
                                     'ردیف ردشده با «بازگردانی» برمی‌گردد.')
                if not effects and not resolution:
                    effects = self._legacy(pid, con)
                message = self._message(pid, con)
                # As in a rejection, the review state is set inside the SQL
                # transaction first, so a refusal further down rolls it back.
                con.execute("UPDATE pending_items SET status='PENDING_REVIEW' WHERE pending_id=?", (pid,))
                if resolution:
                    self._undo_resolution(pid, item)
                effects = self._include_late_reminders(effects, con)
                # The cheque rows this record made are taken back, not forgotten: its next approval
                # posts them again on the same ids (see TransactionLifecycle.run).
                hint = self._cheque_hint(effects)
                if effects:
                    self._reverse(effects, con)
                self._carry_attachments(con, pid, [
                    (ATTACHMENT_ENTITY[effect['table']], effect['key'][0])
                    for effect in effects if effect['table'] in ATTACHMENT_ENTITY and effect['key']])
                self._set_contracts(pid, [])
                self._settle(pid, item, record, message, con)
                if hint:
                    self.db.update_pending(pid, payload={**dict(self.db.get_pending_item(pid)['payload'] or {}),
                                                         CHEQUE_HINT: hint})
                return True
        except Exception:
            self._set_contracts(pid, prior_contracts)
            raise

    def _live_posting(self, pid: str, con=None) -> bool:
        """Whether the record still has an active posting, that is live rows in the ledger."""

        if con is None:
            with self.db.read() as reader:
                return self._live_posting(pid, reader)
        row = con.execute('SELECT status FROM financial_postings WHERE pending_id=?', (pid,)).fetchone()
        return row is not None and str(row['status'] or 'ACTIVE') == 'ACTIVE'

    def _carry_attachments(self, con, pid: str, entities: Iterable[tuple[str, str]]) -> None:
        """Hang the receipts that are on rows just cancelled on the review record
        instead; approving it moves them onto the rows it posts."""

        for entity_type, entity_id in dict.fromkeys(entities):
            for attachment in con.execute('SELECT * FROM attachments WHERE entity_type=? AND entity_id=?',
                                          (entity_type, entity_id)).fetchall():
                con.execute("UPDATE attachments SET entity_type='PENDING',entity_id=? WHERE attachment_id=?",
                            (pid, attachment['attachment_id']))
                self.db._audit(con, 'attachment', attachment['attachment_id'], 'RELINK', self.source,
                               before=dict(attachment),
                               after={**dict(attachment), 'entity_type': 'PENDING', 'entity_id': pid},
                               actor_id=self.actor_id)

    def _settle(self, pid, item, record, message, con) -> None:
        """Leave the review item as a plain pending one."""

        audit = self.db._audit
        posting = con.execute('SELECT * FROM financial_postings WHERE pending_id=?', (pid,)).fetchone()
        if posting:
            con.execute('DELETE FROM financial_postings WHERE pending_id=?', (pid,))
            audit(con, 'financial_posting', posting['posting_id'], 'DELETE', self.source,
                  before=dict(posting), after=None, actor_id=self.actor_id)
        if record:
            con.execute('DELETE FROM transaction_lifecycle WHERE pending_id=?', (pid,))
            audit(con, 'transaction_lifecycle', pid, 'DELETE', self.source,
                  before=dict(record), after=None, actor_id=self.actor_id)
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='posting_revisions'").fetchone():
            con.execute("UPDATE posting_revisions SET status='REJECTED',updated_at=? "
                        "WHERE pending_id=? AND status='PENDING'", (_now(), pid))
        now = _now()
        con.execute("UPDATE pending_items SET status='PENDING_REVIEW',updated_at=? WHERE pending_id=?",
                    (now, pid))
        con.execute("UPDATE telegram_messages SET state='PENDING_REVIEW',reaction_state='NONE',"
                    "linked_entity_type=NULL,linked_entity_id=NULL,updated_at=? "
                    "WHERE chat_id=? AND message_id=?",
                    (now, item['telegram_chat_id'], item['telegram_message_id']))
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='rich_ui_hidden_reviews'").fetchone():
            con.execute('UPDATE rich_ui_hidden_reviews SET hidden=0,updated_at=? WHERE pending_id=?',
                        (now, pid))
        self.db.update_receipt_analysis_status(pid, 'NEEDS_REVIEW')
        self.db.enqueue_integration_event('GUI_REOPENED', pending_id=pid,
                                          payload={'actor_id': self.actor_id, 'review_return': True})
        self.clear_decision(pid)
        audit(con, 'pending', pid, 'REOPEN', self.source,
              before={'status': item['status']}, after={'status': 'PENDING_REVIEW'},
              actor_id=self.actor_id)
        self.db._enqueue_sync(con, 'pending', pid, 'UPDATE', {'status': 'PENDING_REVIEW'})

    def backup(self) -> Path:
        """A verified copy of the project database as it is now, to be made before
        a move changes it. Run it outside any transaction."""

        source = Path(self.db.db_path)
        folder = source.parent / BACKUP_FOLDER
        folder.mkdir(parents=True, exist_ok=True)
        # Microseconds and a random tail: the names sort in the order the copies were made.
        target = folder / (f'{source.name}.{datetime.now():%Y%m%d-%H%M%S-%f}.{uuid.uuid4().hex[:6]}'
                           '.pre-review-return.sqlite3')
        with self.db.read() as con, closing(sqlite3.connect(target)) as destination:
            con.backup(destination)
            if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise sqlite3.DatabaseError('the copy made before the move is not sound')
        for old in sorted(folder.glob(f'{source.name}.*.pre-review-return.sqlite3'))[:-BACKUP_KEEP]:
            try:
                old.unlink()
            except OSError:
                pass
        return target

    # ----------------------------------------------------------- many records
    def return_to_review(self, ids: Iterable[str]) -> list[str]:
        """Return approved records to review, all or none.

        Records that hang on one of these (a cheque one of them issued and a
        later receipt settled) go with it, as they do when it is rejected.
        Returns the ids that moved, newest first."""

        ids = list(dict.fromkeys(str(pid) for pid in ids))
        if not ids:
            return []
        affected = set(ids)
        queue = list(ids)
        while queue:
            for child in self._cheque_dependents(queue.pop()):
                if child not in affected:
                    affected.add(child)
                    queue.append(child)
        # The contracts file is written outside the SQL transaction: keep what
        # it held to put back if any record of the group is refused.
        previous = {pid: self._contracts(pid) for pid in affected}
        try:
            with self.db.atomic():
                return [pid for pid in self._order(affected) if self._return_one(pid)]
        except Exception:
            for pid, payments in previous.items():
                self._set_contracts(pid, payments)
            raise

    def plan_move(self, rows: Iterable[dict]) -> MovePlan:
        """Work out what moving these rows to review would do, or raise
        LifecycleDecision (all the reasons in one message) if any row cannot go."""

        plan = MovePlan()
        scopes: dict[str, LegacyScope] = {}
        failures: list[str] = []
        seen: set[str] = set()
        for row in rows or ():
            if row.get('_lifecycle_decision_only187'):
                failures.append(str(row.get('_lifecycle_decision187') or UNSUPPORTED))
                continue
            try:
                pid = self.pending_for_row(row)
            except LifecycleDecision:
                try:
                    scope = self.legacy_scope(row)
                except LifecycleDecision as exc:
                    failures.append(str(exc))
                    continue
                scopes.setdefault(scope.key, scope)
                continue
            if pid in seen:
                continue
            seen.add(pid)
            status = (self.db.get_pending_item(pid) or {}).get('status')
            if status in ('PENDING_REVIEW', 'NEEDS_REVIEW'):
                plan.already.append(pid)
            elif status in ('APPROVED', 'EDIT_PENDING'):
                plan.sources.append(pid)
            elif status == 'REJECTED' and self._live_posting(pid):
                plan.sources.append(pid)
                plan.revived.append(pid)
            else:
                failures.append('این ردیف تأییدشده نیست و اثری در دفتر مالی ندارد؛ '
                                'ردیف ردشده با «بازگردانی» برمی‌گردد.')
        if failures:
            raise LifecycleDecision('\n'.join(dict.fromkeys(failures)))
        plan.scopes = list(scopes.values())
        queue, known = list(plan.sources), set(plan.sources)
        while queue:
            for child in self._cheque_dependents(queue.pop()):
                if child not in known:
                    known.add(child)
                    queue.append(child)
                    plan.dependents.append(child)
        return plan

    def run_move(self, plan: MovePlan) -> MoveResult:
        """Do what plan_move worked out: old rows get their record, then every
        approved record goes back, in one SQL transaction."""

        result = MoveResult(already=list(plan.already))
        with self.db.atomic():
            result.created = [self._adopt(scope, index) for index, scope in enumerate(plan.scopes)]
            result.moved = self.return_to_review([*plan.sources, *result.created])
            result.payloads = self._payloads(result.moved)
        return result

    def _payloads(self, pids: Iterable[str]) -> dict[str, dict]:
        return {pid: dict(self.db.get_pending_item(pid)['payload']) for pid in pids}

    def undo_move(self, result: MoveResult, approve: Callable[[str, dict], Any]) -> list[str]:
        """Take a move back: approve its records again, oldest first, all or none.

        ``approve(pending_id, payload)`` is the approval of the screens. Raises
        LifecycleDecision, changing nothing, if a record is not waiting in review
        any more or has been edited there since the move. Returns the ids approved."""

        ordered = list(reversed(self._order(result.moved)))
        for pid in ordered:
            item = self.db.get_pending_item(pid)
            if not item or item['status'] not in ('PENDING_REVIEW', 'NEEDS_REVIEW') \
                    or dict(item['payload']) != result.payloads.get(pid):
                raise LifecycleDecision('ردیف‌ها پس از انتقال تغییر کرده‌اند (تأیید، رد، حذف یا ویرایش شده‌اند)؛ '
                                        'برای همین دیگر نمی‌توان انتقال را با Undo برگرداند.')
        previous = {pid: self._contracts(pid) for pid in ordered}
        try:
            with self.db.atomic():
                for pid in ordered:
                    approve(pid, dict(result.payloads[pid]))
                    if (self.db.get_pending_item(pid) or {}).get('status') != 'APPROVED':
                        raise LifecycleDecision('تأیید دوباره کامل نشد؛ همهٔ ردیف‌ها همان‌طور که بودند ماندند.')
        except Exception:
            # The contracts file is written outside the SQL transaction.
            for pid, payments in previous.items():
                self._set_contracts(pid, payments)
            raise
        return ordered

    def redo_move(self, result: MoveResult) -> list[str]:
        """Do a move again after it was taken back: its records return to review.

        Raises LifecycleDecision, changing nothing, if one of them is not an
        approved record any more. What went back this time (a record that leans on
        one of them goes with it) replaces what the result held."""

        for pid in result.moved:
            item = self.db.get_pending_item(pid)
            if not item or item['status'] not in ('APPROVED', 'EDIT_PENDING'):
                raise LifecycleDecision('ردیف‌ها پس از Undo تغییر کرده‌اند (رد، حذف یا دوباره منتقل شده‌اند)؛ '
                                        'برای همین انتقال دوباره اجرا نمی‌شود.')
        with self.db.atomic():
            moved = self.return_to_review(result.moved)
            payloads = self._payloads(moved)
        result.moved, result.payloads = moved, payloads
        return moved

    def move_rows_to_review(self, rows: Iterable[dict]) -> MoveResult:
        """The screens' entry point: table or Data Entry rows in, review out.

        A row that has a Data Entry record is returned through it; one that has
        none is first given one (see the module note). Nothing is changed unless
        every row can be."""

        return self.run_move(self.plan_move(rows))

    # ------------------------------------------------------- rows with no record
    def legacy_scope(self, row: dict) -> LegacyScope:
        """What an old row put in the ledger, or LifecycleDecision if that is not certain."""

        if any(row.get(key) for key in _COMPLEX_KEYS):
            raise LifecycleDecision(UNSUPPORTED)
        with self.db.read() as con:
            if row.get('expense_id'):
                return self._expense_scope(con, str(row['expense_id']))
            if row.get('transaction_id'):
                return self._transaction_scope(con, str(row['transaction_id']))
        raise LifecycleDecision(UNSUPPORTED)

    @staticmethod
    def _tables(con) -> set[str]:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def _linked_elsewhere(self, con, *, expense_ids=(), payment_ids=(), transaction_ids=()) -> bool:
        """Rows from newer services that tie the entry to something else (a
        document, a payment shared by several invoices): not an old plain entry."""

        tables = self._tables(con)
        if 'expense_payment_links' in tables:
            for column, values in (('expense_id', expense_ids), ('payment_id', payment_ids),
                                   ('transaction_id', transaction_ids)):
                for value in values:
                    if con.execute(f'SELECT 1 FROM expense_payment_links WHERE {column}=?', (value,)).fetchone():
                        return True
        if 'financial_document_links' in tables:
            for kind, values in (('EXPENSE', expense_ids), ('PAYMENT', payment_ids),
                                 ('TRANSACTION', transaction_ids)):
                for value in values:
                    if con.execute('SELECT 1 FROM financial_document_links '
                                   'WHERE UPPER(entity_type)=? AND entity_id=?', (kind, value)).fetchone():
                        return True
        return False

    def _expense_scope(self, con, expense_id: str) -> LegacyScope:
        expense = con.execute('SELECT * FROM expenses WHERE expense_id=?', (expense_id,)).fetchone()
        if not expense or expense['deleted_at'] or expense['status'] == 'CANCELLED':
            raise LifecycleDecision('این هزینه دیگر فعال نیست.')
        if con.execute('SELECT 1 FROM financial_postings WHERE expense_id=?', (expense_id,)).fetchone():
            raise LifecycleDecision('این هزینه به یک ثبت دیتا وصل است که فعال نیست؛ تعیین تکلیف لازم است.')
        payments = con.execute("SELECT * FROM payments WHERE expense_id=? AND status!='CANCELLED' "
                               "ORDER BY created_at,rowid", (expense_id,)).fetchall()
        if any(payment['cheque_id'] for payment in payments) or con.execute(
                "SELECT 1 FROM cheques WHERE expense_id=? AND status NOT IN ('CANCELLED','VOIDED')",
                (expense_id,)).fetchone():
            raise LifecycleDecision('هزینهٔ قدیمی چک دارد؛ برای انتقال آن به دردست بررسی تعیین تکلیف دستی لازم است.')
        transactions = {row['transaction_id']: row for row in con.execute(
            "SELECT * FROM transactions WHERE expense_id=? AND status!='VOIDED' AND deleted_at IS NULL "
            "ORDER BY created_at,rowid", (expense_id,))}
        for payment in payments:
            if payment['transaction_id'] and payment['transaction_id'] not in transactions:
                row = con.execute("SELECT * FROM transactions WHERE transaction_id=? AND status!='VOIDED' "
                                  "AND deleted_at IS NULL", (payment['transaction_id'],)).fetchone()
                if row:
                    transactions[row['transaction_id']] = row
        if any(row['sale_id'] or row['loan_id'] for row in transactions.values()):
            raise LifecycleDecision(UNSUPPORTED)
        if self._linked_elsewhere(con, expense_ids=[expense_id],
                                  payment_ids=[p['payment_id'] for p in payments],
                                  transaction_ids=list(transactions)):
            raise LifecycleDecision('این هزینه به سند یا پرداخت دیگری وصل است؛ تعیین تکلیف لازم است.')
        rows = [_effect('expenses', 'expense_id', expense)]
        rows += [_effect('payments', 'payment_id', payment) for payment in payments]
        rows += [_effect('transactions', 'transaction_id', row) for row in transactions.values()]
        paid = sum(int(p['amount'] or 0) for p in payments if p['status'] == 'COMPLETED')
        final = int(expense['final_amount'] or 0)
        first = next(iter(transactions.values()), None)
        payload = {
            'detected_type': 'EXPENSE', 'v18_title': 'هزینه ساخت', 'v18_subtype': 'نقدی',
            'event_date_shamsi': expense['shamsi_date'] or _shamsi(expense['event_date']),
            'amount': final, 'final_amount': final,
            'invoice_amount': int(expense['invoice_amount'] or final),
            'discount_amount': int(expense['discount_amount'] or 0),
            'description': expense['description'] or '',
            'receiver_name': expense['vendor_name'] or (first['receiver_name'] if first else '') or '',
            'payer_name': (first['payer_name'] if first else '') or '',
            'expense_category': expense['category'] or 'OTHER',
            'construction_stage': expense['construction_stage'] or '',
            'cost_group': expense['cost_group'] or '', 'plan_ref': expense['plan_ref'] or '',
            'manager_fee_eligible': bool(expense['manager_fee_eligible']),
            'payment_state': 'UNPAID' if paid <= 0 else ('PAID' if paid >= final else 'PARTIAL'),
            'paid_amount': min(paid, final) if final else paid,
            'payment_method': (payments[0]['method'] if payments and paid > 0 else 'UNKNOWN') or 'UNKNOWN',
            'source': LEGACY_SOURCE, 'legacy_expense_id': expense_id,
        }
        return LegacyScope(f'expense:{expense_id}', tuple(rows), payload, str(expense['description'] or ''))

    def _transaction_scope(self, con, transaction_id: str) -> LegacyScope:
        row = con.execute('SELECT * FROM transactions WHERE transaction_id=?', (transaction_id,)).fetchone()
        if not row or row['deleted_at'] or row['status'] != 'POSTED':
            raise LifecycleDecision('این تراکنش دیگر فعال نیست.')
        if row['expense_id']:
            return self._expense_scope(con, str(row['expense_id']))
        if row['sale_id'] or row['loan_id']:
            raise LifecycleDecision(UNSUPPORTED)
        if con.execute('SELECT 1 FROM financial_postings WHERE transaction_id=?', (transaction_id,)).fetchone() \
                or con.execute('SELECT 1 FROM payments WHERE transaction_id=?', (transaction_id,)).fetchone() \
                or con.execute('SELECT 1 FROM cheques WHERE cash_transaction_id=?', (transaction_id,)).fetchone() \
                or self._linked_elsewhere(con, transaction_ids=[transaction_id]):
            raise LifecycleDecision('این تراکنش به ثبت، پرداخت یا چک دیگری وصل است؛ تعیین تکلیف لازم است.')
        incoming = str(row['direction'] or '').upper() == 'IN'
        payload = {
            'detected_type': 'INCOME' if incoming else 'OUTFLOW',
            'v18_title': 'ورودی' if incoming else 'خروجی', 'v18_subtype': 'سایر',
            'event_date_shamsi': row['shamsi_date'] or _shamsi(row['event_date']),
            'amount': int(row['amount'] or 0), 'description': row['description'] or '',
            'payer_name': row['payer_name'] or '', 'receiver_name': row['receiver_name'] or '',
            'source': LEGACY_SOURCE, 'legacy_transaction_id': transaction_id,
            'legacy_category': row['category'] or '',
        }
        return LegacyScope(f'transaction:{transaction_id}', (_effect('transactions', 'transaction_id', row),),
                           payload, str(row['description'] or ''))

    def _adopt(self, scope: LegacyScope, index: int = 0) -> str:
        """Give an old entry the approved Data Entry record it never had, so that
        the usual return can take its rows back. Runs inside the caller's transaction."""

        mid = int(datetime.now().timestamp() * 1_000_000) + index
        self.db.register_telegram_message(
            chat_id=LEGACY_CHAT_ID, message_id=mid, raw_text=scope.text,
            content_type='legacy_review_gui', message_date=datetime.now().isoformat(timespec='seconds'),
            state='APPROVED')
        pid = self.db.create_or_replace_pending(
            telegram_chat_id=LEGACY_CHAT_ID, telegram_message_id=mid,
            detected_type=scope.payload['detected_type'], payload=scope.payload,
            confidence=1.0, status='APPROVED')
        with self.db.atomic() as con:
            self._persist(pid, 'ACTIVE', list(scope.rows), scope.payload, self._message(pid, con), [], con=con)
            self.db._audit(con, 'pending', pid, 'CREATE', self.source, before=None,
                           after={'status': 'APPROVED', 'legacy': scope.key}, actor_id=self.actor_id)
        return pid


def _shamsi(event_date: Any) -> str:
    from revenue_service import gregorian_to_shamsi
    try:
        return gregorian_to_shamsi(str(event_date or '')[:10])
    except Exception:
        return ''
