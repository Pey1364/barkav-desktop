from datetime import date, timedelta
from pathlib import Path
import tempfile

from finance_db import FinanceDB


def main():
    with tempfile.TemporaryDirectory() as td:
        db = FinanceDB(Path(td) / "stage6_smoke.sqlite3")
        today = date.today()
        amount = 300_000_000
        ex = db.create_expense(
            event_date=today.isoformat(), final_amount=amount,
            description="خرید بتن با چک", category="MATERIALS",
            manager_fee_eligible=True,
        )
        chq = db.create_cheque(
            amount=amount, issue_date=today.isoformat(),
            due_date=(today + timedelta(days=3)).isoformat(),
            expense_id=ex, due_date_shamsi="1405/05/25",
            receiver_name="فروشنده بتن", description="خرید بتن",
        )
        db.add_payment(
            expense_id=ex, payment_date=today.isoformat(), amount=amount,
            method="CHEQUE", cheque_id=chq, status="PENDING",
        )
        reminders = db.ensure_cheque_reminders(
            chq, reminder_times=("09:00", "14:00", "19:00"), days_before=5,
        )
        before = db.snapshot()
        assert before.cash_balance == 0
        assert before.construction_cost == amount
        assert before.manager_fee_accrued == 30_000_000
        assert before.open_cheque_commitments == amount
        assert reminders == 18

        db.return_cheque(chq)
        returned = db.snapshot()
        assert returned.cash_balance == 0
        assert returned.open_cheque_commitments == amount

        tx = db.cash_cheque(chq, cashed_date=today.isoformat())
        after = db.snapshot()
        assert tx.startswith("TX-")
        assert after.cash_balance == -amount
        assert after.construction_cost == amount
        assert after.manager_fee_accrued == 30_000_000
        assert after.open_cheque_commitments == 0
        assert db.get_cheque(chq)["status"] == "CASHED"

        print("STAGE 6 SMOKE TEST: OK")
        print(f"expense={amount}")
        print(f"manager_fee={after.manager_fee_accrued}")
        print(f"cash_after_clearing={after.cash_balance}")
        print(f"open_cheques={after.open_cheque_commitments}")
        print(f"scheduled_reminders_initial={reminders}")


if __name__ == "__main__":
    main()
