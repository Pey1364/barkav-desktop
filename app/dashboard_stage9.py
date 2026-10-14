from __future__ import annotations

import os
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

from config_loader import load_config
from dashboard_service_stage9 import DashboardServiceStage9
from export_utils import export_pdf, export_xlsx, print_file
from finance_db import FinanceDB
from reaction_cleanup import clear_group_reaction
from revenue_service import gregorian_to_shamsi

BASE_DIR=Path(__file__).resolve().parent
CONFIG=load_config(BASE_DIR)
DB=FinanceDB(CONFIG.db_path)
SERVICE=DashboardServiceStage9(DB,BASE_DIR)

COLORS={
    'navy':'#153B5B','blue':'#2D6F9F','cyan':'#2C8E9E','green':'#2F7D63','orange':'#C17C2C',
    'red':'#B84B4B','bg':'#EEF3F7','panel':'#FFFFFF','muted':'#637381','line':'#D8E2EA','text':'#1E2D3D','soft':'#F7FAFC'
}


def money(v:Any)->str:
    try:return f"{int(float(v or 0)):,} تومان"
    except Exception:return '-'

def num(v:Any)->str:
    try:return f"{int(float(v or 0)):,}"
    except Exception:return '-'

def fa_status(v:str)->str:
    return {'ACTIVE':'فعال','DELETED':'حذف‌شده','APPROVED':'تأییدشده','PAID':'پرداخت‌شده','PARTIALLY_PAID':'پرداخت جزئی','POSTED':'ثبت‌شده','VOIDED':'باطل‌شده','ISSUED':'صادرشده','PENDING_DUE':'در انتظار سررسید','CASHED':'پاس‌شده','RETURNED':'برگشتی','CANCELLED':'لغوشده','COMPLETED':'تکمیل‌شده','UPCOMING':'آینده','DUE':'سررسید','OVERDUE':'معوق','UNMATCHED':'تطبیق‌نشده','MATCHED':'تطبیق‌شده','FAILED':'خطا','PENDING':'در انتظار','SYNCED':'همگام','CLOSED':'تسویه‌شده'}.get(str(v or '').upper(),str(v or '-'))


class KPI(tk.Frame):
    def __init__(self,parent,title:str,accent:str):
        super().__init__(parent,bg=COLORS['panel'],highlightbackground=COLORS['line'],highlightthickness=1)
        tk.Frame(self,bg=accent,height=4).pack(fill='x')
        tk.Label(self,text=title,bg=COLORS['panel'],fg=COLORS['muted'],font=('Tahoma',9)).pack(pady=(10,2))
        self.var=tk.StringVar(value='-')
        tk.Label(self,textvariable=self.var,bg=COLORS['panel'],fg=COLORS['text'],font=('Tahoma',12,'bold')).pack(pady=(2,10))


class SmartTable(ttk.Frame):
    def __init__(self,parent,columns:list[tuple[str,str,int]],title:str=''):
        super().__init__(parent)
        self.columns=columns; self.all_rows:list[dict[str,Any]]=[]; self.filtered_rows:list[dict[str,Any]]=[]; self.row_values:Callable[[dict[str,Any]],list[Any]]|None=None
        self.quick=tk.StringVar(); self.total=tk.StringVar(value='0 مورد | جمع: 0 تومان')
        bar=ttk.Frame(self); bar.pack(fill='x',pady=(0,6))
        ttk.Label(bar,text=title,style='Section.TLabel').pack(side='right',padx=(0,10))
        ttk.Label(bar,text='فیلتر سریع:').pack(side='right'); ent=ttk.Entry(bar,textvariable=self.quick,width=28,justify='right'); ent.pack(side='right',padx=5); ent.bind('<KeyRelease>',lambda e:self.apply_filter())
        ttk.Button(bar,text='✖ پاک',command=lambda:(self.quick.set(''),self.apply_filter())).pack(side='right')
        ttk.Button(bar,text='📋 کپی',command=self.copy_selected).pack(side='left')
        ttk.Button(bar,text='📥 پیست به فیلتر',command=self.paste_filter).pack(side='left',padx=3)
        ttk.Button(bar,text='📊 Excel',command=self.export_excel).pack(side='left',padx=3)
        ttk.Button(bar,text='📄 PDF',command=self.export_pdf).pack(side='left',padx=3)
        ttk.Button(bar,text='🖨 پرینت',command=self.print_report).pack(side='left',padx=3)
        frame=ttk.Frame(self); frame.pack(fill='both',expand=True)
        cols=[c[0] for c in columns]
        self.tree=ttk.Treeview(frame,columns=cols,show='headings',selectmode='extended')
        vs=ttk.Scrollbar(frame,orient='vertical',command=self.tree.yview); hs=ttk.Scrollbar(frame,orient='horizontal',command=self.tree.xview); self.tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set)
        self.tree.grid(row=0,column=0,sticky='nsew'); vs.grid(row=0,column=1,sticky='ns'); hs.grid(row=1,column=0,sticky='ew'); frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)
        for key,label,width in columns:
            self.tree.heading(key,text=label); self.tree.column(key,width=width,anchor='center',stretch=True)
        self.tree.tag_configure('odd',background='#F7FAFC'); self.tree.tag_configure('even',background='#FFFFFF')
        ttk.Label(self,textvariable=self.total,style='Summary.TLabel').pack(fill='x',pady=(6,0))
        self.tree.bind('<Control-c>',lambda e:self.copy_selected())
        self.tree.bind('<Control-C>',lambda e:self.copy_selected())

    def set_rows(self,rows:list[dict[str,Any]],row_values:Callable[[dict[str,Any]],list[Any]]):
        self.all_rows=rows; self.row_values=row_values; self.apply_filter()

    def apply_filter(self):
        q=self.quick.get().strip().lower().replace('ي','ی').replace('ك','ک')
        if q:
            toks=q.split(); out=[]
            for r in self.all_rows:
                vals=self.row_values(r) if self.row_values else list(r.values()); hay=' '.join(str(v or '') for v in vals).lower().replace('ي','ی').replace('ك','ک')
                if all(t in hay for t in toks):out.append(r)
            self.filtered_rows=out
        else:self.filtered_rows=list(self.all_rows)
        for x in self.tree.get_children():self.tree.delete(x)
        total_amount=0
        for i,r in enumerate(self.filtered_rows):
            vals=self.row_values(r) if self.row_values else list(r.values()); iid=str(i)
            self.tree.insert('', 'end', iid=iid, values=vals, tags=('even' if i%2==0 else 'odd',))
            try: total_amount += int(r.get('_sum_amount',r.get('amount',r.get('final_amount',r.get('contract_amount',0)))) or 0)
            except Exception:pass
        self.total.set(f"{len(self.filtered_rows):,} مورد | جمع مبالغ: {total_amount:,} تومان")

    def selected_rows(self)->list[dict[str,Any]]:
        out=[]
        for iid in self.tree.selection():
            try:out.append(self.filtered_rows[int(iid)])
            except Exception:pass
        return out

    def current_report_rows(self,selected_only=False)->tuple[list[str],list[list[Any]]]:
        rows=self.selected_rows() if selected_only and self.selected_rows() else self.filtered_rows
        headers=[c[1] for c in self.columns]
        vals=[self.row_values(r) if self.row_values else list(r.values()) for r in rows]
        return headers,vals

    def copy_selected(self):
        headers,rows=self.current_report_rows(selected_only=True)
        if not rows:return
        text='\t'.join(headers)+'\n'+'\n'.join('\t'.join(str(v or '') for v in row) for row in rows)
        self.clipboard_clear();self.clipboard_append(text)

    def paste_filter(self):
        try:text=self.clipboard_get().strip()
        except Exception:return
        first=text.splitlines()[0] if text else ''
        self.quick.set(first[:300]);self.apply_filter()

    def _save(self,kind:str,do_print=False):
        headers,rows=self.current_report_rows(selected_only=False)
        ext='.xlsx' if kind=='xlsx' else '.pdf'; path=filedialog.asksaveasfilename(defaultextension=ext,filetypes=[('Excel','*.xlsx')] if kind=='xlsx' else [('PDF','*.pdf')])
        if not path:return
        if kind=='xlsx':export_xlsx(path,headers,rows,title='گزارش')
        else:export_pdf(path,headers,rows,title='گزارش',summary_lines=[self.total.get()])
        if do_print:print_file(path)
        else:messagebox.showinfo('خروجی',f'فایل ساخته شد:\n{path}')
    def export_excel(self):self._save('xlsx')
    def export_pdf(self):self._save('pdf')
    def print_report(self):
        fd,path=tempfile.mkstemp(suffix='.pdf');os.close(fd);headers,rows=self.current_report_rows(False);export_pdf(path,headers,rows,title='گزارش',summary_lines=[self.total.get()]);print_file(path)


