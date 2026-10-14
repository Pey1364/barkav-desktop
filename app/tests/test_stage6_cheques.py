import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from finance_db import FinanceDB


class Stage6ChequeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = FinanceDB(Path(self.tmp.name) / "test.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def make_cheque_expense(self, amount=300_000_000, due_days=3):
        today = date.today()
        ex = self.db.create_expense(
            event_date=today.isoformat(), final_amount=amount,
            description="بتن با چک", category="MATERIALS", manager_fee_eligible=True,
        )
        chq = self.db.create_cheque(
            amount=amount, issue_date=today.isoformat(),
            due_date=(today + timedelta(days=due_days)).isoformat(),
            expense_id=ex, due_date_shamsi="1405/05/25",
            receiver_name="فروشنده بتن", description="خرید بتن",
        )
        pay = self.db.add_payment(
            expense_id=ex, payment_date=today.isoformat(), amount=amount,
            method="CHEQUE", cheque_id=chq, status="PENDING", description="پرداخت با چک",
        )
        return ex, chq, pay

    def test_returned_cheque_keeps_commitment_and_no_cash_effect(self):
        ex, chq, _ = self.make_cheque_expense()
        self.assertEqual(self.db.snapshot().open_cheque_commitments, 300_000_000)
        self.assertEqual(self.db.snapshot().cash_balance, 0)
        changed = self.db.return_cheque(chq)
        self.assertTrue(changed)
        self.assertEqual(self.db.get_cheque(chq)["status"], "RETURNED")
        self.assertEqual(self.db.snapshot().open_cheque_commitments, 300_000_000)
        self.assertEqual(self.db.snapshot().cash_balance, 0)
        self.assertEqual(self.db.construction_cost(), 300_000_000)
        self.assertEqual(self.db.manager_fee_accrued(), 30_000_000)

    def test_cash_cheque_creates_cash_out_once_and_completes_payment(self):
        ex, chq, pay = self.make_cheque_expense()
        today = date.today().isoformat()
        tx1 = self.db.cash_cheque(chq, cashed_date=today)
        tx2 = self.db.cash_cheque(chq, cashed_date=today)
        self.assertEqual(tx1, tx2)
        self.assertEqual(self.db.snapshot().cash_balance, -300_000_000)
        self.assertEqual(self.db.snapshot().open_cheque_commitments, 0)
        with self.db.read() as con:
            payment = dict(con.execute("SELECT * FROM payments WHERE payment_id=?", (pay,)).fetchone())
            tx_count = con.execute("SELECT COUNT(*) FROM transactions WHERE expense_id=? AND status='POSTED'", (ex,)).fetchone()[0]
        self.assertEqual(payment["status"], "COMPLETED")
        self.assertEqual(payment["transaction_id"], tx1)
        self.assertEqual(tx_count, 1)
        self.assertEqual(self.db.construction_cost(), 300_000_000)
        self.assertEqual(self.db.manager_fee_accrued(), 30_000_000)

    def test_cancel_cheque_cancels_payment_but_not_expense(self):
        ex, chq, pay = self.make_cheque_expense()
        self.db.cancel_cheque(chq)
        self.assertEqual(self.db.get_cheque(chq)["status"], "CANCELLED")
        self.assertEqual(self.db.snapshot().open_cheque_commitments, 0)
        self.assertEqual(self.db.snapshot().cash_balance, 0)
        self.assertEqual(self.db.construction_cost(), 300_000_000)
        self.assertEqual(self.db.manager_fee_accrued(), 30_000_000)
        with self.db.read() as con:
            p = dict(con.execute("SELECT * FROM payments WHERE payment_id=?", (pay,)).fetchone())
            e = dict(con.execute("SELECT * FROM expenses WHERE expense_id=?", (ex,)).fetchone())
        self.assertEqual(p["status"], "CANCELLED")
        self.assertEqual(e["status"], "APPROVED")

    def test_reminder_schedule_is_idempotent(self):
        _, chq, _ = self.make_cheque_expense(due_days=7)
        c1 = self.db.ensure_cheque_reminders(chq, reminder_times=("09:00", "14:00", "19:00"), days_before=5)
        c2 = self.db.ensure_cheque_reminders(chq, reminder_times=("09:00", "14:00", "19:00"), days_before=5)
        self.assertEqual(c1, 18)  # day -5 through due day = 6 days x 3 times
        self.assertEqual(c2, 0)
        self.assertEqual(self.db.reminder_counts().get("SCHEDULED"), 18)

    def test_cashing_cancels_future_reminders(self):
        _, chq, _ = self.make_cheque_expense(due_days=3)
        self.db.ensure_cheque_reminders(chq, reminder_times=("09:00",), days_before=5)
        self.assertGreater(self.db.reminder_counts().get("SCHEDULED", 0), 0)
        self.db.cash_cheque(chq, cashed_date=date.today().isoformat())
        self.assertEqual(self.db.reminder_counts().get("SCHEDULED", 0), 0)

    def test_mark_pending_due_changes_status_only(self):
        _, chq, _ = self.make_cheque_expense(due_days=2)
        before = self.db.snapshot()
        self.assertTrue(self.db.mark_cheque_pending_due(chq))
        after = self.db.snapshot()
        self.assertEqual(self.db.get_cheque(chq)["status"], "PENDING_DUE")
        self.assertEqual(before.cash_balance, after.cash_balance)
        self.assertEqual(before.construction_cost, after.construction_cost)
        self.assertEqual(before.open_cheque_commitments, after.open_cheque_commitments)

    def test_cash_cheque_enqueues_cheque_transaction_payment_and_expense_updates(self):
        ex, chq, pay = self.make_cheque_expense()
        # Clear creation queue so only cashing effects are inspected.
        with self.db.tx() as con:
            con.execute("UPDATE sync_queue SET status='SYNCED'")
        self.db.cash_cheque(chq, cashed_date=date.today().isoformat())
        with self.db.read() as con:
            rows = con.execute(
                "SELECT entity_type, entity_id FROM sync_queue WHERE status='PENDING' ORDER BY sync_id"
            ).fetchall()
        pairs = {(r["entity_type"], r["entity_id"]) for r in rows}
        self.assertIn(("cheque", chq), pairs)
        self.assertIn(("payment", pay), pairs)
        self.assertIn(("expense", ex), pairs)
        self.assertTrue(any(t == "transaction" for t, _ in pairs))



if __name__ == "__main__":
    unittest.main()
