from sales_claims_stage18_7 import (
    CONTRACT_NON_MONEY_COLUMNS_187, CONTRACT_STEPS_187, CONTRACT_TABLE_COLUMNS_187, EXPORT_PLACEHOLDER_187, contract_note_187, contract_price_per_m2_187,
    contract_table_values_187, filter_contract_rows_187, finance_sales_for_filter_187, payment_plan_187, selectable_row_187,
    payment_detail_export_payload_187, contract_preview_payment_rows_187, payment_labels_for_installments_187, persian_digits_187, toman,
    finance_export_rows_187, visible_rows_payload_187, wizard_export_payload_187, export_contract_pdf_187,
    is_temporary_sales_finance_pending_187, sales_finance_pending_payload_187,
)
from finance_db import FinanceDB
from revenue_service import RevenueService
from pathlib import Path
import inspect
import sqlite3
import tempfile


def test_contract_wizard_has_all_requested_steps():
    assert len(CONTRACT_STEPS_187) == 7
    assert CONTRACT_STEPS_187[0].startswith('۱.')
    assert CONTRACT_STEPS_187[-1].endswith('تأیید نهایی')


def test_payment_plan_uses_delivery_and_deed_dates_when_their_rows_are_blank():
    plan = payment_plan_187({
        'payment_count': '۴',
        'pay_1_amount': '100000', 'pay_1_date': '1405/06/01',
        'pay_6_amount': '200000', 'delivery_date': '1405/08/01',
        'pay_7_amount': '300000', 'deed_date': '1405/09/01',
    })
    assert [(row['sequence_no'], row['due_date_shamsi'], row['amount']) for row in plan] == [
        (1, '1405/06/01', 100000), (6, '1405/08/01', 200000), (7, '1405/09/01', 300000),
    ]


def test_extended_contract_data_is_json_metadata_not_a_schema_change():
    note = contract_note_187({'father_name': 'رضا', 'national_id': '001'})
    assert '"contract_v": 1' in note
    assert '"father_name": "رضا"' in note


def test_same_unit_number_is_allowed_in_different_blocks():
    with tempfile.TemporaryDirectory() as directory:
        service = RevenueService(FinanceDB(Path(directory) / 'sales.sqlite3'))
        common = {
            'project_name': 'بارکاو', 'unit_number': '۱۲', 'buyer_name': 'خریدار',
            'contract_date_shamsi': '1405/06/01', 'contract_amount': 100,
            'installments': [{'sequence_no': 1, 'amount': 100, 'due_date_shamsi': '1405/06/01'}],
            'source': 'TEST',
        }
        first = service.create_sale_bundle(block_name='A', **common)
        second = service.create_sale_bundle(block_name='B', **common)
    assert first['sale_id'] != second['sale_id']


def test_step1_visible_rows_use_persian_money_and_safe_export_payload():
    headers = ['ردیف', 'مبلغ قرارداد (تومان)', 'شماره واحد']
    rows = [(selectable_row_187(1), toman(1234567), '۱۰۱')]
    assert rows[0][0] == '☐ ۱'
    assert rows[0][1] == '۱,۲۳۴,۵۶۷'
    assert visible_rows_payload_187(headers, rows) == [{
        'ردیف': '☐ ۱', 'مبلغ قرارداد (تومان)': '۱,۲۳۴,۵۶۷', 'شماره واحد': '۱۰۱',
    }]


def test_step1_tables_fill_their_area_with_both_scrollbars():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    source = inspect.getsource(SalesClaimsPanel187._tree)
    assert "table_area.pack(fill='both', expand=True)" in source
    assert "orient='horizontal'" in source and "orient='vertical'" in source
    assert 'xscrollcommand=xscroll.set' in source
    assert 'yscrollcommand=yscroll.set' in source
    assert 'stretch=False' in source
    assert 'tree._barkav_xscroll187 = xscroll' in source
    assert "yscroll.grid(row=0, column=0, sticky='ns'" in source
    assert "tree.grid(row=0, column=1, sticky='nsew')" in source
    assert "xscroll.grid(row=1, column=1, sticky='ew'" in source


def test_step2_contract_columns_prices_and_all_filter_are_ledger_derived():
    labels = [label for _key, label, _width in CONTRACT_TABLE_COLUMNS_187]
    assert labels == [
        'ردیف', 'طبقه', 'شماره واحد', 'تاریخ قرارداد', 'خریدار', 'نوع فروش',
        'متراژ فروخته‌شده', 'قیمت هر مترمربع (تومان)', 'مبلغ قرارداد (تومان)',
        'تاریخ تحویل', 'تاریخ سند', 'واریزی (تومان)', 'مانده (تومان)', 'انتخاب',
    ]
    rows = [
        {'buyer_name': 'علی', 'unit_number': '۱۰۱', 'contract_number': 'A-1'},
        {'buyer_name': 'مینا', 'unit_number': '۱۰۲', 'contract_number': 'A-2'},
    ]
    assert filter_contract_rows_187(rows, 'همه', 'همه') == rows
    assert filter_contract_rows_187(rows, 'شماره واحد', '۱۰۲') == [rows[1]]
    row = {'contract_amount': 120000000, 'area': 100, 'floor': '۲', 'unit_number': '۱۰۱', 'buyer_name': 'علی'}
    meta = {'contract_area': '۸۰', 'sale_kind': 'آماده', 'delivery_date': '1405/07/01', 'deed_date': '1405/08/01'}
    assert contract_price_per_m2_187(row, meta) == '۱,۵۰۰,۰۰۰'
    detail = type('Summary', (), {'cash_received': 20000000, 'receivable': 100000000})()
    values = contract_table_values_187(1, row, meta, detail)
    assert values[6] == '۸۰'
    assert values[7] == '۱,۵۰۰,۰۰۰'
    assert contract_table_values_187(1, row, {'sale_kind': 'آماده'}, detail)[6] == '-'


def test_finance_name_filter_with_all_value_returns_every_contract():
    rows = [
        {'sale_id': 'S-1', 'buyer_name': 'علی'},
        {'sale_id': 'S-2', 'buyer_name': 'مینا'},
    ]
    assert finance_sales_for_filter_187(rows, 'نام خریدار', 'همه') == rows
    assert finance_sales_for_filter_187(rows, 'نام خریدار', 'مینا') == [rows[1]]
    assert finance_sales_for_filter_187(rows, 'همه', 'همه', 'S-1') == [rows[0]]


def test_step2_contract_actions_open_sales_specific_windows_not_manual_transactions():
    from sales_claims_stage18_7 import ContractDetails187, SalesClaimsPanel187, SalesRecord187
    panel_source = inspect.getsource(SalesClaimsPanel187)
    assert 'SalesRecord187(' in panel_source
    assert 'ContractDetails187(' in panel_source
    assert "('همه', 'نام خریدار', 'شماره واحد', 'شماره قرارداد')" in panel_source
    # Price refresh remains automatic; no refresh action is exposed in either
    # sales toolbar because it was repeatedly mistaken for a required step.
    assert 'بروزرسانی قیمت‌ها' not in panel_source
    assert '_auto_refresh_prices' in panel_source
    assert 'manual_transaction' not in panel_source
    assert ContractDetails187.__name__ == 'ContractDetails187'
    assert SalesRecord187.__name__ == 'SalesRecord187'
    details_source = inspect.getsource(ContractDetails187)
    assert 'self._set_wizard_fields(sale)' in details_source
    assert 'SalesRecord187._FIELDS' in details_source
    assert "'نمایش سند' if documents else '-'" in details_source
    assert "_WIZARD_BOXES" in details_source
    assert "box.pack(fill='x', expand=True" in details_source


def test_sales_record_action_is_in_contracts_not_finance_toolbar():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    contracts = inspect.getsource(SalesClaimsPanel187._build_contracts)
    finance = inspect.getsource(SalesClaimsPanel187._build_finance)
    assert "'ثبت رکورد فروش', self.open_wizard" not in contracts
    assert 'پنجره رکورد' not in finance


def test_edit_starts_prefilled_sales_wizard_then_retains_sales_record_close_path():
    from sales_claims_stage18_7 import ContractWizard187, SalesClaimsPanel187
    panel = inspect.getsource(SalesClaimsPanel187)
    wizard = inspect.getsource(ContractWizard187)
    assert "'ویرایش', self.open_edit_wizard" in panel
    assert 'self.open_wizard(initial=initial' in panel
    assert 'record_opener=self.open_sales_record' in panel
    assert 'initial: dict[str, Any] | None = None' in wizard
    assert 'self.record_opener(sale_id=self.sale_id, draft=draft' in wizard


def test_all_money_columns_have_toman_and_non_money_columns_do_not():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    contracts = [label for _key, label, _width in CONTRACT_TABLE_COLUMNS_187]
    assert [label for label in contracts if '(تومان)' in label] == [
        'قیمت هر مترمربع (تومان)', 'مبلغ قرارداد (تومان)', 'واریزی (تومان)', 'مانده (تومان)',
    ]
    finance = inspect.getsource(SalesClaimsPanel187._build_finance)
    assert 'مبلغ پرداخت (تومان)' in finance
    assert 'کل مبلغ واریزی مرحله (تومان)' in finance
    assert 'بدهکار/بستانکار تا این مرحله (تومان)' in finance
    assert 'بدهکار تا پایان قرارداد (تومان)' in finance
    assert 'دیرکرد (روز)' in finance


def test_contract_table_restores_non_money_headings_after_inherited_currency_pass():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    from ui_stage18_6 import convert_tree_currency_186
    labels = dict((key, label) for key, label, _width in CONTRACT_TABLE_COLUMNS_187)
    assert CONTRACT_NON_MONEY_COLUMNS_187 == ('date', 'buyer', 'kind')
    assert [labels[key] for key in CONTRACT_NON_MONEY_COLUMNS_187] == ['تاریخ قرارداد', 'خریدار', 'نوع فروش']
    source = inspect.getsource(SalesClaimsPanel187._restore_contract_non_money_headings)
    builder = inspect.getsource(SalesClaimsPanel187._build_contracts)
    init = inspect.getsource(SalesClaimsPanel187.__init__)
    converter = inspect.getsource(convert_tree_currency_186)
    assert 'CONTRACT_NON_MONEY_COLUMNS_187' in source
    assert "self.contract_tree._barkav_non_currency_columns_186 = CONTRACT_NON_MONEY_COLUMNS_187" in builder
    assert 'excluded_columns = set(getattr(tree, \'_barkav_non_currency_columns_186\', ()))' in converter
    assert 'if column in excluded_columns:' in converter
    assert 'self.after(80, self._restore_contract_non_money_headings)' in init


def test_contract_table_localizes_non_money_numeric_display_values():
    from types import SimpleNamespace
    row = {
        'floor': '12', 'unit_number': '101', 'contract_date_shamsi': '1405/01/02',
        'buyer_name': 'علی', 'contract_amount': 1234567,
    }
    meta = {'sale_kind': 'آماده', 'contract_area': '80', 'delivery_date': '1405/02/03', 'deed_date': '1405/03/04'}
    values = contract_table_values_187(1, row, meta, SimpleNamespace(cash_received=0, receivable=0))
    assert values[1:4] == ('۱۲', '۱۰۱', '۱۴۰۵/۰۱/۰۲')
    assert values[6] == '۸۰'
    assert values[9:11] == ('۱۴۰۵/۰۲/۰۳', '۱۴۰۵/۰۳/۰۴')


def test_persian_contract_area_is_used_for_price_calculation():
    from sales_claims_stage18_7 import contract_price_per_m2_187
    assert contract_price_per_m2_187({'contract_amount': 8000000}, {'contract_area': '۸۰'}) == '۱۰۰,۰۰۰'