class Stage9Dashboard(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('Peymaan V2 — Stage 9 Management'); self.geometry('1440x900'); self.minsize(1180,720); self.option_add('*Font',('Tahoma',9)); self.configure(bg=COLORS['bg']); self._style(); self._build(); self.after(200,self.refresh_all); self.after(15000,self._periodic)

    def _style(self):
        st=ttk.Style(self)
        try:st.theme_use('clam')
        except Exception:pass
        st.configure('.',font=('Tahoma',9),background=COLORS['bg'],foreground=COLORS['text'])
        st.configure('TFrame',background=COLORS['bg']);st.configure('Panel.TFrame',background=COLORS['panel'])
        st.configure('TNotebook',background=COLORS['bg'],borderwidth=0);st.configure('TNotebook.Tab',padding=(14,8),font=('Tahoma',9,'bold'));st.map('TNotebook.Tab',background=[('selected',COLORS['panel'])],foreground=[('selected',COLORS['navy'])])
        st.configure('TButton',padding=(8,5));st.configure('Primary.TButton',background=COLORS['blue'],foreground='white');st.map('Primary.TButton',background=[('active',COLORS['navy'])])
        st.configure('Danger.TButton',background=COLORS['red'],foreground='white')
        st.configure('Section.TLabel',font=('Tahoma',10,'bold'),foreground=COLORS['navy'],background=COLORS['bg'])
        st.configure('Summary.TLabel',font=('Tahoma',10,'bold'),foreground=COLORS['navy'],padding=(8,6),background='#E3EDF4')
        st.configure('Treeview',rowheight=28,background='white',fieldbackground='white');st.configure('Treeview.Heading',font=('Tahoma',9,'bold'),background='#DDE8F0',foreground=COLORS['navy'])

    def _build(self):
        top=tk.Frame(self,bg=COLORS['navy'],height=62);top.pack(fill='x')
        right=tk.Frame(top,bg=COLORS['navy']);right.pack(side='right',padx=16,pady=10)
        self.project_name_top=tk.StringVar(value='پروژه')
        tk.Label(right,text='پیمان',bg=COLORS['navy'],fg='white',font=('Tahoma',17,'bold')).pack(side='right')
        tk.Label(right,textvariable=self.project_name_top,bg=COLORS['navy'],fg='#B9D8EA',font=('Tahoma',10)).pack(side='right',padx=12)
        left=tk.Frame(top,bg=COLORS['navy']);left.pack(side='left',padx=12,pady=10)
        for text,cmd in [('🔍 جستجوی سراسری',self.open_search),('🏢 مشخصات پروژه',self.open_project),('🔄 بروزرسانی',self.refresh_all),('🧪 سلامت',self.show_health)]:
            tk.Button(left,text=text,command=cmd,bg='#214E70',fg='white',activebackground='#2D6F9F',activeforeground='white',relief='flat',padx=10,pady=6).pack(side='left',padx=3)
        self.notebook=ttk.Notebook(self);self.notebook.pack(fill='both',expand=True,padx=10,pady=10)
        self._build_overview();self._build_manager();self._build_financial();self._build_cheques();self._build_sales();self._build_reconciliation();self._build_reports();self._build_health()

    def _build_overview(self):
        tab=ttk.Frame(self.notebook,padding=12);self.notebook.add(tab,text='داشبورد')
        project=ttk.Frame(tab,style='Panel.TFrame',padding=10);project.pack(fill='x',pady=(0,10));self.project_info=tk.StringVar(value='مشخصات پروژه ثبت نشده')
        ttk.Label(project,textvariable=self.project_info,font=('Tahoma',10,'bold'),background=COLORS['panel'],foreground=COLORS['navy']).pack(side='right')
        ttk.Button(project,text='مشاهده / ویرایش مشخصات و اسناد',command=self.open_project).pack(side='left')
        grid=ttk.Frame(tab);grid.pack(fill='x')
        defs=[('cash','💰 مانده تنخواه',COLORS['blue']),('free','🟢 مانده آزاد پس از چک',COLORS['green']),('cost','🏗 هزینه ساخت',COLORS['orange']),('fee','👷 حقوق مدیر پروژه تحقق‌یافته',COLORS['cyan']),('withdraw','💸 برداشت حقوق مدیر پروژه',COLORS['red']),('manager','⚖️ مانده حساب مدیر',COLORS['blue']),('cheques','🧾 تعهد چک باز',COLORS['orange']),('sales','🏠 فروش قراردادی',COLORS['green']),('received','💵 وصول خریداران',COLORS['cyan']),('receivable','📥 مطالبات خریداران',COLORS['blue']),('overdue','⚠️ مطالبات معوق',COLORS['red']),('loans','🏦 مانده بدهی وام‌ها',COLORS['orange'])]
        self.cards={}
        for i,(k,t,c) in enumerate(defs):
            card=KPI(grid,t,c);card.grid(row=i//4,column=i%4,sticky='nsew',padx=5,pady=5);self.cards[k]=card
        for i in range(4):grid.columnconfigure(i,weight=1)
        rec=ttk.LabelFrame(tab,text='تطبیق سریع با بانک',padding=10);rec.pack(fill='x',pady=10)
        self.bank_var=tk.StringVar();self.bank_date=tk.StringVar()
        ttk.Label(rec,text='موجودی واقعی بانک:').pack(side='right');ttk.Entry(rec,textvariable=self.bank_var,width=20,justify='center').pack(side='right',padx=5);ttk.Label(rec,text='تاریخ شمسی:').pack(side='right',padx=(15,0));ttk.Entry(rec,textvariable=self.bank_date,width=14,justify='center').pack(side='right',padx=5);ttk.Button(rec,text='ثبت تطبیق',command=self.record_reconciliation,style='Primary.TButton').pack(side='right',padx=8);self.bank_info=tk.StringVar(value='آخرین تطبیق: -');ttk.Label(rec,textvariable=self.bank_info).pack(side='left')

    def _build_manager(self):
        tab=ttk.Frame(self.notebook,padding=12);self.notebook.add(tab,text='حساب مدیر')
        controls=ttk.Frame(tab);controls.pack(fill='x');self.mgr_start=tk.StringVar();self.mgr_end=tk.StringVar();ttk.Label(controls,text='از:').pack(side='right');ttk.Entry(controls,textvariable=self.mgr_start,width=14,justify='center').pack(side='right',padx=4);ttk.Label(controls,text='تا:').pack(side='right',padx=(10,0));ttk.Entry(controls,textvariable=self.mgr_end,width=14,justify='center').pack(side='right',padx=4);ttk.Button(controls,text='محاسبه',command=self.refresh_manager).pack(side='right',padx=8)
        self.mgr_summary=tk.StringVar(value='-');ttk.Label(tab,textvariable=self.mgr_summary,justify='right',style='Summary.TLabel').pack(fill='x',pady=10);self.manager_canvas=tk.Canvas(tab,bg='white',height=440,highlightthickness=1,highlightbackground=COLORS['line']);self.manager_canvas.pack(fill='both',expand=True)

    def _build_financial(self):
        tab=ttk.Frame(self.notebook,padding=8);self.notebook.add(tab,text='ثبت‌های مالی');self.fin_nb=ttk.Notebook(tab);self.fin_nb.pack(fill='both',expand=True)
        # all transactions
        t1=ttk.Frame(self.fin_nb,padding=6);self.fin_nb.add(t1,text='کلیه تراکنش‌ها');actions=ttk.Frame(t1);actions.pack(fill='x');ttk.Button(actions,text='✏️ ویرایش',command=lambda:self.edit_transaction(self.all_tx_table)).pack(side='right');ttk.Button(actions,text='🗑 حذف',command=lambda:self.delete_transaction(self.all_tx_table)).pack(side='right',padx=3);ttk.Button(actions,text='📎 رسید',command=lambda:self.receipts_for_transaction(self.all_tx_table)).pack(side='right',padx=3)
        self.all_tx_table=SmartTable(t1,[('date','تاریخ',100),('dir','نوع',70),('amount','مبلغ',130),('cat','دسته',130),('payer','واریزکننده',130),('receiver','دریافت‌کننده',130),('desc','شرح',220),('receipt','رسید',70),('status','وضعیت',90),('id','Transaction ID',150)]);self.all_tx_table.pack(fill='both',expand=True)
        # expenses
        t2=ttk.Frame(self.fin_nb,padding=6);self.fin_nb.add(t2,text='هزینه ساخت');actions=ttk.Frame(t2);actions.pack(fill='x');ttk.Button(actions,text='🏗 تعیین فاز/فعالیت',command=self.classify_expense).pack(side='right');ttk.Button(actions,text='✏️ ویرایش مالی',command=self.edit_expense).pack(side='right',padx=3);ttk.Button(actions,text='🗑 حذف',command=self.delete_expense).pack(side='right',padx=3);ttk.Button(actions,text='📎 رسید',command=self.receipts_for_expense).pack(side='right',padx=3)
        self.exp_table=SmartTable(t2,[('date','تاریخ',95),('final','مبلغ نهایی',125),('paid','پرداخت‌شده',120),('phase','مرحله ساخت',155),('activity','نوع هزینه/فعالیت',165),('payer','واریزکننده',125),('receiver','دریافت‌کننده',125),('desc','شرح',190),('receipt','رسید',65),('status','وضعیت',90),('id','Expense ID',145)]);self.exp_table.pack(fill='both',expand=True)
        # inflows
        t3=ttk.Frame(self.fin_nb,padding=6);self.fin_nb.add(t3,text='ورودی‌ها');a=ttk.Frame(t3);a.pack(fill='x');ttk.Button(a,text='✏️ ویرایش',command=lambda:self.edit_transaction(self.in_table)).pack(side='right');ttk.Button(a,text='🗑 حذف',command=lambda:self.delete_transaction(self.in_table)).pack(side='right',padx=3);ttk.Button(a,text='📎 رسید',command=lambda:self.receipts_for_transaction(self.in_table)).pack(side='right',padx=3)
        self.in_table=SmartTable(t3,[('date','تاریخ',100),('amount','مبلغ ورودی',130),('cat','نوع ورودی',140),('payer','واریزکننده',150),('desc','شرح',250),('receipt','رسید',70),('id','Transaction ID',160)]);self.in_table.pack(fill='both',expand=True)
        # outflows
        t4=ttk.Frame(self.fin_nb,padding=6);self.fin_nb.add(t4,text='خروجی‌ها');a=ttk.Frame(t4);a.pack(fill='x');ttk.Button(a,text='✏️ ویرایش',command=lambda:self.edit_transaction(self.out_table)).pack(side='right');ttk.Button(a,text='🗑 حذف',command=lambda:self.delete_transaction(self.out_table)).pack(side='right',padx=3);ttk.Button(a,text='📎 رسید',command=lambda:self.receipts_for_transaction(self.out_table)).pack(side='right',padx=3)
        self.out_table=SmartTable(t4,[('date','تاریخ',100),('amount','مبلغ خروجی',130),('cat','نوع خروجی',140),('receiver','دریافت‌کننده',150),('desc','شرح',250),('receipt','رسید',70),('id','Transaction ID',160)]);self.out_table.pack(fill='both',expand=True)
        # loans
        t5=ttk.Frame(self.fin_nb,padding=6);self.fin_nb.add(t5,text='وام‌ها');a=ttk.Frame(t5);a.pack(fill='x');ttk.Button(a,text='➕ ثبت وام',command=self.add_loan,style='Primary.TButton').pack(side='right');ttk.Button(a,text='📅 اقساط / پرداخت',command=self.loan_installments).pack(side='right',padx=3);ttk.Button(a,text='🚫 لغو وام',command=self.cancel_loan).pack(side='right',padx=3)
        self.loan_table=SmartTable(t5,[('date','تاریخ دریافت',105),('lender','بانک/وام‌دهنده',150),('principal','اصل وام',125),('received','دریافتی واقعی',125),('interest','سود+کارمزد',120),('paid','اقساط پرداختی',125),('remain','مانده بدهی',125),('count','اقساط',80),('next','قسط بعدی',105),('status','وضعیت',90),('id','Loan ID',145)]);self.loan_table.pack(fill='both',expand=True)

    def _build_cheques(self):
        tab=ttk.Frame(self.notebook,padding=8);self.notebook.add(tab,text='چک‌ها');self.cheque_table=SmartTable(tab,[('due','سررسید شمسی',110),('amount','مبلغ',130),('receiver','گیرنده',140),('bank','بانک',120),('serial','شماره چک',120),('desc','بابت',240),('status','وضعیت',100),('id','Cheque ID',160)]);self.cheque_table.pack(fill='both',expand=True)
    def _build_sales(self):
        tab=ttk.Frame(self.notebook,padding=8);self.notebook.add(tab,text='فروش و مطالبات');self.sales_table=SmartTable(tab,[('unit','واحد',80),('buyer','خریدار',150),('contract','قرارداد',130),('received','وصول',125),('remain','مانده',125),('overdue','معوق',120),('next','سررسید بعدی',110),('status','وضعیت',90),('id','Sale ID',150)]);self.sales_table.pack(fill='both',expand=True)
    def _build_reconciliation(self):
        tab=ttk.Frame(self.notebook,padding=8);self.notebook.add(tab,text='تاریخچه تطبیق بانک');self.rec_table=SmartTable(tab,[('date','تاریخ',100),('system','مانده سیستم',140),('bank','مانده بانک',140),('diff','اختلاف',140),('notes','توضیح',280)]);self.rec_table.pack(fill='both',expand=True)

    def _build_reports(self):
        tab=ttk.Frame(self.notebook,padding=8);self.notebook.add(tab,text='گزارش‌گیری')
        settings=ttk.LabelFrame(tab,text='پارامترهای پروژه و پیش‌بینی',padding=8);settings.pack(fill='x')
        self.report_vars={k:tk.StringVar() for k in ['gross_area','saleable_area','unit_count','unit_areas','inflation','months','presale','end_price','misc','target']}
        fields=[('gross_area','متراژ غیرمفید ساخت'),('saleable_area','متراژ مفید ساخت'),('unit_count','تعداد واحدها'),('unit_areas','متراژ واحدها (با , جدا)'),('inflation','تورم ماهانه %'),('months','ماه تا اتمام'),('presale','قیمت پیش‌فروش/متر'),('end_price','قیمت پایان/متر (اختیاری)'),('misc','هزینه متفرقه خارج برآورد'),('target','درصد سود هدف')]
        for i,(k,label) in enumerate(fields):
            r=i//5;c=(i%5)*2;ttk.Label(settings,text=label+':').grid(row=r,column=c+1,sticky='e',padx=3,pady=3);ttk.Entry(settings,textvariable=self.report_vars[k],width=18,justify='right').grid(row=r,column=c,sticky='ew',padx=3,pady=3)
        actions=ttk.Frame(tab);actions.pack(fill='x',pady=7);ttk.Button(actions,text='💾 ذخیره پارامترها',command=self.save_report_settings,style='Primary.TButton').pack(side='right');ttk.Button(actions,text='📥 بارگذاری/به‌روزرسانی اکسل برآورد',command=self.import_budget).pack(side='right',padx=5);self.budget_version=tk.StringVar(value='نسخه برآورد: -');ttk.Label(actions,textvariable=self.budget_version).pack(side='left')
        kgrid=ttk.Frame(tab);kgrid.pack(fill='x');keys=[('eac','برآورد هزینه نهایی پروژه',COLORS['orange']),('cmp','اختلاف با برآورد اولیه',COLORS['blue']),('profit','سود/زیان پیش‌بینی‌شده',COLORS['green']),('targetprice','قیمت فروش لازم برای سود هدف',COLORS['cyan']),('funding','کسری تأمین مالی',COLORS['red']),('area','متراژ لازم برای پیش‌فروش',COLORS['orange']),('m2gross','هزینه ساخت/متر غیرمفید',COLORS['blue']),('m2sale','تمام‌شده/متر مفید',COLORS['green'])];self.report_cards={}
        for i,(k,t,c) in enumerate(keys):card=KPI(kgrid,t,c);card.grid(row=i//4,column=i%4,sticky='nsew',padx=4,pady=4);self.report_cards[k]=card
        for i in range(4):kgrid.columnconfigure(i,weight=1)
        self.phase_table=SmartTable(tab,[('phase','فاز',220),('estimate','برآورد',130),('actual','واقعی تا امروز',130),('forecast','پیش‌بینی پایان',130),('variance','انحراف',130)],title='کنترل بودجه بر اساس فاز');self.phase_table.pack(fill='both',expand=True,pady=(6,0));self.phase_table.tree.bind('<Double-1>',self.open_phase_detail)

    def _build_health(self):
        tab=ttk.Frame(self.notebook,padding=12);self.notebook.add(tab,text='سلامت سیستم');self.health_text=tk.Text(tab,wrap='word',bg='white',fg=COLORS['text']);self.health_text.pack(fill='both',expand=True);ttk.Button(tab,text='بروزرسانی وضعیت',command=self.refresh_health).pack(pady=6)

    # ---------- refresh ----------
    def _periodic(self):
        try:self.refresh_overview()
        finally:self.after(15000,self._periodic)
    def refresh_all(self):
        self.refresh_overview();self.refresh_manager();self.refresh_financial();self.refresh_cheques();self.refresh_sales();self.refresh_reconciliation();self.refresh_reports();self.refresh_health()
    def refresh_overview(self):
        o=SERVICE.overview();loans=SERVICE.loans.loan_totals();p=SERVICE.project.get_project();self.project_name_top.set(p.get('name') or 'پروژه بدون نام');self.project_info.set(f"🏢 {p.get('name') or 'نام پروژه ثبت نشده'}   |   {p.get('address') or 'آدرس ثبت نشده'}   |   کدپستی: {p.get('postal_code') or '-'}")
        vals={'cash':money(o.cash_balance),'free':money(o.free_cash_after_cheques),'cost':money(o.construction_cost),'fee':money(o.manager_fee_accrued),'withdraw':money(o.manager_withdrawals),'manager':money(o.manager_balance),'cheques':money(o.open_cheque_commitments),'sales':money(o.contract_sales),'received':money(o.buyer_cash_received),'receivable':money(o.buyer_receivable),'overdue':money(o.buyer_overdue),'loans':money(loans['remaining'])}
        for k,v in vals.items():self.cards[k].var.set(v)
        try:self.bank_date.set(gregorian_to_shamsi(__import__('datetime').date.today())) if not self.bank_date.get() else None
        except Exception:pass
        self.bank_info.set('آخرین تطبیق: ثبت نشده' if o.bank_balance is None else f"آخرین تطبیق {o.bank_reconciled_shamsi}: بانک {money(o.bank_balance)} | اختلاف {money(o.bank_difference)}")
    def refresh_manager(self):
        try:
            exp=SERVICE.manager_exposure_shamsi(self.mgr_start.get(),self.mgr_end.get());series=SERVICE.manager_daily_series(self.mgr_start.get(),self.mgr_end.get());self.mgr_summary.set(f"حقوق مدیر پروژه تحقق‌یافته: {money(DB.snapshot().manager_fee_accrued)} | برداشت: {money(DB.snapshot().manager_withdrawals)} | مانده: {money(DB.snapshot().manager_balance)}\nروزهای طلبکار: {exp.creditor_days} | میانگین طلب: {money(exp.average_creditor_balance)} | تومان‌روز مثبت: {exp.creditor_toman_days:,}\nروزهای بدهکار: {exp.debtor_days} | میانگین بدهی: {money(exp.average_debtor_balance)} | تومان‌روز منفی: {exp.debtor_toman_days:,} | خالص: {exp.net_toman_days:,}");self.draw_manager_chart(series)
        except Exception as e:self.mgr_summary.set(str(e))
    def draw_manager_chart(self,rows):
        c=self.manager_canvas;c.delete('all');c.update_idletasks();w=max(c.winfo_width(),600);h=max(c.winfo_height(),300);pad=55
        if not rows:c.create_text(w/2,h/2,text='داده‌ای برای نمودار نیست');return
        vals=[int(x['balance']) for x in rows];lo=min(vals+[0]);hi=max(vals+[0]);span=max(hi-lo,1);x=lambda i:pad+(w-2*pad)*(i/max(len(rows)-1,1));y=lambda v:pad+(h-2*pad)*(hi-v)/span;c.create_line(pad,y(0),w-pad,y(0),fill='#9AA7B2',dash=(4,4));pts=[]
        for i,v in enumerate(vals):pts += [x(i),y(v)]
        if len(pts)>=4:c.create_line(*pts,width=2,fill=COLORS['blue']);c.create_text(pad,h-20,text=rows[0]['shamsi_date'],anchor='w');c.create_text(w-pad,h-20,text=rows[-1]['shamsi_date'],anchor='e')
    def refresh_financial(self):
        tx=SERVICE.list_transactions();self.all_tx_table.set_rows(tx,lambda r:[r.get('shamsi_date') or '-', 'ورودی' if r['direction']=='IN' else 'خروجی',money(r['amount']),r.get('category') or '-',r.get('payer_name') or '-',r.get('receiver_name') or '-',r.get('description') or '-',f"📎 {r.get('receipt_count',0)}",fa_status(r['status']),r['transaction_id']])
        ex=SERVICE.list_construction_expenses();self.exp_table.set_rows(ex,lambda r:[r.get('shamsi_date') or '-',money(r['final_amount']),money(r['paid_amount']),r.get('phase_name') or '⚠️ تعیین نشده',r.get('activity_name_display') or '⚠️ تعیین نشده',r.get('payer_name_display') or '-',r.get('receiver_name_display') or '-',r.get('description') or '-',f"📎 {r.get('receipt_count',0)}",fa_status(r['status']),r['expense_id']])
        ins=SERVICE.list_transactions(direction='IN');self.in_table.set_rows(ins,lambda r:[r.get('shamsi_date') or '-',money(r['amount']),r.get('category') or '-',r.get('payer_name') or '-',r.get('description') or '-',f"📎 {r.get('receipt_count',0)}",r['transaction_id']])
        outs=SERVICE.list_transactions(direction='OUT',nonconstruction_only=True);self.out_table.set_rows(outs,lambda r:[r.get('shamsi_date') or '-',money(r['amount']),r.get('category') or '-',r.get('receiver_name') or '-',r.get('description') or '-',f"📎 {r.get('receipt_count',0)}",r['transaction_id']])
        loans=SERVICE.loans.list_loans();self.loan_table.set_rows(loans,lambda r:[r.get('received_date_shamsi') or '-',r.get('lender_name') or '-',money(r['principal_amount']),money(r.get('net_received_amount')),money(int(r.get('total_interest') or 0)+int(r.get('bank_fees') or 0)),money(r.get('paid_total')),money(r.get('remaining_debt')),f"{r.get('paid_installments',0)}/{r.get('installment_count',0)}",f"{r.get('next_due_shamsi') or '-'} | {money(r.get('next_due_amount'))}",fa_status(r['status']),r['loan_id']])
    def refresh_cheques(self):
        rows=SERVICE.list_cheques(open_only=False);self.cheque_table.set_rows(rows,lambda r:[r.get('due_date_shamsi') or '-',money(r['amount']),r.get('receiver_name') or '-',r.get('issuer_bank') or '-',r.get('cheque_serial') or '-',r.get('description') or r.get('expense_description') or '-',fa_status(r['status']),r['cheque_id']])
    def refresh_sales(self):
        rows=SERVICE.list_sales_summary();self.sales_table.set_rows(rows,lambda r:[r.get('unit_number') or '-',r.get('buyer_name') or '-',money(r['contract_amount']),money(r['cash_received']),money(r['receivable']),money(r['overdue_amount']),r.get('next_due_shamsi') or '-',fa_status(r['status']),r['sale_id']])
    def refresh_reconciliation(self):
        rows=SERVICE.list_reconciliations();self.rec_table.set_rows(rows,lambda r:[r.get('shamsi_date') or '-',money(r['system_balance']),money(r['bank_balance']),money(r['difference']),r.get('notes') or '-'])
    def refresh_reports(self):
        s=SERVICE.budget.get_settings();mapping={'gross_area':'gross_area','saleable_area':'saleable_area','unit_count':'unit_count','inflation':'monthly_inflation','months':'remaining_months','presale':'presale_price_per_m2','end_price':'end_sale_price_override','misc':'unbudgeted_misc','target':'target_profit_percent'}
        for vk,sk in mapping.items():self.report_vars[vk].set('' if s.get(sk) is None else str(s.get(sk) or ''))
        self.report_vars['unit_areas'].set(', '.join(str(x) for x in s.get('unit_areas',[])))
        v=SERVICE.budget.latest_version();self.budget_version.set(f"نسخه برآورد: {v.get('version_no')} — {v.get('title')}" if v else 'نسخه برآورد: -')
        f=SERVICE.budget.forecast();diff=f.forecast_total_cost-f.initial_budget;self.report_cards['eac'].var.set(money(f.forecast_total_cost));self.report_cards['cmp'].var.set(f"{money(diff)} ({(diff/f.initial_budget*100 if f.initial_budget else 0):+.1f}%)");self.report_cards['profit'].var.set(f"{money(f.projected_profit)} | {f.projected_profit_percent:+.1f}%");self.report_cards['targetprice'].var.set(f"{money(f.suggested_remaining_sale_price_per_m2)}/متر");self.report_cards['funding'].var.set(money(f.funding_gap));self.report_cards['area'].var.set(f"{f.presale_area_needed_m2:,.1f} مترمربع");self.report_cards['m2gross'].var.set(f"{money(f.construction_cost_per_gross_m2)}/متر");self.report_cards['m2sale'].var.set(f"{money(f.total_cost_per_saleable_m2)}/متر")
        rows=SERVICE.budget.phase_summary();self.phase_table.set_rows(rows,lambda r:[r['phase'],money(r['estimate']),money(r['actual']),money(r['forecast']),money(r['variance'])])
    def refresh_health(self):
        h=DB.health_check();o=SERVICE.overview();v=SERVICE.budget.latest_version();p=SERVICE.project.get_project();text=f"SQLite integrity: {h['sqlite_integrity']}\nSchema version: {h['schema_version']}\nDB: {CONFIG.db_path}\nGoogle Sheets: {'فعال' if CONFIG.sheets_enabled else 'خاموش'} — {CONFIG.spreadsheet_name}\nTelegram group: {CONFIG.group_chat_id or '-'}\nSync pending/failed: {o.pending_sync}/{o.failed_sync}\nپروژه: {p.get('name') or '-'}\nنسخه برآورد: {v.get('version_no') if v else '-'}\n\nSQLite مرجع اصلی سیستم است. Google Sheets فقط Mirror است."
        self.health_text.delete('1.0','end');self.health_text.insert('1.0',text)
    def show_health(self):self.refresh_health();self.notebook.select(self.notebook.tabs()[-1])

    # ---------- actions ----------
    def record_reconciliation(self):
        try:bank=int(self.bank_var.get().replace(',','').replace('،','').strip());note=simpledialog.askstring('توضیح','توضیح تطبیق (اختیاری):',parent=self) or '';r=SERVICE.record_reconciliation(bank_balance=bank,shamsi_date=self.bank_date.get(),notes=note);messagebox.showinfo('ثبت شد',f"اختلاف: {money(r['difference'])}");self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e))
    def _one(self,table:SmartTable):
        rows=table.selected_rows()
        if not rows:messagebox.showwarning('انتخاب','یک ردیف را انتخاب کن.');return None
        return rows[0]
    def edit_transaction(self,table):
        r=self._one(table)
        if not r:return
        if r.get('pending_id'):
            p=DB.get_pending_item(r['pending_id']);PostingEditDialog(self,r['pending_id'],dict(p['payload']) if p else {},lambda changes:self._save_posting_edit(r['pending_id'],changes));return
        TransactionEditDialog(self,r,lambda changes:self._save_tx_edit(r['transaction_id'],changes))
    def _save_tx_edit(self,tid,changes):
        try:SERVICE.edit_manual_transaction(tid,**changes);self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e))
    def _save_posting_edit(self,pid,changes):
        try:SERVICE.edit_posting(pid,changes);self.refresh_all();messagebox.showinfo('انجام شد','ثبت با همان ID اصلاح شد.')
        except Exception as e:messagebox.showerror('خطا',str(e))
    def delete_transaction(self,table):
        r=self._one(table)
        if not r:return
        if not messagebox.askyesno('حذف','ثبت انتخاب‌شده Soft Delete شود؟'):return
        try:
            if r.get('pending_id'):SERVICE.delete_posting(r['pending_id'])
            else:SERVICE.delete_manual_transaction(r['transaction_id'])
            self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e))
    def edit_expense(self):
        r=self._one(self.exp_table)
        if not r:return
        if not r.get('pending_id'):messagebox.showwarning('ویرایش','این هزینه به Posting تلگرام متصل نیست؛ فعلاً فاز/فعالیت و طرفین آن را از دکمه تعیین فاز اصلاح کن.');return
        p=DB.get_pending_item(r['pending_id']);PostingEditDialog(self,r['pending_id'],dict(p['payload']) if p else {},lambda changes:self._save_posting_edit(r['pending_id'],changes))
    def delete_expense(self):
        r=self._one(self.exp_table)
        if not r:return
        if not r.get('pending_id'):messagebox.showwarning('حذف','این هزینه Posting متصل ندارد.');return
        if messagebox.askyesno('حذف','هزینه و اثر مالی آن Soft Delete شود؟'):
            try:SERVICE.delete_posting(r['pending_id']);self.refresh_all()
            except Exception as e:messagebox.showerror('خطا',str(e))
    def classify_expense(self):
        r=self._one(self.exp_table)
        if r:ExpenseClassifyDialog(self,r,lambda p,a,py,rc:self._save_classification(r['expense_id'],p,a,py,rc))
    def _save_classification(self,eid,p,a,py,rc):
        try:SERVICE.budget.classify_expense(eid,p,a,py,rc);self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e))
    def receipts_for_transaction(self,table):
        r=self._one(table)
        if r:ReceiptDialog(self,[('TRANSACTION',r['transaction_id'])],lambda p:SERVICE.attach_receipt('TRANSACTION',r['transaction_id'],p),self.refresh_all)
    def receipts_for_expense(self):
        r=self._one(self.exp_table)
        if not r:return
        ents=[('EXPENSE',r['expense_id'])]
        if r.get('transaction_id'):ents.append(('TRANSACTION',r['transaction_id']))
        ReceiptDialog(self,ents,lambda p:SERVICE.attach_receipt('EXPENSE',r['expense_id'],p),self.refresh_all)
    def add_loan(self):LoanDialog(self,lambda data:self._create_loan(data))
    def _create_loan(self,data):
        try:SERVICE.loans.create_loan(**data);SERVICE.loans.ensure_reminders();self.refresh_all();messagebox.showinfo('ثبت شد','وام ثبت شد و مبلغ واقعی دریافتی در ورودی تنخواه قرار گرفت.')
        except Exception as e:messagebox.showerror('خطا',str(e))
    def loan_installments(self):
        r=self._one(self.loan_table)
        if r:LoanInstallmentDialog(self,r['loan_id'],self.refresh_all)
    def cancel_loan(self):
        r=self._one(self.loan_table)
        if r and messagebox.askyesno('لغو','وام لغو شود؟ (تراکنش‌های قبلی خودکار حذف نمی‌شوند)'):
            SERVICE.loans.cancel_loan(r['loan_id']);self.refresh_all()
    def save_report_settings(self):
        try:
            unit_areas=[float(x.strip()) for x in self.report_vars['unit_areas'].get().replace('،',',').split(',') if x.strip()]
            SERVICE.budget.save_settings(gross_area=float(self.report_vars['gross_area'].get() or 0),saleable_area=float(self.report_vars['saleable_area'].get() or 0),unit_count=int(self.report_vars['unit_count'].get() or 0),unit_areas=unit_areas,monthly_inflation=float(self.report_vars['inflation'].get() or 0),remaining_months=int(self.report_vars['months'].get() or 0),presale_price_per_m2=int(self.report_vars['presale'].get().replace(',','') or 0),end_sale_price_override=(int(self.report_vars['end_price'].get().replace(',','')) if self.report_vars['end_price'].get().strip() else None),unbudgeted_misc=int(self.report_vars['misc'].get().replace(',','') or 0),target_profit_percent=float(self.report_vars['target'].get() or 0));self.refresh_reports();messagebox.showinfo('ذخیره شد','پارامترهای گزارش‌گیری ذخیره شدند.')
        except Exception as e:messagebox.showerror('خطا',str(e))
    def import_budget(self):
        path=filedialog.askopenfilename(filetypes=[('Excel','*.xlsx')]);
        if not path:return
        title=simpledialog.askstring('عنوان نسخه','عنوان این نسخه برآورد:',parent=self) or ''
        try:r=SERVICE.budget.import_budget_xlsx(path,title);self.refresh_reports();messagebox.showinfo('برآورد بارگذاری شد',f"نسخه {r['version_no']} | جمع برآورد فایل: {money(r['total_estimate'])}")
        except Exception as e:messagebox.showerror('خطا',str(e))
    def open_phase_detail(self,event=None):
        r=self._one(self.phase_table)
        if not r:return
        PhaseDetailDialog(self,r['phase'])
    def open_search(self):SearchWindow(self)
    def open_project(self):ProjectDialog(self,self.refresh_all)


