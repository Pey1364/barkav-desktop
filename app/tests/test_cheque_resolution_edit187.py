"""A cheque resolution record is opened and corrected the same way by a double-click and by «ویرایش»,
whatever state it is in: approved, being edited («در دست بررسی» after an edit), or sent back to review."""
import os
from types import SimpleNamespace

import pytest

from test_cheque_resolution_lifecycle187 import _issue
from test_cheque_workflow187 import cheque_payload
from test_transaction_lifecycle_matrix import m, runtime, register  # noqa: F401

gui_only = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI opt-in')
if os.environ.get('BARKAV_RUN_UI_TESTS') == '1':
    from test_stage18_7_record_fields import root  # noqa: F401
else:
    root = None

HOLDER = 'صاحب حساب معرفی‌شده'


# ---- which window a double-click opens -------------------------------------------------------------------------

def _row(status, **payload):
    return {'pending_id': 'PEN-X', 'status': status, 'payload': payload}


def _opened(row):
    calls = []
    center = SimpleNamespace(current=None, open_editor=lambda r: calls.append('editor'),
                             open_wizard=lambda r: calls.append('wizard'))
    m.DataEntryCenter187._open_row_187(center, row)
    return calls


@pytest.mark.parametrize('status', ['APPROVED', 'EDIT_PENDING', 'REJECTED'])
def test_a_record_that_has_been_through_review_opens_like_edit(status):
    assert _opened(_row(status, v18_title='هزینه ساخت')) == ['editor']


@pytest.mark.parametrize('status', ['APPROVED', 'EDIT_PENDING', 'PENDING_REVIEW', 'NEEDS_REVIEW', 'REJECTED'])
def test_a_cheque_resolution_opens_like_edit_in_every_state(status):
    row = _row(status, cheque_operation187=m.CHEQUE_OPERATION_RESOLVE_187, selected_cheque_id187='CHQ-1')
    assert _opened(row) == ['editor']


@pytest.mark.parametrize('status', ['PENDING_REVIEW', 'NEEDS_REVIEW'])
def test_a_row_nobody_has_reviewed_yet_still_opens_the_wizard(status):
    assert _opened(_row(status, v18_title='هزینه ساخت')) == ['wizard']


def test_rows_that_are_decisions_or_sales_drafts_keep_their_own_window():
    decision = dict(_row('APPROVED', v18_title='هزینه ساخت'), _lifecycle_decision_only187=True)
    assert _opened(decision) == ['wizard']  # open_wizard shows the decision text
    from sales_claims_stage18_7 import SALES_FINANCE_PENDING_ACTIONS_187, SALES_FINANCE_PENDING_SOURCE_187
    draft = _row('EDIT_PENDING', source=SALES_FINANCE_PENDING_SOURCE_187,
                 sales_pending_action=sorted(SALES_FINANCE_PENDING_ACTIONS_187)[0])
    assert _opened(draft) == ['wizard']


# ---- the record window of a resolution, in each state --------------------------------------------------------------

def _resolution(runtime, cheque_id, status='عودتی به شرط تسویه', message_id=2):
    """A resolution record as the wizard and the record window save it, visible fields included."""
    payload = cheque_payload()
    payload.update(cheque_operation187=m.CHEQUE_OPERATION_RESOLVE_187, selected_cheque_id187=cheque_id,
                   cheque_resolution_status187=status, cheque_resolution_registration187='ثبت‌شده',
                   cheque_resolution_return_disposition187=m.CHEQUE_RETURN_DISPOSITION_CHOICES_187[3],
                   cheque_resolution_account_holder187=HOLDER,
                   cheque_return_disposition187=m.CHEQUE_RETURN_DISPOSITION_CHOICES_187[3],
                   cheque_return_account_holder187=HOLDER, cheque_void_reason187='دلیل ابطال')
    pid = register(runtime, payload, message_id)
    m._approve_cheque_resolution_187(pid, payload)
    return pid


def _put_in(runtime, pid, state):
    if state == 'edit_pending':
        runtime.db.update_pending(pid, status='EDIT_PENDING')
    elif state == 'returned':
        from transaction_review import ReviewReturn
        ReviewReturn(runtime.db).return_to_review([pid])


