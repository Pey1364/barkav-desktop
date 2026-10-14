from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytestmark = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='explicit Xvfb UI smoke')
_BOOT = tempfile.TemporaryDirectory()
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'ui182-token')
os.environ.setdefault('GEMINI_API_KEY', 'ui182-key')
os.environ.setdefault('ADMIN_USER_ID', '1')
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'ui182.sqlite3')
os.environ['STAGE4_SHEETS_ENABLED'] = 'false'

import dashboard_stage18_2 as m


@pytest.fixture(scope='module')
def app():
    a = m.Stage182Dashboard(); a.geometry('1500x950+0+0'); a.update(); a.update_idletasks()
    yield a
    try:
        pending = a.tk.call('after', 'info')
        if isinstance(pending, str): pending = (pending,) if pending else ()
        for aid in pending:
            try: a.after_cancel(aid)
            except Exception: pass
    except Exception:
        pass
    try: a.destroy()
    except Exception: pass


@pytest.fixture(autouse=True)
def _clean_review_rows_between_ui_tests(app):
    with m.DB.tx() as con:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        for table in ('rich_ui_hidden_reviews','posting_revisions','receipt_analyses','integration_events',
                      'financial_postings','pending_items','telegram_messages'):
            if table in names:
                con.execute(f'DELETE FROM {table}')
    ac = getattr(app, 'approval_center', None)
    if ac:
        ac._undo_stack.clear(); ac._redo_stack.clear(); ac._copied_rows.clear(); ac.filter.set('Pending'); ac.refresh()
    app.update(); app.update_idletasks()
    yield


def _pending(payload: dict, msgid: int):
    m.DB.register_telegram_message(chat_id=-182, message_id=msgid, raw_text='تست ۱۸.۲', content_type='TEXT', message_date='2026-08-19T10:00:00')
    pid = m.DB.create_or_replace_pending(telegram_chat_id=-182, telegram_message_id=msgid,
                                         detected_type=payload.get('detected_type', 'UNKNOWN'),
                                         payload=payload, confidence=.8, status='PENDING_REVIEW')
    row = dict(m.DB.get_pending_item(pid)); row['raw_text'] = 'تست ۱۸.۲'
    return row


def test_partner_wizard_preserves_common_values_and_conditional_fields(app):
    row = _pending({'detected_type': 'INCOME', 'v18_title': 'ورودی', 'v18_subtype': 'شرکا/قرض'}, 182001)
    w = m.TransactionWizard182(app, row, app.rich, lambda: None, lambda: None); w.update(); w.update_idletasks()
    try:
        w.vars['event_date_shamsi'].set('1405/05/28'); w.vars['amount'].set('۱۲,۳۴۵,۶۷۸')
        w.vars['v18_title'].set('ورودی'); w._title_changed('ورودی'); w.vars['v18_subtype'].set('شرکا/قرض'); w._sub_changed('شرکا/قرض')
        w.next(); w.update(); w.update_idletasks()
        assert w.payload['event_date_shamsi'] == '1405/05/28' and w.payload['amount'] == 12_345_678
        w.vars['partner_name'].set('سایر'); w.update_idletasks(); assert str(w.widgets['partner_other_name'].cget('state')) == 'normal'
        w.vars['partner_other_name'].set('رضا'); w.next(); w.update(); w.update_idletasks()
        assert w.vars['partner_kind'].get() == 'تزریق پول' and str(w.widgets['loan_days'].cget('state')) == 'disabled'
        w.vars['partner_kind'].set('قرض'); w.vars['loan_days'].set('۳۰'); w.update(); w.update_idletasks()
        assert str(w.widgets['loan_days'].cget('state')) == 'normal' and m.normalize_shamsi(w.vars['partner_return_date'].get())
        w.next(); w.update(); w.update_idletasks()
        assert w.payload['partner_name'] == 'رضا' and w.payload['partner_kind'] == 'قرض' and w.payload['loan_days'] == 30
    finally: w.destroy()


