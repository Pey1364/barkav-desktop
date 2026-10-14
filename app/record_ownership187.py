"""RED LINE: no financial row exists without a Data Entry record behind it.

Every row of the Transactions tabs (a cheque, an expense, a payment, a cash transaction) is made by the
approval of one record in Data Entry and belongs to that record for as long as the record is approved:

* the record's lifecycle snapshot lists the rows its approval made (transaction_lifecycle.effects_json);
* a record approved before snapshots existed owns the rows its posting points at, the cheques its
  document links to, or the entity its message is linked to;
* a payment or a cash transaction belongs to the expense or cheque it settles.

Rejecting a record, taking it back to review or approving it again must leave that picture whole:
a row is either owned by an approved record, or it is taken back (cancelled / voided / deleted) and
is no row of any tab. A row that is neither, or a taken-back row that nothing refers to any more,
is a violation. It is never made on purpose, and it is never to be made by accident either: the
approval that re-posts a record gives its cheque the row it already had (see
FinanceDB._new_cheque_id) instead of leaving the old one behind.

This module is the definition and the check. The tests call assert_no_orphans() after every operation
of the lifecycle matrix; tools/audit_ledger_ownership.py runs it against a project database.
"""
from __future__ import annotations

import json
from typing import Any


class RedLineViolation(RuntimeError):
    """A financial row that no record owns."""


# table -> (key column, SQL for «the row is live», i.e. shows in a tab and counts in the totals)
LEDGER = {
    'cheques': ('cheque_id', "(status NOT IN ('CANCELLED','VOIDED') OR settlement_mode='VOIDED')"),
    'transactions': ('transaction_id', "status<>'VOIDED' AND deleted_at IS NULL"),
    'expenses': ('expense_id', "status<>'CANCELLED' AND deleted_at IS NULL"),
    'payments': ('payment_id', "status<>'CANCELLED'"),
}


def _is_new_resolution(payload: dict) -> bool:
    """A resolution record changes a cheque and posts no row of its own; a snapshot it carries is stale."""
    payload = payload or {}
    return str(payload.get('payment_state') or '') == 'CHEQUE_RESOLUTION' and str(
        payload.get('cheque_operation187') or '') == 'تعیین تکلیف چک'


def _payload(text) -> dict:
    try:
        return json.loads(text or '{}')
    except (TypeError, ValueError):
        return {}


