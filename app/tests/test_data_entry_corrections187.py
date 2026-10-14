"""October Data Entry acceptance using disposable data and actual Tk fields."""
import json
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

from test_transaction_lifecycle_matrix import m, runtime, register
from test_stage18_7_record_fields import root, record
from data_entry_rules187 import row_order, insert_after, LAND_TITLE, LAND_MIXED
from transaction_lifecycle import TransactionLifecycle


def land(day='1405/07/10', **changes):
    payload = dict(v18_title=LAND_TITLE, v18_subtype=LAND_MIXED,
        detected_type='EXPENSE', event_date_shamsi=day, description='بابت زمین نمونه',
        payment_method='BANK_TRANSFER', payment_state='PARTIAL', total_debt=200,
        land_cash_amount=50, land_cheque_amount=50, land_barter_amount=20,
        land_barter_description='ملک نمونه', due_date_shamsi='1405/08/10',
        amount=120, manager_fee_eligible=False)
    return dict(payload, **changes)


def active_count(db, table):
    with db.read() as con:
        return con.execute('SELECT COUNT(*) FROM '+table+" WHERE status NOT IN ('CANCELLED','VOIDED','DELETED')").fetchone()[0]


def test_stable_order_insert_does_not_rewrite_registration_dates(runtime):
    ids = [register(runtime, land(), index) for index in range(1, 5)]
    before = {pid: runtime.db.get_pending_item(pid)['created_at'] for pid in ids}
    insert_after(runtime.db, ids[2:], ids[0])
    assert row_order(runtime.db) == [ids[0], ids[2], ids[3], ids[1]]
    assert {pid: runtime.db.get_pending_item(pid)['created_at'] for pid in ids} == before
    # Saving/re-reading the setting keeps the same registration order.
    assert json.loads(runtime.db.get_setting('data_entry_row_order187')) == row_order(runtime.db)


def test_partial_carries_nearest_same_purpose_and_excludes_other_and_rejected(runtime):
    for index, (day, purpose, balance, status) in enumerate((
        ('1405/07/07', 'بابت زمین نمونه', 90, 'APPROVED'),
        ('1405/07/08', 'موضوع دیگر', 1000, 'APPROVED'),
        ('1405/07/09', 'بابت زمین نمونه', 80, 'APPROVED'),
        ('1405/07/10', 'بابت زمین نمونه', 700, 'REJECTED')), 1):
        payload = land(day, description=purpose, remaining_debt=balance)
        pid = register(runtime, payload, index)
        runtime.db.update_pending(pid, status=status)
    current = land('1405/07/11', amount=30, total_debt=999)
    pid = register(runtime, current, 5)
    carried = m._carry_debt_187(pid, current)
    assert carried['total_debt'] == 80 and carried['remaining_debt'] == 50


def test_land_mixed_cash_cheque_barter_and_followup_do_not_duplicate_acquisition(runtime):
    first = register(runtime, land(), 1)
    m.v18.submit_v18(first, land(), runtime.rich)
    assert runtime.db.cash_balance() == -50
    assert runtime.db.land_purchase_cost() == 200
    assert active_count(runtime.db, 'expenses') == 1
    assert active_count(runtime.db, 'cheques') == 1
    assert runtime.db.manager_fee_accrued() == 0
    current = land('1405/07/11', land_cash_amount=30, land_cheque_amount=0,
                   land_barter_amount=0, amount=30, total_debt=999)
    second = register(runtime, current, 2)
    m.v18.submit_v18(second, current, runtime.rich)
    saved = runtime.db.get_pending_item(second)['payload']
    assert saved['total_debt'] == 80 and saved['remaining_debt'] == 50
    assert runtime.db.land_purchase_cost() == 200
    assert runtime.db.cash_balance() == -80
    assert active_count(runtime.db, 'expenses') == 1
    TransactionLifecycle(runtime.db).reject(second)
    assert runtime.db.cash_balance() == -50
    TransactionLifecycle(runtime.db).reject(first)
    assert runtime.db.cash_balance() == 0 and runtime.db.land_purchase_cost() == 0


def test_land_failure_rolls_back_every_component(runtime):
    invalid = land(due_date_shamsi='')
    pid = register(runtime, invalid)
    try:
        m.v18.submit_v18(pid, invalid, runtime.rich)
    except ValueError:
        pass
    else:
        raise AssertionError('missing cheque date was accepted')
    assert active_count(runtime.db, 'expenses') == active_count(runtime.db, 'transactions') == 0
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'


def test_posted_cost_to_land_and_back_keeps_one_active_cost(runtime):
    original = dict(v18_title='هزینه ساخت', v18_subtype='نقدی', detected_type='EXPENSE',
        event_date_shamsi='1405/07/10', amount=100, paid_amount=100, final_amount=100,
        invoice_amount=100, payment_state='PAID', payment_method='BANK_TRANSFER',
        description='نمونه ساخت', construction_stage='سفت کاری', manager_fee_eligible=True)
    pid = register(runtime, original)
    m.v18.submit_v18(pid, original, runtime.rich)
    replacement = land(total_debt=100, land_cash_amount=60, land_cheque_amount=20,
                       land_barter_amount=20, amount=100, payment_state='PAID')
    m.v18.submit_v18(pid, replacement, runtime.rich)
    assert runtime.db.cash_balance() == -60
    assert runtime.db.land_purchase_cost() == 100
    assert active_count(runtime.db, 'expenses') == 1
    m.v18.submit_v18(pid, original, runtime.rich)
    assert runtime.db.cash_balance() == -100 and runtime.db.land_purchase_cost() == 0
    assert active_count(runtime.db, 'expenses') == 1
    assert active_count(runtime.db, 'cheques') == 0


