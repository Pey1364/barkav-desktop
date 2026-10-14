from __future__ import annotations
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from finance_db import FinanceDB
from phase_intelligence_v175 import suggest_phase, apply_suggestion_to_payload


class FakeRich:
    def __init__(self, active=(7,)):
        self.active=set(active)
        self.phases=[
            {'phase_no':7,'phase':'آماده‌سازی، تخریب و عملیات خاکی'},
            {'phase_no':8,'phase':'اجرای اسکلت'},
            {'phase_no':9,'phase':'چاه'},
            {'phase_no':16,'phase':'تأسیسات'},
        ]
        self.items={
            7:[{'description':'خاکبرداری دستی','section':'عملیات خاکی'},{'description':'خاکبرداری ماشینی','section':'عملیات خاکی'}],
            8:[{'description':'اجرای اسکلت','section':'اسکلت'},{'description':'جرثقیل','section':'سقف'}],
            9:[{'description':'لوله سیمانی چاه','section':'چاه'}],
            16:[{'description':'لوازم برق ساختمان','section':'تأسیسات'}],
        }
    def list_phase_summary(self): return self.phases
    def get_phase_progress(self):
        return {p['phase_no']:{'status':'ACTIVE' if p['phase_no'] in self.active else 'NOT_STARTED'} for p in self.phases}
    def subphase_candidates(self,no,query=''): return self.items.get(int(no),[]) if no else []


class PhaseIntelligence175Tests(unittest.TestCase):
    def test_pickaxe_repair_routes_to_active_excavation_and_manual_subphase(self):
        s=suggest_phase('هزینه تعمیر پیکور برای ادامه خاکبرداری',FakeRich((7,)))
        self.assertIsNotNone(s); self.assertEqual(s.phase_no,7); self.assertEqual(s.sub_phase,'خاکبرداری دستی')
        self.assertGreaterEqual(s.confidence,0.57)
    def test_explicit_well_text_wins_when_multiple_phases_active(self):
        s=suggest_phase('خرید لوله سیمانی برای چاه',FakeRich((7,8,9)))
        self.assertIsNotNone(s); self.assertEqual(s.phase_no,9); self.assertIn('لوله سیمانی',s.sub_phase)
    def test_pending_assignment_is_suggestion_not_posting(self):
        p,s,changed=apply_suggestion_to_payload({'detected_type':'EXPENSE','description':'تعمیر پیکور'},'تعمیر پیکور',FakeRich((7,)))
        self.assertTrue(changed); self.assertEqual(p['phase_assignment_source'],'PHASE_INTELLIGENCE_V175'); self.assertTrue(p['main_phase'].startswith('07'))


class ChequeLifecycle175Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=FinanceDB(Path(self.tmp.name)/'db.sqlite3')
        today=date.today(); self.ch=self.db.create_cheque(amount=10_000_000,issue_date=today.isoformat(),due_date=(today+timedelta(days=3)).isoformat(),receiver_name='فروشنده')
    def tearDown(self): self.tmp.cleanup()
    def test_manual_lifecycle_transitions_audited_and_safe(self):
        self.db.set_cheque_lifecycle_status(self.ch,'PENDING_DUE')
        self.assertEqual(self.db.get_cheque(self.ch)['status'],'PENDING_DUE')
        self.db.set_cheque_lifecycle_status(self.ch,'RETURNED')
        self.assertEqual(self.db.get_cheque(self.ch)['status'],'RETURNED')
        self.db.set_cheque_lifecycle_status(self.ch,'ISSUED')
        self.assertEqual(self.db.get_cheque(self.ch)['status'],'ISSUED')
        self.db.set_cheque_lifecycle_status(self.ch,'CASHED',event_date=date.today().isoformat())
        self.assertEqual(self.db.get_cheque(self.ch)['status'],'CASHED')
        self.assertEqual(self.db.snapshot().cash_balance,-10_000_000)
    def test_guarantee_cheque_cannot_be_cashed_through_financial_path(self):
        today=date.today(); g=self.db.create_cheque(amount=2_000_000,issue_date=today.isoformat(),due_date=today.isoformat(),is_guarantee=True)
        with self.assertRaises(ValueError): self.db.set_cheque_lifecycle_status(g,'CASHED',event_date=today.isoformat())


if __name__=='__main__': unittest.main()