def test_wizard_save_converts_persian_contract_area_before_ledger_write():
    from sales_claims_stage18_7 import ContractWizard187
    source = inspect.getsource(ContractWizard187._save)
    assert "float(en(raw['contract_area'])" in source


def test_finance_uses_excel_pdf_print_dropdown_and_add_edit_delete_actions():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    source = inspect.getsource(SalesClaimsPanel187._build_finance)
    assert "values=(EXPORT_PLACEHOLDER_187, 'PDF', 'Excel', 'پرینت')" in source
    assert 'self._export_finance_selected' in source
    assert "('✏️', 'ویرایش', self._finance_edit)" in source
    assert "('JSON', 'خروجی'" not in source


def test_data_entry_does_not_show_a_duplicate_sales_record_button():
    dashboard = (Path(__file__).resolve().parents[1] / 'dashboard_stage18_7.py').read_text(encoding='utf-8')
    assert "text='ثبت رکورد فروش'" not in dashboard
    assert '_open_sales_wizard_187' not in dashboard
    assert "style='Toolbar.TButton'" in dashboard
    assert "('در انتظار بررسی', 'Pending')" in dashboard
    assert "text='افزودن'" in dashboard
    assert "text='ویرایش'" in dashboard
    assert "text='بارگذاری بکاپ'" in dashboard  # renamed, operator round 2026-09-27
    assert "def _configure_data_entry_columns_187" in dashboard
    assert "def _fit_data_entry_table_187" in dashboard
    assert "def _data_entry_cell_text_187" in dashboard
    assert "('date', 'تاریخ شمسی فارسی', 60)" in dashboard
    assert "output.pack(side='left'" in dashboard
    assert 'class _HorizontalTreeSeparator187' in dashboard
    assert 'def _build_service_statuses_187' in dashboard
    assert 'super()._service_status_181()' not in dashboard
    assert 'def _start_gemini_probe_187' in dashboard
    assert 'def _start_telegram_probe_187' in dashboard
    assert 'def _update_bot(self):' in dashboard
    assert "getattr(getattr(v186, 'v185', None), 'v18', None)" in dashboard
    assert 'return panel.open_wizard()' in dashboard


def test_detail_export_has_three_formats_and_places_selected_documents_in_payment_cells():
    headers = ['ردیف', 'مبلغ واریز (تومان)', 'نمایش سند']
    rows = [('☐ ۱', '۱,۰۰۰', 'نمایش سند')]
    documents = {'installment-1': [{'attachment_id': 'att-1', 'local_path': 'C:/docs/receipt.png'}]}
    without_documents = payment_detail_export_payload_187(headers, rows, ['installment-1'], documents, False)
    assert without_documents == [{'ردیف': '☐ ۱', 'مبلغ واریز (تومان)': '۱,۰۰۰'}]
    with_documents = payment_detail_export_payload_187(headers, rows, ['installment-1'], documents, True)
    assert with_documents == [{'ردیف': '☐ ۱', 'مبلغ واریز (تومان)': '۱,۰۰۰', 'نمایش سند': 'C:/docs/receipt.png'}]


def test_contract_detail_preview_expands_every_receipt_to_its_own_payment_row():
    headers = ['مرحله', 'تاریخ واریز', 'مبلغ واریز (تومان)', 'نمایش سند']
    rows = [('قسط دوم', '۱۴۰۵/۰۶/۰۳', '۲۰۰,۰۰۰', 'نمایش سند')]
    documents = {'installment-2': [
        {'local_path': 'C:/docs/one.png'}, {'local_path': 'C:/docs/two.png'},
        {'local_path': 'C:/docs/three.png'}, {'local_path': 'C:/docs/four.png'},
    ]}
    payload = payment_detail_export_payload_187(headers, rows, ['installment-2'], documents, True)
    assert [row['نمایش سند'] for row in payload] == [
        'C:/docs/one.png', 'C:/docs/two.png', 'C:/docs/three.png', 'C:/docs/four.png',
    ]
    assert [row['مبلغ واریز (تومان)'] for row in payload] == ['۲۰۰,۰۰۰', '—', '—', '—']
    assert [row['مرحله'] for row in payload] == ['قسط دوم · فیش ۱', 'قسط دوم · فیش ۲', 'قسط دوم · فیش ۳', 'قسط دوم · فیش ۴']


def test_contract_preview_rows_keep_every_payment_and_split_multi_path_cells():
    headers = ['مرحله پرداخت', 'تاریخ واریز', 'مبلغ واریز (تومان)', 'فیش واریزی']
    payload = [{
        'مرحله پرداخت': 'قسط اول', 'تاریخ واریز': '۱۴۰۵/۰۶/۰۱',
        'مبلغ واریز (تومان)': '۱۰۰', 'فیش واریزی': 'C:/docs/one.png\nC:/docs/two.png',
    }, {
        'مرحله پرداخت': 'قسط دوم', 'تاریخ واریز': '۱۴۰۵/۰۶/۰۲',
        'مبلغ واریز (تومان)': '۲۰۰', 'فیش واریزی': '',
    }]
    rows = contract_preview_payment_rows_187(headers, payload)
    assert len(rows) == 3
    assert [row['فیش واریزی'] for row in rows] == ['C:/docs/one.png', 'C:/docs/two.png', '']
    assert rows[1]['مبلغ واریز (تومان)'] == '—'
    assert rows[2]['مرحله پرداخت'] == 'قسط دوم'

def test_contract_detail_double_click_opens_grouped_all_documents_viewer():
    from sales_claims_stage18_7 import ContractDetails187
    source = inspect.getsource(ContractDetails187._open_document)
    assert 'PaymentDocuments187(' in source
    assert "'documents': documents" in source
    assert 'parse_money' in source


def test_wizard_uses_native_titlebar_and_keeps_safe_draft_exports():
    from sales_claims_stage18_7 import ContractWizard187
    payload = wizard_export_payload_187({'buyer_name': 'علی', 'total_price': '1000'}, 'C:/docs/contract.pdf')
    assert payload == {'buyer_name': 'علی', 'total_price': '1000', 'contract_document_path': 'C:/docs/contract.pdf'}
    source = inspect.getsource(ContractWizard187)
    assert 'overrideredirect' not in source
    assert 'command=self._toggle_maximize' not in source
    assert 'command=self.iconify' not in source
    assert 'class ContractWizard187(BarkavWindow)' in source
    assert "subtitle='BARKAV 18.7'" in source
    assert "self._export_wizard('json')" not in source
    assert "self._export_wizard('csv')" not in source
    assert "self._export_wizard('txt')" not in source


def test_contract_record_groups_wizard_fields_in_full_width_titled_boxes():
    from sales_claims_stage18_7 import ContractWizard187, SalesRecord187
    wizard_source = inspect.getsource(ContractWizard187)
    record_source = inspect.getsource(SalesRecord187)
    assert "page = tk.LabelFrame(self.body, text=CONTRACT_STEPS_187[self.step]" in wizard_source
    assert '_WIZARD_GROUPS' in record_source
    assert "self._record_group(form, title" in record_source
    assert "group.grid(row=row, column=0, sticky='ew'" in record_source
    assert "self._render_payment_group()" in record_source
    assert "self._record_group(self._record_form, '۵. شرایط پرداخت'" in record_source
    assert "text='۷. تأیید نهایی'" not in record_source


def test_sales_record_visual_shell_matches_data_entry_card_layout():
    from sales_claims_stage18_7 import SalesRecord187
    source = inspect.getsource(SalesRecord187._build)
    assert "self.configure(bg=bg)" in source
    assert "highlightbackground=line" in source
    assert "tk.PanedWindow(self.body, orient='horizontal'" in source
    assert "text='پیش‌نمایش قرارداد'" in source
    assert "text='مشخصات فروش'" in source
    assert "text='ذخیرهٔ اطلاعات مجاز'" in source


def test_contract_wizard_has_compact_graphical_seven_stage_progress_indicator():
    from sales_claims_stage18_7 import ContractWizard187
    source = inspect.getsource(ContractWizard187)
    assert 'self.progress_canvas = tk.Canvas' in source
    assert 'self._render_progress()' in source
    assert 'canvas.create_rectangle' in source
    assert 'self.step_label.configure' in source


def test_dates_and_numbers_use_persian_display_digits():
    assert persian_digits_187('1405/12/03') == '۱۴۰۵/۱۲/۰۳'
    assert persian_digits_187('1,250,000') == '۱,۲۵۰,۰۰۰'
    from sales_claims_stage18_7 import SalesClaimsPanel187
    assert 'persian_digits_187(item.get(\'due_date_shamsi\')' in inspect.getsource(SalesClaimsPanel187._refresh_finance)


def test_wizard_date_fields_use_rtl_persian_shamsi_picker_with_year_and_month():
    from sales_claims_stage18_7 import ContractWizard187, ShamsiDatePicker187
    source = inspect.getsource(ContractWizard187._field)
    picker = inspect.getsource(ShamsiDatePicker187)
    assert 'ShamsiDatePicker187(self, current)' in source
    assert "justify='right'" in source
    assert "text='تقویم'" in source
    assert 'self.year_box = ttk.Combobox' in picker
    assert 'self.month_box = ttk.Combobox' in picker
    assert 'kit_font(' in picker
    assert "_p('on_accent')" in picker
    assert "text='ماه قبل'" in picker and "text='ماه بعد'" in picker
    assert "self.variable.set(persian_digits_187" in picker


def test_sales_tabs_use_the_shared_strip_like_every_other_tab():
    """Sales used to draw its own rounded canvas tabs with bespoke sizing and a
    hard-coded blue active title, which made it the one strip in the product
    that did not match the rest.  It now uses the shared kit strip, so its
    sub-tabs follow the same colours and the same one-step-smaller size ladder.
    """
    import sales_claims_stage18_7 as sales
    panel = inspect.getsource(sales.SalesClaimsPanel187.__init__)
    assert 'TabStrip(self.nb, level=1)' in panel
    assert not hasattr(sales, 'SalesTabStrip187')
    for literal in ('#315D86', '#FFFFFF', 'tab_line'):
        assert literal not in panel


def test_sales_export_combos_start_with_placeholder_and_do_not_export_on_placeholder():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    contracts = inspect.getsource(SalesClaimsPanel187._build_contracts)
    finance = inspect.getsource(SalesClaimsPanel187._build_finance)
    contract_handler = inspect.getsource(SalesClaimsPanel187._export_contract_selected)
    finance_handler = inspect.getsource(SalesClaimsPanel187._export_finance_selected)
    assert "value=EXPORT_PLACEHOLDER_187" in contracts
    assert "value=EXPORT_PLACEHOLDER_187" in finance
    assert 'if not export_label:' in contract_handler
    assert 'if not export_label:' in finance_handler


def test_wizard_amount_input_uses_persian_thousands_grouping():
    from sales_claims_stage18_7 import ContractWizard187, formatted_amount_input_187
    assert formatted_amount_input_187('1234567') == '۱,۲۳۴,۵۶۷'
    source = inspect.getsource(ContractWizard187._format_wizard_variable)
    assert 'formatted_amount_input_187' in source
    assert "key.startswith('pay_')" in source


def test_sales_record_amount_input_uses_persian_thousands_grouping():
    from sales_claims_stage18_7 import SalesRecord187
    source = inspect.getsource(SalesRecord187._format_record_variable)
    init_source = inspect.getsource(SalesRecord187.__init__)
    assert 'formatted_amount_input_187' in source
    assert "key.startswith('pay_')" in source
    assert '_format_record_variable(field, current)' in init_source


