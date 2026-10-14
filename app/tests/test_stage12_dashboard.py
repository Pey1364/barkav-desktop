import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from dashboard_service_stage12 import DashboardServiceStage12
from finance_db import FinanceDB
from revenue_service import gregorian_to_shamsi


class Stage12DashboardTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory();self.root=Path(self.td.name)
        self.db=FinanceDB(self.root/'stage12.sqlite3')
        self.svc=DashboardServiceStage12(self.db,self.root)

    def tearDown(self):
        self.td.cleanup()

    def sh(self,d: date)->str:
        return gregorian_to_shamsi(d)

    def test_dashboard_total_out_matches_outflow_tab_rule(self):
        today=date.today();sh=self.sh(today)
        self.db.post_transaction(event_date=today.isoformat(),shamsi_date=sh,direction='IN',amount=500_000_000,category='CAPITAL')
        # Non-construction output: should be counted in dashboard total_out.
        self.db.post_transaction(event_date=today.isoformat(),shamsi_date=sh,direction='OUT',amount=40_000_000,category='LOAN_INSTALLMENT')
        # Construction settlement: belongs to the construction expense, not the خروجی‌ها sub-tab.
        eid=self.db.create_expense(event_date=today.isoformat(),shamsi_date=sh,final_amount=100_000_000,description='بتن',manager_fee_eligible=True,status='PAID')
        self.db.post_transaction(event_date=today.isoformat(),shamsi_date=sh,direction='OUT',amount=100_000_000,category='CONSTRUCTION',expense_id=eid)
        totals=self.svc.financial_flow_totals()
        self.assertEqual(totals['total_in'],500_000_000)
        self.assertEqual(totals['total_out'],40_000_000)
        tab_total=sum(int(r['amount']) for r in self.svc.list_transactions(direction='OUT',nonconstruction_only=True))
        self.assertEqual(totals['total_out'],tab_total)

    def test_cheque_total_includes_historical_non_cancelled(self):
        today=date.today();d1=today+timedelta(days=5);d2=today+timedelta(days=45)
        c1=self.db.create_cheque(amount=60_000_000,issue_date=today.isoformat(),issue_date_shamsi=self.sh(today),due_date=d1.isoformat(),due_date_shamsi=self.sh(d1))
        self.db.create_cheque(amount=90_000_000,issue_date=today.isoformat(),issue_date_shamsi=self.sh(today),due_date=d2.isoformat(),due_date_shamsi=self.sh(d2))
        got=self.svc.cheque_total_summary();self.assertEqual(got['count'],2);self.assertEqual(got['amount'],150_000_000)
        self.db.cancel_cheque(c1)
        got=self.svc.cheque_total_summary();self.assertEqual(got['count'],1);self.assertEqual(got['amount'],90_000_000)

    def test_30d_liquidity_formula_is_cash_plus_buyer_due_minus_cheques_and_loans(self):
        today=date.today();due=today+timedelta(days=10);sh=self.sh(today);dsh=self.sh(due)
        self.db.post_transaction(event_date=today.isoformat(),shamsi_date=sh,direction='IN',amount=400_000_000,category='CAPITAL')
        self.db.create_cheque(amount=120_000_000,issue_date=today.isoformat(),issue_date_shamsi=sh,due_date=due.isoformat(),due_date_shamsi=dsh)
        self.svc.revenue.create_sale_bundle(project_name='P',block_name='A',unit_number='1',buyer_name='خریدار',contract_date_shamsi=sh,contract_amount=200_000_000,installments=[{'amount':200_000_000,'due_date_shamsi':dsh}])
        self.svc.loans.create_loan(lender_name='بانک',principal_amount=80_000_000,net_received_amount=80_000_000,received_date_shamsi=sh,total_interest=20_000_000,installment_count=1,installment_amount=100_000_000,first_due_date_shamsi=dsh,description='وام سرمایه در گردش')
        liq=self.svc.liquidity_30d_summary()
        # cash is 480m because the loan itself actually arrived in petty cash.
        self.assertEqual(liq['cash'],480_000_000)
        self.assertEqual(liq['expected_inflows'],200_000_000)
        self.assertEqual(liq['cheques'],120_000_000)
        self.assertEqual(liq['loan_installments'],100_000_000)
        self.assertEqual(liq['projected_balance'],460_000_000)

    def test_upcoming_loan_rows_have_bank_title_and_date(self):
        today=date.today();due=today+timedelta(days=8)
        self.svc.loans.create_loan(lender_name='بانک ملت',principal_amount=100_000_000,net_received_amount=100_000_000,received_date_shamsi=self.sh(today),installment_count=1,installment_amount=100_000_000,first_due_date_shamsi=self.sh(due),description='وام خرید مصالح')
        rows=self.svc.upcoming_loan_installments()
        self.assertEqual(rows[0]['lender_name'],'بانک ملت')
        self.assertEqual(rows[0]['loan_title'],'وام خرید مصالح')
        self.assertEqual(rows[0]['due_date_shamsi'],self.sh(due))

    def test_project_registration_and_municipal_fields_round_trip(self):
        p=self.svc.project.save_project(name='بارکاو',address='آبادان',postal_code='123',registration_plate='45/678',municipal_file_no='SH-1405-99',description='')
        self.assertEqual(p['registration_plate'],'45/678')
        self.assertEqual(p['municipal_file_no'],'SH-1405-99')

    def test_forecast_exposes_all_four_per_m2_metrics(self):
        # Keep this as a pure report-engine test: no GUI/display dependency.
        self.svc.budget.save_settings(
            gross_area=1_000, saleable_area=800, unit_count=0, unit_areas=[],
            monthly_inflation=0, remaining_months=0, presale_price_per_m2=0,
            end_sale_price_override=None, unbudgeted_misc=0, target_profit_percent=0,
        )
        # New projects now auto-seed the current 32-phase workbook, so this is
        # no longer a zero-budget test. Verify the four independently addressable
        # metrics against their definitions instead of the obsolete Stage-12 zero.
        f=self.svc.budget.forecast()
        self.assertEqual(f.construction_cost_per_gross_m2, round(f.forecast_construction_cost/1000))
        self.assertEqual(f.construction_cost_per_saleable_m2, round(f.forecast_construction_cost/800))
        self.assertEqual(f.total_cost_per_gross_m2, round(f.forecast_total_cost/1000))
        self.assertEqual(f.total_cost_per_saleable_m2, round(f.forecast_total_cost/800))

    def test_stage12_gui_declares_four_per_m2_cards(self):
        src=(Path(__file__).resolve().parents[1]/'dashboard_stage12.py').read_text(encoding='utf-8')
        for label in ('ساخت/متر غیرمفید','ساخت/متر مفید','تمام‌شده/متر غیرمفید','تمام‌شده/متر مفید'):
            self.assertIn(label,src)


if __name__=='__main__':
    unittest.main()
