from __future__ import annotations
import os, tempfile, unittest
from pathlib import Path

# dashboard imports require config; keep the import isolated from any real project DB.
_BOOT=tempfile.TemporaryDirectory()
os.environ.setdefault('TELEGRAM_BOT_TOKEN','test-token')
os.environ.setdefault('GEMINI_API_KEY','test-key')
os.environ.setdefault('ADMIN_USER_ID','1')
os.environ['STAGE4_DB_PATH']=str(Path(_BOOT.name)/'bootstrap.sqlite3')
os.environ['STAGE4_SHEETS_ENABLED']='false'

import dashboard_stage17_5 as v175
from finance_db import FinanceDB


class DummyRich:
    def __init__(self): self.docs=[]
    def add_financial_document(self,pending_id,payload,raw_text='',links=None):
        self.docs.append((pending_id,dict(payload),list(links or [])))
        return 'DOC_TEST'


class MultiCheque175Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=FinanceDB(Path(self.tmp.name)/'multi.sqlite3')
        self.old_db=v175.DB; self.old_raw=v175._raw_text_for_pending; self.old_mark=v175._mark_nonfinancial_approved
        v175.DB=self.db; v175._raw_text_for_pending=lambda pid:'#چک پنج فقره چک'; v175._mark_nonfinancial_approved=lambda *a,**k: None
    def tearDown(self):
        v175.DB=self.old_db; v175._raw_text_for_pending=self.old_raw; v175._mark_nonfinancial_approved=self.old_mark; self.tmp.cleanup()
    def test_five_cheques_create_five_independent_rows_not_one_sum_row(self):
        amounts=[11_000_000,22_000_000,33_000_000,44_000_000,55_000_000]
        cheques=[]
        for i,a in enumerate(amounts,1):
            cheques.append({'amount':a,'issue_date_shamsi':'1405/05/20','due_date_shamsi':f'1405/0{5+i}/20' if i<5 else '1405/10/20','cheque_serial':f'CH{i}','issuer_bank':'ملت'})
        p={'detected_type':'CHEQUE','payment_state':'UNKNOWN','payment_method':'CHEQUE','description':'پنج چک','cheques':cheques}
        rich=DummyRich(); msg=v175.approve_v175('PEN_TEST',p,rich)
        rows=self.db.list_cheques(open_only=False,limit=100)
        self.assertEqual(len(rows),5)
        self.assertEqual(sorted(int(r['amount']) for r in rows),sorted(amounts))
        self.assertFalse(any(int(r['amount'])==sum(amounts) for r in rows))
        self.assertIn('5',msg)
        self.assertEqual(len(rich.docs),1)
        self.assertEqual(len(rich.docs[0][2]),5)

if __name__=='__main__': unittest.main()