def test_installment_wizard_carries_selected_loan_to_later_steps(app):
    loan = m.LoanService(m.DB).create_loan(lender_name='بانک تست', principal_amount=60_000_000,
        net_received_amount=60_000_000, received_date_shamsi='1405/01/01', installment_count=6,
        first_due_date_shamsi='1405/02/01', description='وام تست ۱۸.۲', register_cash=False)
    row = _pending({'detected_type': 'OUTFLOW', 'v18_title': 'خروجی', 'v18_subtype': 'اقساط', 'event_date_shamsi': '1405/05/28', 'amount': 10_000_000}, 182002)
    w = m.TransactionWizard182(app, row, app.rich, lambda: None, lambda: None); w.update(); w.update_idletasks()
    try:
        w.vars['v18_title'].set('خروجی'); w._title_changed('خروجی'); w.vars['v18_subtype'].set('اقساط'); w._sub_changed('اقساط'); w.next(); w.update()
        selected = next(x for x in list(w.widgets['loan_id'].cget('values')) if str(x).startswith((loan['loan_id'], str(loan['loan_name']))))
        w.vars['loan_id'].set(selected); w._loan_selected(selected)
        assert w.payload['loan_bank'] == 'بانک تست' and int(w.payload['loan_total_amount']) == 60_000_000
        w.next(); w.update(); assert w.vars['loan_bank'].get() == 'بانک تست'
        w.next(); w.update(); assert m.parse_int(w.vars['installment_count'].get()) == 6
        w.next(); w.update(); assert m.parse_int(w.vars['remaining_installments'].get()) == 5
    finally: w.destroy()


def test_full_editor_partner_other_and_kind_are_dynamic(app):
    row = _pending({'detected_type': 'INCOME', 'v18_title': 'ورودی', 'v18_subtype': 'شرکا/قرض', 'event_date_shamsi': '1405/05/28', 'amount': 5_000_000,
                    'partner_name': 'رضا', 'partner_other_name': 'رضا', 'partner_kind': 'تزریق پول'}, 182003)
    ed = m.UnifiedPendingEditor182(app, row, app.rich, lambda: None); ed.geometry('1200x800+0+0'); ed.update(); ed.update_idletasks()
    try:
        assert ed.vars['partner_name'].get() == 'سایر' and ed.vars['partner_other_name'].get() == 'رضا'
        assert str(ed.widgets['loan_days'].cget('state')) == 'disabled'
        ed.vars['partner_kind'].set('قرض'); ed.vars['loan_days'].set('۱۵'); ed.update(); ed.update_idletasks()
        p = ed.payload_from_form(); assert p['partner_name'] == 'رضا' and p['partner_kind'] == 'قرض' and p['loan_days'] == 15
    finally: ed.destroy()


def test_live_thousands_separator_formats_while_typing(app):
    var = m.tk.StringVar(master=app, value=''); entry = m.ttk.Entry(app, textvariable=var); m.v18.bind_grouped_number(entry, var)
    var.set('12500000'); app.update_idletasks(); assert var.get() == '12,500,000'
    var.set('۱۲۳۴۵۶۷'); app.update_idletasks(); assert m.parse_int(var.get()) == 1_234_567 and (',' in var.get() or '٬' in var.get())
    entry.destroy()


def test_cash_wizard_reactive_discount_debt_and_scroll_contract(app):
    row = _pending({'detected_type':'EXPENSE','v18_title':'هزینه ساخت','v18_subtype':'نقدی','event_date_shamsi':'1405/05/28','amount':4_000_000}, 182010)
    w = m.TransactionWizard182(app,row,app.rich,lambda:None,lambda:None); w.update()
    try:
        w.vars['v18_title'].set('هزینه ساخت'); w._title_changed('هزینه ساخت'); assert w.subtype_var.get() == 'نقدی'; w.next(); w.update()
        assert [[fd.key for fd in g] for g in w.pages[1:-1]] == [['payer_name','receiver_name','issuer_name'],['description','payment_method'],['invoice_amount','final_amount','discount_amount'],['payment_state','total_debt','remaining_debt'],['main_phase','sub_phase']]
        assert isinstance(w._page_canvas,m.tk.Canvas)
        w.page_index=3; w._show_page(); w.vars['invoice_amount'].set('10,000,000'); w.vars['final_amount'].set('8,500,000'); w.update(); assert m.parse_int(w.vars['discount_amount'].get()) == 1_500_000; w._capture()
        w.page_index=4; w._show_page(); w.vars['payment_state'].set('علی\u200cالحساب'); w.vars['total_debt'].set('20,000,000'); w.update(); assert m.parse_int(w.vars['remaining_debt'].get()) == 16_000_000
    finally: w.destroy()


