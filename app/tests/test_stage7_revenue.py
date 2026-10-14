import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


from finance_db import FinanceDB
from revenue_service import RevenueService, gregorian_to_shamsi


def sh(d: date) -> str:
    return gregorian_to_shamsi(d)


class Stage7RevenueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = FinanceDB(Path(self.tmp.name) / "t.sqlite3")
        self.rev = RevenueService(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def make_sale(self, amounts=(3_000_000_000, 3_000_000_000, 4_000_000_000), dues=None):
        today = date.today()
        dues = dues or [today, today + timedelta(days=30), today + timedelta(days=60)]
        return self.rev.create_sale_bundle(
            project_name="بارکاو",
            block_name="A",
            unit_number="12",
            floor="3",
            area=120,
            parking="P12",
            storage="S12",
            buyer_name="علی رضایی",
            buyer_phone="09120000000",
            contract_number="1405-12",
            contract_date_shamsi=sh(today),
            contract_amount=sum(amounts),
            installments=[
                {"amount": a, "due_date_shamsi": sh(d), "sequence_no": i}
                for i, (a, d) in enumerate(zip(amounts, dues), 1)
            ],
        )

    def test_sale_contract_does_not_change_cash(self):
        ids = self.make_sale()
        self.assertTrue(ids["sale_id"].startswith("SALE-"))
        self.assertEqual(self.db.snapshot().cash_balance, 0)
        d = self.rev.buyer_dashboard()
        self.assertEqual(d["contract_sales"], 10_000_000_000)
        self.assertEqual(d["cash_received"], 0)
        self.assertEqual(d["receivable"], 10_000_000_000)

    def test_receipt_enters_cash_but_does_not_close_installment_until_match(self):
        ids = self.make_sale()
        sale_id = ids["sale_id"]
        rp = self.rev.record_received_payment(
            sale_id=sale_id,
            amount=3_000_000_000,
            received_date_shamsi=sh(date.today()),
        )
        self.assertEqual(self.db.snapshot().cash_balance, 3_000_000_000)
        installments = self.rev.list_installments(sale_id)
        self.assertEqual(sum(i["paid_amount"] for i in installments), 0)
        self.assertEqual(self.rev.get_received_payment(rp["received_payment_id"])["status"], "UNMATCHED")
        summary = self.rev.sale_summary(sale_id)
        self.assertEqual(summary.cash_received, 3_000_000_000)
        self.assertEqual(summary.receivable, 7_000_000_000)

    def test_match_requires_explicit_service_call_and_closes_fifo(self):
        ids = self.make_sale()
        sale_id = ids["sale_id"]
        rp = self.rev.record_received_payment(
            sale_id=sale_id,
            amount=3_000_000_000,
            received_date_shamsi=sh(date.today()),
        )
        preview = self.rev.suggest_fifo_allocations(rp["received_payment_id"])
        self.assertEqual(preview["allocations"][0]["allocate"], 3_000_000_000)
        self.assertEqual(self.rev.list_installments(sale_id)[0]["paid_amount"], 0)
        result = self.rev.match_receipt_fifo(rp["received_payment_id"])
        self.assertEqual(result["unallocated"], 0)
        first = self.rev.list_installments(sale_id)[0]
        self.assertEqual(first["paid_amount"], 3_000_000_000)
        self.assertEqual(first["status"], "PAID")
        self.assertEqual(self.rev.get_received_payment(rp["received_payment_id"])["status"], "MATCHED")

    def test_partial_payment_keeps_remainder_and_reminders(self):
        today = date.today() + timedelta(days=2)
        ids = self.make_sale(amounts=(2_000_000_000,), dues=[today])
        sale_id = ids["sale_id"]
        ins_id = ids["installment_ids"][0]
        self.rev.ensure_installment_reminders(ins_id, reminder_time="09:00", days_before=3, days_after=7)
        rp = self.rev.record_received_payment(
            sale_id=sale_id,
            amount=1_500_000_000,
            received_date_shamsi=sh(date.today()),
        )
        self.rev.match_receipt_fifo(rp["received_payment_id"])
        ins = self.rev.get_installment(ins_id)
        self.assertEqual(ins["status"], "PARTIALLY_PAID")
        self.assertEqual(ins["amount"] - ins["paid_amount"], 500_000_000)
        with self.db.read() as con:
            scheduled = con.execute(
                "SELECT COUNT(*) FROM reminders WHERE entity_type='INSTALLMENT' AND entity_id=? AND status='SCHEDULED'",
                (ins_id,),
            ).fetchone()[0]
        self.assertGreater(scheduled, 0)

    def test_full_payment_cancels_future_installment_reminders(self):
        due = date.today() + timedelta(days=2)
        ids = self.make_sale(amounts=(2_000_000_000,), dues=[due])
        sale_id = ids["sale_id"]
        ins_id = ids["installment_ids"][0]
        created = self.rev.ensure_installment_reminders(ins_id, reminder_time="09:00", days_before=3, days_after=7)
        self.assertEqual(created, 9)
        rp = self.rev.record_received_payment(
            sale_id=sale_id,
            amount=2_000_000_000,
            received_date_shamsi=sh(date.today()),
        )
        self.rev.match_receipt_fifo(rp["received_payment_id"])
        with self.db.read() as con:
            scheduled = con.execute(
                "SELECT COUNT(*) FROM reminders WHERE entity_type='INSTALLMENT' AND entity_id=? AND status='SCHEDULED'",
                (ins_id,),
            ).fetchone()[0]
        self.assertEqual(scheduled, 0)
        self.assertEqual(self.rev.get_sale(sale_id)["status"], "COMPLETED")

    def test_cancel_unmatched_receipt_voids_cash_transaction(self):
        ids = self.make_sale()
        rp = self.rev.record_received_payment(
            sale_id=ids["sale_id"], amount=500_000_000, received_date_shamsi=sh(date.today())
        )
        self.assertEqual(self.db.snapshot().cash_balance, 500_000_000)
        self.assertTrue(self.rev.cancel_unmatched_receipt(rp["received_payment_id"]))
        self.assertEqual(self.db.snapshot().cash_balance, 0)
        self.assertEqual(self.rev.get_received_payment(rp["received_payment_id"])["status"], "CANCELLED")

    def test_overdue_partial_keeps_partial_status_but_dashboard_counts_overdue_remaining(self):
        due = date.today() - timedelta(days=2)
        ids = self.make_sale(amounts=(2_000_000_000,), dues=[due])
        sale_id = ids["sale_id"]
        rp = self.rev.record_received_payment(
            sale_id=sale_id, amount=1_500_000_000, received_date_shamsi=sh(date.today())
        )
        self.rev.match_receipt_fifo(rp["received_payment_id"])
        ins = self.rev.get_installment(ids["installment_ids"][0])
        self.assertEqual(ins["status"], "PARTIALLY_PAID")
        self.assertEqual(self.rev.buyer_dashboard()["overdue"], 500_000_000)


if __name__ == '__main__':
    unittest.main()
