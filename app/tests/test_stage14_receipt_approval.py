from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from approval_service import ApprovalCenterService
from finance_db import FinanceDB
from receipt_intelligence import OCRResult, ReceiptIntelligenceService, extract_amount_candidates
from telegram_stage5_workflow import TelegramStage5Workflow


class DummyParser:
    async def analyze(self, **kwargs):
        return {
            "detected_type": "EXPENSE",
            "document_type": "PAYMENT_RECEIPT",
            "transaction_type_fa": "هزینه ساخت",
            "amount": 120_000_000,
            "invoice_amount": 120_000_000,
            "final_amount": 120_000_000,
            "discount_amount": 0,
            "description": "خرید بتن",
            "expense_category": "مصالح",
            "construction_stage": "اسکلت",
            "payer_name": "پیمان",
            "receiver_name": "بتن جنوب",
            "payment_method": "BANK_TRANSFER",
            "payment_state": "PAID",
            "paid_amount": 120_000_000,
            "is_cheque": False,
            "manager_fee_eligible": True,
            "event_date_shamsi": "1405/05/20",
            "confidence": 0.94,
            "field_confidences": {"amount": 0.95, "description": 0.9},
        }


class Stage14Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = FinanceDB(self.root / "db.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def _pending(self, message_id=1, amount=120_000_000):
        wf = TelegramStage5Workflow(self.db)
        return wf.receive_message(
            chat_id=-1001,
            message_id=message_id,
            raw_text=f"#تست {amount} بابت خرید بتن پرداخت کردم",
            content_type="PHOTO",
            message_date="1405/05/20 10:30",
            analysis={
                "detected_type": "EXPENSE",
                "document_type": "PAYMENT_RECEIPT",
                "transaction_type_fa": "هزینه ساخت",
                "amount": amount,
                "invoice_amount": amount,
                "final_amount": amount,
                "discount_amount": 0,
                "description": "بتن",
                "expense_category": "مصالح",
                "construction_stage": "اسکلت",
                "payer_name": "پیمان",
                "receiver_name": "بتن جنوب",
                "payment_method": "BANK_TRANSFER",
                "payment_state": "PAID",
                "paid_amount": amount,
                "is_cheque": False,
                "manager_fee_eligible": True,
                "event_date_shamsi": "1405/05/20",
                "confidence": 0.9,
            },
        )

    def test_ocr_amount_candidates_convert_rial_to_toman(self):
        vals = extract_amount_candidates("مبلغ 1,200,000,000 ریال")
        self.assertIn(120_000_000, vals)

    def test_schema_and_defaults(self):
        self.assertEqual(self.db.health_check()["schema_version"], 13)
        self.assertEqual(self.db.get_setting("approval_channels"), "BOTH")
        with self.db.read() as con:
            names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("receipt_analyses", names)
        self.assertIn("integration_events", names)
        self.assertIn("learned_rules", names)

    def test_receipt_analysis_conflict_and_duplicate(self):
        # Existing same-amount posting becomes a duplicate candidate.
        p0 = self._pending(message_id=10)
        ApprovalCenterService(self.db, self.root).approve(p0.pending_id)

        p1 = self._pending(message_id=11, amount=100_000_000)
        img = self.root / "sample.jpg"
        from PIL import Image
        Image.new("RGB", (120, 80), "white").save(img)
        svc = ReceiptIntelligenceService(self.db, self.root, parser=DummyParser())
        svc.ocr.extract = lambda path: OCRResult("مبلغ 120,000,000 تومان", "TEST_OCR", True)  # type: ignore
        result = asyncio.run(svc.analyze_archived(
            pending_id=p1.pending_id,
            caption="#تست 100 میلیون بابت بتن پرداخت کردم",
            image_path=img,
            message_date_shamsi="1405/05/20 11:00",
        ))
        self.assertTrue(any(x.get("field") == "amount" for x in result["conflicts"]))
        self.assertTrue(result["duplicate_candidates"])
        row = self.db.get_receipt_analysis(p1.pending_id)
        self.assertEqual(row["provider"], "GEMINI_VISION+TESSERACT")
        self.assertEqual(row["status"], "NEEDS_REVIEW")

    def test_document_group_hint_catches_a_duplicate_the_exact_amount_check_misses(self):
        """Two receipts settling one shared bill in different amounts (e.g.
        two partial payments toward «هزینه دفترخانه») never match on amount -
        find_receipt_duplicate_candidates requires an exact amount equal.
        document_group_hint is exactly what ai_parser.SYSTEM_PROMPT asks the
        model to fill for this case; this is what actually reads it back.
        """

        class GroupHintParser:
            def __init__(self, amount):
                self.amount = amount

            async def analyze(self, **kwargs):
                return {
                    "detected_type": "EXPENSE", "document_type": "PAYMENT_RECEIPT",
                    "transaction_type_fa": "هزینه ساخت", "amount": self.amount,
                    "invoice_amount": self.amount, "final_amount": self.amount,
                    "discount_amount": 0, "description": "قسط دفترخانه",
                    "expense_category": "سایر", "construction_stage": "",
                    "payer_name": "پیمان", "receiver_name": "دفترخانه",
                    "payment_method": "BANK_TRANSFER", "payment_state": "PAID",
                    "paid_amount": self.amount, "is_cheque": False,
                    "manager_fee_eligible": True, "event_date_shamsi": "1405/05/20",
                    "confidence": 0.9, "document_group_hint": "هزینه دفترخانه",
                }

        img = self.root / "sample.jpg"
        from PIL import Image
        Image.new("RGB", (120, 80), "white").save(img)

        p0 = self._pending(message_id=40, amount=200_000_000)
        svc0 = ReceiptIntelligenceService(self.db, self.root, parser=GroupHintParser(200_000_000))
        svc0.ocr.extract = lambda path: OCRResult("", "TEST_OCR", True)  # type: ignore
        asyncio.run(svc0.analyze_archived(
            pending_id=p0.pending_id, caption="قسط اول دفترخانه", image_path=img,
            message_date_shamsi="1405/05/20 11:00",
        ))

        p1 = self._pending(message_id=41, amount=150_000_000)
        svc1 = ReceiptIntelligenceService(self.db, self.root, parser=GroupHintParser(150_000_000))
        svc1.ocr.extract = lambda path: OCRResult("", "TEST_OCR", True)  # type: ignore
        result = asyncio.run(svc1.analyze_archived(
            pending_id=p1.pending_id, caption="قسط دوم دفترخانه", image_path=img,
            message_date_shamsi="1405/05/22 11:00",
        ))

        # Different amounts (200M vs 150M) - the exact-amount duplicate check
        # alone would report none of these as related.
        exact_amount_only = self.db.find_receipt_duplicate_candidates(
            amount=150_000_000, description="قسط دوم دفترخانه")
        self.assertFalse(any(r["entity_id"] == p0.pending_id for r in exact_amount_only
                             if r.get("entity_type") != "PENDING_GROUP"))

        group_matches = [d for d in result["duplicate_candidates"] if d.get("entity_type") == "PENDING_GROUP"]
        self.assertTrue(group_matches, "document_group_hint match was not surfaced")
        self.assertEqual(group_matches[0]["entity_id"], p0.pending_id)
        self.assertTrue(any(c.get("field") == "document_group_hint" for c in result["conflicts"]))

    def test_gui_approval_posts_and_relinks_attachment(self):
        pending = self._pending(message_id=20)
        f = self.root / "receipt.jpg"
        f.write_bytes(b"fake")
        self.db.attach_file_to_pending(
            pending_id=pending.pending_id,
            local_path=str(f),
            mime_type="image/jpeg",
        )
        self.db.upsert_receipt_analysis(
            pending_id=pending.pending_id,
            provider="TEST",
            document_type="PAYMENT_RECEIPT",
            image_path=str(f),
            field_confidences={"amount": 0.99},
        )
        svc = ApprovalCenterService(self.db, self.root)
        approval = svc.approve(pending.pending_id, actor_id="GUI_TEST")
        self.assertEqual(self.db.get_pending_item(pending.pending_id)["status"], "APPROVED")
        self.assertIsNotNone(approval.posting.expense_id)
        with self.db.read() as con:
            att = con.execute("SELECT entity_type,entity_id FROM attachments").fetchone()
            evt = con.execute("SELECT event_type,status FROM integration_events").fetchone()
        self.assertEqual(att[0], "EXPENSE")
        self.assertEqual(att[1], approval.posting.expense_id)
        self.assertEqual(evt[0], "GUI_APPROVED")
        self.assertEqual(evt[1], "PENDING")
        self.assertEqual(self.db.get_receipt_analysis(pending.pending_id)["status"], "APPROVED")

    def test_link_existing_attaches_document_without_new_financial_effect(self):
        base = self._pending(message_id=25)
        svc = ApprovalCenterService(self.db, self.root)
        posted = svc.approve(base.pending_id, actor_id="TEST")
        before = self.db.snapshot()

        doc = self._pending(message_id=26)
        f = self.root / "same_receipt.jpg"
        f.write_bytes(b"same")
        self.db.attach_file_to_pending(pending_id=doc.pending_id, local_path=str(f), mime_type="image/jpeg")
        result = svc.link_existing(doc.pending_id, entity_type="EXPENSE", entity_id=posted.posting.expense_id, actor_id="GUI_TEST")
        after = self.db.snapshot()
        self.assertEqual(before, after)
        self.assertEqual(self.db.get_pending_item(doc.pending_id)["status"], "APPROVED")
        with self.db.read() as con:
            att = con.execute("SELECT entity_type,entity_id FROM attachments WHERE local_path=?", (str(f),)).fetchone()
        self.assertEqual(att[0], "EXPENSE")
        self.assertEqual(att[1], posted.posting.expense_id)
        self.assertEqual(result["entity_type"], "EXPENSE")

    def test_gui_reject_queues_side_effect(self):
        pending = self._pending(message_id=30)
        svc = ApprovalCenterService(self.db, self.root)
        svc.reject(pending.pending_id, actor_id="GUI_TEST")
        self.assertEqual(self.db.get_pending_item(pending.pending_id)["status"], "REJECTED")
        ev = self.db.get_integration_events(limit=10)
        self.assertEqual(ev[0]["event_type"], "GUI_REJECTED")

    def test_learning_rule_applies_on_future_analysis(self):
        self.db.upsert_learned_rule(
            rule_type="COUNTERPARTY_ALIAS", pattern="بتن جنوب",
            target_field="construction_stage", target_value="اسکلت"
        )
        out = self.db.apply_learned_rules("پرداخت به بتن جنوب", {"construction_stage": ""})
        self.assertEqual(out["construction_stage"], "اسکلت")


if __name__ == "__main__":
    unittest.main()
