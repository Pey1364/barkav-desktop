from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import dashboard_stage18 as v18
from dashboard_stage18 import (
    DARK, DB, SERVICE, CONFIG, BASE_DIR, APPROVAL, Image, ImageTk,
    DateField, SearchableCombo, SmartTable, CompactTable,
    fa, group_int, parse_int, bind_grouped_number, add_tooltip,
    normalize_shamsi, shamsi_to_gregorian, gregorian_to_shamsi,
    CHEQUE_TYPE_FA, REG_FA,
)
from loan_service import LoanService, _add_months
from revenue_service import RevenueService
from v18_store import load_profile, save_profile, load_ui, save_ui
from unit_service import UnitService

VERSION = '18.1'
v18.VERSION = VERSION

# ---------------------------------------------------------------------------
# V18.1 transaction schema corrections
# ---------------------------------------------------------------------------
v18.PARTNER_KIND[:] = ['قرض', 'تزریق پول']


def special_fields_181(title: str, subtype: str):
    F=v18.FieldDef
    if title == 'هزینه ساخت' and subtype == 'نقدی':
        return [
            F('payer_name','واریزکننده'), F('receiver_name','گیرنده'), F('description','بابت'),
            F('cost_group','دسته‌بندی','combo',tuple(v18.COST_GROUPS)),
            F('contract_id','انتخاب قرارداد','contract'),
            F('payment_method','روش پرداخت','combo',('واریز بانکی','نقدی/کارتخوان')),
            F('invoice_amount','مبلغ فاکتور','money'), F('final_amount','مبلغ نهایی','money'), F('discount_amount','تخفیف','money'),
            F('payment_state','وضعیت پرداخت','combo',tuple(v18.PAYMENT_STATE)), F('total_debt','کل بدهی','money'), F('remaining_debt','مانده بدهی','money'),
            F('main_phase','فاز اصلی','phase'), F('sub_phase','فاز فرعی','subphase'),
        ]
    if title == 'هزینه ساخت' and subtype == 'چک':
        return [
            F('payer_name','واریزکننده'), F('receiver_name','گیرنده'), F('description','بابت'),
            F('cost_group','دسته‌بندی','combo',tuple(v18.COST_GROUPS)),
            F('contract_id','انتخاب قرارداد','contract'),
            F('issuer_name','صاحب حساب'), F('issuer_bank','نام بانک'),
            F('cheque_type','نوع چک','combo',tuple(v18.CHEQUE_KIND)), F('cheque_registration_state','وضعیت ثبت چک','combo',tuple(v18.CHEQUE_REG)),
            F('due_date_shamsi','تاریخ سررسید','date'), F('cheque_amount','مبلغ چک','money'),
            F('cheque_status','وضعیت چک','combo',tuple(v18.CHEQUE_STATUS)), F('is_guarantee','بابت ضمانت','check'),
            F('invoice_amount','مبلغ فاکتور','money'), F('final_amount','مبلغ نهایی','money'), F('discount_amount','تخفیف','money'),
            F('payment_state','وضعیت پرداخت','combo',tuple(v18.PAYMENT_STATE)), F('total_debt','کل بدهی','money'), F('remaining_debt','مانده بدهی','money'),
            F('main_phase','فاز اصلی','phase'), F('sub_phase','فاز فرعی','subphase'),
        ]
    if title == 'ورودی' and subtype == 'تسهیلات':
        return [
            F('loan_name','نام وام'), F('loan_bank','نام بانک'), F('loan_total_amount','مبلغ تسهیلات','money'),
            F('installment_count','تعداد اقساط','int'), F('interest_rate','درصد سود','float'),
            F('guarantor_1','ضامن ۱'), F('guarantor_2','ضامن ۲'), F('guarantor_3','ضامن ۳'),
            F('loan_start_date','تاریخ شروع','date'), F('loan_end_date','تاریخ پایان','date'),
        ]
    if title == 'ورودی' and subtype == 'فروش':
        return [
            F('sale_id','شناسه فروش','sale'), F('sale_unit','واحد فروخته‌شده','saleunit'),
            F('sold_area','متراژ فروخته‌شده (M2)','float'), F('buyer_name','خریدار','entry',readonly=True),
            F('payer_name','واریزکننده','entry',readonly=True),
        ]
    if title == 'ورودی' and subtype == 'شرکا/قرض':
        return [
            F('partner_name','نام واریزکننده','combo',('پیمان','پیام','سامان','سایر')), F('partner_other_name','نام واریزکننده (سایر)'),
            F('partner_kind','نوع واریز','combo',('قرض','تزریق پول')),
            F('loan_days','مدت قرض (روز)','int'), F('partner_return_date','تاریخ برگشت قرض','date'),
        ]
    if title == 'ورودی' and subtype == 'سایر':
        return [F('payer_name','واریزکننده'), F('description','بابت')]
    if title == 'خروجی' and subtype == 'اقساط':
        return [
            F('payer_name','واریزکننده'), F('loan_id','نام وام','loan'),
            F('loan_bank','نام بانک','entry',readonly=True), F('loan_total_amount','مبلغ کل تسهیلات','money',readonly=True),
            F('installment_count','تعداد کل اقساط','int',readonly=True), F('paid_installments_before','اقساط پرداخت‌شده قبلی','int',readonly=True),
            F('installments_paid_now','تعداد اقساط پرداختی کنونی','int'), F('remaining_installments','تعداد اقساط باقی‌مانده','int',readonly=True),
        ]
    if title == 'خروجی' and subtype == 'سایر':
        return [F('payer_name','واریزکننده'), F('receiver_name','گیرنده'), F('description','بابت'), F('payment_method','روش پرداخت','combo',tuple(v18.PAYMENT_METHODS))]
    if title == 'یادداشت' and subtype == 'اطلاع‌رسانی':
        return [F('description','متن اطلاع‌رسانی','text')]
    if title == 'یادداشت' and subtype == 'داکیومنت':
        return [F('description','شرح سند','text'), F('link_pending_id','شناسه رکورد مرتبط')]
    return []


def wizard_steps_181(title: str, subtype: str):
    fields=special_fields_181(title,subtype)
    # Logical groupings; maximum three fields except the explicitly requested
    # four-field amount row which is split into 2+2 in the wizard.
    keys=[f.key for f in fields]
    groups=[]
    preferred=[]
    if title=='هزینه ساخت' and subtype=='نقدی':
        preferred=[['payer_name','receiver_name'],['description','payment_method'],['invoice_amount','final_amount'],['discount_amount','payment_state'],['total_debt','remaining_debt'],['main_phase','sub_phase']]
    elif title=='هزینه ساخت' and subtype=='چک':
        preferred=[['payer_name','receiver_name'],['description','is_guarantee'],['issuer_name','issuer_bank','cheque_type'],['cheque_registration_state','due_date_shamsi','cheque_amount'],['cheque_status'],['invoice_amount','final_amount','discount_amount'],['payment_state','total_debt','remaining_debt'],['main_phase','sub_phase']]
    elif title=='ورودی' and subtype=='تسهیلات':
        preferred=[['loan_name','loan_bank','loan_total_amount'],['installment_count','interest_rate'],['guarantor_1','guarantor_2','guarantor_3'],['loan_start_date','loan_end_date']]
    elif title=='ورودی' and subtype=='فروش':
        preferred=[['sale_id','sale_unit'],['sold_area','buyer_name','payer_name']]
    elif title=='ورودی' and subtype=='شرکا/قرض':
        preferred=[['partner_name','partner_other_name'],['partner_kind','loan_days','partner_return_date']]
    elif title=='خروجی' and subtype=='اقساط':
        preferred=[['payer_name','loan_id'],['loan_bank','loan_total_amount'],['installment_count','paid_installments_before'],['installments_paid_now','remaining_installments']]
    by={f.key:f for f in fields}
    for g in preferred:
        arr=[by[k] for k in g if k in by]
        if arr:groups.append(arr)
    used={f.key for g in groups for f in g}
    # cost_group is asked on the wizard's first window, so it must not fall
    # through to a page of its own here as well.
    rest=[f for f in fields if f.key not in used and f.key!='cost_group']
    for i in range(0,len(rest),3):groups.append(rest[i:i+3])
    return groups

v18._special_fields = special_fields_181
v18._wizard_steps = wizard_steps_181

# Patch payload semantics for partner/sale extensions while preserving V18 engine.
_orig_payload_from_vars=v18.DynamicFormMixin._payload_from_vars

def _payload_181(self,title,subtype):
    p=_orig_payload_from_vars(self,title,subtype)
    if title=='ورودی' and subtype=='شرکا/قرض':
        if str(p.get('partner_name') or '')=='سایر':
            p['partner_name']=str(p.get('partner_other_name') or '').strip()
        kind=str(p.get('partner_kind') or 'تزریق پول')
        p['description']=f"ورودی {p.get('partner_name') or '-'} — {kind}"
        if kind!='قرض':
            p['loan_days']=0;p['partner_return_date']=''
    if title=='ورودی' and subtype=='فروش':
        # payer is the buyer unless AI supplied an explicit matching payer.
        if not str(p.get('payer_name') or '').strip():p['payer_name']=str(p.get('buyer_name') or '').strip()
    return p
v18.DynamicFormMixin._payload_from_vars=_payload_181

# Custom field renderer additions: sale record chooser + project-unit sync + "other".
_orig_field=v18.DynamicFormMixin._field

