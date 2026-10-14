"""Real Tk forms and disposable project data for record/wizard corrections."""
import os
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

from test_transaction_lifecycle_matrix import m, register, runtime
from ai_parser import CONSTRUCTION_PHASES

NUMBERED_PHASES = tuple(f'{number:02d} — {name}' for number, name in enumerate(CONSTRUCTION_PHASES, 1))


@pytest.fixture
def root():
    from barkav_ui import art
    art.clear_cache()
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip('no display')
    window.geometry('800x600+20+20')
    window.update()
    yield window
    for job in window.tk.call('after', 'info'):
        window.after_cancel(job)
    try:
        window.destroy()
    except tk.TclError:
        # Legacy tooltips can already have deleted a Python callback during
        # teardown. Still destroy the interpreter's complete window tree.
        window.tk.call('destroy', '.')
    if tk._default_root is window:
        tk._default_root = None


def record(runtime, title='هزینه ساخت', day='1405/07/08', mid=1):
    subtype = {'هزینه ساخت': 'نقدی', 'یادداشت': 'یادداشت', 'ورودی': 'سایر'}[title]
    payload = dict(v18_title=title, v18_subtype=subtype,
                   detected_type=m.v18._backend_type(title, subtype),
                   event_date_shamsi=day, amount=1200, description='نمونه',
                   cost_group='مصالح', payer_name='پرداخت‌کننده', receiver_name='گیرنده')
    pid = register(runtime, payload, mid)
    return runtime.db.get_pending_item(pid)


def test_wizard_first_page_updates_category_and_amount_when_title_changes(root, runtime):
    row = record(runtime)
    wizard = m.v182.TransactionWizard182(root, row, runtime.rich, lambda: None, lambda: None)
    root.update()
    assert wizard.widgets['cost_group'].winfo_viewable()
    wizard.vars['amount'].set('2,400')
    wizard.vars['v18_title'].set('یادداشت')
    wizard._title_changed('یادداشت')
    root.update()
    assert 'cost_group' not in wizard.widgets
    assert tuple(wizard.widgets['construction_stage']['values']) == NUMBERED_PHASES
    assert str(wizard.widgets['amount'].cget('state')) == 'disabled'
    assert m.parse_int(wizard.vars['amount'].get()) == 2400
    # Returning to window one must keep the disabled amount control present.
    wizard.next()
    wizard.prev()
    root.update()
    assert str(wizard.widgets['amount'].cget('state')) == 'disabled'
    wizard.vars['v18_title'].set('هزینه ساخت')
    wizard._title_changed('هزینه ساخت')
    root.update()
    assert wizard.widgets['cost_group'].winfo_viewable()
    assert str(wizard.widgets['amount'].cget('state')) == 'normal'
    # Capturing a note keeps the existing nonfinancial zero-amount rule.
    assert m.parse_int(wizard.vars['amount'].get()) == 0


def test_document_note_hides_payment_method_in_wizard_and_record(root, runtime):
    row = record(runtime, title='یادداشت')
    row['payload'].update(v18_subtype='داکیومنت', document_type='DOCUMENT')

    wizard = m.v182.TransactionWizard182(root, row, runtime.rich, lambda: None, lambda: None)
    root.update()
    assert 'payment_method' not in wizard.widgets
    wizard.next()
    root.update()
    assert wizard.page_index == 1
    assert 'payment_method' not in wizard.widgets
    wizard.destroy()

    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    root.update()
    assert 'payment_method' not in editor.widgets
    editor.destroy()


def test_transaction_combos_move_with_arrows_and_commit_with_enter(root, runtime):
    wizard = m.v182.TransactionWizard182(root, record(runtime), runtime.rich,
                                         lambda: None, lambda: None)
    root.update()
    combo = wizard.widgets['v18_title']
    values = tuple(combo['values'])
    index = combo.current()
    direction = -1 if index == len(values) - 1 else 1
    key = '<Up>' if direction < 0 else '<Down>'
    target = max(0, min(len(values) - 1, index + direction))
    combo.focus_force()
    root.update()
    combo.event_generate(key)
    root.update()
    assert combo.current() == target
    selected = values[target]
    combo.event_generate('<Return>')
    root.update()
    assert wizard.title_var.get() == selected
    assert root.bind_class('TEntry', '<Tab>')
    assert root.bind_class('TCombobox', '<Shift-Tab>')
    wizard.destroy()