def test_cheque_wizard_clean_caption_and_requested_step_layout(app):
    row=_pending({'detected_type':'EXPENSE','v18_title':'هزینه ساخت','v18_subtype':'چک','event_date_shamsi':'1405/05/28','amount':7_200_000,'description':'هفت خط متن نامرتبط','receipt_caption':'خرید سیمان پروژه'},182011)
    w=m.TransactionWizard182(app,row,app.rich,lambda:None,lambda:None); w.update()
    try:
        assert w.payload['description']=='خرید سیمان پروژه'; w.vars['v18_title'].set('هزینه ساخت'); w._title_changed('هزینه ساخت'); w.vars['v18_subtype'].set('چک'); w._sub_changed('چک'); w.next(); w.update()
        groups=[[fd.key for fd in g] for g in w.pages[1:-1]]
        assert groups[0]==['payer_name','receiver_name','description','is_guarantee']; assert groups[1]==['issuer_name','issuer_bank','cheque_type']; assert groups[2]==['cheque_registration_state','due_date_shamsi','cheque_status']
        assert 'cheque_amount' not in {k for group in groups for k in group} and isinstance(w._page_canvas,m.tk.Canvas)
    finally:w.destroy()


def test_sale_other_area_appears_and_payer_is_above_buyer(app):
    row=_pending({'detected_type':'INCOME','v18_title':'ورودی','v18_subtype':'فروش','event_date_shamsi':'1405/05/28','amount':9_000_000},182012)
    w=m.TransactionWizard182(app,row,app.rich,lambda:None,lambda:None); w.update()
    try:
        w.vars['v18_title'].set('ورودی'); w._title_changed('ورودی'); w.vars['v18_subtype'].set('فروش'); w._sub_changed('فروش'); w.next(); w.update()
        w.vars['sale_unit'].set('سایر'); w.update(); assert str(w.widgets['sold_area'].cget('state'))=='normal' and m._widget_host(w.widgets['sold_area']).winfo_ismapped()
        w.vars['sold_area'].set('1458.5'); w.update_idletasks(); assert w.vars['sold_area'].get()=='1,458.5'; w._capture(); assert abs(float(w.payload['sold_area'])-1458.5)<0.001
        w.page_index=2; w._show_page(); w.update(); assert list(w.vars)[:2]==['payer_name','buyer_name']; assert int(m._widget_host(w.widgets['payer_name']).grid_info()['row'])==0 and int(m._widget_host(w.widgets['buyer_name']).grid_info()['row'])==1
    finally:w.destroy()


def test_editor_rtl_dependent_default_scroll_and_clean_cheque_caption(app):
    row=_pending({'detected_type':'EXPENSE','v18_title':'هزینه ساخت','v18_subtype':'چک','event_date_shamsi':'1405/05/28','amount':5_000_000,'description':'context اضافه','receipt_caption':'پرداخت آهن'},182013)
    ed=m.UnifiedPendingEditor182(app,row,app.rich,lambda:None); ed.geometry('1200x760+0+0'); ed.update()
    try:
        assert isinstance(ed._form_canvas,m.tk.Canvas); assert int(m._widget_host(ed.widgets['event_date_shamsi']).grid_info()['column'])==1; assert int(m._widget_host(ed.widgets['amount']).grid_info()['column'])==0
        assert int(m._widget_host(ed.widgets['v18_title']).grid_info()['column'])==1 and int(m._widget_host(ed.widgets['v18_subtype']).grid_info()['column'])==0
        assert ed.vars['description'].get()=='پرداخت آهن' and 'cheque_amount' not in ed.widgets
        ed.title_var.set('هزینه ساخت'); ed.subtype_var.set(''); ed._title_changed(); assert ed.subtype_var.get()=='نقدی'
    finally:ed.destroy()