class PostingEditDialog(tk.Toplevel):
    def __init__(self,parent,pid,payload,on_save):
        super().__init__(parent);self.title('ویرایش ثبت مالی');self.transient(parent);self.grab_set();self.on_save=on_save;self.vars={};self.orig={}
        fields=[('amount','مبلغ'),('final_amount','مبلغ نهایی'),('invoice_amount','مبلغ فاکتور'),('paid_amount','پرداخت‌شده'),('description','شرح'),('expense_category','دسته'),('payment_method','روش پرداخت'),('due_date_shamsi','سررسید چک')]
        ttk.Label(self,text=f'Posting: {pid}',font=('Tahoma',10,'bold')).grid(row=0,column=0,columnspan=2,padx=10,pady=8)
        for i,(k,l) in enumerate(fields,1):v=str(payload.get(k) if payload.get(k) is not None else '');self.orig[k]=v;self.vars[k]=tk.StringVar(value=v);ttk.Label(self,text=l+':').grid(row=i,column=1,sticky='e',padx=5,pady=3);ttk.Entry(self,textvariable=self.vars[k],width=38,justify='right').grid(row=i,column=0,padx=5,pady=3)
        ttk.Button(self,text='ذخیره',command=self.save,style='Primary.TButton').grid(row=10,column=0,columnspan=2,pady=10)
    def save(self):
        ch={};nums={'amount','final_amount','invoice_amount','paid_amount'}
        for k,v in self.vars.items():
            s=v.get().strip()
            if s==self.orig[k]:continue
            ch[k]=int(s.replace(',','') or 0) if k in nums else s
        if ch:self.destroy();self.on_save(ch)

