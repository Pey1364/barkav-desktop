"""RED LINE: no financial row exists without a Data Entry record behind it.

record_ownership187 is the definition. Every kind of record the app approves is taken through its
whole life (approve, edit, resolve, take back, approve again, reject, restore) and after each step no
live ledger row may be without an owner, and no row may be left behind by a step that took one back.
"""
import pytest
from test_cheque_identity187 import _bundle_issue, _cheque_rows, _edited
from test_cheque_resolution_lifecycle187 import _issue, _resolve, STATUSES
from test_transaction_lifecycle_matrix import CASES, case_payload, m, runtime, register
from record_ownership187 import RedLineViolation, assert_no_orphans, orphan_rows
from transaction_lifecycle import TransactionLifecycle


def test_an_empty_project_has_no_orphan(runtime):
    assert orphan_rows(runtime.db) == []
    assert_no_orphans(runtime.db)


def test_a_cheque_made_without_a_record_is_a_violation(runtime):
    cheque_id = runtime.db.create_cheque(amount=1000, issue_date='2026-09-30', due_date='2026-10-30',
                                         issue_date_shamsi='1405/07/08', due_date_shamsi='1405/08/08')
    assert [row['key'] for row in orphan_rows(runtime.db)] == [cheque_id]
    with pytest.raises(RedLineViolation):
        assert_no_orphans(runtime.db)


@pytest.mark.parametrize('case', CASES, ids=[case[0] for case in CASES])
def test_every_kind_of_record_owns_what_it_makes_for_its_whole_life(runtime, case):
    payload = case_payload(runtime, case)
    pid = register(runtime, payload)
    assert_no_orphans(runtime.db)
    m.v18.submit_v18(pid, payload, runtime.rich)
    assert_no_orphans(runtime.db)
    lifecycle = TransactionLifecycle(runtime.db)
    lifecycle.reject(pid)
    assert_no_orphans(runtime.db)
    lifecycle.restore(pid)
    assert_no_orphans(runtime.db)


@pytest.mark.parametrize('status', STATUSES)
def test_a_cheque_keeps_one_row_and_an_owner_through_every_operation(runtime, status):
    from transaction_review import ReviewReturn
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, status, 2)
    assert_no_orphans(runtime.db)

    # an edit of the issue
    m.v18.submit_v18(issue, _edited(runtime, issue, issuer_bank='بانک ویرایش‌شده'), runtime.rich)
    assert_no_orphans(runtime.db)
    assert [row['cheque_id'] for row in _cheque_rows(runtime)] == [cheque_id]

    # back to review and approved again, both records
    ReviewReturn(runtime.db).return_to_review([issue])
    assert_no_orphans(runtime.db)
    m.v18.submit_v18(issue, runtime.db.get_pending_item(issue)['payload'], runtime.rich)
    m._approve_cheque_resolution_187(resolution, runtime.db.get_pending_item(resolution)['payload'])
    assert_no_orphans(runtime.db)
    assert [row['cheque_id'] for row in _cheque_rows(runtime)] == [cheque_id]

    # rejected with its resolution, then restored
    runtime.approval.reject(issue)
    assert_no_orphans(runtime.db)
    TransactionLifecycle(runtime.db).restore(issue)
    assert_no_orphans(runtime.db)
    assert [row['cheque_id'] for row in _cheque_rows(runtime)] == [cheque_id]


def test_a_bundle_cheque_edited_twice_is_still_one_row_with_an_owner(runtime):
    issue, cheque_id = _bundle_issue(runtime)
    for bank in ('بانک یک', 'بانک دو'):
        m.v18.submit_v18(issue, _edited(runtime, issue, issuer_bank=bank), runtime.rich)
        assert_no_orphans(runtime.db)
    assert [row['cheque_id'] for row in _cheque_rows(runtime)] == [cheque_id]
    runtime.approval.reject(issue)
    assert_no_orphans(runtime.db)
    assert runtime.service.list_cheques(open_only=False) == []


def test_in_the_running_app_no_row_creator_works_outside_an_approval(runtime, monkeypatch):
    from finance_db import FinanceDB
    monkeypatch.setattr(FinanceDB, 'enforce_record_context', True)
    creators = [
        lambda db: db.create_cheque(amount=1000, issue_date='2026-09-30', due_date='2026-10-30'),
        lambda db: db.post_transaction(event_date='2026-09-30', direction='IN', amount=1000, category='X'),
        lambda db: db.create_expense(event_date='2026-09-30', final_amount=1000, description='x'),
    ]
    for create in creators:
        with pytest.raises(RedLineViolation):
            create(runtime.db)
    assert orphan_rows(runtime.db) == []
    # an approval makes its rows, and its record owns them
    issue, cheque_id = _issue(runtime)
    assert [row['cheque_id'] for row in _cheque_rows(runtime)] == [cheque_id]
    assert_no_orphans(runtime.db)
    # code that works for one record says so
    with runtime.db.record_context(issue):
        runtime.db.create_expense(event_date='2026-09-30', final_amount=1000, description='x')


def test_the_creators_are_free_when_the_guard_is_off(runtime):
    runtime.db.create_cheque(amount=1000, issue_date='2026-09-30', due_date='2026-10-30')


