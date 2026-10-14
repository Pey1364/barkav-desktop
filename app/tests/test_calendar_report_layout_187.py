import json
from datetime import date, timedelta
from types import SimpleNamespace
import pytest
from calendar_report_tables_187 import (clean_report_description, report_table,
    prepare_answer_records, parse_grounded_answer)
from financial_calendar_stage18_7 import daily_report_rows_187


def event(day, title, identifier='A', details='', **meta):
    return SimpleNamespace(kind='DAILY_REPORT', due_date=day.isoformat(), title=title,
        details=details, source_id=identifier, phase='اسکلت', metadata=meta)


@pytest.mark.parametrize('source', [
    'گزارش روزانه ۲۸ شهریور — تیغه‌چینی',
    'گزارش روزانه 28 شهریور: تیغه‌چینی',
    'گزارش روزانه ۲۸ شهریور ۱۴۰۵ — تیغه‌چینی',
    'گزارش روزانه شنبه ۱۴۰۵/۰۶/۲۸ — تیغه‌چینی',
    'گزارش هفتگی: تیغه‌چینی', 'گزارش ماهانه: تیغه‌چینی',
    'تعداد دو ردیف گزارش روزانه ثبت شد. تیغه‌چینی',
    'تعداد 11 ردیف گزارش روزانه ثبت شد\nتیغه‌چینی',
    'تعداد ۲ ردیف ثبت شده است؛ تیغه‌چینی',
    '۲ ردیف ثبت شد؛ تیغه‌چینی',
])
def test_cleanup_removes_boilerplate_but_keeps_activity(source):
    assert clean_report_description(source) == 'تیغه‌چینی'


def test_real_count_and_newlines_are_preserved():
    source = '۲ ردیف وال‌پست اجرا شد\nگزارش روزانه ۲۸ شهریور — تیغه‌چینی'
    assert clean_report_description(source) == '۲ ردیف وال‌پست اجرا شد\nتیغه‌چینی'


def test_summary_only_title_falls_back_to_recorded_details():
    day = date(2026, 9, 19)
    rows = daily_report_rows_187([event(day, 'تعداد دو ردیف گزارش روزانه ثبت شد',
        details='گزارش روزانه ۲۸ شهریور\nتیغه‌چینی\nوال‌پست')], day, day)
    assert {row['شرح گزارش'] for row in rows} == {'تیغه‌چینی', 'وال‌پست'}
    assert all(row['_source_id'] == 'A' for row in rows)



def test_multiline_daily_fallback_does_not_repeat_each_activity():
    day = date(2026, 9, 19)
    rows = daily_report_rows_187([event(day, 'تعداد دو ردیف گزارش روزانه ثبت شد',
        details='گزارش روزانه ۲۸ شهریور\nتیغه‌چینی\nوال‌پست')], day, day, deduplicate=False)
    assert rows[0]['شرح گزارش'] == 'تیغه‌چینی\nوال‌پست'


def test_empty_summary_does_not_show_as_work():
    day = date(2026, 9, 19)
    rows = daily_report_rows_187([event(day, 'تعداد دو ردیف گزارش روزانه ثبت شد')], day, day, deduplicate=False)
    headers, display = report_table(rows)
    assert headers[:3] == ['ردیف', 'تاریخ', 'شرح گزارش']
    assert 'روز هفته' not in headers and display[0]['شرح گزارش'] == 'اطلاعات ثبت نشده'
    assert display[0]['تاریخ'] == 'شنبه ۱۴۰۵/۰۶/۲۸'


@pytest.mark.parametrize('end', [date(2026, 9, 25), date(2026, 10, 18)])
def test_week_month_one_activity_one_row_unique_days(end):
    first = date(2026, 9, 1)
    third = first + timedelta(days=3)
    sources = [event(first, 'گزارش روزانه ۱۰ شهریور — روزهای تعطیل', 'A'),
               event(first, 'روزهای تعطیل', 'B'), event(third, 'روزهای تعطیل', 'C')]
    rows = daily_report_rows_187(sources, first, end)
    headers, display = report_table(rows, periodic=True)
    assert headers[:4] == ['ردیف', 'شرح گزارش', 'تاریخ', 'تعداد روز']
    assert 'روز هفته' not in headers and 'تاریخ ثبت' not in headers
    assert len(display) == 1 and display[0]['شرح گزارش'] == 'روزهای تعطیل'
    assert display[0]['تعداد روز'] == '۲ روز'
    assert display[0]['تاریخ'] == 'سه‌شنبه ۱۴۰۵/۰۶/۱۰\nجمعه ۱۴۰۵/۰۶/۱۳'
    assert set(rows[0]['_source_ids']) == {'A', 'B', 'C'}


def test_status_and_spelling_variants_show_canonical_activity_once():
    first = date(2026, 9, 19)
    rows = daily_report_rows_187([event(first, 'شروع تیغه‌چینی', 'A'),
        event(first + timedelta(days=1), 'تکمیل عملیات تیغه چینی', 'B')], first, first + timedelta(days=1))
    assert len(rows) == 1 and rows[0]['شرح گزارش'] == 'تیغه‌چینی'
    assert len(rows[0]['_activities']) == 2