def _field_181(self,parent,fd,row,col,**kwargs):
    if fd.kind not in {'sale','saleunit'}:
        return _orig_field(self,parent,fd,row,col,**kwargs)
    width=kwargs.get('width',24);box=tk.Frame(parent,bg=DARK['panel']);box.grid(row=row,column=col,sticky='nsew',padx=5,pady=4);box.grid_columnconfigure(0,weight=1)
    lab=tk.Label(box,text=fd.label,bg=DARK['panel'],fg=DARK['text'],font=(self.font_family,self.font_size,'bold'));lab.grid(row=0,column=0,sticky='e');v18._attach_help(lab,fd.label)
    v=tk.StringVar();vals=[]
    if fd.kind=='sale':
        try:
            with DB.read() as con:
                rs=con.execute("SELECT s.sale_id,s.buyer_name,u.display_unit_id,u.unit_number,u.area FROM sales s LEFT JOIN units u ON u.unit_id=s.unit_id WHERE s.status!='CANCELLED' ORDER BY s.created_at DESC").fetchall()
            vals=[f"{r['sale_id']} | {r['buyer_name'] or '-'} | {r['display_unit_id'] or r['unit_number'] or 'سایر'} | {r['area'] or 0} M2" for r in rs]
        except Exception:pass
        w=ttk.Combobox(box,textvariable=v,state='readonly',values=vals,width=width);w.bind('<<ComboboxSelected>>',lambda e:self._sale_selected_181(v.get()),add='+')
    else:
        try:
            units=UnitService(DB).list_units();vals=[f"{r['unit_id']} | {r.get('display_unit_id') or r.get('unit_number') or '-'} | طبقه {r.get('floor') or '-'} | {r.get('area') or 0} M2" for r in units]
        except Exception:vals=[]
        vals.append('سایر')
        w=ttk.Combobox(box,textvariable=v,state='readonly',values=vals,width=width);w.bind('<<ComboboxSelected>>',lambda e:self._sale_unit_selected_181(v.get()),add='+')
    w.grid(row=1,column=0,sticky='ew',pady=(3,0));self.vars[fd.key]=v;self.widgets[fd.key]=w
    try:v.trace_add('write',lambda *_args,k=fd.key:self._mark_manual(k))
    except Exception:pass
    tk.Label(box,text=f"AI: {v18._ai_value(self.ai_original,fd.key)}",bg=DARK['panel'],fg=DARK['muted'],font=(self.font_family,max(7,self.font_size-2))).grid(row=2,column=0,sticky='e',pady=2)
    return w

v18.DynamicFormMixin._field=_field_181


def _sale_selected_181(self,value):
    sid=str(value or '').split('|',1)[0].strip()
    if not sid:return
    try:
        with DB.read() as con:
            r=con.execute("SELECT s.sale_id,s.buyer_name,s.unit_id,u.display_unit_id,u.unit_number,u.area,u.floor FROM sales s LEFT JOIN units u ON u.unit_id=s.unit_id WHERE s.sale_id=?",(sid,)).fetchone()
        if not r:return
        self._loading=True
        vals={'sale_id':sid,'buyer_name':r['buyer_name'] or '','payer_name':r['buyer_name'] or '','sold_area':r['area'] or 0}
        if r['unit_id']:vals['sale_unit']=f"{r['unit_id']} | {r['display_unit_id'] or r['unit_number'] or '-'} | طبقه {r['floor'] or '-'} | {r['area'] or 0} M2"
        for k,x in vals.items():
            if k in self.vars:self.vars[k].set(v18._group_money(x) if k=='sold_area' else str(x))
        self._loading=False;self._sync_sale_area_181()
    except Exception:self._loading=False


def _sale_unit_selected_181(self,value):
    self._loading=True
    try:
        if str(value).strip()=='سایر':
            if 'sold_area' in self.vars:self.vars['sold_area'].set('')
        else:
            uid=str(value).split('|',1)[0].strip()
            with DB.read() as con:r=con.execute("SELECT area FROM units WHERE unit_id=?",(uid,)).fetchone()
            if r and 'sold_area' in self.vars:self.vars['sold_area'].set(str(r['area'] or 0))
    finally:self._loading=False
    self._sync_sale_area_181()


def _sync_sale_area_181(self):
    w=self.widgets.get('sold_area');other=str(self.vars.get('sale_unit').get() if self.vars.get('sale_unit') else '')=='سایر'
    try:
        host=w.master if hasattr(w,'master') else None
        if host: host.grid() if other else host.grid_remove()
        w.configure(state='normal' if other else 'disabled')
    except Exception:pass

v18.DynamicFormMixin._sale_selected_181=_sale_selected_181
v18.DynamicFormMixin._sale_unit_selected_181=_sale_unit_selected_181
v18.DynamicFormMixin._sync_sale_area_181=_sync_sale_area_181


# ---------------------------------------------------------------------------
# Wizard fix: dependent dropdown + true multi-step flow + RTL
# ---------------------------------------------------------------------------
class TransactionWizard181(v18.TransactionWizard18):
    def _build_shell(self):
        top=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);top.pack(fill='x',padx=10,pady=10)
        tk.Label(top,text='ثبت مرحله‌ای',bg=DARK['surface'],fg=DARK['text'],font=(self.font_family,self.font_size+2,'bold')).pack(side='right',padx=10,pady=7)
        self.step_lbl=tk.Label(top,text='',bg=DARK['surface'],fg=DARK['muted'],font=(self.font_family,self.font_size-1));self.step_lbl.pack(side='left',padx=10)
        self.host=tk.Frame(self,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);self.host.pack(fill='both',expand=True,padx=10,pady=(0,8))
        nav=tk.Frame(self,bg=DARK['bg']);nav.pack(fill='x',padx=10,pady=(0,10))
        self.next_b=tk.Button(nav,text='بعدی',command=self.next,bg=DARK['blue'],fg='#FFFFFF',relief='flat',padx=18,pady=8,font=(self.font_family,self.font_size,'bold'));self.next_b.pack(side='right',padx=3)
        self.prev_b=tk.Button(nav,text='قبلی',command=self.prev,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=14,pady=8);self.prev_b.pack(side='right',padx=3)
        tk.Button(nav,text='رد کردن مرحله',command=self.next,bg=DARK['surface'],fg=DARK['muted'],relief='flat',padx=12,pady=8).pack(side='left',padx=3)
        tk.Button(nav,text='فرم کامل',command=self._open_full,bg=DARK['surface'],fg=DARK['text'],relief='flat',padx=12,pady=8).pack(side='left',padx=3)

    def _title_changed(self,title):
        self.title_var.set(title);self.subtype_var.set('')
        # Do not rebuild pages yet; only refresh dependent dropdown.
        w=self.widgets.get('v18_subtype')
        if w is not None:
            try:w.configure(values=v18.TITLE_TYPES.get(title,[]));self.vars['v18_subtype'].set('')
            except Exception:pass

    def _sub_changed(self,sub):
        self.subtype_var.set(sub)

    def next(self):
        # On first page, subtype must be selected, then construct the actual pages.
        if self.page_index==0:
            try:self._capture()
            except Exception as exc:return messagebox.showerror('ثبت مرحله‌ای',str(exc),parent=self)
            if not self.title_var.get() or not self.subtype_var.get():
                return messagebox.showwarning('نوع تراکنش','عنوان تراکنش و نوع تراکنش را انتخاب کن.',parent=self)
            self.pages=[[v18.FieldDef('event_date_shamsi','تاریخ','date'),v18.FieldDef('amount','مبلغ','money'),v18.FieldDef('v18_title','عنوان تراکنش','titlecombo'),v18.FieldDef('v18_subtype','نوع تراکنش','subcombo')]] + wizard_steps_181(self.title_var.get(),self.subtype_var.get()) + [[]]
            self.page_index=1 if len(self.pages)>1 else 0
            return self._show_page()
        return super().next()


