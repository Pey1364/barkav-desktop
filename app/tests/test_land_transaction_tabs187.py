"""Land tabs and fixed title/phase contract, on disposable data and real Tk."""
import tkinter as tk
from pathlib import Path
import pytest

from test_transaction_lifecycle_matrix import m, runtime, register
from test_stage18_7_record_fields import root, record
from test_data_entry_corrections187 import land, active_count
from test_land_wizard_settlement187 import wizard_for
from data_entry_rules187 import (LAND_TITLE, LAND_MODE_KEY, LAND_MODES, LAND_PARTS,
                                normalize_land_parts, land_payment_mode)
from transaction_titles187 import transaction_title, TRANSACTION_TITLES


class _Choice:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_financial_date_choices_sort_rows_without_filtering():
    from types import SimpleNamespace

    app = m.Stage187Dashboard.__new__(m.Stage187Dashboard)
    # This pure sorting test does not initialize a Tk interpreter. A missing
    # tk attribute otherwise makes Tk.__getattr__ recurse on Python 3.13.
    app.tk = SimpleNamespace()
    rows = [
        {'loan_id': 'older', 'received_date_shamsi': '۱۴۰۴/۱۲/۲۹'},
        {'loan_id': 'newer', 'received_date_shamsi': '۱۴۰۵/۰۱/۰۲'},
        {'loan_id': 'middle', 'received_date_shamsi': '۱۴۰۵/۰۱/۰۱'},
    ]
    table = SimpleNamespace(
        _barkav_source_rows187=rows,
        all_rows=rows,
        row_values=lambda row: [row['loan_id']],
        _barkav_filter_field_var187=_Choice('تاریخ'),
        _barkav_filter_value_var187=_Choice('جدیدترین'),
    )
    table.set_rows = lambda new_rows, renderer: setattr(table, 'all_rows', list(new_rows))
    app.loan_table = table
    for name in ('all_tx_table', 'land_table', 'exp_table', 'in_table', 'out_table',
                 'cheque_table', 'document_table'):
        setattr(app, name, None)

    choices = app._transaction_filter_values_187(table, 'تاریخ')
    assert choices[:3] == ('همه', 'جدیدترین', 'قدیمی‌ترین')
    app._apply_transaction_view_filter_187(table)
    assert [row['loan_id'] for row in table.all_rows] == ['newer', 'middle', 'older']

    table._barkav_filter_value_var187.set('قدیمی‌ترین')
    app._apply_transaction_view_filter_187(table)
    assert [row['loan_id'] for row in table.all_rows] == ['older', 'middle', 'newer']


def test_construction_cost_metadata_columns_render_from_expense_fields():
    from types import SimpleNamespace

    app = m.Stage187Dashboard.__new__(m.Stage187Dashboard)
    columns = (
        ('row', 'ردیف', 58),
        ('_cost_group187', 'دسته‌بندی', 95),
        ('_plan_ref187', 'فاز ساخت', 170),
    )
    table = SimpleNamespace(
        columns=columns,
        _row_uid=lambda row: row.get('expense_id', ''),
        _barkav_checked_uids187=set(),
        row_values=lambda _row: [],
    )
    app.exp_table = table
    m.Stage187Dashboard._wrap_financial_row_values_187(app, table)

    rendered = table.row_values({
        'expense_id': 'EXP-RENDER-PROBE', 'cost_group': 'مصالح',
        'construction_stage': 'اسکلت', 'phase_name': 'اسکلت',
        'final_amount': 0, 'paid_amount': 0, 'status': 'POSTED',
    })
    values = dict(zip((key for key, _label, _width in columns), rendered))
    assert values['_cost_group187'] == 'مصالح'
    assert values['_plan_ref187'] == 'اسکلت'


@pytest.mark.parametrize('legacy,mode', [('نقدی', 'نقدی'), ('چک', 'چکی'),
    ('معاوضه', 'معاوضه'), ('نقدی، چک، معاوضه', 'همه موارد'), (LAND_TITLE, 'همه موارد')])
