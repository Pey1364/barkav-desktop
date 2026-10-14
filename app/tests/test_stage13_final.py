import json
import tempfile
import unittest
from pathlib import Path

from budget_service import BudgetService
from finance_db import FinanceDB
from telegram_history_import import import_telegram_export, list_imported_pending
from telegram_workflow import TelegramReviewWorkflow


class Stage13FinalTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory();self.root=Path(self.td.name)
        self.db=FinanceDB(self.root/'stage13.sqlite3')
        self.budget=BudgetService(self.db,self.root)

    def tearDown(self):
        self.td.cleanup()

    def test_new_empty_phase_is_visible_immediately(self):
        before=self.budget.phase_summary()
        after_id=self.budget.add_phase_after(before[0]['phase_id'] if before else None,'فاز آزمایشی بدون فعالیت')['phase_id']
        rows=self.budget.phase_summary()
        match=[r for r in rows if r['phase_id']==after_id]
        self.assertEqual(len(match),1)
        self.assertEqual(match[0]['phase'],'فاز آزمایشی بدون فعالیت')
        self.assertEqual(match[0]['estimate'],0)
        self.assertEqual(match[0]['actual'],0)

    def test_telegram_desktop_json_import_is_review_only_and_idempotent(self):
        data={
            'name':'گروه پروژه قدیمی','type':'private_supergroup','id':12345,
            'messages':[
                {'id':1,'type':'message','date':'2026-07-01T10:30:00','from':'PEYMAN','text':'100 میلیون بابت بتن پرداخت کردم'},
                {'id':2,'type':'message','date':'2026-07-02T11:00:00','from':'PEYMAN','text':'سلام بچه ها'},
                {'id':3,'type':'message','date':'2026-07-03T12:00:00','from':'PEYMAN','text':['200 میلیون ',{'type':'bold','text':'ورودی سرمایه'}]},
            ]
        }
        path=self.root/'result.json';path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        result=import_telegram_export(self.db,path)
        self.assertEqual(result.scanned,3)
        self.assertEqual(result.candidates,2)
        self.assertEqual(result.created,2)
        self.assertEqual(self.db.cash_balance(),0)  # no automatic posting
        pending=list_imported_pending(self.db,20)
        self.assertEqual(len(pending),2)
        self.assertTrue(all(p['status'] in ('PENDING_REVIEW','NEEDS_REVIEW') for p in pending))
        # Same export again must not duplicate rows.
        again=import_telegram_export(self.db,path)
        self.assertEqual(again.created,0)
        self.assertEqual(again.duplicates,2)
        self.assertEqual(len(list_imported_pending(self.db,20)),2)

    def test_pending_review_query_can_put_new_backup_rows_inside_the_ui_limit(self):
        workflow = TelegramReviewWorkflow(self.db)
        for message_id in (11, 12, 13):
            workflow.receive_message(
                chat_id=-8900000000000000, message_id=message_id,
                raw_text=f'پرداخت {message_id} میلیون تومان',
                content_type='HISTORICAL_TEXT', message_date='1405/07/01 10:00',
                analysis={'detected_type': 'EXPENSE', 'amount': message_id},
            )

        newest = self.db.list_pending_reviews(limit=2, newest_first=True)
        self.assertEqual([row['telegram_message_id'] for row in newest], [13, 12])
        # Existing callers keep the original oldest-first ordering by default.
        oldest = self.db.list_pending_reviews(limit=2)
        self.assertEqual([row['telegram_message_id'] for row in oldest], [11, 12])

    def test_dashboard_declares_open_cheque_and_exports(self):
        src=(Path(__file__).resolve().parents[1]/'dashboard_stage12.py').read_text(encoding='utf-8')
        self.assertIn('مجموع چک‌های پاس‌نشده',src)
        self.assertIn('export_dashboard_excel',src)
        self.assertIn('export_dashboard_pdf',src)
        self.assertIn('print_dashboard',src)
        self.assertIn("COLORS['rowblue']",src)

    def test_bank_reconciliation_has_signed_color_rules(self):
        src=(Path(__file__).resolve().parents[1]/'dashboard_stage12.py').read_text(encoding='utf-8')
        self.assertIn("int(o.bank_difference)>0",src)
        self.assertIn("int(o.bank_difference)<0",src)
        self.assertIn("fg=COLORS['green']",src)
        self.assertIn("fg=COLORS['red']",src)


if __name__=='__main__':
    unittest.main()