def test_a_cheque_taken_back_for_review_is_a_leftover_only_until_its_record_posts_it_again(runtime):
    from record_ownership187 import leftover_cheques, remove_leftover_cheques
    from transaction_review import ReviewReturn
    issue, cheque_id = _issue(runtime)
    assert leftover_cheques(runtime.db) == []
    ReviewReturn(runtime.db).return_to_review([issue])
    assert [row['cheque_id'] for row in leftover_cheques(runtime.db)] == [cheque_id]
    assert runtime.service.list_cheques(open_only=False) == []
    assert remove_leftover_cheques(runtime.db, [cheque_id]) == [cheque_id]
    assert _cheque_rows(runtime) == []
    # even with the old row gone the record posts its cheque again, on the id it had
    m.v18.submit_v18(issue, runtime.db.get_pending_item(issue)['payload'], runtime.rich)
    assert [row['cheque_id'] for row in _cheque_rows(runtime)] == [cheque_id]
    assert_no_orphans(runtime.db)


def test_a_rejected_records_cheque_is_kept_for_its_restore(runtime):
    from record_ownership187 import leftover_cheques, remove_leftover_cheques
    issue, cheque_id = _issue(runtime)
    runtime.approval.reject(issue)
    assert leftover_cheques(runtime.db) == []
    with pytest.raises(RedLineViolation):
        remove_leftover_cheques(runtime.db, [cheque_id])
    TransactionLifecycle(runtime.db).restore(issue)
    assert [row['cheque_id'] for row in _cheque_rows(runtime)] == [cheque_id]
    assert_no_orphans(runtime.db)


def test_a_live_cheque_is_never_removed_as_a_leftover(runtime):
    from record_ownership187 import remove_leftover_cheques
    _issue_pid, cheque_id = _issue(runtime)
    with pytest.raises(RedLineViolation):
        remove_leftover_cheques(runtime.db, [cheque_id])
    assert [row['cheque_id'] for row in _cheque_rows(runtime)] == [cheque_id]


def test_an_old_snapshot_left_on_a_resolution_record_does_not_stop_it_being_rejected(runtime):
    import json
    from transaction_lifecycle import is_new_resolution
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'پاس‌شده', 2)
    assert is_new_resolution(runtime.db.get_pending_item(resolution)['payload'])
    # what an older approval of the same record (the clearing flow) left behind: a snapshot of rows that are gone
    stale = [{'table': 'transactions', 'pk': ['transaction_id'], 'key': ['TX-GONE'], 'before': None,
              'after': {'transaction_id': 'TX-GONE', 'status': 'POSTED'}}]
    with runtime.db.atomic() as con:
        con.execute("""INSERT INTO transaction_lifecycle(pending_id,state,effects_json,rejected_json,contract_json,
                       payload_json,message_json,updated_at) VALUES(?,'ACTIVE',?,'[]','[]','{}','{}','2026-10-01T00:00:00')""",
                    (resolution, json.dumps(stale)))
    before_reject = _cheque_state_label(runtime, cheque_id)
    assert before_reject == 'پاس‌شده'

    runtime.approval.reject(resolution)

    assert runtime.db.get_pending_item(resolution)['status'] == 'REJECTED'
    assert _cheque_state_label(runtime, cheque_id) == 'صادرشده'
    assert_no_orphans(runtime.db)


def _cheque_state_label(runtime, cheque_id):
    return m._cheque_status_label_187(runtime.db.get_cheque(cheque_id))


def test_an_old_snapshot_left_on_a_resolution_record_does_not_stop_the_cheque_going_back_to_review(runtime):
    import json
    from transaction_review import ReviewReturn
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'پاس‌شده', 2)
    stale = [{'table': 'transactions', 'pk': ['transaction_id'], 'key': ['TX-GONE'], 'before': None,
              'after': {'transaction_id': 'TX-GONE', 'status': 'POSTED'}}]
    with runtime.db.atomic() as con:
        con.execute("""INSERT INTO transaction_lifecycle(pending_id,state,effects_json,rejected_json,contract_json,
                       payload_json,message_json,updated_at) VALUES(?,'ACTIVE',?,'[]','[]','{}','{}','2026-10-01T00:00:00')""",
                    (resolution, json.dumps(stale)))

    moved = ReviewReturn(runtime.db).return_to_review([issue])

    assert set(moved) == {issue, resolution}
    assert TransactionLifecycle(runtime.db).get(resolution) is None  # the old snapshot went with it
    assert_no_orphans(runtime.db)


# --- the running app tells (opt-in GUI) -----------------------------------------------------------
import os as _os
if _os.environ.get('BARKAV_RUN_UI_TESTS') == '1':
    from test_transaction_lifecycle_ui import window  # noqa: F401
else:
    window = None
gui_only = pytest.mark.skipif(_os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI opt-in')


@gui_only
def test_the_app_tells_at_startup_when_a_row_has_no_record(runtime, window, monkeypatch):
    from finance_db import FinanceDB
    told = []
    monkeypatch.setattr(m.messagebox, 'showwarning', lambda title, text, **k: told.append((title, text)))
    window._red_line_check_187()
    assert told == []  # not in the running app's mode: tests and tools build ledgers directly
    monkeypatch.setattr(FinanceDB, 'enforce_record_context', True)
    window._red_line_check_187()
    assert told == []  # a clean project says nothing
    with runtime.db.record_context('PEN-TEST'):
        runtime.db.create_cheque(amount=1000, issue_date='2026-09-30', due_date='2026-10-30')
    window._red_line_check_187()
    assert len(told) == 1 and told[0][0] == 'خط قرمز ثبت دیتا'