def test_data_entry_copy_paste_below_target_delete_undo_redo_and_context_menu(app,monkeypatch):
    ac=app.approval_center; assert ac._layout_ratio==(70,30)
    app.notebook.select(app.approval_tab); app.update(); app.update_idletasks()
    for _ in range(3): app.update()
    pane_w=max(1,ac._data_pane.winfo_width()); assert abs((ac._data_pane.sashpos(0)/pane_w)-0.30) < 0.03
    labels=[ac.table.menu.entrycget(i,'label') for i in range(ac.table.menu.index('end')+1) if ac.table.menu.type(i)=='command']; assert any('چسباندن' in str(x) for x in labels)
    r1=_pending({'detected_type':'EXPENSE','v18_title':'هزینه ساخت','v18_subtype':'نقدی','amount':1000},182020); r2=_pending({'detected_type':'EXPENSE','v18_title':'هزینه ساخت','v18_subtype':'نقدی','amount':2000},182021)
    with m.DB.tx() as con:
        con.execute("UPDATE pending_items SET created_at='2026-08-19T10:20:00.000000' WHERE pending_id=?",(r1['pending_id'],)); con.execute("UPDATE pending_items SET created_at='2026-08-19T10:19:00.000000' WHERE pending_id=?",(r2['pending_id'],))
    ac.refresh(); ac.copy_rows([r1]); ac.paste_rows([r2]); app.update(); pasted=ac._undo_stack[-1]['pending_ids'][0]; visible=[str(r.get('pending_id')) for r in ac.rows]; assert visible.index(pasted)==visible.index(str(r2['pending_id']))+1
    ac.undo_data_entry(); assert pasted not in [str(r.get('pending_id')) for r in ac.rows]; ac.redo_data_entry(); assert pasted in [str(r.get('pending_id')) for r in ac.rows]
    monkeypatch.setattr(m.messagebox,'askyesno',lambda *a,**k:True); ac.batch_delete18([r2]); assert str(r2['pending_id']) not in [str(r.get('pending_id')) for r in ac.rows]; ac.undo_data_entry(); assert str(r2['pending_id']) in [str(r.get('pending_id')) for r in ac.rows]; ac.redo_data_entry(); assert str(r2['pending_id']) not in [str(r.get('pending_id')) for r in ac.rows]


def test_dashboard_navigation_command_order_reporting_rtl_and_all_export_targets(app):
    assert [b.cget('text') for b in app.command_buttons]==['ذخیره','Undo','Redo','بروزرسانی','تنظیمات','بسته توسعه','سیستم']
    app.update(); app.update_idletasks(); command_x=[b.winfo_rootx() for b in app.command_buttons]; assert command_x==sorted(command_x,reverse=True)
    assert [b.cget('text') for b in app.nav_buttons.values()]==['داشبورد','ثبت دیتا','تراکنش‌ها','فروش و مطالبات','گزارش\u200cگیری','حساب مدیر']
    nav_x=[b.winfo_rootx() for b in app.nav_buttons.values()]; assert nav_x==sorted(nav_x,reverse=True)
    visible={b.cget('text') for b in app.nav_buttons.values()}; assert not {'سیستم','تنظیمات','تطبیق بانکی'} & visible; assert app.manager_bank_button.cget('text')=='تطبیق بانک'
    assert tuple(app.index_table.cget('displaycolumns'))==('s3','s2','s1','metric'); assert [app.report_nb.tab(t,'text') for t in app.report_nb.tabs()]==['قیمت','فازها','خلاصه روندهای گزارش']
    for expected in ['قیمت','فازها','خلاصه روندهای گزارش']:
        tid=next(t for t in app.report_nb.tabs() if app.report_nb.tab(t,'text')==expected); app.report_main.select(0); app.report_nb.select(tid); headers,rows,title=app._report_export_rows(); assert headers and title
    app.report_main.select(1); headers,rows,title=app._report_export_rows(); assert title=='شاخص‌های مالی' and headers



