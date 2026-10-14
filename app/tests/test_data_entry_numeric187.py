"""Digit-by-digit input in real registration forms, using disposable projects."""
import tkinter as tk
from tkinter import ttk
import pytest

from test_transaction_lifecycle_matrix import m, runtime, register, CASES
from test_stage18_7_record_fields import root, record
from test_land_wizard_settlement187 import wizard_for
from test_data_entry_corrections187 import land
from numeric_entry_stage18_7 import format_numeric_entry
from ui_stage18_3 import en
from barkav_ui.clipboard import install, action


@pytest.fixture(autouse=True)
def no_tk_callback_errors(root, monkeypatch):
    errors = []
    monkeypatch.setattr(root, 'report_callback_exception',
                        lambda kind, value, _trace: errors.append((kind.__name__, str(value))))
    yield
    root.update()
    assert not errors


def type_number(root, entry, digits, *, fast=False):
    assert str(entry.cget('state')) == 'normal'
    entry.focus_force()
    root.update()
    entry.selection_range(0, 'end')
    for index, digit in enumerate(digits):
        entry.event_generate('<KeyPress>', keysym='period' if digit == '.' else digit)
        if not fast:
            root.update()
            assert en(entry.get()).replace(',', '') == digits[:index+1]
            assert entry.index('insert') == len(entry.get())
    root.update()
    assert en(entry.get()).replace(',', '') == digits
    assert entry.index('insert') == len(entry.get())


FORM_CASES = [(name, title, sub, extra) for name, title, sub, extra, *_rest in CASES
              if name in {'cash-partial', 'cheque', 'income', 'partner', 'loan',
                          'sale', 'out', 'installment', 'land-fixed', 'land-cash', 'land-cheque', 'land-barter'}]
FORM_CASES += [('daily-report', 'یادداشت', 'گزارش روزانه', {'report_row_count': 1})]


@pytest.mark.parametrize('kind', ['wizard', 'record'])
@pytest.mark.parametrize('name,title,sub,extra', FORM_CASES, ids=[case[0] for case in FORM_CASES])
def test_every_numeric_field_in_transaction_forms(root, runtime, kind, name, title, sub, extra):
    payload = dict(v18_title=title, v18_subtype=sub, detected_type=m.v18._backend_type(title, sub),
                   amount=1000, event_date_shamsi='1405/07/08', description='نمونه عدد',
                   total_debt=2000, payment_state='PARTIAL')
    payload.update(extra)
    if kind == 'wizard':
        form = wizard_for(root, runtime, payload)
    else:
        pid = register(runtime, payload)
        form = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    original = runtime.db.get_pending_item(form.pid)
    numeric = {fd.key: fd.kind for fd in m._special_fields_187(title, sub)
               if fd.kind in {'money', 'int', 'float'}}
    numeric['amount'] = 'money'
    checked = set()
    pages = range(len(form.pages)-1) if kind == 'wizard' else [0]
    for page in pages:
        if kind == 'wizard':
            if page:
                form._capture()
            form.page_index = page
            form._show_page()
        root.update()
        for key, field_kind in numeric.items():
            entry = form.widgets.get(key)
            if (not isinstance(entry, ttk.Entry) or str(entry.cget('state')) != 'normal'
                    or not entry.winfo_viewable()):
                continue
            digits = '12.50' if field_kind == 'float' else '12' if field_kind == 'int' else '123456789'
            type_number(root, entry, digits)
            type_number(root, entry, digits, fast=True)
            if field_kind == 'float':
                captured = form._payload_from_vars(title, form.subtype_var.get())
                assert captured[key] == 12.5
            checked.add(key)
    assert checked, name
    assert runtime.db.get_pending_item(form.pid) == original
    form.destroy()


