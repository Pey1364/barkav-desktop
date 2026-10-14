from __future__ import annotations

import contextlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'documents.sqlite3')

import dashboard_stage18_7 as dashboard  # noqa: E402
import financial_calendar_stage18_7 as calendar  # noqa: E402


def test_nonfinancial_document_schema_and_aliases():
    assert dashboard.v18.TITLE_TYPES['یادداشت'][:5] == [
        'تقویم کارگاهی', 'گزارش روزانه', 'داکیومنت', 'یادآوری', 'یادداشت',
    ]
    assert dashboard._canonical_document_subtype_187('یاداوری') == 'یادآوری'
    assert [field.key for field in dashboard._special_fields_187('یادداشت', 'گزارش روزانه')] == [
        'report_date_shamsi', 'report_row_count', 'report_contractor_count',
        'report_daily_wage_count', 'report_machinery', 'report_weather',
        'report_rows', 'report_images',
    ]
    assert dashboard._special_fields_187('یادداشت', 'داکیومنت')[1].kind == 'file'
    assert dashboard._special_fields_187('یادداشت', 'یادداشت')[0].values == ('فنی', 'توصیفی', 'سایر')
    # «فاکتور» here is a note category, unrelated to document_type=INVOICE
    # (the AI's own classification of an attached image).
    assert 'فاکتور' in dashboard.v18.TITLE_TYPES['یادداشت']
    assert dashboard._DOCUMENT_SUBTYPE_CODES_187['فاکتور'] == 'INVOICE_NOTE'
    assert [field.key for field in dashboard._special_fields_187('یادداشت', 'فاکتور')] == [
        'invoice_note_date_shamsi', 'description',
    ]


def test_nonfinancial_payload_is_zero_amount_and_calendar_typed():
    holder = type('Holder', (), {
        'payload': {
            'v18_title': 'یادداشت', 'v18_subtype': 'تقویم کارگاهی',
            'event_date_shamsi': '۱۴۰۵/۰۶/۲۰', 'amount': 99,
            'calendar_date_shamsi': '۱۴۰۵/۰۶/۲۱', 'description': 'بازدید کارگاهی',
        }, 'vars': {}, '_loading': False, 'manual_fields': set(),
    })()
    payload = dashboard._payload_values_187(holder, 'یادداشت', 'تقویم کارگاهی')
    assert payload['amount'] == 0
    assert payload['document_type'] == 'WORKSHOP_CALENDAR'
    assert payload['calendar_keyword'] == 'تقویم'
    assert payload['event_date_shamsi'] == '1405/06/21'

    report_holder = type('Holder', (), {
        'payload': {
            'v18_title': 'یادداشت', 'v18_subtype': 'گزارش روزانه',
            'event_date_shamsi': '1405/06/20', 'report_row_count': 3,
        }, 'vars': {}, '_loading': False, 'manual_fields': set(),
    })()
    report_payload = dashboard._payload_values_187(report_holder, 'یادداشت', 'گزارش روزانه')
    assert report_payload['report_row_count'] == 3


def test_report_rows_keep_legacy_aliases_for_editor_reload():
    assert dashboard._document_rows_187('[{"ردیف": "۲", "شرح": "بازدید"}]') == [
        {'row': '۲', 'description': 'بازدید'},
    ]


def test_calendar_reads_nonfinancial_documents_without_financial_effect():
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    connection.execute(
        'CREATE TABLE financial_documents('
        'document_type TEXT,event_date_shamsi TEXT,description TEXT,amount INTEGER,status TEXT)'
    )
    connection.execute(
        "INSERT INTO financial_documents VALUES ('REMINDER','1405/06/20','تماس با ناظر',0,'ACTIVE')"
    )
    connection.commit()
    db = type('Db', (), {'read': lambda self: contextlib.nullcontext(connection)})()
    service = type('Service', (), {
        'db': db,
        'upcoming_cheques': lambda self, days: [],
        'upcoming_buyer_installments': lambda self, days: [],
        'overdue_buyer_installments': lambda self: [],
        'upcoming_loan_installments': lambda self, days: [],
    })()
    events = calendar.collect_financial_events_187(service)
    assert len(events) == 1
    assert events[0].kind == 'REMINDER'
    assert events[0].direction == 'INFO'