def test_top_undo_redo_are_scoped_to_data_entry_when_that_tab_is_active(app,monkeypatch):
    ac=app.approval_center; app.notebook.select(app.approval_tab); app.update(); ac._undo_stack.clear(); ac._redo_stack.clear()
    monkeypatch.setattr(m.messagebox,'showinfo',lambda *a,**k:None)
    monkeypatch.setattr(app.rich,'undo_last',lambda:(_ for _ in ()).throw(AssertionError('global undo must not run inside Data Entry')))
    monkeypatch.setattr(app.rich,'redo_last',lambda:(_ for _ in ()).throw(AssertionError('global redo must not run inside Data Entry')))
    app.undo(); app.redo()

def test_dark_and_light_reference_theme_switch(app,monkeypatch):
    monkeypatch.setattr(m,'_is_light',lambda:False); app._style(); app.configure(bg=m._THEME_DARK['bg']); app.refresh_phase_strip(); assert app.cget('bg')==m._THEME_DARK['bg']; assert {b.cget('bg') for b in app.phase_buttons.values()} <= {'#10243A','#177A59','#76571C','#16805D'}
    monkeypatch.setattr(m,'_is_light',lambda:True); app._style(); app.configure(bg=m._THEME_LIGHT['bg']); app.refresh_phase_strip(); assert app.cget('bg')==m._THEME_LIGHT['bg']; assert {b.cget('bg') for b in app.phase_buttons.values()} <= {'#FFFFFF','#28A875','#D8A33D','#239A70'}
    monkeypatch.setattr(m,'_is_light',lambda:False); app._style(); app.configure(bg=m._THEME_DARK['bg']); app.refresh_phase_strip()


def test_data_entry_preview_and_service_labels_are_receipt_scoped_and_stable_persian(app):
    ac=app.approval_center
    m.DB.register_telegram_message(chat_id=-182,message_id=182029,raw_text='یک خط بلافاصله قبل',content_type='TEXT',message_date='2026-08-19T09:59:59')
    row=_pending({'detected_type':'EXPENSE','v18_title':'هزینه ساخت','v18_subtype':'چک','amount':3_000_000,'receipt_caption':'فقط متن همین فیش','description':'پیام دور و نامرتبط'},182030)
    m.DB.register_telegram_message(chat_id=-182,message_id=182031,raw_text='یک خط بلافاصله بعد',content_type='TEXT',message_date='2026-08-19T10:00:01')
    m.DB.register_telegram_message(chat_id=-182,message_id=182032,raw_text='پیام دورتر که نباید دیده شود',content_type='TEXT',message_date='2026-08-19T10:00:02')
    ac._show(row); preview=ac.text.get('1.0','end').strip()
    assert preview == 'فقط متن همین فیش'
    assert 'یک خط بلافاصله قبل' not in preview and 'یک خط بلافاصله بعد' not in preview
    assert 'پیام دورتر' not in preview and 'پیام دور و نامرتبط' not in preview and 'AI:' not in preview
    ac._service_status_181(); assert ac.bot.get().startswith('تلگرام:') and ac.gemini.get().startswith('جمینای:') and 'Telegram:' not in ac.bot.get() and 'Gemini:' not in ac.gemini.get()


def test_pending_edit_history_is_reversible_without_touching_posted_finance(app):
    ac=app.approval_center; row=_pending({'detected_type':'EXPENSE','v18_title':'هزینه ساخت','v18_subtype':'نقدی','amount':10_000,'description':'قبل'},182031); before=ac._pending_snapshot(row['pending_id']); changed=dict(before['payload']); changed['description']='بعد'; m.DB.update_pending(row['pending_id'],payload=changed,status='PENDING_REVIEW'); ac._record_pending_edit(before); assert ac.can_undo(); ac.undo_data_entry(); assert m.DB.get_pending_item(row['pending_id'])['payload']['description']=='قبل'; ac.redo_data_entry(); assert m.DB.get_pending_item(row['pending_id'])['payload']['description']=='بعد'