@pytest.mark.parametrize('kind', ['wizard', 'record'])
@pytest.mark.parametrize('title', ['هزینه ساخت', 'خرید زمین'])
@pytest.mark.parametrize('state', ['PARTIAL', 'PAID', 'UNPAID'])
def test_ai_debt_is_editable_and_manual_correction_survives_navigation(root, runtime, kind, title, state):
    payload = land(v18_subtype='نقدی') if title == 'خرید زمین' else record(runtime)['payload']
    payload.update(payment_state=state, amount=100, total_debt=500,
                   _total_debt_manual187=True,
                   v18_reprocess_suggestions={'amount': 1200, 'total_debt': 9000})
    if kind == 'wizard':
        form = wizard_for(root, runtime, payload)
        debt_page = next(index for index, page in enumerate(form.pages)
                         if any(fd.key == 'total_debt' for fd in page))
        form._capture()
        form.page_index = debt_page
        form._show_page()
    else:
        pid = register(runtime, payload, 2)
        form = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    root.update()
    assert m.parse_int(form.vars['total_debt'].get()) == 9000
    assert not form.payload.get('_total_debt_manual187')
    assert 'total_debt' not in form.manual_fields
    type_number(root, form.widgets['total_debt'], '45678')
    assert form.payload['_total_debt_manual187']
    assert m.parse_int(form.vars['remaining_debt'].get()) == (0 if state == 'PAID' else 45678 if state == 'UNPAID' else 44478)
    if kind == 'wizard':
        form._capture()
        form.page_index = 0
        form._show_page()
        type_number(root, form.widgets['amount'], '2000')
        form._capture()
        form.page_index = debt_page
        form._show_page()
        assert m.parse_int(form.vars['total_debt'].get()) == 45678
    captured = form._payload_from_vars(title, form.subtype_var.get()) if kind == 'wizard' else form.payload_from_form()
    assert captured['total_debt'] == 45678
    form.destroy()
    assert runtime.db.get_pending_item(form.pid)['status'] == 'PENDING_REVIEW'


@pytest.mark.parametrize('state', ['PAID', 'PARTIAL', 'UNPAID'])
def test_debt_can_be_cleared_before_replacement_and_approved_value_is_retained(root, runtime, state):
    payload = record(runtime)['payload']
    payload.update(payment_state=state, total_debt=0, invoice_amount=5000)
    pid = register(runtime, payload, 2)
    editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    root.update()
    entry = editor.widgets['total_debt']
    entry.focus_force()
    entry.selection_range(0, 'end')
    entry.event_generate('<KeyPress>', keysym='BackSpace')
    root.update()
    assert entry.get() == ''
    assert editor.payload['total_debt'] == 0
    type_number(root, entry, '7654')
    assert editor.payload_from_form()['total_debt'] == 7654
    editor._approved_editor_182 = True
    editor._loading = True
    editor.vars['total_debt'].set('7654')
    editor._loading = False
    # Formatter's write must not turn an approved row into a new manual edit.
    editor._approved_editor_182 = True
    root.update()
    assert editor._approved_editor_182
    type_number(root, entry, '7655')
    assert not editor._approved_editor_182


def test_legacy_land_debt_matches_land_and_excludes_construction(runtime):
    old = register(runtime, land('1405/07/08', remaining_debt=8000), 2)
    runtime.db.update_pending(old, status='APPROVED')
    newer = land('1405/07/09', v18_title='هزینه ساخت', v18_subtype='نقدی',
                 transaction_title='هزینه ساخت', remaining_debt=99999)
    other = register(runtime, newer, 3)
    runtime.db.update_pending(other, status='APPROVED')
    current = m.normalize_land_record(land('1405/07/10', amount=1200))
    pid = register(runtime, current)
    carried = m._carry_debt_187(pid, current)
    assert carried['total_debt'] == 8000
    assert carried['_debt_source_pending_id187'] == old


