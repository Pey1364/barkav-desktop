import tempfile
import unittest
from pathlib import Path

from finance_db import FinanceDB
from telegram_stage5_workflow import TelegramStage5Workflow


class Stage5RevisionDeleteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = FinanceDB(Path(self.tmp.name) / "test.sqlite3")
        self.flow = TelegramStage5Workflow(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def receive(self, message_id, text, payload):
        return self.flow.receive_message(
            chat_id=-1001234567890,
            message_id=message_id,
            raw_text=text,
            content_type="TEXT",
            message_date="1405/05/19 12:00",
            analysis=payload,
        )

    @staticmethod
    def paid_expense(amount=100_000_000):
        return {
            "detected_type": "EXPENSE",
            "document_type": "TEXT",
            "amount": amount,
            "invoice_amount": amount,
            "final_amount": amount,
            "discount_amount": 0,
            "paid_amount": amount,
            "payment_state": "PAID",
            "description": "خرید بتن",
            "expense_category": "مصالح",
            "payment_method": "BANK_TRANSFER",
            "is_cheque": False,
            "manager_fee_eligible": True,
            "confidence": .99,
        }

    def test_edit_paid_expense_keeps_ids_and_recalculates(self):
        r = self.receive(101, "#تست 100 میلیون بتن پرداخت کردم", self.paid_expense())
        first = self.flow.approve_and_post(r.pending_id).posting
        new_payload = self.paid_expense(120_000_000)
        new_payload["description"] = "خرید بتن اصلاح‌شده"
        self.flow.begin_posted_revision(r.pending_id, new_payload)
        revised = self.flow.approve_posted_revision(r.pending_id)

        self.assertEqual(revised.posting_id, first.posting_id)
        self.assertEqual(revised.expense_id, first.expense_id)
        self.assertEqual(revised.transaction_id, first.transaction_id)
        self.assertEqual(revised.payment_id, first.payment_id)
        snap = self.db.snapshot()
        self.assertEqual(snap.cash_balance, -120_000_000)
        self.assertEqual(snap.construction_cost, 120_000_000)
        self.assertEqual(snap.manager_fee_accrued, 12_000_000)
        with self.db.read() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM expenses").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM financial_postings").fetchone()[0], 1)

    def test_reject_revision_keeps_original_financial_effect(self):
        r = self.receive(102, "#تست 100 میلیون بتن پرداخت کردم", self.paid_expense())
        self.flow.approve_and_post(r.pending_id)
        new_payload = self.paid_expense(150_000_000)
        self.flow.begin_posted_revision(r.pending_id, new_payload)
        restored = self.flow.reject_posted_revision(r.pending_id)
        self.assertEqual(restored["amount"], 100_000_000)
        snap = self.db.snapshot()
        self.assertEqual(snap.cash_balance, -100_000_000)
        self.assertEqual(snap.construction_cost, 100_000_000)
        self.assertEqual(self.db.get_pending_item(r.pending_id)["status"], "APPROVED")

    def test_delete_expense_reverses_cash_cost_fee_and_is_idempotent(self):
        r = self.receive(103, "#تست 100 میلیون بتن پرداخت کردم", self.paid_expense())
        first = self.flow.approve_and_post(r.pending_id).posting
        self.flow.delete_posting(r.pending_id, reason="test")
        snap = self.db.snapshot()
        self.assertEqual(snap.cash_balance, 0)
        self.assertEqual(snap.construction_cost, 0)
        self.assertEqual(snap.manager_fee_accrued, 0)
        post = self.db.get_financial_posting(r.pending_id)
        self.assertEqual(post["status"], "DELETED")
        with self.db.read() as con:
            self.assertEqual(con.execute("SELECT status FROM transactions WHERE transaction_id=?", (first.transaction_id,)).fetchone()[0], "VOIDED")
            self.assertEqual(con.execute("SELECT status FROM payments WHERE payment_id=?", (first.payment_id,)).fetchone()[0], "CANCELLED")
            self.assertEqual(con.execute("SELECT status FROM expenses WHERE expense_id=?", (first.expense_id,)).fetchone()[0], "CANCELLED")
        # repeated delete must not change anything or duplicate rows
        self.flow.delete_posting(r.pending_id, reason="again")
        self.assertEqual(self.db.snapshot().cash_balance, 0)

    def test_edit_income_keeps_transaction_id(self):
        payload = {
            "detected_type": "INCOME", "document_type": "TEXT", "amount": 100_000_000,
            "description": "واریزی شریک", "payment_method": "BANK_TRANSFER",
            "payment_state": "PAID", "is_cheque": False,
            "manager_fee_eligible": False, "confidence": .99,
        }
        r = self.receive(104, "#تست 100 میلیون ورودی", payload)
        first = self.flow.approve_and_post(r.pending_id).posting
        edited = dict(payload)
        edited["amount"] = 150_000_000
        self.flow.begin_posted_revision(r.pending_id, edited)
        second = self.flow.approve_posted_revision(r.pending_id)
        self.assertEqual(first.transaction_id, second.transaction_id)
        self.assertEqual(self.db.cash_balance(), 150_000_000)
        with self.db.read() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1)

    def test_edit_future_cheque_keeps_cheque_and_payment_ids(self):
        payload = {
            "detected_type": "EXPENSE", "document_type": "TEXT",
            "amount": 300_000_000, "final_amount": 300_000_000, "invoice_amount": 300_000_000,
            "paid_amount": 0, "payment_state": "UNPAID", "description": "مصالح با چک",
            "expense_category": "مصالح", "payment_method": "CHEQUE", "is_cheque": True,
            "due_date_shamsi": "1405/07/01", "manager_fee_eligible": True, "confidence": .99,
        }
        r = self.receive(105, "#تست 300 میلیون مصالح با چک", payload)
        first = self.flow.approve_and_post(r.pending_id).posting
        edited = dict(payload)
        edited.update({"amount": 350_000_000, "final_amount": 350_000_000, "invoice_amount": 350_000_000, "due_date_shamsi": "1405/07/10"})
        self.flow.begin_posted_revision(r.pending_id, edited)
        second = self.flow.approve_posted_revision(r.pending_id)
        self.assertEqual(first.expense_id, second.expense_id)
        self.assertEqual(first.cheque_id, second.cheque_id)
        self.assertEqual(first.payment_id, second.payment_id)
        snap = self.db.snapshot()
        self.assertEqual(snap.cash_balance, 0)
        self.assertEqual(snap.construction_cost, 350_000_000)
        self.assertEqual(snap.open_cheque_commitments, 350_000_000)
        self.assertEqual(snap.manager_fee_accrued, 35_000_000)

    def test_delete_cashed_cheque_is_blocked(self):
        payload = {
            "detected_type": "EXPENSE", "document_type": "TEXT",
            "amount": 300_000_000, "final_amount": 300_000_000,
            "payment_state": "UNPAID", "paid_amount": 0,
            "description": "مصالح با چک", "expense_category": "مصالح",
            "payment_method": "CHEQUE", "is_cheque": True,
            "due_date_shamsi": "1405/07/01", "manager_fee_eligible": True, "confidence": .99,
        }
        r = self.receive(106, "#تست چک", payload)
        post = self.flow.approve_and_post(r.pending_id).posting
        self.db.cash_cheque(post.cheque_id, cashed_date="2026-09-23", cashed_date_shamsi="1405/07/01")
        with self.assertRaises(ValueError):
            self.flow.delete_posting(r.pending_id)
        self.assertEqual(self.db.snapshot().cash_balance, -300_000_000)

    def test_type_change_after_approval_is_blocked(self):
        r = self.receive(107, "#تست 100 میلیون بتن", self.paid_expense())
        self.flow.approve_and_post(r.pending_id)
        changed = {
            "detected_type": "INCOME", "amount": 100_000_000, "description": "اشتباه",
            "payment_method": "BANK_TRANSFER", "payment_state": "PAID", "confidence": .9,
        }
        self.flow.begin_posted_revision(r.pending_id, changed)
        with self.assertRaises(ValueError):
            self.flow.approve_posted_revision(r.pending_id)
        self.assertEqual(self.db.snapshot().construction_cost, 100_000_000)


if __name__ == "__main__":
    unittest.main()