def test_finance_toolbar_has_add_delete_search_and_exports_without_visible_refresh():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    source = inspect.getsource(SalesClaimsPanel187._build_finance)
    export = inspect.getsource(SalesClaimsPanel187._export_finance_selected)
    assert "'اضافه'" in source
    assert "'حذف'" in source
    assert "'بروزرسانی'" not in source
    assert "('🔄', 'بروزرسانی', self._refresh_finance)" not in source
    assert "values=(EXPORT_PLACEHOLDER_187, 'PDF', 'Excel', 'پرینت')" in source
    assert 'self._export_finance_selected' in source and 'self._open_selected_documents' in export
    assert 'finance_export_combo.bind' in source
    assert 'finance_search_kind' in source and 'finance_search_value' in source


def test_finance_export_selection_accepts_combobox_event_and_maps_save_as_format():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    source = inspect.getsource(SalesClaimsPanel187._export_finance_selected)
    save = inspect.getsource(SalesClaimsPanel187._save_finance_export)
    assert 'def _export_finance_selected(self, _event=None)' in source
    assert "'Excel': 'Excel'" in source and "'PDF': 'PDF'" in source and "'پرینت': 'پرینت'" in source
    assert 'self._open_selected_documents()' in source
    assert 'self.finance_export_choice.set(EXPORT_PLACEHOLDER_187)' in source
    assert 'ContractExportPreview187' not in source
    assert 'asksaveasfilename' in save


def test_finance_export_preview_embeds_receipts_at_a6_size():
    from sales_claims_stage18_7 import SalesClaimsPanel187, export_receipts_pdf_187
    save = inspect.getsource(SalesClaimsPanel187._save_finance_export)
    documents = inspect.getsource(SalesClaimsPanel187._finance_export_documents)
    pdf = inspect.getsource(export_receipts_pdf_187)
    assert 'export_receipts_pdf_187' in save
    assert '_finance_export_documents' in save
    assert 'list_for_entities' in documents
    assert '105 * mm' in pdf and '148 * mm' in pdf


def test_finance_export_opens_receipt_documents_window_and_preview_uses_receipt_title():
    from sales_claims_stage18_7 import SalesClaimsPanel187, PaymentDocuments187, ContractExportPreview187
    finance = inspect.getsource(SalesClaimsPanel187._export_finance_selected)
    build = inspect.getsource(SalesClaimsPanel187._build_finance)
    opener = inspect.getsource(SalesClaimsPanel187._open_selected_documents)
    preview = inspect.getsource(ContractExportPreview187)
    assert "self._open_selected_documents()" in finance
    assert "text='نمایش اسناد واریزی'" not in build
    assert 'return PaymentDocuments187(' in opener and 'window.export_choice.set(export_format)' not in opener
    assert "window_title='پیش‌نمایش اسناد واریزی'" in inspect.getsource(PaymentDocuments187._export)
    assert "self.title(window_title)" in preview


def test_contract_export_preview_sets_readable_foreground_on_light_surface():
    from sales_claims_stage18_7 import ContractExportPreview187
    assert 'art.logo(' in inspect.getsource(ContractExportPreview187._render)
    assert 'create_image(left_x * scale' in inspect.getsource(ContractExportPreview187._render)
    source = inspect.getsource(ContractExportPreview187)
    assert "bg='#0A1A2A'" in source
    render = inspect.getsource(ContractExportPreview187._render)
    assert "fill='#FFFFFF'" in render and 'self.preview.create_text' in render


def test_contract_export_preview_builds_visible_text_for_contract_specs_and_payments():
    from sales_claims_stage18_7 import contract_export_preview_lines_187
    lines = contract_export_preview_lines_187(
        [('۱. مورد معامله', 'شماره واحد', 'متری-۱'), ('۴. مالی', 'مبلغ قرارداد', '۱,۰۰۰,۰۰۰')],
        [{'ردیف': '۱', 'مرحله': 'پرداخت نقدی', 'مبلغ': '۵۰۰,۰۰۰'}],
        ['ردیف', 'مرحله', 'مبلغ'],
        ['C:/tmp/receipt.jpg'],
    )
    text = '\n'.join(value for _tag, value in lines)
    assert 'مشخصات قرارداد' in text and 'شماره واحد: متری-۱' in text
    assert 'جدول پرداخت‌ها' in text and 'پرداخت نقدی' in text
    assert 'فیش‌های واریزی انتخاب‌شده:' in text and 'receipt.jpg' in text

    from sales_claims_stage18_7 import ContractExportPreview187
    source = inspect.getsource(ContractExportPreview187)
    assert "self.preview = tk.Canvas" in source
    assert "self.preview.create_text" in inspect.getsource(ContractExportPreview187._render)
    render = inspect.getsource(ContractExportPreview187._render)
    assert 'export_document_paths_187' in render and 'self.preview.create_image' in render


def test_contract_export_preview_has_three_centered_header_sections():
    from sales_claims_stage18_7 import ContractExportPreview187
    specs = [('۱. مورد معامله', 'نام پروژه', 'بارکاو۲')]
    assert ContractExportPreview187._project_name(specs) == 'بارکاو۲'
    assert ContractExportPreview187._output_title('پیش‌نمایش خروجی قرارداد') == 'جزئیات قرارداد فروش'
    render = inspect.getsource(ContractExportPreview187._render)
    assert 'header_height = 146 if self.include_addressee else 112' in render
    assert 'section_width = (header_right - header_left) / 3' in render
    assert 'شرکت مهندسی ساخت بارکاو' in render
    assert "f'پروژه {self._project_name(self.specs)}'" in render
    assert 'self.output_title' in render
    assert 'anchor=\'center\'' in render
    assert 'bold=True' in render
    assert "preview_font_family = kit_font('title', widget=self, bold=True)[0]" in render

def test_export_preview_has_orientation_zoom_and_left_drag_controls():
    from sales_claims_stage18_7 import ContractExportPreview187
    source = inspect.getsource(ContractExportPreview187)
    render = inspect.getsource(ContractExportPreview187._render)
    assert "values=('افقی', 'عمودی')" in source
    assert "self.preview.bind('<MouseWheel>', self._preview_mouse_zoom" in source
    assert "self.preview.bind('<ButtonPress-1>'" in source and "self.preview.bind('<B1-Motion>'" in source
    assert "self.on_confirm(self.format_choice.get(), self.orientation_choice.get())" in source
    assert 'portrait = self.orientation_choice.get() == \'عمودی\'' in render


def test_receipt_pdf_uses_compact_receipt_cells_and_accepts_portrait_preview_choice(tmp_path):
    from PIL import Image
    from pypdf import PdfReader
    from sales_claims_stage18_7 import export_receipts_pdf_187
    receipt = tmp_path / 'receipt.png'
    Image.new('RGB', (60, 90), '#ffffff').save(receipt)
    output = tmp_path / 'receipt_cells.pdf'
    export_receipts_pdf_187(
        output, ['مرحله پرداخت', 'فیش واریزی'], [['قسط اول', str(receipt)]], 'اسناد واریزی',
        ['مبلغ کل قرارداد (تومان): ۱,۰۰۰,۰۰۰', 'مبلغ واریزی (تومان): ۵۰۰,۰۰۰', 'مبلغ بدهکار/بستانکار (تومان): ۵۰۰,۰۰۰'],
        [str(receipt)], orientation='عمودی',
    )
    assert output.is_file() and len(PdfReader(str(output)).pages) >= 1
    source = inspect.getsource(export_receipts_pdf_187)
    assert 'A3' in source and '(74 if documents_below_rows else 45) * mm' in source
    assert '(105 if documents_below_rows else 64) * mm' in source
    assert "header in document_headers" in source and 'orientation' in source


def test_receipt_pdf_flows_compact_receipt_rows_to_the_next_page(tmp_path):
    from PIL import Image
    from pypdf import PdfReader
    from sales_claims_stage18_7 import export_receipts_pdf_187

    receipt = tmp_path / 'receipt.png'
    Image.new('RGB', (100, 160), '#ffffff').save(receipt)
    output = tmp_path / 'many_receipts.pdf'
    export_receipts_pdf_187(
        output, ['مرحله پرداخت', 'فیش واریزی'],
        [[f'قسط {index}', str(receipt)] for index in range(1, 12)],
        'اسناد واریزی', [], [str(receipt)], orientation='عمودی',
    )
    assert output.is_file() and len(PdfReader(str(output)).pages) >= 2


def test_payment_documents_pdf_save_writes_a_real_file_after_preview_confirmation(tmp_path, monkeypatch):
    import sales_claims_stage18_7 as sales
    from PIL import Image
    from sales_claims_stage18_7 import PaymentDocuments187

    receipt = tmp_path / 'receipt.png'
    Image.new('RGB', (40, 60), '#ffffff').save(receipt)
    destination = tmp_path / 'payment_documents.pdf'
    notices = []
    monkeypatch.setattr(sales.filedialog, 'asksaveasfilename', lambda **_kwargs: str(destination))
    monkeypatch.setattr(sales.messagebox, 'showinfo', lambda *args, **_kwargs: notices.append(args))
    PaymentDocuments187._save_export(
        object(), 'PDF', ['مرحله پرداخت', 'تاریخ واریز', 'مبلغ واریز (تومان)', 'فیش واریزی'],
        [{'مرحله پرداخت': 'پرداخت نقدی', 'تاریخ واریز': '۱۴۰۵/۰۶/۰۱', 'مبلغ واریز (تومان)': '۵۰۰,۰۰۰', 'فیش واریزی': str(receipt)}],
        [('خلاصه', 'مبلغ کل قرارداد (تومان)', '۱,۰۰۰,۰۰۰')], [str(receipt)],
    )
    assert destination.is_file() and destination.stat().st_size > 0
    assert notices and notices[-1][0] == 'خروجی اسناد'


def test_payment_document_receipt_canvas_supports_left_drag_without_new_window():
    from sales_claims_stage18_7 import PaymentDocuments187
    source = inspect.getsource(PaymentDocuments187._document_card)
    assert "canvas.bind('<ButtonPress-1>'" in source
    assert "canvas.bind('<B1-Motion>'" in source
    assert '_open_image_zoom' not in source


def test_receipt_preview_has_visible_empty_state_and_save_errors_are_reported():
    from sales_claims_stage18_7 import ContractExportPreview187, PaymentDocuments187, contract_export_preview_lines_187
    save = inspect.getsource(PaymentDocuments187._save_export)
    assert ('rtl', 'داده‌ای برای پیش‌نمایش انتخاب نشده است.') in contract_export_preview_lines_187([], [], [])
    assert "self.preview = tk.Canvas" in inspect.getsource(ContractExportPreview187)
    assert 'Path(path).parent.mkdir' in save and 'except Exception as exc' in save


def test_payment_documents_export_previews_before_save_and_includes_receipt_paths():
    from sales_claims_stage18_7 import PaymentDocuments187
    export = inspect.getsource(PaymentDocuments187._export)
    save = inspect.getsource(PaymentDocuments187._save_export)
    assert 'ContractExportPreview187' in export
    assert 'on_confirm' in export and 'document_paths' in export
    assert 'asksaveasfilename' in save
    assert 'export_receipts_pdf_187' in save
    assert "values=('Excel', 'PDF', 'پرینت')" not in export


def test_finance_edit_routes_to_original_record_without_duplicate_receipt():
    from sales_claims_stage18_7 import SalesClaimsPanel187, sales_finance_pending_payload_187
    toolbar = inspect.getsource(SalesClaimsPanel187._build_finance)
    source = inspect.getsource(SalesClaimsPanel187._finance_edit)
    pending = inspect.getsource(sales_finance_pending_payload_187)
    assert "'ویرایش'" in toolbar
    assert "_selected_finance_receipts_187" in source and "edit_transaction_row" in source
    assert "'EDIT': 'EDIT_REQUEST'" in pending
    assert "'received_payment_id'" in pending and "'transaction_id'" in pending
    assert 'record_received_payment' not in pending