# ---------------------------------------------------------------------------
# Full editor 18.1: one specialization card only; compact row layout
# ---------------------------------------------------------------------------
class UnifiedPendingEditor181(v18.UnifiedPendingEditor18):
    def _build_special(self,title,sub):
        try:
            if getattr(self,'_special_initialized',False) and self.vars and 'event_date_shamsi' in self.vars:
                self.payload=self._payload_from_vars(self.title_var.get(),self.subtype_var.get())
        except Exception:pass
        for w in self.special_host.winfo_children():w.destroy()
        keep={'event_date_shamsi','amount','v18_title','v18_subtype'};self.vars={k:v for k,v in self.vars.items() if k in keep};self.widgets={k:v for k,v in self.widgets.items() if k in keep}
        card=v18.GlassSection(self.special_host,f'{title} — {sub}');card.pack(fill='both',expand=True);body=card.body
        body.grid_columnconfigure((0,1,2,3),weight=1)
        fields=special_fields_181(title,sub);by={f.key:f for f in fields}
        if title=='هزینه ساخت' and sub=='نقدی':
            rows=[['cost_group','payer_name','receiver_name','description'],['payment_method','invoice_amount','final_amount','discount_amount'],['payment_state','total_debt','remaining_debt'],['main_phase','sub_phase']]
        elif title=='هزینه ساخت' and sub=='چک':
            rows=[['cost_group','payer_name','receiver_name','description'],['issuer_name','issuer_bank','cheque_type','cheque_registration_state'],['due_date_shamsi','cheque_amount','cheque_status','is_guarantee'],['payment_method','invoice_amount','final_amount','discount_amount'],['payment_state','total_debt','remaining_debt'],['main_phase','sub_phase']]
        elif title=='ورودی' and sub=='تسهیلات':
            rows=[['loan_name','loan_bank','loan_total_amount'],['installment_count','interest_rate'],['guarantor_1','guarantor_2','guarantor_3'],['loan_start_date','loan_end_date']]
        elif title=='ورودی' and sub=='فروش':
            rows=[['sale_id','sale_unit','sold_area'],['buyer_name','payer_name']]
        elif title=='ورودی' and sub=='شرکا/قرض':
            rows=[['partner_name','partner_other_name','partner_kind'],['loan_days','partner_return_date']]
        elif title=='خروجی' and sub=='اقساط':
            rows=[['payer_name','loan_id'],['loan_bank','loan_total_amount'],['installment_count','paid_installments_before'],['installments_paid_now','remaining_installments']]
        else:
            ks=[f.key for f in fields];rows=[ks[i:i+4] for i in range(0,len(ks),4)]
        for rr,ks in enumerate(rows):
            for cc,k in enumerate(ks):
                if k in by:self._field(body,by[k],rr,3-cc if len(ks)<=4 else cc,width=20)
        self._load_values(title,sub);self._special_initialized=True
        if 'partner_kind' in self.vars:
            self.vars['partner_kind'].trace_add('write',lambda *_:self._partner_sync_181());self._partner_sync_181()
        if 'partner_name' in self.vars:
            self.vars['partner_name'].trace_add('write',lambda *_:self._partner_sync_181());self._partner_sync_181()
        if 'loan_days' in self.vars:self.vars['loan_days'].trace_add('write',lambda *_:self._partner_date_sync())
        if 'loan_start_date' in self.vars:self.vars['loan_start_date'].trace_add('write',lambda *_:self._loan_date_sync())
        if 'installment_count' in self.vars:self.vars['installment_count'].trace_add('write',lambda *_:self._loan_date_sync())
        if 'installments_paid_now' in self.vars:self.vars['installments_paid_now'].trace_add('write',lambda *_:self._installment_count_sync())
        if 'sale_unit' in self.vars:
            self.vars['sale_unit'].trace_add('write',lambda *_:self._sync_sale_area_181());self._sync_sale_area_181()
        if title=='هزینه ساخت':
            bar=tk.Frame(body,bg=DARK['panel']);bar.grid(row=len(rows),column=0,columnspan=4,sticky='ew',padx=5,pady=7)
            self.phase_hint=tk.StringVar(value='');tk.Label(bar,textvariable=self.phase_hint,bg=DARK['panel'],fg=DARK['muted'],font=(self.font_family,max(8,self.font_size-1))).pack(side='right',padx=7)
            tk.Button(bar,text='پیشنهاد فاز',command=self._phase_suggest,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=10,pady=6).pack(side='left')

    def _title_changed(self):
        title=self.title_var.get();subs=v18.TITLE_TYPES.get(title,[])
        self.subtype_var.set('')
        try:self.widgets['v18_subtype'].configure(values=subs)
        except Exception:pass
        for w in self.special_host.winfo_children():w.destroy()
        hint=tk.Label(self.special_host,text='نوع تراکنش را از فهرست انتخاب کنید.',bg=DARK['panel'],fg=DARK['muted'],font=(self.font_family,self.font_size+1,'bold'))
        hint.pack(fill='x',padx=12,pady=24)

    def _sub_changed(self):
        sub=self.subtype_var.get()
        if sub:self._build_special(self.title_var.get(),sub)

    def _partner_sync_181(self):
        kind=self.vars.get('partner_kind').get() if self.vars.get('partner_kind') else ''
        name=self.vars.get('partner_name').get() if self.vars.get('partner_name') else ''
        for k in ('loan_days','partner_return_date'):
            w=self.widgets.get(k);enable=kind=='قرض'
            try:
                host=w.master if hasattr(w,'master') else None
                if host: host.grid() if enable else host.grid_remove()
                if isinstance(w,DateField):w.entry.configure(state='normal' if enable else 'disabled')
                else:w.configure(state='normal' if enable else 'disabled')
            except Exception:pass
        w=self.widgets.get('partner_other_name')
        try:
            host=w.master if hasattr(w,'master') else None
            if host: host.grid() if name=='سایر' else host.grid_remove()
            w.configure(state='normal' if name=='سایر' else 'disabled')
        except Exception:pass


# ---------------------------------------------------------------------------
# Pending table + Data Entry center
# ---------------------------------------------------------------------------
class PendingTable181(v18.PendingTable18):
    COLUMNS=[
        ('row','ردیف',68),('date','تاریخ',92),('title','عنوان',90),('type','نوع',100),('desc','بابت',165),
        ('amount','مبلغ (تومان)',118),('receiver','گیرنده',110),('issuer','صاحب حساب',110),('payment','نوع پرداخت',105),('due','سررسید',95),('phase','فاز اصلی',130),('subphase','فاز فرعی',130),
    ]
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        try:
            unit=str(load_ui().get('currency_unit') or 'تومان')
            self.tree.heading('amount',text=f'مبلغ ({unit})')
        except Exception:pass
        # Visual right-to-left order while keeping logical column keys intact.
        self.tree.configure(displaycolumns=tuple(reversed([x[0] for x in self.COLUMNS])))
        self._tip=None;self.tree.bind('<Motion>',self._motion_tip,add='+');self.tree.bind('<Leave>',lambda e:self._hide_tip(),add='+')
        self.tree.tag_configure('pending',background='#F5C842',foreground='#4A3800')
        self.tree.tag_configure('approved',background='#7FD99A',foreground='#164B32')
        self.tree.tag_configure('rejected',background='#F08080',foreground='#5C1616')
    def _hide_tip(self):
        if self._tip:
            try:self._tip.destroy()
            except Exception:pass
            self._tip=None
    def _motion_tip(self,e):
        iid=self.tree.identify_row(e.y);col=self.tree.identify_column(e.x)
        self._hide_tip()
        if not iid or not col:return
        try:
            idx=int(col[1:])-1;display=list(self.tree['displaycolumns']);key=display[idx];vals=self.tree.item(iid,'values');logical=[x[0] for x in self.COLUMNS];value=str(vals[logical.index(key)] if key in logical else '')
            bbox=self.tree.bbox(iid,col);width=bbox[2] if bbox else 0
            if len(value)<18 and width>120:return
            tip=tk.Toplevel(self);tip.overrideredirect(True);tip.attributes('-topmost',True);lab=tk.Label(tip,text=value,bg='#F0F3F7',fg='#1E2936',font=('Segoe UI',10),padx=8,pady=5,justify='right',wraplength=520,relief='solid',bd=1);lab.pack();tip.geometry(f'+{e.x_root+12}+{e.y_root+12}');self._tip=tip
        except Exception:pass


class DataEntryCenter181(v18.DataEntryCenter18):
    def _build(self):
        ui=load_ui();self.font_family=ui.get('font_family','Segoe UI');self.font_size=int(ui.get('font_size',11))
        # No redundant "ثبت دیتا" title; controls start at the top edge.
        top=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);top.pack(fill='x',pady=(0,5));tb=top
        self.filter=tk.StringVar(value='Pending');self.status_buttons={}
        for key,label in [('همه','همه'),('Pending','در انتظار بررسی'),('تأییدشده','تأییدشده'),('ردشده','ردشده')]:
            b=tk.Button(tb,text=label,command=lambda k=key:self._set_status(k),bg=DARK['glass'],fg=DARK['text'],activebackground='#47657D',relief='flat',font=(self.font_family,self.font_size,'bold'),padx=11,pady=7);b.pack(side='right',padx=3,pady=5);self.status_buttons[key]=(b,'')
        self.bot=tk.StringVar(value='Telegram: بررسی...');self.gemini=tk.StringVar(value='Gemini: بررسی...')
        self.bot_label=tk.Label(tb,textvariable=self.bot,bg=DARK['surface'],fg=DARK['muted'],font=(self.font_family,max(9,self.font_size-1),'bold'));self.bot_label.pack(side='left',padx=6)
        self.gemini_label=tk.Label(tb,textvariable=self.gemini,bg=DARK['surface'],fg=DARK['muted'],font=(self.font_family,max(9,self.font_size-1),'bold'));self.gemini_label.pack(side='left',padx=6)
        tk.Button(tb,text='بازخوانی پیام‌ها',command=self.re_read_messages,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=10,pady=7).pack(side='left',padx=3)
        tk.Button(tb,text='پردازش مجدد',command=lambda:self.reprocess_rows(self.table.selected_rows()),bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=10,pady=7).pack(side='left',padx=3)
        add_tooltip(tb,'بازخوانی پیام‌ها: پیام‌های ذخیره‌شده یا کم‌اطمینان دوباره پردازش می‌شوند؛ Bot نیز با drop_pending_updates=False پیام‌های صف‌شده را دریافت می‌کند.')

        pane=ttk.Panedwindow(self,orient='horizontal');pane.pack(fill='both',expand=True)
        preview=tk.Frame(pane,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);table_side=tk.Frame(pane,bg=DARK['panel'])
        # Preview stays on the left and is deliberately narrower.
        pane.add(preview,weight=1);pane.add(table_side,weight=5)
        bottom=tk.Frame(table_side,bg=DARK['bg']);bottom.pack(side='bottom',fill='x',pady=5)
        tk.Button(bottom,text='حذف',command=lambda:self.batch_delete18(self.table.selected_rows()),bg='#F06A75',fg='#171A1F',relief='flat',font=(self.font_family,self.font_size,'bold'),padx=18,pady=9).pack(side='right',padx=3)
        tk.Button(bottom,text='کپی',command=lambda:self.copy_rows(self.table.selected_rows()),bg='#F5D45E',fg='#171A1F',relief='flat',font=(self.font_family,self.font_size,'bold'),padx=18,pady=9).pack(side='right',padx=3)
        tk.Button(bottom,text='اضافه کردن',command=self.manual_transaction,bg='#69D69B',fg='#102018',relief='flat',font=(self.font_family,self.font_size,'bold'),padx=18,pady=9).pack(side='right',padx=3)
        self.table=PendingTable181(table_side,self.open_wizard,self.batch_delete18,self.copy_rows,self.manual_transaction,self.batch_approve18,self.batch_reject18,self.reprocess_rows,self.export_rows);self.table.pack(side='top',fill='both',expand=True)

        tk.Label(preview,text='پیش‌نمایش',bg=DARK['panel'],fg=DARK['text'],font=(self.font_family,self.font_size+1,'bold')).pack(anchor='e',padx=8,pady=7)
        self.preview=tk.Canvas(preview,bg='#111820',highlightthickness=0,height=260);self.preview.pack(fill='both',expand=True,padx=7);self.preview.bind('<MouseWheel>',self._wheel);self.preview.bind('<ButtonPress-1>',lambda e:self.preview.scan_mark(e.x,e.y));self.preview.bind('<B1-Motion>',lambda e:self.preview.scan_dragto(e.x,e.y,gain=1))
        self.text=tk.Text(preview,height=8,wrap='word',bg=DARK['surface'],fg=DARK['text'],relief='flat',font=(self.font_family,self.font_size+1),padx=8,pady=8);self.text.pack(fill='x',padx=7,pady=7);self.text.configure(state='disabled')
        self.action=tk.StringVar();tk.Label(preview,textvariable=self.action,bg=DARK['panel'],fg=DARK['muted'],font=(self.font_family,max(9,self.font_size-1)),wraplength=240,justify='right').pack(fill='x',padx=7,pady=(0,7))
        self._update_status_buttons();self.after(1500,self._service_status_181);self.after(4000,self._periodic);self.table.tree.bind('<<TreeviewSelect>>',self._select18,add='+')

    def open_wizard(self,row=None):
        row=row or self.current
        if not row:return messagebox.showwarning('ثبت دیتا','یک سطر را انتخاب کن.',parent=self)
        def full():
            fresh=DB.get_pending_item(str(row['pending_id'])) or row;fresh=dict(fresh);fresh['raw_text']=v18._raw_text(str(row['pending_id']),row);UnifiedPendingEditor181(self,fresh,self.rich,self.refresh)
        TransactionWizard181(self,row,self.rich,self.refresh,full)

    def open_editor(self,row=None):
        row=row or self.current
        if row:UnifiedPendingEditor181(self,row,self.rich,self.refresh)

    def _service_status_181(self):
        try:
            proc=getattr(self,'_bot_process',None);ready_file=BASE_DIR/'runtime'/'telegram_bot_ready.flag';ready=ready_file.exists();bot_ok=bool(proc and proc.poll() is None and ready)
            inbound=None
            try:
                hb=BASE_DIR/'runtime'/'telegram_inbound_last.json'
                if hb.exists():inbound=json.loads(hb.read_text(encoding='utf-8'))
            except Exception:inbound=None
            if bot_ok:
                suffix=f" | آخرین پیام #{fa(inbound.get('message_id'))}" if inbound and inbound.get('message_id') else ''
                self.bot.set('Telegram: آنلاین و آماده'+suffix);self.bot_label.configure(fg='#7CE3A8')
            elif proc and proc.poll() is None:
                self.bot.set('Telegram: در حال اتصال');self.bot_label.configure(fg='#F5D45E')
            else:
                self.bot.set('Telegram: قطع');self.bot_label.configure(fg='#FF7A86')

            providers=getattr(getattr(APPROVAL,'receipts',None),'parser',None);names=[str(x[0]) for x in getattr(providers,'providers',[])];gem=any('GEMINI' in x.upper() for x in names)
            last=None
            try:
                with DB.read() as con:last=con.execute("SELECT provider,status,created_at FROM receipt_analyses ORDER BY created_at DESC LIMIT 1").fetchone()
            except Exception:pass
            failed=bool(last and 'VISION_FAILED' in str(last['provider']))
            if not gem:
                self.gemini.set('Gemini: تنظیم نشده');self.gemini_label.configure(fg='#FF7A86')
            elif failed:
                self.gemini.set('Gemini: خطای آخرین تحلیل');self.gemini_label.configure(fg='#FF7A86')
            elif last:
                self.gemini.set('Gemini: آماده | آخرین تحلیل انجام شد');self.gemini_label.configure(fg='#7CE3A8')
            else:
                # Configured provider, but no network call has been proven yet in this session.
                self.gemini.set('Gemini: تنظیم شده / در انتظار اولین تحلیل');self.gemini_label.configure(fg='#F5D45E')
        except Exception:pass
        self.after(4000,self._service_status_181)