def test_manual_debt_overrides_carried_balance_without_duplicate_cost(root, runtime):
    prior_payload = land('1405/07/09', v18_subtype='نقدی', amount=1200, total_debt=9200)
    prior = register(runtime, prior_payload, 2)
    m.v18.submit_v18(prior, prior_payload, runtime.rich)
    form = wizard_for(root, runtime, land('1405/07/10', v18_subtype='نقدی', amount=1200))
    form._capture()
    form.page_index = next(index for index, page in enumerate(form.pages)
                           if any(fd.key == 'total_debt' for fd in page))
    form._show_page()
    root.update()
    assert m.parse_int(form.vars['total_debt'].get()) == 8000
    type_number(root, form.widgets['total_debt'], '9100')
    form._capture()
    assert form.payload['total_debt'] == 9100
    assert form.payload['remaining_debt'] == 7900
    assert form.payload['_debt_source_pending_id187'] == prior
    assert runtime.db.get_pending_item(prior)['payload']['remaining_debt'] == 8000
    assert runtime.db.get_pending_item(form.pid)['payload']['total_debt'] == 200
    assert runtime.db.land_purchase_cost() == 9200
    m.v18.submit_v18(form.pid, form.payload, runtime.rich)
    saved = runtime.db.get_pending_item(form.pid)['payload']
    assert saved['total_debt'] == 9100 and saved['remaining_debt'] == 7900
    assert saved['land_expense_id187'] == runtime.db.get_pending_item(prior)['payload']['land_expense_id187']
    assert runtime.db.land_purchase_cost() == 9200 and runtime.db.cash_balance() == -2400


def test_append_selection_persian_paste_and_backspace(root, runtime, monkeypatch):
    install(root)
    editor = m.v182.UnifiedPendingEditor182(root, record(runtime), runtime.rich, lambda: None)
    root.update()
    entry = editor.widgets['amount']
    type_number(root, entry, '1234567')
    entry.icursor(1)
    entry.event_generate('<KeyPress>', keysym='8')
    root.update()
    assert m.parse_int(entry.get()) == 12345678
    entry.event_generate('<KeyPress>', keysym='BackSpace')
    root.update()
    assert m.parse_int(entry.get()) == 1234567
    root.clipboard_clear()
    root.clipboard_append('۹٬۸۷۶٬۵۴۳')
    entry.selection_range(0, 'end')
    entry.event_generate('<Control-KeyPress>', keycode=86)
    root.update()
    assert m.parse_int(entry.get()) == 9876543
    assert entry.index('insert') == len(entry.get())
    entry.selection_range(0, 1)
    action(entry, 'copy')
    assert root.clipboard_get() == '۹'
    entry.selection_clear()
    entry.icursor(0)
    root.clipboard_clear()
    root.clipboard_append('٢')
    action(entry, 'paste')
    root.update()
    assert m.parse_int(entry.get()) == 98765432
    entry.selection_range(0, 'end')
    entry.event_generate('<KeyPress>', keysym='BackSpace')
    root.update()
    assert entry.get() == '' and entry.index('insert') == 0
    type_number(root, entry, '4096')
    # Exercise the application's right-click paste command as well.
    monkeypatch.setattr(tk.Menu, 'tk_popup', lambda *args: None)
    entry.selection_range(0, 'end')
    root.clipboard_clear()
    root.clipboard_append('۵۱')
    entry.event_generate('<Button-3>', x=3, y=3)
    root.update()
    popup = next(widget for widget in entry.winfo_children() if isinstance(widget, tk.Menu))
    popup.invoke(2)
    root.update()
    assert m.parse_int(entry.get()) == 51
    assert entry.index('insert') == len(entry.get())


def test_other_editors_keep_mid_number_caret_and_selection(root):
    variable = tk.StringVar(value='12345')
    entry = ttk.Entry(root, textvariable=variable)
    entry.pack()
    format_numeric_entry(entry, variable, m.group_int_fa)
    entry.icursor(2)
    entry.insert('insert', '6')
    root.update()
    assert m.parse_int(entry.get()) == 126345
    assert entry.index('insert') == 3
    entry.selection_range(0, 3)
    variable.set('126345')
    root.update()
    assert entry.selection_present()
    entry.destroy()
    variable.set('1')  # Removed traces and idle jobs must not touch a destroyed field.
