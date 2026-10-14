from __future__ import annotations
import asyncio
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from finance_db import FinanceDB
from receipt_intelligence import OCRResult, ReceiptIntelligenceService
from receipt_ai_provider import ReceiptVisionProviderChain
from telegram_stage5_workflow import TelegramStage5Workflow


class WeakThenGoodParser:
    def __init__(self): self.calls=[]
    async def analyze(self, **kwargs):
        self.calls.append(kwargs.get('image_bytes') or b'')
        if len(self.calls)==1:
            return {
                'detected_type':'UNKNOWN','document_type':'OTHER','amount':0,'final_amount':0,
                'description':'','confidence':0.30,'field_confidences':{'amount':0.20},
                '_vision_provider':'GEMINI:TEST'
            }
        return {
            'detected_type':'EXPENSE','document_type':'PAYMENT_RECEIPT','amount':25_000_000,
            'final_amount':25_000_000,'paid_amount':25_000_000,'description':'خرید مصالح',
            'payment_state':'PAID','confidence':0.96,'field_confidences':{'amount':0.98,'description':0.9},
            '_vision_provider':'GEMINI:TEST'
        }


class ContextAwareParser:
    def __init__(self): self.texts=[]
    async def analyze(self, **kwargs):
        self.texts.append(str(kwargs.get('text') or ''))
        return {
            'detected_type':'EXPENSE','document_type':'PAYMENT_RECEIPT','amount':8_000_000,
            'final_amount':8_000_000,'paid_amount':8_000_000,'description':'خرید بتن',
            'payment_state':'PAID','confidence':0.97,'field_confidences':{'amount':0.98,'description':0.95},
            '_vision_provider':'GEMINI:TEST'
        }


class FlakyProvider:
    def __init__(self): self.calls=0
    async def analyze(self, **kwargs):
        self.calls += 1
        if self.calls == 1: raise RuntimeError('503 service unavailable')
        return {'amount': 10, 'confidence': 0.9}


class Stage181ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.db=FinanceDB(self.root/'db.sqlite3')
    def tearDown(self): self.tmp.cleanup()

    def test_low_confidence_receipt_gets_enhanced_second_vision_pass(self):
        wf=TelegramStage5Workflow(self.db)
        pen=wf.receive_message(chat_id=-100,message_id=181,raw_text='فیش خرید مصالح',content_type='PHOTO',message_date='1405/05/28 10:00',analysis={'detected_type':'DOCUMENT','amount':0,'confidence':0.1})
        img=self.root/'receipt.png'
        im=Image.new('RGB',(1200,700),'white'); im.save(img)
        parser=WeakThenGoodParser(); svc=ReceiptIntelligenceService(self.db,self.root,parser=parser)
        svc.ocr.extract=lambda path: OCRResult('مبلغ پرداختی 25,000,000 تومان','TEST',True)  # type: ignore
        out=asyncio.run(svc.analyze_archived(pending_id=pen.pending_id,caption='فیش خرید مصالح',image_path=img,message_date_shamsi='1405/05/28'))
        self.assertEqual(len(parser.calls),2)
        self.assertEqual(out['payload']['amount'],25_000_000)
        self.assertTrue(out['payload'].get('vision_retry_used'))
        self.assertIn('ENHANCED_RETRY',out['provider'])
        self.assertEqual(out['payload']['vision_status'],'OK')
        self.assertEqual(out['payload']['receipt_caption'],'فیش خرید مصالح')


    def test_analyze_archived_never_blends_in_text_beyond_its_own_caption(self):
        wf=TelegramStage5Workflow(self.db)
        pen=wf.receive_message(chat_id=-101,message_id=191,raw_text='خرید بتن سقف سوم',content_type='PHOTO',message_date='1405/05/28 11:00',analysis={'detected_type':'DOCUMENT','amount':0,'confidence':0.1})
        img=self.root/'receipt_context.png'; Image.new('RGB',(900,550),'white').save(img)
        parser=ContextAwareParser(); svc=ReceiptIntelligenceService(self.db,self.root,parser=parser)
        svc.ocr.extract=lambda path: OCRResult('', 'NONE', False)  # type: ignore
        out=asyncio.run(svc.analyze_archived(
            pending_id=pen.pending_id, caption='خرید بتن سقف سوم', image_path=img,
            message_date_shamsi='1405/05/28'))
        self.assertTrue(parser.texts)
        # The vision model receives exactly this receipt's own caption - no
        # adjacent/neighboring message's text can be blended in anymore
        # (analyze_archived no longer accepts any such text at all).
        self.assertEqual(parser.texts[0], 'خرید بتن سقف سوم')
        self.assertEqual(out['payload']['receipt_caption'], 'خرید بتن سقف سوم')

    def test_provider_chain_retries_transient_error_once(self):
        p=FlakyProvider(); chain=ReceiptVisionProviderChain([('GEMINI:TEST',p)])
        out=asyncio.run(chain.analyze(text='',image_bytes=b'x',image_mime_type='image/jpeg',ocr_text=''))
        self.assertEqual(p.calls,2)
        self.assertEqual(out['amount'],10)
        self.assertEqual(out['_vision_provider'],'GEMINI:TEST')

if __name__=='__main__': unittest.main()
