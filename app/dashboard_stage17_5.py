from __future__ import annotations

import asyncio
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

import dashboard_stage17 as v174
import dashboard_stage16_3 as v16
from dashboard_stage17 import (
    DARK, TYPE_FA, TYPE_BY_FA, METHOD_FA, METHOD_BY_FA, STATE_FA_EDIT, STATE_EDIT_BY_FA,
    CHEQUE_TYPE_FA, CHEQUE_TYPE_BY_FA, REG_FA, REG_BY_FA, STATUS_FA,
    SearchableCombo, MiniLineChart, MiniBarChart, ProjectProgressBar,
    PhaseProgressDialog, PhaseChoiceDialog, PriceDetailDialog17, PhaseDetailDialog17,
    fmt_money, fa, norm, as_int, Image, ImageOps, ImageTk, DB, SERVICE, CONFIG, BASE_DIR,
    APPROVAL, SmartTable, CompactTable, DateField, bind_grouped_number, group_int, parse_int,
    add_tooltip, normalize_shamsi, shamsi_to_gregorian, gregorian_to_shamsi, std_window,
    infer_receiver, _mark_nonfinancial_approved, _raw_text_for_pending,
)
from phase_intelligence_v175 import apply_suggestion_to_payload, suggest_phase

VERSION = '17.5'

# More explicit lifecycle vocabulary.  Registration status remains a separate field.
CHEQUE_STATUS_FA = {
    'ISSUED': 'صادرشده',
    'PENDING_DUE': 'صادرشده',
    'CASHED': 'پاس‌شده',
    'RETURNED': 'برگشتی',
    'RETURNED_ON_SETTLEMENT': 'عودتی به شرط تسویه',
    'VOIDED': 'باطل‌شده',
    'CANCELLED': 'باطل‌شده',
}
CHEQUE_STATUS_BY_FA = {
    'صادرشده': 'ISSUED', 'پاس‌شده': 'CASHED', 'برگشتی': 'RETURNED',
    'عودتی به شرط تسویه': 'RETURNED_ON_SETTLEMENT', 'باطل‌شده': 'VOIDED',
}
CHEQUE_RETURN_DISPOSITIONS_175 = (
    'دریافت چک', 'عودت سیستمی', 'دریافت و عودت سیستمی', 'عدم دریافت و عدم عودت سیستمی',
)

# The 17.5 visual system is deliberately high-contrast and closer to the approved
# desktop mock-up.  Mutating the shared dict means inherited widgets use the same
# palette instead of looking like a different application.
DARK.update({
    'bg': '#0A111B',
    'surface': '#101A27',
    'panel': '#121E2C',
    'panel2': '#172536',
    'glass': '#1A2A3D',
    'line': '#30445C',
    'text': '#F1F6FC',
    'muted': '#9BAABD',
    'blue': '#1E86F7',
    'violet': '#8D6BFF',
    'green': '#2BC56C',
    'orange': '#F4B52C',
    'red': '#FF6268',
    'cyan': '#22C7C9',
    'yellow': '#F6C853',
})


# ---------------------------------------------------------------------------
# Visual components
# ---------------------------------------------------------------------------
class PremiumMetricCard175(tk.Frame):
    """Executive KPI card with the same API used by the legacy dashboard cards."""
    def __init__(self, parent, title: str, accent: str, icon: str, info: str = '', on_open=None, compact: bool = False):
        super().__init__(parent, bg=DARK['panel'], highlightbackground=DARK['line'], highlightthickness=1)
        self.title = title; self.info = info; self.on_open = on_open
        self.configure(cursor='hand2' if on_open else '')
        tk.Frame(self, bg=accent, height=3).pack(fill='x')
        body = tk.Frame(self, bg=DARK['panel']); body.pack(fill='both', expand=True, padx=10, pady=7 if compact else 10)
        left = tk.Frame(body, bg=DARK['panel']); left.pack(side='left', padx=(0, 8))
        tk.Label(left, text=icon, bg=DARK['panel'], fg=accent,
                 font=('Segoe UI Symbol', 15 if compact else 22, 'bold')).pack()
        right = tk.Frame(body, bg=DARK['panel']); right.pack(side='right', fill='both', expand=True)
        head = tk.Frame(right, bg=DARK['panel']); head.pack(fill='x')
        tk.Label(head, text=title, bg=DARK['panel'], fg=DARK['muted'], font=('Segoe UI', 7 if compact else 8, 'bold')).pack(side='right')
        if info:
            lab = tk.Label(head, text='ⓘ', bg=DARK['panel'], fg=accent, font=('Segoe UI', 8, 'bold'), cursor='hand2')
            lab.pack(side='left'); add_tooltip(lab, info)
        self.var = tk.StringVar(value='۰ تومان')
        self.value = tk.Label(right, textvariable=self.var, bg=DARK['panel'], fg=DARK['text'],
                              font=('Segoe UI', 10 if compact else 13, 'bold'), anchor='e')
        self.value.pack(fill='x', pady=(4, 0)); self.value_label = self.value
        if on_open:
            for w in (self, body, right, self.value):
                w.bind('<Double-1>', lambda e: on_open())


class DonutChart175(tk.Canvas):
    def __init__(self, parent, title='خلاصه برآورد', height=220):
        super().__init__(parent, bg=DARK['panel'], highlightbackground=DARK['line'], highlightthickness=1, height=height)
        self.title = title; self.items: list[tuple[str, float, str]] = []; self.total = 0.0
        self.bind('<Configure>', lambda e: self.redraw())
    def set_items(self, items: list[tuple[str, float, str]]):
        self.items = items; self.total = sum(max(0, float(x[1] or 0)) for x in items); self.redraw()
    def redraw(self):
        self.delete('all'); w=max(360,self.winfo_width()); h=max(200,self.winfo_height())
        self.create_text(w-12,14,text=self.title,anchor='ne',fill=DARK['text'],font=('Segoe UI',9,'bold'))
        cx,cy=min(105,w*.25),h*.53; r=min(68,h*.32); inner=r*.58
        colors={'blue':DARK['blue'],'green':DARK['green'],'orange':DARK['orange'],'red':DARK['red'],'cyan':DARK['cyan'],'violet':DARK['violet'],'muted':'#718198'}
        start=90.0; total=self.total or 1.0
        for label,val,cname in self.items:
            extent=-360.0*max(0,float(val))/total
            self.create_arc(cx-r,cy-r,cx+r,cy+r,start=start,extent=extent,fill=colors.get(cname,cname),outline=DARK['panel'])
            start += extent
        self.create_oval(cx-inner,cy-inner,cx+inner,cy+inner,fill=DARK['panel'],outline=DARK['panel'])
        # Keep Persian digits and compact the magnitude for a small executive card.
        n=self.total
        if abs(n)>=1_000_000_000: short=fa(f'{n/1_000_000_000:.1f}B')
        elif abs(n)>=1_000_000: short=fa(f'{n/1_000_000:.1f}M')
        else: short=fa(f'{n:,.0f}')
        self.create_text(cx,cy-5,text=short,fill='white',font=('Segoe UI',12,'bold'))
        self.create_text(cx,cy+17,text='تومان',fill=DARK['muted'],font=('Segoe UI',7))
        y=45; x=max(200,w*.52)
        for label,val,cname in self.items[:6]:
            c=colors.get(cname,cname); self.create_rectangle(x,y-5,x+9,y+4,fill=c,outline='')
            pct=(float(val)/total*100) if total else 0
            self.create_text(x+15,y,text=f'{label}  {fa(f"{pct:.0f}")}٪',anchor='w',fill=DARK['text'],font=('Segoe UI',7))
            y += 25


# ---------------------------------------------------------------------------
# Phase intelligence helpers
# ---------------------------------------------------------------------------
def _phase_text(p: dict[str, Any]) -> str:
    return str(p.get('raw_text') or p.get('description') or '')


def _apply_phase_hint(payload: dict[str, Any], raw: str, rich, force=False):
    return apply_suggestion_to_payload(payload, raw or str(payload.get('description') or ''), rich, force=force)


# ---------------------------------------------------------------------------
# Cheque creation / approval
# ---------------------------------------------------------------------------
def _normalize_cheque_status(value: Any) -> str:
    s = str(value or '').strip()
    if s in CHEQUE_STATUS_BY_FA:
        return CHEQUE_STATUS_BY_FA[s]
    up = s.upper()
    return up if up in CHEQUE_STATUS_FA else 'ISSUED'


def _registered_cheque_state_conflict175(row, lifecycle, registration):
    linked = DB.get_cheque_registered_pending(str(row.get('cheque_id') or ''))
    if not linked:
        return None
    payload = linked.get('payload') or {}
    expected_lifecycle = _normalize_cheque_status(
        payload.get('cheque_status') or payload.get('status') or 'ISSUED')
    expected_registration = str(payload.get('cheque_registration_state') or
                                payload.get('registration_state') or 'UNREGISTERED').upper()
    if expected_registration not in {'REGISTERED', 'UNREGISTERED'}:
        expected_registration = str(row.get('registration_state') or 'UNREGISTERED').upper()
    if expected_lifecycle == 'PENDING_DUE':
        expected_lifecycle = 'ISSUED'
    if expected_lifecycle == 'CANCELLED':
        expected_lifecycle = 'VOIDED'
    if expected_lifecycle != lifecycle or expected_registration != registration:
        linked['cheque_id'] = str(row.get('cheque_id') or '')
        return linked
    return None


def _choose_cheque_mismatch_action175(parent, pending):
    """Return True to open the source wizard; False leaves the check unchanged."""
    window = tk.Toplevel(parent)
    std_window(window, 'مغایرت با تراکنش ثبت‌شده', '500x185', (440, 170))
    window.transient(parent)
    window.grab_set()
    decision = {'edit': False}
    tk.Label(
        window,
        text='وضعیت انتخاب‌شده با اطلاعات تراکنش ثبت‌شده مغایرت دارد.',
        bg=DARK['panel'], fg=DARK['text'], wraplength=455, justify='right',
        font=('Segoe UI', 10, 'bold'),
    ).pack(fill='both', expand=True, padx=18, pady=(16, 5))
    actions = tk.Frame(window, bg=DARK['panel'])
    actions.pack(fill='x', padx=16, pady=(4, 14))
    def finish(edit):
        decision['edit'] = bool(edit)
        window.destroy()
    tk.Button(actions, text='انصراف', command=lambda: finish(False),
              bg=DARK['glass'], fg=DARK['text'], relief='flat', padx=18, pady=7).pack(side='left')
    tk.Button(actions, text='ویرایش تراکنش', command=lambda: finish(True),
              bg=DARK['blue'], fg='white', relief='flat', padx=18, pady=7).pack(side='right')
    window.wait_window()
    return decision['edit'], pending


def _open_cheque_source_wizard175(parent, pending):
    owner = parent
    while owner is not None and not hasattr(owner, 'approval_center'):
        owner = getattr(owner, 'master', None)
    center = getattr(owner, 'approval_center', None) if owner is not None else None
    if center is None:
        messagebox.showwarning('ثبت دیتا', 'ویزارد تراکنش در دسترس نیست.', parent=parent)
        return
    try:
        if getattr(owner, 'approval_tab', None) is not None:
            owner.notebook.select(owner.approval_tab)
        center.refresh()
        fresh = DB.get_pending_item(str(pending.get('pending_id') or '')) or pending
        fresh = dict(fresh)
        payload = dict(fresh.get('payload') or {})
        cheque_id = str(pending.get('cheque_id') or payload.get('cheque_id') or payload.get('selected_cheque_id187') or '')
        payload.update(
            v18_title='هزینه ساخت', v18_subtype='چک',
            transaction_title='هزینه ساخت', transaction_subtype='چک',
            cheque_operation187='تعیین تکلیف چک',
            selected_cheque_id187=cheque_id,
            selected_cheque_manual187=True,
            _resolution_edit_cheque_id187=cheque_id,
        )
        fresh['payload'] = payload
        center.open_wizard(fresh)
    except Exception as exc:
        messagebox.showerror('ثبت دیتا', str(exc), parent=parent)


def _cheque_display_status175(row):
    mode = str(row.get('settlement_mode') or '').upper()
    status = str(row.get('status') or 'ISSUED').upper()
    if mode == 'RETURNED_ON_SETTLEMENT':
        return 'RETURNED_ON_SETTLEMENT'
    if mode == 'VOIDED' or status == 'CANCELLED':
        return 'VOIDED'
    return 'ISSUED' if status == 'PENDING_DUE' else status


def _cheque_row_values175(row, columns):
    """Render by stable column keys so RTL reordering cannot shift values."""
    values = {
        'issue': row.get('issue_date_shamsi') or '-',
        'due': row.get('due_date_shamsi') or '-',
        'amount': fmt_money(row.get('amount') or 0),
        'issuer': row.get('issuer_name') or '-',
        'type': CHEQUE_TYPE_FA.get(str(row.get('cheque_type') or 'PHYSICAL').upper(), 'فیزیکی'),
        'reg': REG_FA.get(str(row.get('registration_state') or 'UNREGISTERED').upper(), 'ثبت‌نشده'),
        'status': CHEQUE_STATUS_FA.get(_cheque_display_status175(row), '-'),
        'return_state': (row.get('return_disposition') or '-')
            if _cheque_display_status175(row) in {'RETURNED_ON_SETTLEMENT', 'VOIDED'} else '-',
        'guarantee': 'بله' if row.get('is_guarantee') else 'خیر',
        'receiver': row.get('receiver_name') or '-',
        'bank': row.get('issuer_bank') or '-',
        'serial': row.get('cheque_serial') or '-',
        'desc': row.get('description') or row.get('expense_description') or '-',
        'id': row.get('cheque_id') or '-',
    }
    return [values.get(item[0], '-') for item in (columns or ()) if item[0] != 'row']


def _looks_like_cheque(x: dict[str, Any]) -> bool:
    return any(x.get(k) not in (None, '') for k in ('due_date_shamsi','issue_date_shamsi','cheque_serial','issuer_bank','bank_name')) or as_int(x.get('amount')) > 0