def test_wizard_full_form_keeps_draft_but_close_keeps_database_status(root, runtime):
    row = record(runtime)
    m.v18.submit_v18(row['pending_id'], row['payload'], runtime.rich)
    row = runtime.db.get_pending_item(row['pending_id'])
    baseline = runtime.db.get_pending_item(row['pending_id'])
    opened = []
    def full():
        opened.append(m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None))
    wizard = m.v182.TransactionWizard182(root, row, runtime.rich, lambda: None, full)
    wizard.vars['amount'].set('2500')
    wizard._open_full()
    root.update()
    assert len(opened) == 1 and m.parse_int(opened[0].vars['amount'].get()) == 2500
    assert runtime.db.get_pending_item(row['pending_id'])['payload'] == baseline['payload']
    assert runtime.db.get_pending_item(row['pending_id'])['status'] == 'APPROVED'
    opened[0].destroy()
    wizard = m.v182.TransactionWizard182(root, row, runtime.rich, lambda: None, full)
    wizard.vars['amount'].set('8000')
    wizard.tk.call(wizard.protocol('WM_DELETE_WINDOW'))
    assert len(opened) == 1
    assert runtime.db.get_pending_item(row['pending_id'])['status'] == 'APPROVED'
    rejected = record(runtime, mid=2)
    runtime.db.update_pending(rejected['pending_id'], status='REJECTED')
    editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(rejected['pending_id']), runtime.rich, lambda: None)
    editor.vars['amount'].set('4000')
    editor.destroy()
    assert runtime.db.get_pending_item(rejected['pending_id'])['status'] == 'REJECTED'


def test_actual_land_forms_and_clipboard_for_numeric_and_readonly_fields(root, runtime, monkeypatch):
    from barkav_ui.clipboard import install, action
    install(root)
    pid = register(runtime, land())
    row = runtime.db.get_pending_item(pid)
    wizard = m.v182.TransactionWizard182(root, row, runtime.rich, lambda: None, lambda: None)
    assert not wizard.widgets.get('cost_group')
    assert m.v18.TITLE_TYPES[LAND_TITLE][0] == LAND_TITLE
    wizard.next()
    wizard.next()
    for key in ('land_cash_amount', 'land_cheque_amount', 'land_barter_amount'):
        assert key in wizard.widgets and str(wizard.widgets[key].cget('state')) == 'normal'
    wizard.vars['land_cash_amount'].set('70')
    assert m.parse_int(wizard.vars['amount'].get() if 'amount' in wizard.vars else wizard.payload['amount']) == 140
    wizard.destroy()
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    root.update()
    assert not editor.cost_group_row.winfo_viewable()
    for key in ('land_cash_amount', 'land_cheque_amount', 'land_barter_amount'):
        assert editor.widgets[key].winfo_viewable()
    assert 'سایر' in tuple(editor.widgets['payment_method'].cget('values'))
    entry = ttk.Entry(root)
    entry.pack()
    entry.insert(0, '۱۲۳۴')
    readonly_value = tk.StringVar(value='۹۹۰۰')
    readonly = ttk.Entry(root, state='readonly', textvariable=readonly_value)
    readonly.pack()
    root.update()
    assert 'BarkavFieldClipboard' in entry.bindtags()
    action(readonly, 'copy')
    assert root.clipboard_get() == '۹۹۰۰'
    entry.selection_range(0, 'end')
    action(entry, 'paste')
    assert entry.get() == '۹۹۰۰'
    root.clipboard_clear(); root.clipboard_append('۴۲')
    entry.selection_range(0, 'end')
    entry.focus_force()
    root.update()
    entry.event_generate('<Control-KeyPress>', keycode=86)
    root.update()
    assert entry.get() == '۴۲'
    # Exercise the real right-click binding and Tk menu command; Windows native
    # menu display waits for physical input, so stub only its blocking display.
    monkeypatch.setattr(tk.Menu, 'tk_popup', lambda self, *args: None)
    root.clipboard_clear(); root.clipboard_append('۵۱')
    entry.selection_range(0, 'end')
    entry.event_generate('<Button-3>', x=3, y=3)
    root.update()
    popup = next(widget for widget in entry.winfo_children() if isinstance(widget, tk.Menu))
    assert popup.entrycget(2, 'label') == 'چسباندن'
    popup.invoke(2)
    popup.destroy()
    assert entry.get() == '۵۱'


