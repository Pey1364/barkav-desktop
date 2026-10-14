from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from approval_service import ApprovalCenterService
from finance_db import FinanceDB
from project_registry import ProjectRegistry, apply_project_environment
from receipt_intelligence import OCRResult, ReceiptIntelligenceService
from telegram_history_import import import_telegram_export
from telegram_stage5_workflow import TelegramStage5Workflow


class CaptureVisionParser:
    def __init__(self):
        self.last_image=b"";self.last_ocr=""
    async def analyze(self, **kwargs):
        self.last_image=kwargs.get("image_bytes") or b""
        self.last_ocr=kwargs.get("ocr_text") or ""
        return {
            "detected_type":"EXPENSE","document_type":"PAYMENT_RECEIPT",
            "transaction_type_fa":"هزینه ساخت","amount":25_000_000,
            "invoice_amount":25_000_000,"final_amount":25_000_000,
            "description":"سیمان","expense_category":"مصالح","construction_stage":"اسکلت",
            "payer_name":"پیمان","receiver_name":"فروشنده","payment_method":"BANK_TRANSFER",
            "payment_state":"PAID","paid_amount":25_000_000,"is_cheque":False,
            "manager_fee_eligible":True,"event_date_shamsi":"1405/05/20","confidence":0.96,
            "field_confidences":{"amount":0.97,"description":0.9,"document_type":0.95},
        }


class Stage15Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.db=FinanceDB(self.root/'db.sqlite3')
    def tearDown(self):
        self.tmp.cleanup()

    def test_photo_only_history_is_never_filtered_before_vision(self):
        export=self.root/'export';(export/'photos').mkdir(parents=True)
        img=export/'photos'/'receipt.jpg';Image.new('RGB',(160,90),'white').save(img)
        data={"name":"Project","type":"private_supergroup","id":1,"messages":[
            {"id":101,"type":"message","date":"2026-08-10T10:00:00","from":"Peyman","text":"","photo":"photos/receipt.jpg"},
            {"id":102,"type":"message","date":"2026-08-10T10:01:00","from":"Peyman","text":"سلام دوستان"},
        ]}
        js=export/'result.json';js.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        receipt=ReceiptIntelligenceService(self.db,self.root,parser=None)
        result=import_telegram_export(self.db,js,receipt_service=receipt)
        self.assertEqual(result.scanned,2)
        self.assertEqual(result.media_candidates,1)
        self.assertEqual(result.created,1)
        self.assertEqual(len(result.media_pending_ids),1)
        pid=result.media_pending_ids[0]
        self.assertTrue(self.db.list_pending_attachments(pid))
        row=self.db.get_receipt_analysis(pid)
        self.assertEqual(row['provider'],'PENDING_VISION')
        self.assertTrue(Path(row['image_path']).exists())

    def test_vision_receives_original_image_not_ocr_derivative(self):
        wf=TelegramStage5Workflow(self.db)
        pending=wf.receive_message(chat_id=-100,message_id=1,raw_text='#تست رسید',content_type='PHOTO',message_date='1405/05/20 10:00',analysis={"detected_type":"DOCUMENT","amount":0,"description":"","confidence":0.1})
        img=self.root/'color.png';Image.new('RGB',(20,20),(250,0,0)).save(img)
        original_bytes=img.read_bytes()
        parser=CaptureVisionParser();svc=ReceiptIntelligenceService(self.db,self.root,parser=parser)
        svc.ocr.extract=lambda path: OCRResult('مبلغ 25,000,000 تومان','TEST',True)  # type: ignore
        out=asyncio.run(svc.analyze_archived(pending_id=pending.pending_id,caption='#تست رسید',image_path=img,message_date_shamsi='1405/05/20'))
        archived=Path(out['image_path']).read_bytes()
        self.assertEqual(parser.last_image,archived)
        self.assertEqual(archived,original_bytes)
        self.assertIn('25,000,000',parser.last_ocr)
        self.assertEqual(out['payload']['vision_status'],'OK')
        self.assertTrue(out['payload']['vision_required'])

    def test_gui_can_reanalyze_imported_pending_later(self):
        wf=TelegramStage5Workflow(self.db)
        p=wf.receive_message(chat_id=-200,message_id=2,raw_text='',content_type='HISTORICAL_IMAGE',message_date='1405/05/20 10:00',analysis={"detected_type":"DOCUMENT","amount":0,"description":"","confidence":0.1})
        img=self.root/'later.jpg';Image.new('RGB',(100,70),'white').save(img)
        self.db.attach_file_to_pending(pending_id=p.pending_id,local_path=str(img),mime_type='image/jpeg')
        parser=CaptureVisionParser();svc=ApprovalCenterService(self.db,self.root,parser=parser)
        svc.receipts.ocr.extract=lambda path: OCRResult('25,000,000 تومان','TEST',True)  # type: ignore
        asyncio.run(svc.analyze_pending_with_ai(p.pending_id))
        fresh=self.db.get_pending_item(p.pending_id)
        self.assertEqual(fresh['payload']['amount'],25_000_000)
        self.assertEqual(self.db.get_receipt_analysis(p.pending_id)['provider'],'GEMINI_VISION+TESSERACT')

    def test_project_registry_keeps_legacy_and_creates_isolated_db(self):
        secrets={"STAGE4_DB_PATH":str(self.root/'legacy.sqlite3'),"GROUP_CHAT_ID":"-1001","SPREADSHEET_NAME":"OLD"}
        reg=ProjectRegistry(self.root)
        legacy=reg.ensure_legacy_project(secrets)
        self.assertEqual(legacy.project_id,'PRJ-001')
        p=reg.create(name='Project 2',group_chat_id=-1002,spreadsheet_name='P2')
        self.assertEqual(p.project_id,'PRJ-002')
        self.assertNotEqual(Path(p.db_path),Path(legacy.db_path))
        self.assertTrue(Path(p.db_path).exists())
        apply_project_environment(p)
        self.assertEqual(os.environ['GROUP_CHAT_ID'],'-1002')
        self.assertEqual(os.environ['STAGE4_DB_PATH'],p.db_path)


if __name__=='__main__':unittest.main()