def _set_cheque_meta175(cid: str, payload: dict[str, Any]):
    reg = str(payload.get('cheque_registration_state') or payload.get('registration_state') or 'UNREGISTERED').upper()
    if reg not in {'REGISTERED','UNREGISTERED'}: reg='UNREGISTERED'
    with DB.tx() as con:
        con.execute('''UPDATE cheques SET registration_state=?,is_guarantee=?,guarantee_status=COALESCE(NULLIF(guarantee_status,''),'HELD'),updated_at=? WHERE cheque_id=?''',
                    (reg,1 if payload.get('is_guarantee') else 0,datetime.now().isoformat(timespec='seconds'),cid))


def _apply_created_cheque_status(cid: str, payload: dict[str, Any]):
    target=_normalize_cheque_status(payload.get('cheque_status') or payload.get('status') or 'ISSUED')
    if target=='ISSUED': return
    sh=normalize_shamsi(str(payload.get('cheque_status_event_date_shamsi') or payload.get('cashed_date_shamsi') or payload.get('event_date_shamsi') or payload.get('due_date_shamsi') or ''))
    event_date=shamsi_to_gregorian(sh) if sh else None
    DB.set_cheque_lifecycle_status(cid,target,event_date=event_date,event_date_shamsi=sh or None,source='GUI_17_5',actor_id='GUI')


def _create_cheque175(payload: dict[str, Any], raw='', source='GUI_17_5') -> str:
    amount=as_int(payload.get('amount') or payload.get('paid_amount') or payload.get('final_amount'))
    due=normalize_shamsi(str(payload.get('due_date_shamsi') or ''))
    issue=normalize_shamsi(str(payload.get('issue_date_shamsi') or payload.get('event_date_shamsi') or '')) or due
    if amount<=0: raise ValueError('مبلغ چک کامل نیست.')
    if not due: raise ValueError('تاریخ سررسید چک کامل نیست.')
    cid=DB.create_cheque(
        amount=amount,issue_date=shamsi_to_gregorian(issue),issue_date_shamsi=issue,
        due_date=shamsi_to_gregorian(due),due_date_shamsi=due,
        cheque_serial=str(payload.get('cheque_serial') or ''),issuer_bank=str(payload.get('issuer_bank') or payload.get('bank_name') or ''),
        issuer_name=str(payload.get('issuer_name') or ''),cheque_type=str(payload.get('cheque_type') or 'PHYSICAL'),
        receiver_name=str(payload.get('receiver_name') or ''),description=str(payload.get('description') or raw),
        source=source,actor_id='GUI',is_guarantee=bool(payload.get('is_guarantee')),
    )
    _set_cheque_meta175(cid,payload); _apply_created_cheque_status(cid,payload); return cid


def approve_v175(pid: str, payload: dict[str, Any], rich):
    typ=str(payload.get('detected_type') or 'UNKNOWN').upper(); state=str(payload.get('payment_state') or 'UNKNOWN').upper(); raw=_raw_text_for_pending(pid)
    if typ=='INFO':
        _mark_nonfinancial_approved(pid,'INFO',pid); return 'اطلاع‌رسانی ثبت شد؛ اثر مالی ندارد.'
    if typ=='DOCUMENT':
        links=[]; lp=str(payload.get('link_pending_id') or '')
        if lp:
            post=DB.get_financial_posting(lp)
            if post and post.get('primary_entity_type') and post.get('primary_entity_id'): links=[(post['primary_entity_type'],post['primary_entity_id'])]
        did=rich.add_financial_document(pid,payload,raw,links); DB.relink_pending_attachments(pid,entity_type='DOCUMENT',entity_id=did); _mark_nonfinancial_approved(pid,'DOCUMENT',did)
        return 'سند به پرونده اسناد مالی اضافه شد؛ رویداد مالی جدید ساخته نشد.'

    multi=payload.get('cheques') if isinstance(payload.get('cheques'),list) else []
    multi=[dict(c or {}) for c in multi if isinstance(c,dict) and _looks_like_cheque(c or {})]

    # A multi-cheque image is always decomposed into independent cheque records.
    # The shared image is represented once as a document bundle; the cheque tab
    # therefore shows one row per cheque rather than a synthetic sum row.
    if state!='CHEQUE_CLEARING' and multi:
        created=[]
        guarantee=bool(payload.get('is_guarantee'))
        for idx,c in enumerate(multi,1):
            x=dict(payload); x.pop('cheques',None); x.update(c)
            x['is_guarantee']=bool(c.get('is_guarantee',guarantee))
            x['cheque_registration_state']=c.get('registration_state') or c.get('cheque_registration_state') or payload.get('cheque_registration_state') or 'UNREGISTERED'
            x['cheque_status']=c.get('status') or c.get('cheque_status') or payload.get('cheque_status') or 'ISSUED'
            try: created.append(_create_cheque175(x,raw,'GUI_MULTI_CHEQUE_17_5'))
            except Exception as exc: raise ValueError(f'چک {idx}: {exc}')
        dtype='GUARANTEE_CHEQUE_BUNDLE' if guarantee else 'CHEQUE_BUNDLE'
        did=rich.add_financial_document(pid,{**payload,'document_type':dtype,'amount':sum(as_int(c.get('amount')) for c in multi)},raw,[('CHEQUE',c) for c in created])
        DB.relink_pending_attachments(pid,entity_type='DOCUMENT',entity_id=did); _mark_nonfinancial_approved(pid,'DOCUMENT',did)
        suffix='؛ بدون اثر مالی' if guarantee else ''
        return f'{len(created)} چک مستقل ثبت شد{suffix}. تصویر مشترک به پرونده چک‌ها متصل است.'

    if typ=='CHEQUE' and payload.get('is_guarantee'):
        cid=_create_cheque175({**payload,'is_guarantee':True},raw,'GUI_GUARANTEE_17_5')
        did=rich.add_financial_document(pid,{**payload,'document_type':'GUARANTEE_CHEQUE'},raw,[('CHEQUE',cid)])
        DB.relink_pending_attachments(pid,entity_type='DOCUMENT',entity_id=did); _mark_nonfinancial_approved(pid,'DOCUMENT',did)
        return 'چک ضمانتی ثبت شد؛ در هزینه، خروجی و تعهد مالی محاسبه نمی‌شود.'

    if state=='CHEQUE_CLEARING':
        amount=as_int(payload.get('amount') or payload.get('paid_amount') or payload.get('final_amount')); sh=normalize_shamsi(str(payload.get('event_date_shamsi') or ''))
        editing=bool(payload.get('_editing_cheque_clearing187'))
        previous_id=str(payload.get('_original_clearing_cheque_id187') or '').strip()
        if editing and previous_id:
            DB.reopen_cheque_settlement_for_edit(previous_id,source='GUI_CHEQUE_CLEARING_EDIT',actor_id='GUI')
        rows=[r for r in DB.list_cheques(open_only=True,limit=1000)
              if str(r.get('status') or '').upper() in {'ISSUED','PENDING_DUE'}
              and not int(r.get('is_guarantee') or 0)]; cand=[]
        selected_id=str(payload.get('selected_cheque_id187') or payload.get('cheque_id') or '').strip()
        if selected_id:
            ch=next((r for r in rows if str(r.get('cheque_id'))==selected_id),None)
            if not ch: raise ValueError('چک انتخاب‌شده صادرشده یا قابل پاس‌شدن نیست.')
        else:
            desc=norm(str(payload.get('description') or '')+' '+str(payload.get('receiver_name') or '')+' '+raw)
            for r in rows:
                score=0
                if amount and int(r.get('amount') or 0)==amount: score+=55
                if sh and sh==str(r.get('due_date_shamsi') or ''): score+=40
                hay=norm(str(r.get('receiver_name') or '')+' '+str(r.get('description') or ''))
                if desc and hay and any(t in hay for t in desc.split() if len(t)>2): score+=10
                if score: cand.append((score,r))
            cand.sort(key=lambda x:-x[0])
            if not cand: raise ValueError('چک بازی با مبلغ/سررسید این رسید پیدا نشد.')
            if len(cand)>1 and cand[0][0]==cand[1][0]: raise ValueError('چند چک مشابه پیدا شد؛ ابتدا مشخصات چک صحیح را دقیق کن.')
            ch=cand[0][1]
        target_status=str(payload.get('cheque_status') or 'CASHED').upper()
        if target_status not in {'CASHED','پاس‌شده'}:
            raise ValueError('برای ثبت «پاس کردن چک»، وضعیت نهایی باید «پاس‌شده» باشد.')
        cash_sh=sh or gregorian_to_shamsi(datetime.now().date())
        clearing_mode=str(payload.get('cheque_clearing_mode187') or '').strip()
        linked_cheque_id=ch['cheque_id']
        if clearing_mode=='حساب دسته چک':
            DB.pass_cheque_from_checkbook(ch['cheque_id'],cashed_date=shamsi_to_gregorian(cash_sh),
                cashed_date_shamsi=cash_sh,source='GUI_CHECKBOOK_17_5',actor_id='GUI')
        elif clearing_mode=='واریز به حساب معرفی شده':
            replacement=DB.replace_cheque_by_transfer(ch['cheque_id'],
                settled_date=shamsi_to_gregorian(cash_sh),settled_date_shamsi=cash_sh,
                account_holder=str(payload.get('cheque_transfer_account_holder187') or ch.get('issuer_name') or '').strip(),
                description=str(payload.get('cheque_transfer_description187') or ch.get('description') or '').strip(),
                source='GUI_TRANSFER_REPLACEMENT_17_5',actor_id='GUI')
            linked_cheque_id=str(replacement.get('cheque_id') or ch['cheque_id'])
        else:
            DB.cash_cheque(ch['cheque_id'],cashed_date=shamsi_to_gregorian(cash_sh),
                cashed_date_shamsi=cash_sh,source='GUI_RECEIPT_17_5',actor_id='GUI')
        payload['_editing_cheque_clearing187']=True
        payload['_original_clearing_cheque_id187']=str(ch['cheque_id'])
        payload['_original_clearing_mode187']=clearing_mode
        DB.update_pending(pid,payload=payload)
        DB.relink_pending_attachments(pid,entity_type='CHEQUE',entity_id=linked_cheque_id)
        _mark_nonfinancial_approved(pid,'CHEQUE',linked_cheque_id)
        if clearing_mode=='حساب دسته چک':
            return f"چک {ch['cheque_id']} پاس شد؛ ردیف تازه‌ای در تراکنش‌ها و چک‌ها ساخته نشد."
        if clearing_mode=='واریز به حساب معرفی شده':
            return f"چک قبلی {ch['cheque_id']} عودتی شد؛ تسویهٔ بانکی با ردیف {linked_cheque_id} ثبت شد و هزینه دوباره محاسبه نشد."
        return f"چک {ch['cheque_id']} پاس شد؛ هزینه دوباره ثبت نشد."

    result=APPROVAL.approve(pid,actor_id='GUI_17_5')
    if result.posting.cheque_id:
        _set_cheque_meta175(result.posting.cheque_id,payload)
        try: _apply_created_cheque_status(result.posting.cheque_id,payload)
        except Exception as exc: raise ValueError(f'ثبت مالی انجام شد ولی وضعیت چک کامل نشد: {exc}')
    return f"ثبت شد: {TYPE_FA.get(str(result.posting.posting_type),'ثبت مالی')}"