def test_ai_cleanup_combines_weekday_and_retains_registration_label_in_one_column():
    records = prepare_answer_records([{'تاریخ': '1405/06/28', 'تاریخ ثبت': '1405/06/29',
        'شرح': 'گزارش روزانه ۲۸ شهریور — تیغه‌چینی', 'جزئیات': 'تعداد دو ردیف گزارش روزانه ثبت شد'}])
    headers, rows = parse_grounded_answer(json.dumps({'columns': ['روز هفته', 'تاریخ ثبت', 'شرح', 'جزئیات'], 'record_ids': ['R1']}), records)
    assert [field for field in headers if 'تاریخ' in field] == ['تاریخ']
    assert 'روز هفته' not in headers and rows[0]['جزئیات'] == ''
    assert rows[0]['شرح'] == 'تیغه‌چینی'
    assert rows[0]['تاریخ'] == 'شنبه ۱۴۰۵/۰۶/۲۸\nتاریخ ثبت: یکشنبه ۱۴۰۵/۰۶/۲۹'


@pytest.mark.parametrize('label', ['روزانه', 'هفتگی', 'ماهانه'])
def test_gui_preview_ai_window_and_copy_share_the_visible_columns(label, monkeypatch):
    import tkinter as tk
    import financial_calendar_stage18_7 as module
    from ui_stage18_7 import style_ttk_187
    root = tk.Tk(); root.withdraw(); style_ttk_187(root)
    summary = result = None
    first = date(2026, 9, 19)
    rows = daily_report_rows_187([event(first, 'گزارش روزانه ۲۸ شهریور — تیغه‌چینی')], first, first,
        deduplicate=label != 'روزانه')
    expected_headers, expected_rows = report_table(rows, periodic=label != 'روزانه')
    owner = SimpleNamespace(service=SimpleNamespace(db=None), events=[], _parent=None)
    try:
        summary = module.DailyReportSummaryDialog187(root, owner=owner, label=label,
            start='1405/06/28', end='1405/06/28', rows=rows)
        root.update()
        visible = expected_headers[:-1]
        assert list(summary.tree['columns']) == visible
        assert list(summary.tree['displaycolumns']) == list(reversed(visible))
        values = summary.tree.item('0', 'values')
        assert values[1:] == tuple(expected_rows[0][key] for key in visible[1:])
        # The row selector is physically rightmost after RTL column reversal.
        monkeypatch.setattr(summary.tree, 'identify_row', lambda y: '0')
        monkeypatch.setattr(summary.tree, 'identify_column', lambda x: f'#{len(visible)}')
        assert summary._row_click_187(SimpleNamespace(x=0, y=0)) == 'break'
        assert summary.checked == {'0'}
        summary._row_click_187(SimpleNamespace(x=0, y=0))
        assert summary.checked == set()
        summary.tree.selection_set('0')
        summary._copy_187()
        clip = summary.clipboard_get()
        assert clip.splitlines()[0].split('\t') == visible
        assert 'گزارش روزانه ۲۸' not in clip
        captured = {}
        monkeypatch.setattr(module, 'show_export_preview_187', lambda *args, **kwargs: captured.update(kwargs))
        # This test covers presentation; semantic-provider integration has its own tests.
        summary._semantic_cache_key187 = summary._semantic_key187()
        summary.export_choice.set('PDF'); summary.export_current()
        assert captured['headers'] == expected_headers and captured['rows'] == expected_rows
        result = module.ProjectAIResultDialog187(root, service=owner.service, model='آزمایشی',
            text='', audience='کارفرما', start='1405/06/28', end='1405/06/28', label=label, report_rows=rows)
        assert result._table_data187() == (expected_headers, expected_rows)
    finally:
        if result is not None: result.destroy()
        if summary is not None: summary.destroy()
        root.destroy()


def test_actual_pdf_and_excel_use_cleaned_periodic_table(tmp_path):
    from report_document_stage18_7 import build_report_document
    from pypdf import PdfReader
    from openpyxl import load_workbook
    day = date(2026, 9, 19)
    rows = daily_report_rows_187([event(day, 'تعداد دو ردیف گزارش روزانه ثبت شد',
        details='گزارش روزانه ۲۸ شهریور — تیغه‌چینی')], day, day)
    headers, display = report_table(rows, periodic=True, documents=False)
    document = build_report_document(headers, display, [], 'گزارش هفتگی', progress=30, project_name='نمونه')
    pdf = tmp_path / 'week.pdf'; document.save(pdf, 'PDF')
    assert pdf.read_bytes() == document.pdf and PdfReader(pdf).pages
    excel = tmp_path / 'week.xlsx'; document.save(excel, 'Excel')
    book = load_workbook(excel)
    cells = [str(cell.value or '') for sheet in book for row in sheet for cell in row]
    assert not any('ردیف گزارش روزانه ثبت شد' in cell or 'گزارش روزانه ۲۸' in cell for cell in cells)
    assert any('۱ روز' in cell for cell in cells)


@pytest.mark.parametrize('source', ['شنبه تعطیل بود', 'سه‌شنبه بتن‌ریزی انجام شد'])
def test_weekday_in_actual_activity_is_not_treated_as_a_date_heading(source):
    assert clean_report_description(source) == source