class TransactionEditDialog(tk.Toplevel):
    def __init__(self,parent,row,on_save):
        super().__init__(parent);self.title('ویرایش تراکنش');self.transient(parent);self.grab_set();self.on_save=on_save
        vals={'amount':str(row.get('amount') or 0),'shamsi_date':row.get('shamsi_date') or '','payer_name':row.get('payer_name') or '','receiver_name':row.get('receiver_name') or '','description':row.get('description') or ''};self.vars={k:tk.StringVar(value=v) for k,v in vals.items()}
        for i,(k,l) in enumerate([('amount','مبلغ'),('shamsi_date','تاریخ شمسی'),('payer_name','واریزکننده'),('receiver_name','دریافت‌کننده'),('description','شرح')]):ttk.Label(self,text=l+':').grid(row=i,column=1,sticky='e',padx=6,pady=4);ttk.Entry(self,textvariable=self.vars[k],width=42,justify='right').grid(row=i,column=0,padx=6,pady=4)
        ttk.Button(self,text='ذخیره',command=self.save,style='Primary.TButton').grid(row=6,column=0,columnspan=2,pady=10)
    def save(self):
        try:d={k:v.get().strip() for k,v in self.vars.items()};d['amount']=int(d['amount'].replace(',',''));self.destroy();self.on_save(d)
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