# ---------------------------------------------------------------------------
# Project settings / manual cost entry
# ---------------------------------------------------------------------------
class ProjectSettingsDialog175(tk.Toplevel):
    def __init__(self,parent,on_refresh=None):
        super().__init__(parent); self.on_refresh=on_refresh; std_window(self,'مشخصات پروژه','820x700',(680,560))
        p=SERVICE.project.get_project(); st=SERVICE.budget.get_settings(); self.vars={}
        outer=tk.Frame(self,bg=DARK['bg']); outer.pack(fill='both',expand=True,padx=12,pady=12)
        head=tk.Frame(outer,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1); head.pack(fill='x',pady=(0,8))
        tk.Label(head,text='مشخصات پایه پروژه و پارامترهای متراژ',bg=DARK['surface'],fg=DARK['text'],font=('Segoe UI',11,'bold')).pack(side='right',padx=10,pady=9)
        form=tk.Frame(outer,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1); form.pack(fill='both',expand=True); form.grid_columnconfigure(0,weight=1)
        defs=[
            ('name','نام پروژه',p.get('name') or ''),('address','آدرس',p.get('address') or ''),('postal_code','کدپستی',p.get('postal_code') or ''),
            ('registration_plate','پلاک ثبتی',p.get('registration_plate') or ''),('municipal_file_no','شماره پرونده شهرداری',p.get('municipal_file_no') or ''),
            ('gross_area','متراژ کل/غیرمفید',st.get('gross_area') or 0),('saleable_area','متراژ مفید/فروشی',st.get('saleable_area') or 0),('unit_count','تعداد واحدها',st.get('unit_count') or 0),
        ]
        for i,(k,l,val) in enumerate(defs):
            tk.Label(form,text=l+':',bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',8)).grid(row=i,column=1,sticky='e',padx=10,pady=6)
            v=tk.StringVar(value=str(val if val is not None else '')); self.vars[k]=v
            e=ttk.Entry(form,textvariable=v,justify='right',width=52); e.grid(row=i,column=0,sticky='ew',padx=10,pady=6)
            if k=='unit_count': bind_grouped_number(e,v)
        tk.Label(form,text='توضیحات:',bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',8)).grid(row=len(defs),column=1,sticky='ne',padx=10,pady=6)
        self.desc=tk.Text(form,height=6,wrap='word',bg=DARK['panel2'],fg=DARK['text'],insertbackground='white',relief='flat',font=('Segoe UI',8)); self.desc.grid(row=len(defs),column=0,sticky='nsew',padx=10,pady=6); self.desc.insert('1.0',p.get('description') or '')
        form.grid_rowconfigure(len(defs),weight=1)
        note='این مقادیر در گزارش‌گیری، هزینه/مترمربع و هزینه/واحد استفاده می‌شوند. جزئیات جدول واحدها مستقل باقی می‌ماند.'
        tk.Label(outer,text=note,bg=DARK['bg'],fg=DARK['muted'],font=('Segoe UI',7),wraplength=720,justify='right').pack(fill='x',pady=7)
        bar=tk.Frame(outer,bg=DARK['bg']);bar.pack(fill='x');tk.Button(bar,text='💾 ذخیره مشخصات',command=self.save,bg=DARK['green'],fg='white',relief='flat',padx=18,pady=8,font=('Segoe UI',9,'bold')).pack(side='right')
    def save(self):
        try:
            def fnum(k): return float(str(self.vars[k].get()).replace(',','').replace('٬','').strip() or 0)
            cnt=parse_int(self.vars['unit_count'].get())
            SERVICE.project.save_project(name=self.vars['name'].get(),address=self.vars['address'].get(),postal_code=self.vars['postal_code'].get(),registration_plate=self.vars['registration_plate'].get(),municipal_file_no=self.vars['municipal_file_no'].get(),description=self.desc.get('1.0','end').strip())
            SERVICE.budget.save_settings(gross_area=fnum('gross_area'),saleable_area=fnum('saleable_area'),unit_count=cnt)
            if self.on_refresh: self.on_refresh()
            messagebox.showinfo('مشخصات پروژه','مشخصات پروژه و متراژها ذخیره شد.',parent=self); self.destroy()
        except Exception as exc: messagebox.showerror('مشخصات پروژه',str(exc),parent=self)


class ManualExpenseDialog175(tk.Toplevel):
    def __init__(self,parent,rich,on_saved):
        super().__init__(parent); self.rich=rich; self.on_saved=on_saved; self.vars={}; self._suggestion=None
        std_window(self,'ثبت هزینه دستی — ابتدا به Pending می‌رود','760x620',(620,500))
        body=tk.Frame(self,bg=DARK['panel']); body.pack(fill='both',expand=True,padx=12,pady=12); body.grid_columnconfigure(0,weight=1)
        defs=[('date','تاریخ','date'),('amount','مبلغ پرداختی (تومان)','num'),('payer','واریزکننده','entry'),('receiver','گیرنده','entry'),('desc','بابت / شرح هزینه','entry')]
        for i,(k,l,kind) in enumerate(defs):
            tk.Label(body,text=l+':',bg=DARK['panel'],fg=DARK['muted']).grid(row=i,column=1,sticky='e',padx=6,pady=6); v=tk.StringVar();self.vars[k]=v
            if kind=='date':w=DateField(body,v,width=34)
            else:w=ttk.Entry(body,textvariable=v,justify='right',width=46); bind_grouped_number(w,v) if kind=='num' else None
            w.grid(row=i,column=0,sticky='ew',padx=6,pady=6)
        self.vars['payer'].set('تنخواه'); self.vars['date'].set(gregorian_to_shamsi(datetime.now().date()))
        self.phase_var=tk.StringVar(value='فاز پیشنهادی: بعد از وارد کردن شرح، «پیشنهاد فاز» را بزن.')
        tk.Label(body,textvariable=self.phase_var,bg=DARK['panel2'],fg=DARK['cyan'],font=('Segoe UI',8,'bold'),wraplength=600,justify='right',padx=8,pady=8).grid(row=5,column=0,columnspan=2,sticky='ew',padx=6,pady=7)
        bar=tk.Frame(body,bg=DARK['panel']);bar.grid(row=6,column=0,columnspan=2,sticky='ew',pady=12)
        tk.Button(bar,text='🧠 پیشنهاد فاز',command=self.preview_phase,bg=DARK['glass'],fg='white',relief='flat',padx=12,pady=7).pack(side='right',padx=3)
        tk.Button(bar,text='➕ ایجاد در Pending',command=self.save,bg=DARK['green'],fg='white',relief='flat',padx=16,pady=7,font=('Segoe UI',9,'bold')).pack(side='right',padx=3)
    def preview_phase(self):
        s=suggest_phase(self.vars['desc'].get(),self.rich); self._suggestion=s
        if not s:self.phase_var.set('فاز پیشنهادی: تشخیص مطمئن نیست؛ در فرم Pending خودت فاز را انتخاب کن.');return
        sub=f' ← {s.sub_phase}' if s.sub_phase else ''
        self.phase_var.set(f'فاز پیشنهادی: {s.phase_no:02d} — {s.phase_name}{sub} | اطمینان {fa(f"{s.confidence*100:.0f}")}٪ | {s.reason}')
    def save(self):
        try:
            amount=parse_int(self.vars['amount'].get()); desc=self.vars['desc'].get().strip(); sh=normalize_shamsi(self.vars['date'].get())
            if amount<=0: raise ValueError('مبلغ هزینه را وارد کن.')
            if not desc: raise ValueError('شرح هزینه را وارد کن.')
            if not sh: raise ValueError('تاریخ معتبر نیست.')
            p={'detected_type':'EXPENSE','event_date_shamsi':sh,'amount':amount,'paid_amount':amount,'invoice_amount':amount,'final_amount':amount,'remaining_debt':0,'discount_amount':0,'payment_state':'PAID','payment_method':'UNKNOWN','payer_name':self.vars['payer'].get().strip() or 'تنخواه','receiver_name':self.vars['receiver'].get().strip(),'description':desc,'source':'MANUAL_GUI_17_5'}
            p,s,_=_apply_phase_hint(p,desc,self.rich,force=True)
            mid=int(datetime.now().timestamp()*1_000_000)
            DB.register_telegram_message(chat_id=-175,message_id=mid,raw_text=desc,content_type='manual_gui',message_date=datetime.now().isoformat(timespec='seconds'),state='RECEIVED')
            pid=DB.create_or_replace_pending(telegram_chat_id=-175,telegram_message_id=mid,detected_type='EXPENSE',payload=p,confidence=(s.confidence if s else 1.0),status='PENDING_REVIEW')
            self.destroy(); self.on_saved(pid)
        except Exception as exc: messagebox.showerror('ثبت هزینه دستی',str(exc),parent=self)


# ---------------------------------------------------------------------------
# Scroll-safe Pending editor
# ---------------------------------------------------------------------------
class UnifiedPendingEditor175(v174.UnifiedPendingEditor17):
    def _field(self,parent,key,label,kind='entry',row=0,col=0,width=24):
        if kind!='lifecycle': return super()._field(parent,key,label,kind,row,col,width)
        box=tk.Frame(parent,bg=DARK['panel']);box.grid(row=row,column=col,sticky='ew',padx=4,pady=3);box.grid_columnconfigure(0,weight=1)
        tk.Label(box,text=label,bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',8)).grid(row=0,column=0,sticky='e')
        v=self.vars.setdefault(key,tk.StringVar()); w=ttk.Combobox(box,textvariable=v,state='readonly',values=list(CHEQUE_STATUS_BY_FA),width=width)
        w.grid(row=1,column=0,sticky='ew',pady=(2,0)); self.widgets[key]=w; return w

    def _build(self):
        head=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);head.pack(fill='x',padx=8,pady=8)
        tk.Label(head,text='ویرایش و تأیید رکورد',bg=DARK['surface'],fg=DARK['text'],font=('Segoe UI',11,'bold')).pack(side='right',padx=10,pady=7)
        self.status_lbl=tk.Label(head,text='',bg=DARK['surface'],fg=DARK['yellow'],font=('Segoe UI',8,'bold'));self.status_lbl.pack(side='left',padx=10)
        pane=ttk.Panedwindow(self,orient='horizontal');pane.pack(fill='both',expand=True,padx=8,pady=(0,8))
        ev=tk.Frame(pane,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);frm=tk.Frame(pane,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);pane.add(ev,weight=5);pane.add(frm,weight=5)
        tk.Label(ev,text='شواهد — سند و متن کاربر',bg=DARK['panel'],fg='#7FC9FF',font=('Segoe UI',10,'bold')).pack(anchor='e',padx=9,pady=(7,3))
        ep=ttk.Panedwindow(ev,orient='horizontal');ep.pack(fill='both',expand=True,padx=7,pady=(0,7));imgf=tk.Frame(ep,bg='#07101B');txtf=tk.Frame(ep,bg=DARK['panel2']);ep.add(imgf,weight=3);ep.add(txtf,weight=2)
        self.canvas=tk.Canvas(imgf,bg='#07101B',highlightthickness=0);ys=ttk.Scrollbar(imgf,orient='vertical',command=self.canvas.yview);xs=ttk.Scrollbar(imgf,orient='horizontal',command=self.canvas.xview);self.canvas.configure(yscrollcommand=ys.set,xscrollcommand=xs.set);self.canvas.grid(row=0,column=0,sticky='nsew');ys.grid(row=0,column=1,sticky='ns');xs.grid(row=1,column=0,sticky='ew');imgf.grid_rowconfigure(0,weight=1);imgf.grid_columnconfigure(0,weight=1)
        self.canvas.bind('<MouseWheel>',self._wheel);self.canvas.bind('<ButtonPress-1>',lambda e:self.canvas.scan_mark(e.x,e.y));self.canvas.bind('<B1-Motion>',lambda e:self.canvas.scan_dragto(e.x,e.y,gain=1))
        ib=tk.Frame(imgf,bg='#07101B');ib.grid(row=2,column=0,columnspan=2,sticky='ew')
        for t,cmd in [('−',lambda:self._set_zoom(self._zoom/1.2)),('Fit',self._fit_image),('+',lambda:self._set_zoom(self._zoom*1.2))]:tk.Button(ib,text=t,command=cmd,bg=DARK['glass'],fg='white',relief='flat',width=5).pack(side='left',padx=2,pady=4)
        etf=tk.Frame(txtf,bg=DARK['panel2']);etf.pack(fill='both',expand=True);self.evidence_text=tk.Text(etf,wrap='word',bg='#091726',fg=DARK['text'],insertbackground='white',relief='flat',font=('Segoe UI',8),padx=8,pady=8);ets=ttk.Scrollbar(etf,orient='vertical',command=self.evidence_text.yview);self.evidence_text.configure(yscrollcommand=ets.set);self.evidence_text.pack(side='left',fill='both',expand=True);ets.pack(side='right',fill='y');self.evidence_text.configure(state='disabled')

        # FIX 17.5: form actions stay visible; the user never has to drag the right
        # scrollbar to the bottom just to approve/save a cheque.
        action=tk.Frame(frm,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);self.fixed_action_bar=action;action.pack(side='bottom',fill='x',padx=5,pady=5)
        tk.Button(action,text='✅ تأیید نهایی',command=self.approve,bg=DARK['green'],fg='white',relief='flat',padx=12,pady=7,font=('Segoe UI',8,'bold')).pack(side='right',padx=3,pady=4)
        tk.Button(action,text='💾 ذخیره اصلاحات',command=self.save_only,bg=DARK['blue'],fg='white',relief='flat',padx=12,pady=7).pack(side='right',padx=3,pady=4)
        tk.Button(action,text='❌ رد',command=self.reject,bg=DARK['red'],fg='white',relief='flat',padx=12,pady=7).pack(side='right',padx=3,pady=4)
        self.msg=tk.StringVar();tk.Label(action,textvariable=self.msg,bg=DARK['surface'],fg=DARK['muted'],font=('Segoe UI',7),wraplength=280,justify='left').pack(side='left',padx=6)

        holder=tk.Frame(frm,bg=DARK['panel']);holder.pack(side='top',fill='both',expand=True)
        self.form_canvas=tk.Canvas(holder,bg=DARK['panel'],highlightthickness=0);self.form_scroll=ttk.Scrollbar(holder,orient='vertical',command=self.form_canvas.yview);self.form_canvas.configure(yscrollcommand=self.form_scroll.set);self.form_canvas.pack(side='left',fill='both',expand=True);self.form_scroll.pack(side='right',fill='y')
        body=tk.Frame(self.form_canvas,bg=DARK['panel']);wid=self.form_canvas.create_window((0,0),window=body,anchor='nw');body.bind('<Configure>',lambda e:self.form_canvas.configure(scrollregion=self.form_canvas.bbox('all')));self.form_canvas.bind('<Configure>',lambda e:self.form_canvas.itemconfigure(wid,width=e.width))
        self.bind('<MouseWheel>',self._form_wheel,add='+');self.bind('<Prior>',lambda e:self.form_canvas.yview_scroll(-8,'units'),add='+');self.bind('<Next>',lambda e:self.form_canvas.yview_scroll(8,'units'),add='+')

        sel=tk.LabelFrame(body,text='نوع و تاریخ',bg=DARK['panel'],fg='#7FC9FF',font=('Segoe UI',9,'bold'));sel.pack(fill='x',padx=8,pady=6);sel.grid_columnconfigure((0,1),weight=1)
        self._field(sel,'event_date_shamsi','تاریخ','date',0,1);self._field(sel,'detected_type','نوع تراکنش','type',0,0)
        self.system_event=tk.StringVar(value='');tk.Label(sel,textvariable=self.system_event,bg=DARK['panel'],fg=DARK['orange'],font=('Segoe UI',8,'bold')).grid(row=1,column=0,columnspan=2,sticky='e',padx=5,pady=3)

        self.expense_frame=tk.LabelFrame(body,text='هزینه / سایر تراکنش مالی',bg=DARK['panel'],fg='#7FC9FF',font=('Segoe UI',9,'bold'));self.expense_frame.pack(fill='x',padx=8,pady=6);self.expense_frame.grid_columnconfigure((0,1),weight=1)
        specs=[('payer_name','واریزکننده','entry'),('amount','مبلغ پرداختی','num'),('payment_state','وضعیت پرداخت','state'),('invoice_amount','مبلغ فاکتور','num'),('final_amount','مبلغ نهایی','num'),('remaining_debt','مانده بدهی','num'),('discount_amount','تخفیف','num'),('receiver_name','گیرنده','entry'),('description','بابت','entry'),('payment_method','روش پرداخت','method')]
        self.expense_keys=[];self.expense_widgets=[]
        for i,(k,l,kind) in enumerate(specs):w=self._field(self.expense_frame,k,l,kind,i//2,i%2);self.expense_keys.append(k);self.expense_widgets.append(w)

        self.cheque_frame=tk.LabelFrame(body,text='مشخصات چک',bg=DARK['panel'],fg='#7FC9FF',font=('Segoe UI',9,'bold'));self.cheque_frame.pack(fill='x',padx=8,pady=6);self.cheque_frame.grid_columnconfigure((0,1),weight=1)
        cs=[('amount','مبلغ پرداختی','num'),('invoice_amount','مبلغ فاکتور','num'),('remaining_debt','مانده بدهی','num'),('receiver_name','گیرنده','entry'),('issue_date_shamsi','تاریخ صدور چک','date'),('due_date_shamsi','تاریخ سررسید','date'),('issuer_bank','بانک','entry'),('issuer_name','صاحب حساب','entry'),('cheque_serial','شماره/صیادی','entry'),('cheque_type','نوع چک','chequetype'),('cheque_registration_state','وضعیت ثبت صیادی','reg'),('cheque_status','وضعیت چک','lifecycle'),('cheque_status_event_date_shamsi','تاریخ رویداد وضعیت','date'),('description','بابت','entry')]
        self.cheque_widgets=[]
        for i,(k,l,kind) in enumerate(cs):w=self._field(self.cheque_frame,k,l,kind,i//2,i%2);self.cheque_widgets.append(w)
        self.is_guarantee=tk.BooleanVar(value=False);cb=tk.Checkbutton(self.cheque_frame,text='بابت ضمانت — در هزینه و تعهد مالی محاسبه نشود',variable=self.is_guarantee,bg=DARK['panel'],fg=DARK['text'],selectcolor=DARK['surface'],activebackground=DARK['panel'],activeforeground='white');cb.grid(row=7,column=0,columnspan=2,sticky='e',padx=6,pady=5);self.cheque_widgets.append(cb)
        tk.Label(self.cheque_frame,text='وضعیت چک قابل اصلاح است. «پاس‌شده» از مسیر امن تسویه، و «لغوشده» از مسیر ابطال حسابداری اعمال می‌شود.',bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',7),wraplength=570,justify='right').grid(row=8,column=0,columnspan=2,sticky='e',padx=5,pady=3)
        self.multi_cheque_var=tk.StringVar();tk.Label(self.cheque_frame,textvariable=self.multi_cheque_var,bg=DARK['panel'],fg=DARK['orange'],font=('Segoe UI',8,'bold'),wraplength=570,justify='right').grid(row=9,column=0,columnspan=2,sticky='ew',padx=5,pady=3)
        mt=tk.Frame(self.cheque_frame,bg=DARK['panel']);mt.grid(row=10,column=0,columnspan=2,sticky='nsew',padx=5,pady=4);mt.grid_columnconfigure(0,weight=1);mt.grid_rowconfigure(0,weight=1)
        self.multi_cheque_tree=ttk.Treeview(mt,columns=('amount','issue','due','serial','bank','status'),show='headings',height=7,selectmode='browse')
        for k,l,w in [('amount','مبلغ',125),('issue','صدور',100),('due','سررسید',100),('serial','صیادی',125),('bank','بانک',110),('status','وضعیت',110)]:self.multi_cheque_tree.heading(k,text=l);self.multi_cheque_tree.column(k,width=w,anchor='center',stretch=True)
        mvs=ttk.Scrollbar(mt,orient='vertical',command=self.multi_cheque_tree.yview);mhs=ttk.Scrollbar(mt,orient='horizontal',command=self.multi_cheque_tree.xview);self.multi_cheque_vscroll=mvs;self.multi_cheque_hscroll=mhs;self.multi_cheque_tree.configure(yscrollcommand=mvs.set,xscrollcommand=mhs.set);self.multi_cheque_tree.grid(row=0,column=0,sticky='nsew');mvs.grid(row=0,column=1,sticky='ns');mhs.grid(row=1,column=0,sticky='ew');self.multi_cheque_tree.bind('<Double-1>',lambda e:self._copy_multi_cheque())
        tk.Button(self.cheque_frame,text='↳ انتقال چک انتخابی به فرم بالا',command=self._copy_multi_cheque,bg=DARK['glass'],fg='white',relief='flat',padx=9,pady=4).grid(row=11,column=0,columnspan=2,sticky='e',padx=5,pady=(0,5))

        ph=tk.LabelFrame(body,text='طبقه‌بندی فاز',bg=DARK['panel'],fg='#7FC9FF',font=('Segoe UI',9,'bold'));ph.pack(fill='x',padx=8,pady=6);ph.grid_columnconfigure((0,1),weight=1);self._field(ph,'main_phase','فاز اصلی','phase',0,1,34);self._field(ph,'sub_phase','فاز فرعی','subphase',0,0,34)
        self.phase_hint=tk.StringVar(value='');tk.Label(ph,textvariable=self.phase_hint,bg=DARK['panel'],fg=DARK['cyan'],font=('Segoe UI',7,'bold'),wraplength=540,justify='right').grid(row=1,column=0,columnspan=2,sticky='ew',padx=5,pady=4)
        tk.Button(ph,text='🧠 پیشنهاد مجدد فاز از روی شرح + فازهای فعال',command=self.recommend_phase,bg=DARK['glass'],fg='white',relief='flat',padx=8,pady=4).grid(row=2,column=0,columnspan=2,sticky='e',padx=5,pady=(0,5))
        tk.Label(body,text='راهنما: اسکرول ماوس، PageUp و PageDown روی کل فرم فعال است؛ دکمه‌های تأیید همیشه پایین پنجره ثابت می‌مانند.',bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',7)).pack(fill='x',padx=10,pady=(2,10))

    def _form_wheel(self,e):
        # Keep image/tree scrolling local; everywhere else scroll the complete form.
        try:
            if e.widget is self.canvas or str(e.widget).startswith(str(self.canvas)): return
            if e.widget is self.multi_cheque_tree: return
            self.form_canvas.yview_scroll(int(-e.delta/120),'units')
        except Exception: pass

    def _load(self):
        super()._load(); p=self.payload
        st=_normalize_cheque_status(p.get('cheque_status') or p.get('status') or 'ISSUED'); self.vars['cheque_status'].set(CHEQUE_STATUS_FA.get(st,'صادرشده'))
        self.vars['cheque_status_event_date_shamsi'].set(str(p.get('cheque_status_event_date_shamsi') or p.get('cashed_date_shamsi') or p.get('event_date_shamsi') or ''))
        # Base loader did not have the lifecycle column; rebuild multi rows with it.
        if self._multi_cheques:
            for x in self.multi_cheque_tree.get_children():self.multi_cheque_tree.delete(x)
            for i,c in enumerate(self._multi_cheques):
                stc=_normalize_cheque_status(c.get('status') or c.get('cheque_status') or 'ISSUED')
                self.multi_cheque_tree.insert('', 'end',iid=str(i),values=(fmt_money(c.get('amount')),c.get('issue_date_shamsi') or '-',c.get('due_date_shamsi') or '-',c.get('cheque_serial') or '-',c.get('issuer_bank') or c.get('bank_name') or '-',CHEQUE_STATUS_FA.get(stc,stc)))
        conf=p.get('phase_suggestion_confidence');reason=p.get('phase_suggestion_reason')
        if conf:self.phase_hint.set(f"پیشنهاد هوشمند فاز: اطمینان {fa(f'{float(conf)*100:.0f}')}٪ — {reason or ''}")
        elif not self.vars['main_phase'].get().strip():self.recommend_phase(save=False)
        self.form_canvas.yview_moveto(0)

    def _copy_multi_cheque(self):
        s=self.multi_cheque_tree.selection()
        if not s:return
        try:c=self._multi_cheques[int(s[0])]
        except Exception:return
        super()._copy_multi_cheque();st=_normalize_cheque_status(c.get('status') or c.get('cheque_status') or 'ISSUED');self.vars['cheque_status'].set(CHEQUE_STATUS_FA.get(st,'صادرشده'));self.vars['cheque_status_event_date_shamsi'].set(str(c.get('cheque_status_event_date_shamsi') or c.get('cashed_date_shamsi') or ''))

    def recommend_phase(self,save=False):
        raw=str(self.vars.get('description').get() if self.vars.get('description') else '') or str(self.row.get('raw_text') or _raw_text_for_pending(self.pid) or '')
        p,s,changed=_apply_phase_hint(self.payload,raw,self.rich,force=True)
        if not s:self.phase_hint.set('پیشنهاد هوشمند فاز: تشخیص مطمئن نیست؛ انتخاب دستی لازم است.');return
        self.vars['main_phase'].set(p.get('main_phase') or '');self.vars['sub_phase'].set(p.get('sub_phase') or '');self._update_sub_values();self.phase_hint.set(f"پیشنهاد هوشمند: {p.get('main_phase')} ← {p.get('sub_phase') or 'بدون ریزفعالیت'} | {fa(f'{s.confidence*100:.0f}')}٪ — {s.reason}")
        self.payload.update({k:v for k,v in p.items() if k.startswith('phase_') or k in {'main_phase','sub_phase','construction_stage','expense_category'}})
        if save and changed:APPROVAL.save_payload(self.pid,self.payload,learn=False)

    def payload_from_form(self):
        p=super().payload_from_form();p['cheque_status']=_normalize_cheque_status(self.vars['cheque_status'].get());p['cheque_status_event_date_shamsi']=self.vars['cheque_status_event_date_shamsi'].get().strip();return p

    def approve(self):
        try:self.payload=self.payload_from_form();APPROVAL.save_payload(self.pid,self.payload,learn=True);msg=approve_v175(self.pid,self.payload,self.rich);messagebox.showinfo('ثبت',msg,parent=self);self.on_done();self.destroy()
        except Exception as exc:messagebox.showerror('تأیید انجام نشد',str(exc),parent=self)


# ---------------------------------------------------------------------------
# Data Entry center: explicit multi-select actions + phase routing
# ---------------------------------------------------------------------------
class DataEntryCenter175(v174.DataEntryCenter17):
    def __init__(self,parent,rich,on_posted=None):
        self._phase_seen=set();super().__init__(parent,rich,on_posted)

    def _build(self):
        top=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);top.pack(fill='x',pady=(0,6))
        tk.Label(top,text='ثبت دیتا',bg=DARK['surface'],fg=DARK['text'],font=('Segoe UI',12,'bold')).pack(side='right',padx=(10,3),pady=8)
        tk.Label(top,text='مرکز بررسی، اصلاح و تأیید — هیچ اثر مالی قبل از تأیید نهایی ندارد',bg=DARK['surface'],fg=DARK['muted'],font=('Segoe UI',7)).pack(side='right',padx=5)
        self.bot=tk.StringVar(value='ربات: در حال بررسی...');tk.Label(top,textvariable=self.bot,bg=DARK['surface'],fg=DARK['green'],font=('Segoe UI',8,'bold')).pack(side='left',padx=8)

        tools=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);tools.pack(fill='x',pady=(0,6));self.filter=tk.StringVar(value='Pending')
        for key,label,col in [('همه','همه',DARK['glass']),('Pending','در انتظار',DARK['orange']),('تأییدشده','تأییدشده',DARK['green']),('ردشده','ردشده',DARK['red'])]:
            b=tk.Button(tools,text=label,command=lambda k=key:self._set_status(k),bg=DARK['glass'],fg='white',relief='flat',font=('Segoe UI',8,'bold'),padx=12,pady=6);b.pack(side='right',padx=3,pady=4);self.status_buttons[key]=(b,col)
        # Requested actions are intentionally large/visible; they no longer hide in
        # the generic table toolbar on smaller laptop displays.
        tk.Button(tools,text='☑ انتخاب همه',command=lambda:self.table.select_all(),bg=DARK['glass'],fg='white',relief='flat',padx=9,pady=5).pack(side='left',padx=2)
        tk.Button(tools,text='✅ تأیید انتخاب‌ها',command=self.batch_approve,bg='#17683E',fg='white',relief='flat',padx=9,pady=5).pack(side='left',padx=2)
        tk.Button(tools,text='❌ رد انتخاب‌ها',command=self.batch_reject,bg='#6B3138',fg='white',relief='flat',padx=9,pady=5).pack(side='left',padx=2)
        tk.Button(tools,text='🗑 حذف انتخاب‌ها',command=self.batch_delete,bg='#52333A',fg='white',relief='flat',padx=9,pady=5).pack(side='left',padx=2)
        tk.Button(tools,text='➕ هزینه دستی',command=self.manual_expense,bg=DARK['blue'],fg='white',relief='flat',padx=9,pady=5).pack(side='left',padx=2)
        ttk.Button(tools,text='🔄',command=self.refresh,style='Toolbar.TButton').pack(side='left',padx=2)
        more=tk.Menubutton(tools,text='⋯ ابزار',bg=DARK['glass'],fg='white',relief='flat',padx=8,pady=5);menu=tk.Menu(more,tearoff=False);menu.add_command(label='تحلیل AI انتخاب‌ها',command=self.analyze_selected);menu.add_command(label='تجمیع رسیدهای انتخابی',command=self.merge_selected);menu.add_command(label='پاک‌سازی تعیین‌تکلیف‌شده',command=self.clear_finished);menu.add_command(label='وضعیت اتصال',command=self.status_dialog);more.configure(menu=menu);more.pack(side='left',padx=2)

        self.selection_info=tk.StringVar(value='برای انتخاب چند سطر: Ctrl/Shift + کلیک');tk.Label(self,textvariable=self.selection_info,bg=DARK['bg'],fg=DARK['muted'],font=('Segoe UI',7),anchor='e').pack(fill='x',pady=(0,3))
        pane=ttk.Panedwindow(self,orient='horizontal');pane.pack(fill='both',expand=True);left=tk.Frame(pane,bg=DARK['panel']);right=tk.Frame(pane,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);pane.add(left,weight=7);pane.add(right,weight=3)
        self.table=SmartTable(left,[('doc','سند',55),('date','تاریخ',105),('type','نوع',90),('text','متن کاربر / بابت',300),('amount','مبلغ AI',125),('phase','فاز اصلی',185),('sub','فاز فرعی',185),('pay','پرداخت',105),('conf','AI',65),('status','وضعیت',95)],title='رکوردهای ثبت دیتا — چندانتخاب فعال است');self.table.pack(fill='both',expand=True);self.table.tree.bind('<<TreeviewSelect>>',self._select,add='+');self.table.tree.bind('<<TreeviewSelect>>',lambda e:self._update_selection_info(),add='+');self.table.tree.bind('<Double-1>',lambda e:self.open_editor(),add='+');self.table.set_edit_handler(lambda r:self.open_editor(r));self.table.set_delete_handler(self._delete_row)

        rb=tk.Frame(right,bg=DARK['panel']);rb.pack(fill='x',padx=7,pady=7);tk.Label(rb,text='پیش‌نمایش سند + متن',bg=DARK['panel'],fg='#7FC9FF',font=('Segoe UI',9,'bold')).pack(side='right');tk.Button(rb,text='✅ تأیید سریع',command=self.quick_approve,bg=DARK['green'],fg='white',relief='flat',padx=8,pady=5).pack(side='left');tk.Button(rb,text='✏️ اصلاح و تأیید',command=self.open_editor,bg=DARK['blue'],fg='white',relief='flat',padx=8,pady=5).pack(side='left',padx=3)
        pv=tk.Frame(right,bg='#07101B');pv.pack(fill='both',expand=True,padx=7);pv.grid_rowconfigure(0,weight=1);pv.grid_columnconfigure(0,weight=1);self.preview=tk.Canvas(pv,bg='#07101B',highlightthickness=0,height=300);pys=ttk.Scrollbar(pv,orient='vertical',command=self.preview.yview);pxs=ttk.Scrollbar(pv,orient='horizontal',command=self.preview.xview);self.preview.configure(yscrollcommand=pys.set,xscrollcommand=pxs.set);self.preview.grid(row=0,column=0,sticky='nsew');pys.grid(row=0,column=1,sticky='ns');pxs.grid(row=1,column=0,sticky='ew');self.preview.bind('<MouseWheel>',self._wheel);self.preview.bind('<ButtonPress-1>',lambda e:self.preview.scan_mark(e.x,e.y));self.preview.bind('<B1-Motion>',lambda e:self.preview.scan_dragto(e.x,e.y,gain=1))
        zb=tk.Frame(right,bg=DARK['panel']);zb.pack(fill='x',padx=7);tk.Button(zb,text='Fit',command=self._fit,bg=DARK['glass'],fg='white',relief='flat').pack(side='left',padx=2,pady=3);tk.Button(zb,text='+',command=lambda:self._set_zoom(self.zoom*1.2),bg=DARK['glass'],fg='white',relief='flat').pack(side='left');tk.Button(zb,text='−',command=lambda:self._set_zoom(self.zoom/1.2),bg=DARK['glass'],fg='white',relief='flat').pack(side='left',padx=2)
        tf=tk.Frame(right,bg=DARK['panel']);tf.pack(fill='x',padx=7,pady=7);self.text=tk.Text(tf,height=10,wrap='word',bg='#091726',fg=DARK['text'],relief='flat',font=('Segoe UI',8),padx=7,pady=7);ts=ttk.Scrollbar(tf,orient='vertical',command=self.text.yview);self.text.configure(yscrollcommand=ts.set);self.text.pack(side='left',fill='both',expand=True);ts.pack(side='right',fill='y');self.text.configure(state='disabled');self.action=tk.StringVar();tk.Label(right,textvariable=self.action,bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',8),wraplength=340,justify='right').pack(fill='x',padx=7,pady=(0,7));self._update_status_buttons();self.after(4000,self._periodic)

    def _update_selection_info(self):
        n=len(self.table.selected_rows());self.selection_info.set(f'{fa(n)} سطر انتخاب شده — Ctrl/Shift + کلیک برای چندانتخاب' if n else 'برای انتخاب چند سطر: Ctrl/Shift + کلیک؛ یا «انتخاب همه»')

    def _auto_phase_suggestions(self):
        # Process each pending record at most once per session.  The selected phase is
        # merely a proposal in the pending payload; final posting still needs approval.
        try: rows=APPROVAL.list_reviews(limit=500)
        except Exception:return
        processed=0
        for r in rows:
            if processed>=30:break
            pid=str(r.get('pending_id') or '')
            if not pid or pid in self._phase_seen:continue
            self._phase_seen.add(pid);p=dict(r.get('payload') or {})
            if str(p.get('detected_type') or '').upper()!='EXPENSE':continue
            if str(p.get('main_phase') or p.get('construction_stage') or '').strip():continue
            raw=str(r.get('raw_text') or p.get('description') or '')
            np,s,changed=_apply_phase_hint(p,raw,self.rich,force=False);processed+=1
            if changed and s and s.confidence>=0.57:
                try:APPROVAL.save_payload(pid,np,learn=False)
                except Exception:pass

    def refresh(self):
        self._auto_phase_suggestions();super().refresh();self._update_selection_info()

    def open_editor(self,row=None):
        row=row or self.current
        if not row:return messagebox.showwarning('ثبت دیتا','یک سطر را انتخاب کن.',parent=self)
        UnifiedPendingEditor175(self,row,self.rich,self.refresh)

    def quick_approve(self):
        if not self.current:return
        if self.current.get('status') in {'APPROVED','REJECTED'}:return messagebox.showinfo('ثبت دیتا','این رکورد قبلاً تعیین تکلیف شده است.',parent=self)
        p=dict(self.current.get('payload') or {})
        if not messagebox.askyesno('تأیید سریع',f"{TYPE_FA.get(str(p.get('detected_type') or 'UNKNOWN').upper(),'نامشخص')} | {fmt_money(p.get('amount') or p.get('final_amount') or 0)}\n\nتأیید شود؟",parent=self):return
        try:msg=approve_v175(self.current['pending_id'],p,self.rich);self.action.set(msg);self.refresh();self.on_posted and self.on_posted()
        except Exception as exc:messagebox.showerror('تأیید',str(exc),parent=self)

    def _selected_pending(self):return [r for r in self.table.selected_rows() if r]
    def batch_approve(self):
        rows=[r for r in self._selected_pending() if r.get('status') not in {'APPROVED','REJECTED'}]
        if not rows:return messagebox.showinfo('تأیید گروهی','ردیف Pending انتخاب نشده است.',parent=self)
        if not messagebox.askyesno('تأیید گروهی',f'{fa(len(rows))} ردیف تأیید نهایی شود؟',parent=self):return
        ok=0;errs=[]
        for r in rows:
            try:approve_v175(str(r['pending_id']),dict(r.get('payload') or {}),self.rich);ok+=1
            except Exception as exc:errs.append(f"{r.get('pending_id')}: {exc}")
        self.refresh();self.on_posted and self.on_posted();self.action.set(f'{fa(ok)} تأیید شد | {fa(len(errs))} خطا')
        if errs:messagebox.showwarning('تأیید گروهی','\n'.join(errs[:8]),parent=self)
    def batch_reject(self):
        rows=[r for r in self._selected_pending() if r.get('status') not in {'APPROVED','REJECTED'}]
        if not rows:return messagebox.showinfo('رد گروهی','ردیف Pending انتخاب نشده است.',parent=self)
        if not messagebox.askyesno('رد گروهی',f'{fa(len(rows))} ردیف رد شود؟ هیچ اثر مالی ایجاد نمی‌شود.',parent=self):return
        ok=0
        for r in rows:
            try:APPROVAL.reject(str(r['pending_id']),actor_id='GUI_17_5_BULK');ok+=1
            except Exception:pass
        self.refresh();self.action.set(f'{fa(ok)} ردیف رد شد')
    def batch_delete(self):
        rows=self._selected_pending()
        if not rows:return messagebox.showinfo('حذف گروهی','هیچ ردیفی انتخاب نشده است.',parent=self)
        if not messagebox.askyesno('حذف گروهی',f'{fa(len(rows))} ردیف از نمای ثبت دیتا حذف/مخفی شود؟\nاطلاعات مالی تأییدشده و Audit پاک نمی‌شوند.',parent=self):return
        ids=[]
        for r in rows:
            pid=str(r.get('pending_id') or '')
            if not pid:continue
            if r.get('status') not in {'APPROVED','REJECTED'}:
                try:APPROVAL.reject(pid,actor_id='GUI_17_5_BULK_DELETE')
                except Exception:pass
            ids.append(pid)
        if ids:self.rich.hide_review(ids)
        self.refresh();self.action.set(f'{fa(len(ids))} ردیف از نما حذف شد')
    def manual_expense(self):ManualExpenseDialog175(self,self.rich,self._manual_saved)
    def _manual_saved(self,pid):
        self.filter.set('Pending');self.refresh();self.action.set('هزینه دستی وارد Pending شد و فاز پیشنهادی اعمال شد.')
        row=next((r for r in self.rows if str(r.get('pending_id'))==str(pid)),None)
        if row: self.current=row;UnifiedPendingEditor175(self,row,self.rich,self.refresh)


# ---------------------------------------------------------------------------
# Cheque edit dialog with lifecycle selector
# ---------------------------------------------------------------------------
class ChequeEditDialog175(tk.Toplevel):
    def __init__(self,parent,row,on_refresh):
        super().__init__(parent);self.row=dict(row);self.on_refresh=on_refresh;self.vars={};std_window(self,'مشخصات و وضعیت چک','800x760',(660,600))
        body=tk.Frame(self,bg=DARK['bg']);body.pack(fill='both',expand=True,padx=12,pady=12)
        card=tk.Frame(body,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);card.pack(fill='both',expand=True,padx=2,pady=2);card.grid_columnconfigure(0,weight=1)
        mode=str(row.get('settlement_mode') or '').upper()
        life=('RETURNED_ON_SETTLEMENT' if mode=='RETURNED_ON_SETTLEMENT' else
              'VOIDED' if mode=='VOIDED' or str(row.get('status') or '').upper()=='CANCELLED' else
              str(row.get('status') or 'ISSUED').upper())
        vals={'issue':row.get('issue_date_shamsi') or '','due':row.get('due_date_shamsi') or '','amount':group_int(row.get('amount') or 0),'issuer_name':row.get('issuer_name') or '','receiver_name':row.get('receiver_name') or '','issuer_bank':row.get('issuer_bank') or '','cheque_serial':row.get('cheque_serial') or '','description':row.get('description') or '','cheque_type':CHEQUE_TYPE_FA.get(str(row.get('cheque_type') or 'PHYSICAL').upper(),'فیزیکی'),'registration_state':REG_FA.get(str(row.get('registration_state') or 'UNREGISTERED').upper(),'ثبت‌نشده'),'lifecycle':CHEQUE_STATUS_FA.get(life,'صادرشده'),'return_disposition':row.get('return_disposition') or CHEQUE_RETURN_DISPOSITIONS_175[3],'return_account_holder':row.get('return_account_holder') or '','void_reason':row.get('void_reason') or '','status_date':row.get('cashed_date_shamsi') or row.get('due_date_shamsi') or gregorian_to_shamsi(datetime.now().date())}
        fields=[('issue','تاریخ صدور','date'),('due','تاریخ سررسید','date'),('amount','مبلغ','num'),('issuer_name','صاحب حساب','entry'),('receiver_name','گیرنده','entry'),('issuer_bank','بانک','entry'),('cheque_serial','شماره/صیادی','entry'),('cheque_type','نوع چک','type'),('registration_state','وضعیت ثبت چک','reg'),('lifecycle','وضعیت چک','life'),('return_disposition','وضعیت عودت چک','return'),('return_account_holder','صاحب حساب معرفی‌شده','entry'),('void_reason','دلیل ابطال چک','entry'),('status_date','تاریخ رویداد وضعیت','date'),('description','بابت','entry')]
        self._status_widgets={}
        for i,(k,l,kind) in enumerate(fields):
            v=tk.StringVar(value=str(vals[k]));self.vars[k]=v;label=tk.Label(card,text=l+':',bg=DARK['panel'],fg=DARK['muted']);label.grid(row=i,column=1,sticky='e',padx=8,pady=5)
            if kind=='date':w=DateField(card,v,width=32)
            elif kind=='type':w=ttk.Combobox(card,textvariable=v,state='readonly',values=list(CHEQUE_TYPE_BY_FA),width=34)
            elif kind=='reg':w=ttk.Combobox(card,textvariable=v,state='readonly',values=list(REG_BY_FA),width=34)
            elif kind=='life':w=ttk.Combobox(card,textvariable=v,state='readonly',values=list(CHEQUE_STATUS_BY_FA),width=34)
            elif kind=='return':w=ttk.Combobox(card,textvariable=v,state='readonly',values=CHEQUE_RETURN_DISPOSITIONS_175,width=34)
            else:w=ttk.Entry(card,textvariable=v,width=36,justify='right');bind_grouped_number(w,v) if kind=='num' else None
            w.grid(row=i,column=0,padx=8,pady=5,sticky='ew')
            if k in {'return_disposition','return_account_holder','void_reason'}:self._status_widgets[k]=(label,w)
        self.guarantee=tk.BooleanVar(value=bool(row.get('is_guarantee')));tk.Checkbutton(card,text='بابت ضمانت (در تعهد مالی محاسبه نشود)',variable=self.guarantee,bg=DARK['panel'],fg=DARK['text'],selectcolor=DARK['surface'],activebackground=DARK['panel'],activeforeground='white').grid(row=len(fields),column=0,columnspan=2,sticky='e',pady=7,padx=8)
        self.vars['lifecycle'].trace_add('write',lambda *_args:self._sync_special_status_fields())
        self._sync_special_status_fields()
        tk.Label(card,text='ویرایش وضعیت فقط در صورت تطابق با رکورد ثبت‌شده انجام می‌شود؛ تغییر وضعیت اثر مالی تازه ایجاد نمی‌کند.',bg=DARK['panel2'],fg=DARK['cyan'],font=('Segoe UI',7,'bold'),padx=8,pady=7,wraplength=620,justify='right').grid(row=len(fields)+1,column=0,columnspan=2,sticky='ew',padx=8,pady=5)
        tk.Button(card,text='💾 ذخیره مشخصات و وضعیت',command=self.save,bg=DARK['green'],fg='white',relief='flat',padx=18,pady=8,font=('Segoe UI',9,'bold')).grid(row=len(fields)+2,column=0,columnspan=2,pady=12)
    def save(self):
        try:
            ish=normalize_shamsi(self.vars['issue'].get());due=normalize_shamsi(self.vars['due'].get())
            if not ish or not due:raise ValueError('تاریخ صدور/سررسید نامعتبر است.')
            new_status=CHEQUE_STATUS_BY_FA.get(self.vars['lifecycle'].get(),'ISSUED')
            registration=REG_BY_FA.get(self.vars['registration_state'].get(),'UNREGISTERED')
            if new_status == 'RETURNED_ON_SETTLEMENT' and not self.vars['return_account_holder'].get().strip():
                raise ValueError('نام صاحب حساب معرفی‌شده را وارد کن.')
            if new_status == 'VOIDED':
                if not self.vars['void_reason'].get().strip():
                    raise ValueError('دلیل ابطال چک را وارد کن.')
                if self.vars['return_disposition'].get() not in CHEQUE_RETURN_DISPOSITIONS_175:
                    raise ValueError('وضعیت عودت چک را انتخاب کن.')
            conflict=_registered_cheque_state_conflict175(self.row,new_status,registration)
            if conflict:
                should_edit,_=_choose_cheque_mismatch_action175(self,conflict)
                if should_edit:
                    parent=self.master
                    self.destroy()
                    parent.after(0,lambda target=parent,item=conflict:_open_cheque_source_wizard175(target,item))
                return
            old_status=str(self.row.get('status') or 'ISSUED').upper()
            if old_status not in {'CASHED','CANCELLED'}:
                DB.update_cheque_details(self.row['cheque_id'],amount=parse_int(self.vars['amount'].get()),issue_date=shamsi_to_gregorian(ish),issue_date_shamsi=ish,due_date=shamsi_to_gregorian(due),due_date_shamsi=due,issuer_name=self.vars['issuer_name'].get().strip(),cheque_type=CHEQUE_TYPE_BY_FA.get(self.vars['cheque_type'].get(),'PHYSICAL'),receiver_name=self.vars['receiver_name'].get().strip(),issuer_bank=self.vars['issuer_bank'].get().strip(),cheque_serial=self.vars['cheque_serial'].get().strip(),description=self.vars['description'].get().strip(),is_guarantee=self.guarantee.get(),source='GUI_17_5',actor_id='GUI')
            DB.update_cheque_workflow_state(
                self.row['cheque_id'], lifecycle=new_status, registration_state=registration,
                return_disposition=(self.vars['return_disposition'].get()
                                    if new_status in {'RETURNED_ON_SETTLEMENT','VOIDED'} else None),
                return_account_holder=(self.vars['return_account_holder'].get().strip()
                                       if new_status=='RETURNED_ON_SETTLEMENT' else None),
                void_reason=(self.vars['void_reason'].get().strip() if new_status=='VOIDED' else None),
                source='GUI_17_5',actor_id='GUI')
            self.destroy();self.on_refresh()
        except Exception as exc:messagebox.showerror('چک',str(exc),parent=self)

    def _sync_special_status_fields(self):
        status=CHEQUE_STATUS_BY_FA.get(self.vars['lifecycle'].get(),'ISSUED')
        show={
            'return_disposition':status in {'RETURNED_ON_SETTLEMENT','VOIDED'},
            'return_account_holder':status=='RETURNED_ON_SETTLEMENT',
            'void_reason':status=='VOIDED',
        }
        for key,(label,widget) in self._status_widgets.items():
            if show.get(key,False):
                label.grid();widget.grid()
            else:
                label.grid_remove();widget.grid_remove()


# ---------------------------------------------------------------------------
# Main dashboard 17.5
# ---------------------------------------------------------------------------
class Stage175Dashboard(v174.Stage17Dashboard):
    def __init__(self):
        self.nav_buttons={};self.navbar=None
        super().__init__();self.title('BARKAV — Engineering & Construction — Version 17.5')

    def _style(self):
        # Do not call the old style and then barely change it; 17.5 owns a complete
        # visual theme so every inherited tab has the same background/contrast.
        # SmartTable in the V15/V16 backbone reads the shared dashboard_stage12
        # palette directly, therefore update that palette *before* inherited tables
        # are created.  This prevents old light rows from leaking into the dark UI.
        try:
            v16.d12.COLORS.update({
                'bg': DARK['bg'], 'panel': DARK['panel'], 'soft': '#0D1927',
                'rowblue': '#101F30', 'text': DARK['text'], 'muted': DARK['muted'],
                'line': DARK['line'], 'navy': '#8FD1FF', 'blue': DARK['blue'],
                'cyan': DARK['cyan'], 'green': DARK['green'], 'yellow': DARK['yellow'],
                'orange': DARK['orange'], 'red': DARK['red'],
            })
        except Exception:
            pass
        st=ttk.Style(self)
        try:st.theme_use('clam')
        except Exception:pass
        st.configure('.',font=('Segoe UI',8),background=DARK['bg'],foreground=DARK['text'])
        st.configure('TFrame',background=DARK['bg']);st.configure('Panel.TFrame',background=DARK['panel']);st.configure('TLabel',background=DARK['bg'],foreground=DARK['text'])
        st.configure('TButton',padding=(8,6),background=DARK['glass'],foreground=DARK['text'],bordercolor=DARK['line'],relief='flat');st.map('TButton',background=[('active','#24415E'),('pressed','#176FD1')],foreground=[('disabled','#647589')])
        st.configure('Primary.TButton',background=DARK['blue'],foreground='white',font=('Segoe UI',8,'bold'));st.map('Primary.TButton',background=[('active','#3A9BFF')])
        st.configure('Toolbar.TButton',padding=(6,3),font=('Segoe UI',7),background='#19293C');st.configure('Compact.TButton',padding=(5,3),font=('Segoe UI',7),background='#19293C');st.configure('Danger.TButton',background=DARK['red'],foreground='white')
        st.configure('TEntry',fieldbackground='#0B1724',foreground=DARK['text'],insertcolor='white',bordercolor=DARK['line'],padding=4);st.configure('Compact.TEntry',fieldbackground='#0B1724',foreground=DARK['text'])
        st.configure('TCombobox',fieldbackground='#0B1724',background='#0B1724',foreground=DARK['text'],arrowcolor=DARK['text'],bordercolor=DARK['line'],padding=3);st.map('TCombobox',fieldbackground=[('readonly','#0B1724')],foreground=[('readonly',DARK['text'])])
        st.configure('TScrollbar',background='#1A2A3D',troughcolor='#08111C',bordercolor=DARK['line'],arrowcolor='#AFC0D2',darkcolor='#1A2A3D',lightcolor='#1A2A3D',relief='flat');st.map('TScrollbar',background=[('active','#2A4665'),('pressed',DARK['blue'])])
        st.configure('TPanedwindow',background=DARK['bg']);st.configure('TCheckbutton',background=DARK['panel'],foreground=DARK['text'])
        st.configure('TLabelframe',background=DARK['panel'],bordercolor=DARK['line'],relief='solid',borderwidth=1);st.configure('TLabelframe.Label',background=DARK['panel'],foreground='#8FD1FF',font=('Segoe UI',8,'bold'))
        st.configure('Dashboard.TLabelframe',background=DARK['panel'],bordercolor=DARK['line']);st.configure('Dashboard.TLabelframe.Label',background=DARK['panel'],foreground='#8FD1FF',font=('Segoe UI',9,'bold'))
        st.configure('Report.TLabelframe',background=DARK['panel'],bordercolor=DARK['line']);st.configure('Report.TLabelframe.Label',background=DARK['panel'],foreground='#8FD1FF',font=('Segoe UI',8,'bold'))
        st.configure('Section.TLabel',background=DARK['bg'],foreground='#8FD1FF',font=('Segoe UI',9,'bold'));st.configure('Summary.TLabel',background=DARK['surface'],foreground=DARK['text'],font=('Segoe UI',8,'bold'),padding=(6,3))
        st.configure('Treeview',rowheight=29,background='#0D1927',fieldbackground='#0D1927',foreground='#EAF2FB',bordercolor=DARK['line'],font=('Segoe UI',8));st.configure('Treeview.Heading',background='#1A2A3E',foreground='#F4F8FC',font=('Segoe UI',7,'bold'),padding=(4,6));st.map('Treeview',background=[('selected','#1F6EAD')],foreground=[('selected','#FFFFFF')])
        # Hide native Notebook tabs; the large raised navigation bar below is the
        # single source of navigation styling, matching the approved mock-up.
        try:st.layout('Hidden.TNotebook.Tab',[])
        except Exception:pass
        st.configure('Hidden.TNotebook',background=DARK['bg'],borderwidth=0,tabmargins=0)

    def _build(self):
        self.configure(bg=DARK['bg'])
        top=tk.Frame(self,bg='#0D1622',height=68,highlightbackground='#25384D',highlightthickness=1);top.pack(fill='x');top.pack_propagate(False)
        brand=tk.Frame(top,bg='#0D1622');brand.pack(side='left',padx=12,pady=7);logo=BASE_DIR/'assets'/'barkav_brand_header.png';loaded=False
        if logo.exists() and Image is not None:
            try:
                im=Image.open(logo).convert('RGB');im.thumbnail((185,48));self._logo_img=ImageTk.PhotoImage(im);lab=tk.Label(brand,image=self._logo_img,bg='white',bd=0,padx=3,pady=2);lab.pack(side='left');loaded=True
            except Exception:pass
        if not loaded:
            bt=tk.Frame(brand,bg='#0D1622');bt.pack(side='left');tk.Label(bt,text='BARKAV',bg='#0D1622',fg='white',font=('Arial',15,'bold')).pack(anchor='w');tk.Label(bt,text='ENGINEERING & CONSTRUCTION',bg='#0D1622',fg='#91A5BB',font=('Arial',7)).pack(anchor='w')
        tk.Label(brand,text='17.5',bg='#172536',fg='#8FD1FF',font=('Segoe UI',7,'bold'),padx=7,pady=3).pack(side='left',padx=8)

        project=tk.Frame(top,bg='#111E2C',highlightbackground=DARK['line'],highlightthickness=1);project.pack(side='right',padx=10,pady=8)
        self.project_name_top=tk.StringVar(value='پروژه');self.datetime_top=tk.StringVar(value='')
        tk.Label(project,textvariable=self.project_name_top,bg='#111E2C',fg='#CBE8FF',font=('Segoe UI',8,'bold')).pack(side='right',padx=(10,6),pady=5)
        tk.Button(project,text='✎',command=self.edit_project_settings,bg='#1A2A3D',fg='white',activebackground=DARK['blue'],relief='flat',font=('Segoe UI',8,'bold'),width=3).pack(side='right',padx=2,pady=3)
        tk.Label(project,textvariable=self.datetime_top,bg='#111E2C',fg=DARK['muted'],font=('Segoe UI',7)).pack(side='right',padx=8)

        tools=tk.Frame(top,bg='#0D1622');tools.pack(side='right',padx=4,pady=8)
        defs=[('💾','ذخیره',self.manual_save,'بکاپ دستی دیتابیس'),('📦','بسته توسعه',self.export_development_package,'خروجی امن Handoff و کدهای توسعه'),('↶','Undo',self.undo,'بازگشت آخرین اصلاح'),('↷','Redo',self.redo,'اجرای دوباره'),('🔄','بروزرسانی',self.refresh_all,'بروزرسانی همه داده‌ها'),('⚙','سیستم',self.show_health,'وضعیت سرویس‌ها')]
        for icon,label,cmd,tip in defs:
            b=tk.Button(tools,text=f'{icon} {label}',command=cmd,bg='#172536',fg='white',activebackground='#1F6EAD',activeforeground='white',relief='flat',font=('Segoe UI',7),padx=7,pady=5);b.pack(side='right',padx=2);add_tooltip(b,tip)

        self.navbar=tk.Frame(self,bg='#0B131E',height=44,highlightbackground='#25384D',highlightthickness=1);self.navbar.pack(fill='x',padx=6,pady=(5,0));self.navbar.pack_propagate(False)
        self.notebook=ttk.Notebook(self,style='Hidden.TNotebook');self.notebook.pack(fill='both',expand=True,padx=6,pady=(4,6))
        self._build_overview();self._build_manager();self._build_financial();self._build_cheques();self._build_sales();self._build_reconciliation();self._build_reports();self._build_market();self._rebuild_navbar();self.notebook.bind('<<NotebookTabChanged>>',lambda e:self._sync_nav(),add='+');self._attach_common_tooltips(self);self._tick_clock()

    def _rebuild_navbar(self):
        if not self.navbar:return
        for w in self.navbar.winfo_children():w.destroy()
        self.nav_buttons={}
        for tid in self.notebook.tabs():
            txt=self.notebook.tab(tid,'text');b=tk.Button(self.navbar,text=txt,command=lambda t=tid:self.notebook.select(t),bg='#172331',fg='#AFC0D2',activebackground='#24547F',activeforeground='white',relief='flat',bd=0,font=('Segoe UI',8,'bold'),padx=18,pady=7,cursor='hand2');b.pack(side='left',fill='y',padx=(3,0),pady=4);self.nav_buttons[tid]=b
        self._sync_nav()
    def _sync_nav(self):
        try:sel=str(self.notebook.select())
        except Exception:return
        for tid,b in self.nav_buttons.items():
            active=str(tid)==sel;b.configure(bg='#1778D4' if active else '#172331',fg='white' if active else '#AFC0D2',relief='raised' if active else 'flat',bd=1 if active else 0)

    def _build_approval_center(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.approval_tab=tab;self.notebook.insert(1,tab,text='ثبت دیتا');self.approval_center=DataEntryCenter175(tab,self.rich,on_posted=self.refresh_all);self.approval_center.pack(fill='both',expand=True)
        if self._bot_process:self.approval_center.set_bot_process(self._bot_process,self._bot_log)
        self.after_idle(self._rebuild_navbar)

    def _build_overview(self):
        tab=ttk.Frame(self.notebook,padding=4);self.notebook.add(tab,text='داشبورد');wrap=ttk.Frame(tab);wrap.pack(fill='both',expand=True);canvas=tk.Canvas(wrap,bg=DARK['bg'],highlightthickness=0);vs=ttk.Scrollbar(wrap,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=vs.set);canvas.pack(side='left',fill='both',expand=True);vs.pack(side='right',fill='y');inner=tk.Frame(canvas,bg=DARK['bg']);win=canvas.create_window((0,0),window=inner,anchor='nw');inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')));canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width));canvas.bind('<MouseWheel>',lambda e:canvas.yview_scroll(int(-e.delta/120),'units'))
        # Project banner
        proj=tk.Frame(inner,bg='#111D2A',highlightbackground=DARK['line'],highlightthickness=1);proj.pack(fill='x',padx=4,pady=(3,7));self.project_info=tk.StringVar(value='مشخصات پروژه');tk.Label(proj,text='نمای کلی پروژه',bg='#111D2A',fg='#EAF5FF',font=('Segoe UI',11,'bold')).pack(side='right',padx=(10,5),pady=9);tk.Label(proj,textvariable=self.project_info,bg='#111D2A',fg=DARK['muted'],font=('Segoe UI',7),justify='right').pack(side='right',padx=8);tk.Button(proj,text='✎ اصلاح مشخصات پروژه',command=self.edit_project_settings,bg=DARK['glass'],fg='white',relief='flat',padx=10,pady=5).pack(side='left',padx=8)
        self.project_meta_var=tk.StringVar(value='');tk.Label(proj,textvariable=self.project_meta_var,bg='#111D2A',fg='#8FD1FF',font=('Segoe UI',7,'bold')).pack(side='left',padx=6)

        self.cards={};icons=['▣','◫','◈','◎','▤','◉','◇','⌁']
        hero=tk.Frame(inner,bg=DARK['bg']);hero.pack(fill='x',padx=4,pady=4)
        hero_defs=[('cash','تنخواه فعلی',DARK['blue'],'مانده نقدی جاری.'),('cost','هزینه کل ساخت',DARK['green'],'کل هزینه ساخت تحقق‌یافته.'),('free','مانده آزاد',DARK['cyan'],'مانده پس از تعهد چک‌های باز.'),('ch_open_total','چک‌های پاس‌نشده',DARK['red'],'تعهد باز چک‌ها.'),('sales_receivable','مطالبات',DARK['violet'],'کل مانده طلب از خریداران.'),('liq_projected','تراز ۳۰ روز',DARK['orange'],'نقدینگی پیش‌بینی‌شده ۳۰ روز آینده.')]
        for c in range(6):hero.grid_columnconfigure(c,weight=1,uniform='hero')
        for i,(k,t,col,info) in enumerate(hero_defs):card=PremiumMetricCard175(hero,t,col,icons[i],info);card.grid(row=0,column=i,sticky='nsew',padx=3,pady=2);self.cards[k]=card

        # Secondary KPIs retain all V15 information but are visually subordinate.
        secondary=tk.Frame(inner,bg=DARK['bg']);secondary.pack(fill='x',padx=4,pady=(3,5));sec_defs=[
            ('total_in','کل ورودی',DARK['cyan']),('total_out','کل خروجی',DARK['red']),('liq_obligation','تعهد ۳۰ روز',DARK['orange']),('liq_inflow','وصول ۳۰ روز',DARK['green']),
            ('ch_all_total','کل چک‌ها',DARK['blue']),('ch30_count','سررسید ۳۰ روز',DARK['cyan']),('ch30_amount','مبلغ سررسید ۳۰ روز',DARK['orange']),
            ('sales_contract','کل قرارداد فروش',DARK['green']),('sales_received','وصول خریداران',DARK['cyan']),('sales_30','مطالبات ۳۰ روز',DARK['orange']),('sales_overdue','مطالبات معوق',DARK['red']),
            ('loan_principal','اصل تسهیلات',DARK['blue']),('loan_paid','اقساط پرداختی',DARK['cyan']),('loan_remaining','مانده تسهیلات',DARK['red']),('loan_30','اقساط ۳۰ روز',DARK['orange'])]
        for c in range(5):secondary.grid_columnconfigure(c,weight=1,uniform='sec')
        for i,(k,t,col) in enumerate(sec_defs):card=PremiumMetricCard175(secondary,t,col,icons[i%len(icons)],compact=True);card.grid(row=i//5,column=i%5,sticky='nsew',padx=2,pady=2);self.cards[k]=card

        phase=tk.Frame(inner,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);phase.pack(fill='x',padx=4,pady=6);phhead=tk.Frame(phase,bg=DARK['surface']);phhead.pack(fill='x');tk.Label(phhead,text='پیشرفت مراحل پروژه — ۳۲ فاز',bg=DARK['surface'],fg='#EAF5FF',font=('Segoe UI',10,'bold')).pack(side='right',padx=8,pady=(7,3));tk.Label(phhead,text='کلیک: جزئیات  |  دابل‌کلیک: وضعیت و درصد فاز',bg=DARK['surface'],fg=DARK['muted'],font=('Segoe UI',7)).pack(side='left',padx=8)
        self.phase_strip=tk.Frame(phase,bg=DARK['surface']);self.phase_strip.pack(fill='x',padx=7,pady=4);self.phase_buttons={}
        # Grid, rather than pack+fixed width, guarantees that all 32 phases remain
        # visible on a 1280px laptop display. No horizontal dragging is required.
        for col in range(32): self.phase_strip.grid_columnconfigure(col,weight=1,uniform='phase32')
        for i in range(1,33):
            b=tk.Button(self.phase_strip,text=fa(f'{i:02d}'),bg='#172437',fg='#92A4BA',relief='flat',bd=0,font=('Segoe UI',5,'bold'),padx=0,pady=5,command=lambda n=i:self.open_phase_by_no(n))
            b.grid(row=0,column=i-1,sticky='nsew',padx=1);b.bind('<Double-1>',lambda e,n=i:self.edit_phase_progress(n));self.phase_buttons[i]=b
        self.overall_progress=ProjectProgressBar(phase,on_open=lambda:v16.ProjectFinancialOverview(self,self.rich));self.overall_progress.pack(fill='x',padx=7,pady=(4,8))

        charts=tk.Frame(inner,bg=DARK['bg']);charts.pack(fill='x',padx=4,pady=5);charts.grid_columnconfigure(0,weight=1);charts.grid_columnconfigure(1,weight=2);charts.grid_columnconfigure(2,weight=2)
        self.cost_donut=DonutChart175(charts,'ترکیب برآورد فازها',220);self.cost_donut.grid(row=0,column=0,sticky='nsew',padx=3)
        self.liquidity_chart=MiniLineChart(charts,'روند تجمعی برآورد / واقعی / پیش‌بینی',220);self.liquidity_chart.grid(row=0,column=1,sticky='nsew',padx=3)
        self.phase_chart=MiniBarChart(charts,'مقایسه فازها',220);self.phase_chart.grid(row=0,column=2,sticky='nsew',padx=3)

        tables=tk.Frame(inner,bg=DARK['bg']);tables.pack(fill='x',padx=4,pady=5);tables.grid_columnconfigure(0,weight=1);tables.grid_columnconfigure(1,weight=1);tables.grid_columnconfigure(2,weight=1)
        cbox=ttk.LabelFrame(tables,text='چک‌های ۳۰ روز آینده',padding=4);cbox.grid(row=0,column=2,sticky='nsew',padx=3);self.overview_cheque_table=CompactTable(cbox,[('due','سررسید',90),('days','روز',55),('amount','مبلغ',110),('issuer','صاحب حساب',110),('bank','بانک',90),('receiver','گیرنده',110)],height=5);self.overview_cheque_table.pack(fill='both',expand=True)
        sbox=ttk.LabelFrame(tables,text='وصول ۳۰ روز آینده',padding=4);sbox.grid(row=0,column=1,sticky='nsew',padx=3);self.overview_sales_upcoming=CompactTable(sbox,[('buyer','خریدار',120),('unit','واحد',60),('due','سررسید',85),('amount','مانده',105),('days','روز',45)],height=5);self.overview_sales_upcoming.pack(fill='both',expand=True)
        obox=ttk.LabelFrame(tables,text='مطالبات معوق',padding=4);obox.grid(row=0,column=0,sticky='nsew',padx=3);self.overview_sales_overdue=CompactTable(obox,[('buyer','خریدار',120),('unit','واحد',60),('due','سررسید',85),('amount','مانده',105),('days','تأخیر',45)],height=5);self.overview_sales_overdue.pack(fill='both',expand=True)
        lbox=ttk.LabelFrame(inner,text='اقساط تسهیلات پیش‌رو',padding=4);lbox.pack(fill='x',padx=4,pady=5);self.overview_loan_table=CompactTable(lbox,[('lender','بانک',110),('title','عنوان',150),('no','قسط',50),('due','تاریخ',90),('amount','مانده',110),('days','روز',70)],height=3);self.overview_loan_table.pack(fill='x')

        rec=ttk.LabelFrame(inner,text='تطبیق سریع بانک',padding=7);rec.pack(fill='x',padx=4,pady=(5,12));self.bank_var=tk.StringVar();self.bank_date=tk.StringVar();ttk.Label(rec,text='موجودی واقعی:').pack(side='right');be=ttk.Entry(rec,textvariable=self.bank_var,width=18,justify='center');be.pack(side='right',padx=3);bind_grouped_number(be,self.bank_var,allow_negative=True);ttk.Label(rec,text='تاریخ:').pack(side='right',padx=(8,0));DateField(rec,self.bank_date,width=11).pack(side='right',padx=3);ttk.Button(rec,text='ثبت تطبیق',command=self.record_reconciliation,style='Primary.TButton').pack(side='right',padx=4);self.bank_info=tk.StringVar(value='آخرین تطبیق: -');self.bank_info_label=tk.Label(rec,textvariable=self.bank_info,bg=DARK['panel'],fg=DARK['text'],font=('Segoe UI',7,'bold'));self.bank_info_label.pack(side='left',padx=6)

    def _build_cheques(self):
        tab=ttk.Frame(self.notebook,padding=6);self.notebook.add(tab,text='چک‌ها');bar=tk.Frame(tab,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);bar.pack(fill='x',pady=(0,5));tk.Label(bar,text='مدیریت چک‌ها',bg=DARK['surface'],fg=DARK['text'],font=('Segoe UI',10,'bold')).pack(side='right',padx=8,pady=7)
        self.ch_filter=tk.StringVar(value='همه');vals=['همه','ثبت‌نشده','ثبت‌شده','صادرشده','در انتظار سررسید','پاس‌شده','برگشتی','عودتی به شرط تسویه','باطل‌شده','لغوشده','ضمانتی'];c=ttk.Combobox(bar,textvariable=self.ch_filter,state='readonly',values=vals,width=20);c.pack(side='right',padx=4);c.bind('<<ComboboxSelected>>',lambda e:self.refresh_cheques());ttk.Button(bar,text='✏️ ویرایش مشخصات/وضعیت',command=self.edit_cheque).pack(side='right',padx=3);tk.Label(bar,text='هر چک = یک ردیف مستقل؛ حتی اگر چند چک از یک تصویر ثبت شده باشند.',bg=DARK['surface'],fg=DARK['muted'],font=('Segoe UI',7)).pack(side='left',padx=8)
        self.cheque_table=SmartTable(tab,[('issue','تاریخ صدور',100),('due','سررسید',105),('amount','مبلغ',125),('issuer','صاحب حساب',120),('type','نوع',90),('reg','وضعیت ثبت چک',100),('status','وضعیت چک',125),('return_state','وضعیت عودت چک',185),('guarantee','ضمانت',70),('receiver','گیرنده',120),('bank','بانک',100),('serial','شماره/صیادی',120),('desc','بابت',200),('id','Cheque ID',145)],title='چک‌ها — Ctrl/Shift برای چندانتخاب');self.cheque_table.pack(fill='both',expand=True);self.cheque_table.set_edit_handler(self.edit_cheque_row);self.cheque_table.set_delete_handler(self._cancel_cheque_row)

    def refresh_cheques(self):
        rows=SERVICE.list_cheques(open_only=False);f=getattr(self,'ch_filter',tk.StringVar(value='همه')).get();status_filter={'صادرشده':'ISSUED','در انتظار سررسید':'PENDING_DUE','پاس‌شده':'CASHED','برگشتی':'RETURNED','عودتی به شرط تسویه':'RETURNED_ON_SETTLEMENT','باطل‌شده':'VOIDED','لغوشده':'CANCELLED'}
        if f=='ثبت‌نشده':rows=[r for r in rows if str(r.get('registration_state') or 'UNREGISTERED')=='UNREGISTERED']
        elif f=='ثبت‌شده':rows=[r for r in rows if str(r.get('registration_state') or '')=='REGISTERED']
        elif f=='ضمانتی':rows=[r for r in rows if int(r.get('is_guarantee') or 0)==1]
        elif f=='در انتظار سررسید':rows=[r for r in rows if str(r.get('status') or '').upper()=='PENDING_DUE']
        elif f in status_filter:rows=[r for r in rows if _cheque_display_status175(r)==status_filter[f]]
        for r in rows:r['_sum_amount']=int(r.get('amount') or 0)
        self.cheque_table.set_rows(rows,lambda r:_cheque_row_values175(r,self.cheque_table.columns))
    def edit_cheque_row(self,r):ChequeEditDialog175(self,r,self.refresh_all)
    def edit_cheque(self):
        r=self._one(self.cheque_table)
        if r:ChequeEditDialog175(self,r,self.refresh_all)

    def _build_reports(self):
        tab=ttk.Frame(self.notebook,padding=5);self.notebook.add(tab,text='گزارش‌گیری');top=tk.Frame(tab,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);top.pack(fill='x',pady=(0,5));self.report_vars={k:tk.StringVar() for k in ['gross_area','saleable_area','unit_count','inflation','months','presale','end_price','misc','target']}
        tk.Label(top,text='پارامترهای پروژه و پیش‌بینی',bg=DARK['surface'],fg=DARK['text'],font=('Segoe UI',10,'bold')).pack(anchor='e',padx=8,pady=(7,3))
        fields=[('gross_area','متراژ کل/غیرمفید'),('saleable_area','متراژ مفید/فروشی'),('unit_count','تعداد واحدها'),('inflation','تورم ماهانه %'),('months','ماه تا اتمام'),('presale','پیش‌فروش/متر'),('end_price','فروش پایان/متر'),('misc','متفرقه خارج برآورد'),('target','سود هدف %')];self.report_entries={}
        fgrid=tk.Frame(top,bg=DARK['surface']);fgrid.pack(fill='x',padx=6,pady=5)
        for c in range(6):fgrid.grid_columnconfigure(c,weight=1)
        for i,(k,l) in enumerate(fields):
            rr=(i//3)*2;cc=(2-(i%3))*2;tk.Label(fgrid,text=l+':',bg=DARK['surface'],fg=DARK['muted'],font=('Segoe UI',7)).grid(row=rr,column=cc+1,sticky='e',padx=2);e=ttk.Entry(fgrid,textvariable=self.report_vars[k],width=17,justify='right');e.grid(row=rr,column=cc,sticky='ew',padx=3,pady=2);self.report_entries[k]=e
            if k in ('presale','end_price','misc','unit_count'):bind_grouped_number(e,self.report_vars[k])
        self.unit_summary_var=tk.StringVar(value='واحدها: -');tk.Label(fgrid,textvariable=self.unit_summary_var,bg=DARK['surface'],fg='#8FD1FF',font=('Segoe UI',7,'bold')).grid(row=6,column=0,columnspan=6,sticky='e',pady=4)
        act=tk.Frame(top,bg=DARK['surface']);act.pack(fill='x',padx=6,pady=(0,6));tk.Button(act,text='💾 ذخیره پارامترها',command=self.save_report_settings,bg=DARK['blue'],fg='white',relief='flat',padx=9,pady=5).pack(side='right');tk.Button(act,text='🏗 مشخصات پروژه',command=self.edit_project_settings,bg=DARK['glass'],fg='white',relief='flat',padx=9,pady=5).pack(side='right',padx=3);tk.Button(act,text='📥 بارگذاری فایل برآورد',command=self.import_budget,bg=DARK['glass'],fg='white',relief='flat',padx=9,pady=5).pack(side='right',padx=3);tk.Button(act,text='📤 خروجی انتخابی',command=self.export_report_choose,bg=DARK['glass'],fg='white',relief='flat',padx=9,pady=5).pack(side='right',padx=3);self.budget_version=tk.StringVar(value='نسخه برآورد: -');tk.Label(act,textvariable=self.budget_version,bg=DARK['surface'],fg=DARK['muted'],font=('Segoe UI',7)).pack(side='left')
        kgrid=tk.Frame(tab,bg=DARK['bg']);kgrid.pack(fill='x',pady=(0,5));self.report_cards={};defs=[('eac','برآورد نهایی پروژه',DARK['orange'],'Actual + باقی‌مانده برآوردشده تا پایان پروژه.'),('cmp','اختلاف با برآورد اولیه',DARK['blue'],'برآورد نهایی منهای برآورد اولیه.'),('profit','سود/زیان پیش‌بینی',DARK['green'],'درآمد پیش‌بینی‌شده منهای هزینه نهایی.'),('targetprice','فروش لازم برای سود هدف',DARK['cyan'],'قیمت فروش لازم برای سود هدف.'),('funding','کسری تأمین مالی',DARK['red'],'منابع در برابر هزینه‌های باقی‌مانده.'),('area','متراژ لازم پیش‌فروش',DARK['orange'],'متراژ موردنیاز برای پوشش کسری.'),('m2_build_gross','ساخت/متر کل',DARK['blue'],'هزینه ساخت تقسیم بر متراژ کل.'),('m2_build_saleable','ساخت/متر مفید',DARK['cyan'],'هزینه ساخت تقسیم بر متراژ مفید.'),('m2_total_gross','تمام‌شده/متر کل',DARK['orange'],'کل هزینه پروژه تقسیم بر متراژ کل.'),('m2_total_saleable','تمام‌شده/متر مفید',DARK['green'],'کل هزینه پروژه تقسیم بر متراژ مفید.')]
        for c in range(5):kgrid.grid_columnconfigure(c,weight=1)
        for i,(k,t,col,info) in enumerate(defs):card=PremiumMetricCard175(kgrid,t,col,'◈',info,on_open=lambda kk=k,tt=t,ii=info:self.open_report_kpi(kk,tt,ii),compact=True);card.grid(row=i//5,column=i%5,sticky='nsew',padx=2,pady=2);self.report_cards[k]=card
        self.report_nb=ttk.Notebook(tab);self.report_nb.pack(fill='both',expand=True);price=ttk.Frame(self.report_nb,padding=5);phase=ttk.Frame(self.report_nb,padding=5);self.report_nb.add(price,text='قیمت‌ها');self.report_nb.add(phase,text='فازها')
        self.price_table=SmartTable(price,[('cat','گروه',105),('code','کد',90),('desc','شرح',245),('unit','واحد',80),('est','برآورد',125),('actual','واقعی مرجع',125),('fc','پیش‌بینی',125),('src','منبع',180)],title='قیمت مصالح، اجرت/اجرا و خدمات — دابل‌کلیک برای جزئیات');self.price_table.pack(fill='both',expand=True);self.price_table.set_edit_handler(lambda r:PriceDetailDialog17(self,self.rich,r,self.refresh_reports))
        self.phase_table=SmartTable(phase,[('no','شماره فاز',75),('phase','فاز',230),('est','برآورد',125),('actual','واقعی',125),('rem','مانده پایه',125),('fc','پیش‌بینی',125),('id','ID',90),('var','انحراف',120)],title='کنترل ۳۲ فاز — دابل‌کلیک برای ریز فاز و احجام');self.phase_table.pack(fill='both',expand=True);self.phase_table.set_edit_handler(lambda r:self.open_phase_by_no(r['phase_no']))

    def save_report_settings(self):
        try:
            def f(k):return float(str(self.report_vars[k].get()).replace(',','').replace('٬','').strip() or 0)
            SERVICE.budget.save_settings(gross_area=f('gross_area'),saleable_area=f('saleable_area'),unit_count=parse_int(self.report_vars['unit_count'].get()),monthly_inflation=f('inflation'),remaining_months=int(f('months')),presale_price_per_m2=parse_int(self.report_vars['presale'].get()),end_sale_price_override=(parse_int(self.report_vars['end_price'].get()) if self.report_vars['end_price'].get().strip() else None),unbudgeted_misc=parse_int(self.report_vars['misc'].get()),target_profit_percent=f('target'))
            self.refresh_reports();messagebox.showinfo('ذخیره شد','متراژ کل، متراژ مفید، تعداد واحدها و پارامترهای پیش‌بینی ذخیره شدند.',parent=self)
        except Exception as exc:messagebox.showerror('گزارش‌گیری',str(exc),parent=self)

    def refresh_reports(self):
        st=SERVICE.budget.get_settings();us=v16.d12.UNITS.summary();mapping={'gross_area':'gross_area','saleable_area':'saleable_area','unit_count':'unit_count','inflation':'monthly_inflation','months':'remaining_months','presale':'presale_price_per_m2','end_price':'end_sale_price_override','misc':'unbudgeted_misc','target':'target_profit_percent'}
        for vk,sk in mapping.items():
            val=st.get(sk)
            if vk in ('presale','end_price','misc','unit_count'):self.report_vars[vk].set('' if val is None else group_int(val,blank_zero=(vk=='end_price')))
            else:self.report_vars[vk].set('' if val is None else str(val or ''))
        project_units = int(st.get('unit_count') or 0)
        project_saleable = fa(f"{float(st.get('saleable_area') or 0):,.2f}")
        project_gross = fa(f"{float(st.get('gross_area') or 0):,.2f}")
        unit_rows_count = fa(us.get('count') or 0)
        unit_rows_area = fa(f"{float(us.get('area') or 0):,.2f}")
        self.unit_summary_var.set(
            f"مشخصات پروژه: {fa(project_units)} واحد | مفید {project_saleable} م² | "
            f"کل {project_gross} م²   •   جدول واحدها: {unit_rows_count} واحد / {unit_rows_area} م²"
        )
        v=SERVICE.budget.latest_version();self.budget_version.set(f"نسخه برآورد: {v.get('version_no')} — {v.get('title')}" if v else 'نسخه برآورد: -')
        try:
            fc=SERVICE.budget.forecast();diff=fc.forecast_total_cost-fc.initial_budget;self.report_cards['eac'].var.set(fmt_money(fc.forecast_total_cost));self.report_cards['cmp'].var.set(f"{fmt_money(diff)} ({fa(f'{(diff/fc.initial_budget*100 if fc.initial_budget else 0):+.1f}')}٪)");self.report_cards['profit'].var.set(f"{fmt_money(fc.projected_profit)} | {fa(f'{fc.projected_profit_percent:+.1f}')}٪");self.report_cards['targetprice'].var.set(fmt_money(fc.suggested_remaining_sale_price_per_m2)+'/متر');self.report_cards['funding'].var.set(fmt_money(fc.funding_gap));self.report_cards['area'].var.set(fa(f'{fc.presale_area_needed_m2:,.1f}')+' مترمربع');self.report_cards['m2_build_gross'].var.set(fmt_money(fc.construction_cost_per_gross_m2)+'/متر');self.report_cards['m2_build_saleable'].var.set(fmt_money(fc.construction_cost_per_saleable_m2)+'/متر');self.report_cards['m2_total_gross'].var.set(fmt_money(fc.total_cost_per_gross_m2)+'/متر');self.report_cards['m2_total_saleable'].var.set(fmt_money(fc.total_cost_per_saleable_m2)+'/متر')
        except Exception:pass
        prices=self.rich.list_prices(visible_only=True);catfa={'MATERIAL':'مصالح','LABOR':'اجرت/اجرا','SERVICE':'خدمات','INSTALLATION_GROUP':'تأسیسات (تجمیعی)'};self.price_table.set_rows(prices,lambda r:[catfa.get(r['category'],r['category']),r.get('code') or '-',r['description'],r.get('unit') or '-',fmt_money(r['estimate_rate']),fmt_money(r['actual_rate']),fmt_money(r['forecast_rate']),r.get('source') or '-'])
        phases=self._phase_summary_live();self.phase_table.set_rows(phases,lambda r:[fa(f"{r['phase_no']:02d}"),r['phase'],fmt_money(r['estimate']),fmt_money(r['actual']),fmt_money(r['remaining_base']),fmt_money(r['forecast']),r['phase_id'],fmt_money(r['variance'])]);self.refresh_phase_strip() if hasattr(self,'phase_buttons') else None

    def refresh_overview(self):
        super().refresh_overview()
        try:
            st=SERVICE.budget.get_settings();self.project_meta_var.set(f"{fa(int(st.get('unit_count') or 0))} واحد  •  {fa(f'{float(st.get('gross_area') or 0):,.0f}')} م² کل")
            phases=self._phase_summary_live();vals=sorted([(r['phase'],r['actual'] if r['actual']>0 else r['estimate']) for r in phases],key=lambda x:x[1],reverse=True);top=vals[:5];other=sum(v for _,v in vals[5:]);colors=['blue','green','orange','violet','cyan'];items=[(n,v,colors[i]) for i,(n,v) in enumerate(top)];
            if other:items.append(('سایر',other,'muted'))
            self.cost_donut.set_items(items)
        except Exception:pass

    def edit_project_settings(self):ProjectSettingsDialog175(self,self.refresh_all)

    def export_development_package(self):
        # Override the 17.4 inherited method so package metadata and default file
        # name always match the running 17.5 build.
        dest=filedialog.asksaveasfilename(
            parent=self, defaultextension='.zip',
            initialfile=f'BARKAV_Development_Package_{VERSION}.zip',
            filetypes=[('ZIP','*.zip')]
        )
        if not dest:return
        try:
            result=v174.build_development_package(BASE_DIR,Path(dest),VERSION)
            messagebox.showinfo('بسته توسعه',f"بسته توسعه {VERSION} ساخته شد:\n{result['path']}\n\nفایل‌های حساس و دیتابیس زنده وارد بسته نشده‌اند.\nتعداد فایل‌ها: {fa(result['file_count'])}",parent=self)
        except Exception as exc:
            messagebox.showerror('بسته توسعه',str(exc),parent=self)

    def edit_transaction_row(self,r):
        if r.get('pending_id'):
            p=DB.get_pending_item(r['pending_id']);row=dict(p or {});row['raw_text']=_raw_text_for_pending(r['pending_id']);UnifiedPendingEditor175(self,row,self.rich,self.refresh_all);return
        return super().edit_transaction_row(r)

    def edit_expense_row(self,r):
        if r.get('pending_id'):
            p=DB.get_pending_item(r['pending_id']);row=dict(p or {});row['raw_text']=_raw_text_for_pending(r['pending_id']);UnifiedPendingEditor175(self,row,self.rich,self.refresh_all);return
        return super().edit_expense_row(r)


# Compatibility export for launcher/tests.
Stage17Dashboard = Stage175Dashboard

if __name__=='__main__':
    Stage175Dashboard().mainloop()
