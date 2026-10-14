from pathlib import Path
from tempfile import TemporaryDirectory
from dashboard_service_stage9 import DashboardServiceStage9
from finance_db import FinanceDB
from telegram_stage3_workflow import TelegramStage3Workflow


def main():
    with TemporaryDirectory() as td:
        root=Path(td);db=FinanceDB(root/'stage9.sqlite3');svc=DashboardServiceStage9(db,root);flow=TelegramStage3Workflow(db)
        svc.project.save_project(name='بارکاو',address='آبادان',postal_code='0000000000')
        payload={'detected_type':'EXPENSE','document_type':'TEXT','amount':100_000_000,'invoice_amount':100_000_000,'final_amount':100_000_000,'discount_amount':0,'paid_amount':100_000_000,'payment_state':'PAID','description':'بتن','expense_category':'مصالح','payment_method':'BANK_TRANSFER','is_cheque':False,'manager_fee_eligible':True,'confidence':.99}
        r=flow.receive_message(chat_id=-1001234567890,message_id=9901,raw_text='100 میلیون بتن',content_type='TEXT',message_date='1405/05/19 12:30',analysis=payload);flow.approve_and_post(r.pending_id)
        loan=svc.loans.create_loan(lender_name='بانک تست',principal_amount=500_000_000,net_received_amount=490_000_000,received_date_shamsi='1405/05/20',total_interest=100_000_000,bank_fees=10_000_000,installment_count=6,first_due_date_shamsi='1405/06/20')
        svc.budget.save_settings(gross_area=1500,saleable_area=1000,monthly_inflation=2.5,remaining_months=10,presale_price_per_m2=80_000_000,target_profit_percent=25)
        f=svc.budget.forecast();o=svc.overview();assert db.health_check()['sqlite_integrity']=='ok';assert len(svc.budget.list_phases())==30;assert len(svc.loans.list_installments(loan['loan_id']))==6
        print('STAGE 9 SMOKE TEST: OK')
        print(f'cash={o.cash_balance:,}')
        print(f'construction={o.construction_cost:,}')
        print(f'manager_fee={o.manager_fee_accrued:,}')
        print(f'forecast_total={f.forecast_total_cost:,}')
        print(f'phase_count={len(svc.budget.list_phases())}')

if __name__=='__main__':main()
