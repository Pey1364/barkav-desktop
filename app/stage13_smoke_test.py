from __future__ import annotations
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

from dashboard_service_stage12 import DashboardServiceStage12
from finance_db import FinanceDB
from revenue_service import gregorian_to_shamsi
from telegram_history_import import import_telegram_export

with tempfile.TemporaryDirectory() as td:
    root=Path(td);db=FinanceDB(root/'smoke.sqlite3');svc=DashboardServiceStage12(db,root)
    today=date.today();due=today+timedelta(days=10);sh=gregorian_to_shamsi(today);dsh=gregorian_to_shamsi(due)
    db.post_transaction(event_date=today.isoformat(),shamsi_date=sh,direction='IN',amount=500_000_000,category='CAPITAL')
    db.create_cheque(amount=120_000_000,issue_date=today.isoformat(),issue_date_shamsi=sh,due_date=due.isoformat(),due_date_shamsi=dsh)
    assert db.open_cheque_commitments()==120_000_000
    phase=svc.budget.add_phase_after(None,'فاز خالی تست')
    assert any(r['phase_id']==phase['phase_id'] for r in svc.budget.phase_summary())
    export={'name':'old','messages':[{'id':1,'type':'message','date':'2026-07-01T10:00:00','text':'50 میلیون بابت سیمان پرداخت کردم'}]}
    jp=root/'result.json';jp.write_text(json.dumps(export,ensure_ascii=False),encoding='utf-8')
    imp=import_telegram_export(db,jp);assert imp.created==1;assert db.cash_balance()==500_000_000
    print('STAGE 13 SMOKE TEST: OK')
    print('open_cheques=120,000,000')
    print('historical_pending=1')
    print('empty_phase_visible=yes')
