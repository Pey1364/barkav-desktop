import tempfile
import unittest
from pathlib import Path

from budget_service import BudgetService, norm_fa
from dashboard_service_stage9 import DashboardServiceStage9
from finance_db import FinanceDB
from loan_service import LoanService
from project_service import ProjectService
from telegram_stage3_workflow import TelegramStage3Workflow
from xlsx_simple import parse_phase_budget

BASE=Path(__file__).resolve().parents[1]

class Stage9ManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.db=FinanceDB(self.root/'s9.sqlite3'); self.svc=DashboardServiceStage9(self.db,self.root); self.flow=TelegramStage3Workflow(self.db)
    def tearDown(self):self.tmp.cleanup()

    def post_expense(self,amount=100_000_000):
        payload={'detected_type':'EXPENSE','document_type':'TEXT','amount':amount,'invoice_amount':amount,'final_amount':amount,'discount_amount':0,'paid_amount':amount,'payment_state':'PAID','description':'بتن','expense_category':'مصالح','payment_method':'BANK_TRANSFER','is_cheque':False,'manager_fee_eligible':True,'confidence':.99}
        r=self.flow.receive_message(chat_id=-1001234567890,message_id=9001,raw_text='100 میلیون بتن',content_type='TEXT',message_date='1405/05/19 12:30',analysis=payload);a=self.flow.approve_and_post(r.pending_id);return r,a

    def test_template_has_expected_phase_master(self):
        phases=parse_phase_budget(BASE/'phase_budget_template.xlsx')
        self.assertEqual(len(phases),30); self.assertGreaterEqual(sum(len(p['activities']) for p in phases),290)
        self.assertEqual(phases[0]['phase'],'خرید زمین')

    def test_project_profile_and_document_archive(self):
        p=self.svc.project.save_project(name='بارکاو',address='آبادان',postal_code='1234567890',description='تست')
        self.assertEqual(p['name'],'بارکاو')
        src=self.root/'doc.txt';src.write_text('hello',encoding='utf-8')
        d=self.svc.project.add_document(src,document_type='جواز',title='جواز ساخت')
        self.assertTrue(Path(d['local_path']).exists());self.assertEqual(len(self.svc.project.list_documents()),1)

    def test_loan_registers_inflow_and_installments(self):
        loan=self.svc.loans.create_loan(lender_name='بانک ملت',principal_amount=1_000_000_000,net_received_amount=980_000_000,received_date_shamsi='1405/05/20',interest_rate=20,total_interest=200_000_000,bank_fees=20_000_000,installment_count=12,installment_amount=101_666_667,first_due_date_shamsi='1405/06/20',guarantors='الف',collateral='سند',contract_number='L1')
        self.assertEqual(self.db.cash_balance(),980_000_000); ins=self.svc.loans.list_installments(loan['loan_id']);self.assertEqual(len(ins),12)
        self.svc.loans.pay_installment(ins[0]['loan_installment_id'],amount=10_000_000,paid_date_shamsi='1405/06/20')
        self.assertEqual(self.db.cash_balance(),970_000_000)

    def test_expense_classification_and_report_forecast(self):
        r,a=self.post_expense(); exp_id=self.db.get_financial_posting(r.pending_id)['expense_id']
        phase=[p for p in self.svc.budget.list_phases() if 'اسکلت' in p['name']][0]; act=[a for a in self.svc.budget.list_activities(phase['phase_id']) if a['name'].strip()=='بتن'][0]
        self.svc.budget.classify_expense(exp_id,phase['phase_id'],act['activity_id'],'پیمان','بتن‌فروش')
        rows=self.svc.list_construction_expenses();self.assertIn('اسکلت',rows[0]['phase_name']);self.assertEqual(rows[0]['activity_name_display'].strip(),'بتن')
        self.svc.budget.save_settings(gross_area=2000,saleable_area=1400,unit_count=10,unit_areas=[140]*10,monthly_inflation=3,remaining_months=12,presale_price_per_m2=100_000_000,unbudgeted_misc=50_000_000,target_profit_percent=25)
        f=self.svc.budget.forecast();self.assertGreaterEqual(f.forecast_total_cost,100_000_000);self.assertGreaterEqual(f.total_cost_per_saleable_m2,0)

    def test_global_search_and_sum_source(self):
        self.post_expense(120_000_000); rows=self.svc.search('بتن','همه');self.assertTrue(any(r['amount']==120_000_000 for r in rows))

if __name__=='__main__':unittest.main()
