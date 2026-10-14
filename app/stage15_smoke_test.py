from __future__ import annotations
import asyncio,json,tempfile
from pathlib import Path
from PIL import Image
from finance_db import FinanceDB
from receipt_intelligence import OCRResult,ReceiptIntelligenceService
from telegram_history_import import import_telegram_export
from approval_service import ApprovalCenterService

class P:
    async def analyze(self,**kwargs):
        return {"detected_type":"EXPENSE","document_type":"PAYMENT_RECEIPT","transaction_type_fa":"هزینه ساخت","amount":50_000_000,"invoice_amount":50_000_000,"final_amount":50_000_000,"description":"سیمان","expense_category":"مصالح","construction_stage":"اسکلت","payer_name":"پیمان","receiver_name":"فروشنده","payment_method":"BANK_TRANSFER","payment_state":"PAID","paid_amount":50_000_000,"is_cheque":False,"manager_fee_eligible":True,"event_date_shamsi":"1405/05/20","confidence":0.98,"field_confidences":{"amount":0.99}}

with tempfile.TemporaryDirectory() as td:
    root=Path(td);db=FinanceDB(root/'db.sqlite3');exp=root/'export';(exp/'photos').mkdir(parents=True)
    Image.new('RGB',(100,60),'white').save(exp/'photos'/'r.jpg')
    (exp/'result.json').write_text(json.dumps({"name":"g","messages":[{"id":1,"type":"message","date":"2026-08-10T10:00:00","text":"","photo":"photos/r.jpg"}]},ensure_ascii=False),encoding='utf-8')
    rsvc=ReceiptIntelligenceService(db,root,parser=P());rsvc.ocr.extract=lambda p:OCRResult('50,000,000 تومان','TEST',True)
    imp=import_telegram_export(db,exp/'result.json',receipt_service=rsvc);pid=imp.media_pending_ids[0]
    app=ApprovalCenterService(db,root,parser=P());app.receipts.ocr.extract=lambda p:OCRResult('50,000,000 تومان','TEST',True)
    asyncio.run(app.analyze_pending_with_ai(pid));app.approve(pid,actor_id='SMOKE')
    snap=db.snapshot();assert snap.construction_cost==50_000_000 and snap.cash_balance==-50_000_000
    print('STAGE 15 SMOKE TEST: OK')
    print('photo_only_history_import=yes')
    print('vision_provider=yes')
    print('construction=50,000,000')
