from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

from dashboard_service_stage11 import DashboardServiceStage11
from finance_db import FinanceDB
from revenue_service import gregorian_to_shamsi
from unit_service import UnitService


def main():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); db=FinanceDB(root/'stage11_smoke.sqlite3'); svc=DashboardServiceStage11(db,root); units=UnitService(db)
        today=date.today(); sh=lambda d: gregorian_to_shamsi(d)

        # Manager fee without any withdrawal.
        exp_day=today-timedelta(days=2)
        db.create_expense(event_date=exp_day.isoformat(),shamsi_date=sh(exp_day),final_amount=100_000_000,
                          description='Stage11 smoke expense',manager_fee_eligible=True,status='APPROVED')
        mgr=svc.manager_summary_shamsi(sh(exp_day),sh(today))
        assert mgr.manager_fee==10_000_000 and mgr.withdrawals_signed==0 and mgr.balance==10_000_000

        # Current liquidity + upcoming obligations/inflows.
        db.post_transaction(event_date=today.isoformat(),shamsi_date=sh(today),direction='IN',amount=500_000_000,category='CAPITAL')
        due=today+timedelta(days=10)
        db.create_cheque(amount=80_000_000,issue_date=today.isoformat(),issue_date_shamsi=sh(today),due_date=due.isoformat(),due_date_shamsi=sh(due),issuer_name='مالک حساب',issuer_bank='بانک تست',receiver_name='فروشنده')
        svc.revenue.create_sale_bundle(project_name='Smoke',block_name='A',unit_number='1',buyer_name='خریدار تست',contract_date_shamsi=sh(today),contract_amount=150_000_000,installments=[{'amount':150_000_000,'due_date_shamsi':sh(due)}])
        svc.loans.create_loan(lender_name='بانک تست',principal_amount=100_000_000,net_received_amount=100_000_000,received_date_shamsi=sh(today),total_interest=10_000_000,installment_count=1,installment_amount=110_000_000,first_due_date_shamsi=sh(due))
        liq=svc.liquidity_30d_summary()
        assert liq['cheques']==80_000_000 and liq['loan_installments']==110_000_000 and liq['expected_inflows']==150_000_000

        # Editable display IDs must not change the stable internal relation.
        sold=units.list_units()[0]; internal=sold['unit_id']; units.update_unit(internal,display_unit_id='U-010')
        with db.read() as con:
            linked=con.execute("SELECT unit_id FROM sales WHERE status!='CANCELLED' LIMIT 1").fetchone()['unit_id']
        assert linked==internal and units.get_unit(internal)['display_unit_id']=='U-010'

        health=db.health_check(); assert health['sqlite_integrity']=='ok'
        print('STAGE 11 SMOKE TEST: OK')
        print(f"manager_fee={mgr.manager_fee:,}")
        print(f"manager_balance={mgr.balance:,}")
        print(f"30d_obligations={liq['obligations']:,}")
        print(f"30d_expected_inflows={liq['expected_inflows']:,}")
        print(f"30d_projected_balance={liq['projected_balance']:,}")
        print(f"schema={health['schema_version']}")


if __name__=='__main__':
    main()
