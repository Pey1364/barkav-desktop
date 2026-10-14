from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import mimetypes, threading, tkinter as tk
from tkinter import ttk, messagebox, filedialog

import dashboard_stage18_3 as v183
import dashboard_stage18_2 as v182
import dashboard_stage18_1 as v181
import dashboard_stage18 as v18
from v18_store import load_ui, save_ui
from attachment_service import AttachmentService
from ui_stage18_3 import fa, en, parse_int, group_int_fa, bind_grouped_number_fa, fetch_tgju_usd_toman
from ui_stage18_4 import (
    attach_tree_grid_184, attach_table_visuals_recursive,
    upgrade_smarttables_recursive_184, build_brand_widget_184,
)

VERSION='18.4'
BASE_DIR=v183.BASE_DIR; DB=v183.DB; APPROVAL=v183.APPROVAL; SERVICE=v183.SERVICE; DARK=v183.DARK


def _walk(root):
    stack=[root]
    while stack:
        w=stack.pop();yield w
        try:stack.extend(w.winfo_children())
        except Exception:pass


def _is_light():
    try:return str(load_ui().get('appearance') or 'dark').lower()=='light'
    except Exception:return False


def _fs():
    try:return int(load_ui().get('font_size') or 11)
    except Exception:return 11


class UnifiedPendingEditor184(v183.UnifiedPendingEditor183):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw);self.title('ویرایش و تأیید رکورد — BARKAV 18.4')
        self.after_idle(lambda:attach_table_visuals_recursive(self,light=_is_light()))


class TransactionWizard184(v183.TransactionWizard183):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw);self.title('ثبت تراکنش — Wizard — BARKAV 18.4')


