"""Latest wizard acceptance on real Tk controls and disposable project data."""
import tkinter as tk
from tkinter import ttk
import pytest

from test_transaction_lifecycle_matrix import m, runtime, register
from test_stage18_7_record_fields import root, record
from test_data_entry_corrections187 import land, active_count
from data_entry_rules187 import LAND_TITLE, LAND_PARTS, LAND_MIXED
from land_purchase187 import debt_signature


def wizard_for(root, runtime, payload):
    pid = register(runtime, payload)
    row = runtime.db.get_pending_item(pid)
    return m.v182.TransactionWizard182(root, row, runtime.rich, lambda: None, lambda: None)


def test_information_hides_method_and_phase_uses_its_project_number(root, runtime, monkeypatch):
    row = record(runtime, title='یادداشت')
    row['payload'].update(v18_subtype='اطلاع‌رسانی', construction_stage='اسکلت')
    monkeypatch.setattr(runtime.rich, 'list_phase_summary', lambda: [dict(phase_no=17, phase='اسکلت')])
    wizard = m.v182.TransactionWizard182(root, row, runtime.rich, lambda: None, lambda: None)
    assert '17 — اسکلت' in wizard.widgets['construction_stage']['values']
    assert wizard.vars['construction_stage'].get() == '17 — اسکلت'
    wizard.next()
    assert 'payment_method' not in wizard.vars
    assert not any(fd.key == 'payment_method' for page in wizard.pages for fd in page)
    assert wizard.payload['construction_stage'] == 'اسکلت'
    wizard.destroy()
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    assert 'payment_method' not in editor.vars
    assert 'payment_method' not in editor.widgets
    assert editor.vars['construction_stage'].get() == '17 — اسکلت'
    assert editor.payload_from_form()['construction_stage'] == 'اسکلت'


@pytest.mark.parametrize('state', ['PARTIAL', 'PAID'])
def test_cash_wizard_amount_debt_navigation_and_no_cheque(root, runtime, state):
    wizard = wizard_for(root, runtime, land(v18_subtype='نقدی', amount=1200,
        total_debt=0 if state == 'PAID' else 4000, payment_state=state, land_cash_amount=50))
    assert str(wizard.widgets['amount'].cget('state')) == 'normal'
    assert m.parse_int(wizard.vars['amount'].get()) == 1200
    wizard.vars['amount'].set('۲,۴۰۰')
    assert wizard.payload['total_debt'] == (2400 if state == 'PAID' else 4000)
    wizard.next()
    assert wizard.payload['total_debt'] == (2400 if state == 'PAID' else 4000)
    wizard.next()
    assert wizard.payload['total_debt'] == (2400 if state == 'PAID' else 4000)
    assert m.parse_int(wizard.vars['land_cash_amount'].get()) == 2400
    assert str(wizard.widgets['land_barter_description'].cget('state')) == 'disabled'
    assert str(wizard.widgets['land_cash_amount'].cget('state')) == 'disabled'
    assert wizard.payload['amount'] == 2400
    assert not any(fd.key == 'cheque_serial' for page in wizard.pages for fd in page)
    wizard.next()
    assert 'total_debt' in wizard.vars and 'cheque_serial' not in wizard.vars
    expected = 2400 if state == 'PAID' else 4000
    assert m.parse_int(wizard.vars['total_debt'].get()) == expected
    assert str(wizard.widgets['total_debt'].cget('state')) == 'normal'
    wizard.prev()
    wizard.prev()
    wizard.prev()
    assert m.parse_int(wizard.vars['amount'].get()) == 2400
    wizard.vars['amount'].set('3000')
    wizard.next()
    wizard.next()
    assert m.parse_int(wizard.vars['land_cash_amount'].get()) == 3000
    wizard.next()
    wizard.next()
    wizard.next()  # Actual approval, with no cheque details or debt error.
    row = runtime.db.get_pending_item(wizard.pid)
    assert row['status'] == 'APPROVED'
    assert row['payload']['land_cash_amount'] == row['payload']['amount'] == 3000
    assert row['payload']['land_cheque_amount'] == row['payload']['land_barter_amount'] == 0
    assert active_count(runtime.db, 'cheques') == 0
    assert runtime.db.cash_balance() == -3000
    assert runtime.db.land_purchase_cost() == (3000 if state == 'PAID' else 4000)


