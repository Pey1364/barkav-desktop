import tempfile
import unittest
from pathlib import Path

from finance_db import FinanceDB
from telegram_stage5_workflow import TelegramStage5Workflow


class Stage53PaidMappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = FinanceDB(Path(self.tmp.name) / "test.sqlite3")
        self.flow = TelegramStage5Workflow(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def payload(amount: int) -> dict:
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

    def receive(self, mid: int, payload: dict):
        return self.flow.receive_message(
            chat_id=-1001234567890,
            message_id=mid,
            raw_text="#تست 100 میلیون بابت خرید بتن پرداخت کردم",
            content_type="TEXT",
            message_date="1405/05/19 12:00",
            analysis=payload,
        )

    def test_old_100_plus_revised_100_to_120_totals_220_everywhere(self):
        # Old test record from prior versions: legitimate and must remain 100M.
        old = self.receive(1001, self.payload(100_000_000))
        old_post = self.flow.approve_and_post(old.pending_id).posting

        # Current record starts at 100M.
        current = self.receive(1002, self.payload(100_000_000))
        current_post = self.flow.approve_and_post(current.pending_id).posting

        # Reproduce the real bug: expense fields were changed to 120M, but the
        # old payload's paid_amount incorrectly remained 100M while state=PAID.
        revised_payload = self.payload(120_000_000)
        revised_payload["paid_amount"] = 100_000_000
        revised_payload["payment_state"] = "PAID"
        revised_payload["description"] = "خرید بتن اصلاحی"

        self.flow.begin_posted_revision(current.pending_id, revised_payload)
        revised_post = self.flow.approve_posted_revision(current.pending_id)

        # IDs for the edited posting stay stable, so this is an update not a duplicate.
        self.assertEqual(current_post.expense_id, revised_post.expense_id)
        self.assertEqual(current_post.transaction_id, revised_post.transaction_id)
        self.assertEqual(current_post.payment_id, revised_post.payment_id)

        snap = self.db.snapshot()
        self.assertEqual(snap.construction_cost, 220_000_000)
        self.assertEqual(snap.cash_balance, -220_000_000)
        self.assertEqual(snap.manager_fee_accrued, 22_000_000)

        with self.db.read() as con:
            expenses = con.execute("SELECT final_amount FROM expenses WHERE status!='CANCELLED' ORDER BY created_at").fetchall()
            txs = con.execute("SELECT amount FROM transactions WHERE status='POSTED' ORDER BY created_at").fetchall()
            pays = con.execute("SELECT amount FROM payments WHERE status='COMPLETED' ORDER BY created_at").fetchall()
            self.assertEqual([int(r[0]) for r in expenses], [100_000_000, 120_000_000])
            self.assertEqual([int(r[0]) for r in txs], [100_000_000, 120_000_000])
            self.assertEqual([int(r[0]) for r in pays], [100_000_000, 120_000_000])

            # Old record is untouched.
            self.assertEqual(
                int(con.execute("SELECT amount FROM transactions WHERE transaction_id=?", (old_post.transaction_id,)).fetchone()[0]),
                100_000_000,
            )

    def test_explicit_partial_payment_remains_partial(self):
        current = self.receive(1003, self.payload(100_000_000))
        post = self.flow.approve_and_post(current.pending_id).posting

        revised_payload = self.payload(120_000_000)
        revised_payload["paid_amount"] = 100_000_000
        revised_payload["payment_state"] = "PARTIAL"
        self.flow.begin_posted_revision(current.pending_id, revised_payload)
        self.flow.approve_posted_revision(current.pending_id)

        with self.db.read() as con:
            exp = con.execute("SELECT final_amount,status FROM expenses WHERE expense_id=?", (post.expense_id,)).fetchone()
            tx = con.execute("SELECT amount FROM transactions WHERE transaction_id=?", (post.transaction_id,)).fetchone()
            pay = con.execute("SELECT amount FROM payments WHERE payment_id=?", (post.payment_id,)).fetchone()
        self.assertEqual(int(exp[0]), 120_000_000)
        self.assertEqual(exp[1], "PARTIALLY_PAID")
        self.assertEqual(int(tx[0]), 100_000_000)
        self.assertEqual(int(pay[0]), 100_000_000)
        self.assertEqual(self.db.snapshot().cash_balance, -100_000_000)
        self.assertEqual(self.db.snapshot().construction_cost, 120_000_000)


if __name__ == "__main__":
    unittest.main()

class Stage53RepairTests(unittest.TestCase):
    def test_repair_strict_paid_invariant_updates_stale_payment_and_transaction(self):
        with tempfile.TemporaryDirectory() as td:
            db = FinanceDB(Path(td) / "test.sqlite3")
            flow = TelegramStage5Workflow(db)
            payload = Stage53PaidMappingTests.payload(100_000_000)
            r = flow.receive_message(
                chat_id=-1001234567890, message_id=2001,
                raw_text="#تست 100 میلیون بتن پرداخت کردم", content_type="TEXT",
                message_date="1405/05/19 12:00", analysis=payload,
            )
            post = flow.approve_and_post(r.pending_id).posting

            # Simulate the exact legacy inconsistent state from the user's DB:
            # expense final=120 but payment/transaction and stored paid_amount remain 100.
            with db.tx() as con:
                con.execute("UPDATE expenses SET final_amount=120000000,status='PARTIALLY_PAID' WHERE expense_id=?", (post.expense_id,))
                row = con.execute("SELECT plan_json FROM financial_postings WHERE posting_id=?", (post.posting_id,)).fetchone()
                import json
                plan = json.loads(row[0])
                plan["amount"] = 120_000_000
                plan["final_amount"] = 120_000_000
                plan["paid_amount"] = 100_000_000
                plan["payment_state"] = "PAID"
                con.execute("UPDATE financial_postings SET plan_json=? WHERE posting_id=?", (json.dumps(plan, ensure_ascii=False), post.posting_id))

            result = db.repair_paid_expense_invariants(actor_id="test")
            self.assertEqual(result["repaired_count"], 1)
            with db.read() as con:
                exp = con.execute("SELECT final_amount,status FROM expenses WHERE expense_id=?", (post.expense_id,)).fetchone()
                pay = con.execute("SELECT amount,status FROM payments WHERE payment_id=?", (post.payment_id,)).fetchone()
                tx = con.execute("SELECT amount,status FROM transactions WHERE transaction_id=?", (post.transaction_id,)).fetchone()
            self.assertEqual((int(exp[0]), exp[1]), (120_000_000, "PAID"))
            self.assertEqual((int(pay[0]), pay[1]), (120_000_000, "COMPLETED"))
            self.assertEqual((int(tx[0]), tx[1]), (120_000_000, "POSTED"))
            self.assertEqual(db.snapshot().cash_balance, -120_000_000)

    def test_repair_does_not_touch_partial_expense(self):
        with tempfile.TemporaryDirectory() as td:
            db = FinanceDB(Path(td) / "test.sqlite3")
            flow = TelegramStage5Workflow(db)
            payload = Stage53PaidMappingTests.payload(120_000_000)
            payload["paid_amount"] = 100_000_000
            payload["payment_state"] = "PARTIAL"
            r = flow.receive_message(
                chat_id=-1001234567890, message_id=2002,
                raw_text="#تست پرداخت جزئی", content_type="TEXT",
                message_date="1405/05/19 12:00", analysis=payload,
            )
            post = flow.approve_and_post(r.pending_id).posting
            result = db.repair_paid_expense_invariants(actor_id="test")
            self.assertEqual(result["repaired_count"], 0)
            with db.read() as con:
                pay = con.execute("SELECT amount FROM payments WHERE payment_id=?", (post.payment_id,)).fetchone()
            self.assertEqual(int(pay[0]), 100_000_000)