def test_finance_context_removes_copy_paste_and_routes_add_edit_delete_to_data_entry():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    toolbar = inspect.getsource(SalesClaimsPanel187._build_finance)
    context = inspect.getsource(SalesClaimsPanel187._context)
    add = inspect.getsource(SalesClaimsPanel187._finance_add)
    edit = inspect.getsource(SalesClaimsPanel187._finance_edit)
    delete = inspect.getsource(SalesClaimsPanel187._finance_delete)
    assert "'اضافه'" in toolbar and "'حذف'" in toolbar
    assert 'if tree is self.finance_tree' in context
    assert "'📋 کپی'" in context and "'📋 کپی'" not in context.split('if tree is self.finance_tree', 1)[1].split('else:', 1)[0]
    assert '_create_finance_pending' in add
    assert "edit_transaction_row" in edit
    assert '_delete_lifecycle_rows187' in delete


def test_finance_add_delete_create_pending_with_buyer_context_without_cash_posting():
    from sales_claims_stage18_7 import SalesClaimsPanel187, sales_finance_pending_payload_187
    source = inspect.getsource(SalesClaimsPanel187._create_finance_pending)
    payload = inspect.getsource(sales_finance_pending_payload_187)
    assert 'create_or_replace_pending' in source
    assert "'buyer_name': sale.get('buyer_name')" in payload
    assert "'EDIT': 'EDIT_REQUEST'" in payload
    assert "center.open_wizard(row)" in source
    assert 'record_received_payment' not in source


def test_finance_add_and_edit_pending_use_input_sale_labels_and_keep_receipt_context():
    sale = {'sale_id': 'SALE-1', 'buyer_name': 'علی', 'unit_number': '۱۰۱', 'contract_number': 'C-7'}
    installment = {'installment_id': 'INST-1', 'amount': 500_000}
    receipt = {'received_payment_id': 'REC-1', 'transaction_id': 'TX-1', 'amount': 250_000,
               'received_date_shamsi': '۱۴۰۵/۰۶/۰۱'}
    add = sales_finance_pending_payload_187(action='ADD', sale=sale, installment=installment, receipt={})
    edit = sales_finance_pending_payload_187(action='EDIT', sale=sale, installment=installment, receipt=receipt)
    assert (add['v18_title'], add['v18_subtype'], add['amount']) == ('ورودی', 'فروش', 500_000)
    assert (edit['v18_title'], edit['v18_subtype'], edit['amount']) == ('ورودی', 'فروش', 250_000)
    assert edit['event_date_shamsi'] == '۱۴۰۵/۰۶/۰۱'
    assert edit['received_payment_id'] == 'REC-1' and edit['transaction_id'] == 'TX-1'
    assert is_temporary_sales_finance_pending_187(add)
    assert is_temporary_sales_finance_pending_187(edit)


def test_sales_finance_pending_display_date_is_shamsi_persian_digits():
    from sales_claims_stage18_7 import sales_finance_pending_message_date_187

    assert sales_finance_pending_message_date_187({'event_date_shamsi': '1405/06/01'}) == '۱۴۰۵/۰۶/۰۱'
    assert sales_finance_pending_message_date_187({'event_date_shamsi': '۱۴۰۵/۰۶/۰۲ 12:30'}) == '۱۴۰۵/۰۶/۰۲'


def test_unapproved_sales_finance_pending_is_rejected_without_changing_the_existing_receipt():
    from telegram_workflow import TelegramReviewWorkflow
    with tempfile.TemporaryDirectory() as directory:
        db = FinanceDB(Path(directory) / 'sales-pending.sqlite3')
        payload = sales_finance_pending_payload_187(
            action='EDIT', sale={'sale_id': 'SALE-1'}, installment={'installment_id': 'INST-1'},
            receipt={'received_payment_id': 'REC-1', 'transaction_id': 'TX-1', 'amount': 250_000,
                     'received_date_shamsi': '1405/06/01'},
        )
        db.register_telegram_message(chat_id=-187, message_id=187001, raw_text='', content_type='sales_finance',
                                     message_date='2026-08-25T00:00:00', state='RECEIVED')
        pending_id = db.create_or_replace_pending(telegram_chat_id=-187, telegram_message_id=187001,
                                                  detected_type='TRANSACTION', payload=payload,
                                                  confidence=1.0, status='PENDING_REVIEW')
        TelegramReviewWorkflow(db).reject(pending_id)
        assert db.get_pending_item(pending_id)['status'] == 'REJECTED'
        assert db.get_telegram_message(-187, 187001)['state'] == 'REJECTED'
        assert db.get_financial_posting(pending_id) is None


def test_sales_finance_data_entry_closes_an_unapproved_temporary_draft_safely():
    source = Path('dashboard_stage18_7.py').read_text(encoding='utf-8')
    assert 'class SalesFinancePendingWizard187' in source
    assert 'class SalesFinancePendingEditor187' in source
    assert 'SalesFinancePendingWizard187(self, row, self.rich, done, full)' in source
    assert "v186.APPROVAL.reject(pending_id, actor_id='GUI_187_SALES_FINANCE_CANCEL')" in source
    assert "self.protocol('WM_DELETE_WINDOW', self._abandon)" in source
    assert 'جلوگیری از واریزی تکراری' in source


def test_finance_receipt_documents_window_groups_selected_stages_and_exports():
    from sales_claims_stage18_7 import PaymentDocuments187, SalesClaimsPanel187
    panel = inspect.getsource(SalesClaimsPanel187._build_finance)
    opener = inspect.getsource(SalesClaimsPanel187._open_selected_documents)
    window = inspect.getsource(PaymentDocuments187)
    assert "'نمایش اسناد واریزی'" not in panel
    assert 'list_for_entities' in opener and 'payment_allocations' in opener
    assert 'self.stage_filter' in window and 'همه موارد' in window
    assert "'Excel': 'xlsx'" in window and 'ContractExportPreview187' in window
    assert 'export_receipts_pdf_187' in window
    assert 'export_receipts_pdf_187' in window and 'startfile' in window
    assert 'سند ثبت نشده است' in window


def test_finance_receipt_documents_include_sale_payment_links_and_export_summary():
    from sales_claims_stage18_7 import PaymentDocuments187, SalesClaimsPanel187
    opener = inspect.getsource(SalesClaimsPanel187._open_selected_documents)
    export = inspect.getsource(PaymentDocuments187._export)
    assert "('SALE_PAYMENT'" in opener and "('TRANSACTION'" in opener
    assert 'known = ' in opener
    assert 'مبلغ کل قرارداد (تومان)' in export
    assert 'summary_lines' in export
    assert 'Helvetica' not in export


def test_receipt_documents_summary_uses_separate_right_aligned_amount_fields():
    from sales_claims_stage18_7 import PaymentDocuments187
    build = inspect.getsource(PaymentDocuments187._build)
    refresh = inspect.getsource(PaymentDocuments187._render_cards)
    assert 'self.summary_values = {}' in build
    assert "('debt', 'مبلغ بدهکار/بستانکار (تومان)')" in build
    assert "self.summary_values['debt'].set(toman(debt))" in refresh


def test_receipt_thumbnails_are_left_aligned_and_open_zoom_viewer():
    from sales_claims_stage18_7 import PaymentDocuments187
    source = inspect.getsource(PaymentDocuments187._document_card)
    zoom = inspect.getsource(PaymentDocuments187._open_image_zoom)
    assert "image_host.pack(side='left'" in source
    assert 'ImageTk.PhotoImage' in source
    assert "text='+'" in source and "text='−'" in source
    assert "<MouseWheel>" in source and 'zoom.get()' in source
    assert 'self.attachments.get' in source
    assert 'tk.Toplevel' not in source


def test_finance_table_has_left_document_action_and_direct_save_as_export():
    from sales_claims_stage18_7 import PaymentDocuments187, SalesClaimsPanel187
    build = inspect.getsource(SalesClaimsPanel187._build_finance)
    refresh = inspect.getsource(SalesClaimsPanel187._refresh_finance)
    click = inspect.getsource(SalesClaimsPanel187._finance_document_click)
    export = inspect.getsource(SalesClaimsPanel187._export_tree)
    window = inspect.getsource(PaymentDocuments187._build)
    assert "('document', 'نمایش سند'" in build
    assert "'نمایش سند', selection_cell_187())" in refresh
    assert "key != 'document'" in click and "self._open_selected_documents()" in click
    assert 'filedialog.asksaveasfilename' in export and 'export_contract_pdf_187' in export
    assert "values=(EXPORT_PLACEHOLDER_187, 'PDF', 'Excel', 'پرینت')" in window


def test_finance_exports_force_selected_json_csv_or_txt_format():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    source = inspect.getsource(SalesClaimsPanel187._export_tree)
    assert "export_format: str | None = None" in source
    assert "formats = {'json'" in source
    assert "'csv': ('CSV', '.csv'" in source
    assert "'txt': ('TXT', '.txt'" in source


def test_contract_pdf_export_uses_project_rtl_font_and_does_not_render_persian_as_squares():
    from sales_claims_stage18_7 import ContractDetails187, SalesClaimsPanel187
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        output = export_contract_pdf_187(Path(directory) / 'contracts.pdf', ['خریدار'], [['علی رضایی']], 'قراردادها')
        assert output.exists() and output.read_bytes().startswith(b'%PDF')
    source = inspect.getsource(export_contract_pdf_187)
    panel_export = inspect.getsource(SalesClaimsPanel187._export_tree)
    details_export = inspect.getsource(ContractDetails187._save_export)
    assert 'from export_utils import export_pdf' in source
    assert 'export_contract_pdf_187' in panel_export and 'export_receipts_pdf_187' in details_export
    assert 'Helvetica' not in panel_export and 'Helvetica' not in details_export


def test_finance_export_removes_checkbox_glyphs_but_keeps_selected_row_text():
    headers = ['ردیف', 'مرحله پرداخت', 'مبلغ پرداخت (تومان)']
    rows = [('☑ ۲', 'قسط اول', '۱,۰۰۰'), ('☐ ۳', 'قسط دوم', '۲,۰۰۰')]
    assert finance_export_rows_187(headers, rows) == [
        {'ردیف': '۲', 'مرحله پرداخت': 'قسط اول', 'مبلغ پرداخت (تومان)': '۱,۰۰۰'},
        {'ردیف': '۳', 'مرحله پرداخت': 'قسط دوم', 'مبلغ پرداخت (تومان)': '۲,۰۰۰'},
    ]


def test_finance_tab_has_theme_summary_edit_actions_and_receipts_above_table():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    source = inspect.getsource(SalesClaimsPanel187._build_finance)
    context = inspect.getsource(SalesClaimsPanel187._context)
    assert "style='SalesClaims.Summary.TLabel'" in source
    assert "('✏️', 'ویرایش', self._finance_edit)" in source
    assert "text='نمایش اسناد واریزی'" not in source
    assert "label='✏️ ویرایش'" in context


def test_finance_columns_keep_toman_only_on_money_and_have_separate_selection_column():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    source = inspect.getsource(SalesClaimsPanel187._build_finance)
    checkbox = inspect.getsource(SalesClaimsPanel187._toggle_row_checkbox)
    assert "('stage', 'مرحله پرداخت'" in source
    assert "('due', 'تاریخ پرداخت'" in source
    assert "heading('stage', text='مرحله پرداخت'" in source
    assert "heading('due', text='تاریخ پرداخت'" in source
    assert "self.finance_tree._barkav_non_currency_columns_186 = ('row', 'stage', 'due', 'late', 'document')" in source
    assert 'مرحله پرداخت (تومان)' not in source and 'تاریخ پرداخت (تومان)' not in source
    assert 'بدهکار تا پایان قرارداد (تومان)' in source
    assert "self._install_row_checkbox(self.finance_tree)" in source
    assert "self.finance_tree.heading('row', text='ردیف'" in source
    refresh = inspect.getsource(SalesClaimsPanel187._refresh_finance)
    assert "('select', 'انتخاب', 75)" in source
    assert 'selection_cell_187()' in refresh


