from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any

from config_loader import load_config
from dashboard_service import DashboardService
from finance_db import FinanceDB
from reaction_cleanup import clear_group_reaction
from revenue_service import gregorian_to_shamsi

BASE_DIR = Path(__file__).resolve().parent
CONFIG = load_config(BASE_DIR)
DB = FinanceDB(CONFIG.db_path)
SERVICE = DashboardService(DB)


def money(v: Any) -> str:
    try:
        return f"{int(v or 0):,} تومان"
    except Exception:
        return "-"


def fa_status(v: str) -> str:
    m = {
        'ACTIVE':'فعال','DELETED':'حذف‌شده','APPROVED':'تأییدشده','PAID':'پرداخت‌شده',
        'PARTIALLY_PAID':'پرداخت جزئی','POSTED':'ثبت‌شده','VOIDED':'باطل‌شده',
        'ISSUED':'صادرشده','PENDING_DUE':'در انتظار سررسید','CASHED':'پاس‌شده',
        'RETURNED':'برگشتی','CANCELLED':'لغوشده','COMPLETED':'تکمیل‌شده',
        'UPCOMING':'آینده','DUE':'سررسید','OVERDUE':'معوق','UNMATCHED':'تطبیق‌نشده',
        'MATCHED':'تطبیق‌شده','FAILED':'خطا','PENDING':'در انتظار','SYNCED':'همگام',
    }
    return m.get(str(v or '').upper(), str(v or '-'))


class Card(ttk.Frame):
    def __init__(self, parent, title: str):
        super().__init__(parent, padding=10, relief='ridge')
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text=title, anchor='center').grid(row=0, column=0, sticky='ew')
        self.var = tk.StringVar(value='-')
        ttk.Label(self, textvariable=self.var, anchor='center', font=('TkDefaultFont', 12, 'bold')).grid(row=1, column=0, sticky='ew', pady=(6,0))


