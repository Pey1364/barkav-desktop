import tempfile
import unittest
from pathlib import Path

from budget_service import BudgetService
from finance_db import FinanceDB
from revenue_service import RevenueService
from unit_service import UnitService


class Stage10ManagementTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory()
        self.db=FinanceDB(Path(self.td.name)/'t.sqlite3')
        self.base=Path(__file__).resolve().parents[1]

    def tearDown(self):
        self.td.cleanup()

    def test_cheque_has_issuer_and_type(self):
        cid=self.db.create_cheque(amount=50_000_000,issue_date='2026-08-11',due_date='2026-09-11',
            issue_date_shamsi='1405/05/20',due_date_shamsi='1405/06/20',issuer_name='پیمان',cheque_type='DIGITAL')
        r=self.db.get_cheque(cid)
        self.assertEqual(r['issuer_name'],'پیمان')
        self.assertEqual(r['cheque_type'],'DIGITAL')

    def test_unit_master_codes_and_bulk(self):
        u=UnitService(self.db)
        rows=u.bulk_create(floor='1',count=3,start_number=1,default_area=100)
        self.assertEqual([x['unit_id'] for x in rows],['U-001','U-002','U-003'])
        all_rows=u.list_units()
        self.assertEqual(all_rows[0]['parking_id'],'P-001')
        self.assertEqual(all_rows[0]['storage_id'],'S-001')
        self.assertEqual(u.summary()['count'],3)
        self.assertEqual(u.summary()['area'],300.0)

    def test_existing_available_unit_is_reused_when_sold(self):
        u=UnitService(self.db)
        unit=u.add_unit(floor='1',unit_number='1',area=120,project_name='X',block_name='A')
        r=RevenueService(self.db)
        result=r.create_sale_bundle(project_name='X',block_name='A',unit_number='1',floor='1',area=120,parking='',storage='',
            buyer_name='Buyer',contract_number='1',contract_date_shamsi='1405/05/20',contract_amount=1_000_000_000,
            installments=[{'amount':1_000_000_000,'due_date_shamsi':'1405/06/20'}])
        self.assertEqual(result['unit_id'],unit['unit_id'])
        self.assertEqual(u.get_unit(unit['unit_id'])['status'],'SOLD')

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "phase_budget_current.xlsx").exists(), 'needs the private 32-phase workbook phase_budget_current.xlsx, which is not shipped in this repository')
    def test_budget_is_editable_and_phase_can_be_added(self):
        b=BudgetService(self.db,self.base)
        p=b.list_phases()[0]
        act=b.list_activities(p['phase_id'])[0]
        b.update_activity_estimate(act['activity_id'],123_456_789)
        row=next(x for x in b.report_rows() if x['activity_id']==act['activity_id'])
        self.assertEqual(row['estimate'],123_456_789)
        added=b.add_phase_after(p['phase_id'],'فاز تست 10')
        self.assertTrue(any(x['phase_id']==added['phase_id'] for x in b.list_phases()))


if __name__=='__main__':unittest.main()

class Stage10EditingTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory()
        self.db=FinanceDB(Path(self.td.name)/'t.sqlite3')
        self.base=Path(__file__).resolve().parents[1]

    def tearDown(self):
        self.td.cleanup()

    def test_cheque_edit_issue_due_issuer_type(self):
        cid=self.db.create_cheque(amount=10_000_000,issue_date='2026-08-11',due_date='2026-09-11',
            issue_date_shamsi='1405/05/20',due_date_shamsi='1405/06/20')
        self.db.update_cheque_details(cid,amount=12_500_000,issue_date='2026-08-12',issue_date_shamsi='1405/05/21',
            due_date='2026-09-21',due_date_shamsi='1405/06/30',issuer_name='صادرکننده تست',cheque_type='DIGITAL')
        r=self.db.get_cheque(cid)
        self.assertEqual(r['amount'],12_500_000)
        self.assertEqual(r['issue_date_shamsi'],'1405/05/21')
        self.assertEqual(r['due_date_shamsi'],'1405/06/30')
        self.assertEqual(r['cheque_type'],'DIGITAL')

    def test_reconciliation_can_edit_and_soft_delete(self):
        from dashboard_service import DashboardService
        svc=DashboardService(self.db)
        r=svc.record_reconciliation(bank_balance=100_000_000,shamsi_date='1405/05/20',notes='اول')
        r2=svc.update_reconciliation(r['reconciliation_id'],bank_balance=120_000_000,shamsi_date='1405/05/21',notes='اصلاح')
        self.assertEqual(r2['bank_balance'],120_000_000)
        self.assertEqual(r2['shamsi_date'],'1405/05/21')
        svc.delete_reconciliation(r['reconciliation_id'])
        self.assertEqual(svc.list_reconciliations(),[])

    def test_sale_and_installment_edit(self):
        rev=RevenueService(self.db)
        made=rev.create_sale_bundle(project_name='X',block_name='A',unit_number='1',buyer_name='الف',contract_date_shamsi='1405/05/20',
            contract_amount=1_000_000_000,installments=[{'amount':500_000_000,'due_date_shamsi':'1405/06/20'},{'amount':500_000_000,'due_date_shamsi':'1405/07/20'}])
        rev.update_sale_metadata(made['sale_id'],buyer_name='ب',contract_date_shamsi='1405/05/21',contract_number='C-1')
        sale=rev.get_sale(made['sale_id']);self.assertEqual(sale['buyer_name'],'ب');self.assertEqual(sale['contract_date_shamsi'],'1405/05/21')
        iid=made['installment_ids'][0]
        rev.update_installment_details(iid,amount=600_000_000,due_date_shamsi='1405/06/25',description='اصلاح قسط')
        inst=rev.get_installment(iid);self.assertEqual(inst['amount'],600_000_000);self.assertEqual(inst['due_date_shamsi'],'1405/06/25')
        self.assertEqual(rev.get_sale(made['sale_id'])['contract_amount'],1_100_000_000)
