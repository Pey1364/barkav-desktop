from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from finance_db import FinanceDB


def run_golden_scenario(db: FinanceDB) -> dict:
    # 1) +1B cash into petty-cash account
    db.post_transaction(event_date="2026-08-01", direction="IN", amount=1_000_000_000,
                        category="PROJECT_FUNDING", description="Golden test: funding")

    # 2) 200M cash construction expense
    ex_cash = db.create_expense(event_date="2026-08-02", final_amount=200_000_000,
                                description="Golden test: concrete cash", category="CONCRETE")
    tx_cash = db.post_transaction(event_date="2026-08-02", direction="OUT", amount=200_000_000,
                                  category="EXPENSE_PAYMENT", expense_id=ex_cash,
                                  description="Golden test: concrete cash payment")
    db.add_payment(expense_id=ex_cash, payment_date="2026-08-02", amount=200_000_000,
                   method="BANK_TRANSFER", transaction_id=tx_cash)

    # 3) 300M construction expense via future cheque: cost/manager fee now, cash later
    ex_cheque = db.create_expense(event_date="2026-08-03", final_amount=300_000_000,
                                  description="Golden test: rebar cheque", category="REBAR")
    chq = db.create_cheque(expense_id=ex_cheque, amount=300_000_000,
                           issue_date="2026-08-03", due_date="2026-10-03",
                           description="Golden test: rebar cheque")
    db.add_payment(expense_id=ex_cheque, payment_date="2026-10-03", amount=300_000_000,
                   method="CHEQUE", cheque_id=chq, status="PENDING")

    # 4) 50M loan installment: OUT, not construction cost
    db.post_transaction(event_date="2026-08-04", direction="OUT", amount=50_000_000,
                        category="LOAN_INSTALLMENT", description="Golden test: loan installment")

    # 5) 20M contractor fee withdrawal: OUT, not construction cost
    db.post_transaction(event_date="2026-08-05", direction="OUT", amount=20_000_000,
                        category="CONTRACTOR_FEE", description="Golden test: manager withdrawal")

    before_cash = db.snapshot(as_of="2026-08-05")

    # 6) cheque cashes later
    db.cash_cheque(chq, cashed_date="2026-10-03")
    after_cash = db.snapshot(as_of="2026-10-03")

    expected_before = {
        "cash_balance": 730_000_000,
        "construction_cost": 550_000_000,
        "manager_fee_accrued": 50_000_000,
        "manager_withdrawals": 20_000_000,
        "manager_balance": 30_000_000,
        "open_cheque_commitments": 300_000_000,
        "free_cash_after_cheques": 430_000_000,
    }
    expected_after = {
        "cash_balance": 430_000_000,
        "construction_cost": 550_000_000,
        "manager_fee_accrued": 50_000_000,
        "manager_withdrawals": 20_000_000,
        "manager_balance": 30_000_000,
        "open_cheque_commitments": 0,
        "free_cash_after_cheques": 430_000_000,
    }

    before = before_cash.__dict__
    after = after_cash.__dict__
    return {
        "before_cheque_cash": before,
        "expected_before": expected_before,
        "before_passed": before == expected_before,
        "after_cheque_cash": after,
        "expected_after": expected_after,
        "after_passed": after == expected_after,
        "health": db.health_check(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Peyman V2 isolated financial test mode")
    parser.add_argument("--db", help="Optional SQLite path. Default: temporary DB")
    args = parser.parse_args()

    if args.db:
        db_path = Path(args.db)
        db = FinanceDB(db_path)
        result = run_golden_scenario(db)
    else:
        with tempfile.TemporaryDirectory() as td:
            db = FinanceDB(Path(td) / "test.sqlite3")
            result = run_golden_scenario(db)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["before_passed"] and result["after_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