class Stage8Dashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Peymaan V2 — Stage 8 Dashboard')
        self.geometry('1260x820')
        self.minsize(1050, 680)
        self.option_add('*Font', ('Tahoma', 10))
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self._build()
        self.after(150, self.refresh_all)
        self.after(15000, self._periodic_refresh)

    def _build(self):
        top = ttk.Frame(self, padding=(10,8))
        top.pack(fill='x')
        ttk.Label(top, text='داشبورد مدیریتی پیمان', font=('Tahoma', 15, 'bold')).pack(side='right')
        ttk.Button(top, text='🔄 بروزرسانی', command=self.refresh_all).pack(side='left')
        ttk.Button(top, text='🧪 بررسی سلامت', command=self.show_health).pack(side='left', padx=6)
        ttk.Button(top, text='🛠 اصلاح Ledger', command=self.repair_ledger).pack(side='left')

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=(0,10))
        self._build_overview()
        self._build_manager()
        self._build_ledger()
        self._build_cheques()
        self._build_sales()
        self._build_reconciliation()
        self._build_health()

    # ---------- overview ----------
    def _build_overview(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text='داشبورد')
        cards = [
            ('cash','💰 مانده تنخواه'), ('free','🟢 مانده آزاد پس از چک'),
            ('cost','🏗 هزینه ساخت'), ('fee','👷 حقوق مدیر پروژه تحقق‌یافته'),
            ('withdraw','💸 برداشت حقوق مدیر پروژه'), ('manager','⚖️ مانده حساب مدیر'),
            ('cheques','🧾 تعهد چک باز'), ('sales','🏠 فروش قراردادی'),
            ('received','💵 وصول خریداران'), ('receivable','📥 مطالبات خریداران'),
            ('overdue','⚠️ مطالبات معوق'), ('sync','🔄 صف Sync'),
        ]
        self.cards: dict[str, Card] = {}
        for i, (key,title) in enumerate(cards):
            c = Card(tab, title)
            c.grid(row=i//4, column=i%4, sticky='nsew', padx=5, pady=5)
            self.cards[key] = c
        for c in range(4): tab.columnconfigure(c, weight=1)
        for r in range(3): tab.rowconfigure(r, weight=0)

        rec = ttk.LabelFrame(tab, text='تطبیق با بانک', padding=12)
        rec.grid(row=3, column=0, columnspan=4, sticky='ew', padx=5, pady=(15,5))
        ttk.Label(rec, text='موجودی واقعی بانک:').grid(row=0,column=4,padx=4)
        self.bank_var = tk.StringVar()
        ttk.Entry(rec, textvariable=self.bank_var, width=22, justify='center').grid(row=0,column=3,padx=4)
        ttk.Label(rec, text='تاریخ شمسی:').grid(row=0,column=2,padx=4)
        self.bank_date_var = tk.StringVar()
        ttk.Entry(rec, textvariable=self.bank_date_var, width=14, justify='center').grid(row=0,column=1,padx=4)
        ttk.Button(rec, text='ثبت تطبیق', command=self.record_reconciliation).grid(row=0,column=0,padx=6)
        self.bank_info_var = tk.StringVar(value='آخرین تطبیق: -')
        ttk.Label(rec, textvariable=self.bank_info_var).grid(row=1,column=0,columnspan=5,sticky='e',pady=(10,0))

    # ---------- manager ----------
    def _build_manager(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text='حساب مدیر')
        controls = ttk.Frame(tab)
        controls.pack(fill='x')
        ttk.Label(controls,text='از:').pack(side='right')
        self.mgr_start = tk.StringVar(); ttk.Entry(controls,textvariable=self.mgr_start,width=14,justify='center').pack(side='right',padx=4)
        ttk.Label(controls,text='تا:').pack(side='right',padx=(10,0))
        self.mgr_end = tk.StringVar(); ttk.Entry(controls,textvariable=self.mgr_end,width=14,justify='center').pack(side='right',padx=4)
        ttk.Button(controls,text='محاسبه',command=self.refresh_manager).pack(side='right',padx=8)
        self.mgr_summary = tk.StringVar(value='-')
        ttk.Label(tab,textvariable=self.mgr_summary,justify='right').pack(fill='x',pady=12)
        self.manager_canvas = tk.Canvas(tab, background='white', height=440, highlightthickness=1, highlightbackground='#bbb')
        self.manager_canvas.pack(fill='both',expand=True)

    # ---------- ledger ----------
    def _build_ledger(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text='ثبت‌های مالی')
        bar = ttk.Frame(tab); bar.pack(fill='x',pady=(0,8))
        ttk.Button(bar,text='✏️ ویرایش ثبت',command=self.edit_selected_posting).pack(side='right')
        ttk.Button(bar,text='🗑 حذف ثبت',command=self.delete_selected_posting).pack(side='right',padx=6)
        ttk.Button(bar,text='🔄 بروزرسانی',command=self.refresh_ledger).pack(side='left')
        cols = ('pending','type','amount','description','expense','transaction','payment','cheque','status')
        self.ledger_tree = ttk.Treeview(tab, columns=cols, show='headings', selectmode='browse')
        headings = {'pending':'Pending ID','type':'نوع','amount':'مبلغ','description':'بابت/شرح','expense':'Expense','transaction':'Transaction','payment':'Payment','cheque':'Cheque','status':'وضعیت'}
        widths = {'pending':145,'type':80,'amount':130,'description':250,'expense':130,'transaction':130,'payment':130,'cheque':130,'status':90}
        for c in cols:
            self.ledger_tree.heading(c,text=headings[c]); self.ledger_tree.column(c,width=widths[c],anchor='center')
        self.ledger_tree.pack(fill='both',expand=True)
        self.ledger_rows: dict[str,dict[str,Any]] = {}

    # ---------- cheques ----------
    def _build_cheques(self):
        tab = ttk.Frame(self.notebook,padding=10); self.notebook.add(tab,text='چک‌ها')
        top=ttk.Frame(tab); top.pack(fill='x',pady=(0,8))
        self.open_cheques_only=tk.BooleanVar(value=False)
        ttk.Checkbutton(top,text='فقط چک‌های باز',variable=self.open_cheques_only,command=self.refresh_cheques).pack(side='right')
        cols=('id','amount','due','receiver','description','status')
        self.cheque_tree=ttk.Treeview(tab,columns=cols,show='headings')
        labels={'id':'Cheque ID','amount':'مبلغ','due':'سررسید شمسی','receiver':'گیرنده','description':'بابت','status':'وضعیت'}
        for c in cols:
            self.cheque_tree.heading(c,text=labels[c]); self.cheque_tree.column(c,width=170 if c=='description' else 130,anchor='center')
        self.cheque_tree.pack(fill='both',expand=True)

    # ---------- sales ----------
    def _build_sales(self):
        tab=ttk.Frame(self.notebook,padding=10); self.notebook.add(tab,text='فروش و مطالبات')
        cols=('sale','unit','buyer','contract','received','receivable','overdue','next_due','status')
        self.sales_tree=ttk.Treeview(tab,columns=cols,show='headings')
        labels={'sale':'Sale ID','unit':'واحد','buyer':'خریدار','contract':'قرارداد','received':'وصول','receivable':'مانده','overdue':'معوق','next_due':'سررسید بعدی','status':'وضعیت'}
        for c in cols:
            self.sales_tree.heading(c,text=labels[c]); self.sales_tree.column(c,width=145 if c in {'sale','buyer'} else 120,anchor='center')
        self.sales_tree.pack(fill='both',expand=True)

    # ---------- reconciliation ----------
    def _build_reconciliation(self):
        tab=ttk.Frame(self.notebook,padding=10); self.notebook.add(tab,text='تاریخچه تطبیق بانک')
        cols=('date','system','bank','difference','notes')
        self.rec_tree=ttk.Treeview(tab,columns=cols,show='headings')
        labels={'date':'تاریخ شمسی','system':'مانده سیستم','bank':'بانک','difference':'اختلاف','notes':'توضیح'}
        for c in cols:
            self.rec_tree.heading(c,text=labels[c]); self.rec_tree.column(c,width=260 if c=='notes' else 160,anchor='center')
        self.rec_tree.pack(fill='both',expand=True)

    # ---------- health ----------
    def _build_health(self):
        tab=ttk.Frame(self.notebook,padding=15); self.notebook.add(tab,text='سلامت سیستم')
        self.health_text=tk.Text(tab,wrap='word',height=20)
        self.health_text.pack(fill='both',expand=True)
        ttk.Button(tab,text='بروزرسانی وضعیت',command=self.refresh_health).pack(pady=8)

    # ---------- refresh ----------
    def _periodic_refresh(self):
        try: self.refresh_overview()
        finally: self.after(15000,self._periodic_refresh)

    def refresh_all(self):
        try:
            start,end=SERVICE.manager_activity_bounds()
            if not self.mgr_start.get(): self.mgr_start.set(start)
            if not self.mgr_end.get(): self.mgr_end.set(end)
            if not self.bank_date_var.get(): self.bank_date_var.set(end)
            self.refresh_overview(); self.refresh_manager(); self.refresh_ledger(); self.refresh_cheques(); self.refresh_sales(); self.refresh_reconciliations(); self.refresh_health()
        except Exception as exc:
            messagebox.showerror('خطا',str(exc))

    def refresh_overview(self):
        o=SERVICE.overview()
        vals={'cash':o.cash_balance,'free':o.free_cash_after_cheques,'cost':o.construction_cost,'fee':o.manager_fee_accrued,
              'withdraw':o.manager_withdrawals,'manager':o.manager_balance,'cheques':o.open_cheque_commitments,'sales':o.contract_sales,
              'received':o.buyer_cash_received,'receivable':o.buyer_receivable,'overdue':o.buyer_overdue}
        for k,v in vals.items(): self.cards[k].var.set(money(v))
        self.cards['sync'].var.set(f"{o.pending_sync} مورد | خطا {o.failed_sync}")
        if o.bank_balance is None:
            self.bank_info_var.set('آخرین تطبیق: ثبت نشده')
        else:
            self.bank_info_var.set(f"آخرین تطبیق {o.bank_reconciled_shamsi}: بانک {money(o.bank_balance)} | اختلاف {money(o.bank_difference)}")

    def refresh_manager(self):
        try:
            exp=SERVICE.manager_exposure_shamsi(self.mgr_start.get(),self.mgr_end.get())
            series=SERVICE.manager_daily_series(self.mgr_start.get(),self.mgr_end.get())
            self.mgr_summary.set(
                f"روزهای طلبکار: {exp.creditor_days} | میانگین طلب: {money(exp.average_creditor_balance)} | تومان‌روز مثبت: {exp.creditor_toman_days:,}\n"
                f"روزهای بدهکار: {exp.debtor_days} | میانگین بدهی: {money(exp.average_debtor_balance)} | تومان‌روز منفی: {exp.debtor_toman_days:,}\n"
                f"تومان‌روز خالص: {exp.net_toman_days:,} | روزهای خنثی: {exp.neutral_days}"
            )
            self.draw_manager_chart(series)
        except Exception as exc:
            self.mgr_summary.set(f'خطا: {exc}')

    def draw_manager_chart(self, rows):
        c=self.manager_canvas; c.delete('all'); c.update_idletasks()
        w=max(c.winfo_width(),600); h=max(c.winfo_height(),300); pad=55
        if not rows: c.create_text(w/2,h/2,text='داده‌ای برای نمودار نیست'); return
        vals=[int(x['balance']) for x in rows]; lo=min(vals+[0]); hi=max(vals+[0]); span=max(hi-lo,1)
        def x(i): return pad+(w-2*pad)*(i/max(len(rows)-1,1))
        def y(v): return pad+(h-2*pad)*(hi-v)/span
        c.create_line(pad,y(0),w-pad,y(0),fill='#888',dash=(4,4)); c.create_text(8,y(0),text='0',anchor='w')
        pts=[]
        for i,v in enumerate(vals): pts += [x(i),y(v)]
        if len(pts)>=4: c.create_line(*pts,width=2,fill='#2457a6')
        elif pts: c.create_oval(pts[0]-2,pts[1]-2,pts[0]+2,pts[1]+2,fill='#2457a6')
        c.create_text(pad,h-20,text=rows[0]['shamsi_date'],anchor='w'); c.create_text(w-pad,h-20,text=rows[-1]['shamsi_date'],anchor='e')
        c.create_text(8,pad,text=money(hi),anchor='w'); c.create_text(8,h-pad,text=money(lo),anchor='w')

    def refresh_ledger(self):
        for x in self.ledger_tree.get_children(): self.ledger_tree.delete(x)
        self.ledger_rows.clear()
        for r in SERVICE.list_postings(limit=1000):
            iid=str(r['pending_id']); self.ledger_rows[iid]=r
            self.ledger_tree.insert('', 'end', iid=iid, values=(iid,r['posting_type'],money(r['display_amount']),r['description'],r.get('expense_id') or '-',r.get('transaction_id') or '-',r.get('payment_id') or '-',r.get('cheque_id') or '-',fa_status(r.get('status') or 'ACTIVE')))

    def refresh_cheques(self):
        for x in self.cheque_tree.get_children(): self.cheque_tree.delete(x)
        for r in SERVICE.list_cheques(open_only=self.open_cheques_only.get()):
            self.cheque_tree.insert('', 'end', values=(r['cheque_id'],money(r['amount']),r.get('due_date_shamsi') or '-',r.get('receiver_name') or '-',r.get('description') or r.get('expense_description') or '-',fa_status(r['status'])))

    def refresh_sales(self):
        for x in self.sales_tree.get_children(): self.sales_tree.delete(x)
        for r in SERVICE.list_sales_summary():
            self.sales_tree.insert('', 'end', values=(r['sale_id'],r.get('unit_number') or '-',r.get('buyer_name') or '-',money(r['contract_amount']),money(r['cash_received']),money(r['receivable']),money(r['overdue_amount']),r.get('next_due_shamsi') or '-',fa_status(r['status'])))

    def refresh_reconciliations(self):
        for x in self.rec_tree.get_children(): self.rec_tree.delete(x)
        for r in SERVICE.list_reconciliations():
            self.rec_tree.insert('', 'end', values=(r.get('shamsi_date') or '-',money(r['system_balance']),money(r['bank_balance']),money(r['difference']),r.get('notes') or '-'))

    def refresh_health(self):
        h=DB.health_check(); o=SERVICE.overview()
        text=(f"SQLite integrity: {h['sqlite_integrity']}\nSchema version: {h['schema_version']}\n"
              f"Sync pending/failed: {o.pending_sync} / {o.failed_sync}\nDuplicate Telegram messages: {h['duplicate_telegram_messages']}\n"
              f"DB: {CONFIG.db_path}\nGoogle Sheets: {'فعال' if CONFIG.sheets_enabled else 'خاموش'} — {CONFIG.spreadsheet_name}\n"
              f"Telegram group: {CONFIG.group_chat_id or '-'}\n\n"
              "نکته: همه اعداد داشبورد از Ledger دوباره محاسبه می‌شوند؛ مانده قابل‌ویرایش ذخیره‌شده وجود ندارد.")
        self.health_text.delete('1.0','end'); self.health_text.insert('1.0',text)

    def show_health(self):
        self.refresh_health(); self.notebook.select(self.notebook.tabs()[-1])

    # ---------- actions ----------
    def record_reconciliation(self):
        raw=self.bank_var.get().replace(',','').replace('،','').strip()
        try: bank=int(raw)
        except ValueError: messagebox.showerror('خطا','موجودی بانک باید عدد صحیح تومان باشد.'); return
        note=simpledialog.askstring('توضیح','توضیح تطبیق (اختیاری):',parent=self) or ''
        try:
            row=SERVICE.record_reconciliation(bank_balance=bank,shamsi_date=self.bank_date_var.get(),notes=note)
            messagebox.showinfo('ثبت شد',f"اختلاف بانک با سیستم: {money(row['difference'])}")
            self.refresh_overview(); self.refresh_reconciliations()
        except Exception as exc: messagebox.showerror('خطا',str(exc))

    def _selected_posting(self):
        sel=self.ledger_tree.selection()
        if not sel: messagebox.showwarning('انتخاب','ابتدا یک ثبت را انتخاب کن.'); return None
        return self.ledger_rows.get(sel[0])

    def edit_selected_posting(self):
        row=self._selected_posting()
        if not row: return
        payload=dict(row.get('payload') or {})
        EditDialog(self, row, payload, self._commit_edit)

    def _commit_edit(self, pending_id: str, changes: dict[str,Any]):
        try:
            SERVICE.edit_posting(pending_id,changes)
            messagebox.showinfo('انجام شد','همان ثبت با همان IDها اصلاح شد و Sync در صف قرار گرفت.')
            self.refresh_all()
        except Exception as exc: messagebox.showerror('ویرایش ناموفق',str(exc))

    def delete_selected_posting(self):
        row=self._selected_posting()
        if not row: return
        if not messagebox.askyesno('تأیید حذف',f"این ثبت Soft Delete شود؟\n{row['pending_id']}\n{row['description']}\n{money(row['display_amount'])}"):
            return
        target=SERVICE.posting_telegram_target(row['pending_id'])
        try:
            SERVICE.delete_posting(row['pending_id'])
        except Exception as exc:
            messagebox.showerror('حذف ناموفق',str(exc)); return
        self.refresh_all()
        if target and CONFIG.telegram_bot_token:
            chat_id,msg_id=target
            def cleanup():
                ok,detail=clear_group_reaction(CONFIG.telegram_bot_token,chat_id,msg_id)
                if not ok:
                    self.after(0,lambda: messagebox.showwarning('ثبت مالی حذف شد',f"حذف مالی انجام شد، اما پاک‌کردن 👍 از تلگرام موفق نبود:\n{detail}"))
            threading.Thread(target=cleanup,daemon=True).start()
        messagebox.showinfo('حذف شد','اثر مالی ثبت حذف شد؛ سابقه Audit در SQLite باقی مانده است.')

    def repair_ledger(self):
        if not messagebox.askyesno('اصلاح Ledger','فقط ناسازگاری‌های قطعی PAID بررسی و اصلاح شوند؟'): return
        try:
            r=SERVICE.repair_ledger(); messagebox.showinfo('نتیجه',f"تعداد اصلاح‌شده: {r['repaired_count']}\nSkipped: {r['skipped']}"); self.refresh_all()
        except Exception as exc: messagebox.showerror('خطا',str(exc))


class EditDialog(tk.Toplevel):
    def __init__(self,parent,row,payload,on_save):
        super().__init__(parent); self.title('ویرایش ثبت مالی'); self.transient(parent); self.grab_set(); self.resizable(False,False)
        self.pending_id=str(row['pending_id']); self.payload=payload; self.on_save=on_save
        ttk.Label(self,text=f"نوع: {row['posting_type']}   |   {self.pending_id}",font=('Tahoma',10,'bold')).grid(row=0,column=0,columnspan=2,padx=12,pady=10)
        fields=[
            ('amount','مبلغ'),('final_amount','مبلغ نهایی'),('invoice_amount','مبلغ فاکتور'),('paid_amount','مبلغ پرداخت‌شده'),
            ('payment_state','وضعیت پرداخت'),('description','بابت/شرح'),('expense_category','دسته هزینه'),('payment_method','روش پرداخت'),('due_date_shamsi','سررسید چک شمسی'),
        ]
        self.vars={}; self.original={}
        for i,(key,label) in enumerate(fields,1):
            val=payload.get(key)
            if val is None: val=''
            s=str(val); self.original[key]=s
            v=tk.StringVar(value=s); self.vars[key]=v
            ttk.Label(self,text=label+':').grid(row=i,column=1,sticky='e',padx=8,pady=3)
            ttk.Entry(self,textvariable=v,width=38,justify='right').grid(row=i,column=0,padx=8,pady=3)
        ttk.Label(self,text='فقط فیلدهایی که واقعاً تغییر کرده‌اند اعمال می‌شوند. نوع اصلی ثبت قابل تغییر نیست.',foreground='#555').grid(row=10,column=0,columnspan=2,padx=10,pady=(8,4))
        buttons=ttk.Frame(self); buttons.grid(row=11,column=0,columnspan=2,pady=10)
        ttk.Button(buttons,text='✅ ذخیره اصلاح',command=self.save).pack(side='right',padx=5)
        ttk.Button(buttons,text='انصراف',command=self.destroy).pack(side='right')

    def save(self):
        changes={}
        numeric={'amount','final_amount','invoice_amount','paid_amount'}
        for k,v in self.vars.items():
            now=v.get().strip()
            if now==self.original[k]: continue
            if k in numeric:
                if now=='': changes[k]=0
                else:
                    try: changes[k]=int(now.replace(',','').replace('،',''))
                    except ValueError: messagebox.showerror('خطا',f"{k} باید عدد صحیح باشد.",parent=self); return
            else: changes[k]=now
        if not changes: messagebox.showinfo('بدون تغییر','هیچ فیلدی تغییر نکرده است.',parent=self); return
        self.destroy(); self.on_save(self.pending_id,changes)


if __name__ == '__main__':
    Stage8Dashboard().mainloop()