def test_noncash_land_registered_record_keeps_receipt_and_edit_source(runtime, tmp_path):
    payload = land(v18_subtype='معاوضه', land_cash_amount=0, land_cheque_amount=0,
                   land_barter_amount=200, amount=200, payment_state='PAID')
    pid = register(runtime, payload)
    receipt = tmp_path / 'sample-receipt.txt'
    receipt.write_text('disposable receipt', encoding='utf-8')
    runtime.service.attachments.add_local(entity_type='PENDING', entity_id=pid, source_path=receipt)
    m.v18.submit_v18(pid, payload, runtime.rich)
    row = next(row for row in runtime.service.list_registered_records() if row.get('pending_id') == pid)
    assert row['expense_id'] and row['receipt_count'] == 1
    expense = next(expense for expense in runtime.service.list_construction_expenses()
                   if expense['expense_id'] == row['expense_id'])
    assert expense['pending_id'] == pid and expense['receipt_count'] == 1


def test_record_title_switch_defaults_land_to_three_parts_and_methods_exist_for_all_titles(root, runtime):
    editor = m.v182.UnifiedPendingEditor182(root, record(runtime), runtime.rich, lambda: None)
    for title in m.v18.TITLE_TYPES:
        editor.title_var.set(title)
        editor._title_changed()
        root.update()
        if (title == 'یادداشت' or m._is_facility_payload_187(title, editor.subtype_var.get())
                or m._is_installment_payload_187(title, editor.subtype_var.get())):
            # A note is not paid; a loan is paid into the account and an instalment is posted by the loan's
            # schedule: no method.
            assert 'payment_method' not in editor.widgets
        else:
            assert 'payment_method' in editor.widgets
            assert 'سایر' in tuple(editor.widgets['payment_method'].cget('values'))
        if title == LAND_TITLE:
            assert editor.subtype_var.get() == LAND_TITLE
            assert editor.vars['land_payment_mode187'].get() == 'همه موارد'
            assert not editor.cost_group_row.winfo_viewable()


def test_navigation_and_failed_approval_keep_original_status_and_payload(root, runtime, monkeypatch):
    first = record(runtime, mid=1)
    m.v18.submit_v18(first['pending_id'], first['payload'], runtime.rich)
    first = runtime.db.get_pending_item(first['pending_id'])
    second = record(runtime, day='1405/07/09', mid=2)
    runtime.db.update_pending(second['pending_id'], status='REJECTED')
    second = runtime.db.get_pending_item(second['pending_id'])
    editor = m.v182.UnifiedPendingEditor182(root, first, runtime.rich, lambda: None,
                                          navigation_rows=[first, second])
    editor.vars['amount'].set('3300')
    editor._navigate_record_182(1)
    assert runtime.db.get_pending_item(first['pending_id'])['payload'] == first['payload']
    assert runtime.db.get_pending_item(first['pending_id'])['status'] == 'APPROVED'
    editor._navigate_record_182(-1)
    assert m.parse_int(editor.vars['amount'].get()) == 3300
    monkeypatch.setattr(m.messagebox, 'showerror', lambda *args, **kwargs: None)
    def fail(*args, **kwargs):
        raise ValueError('disposable approval failure')
    monkeypatch.setattr(m.v18, 'submit_v18', fail)
    editor.approve()
    editor.destroy()
    assert runtime.db.get_pending_item(first['pending_id'])['status'] == 'APPROVED'
    assert runtime.db.get_pending_item(first['pending_id'])['payload'] == first['payload']
    assert runtime.db.get_pending_item(second['pending_id'])['status'] == 'REJECTED'


def test_actual_data_entry_copy_manual_row_order_and_date_sort(root, runtime, monkeypatch):
    m.style_ttk_187(root)
    monkeypatch.setattr(m.DataEntryCenter187, '_service_status_181', lambda self: None)
    for name in ('_start_telegram_probe_187', '_start_gemini_probe_187'):
        if hasattr(m.DataEntryCenter187, name):
            monkeypatch.setattr(m.DataEntryCenter187, name, lambda self: None)
    a = register(runtime, land('1405/07/11'), 1)
    b = register(runtime, land('1405/07/09'), 2)
    center = m.DataEntryCenter187(root, runtime.rich)
    center.pack(fill='both', expand=True)
    root.update()
    center.filter.set('همه')
    center.refresh()
    center._copied_rows = [runtime.db.get_pending_item(b)]
    copied = center.paste_rows([runtime.db.get_pending_item(a)])[0]
    assert [row['pending_id'] for row in center.rows] == [a, copied, b]
    center._set_data_entry_sort_187('date')
    assert [row['pending_id'] for row in center.rows] == [copied, b, a]
    numbers = [center.table.tree.item(iid, 'values')[0].split()[-1]
               for iid in center.table.tree.get_children()]
    assert numbers == ['۲', '۳', '۱']
    center._set_data_entry_sort_187('row')
    center._select_pending_ids([a])
    monkeypatch.setattr(center, 'open_wizard', lambda row: None)
    added = center.manual_transaction()
    assert [row['pending_id'] for row in center.rows] == [a, added, copied, b]
    menu = center.table.menu
    labels = [menu.entrycget(index, 'label') for index in range(menu.index('end')+1)
              if menu.type(index) == 'cascade']
    assert 'سورتینگ' in labels