def test_calendar_reads_every_nonfinancial_document_type():
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    connection.execute(
        'CREATE TABLE financial_documents('
        'document_type TEXT,event_date_shamsi TEXT,description TEXT,amount INTEGER,status TEXT)'
    )
    types = ('WORKSHOP_CALENDAR', 'DAILY_REPORT', 'DOCUMENT', 'REMINDER', 'NOTE', 'INFO', 'INVOICE_NOTE')
    connection.executemany(
        'INSERT INTO financial_documents VALUES (?, ?, ?, 0, "ACTIVE")',
        [(kind, '1405/06/20', kind, ) for kind in types],
    )
    connection.commit()
    db = type('Db', (), {'read': lambda self: contextlib.nullcontext(connection)})()
    service = type('Service', (), {
        'db': db,
        'upcoming_cheques': lambda self, days: [],
        'upcoming_buyer_installments': lambda self, days: [],
        'overdue_buyer_installments': lambda self: [],
        'upcoming_loan_installments': lambda self, days: [],
    })()
    assert {event.kind for event in calendar.collect_financial_events_187(service)} == set(types)
    assert {event.kind for event in calendar.message_events_187(service)} == set(types)




def test_message_type_aliases_keep_legacy_notes_filterable():
    assert calendar._message_document_kind_187('NOTES') == 'NOTE'
    assert calendar._message_document_kind_187('یادداشت') == 'NOTE'
    assert calendar._message_document_kind_187('NOTIFICATION') == 'INFO'
    assert calendar._message_document_kind_187('OTHER', 'یادداشت قدیمی') == 'NOTE'


def test_messages_keep_legacy_documents_when_type_or_date_is_incomplete():
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    connection.execute(
        'CREATE TABLE financial_documents('
        'document_type TEXT,event_date_shamsi TEXT,description TEXT,amount INTEGER)'
    )
    connection.execute(
        "INSERT INTO financial_documents VALUES ('OTHER','','یادداشت قدیمی',0)"
    )
    connection.commit()
    db = type('Db', (), {'read': lambda self: contextlib.nullcontext(connection)})()
    service = type('Service', (), {
        'db': db,
        'upcoming_cheques': lambda self, days: [],
        'upcoming_buyer_installments': lambda self, days: [],
        'overdue_buyer_installments': lambda self: [],
        'upcoming_loan_installments': lambda self, days: [],
    })()
    events = calendar.message_events_187(service)
    assert len(events) == 1
    assert events[0].kind == 'NOTE'
    assert events[0].title == 'یادداشت قدیمی'


def test_messages_can_use_the_same_document_provider_as_the_documents_tab():
    financial_service = type('FinancialService', (), {
        'upcoming_cheques': lambda self, days: [],
        'upcoming_buyer_installments': lambda self, days: [],
        'overdue_buyer_installments': lambda self: [],
        'upcoming_loan_installments': lambda self, days: [],
    })()
    shared_documents = type('SharedDocuments', (), {
        'list_documents': lambda self: [{
            'document_id': 'DOC-SHARED',
            'document_type': 'NOTE',
            'event_date_shamsi': '1405/06/20',
            'description': 'یادداشت مشترک تب اسناد',
            'amount': 0,
            'status': 'ACTIVE',
        }],
    })()
    events = calendar.message_events_187(
        financial_service, document_service=shared_documents,
    )
    assert [event.source_id for event in events] == ['DOC-SHARED']
    assert events[0].kind == 'NOTE'


def test_messages_fall_back_to_database_when_document_provider_is_empty():
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    connection.execute(
        'CREATE TABLE financial_documents('
        'document_type TEXT,event_date_shamsi TEXT,description TEXT,amount INTEGER,status TEXT)'
    )
    connection.execute(
        "INSERT INTO financial_documents VALUES ('NOTE','1405/06/20','یادداشت fallback',0,'ACTIVE')"
    )
    connection.commit()
    db = type('Db', (), {'read': lambda self: contextlib.nullcontext(connection)})()
    service = type('Service', (), {
        'db': db,
        'list_documents': lambda self: [],
        'upcoming_cheques': lambda self, days: [],
        'upcoming_buyer_installments': lambda self, days: [],
        'overdue_buyer_installments': lambda self: [],
        'upcoming_loan_installments': lambda self, days: [],
    })()
    events = calendar.message_events_187(service)
    assert len(events) == 1
    assert events[0].kind == 'NOTE'
    connection.close()