def test_manual_add_participates_in_data_entry_undo_redo(app,monkeypatch):
    ac=app.approval_center; monkeypatch.setattr(ac,'open_wizard',lambda row=None:None)
    ac.manual_transaction(); assert ac._undo_stack and ac._undo_stack[-1]['kind']=='add'
    pid=ac._undo_stack[-1]['pending_ids'][0]; assert str((m.DB.get_pending_item(pid) or {}).get('status')) in {'PENDING_REVIEW','NEEDS_REVIEW'}
    ac.undo_data_entry(); assert pid not in [str(r.get('pending_id')) for r in ac.rows]
    ac.redo_data_entry(); assert pid in [str(r.get('pending_id')) for r in ac.rows]

def test_reprocess_opens_progress_immediately_and_refreshes_result(app,monkeypatch):
    import asyncio as _asyncio, time as _time
    ac=app.approval_center; row=_pending({'detected_type':'EXPENSE','v18_title':'هزینه ساخت','v18_subtype':'نقدی','amount':1000,'description':'قبل'},182032)
    async def fake(pid):
        await _asyncio.sleep(.03); fresh=m.DB.get_pending_item(pid) or {}; p=dict(fresh.get('payload') or {}); p['description']='اصلاح شده توسط تحلیل'; p['amount']=2000; m.DB.update_pending(pid,payload=p,status='PENDING_REVIEW'); return {'payload':p}
    class SyncThread:
        def __init__(self,target=None,daemon=None,**kwargs): self.target=target
        def start(self): self.target()
    monkeypatch.setattr(m.APPROVAL,'analyze_pending_with_ai',fake); monkeypatch.setattr(m.threading,'Thread',SyncThread); monkeypatch.setattr(m.messagebox,'showinfo',lambda *a,**k:None); monkeypatch.setattr(m.messagebox,'showwarning',lambda *a,**k:None); monkeypatch.setattr(m.messagebox,'showerror',lambda *a,**k:None)
    ac.reprocess_rows([row]); assert ac._reprocess_dialog is not None and ac._reprocess_dialog.winfo_exists() and 'در حال پردازش' in ac.action.get(); deadline=_time.time()+2
    while _time.time()<deadline and 'در حال پردازش' in ac.action.get(): app.update(); app.update_idletasks(); _time.sleep(.01)
    assert m.DB.get_pending_item(row['pending_id'])['payload']['description']=='اصلاح شده توسط تحلیل'; assert 'موفقیت' in ac.action.get() or 'به\u200cروزرسانی' in ac.action.get()


def test_pdf_export_uses_current_valid_summary_tab(app,monkeypatch,tmp_path):
    app.refresh_reports(); app.report_main.select(0); tid=next(t for t in app.report_nb.tabs() if app.report_nb.tab(t,'text')=='خلاصه روندهای گزارش'); app.report_nb.select(tid); out=tmp_path/'summary.pdf'; app.report_export_mode.set('PDF'); captured={}
    def fake_pdf(path,headers,rows,title=''): captured.update(headers=list(headers),rows=list(rows),title=title); Path(path).write_bytes(b'%PDF-1.4\n% routing smoke\n')
    monkeypatch.setattr(m.v163,'export_pdf',fake_pdf); monkeypatch.setattr(m.filedialog,'asksaveasfilename',lambda **k:str(out)); monkeypatch.setattr(m.messagebox,'showinfo',lambda *a,**k:None); monkeypatch.setattr(m.messagebox,'showerror',lambda *a,**k:(_ for _ in ()).throw(AssertionError(a))); app.export_report_choose(); assert out.exists() and out.read_bytes().startswith(b'%PDF'); assert captured['headers']==['شاخص','مقدار','جزئیات'] and 'خلاصه روندهای گزارش' in captured['title']
