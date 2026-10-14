from __future__ import annotations
import os,tempfile
from pathlib import Path
import pytest
pytestmark=pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS')!='1',reason='explicit Xvfb UI smoke')
_BOOT=tempfile.TemporaryDirectory()
os.environ.setdefault('TELEGRAM_BOT_TOKEN','ui18-token')
os.environ.setdefault('GEMINI_API_KEY','ui18-key')
os.environ.setdefault('ADMIN_USER_ID','1')
os.environ['STAGE4_DB_PATH']=str(Path(_BOOT.name)/'ui18.sqlite3')
os.environ['STAGE4_SHEETS_ENABLED']='false'
import dashboard_stage18 as m

def test_v18_shell_pending_wizard_and_project_settings():
    app=m.Stage18Dashboard();app.geometry('1280x900+0+0');app.update();app.update_idletasks()
    try:
        assert '18.0' in app.title()
        tabs=[app.notebook.tab(t,'text') for t in app.notebook.tabs()]
        assert 'ثبت دیتا' in tabs and 'سیستم' in tabs and 'تنظیمات' in tabs
        assert tabs.index('سیستم') < tabs.index('تنظیمات')
        assert len(app.phase_buttons)==32
        assert str(app.approval_center.table.tree.cget('selectmode'))=='extended'
        assert len(app.approval_center.table.COLUMNS)==11
        assert app.approval_center.table.COLUMNS[0][1]=='ردیف'
        # Build a pending cheque and verify V18 wizard starts from only four general fields.
        p={'detected_type':'CHEQUE','v18_title':'هزینه ساخت','v18_subtype':'چک','event_date_shamsi':'1405/05/27','amount':30_000_000,'description':'خرید مصالح','payment_method':'CHEQUE','due_date_shamsi':'1405/06/27'}
        m.DB.register_telegram_message(chat_id=-180,message_id=180001,raw_text='چک بابت خرید مصالح',content_type='TEXT',message_date='2026-08-18T12:00:00')
        pid=m.DB.create_or_replace_pending(telegram_chat_id=-180,telegram_message_id=180001,detected_type='CHEQUE',payload=p,confidence=.8,status='PENDING_REVIEW')
        row=m.DB.get_pending_item(pid);row['raw_text']='چک بابت خرید مصالح'
        w=m.TransactionWizard18(app,row,app.rich,lambda:None,lambda:None);w.update();w.update_idletasks()
        try:
            assert set(w.vars)=={'event_date_shamsi','amount','v18_title','v18_subtype'}
            assert w.title_var.get()=='هزینه ساخت' and w.subtype_var.get()=='چک'
        finally:w.destroy()
        ed=m.UnifiedPendingEditor18(app,row,app.rich,lambda:None);ed.geometry('1200x800+0+0');ed.update();ed.update_idletasks()
        try:
            assert ed.title_var.get()=='هزینه ساخت';assert ed.subtype_var.get()=='چک'
            assert 'cheque_status' in ed.vars and 'is_guarantee' in ed.vars
            assert tuple(ed.widgets['cheque_status'].cget('values'))==tuple(m.CHEQUE_STATUS)
        finally:ed.destroy()
        ps=m.ProjectSettingsDialog18(app,lambda:None);ps.update();ps.update_idletasks()
        try:
            assert 'floor_count' in ps.vars
            assert set(ps.team_vars)=={'executor','supervisor','designer'}
        finally:ps.destroy()
    finally:app.destroy()
