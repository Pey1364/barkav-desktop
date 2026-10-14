from __future__ import annotations

import asyncio
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any, Callable
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import dashboard_stage17_5 as v175
from dashboard_stage17_5 import (
    DARK, DB, SERVICE, CONFIG, BASE_DIR, APPROVAL, Image, ImageOps, ImageTk,
    DateField, SearchableCombo, SmartTable, CompactTable, PhaseChoiceDialog,
    fmt_money, fa, group_int, parse_int, bind_grouped_number, add_tooltip,
    normalize_shamsi, shamsi_to_gregorian, gregorian_to_shamsi,
    CHEQUE_TYPE_FA, CHEQUE_TYPE_BY_FA, REG_FA, REG_BY_FA,
)
from loan_service import LoanService, _add_months
from ui_stage10 import bind_grouped_decimal, parse_decimal
from revenue_service import RevenueService
from v18_store import load_profile, save_profile, load_ui, save_ui
from phase04_v18 import apply_phase04_rules_v18
from cost_allocation_stage18_7 import attach_payment_to_contract, guess_for_payload
from financial_posting import build_posting_plan

VERSION = '18.0'

# ---------------------------------------------------------------------------
# V18 information architecture
# ---------------------------------------------------------------------------
TITLE_TYPES = {
    'هزینه ساخت': ['نقدی', 'چک'],
    'ورودی': ['تسهیلات', 'فروش', 'شرکا/قرض', 'سایر'],
    'خروجی': ['اقساط', 'سایر'],
    'یادداشت': ['اطلاع‌رسانی', 'داکیومنت'],
}
# Which side of the estimate a construction cost belongs to. The project plan
# is kept in these three sections, so a payment tagged with one of them tells
# the plan which of its three actual totals to add to.
COST_GROUPS = ['مصالح', 'پیمانکار', 'خدمات']
PAYMENT_METHODS = ['واریز بانکی', 'نقدی/کارتخوان', 'چک']
PAYMENT_STATE = ['تسویه', 'علی‌الحساب', 'پرداخت‌نشده']
CHEQUE_KIND = ['فیزیکی', 'دیجیتال']
CHEQUE_REG = ['ثبت‌نشده', 'ثبت‌شده']
CHEQUE_STATUS = ['صادرشده', 'پاس‌شده', 'برگشتی', 'عودتی به شرط تسویه', 'باطل‌شده']
PARTNER_KIND = ['قرض', 'قطعی']

HELP = {
    'عنوان تراکنش': 'گروه اصلی رکورد را مشخص می‌کند: هزینه ساخت، ورودی، خروجی یا یادداشت.',
    'نوع تراکنش': 'زیرنوع وابسته به عنوان تراکنش است و فرم اختصاصی همان نوع را باز می‌کند.',
    'مبلغ': 'مبلغ واقعی همین رویداد مالی؛ نه مبلغ کل فاکتور یا کل بدهی.',
    'علی‌الحساب': 'بخشی از بدهی پرداخت شده و هنوز مانده بدهی وجود دارد.',
    'تسویه': 'بدهی مربوط به این رویداد به‌طور کامل تسویه شده است.',
    'پرداخت‌نشده': 'هنوز پرداختی برای این بدهی انجام نشده است.',
    'کل بدهی': 'کل تعهد مالی مربوط به این هزینه یا فاکتور.',
    'مانده بدهی': 'بخشی از کل بدهی که هنوز تسویه نشده است.',
    'بابت ضمانت': 'چک تضمینی است؛ در هزینه ساخت، خروجی و تعهد پرداخت عادی محاسبه نمی‌شود.',
    'وضعیت ثبت چک': 'مشخص می‌کند چک در سامانه/فرآیند ثبت مربوطه ثبت شده یا هنوز ثبت نشده است.',
    'عودتی به شرط تسویه': 'چک پس گرفته شده و مبلغ آن با روش دیگری تسویه شده؛ اثر مالی آن مثل پاس‌شدن چک است.',
    'فاز اصلی': 'فاز اصلی ساخت که هزینه به آن مربوط است. AI پیشنهاد می‌دهد ولی انتخاب نهایی قابل اصلاح است.',
    'فاز فرعی': 'فعالیت یا ریزفاز داخل فاز اصلی.',
    'وضعیت پرداخت': 'تسویه یعنی بدهی کامل پرداخت شده؛ علی‌الحساب یعنی بخشی پرداخت شده؛ پرداخت‌نشده یعنی هنوز پرداختی ثبت نشده است.',
    'روش پرداخت': 'روش انجام همین پرداخت: واریز بانکی، نقدی/کارتخوان یا چک.',
    'نوع چک': 'فیزیکی یا دیجیتال بودن چک را مشخص می‌کند.',
    'وضعیت چک': 'چرخه جاری چک: صادرشده، پاس‌شده، برگشتی، عودتی به شرط تسویه یا باطل‌شده.',
    'نام شریک': 'شریک مرتبط با ورودی؛ فهرست اولیه پیمان، پیام و سامان است و قابل ویرایش/افزودن است.',
    'نوع': 'برای ورودی شریک مشخص می‌کند مبلغ قرض است یا آورده قطعی.',
}

# Keep the backend lifecycle codes compatible with the existing ledger.
CHEQUE_STATUS_TO_CODE = {
    'صادرشده': 'ISSUED',
    'پاس‌شده': 'CASHED',
    'برگشتی': 'RETURNED',
    'عودتی به شرط تسویه': 'RETURNED_SETTLED',
    'باطل‌شده': 'CANCELLED',
}
CODE_TO_CHEQUE_STATUS = {v: k for k, v in CHEQUE_STATUS_TO_CODE.items()}

METHOD_TO_CODE = {'واریز بانکی': 'BANK_TRANSFER', 'نقدی/کارتخوان': 'CASH_POS', 'چک': 'CHEQUE'}
CODE_TO_METHOD = {
    'BANK_TRANSFER': 'واریز بانکی', 'TRANSFER': 'واریز بانکی', 'CARD_TO_CARD': 'واریز بانکی',
    'CASH': 'نقدی/کارتخوان', 'POS': 'نقدی/کارتخوان', 'CASH_POS': 'نقدی/کارتخوان',
    'CHEQUE': 'چک',
}
STATE_TO_CODE = {'تسویه': 'PAID', 'علی‌الحساب': 'PARTIAL', 'پرداخت‌نشده': 'UNPAID'}
CODE_TO_STATE = {'PAID': 'تسویه', 'PARTIAL': 'علی‌الحساب', 'UNPAID': 'پرداخت‌نشده', 'UNKNOWN': 'پرداخت‌نشده'}


def _title_type_from_payload(p: dict[str, Any]) -> tuple[str, str]:
    title = str(p.get('v18_title') or p.get('transaction_title') or '').strip()
    subtype = str(p.get('v18_subtype') or p.get('transaction_subtype') or '').strip()
    if title in TITLE_TYPES and subtype in TITLE_TYPES[title]:
        return title, subtype
    typ = str(p.get('detected_type') or 'UNKNOWN').upper()
    method = str(p.get('payment_method') or '').upper()
    cat = str(p.get('category') or p.get('outflow_category') or '').upper()
    if typ == 'EXPENSE': return 'هزینه ساخت', 'چک' if (method == 'CHEQUE' or p.get('is_cheque')) else 'نقدی'
    if typ == 'CHEQUE': return 'هزینه ساخت', 'چک'
    if typ == 'INCOME':
        if p.get('loan_name') or p.get('loan_id') or cat == 'LOAN_RECEIPT': return 'ورودی', 'تسهیلات'
        if p.get('sale_id') or p.get('unit_id'): return 'ورودی', 'فروش'
        if p.get('partner_name'): return 'ورودی', 'شرکا/قرض'
        return 'ورودی', 'سایر'
    if typ == 'OUTFLOW':
        if p.get('loan_id') or cat == 'LOAN_INSTALLMENT': return 'خروجی', 'اقساط'
        return 'خروجی', 'سایر'
    if typ in {'DOCUMENT', 'INFO'}:
        # The category the bot read («گزارش روزانه», «تقویم کارگاهی», ...),
        # not one fixed subtype per detected_type.
        from ai_parser import NOTE_TYPE_LABELS
        note = NOTE_TYPE_LABELS.get(str(p.get('note_type') or '').strip())
        if note and note in TITLE_TYPES.get('یادداشت', ()):
            return 'یادداشت', note
        return 'یادداشت', 'داکیومنت' if typ == 'DOCUMENT' else 'اطلاع‌رسانی'
    # AI may not know the type yet; keep a conservative default.
    return 'هزینه ساخت', 'نقدی'


def _backend_type(title: str, subtype: str) -> str:
    if title == 'هزینه ساخت': return 'CHEQUE' if subtype == 'چک' else 'EXPENSE'
    if title == 'ورودی': return 'INCOME'
    if title == 'خروجی': return 'OUTFLOW'
    if title == 'یادداشت': return 'DOCUMENT' if subtype == 'داکیومنت' else 'INFO'
    return 'UNKNOWN'


def _display_payment(p: dict[str, Any], title: str, subtype: str) -> str:
    if title == 'هزینه ساخت' and subtype == 'چک': return 'چک'
    return CODE_TO_METHOD.get(str(p.get('payment_method') or '').upper(), '-')


def _raw_text(pid: str, row: dict[str, Any]) -> str:
    return str(row.get('raw_text') or v175._raw_text_for_pending(pid) or '').strip()


def _group_money(value: Any) -> str:
    try: return group_int(int(value or 0), blank_zero=False)
    except Exception: return '0'


def _ai_value(original: dict[str, Any], key: str) -> str:
    v = original.get(key)
    if v in (None, ''): return '—'
    if key in {'amount','invoice_amount','final_amount','discount_amount','total_debt','remaining_debt','loan_total_amount','principal_amount'}:
        return _group_money(v)
    return str(v)


def _maximize(win: tk.Misc) -> None:
    try:
        win.state('zoomed')
    except Exception:
        try:
            sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
            win.geometry(f'{sw}x{max(700, sh-70)}+0+0')
        except Exception:
            pass


def _attach_help(widget: tk.Widget, label: str) -> None:
    text = HELP.get(label)
    if text:
        add_tooltip(widget, text)


class GlassSection(tk.Frame):
    def __init__(self, parent, title='', *, padx=12, pady=10):
        super().__init__(parent, bg=DARK['panel'], highlightbackground=DARK['line'], highlightthickness=1)
        if title:
            h = tk.Frame(self, bg=DARK['surface'])
            h.pack(fill='x')
            lab = tk.Label(h, text=title, bg=DARK['surface'], fg=DARK['text'], font=('Segoe UI', 10, 'bold'))
            lab.pack(side='right', padx=10, pady=7)
            _attach_help(lab, title)
        self.body = tk.Frame(self, bg=DARK['panel'])
        self.body.pack(fill='both', expand=True, padx=padx, pady=pady)


@dataclass
class FieldDef:
    key: str
    label: str
    kind: str = 'entry'
    values: tuple[str, ...] = ()
    readonly: bool = False