def _tables(con) -> set[str]:
    return {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def owned_keys(con) -> dict[str, set[str]]:
    """The keys of the rows some approved record holds, per ledger table."""
    tables = _tables(con)
    owned: dict[str, set[str]] = {table: set() for table in LEDGER}
    if 'transaction_lifecycle' in tables:
        for row in con.execute("""SELECT l.effects_json,p.payload_json FROM transaction_lifecycle l
                                  JOIN pending_items p ON p.pending_id=l.pending_id WHERE l.state='ACTIVE'"""):
            try:
                payload = json.loads(row['payload_json'] or '{}')
            except (TypeError, ValueError):
                payload = {}
            if _is_new_resolution(payload):
                continue
            for effect in json.loads(row['effects_json'] or '[]'):
                if effect.get('table') in owned and effect.get('after') and effect.get('key'):
                    owned[effect['table']].add(str(effect['key'][0]))
    if 'financial_postings' in tables:
        for post in con.execute("SELECT * FROM financial_postings WHERE COALESCE(status,'ACTIVE')='ACTIVE'"):
            for table, column in (('expenses', 'expense_id'), ('transactions', 'transaction_id'),
                                  ('payments', 'payment_id'), ('cheques', 'cheque_id')):
                if post[column]:
                    owned[table].add(str(post[column]))
    if 'financial_document_links' in tables and 'financial_documents' in tables:
        names = {'CHEQUE': 'cheques', 'EXPENSE': 'expenses', 'TRANSACTION': 'transactions', 'PAYMENT': 'payments'}
        for link in con.execute("""SELECT l.entity_type,l.entity_id FROM financial_document_links l
                                   JOIN financial_documents d ON d.document_id=l.document_id
                                   WHERE d.status='ACTIVE'"""):
            table = names.get(str(link['entity_type'] or '').upper())
            if table:
                owned[table].add(str(link['entity_id']))
    if 'telegram_messages' in tables:
        names = {'CHEQUE': 'cheques', 'EXPENSE': 'expenses', 'TRANSACTION': 'transactions'}
        for message in con.execute("""SELECT m.linked_entity_type,m.linked_entity_id,p.payload_json FROM telegram_messages m
                                      JOIN pending_items p ON p.telegram_chat_id=m.chat_id AND p.telegram_message_id=m.message_id
                                      WHERE p.status IN ('APPROVED','EDIT_PENDING') AND m.linked_entity_id IS NOT NULL"""):
            table = names.get(str(message['linked_entity_type'] or '').upper())
            # a resolution record is linked to the cheque it changes; it does not own the cheque's row
            if table and not _is_new_resolution(_payload(message['payload_json'])):
                owned[table].add(str(message['linked_entity_id']))
    # what settles an owned expense or cheque belongs to it
    if owned['expenses'] or owned['cheques']:
        for payment in con.execute('SELECT payment_id,expense_id,cheque_id,transaction_id FROM payments'):
            if str(payment['expense_id'] or '') in owned['expenses'] or str(payment['cheque_id'] or '') in owned['cheques']:
                owned['payments'].add(str(payment['payment_id']))
                if payment['transaction_id']:
                    owned['transactions'].add(str(payment['transaction_id']))
        for transaction in con.execute('SELECT transaction_id,expense_id FROM transactions WHERE expense_id IS NOT NULL'):
            if str(transaction['expense_id']) in owned['expenses']:
                owned['transactions'].add(str(transaction['transaction_id']))
        for cheque in con.execute('SELECT cash_transaction_id FROM cheques WHERE cash_transaction_id IS NOT NULL'):
            owned['transactions'].add(str(cheque['cash_transaction_id']))
    return owned


def orphan_rows(db) -> list[dict[str, Any]]:
    """Live ledger rows that no approved record owns: the violations of the red line."""
    out: list[dict[str, Any]] = []
    with db.read() as con:
        owned = owned_keys(con)
        for table, (column, live) in LEDGER.items():
            if table not in _tables(con):
                continue
            for row in con.execute(f'SELECT {column},status FROM {table} WHERE {live}'):
                if str(row[column]) not in owned[table]:
                    out.append({'table': table, 'key': str(row[column]), 'status': row['status']})
    return out


def assert_no_orphans(db) -> None:
    orphans = orphan_rows(db)
    if orphans:
        shown = '، '.join(f"{row['table']}:{row['key']}" for row in orphans[:5])
        raise RedLineViolation(f'ردیف مالی بدون رکورد ثبت دیتا پیدا شد ({shown}). '
                               'هیچ ردیف مالی نباید بدون رکورد ساخته شود.')


# ---------------------------------------------------------------------------------------------------------
# What a taken-back cheque leaves behind
# ---------------------------------------------------------------------------------------------------------
def referenced_cheque_ids(con) -> set[str]:
    """Cheque ids some record still points at, structurally: its snapshot (rejected ones too: a
    restore needs them), its posting, its document, the message it is linked to."""
    tables = _tables(con)
    referenced: set[str] = set()
    if 'transaction_lifecycle' in tables:
        for row in con.execute("""SELECT l.effects_json,l.rejected_json,p.payload_json FROM transaction_lifecycle l
                                  JOIN pending_items p ON p.pending_id=l.pending_id"""):
            try:
                payload = json.loads(row['payload_json'] or '{}')
            except (TypeError, ValueError):
                payload = {}
            if _is_new_resolution(payload):
                continue
            for effects in (row['effects_json'], row['rejected_json']):
                for effect in json.loads(effects or '[]'):
                    if effect.get('table') == 'cheques' and effect.get('key'):
                        referenced.add(str(effect['key'][0]))
    if 'financial_postings' in tables:
        for post in con.execute("SELECT cheque_id,primary_entity_type,primary_entity_id FROM financial_postings"):
            if post['cheque_id']:
                referenced.add(str(post['cheque_id']))
            if str(post['primary_entity_type'] or '').lower() == 'cheque' and post['primary_entity_id']:
                referenced.add(str(post['primary_entity_id']))
    if 'financial_document_links' in tables and 'financial_documents' in tables:
        for link in con.execute("""SELECT l.entity_id FROM financial_document_links l
                                   JOIN financial_documents d ON d.document_id=l.document_id
                                   WHERE UPPER(l.entity_type)='CHEQUE' AND d.status='ACTIVE'"""):
            referenced.add(str(link['entity_id']))
    if 'telegram_messages' in tables:
        for message in con.execute("""SELECT m.linked_entity_id,p.payload_json FROM telegram_messages m
                                      JOIN pending_items p ON p.telegram_chat_id=m.chat_id AND p.telegram_message_id=m.message_id
                                      WHERE UPPER(m.linked_entity_type)='CHEQUE' AND p.status<>'REJECTED'
                                        AND m.linked_entity_id IS NOT NULL"""):
            if not _is_new_resolution(_payload(message['payload_json'])):
                referenced.add(str(message['linked_entity_id']))
    return referenced


def leftover_cheques(db) -> list[dict[str, Any]]:
    """Cheque rows that were taken back (cancelled, not «باطل‌شده») and that no record refers to any more:
    they are no row of any tab and nothing can bring them back. Safe to delete."""
    with db.read() as con:
        referenced = referenced_cheque_ids(con)
        rows = con.execute("""SELECT cheque_id,status,settlement_mode,created_at FROM cheques
                              WHERE status IN ('CANCELLED','VOIDED') AND COALESCE(settlement_mode,'')<>'VOIDED'""").fetchall()
        return [dict(row) for row in rows if str(row['cheque_id']) not in referenced]


def remove_leftover_cheques(db, ids, *, source: str = 'RED_LINE_REPAIR', actor_id: str = 'GUI') -> list[str]:
    """Delete leftover cheque rows (re-checked inside the transaction) and what hangs only off them."""
    wanted = {str(cid) for cid in ids}
    removed: list[str] = []
    with db.atomic() as con:
        referenced = referenced_cheque_ids(con)
        for cid in sorted(wanted):
            row = con.execute('SELECT * FROM cheques WHERE cheque_id=?', (cid,)).fetchone()
            if not row:
                continue
            if cid in referenced or row['status'] not in ('CANCELLED', 'VOIDED') or row['settlement_mode'] == 'VOIDED':
                raise RedLineViolation(f'چک {cid} هنوز به یک رکورد وصل است و پاک نمی‌شود.')
            if con.execute("SELECT 1 FROM payments WHERE cheque_id=? AND status<>'CANCELLED'", (cid,)).fetchone():
                raise RedLineViolation(f'چک {cid} پرداخت فعال دارد و پاک نمی‌شود.')
            if con.execute("SELECT 1 FROM attachments WHERE entity_type='CHEQUE' AND entity_id=?", (cid,)).fetchone():
                raise RedLineViolation(f'چک {cid} پیوست دارد؛ ابتدا پیوست‌ها باید جابه‌جا شوند.')
            con.execute('UPDATE payments SET cheque_id=NULL WHERE cheque_id=?', (cid,))
            con.execute("DELETE FROM reminders WHERE entity_type='CHEQUE' AND entity_id=?", (cid,))
            con.execute("DELETE FROM financial_document_links WHERE UPPER(entity_type)='CHEQUE' AND entity_id=?", (cid,))
            con.execute('DELETE FROM cheques WHERE cheque_id=?', (cid,))
            db._audit(con, 'cheque', cid, 'DELETE', source, before=dict(row), after=None, actor_id=actor_id)
            db._enqueue_sync(con, 'cheque', cid, 'DELETE', None)
            removed.append(cid)
    return removed