def test_record_category_visibility_amount_editability_and_party_alignment(root, runtime):
    editor = m.v182.UnifiedPendingEditor182(root, record(runtime), runtime.rich, lambda: None)
    root.update()
    assert editor.cost_group_row.winfo_viewable()
    assert int(editor.widgets['payer_name'].master.grid_info()['column']) == 3
    assert int(editor.widgets['receiver_name'].master.grid_info()['column']) == 2
    for key in ('payer_name', 'receiver_name'):
        assert editor.widgets[key].cget('justify') == 'right'
    for title in ('یادداشت', 'ورودی', 'خروجی', 'هزینه ساخت'):
        editor.title_var.set(title)
        editor._title_changed()
        root.update()
        assert bool(editor.cost_group_row.winfo_viewable()) == (title == 'هزینه ساخت')
        assert str(editor.widgets['amount'].cget('state')) == ('disabled' if title == 'یادداشت' else 'normal')
        assert bool(editor.widgets['construction_stage'].winfo_viewable()) == (title == 'یادداشت')
    editor.vars['amount'].set('2,500')
    assert 'amount' in editor.manual_fields


def test_record_previous_is_older_and_next_is_newer_even_with_descending_input(root, runtime):
    rows = [record(runtime, day=day, mid=index) for index, day in enumerate(
        ('1405/07/10', '۱۴۰۵/۰۷/۰۸', '1405/07/09'), 1)]
    editor = m.v182.UnifiedPendingEditor182(root, rows[2], runtime.rich, lambda: None,
                                           navigation_rows=rows, navigation_index=2)
    root.update()
    assert editor._navigation_index_182 == 1
    editor._navigate_record_182(-1)
    root.update()
    assert editor.pid == rows[1]['pending_id']
    assert str(editor._previous_button_182.cget('state')) == 'disabled'
    editor._navigate_record_182(1)
    root.update()
    assert editor.pid == rows[2]['pending_id']
    editor._navigate_record_182(1)
    root.update()
    assert editor.pid == rows[0]['pending_id']
    assert str(editor._next_button_182.cget('state')) == 'disabled'


@pytest.mark.skipif(os.name != 'nt', reason='Windows caption')
def test_record_native_caption_keeps_all_controls_after_field_edit_and_reload(root, runtime):
    import ctypes
    rows = [record(runtime, mid=index) for index in (1, 2)]
    editor = m.v182.UnifiedPendingEditor182(root, rows[0], runtime.rich, lambda: None,
                                           navigation_rows=rows)
    root.update()
    editor.vars['amount'].set('2,500')
    editor.focus_force()
    root.update()
    assert editor.transient() == ''
    assert editor.resizable() == (1, 1)

    def check_caption():
        user32 = ctypes.windll.user32
        hwnd = user32.GetAncestor(editor.winfo_id(), 2)
        style = user32.GetWindowLongW(hwnd, -16)
        for bit in (0x00080000, 0x00010000, 0x00020000):
            assert style & bit, hex(style)
        assert not user32.GetWindowLongW(hwnd, -20) & 0x00000080

    check_caption()
    editor._navigation_baseline_182 = editor._navigation_values_182()
    editor._navigate_record_182(1)
    root.update()
    check_caption()


def test_record_date_order_normalizes_shamsi_gregorian_and_missing_dates():
    shamsi = {'payload': {'event_date_shamsi': '۱۴۰۵/۰۷/۰۸'}}
    gregorian = {'message_date': '2026-09-30T10:00:00'}
    assert m._record_date_order_187(shamsi) == m._record_date_order_187(gregorian)
    assert m._record_date_order_187({}) > m._record_date_order_187(shamsi)


@pytest.mark.parametrize('subtype', m.v18.TITLE_TYPES['یادداشت'])
def test_note_phase_survives_approval_edit_and_document_table(runtime, subtype):
    holder = SimpleNamespace(payload={
        'v18_title': 'یادداشت', 'v18_subtype': subtype,
        'event_date_shamsi': '1405/07/08', 'description': 'سند آزمون',
        'construction_stage': 'طراحی', 'amount': 1200,
    }, vars={'construction_stage': SimpleNamespace(get=lambda: 'اسکلت')},
        manual_fields={'construction_stage'})
    payload = m._payload_values_187(holder, 'یادداشت', subtype)
    assert payload['construction_stage'] == 'اسکلت'
    assert payload['amount'] == payload['paid_amount'] == 0
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, payload, runtime.rich)
    document = runtime.rich.list_documents()[0]
    assert runtime.db.get_pending_item(pid)['payload']['construction_stage'] == 'اسکلت'

    table = SimpleNamespace(
        columns=[('row', 'ردیف', 58), ('phase', 'فاز ساخت', 170)],
        _row_uid=lambda row: row['document_id'], row_values=None,
    )
    dashboard = SimpleNamespace(document_table=table)
    dashboard._first_value_187 = m.Stage187Dashboard._first_value_187
    dashboard._transaction_payload_187 = lambda row: m.Stage187Dashboard._transaction_payload_187(dashboard, row)
    dashboard._document_image_indicator_187 = lambda row: '-'
    m.Stage187Dashboard._wrap_financial_row_values_187(dashboard, table)
    assert table.row_values(document)[1] == 'اسکلت'

    # Editing updates the existing document and its pending payload; no new
    # financial effect or duplicate document may be introduced by a phase.
    payload.update(construction_stage='سند و فروش', _document_edit_id_187=document['document_id'])
    m.v18.submit_v18(pid, payload, runtime.rich)
    dashboard._transaction_payload_cache187.clear()
    assert len(runtime.rich.list_documents()) == 1
    assert table.row_values(runtime.rich.list_documents()[0])[1] == 'سند و فروش'
    assert runtime.db.snapshot().cash_balance == 0
    assert runtime.service.list_transactions() == []
    assert runtime.service.list_construction_expenses() == []