class PremiumMetricCard18(tk.Frame):
    """Neutral Windows-11 style KPI card with automatic value font fitting."""
    def __init__(self,parent,title:str,accent:str='',icon:str='◈',info:str='',on_open=None,compact:bool=False):
        super().__init__(parent,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1)
        self.title=title;self.info=info;self.on_open=on_open;self.compact=compact
        body=tk.Frame(self,bg=DARK['panel']);body.pack(fill='both',expand=True,padx=11,pady=8 if compact else 11)
        head=tk.Frame(body,bg=DARK['panel']);head.pack(fill='x')
        tk.Label(head,text=title,bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',8 if compact else 9,'bold')).pack(side='right')
        if info:
            lab=tk.Label(head,text='ⓘ',bg=DARK['panel'],fg='#9EB9D1',font=('Segoe UI',8,'bold'),cursor='hand2');lab.pack(side='left');add_tooltip(lab,info)
        self.var=tk.StringVar(value='۰ تومان')
        self.value=tk.Label(body,textvariable=self.var,bg=DARK['panel'],fg=DARK['text'],font=('Segoe UI',11 if compact else 14,'bold'),anchor='e')
        self.value.pack(fill='x',pady=(7,1));self.value_label=self.value
        self.var.trace_add('write',lambda *_:self._fit_value())
        if on_open:
            for w in (self,body,self.value):w.bind('<Double-1>',lambda e:on_open())
    def _fit_value(self):
        txt=str(self.var.get() or '');n=len(txt)
        base=11 if self.compact else 14
        size=base if n<=15 else (max(8,base-2) if n<=20 else max(7,base-4))
        try:self.value.configure(font=('Segoe UI',size,'bold'))
        except Exception:pass


class InlineMetric18(tk.Frame):
    """A compact row metric inside one large glass group; avoids card/rainbow clutter."""
    def __init__(self,parent,title,info=''):
        super().__init__(parent,bg=DARK['panel2'])
        self.var=tk.StringVar(value='۰')
        head=tk.Frame(self,bg=DARK['panel2']);head.pack(fill='x',padx=9,pady=(7,2))
        lab=tk.Label(head,text=title,bg=DARK['panel2'],fg=DARK['muted'],font=('Segoe UI',8,'bold'));lab.pack(side='right');add_tooltip(lab,info or title)
        self.value_label=tk.Label(self,textvariable=self.var,bg=DARK['panel2'],fg=DARK['text'],font=('Segoe UI',11,'bold'),anchor='e')
        self.value_label.pack(fill='x',padx=9,pady=(1,7))
        self.var.trace_add('write',lambda *_:self._fit())
    def _fit(self):
        n=len(str(self.var.get() or ''));size=11 if n<=17 else (9 if n<=22 else 8)
        try:self.value_label.configure(font=('Segoe UI',size,'bold'))
        except Exception:pass


# ---------------------------------------------------------------------------
# Dynamic transaction schema shared by Wizard + full editor
# ---------------------------------------------------------------------------
def _special_fields(title: str, subtype: str) -> list[FieldDef]:
    if title == 'هزینه ساخت' and subtype == 'نقدی':
        return [
            FieldDef('payer_name','واریزکننده'), FieldDef('receiver_name','گیرنده'),
            # پیمانکار گاهی مجبور است شماره کارت/حساب شخص دیگری را برای دریافت
            # وجه بدهد؛ صاحب حساب همان‌جا کنار واریزکننده/گیرنده پرسیده می‌شود.
            FieldDef('issuer_name','صاحب حساب'),
            FieldDef('description','بابت'), FieldDef('cost_group','دسته‌بندی','combo',tuple(COST_GROUPS)),
            FieldDef('contract_id','انتخاب قرارداد','contract'),
            FieldDef('payment_method','روش پرداخت','combo',('واریز بانکی','نقدی/کارتخوان')),
            FieldDef('invoice_amount','مبلغ فاکتور','money'), FieldDef('final_amount','مبلغ نهایی','money'), FieldDef('discount_amount','تخفیف','money'),
            FieldDef('payment_state','وضعیت پرداخت','combo',tuple(PAYMENT_STATE)), FieldDef('total_debt','کل بدهی','money'), FieldDef('remaining_debt','مانده بدهی','money'),
            FieldDef('main_phase','فاز اصلی','phase'), FieldDef('sub_phase','فاز فرعی','subphase'),
        ]
    if title == 'هزینه ساخت' and subtype == 'چک':
        return [
            FieldDef('payer_name','واریزکننده'), FieldDef('receiver_name','گیرنده'), FieldDef('description','بابت'),
            FieldDef('cost_group','دسته‌بندی','combo',tuple(COST_GROUPS)),
            FieldDef('contract_id','انتخاب قرارداد','contract'),
            FieldDef('issuer_name','صاحب حساب'), FieldDef('issuer_bank','نام بانک'),
            FieldDef('cheque_type','نوع چک','combo',tuple(CHEQUE_KIND)), FieldDef('cheque_registration_state','وضعیت ثبت چک','combo',tuple(CHEQUE_REG)),
            FieldDef('due_date_shamsi','تاریخ سررسید','date'), FieldDef('cheque_amount','مبلغ چک','money'),
            FieldDef('cheque_status','وضعیت چک','combo',tuple(CHEQUE_STATUS)), FieldDef('is_guarantee','بابت ضمانت','check'),
            FieldDef('invoice_amount','مبلغ فاکتور','money'), FieldDef('final_amount','مبلغ نهایی','money'), FieldDef('discount_amount','تخفیف','money'),
            FieldDef('payment_state','وضعیت پرداخت','combo',tuple(PAYMENT_STATE)), FieldDef('total_debt','کل بدهی','money'), FieldDef('remaining_debt','مانده بدهی','money'),
            FieldDef('main_phase','فاز اصلی','phase'), FieldDef('sub_phase','فاز فرعی','subphase'),
        ]
    if title == 'ورودی' and subtype == 'تسهیلات':
        return [
            FieldDef('loan_name','نام وام'), FieldDef('loan_bank','نام بانک'), FieldDef('loan_total_amount','مبلغ تسهیلات','money'),
            FieldDef('installment_count','تعداد اقساط','int'), FieldDef('interest_rate','درصد سود','float'),
            FieldDef('guarantor_1','ضامن ۱'), FieldDef('guarantor_2','ضامن ۲'), FieldDef('guarantor_3','ضامن ۳'),
            FieldDef('loan_start_date','تاریخ شروع','date'), FieldDef('loan_end_date','تاریخ پایان','date'),
        ]
    if title == 'ورودی' and subtype == 'فروش':
        return [
            FieldDef('payer_name','واریزکننده'), FieldDef('sale_unit','واحد فروخته‌شده','saleunit'),
            FieldDef('buyer_name','خریدار'), FieldDef('sale_id','شناسه فروش','entry',readonly=True),
        ]
    if title == 'ورودی' and subtype == 'شرکا/قرض':
        return [
            FieldDef('partner_name','نام شریک','partner'), FieldDef('partner_kind','نوع','combo',tuple(PARTNER_KIND)),
            FieldDef('loan_days','مدت قرض (روز)','int'), FieldDef('partner_return_date','تاریخ برگشت قرض','date'),
        ]
    if title == 'ورودی' and subtype == 'سایر':
        return [FieldDef('payer_name','واریزکننده'), FieldDef('description','بابت')]
    if title == 'خروجی' and subtype == 'اقساط':
        return [
            FieldDef('payer_name','واریزکننده'), FieldDef('loan_id','نام وام','loan'),
            FieldDef('loan_bank','نام بانک','entry',readonly=True), FieldDef('loan_total_amount','مبلغ کل تسهیلات','money',readonly=True),
            FieldDef('installment_count','تعداد کل اقساط','int',readonly=True), FieldDef('paid_installments_before','اقساط پرداخت‌شده قبلی','int',readonly=True),
            FieldDef('installments_paid_now','تعداد اقساط پرداختی کنونی','int'), FieldDef('remaining_installments','تعداد اقساط باقی‌مانده','int',readonly=True),
        ]
    if title == 'خروجی' and subtype == 'سایر':
        return [FieldDef('payer_name','واریزکننده'), FieldDef('receiver_name','گیرنده'), FieldDef('description','بابت'), FieldDef('payment_method','روش پرداخت','combo',tuple(PAYMENT_METHODS))]
    if title == 'یادداشت' and subtype == 'اطلاع‌رسانی':
        return [FieldDef('description','متن اطلاع‌رسانی','text')]
    if title == 'یادداشت' and subtype == 'داکیومنت':
        return [FieldDef('description','شرح سند','text'), FieldDef('link_pending_id','شناسه رکورد مرتبط')]
    return []


def _wizard_steps(title: str, subtype: str) -> list[list[FieldDef]]:
    fields = _special_fields(title, subtype)
    # Keep each page to 2-3 fields as requested. Related financial fields stay together.
    out: list[list[FieldDef]] = []
    i = 0
    while i < len(fields):
        # Guarantee + cheque status can be grouped; three-field groups are preferred.
        take = 3 if len(fields) - i >= 3 else len(fields) - i
        out.append(fields[i:i+take]); i += take
    return out


def _contract_display(contract_id) -> str:
    """Render a stored bare contract_id back into the combobox's own
    "id | title — family" text, so a reopened form shows the contract's
    عنوان قرارداد instead of just its id."""
    cid = str(contract_id or '').strip()
    if not cid:
        return ''
    try:
        from contractor_store_stage18_7 import load_contracts as _load_contracts
        match = next((c for c in _load_contracts() if str(c.get('contract_id')) == cid), None)
    except Exception:
        match = None
    if not match:
        return cid
    return f"{cid} | {match.get('title') or '-'} — {match.get('family_name') or '-'}"


# ---------------------------------------------------------------------------
# Generic V18 field renderer
# ---------------------------------------------------------------------------
class DynamicFormMixin:
    def _init_dynamic(self, payload: dict[str, Any]):
        self.payload = dict(payload or {})
        self.ai_original = dict(payload or {})
        self.vars: dict[str, Any] = {}
        self.widgets: dict[str, Any] = {}
        self.manual_fields: set[str] = set(self.payload.get('v18_manual_fields') or [])
        self._loading = False

    def _phase_values(self):
        try: return [f"{int(r['phase_no']):02d} — {r['phase']}" for r in self.rich.list_phase_summary()]
        except Exception: return []

    def _field(self, parent, fd: FieldDef, row: int, col: int, *, ai=True, width=24):
        box = tk.Frame(parent, bg=DARK['panel'])
        box.grid(row=row, column=col, sticky='nsew', padx=5, pady=4)
        box.grid_columnconfigure(0, weight=1)
        lab = tk.Label(box, text=fd.label, bg=DARK['panel'], fg=DARK['text'], font=(self.font_family, self.font_size, 'bold'))
        lab.grid(row=0, column=0, sticky='e')
        _attach_help(lab, fd.label)
        if fd.kind == 'check':
            v = tk.BooleanVar(value=bool(self.payload.get(fd.key)))
            w = tk.Checkbutton(box, text=fd.label, variable=v, bg=DARK['panel'], fg=DARK['text'], selectcolor=DARK['surface'], activebackground=DARK['panel'], activeforeground=DARK['text'])
            w.grid(row=1,column=0,sticky='e',pady=(3,0)); lab.grid_remove()
        else:
            v = tk.StringVar()
            if fd.kind == 'date': w = DateField(box, v, width=width)
            elif fd.kind == 'combo': w = ttk.Combobox(box, textvariable=v, state='readonly', values=list(fd.values), width=width)
            elif fd.kind == 'phase': w = SearchableCombo(box, v, self._phase_values(), on_pick=lambda _:self._refresh_subphase(), width=width)
            elif fd.kind == 'subphase': w = SearchableCombo(box, v, [], width=width)
            elif fd.kind == 'contract':
                vals = []
                try:
                    from contractor_store_stage18_7 import load_contracts as _load_contracts
                    vals = [f"{c.get('contract_id')} | {c.get('title') or '-'} — {c.get('family_name') or '-'}"
                           for c in _load_contracts()]
                except Exception: pass
                w = ttk.Combobox(box, textvariable=v, state='readonly', values=vals, width=width)
            elif fd.kind == 'partner':
                partners = load_profile().get('partners') or ['پیمان','پیام','سامان']
                w = ttk.Combobox(box, textvariable=v, state='normal', values=partners, width=width)
            elif fd.kind == 'loan':
                vals=[]
                try:
                    vals=[f"{r['loan_id']} | {r.get('description') or r.get('lender_name') or '-'} | {r.get('lender_name') or '-'} | {_group_money(r.get('principal_amount'))}" for r in LoanService(DB).list_loans()]
                except Exception: pass
                w = ttk.Combobox(box,textvariable=v,state='readonly',values=vals,width=width)
                w.bind('<<ComboboxSelected>>',lambda e:self._loan_selected(v.get()),add='+')
            elif fd.kind == 'saleunit':
                vals=[]
                try:
                    with DB.read() as con:
                        rs=con.execute("SELECT u.unit_id,u.display_unit_id,u.unit_number,u.floor,u.area,s.sale_id,s.buyer_name FROM units u LEFT JOIN sales s ON s.unit_id=u.unit_id AND s.status!='CANCELLED' ORDER BY u.floor,u.unit_number").fetchall()
                    vals=[f"{r['unit_id']} | {r['display_unit_id'] or r['unit_number']} | طبقه {r['floor'] or '-'} | {r['area'] or 0}م²" for r in rs]
                except Exception: pass
                w=ttk.Combobox(box,textvariable=v,state='readonly',values=vals,width=width)
                w.bind('<<ComboboxSelected>>',lambda e:self._sale_unit_selected(v.get()),add='+')
            elif fd.kind == 'text':
                w = ttk.Entry(box, textvariable=v, justify='right', width=width)
            else:
                w = ttk.Entry(box, textvariable=v, justify='right', width=width)
                if fd.kind in {'money','int'}: bind_grouped_number(w, v)
                elif fd.kind == 'float': bind_grouped_decimal(w, v)
            try:
                if fd.readonly:
                    if isinstance(w, DateField): w.entry.configure(state='disabled')
                    else: w.configure(state='disabled')
            except Exception: pass
            w.grid(row=1,column=0,sticky='ew',pady=(3,0))
        self.vars[fd.key]=v; self.widgets[fd.key]=w
        if not fd.readonly:
            try:
                v.trace_add('write',lambda *_args,k=fd.key:self._mark_manual(k))
            except Exception: pass
        if ai:
            a = tk.Label(box, text=f"AI: {_ai_value(self.ai_original, fd.key)}", bg=DARK['panel'], fg=DARK['muted'], font=(self.font_family,max(7,self.font_size-2)))
            a.grid(row=2,column=0,sticky='e',pady=(2,0))
        return w

    def _mark_manual(self, key):
        if not getattr(self,'_loading',False):
            self.manual_fields.add(key)

    def _refresh_subphase(self):
        if 'main_phase' not in self.vars or 'sub_phase' not in self.widgets: return
        text=str(self.vars['main_phase'].get() or ''); no=None
        try:no=int(text.split('—',1)[0].strip())
        except Exception:
            try:
                c=self.rich.phase_candidates(text,1); no=c[0]['phase_no'] if c else None
                if c and text.strip(): self.vars['main_phase'].set(f"{no:02d} — {c[0]['phase_name']}")
            except Exception: pass
        try:
            rows=self.rich.subphase_candidates(no,''); self.widgets['sub_phase'].set_all([r['description'] for r in rows])
        except Exception: pass

    def _loan_selected(self, value: str):
        lid=str(value or '').split('|',1)[0].strip()
        if not lid:return
        try:
            loan=LoanService(DB).get_loan(lid) or {}
            paid=int(loan.get('paid_installments') or 0)
            if not paid:
                with DB.read() as con:
                    paid=con.execute("SELECT COUNT(*) FROM loan_installments WHERE loan_id=? AND status='PAID'",(lid,)).fetchone()[0]
            self.payload['selected_loan_name']=loan.get('description') or loan.get('lender_name') or lid
            vals={
                'loan_id': value,
                'loan_bank':loan.get('lender_name') or '',
                'loan_total_amount':loan.get('principal_amount') or 0,
                'installment_count':loan.get('installment_count') or 0,
                'paid_installments_before':paid,
                'installments_paid_now':1,
                'remaining_installments':max(int(loan.get('installment_count') or 0)-paid-1,0),
            }
            self._loading=True
            for k,x in vals.items():
                if k in self.vars:self.vars[k].set(_group_money(x) if isinstance(x,(int,float)) else str(x))
            self._loading=False
        except Exception:
            self._loading=False

    def _sale_unit_selected(self,value:str):
        uid=str(value or '').split('|',1)[0].strip()
        if not uid:return
        try:
            with DB.read() as con:
                r=con.execute("SELECT s.sale_id,s.buyer_name FROM sales s WHERE s.unit_id=? AND s.status!='CANCELLED' ORDER BY s.created_at DESC LIMIT 1",(uid,)).fetchone()
            self._loading=True
            if r:
                if 'sale_id' in self.vars:self.vars['sale_id'].set(r['sale_id'] or '')
                if 'buyer_name' in self.vars:self.vars['buyer_name'].set(r['buyer_name'] or '')
            self._loading=False
        except Exception:self._loading=False

    def _load_values(self, title: str, subtype: str):
        p=self.payload
        self._loading=True
        general={
            'event_date_shamsi': str(p.get('event_date_shamsi') or self.row.get('message_date') or '').split()[0],
            'amount': _group_money(p.get('amount') or p.get('paid_amount') or p.get('final_amount') or 0),
            'v18_title':title,'v18_subtype':subtype,
        }
        for k,v in general.items():
            if k in self.vars:self.vars[k].set(v)
        for fd in _special_fields(title,subtype):
            if fd.key not in self.vars:continue
            value=p.get(fd.key)
            if fd.key=='payment_method':value=CODE_TO_METHOD.get(str(value or '').upper(),value or '')
            elif fd.key=='payment_state':value=CODE_TO_STATE.get(str(value or '').upper(),value or 'پرداخت‌نشده')
            elif fd.key=='cheque_type':value=CHEQUE_TYPE_FA.get(str(value or 'PHYSICAL').upper(),value or 'فیزیکی')
            elif fd.key=='cheque_registration_state':value=REG_FA.get(str(value or 'UNREGISTERED').upper(),value or 'ثبت‌نشده')
            elif fd.key=='cheque_status':value=CODE_TO_CHEQUE_STATUS.get(str(value or 'ISSUED').upper(),value or 'صادرشده')
            elif fd.key=='contract_id':value=_contract_display(value)
            elif fd.key=='cheque_amount':value=p.get('cheque_amount') or p.get('amount') or 0
            elif fd.key=='total_debt':value=p.get('total_debt') or p.get('final_amount') or p.get('invoice_amount') or 0
            elif fd.key=='loan_total_amount':value=p.get('loan_total_amount') or p.get('principal_amount') or 0
            elif fd.key=='loan_name':value=p.get('loan_name') or p.get('description') or ''
            elif fd.key=='loan_bank':value=p.get('loan_bank') or p.get('lender_name') or ''
            elif fd.key=='installment_count':value=p.get('installment_count') or 0
            elif fd.key=='installments_paid_now':value=p.get('installments_paid_now') or 1
            elif fd.key=='loan_end_date':
                value=p.get('loan_end_date') or ''
                if not value:
                    try:
                        start=normalize_shamsi(str(p.get('loan_start_date') or p.get('event_date_shamsi') or ''));count=int(p.get('installment_count') or 0)
                        if start and count>0:value=gregorian_to_shamsi(_add_months(date.fromisoformat(shamsi_to_gregorian(start)),count))
                    except Exception:pass
            elif fd.key=='partner_kind':value=p.get('partner_kind') or 'قطعی'
            elif fd.key=='is_guarantee':value=bool(p.get('is_guarantee'))
            if isinstance(self.vars[fd.key],tk.BooleanVar):self.vars[fd.key].set(bool(value))
            elif fd.kind in {'money','int'}:self.vars[fd.key].set(_group_money(value or 0))
            else:self.vars[fd.key].set('' if value is None else str(value))
        self._loading=False
        self._refresh_subphase()

    def _payload_from_vars(self, title: str, subtype: str) -> dict[str, Any]:
        p=dict(self.payload)
        p['v18_title']=title;p['v18_subtype']=subtype;p['detected_type']=_backend_type(title,subtype)
        p['event_date_shamsi']=str(self.vars.get('event_date_shamsi').get() if self.vars.get('event_date_shamsi') else '').strip()
        p['amount']=parse_int(self.vars.get('amount').get() if self.vars.get('amount') else 0)
        p['paid_amount']=p['amount']
        for fd in _special_fields(title,subtype):
            if fd.key not in self.vars:continue
            v=self.vars[fd.key].get()
            if fd.kind in {'money','int'}:v=parse_int(v)
            elif fd.kind=='float':
                v=parse_decimal(str(v).replace('٪','').replace('%','').strip(), 0.0)
            elif fd.kind=='check':v=bool(v)
            else:v=str(v).strip()
            if fd.key=='payment_method':v=METHOD_TO_CODE.get(v,'UNKNOWN')
            elif fd.key=='payment_state':v=STATE_TO_CODE.get(v,'UNKNOWN')
            elif fd.key=='cheque_type':v=CHEQUE_TYPE_BY_FA.get(v,'PHYSICAL')
            elif fd.key=='cheque_registration_state':v=REG_BY_FA.get(v,'UNREGISTERED')
            elif fd.key=='cheque_status':v=CHEQUE_STATUS_TO_CODE.get(v,'ISSUED')
            elif fd.key=='cheque_amount':
                p['amount']=v;p['paid_amount']=v;continue
            elif fd.key=='contract_id':v=v.split('|',1)[0].strip()
            p[fd.key]=v
        # Compatibility aliases for the existing accounting engine.
        p['transaction_title']=title;p['transaction_subtype']=subtype
        if 'total_debt' in p and not p.get('final_amount'):p['final_amount']=p['total_debt']
        if title=='هزینه ساخت':
            p['manager_fee_eligible']=not bool(p.get('is_guarantee'))
            p['is_cheque']=subtype=='چک'
            if subtype=='چک':p['payment_method']='CHEQUE'
            main=str(p.get('main_phase') or '');sub=str(p.get('sub_phase') or '')
            p['construction_stage']=main;p['expense_category']=sub or p.get('expense_category') or ''
            # Which line of the plan this cost belongs to, read from the
            # wording and stored so the plan's واقعی columns can be totalled
            # from it. Re-read on every save rather than kept, because the
            # operator corrects it by choosing a فاز فرعی - a stale answer
            # would then outlive the correction that was meant to replace it.
            p['plan_ref']=guess_for_payload(getattr(self,'rich',None),p)
        if title=='ورودی' and subtype=='تسهیلات':
            p['principal_amount']=p.get('loan_total_amount') or p['amount'];p['net_received_amount']=p['amount'];p['lender_name']=p.get('loan_bank') or ''
            p['description']=p.get('loan_name') or 'ورودی تسهیلات'
        if title=='خروجی' and subtype=='اقساط':
            val=str(p.get('loan_id') or '');p['loan_id']=val.split('|',1)[0].strip();p['description']=f"قسط تسهیلات {p.get('selected_loan_name') or p.get('loan_bank') or p.get('loan_id') or ''}".strip()
            p['category']='LOAN_INSTALLMENT'
        if title=='ورودی' and subtype=='شرکا/قرض':p['description']=f"ورودی شریک {p.get('partner_name') or ''} — {p.get('partner_kind') or ''}".strip()
        p['v18_manual_fields']=sorted(self.manual_fields)
        return p


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------
class TransactionWizard18(tk.Toplevel, DynamicFormMixin):
    def __init__(self,parent,row,rich,on_done,on_full):
        super().__init__(parent);self.row=row;self.rich=rich;self.on_done=on_done;self.on_full=on_full;self.pid=str(row['pending_id']);self._init_dynamic(dict(row.get('payload') or {}));self.ui=load_ui();self.font_family=self.ui.get('font_family','Segoe UI');self.font_size=int(self.ui.get('font_size',10));self.page_index=0;self.pages=[];self.protocol('WM_DELETE_WINDOW',self._open_full)
        self.title('ثبت مرحله‌ای تراکنش');self.geometry('690x480');self.minsize(620,420);self.configure(bg=DARK['bg']);self.transient(parent)
        title,sub=_title_type_from_payload(self.payload);self.title_var=tk.StringVar(value=title);self.subtype_var=tk.StringVar(value=sub);self._build_shell();self._rebuild_pages(load=True)
        try:self.grab_set()
        except Exception:pass

    def _build_shell(self):
        top=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);top.pack(fill='x',padx=10,pady=10)
        tk.Label(top,text='ثبت مرحله‌ای',bg=DARK['surface'],fg=DARK['text'],font=(self.font_family,self.font_size+2,'bold')).pack(side='right',padx=10,pady=7)
        self.step_lbl=tk.Label(top,text='',bg=DARK['surface'],fg=DARK['muted'],font=(self.font_family,self.font_size-1));self.step_lbl.pack(side='left',padx=10)
        self.host=tk.Frame(self,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);self.host.pack(fill='both',expand=True,padx=10,pady=(0,8))
        nav=tk.Frame(self,bg=DARK['bg']);nav.pack(fill='x',padx=10,pady=(0,10))
        self.next_b=tk.Button(nav,text='بعدی ←',command=self.next,bg='#2563A6',fg='white',relief='flat',padx=18,pady=8,font=(self.font_family,self.font_size,'bold'));self.next_b.pack(side='right',padx=3)
        self.prev_b=tk.Button(nav,text='→ قبلی',command=self.prev,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=14,pady=8);self.prev_b.pack(side='right',padx=3)
        tk.Button(nav,text='Skip',command=self.next,bg=DARK['surface'],fg=DARK['muted'],relief='flat',padx=12,pady=8).pack(side='left',padx=3)
        tk.Button(nav,text='فرم کامل',command=self._open_full,bg=DARK['surface'],fg=DARK['text'],relief='flat',padx=12,pady=8).pack(side='left',padx=3)

    def _clear(self):
        for w in self.host.winfo_children():w.destroy()
        self.vars={};self.widgets={}

    def _rebuild_pages(self,load=False):
        title=self.title_var.get();sub=self.subtype_var.get()
        first=[FieldDef('event_date_shamsi','تاریخ','date'),FieldDef('amount','مبلغ','money'),FieldDef('v18_title','عنوان تراکنش','titlecombo'),FieldDef('v18_subtype','نوع تراکنش','subcombo')]
        # Which of the plan's three sections a construction cost belongs to is
        # asked the moment the cost is declared one, not pages later: it is
        # part of saying what the payment was, like the amount and the date.
        if title=='هزینه ساخت':
            first.append(FieldDef('cost_group','دسته‌بندی','combo',tuple(COST_GROUPS)))
            # Only پیمانکار work is ever tied to one of the project's
            # contracts; the field lives here too so a change of عنوان
            # تراکنش mid-wizard still finds it on this window.
            first.append(FieldDef('contract_id','انتخاب قرارداد','contract'))
        self.pages=[first] + _wizard_steps(title,sub) + [[]]
        self.page_index=min(self.page_index,len(self.pages)-1);self._show_page(load=load)

    def _show_page(self,load=False):
        # Preserve values already entered before recreating the page.
        old={k:(v.get() if hasattr(v,'get') else v) for k,v in self.vars.items()}
        if old:
            try:self.payload=self._payload_from_vars(self.title_var.get(),self.subtype_var.get())
            except Exception:pass
        self._clear();page=self.pages[self.page_index];body=tk.Frame(self.host,bg=DARK['panel']);body.pack(fill='both',expand=True,padx=18,pady=18);body.grid_columnconfigure((0,1),weight=1)
        if self.page_index==0:
            fds=page
            for i,fd in enumerate(fds):
                box=tk.Frame(body,bg=DARK['panel']);box.grid(row=i//2,column=i%2,sticky='nsew',padx=7,pady=8);box.grid_columnconfigure(0,weight=1)
                lab=tk.Label(box,text=fd.label,bg=DARK['panel'],fg=DARK['text'],font=(self.font_family,self.font_size,'bold'));lab.grid(row=0,column=0,sticky='e');_attach_help(lab,fd.label)
                if fd.key=='v18_title':
                    v=tk.StringVar(value=self.title_var.get());w=ttk.Combobox(box,textvariable=v,state='readonly',values=list(TITLE_TYPES),width=26);w.bind('<<ComboboxSelected>>',lambda e:self._title_changed(v.get()))
                elif fd.key=='v18_subtype':
                    v=tk.StringVar(value=self.subtype_var.get());w=ttk.Combobox(box,textvariable=v,state='readonly',values=TITLE_TYPES.get(self.title_var.get(),[]),width=26);w.bind('<<ComboboxSelected>>',lambda e:self._sub_changed(v.get()))
                else:
                    self.vars[fd.key]=tk.StringVar();self._field(box,fd,1,0,width=25);v=self.vars[fd.key];w=self.widgets[fd.key]
                    # _field created an extra label; hide outer label duplicate.
                    for child in box.grid_slaves(row=1,column=0): pass
                    continue
                w.grid(row=1,column=0,sticky='ew',pady=(5,0));self.vars[fd.key]=v;self.widgets[fd.key]=w
                tk.Label(box,text=f"AI: {_ai_value(self.ai_original,fd.key)}",bg=DARK['panel'],fg=DARK['muted'],font=(self.font_family,max(7,self.font_size-2))).grid(row=2,column=0,sticky='e',pady=2)
            self._loading=True
            self.vars['event_date_shamsi'].set(str(self.payload.get('event_date_shamsi') or self.row.get('message_date') or '').split()[0])
            self.vars['amount'].set(_group_money(self.payload.get('amount') or self.payload.get('paid_amount') or self.payload.get('final_amount') or 0))
            # دسته‌بندی/انتخاب قرارداد live only on this window (see _rebuild_pages
            # above) - if a re-edit doesn't restore them here, nothing else will.
            if 'cost_group' in self.vars:self.vars['cost_group'].set(str(self.payload.get('cost_group') or ''))
            if 'contract_id' in self.vars:self.vars['contract_id'].set(_contract_display(self.payload.get('contract_id')))
            self._loading=False
        elif page:
            for i,fd in enumerate(page):self._field(body,fd,i//2,i%2,width=28)
            self._load_values(self.title_var.get(),self.subtype_var.get())
        else:
            tk.Label(body,text='مرور نهایی',bg=DARK['panel'],fg=DARK['text'],font=(self.font_family,self.font_size+3,'bold')).pack(anchor='e',pady=(10,12))
            p=self.payload
            lines=[f"تاریخ: {p.get('event_date_shamsi') or '-'}",f"مبلغ: {_group_money(p.get('amount'))}",f"عنوان: {self.title_var.get()}",f"نوع: {self.subtype_var.get()}"]
            for fd in _special_fields(self.title_var.get(),self.subtype_var.get()):
                v=p.get(fd.key)
                if v not in (None,'',False):lines.append(f"{fd.label}: {_group_money(v) if fd.kind in {'money','int'} else v}")
            tk.Label(body,text='\n'.join(lines),bg=DARK['panel2'],fg=DARK['text'],justify='right',anchor='ne',font=(self.font_family,self.font_size),padx=16,pady=14).pack(fill='both',expand=True)
        self.step_lbl.configure(text=f"مرحله {fa(self.page_index+1)} از {fa(len(self.pages))}")
        self.prev_b.configure(state='normal' if self.page_index>0 else 'disabled')
        self.next_b.configure(text='✅ تأیید و ثبت' if self.page_index==len(self.pages)-1 else 'بعدی ←')

    def _title_changed(self,title):
        self.title_var.set(title);subs=TITLE_TYPES.get(title,[]);self.subtype_var.set(subs[0] if subs else '');self.page_index=0;self._rebuild_pages()
    def _sub_changed(self,sub):self.subtype_var.set(sub);self.page_index=0;self._rebuild_pages()
    def _capture(self):
        if self.page_index==0:
            self.title_var.set(self.vars['v18_title'].get());self.subtype_var.set(self.vars['v18_subtype'].get())
            self.payload['event_date_shamsi']=self.vars['event_date_shamsi'].get().strip();self.payload['amount']=parse_int(self.vars['amount'].get());self.payload['paid_amount']=self.payload['amount'];self.payload['v18_title']=self.title_var.get();self.payload['v18_subtype']=self.subtype_var.get()
            # دسته‌بندی and انتخاب قرارداد exist only on this window; leaving
            # it clears self.vars for every key built here, so they have to
            # be saved into the payload now or nothing captures them again.
            if 'cost_group' in self.vars:self.payload['cost_group']=self.vars['cost_group'].get().strip()
            if 'contract_id' in self.vars:self.payload['contract_id']=self.vars['contract_id'].get().split('|',1)[0].strip()
            return
        if self.pages[self.page_index]:self.payload=self._payload_from_vars(self.title_var.get(),self.subtype_var.get())
    def next(self):
        try:self._capture()
        except Exception as exc:return messagebox.showerror('ثبت مرحله‌ای',str(exc),parent=self)
        if self.page_index>=len(self.pages)-1:
            try:
                p=dict(self.payload);p['v18_manual_fields']=sorted(self.manual_fields);msg=submit_v18(self.pid,p,self.rich);messagebox.showinfo('ثبت',msg,parent=self);self.on_done();self.destroy()
            except Exception as exc:messagebox.showerror('تأیید انجام نشد',str(exc),parent=self)
            return
        self.page_index+=1;self._show_page()
    def prev(self):
        try:self._capture()
        except Exception:pass
        if self.page_index>0:self.page_index-=1;self._show_page()
    def _open_full(self):
        try:
            self._capture()
            if DB.get_financial_posting(self.pid):
                DB.begin_posting_revision(pending_id=self.pid,new_payload=dict(self.payload),
                                          source='GUI_187_EDIT',actor_id='GUI')
            else:
                APPROVAL.save_payload(self.pid,self.payload,learn=False)
        except Exception:pass
        try:self.grab_release()
        except Exception:pass
        self.destroy();self.on_full()


# ---------------------------------------------------------------------------
# Full editor
# ---------------------------------------------------------------------------
class UnifiedPendingEditor18(tk.Toplevel, DynamicFormMixin):
    def __init__(self,parent,row,rich,on_done):
        super().__init__(parent);self.row=row;self.rich=rich;self.on_done=on_done;self.pid=str(row['pending_id']);self._init_dynamic(dict(row.get('payload') or {}));self.ui=load_ui();self.font_family=self.ui.get('font_family','Segoe UI');self.font_size=int(self.ui.get('font_size',10));self._image=None;self._tkimg=None;self._zoom=.65
        self.title(f'ویرایش و تأیید رکورد — {self.pid}');self.configure(bg=DARK['bg']);self.minsize(1050,680);self.geometry('1380x820');_maximize(self);self._build();self._load_evidence();self.after(120,self._fit_image)

    def _build(self):
        head=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);head.pack(fill='x',padx=10,pady=8)
        tk.Label(head,text='ویرایش و تأیید رکورد',bg=DARK['surface'],fg=DARK['text'],font=(self.font_family,self.font_size+2,'bold')).pack(side='right',padx=12,pady=8)
        self.msg=tk.StringVar(value='');tk.Label(head,textvariable=self.msg,bg=DARK['surface'],fg=DARK['muted'],font=(self.font_family,max(8,self.font_size-1))).pack(side='left',padx=10)
        pane=ttk.Panedwindow(self,orient='horizontal');pane.pack(fill='both',expand=True,padx=10,pady=(0,8))
        left=tk.Frame(pane,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);right=tk.Frame(pane,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);pane.add(left,weight=4);pane.add(right,weight=6)
        # image + actual Telegram caption underneath
        imgf=tk.Frame(left,bg='#0B1119');imgf.pack(fill='both',expand=True,padx=7,pady=(7,4));imgf.grid_rowconfigure(0,weight=1);imgf.grid_columnconfigure(0,weight=1)
        self.canvas=tk.Canvas(imgf,bg='#0B1119',highlightthickness=0);ys=ttk.Scrollbar(imgf,orient='vertical',command=self.canvas.yview);xs=ttk.Scrollbar(imgf,orient='horizontal',command=self.canvas.xview);self.canvas.configure(yscrollcommand=ys.set,xscrollcommand=xs.set);self.canvas.grid(row=0,column=0,sticky='nsew');ys.grid(row=0,column=1,sticky='ns');xs.grid(row=1,column=0,sticky='ew')
        self.canvas.bind('<MouseWheel>',self._wheel);self.canvas.bind('<ButtonPress-1>',lambda e:self.canvas.scan_mark(e.x,e.y));self.canvas.bind('<B1-Motion>',lambda e:self.canvas.scan_dragto(e.x,e.y,gain=1))
        z=tk.Frame(left,bg=DARK['panel']);z.pack(fill='x',padx=7)
        for t,cmd in [('−',lambda:self._set_zoom(self._zoom/1.2)),('Fit',self._fit_image),('+',lambda:self._set_zoom(self._zoom*1.2))]:tk.Button(z,text=t,command=cmd,bg=DARK['glass'],fg=DARK['text'],relief='flat',width=5).pack(side='left',padx=2,pady=3)
        self.caption=tk.Text(left,height=7,wrap='word',bg=DARK['surface'],fg=DARK['text'],insertbackground='white',relief='flat',font=(self.font_family,self.font_size+1),padx=10,pady=8);self.caption.pack(fill='x',padx=7,pady=(3,7));self.caption.configure(state='disabled')

        self.main=GlassSection(right,'مشخصات تراکنش');self.main.pack(fill='both',expand=True,padx=8,pady=8);b=self.main.body;b.grid_columnconfigure((0,1),weight=1)
        # General section always exactly four fields.
        self.title_var=tk.StringVar();self.subtype_var=tk.StringVar()
        defs=[FieldDef('event_date_shamsi','تاریخ','date'),FieldDef('amount','مبلغ','money')]
        for i,fd in enumerate(defs):self._field(b,fd,0,i,width=26)
        # title/type controls
        for col,(key,label) in enumerate([('v18_title','عنوان تراکنش'),('v18_subtype','نوع تراکنش')]):
            box=tk.Frame(b,bg=DARK['panel']);box.grid(row=1,column=col,sticky='nsew',padx=5,pady=4);box.grid_columnconfigure(0,weight=1)
            lab=tk.Label(box,text=label,bg=DARK['panel'],fg=DARK['text'],font=(self.font_family,self.font_size,'bold'));lab.grid(row=0,column=0,sticky='e');_attach_help(lab,label)
            v=self.title_var if key=='v18_title' else self.subtype_var
            vals=list(TITLE_TYPES) if key=='v18_title' else []
            w=ttk.Combobox(box,textvariable=v,state='readonly',values=vals,width=26);w.grid(row=1,column=0,sticky='ew',pady=(3,0));self.vars[key]=v;self.widgets[key]=w
            tk.Label(box,text=f"AI: {_ai_value(self.ai_original,key)}",bg=DARK['panel'],fg=DARK['muted'],font=(self.font_family,max(7,self.font_size-2))).grid(row=2,column=0,sticky='e',pady=2)
        self.widgets['v18_title'].bind('<<ComboboxSelected>>',lambda e:self._title_changed(),add='+');self.widgets['v18_subtype'].bind('<<ComboboxSelected>>',lambda e:self._sub_changed(),add='+')
        self.special_host=tk.Frame(b,bg=DARK['panel']);self.special_host.grid(row=2,column=0,columnspan=2,sticky='nsew',pady=(8,0));b.grid_rowconfigure(2,weight=1)
        title,sub=_title_type_from_payload(self.payload);self.title_var.set(title);self.subtype_var.set(sub);self.widgets['v18_subtype'].configure(values=TITLE_TYPES[title]);self._build_special(title,sub);self._load_values(title,sub)

        action=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);action.pack(fill='x',padx=10,pady=(0,10))
        tk.Button(action,text='✅ تأیید و ثبت',command=self.approve,bg='#2E6F4E',fg='white',relief='flat',padx=18,pady=9,font=(self.font_family,self.font_size,'bold')).pack(side='right',padx=4,pady=5)
        tk.Button(action,text='💾 ذخیره اصلاحات',command=self.save_only,bg='#315D86',fg='white',relief='flat',padx=15,pady=9).pack(side='right',padx=4,pady=5)
        tk.Button(action,text='❌ رد',command=self.reject,bg='#6A3A42',fg='white',relief='flat',padx=15,pady=9).pack(side='right',padx=4,pady=5)

    def _title_changed(self):
        t=self.title_var.get();subs=TITLE_TYPES.get(t,[]);self.subtype_var.set(subs[0] if subs else '');self.widgets['v18_subtype'].configure(values=subs);self._build_special(t,self.subtype_var.get())
    def _sub_changed(self):self._build_special(self.title_var.get(),self.subtype_var.get())
    def _build_special(self,title,sub):
        # capture current visible values before swapping the only specialization card
        try:
            if getattr(self,'_special_initialized',False) and self.vars and 'event_date_shamsi' in self.vars:
                self.payload=self._payload_from_vars(self.title_var.get(),self.subtype_var.get())
        except Exception:pass
        for w in self.special_host.winfo_children():w.destroy()
        # Preserve only general vars/widgets and rebuild specialization variables.
        keep={'event_date_shamsi','amount','v18_title','v18_subtype'};self.vars={k:v for k,v in self.vars.items() if k in keep};self.widgets={k:v for k,v in self.widgets.items() if k in keep}
        card=GlassSection(self.special_host,f'{title} — {sub}');card.pack(fill='both',expand=True);body=card.body;body.grid_columnconfigure((0,1,2),weight=1)
        fields=_special_fields(title,sub)
        for i,fd in enumerate(fields):self._field(body,fd,i//3,i%3,width=22)
        self._load_values(title,sub);self._special_initialized=True
        # Conditional partner loan fields are visible but disabled when type=قطعی.
        if 'cost_group' in self.vars and 'contract_id' in self.vars:
            self.vars['cost_group'].trace_add('write',lambda *_:self._contract_field_sync());self._contract_field_sync()
        if 'partner_kind' in self.vars:
            self.vars['partner_kind'].trace_add('write',lambda *_:self._partner_sync());self._partner_sync()
        if 'loan_days' in self.vars:self.vars['loan_days'].trace_add('write',lambda *_:self._partner_date_sync())
        if 'loan_start_date' in self.vars:self.vars['loan_start_date'].trace_add('write',lambda *_:self._loan_date_sync())
        if 'installment_count' in self.vars:self.vars['installment_count'].trace_add('write',lambda *_:self._loan_date_sync())
        if 'installments_paid_now' in self.vars:self.vars['installments_paid_now'].trace_add('write',lambda *_:self._installment_count_sync())
        # AI phase suggestion control for construction costs.
        if title=='هزینه ساخت':
            bar=tk.Frame(body,bg=DARK['panel']);bar.grid(row=(len(fields)+2)//3,column=0,columnspan=3,sticky='ew',padx=5,pady=7)
            self.phase_hint=tk.StringVar(value='');tk.Label(bar,textvariable=self.phase_hint,bg=DARK['panel'],fg=DARK['muted'],font=(self.font_family,max(8,self.font_size-1))).pack(side='right',padx=7)
            tk.Button(bar,text='🧠 پیشنهاد فاز',command=self._phase_suggest,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=10,pady=6).pack(side='left')

    def _contract_field_sync(self):
        # انتخاب قرارداد only means anything for پیمانکار work.
        widget=self.widgets.get('contract_id')
        if widget is None:return
        box=widget.master
        shown=self.vars.get('cost_group')
        if shown is not None and shown.get()=='پیمانکار':box.grid()
        else:box.grid_remove()

    def _loan_date_sync(self):
        if not self.vars.get('loan_start_date') or not self.vars.get('installment_count') or not self.vars.get('loan_end_date'):return
        try:
            sh=normalize_shamsi(self.vars['loan_start_date'].get());count=parse_int(self.vars['installment_count'].get())
            if not sh or count<=0:return
            gd=date.fromisoformat(shamsi_to_gregorian(sh));end=gregorian_to_shamsi(_add_months(gd,count));self._loading=True;self.vars['loan_end_date'].set(end);self._loading=False
        except Exception:self._loading=False
    def _installment_count_sync(self):
        if not all(k in self.vars for k in ('installment_count','paid_installments_before','installments_paid_now','remaining_installments')):return
        try:
            total=parse_int(self.vars['installment_count'].get());before=parse_int(self.vars['paid_installments_before'].get());now=max(0,parse_int(self.vars['installments_paid_now'].get()));self._loading=True;self.vars['remaining_installments'].set(_group_money(max(total-before-now,0)));self._loading=False
        except Exception:self._loading=False
    def _partner_sync(self):
        kind=self.vars.get('partner_kind').get() if self.vars.get('partner_kind') else ''
        enabled=kind=='قرض'
        for k in ('loan_days','partner_return_date'):
            w=self.widgets.get(k)
            try:
                if isinstance(w,DateField):w.entry.configure(state='normal' if enabled else 'disabled')
                else:w.configure(state='normal' if enabled else 'disabled')
            except Exception:pass
    def _partner_date_sync(self):
        if not self.vars.get('loan_days') or not self.vars.get('event_date_shamsi') or not self.vars.get('partner_return_date'):return
        try:
            days=parse_int(self.vars['loan_days'].get());sh=normalize_shamsi(self.vars['event_date_shamsi'].get());gd=datetime.fromisoformat(shamsi_to_gregorian(sh)).date()+timedelta(days=days);self._loading=True;self.vars['partner_return_date'].set(gregorian_to_shamsi(gd));self._loading=False
        except Exception:pass
    def _phase_suggest(self):
        desc=str(self.vars.get('description').get() if self.vars.get('description') else _raw_text(self.pid,self.row))
        try:
            s=v175.suggest_phase(desc,self.rich)
            if not s:self.phase_hint.set('پیشنهاد مطمئن پیدا نشد؛ فاز را دستی انتخاب کنید.');return
            main=f"{s.phase_no:02d} — {s.phase_name}";self._loading=True
            if 'main_phase' in self.vars:self.vars['main_phase'].set(main)
            self._refresh_subphase()
            if 'sub_phase' in self.vars and s.sub_phase:self.vars['sub_phase'].set(s.sub_phase)
            self._loading=False;self.phase_hint.set(f"پیشنهاد AI: {main}{' ← '+s.sub_phase if s.sub_phase else ''} | {fa(f'{s.confidence*100:.0f}')}٪")
        except Exception as exc:self.phase_hint.set(f'خطا در پیشنهاد فاز: {exc}')

    def _load_evidence(self):
        raw=_raw_text(self.pid,self.row);self.caption.configure(state='normal');self.caption.delete('1.0','end');self.caption.insert('1.0',raw or 'متن همراه پیام ثبت نشده است.');self.caption.configure(state='disabled')
        path=str(self.row.get('receipt_image_path') or '')
        try:
            if not path:
                b=APPROVAL.evidence_bundle(self.pid,window=1)
                for a in b.get('attachments') or []:
                    p=str(a.get('local_path') or '')
                    if str(a.get('mime_type') or '').startswith('image/') and Path(p).exists():path=p;break
        except Exception:pass
        if path and Image is not None:
            try:self._image=ImageOps.exif_transpose(Image.open(path)).convert('RGB')
            except Exception:self._image=None
        if not self._image:self.canvas.create_text(220,180,text='رسید تصویری ندارد',fill=DARK['muted'],font=(self.font_family,self.font_size))
    def _fit_image(self):
        if not self._image:return
        self.canvas.update_idletasks();cw=max(220,self.canvas.winfo_width()-24);ch=max(220,self.canvas.winfo_height()-24);self._zoom=min(.88,cw/self._image.width,ch/self._image.height);self._render_image()
    def _set_zoom(self,z):self._zoom=max(.08,min(4,float(z)));self._render_image()
    def _wheel(self,e):self._set_zoom(self._zoom*(1.1 if e.delta>0 else 1/1.1));return 'break'
    def _render_image(self):
        if not self._image or ImageTk is None:return
        w=max(1,int(self._image.width*self._zoom));h=max(1,int(self._image.height*self._zoom));im=self._image.resize((w,h)) if (w,h)!=self._image.size else self._image;self._tkimg=ImageTk.PhotoImage(im);self.canvas.delete('all');self.canvas.create_image(8,8,image=self._tkimg,anchor='nw');self.canvas.configure(scrollregion=(0,0,w+16,h+16))
    def payload_from_form(self):return self._payload_from_vars(self.title_var.get(),self.subtype_var.get())
    def save_only(self):
        try:
            self.payload=self.payload_from_form()
            if DB.get_financial_posting(self.pid):
                # Already posted: a bare save can only stage the edit, the
                # same way begin_posting_revision() does for a Telegram one -
                # save_payload() would refuse it outright (item is no longer
                # PENDING_REVIEW), and posting it for real needs تأیید.
                DB.begin_posting_revision(pending_id=self.pid,new_payload=dict(self.payload),
                                          source='GUI_187_EDIT',actor_id='GUI')
                self.msg.set('اصلاحات روی ثبت تأییدشده ذخیره شد؛ برای اعمال نهایی «تأیید و ثبت» را بزنید.')
            else:
                APPROVAL.save_payload(self.pid,self.payload,learn=True)
                self.msg.set('اصلاحات ذخیره شد؛ هنوز اثر مالی ندارد.')
            self.on_done()
        except Exception as exc:messagebox.showerror('ذخیره',str(exc),parent=self)
    def approve(self):
        try:self.payload=self.payload_from_form();msg=submit_v18(self.pid,self.payload,self.rich);messagebox.showinfo('ثبت',msg,parent=self);self.on_done();self.destroy()
        except Exception as exc:messagebox.showerror('تأیید انجام نشد',str(exc),parent=self)
    def reject(self):
        if not messagebox.askyesno('رد','این رکورد رد شود؟ هیچ اثر مالی ایجاد نمی‌شود.',parent=self):return
        try:APPROVAL.reject(self.pid,actor_id='GUI_18');self.on_done();self.destroy()
        except Exception as exc:messagebox.showerror('رد',str(exc),parent=self)


# ---------------------------------------------------------------------------
# Posting special V18 types safely
# ---------------------------------------------------------------------------
def approve_v18(pid: str, p: dict[str, Any], rich) -> str:
    title,sub=_title_type_from_payload(p)
    # Loan receipt creates a loan file and the cash-in transaction together.
    if title=='ورودی' and sub=='تسهیلات':
        if DB.get_financial_posting(pid):return 'این رکورد قبلاً ثبت شده است.'
        amount=int(p.get('amount') or 0);principal=int(p.get('loan_total_amount') or p.get('principal_amount') or amount)
        if amount<=0 or principal<=0:raise ValueError('مبلغ تسهیلات کامل نیست.')
        guarantors=' | '.join([str(p.get('guarantor_1') or '').strip(),str(p.get('guarantor_2') or '').strip(),str(p.get('guarantor_3') or '').strip()]).strip(' |')
        # loan_start_date is the receipt/start date. Create a real schedule from the next month.
        rec=str(p.get('loan_start_date') or p.get('event_date_shamsi') or '')
        count=max(0,int(p.get('installment_count') or 0))
        first_due=''
        if count and normalize_shamsi(rec):
            g=date.fromisoformat(shamsi_to_gregorian(normalize_shamsi(rec)))
            first_due=gregorian_to_shamsi(_add_months(g,1))
            # Keep the calculated end date in the approved payload for UI/audit.
            p['loan_end_date']=p.get('loan_end_date') or gregorian_to_shamsi(_add_months(g,count))
        obj=LoanService(DB).create_loan(lender_name=str(p.get('loan_bank') or p.get('lender_name') or 'بانک'),principal_amount=principal,net_received_amount=amount,received_date_shamsi=rec,interest_rate=float(p.get('interest_rate') or 0),installment_count=count,first_due_date_shamsi=first_due,guarantors=guarantors,description=str(p.get('loan_name') or 'ورودی تسهیلات'),source='GUI_18')
        v175._mark_nonfinancial_approved(pid,'LOAN',obj.get('loan_id') or '')
        DB.relink_pending_attachments(pid,entity_type='LOAN',entity_id=obj.get('loan_id') or '')
        return 'ورودی تسهیلات و پرونده وام ثبت شد.'
    if title=='ورودی' and sub=='فروش':
        if DB.get_financial_posting(pid):return 'این رکورد قبلاً ثبت شده است.'
        sid=str(p.get('sale_id') or '').strip();amount=int(p.get('amount') or 0);sh=normalize_shamsi(str(p.get('event_date_shamsi') or ''))
        if not sid:raise ValueError('واحد/فروش ثبت‌شده را انتخاب کن.')
        if amount<=0 or not sh:raise ValueError('مبلغ یا تاریخ وصول فروش کامل نیست.')
        obj=RevenueService(DB).record_received_payment(sale_id=sid,amount=amount,received_date_shamsi=sh,payer_name=str(p.get('payer_name') or p.get('buyer_name') or ''),description=f"وصول فروش {sid}",source='GUI_18',actor_id='GUI')
        try:RevenueService(DB).match_receipt_fifo(obj['received_payment_id'],source='GUI_18',actor_id='GUI')
        except Exception:pass
        v175._mark_nonfinancial_approved(pid,'SALE_PAYMENT',obj.get('received_payment_id') or '')
        DB.relink_pending_attachments(pid,entity_type='SALE_PAYMENT',entity_id=obj.get('received_payment_id') or '')
        return 'وصول فروش به همان واحد/پرونده فروش لینک و ثبت شد.'
    # Installment output: choose next unpaid installments for selected loan and post the current amount.
    if title=='خروجی' and sub=='اقساط':
        lid=str(p.get('loan_id') or '').split('|',1)[0].strip();count=max(1,int(p.get('installments_paid_now') or 1));amount=int(p.get('amount') or 0)
        if not lid:raise ValueError('نام وام را انتخاب کن.')
        with DB.read() as con:
            rows=[dict(r) for r in con.execute("SELECT * FROM loan_installments WHERE loan_id=? AND status NOT IN ('PAID','CANCELLED') ORDER BY installment_number LIMIT ?",(lid,count)).fetchall()]
        if not rows:raise ValueError('قسط پرداخت‌نشده‌ای برای این وام پیدا نشد.')
        remaining=amount
        svc=LoanService(DB);posted=[]
        for idx,r in enumerate(rows):
            due=max(int(r.get('amount') or 0)-int(r.get('paid_amount') or 0),0)
            part=due if idx<len(rows)-1 else (remaining if remaining>0 else due)
            if remaining>0:part=min(part,remaining)
            if part<=0:continue
            res=svc.pay_installment(r['loan_installment_id'],amount=part,paid_date_shamsi=str(p.get('event_date_shamsi') or ''),description=f"پرداخت قسط وام {lid}",source='GUI_18')
            posted.append(res);remaining=max(0,remaining-part)
        v175._mark_nonfinancial_approved(pid,'LOAN_INSTALLMENT',posted[-1]['installment_id'] if posted else '')
        return f'{fa(len(posted))} قسط به پرونده تسهیلات ثبت شد.'
    # Returned-and-settled cheque has the same financial settlement semantics as cashed.
    if str(p.get('cheque_status') or '').upper()=='RETURNED_SETTLED':
        p=dict(p);p['cheque_status']='CASHED';p['v18_cheque_display_status']='RETURNED_SETTLED'
    msg=v175.approve_v175(pid,p,rich)
    if title=='هزینه ساخت':
        # final_amount/payment_state from the posting actually made, not
        # the raw form payload - build_posting_plan cascades final_amount
        # from amount and promotes PARTIAL to PAID once paid_amount covers
        # it, so a form left with final_amount=0 or an unflipped وضعیت
        # پرداخت still attaches correctly once posting itself settled.
        settled=dict(p)
        try:
            posted=DB.get_financial_posting(pid)
            plan=(posted or {}).get('plan') or {}
            if 'final_amount' in plan:settled['final_amount']=plan['final_amount']
            if 'payment_state' in plan:settled['payment_state']=plan['payment_state']
        except Exception:pass
        try:attach_payment_to_contract(settled,pending_id=pid)
        except Exception:pass
    return msg


def revise_v18(pid: str, new_payload: dict[str, Any], rich) -> str:
    """Apply an edit to an already-posted item without duplicating it.

    A double-click into ثبت دیتا opens the same wizard for an approved item
    as for a pending one; save_payload()/approve_v18() both assume the item
    is still awaiting its FIRST approval and refuse an already-posted one
    outright. finance_db already has the real mechanism for this - Telegram
    edits to a posted item use begin_posting_revision()/
    revise_financial_posting() to update the same expense/transaction/cheque
    row in place, never a second one - so the GUI's own edit follows the
    same two calls instead of trying to re-approve.
    """

    DB.begin_posting_revision(pending_id=pid, new_payload=dict(new_payload),
                              source='GUI_187_EDIT', actor_id='GUI')
    try:
        refreshed=DB.get_pending_item(pid)
        if not refreshed:raise KeyError(pid)
        tg=DB.get_telegram_message(int(refreshed['telegram_chat_id']),int(refreshed['telegram_message_id'])) or {}
        plan=build_posting_plan(payload=refreshed['payload'],raw_text=tg.get('raw_text') or '',
                                telegram_message_date=tg.get('message_date') or '')
        DB.revise_financial_posting(pending_id=pid,plan=plan,source='GUI_187_EDIT',actor_id='GUI')
    except Exception:
        try:
            if DB.get_open_revision(pid):
                DB.reject_posting_revision(pending_id=pid,source='GUI_187_EDIT_ROLLBACK',actor_id='GUI')
        except Exception:pass
        raise
    title,_sub=_title_type_from_payload(new_payload)
    if title=='هزینه ساخت':
        # final_amount/payment_state come from plan, not the raw form
        # payload: build_posting_plan already cascaded final_amount from
        # amount and promoted payment_state to PAID once paid_amount covers
        # it, which is why the posted expense reads PAID even when the form
        # itself still said final_amount=0/PARTIAL. contract_id and the
        # rest stay from new_payload - build_posting_plan is a whitelist
        # that never carries contract_id at all.
        settled=dict(new_payload)
        settled['final_amount']=plan.get('final_amount')
        settled['payment_state']=plan.get('payment_state')
        try:attach_payment_to_contract(settled,pending_id=pid)
        except Exception:pass
    return 'اصلاحات روی ثبت تأییدشده اعمال شد.'


def submit_v18(pid: str, payload: dict[str, Any], rich) -> str:
    """تأیید on ثبت دیتا: approve a pending item, or revise a posted one.

    A still-pending item goes through save_payload()+approve_v18() exactly
    as before. An item that already has a financial_postings row has
    already been approved once - re-running the approval path on it is
    what raised 'این مورد دیگر در انتظار تأیید نیست'، so it goes through
    revise_v18() instead, which edits the existing posting in place.
    """

    if DB.get_financial_posting(pid):
        return revise_v18(pid,payload,rich)
    APPROVAL.save_payload(pid,payload,learn=True)
    return approve_v18(pid,payload,rich)


# ---------------------------------------------------------------------------
# V18 cheque editor: one cheque = one row, exact lifecycle requested by user
# ---------------------------------------------------------------------------
class ChequeEditDialog18(tk.Toplevel):
    def __init__(self,parent,row,on_refresh):
        super().__init__(parent);self.row=dict(row);self.on_refresh=on_refresh;self.ui=load_ui();ff=self.ui.get('font_family','Segoe UI');fs=int(self.ui.get('font_size',10));self.vars={}
        self.title('مشخصات و وضعیت چک');self.geometry('820x720');self.minsize(720,620);self.configure(bg=DARK['bg']);self.transient(parent)
        card=GlassSection(self,'مشخصات چک');card.pack(fill='both',expand=True,padx=12,pady=12);b=card.body;b.grid_columnconfigure((0,1),weight=1)
        mode=str(row.get('settlement_mode') or 'NORMAL').upper();status=str(row.get('status') or 'ISSUED').upper();display='عودتی به شرط تسویه' if status=='CASHED' and mode=='RETURNED_SETTLED' else CODE_TO_CHEQUE_STATUS.get(status,{'PENDING_DUE':'صادرشده'}.get(status,'صادرشده'))
        vals={'issue':row.get('issue_date_shamsi') or '','due':row.get('due_date_shamsi') or '','amount':_group_money(row.get('amount')),'issuer_name':row.get('issuer_name') or '','receiver_name':row.get('receiver_name') or '','issuer_bank':row.get('issuer_bank') or '','cheque_serial':row.get('cheque_serial') or '','description':row.get('description') or '','cheque_type':CHEQUE_TYPE_FA.get(str(row.get('cheque_type') or 'PHYSICAL').upper(),'فیزیکی'),'registration_state':REG_FA.get(str(row.get('registration_state') or 'UNREGISTERED').upper(),'ثبت‌نشده'),'lifecycle':display,'status_date':row.get('cashed_date_shamsi') or row.get('due_date_shamsi') or gregorian_to_shamsi(datetime.now().date())}
        defs=[('issue','تاریخ صدور','date'),('due','تاریخ سررسید','date'),('amount','مبلغ','num'),('issuer_name','صاحب حساب','entry'),('issuer_bank','نام بانک','entry'),('cheque_serial','شماره/شناسه چک','entry'),('cheque_type','نوع چک','type'),('registration_state','وضعیت ثبت چک','reg'),('lifecycle','وضعیت چک','life'),('status_date','تاریخ رویداد وضعیت','date'),('receiver_name','گیرنده','entry'),('description','بابت','entry')]
        for i,(k,l,kind) in enumerate(defs):
            box=tk.Frame(b,bg=DARK['panel']);box.grid(row=i//2,column=i%2,sticky='ew',padx=7,pady=6);box.grid_columnconfigure(0,weight=1)
            lab=tk.Label(box,text=l,bg=DARK['panel'],fg=DARK['text'],font=(ff,fs,'bold'));lab.grid(row=0,column=0,sticky='e');_attach_help(lab,l)
            v=tk.StringVar(value=str(vals[k]));self.vars[k]=v
            if kind=='date':w=DateField(box,v,width=27)
            elif kind=='type':w=ttk.Combobox(box,textvariable=v,state='readonly',values=CHEQUE_KIND,width=28)
            elif kind=='reg':w=ttk.Combobox(box,textvariable=v,state='readonly',values=CHEQUE_REG,width=28)
            elif kind=='life':w=ttk.Combobox(box,textvariable=v,state='readonly',values=CHEQUE_STATUS,width=28)
            else:w=ttk.Entry(box,textvariable=v,justify='right',width=30);bind_grouped_number(w,v) if kind=='num' else None
            w.grid(row=1,column=0,sticky='ew',pady=4)
        self.guarantee=tk.BooleanVar(value=bool(row.get('is_guarantee')))
        cb=tk.Checkbutton(b,text='بابت ضمانت',variable=self.guarantee,bg=DARK['panel'],fg=DARK['text'],selectcolor=DARK['surface'],activebackground=DARK['panel'],activeforeground=DARK['text'],font=(ff,fs,'bold'));cb.grid(row=6,column=0,columnspan=2,sticky='e',padx=7,pady=8);add_tooltip(cb,HELP['بابت ضمانت'])
        actions=tk.Frame(b,bg=DARK['panel']);actions.grid(row=7,column=0,columnspan=2,sticky='ew',pady=10)
        tk.Button(actions,text='ذخیره و اعمال',command=self.save,bg='#315D82',fg='white',relief='flat',font=(ff,fs,'bold'),padx=18,pady=8).pack(side='right',padx=4)
        tk.Button(actions,text='انصراف',command=self.destroy,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=14,pady=8).pack(side='right',padx=4)
    def save(self):
        try:
            ish=normalize_shamsi(self.vars['issue'].get());due=normalize_shamsi(self.vars['due'].get())
            if not ish or not due:raise ValueError('تاریخ صدور و سررسید باید معتبر باشند.')
            cid=self.row['cheque_id'];old=str(self.row.get('status') or 'ISSUED').upper();target=CHEQUE_STATUS_TO_CODE[self.vars['lifecycle'].get()]
            # Descriptive fields stay editable before final settlement/cancellation.
            if old not in {'CASHED','CANCELLED'}:
                DB.update_cheque_details(cid,amount=parse_int(self.vars['amount'].get()),issue_date=shamsi_to_gregorian(ish),issue_date_shamsi=ish,due_date=shamsi_to_gregorian(due),due_date_shamsi=due,issuer_name=self.vars['issuer_name'].get().strip(),cheque_type=CHEQUE_TYPE_BY_FA.get(self.vars['cheque_type'].get(),'PHYSICAL'),receiver_name=self.vars['receiver_name'].get().strip(),issuer_bank=self.vars['issuer_bank'].get().strip(),cheque_serial=self.vars['cheque_serial'].get().strip(),description=self.vars['description'].get().strip(),is_guarantee=self.guarantee.get(),source='GUI_18',actor_id='GUI')
            with DB.tx() as con:
                con.execute("UPDATE cheques SET registration_state=?,is_guarantee=?,updated_at=? WHERE cheque_id=?",(REG_BY_FA.get(self.vars['registration_state'].get(),'UNREGISTERED'),1 if self.guarantee.get() else 0,datetime.now().isoformat(timespec='seconds'),cid))
            sh=normalize_shamsi(self.vars['status_date'].get());gd=shamsi_to_gregorian(sh) if sh else None
            current_mode=str(self.row.get('settlement_mode') or 'NORMAL').upper()
            if target=='RETURNED_SETTLED':
                if self.guarantee.get():raise ValueError('چک ضمانتی از مسیر «عودتی به شرط تسویه» ثبت مالی نمی‌شود.')
                if old!='CASHED' or current_mode!='RETURNED_SETTLED':
                    if not gd:raise ValueError('تاریخ تسویه را وارد کن.')
                    DB.settle_returned_cheque(cid,settled_date=gd,settled_date_shamsi=sh,source='GUI_18',actor_id='GUI')
            else:
                if old=='CASHED' and current_mode=='RETURNED_SETTLED' and target!='CASHED':
                    raise ValueError('برای برگشت از تسویه نهایی، عملیات اصلاح تخصصی لازم است.')
                if target=='CASHED' and old!='CASHED':
                    if not gd:raise ValueError('تاریخ پاس‌شدن را وارد کن.')
                    DB.set_cheque_lifecycle_status(cid,'CASHED',event_date=gd,event_date_shamsi=sh,source='GUI_18',actor_id='GUI')
                    with DB.tx() as con:con.execute("UPDATE cheques SET settlement_mode='NORMAL' WHERE cheque_id=?",(cid,))
                elif target in {'ISSUED','RETURNED','CANCELLED'} and target!=old:
                    DB.set_cheque_lifecycle_status(cid,target,event_date=gd,event_date_shamsi=sh,source='GUI_18',actor_id='GUI')
            self.destroy();self.on_refresh()
        except Exception as exc:messagebox.showerror('چک',str(exc),parent=self)

# ---------------------------------------------------------------------------
# Pending table / center
# ---------------------------------------------------------------------------
class PendingTable18(tk.Frame):
    COLUMNS=[
        ('row','ردیف',74),('date','تاریخ',105),('title','عنوان تراکنش',115),('type','نوع تراکنش',120),('desc','بابت',215),
        ('amount','مبلغ (تومان)',130),('receiver','گیرنده',135),('payment','نوع پرداخت',125),('due','تاریخ سررسید',105),('phase','فاز اصلی',175),('subphase','فاز فرعی',175),
    ]
    def __init__(self,parent,on_open,on_delete,on_copy,on_add,on_approve,on_reject,on_reprocess,on_export):
        super().__init__(parent,bg=DARK['panel']);self.rows=[];self.iid_to_row={};self.on_open=on_open;self.on_delete=on_delete;self.on_copy=on_copy;self.on_add=on_add;self.on_approve=on_approve;self.on_reject=on_reject;self.on_reprocess=on_reprocess;self.on_export=on_export
        self.tree=ttk.Treeview(self,columns=[x[0] for x in self.COLUMNS],show='headings',height=10,selectmode='extended')

        for k,l,w in self.COLUMNS:
            if k=='row': self.tree.heading(k,text=l,command=self.toggle_all)
            else: self.tree.heading(k,text=l)
            self.tree.column(k,width=w,minwidth=60,anchor='center',stretch=(k in {'desc','phase','subphase'}))
        vs=ttk.Scrollbar(self,orient='vertical',command=self.tree.yview);hs=ttk.Scrollbar(self,orient='horizontal',command=self.tree.xview);self.tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set);self.tree.grid(row=0,column=0,sticky='nsew');vs.grid(row=0,column=1,sticky='ns');hs.grid(row=1,column=0,sticky='ew');self.grid_rowconfigure(0,weight=1);self.grid_columnconfigure(0,weight=1)
        self.tree.bind('<Double-1>',lambda e:self._double(e));self.tree.bind('<Button-3>',self._menu);self.tree.bind('<Button-1>',self._click,add='+');self.tree.bind('<Escape>',lambda e:self.clear_selection());self.tree.bind('<Delete>',lambda e:self.on_delete(self.selected_rows()));self.tree.bind('<MouseWheel>',lambda e:(self.tree.yview_scroll(int(-e.delta/120),'units'),'break')[1])
        self.menu=tk.Menu(self,tearoff=False);self.menu.add_command(label='✅ تأیید انتخاب‌ها',command=lambda:self.on_approve(self.selected_rows()));self.menu.add_command(label='❌ رد انتخاب‌ها',command=lambda:self.on_reject(self.selected_rows()));self.menu.add_separator();self.menu.add_command(label='♻ پردازش مجدد AI',command=lambda:self.on_reprocess(self.selected_rows()));self.menu.add_command(label='📤 خروجی گرفتن',command=lambda:self.on_export(self.selected_rows()));self.menu.add_command(label='📋 کپی',command=lambda:self.on_copy(self.selected_rows()));self.menu.add_separator();self.menu.add_command(label='➕ اضافه کردن',command=self.on_add);self.menu.add_command(label='🗑 حذف',command=lambda:self.on_delete(self.selected_rows()))
    def set_rows(self,rows,renderer):
        self.rows=rows;old={str(self.iid_to_row[i].get('pending_id')) for i in self.tree.selection() if i in self.iid_to_row};self.iid_to_row={}
        for i in self.tree.get_children():self.tree.delete(i)
        for idx,r in enumerate(rows,1):
            iid=f'r{idx}';vals=renderer(r,idx);self.tree.insert('', 'end',iid=iid,values=vals);self.iid_to_row[iid]=r
            st=str(r.get('status') or '');tag='approved' if st=='APPROVED' else ('rejected' if st=='REJECTED' else 'pending');self.tree.item(iid,tags=(tag,))
            if str(r.get('pending_id')) in old:self.tree.selection_add(iid)
        # set_rows() runs on every refresh, so this - not PendingTable181's
        # one-time __init__ call - is the tag_configure that actually sticks;
        # keep both in sync with the same light palette.
        self.tree.tag_configure('pending',background='#F5C842',foreground='#4A3800');self.tree.tag_configure('approved',background='#7FD99A',foreground='#164B32');self.tree.tag_configure('rejected',background='#F08080',foreground='#5C1616')
        self._sync_checks()
    def selected_rows(self):return [self.iid_to_row[i] for i in self.tree.selection() if i in self.iid_to_row]
    def clear_selection(self):self.tree.selection_remove(self.tree.selection());self._sync_checks();return 'break'
    def toggle_all(self):
        if len(self.tree.selection())==len(self.tree.get_children()):self.tree.selection_remove(self.tree.selection())
        else:self.tree.selection_set(self.tree.get_children())
        self._sync_checks()
    def _sync_checks(self):
        selected=set(self.tree.selection())
        for idx,iid in enumerate(self.tree.get_children(),1):
            vals=list(self.tree.item(iid,'values'));vals[0]=f"{'☑' if iid in selected else '☐'} {fa(idx)}";self.tree.item(iid,values=vals)
        self.tree.heading('row',text=('☑ ردیف' if selected and len(selected)==len(self.tree.get_children()) else '☐ ردیف'))
    def _click(self,e):
        iid=self.tree.identify_row(e.y);col=self.tree.identify_column(e.x)
        if not iid:return
        if col=='#1':
            if iid in self.tree.selection():self.tree.selection_remove(iid)
            else:self.tree.selection_add(iid)
            self._sync_checks();return 'break'
        self.after_idle(self._sync_checks)
    def _double(self,e):
        iid=self.tree.identify_row(e.y)
        if iid and iid in self.iid_to_row:self.on_open(self.iid_to_row[iid])
    def _menu(self,e):
        iid=self.tree.identify_row(e.y)
        if iid and iid not in self.tree.selection():self.tree.selection_set(iid);self._sync_checks()
        try:self.menu.tk_popup(e.x_root,e.y_root)
        finally:self.menu.grab_release()


class DataEntryCenter18(v175.DataEntryCenter175):
    def __init__(self,parent,rich,on_posted=None):
        self._phase_seen=set();self._shown_pid='';super(v175.DataEntryCenter175,self).__init__(parent,rich,on_posted)
    def _build(self):
        ui=load_ui();self.font_family=ui.get('font_family','Segoe UI');self.font_size=int(ui.get('font_size',10))
        top=GlassSection(self,'ثبت دیتا');top.pack(fill='x',pady=(0,6));tb=top.body
        self.filter=tk.StringVar(value='Pending');self.status_buttons={}
        for key,label in [('همه','همه'),('Pending','در انتظار بررسی'),('تأییدشده','تأییدشده'),('ردشده','ردشده')]:
            b=tk.Button(tb,text=label,command=lambda k=key:self._set_status(k),bg=DARK['glass'],fg=DARK['text'],activebackground='#27425E',relief='flat',font=(self.font_family,self.font_size,'bold'),padx=11,pady=6);b.pack(side='right',padx=3);self.status_buttons[key]=(b,'')
        self.bot=tk.StringVar(value='ربات: در حال بررسی...');tk.Label(tb,textvariable=self.bot,bg=DARK['panel'],fg=DARK['muted'],font=(self.font_family,max(8,self.font_size-1))).pack(side='left',padx=7)
        tk.Button(tb,text='🔄 بازخوانی پیام‌ها',command=self.re_read_messages,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=10,pady=6).pack(side='left',padx=3)
        tk.Button(tb,text='♻ پردازش مجدد',command=lambda:self.reprocess_rows(self.table.selected_rows()),bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=10,pady=6).pack(side='left',padx=3)
        add_tooltip(tb,'بازخوانی پیام‌ها: پیام‌های ذخیره‌شده‌ای که AI هنگام دریافت نتوانسته تحلیل کند دوباره پردازش می‌شوند؛ پیام تکراری ساخته نمی‌شود.')

        pane=ttk.Panedwindow(self,orient='horizontal');pane.pack(fill='both',expand=True);left=tk.Frame(pane,bg=DARK['panel']);right=tk.Frame(pane,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);pane.add(left,weight=8);pane.add(right,weight=2)
        self.table=PendingTable18(left,self.open_wizard,self.batch_delete18,self.copy_rows,self.manual_transaction,self.batch_approve18,self.batch_reject18,self.reprocess_rows,self.export_rows);self.table.pack(fill='both',expand=True)
        bottom=tk.Frame(left,bg=DARK['bg']);bottom.pack(fill='x',pady=5)
        tk.Button(bottom,text='🗑 حذف',command=lambda:self.batch_delete18(self.table.selected_rows()),bg='#713B43',fg='white',relief='flat',font=(self.font_family,self.font_size,'bold'),padx=18,pady=8).pack(side='right',padx=3)
        tk.Button(bottom,text='📋 کپی',command=lambda:self.copy_rows(self.table.selected_rows()),bg='#8A772C',fg='white',relief='flat',font=(self.font_family,self.font_size,'bold'),padx=18,pady=8).pack(side='right',padx=3)
        tk.Button(bottom,text='➕ اضافه کردن',command=self.manual_transaction,bg='#356B4E',fg='white',relief='flat',font=(self.font_family,self.font_size,'bold'),padx=18,pady=8).pack(side='right',padx=3)
        # Selection preview; actual message is given visual priority over OCR.
        tk.Label(right,text='پیش‌نمایش',bg=DARK['panel'],fg=DARK['text'],font=(self.font_family,self.font_size+1,'bold')).pack(anchor='e',padx=8,pady=7)
        self.preview=tk.Canvas(right,bg='#0B1119',highlightthickness=0,height=280);self.preview.pack(fill='both',expand=True,padx=7);self.preview.bind('<MouseWheel>',self._wheel);self.preview.bind('<ButtonPress-1>',lambda e:self.preview.scan_mark(e.x,e.y));self.preview.bind('<B1-Motion>',lambda e:self.preview.scan_dragto(e.x,e.y,gain=1))
        self.text=tk.Text(right,height=9,wrap='word',bg=DARK['surface'],fg=DARK['text'],relief='flat',font=(self.font_family,self.font_size),padx=8,pady=8);self.text.pack(fill='x',padx=7,pady=7);self.text.configure(state='disabled')
        self.action=tk.StringVar();tk.Label(right,textvariable=self.action,bg=DARK['panel'],fg=DARK['muted'],font=(self.font_family,max(8,self.font_size-1)),wraplength=330,justify='right').pack(fill='x',padx=7,pady=(0,7))
        self._update_status_buttons();self.after(4000,self._periodic)
        self.table.tree.bind('<<TreeviewSelect>>',self._select18,add='+')

    def _update_status_buttons(self,counts=None):
        labels={'همه':'همه','Pending':'در انتظار بررسی','تأییدشده':'تأییدشده','ردشده':'ردشده'}
        for k,(b,_) in self.status_buttons.items():
            active=self.filter.get()==k;b.configure(bg='#315D86' if active else DARK['glass'],relief='raised' if active else 'flat',bd=1 if active else 0)
            if counts is not None:b.configure(text=f"{labels[k]} ({fa(counts.get(k,0))})")
    def refresh(self):
        self._auto_phase_suggestions();hidden=self.rich.hidden_review_ids();allrows=[r for r in APPROVAL.list_reviews(limit=3000) if str(r.get('pending_id')) not in hidden];counts={'همه':len(allrows),'Pending':sum(r.get('status') in {'PENDING_REVIEW','NEEDS_REVIEW','EDIT_PENDING'} for r in allrows),'تأییدشده':sum(r.get('status')=='APPROVED' for r in allrows),'ردشده':sum(r.get('status')=='REJECTED' for r in allrows)};self._update_status_buttons(counts)
        f=self.filter.get();rows=allrows
        if f=='Pending':rows=[r for r in rows if r.get('status') in {'PENDING_REVIEW','NEEDS_REVIEW','EDIT_PENDING'}]
        elif f=='تأییدشده':rows=[r for r in rows if r.get('status')=='APPROVED']
        elif f=='ردشده':rows=[r for r in rows if r.get('status')=='REJECTED']
        self.rows=rows
        def rv(r,idx):
            p=r.get('payload') or {};title,sub=_title_type_from_payload(p);desc=str(p.get('description') or r.get('raw_text') or '');amt=p.get('amount') or p.get('paid_amount') or p.get('final_amount') or 0;due=p.get('due_date_shamsi') if (title=='هزینه ساخت' and sub=='چک') else '—'
            return [f'☐ {fa(idx)}',str(r.get('message_date') or p.get('event_date_shamsi') or '-').split()[0],title,sub,desc[:80],_group_money(amt),p.get('receiver_name') or '—',p.get('issuer_name') or '—',_display_payment(p,title,sub),due or '—',p.get('main_phase') or '—',p.get('sub_phase') or '—']
        self.table.set_rows(rows,rv)
    def _select18(self,e=None):
        rows=self.table.selected_rows();self.current=rows[-1] if rows else None
        if self.current:self._show(self.current)
        self.table._sync_checks()
    def open_wizard(self,row=None):
        row=row or self.current
        if not row:return messagebox.showwarning('ثبت دیتا','یک سطر را انتخاب کن.',parent=self)
        def full():
            fresh=DB.get_pending_item(str(row['pending_id'])) or row;fresh=dict(fresh);fresh['raw_text']=_raw_text(str(row['pending_id']),row);UnifiedPendingEditor18(self,fresh,self.rich,self.refresh)
        TransactionWizard18(self,row,self.rich,self.refresh,full)
    def open_editor(self,row=None):
        row=row or self.current
        if not row:return
        UnifiedPendingEditor18(self,row,self.rich,self.refresh)
    def batch_delete18(self,rows):
        if not rows:return
        if not messagebox.askyesno('حذف',f'{fa(len(rows))} ردیف انتخاب‌شده حذف/مخفی شوند؟\nحذف مالی Soft Delete است.',parent=self):return
        ids=[]
        for r in rows:
            pid=str(r.get('pending_id') or '');
            if r.get('status') not in {'APPROVED','REJECTED'}:
                try:APPROVAL.reject(pid,actor_id='GUI_18_DELETE')
                except Exception:pass
            if pid:ids.append(pid)
        if ids:self.rich.hide_review(ids)
        self.refresh()
    def batch_approve18(self,rows):
        rows=[r for r in rows if r.get('status') not in {'APPROVED','REJECTED'}]
        if not rows:return
        if not messagebox.askyesno('تأیید انتخاب‌ها',f'{fa(len(rows))} رکورد تأیید شوند؟',parent=self):return
        ok=0;errs=[]
        for r in rows:
            try:approve_v18(str(r['pending_id']),dict(r.get('payload') or {}),self.rich);ok+=1
            except Exception as exc:errs.append(str(exc))
        self.refresh();self.on_posted and self.on_posted();self.action.set(f'{fa(ok)} تأیید شد | {fa(len(errs))} خطا')
        if errs:messagebox.showwarning('تأیید انتخاب‌ها','\n'.join(errs[:7]),parent=self)
    def batch_reject18(self,rows):
        rows=[r for r in rows if r.get('status') not in {'APPROVED','REJECTED'}]
        if not rows:return
        if not messagebox.askyesno('رد انتخاب‌ها',f'{fa(len(rows))} رکورد رد شوند؟',parent=self):return
        for r in rows:
            try:APPROVAL.reject(str(r['pending_id']),actor_id='GUI_18_BULK')
            except Exception:pass
        self.refresh()
    def copy_rows(self,rows):
        if not rows:return
        lines=[]
        for r in rows:
            p=r.get('payload') or {};t,s=_title_type_from_payload(p);lines.append(f"{r.get('message_date') or '-'}\t{t}\t{s}\t{p.get('description') or r.get('raw_text') or ''}\t{int(p.get('amount') or 0):,}")
        self.clipboard_clear();self.clipboard_append('\n'.join(lines));self.action.set(f'{fa(len(rows))} ردیف کپی شد.')
    def export_rows(self,rows):
        if not rows:return
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.txt',filetypes=[('Text','*.txt')],initialfile='BARKAV_Pending_Export.txt')
        if not path:return
        blocks=[]
        for r in rows:
            p=r.get('payload') or {};t,s=_title_type_from_payload(p);blocks.append('\n'.join([f"Pending ID: {r.get('pending_id')}",f"تاریخ: {r.get('message_date') or p.get('event_date_shamsi') or '-'}",f"عنوان: {t}",f"نوع: {s}",f"مبلغ: {_group_money(p.get('amount'))}",f"متن: {r.get('raw_text') or ''}",json.dumps(p,ensure_ascii=False,indent=2)]))
        Path(path).write_text('\n\n'+'\n\n---\n\n'.join(blocks),encoding='utf-8');self.action.set('خروجی کامل رکوردها ساخته شد.')
    def manual_transaction(self):
        mid=int(datetime.now().timestamp()*1_000_000);sh=gregorian_to_shamsi(datetime.now().date());p={'detected_type':'EXPENSE','v18_title':'هزینه ساخت','v18_subtype':'نقدی','event_date_shamsi':sh,'amount':0,'payment_state':'UNPAID','source':'MANUAL_GUI_18'};DB.register_telegram_message(chat_id=-180,message_id=mid,raw_text='',content_type='manual_gui',message_date=datetime.now().isoformat(timespec='seconds'),state='RECEIVED');pid=DB.create_or_replace_pending(telegram_chat_id=-180,telegram_message_id=mid,detected_type='EXPENSE',payload=p,confidence=1.0,status='PENDING_REVIEW');self.refresh();row=next((x for x in self.rows if str(x.get('pending_id'))==str(pid)),None)
        if row:self.open_wizard(row)
    def reprocess_rows(self,rows):
        rows=rows or ([self.current] if self.current else []);rows=[r for r in rows if r and r.get('status') in {'PENDING_REVIEW','NEEDS_REVIEW','EDIT_PENDING'}]
        if not rows:return messagebox.showinfo('پردازش مجدد','رکورد قابل پردازش انتخاب نشده است.',parent=self)
        self.action.set(f'در حال پردازش مجدد {fa(len(rows))} رکورد...')
        def worker():
            ok=0;errs=[]
            for r in rows:
                pid=str(r['pending_id']);old=dict(r.get('payload') or {});manual=set(old.get('v18_manual_fields') or [])
                try:
                    asyncio.run(APPROVAL.analyze_pending_with_ai(pid));fresh=DB.get_pending_item(pid) or {};new=dict(fresh.get('payload') or {});suggest={}
                    for k in manual:
                        if k in old and new.get(k)!=old.get(k):suggest[k]=new.get(k);new[k]=old.get(k)
                    new['v18_manual_fields']=sorted(manual)
                    if suggest:new['v18_reprocess_suggestions']=suggest
                    APPROVAL.save_payload(pid,new,learn=False);ok+=1
                except Exception as exc:errs.append(f'{pid}: {exc}')
            self.after(0,lambda:self._finish_reprocess(ok,errs))
        threading.Thread(target=worker,daemon=True).start()
    def _finish_reprocess(self,ok,errs):
        self.refresh();self.action.set(f'{fa(ok)} پردازش مجدد موفق | {fa(len(errs))} خطا')
        if errs:messagebox.showwarning('پردازش مجدد','\n'.join(errs[:6]),parent=self)
    def re_read_messages(self):
        # Telegram polling continues in the background; here we re-run failed/low-confidence saved items.
        candidates=[]
        for r in APPROVAL.list_reviews(limit=80):
            if r.get('status') not in {'PENDING_REVIEW','NEEDS_REVIEW','EDIT_PENDING'}:continue
            p=r.get('payload') or {};conf=float(p.get('confidence') or 0)
            if r.get('status')=='NEEDS_REVIEW' or conf<0.75:candidates.append(r)
        if not candidates:self.refresh();self.action.set('پیام جدید/ناموفق ذخیره‌شده‌ای برای بازخوانی پیدا نشد.');return
        self.reprocess_rows(candidates[:20])


# ---------------------------------------------------------------------------
# Project profile V18
# ---------------------------------------------------------------------------
class ProjectSettingsDialog18(tk.Toplevel):
    def __init__(self,parent,on_refresh=None):
        super().__init__(parent);self.on_refresh=on_refresh;self.ui=load_ui();self.font_family=self.ui.get('font_family','Segoe UI');self.font_size=int(self.ui.get('font_size',10));self.profile=load_profile();self.vars={};self.title('مشخصات پروژه');self.configure(bg=DARK['bg']);self.minsize(1000,680);_maximize(self);self._build()
    def _build(self):
        nb=ttk.Notebook(self);nb.pack(fill='both',expand=True,padx=10,pady=10)
        basic=tk.Frame(nb,bg=DARK['bg']);floors=tk.Frame(nb,bg=DARK['bg']);team=tk.Frame(nb,bg=DARK['bg']);nb.add(basic,text='مشخصات پایه');nb.add(floors,text='طبقات و واحدها');nb.add(team,text='عوامل پروژه')
        p=SERVICE.project.get_project();st=SERVICE.budget.get_settings();card=GlassSection(basic,'مشخصات پایه پروژه');card.pack(fill='x',padx=8,pady=8);b=card.body;b.grid_columnconfigure((0,1),weight=1)
        defs=[('name','نام پروژه',p.get('name') or ''),('address','آدرس',p.get('address') or ''),('postal_code','کدپستی',p.get('postal_code') or ''),('registration_plate','پلاک ثبتی',p.get('registration_plate') or ''),('municipal_file_no','شماره پرونده شهرداری',p.get('municipal_file_no') or ''),('gross_area','متراژ کل/غیرمفید',st.get('gross_area') or 0),('saleable_area','متراژ مفید/فروشی',st.get('saleable_area') or 0),('unit_count','تعداد کل واحدها',st.get('unit_count') or 0),('floor_count','تعداد طبقات',len(self.profile.get('floors') or []))]
        for i,(k,l,val) in enumerate(defs):
            box=tk.Frame(b,bg=DARK['panel']);box.grid(row=i//2,column=i%2,sticky='ew',padx=6,pady=5);tk.Label(box,text=l,bg=DARK['panel'],fg=DARK['text'],font=(self.font_family,self.font_size,'bold')).pack(anchor='e');v=tk.StringVar(value=str(val));self.vars[k]=v;e=ttk.Entry(box,textvariable=v,justify='right');e.pack(fill='x',pady=3);bind_grouped_number(e,v) if k in {'gross_area','saleable_area','unit_count','floor_count'} else None
        tk.Button(basic,text='💾 ذخیره مشخصات پایه',command=self.save_basic,bg='#356B4E',fg='white',relief='flat',font=(self.font_family,self.font_size,'bold'),padx=18,pady=8).pack(anchor='e',padx=8,pady=8)
        # floors / units editable grid
        fc=GlassSection(floors,'طبقات، تعداد واحد و متراژ واحدها');fc.pack(fill='both',expand=True,padx=8,pady=8);fb=fc.body
        self.floor_tree=ttk.Treeview(fb,columns=('floor','count','areas'),show='headings',height=13);self.floor_tree.heading('floor',text='طبقه');self.floor_tree.heading('count',text='تعداد واحد');self.floor_tree.heading('areas',text='متراژ واحدها (با , جدا شود)');self.floor_tree.column('floor',width=140,anchor='center');self.floor_tree.column('count',width=120,anchor='center');self.floor_tree.column('areas',width=500,anchor='e');self.floor_tree.pack(fill='both',expand=True)
        for i,r in enumerate(self.profile.get('floors') or []):self.floor_tree.insert('', 'end',iid=str(i),values=(r.get('floor',''),r.get('unit_count',0),', '.join(str(x) for x in r.get('areas',[]))))
        bar=tk.Frame(fb,bg=DARK['panel']);bar.pack(fill='x',pady=6);tk.Button(bar,text='➕ طبقه',command=self.add_floor,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=12,pady=6).pack(side='right',padx=3);tk.Button(bar,text='✏ ویرایش',command=self.edit_floor,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=12,pady=6).pack(side='right',padx=3);tk.Button(bar,text='🗑 حذف',command=self.del_floor,bg='#6A3A42',fg='white',relief='flat',padx=12,pady=6).pack(side='right',padx=3);tk.Button(bar,text='💾 ذخیره',command=self.save_floors,bg='#356B4E',fg='white',relief='flat',padx=14,pady=6).pack(side='left')
        # team
        tc=GlassSection(team,'مجری، ناظر و طراح');tc.pack(fill='both',expand=True,padx=8,pady=8);tb=tc.body;tb.grid_columnconfigure((0,1,2),weight=1);self.team_vars={}
        roles=[('executor','مجری'),('supervisor','ناظر'),('designer','طراح')]
        for c,(key,label) in enumerate(roles):
            box=GlassSection(tb,label);box.grid(row=0,column=c,sticky='nsew',padx=5,pady=5);d=self.profile.get('team',{}).get(key,{})
            self.team_vars[key]={}
            for i,(f,l) in enumerate([('name','نام و نام خانوادگی'),('phone','شماره تماس'),('license_no','شماره پروانه/عضویت'),('company','شرکت/دفتر')]):
                tk.Label(box.body,text=l,bg=DARK['panel'],fg=DARK['text'],font=(self.font_family,self.font_size,'bold')).pack(anchor='e',pady=(5,1));v=tk.StringVar(value=d.get(f,'') or '');self.team_vars[key][f]=v;ttk.Entry(box.body,textvariable=v,justify='right').pack(fill='x',pady=(0,4))
        tk.Button(team,text='💾 ذخیره عوامل پروژه',command=self.save_team,bg='#356B4E',fg='white',relief='flat',font=(self.font_family,self.font_size,'bold'),padx=18,pady=8).pack(anchor='e',padx=8,pady=8)
    def save_basic(self):
        try:
            def f(k):return float(str(self.vars[k].get()).replace(',','').replace('٬','') or 0)
            SERVICE.project.save_project(name=self.vars['name'].get(),address=self.vars['address'].get(),postal_code=self.vars['postal_code'].get(),registration_plate=self.vars['registration_plate'].get(),municipal_file_no=self.vars['municipal_file_no'].get())
            SERVICE.budget.save_settings(gross_area=f('gross_area'),saleable_area=f('saleable_area'),unit_count=int(f('unit_count')));self.on_refresh and self.on_refresh();messagebox.showinfo('مشخصات پروژه','مشخصات پایه ذخیره شد.',parent=self)
        except Exception as exc:messagebox.showerror('مشخصات پروژه',str(exc),parent=self)
    def _floor_dialog(self,initial=None):
        d=tk.Toplevel(self);d.title('طبقه');d.configure(bg=DARK['panel']);d.transient(self);d.grab_set();vals=initial or ('','','');vs=[tk.StringVar(value=str(x)) for x in vals]
        for i,l in enumerate(['نام/شماره طبقه','تعداد واحد','متراژ واحدها (مثال: 120, 135, 135)']):tk.Label(d,text=l,bg=DARK['panel'],fg=DARK['text']).grid(row=i,column=1,padx=7,pady=6);ttk.Entry(d,textvariable=vs[i],width=42,justify='right').grid(row=i,column=0,padx=7,pady=6)
        result={}
        def ok():result['v']=(vs[0].get().strip(),parse_int(vs[1].get()),vs[2].get().strip());d.destroy()
        tk.Button(d,text='تأیید',command=ok,bg='#356B4E',fg='white',relief='flat',padx=15,pady=7).grid(row=3,column=0,columnspan=2,pady=10);self.wait_window(d);return result.get('v')
    def add_floor(self):
        v=self._floor_dialog();
        if v:self.floor_tree.insert('', 'end',values=v)
    def edit_floor(self):
        s=self.floor_tree.selection();
        if not s:return
        old=self.floor_tree.item(s[0],'values');v=self._floor_dialog(old)
        if v:self.floor_tree.item(s[0],values=v)
    def del_floor(self):
        for i in self.floor_tree.selection():self.floor_tree.delete(i)
    def save_floors(self):
        floors=[]
        for iid in self.floor_tree.get_children():
            floor,count,areas=self.floor_tree.item(iid,'values');arr=[]
            for x in str(areas).replace('،',',').split(','):
                try:arr.append(float(x.strip()))
                except Exception:pass
            floors.append({'floor':str(floor),'unit_count':int(count or 0),'areas':arr})
        self.profile['floors']=floors;save_profile(self.profile);messagebox.showinfo('طبقات','اطلاعات طبقات و واحدها ذخیره شد.',parent=self);self.on_refresh and self.on_refresh()
    def save_team(self):
        self.profile['team']={k:{f:v.get().strip() for f,v in d.items()} for k,d in self.team_vars.items()};save_profile(self.profile);messagebox.showinfo('عوامل پروژه','مشخصات مجری، ناظر و طراح ذخیره شد.',parent=self)


class SystemTab18(tk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,bg=DARK['bg']);self.app=app;self.vars={};self._build();self.refresh()
    def _build(self):
        card=GlassSection(self,'سیستم');card.pack(fill='x',padx=12,pady=12);b=card.body;b.grid_columnconfigure(0,weight=1)
        self.status=tk.StringVar(value='');tk.Label(b,textvariable=self.status,bg=DARK['panel'],fg=DARK['text'],justify='right',anchor='ne',font=('Segoe UI',10),padx=12,pady=12).grid(row=0,column=0,sticky='ew')
        act=tk.Frame(b,bg=DARK['panel']);act.grid(row=1,column=0,sticky='ew',pady=8)
        ttk.Button(act,text='↻ بروزرسانی وضعیت',command=self.refresh).pack(side='right',padx=4)
        ttk.Button(act,text='📦 بسته توسعه',command=self.app.export_development_package).pack(side='right',padx=4)
        ttk.Button(act,text='🏗 مشخصات پروژه',command=self.app.edit_project_settings).pack(side='right',padx=4)
    def refresh(self):
        bot='در حال اجرا' if getattr(self.app,'_bot_process',None) and getattr(self.app._bot_process,'poll',lambda:1)() is None else 'متوقف/نامشخص'
        db_path=getattr(DB,'db_path',getattr(DB,'path','-'))
        self.status.set(f'نسخه برنامه: {VERSION}\nوضعیت دیتابیس: آماده\nTelegram Bot: {bot}\nمسیر دیتابیس: {db_path}\nAutoSave و رخدادهای مالی از مسیر دیتابیس پروژه مدیریت می‌شوند.')


class SettingsTab18(tk.Frame):
    def __init__(self,parent,on_apply):
        super().__init__(parent,bg=DARK['bg']);self.on_apply=on_apply;self.data=load_ui();self.vars={};self._build()
    def _build(self):
        card=GlassSection(self,'تنظیمات ظاهر و کاربری');card.pack(fill='x',padx=12,pady=12);b=card.body;b.grid_columnconfigure((0,1),weight=1)
        defs=[('font_family','نوع فونت',('Segoe UI','Segoe UI','Arial')),('font_size','اندازه فونت',tuple(str(x) for x in range(8,17))),('appearance','حالت نمایش',('dark','light'))]
        for i,(k,l,vals) in enumerate(defs):
            box=tk.Frame(b,bg=DARK['panel']);box.grid(row=i//2,column=i%2,sticky='ew',padx=7,pady=7);tk.Label(box,text=l,bg=DARK['panel'],fg=DARK['text'],font=('Segoe UI',10,'bold')).pack(anchor='e');v=tk.StringVar(value=str(self.data.get(k,'')));self.vars[k]=v;ttk.Combobox(box,textvariable=v,state='readonly',values=vals).pack(fill='x',pady=4)
        tk.Button(b,text='💾 ذخیره تنظیمات',command=self.save,bg='#356B4E',fg='white',relief='flat',padx=16,pady=8,font=('Segoe UI',10,'bold')).grid(row=3,column=0,columnspan=2,sticky='e',padx=7,pady=10)
        tk.Label(b,text='برخی تغییرات ظاهری پس از بازکردن مجدد برنامه روی تمام تب‌ها اعمال می‌شوند.',bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',8)).grid(row=4,column=0,columnspan=2,sticky='e',padx=7,pady=5)
    def save(self):
        d=load_ui();d.update({k:v.get() for k,v in self.vars.items()});d['font_size']=int(d['font_size']);save_ui(d);messagebox.showinfo('تنظیمات','تنظیمات ذخیره شد. برای یکپارچه‌شدن کامل فونت/تم، برنامه را یک بار باز و بسته کن.',parent=self);self.on_apply and self.on_apply()


# ---------------------------------------------------------------------------
# Main V18 shell and dashboard visual system
# ---------------------------------------------------------------------------
class Stage18Dashboard(v175.Stage175Dashboard):
    def __init__(self):
        self.ui=load_ui();self.nav_buttons={};self.navbar=None;super().__init__();self.title('BARKAV — Engineering & Construction — Version 18.0');
        try: apply_phase04_rules_v18(self.rich)
        except Exception: pass
        self.after(50,lambda:_maximize(self));self.bind_all('<Escape>',self._global_escape,add='+');self.bind_all('<MouseWheel>',self._global_mousewheel,add='+')
    def _style(self):
        # restrained Windows-11-inspired palette; one blue accent, no rainbow headings.
        DARK.update({'bg':'#0E1116','surface':'#171B22','panel':'#1B2028','panel2':'#202731','glass':'#222A35','line':'#343D49','text':'#F1F4F8','muted':'#A7B0BC','blue':'#4C8DCE','green':'#557B68','orange':'#8A7B54','red':'#77535B','cyan':'#607A83','violet':'#6E687D','yellow':'#9A8B54'})
        try:v175.v16.d12.COLORS.update({'bg':DARK['bg'],'panel':DARK['panel'],'soft':DARK['surface'],'rowblue':'#181E26','text':DARK['text'],'muted':DARK['muted'],'line':DARK['line'],'navy':'#D7E5F4','blue':DARK['blue'],'cyan':DARK['cyan'],'green':DARK['green'],'yellow':DARK['yellow'],'orange':DARK['orange'],'red':DARK['red']})
        except Exception:pass
        # Inherited dashboard/report builders now instantiate the V18 neutral KPI card.
        v175.PremiumMetricCard175=PremiumMetricCard18
        st=ttk.Style(self)
        try:st.theme_use('clam')
        except Exception:pass
        ff=self.ui.get('font_family','Segoe UI');fs=int(self.ui.get('font_size',10));rh=int(self.ui.get('row_height',38))
        st.configure('.',font=(ff,fs),background=DARK['bg'],foreground=DARK['text']);st.configure('TFrame',background=DARK['bg']);st.configure('Panel.TFrame',background=DARK['panel']);st.configure('TLabel',background=DARK['bg'],foreground=DARK['text']);st.configure('TButton',padding=(10,7),background=DARK['glass'],foreground=DARK['text'],bordercolor=DARK['line'],relief='flat');st.map('TButton',background=[('active','#303A47'),('pressed','#3B526A')]);st.configure('TEntry',fieldbackground='#151A21',foreground=DARK['text'],insertcolor='white',bordercolor=DARK['line'],padding=6);st.configure('TCombobox',fieldbackground='#151A21',background='#151A21',foreground=DARK['text'],arrowcolor=DARK['text'],bordercolor=DARK['line'],padding=5);st.map('TCombobox',fieldbackground=[('readonly','#151A21')],foreground=[('readonly',DARK['text'])]);st.configure('TScrollbar',background='#2A323D',troughcolor='#12161C',bordercolor=DARK['line'],arrowcolor=DARK['muted']);st.configure('Treeview',rowheight=rh,background='#171C23',fieldbackground='#171C23',foreground=DARK['text'],bordercolor=DARK['line'],font=(ff,fs));st.configure('Treeview.Heading',background='#232A34',foreground=DARK['text'],font=(ff,max(8,fs-1),'bold'),padding=(6,8));st.map('Treeview',background=[('selected','#335C80')],foreground=[('selected','#FFFFFF')]);st.configure('Hidden.TNotebook',background=DARK['bg'],borderwidth=0);st.layout('Hidden.TNotebook.Tab',[])
    def _build(self):
        self.configure(bg=DARK['bg']);ff=self.ui.get('font_family','Segoe UI');fs=int(self.ui.get('font_size',10))
        top=tk.Frame(self,bg='#151A21',height=66,highlightbackground=DARK['line'],highlightthickness=1);top.pack(fill='x');top.pack_propagate(False)
        brand=tk.Frame(top,bg='#151A21');brand.pack(side='left',padx=14,pady=7);tk.Label(brand,text='BARKAV',bg='#151A21',fg=DARK['text'],font=('Segoe UI',17,'bold')).pack(anchor='w');tk.Label(brand,text='Engineering & Construction   18.0',bg='#151A21',fg=DARK['muted'],font=('Segoe UI',8)).pack(anchor='w')
        project=tk.Frame(top,bg=DARK['glass'],highlightbackground=DARK['line'],highlightthickness=1);project.pack(side='right',padx=10,pady=9);self.project_name_top=tk.StringVar(value='پروژه');self.datetime_top=tk.StringVar(value='');tk.Label(project,textvariable=self.project_name_top,bg=DARK['glass'],fg=DARK['text'],font=(ff,fs,'bold')).pack(side='right',padx=10,pady=5);tk.Button(project,text='✎',command=self.edit_project_settings,bg=DARK['glass'],fg=DARK['text'],activebackground='#303A47',relief='flat').pack(side='right',padx=3);tk.Label(project,textvariable=self.datetime_top,bg=DARK['glass'],fg=DARK['muted'],font=(ff,max(8,fs-2))).pack(side='right',padx=8)
        tools=tk.Frame(top,bg='#151A21');tools.pack(side='right',padx=5,pady=9)
        for text,cmd,tip in [('💾 ذخیره',self.manual_save,'بکاپ دستی دیتابیس'),('📦 بسته توسعه',self.export_development_package,'خروجی امن توسعه'),('↶ Undo',self.undo,'بازگشت'),('↷ Redo',self.redo,'اجرای دوباره'),('↻ بروزرسانی',self.refresh_all,'بروزرسانی اطلاعات')]:
            b=tk.Button(tools,text=text,command=cmd,bg=DARK['glass'],fg=DARK['text'],activebackground='#303A47',relief='flat',font=(ff,max(8,fs-1)),padx=8,pady=6);b.pack(side='right',padx=2);add_tooltip(b,tip)
        self.navbar=tk.Frame(self,bg='#12161C',height=48,highlightbackground=DARK['line'],highlightthickness=1);self.navbar.pack(fill='x',padx=7,pady=(6,0));self.navbar.pack_propagate(False)
        self.notebook=ttk.Notebook(self,style='Hidden.TNotebook');self.notebook.pack(fill='both',expand=True,padx=7,pady=(5,7))
        self._build_overview();self._build_manager();self._build_financial();self._build_cheques();self._build_sales();self._build_reconciliation();self._build_reports();self._build_market();self._build_system();self._build_settings();self._rebuild_navbar();self.notebook.bind('<<NotebookTabChanged>>',lambda e:(self._sync_nav(),_maximize(self)),add='+');self._attach_common_tooltips(self);self._tick_clock()
    def _rebuild_navbar(self):
        for w in self.navbar.winfo_children():w.destroy()
        self.nav_buttons={};ff=self.ui.get('font_family','Segoe UI');fs=int(self.ui.get('font_size',10))
        for tid in self.notebook.tabs():
            txt=self.notebook.tab(tid,'text');b=tk.Button(self.navbar,text=txt,command=lambda t=tid:self.notebook.select(t),bg='#1E252E',fg=DARK['muted'],activebackground='#2B3541',activeforeground=DARK['text'],relief='flat',bd=0,font=(ff,fs,'bold'),padx=16,pady=8,cursor='hand2',highlightbackground=DARK['line'],highlightthickness=1);b.pack(side='left',fill='y',padx=3,pady=5);self.nav_buttons[tid]=b
        self._sync_nav()
    def _sync_nav(self):
        try:sel=str(self.notebook.select())
        except Exception:return
        for tid,b in self.nav_buttons.items():
            active=str(tid)==sel;b.configure(bg='#2B3B4C' if active else '#1E252E',fg=DARK['text'] if active else DARK['muted'],relief='raised' if active else 'flat',bd=1 if active else 0)
    def _build_approval_center(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.approval_tab=tab;self.notebook.insert(1,tab,text='ثبت دیتا');self.approval_center=DataEntryCenter18(tab,self.rich,on_posted=self.refresh_all);self.approval_center.pack(fill='both',expand=True)
        if self._bot_process:self.approval_center.set_bot_process(self._bot_process,self._bot_log)
        self.after_idle(self._rebuild_navbar)
    def _build_system(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.notebook.add(tab,text='سیستم');self.system_tab18=SystemTab18(tab,self);self.system_tab18.pack(fill='both',expand=True)
    def _build_settings(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.notebook.add(tab,text='تنظیمات');SettingsTab18(tab,self._reload_ui).pack(fill='both',expand=True)
    def _reload_ui(self):self.ui=load_ui()
    def edit_project_settings(self):ProjectSettingsDialog18(self,self.refresh_all)
    def _global_escape(self,e=None):
        try:
            w=self.focus_get();
            if isinstance(w,ttk.Treeview):w.selection_remove(w.selection())
        except Exception:pass
    def _global_mousewheel(self,e):
        # Let the widget directly under the cursor scroll; this fixes dashboard/forms that otherwise require dragging the scrollbar.
        try:w=self.winfo_containing(e.x_root,e.y_root)
        except Exception:return
        cur=w
        while cur is not None:
            if isinstance(cur,ttk.Treeview):cur.yview_scroll(int(-e.delta/120),'units');return 'break'
            if isinstance(cur,tk.Text):cur.yview_scroll(int(-e.delta/120),'units');return 'break'
            if isinstance(cur,tk.Canvas) and cur.cget('scrollregion'):
                try:cur.yview_scroll(int(-e.delta/120),'units');return 'break'
                except Exception:pass
            cur=getattr(cur,'master',None)
    def _build_overview(self):
        # V18 dashboard follows the user's hand sketch: a few large glass groups,
        # one phase strip, then charts/tables.  All V15 metrics remain available.
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.notebook.add(tab,text='داشبورد')
        wrap=tk.Frame(tab,bg=DARK['bg']);wrap.pack(fill='both',expand=True)
        canvas=tk.Canvas(wrap,bg=DARK['bg'],highlightthickness=0);vs=ttk.Scrollbar(wrap,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=vs.set);canvas.pack(side='left',fill='both',expand=True);vs.pack(side='right',fill='y')
        inner=tk.Frame(canvas,bg=DARK['bg']);win=canvas.create_window((0,0),window=inner,anchor='nw');inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')));canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width));canvas.bind('<MouseWheel>',lambda e:(canvas.yview_scroll(int(-e.delta/120),'units'),'break')[1]);self.overview_canvas=canvas
        # Project header
        proj=GlassSection(inner,'نمای کلی پروژه');proj.pack(fill='x',padx=5,pady=(4,7));pb=proj.body
        self.project_info=tk.StringVar(value='مشخصات پروژه');self.project_meta_var=tk.StringVar(value='')
        tk.Label(pb,textvariable=self.project_info,bg=DARK['panel'],fg=DARK['text'],font=('Segoe UI',9,'bold'),justify='right').pack(side='right',padx=7)
        tk.Label(pb,textvariable=self.project_meta_var,bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',8)).pack(side='right',padx=8)
        tk.Button(pb,text='اصلاح مشخصات پروژه',command=self.edit_project_settings,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=12,pady=6).pack(side='left',padx=4)
        self.cards={}
        groups=tk.Frame(inner,bg=DARK['bg']);groups.pack(fill='x',padx=5,pady=3)
        for c in range(3):groups.grid_columnconfigure(c,weight=1,uniform='dash3')
        group_defs=[
            ('تراکنش‌ها',[('total_in','کل ورودی'),('cost','هزینه کل ساخت'),('total_out','کل خروجی'),('cash','تنخواه فعلی'),('free','مانده آزاد')]),
            ('چک‌ها',[('ch_all_total','کل چک‌ها'),('ch_open_total','چک‌های پاس‌نشده'),('ch30_count','سررسید ۳۰ روز'),('ch30_amount','مبلغ سررسید ۳۰ روز')]),
            ('فروش و مطالبات',[('sales_contract','کل قرارداد فروش'),('sales_received','وصول خریداران'),('sales_receivable','مطالبات'),('sales_30','مطالبات ۳۰ روز'),('sales_overdue','مطالبات معوق')]),
        ]
        for col,(gt,items) in enumerate(group_defs):
            sec=GlassSection(groups,gt);sec.grid(row=0,column=col,sticky='nsew',padx=4,pady=2);body=sec.body
            for k,t in items:
                m=InlineMetric18(body,t);m.pack(fill='x',pady=2);self.cards[k]=m
        finance=GlassSection(inner,'نقدینگی و تسهیلات');finance.pack(fill='x',padx=9,pady=5);fb=finance.body
        fdefs=[('liq_obligation','تعهد ۳۰ روز'),('liq_inflow','وصول ۳۰ روز'),('liq_projected','تراز ۳۰ روز'),('loan_principal','اصل تسهیلات'),('loan_paid','اقساط پرداختی'),('loan_remaining','مانده تسهیلات'),('loan_30','اقساط ۳۰ روز')]
        for c in range(len(fdefs)):fb.grid_columnconfigure(c,weight=1,uniform='loanliq')
        for c,(k,t) in enumerate(fdefs):m=InlineMetric18(fb,t);m.grid(row=0,column=c,sticky='nsew',padx=2);self.cards[k]=m
        # Phase strip exactly one horizontal line.
        phase=GlassSection(inner,'پیشرفت مراحل پروژه — ۳۲ فاز');phase.pack(fill='x',padx=9,pady=6);ph=phase.body
        hint=tk.Label(ph,text='کلیک: جزئیات  |  دابل‌کلیک: وضعیت و درصد فاز',bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',8));hint.pack(anchor='e',pady=(0,4))
        self.phase_strip=tk.Frame(ph,bg=DARK['panel']);self.phase_strip.pack(fill='x');self.phase_buttons={}
        for c in range(32):self.phase_strip.grid_columnconfigure(c,weight=1,uniform='phase32')
        for i in range(1,33):
            b=tk.Button(self.phase_strip,text=fa(f'{i:02d}'),bg='#202731',fg='#AEB8C5',activebackground='#33445A',activeforeground='white',relief='flat',bd=0,font=('Segoe UI',6,'bold'),padx=0,pady=6,command=lambda n=i:self.open_phase_by_no(n));b.grid(row=0,column=i-1,sticky='nsew',padx=1);b.bind('<Double-1>',lambda e,n=i:self.edit_phase_progress(n));self.phase_buttons[i]=b
        self.overall_progress=v175.ProjectProgressBar(ph,on_open=lambda:v175.v16.ProjectFinancialOverview(self,self.rich));self.overall_progress.pack(fill='x',pady=(6,0))
        # Charts: large and clean, as in the lower circles of the sketch.
        charts=tk.Frame(inner,bg=DARK['bg']);charts.pack(fill='x',padx=5,pady=5);charts.grid_columnconfigure((0,1,2),weight=1,uniform='chart3')
        self.cost_donut=v175.DonutChart175(charts,'ترکیب برآورد فازها',230);self.cost_donut.grid(row=0,column=0,sticky='nsew',padx=4)
        self.liquidity_chart=v175.MiniLineChart(charts,'روند تجمعی برآورد / واقعی / پیش‌بینی',230);self.liquidity_chart.grid(row=0,column=1,sticky='nsew',padx=4)
        self.phase_chart=v175.MiniBarChart(charts,'مقایسه فازها',230);self.phase_chart.grid(row=0,column=2,sticky='nsew',padx=4)
        # Operational near-term tables remain available but visually below the executive dashboard.
        tables=tk.Frame(inner,bg=DARK['bg']);tables.pack(fill='x',padx=5,pady=5);tables.grid_columnconfigure((0,1,2),weight=1,uniform='table3')
        cbox=ttk.LabelFrame(tables,text='چک‌های ۳۰ روز آینده',padding=5);cbox.grid(row=0,column=2,sticky='nsew',padx=3);self.overview_cheque_table=CompactTable(cbox,[('due','سررسید',90),('days','روز',55),('amount','مبلغ',110),('issuer','صاحب حساب',110),('bank','بانک',90),('receiver','گیرنده',110)],height=5);self.overview_cheque_table.pack(fill='both',expand=True)
        sbox=ttk.LabelFrame(tables,text='وصول ۳۰ روز آینده',padding=5);sbox.grid(row=0,column=1,sticky='nsew',padx=3);self.overview_sales_upcoming=CompactTable(sbox,[('buyer','خریدار',120),('unit','واحد',60),('due','سررسید',85),('amount','مانده',105),('days','روز',45)],height=5);self.overview_sales_upcoming.pack(fill='both',expand=True)
        obox=ttk.LabelFrame(tables,text='مطالبات معوق',padding=5);obox.grid(row=0,column=0,sticky='nsew',padx=3);self.overview_sales_overdue=CompactTable(obox,[('buyer','خریدار',120),('unit','واحد',60),('due','سررسید',85),('amount','مانده',105),('days','تأخیر',45)],height=5);self.overview_sales_overdue.pack(fill='both',expand=True)
        lbox=ttk.LabelFrame(inner,text='اقساط تسهیلات پیش‌رو',padding=5);lbox.pack(fill='x',padx=9,pady=5);self.overview_loan_table=CompactTable(lbox,[('lender','بانک',110),('title','عنوان',150),('no','قسط',50),('due','تاریخ',90),('amount','مانده',110),('days','روز',70)],height=3);self.overview_loan_table.pack(fill='x')
        rec=ttk.LabelFrame(inner,text='تطبیق سریع بانک',padding=7);rec.pack(fill='x',padx=9,pady=(5,12));self.bank_var=tk.StringVar();self.bank_date=tk.StringVar();ttk.Label(rec,text='موجودی واقعی:').pack(side='right');be=ttk.Entry(rec,textvariable=self.bank_var,width=18,justify='center');be.pack(side='right',padx=3);bind_grouped_number(be,self.bank_var,allow_negative=True);ttk.Label(rec,text='تاریخ:').pack(side='right',padx=(8,0));DateField(rec,self.bank_date,width=11).pack(side='right',padx=3);ttk.Button(rec,text='ثبت تطبیق',command=self.record_reconciliation).pack(side='right',padx=4);self.bank_info=tk.StringVar(value='آخرین تطبیق: -');self.bank_info_label=tk.Label(rec,textvariable=self.bank_info,bg=DARK['panel'],fg=DARK['text'],font=('Segoe UI',8,'bold'));self.bank_info_label.pack(side='left',padx=6)

    def _build_cheques(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.notebook.add(tab,text='چک‌ها')
        bar=GlassSection(tab,'مدیریت چک‌ها');bar.pack(fill='x',padx=4,pady=(2,6));h=bar.body
        self.ch_filter=tk.StringVar(value='همه');vals=['همه','ثبت‌نشده','ثبت‌شده','صادرشده','پاس‌شده','برگشتی','عودتی','عودتی به شرط تسویه','باطل‌شده','ضمانتی']
        ttk.Combobox(h,textvariable=self.ch_filter,state='readonly',values=vals,width=22).pack(side='right',padx=4)
        ttk.Button(h,text='ویرایش مشخصات/وضعیت',command=self.edit_cheque).pack(side='right',padx=4)
        self.ch_filter.trace_add('write',lambda *_:self.refresh_cheques())
        tk.Label(h,text='هر چک یک ردیف مستقل است.',bg=DARK['panel'],fg=DARK['muted']).pack(side='left',padx=8)
        self.cheque_table=SmartTable(tab,[('issue','تاریخ صدور',100),('due','سررسید',105),('amount','مبلغ',125),('issuer','صاحب حساب',120),('type','نوع',90),('reg','ثبت',90),('guarantee','ضمانت',70),('receiver','گیرنده',120),('bank','بانک',100),('serial','شماره/صیادی',120),('desc','بابت',190),('status','وضعیت چک',135),('id','Cheque ID',145)],title='چک‌ها')
        self.cheque_table.pack(fill='both',expand=True);self.cheque_table.set_edit_handler(self.edit_cheque_row);self.cheque_table.set_delete_handler(self._cancel_cheque_row)
    def _cheque_display_status(self,r):
        st=str(r.get('status') or 'ISSUED').upper();mode=str(r.get('settlement_mode') or 'NORMAL').upper()
        if st=='CASHED' and mode=='RETURNED_SETTLED':return 'عودتی به شرط تسویه'
        return {'ISSUED':'صادرشده','PENDING_DUE':'صادرشده','CASHED':'پاس‌شده','RETURNED':'برگشتی','CANCELLED':'باطل‌شده'}.get(st,st)
    def refresh_cheques(self):
        rows=SERVICE.list_cheques(open_only=False);f=getattr(self,'ch_filter',tk.StringVar(value='همه')).get()
        if f=='ثبت‌نشده':rows=[r for r in rows if str(r.get('registration_state') or 'UNREGISTERED')=='UNREGISTERED']
        elif f=='ثبت‌شده':rows=[r for r in rows if str(r.get('registration_state') or '')=='REGISTERED']
        elif f=='ضمانتی':rows=[r for r in rows if int(r.get('is_guarantee') or 0)==1]
        elif f!='همه':rows=[r for r in rows if self._cheque_display_status(r)==f]
        for r in rows:r['_sum_amount']=int(r.get('amount') or 0)
        self.cheque_table.set_rows(rows,lambda r:[r.get('issue_date_shamsi') or '-',r.get('due_date_shamsi') or '-',_group_money(r.get('amount')),r.get('issuer_name') or '-',CHEQUE_TYPE_FA.get(str(r.get('cheque_type') or 'PHYSICAL').upper(),'فیزیکی'),REG_FA.get(str(r.get('registration_state') or 'UNREGISTERED').upper(),'ثبت‌نشده'),'بله' if r.get('is_guarantee') else 'خیر',r.get('receiver_name') or '-',r.get('issuer_bank') or '-',r.get('cheque_serial') or '-',r.get('description') or '-',self._cheque_display_status(r),r['cheque_id']])
    def edit_cheque_row(self,r):ChequeEditDialog18(self,r,self.refresh_all)
    def edit_cheque(self):
        r=self._one(self.cheque_table)
        if r:ChequeEditDialog18(self,r,self.refresh_all)

    def import_budget(self):
        path=filedialog.askopenfilename(parent=self,filetypes=[('Excel','*.xlsx')])
        if not path:return
        from tkinter import simpledialog
        import shutil
        title=simpledialog.askstring('عنوان نسخه','عنوان این نسخه برآورد:',parent=self) or Path(path).stem
        try:
            SERVICE.budget.import_budget_xlsx(path,title)
            rich_result=self.rich.import_workbook(path,title,preserve_manual=True)
            apply_phase04_rules_v18(self.rich)
            shutil.copy2(path,BASE_DIR/'phase_budget_current.xlsx')
            self.refresh_reports()
            messagebox.showinfo('برآورد بارگذاری شد',f"اکسل بارگذاری و قواعد V18 فاز 04 اعمال شد.\n\nفازها: {rich_result.phase_count}\nریز ردیف‌ها: {rich_result.phase_item_count}\nجمع فایل ورودی: {fmt_money(rich_result.total_estimate)}",parent=self)
        except Exception as exc:messagebox.showerror('Import برآورد',str(exc),parent=self)

    def export_development_package(self):
        dest=filedialog.asksaveasfilename(parent=self,defaultextension='.zip',initialfile='BARKAV_Development_Package_18.0.zip',filetypes=[('ZIP','*.zip')])
        if not dest:return
        try:
            res=v175.v174.build_development_package(BASE_DIR,Path(dest),VERSION);messagebox.showinfo('بسته توسعه',f"بسته توسعه {VERSION} ساخته شد:\n{res['path']}\n\nدیتابیس زنده و secrets وارد بسته نشده‌اند.",parent=self)
        except Exception as exc:messagebox.showerror('بسته توسعه',str(exc),parent=self)


# compatibility aliases
Stage175Dashboard = Stage18Dashboard
Stage17Dashboard = Stage18Dashboard

if __name__=='__main__':Stage18Dashboard().mainloop()