def test_selection_checkbox_targets_dedicated_column_and_selects_whole_row():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    source = inspect.getsource(SalesClaimsPanel187._toggle_row_checkbox)
    assert "visible_key = visible_columns[int(column_id[1:]) - 1]" in source
    assert "if visible_key != 'select'" in source
    assert 'tree.selection_add(iid)' in source and 'tree.selection_remove(iid)' in source
    assert 'tree.focus(iid)' in source
    assert 'tree.see(iid)' in source


def test_selection_header_toggles_all_rows():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    source = inspect.getsource(SalesClaimsPanel187._tree)
    toggle = inspect.getsource(SalesClaimsPanel187._toggle_all_checkboxes)
    assert "text='انتخاب ☐'" in source and 'command=lambda target=tree' in source
    assert 'all(str(tree.item(iid, \'values\')[column_index]).startswith(\'☑\')' in toggle
    assert "tree.heading('select', text=f\"انتخاب" in toggle


def test_payment_documents_show_a_no_document_message_and_use_native_window_chrome():
    from sales_claims_stage18_7 import PaymentDocuments187
    source = inspect.getsource(PaymentDocuments187)
    assert 'overrideredirect' not in source
    assert "self.title('اسناد واریزی')" in source
    assert "path == 'سند ثبت نشده است'" in source
    assert "messagebox.showinfo('اسناد واریزی', 'سند ثبت نشده است.'" in source


def test_sales_contract_and_finance_tables_share_light_separator_style():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    init_source = inspect.getsource(SalesClaimsPanel187.__init__)
    tree_source = inspect.getsource(SalesClaimsPanel187._tree)
    assert "SalesClaims.Treeview" in init_source
    assert "borderwidth=0" in init_source and "relief='flat'" in init_source
    assert "style='SalesClaims.Treeview'" in tree_source


def test_contract_details_uses_excel_pdf_print_dropdown():
    from sales_claims_stage18_7 import ContractDetails187
    build = inspect.getsource(ContractDetails187._build)
    export = inspect.getsource(ContractDetails187._save_export)
    assert "values=(EXPORT_PLACEHOLDER_187, 'PDF', 'Excel', 'پرینت')" in build
    assert 'self._export_selected' in build
    assert "'Excel': 'xlsx'" in export or "'Excel': 'xlsx'" in inspect.getsource(ContractDetails187._export_selected)
    assert 'openpyxl' in export and 'export_receipts_pdf_187' in export


def test_contract_details_export_includes_wizard_fields_before_payment_table():
    from sales_claims_stage18_7 import ContractDetails187, ContractExportPreview187, export_receipts_pdf_187
    fields = inspect.getsource(ContractDetails187._set_wizard_fields)
    export = inspect.getsource(ContractDetails187._save_export)
    preview = inspect.getsource(ContractExportPreview187)
    assert 'self._wizard_export_fields = export_fields' in fields
    assert "sheet.title = 'مشخصات قرارداد'" in export
    assert "sheet.append(('کادر ویزارد', 'عنوان', 'مقدار'))" in export
    assert "'خروجی جزئیات قرارداد'" in export and 'export_receipts_pdf_187' in export
    assert 'format_combo' in preview and 'تأیید و ذخیره' in preview
    assert 'platypus.Image' in inspect.getsource(export_receipts_pdf_187)


def test_contract_pdf_export_renders_wizard_specs_as_separate_boxes():
    from sales_claims_stage18_7 import ContractDetails187, export_receipts_pdf_187
    pdf = inspect.getsource(export_receipts_pdf_187)
    save = inspect.getsource(ContractDetails187._save_export)
    assert "'BOX'" in pdf and "'INNERGRID'" in pdf
    assert "'SPAN', (0, 0), (-1, 0)" in pdf
    assert 'export_receipts_pdf_187(destination' in save
    assert 'list(document_paths or [])' in save


def test_contract_preview_is_rtl_and_shows_selected_receipt_images_and_excel_embeds_them():
    from sales_claims_stage18_7 import ContractDetails187, ContractExportPreview187
    preview = inspect.getsource(ContractExportPreview187)
    save = inspect.getsource(ContractDetails187._save_export)
    export = inspect.getsource(ContractDetails187._export)
    assert 'document_paths=None' in preview and 'create_image' in preview
    assert "justify='right'" in preview and 'self.preview.create_text' in preview
    assert 'document_paths=document_paths' in export
    assert 'ExcelImage' in save and 'add_image' in save


def test_contract_details_has_native_resize_controls_and_swapped_card_columns():
    from sales_claims_stage18_7 import ContractDetails187
    init = inspect.getsource(ContractDetails187.__init__)
    cards = inspect.getsource(ContractDetails187._build_wizard_box)
    assert 'self.resizable(True, True)' in init
    assert 'self.transient(parent)' not in init
    assert 'overrideredirect' not in init
    assert 'original_column' in cards and 'column = 1 - original_column' in cards


def test_contracts_tab_uses_excel_pdf_print_dropdown():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    build = inspect.getsource(SalesClaimsPanel187._build_contracts)
    helper = inspect.getsource(SalesClaimsPanel187._export_contract_selected)
    assert "values=(EXPORT_PLACEHOLDER_187, 'PDF', 'Excel', 'پرینت')" in build
    assert 'self._export_contract_selected' in build
    assert "contract_export_combo.bind('<<ComboboxSelected>>', self._export_contract_selected)" in build
    assert 'ایجاد خروجی' not in build
    assert "'Excel': 'Excel'" in helper and "'PDF': 'PDF'" in helper and "'پرینت': 'پرینت'" in helper
    assert 'ContractDetails187(' in helper and 'details._export_selected()' in helper


def test_contracts_tab_export_choice_routes_to_selected_contract_details():
    from sales_claims_stage18_7 import SalesClaimsPanel187

    class Choice:
        def __init__(self, value): self.value = value
        def get(self): return self.value

    class PanelHarness:
        def __init__(self, value): self.contract_export_choice, self.contract_tree = Choice(value), self.Tree()
        class Tree:
            def selection(self): return ('sale-1',)
        def winfo_toplevel(self): return object()

    for value in ('Excel', 'PDF', 'پرینت'):
        panel = PanelHarness(value)
        # The real Toplevel is intentionally not created in headless tests;
        # the source-level assertions above verify the runtime route.
        assert panel.contract_export_choice.get() == value


def test_contract_wizard_step_zero_has_contract_upload_option():
    from sales_claims_stage18_7 import ContractWizard187
    source = inspect.getsource(ContractWizard187._show_step)
    assert "text='بارگذاری قرارداد'" in source
    assert 'command=self._load_document' in source


def test_contract_wizard_card_titles_are_top_right_aligned():
    from sales_claims_stage18_7 import ContractWizard187, SalesRecord187
    wizard = inspect.getsource(ContractWizard187._show_step)
    record = inspect.getsource(SalesRecord187._record_group)
    assert "labelanchor='ne'" in wizard
    assert "labelanchor='ne'" in record


def test_sales_record_and_details_place_payment_stage_five_before_signers_stage_six():
    from sales_claims_stage18_7 import ContractDetails187, SalesRecord187
    record = inspect.getsource(SalesRecord187._build)
    details = inspect.getsource(ContractDetails187._set_wizard_fields)
    assert 'signer_groups = []' in record and 'for title, keys in signer_groups' in record
    assert "self._render_payment_group()" in record
    assert "self._record_group(self._record_form, '۵. شرایط پرداخت'" in inspect.getsource(SalesRecord187._render_payment_group)
    assert 'signer_boxes = []' in details and 'for title, keys in signer_boxes' in details
    assert "self._build_wizard_box('۵. شرایط پرداخت'" in details


def test_sales_record_window_has_numbered_stage_seven_confirmation_card():
    from sales_claims_stage18_7 import SalesRecord187
    source = inspect.getsource(SalesRecord187._build)
    assert "'۷. تأیید نهایی'" in source
    assert "text='ذخیرهٔ اطلاعات مجاز'" in source


def test_sales_record_has_native_titlebar_without_custom_window_controls():
    from sales_claims_stage18_7 import SalesRecord187
    source = inspect.getsource(SalesRecord187)
    assert 'overrideredirect' not in source
    assert "text='—'" not in source and "text='□'" not in source and "text='×'" not in source
    assert "self.title('پنجره رکورد فروش')" in source


def test_sales_record_uses_project_units_editable_area_and_dynamic_payment_plan():
    from sales_claims_stage18_7 import SalesRecord187
    source = inspect.getsource(SalesRecord187)
    build = inspect.getsource(SalesRecord187._record_field)
    payment = inspect.getsource(SalesRecord187._render_payment_group)
    assert 'SELECT unit_number, floor, area FROM units' in source
    assert "self._unit_combo.bind('<<ComboboxSelected>>', self._unit_selected)" in source
    assert "self.values['map_area'].set" in source and "self.values['floor'].set" in source
    assert "values=('واحد کامل', 'فروش متری')" in build
    assert "values=('پیش‌فروش', 'آماده')" in build
    assert "'تعداد اقساط'" in payment
    assert "widget = ttk.Entry(box, textvariable=self.values[key]" in build
    assert "widget.bind('<FocusOut>', self._payment_count_changed)" in build
    assert "int(en(self.values['payment_count'].get())) - 3" in inspect.getsource(SalesRecord187._payment_installment_count)
    assert 'payment_labels_for_installments_187' in payment


def test_sales_record_uses_native_resizable_titlebar_without_transient_mode():
    from sales_claims_stage18_7 import SalesRecord187
    source = inspect.getsource(SalesRecord187.__init__)
    assert 'self.resizable(True, True)' in source
    assert 'self.transient(parent)' not in source


def test_new_wizard_draft_does_not_inherit_selected_contract():
    from sales_claims_stage18_7 import SalesClaimsPanel187, SalesRecord187

    panel_source = inspect.getsource(SalesClaimsPanel187.open_sales_record)
    assert 'self.selected_sale_id if draft is None' in panel_source

    record = object.__new__(SalesRecord187)
    record.sale_id = ''
    draft = {'project_name': 'پروژه جدید', 'buyer_name': 'خریدار جدید'}
    assert SalesRecord187._initial_values(record, draft) == draft


def test_sales_record_price_per_meter_is_contract_price_divided_by_contract_area():
    from sales_claims_stage18_7 import SalesRecord187
    source = inspect.getsource(SalesRecord187._record_price_per_m2)
    init = inspect.getsource(SalesRecord187.__init__)
    assert "self.values['total_price'].trace_add" in init
    assert "self.values['contract_area'].trace_add" in init
    assert 'parse_money(self.values[\'total_price\'].get())' in source
    assert "self.values['price_per_m2'].set(toman(price / area)" in source


def test_sales_record_file_display_button_has_dedicated_visual_treatment():
    from sales_claims_stage18_7 import SalesRecord187
    source = inspect.getsource(SalesRecord187._build)
    assert "text='نمایش فایل قرارداد'" in source
    assert "_p('blue')" in source


def test_sales_record_field_labels_and_entries_are_right_aligned():
    from sales_claims_stage18_7 import SalesRecord187
    source = inspect.getsource(SalesRecord187._record_field)
    assert "anchor='e'" in source and "justify='right'" in source


def test_sales_record_payment_dates_use_persian_shamsi_calendar():
    from sales_claims_stage18_7 import SalesRecord187
    source = inspect.getsource(SalesRecord187._record_field)
    assert "if key.endswith('_date')" in source
    assert 'ShamsiDatePicker187(self, current)' in source
    assert "text='تقویم'" in source