class DataEntryCenter184(v183.DataEntryCenter183):
    """18.4 Data Entry: vivid rows + chat-history attachments; all 18.3 business behavior inherited."""
    def _build(self):
        super()._build();self._install_chat_history_actions();self.after_idle(self._vivid_rows_184)

    def refresh(self,*a,**kw):
        res=super().refresh(*a,**kw)
        try:self._vivid_rows_184()
        except Exception:pass
        return res

    def _vivid_rows_184(self):
        tree=self.table.tree;light=_is_light()
        colors={
            'tx183_هزینه_ساخت':('#F5C842','#4A3800'),
            'tx183_ورودی':('#F5C842','#4A3800'),
            'tx183_خروجی':('#F5C842','#4A3800'),
            'tx183_یادداشت':('#F5C842','#4A3800'),
        }
        for tag,(bg,fg) in colors.items():
            try:tree.tag_configure(tag,background=bg,foreground=fg)
            except Exception:pass
        attach_tree_grid_184(tree,light=light)

    def open_editor(self,row=None):
        row=row or getattr(self,'current',None)
        if not row:return
        pid=str(row.get('pending_id') or '');before=self._pending_snapshot(pid)
        def done():self._record_pending_edit(before);self.refresh()
        UnifiedPendingEditor184(self,row,self.rich,done)

    def open_wizard(self,row=None):
        row=row or getattr(self,'current',None)
        if not row:return messagebox.showwarning('ثبت دیتا','یک سطر را انتخاب کن.',parent=self)
        pid=str(row.get('pending_id') or '');before=self._pending_snapshot(pid)
        def done():self._record_pending_edit(before);self.refresh()
        def full():
            fresh=DB.get_pending_item(pid) or row;fresh=dict(fresh);fresh['raw_text']=v18._raw_text(pid,row);self.open_editor(fresh)
        TransactionWizard184(self,row,self.rich,done,full)

    def _install_chat_history_actions(self):
        parent=getattr(self,'_center_data_actions',None)
        if parent is None:
            try:parent=self.winfo_children()[0]
            except Exception:return
        p=v183._palette()
        self.chat_attach_button=tk.Button(parent,text='📎 تاریخچه چت',command=self.attach_chat_history,
            bg=p['glass'],fg=p['text'],activebackground=p['panel2'],relief='flat',padx=9,pady=5,font=('Segoe UI',max(9,_fs()-1),'bold'))
        self.chat_attach_button.pack(side='right',padx=4,pady=4)
        self.chat_view_button=tk.Button(parent,text='📂 تاریخچه‌های متصل',command=self.show_chat_histories,
            bg=p['glass'],fg=p['text'],activebackground=p['panel2'],relief='flat',padx=9,pady=5,font=('Segoe UI',max(9,_fs()-1),'bold'))
        self.chat_view_button.pack(side='right',padx=4,pady=4)

    def _one_pending(self):
        rows=self.table.selected_rows()
        if len(rows)!=1:
            messagebox.showwarning('تاریخچه چت','دقیقاً یک سطر را انتخاب کن.',parent=self);return None
        return rows[0]

    @staticmethod
    def _entities_for_pending(pid:str):
        entities=[('PENDING',pid)]
        try:
            post=DB.get_financial_posting(pid) or {}
            typ=str(post.get('primary_entity_type') or '').strip();eid=str(post.get('primary_entity_id') or '').strip()
            if typ and eid:entities.append((typ,eid))
        except Exception:pass
        return entities

    def attach_chat_history(self):
        row=self._one_pending()
        if not row:return
        pid=str(row.get('pending_id') or '')
        path=filedialog.askopenfilename(parent=self,title='انتخاب فایل تاریخچه چت',
            filetypes=[('Telegram / Chat History','*.json *.txt *.html *.htm *.zip'),('JSON','*.json'),('Text','*.txt'),('HTML','*.html *.htm'),('All files','*.*')])
        if not path:return
        try:
            service=AttachmentService(DB,BASE_DIR);post=DB.get_financial_posting(pid) or {}
            typ=str(post.get('primary_entity_type') or '').strip() if str(row.get('status') or '')=='APPROVED' else 'PENDING'
            eid=str(post.get('primary_entity_id') or '').strip() if typ!='PENDING' else pid
            if not typ or not eid:typ,eid='PENDING',pid
            service.add_local(entity_type=typ,entity_id=eid,source_path=path,document_type='CHAT_HISTORY')
            messagebox.showinfo('تاریخچه چت','تاریخچه چت به این رکورد متصل شد.\nاین ضمیمه از «بابت» و متن اصلی فیش جدا نگهداری می‌شود.',parent=self)
        except Exception as exc:messagebox.showerror('تاریخچه چت',str(exc),parent=self)

    def _chat_docs(self,pid):
        service=AttachmentService(DB,BASE_DIR);docs=service.list_for_entities(self._entities_for_pending(pid))
        return [d for d in docs if str(d.get('document_type') or '').upper()=='CHAT_HISTORY']

    def show_chat_histories(self):
        row=self._one_pending()
        if not row:return
        pid=str(row.get('pending_id') or '');docs=self._chat_docs(pid)
        win=tk.Toplevel(self);win.title('تاریخچه‌های چت متصل');win.geometry('820x420')
        tree=ttk.Treeview(win,columns=('file','date','entity','id'),show='headings',selectmode='extended')
        for c,t,w in [('file','فایل',360),('date','تاریخ اتصال',170),('entity','اتصال به',120),('id','Attachment ID',150)]:tree.heading(c,text=t,anchor='e');tree.column(c,width=w,anchor='e')
        tree.pack(fill='both',expand=True,padx=8,pady=8)
        for d in docs:tree.insert('', 'end',values=(Path(d.get('local_path') or '').name,fa(d.get('created_at') or ''),fa(d.get('entity_type') or ''),fa(d.get('attachment_id') or '')))
        attach_table_visuals_recursive(win,light=_is_light())
        def open_selected():
            sel=tree.selection()
            if not sel:return
            shown=tree.item(sel[0],'values');shown_id=str(shown[-1]);
            # UI digits may be Persian; resolve from selected row position instead of parsing ID.
            idx=tree.index(sel[0]);aid=str(docs[idx].get('attachment_id') or '')
            try:AttachmentService(DB,BASE_DIR).open(aid)
            except Exception as exc:messagebox.showerror('فایل',str(exc),parent=win)
        tk.Button(win,text='باز کردن فایل',command=open_selected,bg=v183._palette()['glass'],fg=v183._palette()['text'],relief='flat',padx=14,pady=6).pack(anchor='e',padx=8,pady=(0,8))


