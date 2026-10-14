import tempfile
import unittest
from pathlib import Path

from finance_db import FinanceDB
from telegram_stage5_workflow import TelegramStage5Workflow
from edit_normalizer import normalize_financial_edit


class Stage5EditNormalizerTests(unittest.TestCase):
    def test_paid_expense_amount_edit_cascades_final_invoice_and_paid(self):
        old = {
            "detected_type": "EXPENSE",
            "document_type": "TEXT",
            "amount": 100_000_000,
            "invoice_amount": 100_000_000,
            "final_amount": 100_000_000,
            "paid_amount": 100_000_000,
            "payment_state": "PAID",
        }
        new = normalize_financial_edit(old, {"amount": 120_000_000})
        self.assertEqual(new["amount"], 120_000_000)
        self.assertEqual(new["final_amount"], 120_000_000)
        self.assertEqual(new["invoice_amount"], 120_000_000)
        self.assertEqual(new["paid_amount"], 120_000_000)

    def test_paid_expense_final_edit_cascades_paid(self):
        old = {
            "detected_type": "EXPENSE", "amount": 100_000_000,
            "invoice_amount": 100_000_000, "final_amount": 100_000_000,
            "paid_amount": 100_000_000, "payment_state": "PAID",
        }
        new = normalize_financial_edit(old, {"final_amount": 120_000_000})
        self.assertEqual(new["final_amount"], 120_000_000)
        self.assertEqual(new["invoice_amount"], 120_000_000)
        self.assertEqual(new["paid_amount"], 120_000_000)

    def test_partial_expense_does_not_auto_increase_paid_amount(self):
        old = {
            "detected_type": "EXPENSE", "amount": 500_000_000,
            "invoice_amount": 500_000_000, "final_amount": 500_000_000,
            "paid_amount": 300_000_000, "payment_state": "PARTIAL",
        }
        new = normalize_financial_edit(old, {"final_amount": 600_000_000})
        self.assertEqual(new["paid_amount"], 300_000_000)
        self.assertEqual(new["payment_state"], "PARTIAL")

    def test_explicit_paid_amount_wins_and_sets_partial(self):
        old = {
            "detected_type": "EXPENSE", "amount": 100_000_000,
            "invoice_amount": 100_000_000, "final_amount": 100_000_000,
            "paid_amount": 100_000_000, "payment_state": "PAID",
        }
        new = normalize_financial_edit(old, {"final_amount": 120_000_000, "paid_amount": 100_000_000})
        self.assertEqual(new["paid_amount"], 100_000_000)
        self.assertEqual(new["payment_state"], "PARTIAL")

    def test_preapproval_edit_then_post_uses_120_everywhere(self):
        with tempfile.TemporaryDirectory() as td:
            db = FinanceDB(Path(td) / "test.sqlite3")
            flow = TelegramStage5Workflow(db)
            payload = {
                "detected_type": "EXPENSE", "document_type": "TEXT",
                "amount": 100_000_000, "invoice_amount": 100_000_000,
                "final_amount": 100_000_000, "paid_amount": 100_000_000,
                "payment_state": "PAID", "description": "خرید بتن",
                "expense_category": "مصالح", "payment_method": "BANK_TRANSFER",
                "is_cheque": False, "manager_fee_eligible": True, "confidence": .99,
            }
            r = flow.receive_message(
                chat_id=-1001, message_id=501, raw_text="#تست 100 میلیون بتن پرداخت کردم",
                content_type="TEXT", message_date="1405/05/19 12:00", analysis=payload,
            )
            flow.begin_preapproval_edit(r.pending_id)
            edited = flow.apply_preapproval_edit(r.pending_id, {"amount": 120_000_000, "description": "خرید بتن اصلاحی"})
            self.assertEqual(edited.payload["final_amount"], 120_000_000)
            self.assertEqual(edited.payload["paid_amount"], 120_000_000)
            posted = flow.approve_and_post(r.pending_id).posting
            with db.read() as con:
                exp = dict(con.execute("SELECT * FROM expenses WHERE expense_id=?", (posted.expense_id,)).fetchone())
                tx = dict(con.execute("SELECT * FROM transactions WHERE transaction_id=?", (posted.transaction_id,)).fetchone())
                pay = dict(con.execute("SELECT * FROM payments WHERE payment_id=?", (posted.payment_id,)).fetchone())
            self.assertEqual(exp["final_amount"], 120_000_000)
            self.assertEqual(tx["amount"], 120_000_000)
            self.assertEqual(pay["amount"], 120_000_000)
            self.assertEqual(db.snapshot().cash_balance, -120_000_000)


if __name__ == "__main__":
    unittest.main()