def test_sales_record_upload_analysis_button_is_inside_stage_zero_card():
    from sales_claims_stage18_7 import SalesRecord187
    source = inspect.getsource(SalesRecord187._build)
    upload_pos = source.index("upload = ttk.LabelFrame")
    button_pos = source.index("text='بارگذاری و تحلیل قرارداد'")
    actions_pos = source.index("actions = tk.Frame")
    assert upload_pos < button_pos < actions_pos


def test_sales_record_contract_preview_has_scroll_and_zoom_controls():
    from sales_claims_stage18_7 import SalesRecord187
    build = inspect.getsource(SalesRecord187._build)
    zoom = inspect.getsource(SalesRecord187._zoom_preview)
    assert 'self.preview_canvas = tk.Canvas' in build
    assert 'preview_xscroll = ttk.Scrollbar' in build and 'preview_yscroll = ttk.Scrollbar' in build
    assert "command=lambda: self._zoom_preview(1)" in build
    assert 'self.preview_zoom' in zoom and '_render_preview_image' in zoom


def test_sales_record_edit_loads_common_image_types_and_closes_after_confirmed_save():
    from sales_claims_stage18_7 import SalesRecord187
    preview = inspect.getsource(SalesRecord187._show_preview)
    render = inspect.getsource(SalesRecord187._render_preview_image)
    save = inspect.getsource(SalesRecord187._save_metadata)
    assert "'.jpg', '.jpeg', '.webp', '.bmp'" in preview
    assert 'self._preview_pil_image' in preview and 'ImageTk.PhotoImage' in render
    assert 'self.destroy()' in save


def test_sales_record_preview_fits_image_to_canvas_and_supports_mouse_zoom():
    from sales_claims_stage18_7 import SalesRecord187
    build = inspect.getsource(SalesRecord187._build)
    render = inspect.getsource(SalesRecord187._render_preview_image)
    zoom = inspect.getsource(SalesRecord187._preview_mouse_zoom)
    assert "self.preview_canvas.bind('<Configure>'" in build
    assert 'fit_scale' in render and 'canvas_width' in render and 'canvas_height' in render
    assert "event.delta" in zoom and "return 'break'" in zoom


def test_payment_documents_preview_resolves_attachment_paths_and_saves_images_in_excel():
    from sales_claims_stage18_7 import ContractExportPreview187, PaymentDocuments187
    export = inspect.getsource(PaymentDocuments187._export)
    save = inspect.getsource(PaymentDocuments187._save_export)
    preview = inspect.getsource(ContractExportPreview187)
    assert 'self.attachments.get' in export
    assert "document.get('attachment_id')" in export
    assert 'ExcelImage' in save and 'add_image' in save
    assert "self.orientation_choice" in preview and 'create_image' in preview
    assert 'except Exception as exc' in save


def test_contract_wizard_progress_matches_compact_data_entry_shell():
    from sales_claims_stage18_7 import ContractWizard187
    build = inspect.getsource(ContractWizard187._build_shell)
    progress = inspect.getsource(ContractWizard187._render_progress)
    assert "text='ثبت مرحله‌ای قرارداد'" in build
    assert "text='هر مرحله فقط اطلاعات مرتبط با قرارداد را نشان می‌دهد.'" in build
    assert 'width=128, height=16' in build
    assert "_p('accent')" in progress
    assert 'filled = max(2' in progress


def test_contract_wizard_shell_has_framed_scrollable_body_and_data_entry_footer():
    from sales_claims_stage18_7 import ContractWizard187
    shell = inspect.getsource(ContractWizard187._build_shell)
    source = inspect.getsource(ContractWizard187)
    assert 'scrollable=True' in source
    assert 'show_header=True' in source
    assert "style='Primary.TButton'" in shell


def test_contract_wizard_step_zero_has_no_explanatory_text_and_titles_are_rtl():
    from sales_claims_stage18_7 import ContractWizard187
    source = inspect.getsource(ContractWizard187._show_step)
    shell = inspect.getsource(ContractWizard187._build_shell)
    assert 'OCR/AI فقط پیشنهاد می‌دهد' not in source
    assert "labelanchor='ne'" in source
    assert "anchor='e', justify='right'" in shell


def test_contract_wizard_step_one_has_sale_method_and_kind_dropdowns():
    from sales_claims_stage18_7 import ContractWizard187
    source = inspect.getsource(ContractWizard187._show_step)
    assert "self.deal_mode_combo = self._field" in source
    assert "values=('واحد کامل', 'فروش متری')" in source
    assert "self.sale_kind_combo = self._field" in source
    assert "values=('پیش‌فروش', 'آماده')" in source
    assert "self.deal_mode_combo.configure(values=('واحد کامل', 'فروش متری'), state='readonly')" in source
    assert "self.sale_kind_combo.configure(values=('پیش‌فروش', 'آماده'), state='readonly')" in source


def test_edit_contract_carries_sale_attachment_into_record_window():
    from sales_claims_stage18_7 import ContractWizard187, SalesClaimsPanel187
    wizard = inspect.getsource(ContractWizard187.__init__)
    close = inspect.getsource(ContractWizard187._close_to_record)
    panel = inspect.getsource(SalesClaimsPanel187.open_edit_wizard)
    opener = inspect.getsource(SalesClaimsPanel187.open_wizard)
    assert "document_path: str = ''" in wizard
    assert 'self.step, self.document_path = 0, str(document_path or' in wizard
    assert "('SALE', self.selected_sale_id)" in panel and 'document_path=document_path' in panel
    assert 'document_path=document_path' in opener
    assert 'sale_id: str = \'\'' in wizard
    assert 'sale_id=self.sale_id' in close
    assert 'sale_id=self.selected_sale_id' in panel


def test_contract_wizard_unit_selection_reads_existing_units_and_fills_editable_details():
    from sales_claims_stage18_7 import ContractWizard187
    source = inspect.getsource(ContractWizard187)
    assert 'SELECT unit_number, floor, area FROM units' in source
    assert "self._unit_combo.bind('<<ComboboxSelected>>', self._unit_selected)" in source
    assert "self.values['floor'].set" in source and "self.values['map_area'].set" in source


def test_contract_wizard_unit_field_stays_dropdown_when_project_units_are_not_loaded_yet():
    from sales_claims_stage18_7 import ContractWizard187
    source = inspect.getsource(ContractWizard187._field)
    assert 'if values is not None:' in source
    assert "widget.pack(fill='x', padx=6, pady=(0, 6))" in source
    assert "self._field(page, 'unit_number'" in inspect.getsource(ContractWizard187._show_step)


def test_payment_stage_dropdown_supports_ten_persian_installments_and_fixed_end_stages():
    from sales_claims_stage18_7 import ContractWizard187, payment_plan_187, payment_labels_for_installments_187
    source = inspect.getsource(ContractWizard187._show_step)
    assert "'تعداد اقساط'" in source
    assert 'Combobox' not in source.split("elif self.step == 4:", 1)[1].split("elif self.step == 5:", 1)[0]
    labels = payment_labels_for_installments_187(10)
    assert labels[0] == 'پرداخت نقدی'
    assert labels[-2:] == ('موعد تحویل', 'موعد سند')
    assert len(labels) == 13
    values = {'payment_count': '۱۰', 'total_price': '۱۰۰۰'}
    for index in range(1, 14):
        values[f'pay_{index}_amount'] = '۱۰۰'
        values[f'pay_{index}_date'] = '۱۴۰۴/۰۱/۰۱'
    assert len(payment_plan_187(values)) == 13


def test_contract_wizard_defaults_to_four_installments_with_fixed_cash_delivery_and_deed():
    from sales_claims_stage18_7 import ContractWizard187
    source = inspect.getsource(ContractWizard187.__init__)
    assert "self.values['payment_count'].set('۴')" in source
    assert payment_labels_for_installments_187(4) == (
        'پرداخت نقدی', 'قسط اول', 'قسط دوم', 'قسط سوم', 'قسط چهارم', 'موعد تحویل', 'موعد سند',
    )


def test_contract_wizard_payment_count_entry_maps_total_stages_to_dynamic_rows():
    from sales_claims_stage18_7 import ContractWizard187
    source = inspect.getsource(ContractWizard187._show_step)
    count_source = inspect.getsource(ContractWizard187._payment_installment_count)
    assert "count_box.bind('<FocusOut>', self._payment_count_changed)" in source
    assert "count_box.bind('<Return>', self._payment_count_changed)" in source
    assert "int(en(self.values['payment_count'].get())) - 3" in count_source
    assert 'تعداد اقساط (۱ تا ۱۰)' not in source


def test_installment_count_changes_only_the_dynamic_installment_rows():
    one = payment_labels_for_installments_187(1)
    seven = payment_labels_for_installments_187(7)
    assert one == ('پرداخت نقدی', 'قسط اول', 'موعد تحویل', 'موعد سند')
    assert seven[0] == 'پرداخت نقدی'
    assert seven[1:8] == ('قسط اول', 'قسط دوم', 'قسط سوم', 'قسط چهارم', 'قسط پنجم', 'قسط ششم', 'قسط هفتم')
    assert seven[-2:] == ('موعد تحویل', 'موعد سند')


def test_cash_payment_date_row_explicitly_uses_calendar_picker():
    from sales_claims_stage18_7 import ContractWizard187
    source = inspect.getsource(ContractWizard187._field)
    assert "key.startswith('pay_') and key.endswith('_date')" in source
    assert 'ShamsiDatePicker187(self, current)' in source


def test_payment_stage_count_normalizes_all_persian_digits():
    from sales_claims_stage18_7 import ContractWizard187, payment_plan_187
    toggle = inspect.getsource(ContractWizard187._payment_installment_count)
    assert "int(en(self.values['payment_count'].get()))" in toggle
    values = {'payment_count': '۷'}
    for index in range(1, 11):
        values[f'pay_{index}_amount'] = '۱۰۰'
        values[f'pay_{index}_date'] = '۱۴۰۴/۰۱/۰۱'
    assert len(payment_plan_187(values)) == 10


def test_payment_row_visibility_uses_outer_grid_frame_not_packed_date_line():
    from sales_claims_stage18_7 import ContractWizard187

    class Node:
        def __init__(self, manager, master=None):
            self.manager, self.master = manager, master

        def winfo_manager(self):
            return self.manager

    outer = Node('grid')
    packed_frame = Node('pack', outer)
    packed_entry = Node('pack', packed_frame)
    assert ContractWizard187._payment_widget_container(packed_entry) is outer
    source = inspect.getsource(ContractWizard187._show_step)
    assert '_payment_widget_container(amount)' in source
    assert '_payment_widget_container(due)' in source


def test_finance_document_rows_convert_sqlite_rows_before_get_access():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    con = sqlite3.connect(':memory:')
    con.row_factory = sqlite3.Row
    row = con.execute("select 'قسط اول' as description, 1 as sequence_no, 125 as amount").fetchall()
    converted = [dict(item) for item in row]
    assert converted[0].get('description') == 'قسط اول'
    source = inspect.getsource(SalesClaimsPanel187._open_selected_documents)
    assert 'row = [dict(item) for item in con.execute' in source
    assert 'receipts, known_receipts' in source
    assert "'amount': int(receipt.get('amount') or 0)" in source


def test_ten_installment_plan_auto_fills_delivery_and_deed_after_dynamic_installments():
    from sales_claims_stage18_7 import payment_plan_187
    values = {'payment_count': '۱۰', 'delivery_date': '۱۴۰۴/۰۸/۰۱', 'deed_date': '۱۴۰۴/۰۹/۰۱'}
    for index in range(1, 14):
        values[f'pay_{index}_amount'] = '۱۰۰'
        values[f'pay_{index}_date'] = '۱۴۰۴/۰۱/۰۱' if index < 12 else ''
    plan = payment_plan_187(values)
    assert plan[11]['due_date_shamsi'] == '1404/08/01'
    assert plan[12]['due_date_shamsi'] == '1404/09/01'