def test_note_phase_can_be_cleared_and_old_records_stay_unassigned():
    payload = {'v18_title': 'یادداشت', 'v18_subtype': 'یادداشت',
               'construction_stage': 'اسکلت'}
    holder = SimpleNamespace(payload=payload, vars={
        'construction_stage': SimpleNamespace(get=lambda: '')}, manual_fields=set())
    assert m._payload_values_187(holder, 'یادداشت', 'یادداشت')['construction_stage'] == ''
    holder.payload = {'v18_title': 'یادداشت', 'v18_subtype': 'یادداشت'}
    holder.vars = {}
    assert not m._payload_values_187(holder, 'یادداشت', 'یادداشت').get('construction_stage')


@pytest.mark.parametrize('subtype', m.v18.TITLE_TYPES['یادداشت'])
def test_note_wizard_first_page_and_record_use_all_32_phases(root, runtime, subtype):
    row = record(runtime, title='یادداشت')
    row['payload'].update(v18_subtype=subtype, construction_stage='طراحی')
    wizard = m.v182.TransactionWizard182(root, row, runtime.rich, lambda: None, lambda: None)
    root.update()
    assert tuple(wizard.widgets['construction_stage']['values']) == NUMBERED_PHASES
    assert len(CONSTRUCTION_PHASES) == 32
    assert wizard.vars['construction_stage'].get() == '03 — طراحی'
    wizard.vars['construction_stage'].set('اسکلت')
    wizard.next()
    wizard.prev()
    root.update()
    assert wizard.vars['construction_stage'].get() == '08 — اسکلت'
    assert 'construction_stage' in wizard.manual_fields
    wizard.destroy()

    row['payload'].update(construction_stage='اسکلت')
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    root.update()
    assert tuple(editor.widgets['construction_stage']['values']) == NUMBERED_PHASES
    assert editor.vars['construction_stage'].get() == '08 — اسکلت'
    editor.vars['construction_stage'].set('سند و فروش')
    for next_subtype in m.v18.TITLE_TYPES['یادداشت']:
        editor.subtype_var.set(next_subtype)
        editor._sub_changed()
        root.update()
        assert editor.widgets['construction_stage'].winfo_viewable()
        assert editor.vars['construction_stage'].get() == '32 — سند و فروش'
        assert editor._payload_from_vars('یادداشت', next_subtype)['construction_stage'] == 'سند و فروش'


def _review_wizard(root, runtime, *, title='یادداشت', done=None, full=None):
    root.notebook = ttk.Notebook(root)
    root.notebook.pack(fill='both', expand=True)
    root.approval_tab = ttk.Frame(root.notebook)
    other = ttk.Frame(root.notebook)
    root.notebook.add(root.approval_tab, text='ثبت دیتا')
    root.notebook.add(other, text='تراکنش‌ها')
    root.notebook.select(other)
    parent = ttk.Frame(other)
    parent.pack()
    row = record(runtime, title=title)
    wizard = m.v182.TransactionWizard182(parent, row, runtime.rich,
                                         done or (lambda: None), full or (lambda: None))
    wizard._capture()
    wizard.page_index = len(wizard.pages) - 1
    wizard._show_page()
    root.update()
    return wizard


@pytest.mark.parametrize('title', ['یادداشت', 'ورودی'])
def test_wizard_success_closes_returns_to_data_entry_and_refreshes(root, runtime, title):
    refreshed, full = [], []
    wizard = _review_wizard(root, runtime, title=title,
                           done=lambda: refreshed.append((wizard.winfo_exists(), root.notebook.select())),
                           full=lambda: full.append(True))
    pid = wizard.pid
    wizard.next()
    root.update()
    assert not wizard.winfo_exists()
    assert root.grab_current() is None
    assert root.notebook.select() == str(root.approval_tab)
    assert refreshed == [(0, str(root.approval_tab))]
    assert full == []
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    wizard.next()  # A queued second click must never create a second posting.
    assert len(runtime.rich.list_documents() if title == 'یادداشت'
               else runtime.service.list_transactions()) == 1


