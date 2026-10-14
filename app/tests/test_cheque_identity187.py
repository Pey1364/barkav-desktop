"""One cheque is one row for good: editing, returning to review and approving again never
makes a second row, never leaves a «باطل‌شده» leftover and never changes the cheque's id."""
import json
import pytest
from test_cheque_resolution_lifecycle187 import _issue, _resolve, _ledger, STATUSES
from test_cheque_workflow187 import cheque_payload
from test_transaction_lifecycle_matrix import m, runtime, register
from transaction_lifecycle import TransactionLifecycle


def _cheque_rows(runtime):
    with runtime.db.read() as con:
        return [dict(r) for r in con.execute('SELECT * FROM cheques')]


def _tab_rows(runtime):
    """What the cheque tab lists (the dashboard service, not the narrower database list)."""
    return runtime.service.list_cheques(open_only=False)


def _bundle_issue(runtime):
    """The older way an issue was approved: a one-cheque list on the payload (no expense posting)."""
    payload = cheque_payload()
    payload['cheques'] = [dict(amount=payload['amount'], due_date_shamsi=payload['due_date_shamsi'],
                               cheque_serial=payload['cheque_serial'], issuer_bank=payload['issuer_bank'])]
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, payload, runtime.rich)
    return pid, _cheque_rows(runtime)[0]['cheque_id']


def _edited(runtime, pid, **changes):
    payload = dict(runtime.db.get_pending_item(pid)['payload'])
    payload.update(changes)
    return payload


@pytest.mark.parametrize('status', STATUSES)
def test_editing_the_issue_in_data_entry_keeps_the_row_and_the_resolution(runtime, status):
    issue, cheque_id = _issue(runtime)
    _resolve(runtime, cheque_id, status, 2)
    resolved = runtime.db.get_cheque(cheque_id)

    m.v18.submit_v18(issue, _edited(runtime, issue, issuer_bank='بانک ویرایش‌شده'), runtime.rich)

    rows = _cheque_rows(runtime)
    assert [row['cheque_id'] for row in rows] == [cheque_id]
    now = runtime.db.get_cheque(cheque_id)
    assert now['issuer_bank'] == 'بانک ویرایش‌شده'
    for column in ('status', 'settlement_mode', 'return_disposition', 'return_account_holder', 'void_reason'):
        assert now[column] == resolved[column], column
    assert m._cheque_status_label_187(now) == status
    assert len(_tab_rows(runtime)) == 1


def test_editing_a_bundle_issue_reposts_it_on_the_same_cheque_row(runtime):
    issue, cheque_id = _bundle_issue(runtime)

    m.v18.submit_v18(issue, _edited(runtime, issue, issuer_bank='بانک ویرایش‌شده'), runtime.rich)

    assert [row['cheque_id'] for row in _cheque_rows(runtime)] == [cheque_id]
    assert runtime.db.get_cheque(cheque_id)['issuer_bank'] == 'بانک ویرایش‌شده'
    assert len(_tab_rows(runtime)) == 1


@pytest.mark.parametrize('status', STATUSES)
def test_editing_a_bundle_issue_after_it_was_resolved_keeps_the_resolution(runtime, status):
    issue, cheque_id = _bundle_issue(runtime)
    _resolve(runtime, cheque_id, status, 2)

    m.v18.submit_v18(issue, _edited(runtime, issue, issuer_bank='بانک ویرایش‌شده'), runtime.rich)

    assert [row['cheque_id'] for row in _cheque_rows(runtime)] == [cheque_id]
    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == status
    assert len(_tab_rows(runtime)) == 1


def test_returning_a_resolved_cheque_to_review_and_approving_both_again_keeps_its_id(runtime):
    from transaction_review import ReviewReturn
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'پاس‌شده', 2)
    ReviewReturn(runtime.db).return_to_review([issue])

    m.v18.submit_v18(issue, runtime.db.get_pending_item(issue)['payload'], runtime.rich)
    m._approve_cheque_resolution_187(resolution, runtime.db.get_pending_item(resolution)['payload'])

    assert [row['cheque_id'] for row in _cheque_rows(runtime)] == [cheque_id]
    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == 'پاس‌شده'
    assert len(_tab_rows(runtime)) == 1
    assert runtime.db.get_pending_item(resolution)['status'] == 'APPROVED'


def test_the_cheque_tab_lists_no_leftover_of_a_reversed_posting(runtime):
    issue, cheque_id = _bundle_issue(runtime)
    from transaction_review import ReviewReturn
    ReviewReturn(runtime.db).return_to_review([issue])
    # the cheque the record made is taken back with it, nothing is left behind in the tab
    assert _tab_rows(runtime) == []
    m.v18.submit_v18(issue, runtime.db.get_pending_item(issue)['payload'], runtime.rich)
    assert [row['cheque_id'] for row in _tab_rows(runtime)] == [cheque_id]