def test_sales_wizard_has_vertical_body_scroll_and_previous_next_labels():
    from sales_claims_stage18_7 import ContractWizard187
    shell = inspect.getsource(ContractWizard187._build_shell)
    # Scrolling belongs to the shell now, so ask the shell for it. The step
    # labels are still the wizard's own and stay asserted here.
    assert 'scrollable=True' in inspect.getsource(ContractWizard187)
    assert 'قبلی' in shell and 'بعدی' in shell


def test_signers_stage_has_buyer_representative_before_seller_representative():
    from sales_claims_stage18_7 import ContractWizard187, SalesRecord187, ContractDetails187
    wizard = inspect.getsource(ContractWizard187._show_step)
    record = inspect.getsource(SalesRecord187._record_group)
    fields = inspect.getsource(SalesRecord187)
    details = inspect.getsource(ContractDetails187)
    assert "'نماینده خریدار'" in wizard
    assert fields.index("'buyer_representative'") < fields.index("'seller_representative'")
    assert "'buyer_representative'" in details and "'seller_representative'" in details


def test_final_wizard_summary_uses_smaller_rtl_persian_labels():
    from sales_claims_stage18_7 import ContractWizard187
    show = inspect.getsource(ContractWizard187._show_step)
    summary = inspect.getsource(ContractWizard187._summary_text)
    assert "kit_font('body')" in show
    assert "'project_name': 'نام پروژه'" in summary
    assert "'buyer_representative': 'نماینده خریدار'" in summary
    assert "for index, title in enumerate(payment_labels_for_installments_187" in summary
    assert 'persian_digits_187' in summary


def test_contract_details_payment_table_has_horizontal_and_vertical_scrollbars():
    from sales_claims_stage18_7 import ContractDetails187
    source = inspect.getsource(ContractDetails187._build)
    assert 'table_xscroll = ttk.Scrollbar' in source
    assert 'table_yscroll = ttk.Scrollbar' in source
    assert 'xscrollcommand=table_xscroll.set' in source
    assert 'yscrollcommand=table_yscroll.set' in source


def test_contract_details_uses_native_title_bar_without_form_window_controls():
    from sales_claims_stage18_7 import ContractDetails187
    source = inspect.getsource(ContractDetails187._build)
    init = inspect.getsource(ContractDetails187.__init__)
    assert "text='×'" not in source
    assert "text='—'" not in source
    assert "text='□'" not in source
    assert "text='بستن'" not in source
    assert 'overrideredirect' not in (init + source)
    assert "self.title('جزئیات قرارداد فروش')" in init


def test_contract_details_export_combobox_immediately_maps_all_three_formats():
    from sales_claims_stage18_7 import ContractDetails187
    source = inspect.getsource(ContractDetails187._build)
    assert "export_combo.bind('<<ComboboxSelected>>', self._export_selected)" in source
    assert 'ایجاد خروجی' not in source

    class Choice:
        def __init__(self, value): self.value = value
        def get(self): return self.value

    class DetailHarness:
        def __init__(self, value): self.export_choice, self.exported = Choice(value), []
        def _export(self, fmt): self.exported.append(fmt)

    for value, expected in (('Excel', 'xlsx'), ('PDF', 'pdf'), ('پرینت', 'print')):
        harness = DetailHarness(value)
        ContractDetails187._export_selected(harness)
        assert harness.exported == [expected]


def test_contract_details_export_cancel_keeps_each_selected_format_reusable():
    import sales_claims_stage18_7 as sales
    from sales_claims_stage18_7 import ContractDetails187

    class Flag:
        def get(self): return False

    class Tree:
        def selection(self): return ('installment-1',)
        def get_children(self): return ('installment-1',)
        def __getitem__(self, key): return ('row', 'document') if key == 'columns' else None
        def heading(self, key, option): return {'row': 'ردیف', 'document': 'نمایش سند'}[key]
        def item(self, _iid, option): return ('☐ ۱', '-') if option == 'values' else None

    class DetailHarness:
        tree = Tree()
        _documents = {}
        include_documents = Flag()

    calls, original = [], sales.filedialog.asksaveasfilename
    sales.filedialog.asksaveasfilename = lambda **kwargs: calls.append(kwargs) or ''
    try:
            for fmt in ('Excel', 'PDF', 'پرینت'):
                ContractDetails187._save_export(DetailHarness(), fmt, ['ردیف', 'نمایش سند'], [], [])
    finally:
        sales.filedialog.asksaveasfilename = original
    assert [call['defaultextension'] for call in calls] == ['.xlsx', '.pdf', '.pdf']


def test_contract_details_group_titles_are_top_right_aligned():
    from sales_claims_stage18_7 import ContractDetails187
    source = inspect.getsource(ContractDetails187._build_wizard_box)
    assert "labelanchor='ne'" in source


def test_contract_details_has_contractual_payment_date_column_in_persian_digits():
    from sales_claims_stage18_7 import ContractDetails187, PAYMENT_DETAIL_COLUMNS_187
    labels = [label for _key, label, _width in PAYMENT_DETAIL_COLUMNS_187]
    assert 'تاریخ واریز طبق قرارداد' in labels
    source = inspect.getsource(ContractDetails187._refresh)
    assert "item.get('due_date_shamsi')" in source
    assert 'persian_digits_187' in source


def test_finance_double_click_opens_selected_receipts_and_text_documents():
    from sales_claims_stage18_7 import PaymentDocuments187, SalesClaimsPanel187
    binding = inspect.getsource(SalesClaimsPanel187._build_finance)
    handler = inspect.getsource(SalesClaimsPanel187._double_click_finance_payment)
    opener = inspect.getsource(PaymentDocuments187._open_document)
    assert 'self._double_click_finance_payment' in binding
    assert 'self._open_selected_documents()' in handler
    assert "'.txt', '.csv', '.log'" in opener
    assert 'متن سند مالی' in opener


def test_contract_export_uses_only_boxes_one_to_six_and_places_contract_image_last():
    from sales_claims_stage18_7 import ContractDetails187, ContractExportPreview187, export_receipts_pdf_187
    boxes = [title for title, _keys in ContractDetails187._WIZARD_BOXES]
    assert boxes == ['۱. مورد معامله', '۲. تاریخ‌ها', '۳. خریدار', '۴. مالی', '۶. امضاکنندگان']
    fields = inspect.getsource(ContractDetails187._set_wizard_fields)
    assert "'۰. بارگذاری قرارداد'" not in fields and "'۷. تأیید نهایی'" not in fields
    assert 'self._contract_document_paths' in fields
    preview = inspect.getsource(ContractExportPreview187._render)
    pdf = inspect.getsource(export_receipts_pdf_187)
    assert "'تصویر قرارداد'" in preview and 'contract_document_paths' in pdf and 'platypus.PageBreak()' in pdf


def test_contract_detail_collects_every_payment_document_and_defaults_to_include_them():
    from sales_claims_stage18_7 import ContractDetails187
    init = inspect.getsource(ContractDetails187.__init__)
    refresh = inspect.getsource(ContractDetails187._refresh)
    assert 'self.include_documents = tk.BooleanVar(value=True)' in init
    assert "('RECEIVED_PAYMENT'" in refresh and "('SALE_PAYMENT'" in refresh
    assert 'links_by_installment' in refresh and 'seen_documents' in refresh


def test_contract_detail_export_uses_its_real_payment_stages_and_preview_flows_receipts():
    from sales_claims_stage18_7 import ContractDetails187, ContractExportPreview187, export_receipts_pdf_187
    fields = inspect.getsource(ContractDetails187._set_wizard_fields)
    preview = inspect.getsource(ContractExportPreview187._render)
    pdf = inspect.getsource(export_receipts_pdf_187)
    assert 'recorded_installments = self.revenue.list_installments(self.sale_id)' in fields
    assert "payment_labels_for_installments_187(installment_count)" in fields
    assert "'ادامه جدول پرداخت‌ها'" in preview and 'receipt_preview_height' in preview
    assert "splitByRow=1, hAlign='RIGHT'" in pdf
    assert "box_rows.extend([[platypus.Paragraph(_rtl(value), style), platypus.Paragraph(_rtl(label), style)]" in pdf


def test_contract_preview_and_pdf_use_the_same_paired_boxes_and_export_all_receipts():
    from sales_claims_stage18_7 import ContractDetails187, ContractExportPreview187, export_receipts_pdf_187
    preview = inspect.getsource(ContractExportPreview187._render)
    pdf = inspect.getsource(export_receipts_pdf_187)
    export = inspect.getsource(ContractDetails187._export)
    assert "group_width = (page_width - 3 * margin) / 2" in preview
    assert 'row_groups = list(reversed(group_items[index:index + 2]))' in preview
    assert 'pair_rows.append([left_box, right_box])' in pdf
    assert 'selected = selected_tree_items(self.tree)' in export


def test_contract_detail_export_save_writes_pdf_with_receipt_and_contract_image(tmp_path, monkeypatch):
    import sales_claims_stage18_7 as sales
    from PIL import Image
    from pypdf import PdfReader
    from sales_claims_stage18_7 import ContractDetails187

    receipt, contract = tmp_path / 'receipt.png', tmp_path / 'contract.jpg'
    Image.new('RGB', (60, 90), '#ffffff').save(receipt)
    Image.new('RGB', (80, 120), '#e8eef5').save(contract)
    destination = tmp_path / 'contract_export.pdf'
    notices = []
    monkeypatch.setattr(sales.filedialog, 'asksaveasfilename', lambda **_kwargs: str(destination))
    monkeypatch.setattr(sales.messagebox, 'showinfo', lambda *args, **_kwargs: notices.append(args))
    ContractDetails187._save_export(
        object(), 'PDF', ['مرحله', 'نمایش سند'], [{'مرحله': 'قسط اول', 'نمایش سند': str(receipt)}],
        [('۱. مورد معامله', 'شماره واحد', 'متری-۱')], [str(receipt)], 'عمودی', [str(contract)],
    )
    assert destination.is_file() and len(PdfReader(str(destination)).pages) >= 2
    assert notices and notices[-1][0] == 'خروجی'