def test_legacy_mode_preserved_and_land_identity_fixed(root, runtime, legacy, mode):
    wizard = wizard_for(root, runtime, land(v18_subtype=legacy))
    assert wizard.subtype_var.get() == LAND_TITLE
    assert str(wizard.widgets['v18_subtype'].cget('state')) == 'disabled'
    assert wizard.vars[LAND_MODE_KEY].get() == mode
    assert tuple(wizard.widgets[LAND_MODE_KEY].cget('values')) == LAND_MODES
    assert wizard.vars['construction_stage'].get() == LAND_TITLE
    assert str(wizard.widgets['construction_stage'].cget('state')) == 'disabled'
    wizard._capture()
    assert wizard.payload['v18_subtype'] == wizard.payload['main_phase'] == LAND_TITLE
    wizard.destroy()
    row = runtime.db.get_pending_item(wizard.pid)
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    assert editor.subtype_var.get() == LAND_TITLE
    assert str(editor.widgets['v18_subtype'].cget('state')) == 'disabled'
    assert editor.vars[LAND_MODE_KEY].get() == mode
    assert editor.vars['construction_stage'].get() == LAND_TITLE
    assert str(editor.widgets['construction_stage'].cget('state')) == 'disabled'
    payload = editor.payload_from_form()
    assert payload['v18_subtype'] == payload['construction_stage'] == LAND_TITLE
    assert land_payment_mode(payload) == mode


@pytest.mark.parametrize('mode,active', [('نقدی', [0]), ('چکی', [1]),
    ('معاوضه', [2]), ('همه موارد', [0, 1, 2])])
def test_mode_switch_rebuilds_wizard_pages_and_record_parts(root, runtime, mode, active):
    wizard = wizard_for(root, runtime, land())
    wizard.vars[LAND_MODE_KEY].set(mode)
    assert str(wizard.widgets['amount'].cget('state')) == ('normal' if mode == 'نقدی' else 'disabled')
    wizard.next()
    assert any(fd.key == 'cheque_serial' for page in wizard.pages for fd in page) == (1 in active)
    wizard.next()
    for index, key in enumerate(LAND_PARTS):
        editable = index in active and mode != 'نقدی'
        assert str(wizard.widgets[key].cget('state')) == ('normal' if editable else 'disabled')
    wizard.prev(); wizard.prev()
    assert wizard.vars[LAND_MODE_KEY].get() == mode
    wizard.destroy()
    editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(wizard.pid), runtime.rich, lambda: None)
    editor.vars[LAND_MODE_KEY].set(mode)
    for index, key in enumerate(LAND_PARTS):
        editable = index in active and mode != 'نقدی'
        assert str(editor.widgets[key].cget('state')) == ('normal' if editable else 'disabled')
    assert bool(editor.widgets['cheque_serial'].master.winfo_manager()) == (1 in active)
    result = editor.payload_from_form()
    assert result['v18_subtype'] == LAND_TITLE
    assert result[LAND_MODE_KEY] == mode
    assert all(result[key] == 0 for index, key in enumerate(LAND_PARTS) if index not in active)


@pytest.mark.parametrize('title', TRANSACTION_TITLES)
def test_phase_question_matches_title_after_back_navigation(root, runtime, title):
    payload = land() if title == LAND_TITLE else dict(v18_title=title,
        v18_subtype='یادداشت' if title == 'یادداشت' else 'نقدی' if title == 'هزینه ساخت' else 'سایر',
        detected_type=m.v18._backend_type(title, 'سایر'), amount=100,
        event_date_shamsi='1405/07/10', description='تست فاز', cost_group='مصالح')
    wizard = wizard_for(root, runtime, payload)
    wizard.next()
    keys = {fd.key for page in wizard.pages for fd in page}
    assert bool(keys & {'construction_stage', 'main_phase'}) == (title not in {'ورودی', 'خروجی'})
    wizard.prev(); wizard.next()
    keys = {fd.key for page in wizard.pages for fd in page}
    assert bool(keys & {'construction_stage', 'main_phase'}) == (title not in {'ورودی', 'خروجی'})


