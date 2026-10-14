from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

from finance_db import FinanceDB
from revenue_service import RevenueService, gregorian_to_shamsi


def main():
    with tempfile.TemporaryDirectory() as td:
        db = FinanceDB(Path(td) / "stage7.sqlite3")
        rev = RevenueService(db)
        today = date.today()
        ids = rev.create_sale_bundle(
            project_name="بارکاو",
            block_name="A",
            unit_number="12",
            floor="3",
            area=120,
            buyer_name="خریدار تست",
            contract_date_shamsi=gregorian_to_shamsi(today),
            contract_amount=10_000_000_000,
            installments=[
                {"amount": 3_000_000_000, "due_date_shamsi": gregorian_to_shamsi(today), "sequence_no": 1},
                {"amount": 3_000_000_000, "due_date_shamsi": gregorian_to_shamsi(today + timedelta(days=30)), "sequence_no": 2},
                {"amount": 4_000_000_000, "due_date_shamsi": gregorian_to_shamsi(today + timedelta(days=60)), "sequence_no": 3},
            ],
        )
        assert db.snapshot().cash_balance == 0
        receipt = rev.record_received_payment(
            sale_id=ids["sale_id"], amount=3_000_000_000,
            received_date_shamsi=gregorian_to_shamsi(today),
        )
        assert db.snapshot().cash_balance == 3_000_000_000
        assert rev.list_installments(ids["sale_id"])[0]["paid_amount"] == 0
        preview = rev.suggest_fifo_allocations(receipt["received_payment_id"])
        assert preview["allocations"][0]["allocate"] == 3_000_000_000
        rev.match_receipt_fifo(receipt["received_payment_id"])
        summary = rev.sale_summary(ids["sale_id"])
        assert summary.cash_received == 3_000_000_000
        assert summary.receivable == 7_000_000_000
        assert rev.list_installments(ids["sale_id"])[0]["status"] == "PAID"
        print("STAGE 7 SMOKE TEST: OK")
        print("contract=10,000,000,000")
        print("cash_received=3,000,000,000")
        print("receivable=7,000,000,000")
        print("first_installment=PAID")
        print("cash_balance=3,000,000,000")


if __name__ == "__main__":
    main()