class SettingsTab184(v183.SettingsTab183):
    """USD belongs in Settings in 18.4; current rate remains manually editable and TGJU-refreshable."""
    def _build(self):
        super()._build();self._install_tgju()

    def _install_tgju(self):
        v=self.vars.get('usd_rate_current')
        if v is None:return
        host=None
        for w in _walk(self):
            try:
                if isinstance(w,ttk.Entry) and str(w.cget('textvariable'))==str(v):host=w.master;break
            except Exception:pass
        if host is None:return
        self.usd_status=tk.StringVar(value='نرخ قابل ویرایش است.')
        tk.Button(host,text='بروزرسانی از TGJU',command=self.refresh_usd,bg=v183._palette()['glass'],fg=v183._palette()['text'],relief='flat',padx=8,pady=4).pack(anchor='e',pady=(2,0))
        tk.Label(host,textvariable=self.usd_status,bg=v183._palette()['panel'],fg=v183._palette()['muted'],font=('Segoe UI',8)).pack(anchor='e')

    def refresh_usd(self):
        self.usd_status.set('در حال دریافت نرخ دلار...')
        def job():
            try:rate,ts=fetch_tgju_usd_toman();err=''
            except Exception as exc:rate=0;ts='';err=str(exc)
            def done():
                if rate>0:self.vars['usd_rate_current'].set(group_int_fa(rate));self.usd_status.set(f'آخرین بروزرسانی: {fa(ts.replace("T"," "))}')
                else:self.usd_status.set('دریافت آنلاین انجام نشد؛ مقدار دستی حفظ شد.')
            try:self.after(0,done)
            except Exception:pass
        threading.Thread(target=job,daemon=True).start()


class ProjectSettingsDialog184(v183.ProjectSettingsDialog183):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw);self.title('مشخصات پروژه — BARKAV 18.4');self.after_idle(self._units_rtl_184)

    def _build(self):
        super()._build();self._remove_usd_from_project_base();self._units_rtl_184()

    def _remove_usd_from_project_base(self):
        var=self.vars.get('usd_rate_current')
        if var is not None:
            for w in list(_walk(self)):
                try:
                    if isinstance(w,ttk.Entry) and str(w.cget('textvariable'))==str(var):w.master.destroy();break
                except Exception:pass
            self.vars.pop('usd_rate_current',None)
        for w in list(_walk(self)):
            try:
                if isinstance(w,tk.Button) and 'TGJU' in str(w.cget('text')):
                    parent=w.master;parent.destroy();break
            except Exception:pass

    # The 18.3 button is bound to this method name during super()._build().
    def save_basic_183(self):
        self.save_basic_181()

    def _active_export_data(self):
        label=self.nb.tab(self.nb.select(),'text')
        if label=='مشخصات پایه':
            headers=['عنوان','مقدار'];rows=[]
            labels={'name':'نام پروژه','address':'آدرس','postal_code':'کدپستی','registration_plate':'پلاک ثبتی','municipal_file_no':'شماره پرونده شهرداری','gross_area':'متراژ کل M2','saleable_area':'متراژ مفید M2','unit_count':'تعداد واحد','floor_count':'تعداد طبقات'}
            for k,l in labels.items():rows.append([l,self.vars[k].get()])
            return label,headers,rows
        return super()._active_export_data()

    def _units_rtl_184(self):
        tree=getattr(self,'floor_tree',None)
        if not isinstance(tree,ttk.Treeview):return
        try:
            tree.configure(displaycolumns=('areas','count','floor'))
            for c in ('floor','count','areas'):
                tree.heading(c,anchor='e');tree.column(c,anchor='e')
            attach_tree_grid_184(tree,light=_is_light())
        except Exception:pass