@pytest.mark.parametrize('mode', LAND_MODES)
def test_backend_stores_fixed_identity_and_only_active_payments(runtime, mode):
    payload = land(**{LAND_MODE_KEY: mode})
    expected = normalize_land_parts(payload, m.parse_int)
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, payload, runtime.rich)
    saved = runtime.db.get_pending_item(pid)['payload']
    assert saved['v18_subtype'] == saved['transaction_subtype'] == saved['construction_stage'] == LAND_TITLE
    assert saved[LAND_MODE_KEY] == mode
    assert [saved[key] for key in LAND_PARTS] == [expected[key] for key in LAND_PARTS]
    assert active_count(runtime.db, 'cheques') == int(expected['land_cheque_amount'] > 0)
    assert runtime.db.cash_balance() == -expected['land_cash_amount']
    assert runtime.db.manager_fee_accrued() == 0


def test_legacy_row_titles():
    assert transaction_title({'expense_id': 'e', 'phase_name': LAND_TITLE}, {'v18_title': 'هزینه ساخت'}) == LAND_TITLE
    assert transaction_title({}, {'v18_title': 'ورودی', 'construction_stage': LAND_TITLE}) == 'ورودی'
    assert transaction_title({'loan_id': 'l', 'category': 'LOAN_INSTALLMENT'}) == 'خروجی'
    assert transaction_title({'loan_id': 'l', 'category': 'LOAN_INSTALLMENT_PAYMENT'}, {'v18_title': 'ورودی'}) == 'خروجی'
    assert transaction_title({'cheque_id': 'c'}) == 'هزینه ساخت'
    assert transaction_title({'document_id': 'd'}) == 'یادداشت'


