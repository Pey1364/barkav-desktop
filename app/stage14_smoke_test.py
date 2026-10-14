from __future__ import annotations

import tempfile
from pathlib import Path

from approval_service import ApprovalCenterService
from finance_db import FinanceDB
from telegram_stage5_workflow import TelegramStage5Workflow

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    db=FinanceDB(root/'stage14.sqlite3')
    wf=TelegramStage5Workflow(db)
    pending=wf.receive_message(
        chat_id=-1001,message_id=1,raw_text='#تست 120 میلیون بابت بتن پرداخت کردم',
        content_type='PHOTO',message_date='1405/05/20 09:15',
        analysis={
            'detected_type':'EXPENSE','document_type':'PAYMENT_RECEIPT','transaction_type_fa':'هزینه ساخت',
            'amount':120_000_000,'invoice_amount':120_000_000,'final_amount':120_000_000,'discount_amount':0,
            'description':'بتن','expense_category':'مصالح','construction_stage':'اسکلت','payer_name':'پیمان',
            'receiver_name':'بتن جنوب','payment_method':'BANK_TRANSFER','payment_state':'PAID','paid_amount':120_000_000,
            'is_cheque':False,'manager_fee_eligible':True,'event_date_shamsi':'1405/05/20','confidence':0.95,
        }
    )
    image=root/'receipt.jpg'; image.write_bytes(b'test-image')
    db.attach_file_to_pending(pending_id=pending.pending_id,local_path=str(image),mime_type='image/jpeg')
    db.upsert_receipt_analysis(pending_id=pending.pending_id,provider='SMOKE',document_type='PAYMENT_RECEIPT',image_path=str(image),field_confidences={'amount':0.99})
    svc=ApprovalCenterService(db,root)
    result=svc.approve(pending.pending_id,actor_id='SMOKE')
    snap=db.snapshot()
    assert result.posting.expense_id
    assert snap.construction_cost==120_000_000
    assert snap.cash_balance==-120_000_000
    assert snap.manager_fee_accrued==12_000_000
    assert db.get_receipt_analysis(pending.pending_id)['status']=='APPROVED'
    assert db.get_integration_events()[0]['event_type']=='GUI_APPROVED'
    assert db.health_check()['schema_version']==12
    print('STAGE 14 SMOKE TEST: OK')
    print('receipt_pending_to_posted=yes')
    print('construction=120,000,000')
    print('manager_fee=12,000,000')
    print('gui_telegram_outbox=queued')
