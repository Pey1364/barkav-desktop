"""A rejected record keeps its category when it is opened, saved or closed for editing."""
import pytest

from test_transaction_lifecycle_matrix import runtime, register, case_payload, CASES, m

CASE = {case[0]: case for case in CASES}


def _revisions(runtime, pid):
    with runtime.db.read() as con:
        return con.execute('SELECT COUNT(*) FROM posting_revisions WHERE pending_id=?', (pid,)).fetchone()[0]


def _rejected_with_its_posting_still_active(runtime, message_id):
    """A rejected record whose ledger rows are still live.

    Older databases hold such rows (rejected by hand, or before a rejected edit
    also reversed its posting), so the guard must not depend on the ledger state.
    """
    payload = case_payload(runtime, CASE['cash-paid'])
    pid = register(runtime, dict(payload), message_id)
    runtime.approval._approve_without_lifecycle(pid)
    runtime.db.update_pending(pid, status='REJECTED')
    item = runtime.db.get_pending_item(pid)
    assert item['status'] == 'REJECTED'
    assert runtime.db.get_financial_posting(pid)['status'] == 'ACTIVE'
    return pid, payload


def test_the_edit_windows_cannot_move_a_rejected_record_out_of_the_rejected_list(runtime):
    pid, payload = _rejected_with_its_posting_still_active(runtime, 5000)
    revisions = _revisions(runtime, pid)

    # Save-without-approving, the save-on-navigate prompt and the wizard's close
    # button all stage the edit through begin_posting_revision.
    with pytest.raises(ValueError, match='ردشده'):
        runtime.db.begin_posting_revision(pending_id=pid, new_payload=dict(payload), source='GUI_187_EDIT', actor_id='GUI')

    assert runtime.db.get_pending_item(pid)['status'] == 'REJECTED'
    assert _revisions(runtime, pid) == revisions


def test_pressing_approve_on_a_rejected_record_is_refused_and_changes_nothing(runtime):
    pid, payload = _rejected_with_its_posting_still_active(runtime, 5001)
    revisions = _revisions(runtime, pid)

    with pytest.raises(ValueError):
        m.v18.submit_v18(pid, dict(payload), runtime.rich)

    assert runtime.db.get_pending_item(pid)['status'] == 'REJECTED'
    assert _revisions(runtime, pid) == revisions


def test_editing_an_approved_record_still_stages_a_revision(runtime):
    payload = case_payload(runtime, CASE['cash-paid'])
    pid = register(runtime, dict(payload), 5002)
    runtime.approval._approve_without_lifecycle(pid)
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'

    runtime.db.begin_posting_revision(pending_id=pid, new_payload=dict(payload), source='GUI_187_EDIT', actor_id='GUI')

    assert runtime.db.get_pending_item(pid)['status'] == 'EDIT_PENDING'
    assert _revisions(runtime, pid) == 1
