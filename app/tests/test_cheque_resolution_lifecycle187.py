"""Rejecting a resolution undoes it; rejecting the issue takes its resolutions along."""
from pathlib import Path
import pytest
from test_cheque_workflow187 import cheque_payload
from test_transaction_lifecycle_matrix import m, runtime, register
from transaction_lifecycle import TransactionLifecycle

STATUSES = ['پاس‌شده', 'برگشتی', 'عودتی به شرط تسویه', 'باطل‌شده']


def _issue(runtime):
    payload = cheque_payload()
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, payload, runtime.rich)
    return pid, runtime.db.list_cheques(open_only=False)[0]['cheque_id']


def _resolve(runtime, cheque_id, status, message_id, *, attach=None):
    payload = cheque_payload()
    payload.update(cheque_operation187=m.CHEQUE_OPERATION_RESOLVE_187, selected_cheque_id187=cheque_id,
                   cheque_resolution_status187=status, cheque_return_account_holder187='حساب معرفی‌شده',
                   cheque_void_reason187='دلیل ابطال',
                   cheque_return_disposition187=m.CHEQUE_RETURN_DISPOSITION_CHOICES_187[3])
    pid = register(runtime, payload, message_id)
    if attach:
        path = Path(runtime.db.db_path).parent / attach
        path.write_text(attach, encoding='utf-8')
        runtime.service.attachments.add_local(entity_type='PENDING', entity_id=pid, source_path=path)
    m._approve_cheque_resolution_187(pid, payload)
    return pid


def _ledger(runtime):
    with runtime.db.read() as con:
        return {
            'cheques': [tuple(r) for r in con.execute(
                'SELECT cheque_id,status,settlement_mode,registration_state,return_disposition,return_account_holder,void_reason FROM cheques')],
            'payments': sorted(r[0] for r in con.execute('SELECT status FROM payments')),
            'expenses': sorted(r[0] for r in con.execute('SELECT status FROM expenses')),
            'cost': runtime.db.snapshot().construction_cost,
            'cash': runtime.db.snapshot().cash_balance,
        }


@pytest.mark.parametrize('status', STATUSES)
def test_rejecting_a_resolution_returns_the_cheque_to_before_it_was_resolved(runtime, status):
    issue, cheque_id = _issue(runtime)
    before = _ledger(runtime)
    resolution = _resolve(runtime, cheque_id, status, 2, attach='resolution-proof.txt')
    assert _ledger(runtime) != before

    runtime.approval.reject(resolution)

    assert runtime.db.get_pending_item(resolution)['status'] == 'REJECTED'
    assert _ledger(runtime) == before
    assert runtime.db.get_pending_item(issue)['status'] == 'APPROVED'
    assert runtime.db.get_pending_item(issue)['payload']['cheque_status'] == 'ISSUED'
    # the receipt it brought is back on the record, and the record is no longer the cheque's
    with runtime.db.read() as con:
        assert con.execute("SELECT COUNT(*) FROM attachments WHERE entity_type='CHEQUE' AND entity_id=? "
                           "AND local_path LIKE '%resolution-proof%'", (cheque_id,)).fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM attachments WHERE entity_type='PENDING' AND entity_id=?",
                           (resolution,)).fetchone()[0] == 1
    # and the cheque can be resolved again with a new record
    again = _resolve(runtime, cheque_id, 'پاس‌شده', 3)
    assert runtime.db.get_pending_item(again)['status'] == 'APPROVED'
    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == 'پاس‌شده'


def test_rejecting_the_issue_takes_the_resolution_along_and_the_resolution_is_approved_on_its_own_after(runtime):
    issue, cheque_id = _issue(runtime)
    empty = {'cost': 0, 'cash': 0}
    approved = _ledger(runtime)
    resolution = _resolve(runtime, cheque_id, 'پاس‌شده', 2)

    assert TransactionLifecycle(runtime.db)._cheque_dependents(issue) == [resolution]
    runtime.approval.reject(issue)

    assert runtime.db.get_pending_item(issue)['status'] == 'REJECTED'
    assert runtime.db.get_pending_item(resolution)['status'] == 'REJECTED'
    state = _ledger(runtime)
    assert state['cost'] == 0 and state['cash'] == 0 and state['payments'] != approved['payments']

    # restoring the issue brings the cheque and its cost back; the resolution that was rejected
    # with it returns to review, where it can be approved on its own
    TransactionLifecycle(runtime.db).restore(issue)
    assert runtime.db.get_pending_item(issue)['status'] == 'APPROVED'
    assert runtime.db.get_pending_item(resolution)['status'] == 'PENDING_REVIEW'
    assert _ledger(runtime) == approved
    m._approve_cheque_resolution_187(resolution, runtime.db.get_pending_item(resolution)['payload'])
    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == 'پاس‌شده'
    assert runtime.db.get_pending_item(resolution)['status'] == 'APPROVED'
    assert len(runtime.db.list_cheques(open_only=False)) == 1


def test_moving_a_resolved_cheque_to_review_takes_both_records_back_and_removes_the_effect(runtime):
    from transaction_review import ReviewReturn
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'پاس‌شده', 2)

    moved = ReviewReturn(runtime.db).return_to_review([issue])

    assert set(moved) == {issue, resolution}
    assert runtime.db.get_pending_item(issue)['status'] == 'PENDING_REVIEW'
    assert runtime.db.get_pending_item(resolution)['status'] == 'PENDING_REVIEW'
    state = _ledger(runtime)
    assert state['cost'] == 0 and state['cash'] == 0
    # approving the issue again brings the cheque back; the resolution is then approved on its own
    m.v18.submit_v18(issue, runtime.db.get_pending_item(issue)['payload'], runtime.rich)
    assert len(runtime.db.list_cheques(open_only=False)) == 1


def test_the_confirmation_says_what_rejecting_does_to_the_cheque(runtime):
    from transaction_lifecycle_ui import cheque_reject_notice
    issue, cheque_id = _issue(runtime)
    assert cheque_reject_notice(runtime.db, [issue]) == ''
    resolution = _resolve(runtime, cheque_id, 'پاس‌شده', 2)
    assert 'پیش از تعیین تکلیف' in cheque_reject_notice(runtime.db, [resolution])
    assert 'رکورد تعیین تکلیف همان چک هم به ردشده‌ها' in cheque_reject_notice(runtime.db, [issue])