class Stage184Dashboard(v183.Stage183Dashboard):
    _VISIBLE_NAV=v183.Stage183Dashboard._VISIBLE_NAV
    def __init__(self):
        super().__init__();self.title('BARKAV — Engineering & Construction — Version 18.4');self.after_idle(self._finalize_184)

    def _build_approval_center(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.approval_tab=tab;self.notebook.insert(1,tab,text='ثبت دیتا');self.approval_center=DataEntryCenter184(tab,self.rich,on_posted=self.refresh_all);self.approval_center.pack(fill='both',expand=True)
        if self._bot_process:self.approval_center.set_bot_process(self._bot_process,self._bot_log)
        self.after_idle(self._rebuild_navbar)

    def _build_settings(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.notebook.add(tab,text='تنظیمات');SettingsTab184(tab,self._settings_saved).pack(fill='both',expand=True)

    def edit_project_settings(self):ProjectSettingsDialog184(self,self.refresh_all)

    def _find_datetime_label(self):
        target=str(getattr(self,'datetime_top',''))
        for w in _walk(self):
            if isinstance(w,tk.Label):
                try:
                    if str(w.cget('textvariable'))==target:return w
                except Exception:pass
        return None

    def _install_quick_theme(self):
        if getattr(self,'quick_theme_button',None):return
        lab=self._find_datetime_label()
        if lab is None:return
        p=v183._palette();symbol='☀' if _is_light() else '🌙'
        self.quick_theme_button=tk.Button(lab.master,text=symbol,command=self.toggle_theme_184,bg=p['glass'],fg=p['text'],activebackground=p['panel2'],relief='flat',font=('Segoe UI',13,'bold'),padx=8,pady=5,cursor='hand2')
        self.quick_theme_button.pack(side='right',padx=4)
        v18.add_tooltip(self.quick_theme_button,'تغییر سریع تم روشن / تیره')

    def toggle_theme_184(self):
        ui=load_ui();ui['appearance']='dark' if str(ui.get('appearance') or 'dark').lower()=='light' else 'light';save_ui(ui)
        self._restart_requested=True;self.after(80,self.destroy)

    def _replace_brand_184(self):
        if getattr(self,'_brand_host_184',None):return
        p=v183._palette();old=None;top=None
        for w in _walk(self):
            if isinstance(w,tk.Label):
                try:
                    if str(w.cget('image')) and w.master is not None and int(w.master.winfo_height() or 0)<=100:old=w;top=w.master;break
                except Exception:pass
        if top is None:return
        try:old.destroy()
        except Exception:pass
        self._brand_host_184=build_brand_widget_184(top,BASE_DIR/'assets'/'barkav_brand_header.png',bg=p['surface'],fg=p['text']);self._brand_host_184.pack(side='left',padx=(14,6),pady=4)

    def _pending_from_posted_row(self,r:dict):
        pid=str(r.get('pending_id') or '').strip()
        if pid:return pid
        with DB.read() as con:
            for col,key in [('transaction_id','transaction_id'),('expense_id','expense_id'),('cheque_id','cheque_id')]:
                val=str(r.get(key) or '').strip()
                if val:
                    row=con.execute(f"SELECT pending_id FROM financial_postings WHERE {col}=? AND COALESCE(status,'ACTIVE')='ACTIVE' ORDER BY created_at DESC LIMIT 1",(val,)).fetchone()
                    if row:return str(row['pending_id'])
            loan=str(r.get('loan_id') or '').strip()
            if loan:
                row=con.execute("SELECT fp.pending_id FROM transactions t JOIN financial_postings fp ON fp.transaction_id=t.transaction_id WHERE t.loan_id=? AND COALESCE(fp.status,'ACTIVE')='ACTIVE' ORDER BY fp.created_at DESC LIMIT 1",(loan,)).fetchone()
                if row:return str(row['pending_id'])
            doc=str(r.get('document_id') or '').strip()
            if doc:
                row=con.execute("SELECT pending_id FROM financial_documents WHERE document_id=? LIMIT 1",(doc,)).fetchone()
                if row and row['pending_id']:return str(row['pending_id'])
        return ''

    def _open_new_record_editor_184(self,r:dict):
        pid=self._pending_from_posted_row(r)
        if not pid:
            return messagebox.showinfo('ویرایش رکورد','این رکورد قدیمی به Pending اصلی متصل نیست؛ برای جلوگیری از تغییر ناخواسته منطق مالی، پنجره قدیمی باز نشد.',parent=self)
        row=DB.get_pending_item(pid)
        if not row:return messagebox.showwarning('ویرایش رکورد','رکورد مبدا پیدا نشد.',parent=self)
        row=dict(row);row['raw_text']=v18._raw_text(pid,row)
        UnifiedPendingEditor184(self,row,self.rich,self.refresh_all)

    def edit_transaction_row(self,r):self._open_new_record_editor_184(r)
    def edit_expense_row(self,r):self._open_new_record_editor_184(r)
    def edit_cheque_row(self,r):self._open_new_record_editor_184(r)
    def edit_loan_row(self,r):self._open_new_record_editor_184(r)
    def edit_document_row_184(self,r):self._open_new_record_editor_184(r)

    def _order_financial_tabs_184(self):
        nb=getattr(self,'fin_nb',None)
        if not isinstance(nb,ttk.Notebook):return
        by={nb.tab(t,'text'):t for t in nb.tabs()}
        desired=['کلیه تراکنش‌ها','هزینه ساخت','چک‌ها','ورودی‌ها','خروجی‌ها','تسهیلات','داکیومنت‌ها']
        # Accept singular variants while preserving every unmentioned tab.
        order=[]
        for label in desired:
            t=by.get(label)
            if t:order.append(t)
        order += [t for t in nb.tabs() if t not in order]
        for i,t in enumerate(order):
            try:nb.insert(i,t)
            except Exception:pass
        try:
            strip=getattr(nb,'_barkav_rtl_strip',None)
            if strip:strip.rebuild()
        except Exception:pass

    def _upgrade_tables_184(self,root=None):
        root=root or self;upgrade_smarttables_recursive_184(root,font_size=_fs(),light=_is_light());attach_table_visuals_recursive(root,light=_is_light())
        # All raw Treeview visible values are Persianized without touching underlying row dicts.
        for w in _walk(root):
            if isinstance(w,ttk.Treeview):
                try:
                    for iid in w.get_children(''):
                        vals=list(w.item(iid,'values') or ())
                        if vals:w.item(iid,values=[fa(v) for v in vals])
                except Exception:pass

    def refresh_financial(self):
        super().refresh_financial();self._upgrade_tables_184(getattr(self,'fin_nb',self))
    def refresh_sales(self):
        super().refresh_sales();self._upgrade_tables_184(getattr(self,'sales_root',self))
    def refresh_reports(self):
        super().refresh_reports();self._upgrade_tables_184(getattr(self,'report_main',self))
    def refresh_manager(self):
        super().refresh_manager();self._upgrade_tables_184(self)

    def _finalize_184(self):
        self._install_quick_theme();self._replace_brand_184();self._order_financial_tabs_184();self._upgrade_tables_184(self)
        # Route every transaction subtable double-click to the current unified editor.
        for name in ('all_tx_table','exp_table','in_table','out_table','cheque_table','loan_table'):
            table=getattr(self,name,None)
            if table is not None and hasattr(table,'set_edit_handler'):
                handler=(self.edit_expense_row if name=='exp_table' else self.edit_cheque_row if name=='cheque_table' else self.edit_loan_row if name=='loan_table' else self.edit_transaction_row)
                table.set_edit_handler(handler)
        doc=getattr(self,'document_table',None)
        if doc is not None and hasattr(doc,'set_edit_handler'):doc.set_edit_handler(self.edit_document_row_184)

    def export_development_package(self):
        dest=filedialog.asksaveasfilename(parent=self,defaultextension='.zip',initialfile='BARKAV_Development_Package_18.4.zip',filetypes=[('ZIP','*.zip')])
        if not dest:return
        try:
            from development_package_v184 import build_development_package as build_dev_184
            res=build_dev_184(BASE_DIR,Path(dest),VERSION);messagebox.showinfo('بسته توسعه',f"بسته توسعه {VERSION} ساخته شد:\n{res['path']}\n\nدیتابیس زنده و secrets وارد بسته نشده‌اند.",parent=self)
        except Exception as exc:messagebox.showerror('بسته توسعه',str(exc),parent=self)


# Compatibility aliases for launchers/importers.
Stage184DashboardFinal=Stage184Dashboard
Stage183Dashboard=Stage184Dashboard
Stage182Dashboard=Stage184Dashboard
Stage18Dashboard=Stage184Dashboard

if __name__=='__main__':Stage184Dashboard().mainloop()
