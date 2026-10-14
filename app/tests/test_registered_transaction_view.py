"""Approved records belong in the transaction view without becoming cash entries."""
import pytest
from finance_db import FinanceDB
from dashboard_service_stage9 import DashboardServiceStage9
from financial_posting import build_posting_plan
from budget_rich_v163 import RichBudgetService

@pytest.fixture
def env(tmp_path):
    db = FinanceDB(tmp_path / 'view.sqlite3')
    service = DashboardServiceStage9(db, tmp_path)
    rich = RichBudgetService(db, tmp_path)
    return db, service, rich

def seed(db, kind, **values):
    db.register_telegram_message(chat_id=-777, message_id=1, raw_text='متن مستقل',
        content_type='TEXT', message_date='2026-09-20T10:00:00')
    payload = {'detected_type': kind, 'event_date_shamsi': '1405/06/29',
        'description': 'شرح ثبت', 'amount': 100, **values}
    pid = db.create_or_replace_pending(telegram_chat_id=-777, telegram_message_id=1,
        detected_type=kind, payload=payload, status='PENDING_REVIEW')
    return pid, payload

def post(db, pid, payload):
    plan = build_posting_plan(payload=payload, raw_text='شرح ثبت',
        telegram_message_date='2026-09-20T10:00:00')
    return db.apply_financial_posting(pending_id=pid, plan=plan, source='TEST')

def test_approved_note_visible_after_refresh_without_cash_effect(env):
    db, service, _ = env
    pid, _ = seed(db, 'INFO', v18_title='یادداشت', v18_subtype='اطلاع‌رسانی', amount=0)
    assert service.list_registered_records() == []
    before = db.snapshot()
    db.update_pending(pid, status='APPROVED')
    rows = service.list_registered_records()
    assert [r['pending_id'] for r in rows] == [pid]
    assert rows[0]['transaction_id'] is None
    assert rows[0]['_sum_amount'] == 0
    assert service.list_transactions() == []
    assert db.snapshot() == before

def test_document_view_tracks_active_document(env):
    db, service, rich = env
    pid, payload = seed(db, 'DOCUMENT', amount=0)
    did = rich.add_financial_document(pid, payload)
    db.update_pending(pid, status='APPROVED')
    assert service.list_registered_records()[0]['document_id'] == did
    rich.delete_document(did)
    assert service.list_registered_records() == []
    assert db.snapshot().cash_balance == 0

@pytest.mark.parametrize('method', ['CASH', 'CHEQUE'])
def test_unpaid_and_cheque_expense_visible_once_without_cash(env, method):
    db, service, _ = env
    pid, payload = seed(db, 'EXPENSE', final_amount=100, payment_state='UNPAID',
        payment_method=method, is_cheque=(method == 'CHEQUE'),
        due_date_shamsi='1405/07/15', issue_date_shamsi='1405/06/29')
    post(db, pid, payload)
    before = db.snapshot()
    rows = service.list_registered_records()
    assert [r['pending_id'] for r in rows] == [pid]
    assert rows[0]['expense_id']
    assert rows[0]['_sum_amount'] == 0
    assert service.list_transactions() == []
    assert db.snapshot() == before
    assert before.cash_balance == 0
    db.delete_financial_posting(pending_id=pid, source='TEST')
    assert service.list_registered_records() == []

def test_paid_expense_is_not_duplicated_by_approved_source(env):
    db, service, _ = env
    pid, payload = seed(db, 'EXPENSE', final_amount=100, paid_amount=100,
        payment_state='PAID', payment_method='CASH')
    post(db, pid, payload)
    rows = service.list_registered_records()
    assert len(rows) == 1
    assert rows[0]['pending_id'] == pid
    assert rows[0]['transaction_id']
    assert db.snapshot().cash_balance == -100
    db.delete_financial_posting(pending_id=pid, source='TEST')
    assert service.list_registered_records() == []


def test_registered_note_deletion_is_audited_without_cash(env):
    db, service, _ = env
    pid, _ = seed(db, 'INFO', amount=0)
    db.update_pending(pid, status='APPROVED')
    service.delete_registered_note(pid)
    assert service.list_registered_records() == []
    assert db.snapshot().cash_balance == 0
    with db.read() as con:
        assert con.execute("SELECT 1 FROM audit_log WHERE entity_id=? AND action='DELETE'",(pid,)).fetchone()
        assert con.execute("SELECT 1 FROM sync_queue WHERE entity_id=? AND operation='DELETE'",(pid,)).fetchone()


def test_note_deletion_does_not_bypass_financial_posting(env):
    db, service, _ = env
    pid, payload = seed(db, 'EXPENSE', final_amount=100, payment_state='UNPAID')
    post(db,pid,payload)
    with pytest.raises(ValueError):
        service.delete_registered_note(pid)
    assert service.list_registered_records()
