"""Rejecting an approved record that is open for editing removes its financial effect."""
from test_transaction_lifecycle_matrix import runtime, register, case_payload, CASES, m
from transaction_lifecycle import TransactionLifecycle

CASE = {case[0]: case for case in CASES}


def _approved_then_staged_edit(runtime, message_id=7000):
    """Posted by the bot (no lifecycle entry), then an unapproved edit is staged."""
    payload = case_payload(runtime, CASE['cash-paid'])
    pid = register(runtime, dict(payload), message_id)
    runtime.approval._approve_without_lifecycle(pid)
    approved_cash = runtime.db.snapshot().cash_balance
    edited = dict(payload, amount=2500, paid_amount=2500)
    runtime.db.begin_posting_revision(pending_id=pid, new_payload=edited, source='GUI_187_EDIT', actor_id='GUI')
    item = runtime.db.get_pending_item(pid)
    assert item['status'] == 'EDIT_PENDING'
    assert runtime.db.snapshot().cash_balance == approved_cash
    return pid, payload, approved_cash


def test_rejecting_a_record_in_edit_removes_its_money_and_moves_it_to_rejected(runtime):
    pid, payload, approved_cash = _approved_then_staged_edit(runtime)
    assert approved_cash != 0

    runtime.approval.reject(pid)

    item = runtime.db.get_pending_item(pid)
    assert item['status'] == 'REJECTED'
    assert runtime.db.snapshot().cash_balance == 0
    assert runtime.db.get_financial_posting(pid)['status'] != 'ACTIVE'
    with runtime.db.read() as con:
        assert con.execute("SELECT COUNT(*) FROM posting_revisions WHERE pending_id=? AND status='PENDING'", (pid,)).fetchone()[0] == 0


def test_restoring_that_rejected_record_brings_back_what_was_approved_not_the_edit(runtime):
    pid, payload, approved_cash = _approved_then_staged_edit(runtime, 7001)
    runtime.approval.reject(pid)

    TransactionLifecycle(runtime.db).restore(pid)

    item = runtime.db.get_pending_item(pid)
    assert item['status'] == 'APPROVED'
    assert item['payload'].get('amount') == payload['amount']
    assert runtime.db.snapshot().cash_balance == approved_cash
    assert runtime.db.get_financial_posting(pid)['status'] == 'ACTIVE'


def test_rejecting_an_approved_record_that_is_not_in_edit_still_works(runtime):
    payload = case_payload(runtime, CASE['cash-paid'])
    pid = register(runtime, dict(payload), 7002)
    runtime.approval._approve_without_lifecycle(pid)
    assert runtime.db.snapshot().cash_balance != 0

    runtime.approval.reject(pid)

    assert runtime.db.get_pending_item(pid)['status'] == 'REJECTED'
    assert runtime.db.snapshot().cash_balance == 0
