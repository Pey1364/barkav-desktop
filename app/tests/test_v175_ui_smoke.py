from __future__ import annotations
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
import pytest

pytestmark = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='Tk smoke is run explicitly under Xvfb')

_BOOT=tempfile.TemporaryDirectory()
os.environ.setdefault('TELEGRAM_BOT_TOKEN','ui-test-token')
os.environ.setdefault('GEMINI_API_KEY','ui-test-key')
os.environ.setdefault('ADMIN_USER_ID','1')
os.environ['STAGE4_DB_PATH']=str(Path(_BOOT.name)/'ui.sqlite3')
os.environ['STAGE4_SHEETS_ENABLED']='false'

import dashboard_stage17_5 as m


def test_dashboard_and_data_entry_17_5_smoke():
    app=m.Stage175Dashboard(); app.geometry('1280x900+0+0'); app.update(); app.update_idletasks()
    try:
        assert '17.5' in app.title()
        tabs=[app.notebook.tab(t,'text') for t in app.notebook.tabs()]
        assert 'داشبورد' in tabs and 'ثبت دیتا' in tabs and 'پیمانکار-بازار' in tabs
        assert len(app.nav_buttons)==len(tabs)
        assert {'gross_area','saleable_area','unit_count'} <= set(app.report_entries)
        assert str(app.approval_center.table.tree.cget('selectmode'))=='extended'
        assert len(app.phase_buttons)==32
        # All 32 buttons must remain inside a 1280px-class window.
        last=app.phase_buttons[32]
        assert last.winfo_rootx()+last.winfo_width() <= app.winfo_rootx()+app.winfo_width()+2

        cheques=[{'amount':i*10_000_000,'issue_date_shamsi':'1405/05/20','due_date_shamsi':f'1405/{5+i:02d}/20','cheque_serial':f'S{i}','issuer_bank':'ملت','status':'ISSUED'} for i in range(1,6)]
        payload={'detected_type':'CHEQUE','amount':10_000_000,'payment_method':'CHEQUE','payment_state':'UNKNOWN','event_date_shamsi':'1405/05/20','description':'پنج چک تست','cheques':cheques}
        m.DB.register_telegram_message(chat_id=-175,message_id=175175,raw_text='پنج چک تست',content_type='PHOTO',message_date='1405/05/20 10:00')
        pid=m.DB.create_or_replace_pending(telegram_chat_id=-175,telegram_message_id=175175,detected_type='CHEQUE',payload=payload,confidence=.9)
        row=m.DB.get_pending_item(pid); row['raw_text']='پنج چک تست'
        ed=m.UnifiedPendingEditor175(app,row,app.rich,lambda:None); ed.geometry('1180x720+20+20'); ed.update(); ed.update_idletasks()
        try:
            assert ed.fixed_action_bar.winfo_ismapped()
            assert ed.fixed_action_bar.winfo_rooty()+ed.fixed_action_bar.winfo_height() <= ed.winfo_rooty()+ed.winfo_height()+2
            assert len(ed.multi_cheque_tree.get_children())==5
            assert ed.multi_cheque_vscroll.winfo_ismapped()
            assert ed.multi_cheque_hscroll.winfo_ismapped()
            vals=set(ed.widgets['cheque_status'].cget('values'))
            assert {'صادرشده','در انتظار سررسید','پاس‌شده','برگشتی','لغوشده / باطل‌شده'} <= vals
            before=ed.form_canvas.yview()[0]
            ed._form_wheel(SimpleNamespace(widget=ed.widgets['description'],delta=-120)); ed.update_idletasks()
            assert ed.form_canvas.yview()[0] > before
        finally:
            ed.destroy()
    finally:
        app.destroy()
