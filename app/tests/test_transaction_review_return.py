"""«انتقال به دردست بررسی»: an approved record goes back to the review queue.

The same disposable-project harness as the lifecycle matrix: every kind of
record the runtime can approve is approved, returned to review, and approved
again, and every view the app has (cash, cost, manager fee, cheques, plan
actuals, transaction and expense lists, documents, calendar, loans, sales) must
show it back where it was before the approval after the return, and with the
approval's effect again after the second approval. Undo and Redo of a move are
tested here too: Undo approves the records again, Redo returns them to review.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_transaction_lifecycle_matrix import CASES, case_payload, m, register, runtime, views  # noqa: E402,F401

from transaction_lifecycle import LifecycleDecision, TransactionLifecycle  # noqa: E402
from transaction_review import ReviewReturn  # noqa: E402


def shape(view: dict) -> dict:
    """A view without the ids a second approval makes afresh."""

    keep = ('snapshot', 'flow', 'manager', 'cheques', 'actuals')
    out = {key: view[key] for key in keep}
    out.update({f'{key}#': len(view[key]) for key in (
        'transactions', 'expenses', 'documents', 'cheque_rows', 'records', 'events', 'messages',
        'loans', 'sales')})
    return out


def audit_rows(runtime, **where):
    clause = ' AND '.join(f'{key}=?' for key in where)
    with runtime.db.read() as con:
        return [dict(row) for row in con.execute(
            f'SELECT * FROM audit_log WHERE {clause} ORDER BY audit_id', tuple(where.values()))]


@pytest.mark.parametrize('case', CASES, ids=[c[0] for c in CASES])
def test_each_type_returns_to_review_and_posts_afresh(runtime, case):
    payload = case_payload(runtime, case)
    baseline = views(runtime)
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, payload, runtime.rich)
    approved = views(runtime)

    assert ReviewReturn(runtime.db).return_to_review([pid]) == [pid]

    item = runtime.db.get_pending_item(pid)
    assert item['status'] == 'PENDING_REVIEW'
    assert item['payload']['description'] == payload['description'], 'the record keeps what it was approved with'
    assert views(runtime) == baseline, 'every view is back to before the approval'
    assert runtime.db.get_financial_posting(pid) is None
    assert TransactionLifecycle(runtime.db).get(pid) is None
    assert pid in {row['pending_id'] for row in runtime.approval.list_reviews(statuses=('PENDING_REVIEW',))}
    assert runtime.db.get_telegram_message(-989, 1)['state'] == 'PENDING_REVIEW'

    m.v18.submit_v18(pid, payload, runtime.rich)
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert shape(views(runtime)) == shape(approved), 'approving again posts the same effect'
    # The record is an ordinary approved one again: it can still be rejected and restored.
    life = TransactionLifecycle(runtime.db)
    life.reject(pid)
    assert views(runtime) == baseline
    life.restore(pid)
    assert shape(views(runtime)) == shape(approved)


def approved_record(runtime, case=CASES[0], message_id=1, **overrides):
    payload = {**case_payload(runtime, case), **overrides}
    pid = register(runtime, payload, message_id)
    m.v18.submit_v18(pid, payload, runtime.rich)
    return pid, payload


# ------------------------------------------------------------- the group rule

def test_a_refused_record_stops_the_whole_group(runtime):
    first, _ = approved_record(runtime, message_id=1)
    second, _ = approved_record(runtime, message_id=2)
    posting = runtime.db.get_financial_posting(second)
    with runtime.db.tx() as con:
        # A later change to a row the second record posted: taking its effect
        # back would overwrite it, so the lifecycle refuses.
        con.execute('UPDATE transactions SET amount=1200 WHERE transaction_id=?', (posting['transaction_id'],))
    approved = views(runtime)
    with pytest.raises(LifecycleDecision):
        ReviewReturn(runtime.db).return_to_review([first, second])
    assert views(runtime) == approved
    assert {runtime.db.get_pending_item(pid)['status'] for pid in (first, second)} == {'APPROVED'}
    assert runtime.db.get_financial_posting(first) is not None


def test_a_rejected_record_is_not_returned_and_still_restores(runtime):
    pid, _ = approved_record(runtime)
    life = TransactionLifecycle(runtime.db)
    life.reject(pid)
    rejected = views(runtime)
    with pytest.raises(ValueError):
        ReviewReturn(runtime.db).return_to_review([pid])
    assert runtime.db.get_pending_item(pid)['status'] == 'REJECTED'
    assert views(runtime) == rejected
    life.restore(pid)
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'


def test_a_record_already_under_review_is_left_alone(runtime):
    pid = register(runtime, case_payload(runtime, CASES[0]))
    before = views(runtime)
    result = ReviewReturn(runtime.db).move_rows_to_review([{'pending_id': pid}])
    assert (result.moved, result.created, result.already) == ([], [], [pid])
    assert views(runtime) == before
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'


def test_a_table_row_is_returned_through_the_record_it_came_from(runtime):
    pid, _ = approved_record(runtime)
    assert runtime.db.snapshot().cash_balance == -1000
    row = next(r for r in runtime.service.list_transactions() if r['pending_id'] == pid)
    result = ReviewReturn(runtime.db).move_rows_to_review([row, row])
    assert (result.moved, result.created) == ([pid], [])
    assert runtime.db.snapshot().cash_balance == 0
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'


# --------------------------------------------------------- what it leaves behind

def test_the_return_leaves_its_whole_trail(runtime):
    pid, _ = approved_record(runtime)
    posting = runtime.db.get_financial_posting(pid)
    with runtime.db.tx() as con:
        con.execute("INSERT INTO receipt_analyses(analysis_id,pending_id,status,created_at,updated_at) "
                    "VALUES('A',?,'APPROVED','2026-09-30','2026-09-30')", (pid,))
    ReviewReturn(runtime.db).return_to_review([pid])

    posting_rows = audit_rows(runtime, entity_type='financial_posting', entity_id=posting['posting_id'],
                              action='DELETE')
    assert posting_rows and posting_rows[-1]['source'] == 'GUI_REVIEW_RETURN'
    assert json.loads(posting_rows[-1]['before_json'])['pending_id'] == pid, 'the row is in the log before it goes'
    assert audit_rows(runtime, entity_type='pending', entity_id=pid, action='REOPEN')
    assert audit_rows(runtime, entity_type='transaction_lifecycle', entity_id=pid, action='DELETE')
    with runtime.db.read() as con:
        assert con.execute("SELECT status FROM receipt_analyses WHERE pending_id=?", (pid,)).fetchone()[0] == 'NEEDS_REVIEW'
        assert tuple(con.execute("SELECT state,reaction_state,linked_entity_type FROM telegram_messages "
                                 "WHERE chat_id=-989 AND message_id=1").fetchone()) == ('PENDING_REVIEW', 'NONE', None)
        assert con.execute("SELECT COUNT(*) FROM integration_events WHERE pending_id=? AND event_type='GUI_REOPENED'",
                           (pid,)).fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM sync_queue WHERE entity_id=? AND operation='UPDATE'",
                           (pid,)).fetchone()[0] >= 1
        # What the approval cancelled stays in the ledger, cancelled: nothing was deleted from it.
        assert con.execute("SELECT status FROM transactions WHERE transaction_id=?",
                           (posting['transaction_id'],)).fetchone()[0] == 'VOIDED'
        assert con.execute("SELECT status FROM expenses WHERE expense_id=?",
                           (posting['expense_id'],)).fetchone()[0] == 'CANCELLED'


def test_a_hidden_record_shows_again_in_review(runtime):
    pid, _ = approved_record(runtime)
    runtime.rich.hidden_review_ids()  # creates the hidden-reviews table
    with runtime.db.tx() as con:
        con.execute("INSERT INTO rich_ui_hidden_reviews(pending_id,hidden,updated_at) VALUES(?,1,'2026-09-30') "
                    "ON CONFLICT(pending_id) DO UPDATE SET hidden=1", (pid,))
    assert pid in runtime.rich.hidden_review_ids()
    ReviewReturn(runtime.db).return_to_review([pid])
    assert pid not in runtime.rich.hidden_review_ids()


# ----------------------------------------------------------- contracts and files

def test_a_contract_payment_goes_off_and_comes_back_with_the_approval(runtime):
    from contractor_store_stage18_7 import amount_of, get_contract, upsert_contract
    upsert_contract({'contract_id': 'C1', 'title': 'قرارداد آزمون', 'total_amount': 2000, 'payments': []})
    pid, payload = approved_record(runtime, contract_id='C1', cost_group='پیمانکار')
    assert sum(amount_of(p['amount']) for p in get_contract('C1')['payments']) == 1000
    ReviewReturn(runtime.db).return_to_review([pid])
    assert not get_contract('C1')['payments']
    m.v18.submit_v18(pid, payload, runtime.rich)
    assert sum(amount_of(p['amount']) for p in get_contract('C1')['payments']) == 1000


def test_contract_file_failure_rolls_back_database_and_file(runtime, monkeypatch):
    from contractor_store_stage18_7 import get_contract, upsert_contract
    upsert_contract({'contract_id': 'C1', 'title': 'آزمون', 'total_amount': 2000, 'payments': []})
    pid, _ = approved_record(runtime, contract_id='C1', cost_group='پیمانکار')
    approved, contract = views(runtime), get_contract('C1')
    life = ReviewReturn(runtime.db)
    original = life._set_contracts

    def fail(key, wanted):
        if not wanted:
            raise OSError('injected file permission failure')
        return original(key, wanted)
    monkeypatch.setattr(life, '_set_contracts', fail)
    with pytest.raises(OSError):
        life.return_to_review([pid])
    assert views(runtime) == approved and get_contract('C1') == contract
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'


def test_failure_after_the_file_was_written_puts_both_back(runtime, monkeypatch):
    from contractor_store_stage18_7 import get_contract, upsert_contract
    upsert_contract({'contract_id': 'C1', 'title': 'آزمون', 'total_amount': 2000, 'payments': []})
    pid, _ = approved_record(runtime, contract_id='C1', cost_group='پیمانکار')
    approved, contract = views(runtime), get_contract('C1')
    audit = runtime.db._audit

    def fail(con, entity, *args, **kwargs):
        if entity == 'pending':
            raise ValueError('injected audit failure after the file write')
        return audit(con, entity, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(runtime.db, '_audit', fail)
        with pytest.raises(ValueError):
            ReviewReturn(runtime.db).return_to_review([pid])
    assert views(runtime) == approved and get_contract('C1') == contract
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert runtime.db.get_financial_posting(pid) is not None, 'the deleted posting row came back with the rollback'


# -------------------------------------------------------------------- dependents

def test_a_cheque_goes_back_with_the_receipt_that_cleared_it(runtime):
    payload = case_payload(runtime, CASES[3])
    baseline = views(runtime)
    origin = register(runtime, payload)
    m.v18.submit_v18(origin, payload, runtime.rich)
    clearing = {**payload, 'v18_subtype': 'نقدی', 'detected_type': 'EXPENSE', 'payment_method': 'BANK_TRANSFER',
                'is_cheque': False, 'payment_state': 'CHEQUE_CLEARING'}
    receipt = register(runtime, clearing, 2)
    m.v18.submit_v18(receipt, clearing, runtime.rich)
    approved = views(runtime)

    moved = ReviewReturn(runtime.db).return_to_review([origin])
    assert moved == [receipt, origin], 'the later receipt goes back first'
    assert views(runtime) == baseline
    assert {runtime.db.get_pending_item(pid)['status'] for pid in (origin, receipt)} == {'PENDING_REVIEW'}

    m.v18.submit_v18(origin, payload, runtime.rich)
    m.v18.submit_v18(receipt, clearing, runtime.rich)
    assert shape(views(runtime)) == shape(approved)


# ----------------------------------------------- rows with no Data Entry record

def old_expense(runtime, *, final=1000, paid=1000, method='CASH', description='هزینهٔ قدیمی'):
    """What an older version wrote straight into the ledger: no pending record,
    no posting."""

    db = runtime.db
    expense = db.create_expense(
        event_date='2026-09-20', shamsi_date='1405/06/29', final_amount=final, description=description,
        vendor_name='فروشندهٔ قدیمی', category='MATERIAL', construction_stage='اسکلت', cost_group='مصالح',
        plan_ref='OLD-LINE', status='APPROVED', source='LEGACY')
    transaction = None
    if paid:
        transaction = db.post_transaction(
            event_date='2026-09-20', shamsi_date='1405/06/29', direction='OUT', amount=paid,
            category='EXPENSE_PAYMENT', description=description, payer_name='پرداخت‌کننده',
            receiver_name='فروشندهٔ قدیمی', expense_id=expense)
        db.add_payment(expense_id=expense, payment_date='2026-09-20', payment_date_shamsi='1405/06/29',
                       amount=paid, method=method, transaction_id=transaction)
    return expense, transaction


def expense_row(runtime, expense):
    return next(r for r in runtime.service.list_construction_expenses() if r['expense_id'] == expense)


def test_an_old_expense_without_a_record_becomes_a_review_record(runtime):
    baseline = views(runtime)
    expense, transaction = old_expense(runtime)
    assert (runtime.db.snapshot().construction_cost, runtime.db.snapshot().cash_balance) == (1000, -1000)
    row = expense_row(runtime, expense)
    assert not row['pending_id'], 'the row has no Data Entry record'

    result = ReviewReturn(runtime.db).move_rows_to_review([row])

    assert len(result.created) == 1 and result.moved == result.created
    pid = result.created[0]
    assert views(runtime) == baseline, 'the old rows no longer count anywhere'
    item = runtime.db.get_pending_item(pid)
    assert item['status'] == 'PENDING_REVIEW'
    payload = item['payload']
    assert (payload['detected_type'], payload['v18_title'], payload['v18_subtype']) == ('EXPENSE', 'هزینه ساخت', 'نقدی')
    assert (payload['amount'], payload['paid_amount'], payload['payment_state']) == (1000, 1000, 'PAID')
    assert (payload['receiver_name'], payload['description'], payload['cost_group'], payload['plan_ref'],
            payload['event_date_shamsi']) == ('فروشندهٔ قدیمی', 'هزینهٔ قدیمی', 'مصالح', 'OLD-LINE', '1405/06/29')
    assert (payload['source'], payload['legacy_expense_id']) == ('LEGACY_REVIEW_187', expense)
    with runtime.db.read() as con:  # cancelled, never deleted
        assert con.execute('SELECT status FROM expenses WHERE expense_id=?', (expense,)).fetchone()[0] == 'CANCELLED'
        assert con.execute('SELECT status FROM transactions WHERE transaction_id=?',
                           (transaction,)).fetchone()[0] == 'VOIDED'
        assert con.execute('SELECT DISTINCT status FROM payments WHERE expense_id=?', (expense,)).fetchall()[0][0] == 'CANCELLED'
        assert con.execute("SELECT COUNT(*) FROM audit_log WHERE source='GUI_REVIEW_RETURN' AND action='REJECT'"
                           ).fetchone()[0] >= 3
    assert pid in {r['pending_id'] for r in runtime.approval.list_reviews(statuses=('PENDING_REVIEW',))}
    assert runtime.db.get_telegram_message(-187, int(item['telegram_message_id']))['state'] == 'PENDING_REVIEW'

    m.v18.submit_v18(pid, payload, runtime.rich)  # the operator approves it, and now it posts everywhere
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert (runtime.db.snapshot().construction_cost, runtime.db.snapshot().cash_balance) == (1000, -1000)
    assert runtime.db.get_financial_posting(pid) is not None


@pytest.mark.parametrize('paid,state', [(400, 'PARTIAL'), (0, 'UNPAID')])
def test_an_old_expense_keeps_how_much_of_it_was_paid(runtime, paid, state):
    expense, _ = old_expense(runtime, paid=paid)
    pid = ReviewReturn(runtime.db).move_rows_to_review([expense_row(runtime, expense)]).created[0]
    payload = runtime.db.get_pending_item(pid)['payload']
    assert (payload['payment_state'], payload['paid_amount'], payload['amount']) == (state, paid, 1000)
    assert runtime.db.snapshot().construction_cost == 0


@pytest.mark.parametrize('direction,detected,title', [('OUT', 'OUTFLOW', 'خروجی'), ('IN', 'INCOME', 'ورودی')])
def test_an_old_standalone_transaction_becomes_a_review_record(runtime, direction, detected, title):
    baseline = views(runtime)
    transaction = runtime.db.post_transaction(
        event_date='2026-09-21', shamsi_date='1405/06/30', direction=direction, amount=500,
        category='NON_CONSTRUCTION_OUTFLOW', description='تراکنش قدیمی', payer_name='صندوق',
        receiver_name='گیرنده')
    row = next(r for r in runtime.service.list_transactions() if r['transaction_id'] == transaction)
    assert not row['pending_id']
    pid = ReviewReturn(runtime.db).move_rows_to_review([row]).created[0]
    assert views(runtime) == baseline
    payload = runtime.db.get_pending_item(pid)['payload']
    assert (payload['detected_type'], payload['v18_title'], payload['amount'], payload['description'],
            payload['payer_name'], payload['receiver_name']) == (detected, title, 500, 'تراکنش قدیمی', 'صندوق', 'گیرنده')
    assert payload['legacy_transaction_id'] == transaction
    m.v18.submit_v18(pid, payload, runtime.rich)
    assert runtime.db.snapshot().cash_balance == (500 if direction == 'IN' else -500)


def test_a_transaction_row_of_an_old_expense_moves_the_whole_expense_once(runtime):
    expense, transaction = old_expense(runtime, paid=1000)
    tx_row = next(r for r in runtime.service.list_transactions() if r['transaction_id'] == transaction)
    result = ReviewReturn(runtime.db).move_rows_to_review([tx_row, expense_row(runtime, expense)])
    assert len(result.created) == 1, 'the expense and its payment are one entry'
    assert (runtime.db.snapshot().construction_cost, runtime.db.snapshot().cash_balance) == (0, 0)


def test_the_receipts_of_an_old_row_follow_it_into_review_and_onto_the_new_rows(runtime):
    expense, transaction = old_expense(runtime)
    with runtime.db.tx() as con:
        con.execute("INSERT INTO attachments(attachment_id,entity_type,entity_id,document_type,local_path,"
                    "mime_type,created_at) VALUES('ATT1','EXPENSE',?,'RECEIPT','x.png','image/png','2026-09-20')",
                    (expense,))
    pid = ReviewReturn(runtime.db).move_rows_to_review([expense_row(runtime, expense)]).created[0]
    assert [a['attachment_id'] for a in runtime.db.list_pending_attachments(pid)] == ['ATT1']
    assert not runtime.db.list_entity_attachments('EXPENSE', expense)
    assert audit_rows(runtime, entity_type='attachment', entity_id='ATT1', action='RELINK')
    m.v18.submit_v18(pid, runtime.db.get_pending_item(pid)['payload'], runtime.rich)
    new_expense = runtime.db.get_financial_posting(pid)['expense_id']
    assert [a['attachment_id'] for a in runtime.db.list_entity_attachments('EXPENSE', new_expense)] == ['ATT1']


# ------------------------------------------------- what is refused, and changes nothing

def test_an_old_expense_paid_by_cheque_is_refused(runtime):
    expense, _ = old_expense(runtime, paid=0)
    runtime.db.create_cheque(amount=1000, issue_date='2026-09-20', due_date='2026-10-20', expense_id=expense)
    before = views(runtime)
    with pytest.raises(LifecycleDecision, match='چک'):
        ReviewReturn(runtime.db).move_rows_to_review([expense_row(runtime, expense)])
    assert views(runtime) == before


def test_an_old_expense_with_a_document_on_it_is_refused(runtime):
    expense, _ = old_expense(runtime)
    runtime.rich.add_financial_document(None, {'document_type': 'DOCUMENT', 'description': 'سند'}, 'مدرک',
                                        [('EXPENSE', expense)])
    before = views(runtime)
    with pytest.raises(LifecycleDecision):
        ReviewReturn(runtime.db).move_rows_to_review([expense_row(runtime, expense)])
    assert views(runtime) == before


@pytest.mark.parametrize('extra', [{'cheque_id': 'C1'}, {'loan_id': 'L1'}, {'sale_id': 'S1'},
                                   {'document_id': 'D1'}, {'loan_installment_id': 'I1'}])
def test_old_rows_of_other_kinds_are_refused(runtime, extra):
    expense, _ = old_expense(runtime)
    before = views(runtime)
    with pytest.raises(LifecycleDecision, match='تعیین تکلیف'):
        ReviewReturn(runtime.db).move_rows_to_review([{**expense_row(runtime, expense), **extra}])
    assert views(runtime) == before


def test_one_refused_row_stops_the_rest_of_the_selection(runtime):
    approved, _ = approved_record(runtime)
    expense, _ = old_expense(runtime)
    before = views(runtime)
    with pytest.raises(LifecycleDecision):
        ReviewReturn(runtime.db).move_rows_to_review(
            [{'pending_id': approved}, {**expense_row(runtime, expense), 'cheque_id': 'C1'}])
    assert views(runtime) == before
    assert runtime.db.get_pending_item(approved)['status'] == 'APPROVED'


def test_a_failure_while_adopting_leaves_no_review_record_behind(runtime, monkeypatch):
    expense, _ = old_expense(runtime)
    before, pending = views(runtime), runtime.db.pending_counts()
    audit = runtime.db._audit

    def fail(con, entity, *args, **kwargs):
        if entity == 'pending':
            raise ValueError('injected failure after the review record was made')
        return audit(con, entity, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(runtime.db, '_audit', fail)
        with pytest.raises(ValueError):
            ReviewReturn(runtime.db).move_rows_to_review([expense_row(runtime, expense)])
    assert views(runtime) == before
    assert runtime.db.pending_counts() == pending
    with runtime.db.read() as con:
        assert con.execute('SELECT status FROM expenses WHERE expense_id=?', (expense,)).fetchone()[0] != 'CANCELLED'


# ------------------------------- deleted for good, rows still live (found in a real project)

def half_deleted(runtime):
    """A record deleted for good from Data Entry (rejected, purged, hidden) whose
    approval's rows are still live: its lifecycle snapshot was empty when it was
    deleted, so the deletion took nothing back."""

    pid, payload = approved_record(runtime)
    runtime.rich.hidden_review_ids()  # creates the hidden-reviews table
    with runtime.db.tx() as con:
        con.execute("UPDATE transaction_lifecycle SET state='PURGED',effects_json='[]',rejected_json='[]' "
                    "WHERE pending_id=?", (pid,))
        con.execute("UPDATE pending_items SET status='REJECTED' WHERE pending_id=?", (pid,))
        con.execute("UPDATE telegram_messages SET state='REJECTED',linked_entity_type='expense' "
                    "WHERE chat_id=-989 AND message_id=1")
        con.execute("INSERT INTO rich_ui_hidden_reviews(pending_id,hidden,updated_at) VALUES(?,1,'2026-10-01') "
                    "ON CONFLICT(pending_id) DO UPDATE SET hidden=1", (pid,))
    return pid, payload


def test_a_record_deleted_for_good_whose_rows_are_still_live_comes_back_to_review(runtime):
    baseline = views(runtime)
    pid, payload = half_deleted(runtime)
    posting = runtime.db.get_financial_posting(pid)
    assert posting['status'] == 'ACTIVE' and runtime.db.snapshot().construction_cost == 1000, 'the rows are live'
    assert pid not in {r['pending_id'] for r in runtime.approval.list_reviews()}, 'and Data Entry cannot show it'
    row = next(r for r in runtime.service.list_construction_expenses() if r['expense_id'] == posting['expense_id'])
    assert row['pending_id'] == pid, 'the expense row carries the deleted record id'
    with runtime.db.tx() as con:  # the receipts hang on the ledger rows, as approval leaves them
        for number, (kind, entity) in enumerate((('EXPENSE', posting['expense_id']),
                                                  ('EXPENSE', posting['expense_id']),
                                                  ('TRANSACTION', posting['transaction_id']))):
            con.execute("INSERT INTO attachments(attachment_id,entity_type,entity_id,document_type,local_path,"
                        "mime_type,created_at) VALUES(?,?,?,'RECEIPT','x.png','image/png','2026-09-30')",
                        (f'ATT{number}', kind, entity))

    mover = ReviewReturn(runtime.db)
    plan = mover.plan_move([row])
    assert (plan.sources, plan.revived, plan.already) == ([pid], [pid], [])
    assert 'قبلاً از ثبت دیتا حذف شده بود' in __import__('transaction_review_ui').question(plan)
    result = mover.run_move(plan)

    assert result.moved == [pid] and not result.created
    assert views(runtime) == baseline, 'the live rows no longer count anywhere'
    item = runtime.db.get_pending_item(pid)
    assert item['status'] == 'PENDING_REVIEW' and item['payload']['description'] == payload['description']
    assert pid in {r['pending_id'] for r in runtime.approval.list_reviews(statuses=('PENDING_REVIEW',))}
    assert pid not in runtime.rich.hidden_review_ids()
    assert TransactionLifecycle(runtime.db).get(pid) is None and runtime.db.get_financial_posting(pid) is None
    assert sorted(a['attachment_id'] for a in runtime.db.list_pending_attachments(pid)) == ['ATT0', 'ATT1', 'ATT2']
    with runtime.db.read() as con:
        assert con.execute('SELECT status FROM expenses WHERE expense_id=?',
                           (posting['expense_id'],)).fetchone()[0] == 'CANCELLED'
        assert tuple(con.execute("SELECT state,linked_entity_type FROM telegram_messages "
                                 "WHERE chat_id=-989 AND message_id=1").fetchone()) == ('PENDING_REVIEW', None)

    m.v18.submit_v18(pid, payload, runtime.rich)  # approving it posts afresh, receipts and all
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert (runtime.db.snapshot().construction_cost, runtime.db.snapshot().cash_balance) == (1000, -1000)
    new_expense = runtime.db.get_financial_posting(pid)['expense_id']
    assert new_expense != posting['expense_id']
    assert sorted(a['attachment_id'] for a in runtime.db.list_entity_attachments('EXPENSE', new_expense)) == [
        'ATT0', 'ATT1', 'ATT2']


def test_a_deleted_record_with_its_rows_properly_cancelled_is_not_returned(runtime):
    pid, _ = approved_record(runtime)
    TransactionLifecycle(runtime.db).reject(pid, permanent=True)
    before = views(runtime)
    with pytest.raises(LifecycleDecision, match='بازگردانی'):
        ReviewReturn(runtime.db).move_rows_to_review([{'pending_id': pid}])
    assert views(runtime) == before


# ------------------------------------------------------------------ Undo and Redo

def approver(runtime):
    """The approval Undo uses on the screens."""

    return lambda pid, payload: m.v18.submit_v18(pid, payload, runtime.rich)


def moved(runtime, pids, mover=None):
    mover = mover or ReviewReturn(runtime.db)
    return mover, mover.run_move(mover.plan_move([{'pending_id': pid} for pid in pids]))


@pytest.mark.parametrize('case', CASES, ids=[c[0] for c in CASES])
def test_each_type_can_be_moved_undone_and_redone(runtime, case):
    payload = case_payload(runtime, case)
    baseline = views(runtime)
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, payload, runtime.rich)
    approved = views(runtime)
    # Loans, sales, installments, guarantees and notes are approved without a posting row.
    had_posting = runtime.db.get_financial_posting(pid) is not None
    mover, result = moved(runtime, [pid])
    assert result.moved == [pid] and views(runtime) == baseline

    assert mover.undo_move(result, approver(runtime)) == [pid]
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert shape(views(runtime)) == shape(approved), 'Undo puts the effect back where it was'
    assert (runtime.db.get_financial_posting(pid) is not None) == had_posting
    assert TransactionLifecycle(runtime.db).get(pid)['state'] == 'ACTIVE', 'and it is an ordinary approved record'

    assert mover.redo_move(result) == [pid]
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'
    assert views(runtime) == baseline, 'Redo takes it away again'

    mover.undo_move(result, approver(runtime))  # and it goes on, as often as it is asked
    assert shape(views(runtime)) == shape(approved)


def test_undo_brings_a_cheque_back_before_the_receipt_that_cleared_it(runtime):
    payload = case_payload(runtime, CASES[3])
    baseline = views(runtime)
    origin = register(runtime, payload)
    m.v18.submit_v18(origin, payload, runtime.rich)
    clearing = {**payload, 'v18_subtype': 'نقدی', 'detected_type': 'EXPENSE', 'payment_method': 'BANK_TRANSFER',
                'is_cheque': False, 'payment_state': 'CHEQUE_CLEARING'}
    receipt = register(runtime, clearing, 2)
    m.v18.submit_v18(receipt, clearing, runtime.rich)
    approved = views(runtime)
    mover, result = moved(runtime, [origin])
    assert result.moved == [receipt, origin] and views(runtime) == baseline

    assert mover.undo_move(result, approver(runtime)) == [origin, receipt], 'the cheque first, then its receipt'
    assert {runtime.db.get_pending_item(pid)['status'] for pid in (origin, receipt)} == {'APPROVED'}
    assert shape(views(runtime)) == shape(approved)
    assert set(mover.redo_move(result)) == {origin, receipt} and views(runtime) == baseline


def test_undo_is_refused_when_a_record_was_edited_since_the_move(runtime):
    pid, payload = approved_record(runtime)
    mover, result = moved(runtime, [pid])
    baseline = views(runtime)
    runtime.db.update_pending(pid, payload={**payload, 'description': 'ویرایش پس از انتقال'})
    with pytest.raises(LifecycleDecision, match='تغییر کرده‌اند'):
        mover.undo_move(result, approver(runtime))
    assert views(runtime) == baseline
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'
    assert runtime.db.get_financial_posting(pid) is None


def test_undo_is_refused_when_a_record_was_approved_again_by_hand(runtime):
    pid, payload = approved_record(runtime)
    mover, result = moved(runtime, [pid])
    m.v18.submit_v18(pid, payload, runtime.rich)
    approved = views(runtime)
    with pytest.raises(LifecycleDecision, match='تغییر کرده‌اند'):
        mover.undo_move(result, approver(runtime))
    assert views(runtime) == approved, 'nothing was posted a second time'


def test_undo_is_refused_when_a_record_is_gone(runtime):
    pid, _ = approved_record(runtime)
    mover, result = moved(runtime, [pid])
    result.moved.append('P-missing')
    with pytest.raises(LifecycleDecision, match='تغییر کرده‌اند'):
        mover.undo_move(result, approver(runtime))
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'


def test_undo_is_all_or_none_and_puts_the_contracts_file_back(runtime):
    from contractor_store_stage18_7 import get_contract, upsert_contract
    upsert_contract({'contract_id': 'C1', 'title': 'آزمون', 'total_amount': 5000, 'payments': []})
    first, _ = approved_record(runtime, message_id=1, contract_id='C1', cost_group='پیمانکار')
    second, _ = approved_record(runtime, message_id=2)
    mover, result = moved(runtime, [first, second])
    after_move, contract = views(runtime), get_contract('C1')
    assert not contract['payments']
    calls = []

    def fails_on_the_second(pid, payload):
        calls.append(pid)
        if len(calls) == 2:
            raise ValueError('injected approval failure')
        return m.v18.submit_v18(pid, payload, runtime.rich)

    with pytest.raises(ValueError, match='injected'):
        mover.undo_move(result, fails_on_the_second)
    assert len(calls) == 2
    assert views(runtime) == after_move, 'the first approval was rolled back with the second'
    assert {runtime.db.get_pending_item(pid)['status'] for pid in (first, second)} == {'PENDING_REVIEW'}
    assert runtime.db.get_financial_posting(first) is None
    assert get_contract('C1') == contract, 'the payment the first approval wrote on the contract is off again'
    # Nothing was lost: the same Undo goes through once the failure is gone.
    mover.undo_move(result, approver(runtime))
    assert {runtime.db.get_pending_item(pid)['status'] for pid in (first, second)} == {'APPROVED'}
    assert sum(1 for p in get_contract('C1')['payments']) == 1


def test_a_contract_payment_goes_off_and_comes_back_with_undo_and_redo(runtime):
    from contractor_store_stage18_7 import amount_of, get_contract, upsert_contract
    upsert_contract({'contract_id': 'C1', 'title': 'قرارداد آزمون', 'total_amount': 2000, 'payments': []})
    pid, _ = approved_record(runtime, contract_id='C1', cost_group='پیمانکار')
    paid = lambda: sum(amount_of(p['amount']) for p in get_contract('C1')['payments'])  # noqa: E731
    mover, result = moved(runtime, [pid])
    assert paid() == 0
    mover.undo_move(result, approver(runtime))
    assert paid() == 1000
    mover.redo_move(result)
    assert paid() == 0


def test_redo_is_refused_when_a_record_was_rejected_after_undo(runtime):
    pid, _ = approved_record(runtime)
    mover, result = moved(runtime, [pid])
    mover.undo_move(result, approver(runtime))
    TransactionLifecycle(runtime.db).reject(pid)
    rejected = views(runtime)
    with pytest.raises(LifecycleDecision, match='تغییر کرده‌اند'):
        mover.redo_move(result)
    assert views(runtime) == rejected and runtime.db.get_pending_item(pid)['status'] == 'REJECTED'


def test_what_redo_moves_is_what_a_later_undo_approves(runtime):
    """A record that came to lean on one of the group after Undo goes back with it on Redo."""

    payload = case_payload(runtime, CASES[3])
    origin = register(runtime, payload)
    m.v18.submit_v18(origin, payload, runtime.rich)
    mover, result = moved(runtime, [origin])
    assert result.moved == [origin]
    mover.undo_move(result, approver(runtime))
    clearing = {**payload, 'v18_subtype': 'نقدی', 'detected_type': 'EXPENSE', 'payment_method': 'BANK_TRANSFER',
                'is_cheque': False, 'payment_state': 'CHEQUE_CLEARING'}
    receipt = register(runtime, clearing, 2)
    m.v18.submit_v18(receipt, clearing, runtime.rich)
    approved = views(runtime)

    assert set(mover.redo_move(result)) == {origin, receipt}
    assert set(result.moved) == {origin, receipt}
    mover.undo_move(result, approver(runtime))
    assert shape(views(runtime)) == shape(approved)
    assert {runtime.db.get_pending_item(pid)['status'] for pid in (origin, receipt)} == {'APPROVED'}


def test_an_old_row_moved_to_review_comes_back_on_undo_as_an_approved_record(runtime):
    expense, _ = old_expense(runtime)
    row = expense_row(runtime, expense)
    mover = ReviewReturn(runtime.db)
    result = mover.move_rows_to_review([row])
    (pid,) = result.created
    assert (runtime.db.snapshot().construction_cost, runtime.db.snapshot().cash_balance) == (0, 0)

    mover.undo_move(result, approver(runtime))
    assert (runtime.db.snapshot().construction_cost, runtime.db.snapshot().cash_balance) == (1000, -1000)
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert runtime.db.get_financial_posting(pid) is not None, 'Data Entry now has the record the old row never had'

    mover.redo_move(result)
    assert (runtime.db.snapshot().construction_cost, runtime.db.snapshot().cash_balance) == (0, 0)
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'


def test_a_record_deleted_for_good_comes_back_on_undo_approved_and_visible(runtime):
    pid, payload = half_deleted(runtime)
    live = views(runtime)
    posting = runtime.db.get_financial_posting(pid)
    row = next(r for r in runtime.service.list_construction_expenses() if r['expense_id'] == posting['expense_id'])
    mover = ReviewReturn(runtime.db)
    result = mover.run_move(mover.plan_move([row]))
    baseline = views(runtime)
    assert result.moved == [pid] and runtime.db.snapshot().construction_cost == 0

    mover.undo_move(result, approver(runtime))
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert shape(views(runtime)) == shape(live), 'the effect is live again, once'
    assert runtime.db.get_financial_posting(pid)['status'] == 'ACTIVE'
    assert pid not in runtime.rich.hidden_review_ids(), 'and Data Entry shows the record'
    assert runtime.db.get_financial_posting(pid)['expense_id'] != posting['expense_id']

    mover.redo_move(result)
    assert views(runtime) == baseline
