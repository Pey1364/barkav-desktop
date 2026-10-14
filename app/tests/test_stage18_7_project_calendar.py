from __future__ import annotations

from datetime import date
from pathlib import Path

import financial_calendar_stage18_7 as calendar


def test_project_calendar_has_required_rtl_columns_and_labels():
    assert calendar.EVENT_LABELS['CHEQUE'] == 'سررسید چک هزینه'
    assert calendar.EVENT_LABELS['RECEIVABLE'] == 'سررسید مطالبات'
    assert calendar.EVENT_LABELS['INFO'] == 'اطلاع‌رسانی'
    # «فاکتور» is a note category (note_type), distinct from the AI's own
    # document_type=INVOICE, which classifies an attached image.
    assert calendar.EVENT_LABELS['INVOICE_NOTE'] == 'فاکتور'
    assert calendar.CALENDAR_EVENT_FILTERS_187['فاکتور'] == 'INVOICE_NOTE'
    assert calendar._message_document_kind_187('INVOICE_NOTE') == 'INVOICE_NOTE'
    source = open(calendar.__file__, encoding='utf-8').read()
    for marker in (
        'پیام‌ها', 'تقویم پروژه', 'year_box', 'month_box', 'export_current',
        'وضعیت اعلان', 'تاریخ ثبت', 'تاریخ سر رسید', '<Double-1>',
        '_is_official_holiday_187',
    ):
        assert marker in source
    messages_source = source.split('class FinancialMessagesDialog187', 1)[1].split(
        'class FinancialCalendarDialog187', 1,
    )[0]
    assert 'جریان' not in messages_source
    dashboard_source = Path(calendar.__file__).with_name('dashboard_stage18_7.py').read_text(encoding='utf-8')
    assert "footer_clock_host187.bind('<Double-1>'" in dashboard_source
    assert "datetime_label_186.bind('<Double-1>'" in dashboard_source


def test_daily_report_summary_prefers_completion_and_deduplicates():
    events = [
        calendar.FinancialEvent187('2026-08-25', '1405/06/03', 'DAILY_REPORT', 'شروع اجرای اسکلت', 0, 'INFO'),
        calendar.FinancialEvent187('2026-08-26', '1405/06/04', 'DAILY_REPORT', 'ادامه اجرای اسکلت', 0, 'INFO'),
        calendar.FinancialEvent187('2026-08-27', '1405/06/05', 'DAILY_REPORT', 'تکمیل عملیات اجرای اسکلت', 0, 'INFO'),
    ]
    summary = calendar.summarize_daily_reports_187(events, date(2026, 8, 25), date(2026, 8, 27))
    assert summary == ['تکمیل عملیات اجرای اسکلت']


def test_friday_and_fixed_days_are_marked_official_holidays():
    assert calendar._is_official_holiday_187(1405, 1, 1)
    # 1405/06/20 is Friday in the Persian calendar.
    assert calendar._is_official_holiday_187(1405, 6, 20)


def test_message_alert_defaults_cover_financial_due_items_only():
    assert calendar._alert_enabled_187('CHEQUE', {}) is True
    assert calendar._alert_enabled_187('RECEIVABLE', {}) is True
    assert calendar._alert_enabled_187('REMINDER', {}) is True
    assert calendar._alert_enabled_187('DOCUMENT', {}) is False
    assert calendar._alert_enabled_187('INFO', {}) is False

def test_reminder_startup_alert_waits_for_its_reminder_date():
    reminder = calendar.FinancialEvent187(
        '2026-09-14', '1405/06/23', 'REMINDER', 'پیگیری قرارداد', 0, 'INFO',
    )
    enabled = {calendar._event_alert_key_187(reminder): True}
    assert calendar.is_startup_alert_due_187(reminder, date(2026, 9, 13), enabled) is False
    assert calendar.is_startup_alert_due_187(reminder, date(2026, 9, 14), enabled) is True


def test_hidden_startup_message_stays_hidden_but_a_new_message_is_unread(monkeypatch):
    original = calendar.FinancialEvent187(
        '2026-09-14', '1405/06/23', 'LOAN', 'قسط اول', 120, 'OUT', source_id='loan-1',
    )
    newer = calendar.FinancialEvent187(
        '2026-09-14', '1405/06/23', 'LOAN', 'قسط دوم', 120, 'OUT', source_id='loan-2',
    )
    hidden = {calendar._message_state_key_187(original)}
    assert calendar.is_startup_alert_due_187(original, hidden_events=hidden) is False
    assert calendar.is_startup_alert_due_187(newer, hidden_events=hidden) is True

    def saved(setting_key):
        return hidden if setting_key == calendar.STARTUP_HIDDEN_EVENTS_KEY_187 else set()

    monkeypatch.setattr(calendar, '_saved_message_keys_187', saved)
    assert calendar.unread_message_events_187([original, newer]) == [newer]