class ExpenseClassifyDialog(tk.Toplevel):
    def __init__(self,parent,row,on_save):
        super().__init__(parent);self.title('مرحله ساخت و نوع هزینه');self.transient(parent);self.grab_set();self.on_save=on_save;self.phases=SERVICE.budget.list_phases();self.phase_map={p['name']:p['phase_id'] for p in self.phases};self.pv=tk.StringVar(value=row.get('phase_name') or '');self.av=tk.StringVar(value=row.get('activity_name_display') or '');self.py=tk.StringVar(value=row.get('payer_name_display') or '');self.rc=tk.StringVar(value=row.get('receiver_name_display') or '')
        ttk.Label(self,text='مرحله ساخت:').grid(row=0,column=1,sticky='e',padx=6,pady=5);self.pc=ttk.Combobox(self,textvariable=self.pv,values=list(self.phase_map),state='readonly',width=42);self.pc.grid(row=0,column=0,padx=6,pady=5);self.pc.bind('<<ComboboxSelected>>',lambda e:self.load_acts())
        ttk.Label(self,text='نوع هزینه/فعالیت:').grid(row=1,column=1,sticky='e',padx=6,pady=5);self.ac=ttk.Combobox(self,textvariable=self.av,state='readonly',width=42);self.ac.grid(row=1,column=0,padx=6,pady=5)
        for i,(v,l) in enumerate([(self.py,'نام واریزکننده'),(self.rc,'نام دریافت‌کننده')],2):ttk.Label(self,text=l+':').grid(row=i,column=1,sticky='e',padx=6,pady=5);ttk.Entry(self,textvariable=v,width=44,justify='right').grid(row=i,column=0,padx=6,pady=5)
        self.load_acts();ttk.Button(self,text='ذخیره دسته‌بندی',command=self.save,style='Primary.TButton').grid(row=5,column=0,columnspan=2,pady=10)
    def load_acts(self):
        pid=self.phase_map.get(self.pv.get());self.acts=SERVICE.budget.list_activities(pid) if pid else [];self.act_map={a['name']:a['activity_id'] for a in self.acts};self.ac['values']=list(self.act_map)
        if self.av.get() not in self.act_map:self.av.set('')
    def save(self):
        pid=self.phase_map.get(self.pv.get());aid=self.act_map.get(self.av.get())
        if not pid or not aid:messagebox.showerror('خطا','فاز و فعالیت را انتخاب کن.',parent=self);return
        self.destroy();self.on_save(pid,aid,self.py.get(),self.rc.get())