def test_the_cheque_tab_finds_the_issue_record_of_a_bundle_cheque_before_its_resolution(runtime):
    from cheque_record_edit187 import pending_ids
    issue, cheque_id = _bundle_issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'برگشتی', 2)
    assert pending_ids(runtime.db, cheque_id) == [issue, resolution]


def test_a_resolution_record_that_does_not_remember_the_cheques_state_can_still_be_taken_back(runtime):
    """Records from before the state was kept: undoing them puts back the issue's state, with the
    columns the database does not allow to be empty at their defaults."""
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'عودتی به شرط تسویه', 2)
    payload = dict(runtime.db.get_pending_item(resolution)['payload'])
    payload.pop('_resolution_before187')
    runtime.db.update_pending(resolution, payload=payload)

    runtime.approval.reject(resolution)

    cheque = runtime.db.get_cheque(cheque_id)
    assert m._cheque_status_label_187(cheque) == 'صادرشده'
    assert cheque['return_account_holder'] == '' and cheque['void_reason'] == ''


def test_the_registration_a_resolution_changed_does_not_stop_the_issue_being_taken_back(runtime):
    from transaction_review import ReviewReturn
    payload = cheque_payload()
    payload['cheque_registration_state'] = 'UNREGISTERED'
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, payload, runtime.rich)
    cheque_id = runtime.db.list_cheques(open_only=False)[0]['cheque_id']
    assert runtime.db.get_cheque(cheque_id)['registration_state'] == 'UNREGISTERED'
    resolution = _resolve(runtime, cheque_id, 'پاس‌شده', 2)   # its form says «ثبت‌شده»
    assert runtime.db.get_cheque(cheque_id)['registration_state'] == 'REGISTERED'

    moved = ReviewReturn(runtime.db).return_to_review([pid])

    assert set(moved) == {pid, resolution}
    runtime.approval.reject(pid)  # nothing is left to refuse it


def test_a_cheque_the_new_approval_leaves_out_stays_taken_back_even_if_it_was_resolved(runtime):
    """A two-cheque bundle edited down to one cheque: the other, resolved, is not brought back to life."""
    from record_ownership187 import assert_no_orphans
    payload = cheque_payload()
    payload['cheques'] = [
        dict(amount=600000, due_date_shamsi='1405/08/08', cheque_serial='111', issuer_bank='بانک یک'),
        dict(amount=600000, due_date_shamsi='1405/09/08', cheque_serial='222', issuer_bank='بانک دو')]
    issue = register(runtime, payload)
    m.v18.submit_v18(issue, payload, runtime.rich)
    first, second = sorted(_cheque_rows(runtime), key=lambda row: (row['created_at'], row['cheque_id']))
    _resolve(runtime, second['cheque_id'], 'برگشتی', 2)

    edited = _edited(runtime, issue, amount=600000, final_amount=600000, invoice_amount=600000)
    edited['cheques'] = edited['cheques'][:1]
    m.v18.submit_v18(issue, edited, runtime.rich)

    left_out = runtime.db.get_cheque(second['cheque_id'])
    assert left_out['status'] == 'CANCELLED' and left_out['settlement_mode'] != 'VOIDED'
    assert [row['cheque_id'] for row in runtime.service.list_cheques(open_only=False)] == [first['cheque_id']]
    assert_no_orphans(runtime.db)


def test_a_copy_of_a_record_never_takes_over_a_cheque_row(runtime):
    from table_actions import copy_payload
    from transaction_review import ReviewReturn
    issue, cheque_id = _issue(runtime)
    ReviewReturn(runtime.db).return_to_review([issue])
    payload = runtime.db.get_pending_item(issue)['payload']
    assert payload['_cheque_hint187'][0]['cheque_id'] == cheque_id
    assert '_cheque_hint187' not in copy_payload(payload)

    # even if a token travelled with a copy, a cheque that is live again is not written over
    m.v18.submit_v18(issue, payload, runtime.rich)
    other = dict(payload)
    copy = register(runtime, other, 5)
    assert runtime.db.get_pending_item(copy)['payload']['_cheque_hint187'][0]['cheque_id'] == cheque_id
    m.v18.submit_v18(copy, runtime.db.get_pending_item(copy)['payload'], runtime.rich)
    rows = _cheque_rows(runtime)
    assert len(rows) == 2 and cheque_id in {row['cheque_id'] for row in rows}
    assert runtime.db.get_cheque(cheque_id)['status'] == 'ISSUED'


def test_a_cheque_cancelled_on_purpose_while_its_record_stands_is_still_a_row(runtime):
    """Only what a taken-back approval leaves is hidden from the cheque tab, not what the user cancelled."""
    issue, cheque_id = _issue(runtime)
    runtime.db.cancel_cheque(cheque_id, source='LEGACY')
    assert runtime.db.get_cheque(cheque_id)['status'] == 'CANCELLED'
    assert [row['cheque_id'] for row in _tab_rows(runtime)] == [cheque_id]
