"""Editing a resolved cheque from its row: both records under review, nothing lost on cancel."""
import pytest
from test_cheque_resolution_lifecycle187 import _issue, _resolve, _ledger
from test_cheque_workflow187 import cheque_payload
from test_transaction_lifecycle_matrix import m, runtime, register
from cheque_record_edit187 import ChequeRecordSession187, pending_ids


def _session(runtime, cheque_id):
    ids = pending_ids(runtime.db, cheque_id)
    return ChequeRecordSession187(runtime.db, cheque_id, ids[0]), ids


def _form_payload(runtime, session, **changes):
    payload = dict(session.before['payload'])
    cheque = runtime.db.get_cheque(session.cheque_id)
    payload.update(v18_title='هزینه ساخت', v18_subtype='چک', cheque_operation187=m.CHEQUE_OPERATION_ISSUE_187,
                   _cheque_record_id187=session.cheque_id, event_date_shamsi=cheque['issue_date_shamsi'],
                   due_date_shamsi=cheque['due_date_shamsi'], amount=cheque['amount'],
                   cheque_status=m._cheque_status_label_187(cheque),
                   cheque_registration_state=cheque['registration_state'],
                   cheque_return_disposition187=cheque.get('return_disposition') or '',
                   cheque_return_account_holder187=cheque.get('return_account_holder') or '',
                   cheque_void_reason187=cheque.get('void_reason') or '')
    for key in ('issuer_name', 'issuer_bank', 'receiver_name', 'description', 'cheque_serial', 'cheque_type', 'is_guarantee'):
        payload[key] = cheque.get(key)
    payload.update(changes)
    return payload


def test_the_issue_record_is_the_one_the_row_editor_opens(runtime):
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'پاس‌شده', 2)
    session, ids = _session(runtime, cheque_id)
    assert ids[0] == issue and set(ids) == {issue, resolution}


def test_editing_the_row_puts_both_records_under_review_and_offers_the_cheque_for_resolution(runtime):
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'پاس‌شده', 2)
    session, _ = _session(runtime, cheque_id)
    assert cheque_id not in {row['cheque_id'] for row in m._registered_cheques_for_clearing_187()}

    session.under_review()

    assert runtime.db.get_pending_item(issue)['status'] == 'EDIT_PENDING'
    assert runtime.db.get_pending_item(resolution)['status'] == 'EDIT_PENDING'
    assert cheque_id in {row['cheque_id'] for row in m._registered_cheques_for_clearing_187()}


def test_closing_without_approving_gives_back_both_records_and_the_cheque_unchanged(runtime):
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'باطل‌شده', 2)
    before = (_ledger(runtime), runtime.db.get_pending_item(issue)['payload'], runtime.db.get_pending_item(resolution)['payload'])
    session, _ = _session(runtime, cheque_id)
    session.under_review()

    session.cancel()

    assert runtime.db.get_pending_item(issue)['status'] == 'APPROVED'
    assert runtime.db.get_pending_item(resolution)['status'] == 'APPROVED'
    assert (_ledger(runtime), runtime.db.get_pending_item(issue)['payload'],
            runtime.db.get_pending_item(resolution)['payload']) == before


def test_approving_an_edit_of_the_issue_leaves_the_resolution_status_alone(runtime):
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'برگشتی', 2)
    session, _ = _session(runtime, cheque_id)
    session.under_review()

    session.approve(_form_payload(runtime, session, issuer_bank='بانک ویرایش‌شده'), m)

    assert runtime.db.get_cheque(cheque_id)['issuer_bank'] == 'بانک ویرایش‌شده'
    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == 'برگشتی'
    assert runtime.db.get_pending_item(resolution)['status'] == 'APPROVED'
    assert runtime.db.get_pending_item(issue)['status'] == 'APPROVED'
    assert len(runtime.db.list_cheques(open_only=False)) == 1


def test_changing_a_voided_cheque_to_cashed_in_the_row_gives_its_payment_back(runtime):
    issue, cheque_id = _issue(runtime)
    issued = _ledger(runtime)
    _resolve(runtime, cheque_id, 'باطل‌شده', 2)
    assert _ledger(runtime)['payments'] == ['CANCELLED']
    session, _ = _session(runtime, cheque_id)
    session.under_review()

    session.approve(_form_payload(runtime, session, cheque_status='پاس‌شده'), m)

    state = _ledger(runtime)
    assert state['payments'] == issued['payments'] and state['cost'] == issued['cost']
    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == 'پاس‌شده'


# --- a status changed by hand always leaves a resolution record -----------------------------------
def test_a_status_changed_by_hand_on_an_unresolved_cheque_gets_a_resolution_record(runtime):
    from record_ownership187 import assert_no_orphans
    from transaction_lifecycle import is_new_resolution
    issue, cheque_id = _issue(runtime)
    session, _ = _session(runtime, cheque_id)
    session.under_review()

    session.approve(_form_payload(runtime, session, cheque_status='پاس‌شده'), m)

    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == 'پاس‌شده'
    resolutions = [pid for pid in pending_ids(runtime.db, cheque_id) if pid != issue]
    assert len(resolutions) == 1 and session.resolution_pid == resolutions[0]
    record = runtime.db.get_pending_item(resolutions[0])
    assert record['status'] == 'APPROVED' and is_new_resolution(record['payload'])
    assert runtime.db.get_pending_item(issue)['status'] == 'APPROVED'
    assert_no_orphans(runtime.db)
    # the new record is an ordinary resolution: rejecting it puts the cheque back
    runtime.approval.reject(resolutions[0])
    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == 'صادرشده'


def test_a_hand_made_return_on_settlement_without_its_holder_is_refused_unless_it_is_to_be_completed_later(runtime):
    issue, cheque_id = _issue(runtime)
    session, _ = _session(runtime, cheque_id)
    session.under_review()
    changes = dict(cheque_status='عودتی به شرط تسویه', cheque_return_account_holder187='')
    with pytest.raises(ValueError):
        session.approve(_form_payload(runtime, session, **changes), m)
    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == 'صادرشده'

    session.approve(_form_payload(runtime, session, **changes), m, require_details=False)

    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == 'عودتی به شرط تسویه'
    assert runtime.db.get_pending_item(session.resolution_pid)['status'] == 'APPROVED'


def test_changing_a_resolved_status_by_hand_follows_into_the_resolution_record(runtime):
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'برگشتی', 2)
    session, _ = _session(runtime, cheque_id)
    session.under_review()

    session.approve(_form_payload(runtime, session, cheque_status='پاس‌شده'), m)

    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == 'پاس‌شده'
    assert runtime.db.get_pending_item(resolution)['payload']['cheque_status'] == 'CASHED'
    assert [pid for pid in pending_ids(runtime.db, cheque_id) if pid != issue] == [resolution]
    assert session.resolution_pid == resolution


def test_setting_a_resolved_cheque_back_to_issued_takes_its_resolution_back(runtime):
    from record_ownership187 import assert_no_orphans
    issue, cheque_id = _issue(runtime)
    issued = _ledger(runtime)
    resolution = _resolve(runtime, cheque_id, 'باطل‌شده', 2)
    session, _ = _session(runtime, cheque_id)
    session.under_review()

    session.approve(_form_payload(runtime, session, cheque_status='صادرشده'), m)

    assert runtime.db.get_pending_item(resolution)['status'] == 'REJECTED'
    assert _ledger(runtime) == issued
    assert runtime.db.get_pending_item(issue)['status'] == 'APPROVED'
    assert_no_orphans(runtime.db)