def test_wizard_failed_submission_keeps_the_review_open(root, runtime, monkeypatch):
    done, errors = [], []
    wizard = _review_wizard(root, runtime, done=lambda: done.append(True))
    selected = root.notebook.select()
    def fail(*args):
        raise ValueError('خطای آزمایشی ثبت')
    monkeypatch.setattr(m.v18, 'submit_v18', fail)
    monkeypatch.setattr(m.messagebox, 'showerror', lambda *args, **kwargs: errors.append(args))
    wizard.next()
    root.update()
    assert wizard.winfo_exists()
    assert root.notebook.select() == selected
    assert done == [] and len(errors) == 1
    assert runtime.db.get_pending_item(wizard.pid)['status'] == 'PENDING_REVIEW'


def test_wizard_refresh_failure_after_posting_still_closes(root, runtime, monkeypatch):
    warnings = []
    def fail():
        raise ValueError('خطای آزمایشی تازه‌سازی')
    wizard = _review_wizard(root, runtime, done=fail)
    monkeypatch.setattr(m.messagebox, 'showwarning', lambda *args, **kwargs: warnings.append(args))
    wizard.next()
    root.update()
    assert not wizard.winfo_exists()
    assert root.notebook.select() == str(root.approval_tab)
    assert runtime.db.get_pending_item(wizard.pid)['status'] == 'APPROVED'
    assert len(warnings) == 1


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _assert_form_text_is_right_aligned(window):
    for widget in _walk(window):
        if isinstance(widget, tk.Text):
            assert widget.tag_cget('rtl187', 'justify') == 'right'
            assert 'rtl187' in widget.tag_names('end-1c')
        elif isinstance(widget, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Spinbox)):
            assert widget.cget('justify') == 'right'
        elif isinstance(widget, (tk.Label, ttk.Label)):
            assert widget.cget('anchor') == 'e'


def test_daily_report_record_has_large_full_width_rtl_rows_and_keeps_approval_behavior(root, runtime):
    row = record(runtime, title='یادداشت')
    row['payload'].update(v18_subtype='گزارش روزانه', report_row_count=2,
                          daily_report_rows=[{'description': 'گزارش پیشین\nمرحله دوم'}])
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    root.update()
    host = editor.widgets['report_rows']
    assert int(host.master.grid_info()['columnspan']) == 4
    reports = [widget for widget in _walk(host) if isinstance(widget, tk.Text)]
    assert len(reports) == 2
    assert all(int(widget.cget('height')) >= 8 for widget in reports)
    assert reports[0].get('1.0', 'end-1c') == 'گزارش پیشین\nمرحله دوم'
    reports[1].insert('1.0', 'گزارش فارسی\nمرحله ABC-12 و ادامه گزارش')
    root.update()
    editor.vars['report_row_count'].set('3')
    root.update()
    assert len(editor._report_row_vars_187) == 3
    assert editor._report_row_vars_187[1].get() == 'گزارش فارسی\nمرحله ABC-12 و ادامه گزارش'
    _assert_form_text_is_right_aligned(editor)
    editor.approve()
    root.update()
    assert editor.winfo_exists() and editor._approved_editor_182
    saved = runtime.db.get_pending_item(editor.pid)['payload']['daily_report_rows']
    assert saved[1]['description'] == 'گزارش فارسی\nمرحله ABC-12 و ادامه گزارش'


def test_wizard_text_stays_right_aligned_across_pages_and_new_paragraphs(root, runtime):
    wizard = m.v182.TransactionWizard182(root, record(runtime, title='یادداشت'),
                                         runtime.rich, lambda: None, lambda: None)
    root.update()
    _assert_form_text_is_right_aligned(wizard)
    wizard.next()
    root.update()
    description = wizard.widgets['description']
    description.insert('end', '\nگزارش جدید ۱۲۳\nABC و متن فارسی')
    root.update()
    _assert_form_text_is_right_aligned(wizard)
    wizard.next()
    root.update()
    _assert_form_text_is_right_aligned(wizard)


def test_focused_child_does_not_raise_its_visible_owner(root, monkeypatch):
    from barkav_ui.window import keep_above_parent
    child = tk.Toplevel(root)
    root.update()
    owner_raises = []
    monkeypatch.setattr(root, 'lift', lambda: owner_raises.append(True))
    keep_above_parent(child, root)
    child.focus_force()
    child.event_generate('<FocusIn>')
    root.update()
    assert owner_raises == []
    assert root.tk.getboolean(root.tk.call('wm', 'stackorder', child, 'isabove', root))