class ReceiptDialog(tk.Toplevel):
    def __init__(self,parent,entities,on_add,on_refresh):
        super().__init__(parent);self.title('رسیدها و مدارک تراکنش');self.transient(parent);self.grab_set();self.entities=entities;self.on_add=on_add;self.on_refresh=on_refresh;self.tree=ttk.Treeview(self,columns=('type','file'),show='headings');self.tree.heading('type',text='نوع');self.tree.heading('file',text='فایل');self.tree.column('type',width=120);self.tree.column('file',width=420);self.tree.pack(fill='both',expand=True,padx=8,pady=8);bar=ttk.Frame(self);bar.pack(fill='x',padx=8,pady=(0,8));ttk.Button(bar,text='➕ افزودن رسید',command=self.add).pack(side='right');ttk.Button(bar,text='👁 باز کردن',command=self.open).pack(side='right',padx=4);self.refresh()
    def refresh(self):
        for x in self.tree.get_children():self.tree.delete(x)
        self.rows=SERVICE.receipt_list(self.entities)
        for i,r in enumerate(self.rows):self.tree.insert('', 'end',iid=str(i),values=(r.get('document_type'),r.get('local_path')))
    def add(self):
        p=filedialog.askopenfilename(filetypes=[('مدارک','*.jpg *.jpeg *.png *.pdf'),('همه','*.*')])
        if p:self.on_add(p);self.refresh();self.on_refresh()
    def open(self):
        s=self.tree.selection()
        if s:SERVICE.attachments.open(self.rows[int(s[0])]['attachment_id'])