def test_message_row_alerts_default_on_for_financial_due_items_and_due_dates_are_limited():
    loan = calendar.FinancialEvent187('2026-09-14', '1405/06/23', 'LOAN', 'قسط', 0, 'OUT')
    receivable = calendar.FinancialEvent187('2026-09-14', '1405/06/23', 'RECEIVABLE', 'قسط فروش', 0, 'IN')
    reminder = calendar.FinancialEvent187('2026-09-14', '1405/06/23', 'REMINDER', 'پیگیری', 0, 'INFO')
    note = calendar.FinancialEvent187('2026-09-14', '1405/06/23', 'NOTE', 'یادداشت', 0, 'INFO')
    assert calendar._event_alert_enabled_187(loan, {}) is True
    assert calendar._event_alert_enabled_187(receivable, {}) is True
    assert calendar._event_alert_enabled_187(reminder, {}) is False
    assert calendar._display_due_date_187(reminder) == '۱۴۰۵/۰۶/۲۳'
    assert calendar._display_due_date_187(note) == '—'

def test_calendar_kind_and_shamsi_range_filters_are_inclusive():
    events = [
        calendar.FinancialEvent187('2026-08-25', '1405/06/03', 'DAILY_REPORT', 'گزارش اول', 0, 'INFO'),
        calendar.FinancialEvent187('2026-08-26', '1405/06/04', 'NOTE', 'یادداشت', 0, 'INFO'),
        calendar.FinancialEvent187('2026-08-27', '1405/06/05', 'DAILY_REPORT', 'گزارش دوم', 0, 'INFO'),
    ]
    assert [item.title for item in calendar.filter_calendar_events_187(events, 'گزارش روزانه', '۱۴۰۵/۰۶/۰۳', '۱۴۰۵/۰۶/۰۵')] == ['گزارش اول', 'گزارش دوم']
    assert [item.title for item in calendar.filter_calendar_events_187(events, 'همه', '1405/06/04', '1405/06/04')] == ['یادداشت']
def test_messages_keep_stripes_and_expose_document_preview_controls():
    source = Path(calendar.__file__).read_text(encoding='utf-8')
    messages = source.split('class FinancialMessagesDialog187', 1)[1].split('class FinancialCalendarDialog187', 1)[0]
    assert 'self.search_entry = ttk.Entry' in messages
    assert "self.search_entry.bind('<Return>'" in messages
    assert 'displaycolumns=message_columns' in messages
    assert "('document', 'نمایش سند'" in messages
    assert "tags=(stripe, event.kind)" in messages
    assert "if key == 'document'" in messages
    assert "return 'break'" in messages
    assert "self.tree.column('#0', width=0" in messages


def test_startup_popup_has_per_message_hide_controls_and_dashboard_clears_badge_on_open():
    source = Path(calendar.__file__).read_text(encoding='utf-8')
    messages = source.split('class FinancialMessagesDialog187', 1)[1].split(
        'class FinancialCalendarDialog187', 1,
    )[0]
    popup = source.split('class StartupMessagesPopup187', 1)[1].split(
        'class FinancialMessagesDialog187', 1,
    )[0]
    assert "('hide', 'عدم نمایش مجدد'" in popup
    assert 'def _toggle_hide_187' in popup
    assert 'def _hide_selected_187' in popup
    assert 'hide_startup_events_187(selected)' in popup
    dashboard = Path(calendar.__file__).with_name('dashboard_stage18_7.py').read_text(encoding='utf-8')
    assert 'command=self._open_messages_187' in dashboard
    assert 'on_messages_opened=self._refresh_message_count_187' in dashboard
    assert 'unread_message_events_187(upcoming_events_187(SERVICE, 30))' in dashboard
    assert "(('تا تاریخ', end_var), ('از تاریخ', start_var))" in source
    assert "selectmode='extended'" in messages
    assert "self.tree.column('#0', width=0" in messages


def test_calendar_has_a_real_post_mapping_reload_callback():
    source = Path(calendar.__file__).read_text(encoding='utf-8')
    calendar_source = source.split('class FinancialCalendarDialog187', 1)[1]
    assert 'def _reload_events_187(self)' in calendar_source
    assert "Project calendar data reload failed" in calendar_source


