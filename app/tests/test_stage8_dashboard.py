import tempfile
import unittest
from pathlib import Path

from dashboard_service import DashboardService
from finance_db import FinanceDB
from telegram_stage3_workflow import TelegramStage3Workflow


class Stage8DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = FinanceDB(Path(self.tmp.name) / 's8.sqlite3')
        self.service = DashboardService(self.db)
        self.flow = TelegramStage3Workflow(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def receive(self, mid, text, payload, message_date='1405/05/19 12:30'):
        return self.flow.receive_message(
            chat_id=-1001234567890, message_id=mid, raw_text=text,
            content_type='TEXT', message_date=message_date, analysis=payload,
        )

    def post_expense(self, mid=1, amount=100_000_000):
        payload = {
            'detected_type':'EXPENSE','document_type':'TEXT','amount':amount,
            'invoice_amount':amount,'final_amount':amount,'discount_amount':0,
            'paid_amount':amount,'payment_state':'PAID','description':'خرید بتن',
            'expense_category':'مصالح','payment_method':'BANK_TRANSFER','is_cheque':False,
            'manager_fee_eligible':True,'confidence':.99,
        }
        r = self.receive(mid, f'#تست {amount} خرید بتن پرداخت کردم', payload)
        a = self.flow.approve_and_post(r.pending_id)
        return r, a

    def test_overview_combines_finance_revenue_and_health(self):
        self.post_expense()
        sale = self.service.revenue.create_sale_bundle(
            project_name='بارکاو', block_name='A', unit_number='12', floor='3', area=120,
            parking='P12', storage='S12', buyer_name='علی', buyer_phone='0912',
            contract_number='C12', contract_date_shamsi='1405/05/20', contract_amount=1_000_000_000,
            installments=[{'due_date_shamsi':'1405/05/20','amount':1_000_000_000}], source='TEST'
        )
        self.service.revenue.record_received_payment(
            sale_id=sale['sale_id'], amount=300_000_000, received_date_shamsi='1405/05/21',
            payer_name='علی', description='قسط', source='TEST'
        )
        o = self.service.overview()
        self.assertEqual(o.construction_cost, 110_000_000)
        self.assertEqual(o.manager_fee_accrued, 10_000_000)
        self.assertEqual(o.contract_sales, 1_000_000_000)
        self.assertEqual(o.buyer_cash_received, 300_000_000)
        self.assertEqual(o.buyer_receivable, 700_000_000)
        self.assertEqual(o.cash_balance, 200_000_000)
        self.assertEqual(o.sqlite_integrity, 'ok')

    def test_reconciliation_persists_difference(self):
        self.post_expense()
        r = self.service.record_reconciliation(
            bank_balance=-90_000_000, shamsi_date='1405/05/19', notes='test'
        )
        self.assertEqual(r['system_balance'], -100_000_000)
        self.assertEqual(r['difference'], 10_000_000)
        rows = self.service.list_reconciliations()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['shamsi_date'], '1405/05/19')

    def test_gui_edit_reuses_same_component_ids(self):
        r, a = self.post_expense()
        before = self.db.get_financial_posting(r.pending_id)
        self.service.edit_posting(r.pending_id, {'amount':120_000_000,'final_amount':120_000_000})
        after = self.db.get_financial_posting(r.pending_id)
        self.assertEqual(before['posting_id'], after['posting_id'])
        self.assertEqual(before['expense_id'], after['expense_id'])
        self.assertEqual(before['transaction_id'], after['transaction_id'])
        self.assertEqual(before['payment_id'], after['payment_id'])
        snap = self.db.snapshot()
        self.assertEqual(snap.construction_cost, 132_000_000)
        self.assertEqual(snap.cash_balance, -120_000_000)
        self.assertEqual(snap.manager_fee_accrued, 12_000_000)

    def test_gui_delete_soft_deletes_and_recalculates(self):
        r, a = self.post_expense()
        self.service.delete_posting(r.pending_id)
        snap = self.db.snapshot()
        self.assertEqual(snap.construction_cost, 0)
        self.assertEqual(snap.cash_balance, 0)
        self.assertEqual(snap.manager_fee_accrued, 0)
        post = self.db.get_financial_posting(r.pending_id)
        self.assertEqual(post['status'], 'DELETED')

    def test_manager_daily_series_matches_end_snapshot(self):
        self.post_expense()
        rows = self.service.manager_daily_series('1405/05/19','1405/05/21')
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]['balance'], self.db.snapshot().manager_balance)
        exp = self.service.manager_exposure_shamsi('1405/05/19','1405/05/21')
        self.assertEqual(exp.creditor_days, 3)
        self.assertEqual(exp.creditor_toman_days, 30_000_000)

    def test_posting_list_exposes_stable_pending_id(self):
        r, a = self.post_expense()
        rows = self.service.list_postings()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['pending_id'], r.pending_id)
        self.assertEqual(rows[0]['display_amount'], 100_000_000)
        self.assertEqual(rows[0]['description'], 'خرید بتن')


if __name__ == '__main__':
    unittest.main()