class LoanDialog(tk.Toplevel):
    def __init__(self,parent,on_save):
        super().__init__(parent);self.title('ثبت وام جدید');self.transient(parent);self.grab_set();self.on_save=on_save;keys=[('lender_name','بانک/وام‌دهنده'),('principal_amount','اصل وام'),('net_received_amount','مبلغ واقعی واریزی'),('received_date_shamsi','تاریخ دریافت'),('interest_rate','نرخ سود %'),('total_interest','کل سود'),('bank_fees','کارمزد'),('installment_count','تعداد اقساط'),('installment_amount','مبلغ هر قسط'),('first_due_date_shamsi','تاریخ اولین قسط'),('guarantors','ضامنین'),('collateral','وثیقه'),('contract_number','شماره قرارداد'),('description','توضیحات')];self.vars={k:tk.StringVar() for k,_ in keys}
        for i,(k,l) in enumerate(keys):ttk.Label(self,text=l+':').grid(row=i,column=1,sticky='e',padx=6,pady=3);ttk.Entry(self,textvariable=self.vars[k],width=42,justify='right').grid(row=i,column=0,padx=6,pady=3)
        ttk.Button(self,text='ثبت وام + ورودی تنخواه',command=self.save,style='Primary.TButton').grid(row=len(keys)+1,column=0,columnspan=2,pady=10)
    def save(self):
        try:
            d={k:v.get().strip() for k,v in self.vars.items()};
            for k in ['principal_amount','net_received_amount','total_interest','bank_fees','installment_count','installment_amount']:d[k]=int(d[k].replace(',','') or 0)
            d['interest_rate']=float(d['interest_rate'] or 0);d['loan_type']='BANK';self.destroy();self.on_save(d)
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

class LoanInstallmentDialog(tk.Toplevel):
    def __init__(self,parent,loan_id,on_refresh):
        super().__init__(parent);self.title('اقساط وام');self.geometry('900x520');self.transient(parent);self.loan_id=loan_id;self.on_refresh=on_refresh;self.tree=ttk.Treeview(self,columns=('no','due','amount','paid','principal','interest','status'),show='headings');labs={'no':'قسط','due':'سررسید','amount':'مبلغ','paid':'پرداخت‌شده','principal':'اصل','interest':'سود/کارمزد','status':'وضعیت'}
        for c in self.tree['columns']:self.tree.heading(c,text=labs[c]);self.tree.column(c,width=120,anchor='center')
        self.tree.pack(fill='both',expand=True,padx=8,pady=8);ttk.Button(self,text='💸 ثبت پرداخت قسط',command=self.pay).pack(pady=6);self.refresh()
    def refresh(self):
        for x in self.tree.get_children():self.tree.delete(x)
        self.rows=SERVICE.loans.list_installments(self.loan_id)
        for i,r in enumerate(self.rows):self.tree.insert('', 'end',iid=str(i),values=(r['installment_number'],r.get('due_date_shamsi') or '-',money(r['amount']),money(r['paid_amount']),money(r['principal_component']),money(r['interest_component']),fa_status(r['status'])))
    def pay(self):
        s=self.tree.selection()
        if not s:return
        r=self.rows[int(s[0])];remain=int(r['amount'])-int(r['paid_amount']);amount=simpledialog.askinteger('مبلغ',f'مانده این قسط: {money(remain)}\nمبلغ پرداخت:',parent=self,minvalue=1,maxvalue=remain)
        if not amount:return
        sh=simpledialog.askstring('تاریخ','تاریخ شمسی پرداخت:',parent=self)
        if not sh:return
        try:SERVICE.loans.pay_installment(r['loan_installment_id'],amount=amount,paid_date_shamsi=sh);self.refresh();self.on_refresh()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