# ---------------------------------------------------------------------------
# Project profile: tab title, auto unit rows, discipline-specific team
# ---------------------------------------------------------------------------
class ProjectSettingsDialog181(v18.ProjectSettingsDialog18):
    def _build(self):
        nb=ttk.Notebook(self);nb.pack(fill='both',expand=True,padx=8,pady=8)
        basic=ttk.Frame(nb,style='Panel.TFrame');floors=ttk.Frame(nb,style='Panel.TFrame');team=ttk.Frame(nb,style='Panel.TFrame');nb.add(basic,text='مشخصات پایه');nb.add(floors,text='طبقات و واحدها');nb.add(team,text='عوامل پروژه')
        p=SERVICE.project.get_project();st=SERVICE.budget.get_settings()
        defs=[('name','نام پروژه',p.get('name') or ''),('address','آدرس',p.get('address') or ''),('postal_code','کدپستی',p.get('postal_code') or ''),('registration_plate','پلاک ثبتی',p.get('registration_plate') or ''),('municipal_file_no','شماره پرونده شهرداری',p.get('municipal_file_no') or ''),('gross_area','متراژ کل/غیرمفید (M2)',st.get('gross_area') or 0),('saleable_area','متراژ مفید/فروشی (M2)',st.get('saleable_area') or 0),('unit_count','تعداد کل واحدها',st.get('unit_count') or 0),('floor_count','تعداد طبقات',len(self.profile.get('floors') or []))]
        card=v18.GlassSection(basic,'مشخصات پروژه');card.pack(fill='x',padx=8,pady=8);b=card.body;b.grid_columnconfigure((0,1,2),weight=1)
        for i,(k,l,val) in enumerate(defs):
            box=tk.Frame(b,bg=DARK['panel']);box.grid(row=i//3,column=2-(i%3),sticky='ew',padx=6,pady=6);tk.Label(box,text=l,bg=DARK['panel'],fg=DARK['text'],font=(self.font_family,self.font_size,'bold')).pack(anchor='e');v=tk.StringVar(value=str(val));self.vars[k]=v;e=ttk.Entry(box,textvariable=v,justify='right');e.pack(fill='x',pady=3);bind_grouped_number(e,v) if k in {'gross_area','saleable_area','unit_count','floor_count'} else None
        tk.Button(basic,text='ذخیره مشخصات پایه',command=self.save_basic_181,bg=DARK['green'],fg='#102018',relief='flat',font=(self.font_family,self.font_size,'bold'),padx=18,pady=8).pack(anchor='e',padx=8,pady=8)

        fc=v18.GlassSection(floors,'طبقات، تعداد واحد و متراژ واحدها');fc.pack(fill='both',expand=True,padx=8,pady=8);fb=fc.body
        self.floor_tree=ttk.Treeview(fb,columns=('floor','count','areas'),show='headings',height=13);self.floor_tree.heading('floor',text='طبقه');self.floor_tree.heading('count',text='تعداد واحد');self.floor_tree.heading('areas',text='متراژ واحدها (M2، با , جدا شود)');self.floor_tree.column('floor',width=140,anchor='center');self.floor_tree.column('count',width=120,anchor='center');self.floor_tree.column('areas',width=500,anchor='e');self.floor_tree.pack(fill='both',expand=True)
        for i,r in enumerate(self.profile.get('floors') or []):self.floor_tree.insert('', 'end',iid=str(i),values=(r.get('floor',''),r.get('unit_count',0),', '.join(str(x) for x in r.get('areas',[]))))
        bar=tk.Frame(fb,bg=DARK['panel']);bar.pack(fill='x',pady=6);tk.Button(bar,text='افزودن طبقه',command=self.add_floor,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=12,pady=6).pack(side='right',padx=3);tk.Button(bar,text='ویرایش',command=self.edit_floor,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=12,pady=6).pack(side='right',padx=3);tk.Button(bar,text='حذف',command=self.del_floor,bg=DARK['red'],fg='#221316',relief='flat',padx=12,pady=6).pack(side='right',padx=3);tk.Button(bar,text='ذخیره و همگام‌سازی واحدها',command=self.save_floors_181,bg=DARK['green'],fg='#102018',relief='flat',padx=14,pady=6).pack(side='left')

        tc=v18.GlassSection(team,'مجری، ناظر و طراح');tc.pack(fill='both',expand=True,padx=8,pady=8);tb=tc.body;tb.grid_columnconfigure((0,1,2),weight=1);self.team_vars={}
        role_specs={'executor':['مجری'],'supervisor':['معماری','سازه','مکانیک/تأسیسات','برق','گاز','آبفا','نقشه‌برداری'],'designer':['معماری','سازه','مکانیک/تأسیسات','برق']}
        labels={'executor':'مجری','supervisor':'ناظر','designer':'طراح'}
        old=self.profile.get('team',{})
        for c,key in enumerate(('executor','supervisor','designer')):
            box=v18.GlassSection(tb,labels[key]);box.grid(row=0,column=2-c,sticky='nsew',padx=5,pady=5);self.team_vars[key]={}
            for disc in role_specs[key]:
                sub=tk.LabelFrame(box.body,text=disc,bg=DARK['panel'],fg=DARK['muted']);sub.pack(fill='x',pady=4);d=(old.get(key,{}).get(disc,{}) if isinstance(old.get(key,{}).get(disc),dict) else (old.get(key,{}) if disc in {'مجری','معماری'} else {}));self.team_vars[key][disc]={}
                for f,l in [('name','نام'),('phone','شماره تماس'),('license_no','شماره پروانه/عضویت'),('company','شرکت/دفتر')]:
                    row=tk.Frame(sub,bg=DARK['panel']);row.pack(fill='x',padx=4,pady=2);tk.Label(row,text=l,bg=DARK['panel'],fg=DARK['text'],width=15,anchor='e').pack(side='right');vv=tk.StringVar(value=str(d.get(f,'') or ''));self.team_vars[key][disc][f]=vv;ttk.Entry(row,textvariable=vv,justify='right').pack(side='right',fill='x',expand=True,padx=4)
        tk.Button(team,text='ذخیره عوامل پروژه',command=self.save_team_181,bg=DARK['green'],fg='#102018',relief='flat',font=(self.font_family,self.font_size,'bold'),padx=18,pady=8).pack(anchor='e',padx=8,pady=8)

    def save_basic_181(self):
        try:
            def f(k):return float(str(self.vars[k].get()).replace(',','').replace('٬','') or 0)
            SERVICE.project.save_project(name=self.vars['name'].get(),address=self.vars['address'].get(),postal_code=self.vars['postal_code'].get(),registration_plate=self.vars['registration_plate'].get(),municipal_file_no=self.vars['municipal_file_no'].get())
            SERVICE.budget.save_settings(gross_area=f('gross_area'),saleable_area=f('saleable_area'),unit_count=int(f('unit_count')))
            target=max(0,int(f('floor_count')));current=list(self.profile.get('floors') or [])
            while len(current)<target:current.append({'floor':str(len(current)+1),'unit_count':0,'areas':[]})
            if target and len(current)>target:current=current[:target]
            self.profile['floors']=current;save_profile(self.profile);self.on_refresh and self.on_refresh();messagebox.showinfo('مشخصات پروژه','مشخصات پایه ذخیره شد و تعداد ردیف طبقات بروزرسانی شد.',parent=self)
        except Exception as exc:messagebox.showerror('مشخصات پروژه',str(exc),parent=self)

    def save_floors_181(self):
        floors=[]
        for iid in self.floor_tree.get_children():
            floor,count,areas=self.floor_tree.item(iid,'values');arr=[]
            for x in str(areas).replace('،',',').split(','):
                try:arr.append(float(x.strip()))
                except Exception:pass
            count=int(count or 0);arr=(arr+[0.0]*count)[:count] if count else []
            floors.append({'floor':str(floor),'unit_count':count,'areas':arr})
        self.profile['floors']=floors;save_profile(self.profile)
        # Conservative sync: create missing units, update matching available units;
        # never cancel/split units already tied to a sale.
        units=UnitService(DB);existing=units.list_units(include_cancelled=False);by={(str(r.get('floor') or ''),str(r.get('unit_number') or '')):r for r in existing};seq=1
        for fr in floors:
            for i in range(fr['unit_count']):
                num=str(seq);area=fr['areas'][i] if i<len(fr['areas']) else 0;key=(fr['floor'],num)
                if key in by:
                    try:units.update_unit(by[key]['unit_id'],area=area)
                    except Exception:pass
                else:
                    try:units.add_unit(floor=fr['floor'],unit_number=num,area=area,project_name=SERVICE.project.get_project().get('name') or '')
                    except Exception:pass
                seq+=1
        messagebox.showinfo('طبقات و واحدها','اطلاعات ذخیره و با فهرست واحدهای فروش همگام شد؛ رکوردهای فروخته‌شده حذف نشده‌اند.',parent=self);self.on_refresh and self.on_refresh()

    def save_team_181(self):
        self.profile['team']={role:{disc:{f:v.get().strip() for f,v in vals.items()} for disc,vals in discs.items()} for role,discs in self.team_vars.items()};save_profile(self.profile);messagebox.showinfo('عوامل پروژه','مشخصات مجری، ناظرها و طراح‌ها ذخیره شد.',parent=self)


# ---------------------------------------------------------------------------
# Settings and reports
# ---------------------------------------------------------------------------
class SettingsTab181(tk.Frame):
    def __init__(self,parent,on_apply):
        super().__init__(parent,bg=DARK['bg']);self.on_apply=on_apply;self.data=load_ui();self.vars={};self._build()
    def _build(self):
        card=v18.GlassSection(self,'تنظیمات ظاهر و کاربری');card.pack(fill='x',padx=12,pady=12);b=card.body;b.grid_columnconfigure((0,1),weight=1)
        defs=[('font_family','نوع فونت',('Segoe UI','Tahoma','Arial')),('font_size','اندازه فونت',tuple(str(x) for x in range(9,19))),('appearance','حالت نمایش',('dark','light')),('currency_unit','واحد پول',('تومان','ریال','دلار'))]
        for i,(k,l,vals) in enumerate(defs):
            box=tk.Frame(b,bg=DARK['panel']);box.grid(row=i//2,column=1-(i%2),sticky='ew',padx=7,pady=7);tk.Label(box,text=l,bg=DARK['panel'],fg=DARK['text'],font=('Segoe UI',10,'bold')).pack(anchor='e');v=tk.StringVar(value=str(self.data.get(k, 'تومان' if k=='currency_unit' else '')));self.vars[k]=v;ttk.Combobox(box,textvariable=v,state='readonly',values=vals).pack(fill='x',pady=4)
        rate=tk.Frame(b,bg=DARK['panel']);rate.grid(row=2,column=0,columnspan=2,sticky='ew',padx=7,pady=7);rate.grid_columnconfigure((0,1),weight=1)
        for c,(k,l) in enumerate([('usd_rate_current','قیمت روز دلار آمریکا (تومان)'),('usd_rate_baseline','قیمت دلار زمان برآورد اولیه (تومان)')]):
            box=tk.Frame(rate,bg=DARK['panel']);box.grid(row=0,column=1-c,sticky='ew',padx=4);tk.Label(box,text=l,bg=DARK['panel'],fg=DARK['text']).pack(anchor='e');v=tk.StringVar(value=group_int(self.data.get(k,0) or 0,blank_zero=True));self.vars[k]=v;e=ttk.Entry(box,textvariable=v,justify='right');e.pack(fill='x',pady=4);bind_grouped_number(e,v)
        tk.Button(b,text='ذخیره تنظیمات',command=self.save,bg=DARK['green'],fg='#102018',relief='flat',padx=16,pady=8,font=('Segoe UI',10,'bold')).grid(row=3,column=0,columnspan=2,sticky='e',padx=7,pady=10)
    def save(self):
        d=load_ui();d.update({k:v.get() for k,v in self.vars.items()});d['font_size']=int(d['font_size']);d['usd_rate_current']=parse_int(d.get('usd_rate_current'));d['usd_rate_baseline']=parse_int(d.get('usd_rate_baseline'))
        if d.get('currency_unit')=='دلار' and d['usd_rate_current']<=0:return messagebox.showwarning('واحد دلار','قیمت روز دلار آمریکا را وارد کن.',parent=self)
        save_ui(d);messagebox.showinfo('تنظیمات','تنظیمات ذخیره شد. برای اعمال کامل فونت و تم، برنامه را یک بار باز و بسته کن.',parent=self);self.on_apply and self.on_apply()


class Stage181Dashboard(v18.Stage18Dashboard):
    def __init__(self):
        super().__init__();self.title('BARKAV — Engineering & Construction — Version 18.1')
        try:self.iconbitmap(default=str(BASE_DIR/'assets'/'BARKAV.ico'))
        except Exception:pass

    def _style(self):
        # One step lighter than 18.0; Fluent/Windows-11 inspired glass palette.
        DARK.update({'bg':'#151B22','surface':'#1D2630','panel':'#222D38','panel2':'#293644','glass':'#304154','line':'#46596B','text':'#DDE5EC','muted':'#AEBBC7','blue':'#73AEE6','green':'#69D69B','orange':'#E7B96B','red':'#F06A75','cyan':'#72C7D7','violet':'#AAA0CF','yellow':'#F5D45E'})
        try:v18.v175.v16.d12.COLORS.update({'bg':DARK['bg'],'panel':DARK['panel'],'soft':DARK['surface'],'rowblue':'#26323E','text':DARK['text'],'muted':DARK['muted'],'line':DARK['line'],'navy':'#D6E5F2','blue':DARK['blue'],'cyan':DARK['cyan'],'green':DARK['green'],'yellow':DARK['yellow'],'orange':DARK['orange'],'red':DARK['red']})
        except Exception:pass
        st=ttk.Style(self)
        try:st.theme_use('clam')
        except Exception:pass
        ff=self.ui.get('font_family') or 'Segoe UI';fs=int(self.ui.get('font_size') or 11);rh=int(self.ui.get('row_height') or 40)
        st.configure('.',font=(ff,fs),background=DARK['bg'],foreground=DARK['text']);st.configure('TFrame',background=DARK['bg']);st.configure('Panel.TFrame',background=DARK['panel']);st.configure('TLabel',background=DARK['bg'],foreground=DARK['text']);st.configure('TButton',padding=(10,7),background=DARK['glass'],foreground=DARK['text'],bordercolor=DARK['line'],relief='flat');st.map('TButton',background=[('active','#42576B'),('pressed','#536D84')]);st.configure('TEntry',fieldbackground='#1B242D',foreground=DARK['text'],insertcolor='#FFFFFF',bordercolor=DARK['line'],padding=6);st.configure('TCombobox',fieldbackground='#1B242D',background='#1B242D',foreground=DARK['text'],arrowcolor=DARK['text'],bordercolor=DARK['line'],padding=5);st.map('TCombobox',fieldbackground=[('readonly','#1B242D')],foreground=[('readonly',DARK['text'])]);st.configure('TScrollbar',background='#3A4B5C',troughcolor='#192129',bordercolor=DARK['line'],arrowcolor=DARK['muted']);st.configure('Treeview',rowheight=rh,background='#222D38',fieldbackground='#222D38',foreground=DARK['text'],bordercolor='#172029',font=(ff,fs));st.configure('Treeview.Heading',background='#344454',foreground=DARK['text'],font=(ff,max(9,fs-1),'bold'),padding=(6,8));st.map('Treeview',background=[('selected','#4B7091')],foreground=[('selected','#FFFFFF')]);st.configure('Hidden.TNotebook',background=DARK['bg'],borderwidth=0);st.layout('Hidden.TNotebook.Tab',[])

    def _load_nav_icon(self,name):
        if not hasattr(self,'_nav_images'):self._nav_images={}
        if name in self._nav_images:return self._nav_images[name]
        p=BASE_DIR/'assets'/f'nav_{name}.png'
        try:
            im=Image.open(p).convert('RGBA').resize((28,28),Image.Resampling.LANCZOS);img=ImageTk.PhotoImage(im);self._nav_images[name]=img;return img
        except Exception:return None

    def _build(self):
        self.configure(bg=DARK['bg']);ff=self.ui.get('font_family') or 'Segoe UI';fs=int(self.ui.get('font_size') or 11)
        # Light top command strip approximates the requested Windows title-bar zone
        # without unsafe borderless-window hacks.
        top=tk.Frame(self,bg='#E8EDF2',height=54,highlightbackground='#CAD3DB',highlightthickness=1);top.pack(fill='x');top.pack_propagate(False)
        self.datetime_top=tk.StringVar(value='');tk.Label(top,textvariable=self.datetime_top,bg='#E8EDF2',fg='#3B4855',font=(ff,fs+1,'bold')).pack(side='left',padx=14)
        tk.Label(top,text=f'BARKAV Engineering & Construction — Version {VERSION}',bg='#E8EDF2',fg='#5A6773',font=('Segoe UI',9)).pack(side='left',padx=8)
        tools=tk.Frame(top,bg='#E8EDF2');tools.pack(side='right',padx=6)
        for text,cmd,tip in [('ذخیره',self.manual_save,'بکاپ دستی'),('بسته توسعه',self.export_development_package,'خروجی امن توسعه'),('Undo',self.undo,'بازگشت'),('Redo',self.redo,'اجرای دوباره'),('بروزرسانی',self.refresh_all,'بروزرسانی'),('تنظیمات',lambda:self._select_tab_text('تنظیمات'),'تنظیمات'),('سیستم',lambda:self._select_tab_text('سیستم'),'وضعیت سیستم')]:
            b=tk.Button(tools,text=text,command=cmd,bg='#F4F7F9',fg='#26323D',activebackground='#D8E2EA',relief='flat',font=(ff,max(9,fs-1)),padx=7,pady=5);b.pack(side='right',padx=2);add_tooltip(b,tip)
        logo=BASE_DIR/'assets'/'barkav_logo.jpg'
        try:
            im=Image.open(logo).convert('RGB');im.thumbnail((145,42));self._logo_img181=ImageTk.PhotoImage(im);tk.Label(top,image=self._logo_img181,bg='#FFFFFF',bd=0).pack(side='right',padx=8,pady=4)
        except Exception:tk.Label(top,text='بارکاو',bg='#E8EDF2',fg='#111820',font=(ff,16,'bold')).pack(side='right',padx=10)
        self.project_name_top=tk.StringVar(value='پروژه')

        self.navbar=tk.Frame(self,bg='#1A232C',height=56,highlightbackground=DARK['line'],highlightthickness=1);self.navbar.pack(fill='x',padx=7,pady=(6,0));self.navbar.pack_propagate(False)
        self.notebook=ttk.Notebook(self,style='Hidden.TNotebook');self.notebook.pack(fill='both',expand=True,padx=7,pady=(5,7))
        self._build_overview();self._build_manager();self._build_financial();self._build_cheques();self._build_sales();self._build_reconciliation();self._build_reports();self._build_market();self._build_system();self._build_settings();self._rebuild_navbar();self.notebook.bind('<<NotebookTabChanged>>',lambda e:(self._sync_nav(),v18._maximize(self)),add='+');self._attach_common_tooltips(self);self._tick_clock()

    def _select_tab_text(self,text):
        for t in self.notebook.tabs():
            if self.notebook.tab(t,'text')==text:self.notebook.select(t);return

    def _rebuild_navbar(self):
        for w in self.navbar.winfo_children():w.destroy()
        self.nav_buttons={};ff=self.ui.get('font_family') or 'Segoe UI';fs=int(self.ui.get('font_size') or 11)
        map_icon={'داشبورد':'dashboard','ثبت دیتا':'data','حساب مدیر پروژه':'manager','تراکنش‌ها':'transactions','فروش و مطالبات':'sales','گزارش‌گیری':'reports','پیمانکار-بازار':'market','سیستم':'system','تنظیمات':'settings','تطبیق بانکی':'transactions'}
        for tid in reversed(self.notebook.tabs()):
            txt=self.notebook.tab(tid,'text');img=self._load_nav_icon(map_icon.get(txt,'dashboard'));b=tk.Button(self.navbar,text=txt,image=img,compound='right' if img else 'none',command=lambda t=tid:self.notebook.select(t),bg='#263542',fg=DARK['muted'],activebackground='#3B5062',activeforeground=DARK['text'],relief='flat',bd=0,font=(ff,fs,'bold'),padx=12,pady=6,cursor='hand2',highlightbackground=DARK['line'],highlightthickness=1);b.pack(side='right',fill='y',padx=3,pady=5);self.nav_buttons[tid]=b
        self._sync_nav()

    def _sync_nav(self):
        try:sel=str(self.notebook.select())
        except Exception:return
        for tid,b in self.nav_buttons.items():
            active=str(tid)==sel;b.configure(bg='#3D566C' if active else '#263542',fg='#FFFFFF' if active else DARK['muted'],relief='raised' if active else 'flat',bd=1 if active else 0)

    def _build_approval_center(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.approval_tab=tab;self.notebook.insert(1,tab,text='ثبت دیتا');self.approval_center=DataEntryCenter181(tab,self.rich,on_posted=self.refresh_all);self.approval_center.pack(fill='both',expand=True)
        if self._bot_process:self.approval_center.set_bot_process(self._bot_process,self._bot_log)
        self.after_idle(self._rebuild_navbar)

    def _build_system(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.notebook.add(tab,text='سیستم');self.system_tab18=v18.SystemTab18(tab,self);self.system_tab18.pack(fill='both',expand=True)

    def _build_settings(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.notebook.add(tab,text='تنظیمات');SettingsTab181(tab,self._reload_ui).pack(fill='both',expand=True)

    def edit_project_settings(self):ProjectSettingsDialog181(self,self.refresh_all)

    def _build_cheques(self):
        # 18.1: cheques are a sub-tab of Transactions, not a top-level navigation tab.
        tab=ttk.Frame(self.fin_nb,style='Panel.TFrame');self.fin_nb.add(tab,text='چک‌ها')
        bar=v18.GlassSection(tab,'مدیریت چک‌ها');bar.pack(fill='x',padx=4,pady=(2,6));h=bar.body
        self.ch_filter=tk.StringVar(value='همه');vals=['همه','ثبت‌نشده','ثبت‌شده','صادرشده','پاس‌شده','برگشتی','عودتی به شرط تسویه','باطل‌شده','ضمانتی'];ttk.Combobox(h,textvariable=self.ch_filter,state='readonly',values=vals,width=22).pack(side='right',padx=4);ttk.Button(h,text='ویرایش مشخصات/وضعیت',command=self.edit_cheque).pack(side='right',padx=4);self.ch_filter.trace_add('write',lambda *_:self.refresh_cheques())
        self.cheque_table=SmartTable(tab,[('issue','تاریخ صدور',95),('due','سررسید',95),('amount','مبلغ (تومان)',120),('issuer','صاحب حساب',115),('type','نوع',80),('reg','ثبت',85),('guarantee','ضمانت',70),('receiver','گیرنده',110),('bank','بانک',95),('serial','شماره/صیادی',115),('desc','بابت',170),('status','وضعیت چک',130),('id','Cheque ID',140)],title='چک‌ها');self.cheque_table.pack(fill='both',expand=True);self.cheque_table.set_edit_handler(self.edit_cheque_row);self.cheque_table.set_delete_handler(self._cancel_cheque_row)

    def _tick_clock(self):
        try:
            dt=datetime.now()
            self.datetime_top.set(f"📅 {fa(gregorian_to_shamsi(dt.date()))}   ⏰ {fa(dt.strftime('%H:%M:%S'))}")
        finally:
            self.after(1000,self._tick_clock)

    def _build_overview(self):
        tab=ttk.Frame(self.notebook,padding=4,style='Panel.TFrame');self.notebook.add(tab,text='داشبورد');wrap=tk.Frame(tab,bg=DARK['bg']);wrap.pack(fill='both',expand=True);canvas=tk.Canvas(wrap,bg=DARK['bg'],highlightthickness=0);vs=ttk.Scrollbar(wrap,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=vs.set);canvas.pack(side='left',fill='both',expand=True);vs.pack(side='right',fill='y');inner=tk.Frame(canvas,bg=DARK['bg']);win=canvas.create_window((0,0),window=inner,anchor='nw');inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')));canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width));canvas.bind('<MouseWheel>',lambda e:(canvas.yview_scroll(int(-e.delta/120),'units'),'break')[1]);self.overview_canvas=canvas
        proj=v18.GlassSection(inner,'نمای کلی پروژه');proj.pack(fill='x',padx=5,pady=(4,7));pb=proj.body;self.project_info=tk.StringVar(value='مشخصات پروژه');self.project_meta_var=tk.StringVar(value='');tk.Label(pb,textvariable=self.project_info,bg=DARK['panel'],fg=DARK['text'],font=('Segoe UI',10,'bold'),justify='right').pack(side='right',padx=7);tk.Button(pb,text='مشخصات پروژه',command=self.edit_project_settings,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=12,pady=6).pack(side='left',padx=4)
        self.cards={};groups=tk.Frame(inner,bg=DARK['bg']);groups.pack(fill='x',padx=5,pady=3)
        for c in range(5):groups.grid_columnconfigure(c,weight=1,uniform='dash5')
        defs=[
            ('تراکنش‌ها',[('total_in','کل ورودی'),('cost','هزینه کل ساخت'),('total_out','کل خروجی'),('cash','تنخواه فعلی'),('free','مانده آزاد')]),
            ('چک‌ها',[('ch_all_total','کل چک‌ها'),('ch_open_total','چک‌های پاس‌نشده'),('ch30_count','سررسید ۳۰ روز'),('ch30_amount','مبلغ سررسید ۳۰ روز')]),
            ('تسهیلات',[('loan_principal','اصل تسهیلات'),('loan_paid','اقساط پرداختی'),('loan_remaining','مانده تسهیلات')]),
            ('فروش و مطالبات',[('sales_contract','کل قرارداد فروش'),('sales_received','وصول خریداران'),('sales_receivable','مطالبات'),('sales_overdue','مطالبات معوق')]),
            ('۳۰ روز آینده',[('liq_obligation','تعهد ۳۰ روز'),('liq_inflow','وصول ۳۰ روز'),('liq_projected','تراز ۳۰ روز'),('sales_30','مطالبات ۳۰ روز'),('loan_30','اقساط ۳۰ روز')]),
        ]
        # first item should appear at the right in RTL layout
        for c,(gt,items) in enumerate(defs):
            sec=v18.GlassSection(groups,gt);sec.grid(row=0,column=4-c,sticky='nsew',padx=4,pady=2);body=sec.body
            try:sec.bind('<Double-1>',lambda e,g=gt:self._open_dashboard_summary(g),add='+')
            except Exception:pass
            for k,t in items:m=v18.InlineMetric18(body,t);m.pack(fill='x',pady=2);self.cards[k]=m;m.bind('<Double-1>',lambda e,g=gt:self._open_dashboard_summary(g),add='+')
        phase=v18.GlassSection(inner,'پیشرفت مراحل پروژه — ۳۲ فاز');phase.pack(fill='x',padx=9,pady=7);ph=phase.body;tk.Label(ph,text='کلیک: جزئیات | دابل‌کلیک: وضعیت و درصد فاز',bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',9)).pack(anchor='e',pady=(0,4));self.phase_strip=tk.Frame(ph,bg=DARK['panel']);self.phase_strip.pack(fill='x');self.phase_buttons={}
        for c in range(32):self.phase_strip.grid_columnconfigure(c,weight=1,uniform='phase32')
        for i in range(1,33):
            b=tk.Button(self.phase_strip,text=fa(f'{i:02d}'),bg='#2A3947',fg='#C8D2DC',activebackground='#4B647A',activeforeground='white',relief='flat',bd=0,font=('Segoe UI',7,'bold'),padx=0,pady=7,command=lambda n=i:self.open_phase_by_no(n));b.grid(row=0,column=i-1,sticky='nsew',padx=1);b.bind('<Double-1>',lambda e,n=i:self.edit_phase_progress(n));self.phase_buttons[i]=b
        self.overall_progress=v18.v175.ProjectProgressBar(ph,on_open=lambda:v18.v175.v16.ProjectFinancialOverview(self,self.rich));self.overall_progress.pack(fill='x',pady=(7,0))
        charts=tk.Frame(inner,bg=DARK['bg']);charts.pack(fill='x',padx=5,pady=6);charts.grid_columnconfigure((0,1,2),weight=1,uniform='chart3');self.cost_donut=v18.v175.DonutChart175(charts,'ترکیب برآورد فازها',250);self.cost_donut.grid(row=0,column=0,sticky='nsew',padx=4);self.liquidity_chart=v18.v175.MiniLineChart(charts,'روند تجمعی برآورد / واقعی / پیش‌بینی',250);self.liquidity_chart.grid(row=0,column=1,sticky='nsew',padx=4);self.phase_chart=v18.v175.MiniBarChart(charts,'مقایسه فازها',250);self.phase_chart.grid(row=0,column=2,sticky='nsew',padx=4)
        # The old blocks below the charts are intentionally removed in 18.1.

    def _open_dashboard_summary(self,group):
        d=tk.Toplevel(self);d.title(f'مشخصات اجمالی — {group}');d.geometry('760x460');d.configure(bg=DARK['bg']);card=v18.GlassSection(d,group);card.pack(fill='both',expand=True,padx=10,pady=10);rows=[]
        mapping={'تراکنش‌ها':['total_in','cost','total_out','cash','free'],'چک‌ها':['ch_all_total','ch_open_total','ch30_count','ch30_amount'],'تسهیلات':['loan_principal','loan_paid','loan_remaining','loan_30'],'فروش و مطالبات':['sales_contract','sales_received','sales_receivable','sales_overdue','sales_30'],'۳۰ روز آینده':['liq_obligation','liq_inflow','liq_projected','sales_30','loan_30']}
        for k in mapping.get(group,[]):
            c=self.cards.get(k);rows.append((getattr(c,'title',k),c.var.get() if c else '-'))
        tree=ttk.Treeview(card.body,columns=('title','value'),show='headings');tree.heading('title',text='عنوان');tree.heading('value',text='مقدار');tree.column('title',anchor='e',width=320);tree.column('value',anchor='center',width=260);tree.pack(fill='both',expand=True)
        for a,b in rows:tree.insert('','end',values=(a,b))

    def refresh_overview(self):
        # Copy the stable service calculations but do not touch removed tables.
        o=SERVICE.overview();flows=SERVICE.financial_flow_totals();p=SERVICE.project.get_project();ch=SERVICE.cheque_30d_summary();chall=SERVICE.cheque_total_summary();sales=SERVICE.sales_30d_summary();loans=SERVICE.loans_30d_summary();liq=SERVICE.liquidity_30d_summary();self.project_name_top.set(fa(p.get('name') or 'پروژه بدون نام'));self.project_info.set(fa(f"{p.get('name') or 'نام پروژه ثبت نشده'} | {p.get('address') or 'آدرس ثبت نشده'}\nکدپستی: {p.get('postal_code') or '-'} | پلاک ثبتی: {p.get('registration_plate') or '-'} | پرونده شهرداری: {p.get('municipal_file_no') or '-'}"))
        vals={'cost':o.construction_cost,'cash':o.cash_balance,'free':o.free_cash_after_cheques,'total_in':flows['total_in'],'total_out':flows['total_out'],'liq_obligation':liq['obligations'],'liq_inflow':liq['expected_inflows'],'liq_projected':liq['projected_balance'],'ch_all_total':chall['amount'],'ch_open_total':o.open_cheque_commitments,'ch30_count':ch['count'],'ch30_amount':ch['amount'],'sales_contract':sales['contract_sales'],'sales_received':sales['cash_received'],'sales_receivable':sales['receivable'],'sales_30':sales['upcoming_amount'],'sales_overdue':sales['overdue_amount'],'loan_principal':loans['principal'],'loan_paid':loans['paid'],'loan_remaining':loans['remaining'],'loan_30':loans['upcoming_amount']}
        for k,v in vals.items():
            if k in self.cards:self.cards[k].var.set(fa(f'{int(v):,} فقره') if k=='ch30_count' else fa(f'{int(v):,}'))
        try:
            phases=self._phase_summary_live();vals2=sorted([(r['phase'],r['actual'] if r['actual']>0 else r['estimate']) for r in phases],key=lambda x:x[1],reverse=True);top=vals2[:5];other=sum(v for _,v in vals2[5:]);colors=['blue','green','orange','violet','cyan'];items=[(n,v,colors[i]) for i,(n,v) in enumerate(top)];items += [('سایر',other,'muted')] if other else [];self.cost_donut.set_items(items);cum=[];a=e=f=0
            for r in phases:e+=r['estimate'];a+=r['actual'];f+=r['forecast'];cum.append((e,a,f))
            self.liquidity_chart.set_series([('برآورد',[x[0] for x in cum],'orange'),('واقعی',[x[1] for x in cum],'green'),('پیش‌بینی',[x[2] for x in cum],'blue')]);self.phase_chart.set_rows([(f"{r['phase_no']:02d}",r['estimate'],r['actual'],r['forecast']) for r in phases]);self.refresh_phase_strip()
        except Exception:pass

    def _build_reports(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.notebook.add(tab,text='گزارش‌گیری');self.report_main=ttk.Notebook(tab);self.report_main.pack(fill='both',expand=True,padx=5,pady=5);phase_root=ttk.Frame(self.report_main,style='Panel.TFrame');idx_root=ttk.Frame(self.report_main,style='Panel.TFrame');self.report_main.add(phase_root,text='گزارش فازها');self.report_main.add(idx_root,text='شاخص‌های مالی')
        # Phase reports: only Price + Phases, with import button opposite.
        top=tk.Frame(phase_root,bg=DARK['surface']);top.pack(fill='x',pady=(0,5));tk.Button(top,text='بارگذاری فایل برآورد',command=self.import_budget,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=12,pady=7).pack(side='left',padx=5,pady=5);self.budget_version=tk.StringVar(value='نسخه برآورد: -');tk.Label(top,textvariable=self.budget_version,bg=DARK['surface'],fg=DARK['muted']).pack(side='left',padx=5)
        self.report_nb=ttk.Notebook(phase_root);self.report_nb.pack(fill='both',expand=True);price=ttk.Frame(self.report_nb,style='Panel.TFrame');phase=ttk.Frame(self.report_nb,style='Panel.TFrame');self.report_nb.add(price,text='قیمت');self.report_nb.add(phase,text='فازها');self.price_table=SmartTable(price,[('cat','گروه',105),('code','کد',80),('desc','شرح',240),('unit','واحد',75),('est','برآورد',115),('actual','واقعی مرجع',115),('fc','پیش‌بینی',115),('src','منبع',150)],title='قیمت مصالح، اجرت/اجرا و خدمات');self.price_table.pack(fill='both',expand=True);self.price_table.set_edit_handler(lambda r:v18.v175.PriceDetailDialog17(self,self.rich,r,self.refresh_reports));self.phase_table=SmartTable(phase,[('no','شماره فاز',75),('phase','فاز',220),('est','برآورد',115),('actual','واقعی',115),('rem','مانده پایه',115),('fc','پیش‌بینی',115),('id','ID',85),('var','انحراف',110)],title='کنترل ۳۲ فاز');self.phase_table.pack(fill='both',expand=True);self.phase_table.set_edit_handler(lambda r:self.open_phase_by_no(r['phase_no']))
        # Financial indices input area
        self.report_vars={k:tk.StringVar() for k in ['gross_area','saleable_area','unit_count','inflation','months','presale','end_price','misc','target','external_injection']}
        params=v18.GlassSection(idx_root,'پارامترهای برآورد');params.pack(fill='x',padx=5,pady=5);pg=params.body;pg.grid_columnconfigure((0,1,2,3,4),weight=1)
        fields=[('gross_area','زیربنای غیرمفید (M2)'),('saleable_area','زیربنای مفید (M2)'),('unit_count','تعداد واحدها'),('inflation','تورم ماهانه %'),('months','ماه تا اتمام'),('presale','قیمت پیش‌فروش / M2'),('end_price','قیمت فروش پایان / M2'),('misc','متفرقه خارج برآورد'),('target','سود هدف %'),('external_injection','توان مالی تزریق پول خارج از پروژه')]
        for i,(k,l) in enumerate(fields):
            box=tk.Frame(pg,bg=DARK['panel']);box.grid(row=i//5,column=4-(i%5),sticky='ew',padx=4,pady=4);tk.Label(box,text=l,bg=DARK['panel'],fg=DARK['text']).pack(anchor='e');e=ttk.Entry(box,textvariable=self.report_vars[k],justify='right');e.pack(fill='x',pady=3);bind_grouped_number(e,self.report_vars[k]) if k in {'presale','end_price','misc','unit_count','external_injection'} else None
        act=tk.Frame(idx_root,bg=DARK['bg']);act.pack(fill='x',padx=5,pady=4);tk.Button(act,text='محاسبه',command=self.calculate_financial_indices,bg=DARK['green'],fg='#102018',relief='flat',padx=18,pady=8,font=('Segoe UI',10,'bold')).pack(side='right',padx=3);tk.Button(act,text='ذخیره پارامترها',command=self.save_report_settings_181,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=12,pady=8).pack(side='right',padx=3);self.report_export_mode=tk.StringVar(value='PDF');ttk.Combobox(act,textvariable=self.report_export_mode,state='readonly',values=['Print','PDF','Excel'],width=10).pack(side='left',padx=3);tk.Button(act,text='خروجی',command=self.export_report_choose,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=12,pady=7).pack(side='left',padx=3)
        legend=tk.Frame(idx_root,bg=DARK['surface']);legend.pack(fill='x',padx=5,pady=4)
        for text,col in [('برآورد اولیه','#7FAED3'),('انجام‌شده + برآورد به‌روز تا پایان','#73D2A2'),('برآورد به‌روز صفر تا ۱۰۰','#E7B96B')]:tk.Label(legend,text='● '+text,bg=DARK['surface'],fg=col,font=('Segoe UI',9,'bold')).pack(side='right',padx=10,pady=5)
        self.index_table=ttk.Treeview(idx_root,columns=('metric','s1','s2','s3'),show='headings',height=12);self.index_table.heading('metric',text='شاخص');self.index_table.heading('s1',text='برآورد اولیه');self.index_table.heading('s2',text='انجام‌شده + بروز تا پایان');self.index_table.heading('s3',text='بروز صفر تا ۱۰۰');self.index_table.column('metric',width=280,anchor='e');self.index_table.column('s1',width=190,anchor='center');self.index_table.column('s2',width=190,anchor='center');self.index_table.column('s3',width=190,anchor='center');self.index_table.pack(fill='both',expand=True,padx=5,pady=(0,5));self.report_cards={}

    def save_report_settings_181(self):
        try:
            def f(k):return float(str(self.report_vars[k].get()).replace(',','').replace('٬','').strip() or 0)
            SERVICE.budget.save_settings(gross_area=f('gross_area'),saleable_area=f('saleable_area'),unit_count=parse_int(self.report_vars['unit_count'].get()),monthly_inflation=f('inflation'),remaining_months=int(f('months')),presale_price_per_m2=parse_int(self.report_vars['presale'].get()),end_sale_price_override=(parse_int(self.report_vars['end_price'].get()) if self.report_vars['end_price'].get().strip() else None),unbudgeted_misc=parse_int(self.report_vars['misc'].get()),target_profit_percent=f('target'))
            ui=load_ui();ui['external_injection']=parse_int(self.report_vars['external_injection'].get());save_ui(ui);messagebox.showinfo('گزارش‌گیری','پارامترها ذخیره شدند.',parent=self)
        except Exception as exc:messagebox.showerror('گزارش‌گیری',str(exc),parent=self)

    def calculate_financial_indices(self):
        try:
            self.save_report_settings_181();fc=SERVICE.budget.forecast();ph=self._phase_summary_live();s1=int(fc.initial_budget);s2=int(fc.forecast_total_cost);s3=sum(int(r.get('forecast') or 0) for r in ph)
            if s3<=0:s3=int(fc.current_budget or s2)
            st=SERVICE.budget.get_settings();gross=float(st.get('gross_area') or 0);sale=float(st.get('saleable_area') or 0);ui=load_ui();extra=int(ui.get('external_injection') or 0);cash=SERVICE.overview().cash_balance;receivable=SERVICE.sales_30d_summary()['receivable'];remaining_area=float(fc.remaining_saleable_area_m2 or 0);presale=int(st.get('presale_price_per_m2') or 0);target=float(st.get('target_profit_percent') or 0)
            scenarios=[s1,s2,s3];rows=[]
            def vals(fn):return [fn(x) for x in scenarios]
            rows.append(('برآورد نهایی پروژه',*scenarios));rows.append(('اختلاف با برآورد اولیه',*[x-s1 for x in scenarios]))
            need=vals(lambda x:max(0,int(x-(cash+receivable+extra))));rows.append(('نقدینگی لازم تا انتهای پروژه',*need));rows.append(('متراژ لازم برای پیش‌فروش',*[(n/presale if presale else 0) for n in need]))
            projected_revenue=int(fc.projected_revenue or 0);rows.append(('سود پروژه',*[projected_revenue-x for x in scenarios]));rows.append(('قیمت پیش‌فروش برای سود هدف',*[round(max(0,x*(1+target/100)-int(SERVICE.sales_30d_summary()['contract_sales']))/remaining_area) if remaining_area>0 else 0 for x in scenarios]))
            rows.append(('هزینه کل پروژه / زیربنای غیرمفید',*[round(x/gross) if gross else 0 for x in scenarios]));rows.append(('هزینه کل پروژه / زیربنای مفید',*[round(x/sale) if sale else 0 for x in scenarios]))
            # construction-only uses the current land share as an approximation for scenario 1/3; scenario 2 has exact service result.
            land=max(0,int(fc.forecast_land_cost or 0));build=[max(0,x-land) for x in scenarios];rows.append(('هزینه ساخت پروژه / زیربنای غیرمفید',*[round(x/gross) if gross else 0 for x in build]));rows.append(('هزینه ساخت پروژه / زیربنای مفید',*[round(x/sale) if sale else 0 for x in build]))
            for i in self.index_table.get_children():self.index_table.delete(i)
            for metric,a,b,c in rows:
                area_metric='متراژ' in metric
                fmt=lambda x:fa(f'{x:,.2f}') if area_metric else fa(f'{int(x):,}')
                self.index_table.insert('','end',values=(metric,fmt(a),fmt(b),fmt(c)))
        except Exception as exc:messagebox.showerror('محاسبه شاخص‌ها',str(exc),parent=self)

    def refresh_reports(self):
        st=SERVICE.budget.get_settings();ui=load_ui();mapping={'gross_area':'gross_area','saleable_area':'saleable_area','unit_count':'unit_count','inflation':'monthly_inflation','months':'remaining_months','presale':'presale_price_per_m2','end_price':'end_sale_price_override','misc':'unbudgeted_misc','target':'target_profit_percent'}
        for vk,sk in mapping.items():
            val=st.get(sk);self.report_vars[vk].set('' if val is None else (group_int(val,blank_zero=(vk=='end_price')) if vk in {'presale','end_price','misc','unit_count'} else str(val or '')))
        self.report_vars['external_injection'].set(group_int(ui.get('external_injection') or 0,blank_zero=True));v=SERVICE.budget.latest_version();self.budget_version.set(f"نسخه برآورد: {v.get('version_no')} — {v.get('title')}" if v else 'نسخه برآورد: -')
        prices=self.rich.list_prices(visible_only=True);catfa={'MATERIAL':'مصالح','LABOR':'اجرت/اجرا','SERVICE':'خدمات','INSTALLATION_GROUP':'تأسیسات (تجمیعی)'};self.price_table.set_rows(prices,lambda r:[catfa.get(r['category'],r['category']),r.get('code') or '-',r['description'],r.get('unit') or '-',fa(f"{int(r['estimate_rate']):,}"),fa(f"{int(r['actual_rate']):,}"),fa(f"{int(r['forecast_rate']):,}"),r.get('source') or '-']);phases=self._phase_summary_live();self.phase_table.set_rows(phases,lambda r:[fa(f"{r['phase_no']:02d}"),r['phase'],fa(f"{int(r['estimate']):,}"),fa(f"{int(r['actual']):,}"),fa(f"{int(r['remaining_base']):,}"),fa(f"{int(r['forecast']):,}"),r['phase_id'],fa(f"{int(r['variance']):,}")]);self.refresh_phase_strip() if hasattr(self,'phase_buttons') else None

    def export_development_package(self):
        dest=filedialog.asksaveasfilename(parent=self,defaultextension='.zip',initialfile='BARKAV_Development_Package_18.1.zip',filetypes=[('ZIP','*.zip')])
        if not dest:return
        try:
            res=v18.v175.v174.build_development_package(BASE_DIR,Path(dest),VERSION);messagebox.showinfo('بسته توسعه',f"بسته توسعه {VERSION} ساخته شد:\n{res['path']}\n\nدیتابیس زنده و secrets وارد بسته نشده‌اند.",parent=self)
        except Exception as exc:messagebox.showerror('بسته توسعه',str(exc),parent=self)


Stage18Dashboard=Stage181Dashboard
Stage175Dashboard=Stage181Dashboard
Stage17Dashboard=Stage181Dashboard

if __name__=='__main__':Stage181Dashboard().mainloop()
