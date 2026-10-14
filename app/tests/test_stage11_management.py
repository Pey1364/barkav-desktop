import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from dashboard_service_stage11 import DashboardServiceStage11
from finance_db import FinanceDB
from revenue_service import gregorian_to_shamsi
from unit_service import UnitService


class Stage11ManagementTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory()
        self.root=Path(self.td.name)
        self.db=FinanceDB(self.root/'stage11.sqlite3')
        self.svc=DashboardServiceStage11(self.db,self.root)

    def tearDown(self):
        self.td.cleanup()

    def sh(self,d: date) -> str:
        return gregorian_to_shamsi(d)

    def test_manager_metrics_populate_without_withdrawal(self):
        start=date.today()-timedelta(days=2)
        self.db.create_expense(event_date=start.isoformat(),shamsi_date=self.sh(start),final_amount=100_000_000,
                               description='بتن',manager_fee_eligible=True,status='APPROVED')
        m=self.svc.manager_summary_shamsi(self.sh(start),self.sh(date.today()))
        self.assertEqual(m.manager_fee,10_000_000)
        self.assertEqual(m.withdrawals_signed,0)
        self.assertEqual(m.balance,10_000_000)
        self.assertGreater(m.signed_days,0)
        self.assertGreater(m.signed_average,0)
        self.assertGreater(m.toman_month,0)

    def test_financial_flow_totals_are_separate(self):
        t=date.today();sh=self.sh(t)
        self.db.post_transaction(event_date=t.isoformat(),shamsi_date=sh,direction='IN',amount=150_000_000,category='CAPITAL')
        self.db.post_transaction(event_date=t.isoformat(),shamsi_date=sh,direction='OUT',amount=40_000_000,category='OTHER')
        got=self.svc.financial_flow_totals()
        self.assertEqual(got,{'total_in':150_000_000,'total_out':40_000_000})

    def test_cheque_30d_summary_has_issuer_bank_days_and_surplus(self):
        today=date.today(); due=today+timedelta(days=10)
        self.db.post_transaction(event_date=today.isoformat(),shamsi_date=self.sh(today),direction='IN',amount=100_000_000,category='CAPITAL')
        self.db.create_cheque(amount=60_000_000,issue_date=today.isoformat(),issue_date_shamsi=self.sh(today),
                              due_date=due.isoformat(),due_date_shamsi=self.sh(due),issuer_name='پیمان',issuer_bank='ملت',receiver_name='فروشنده')
        got=self.svc.cheque_30d_summary()
        self.assertEqual(got['count'],1);self.assertEqual(got['amount'],60_000_000);self.assertEqual(got['surplus'],40_000_000)
        self.assertEqual(got['rows'][0]['days_to_due'],10);self.assertEqual(got['rows'][0]['issuer_name'],'پیمان');self.assertEqual(got['rows'][0]['issuer_bank'],'ملت')

    def test_sales_loans_and_liquidity_30d(self):
        today=date.today(); due=today+timedelta(days=15); sh_today=self.sh(today);sh_due=self.sh(due)
        self.db.post_transaction(event_date=today.isoformat(),shamsi_date=sh_today,direction='IN',amount=200_000_000,category='CAPITAL')
        sale=self.svc.revenue.create_sale_bundle(project_name='P',block_name='A',unit_number='1',buyer_name='خریدار',
            contract_date_shamsi=sh_today,contract_amount=300_000_000,installments=[{'amount':300_000_000,'due_date_shamsi':sh_due}])
        loan=self.svc.loans.create_loan(lender_name='بانک',principal_amount=100_000_000,net_received_amount=100_000_000,
            received_date_shamsi=sh_today,total_interest=10_000_000,installment_count=1,installment_amount=110_000_000,first_due_date_shamsi=sh_due)
        sales=self.svc.sales_30d_summary();loans=self.svc.loans_30d_summary();liq=self.svc.liquidity_30d_summary()
        self.assertEqual(sales['upcoming_amount'],300_000_000)
        self.assertEqual(sales['upcoming_rows'][0]['buyer_name'],'خریدار')
        self.assertEqual(loans['upcoming_amount'],110_000_000)
        self.assertEqual(loans['remaining'],110_000_000)
        self.assertEqual(liq['obligations'],110_000_000)
        self.assertEqual(liq['expected_inflows'],300_000_000)
        self.assertEqual(liq['cash'],300_000_000)
        self.assertEqual(liq['conservative_balance'],190_000_000)
        self.assertEqual(liq['projected_balance'],490_000_000)

    def test_editable_unit_display_id_does_not_break_sale_fk(self):
        units=UnitService(self.db)
        u=units.add_unit(floor='1',unit_number='1',area=100,display_unit_id='U-001')
        internal=u['unit_id']
        made=self.svc.revenue.create_sale_bundle(project_name='',block_name='',unit_number='1',buyer_name='الف',
            contract_date_shamsi=self.sh(date.today()),contract_amount=100_000_000,
            installments=[{'amount':100_000_000,'due_date_shamsi':self.sh(date.today()+timedelta(days=20))}])
        self.assertEqual(made['unit_id'],internal)
        units.update_unit(internal,display_unit_id='U-010',parking_display_id='P-010',storage_display_id='S-010')
        changed=units.get_unit(internal)
        self.assertEqual(changed['display_unit_id'],'U-010')
        with self.db.read() as con:
            sale_unit=con.execute('SELECT unit_id FROM sales WHERE sale_id=?',(made['sale_id'],)).fetchone()['unit_id']
        self.assertEqual(sale_unit,internal)

    def test_unpaid_sale_installment_can_be_cancelled_but_paid_one_is_protected(self):
        today=date.today(); sh_today=self.sh(today)
        made=self.svc.revenue.create_sale_bundle(project_name='P',block_name='A',unit_number='9',buyer_name='الف',contract_date_shamsi=sh_today,
            contract_amount=300_000_000,installments=[
                {'amount':100_000_000,'due_date_shamsi':self.sh(today+timedelta(days=10))},
                {'amount':200_000_000,'due_date_shamsi':self.sh(today+timedelta(days=20))},])
        first,second=made['installment_ids']
        self.svc.revenue.cancel_installment(second)
        self.assertEqual(self.svc.revenue.get_sale(made['sale_id'])['contract_amount'],100_000_000)
        receipt=self.svc.revenue.record_received_payment(sale_id=made['sale_id'],amount=10_000_000,received_date_shamsi=sh_today)
        self.svc.revenue.match_receipt_fifo(receipt['received_payment_id'])
        with self.assertRaises(ValueError):self.svc.revenue.cancel_installment(first)

    def test_phase_add_rename_delete(self):
        phases=self.svc.budget.list_phases(); after=phases[0]['phase_id'] if phases else None
        added=self.svc.budget.add_phase_after(after,'فاز تست Stage11')
        self.svc.budget.rename_phase(added['phase_id'],'فاز تست ویرایش‌شده')
        self.assertTrue(any(p['phase_id']==added['phase_id'] and p['name']=='فاز تست ویرایش‌شده' for p in self.svc.budget.list_phases()))
        self.svc.budget.delete_phase(added['phase_id'])
        self.assertFalse(any(p['phase_id']==added['phase_id'] for p in self.svc.budget.list_phases()))

    def test_unpaid_loan_installment_can_be_cancelled(self):
        today=date.today(); due=today+timedelta(days=12)
        loan=self.svc.loans.create_loan(lender_name='بانک تست',principal_amount=90_000_000,net_received_amount=90_000_000,
            received_date_shamsi=self.sh(today),installment_count=1,installment_amount=90_000_000,first_due_date_shamsi=self.sh(due))
        row=self.svc.loans.list_installments(loan['loan_id'])[0]
        self.svc.loans.cancel_installment(row['loan_installment_id'])
        rows=self.svc.loans.list_installments(loan['loan_id'])
        self.assertEqual(rows[0]['status'],'CANCELLED')


if __name__=='__main__':
    unittest.main()