def test_messages_keep_documents_when_financial_source_errors():
    shared_documents = type('SharedDocuments', (), {
        'list_documents': lambda self: [{
            'document_id': 'DOC-AFTER-FINANCE-ERROR',
            'document_type': 'NOTE',
            'event_date_shamsi': '1405/06/20',
            'description': 'یادداشت باقی‌مانده',
            'amount': 0,
            'status': 'ACTIVE',
        }],
    })()
    financial_service = type('BrokenFinancialService', (), {
        'upcoming_cheques': lambda self, days: (_ for _ in ()).throw(RuntimeError('financial source unavailable')),
    })()
    events = calendar.message_events_187(financial_service, document_service=shared_documents)
    assert [event.source_id for event in events] == ['DOC-AFTER-FINANCE-ERROR']
    assert events[0].kind == 'NOTE'

def test_approved_document_is_stored_as_nonfinancial_record():
    from budget_rich_v163 import RichBudgetService

    dashboard.DB.register_telegram_message(
        chat_id=-187, message_id=987654321, raw_text='',
        content_type='test_document', message_date='2026-09-06T00:00:00', state='RECEIVED',
    )
    pending_id = dashboard.DB.create_or_replace_pending(
        telegram_chat_id=-187, telegram_message_id=987654321,
        detected_type='INFO',
        payload={
            'v18_title': 'یادداشت', 'v18_subtype': 'یادآوری',
            'event_date_shamsi': '1405/06/20',
            'reminder_date_shamsi': '1405/06/20',
            'description': 'پیگیری قرارداد', 'amount': 0,
        }, confidence=1.0, status='PENDING_REVIEW',
    )
    rich = RichBudgetService(dashboard.DB, dashboard.BASE_DIR)
    message = dashboard._approve_nonfinancial_187(
        pending_id, dashboard.DB.get_pending_item(pending_id)['payload'], rich,
    )
    assert 'یادآوری' in message
    stored = [row for row in rich.list_documents() if row['pending_id'] == pending_id]
    assert stored and stored[0]['document_type'] == 'REMINDER'
    assert stored[0]['amount'] == 0


def test_invoice_note_is_approved_and_stored_with_its_own_code():
    # «فاکتور» end to end: wizard save (_approve_nonfinancial_187) through to
    # the persisted document_type - distinct from document_type=INVOICE,
    # which is the AI's classification of an attached image, not this code.
    from budget_rich_v163 import RichBudgetService

    dashboard.DB.register_telegram_message(
        chat_id=-187, message_id=987654322, raw_text='',
        content_type='test_document', message_date='2026-09-06T00:00:00', state='RECEIVED',
    )
    pending_id = dashboard.DB.create_or_replace_pending(
        telegram_chat_id=-187, telegram_message_id=987654322,
        detected_type='INFO',
        payload={
            'v18_title': 'یادداشت', 'v18_subtype': 'فاکتور',
            'event_date_shamsi': '1405/06/20',
            'invoice_note_date_shamsi': '1405/06/20',
            'description': 'فاکتور خرید مصالح', 'amount': 0,
        }, confidence=1.0, status='PENDING_REVIEW',
    )
    rich = RichBudgetService(dashboard.DB, dashboard.BASE_DIR)
    message = dashboard._approve_nonfinancial_187(
        pending_id, dashboard.DB.get_pending_item(pending_id)['payload'], rich,
    )
    assert 'فاکتور' in message
    stored = [row for row in rich.list_documents() if row['pending_id'] == pending_id]
    assert stored and stored[0]['document_type'] == 'INVOICE_NOTE'
    assert stored[0]['amount'] == 0
