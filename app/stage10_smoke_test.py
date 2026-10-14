from __future__ import annotations
import tempfile
from pathlib import Path

from finance_db import FinanceDB
from unit_service import UnitService
from budget_service import BudgetService
from revenue_service import RevenueService
from dashboard_service import DashboardService


def main():
    with tempfile.TemporaryDirectory() as td:
        base=Path(__file__).resolve().parent
        db=FinanceDB(Path(td)/'stage10_smoke.sqlite3')

        units=UnitService(db)
        made=units.bulk_create(floor='1',count=2,start_number=1,default_area=100,project_name='Smoke')
        assert len(made)==2 and units.summary()['area']==200.0

        budget=BudgetService(db,base)
        phase=budget.list_phases()[0]
        act=budget.list_activities(phase['phase_id'])[0]
        budget.update_activity_estimate(act['activity_id'],250_000_000)
        assert next(x for x in budget.report_rows() if x['activity_id']==act['activity_id'])['estimate']==250_000_000

        cid=db.create_cheque(amount=50_000_000,issue_date='2026-08-11',due_date='2026-09-11',issue_date_shamsi='1405/05/20',due_date_shamsi='1405/06/20',issuer_name='پیمان',cheque_type='DIGITAL')
        ch=db.get_cheque(cid)
        assert ch['issuer_name']=='پیمان' and ch['cheque_type']=='DIGITAL'

        rev=RevenueService(db)
        sale=rev.create_sale_bundle(project_name='Smoke',block_name='',unit_number='1',buyer_name='Buyer',contract_date_shamsi='1405/05/20',contract_amount=1_000_000_000,installments=[{'amount':1_000_000_000,'due_date_shamsi':'1405/07/20'}])
        rev.update_sale_metadata(sale['sale_id'],buyer_name='Buyer Edited',contract_date_shamsi='1405/05/21')
        assert rev.get_sale(sale['sale_id'])['buyer_name']=='Buyer Edited'

        dash=DashboardService(db)
        rec=dash.record_reconciliation(bank_balance=0,shamsi_date='1405/05/20')
        dash.update_reconciliation(rec['reconciliation_id'],bank_balance=1_000_000,shamsi_date='1405/05/21')
        assert dash.list_reconciliations()[0]['bank_balance']==1_000_000

        print('STAGE 10 SMOKE TEST: OK')
        print('units=2')
        print('budget_edit=250,000,000')
        print('cheque_type=DIGITAL')
        print('sale_edit=OK')
        print('reconciliation_edit=OK')

if __name__=='__main__':
    main()