class ProjectDialog(tk.Toplevel):
    def __init__(self,parent,on_refresh):
        super().__init__(parent);self.title('مشخصات پروژه و آرشیو اسناد');self.geometry('1000x650');self.transient(parent);self.grab_set();self.on_refresh=on_refresh;p=SERVICE.project.get_project();self.vars={k:tk.StringVar(value=p.get(k) or '') for k in ['name','address','postal_code','description']}
        form=ttk.LabelFrame(self,text='مشخصات پروژه',padding=8);form.pack(fill='x',padx=8,pady=8)
        for i,(k,l) in enumerate([('name','نام پروژه'),('address','آدرس'),('postal_code','کد پستی'),('description','توضیحات')]):ttk.Label(form,text=l+':').grid(row=i//2,column=(i%2)*2+1,sticky='e',padx=4,pady=4);ttk.Entry(form,textvariable=self.vars[k],width=45,justify='right').grid(row=i//2,column=(i%2)*2,padx=4,pady=4)
        ttk.Button(form,text='💾 ذخیره مشخصات',command=self.save,style='Primary.TButton').grid(row=2,column=0,columnspan=4,pady=5)
        docs=ttk.LabelFrame(self,text='اسکن سند، جواز، پایان کار و سایر مدارک',padding=8);docs.pack(fill='both',expand=True,padx=8,pady=8);self.tree=ttk.Treeview(docs,columns=('type','title','path'),show='headings');self.tree.heading('type',text='نوع سند');self.tree.heading('title',text='عنوان');self.tree.heading('path',text='فایل آرشیو');self.tree.column('type',width=140);self.tree.column('title',width=220);self.tree.column('path',width=520);self.tree.pack(fill='both',expand=True);bar=ttk.Frame(docs);bar.pack(fill='x',pady=5);ttk.Button(bar,text='➕ افزودن اسکن/فایل',command=self.add).pack(side='right');ttk.Button(bar,text='👁 باز کردن',command=self.open).pack(side='right',padx=3);ttk.Button(bar,text='🖨 پرینت سند',command=self.print_doc).pack(side='right',padx=3);ttk.Button(bar,text='🗑 حذف از آرشیو',command=self.delete).pack(side='right',padx=3);self.refresh_docs()
    def save(self):SERVICE.project.save_project(**{k:v.get() for k,v in self.vars.items()});self.on_refresh();messagebox.showinfo('ذخیره شد','مشخصات پروژه ذخیره شد.',parent=self)
    def refresh_docs(self):
        for x in self.tree.get_children():self.tree.delete(x)
        self.rows=SERVICE.project.list_documents()
        for i,r in enumerate(self.rows):self.tree.insert('', 'end',iid=str(i),values=(r['document_type'],r['title'],r['local_path']))
    def _selected(self):
        s=self.tree.selection();return self.rows[int(s[0])] if s else None
    def add(self):
        p=filedialog.askopenfilename(filetypes=[('اسناد','*.pdf *.jpg *.jpeg *.png'),('همه','*.*')])
        if not p:return
        typ=simpledialog.askstring('نوع سند','نوع سند (سند / جواز / پایان کار / پروانه / سایر):',parent=self) or 'سایر';title=simpledialog.askstring('عنوان','عنوان سند:',parent=self) or Path(p).stem;SERVICE.project.add_document(p,document_type=typ,title=title);self.refresh_docs()
    def open(self):
        r=self._selected();
        if r:SERVICE.project.open_document(r['document_id'])
    def print_doc(self):
        r=self._selected();
        if r:
            try:SERVICE.project.print_document(r['document_id'])
            except Exception as e:messagebox.showerror('پرینت',str(e),parent=self)
    def delete(self):
        r=self._selected();
        if r and messagebox.askyesno('حذف','سند از فهرست آرشیو حذف شود؟',parent=self):SERVICE.project.delete_document(r['document_id']);self.refresh_docs()

class SearchWindow(tk.Toplevel):
    def __init__(self,parent):
        super().__init__(parent);self.title('جستجوی سراسری');self.geometry('1200x700');self.transient(parent);top=ttk.Frame(self,padding=8);top.pack(fill='x');self.scope=tk.StringVar(value='همه');self.query=tk.StringVar();self.dfrom=tk.StringVar();self.dto=tk.StringVar();self.amin=tk.StringVar();self.amax=tk.StringVar();ttk.Label(top,text='جستجو در:').pack(side='right');ttk.Combobox(top,textvariable=self.scope,values=['همه','کلیه تراکنش‌ها','هزینه ساخت','ورودی‌ها','خروجی‌ها','وام‌ها','چک‌ها','فروش و مطالبات'],state='readonly',width=18).pack(side='right',padx=4);ttk.Label(top,text='عبارت:').pack(side='right');e=ttk.Entry(top,textvariable=self.query,width=28,justify='right');e.pack(side='right',padx=4);e.bind('<Return>',lambda ev:self.run());ttk.Label(top,text='از تاریخ:').pack(side='right');ttk.Entry(top,textvariable=self.dfrom,width=11).pack(side='right');ttk.Label(top,text='تا:').pack(side='right');ttk.Entry(top,textvariable=self.dto,width=11).pack(side='right');ttk.Button(top,text='🔎 جستجو',command=self.run,style='Primary.TButton').pack(side='left')
        self.table=SmartTable(self,[('source','نوع',100),('date','تاریخ',100),('amount','مبلغ',130),('dir','جهت',70),('person','شخص/طرف حساب',160),('desc','شرح',300),('status','وضعیت',100),('receipt','رسید',70),('id','ID',160)]);self.table.pack(fill='both',expand=True,padx=8,pady=8);self.run()
    def run(self):
        try:rows=SERVICE.search(self.query.get(),self.scope.get(),date_from=self.dfrom.get().strip(),date_to=self.dto.get().strip());self.table.set_rows(rows,lambda r:[r['source'],r['date'],money(r['amount']),'ورودی' if r['direction']=='IN' else 'خروجی',r['person'],r['description'],fa_status(r['status']),f"📎 {r['receipt_count']}",r['id']])
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

class PhaseDetailDialog(tk.Toplevel):
    def __init__(self,parent,phase):
        super().__init__(parent);self.title(f'جزئیات فاز — {phase}');self.geometry('1000x650');rows=[r for r in SERVICE.budget.report_rows() if r['phase']==phase];self.table=SmartTable(self,[('act','فعالیت',260),('estimate','برآورد',140),('actual','واقعی',140),('remain','مانده بودجه',140),('forecast','پیش‌بینی پایان',140),('var','انحراف',140)],title=phase);self.table.pack(fill='both',expand=True,padx=8,pady=8);self.table.set_rows(rows,lambda r:[r['activity'],money(r['estimate']),money(r['actual']),money(r['remaining_budget']),money(r['forecast']),money(r['variance'])])

if __name__=='__main__':Stage9Dashboard().mainloop()