@pytest.mark.parametrize('title', [LAND_TITLE, 'هزینه ساخت'])
def test_settlement_debt_and_partial_debt_remain_editable(root, runtime, title):
    payload = land(v18_subtype='نقدی', amount=1700, payment_state='PAID') if title == LAND_TITLE else record(runtime)['payload']
    payload.update(payment_state='PAID', total_debt=99)
    pid = register(runtime, payload, 2)
    editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    assert str(editor.widgets['total_debt'].cget('state')) == 'normal'
    assert m.parse_int(editor.vars['total_debt'].get()) == 99
    editor.vars['amount'].set('2,500')
    assert m.parse_int(editor.vars['total_debt'].get()) == 99
    if title == LAND_TITLE:
        assert m.parse_int(editor.vars['land_cash_amount'].get()) == 2500
        assert str(editor.widgets['land_barter_description'].cget('state')) == 'disabled'
        assert not editor.widgets['cheque_serial'].master.winfo_manager()
    editor.vars['payment_state'].set('علی‌الحساب')
    assert str(editor.widgets['total_debt'].cget('state')) == 'normal'
    editor.vars['total_debt'].set('3000')
    assert m.parse_int(editor.vars['remaining_debt'].get()) == 500


@pytest.mark.parametrize('subtype', ['نقدی', LAND_MIXED])
def test_ai_extracted_amount_is_in_fields_not_only_label(root, runtime, subtype):
    payload = land(v18_subtype=subtype, amount=8600, total_debt=10000)
    for key in LAND_PARTS:
        payload.pop(key)
    wizard = wizard_for(root, runtime, payload)
    assert m.parse_int(wizard.vars['amount'].get()) == 8600
    wizard.next()
    wizard.next()
    assert m.parse_int(wizard.vars['land_cash_amount'].get()) == 8600
    assert wizard.payload['amount'] == 8600
    wizard.destroy()
    pid = register(runtime, payload, 2)
    editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    assert m.parse_int(editor.vars['amount'].get()) == 8600
    assert m.parse_int(editor.vars['land_cash_amount'].get()) == 8600


@pytest.mark.parametrize('ignore', [False, True])
@pytest.mark.parametrize('state,debt', [('PARTIAL', 10), ('PAID', 10), ('PAID', 100)])
def test_debt_warning_explicit_choices_and_atomic_approval(root, runtime, monkeypatch, ignore, state, debt):
    from barkav_ui.messages import MessageDialog
    original_wait = tk.Misc.wait_window
    seen = []
    def answer(dialog, *args):
        buttons = [child for child in dialog.footer.winfo_children() if isinstance(child, ttk.Button)]
        seen.extend(button.cget('text') for button in buttons)
        dialog.after(1, buttons[int(ignore)].invoke)
        return original_wait(dialog, *args)
    monkeypatch.setattr(MessageDialog, 'wait_window', answer)
    payload = land(v18_subtype='نقدی', land_cash_amount=50,
                   land_cheque_amount=0, land_barter_amount=0, amount=50, total_debt=debt, payment_state=state)
    pid = register(runtime, payload)
    editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    editor.approve()
    assert seen == ['اصلاح تراکنش', 'نادیده گرفتن و ثبت تراکنش']
    row = runtime.db.get_pending_item(pid)
    if ignore:
        assert row['status'] == 'APPROVED'
        assert runtime.db.cash_balance() == -50 and runtime.db.land_purchase_cost() == debt
        assert row['payload']['land_debt_override187'] == debt_signature(payload, m.parse_int)
    else:
        assert row['status'] == 'PENDING_REVIEW'
        assert editor.winfo_exists() and not editor._approved_editor_182
        assert runtime.db.cash_balance() == runtime.db.land_purchase_cost() == 0


