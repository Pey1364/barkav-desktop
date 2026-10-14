from __future__ import annotations
import os,sys,tempfile,shutil
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
_BOOT=tempfile.TemporaryDirectory();os.environ['STAGE4_DB_PATH']=str(Path(_BOOT.name)/'stage184_ui.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN','ui184-token');os.environ.setdefault('GEMINI_API_KEY','ui184-gemini');os.environ.setdefault('ADMIN_USER_ID','184');os.environ.setdefault('GROUP_CHAT_ID','-100184')
pytestmark=pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS')!='1',reason='GUI tests opt-in')


def test_dashboard_184_font_number_rtl_order_theme_and_checks():
    from dashboard_stage18_4 import Stage184Dashboard
    import tkinter.ttk as ttk
    app=Stage184Dashboard();app.update_idletasks();app.update()
    try:
        assert app.title().endswith('18.4')
        assert getattr(app,'quick_theme_button',None) is not None
        assert getattr(app,'_brand_host_184',None) is not None
        assert [app.fin_nb.tab(t,'text') for t in app.fin_nb.tabs()]==['کلیه تراکنش‌ها','هزینه ساخت','چک‌ها','ورودی‌ها','خروجی‌ها','تسهیلات','داکیومنت‌ها']
        # Legacy SmartTables now keep Segoe UI and Persianize displayed numeric content.
        table=app.all_tx_table;table.set_rows([{'transaction_id':'T-184','amount':1234567}],lambda r:['1405/05/28','IN','1,234,567','TEST','-','-','شرح 123','0','POSTED','T-184'])
        vals=list(table.tree.item(table.tree.get_children()[0],'values'))
        assert any('۱,۲۳۴,۵۶۷' in str(v) for v in vals)
        st=ttk.Style(app);assert 'Segoe UI' in str(st.lookup(table.style_name,'font'))
        assert getattr(table.tree,'_barkav_checkboxes_184',False)
        assert table.tree._barkav_grid_overlay.column_color=='#122436'
        assert table.edit_handler==app.edit_transaction_row
        assert app.document_table.edit_handler==app.edit_document_row_184
    finally:app.destroy()


def test_project_settings_184_usd_removed_units_rtl_settings_usd_present():
    import tkinter as tk
    from dashboard_stage18_4 import ProjectSettingsDialog184,SettingsTab184
    root=tk.Tk();root.withdraw();d=ProjectSettingsDialog184(root,None);d.update_idletasks();d.update()
    try:
        assert 'usd_rate_current' not in d.vars
        assert tuple(str(x) for x in d.floor_tree.cget('displaycolumns'))==('areas','count','floor')
        assert str(d.floor_tree.column('floor','anchor'))=='e'
        d.nb.select(d._project_tabs['مشخصات پایه']);label,headers,rows=d._active_export_data();assert all(r[0]!='قیمت روز دلار (تومان)' for r in rows)
    finally:d.destroy()
    host=tk.Frame(root);s=SettingsTab184(host,lambda o,n:None);s.pack();root.update_idletasks()
    try:
        assert 'usd_rate_current' in s.vars and hasattr(s,'usd_status')
    finally:s.destroy();root.destroy()


def test_data_entry_184_vivid_rows_and_chat_history_attachment(monkeypatch,tmp_path):
    from datetime import datetime
    from dashboard_stage18_4 import Stage184Dashboard,DB
    from attachment_service import AttachmentService
    import dashboard_stage18_4 as d184
    app=Stage184Dashboard();app.update_idletasks();app.update();ac=app.approval_center
    try:
        mid=184000001
        DB.register_telegram_message(chat_id=-184,message_id=mid,raw_text='رسید تست',content_type='text',message_date=datetime.now().isoformat(),state='RECEIVED')
        pid=DB.create_or_replace_pending(telegram_chat_id=-184,telegram_message_id=mid,detected_type='EXPENSE',payload={'v18_title':'هزینه ساخت','v18_subtype':'نقدی','amount':1234,'event_date_shamsi':'1405/05/28'},confidence=.9,status='PENDING_REVIEW')
        ac.filter.set('Pending');ac.refresh();iid=next(i for i,r in ac.table.iid_to_row.items() if str(r.get('pending_id'))==str(pid));ac.table.tree.selection_set(iid)
        hist=tmp_path/'chat.json';hist.write_text('{"messages":[]}',encoding='utf-8')
        monkeypatch.setattr(d184.filedialog,'askopenfilename',lambda **k:str(hist));monkeypatch.setattr(d184.messagebox,'showinfo',lambda *a,**k:None);monkeypatch.setattr(d184.messagebox,'showerror',lambda *a,**k:None)
        ac.attach_chat_history()
        docs=AttachmentService(DB,d184.BASE_DIR).list_for_entities([('PENDING',str(pid))])
        assert any(x.get('document_type')=='CHAT_HISTORY' for x in docs)
        bg=ac.table.tree.tag_configure('tx183_هزینه_ساخت').get('background')
        assert bg=='#F5C842'
        assert ac.table.tree._barkav_grid_overlay.column_color in ('#122436','#EEF1F4')
        assert hasattr(ac,'chat_attach_button') and hasattr(ac,'chat_view_button')
    finally:app.destroy()


def test_project_center_184_counter_persian_shortcut_logo_and_close(tmp_path):
    from project_center_stage18_4 import ProjectCenter184
    (tmp_path/'assets').mkdir();(tmp_path/'data').mkdir();(tmp_path/'secrets.local.json').write_text('{}',encoding='utf-8')
    for f in ('barkav_brand_header.png','BARKAV_18_4.ico','BARKAV.ico'):
        shutil.copy2(ROOT/'assets'/f,tmp_path/'assets'/f)
    app=ProjectCenter184(tmp_path);app.update_idletasks();app.update()
    try:
        tabs=app.nb.tabs();assert len(tabs)==1
        text=app.nb.tab(tabs[0],'text');assert 'PRJ-۰۰۱' in text and '×' in text
        assert app.info.get()=='پروژه‌های باز: ۰    •    کل پروژه‌ها: ۱'
        assert len(list((tmp_path/'data'/'project_shortcuts').glob('*.barkav')))==1
        assert any(hasattr(w,'_brand_photo') for w in app.winfo_children()[0].winfo_children())
        pid=next(iter(app._tab_project_ids.values()));app.close_project(pid);app.update_idletasks();assert len(app.nb.tabs())==0
    finally:app.destroy()