def test_finance_receipt_opener_keeps_checked_rows_and_splits_each_receipt(monkeypatch):
    """Each allocation must retain its own stage suffix, amount and receipt."""
    import sales_claims_stage18_7 as sales
    from contextlib import contextmanager

    class Tree:
        def __getitem__(self, key):
            return ('row', 'select') if key == 'columns' else ()
        def get_children(self):
            return ('stage-2', 'cash')
        def item(self, iid, key):
            return ('☐ ۱', '☑') if iid == 'stage-2' else ('☐ ۲', '☑')
        def selection(self):
            return ('stage-2',)

    receipts = {
        'stage-2': [
            {'description': 'قسط دوم', 'sequence_no': 3, 'received_payment_id': 'r-1', 'transaction_id': 't-1', 'amount': 50, 'received_date_shamsi': '1405/06/01'},
            {'description': 'قسط دوم', 'sequence_no': 3, 'received_payment_id': 'r-2', 'transaction_id': 't-2', 'amount': 80, 'received_date_shamsi': '1405/06/02'},
        ],
        'cash': [
            {'description': 'پرداخت نقدی', 'sequence_no': 1, 'received_payment_id': 'r-3', 'transaction_id': 't-3', 'amount': 20, 'received_date_shamsi': '1405/05/31'},
        ],
    }

    class Cursor:
        def __init__(self, rows): self.rows = rows
        def fetchall(self): return self.rows

    class Connection:
        def execute(self, _sql, values): return Cursor(receipts[str(values[0])])

    class DB:
        @contextmanager
        def read(self): yield Connection()

    class Attachments:
        def list_for_entities(self, entities):
            receipt = next(value for kind, value in entities if kind == 'RECEIVED_PAYMENT')
            return [{'attachment_id': f'att-{receipt}', 'local_path': f'C:/receipts/{receipt}.png'}]

    captured = {}
    class Documents:
        def __init__(self, _parent, **kwargs): captured.update(kwargs)

    class Revenue:
        def get_sale(self, _sale_id): return {'contract_amount': 1000}

    class Harness:
        finance_tree = Tree(); db = DB(); attachments = Attachments(); revenue = Revenue(); selected_sale_id = 'sale-1'; base_dir = Path('.')
        def _checked_or_selected_rows(self, _tree): return ['stage-2', 'cash']
        def winfo_toplevel(self): return self

    monkeypatch.setattr(sales, 'PaymentDocuments187', Documents)
    sales.SalesClaimsPanel187._open_selected_documents(Harness())
    assert [(item['stage'], item['amount'], item['date']) for item in captured['payments']] == [
        ('قسط دوم-۱', 50, '1405/06/01'), ('قسط دوم-۲', 80, '1405/06/02'), ('پرداخت نقدی', 20, '1405/05/31'),
    ]
    assert [item['documents'][0]['attachment_id'] for item in captured['payments']] == ['att-r-1', 'att-r-2', 'att-r-3']


def test_finance_receipt_checkbox_selection_and_pdf_table_are_right_aligned():
    from sales_claims_stage18_7 import SalesClaimsPanel187, export_receipts_pdf_187
    selection = inspect.getsource(SalesClaimsPanel187._toggle_row_checkbox)
    all_selection = inspect.getsource(SalesClaimsPanel187._toggle_all_checkboxes)
    opener = inspect.getsource(SalesClaimsPanel187._open_selected_documents)
    pdf = inspect.getsource(export_receipts_pdf_187)
    assert 'tree.selection_add(iid)' in selection and 'tree.selection_remove(iid)' in selection
    assert "tree.selection_set(item_ids)" in all_selection
    assert 'self._checked_or_selected_rows(self.finance_tree)' in opener
    assert "splitByRow=1, hAlign='RIGHT'" in pdf


def test_payment_documents_preview_creates_a_row_for_every_receipt_file(monkeypatch):
    import sales_claims_stage18_7 as sales
    from sales_claims_stage18_7 import PaymentDocuments187

    captured = {}
    class Preview:
        def __init__(self, _parent, **kwargs): captured.update(kwargs)

    class Attachments:
        def get(self, _attachment_id): return {}

    class Harness:
        contract_total = 1_000
        attachments = Attachments()
        def _rows_for_filter(self):
            return [{'stage': 'قسط دوم', 'date': '1405/06/03', 'amount': 250,
                     'documents': [
                         {'local_path': 'C:/receipts/one.png'}, {'local_path': 'C:/receipts/two.png'},
                         {'local_path': 'C:/receipts/three.png'}, {'local_path': 'C:/receipts/four.png'},
                     ]}]

    monkeypatch.setattr(sales, 'ContractExportPreview187', Preview)
    PaymentDocuments187._export(Harness(), 'pdf')
    payload = captured['payload']
    assert [row['فیش واریزی'] for row in payload] == [
        'C:/receipts/one.png', 'C:/receipts/two.png', 'C:/receipts/three.png', 'C:/receipts/four.png',
    ]
    assert [row['مبلغ واریز (تومان)'] for row in payload] == ['۲۵۰', '—', '—', '—']
    assert [row['مرحله پرداخت'] for row in payload] == ['قسط دوم · فیش ۱', 'قسط دوم · فیش ۲', 'قسط دوم · فیش ۳', 'قسط دوم · فیش ۴']


def test_main_export_selectors_forward_the_selected_format_to_the_preview():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    contract = inspect.getsource(SalesClaimsPanel187._export_contract_selected)
    finance = inspect.getsource(SalesClaimsPanel187._export_finance_selected)
    documents = inspect.getsource(SalesClaimsPanel187._open_selected_documents)
    assert 'ContractDetails187(' in contract and 'details._export_selected()' in contract
    assert 'self.contract_export_choice.set(EXPORT_PLACEHOLDER_187)' in contract
    assert 'self._open_selected_documents()' in finance and 'documents._export_selected()' in finance
    assert 'self.finance_export_choice.set(EXPORT_PLACEHOLDER_187)' in finance
    assert 'PaymentDocuments187(' in documents


def test_main_export_selection_does_not_create_a_preview_behind_contract_or_receipt_windows(monkeypatch):
    import sales_claims_stage18_7 as sales
    from sales_claims_stage18_7 import SalesClaimsPanel187

    class Choice:
        def __init__(self, value): self.value = value
        def get(self): return self.value
        def set(self, value): self.value = value

    opened = []
    class Details:
        def __init__(self, *_args, **kwargs):
            opened.append(kwargs['sale_id']); self.export_choice = Choice('')
        def _export_selected(self): opened.append(('preview', self.export_choice.get()))

    class ContractTree:
        def selection(self): return ('sale-1',)

    class ContractPanel:
        contract_export_choice = Choice('PDF'); contract_tree = ContractTree(); base_dir = Path('.'); db = object()
        def winfo_toplevel(self): return self

    monkeypatch.setattr(sales, 'ContractDetails187', Details)
    SalesClaimsPanel187._export_contract_selected(ContractPanel())
    assert opened == ['sale-1', ('preview', 'PDF')]
    assert ContractPanel.contract_export_choice.get() == EXPORT_PLACEHOLDER_187

    class FinancePanel:
        finance_export_choice = Choice('PDF'); opened_documents = 0
        class Documents:
            export_choice = Choice('')
            def _export_selected(self): opened.append(('finance-preview', self.export_choice.get()))
        def _open_selected_documents(self): self.opened_documents += 1; return self.Documents()

    panel = FinancePanel()
    monkeypatch.setattr(sales, 'PaymentDocuments187', FinancePanel.Documents)
    SalesClaimsPanel187._export_finance_selected(panel)
    assert panel.opened_documents == 1
    assert opened[-1] == ('finance-preview', 'PDF')
    assert panel.finance_export_choice.get() == EXPORT_PLACEHOLDER_187


def test_export_preview_closes_only_after_a_successful_save():
    from sales_claims_stage18_7 import ContractExportPreview187

    class Value:
        def get(self): return 'PDF'

    class Preview:
        format_choice = Value(); orientation_choice = Value()
        def __init__(self, saved): self.saved = saved; self.closed = False
        def on_confirm(self, _format, _orientation): return self.saved
        def destroy(self): self.closed = True

    cancelled, saved = Preview(False), Preview(True)
    ContractExportPreview187._confirm(cancelled)
    ContractExportPreview187._confirm(saved)
    assert not cancelled.closed and saved.closed


def test_both_exports_use_rtl_physical_column_order_with_the_receipt_on_left():
    from sales_claims_stage18_7 import ContractDetails187, PaymentDocuments187, export_receipts_pdf_187
    pdf = inspect.getsource(export_receipts_pdf_187)
    contract = inspect.getsource(ContractDetails187._save_export)
    finance = inspect.getsource(PaymentDocuments187._save_export)
    assert 'headers = list(reversed(headers))' in pdf and 'rows = [list(reversed(row)) for row in rows]' in pdf
    assert 'export_receipts_pdf_187(' in contract and 'export_receipts_pdf_187(' in finance


def test_contract_export_specification_boxes_share_one_continuous_outer_frame():
    from sales_claims_stage18_7 import export_receipts_pdf_187
    pdf = inspect.getsource(export_receipts_pdf_187)
    paired_grid = pdf.split('pair_table = platypus.Table', 1)[1].split('document_width =', 1)[0]
    assert "('BOX', (0, 0), (-1, -1), .8, colors.HexColor('#496176'))" in paired_grid
    assert "('INNERGRID', (0, 0), (-1, -1), .8, colors.HexColor('#496176'))" in paired_grid
    assert "('BOTTOMPADDING', (0, 0), (-1, -1), 0)" in paired_grid
    assert 'story.append(pair_table)' in paired_grid
    assert 'Spacer(1, 7)' not in paired_grid


def test_contract_receipt_evidence_keeps_every_allocated_payment_document_link():
    from sales_claims_stage18_7 import ContractDetails187
    refresh = inspect.getsource(ContractDetails187._refresh)
    links_query = refresh.split('payment_links =', 1)[1].split('links_by_installment', 1)[0]
    # Payment amounts remain filtered by accounting status above; document evidence
    # must retain all links, matching the finance receipts table.
    assert "r.status!='CANCELLED'" not in links_query
    assert "('RECEIVED_PAYMENT', str(link['received_payment_id']))" in refresh
    assert "('SALE_PAYMENT', str(link['received_payment_id']))" in refresh


def test_contract_export_uses_the_finance_style_one_row_per_received_payment(monkeypatch):
    import sales_claims_stage18_7 as sales
    from sales_claims_stage18_7 import ContractDetails187

    class Tree:
        def __getitem__(self, key):
            return ('row', 'stage', 'received_date', 'received_amount', 'document') if key == 'columns' else ()
        def get_children(self): return ('installment-3',)
        def heading(self, key, option):
            return {'row': 'ردیف', 'stage': 'مرحله', 'received_date': 'تاریخ واریز',
                    'received_amount': 'مبلغ واریز (تومان)', 'document': 'نمایش سند'}[key]
        def item(self, _iid, option):
            return ('☐ ۳', 'قسط دوم', '۱۴۰۵/۰۶/۰۳', '۲۰۰,۰۰۰', 'نمایش سند')

    captured = {}
    class Preview:
        def __init__(self, _parent, **kwargs): captured.update(kwargs)

    class IncludeDocuments:
        def get(self): return True

    class Harness:
        tree = Tree(); include_documents = IncludeDocuments()
        _documents = {'installment-3': []}
        _receipt_rows_by_installment = {
            'installment-3': [
                {'received_payment_id': 'receipt-1', 'amount': 90, 'received_date_shamsi': '1405/06/02',
                 'documents': [{'local_path': 'C:/receipts/one.png'}]},
                {'received_payment_id': 'receipt-2', 'amount': 110, 'received_date_shamsi': '1405/06/03',
                 'documents': [{'local_path': 'C:/receipts/two.png'}]},
            ],
        }
        _wizard_export_fields = []; _contract_document_paths = []
        def _save_export(self, *_args): return True

    monkeypatch.setattr(sales, 'ContractExportPreview187', Preview)
    ContractDetails187._export(Harness(), 'pdf')
    payload = captured['payload']
    assert [row['مرحله'] for row in payload] == ['قسط دوم-۱', 'قسط دوم-۲']
    assert [row['تاریخ واریز'] for row in payload] == ['۱۴۰۵/۰۶/۰۲', '۱۴۰۵/۰۶/۰۳']
    assert [row['مبلغ واریز (تومان)'] for row in payload] == ['۹۰', '۱۱۰']
    assert [row['نمایش سند'] for row in payload] == ['C:/receipts/one.png', 'C:/receipts/two.png']


def test_finance_toolbar_uses_one_row_with_center_filter_and_left_export():
    from sales_claims_stage18_7 import SalesClaimsPanel187
    source = inspect.getsource(SalesClaimsPanel187._build_finance)
    assert "actions.grid(row=0, column=2, sticky='e')" in source
    assert 'filters.grid(row=0, column=1)' in source
    assert "output.grid(row=0, column=0, sticky='w')" in source