def test_calendar_details_mirror_messages_and_selection_uses_cached_grid():
    source = Path(calendar.__file__).read_text(encoding='utf-8')
    calendar_source = source.split('class FinancialCalendarDialog187', 1)[1]
    assert 'self.message_events = message_events_187(service, 30)' in calendar_source
    assert 'rows = self._filtered_rows_187(self.message_events)' in calendar_source
    assert 'def _round_calendar_grid_187' in calendar_source
    assert 'self.after_idle(round_cell)' not in calendar_source
    assert 'xscrollcommand=details_hbar.set' in calendar_source


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def test_message_search_ignores_placeholder_and_matches_amount_and_alert():
    dialog = object.__new__(calendar.FinancialMessagesDialog187)
    dialog.search_placeholder187 = 'جستجو'
    dialog.search_var = _Value('۱۲۰')
    dialog.kind_filter_var = _Value('همه')
    dialog.alert_filter_var = _Value('همه')
    dialog.due_filter_var = _Value('همه')
    dialog.alert_preferences = {}
    dialog.events = [calendar.FinancialEvent187(
        '2026-08-25', '1405/06/03', 'INFO', 'گزارش', 120, 'INFO',
    )]
    assert dialog._visible_event_indices() == [0]
    dialog.search_var = _Value('جستجو')
    assert dialog._search_query_187() == ''


def test_message_export_uses_checked_visible_rows_or_all_by_default():
    assert calendar.message_export_indices_187([5, 7, 9], set()) == [5, 7, 9]
    assert calendar.message_export_indices_187([5, 7, 9], {7, 8}) == [7]


def test_daily_report_rows_preserve_columns_and_weekly_deduplication():
    events = [
        calendar.FinancialEvent187(
            '2026-08-25', '1405/06/03', 'DAILY_REPORT',
            'شروع اجرای اسکلت', 0, 'INFO', 'فاز ۱', '', True, 'doc-1',
        ),
        calendar.FinancialEvent187(
            '2026-08-26', '1405/06/04', 'DAILY_REPORT',
            'تکمیل عملیات اجرای اسکلت', 0, 'INFO', 'فاز ۱', '', True, 'doc-2',
        ),
    ]
    rows = calendar.daily_report_rows_187(
        events, date(2026, 8, 25), date(2026, 8, 26),
    )
    assert len(rows) == 1
    assert rows[0]['شرح گزارش'] == 'اجرای اسکلت'
    assert set(rows[0]['_activities']) == {'شروع اجرای اسکلت', 'تکمیل عملیات اجرای اسکلت'}
    assert len(rows[0]['تاریخ'].splitlines()) == 2
    assert rows[0]['مرحله ساخت'] == '۱'
    assert set(rows[0]['_source_ids']) == {'doc-1', 'doc-2'}
    assert rows[0]['_source_id'] == ''
    assert set(('تاریخ', 'شرح گزارش', 'مرحله ساخت', 'توضیحات')) <= rows[0].keys()
    assert len(calendar.daily_report_rows_187(
        events, date(2026, 8, 25), date(2026, 8, 26), deduplicate=False,
    )) == 2


def test_daily_report_date_in_text_moves_to_date_column_and_is_removed_from_description():
    event = calendar.FinancialEvent187(
        '2026-08-25', '1405/06/03', 'DAILY_REPORT',
        'گزارش روزانه ۱۷ شهریور ۱۴۰۵ — اجرای اسکلت', 0, 'INFO',
        'فاز ۰۴ — گزارش روزانه ۱۷ شهریور ۱۴۰۵', '', True, 'doc-date', '۰۴ — اسکلت',
    )
    # A date explicitly written in a report belongs to that execution day,
    # not the earlier registration day; a day with no report stays visible.
    missing = calendar.daily_report_rows_187(
        [event], date(2026, 8, 25), date(2026, 8, 25), deduplicate=False,
    )
    assert missing[0]['شرح گزارش'] == 'اطلاعات ثبت نشده'
    rows = calendar.daily_report_rows_187(
        [event], date(2026, 9, 8), date(2026, 9, 8), deduplicate=False,
    )
    assert rows[0]['تاریخ'] == '۱۴۰۵/۰۶/۱۷'
    assert '۱۷ شهریور' not in rows[0]['شرح گزارش']
    assert '۱۷ شهریور' not in rows[0]['توضیحات']
    assert rows[0]['مرحله ساخت'] == '۰۴ — اسکلت'


def test_daily_report_document_expands_all_entered_rows_for_export():
    events = calendar._document_events_from_rows_187([{
        'document_id': 'DOC-REPORT', 'document_type': 'DAILY_REPORT',
        'event_date_shamsi': '1405/06/20', 'description': 'تعداد دو ردیف گزارش روزانه ثبت شد',
        'raw_text': 'گزارش روزانه ۲۰ شهریور ۱۴۰۵',
        'daily_report_rows': [{'description': 'ردیف اول'}, {'description': 'ردیف دوم'}],
    }])
    assert [event.title for event in events] == ['ردیف اول', 'ردیف دوم']
