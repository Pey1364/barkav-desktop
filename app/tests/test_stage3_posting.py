import tempfile
import unittest
from pathlib import Path

from finance_db import FinanceDB
from telegram_stage3_workflow import TelegramStage3Workflow


class Stage3PostingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = FinanceDB(Path(self.tmp.name) / "stage3.sqlite3")
        self.flow = TelegramStage3Workflow(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def receive(self, message_id, text, payload):
        return self.flow.receive_message(
            chat_id=-1001234567890,
            message_id=message_id,
            raw_text=text,
            content_type="TEXT",
            message_date="1405/05/19 12:30",
            analysis=payload,
        )

    def test_paid_expense_posts_cost_cash_and_manager_fee(self):
        payload = {
            "detected_type": "EXPENSE",
            "document_type": "TEXT",
            "amount": 100_000_000,
            "invoice_amount": 0,
            "final_amount": 0,
            "discount_amount": 0,
            "paid_amount": 0,
            "payment_state": "UNKNOWN",
            "description": "خرید بتن",
            "expense_category": "مصالح",
            "payment_method": "UNKNOWN",
            "is_cheque": False,
            "manager_fee_eligible": True,
            "confidence": .95,
        }
        r = self.receive(1, "#تست 100 میلیون بابت خرید بتن پرداخت کردم", payload)
        approval = self.flow.approve_and_post(r.pending_id, actor_id="123456789")
        self.assertIsNotNone(approval.posting.expense_id)
        self.assertIsNotNone(approval.posting.transaction_id)
        self.assertIsNotNone(approval.posting.payment_id)
        snap = self.db.snapshot()
        self.assertEqual(snap.cash_balance, -100_000_000)
        self.assertEqual(snap.construction_cost, 110_000_000)
        self.assertEqual(snap.manager_fee_accrued, 10_000_000)
        with self.db.read() as con:
            exp = con.execute("SELECT * FROM expenses").fetchone()
            self.assertEqual(exp["final_amount"], 100_000_000)
            self.assertEqual(exp["invoice_amount"], 100_000_000)
            self.assertEqual(exp["status"], "PAID")
            pay = con.execute("SELECT * FROM payments").fetchone()
            self.assertEqual(pay["method"], "OTHER")
            self.assertEqual(pay["status"], "COMPLETED")

    def test_unpaid_invoice_recognizes_cost_without_cash(self):
        payload = {
            "detected_type": "EXPENSE", "document_type": "INVOICE",
            "amount": 500_000_000, "invoice_amount": 500_000_000, "final_amount": 500_000_000,
            "payment_state": "UNPAID", "paid_amount": 0,
            "description": "فاکتور میلگرد", "expense_category": "مصالح",
            "payment_method": "UNKNOWN", "is_cheque": False,
            "manager_fee_eligible": True, "confidence": .98,
        }
        r = self.receive(2, "#تست فاکتور میلگرد 500 میلیون", payload)
        self.flow.approve_and_post(r.pending_id)
        snap = self.db.snapshot()
        self.assertEqual(snap.cash_balance, 0)
        self.assertEqual(snap.construction_cost, 550_000_000)
        self.assertEqual(snap.manager_fee_accrued, 50_000_000)
        with self.db.read() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 0)

    def test_future_cheque_expense_does_not_reduce_cash_until_cashed(self):
        payload = {
            "detected_type": "EXPENSE", "document_type": "TEXT",
            "amount": 300_000_000, "final_amount": 300_000_000,
            "payment_state": "PAID", "paid_amount": 300_000_000,
            "description": "خرید مصالح با چک", "expense_category": "مصالح",
            "payment_method": "CHEQUE", "is_cheque": True,
            "due_date_shamsi": "1405/07/01", "cheque_serial": "123",
            "manager_fee_eligible": True, "confidence": .99,
        }
        r = self.receive(3, "#تست 300 میلیون مصالح با چک سررسید 1405/07/01", payload)
        approval = self.flow.approve_and_post(r.pending_id)
        self.assertIsNotNone(approval.posting.cheque_id)
        snap = self.db.snapshot()
        self.assertEqual(snap.cash_balance, 0)
        self.assertEqual(snap.construction_cost, 330_000_000)
        self.assertEqual(snap.manager_fee_accrued, 30_000_000)
        self.assertEqual(snap.open_cheque_commitments, 300_000_000)
        self.db.cash_cheque(approval.posting.cheque_id, cashed_date="2026-09-23", cashed_date_shamsi="1405/07/01")
        snap2 = self.db.snapshot()
        self.assertEqual(snap2.cash_balance, -300_000_000)
        self.assertEqual(snap2.construction_cost, 330_000_000)
        self.assertEqual(snap2.manager_fee_accrued, 30_000_000)
        self.assertEqual(snap2.open_cheque_commitments, 0)

    def test_income_and_manager_withdrawal(self):
        income = {
            "detected_type": "INCOME", "document_type": "TEXT", "amount": 1_000_000_000,
            "description": "واریزی شریک", "payment_method": "BANK_TRANSFER",
            "payment_state": "PAID", "is_cheque": False, "manager_fee_eligible": False, "confidence": .99,
        }
        r1 = self.receive(4, "#تست یک میلیارد واریزی شریک", income)
        self.flow.approve_and_post(r1.pending_id)
        out = {
            "detected_type": "OUTFLOW", "document_type": "TEXT", "amount": 20_000_000,
            "description": "برداشت حقوق پیمان", "payment_method": "BANK_TRANSFER",
            "payment_state": "PAID", "is_cheque": False, "manager_fee_eligible": False, "confidence": .99,
        }
        r2 = self.receive(5, "#تست 20 میلیون حقوق پیمان برداشت کردم", out)
        self.flow.approve_and_post(r2.pending_id)
        snap = self.db.snapshot()
        self.assertEqual(snap.cash_balance, 980_000_000)
        self.assertEqual(snap.manager_withdrawals, 20_000_000)
        self.assertEqual(snap.manager_fee_accrued, 0)
        self.assertEqual(snap.manager_balance, -20_000_000)

    def test_repeated_approval_is_idempotent(self):
        payload = {
            "detected_type": "INCOME", "document_type": "TEXT", "amount": 100_000_000,
            "description": "ورودی", "payment_method": "BANK_TRANSFER", "payment_state": "PAID",
            "is_cheque": False, "manager_fee_eligible": False, "confidence": .99,
        }
        r = self.receive(6, "#تست 100 میلیون ورودی", payload)
        a1 = self.flow.approve_and_post(r.pending_id)
        a2 = self.flow.approve_and_post(r.pending_id)
        self.assertEqual(a1.posting.posting_id, a2.posting.posting_id)
        self.assertEqual(self.db.cash_balance(), 100_000_000)
        with self.db.read() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM financial_postings").fetchone()[0], 1)

    def test_reject_has_no_financial_effect(self):
        payload = {
            "detected_type": "OUTFLOW", "document_type": "TEXT", "amount": 70_000_000,
            "description": "سفر", "payment_method": "CARD", "payment_state": "PAID",
            "is_cheque": False, "manager_fee_eligible": False, "confidence": .9,
        }
        r = self.receive(7, "#تست 70 میلیون سفر", payload)
        self.flow.reject(r.pending_id)
        self.assertEqual(self.db.cash_balance(), 0)
        with self.db.read() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM financial_postings").fetchone()[0], 0)

    def test_cheque_without_due_date_is_blocked_atomically(self):
        payload = {
            "detected_type": "EXPENSE", "document_type": "TEXT", "amount": 200_000_000,
            "final_amount": 200_000_000, "description": "خرید با چک",
            "payment_method": "CHEQUE", "payment_state": "PAID", "is_cheque": True,
            "due_date_shamsi": "", "manager_fee_eligible": True, "confidence": .9,
        }
        r = self.receive(8, "#تست خرید با چک 200 میلیون", payload)
        with self.assertRaises(ValueError):
            self.flow.approve_and_post(r.pending_id)
        self.assertEqual(self.db.construction_cost(), 0)
        with self.db.read() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM expenses").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM financial_postings").fetchone()[0], 0)
        self.assertEqual(self.db.get_pending_item(r.pending_id)["status"], "PENDING_REVIEW")


if __name__ == "__main__":
    unittest.main()