def test_warning_override_does_not_authorize_changed_amounts(runtime):
    payload = land(total_debt=10)
    payload['land_debt_override187'] = debt_signature(payload, m.parse_int)
    payload['land_cash_amount'] += 1
    pid = register(runtime, payload)
    with pytest.raises(ValueError):
        m.v18.submit_v18(pid, payload, runtime.rich)
    assert runtime.db.cash_balance() == runtime.db.land_purchase_cost() == 0


def test_wizard_warning_correction_returns_to_editable_payment(root, runtime, monkeypatch):
    from barkav_ui.messages import MessageDialog
    original_wait = tk.Misc.wait_window
    def correct(dialog):
        button = next(child for child in dialog.footer.winfo_children() if isinstance(child, ttk.Button))
        dialog.after(1, button.invoke)
        return original_wait(dialog)
    monkeypatch.setattr(MessageDialog, 'wait_window', correct)
    wizard = wizard_for(root, runtime, land(payment_state='PAID', total_debt=100))
    wizard.page_index = len(wizard.pages)-1
    wizard._show_page()
    wizard.next()
    assert 'land_cash_amount' in wizard.vars
    assert str(wizard.widgets['land_cash_amount'].cget('state')) == 'normal'
    assert runtime.db.get_pending_item(wizard.pid)['status'] == 'PENDING_REVIEW'


def test_ai_numeric_suggestions_populate_draft_and_stay_editable(root, runtime):
    payload = land(v18_subtype='نقدی', amount=100, total_debt=500,
        v18_manual_fields=['amount', 'total_debt', 'description'],
        v18_reprocess_suggestions={'amount': 8600, 'total_debt': 10000, 'description': 'متن پیشنهادی'})
    wizard = wizard_for(root, runtime, payload)
    assert m.parse_int(wizard.vars['amount'].get()) == 8600
    wizard.vars['amount'].set('9000')
    wizard.next()
    wizard.next()
    wizard.next()
    assert m.parse_int(wizard.vars['total_debt'].get()) == 10000
    wizard.prev()
    wizard.prev()
    wizard.prev()
    assert m.parse_int(wizard.vars['amount'].get()) == 9000
    # No write to a pending/approved financial row until explicit approval.
    assert runtime.db.get_pending_item(wizard.pid)['payload']['amount'] == 100
    wizard.destroy()
    pid = register(runtime, payload, 2)
    editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    assert m.parse_int(editor.vars['amount'].get()) == 8600
    assert m.parse_int(editor.vars['total_debt'].get()) == 10000
    editor.vars['amount'].set('9200')
    assert editor.payload_from_form()['amount'] == 9200
    assert editor.payload['v18_reprocess_suggestions'] == {'description': 'متن پیشنهادی'}


def test_ai_cash_component_suggestion_updates_transaction_amount(root, runtime):
    payload = land(v18_subtype='نقدی', amount=100,
                   v18_reprocess_suggestions={'land_cash_amount': 16000})
    wizard = wizard_for(root, runtime, payload)
    assert m.parse_int(wizard.vars['amount'].get()) == 16000
    wizard.next()
    wizard.next()
    assert m.parse_int(wizard.vars['land_cash_amount'].get()) == 16000


def test_calendar_first_visible_geometry_is_final_center(root, runtime, monkeypatch):
    from sales_claims_stage18_7 import ShamsiDatePicker187
    from barkav_ui.window import work_area
    observed = []
    original = tk.Toplevel.deiconify
    def show(window):
        if isinstance(window, ShamsiDatePicker187):
            observed.append((window.geometry(), len(window.grid_host.winfo_children())))
        return original(window)
    monkeypatch.setattr(tk.Toplevel, 'deiconify', show)
    wizard = wizard_for(root, runtime, land(v18_subtype='نقدی'))
    picker = wizard.widgets['event_date_shamsi'].open_calendar()
    assert observed and observed[0][1] >= 35  # Dates built before first visibility.
    first_geometry = observed[0][0]
    root.update()
    assert picker.geometry() == first_geometry
    width, height = work_area(picker)
    # BarkavWindow includes the native frame reserve in its centering formula.
    assert abs(picker.winfo_x() - (width-470)//2) < 15
    assert abs(picker.winfo_y() - (height-430)//2) < 35
    picker._select(12)
    assert '۱۲' in wizard.vars['event_date_shamsi'].get()
