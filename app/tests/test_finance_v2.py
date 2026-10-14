import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance_db import FinanceDB
from test_mode import run_golden_scenario


class FinanceV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = FinanceDB(Path(self.tmp.name) / "finance.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def test_golden_scenario(self):
        result = run_golden_scenario(self.db)
        self.assertTrue(result["before_passed"], result)
        self.assertTrue(result["after_passed"], result)

    def test_void_is_idempotent(self):
        tx = self.db.post_transaction(event_date="2026-08-01", direction="IN", amount=100_000_000,
                                      category="PROJECT_FUNDING")
        self.assertEqual(self.db.cash_balance(), 100_000_000)
        self.db.void_transaction(tx, reason="test")
        self.assertEqual(self.db.cash_balance(), 0)
        self.db.void_transaction(tx, reason="test again")
        self.assertEqual(self.db.cash_balance(), 0)

    def test_cancel_old_expense_recalculates_manager_fee(self):
        ex = self.db.create_expense(event_date="2026-01-01", final_amount=100_000_000,
                                    description="old expense")
        self.assertEqual(self.db.construction_cost(), 100_000_000)
        self.assertEqual(self.db.manager_fee_accrued(), 10_000_000)
        self.db.cancel_expense(ex, reason="cancelled transaction")
        self.assertEqual(self.db.construction_cost(), 0)
        self.assertEqual(self.db.manager_fee_accrued(), 0)

    def test_manager_balance_deducts_receipts_after_rate(self):
        self.db.create_expense(event_date="2026-01-01", final_amount=1_000_000,
                               construction_stage="اسکلت", description="construction")
        self.db.create_expense(event_date="2026-01-02", final_amount=400_000,
                               construction_stage="خرید زمین", description="land")
        self.db.post_transaction(event_date="2026-01-03", direction="OUT", amount=100_000,
                                 category="CONTRACTOR_FEE", description="manager withdrawal")

        snapshot = self.db.snapshot()
        self.assertEqual(snapshot.construction_cost, 1_100_000)
        self.assertEqual(self.db.land_purchase_cost(), 400_000)
        self.assertEqual(snapshot.manager_fee_accrued, 100_000)
        self.assertEqual(snapshot.manager_withdrawals, 100_000)
        self.assertEqual(snapshot.manager_balance, 0)

    def test_manager_toman_day(self):
        self.db.create_expense(event_date="2026-01-01", final_amount=500_000_000,
                               description="creates 50m manager receivable")
        exposure = self.db.manager_exposure("2026-01-01", "2026-01-10")
        self.assertEqual(exposure.creditor_days, 10)
        self.assertEqual(exposure.creditor_toman_days, 500_000_000)
        self.assertEqual(exposure.average_creditor_balance, 50_000_000)

    def test_cheque_does_not_hit_cash_until_cashed(self):
        ex = self.db.create_expense(event_date="2026-08-01", final_amount=100_000_000,
                                    description="cheque expense")
        chq = self.db.create_cheque(expense_id=ex, amount=100_000_000,
                                    issue_date="2026-08-01", due_date="2026-10-01")
        self.db.add_payment(expense_id=ex, payment_date="2026-10-01", amount=100_000_000,
                            method="CHEQUE", cheque_id=chq, status="PENDING")
        self.assertEqual(self.db.construction_cost(), 100_000_000)
        self.assertEqual(self.db.manager_fee_accrued(), 10_000_000)
        self.assertEqual(self.db.cash_balance(), 0)
        self.assertEqual(self.db.open_cheque_commitments(), 100_000_000)
        self.db.cash_cheque(chq, cashed_date="2026-10-01")
        self.assertEqual(self.db.cash_balance(), -100_000_000)
        self.assertEqual(self.db.construction_cost(), 100_000_000)
        self.assertEqual(self.db.manager_fee_accrued(), 10_000_000)
        self.assertEqual(self.db.open_cheque_commitments(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
