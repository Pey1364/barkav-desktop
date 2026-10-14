"""The record window of a cheque: «اطلاعات چک», «صدور چک» and «تعیین تکلیف چک», one box each (opt-in GUI)."""
import os
from copy import deepcopy
import pytest
from test_cheque_resolution_lifecycle187 import _issue, _resolve
from test_cheque_workflow187 import cheque_payload
from test_transaction_lifecycle_matrix import m, runtime, register

gui_only = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI opt-in')
if os.environ.get('BARKAV_RUN_UI_TESTS') == '1':
    from test_stage18_7_record_fields import root  # noqa: F401
else:
    root = None

BOXES = ['اطلاعات چک', 'صدور چک', 'تعیین تکلیف چک']


def _editor(root, runtime, pid, **changes):
    item = deepcopy(runtime.db.get_pending_item(pid))
    item['payload'].update(changes)
    editor = m.v182.UnifiedPendingEditor182(root, item, runtime.rich, lambda: None)
    root.update()
    return editor


def _titles(editor):
    titles = []
    for card in editor.special_host.winfo_children():
        header = card.winfo_children()[0]
        titles.append(str(header.winfo_children()[0].cget('text')))
    return titles


def _state(editor, key):
    return str(editor.widgets[key].cget('state'))


@gui_only
def test_an_approved_issue_record_shows_the_three_boxes_and_can_change_only_the_issue(root, runtime):
    issue, cheque_id = _issue(runtime)
    _resolve(runtime, cheque_id, 'برگشتی', 2)
    editor = _editor(root, runtime, issue)
    assert _titles(editor) == BOXES
    assert 'cheque_operation187' not in editor.widgets  # the operation is no choice of the window
    for key in ('issuer_name', 'payer_name', 'invoice_amount'):
        assert _state(editor, key) != 'disabled', key
    for key in ('cheque_status', 'cheque_registration_state'):
        assert _state(editor, key) == 'disabled', key
    assert editor.vars['cheque_status'].get() == 'برگشتی'


@gui_only
def test_a_new_issue_record_has_no_resolution_box_and_its_statuses_are_part_of_the_issue(root, runtime):
    pending = register(runtime, cheque_payload(), 9)
    editor = _editor(root, runtime, pending)
    assert _titles(editor) == BOXES[:2]
    assert _state(editor, 'cheque_status') != 'disabled'


@gui_only
def test_a_resolution_record_shows_the_cheque_the_issue_and_changes_only_the_resolution(root, runtime):
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'برگشتی', 2)
    editor = _editor(root, runtime, resolution)
    assert _titles(editor) == BOXES
    assert 'cheque_operation187' not in editor.widgets
    assert editor.widgets['selected_cheque_id187'].selection() == (cheque_id,)
    assert str(editor.widgets['cheque_snapshot_serial187'].cget('state')) in ('readonly', 'disabled')
    assert editor.vars['cheque_resolution_status187'].get() == 'برگشتی'
    assert str(editor.widgets['cheque_resolution_status187'].cget('state')) != 'disabled'


@gui_only
def test_the_record_opened_from_the_cheque_tab_changes_both_parts(root, runtime):
    issue, cheque_id = _issue(runtime)
    _resolve(runtime, cheque_id, 'برگشتی', 2)
    cheque = runtime.db.get_cheque(cheque_id)
    editor = _editor(root, runtime, issue, _cheque_record_id187=cheque_id,
                     cheque_status=m._cheque_status_label_187(cheque), cheque_registration_state=cheque['registration_state'])
    assert _titles(editor) == BOXES
    for key in ('issuer_name', 'payer_name', 'cheque_status', 'cheque_registration_state'):
        assert _state(editor, key) != 'disabled', key


@gui_only
def test_the_return_details_follow_the_status_in_the_resolution_box(root, runtime):
    issue, cheque_id = _issue(runtime)
    cheque = runtime.db.get_cheque(cheque_id)
    editor = _editor(root, runtime, issue, _cheque_record_id187=cheque_id,
                     cheque_status='صادرشده', cheque_registration_state=cheque['registration_state'])
    shown = lambda key: bool(editor.widgets[key].master.winfo_manager())
    assert not shown('cheque_return_account_holder187') and not shown('cheque_void_reason187')
    editor.vars['cheque_status'].set('عودتی به شرط تسویه')
    root.update()
    assert shown('cheque_return_account_holder187') and shown('cheque_return_disposition187')
    assert not shown('cheque_void_reason187')
    editor.vars['cheque_status'].set('باطل‌شده')
    root.update()
    assert shown('cheque_void_reason187') and not shown('cheque_return_account_holder187')


def _session_editor(root, runtime, issue, cheque_id, **changes):
    from cheque_record_edit187 import ChequeRecordSession187, pending_ids
    session = ChequeRecordSession187(runtime.db, cheque_id, pending_ids(runtime.db, cheque_id)[0])
    cheque = runtime.db.get_cheque(cheque_id)
    base = dict(_cheque_record_id187=cheque_id, event_date_shamsi=cheque['issue_date_shamsi'],
                due_date_shamsi=cheque['due_date_shamsi'], amount=cheque['amount'],
                cheque_status=m._cheque_status_label_187(cheque), cheque_registration_state=cheque['registration_state'])
    base.update(changes)
    editor = _editor(root, runtime, issue, **base)
    editor._cheque_record_session187 = session
    session.under_review()
    return editor, session


@gui_only
@pytest.mark.parametrize('answer', ['cancel', 'ignore', 'open'])
def test_a_manual_status_change_lacking_its_details_asks_three_ways(root, runtime, monkeypatch, answer):
    issue, cheque_id = _issue(runtime)
    editor, session = _session_editor(root, runtime, issue, cheque_id)
    editor.vars['cheque_status'].set('عودتی به شرط تسویه')
    asked, opened, errors = [], [], []
    monkeypatch.setattr(m, '_choose_cheque_incomplete_action_187', lambda parent, missing: asked.append(missing) or answer)
    monkeypatch.setattr(m, '_open_resolution_record_187', lambda form, pid: opened.append(pid))
    monkeypatch.setattr(m.messagebox, 'showerror', lambda *a, **k: errors.append(a))
    monkeypatch.setattr(m, '_confirm_debt_warning_187', lambda *a: True)
    editor.after = lambda ms, func=None, *args: func(*args) if func else None

    editor.approve()

    assert asked == [['نام صاحب حساب معرفی‌شده']] and not errors
    changed = m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == 'عودتی به شرط تسویه'
    assert changed == (answer != 'cancel')
    assert bool(opened) == (answer == 'open')
    if answer == 'open':
        assert opened == [session.resolution_pid]
        assert runtime.db.get_pending_item(opened[0])['status'] == 'APPROVED'


@gui_only
@pytest.mark.parametrize('confirm', [True, False])
def test_setting_a_resolved_cheque_back_to_issued_asks_first(root, runtime, monkeypatch, confirm):
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'پاس‌شده', 2)
    editor, session = _session_editor(root, runtime, issue, cheque_id)
    editor.vars['cheque_status'].set('صادرشده')
    asked = []
    monkeypatch.setattr(m.messagebox, 'askyesno', lambda title, text, **k: asked.append(text) or confirm)
    monkeypatch.setattr(m, '_confirm_debt_warning_187', lambda *a: True)

    editor.approve()

    assert len(asked) == 1 and 'رکورد تعیین تکلیف' in asked[0]
    assert runtime.db.get_pending_item(resolution)['status'] == ('REJECTED' if confirm else 'EDIT_PENDING')
    assert (m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == 'صادرشده') == confirm
