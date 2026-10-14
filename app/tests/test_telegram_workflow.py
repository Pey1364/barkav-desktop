import tempfile
import unittest
from pathlib import Path

from finance_db import FinanceDB
from telegram_workflow import TelegramReviewWorkflow


SAMPLE = {
    "detected_type": "EXPENSE",
    "document_type": "TEXT",
    "transaction_type_fa": "هزینه",
    "amount": 100_000_000,
    "description": "بتن",
    "payment_method": "BANK_TRANSFER",
    "is_cheque": False,
    "manager_fee_eligible": True,
    "confidence": 0.95,
}


class TelegramWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = FinanceDB(Path(self.tmp.name) / "test.sqlite3")
        self.flow = TelegramReviewWorkflow(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_receive_creates_pending_without_financial_effect(self):
        r = self.flow.receive_message(
            chat_id=-1001, message_id=10, raw_text="بتن 100", content_type="TEXT",
            message_date="1405/05/19 12:00", analysis=SAMPLE,
        )
        self.assertEqual(r.state, "PENDING_REVIEW")
        self.assertEqual(self.db.cash_balance(), 0)
        self.assertEqual(self.db.construction_cost(), 0)

    def test_approve_changes_state_but_not_money_in_stage2(self):
        r = self.flow.receive_message(
            chat_id=-1001, message_id=11, raw_text="بتن 100", content_type="TEXT",
            message_date="1405/05/19 12:00", analysis=SAMPLE,
        )
        approved = self.flow.approve(r.pending_id)
        self.assertEqual(approved.state, "APPROVED")
        self.assertEqual(self.db.cash_balance(), 0)
        self.assertEqual(self.db.construction_cost(), 0)
        tg = self.db.get_telegram_message(-1001, 11)
        self.assertEqual(tg["state"], "APPROVED")

    def test_reject_has_no_financial_effect(self):
        r = self.flow.receive_message(
            chat_id=-1001, message_id=12, raw_text="تست", content_type="TEXT",
            message_date="1405/05/19 12:00", analysis=SAMPLE,
        )
        self.flow.reject(r.pending_id)
        self.assertEqual(self.db.cash_balance(), 0)
        self.assertEqual(self.db.construction_cost(), 0)
        self.assertEqual(self.db.get_pending_item(r.pending_id)["status"], "REJECTED")

    def test_duplicate_message_does_not_create_second_pending(self):
        r1 = self.flow.receive_message(
            chat_id=-1001, message_id=13, raw_text="تست", content_type="TEXT",
            message_date="1405/05/19 12:00", analysis=SAMPLE,
        )
        r2 = self.flow.receive_message(
            chat_id=-1001, message_id=13, raw_text="تست", content_type="TEXT",
            message_date="1405/05/19 12:00", analysis=SAMPLE,
        )
        self.assertEqual(r1.pending_id, r2.pending_id)
        with self.db.read() as con:
            count = con.execute("SELECT COUNT(*) FROM pending_items").fetchone()[0]
        self.assertEqual(count, 1)

    def test_edit_updates_same_pending(self):
        r = self.flow.receive_message(
            chat_id=-1001, message_id=14, raw_text="بتن 100", content_type="TEXT",
            message_date="1405/05/19 12:00", analysis=SAMPLE,
        )
        self.flow.begin_edit(r.pending_id)
        edited = self.flow.apply_edit(r.pending_id, {"amount": 120_000_000, "description": "بتن اصلاح‌شده"})
        self.assertEqual(edited.pending_id, r.pending_id)
        self.assertEqual(edited.payload["amount"], 120_000_000)
        self.assertEqual(edited.state, "PENDING_REVIEW")


if __name__ == "__main__":
    unittest.main()
