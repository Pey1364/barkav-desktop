from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

from dashboard_service_stage12 import DashboardServiceStage12
from finance_db import FinanceDB
from revenue_service import gregorian_to_shamsi


def main():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);db=FinanceDB(root/'stage12_smoke.sqlite3');svc=DashboardServiceStage12(db,root)
        today=date.today();due=today+timedelta(days=10);sh=gregorian_to_shamsi(today);dsh=gregorian_to_shamsi(due)
        db.post_transaction(event_date=today.isoformat(),shamsi_date=sh,direction='IN',amount=500_000_000,category='CAPITAL')
        db.post_transaction(event_date=today.isoformat(),shamsi_date=sh,direction='OUT',amount=20_000_000,category='OTHER')
        eid=db.create_expense(event_date=today.isoformat(),shamsi_date=sh,final_amount=100_000_000,description='بتن',manager_fee_eligible=True,status='PAID')
        db.post_transaction(event_date=today.isoformat(),shamsi_date=sh,direction='OUT',amount=100_000_000,category='CONSTRUCTION',expense_id=eid)
        db.create_cheque(amount=80_000_000,issue_date=today.isoformat(),issue_date_shamsi=sh,due_date=due.isoformat(),due_date_shamsi=dsh,issuer_name='پیمان',issuer_bank='ملت')
        svc.revenue.create_sale_bundle(project_name='P',block_name='A',unit_number='1',buyer_name='خریدار',contract_date_shamsi=sh,contract_amount=120_000_000,installments=[{'amount':120_000_000,'due_date_shamsi':dsh}])
        svc.loans.create_loan(lender_name='بانک',principal_amount=50_000_000,net_received_amount=50_000_000,received_date_shamsi=sh,installment_count=1,installment_amount=50_000_000,first_due_date_shamsi=dsh,description='وام تست')
        flows=svc.financial_flow_totals();liq=svc.liquidity_30d_summary();cheques=svc.cheque_total_summary();loans=svc.loans_30d_summary()
        assert flows['total_out']==20_000_000
        assert cheques['amount']==80_000_000
        assert liq['projected_balance']==420_000_000  # 430 cash +120 due -80 cheque -50 loan
        assert loans['upcoming_rows'][0]['loan_title']=='وام تست'
        svc.project.save_project(name='بارکاو',address='آبادان',postal_code='1',registration_plate='12/34',municipal_file_no='M-1')
        p=svc.project.get_project();assert p['registration_plate']=='12/34' and p['municipal_file_no']=='M-1'
        print('STAGE 12 SMOKE TEST: OK')
        print(f"dashboard_out={flows['total_out']:,}")
        print(f"cheques_total={cheques['amount']:,}")
        print(f"projected_30d={liq['projected_balance']:,}")


if __name__=='__main__':
    main()