@pytest.fixture
def dashboard(runtime, monkeypatch):
    from barkav_ui import art
    art.clear_cache()
    monkeypatch.setattr(m.v186.v185, 'fetch_tgju_usd_toman', lambda timeout=6: (70000, '2026-10-05'))
    monkeypatch.setattr(m.DataEntryCenter187, '_start_gemini_probe_187', lambda self: None)
    monkeypatch.setattr(m.DataEntryCenter187, '_start_telegram_probe_187', lambda self: None)
    monkeypatch.setattr(m.Stage187Dashboard, '_show_startup_reminders_187', lambda self: None)
    app = m.Stage187Dashboard()
    app.update()
    yield app
    app.destroy()


def _windows(app):
    found, stack = [], list(app.winfo_children())
    while stack:
        widget = stack.pop()
        if widget.winfo_class() == 'Toplevel':
            found.append(widget)
        stack.extend(widget.winfo_children())
    return found


def _open(dashboard, row, how):
    before = set(_windows(dashboard))
    if how == 'double-click':
        table = dashboard.approval_center.table
        iid = next(key for key, value in table.iid_to_row.items() if value['pending_id'] == row['pending_id'])
        table.tree.identify_row = lambda _y: iid  # the row under the pointer
        table._double(SimpleNamespace(x=5, y=5))
    else:
        dashboard.approval_center.open_editor(row)
    dashboard.update()
    return next(window for window in _windows(dashboard) if window not in before)


@gui_only
@pytest.mark.parametrize('state', ['approved', 'edit_pending', 'returned'])
@pytest.mark.parametrize('how', ['double-click', 'edit'])
def test_the_record_can_be_corrected_in_every_state(dashboard, runtime, monkeypatch, state, how):
    errors = []
    for name in ('showerror', 'showwarning'):
        monkeypatch.setattr(m.messagebox, name, lambda *a, **k: errors.append(a))
    monkeypatch.setattr(m, '_confirm_debt_warning_187', lambda *a: True)
    issue, cheque_id = _issue(runtime)
    resolution = _resolution(runtime, cheque_id)
    _put_in(runtime, resolution, state)
    center = dashboard.approval_center
    center.refresh()
    dashboard.update()
    row = next(item for item in center.rows if item['pending_id'] == resolution)

    window = _open(dashboard, row, how)

    assert isinstance(window, m.v182.UnifiedPendingEditor182)          # the record window, like «ویرایش»
    picker = window.widgets['selected_cheque_id187']
    assert picker.selection() == (cheque_id,)                          # its cheque is listed and chosen
    assert window.vars['cheque_resolution_account_holder187'].get() == HOLDER   # and its answers are still there
    window.vars['cheque_resolution_account_holder187'].set('صاحب حساب اصلاح‌شده')
    m._editor_approve_187(window)
    dashboard.update()

    assert not errors
    assert runtime.db.get_pending_item(resolution)['status'] == 'APPROVED'
    cheque = runtime.db.get_cheque(cheque_id)
    assert (cheque['status'], cheque['settlement_mode']) == ('RETURNED', 'RETURNED_ON_SETTLEMENT')
    assert cheque['return_account_holder'] == 'صاحب حساب اصلاح‌شده'
    assert len(runtime.db.list_cheques(open_only=False)) == 1


@gui_only
def test_a_double_click_on_a_fresh_pending_row_opens_the_wizard(dashboard, runtime):
    payload = cheque_payload()
    pid = register(runtime, payload, 5)
    center = dashboard.approval_center
    center.refresh()
    dashboard.update()
    row = next(item for item in center.rows if item['pending_id'] == pid)
    window = _open(dashboard, row, 'double-click')
    assert isinstance(window, m.v182.TransactionWizard182)
    window.destroy()


@gui_only
def test_the_wizard_lists_the_cheque_of_an_approved_resolution_too(root, runtime, monkeypatch):
    errors = []
    for name in ('showerror', 'showwarning'):
        monkeypatch.setattr(m.messagebox, name, lambda *a, **k: errors.append(a))
    monkeypatch.setattr(m, '_confirm_debt_warning_187', lambda *a: True)
    issue, cheque_id = _issue(runtime)
    resolution = _resolution(runtime, cheque_id)
    window = m.v182.TransactionWizard182(root, runtime.db.get_pending_item(resolution), runtime.rich,
                                         lambda: None, lambda: None)
    root.update()
    picker = window.widgets['selected_cheque_id187']
    assert cheque_id in picker.get_children() and picker.selection() == (cheque_id,)
    for _ in range(8):
        window.next()
        root.update()
        if errors or getattr(window, '_approved_in_wizard_187', False):
            break
    assert not errors and runtime.db.get_pending_item(resolution)['status'] == 'APPROVED'
    assert runtime.db.get_cheque(cheque_id)['settlement_mode'] == 'RETURNED_ON_SETTLEMENT'