def test_actual_dashboard_land_tab_filters_and_common_actions(runtime, monkeypatch):
    from barkav_ui import art
    art.clear_cache()
    monkeypatch.setattr(m.v186.v185, 'fetch_tgju_usd_toman', lambda timeout=6: (70000, '2026-10-03'))
    monkeypatch.setattr(m.DataEntryCenter187, '_start_gemini_probe_187', lambda self: None)
    monkeypatch.setattr(m.DataEntryCenter187, '_start_telegram_probe_187', lambda self: None)
    monkeypatch.setattr(m.Stage187Dashboard, '_show_startup_reminders_187', lambda self: None)
    pid = register(runtime, land())
    receipt = Path(runtime.db.db_path).parent / 'sample-land-receipt.txt'
    receipt.write_text('disposable land receipt', encoding='utf-8')
    runtime.service.attachments.add_local(entity_type='PENDING', entity_id=pid, source_path=receipt)
    m.v18.submit_v18(pid, land(), runtime.rich)
    income = dict(v18_title='ورودی', v18_subtype='سایر', detected_type='INCOME',
                  amount=300, event_date_shamsi='1405/07/10', description='درآمد تست')
    income_id = register(runtime, income, 2)
    m.v18.submit_v18(income_id, income, runtime.rich)
    before = runtime.db.snapshot()
    app = m.Stage187Dashboard()
    try:
        app.update_idletasks(); app.update()
        app.refresh_financial()
        names = [app.fin_nb.tab(tab, 'text') for tab in app.fin_nb.tabs()]
        assert names[names.index('کلیه تراکنش‌ها')+1:names.index('کلیه تراکنش‌ها')+3] == [LAND_TITLE, 'هزینه ساخت']
        app._order_financial_tabs_184()
        names = [app.fin_nb.tab(tab, 'text') for tab in app.fin_nb.tabs()]
        assert names.index(LAND_TITLE) == names.index('کلیه تراکنش‌ها')+1
        assert [row['pending_id'] for row in app.land_table.all_rows] == [pid]
        assert not any(row.get('pending_id') == pid for row in app.exp_table.all_rows)
        expected_fields = {
            'all_tx_table': ('همه', 'تاریخ', 'عنوان تراکنش', 'گیرنده', 'بابت', 'فاز اصلی'),
            'land_table': ('همه', 'تاریخ', 'واریز کننده', 'بابت'),
            'exp_table': ('همه', 'تاریخ', 'دسته‌بندی', 'گیرنده', 'شرح', 'فاز ساخت'),
            'in_table': ('همه', 'تاریخ', 'واریز کننده', 'شرح', 'نوع ورودی'),
            'out_table': ('همه', 'تاریخ', 'نوع خروجی', 'دریافت کننده', 'شرح'),
            'loan_table': ('همه', 'تاریخ', 'بانک', 'نام وام', 'گیرنده وام', 'وضعیت'),
            'cheque_table': ('همه', 'تاریخ سررسید', 'گیرنده', 'بابت', 'صاحب حساب', 'بانک', 'ثبت', 'شماره صیادی'),
            'document_table': ('همه', 'تاریخ', 'نوع سند', 'شرح', 'فاز ساخت'),
        }
        for name, fields in expected_fields.items():
            table = getattr(app, name)
            assert tuple(table._barkav_filter_field_combo187.cget('values')) == fields
        assert app._transaction_filter_values_187(app.all_tx_table, 'عنوان تراکنش') == ('همه', *TRANSACTION_TITLES)
        assert app._transaction_filter_values_187(app.land_table, 'عنوان تراکنش') == ('همه',)
        assert tuple(app.land_table.tree.cget('columns')) == tuple(
            key for key, _label, _width in app._LAND_TRANSACTION_COLUMNS_187
        )
        table = app.land_table
        assert callable(table.edit_handler) and callable(table.delete_handler)
        assert table.tree.bind('<Double-1>') and table.tree.bind('<Button-3>')
        assert table._barkav_transaction_toolbar187.winfo_exists()
        all_table = app.all_tx_table
        all_table._barkav_filter_field_var187.set('عنوان تراکنش')
        all_table._barkav_filter_value_var187.set(LAND_TITLE)
        app._apply_transaction_view_filter_187(all_table)
        assert [row['pending_id'] for row in all_table.all_rows] == [pid]
        assert runtime.db.snapshot() == before
        row = table.all_rows[0]
        assert app._transaction_document_paths_187(table, row)
        edited = []
        monkeypatch.setattr(app.approval_center, 'open_editor', lambda pending, **kw: edited.append(pending['pending_id']))
        table.edit_handler(row)
        assert edited == [pid]
        selected_filter = app.approval_center.filter.get()
        clone = app._copy_transaction_row_187(table, row)
        clone_row = runtime.db.get_pending_item(clone)
        assert clone_row['status'] == 'PENDING_REVIEW'
        assert clone_row['payload']['v18_subtype'] == LAND_TITLE
        assert runtime.db.list_pending_attachments(clone)
        assert app.approval_center.filter.get() == selected_filter
        assert runtime.db.snapshot() == before
        clone_payload = dict(clone_row['payload'], description='تعهد زمین دوم')
        m.v18.submit_v18(clone, clone_payload, runtime.rich)
        app.refresh_financial()
        import transaction_lifecycle_ui as lifecycle_ui
        confirmations = []
        monkeypatch.setattr(lifecycle_ui, 'confirm_delete', lambda parent, count, **kw:
                            confirmations.append(count) or lifecycle_ui.DeleteChoice(False, True))
        monkeypatch.setattr(table, 'selected_rows', lambda: list(table.all_rows))
        monkeypatch.setattr(app, 'refresh_all', app.refresh_financial)
        table._delete_selected_many()
        assert confirmations == [2]
        assert runtime.db.get_pending_item(pid)['status'] == runtime.db.get_pending_item(clone)['status'] == 'REJECTED'
        assert not table.all_rows
        assert runtime.db.cash_balance() == 300 and runtime.db.land_purchase_cost() == 0
    finally:
        for job in app.tk.call('after', 'info'):
            app.after_cancel(job)
        try:
            app.destroy()
        except tk.TclError:
            app.tk.call('destroy', '.')
        tk._default_root = None
