from __future__ import annotations

import json, os, re, shutil, tempfile, threading, asyncio, zipfile
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from typing import Any, Callable

import dashboard_stage16_3 as v16
from dashboard_stage16_3 import (
    DARK, TYPE_FA, TYPE_BY_FA, METHOD_FA, METHOD_BY_FA, STATE_FA, STATE_BY_FA,
    CHEQUE_TYPE_FA, CHEQUE_TYPE_BY_FA, STATUS_FA, SearchableCombo, GlassMetricCard,
    MiniLineChart, MiniBarChart, ProjectProgressBar, PriceDetailDialog,
    PhaseProgressDialog, PhaseChoiceDialog, fmt_money, fa, norm, as_int,
    Image, ImageOps, ImageTk, DB, SERVICE, CONFIG, BASE_DIR, APPROVAL,
    SmartTable, CompactTable, DateField, bind_grouped_number, group_int, parse_int,
    add_tooltip, normalize_shamsi, shamsi_to_gregorian, gregorian_to_shamsi,
)
from budget_rich_v163 import RichBudgetService
from market_service_v17 import MarketServiceV17
from historical_learning_v17 import HistoricalLearningV17
from runtime_status16 import preflight_snapshot, tail as runtime_tail
from development_package_v174 import build_development_package

VERSION='17.4'
REG_FA={'REGISTERED':'ثبت‌شده','UNREGISTERED':'ثبت‌نشده'}
REG_BY_FA={v:k for k,v in REG_FA.items()}
STATE_FA_EDIT={'PAID':'پرداخت کامل','PARTIAL':'پرداخت بخشی','UNPAID':'پرداخت‌نشده','UNKNOWN':'نامشخص'}
STATE_EDIT_BY_FA={v:k for k,v in STATE_FA_EDIT.items()}

# ---------- helpers ----------
def std_window(win:tk.Toplevel,title:str,geometry='1180x760',minsize=(820,560)):
    win.title(title);win.geometry(geometry);win.minsize(*minsize);win.resizable(True,True);win.configure(bg=DARK['bg'])
    try:win.protocol('WM_DELETE_WINDOW',win.destroy)
    except Exception:pass
    return win

def infer_receiver(text:str)->str:
    t=str(text or '').replace('ي','ی').replace('ك','ک')
    pats=[r'(?:به\s*حساب|واریز\s*به\s*حساب|انتقال\s*به\s*حساب)\s+([آ-یA-Za-z][آ-یA-Za-z\s‌]{2,45})',r'(?:برای|به)\s+([آ-ی][آ-ی\s‌]{3,35})(?:\s+#|\s+بابت|$)']
    for p in pats:
        m=re.search(p,t)
        if m:return re.sub(r'\s+',' ',m.group(1)).strip(' ،,-')
    return ''

def _mark_nonfinancial_approved(pid:str,entity_type='',entity_id=''):
    return v16._mark_nonfinancial_approved(pid,entity_type,entity_id)

def _raw_text_for_pending(pid):return v16._raw_text_for_pending(pid)

# ---------- V17 approval logic ----------
def _set_cheque_meta(cid:str,payload:dict[str,Any]):
    reg=str(payload.get('cheque_registration_state') or 'UNREGISTERED').upper()
    if reg not in {'REGISTERED','UNREGISTERED'}:reg='UNREGISTERED'
    with DB.tx() as con:
        con.execute('''UPDATE cheques SET registration_state=?,is_guarantee=?,guarantee_status=COALESCE(NULLIF(guarantee_status,''),'HELD'),updated_at=? WHERE cheque_id=?''',
                    (reg,1 if payload.get('is_guarantee') else 0,datetime.now().isoformat(timespec='seconds'),cid))

def _create_cheque_from_payload(payload:dict[str,Any],raw='',source='GUI_17'):
    amount=as_int(payload.get('amount') or payload.get('paid_amount') or payload.get('final_amount'))
    due=normalize_shamsi(str(payload.get('due_date_shamsi') or ''));issue=normalize_shamsi(str(payload.get('issue_date_shamsi') or payload.get('event_date_shamsi') or '')) or due
    if amount<=0:raise ValueError('مبلغ چک کامل نیست.')
    if not due:raise ValueError('تاریخ سررسید چک کامل نیست.')
    cid=DB.create_cheque(amount=amount,issue_date=shamsi_to_gregorian(issue),issue_date_shamsi=issue,due_date=shamsi_to_gregorian(due),due_date_shamsi=due,
        cheque_serial=str(payload.get('cheque_serial') or ''),issuer_bank=str(payload.get('issuer_bank') or payload.get('bank_name') or ''),issuer_name=str(payload.get('issuer_name') or ''),
        cheque_type=str(payload.get('cheque_type') or 'PHYSICAL'),receiver_name=str(payload.get('receiver_name') or ''),description=str(payload.get('description') or raw),source=source,actor_id='GUI',is_guarantee=bool(payload.get('is_guarantee')))
    _set_cheque_meta(cid,payload);return cid

def approve_v17(pid:str,payload:dict[str,Any],rich:RichBudgetService):
    typ=str(payload.get('detected_type') or 'UNKNOWN').upper();state=str(payload.get('payment_state') or 'UNKNOWN').upper();raw=_raw_text_for_pending(pid)
    if typ=='INFO':_mark_nonfinancial_approved(pid,'INFO',pid);return 'اطلاع‌رسانی ثبت شد؛ اثر مالی ندارد.'
    if typ=='DOCUMENT':
        links=[];lp=str(payload.get('link_pending_id') or '')
        if lp:
            post=DB.get_financial_posting(lp)
            if post and post.get('primary_entity_type') and post.get('primary_entity_id'):links=[(post['primary_entity_type'],post['primary_entity_id'])]
        did=rich.add_financial_document(pid,payload,raw,links);DB.relink_pending_attachments(pid,entity_type='DOCUMENT',entity_id=did);_mark_nonfinancial_approved(pid,'DOCUMENT',did)
        return 'سند به پرونده اسناد مالی اضافه شد؛ رویداد مالی جدید ساخته نشد.'
    multi=payload.get('cheques') if isinstance(payload.get('cheques'),list) else []
    # Guarantee cheques are custody/security documents, never financial commitments.
    if typ=='CHEQUE' and payload.get('is_guarantee'):
        created=[]
        source_rows=multi if multi else [payload]
        for c in source_rows:
            x=dict(payload);x.update(c);x['is_guarantee']=True;created.append(_create_cheque_from_payload(x,raw,'GUI_GUARANTEE'))
        did=rich.add_financial_document(pid,{**payload,'document_type':'GUARANTEE_CHEQUE','amount':sum(as_int((c or {}).get('amount')) for c in source_rows)},raw,[('CHEQUE',c) for c in created])
        DB.relink_pending_attachments(pid,entity_type='DOCUMENT',entity_id=did);_mark_nonfinancial_approved(pid,'DOCUMENT',did)
        return f'{len(created)} چک ضمانتی ثبت شد؛ در هزینه، خروجی و تعهد مالی محاسبه نمی‌شود.'
    if state!='CHEQUE_CLEARING' and len(multi)>1 and (typ=='CHEQUE' or str(payload.get('payment_method') or '').upper()=='CHEQUE' or '#چک' in raw):
        created=[]
        for idx,c in enumerate(multi,1):
            x=dict(payload);x.update(c);x['cheque_registration_state']=c.get('registration_state') or c.get('cheque_registration_state') or payload.get('cheque_registration_state') or 'UNREGISTERED'
            try:created.append(_create_cheque_from_payload(x,raw,'GUI_MULTI_CHEQUE_17'))
            except Exception as exc:raise ValueError(f'چک {idx}: {exc}')
        did=rich.add_financial_document(pid,{**payload,'document_type':'CHEQUE_BUNDLE','amount':sum(as_int(c.get('amount')) for c in multi)},raw,[('CHEQUE',c) for c in created]);DB.relink_pending_attachments(pid,entity_type='DOCUMENT',entity_id=did);_mark_nonfinancial_approved(pid,'DOCUMENT',did)
        return f'{len(created)} چک جدا ثبت شد و تصویر مشترک به همه متصل شد.'
    if state=='CHEQUE_CLEARING':
        amount=as_int(payload.get('amount') or payload.get('paid_amount') or payload.get('final_amount'));sh=normalize_shamsi(str(payload.get('event_date_shamsi') or ''))
        rows=[r for r in DB.list_cheques(open_only=True,limit=1000) if not int(r.get('is_guarantee') or 0)];cand=[]
        desc=norm(str(payload.get('description') or '')+' '+str(payload.get('receiver_name') or '')+' '+raw)
        for r in rows:
            score=0
            if amount and int(r.get('amount') or 0)==amount:score+=55
            if sh and sh==str(r.get('due_date_shamsi') or ''):score+=40
            hay=norm(str(r.get('receiver_name') or '')+' '+str(r.get('description') or ''))
            if desc and hay and any(t in hay for t in desc.split() if len(t)>2):score+=10
            if score:cand.append((score,r))
        cand.sort(key=lambda x:-x[0])
        if not cand:raise ValueError('چک بازی با مبلغ/سررسید این رسید پیدا نشد.')
        if len(cand)>1 and cand[0][0]==cand[1][0]:raise ValueError('چند چک مشابه پیدا شد؛ ابتدا مشخصات چک صحیح را دقیق کن.')
        ch=cand[0][1];cash_sh=sh or gregorian_to_shamsi(datetime.now().date());DB.cash_cheque(ch['cheque_id'],cashed_date=shamsi_to_gregorian(cash_sh),cashed_date_shamsi=cash_sh,source='GUI_RECEIPT_17',actor_id='GUI')
        DB.relink_pending_attachments(pid,entity_type='CHEQUE',entity_id=ch['cheque_id']);_mark_nonfinancial_approved(pid,'CHEQUE',ch['cheque_id']);return f"چک {ch['cheque_id']} پاس شد؛ هزینه دوباره ثبت نشد."
    result=APPROVAL.approve(pid,actor_id='GUI_17')
    if result.posting.cheque_id:_set_cheque_meta(result.posting.cheque_id,payload)
    return f"ثبت شد: {TYPE_FA.get(str(result.posting.posting_type),'ثبت مالی')}"

# ---------- unified detail editor ----------
class UnifiedPendingEditor17(tk.Toplevel):
    def __init__(self,parent,row:dict[str,Any],rich:RichBudgetService,on_done:Callable[[],None]):
        super().__init__(parent);self.row=row;self.rich=rich;self.on_done=on_done;self.pid=str(row['pending_id']);self.payload=dict(row.get('payload') or {});self.vars={};self.widgets={};self.expense_widgets=[];self._image=None;self._tkimg=None;self._zoom=.7;self._multi_cheques=[];self._system_state=str(self.payload.get('payment_state') or '').upper()
        std_window(self,f'جزئیات ثبت دیتا — {self.pid}','1320x800',(940,620));self._build();self._load();self.after(160,self._fit_image)
    def _field(self,parent,key,label,kind='entry',row=0,col=0,width=24):
        box=tk.Frame(parent,bg=DARK['panel']);box.grid(row=row,column=col,sticky='ew',padx=4,pady=3);box.grid_columnconfigure(0,weight=1)
        tk.Label(box,text=label,bg=DARK['panel'],fg=DARK['muted'],font=('Tahoma',8)).grid(row=0,column=0,sticky='e')
        v=self.vars.setdefault(key,tk.StringVar())
        if kind=='date':w=DateField(box,v,width=width)
        elif kind=='type':w=ttk.Combobox(box,textvariable=v,state='readonly',values=list(TYPE_BY_FA),width=width);w.bind('<<ComboboxSelected>>',lambda e:self._sync_dynamic())
        elif kind=='state':w=ttk.Combobox(box,textvariable=v,state='readonly',values=list(STATE_EDIT_BY_FA),width=width);w.bind('<<ComboboxSelected>>',lambda e:self._sync_amounts())
        elif kind=='method':w=ttk.Combobox(box,textvariable=v,state='readonly',values=list(METHOD_BY_FA),width=width)
        elif kind=='chequetype':w=ttk.Combobox(box,textvariable=v,state='readonly',values=list(CHEQUE_TYPE_BY_FA),width=width)
        elif kind=='reg':w=ttk.Combobox(box,textvariable=v,state='readonly',values=list(REG_BY_FA),width=width)
        elif kind=='phase':w=SearchableCombo(box,v,[],on_pick=lambda x:self._update_sub_values(),width=width)
        elif kind=='subphase':w=SearchableCombo(box,v,[],on_pick=self._subphase_picked,width=width)
        else:w=ttk.Entry(box,textvariable=v,justify='right',width=width);bind_grouped_number(w,v) if kind=='num' else None
        w.grid(row=1,column=0,sticky='ew',pady=(2,0));self.widgets[key]=w
        if key in {'amount','invoice_amount','final_amount'}:v.trace_add('write',lambda *_:self.after_idle(self._sync_amounts))
        return w
    def _build(self):
        head=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);head.pack(fill='x',padx=8,pady=8)
        tk.Label(head,text='ویرایش و تأیید رکورد',bg=DARK['surface'],fg=DARK['text'],font=('Tahoma',11,'bold')).pack(side='right',padx=10,pady=7)
        self.status_lbl=tk.Label(head,text='',bg=DARK['surface'],fg=DARK['yellow'],font=('Tahoma',8,'bold'));self.status_lbl.pack(side='left',padx=10)
        pane=ttk.Panedwindow(self,orient='horizontal');pane.pack(fill='both',expand=True,padx=8,pady=(0,8))
        ev=tk.Frame(pane,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);frm=tk.Frame(pane,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);pane.add(ev,weight=5);pane.add(frm,weight=5)
        tk.Label(ev,text='شواهد — سند و متن کاربر',bg=DARK['panel'],fg='#7FC9FF',font=('Tahoma',10,'bold')).pack(anchor='e',padx=9,pady=(7,3))
        ep=ttk.Panedwindow(ev,orient='horizontal');ep.pack(fill='both',expand=True,padx=7,pady=(0,7));imgf=tk.Frame(ep,bg='#07101B');txtf=tk.Frame(ep,bg=DARK['panel2']);ep.add(imgf,weight=3);ep.add(txtf,weight=2)
        self.canvas=tk.Canvas(imgf,bg='#07101B',highlightthickness=0);ys=ttk.Scrollbar(imgf,orient='vertical',command=self.canvas.yview);xs=ttk.Scrollbar(imgf,orient='horizontal',command=self.canvas.xview);self.canvas.configure(yscrollcommand=ys.set,xscrollcommand=xs.set);self.canvas.grid(row=0,column=0,sticky='nsew');ys.grid(row=0,column=1,sticky='ns');xs.grid(row=1,column=0,sticky='ew');imgf.grid_rowconfigure(0,weight=1);imgf.grid_columnconfigure(0,weight=1)
        self.canvas.bind('<MouseWheel>',self._wheel);self.canvas.bind('<ButtonPress-1>',lambda e:self.canvas.scan_mark(e.x,e.y));self.canvas.bind('<B1-Motion>',lambda e:self.canvas.scan_dragto(e.x,e.y,gain=1))
        ib=tk.Frame(imgf,bg='#07101B');ib.grid(row=2,column=0,columnspan=2,sticky='ew');
        for t,cmd in [('−',lambda:self._set_zoom(self._zoom/1.2)),('Fit',self._fit_image),('+',lambda:self._set_zoom(self._zoom*1.2))]:tk.Button(ib,text=t,command=cmd,bg=DARK['glass'],fg='white',relief='flat',width=5).pack(side='left',padx=2,pady=4)
        self.evidence_text=tk.Text(txtf,wrap='word',bg='#091726',fg=DARK['text'],insertbackground='white',relief='flat',font=('Tahoma',8),padx=8,pady=8);self.evidence_text.pack(fill='both',expand=True);self.evidence_text.configure(state='disabled')
        # scrollable form
        c=tk.Canvas(frm,bg=DARK['panel'],highlightthickness=0);sb=ttk.Scrollbar(frm,orient='vertical',command=c.yview);c.configure(yscrollcommand=sb.set);c.pack(side='left',fill='both',expand=True);sb.pack(side='right',fill='y');body=tk.Frame(c,bg=DARK['panel']);wid=c.create_window((0,0),window=body,anchor='nw');body.bind('<Configure>',lambda e:c.configure(scrollregion=c.bbox('all')));c.bind('<Configure>',lambda e:c.itemconfigure(wid,width=e.width));c.bind('<MouseWheel>',lambda e:c.yview_scroll(int(-e.delta/120),'units'))
        sel=tk.LabelFrame(body,text='نوع و تاریخ',bg=DARK['panel'],fg='#7FC9FF',font=('Tahoma',9,'bold'));sel.pack(fill='x',padx=8,pady=6);sel.grid_columnconfigure((0,1),weight=1)
        self._field(sel,'event_date_shamsi','تاریخ', 'date',0,1);self._field(sel,'detected_type','نوع تراکنش','type',0,0)
        self.system_event=tk.StringVar(value='');tk.Label(sel,textvariable=self.system_event,bg=DARK['panel'],fg=DARK['orange'],font=('Tahoma',8,'bold')).grid(row=1,column=0,columnspan=2,sticky='e',padx=5,pady=3)
        self.expense_frame=tk.LabelFrame(body,text='هزینه / سایر تراکنش مالی',bg=DARK['panel'],fg='#7FC9FF',font=('Tahoma',9,'bold'));self.expense_frame.pack(fill='x',padx=8,pady=6);self.expense_frame.grid_columnconfigure((0,1),weight=1)
        specs=[('payer_name','واریزکننده','entry'),('amount','مبلغ پرداختی','num'),('payment_state','وضعیت پرداخت','state'),('invoice_amount','مبلغ فاکتور','num'),('final_amount','مبلغ نهایی','num'),('remaining_debt','مانده بدهی','num'),('discount_amount','تخفیف','num'),('receiver_name','گیرنده','entry'),('description','بابت','entry'),('payment_method','روش پرداخت','method')]
        self.expense_keys=[]
        for i,(k,l,kind) in enumerate(specs):
            w=self._field(self.expense_frame,k,l,kind,i//2,i%2);self.expense_keys.append(k);self.expense_widgets.append(w)
        self.cheque_frame=tk.LabelFrame(body,text='مشخصات چک',bg=DARK['panel'],fg='#7FC9FF',font=('Tahoma',9,'bold'));self.cheque_frame.pack(fill='x',padx=8,pady=6);self.cheque_frame.grid_columnconfigure((0,1),weight=1)
        cs=[('amount','مبلغ پرداختی','num'),('invoice_amount','مبلغ فاکتور','num'),('remaining_debt','مانده بدهی','num'),('receiver_name','گیرنده','entry'),('issue_date_shamsi','تاریخ صدور چک','date'),('due_date_shamsi','تاریخ سررسید','date'),('issuer_bank','بانک','entry'),('issuer_name','صاحب حساب','entry'),('cheque_serial','شماره/صیادی','entry'),('cheque_type','نوع چک','chequetype'),('cheque_registration_state','وضعیت ثبت','reg'),('description','بابت','entry')]
        self.cheque_widgets=[]
        for i,(k,l,kind) in enumerate(cs):w=self._field(self.cheque_frame,k,l,kind,i//2,i%2);self.cheque_widgets.append(w)
        self.is_guarantee=tk.BooleanVar(value=False);cb=tk.Checkbutton(self.cheque_frame,text='بابت ضمانت — در هزینه و تعهد مالی محاسبه نشود',variable=self.is_guarantee,bg=DARK['panel'],fg=DARK['text'],selectcolor=DARK['surface'],activebackground=DARK['panel'],activeforeground='white');cb.grid(row=6,column=0,columnspan=2,sticky='e',padx=6,pady=5);self.cheque_widgets.append(cb)
        tk.Label(self.cheque_frame,text='وضعیت پاس/برگشت چک انتخاب دستی ندارد و از رسید/متن رویداد تشخیص داده می‌شود.',bg=DARK['panel'],fg=DARK['muted'],font=('Tahoma',7)).grid(row=7,column=0,columnspan=2,sticky='e',padx=5,pady=3)
        self.multi_cheque_var=tk.StringVar();tk.Label(self.cheque_frame,textvariable=self.multi_cheque_var,bg=DARK['panel'],fg=DARK['orange'],font=('Tahoma',8,'bold')).grid(row=8,column=0,columnspan=2,sticky='ew',padx=5,pady=3)
        self.multi_cheque_tree=ttk.Treeview(self.cheque_frame,columns=('amount','issue','due','serial','bank'),show='headings',height=5)
        for k,l,w in [('amount','مبلغ',125),('issue','صدور',100),('due','سررسید',100),('serial','صیادی',120),('bank','بانک',110)]:self.multi_cheque_tree.heading(k,text=l);self.multi_cheque_tree.column(k,width=w,anchor='center')
        self.multi_cheque_tree.grid(row=9,column=0,columnspan=2,sticky='ew',padx=5,pady=4);self.multi_cheque_tree.bind('<Double-1>',lambda e:self._copy_multi_cheque())
        ph=tk.LabelFrame(body,text='طبقه‌بندی فاز',bg=DARK['panel'],fg='#7FC9FF',font=('Tahoma',9,'bold'));ph.pack(fill='x',padx=8,pady=6);ph.grid_columnconfigure((0,1),weight=1);self._field(ph,'main_phase','فاز اصلی','phase',0,1,32);self._field(ph,'sub_phase','فاز فرعی','subphase',0,0,32)
        act=tk.Frame(body,bg=DARK['panel']);act.pack(fill='x',padx=8,pady=10);tk.Button(act,text='💾 ذخیره اصلاحات',command=self.save_only,bg=DARK['blue'],fg='white',relief='flat',padx=12,pady=7).pack(side='right',padx=3);tk.Button(act,text='✅ تأیید نهایی',command=self.approve,bg=DARK['green'],fg='white',relief='flat',padx=12,pady=7).pack(side='right',padx=3);tk.Button(act,text='❌ رد',command=self.reject,bg=DARK['red'],fg='white',relief='flat',padx=12,pady=7).pack(side='right',padx=3);self.msg=tk.StringVar();tk.Label(act,textvariable=self.msg,bg=DARK['panel'],fg=DARK['muted'],font=('Tahoma',8)).pack(side='left')
    def _phase_values(self):return [f"{int(r['phase_no']):02d} — {r['phase']}" for r in self.rich.list_phase_summary()]
    def _load(self):
        p=self.payload;raw=str(self.row.get('raw_text') or _raw_text_for_pending(self.pid) or '')
        state=str(p.get('payment_state') or 'UNKNOWN').upper();self._system_state=state
        vals={'event_date_shamsi':str(p.get('event_date_shamsi') or self.row.get('message_date') or '').split()[0],'detected_type':TYPE_FA.get(str(p.get('detected_type') or 'UNKNOWN').upper(),'نامشخص'),'payer_name':p.get('payer_name') or 'تنخواه','amount':group_int(p.get('amount') or 0),'payment_state':STATE_FA_EDIT.get(state,'نامشخص'),'invoice_amount':group_int(p.get('invoice_amount') or 0),'final_amount':group_int(p.get('final_amount') or 0),'remaining_debt':group_int(p.get('remaining_debt') or 0),'discount_amount':group_int(p.get('discount_amount') or 0),'receiver_name':p.get('receiver_name') or infer_receiver(raw),'description':p.get('description') or raw,'payment_method':METHOD_FA.get(str(p.get('payment_method') or 'UNKNOWN').upper(),'نامشخص'),'issue_date_shamsi':p.get('issue_date_shamsi') or '','due_date_shamsi':p.get('due_date_shamsi') or '','issuer_bank':p.get('issuer_bank') or p.get('bank_name') or '','issuer_name':p.get('issuer_name') or '','cheque_serial':p.get('cheque_serial') or '','cheque_type':CHEQUE_TYPE_FA.get(str(p.get('cheque_type') or 'PHYSICAL').upper(),'فیزیکی'),'cheque_registration_state':REG_FA.get(str(p.get('cheque_registration_state') or 'UNREGISTERED').upper(),'ثبت‌نشده'),'main_phase':p.get('main_phase') or p.get('construction_stage') or '','sub_phase':p.get('sub_phase') or p.get('expense_category') or ''}
        for k,val in vals.items():self.vars[k].set(str(val or ''))
        self.is_guarantee.set(bool(p.get('is_guarantee')));self.status_lbl.configure(text=f"● {STATUS_FA.get(self.row.get('status'),self.row.get('status'))}")
        if state=='CHEQUE_CLEARING':self.system_event.set('رویداد تشخیص‌شده: پاس کردن چک قبلی — وضعیت وصول پس از تطبیق خودکار می‌شود.')
        self.widgets['main_phase'].set_all(self._phase_values());self._update_sub_values();self._load_evidence();self._sync_amounts();self._sync_dynamic()
        self._multi_cheques=p.get('cheques') if isinstance(p.get('cheques'),list) else []
        for x in self.multi_cheque_tree.get_children():self.multi_cheque_tree.delete(x)
        if self._multi_cheques:
            self.multi_cheque_var.set(f"AI تعداد {fa(len(self._multi_cheques))} چک در تصویر تشخیص داده؛ دابل‌کلیک هر ردیف برای بررسی.")
            for i,c in enumerate(self._multi_cheques):self.multi_cheque_tree.insert('', 'end',iid=str(i),values=(fmt_money(c.get('amount')),c.get('issue_date_shamsi') or '-',c.get('due_date_shamsi') or '-',c.get('cheque_serial') or '-',c.get('issuer_bank') or '-'))
        else:self.multi_cheque_var.set('')
    def _load_evidence(self):
        try:b=APPROVAL.evidence_bundle(self.pid,window=3)
        except Exception:b={'current':{'raw_text':self.row.get('raw_text') or ''},'nearby':[],'attachments':[]}
        cur=b.get('current') or {};lines=[];raw=str(cur.get('raw_text') or self.row.get('raw_text') or '').strip()
        if raw:lines.append('متن کاربر / کپشن:\n'+raw)
        near=[]
        for m in b.get('nearby') or []:
            t=str(m.get('raw_text') or '').strip()
            if t:near.append(f"{m.get('message_date') or ''} — {t}")
        if near:lines.append('پیام‌های مرتبط نزدیک:\n'+'\n'.join(near))
        analysis=DB.get_receipt_analysis(self.pid) or {};ocr=str(analysis.get('ocr_text') or self.row.get('receipt_ocr_text') or '').strip()
        if ocr:lines.append('متن استخراج‌شده از داخل تصویر (OCR/AI — منبع کمکی):\n'+ocr[:6000])
        self.evidence_text.configure(state='normal');self.evidence_text.delete('1.0','end');self.evidence_text.insert('1.0','\n\n'.join(lines) or 'متن همراه ثبت نشده است.');self.evidence_text.configure(state='disabled')
        path=str(self.row.get('receipt_image_path') or '')
        if not path:
            for a in b.get('attachments') or []:
                if str(a.get('mime_type') or '').startswith('image/') and Path(str(a.get('local_path') or '')).exists():path=str(a.get('local_path'));break
        if path and Image is not None:
            try:self._image=ImageOps.exif_transpose(Image.open(path)).convert('RGB')
            except Exception:self._image=None
        if not self._image:self.canvas.create_text(220,180,text='رسید تصویری ندارد',fill=DARK['muted'],font=('Tahoma',10))
    def _fit_image(self):
        if not self._image:return
        self.canvas.update_idletasks();cw=max(220,self.canvas.winfo_width()-26);ch=max(220,self.canvas.winfo_height()-26);self._zoom=min(.82,cw/self._image.width,ch/self._image.height);self._render_image()
    def _set_zoom(self,z):self._zoom=max(.08,min(4,float(z)));self._render_image()
    def _wheel(self,e):self._set_zoom(self._zoom*(1.1 if e.delta>0 else 1/1.1))
    def _render_image(self):
        if not self._image or ImageTk is None:return
        w=max(1,int(self._image.width*self._zoom));h=max(1,int(self._image.height*self._zoom));im=self._image.resize((w,h)) if (w,h)!=self._image.size else self._image;self._tkimg=ImageTk.PhotoImage(im);self.canvas.delete('all');self.canvas.create_image(8,8,image=self._tkimg,anchor='nw');self.canvas.configure(scrollregion=(0,0,w+16,h+16))
    def _copy_multi_cheque(self):
        s=self.multi_cheque_tree.selection()
        if not s:return
        try:c=self._multi_cheques[int(s[0])]
        except Exception:return
        self.vars['detected_type'].set('چک');self.vars['amount'].set(group_int(c.get('amount') or 0));self.vars['issue_date_shamsi'].set(str(c.get('issue_date_shamsi') or ''));self.vars['due_date_shamsi'].set(str(c.get('due_date_shamsi') or ''));self.vars['issuer_bank'].set(str(c.get('issuer_bank') or ''));self.vars['issuer_name'].set(str(c.get('issuer_name') or ''));self.vars['receiver_name'].set(str(c.get('receiver_name') or self.vars['receiver_name'].get()));self.vars['cheque_serial'].set(str(c.get('cheque_serial') or ''));self.vars['cheque_type'].set(CHEQUE_TYPE_FA.get(str(c.get('cheque_type') or 'PHYSICAL').upper(),'فیزیکی'));self.vars['cheque_registration_state'].set(REG_FA.get(str(c.get('registration_state') or c.get('cheque_registration_state') or 'UNREGISTERED').upper(),'ثبت‌نشده'));self.is_guarantee.set(bool(c.get('is_guarantee')));self._sync_dynamic()
    def _update_sub_values(self):
        txt=self.vars['main_phase'].get();no=None
        try:no=int(txt.split('—',1)[0].strip())
        except Exception:
            c=self.rich.phase_candidates(txt,1);no=c[0]['phase_no'] if c else None
            if c and txt.strip():self.vars['main_phase'].set(f"{no:02d} — {c[0]['phase_name']}")
        rows=self.rich.subphase_candidates(no,'');self.widgets['sub_phase'].set_all([r['description'] for r in rows])
    def _subphase_picked(self,value):
        matches=self.rich.subphase_candidates(None,value);ph=[]
        for r in matches:
            k=(r['phase_no'],r['phase_name'])
            if k not in ph:ph.append(k)
        if len(ph)==1:self.vars['main_phase'].set(f"{ph[0][0]:02d} — {ph[0][1]}");self._update_sub_values()
        elif len(ph)>1:self.widgets['main_phase'].set_all([f"{n:02d} — {name}" for n,name in ph])
    def _sync_amounts(self):
        try:
            inv=parse_int(self.vars['invoice_amount'].get());fin=parse_int(self.vars['final_amount'].get());paid=parse_int(self.vars['amount'].get());state=STATE_EDIT_BY_FA.get(self.vars['payment_state'].get(),'UNKNOWN')
            if inv and fin and fin<inv:self.vars['discount_amount'].set(group_int(inv-fin))
            if state=='PARTIAL':self.vars['remaining_debt'].set(group_int(max(fin-paid,0)))
            elif state=='PAID':self.vars['remaining_debt'].set(group_int(0))
            elif state=='UNPAID':self.vars['remaining_debt'].set(group_int(fin))
        except Exception:pass
    def _set_widget_state(self,w,enabled:bool):
        try:
            if isinstance(w,DateField):w.entry.configure(state='normal' if enabled else 'disabled');return
            if isinstance(w,(ttk.Combobox,SearchableCombo)):w.configure(state='readonly' if enabled else 'disabled');return
            if isinstance(w,ttk.Entry):w.configure(state='normal' if enabled else 'disabled');return
            if isinstance(w,tk.Checkbutton):w.configure(state='normal' if enabled else 'disabled');return
        except Exception:pass
    def _sync_dynamic(self):
        typ=TYPE_BY_FA.get(self.vars['detected_type'].get(),'UNKNOWN');is_ch=typ=='CHEQUE'
        for w in self.expense_widgets:self._set_widget_state(w,not is_ch)
        for w in self.cheque_widgets:self._set_widget_state(w,is_ch)
        # common type/date and phase remain editable.
    def payload_from_form(self):
        p=dict(self.payload);typ=TYPE_BY_FA.get(self.vars['detected_type'].get(),'UNKNOWN');state=self._system_state if self._system_state=='CHEQUE_CLEARING' else STATE_EDIT_BY_FA.get(self.vars['payment_state'].get(),'UNKNOWN');method=METHOD_BY_FA.get(self.vars['payment_method'].get(),'UNKNOWN')
        if typ=='CHEQUE' and method=='UNKNOWN':method='CHEQUE'
        p.update({'detected_type':typ,'event_date_shamsi':self.vars['event_date_shamsi'].get().strip(),'payer_name':self.vars['payer_name'].get().strip() or 'تنخواه','receiver_name':self.vars['receiver_name'].get().strip(),'description':self.vars['description'].get().strip(),'payment_method':method,'payment_state':state})
        for k in ('amount','invoice_amount','final_amount','remaining_debt','discount_amount'):p[k]=parse_int(self.vars[k].get())
        p['paid_amount']=p['amount'] if state in {'PAID','PARTIAL','CHEQUE_CLEARING'} else int(p.get('paid_amount') or 0)
        main=self.vars['main_phase'].get().strip();sub=self.vars['sub_phase'].get().strip();sel=None
        try:no=int(main.split('—',1)[0].strip());sel=next((x for x in self.rich.list_phase_summary() if x['phase_no']==no),None)
        except Exception:pass
        if not sel and main:sel=(self.rich.phase_candidates(main,1) or [None])[0]
        if not sel and sub:
            ms=self.rich.subphase_candidates(None,sub);uniq=[]
            for x in ms:
                c={'phase_no':x['phase_no'],'phase_name':x['phase_name']}
                if c not in uniq:uniq.append(c)
            sel=PhaseChoiceDialog.choose(self,uniq[:8])
        if sel:main=f"{int(sel['phase_no']):02d} — {sel.get('phase') or sel.get('phase_name')}";self.vars['main_phase'].set(main)
        p['main_phase']=main;p['sub_phase']=sub;p['construction_stage']=main;p['expense_category']=sub or p.get('expense_category') or ''
        p['is_cheque']=typ=='CHEQUE';p['is_guarantee']=bool(self.is_guarantee.get())
        for k in ('issue_date_shamsi','due_date_shamsi','issuer_bank','issuer_name','cheque_serial'):p[k]=self.vars[k].get().strip()
        p['cheque_type']=CHEQUE_TYPE_BY_FA.get(self.vars['cheque_type'].get(),'PHYSICAL');p['cheque_registration_state']=REG_BY_FA.get(self.vars['cheque_registration_state'].get(),'UNREGISTERED');p['manager_fee_eligible']=typ=='EXPENSE'
        return p
    def save_only(self):
        try:self.payload=self.payload_from_form();APPROVAL.save_payload(self.pid,self.payload,learn=True);self.msg.set('اصلاحات ذخیره شد؛ هنوز اثر مالی ندارد.');self.on_done()
        except Exception as exc:messagebox.showerror('ذخیره',str(exc),parent=self)
    def approve(self):
        try:self.payload=self.payload_from_form();APPROVAL.save_payload(self.pid,self.payload,learn=True);msg=approve_v17(self.pid,self.payload,self.rich);messagebox.showinfo('ثبت',msg,parent=self);self.on_done();self.destroy()
        except Exception as exc:messagebox.showerror('تأیید انجام نشد',str(exc),parent=self)
    def reject(self):
        if not messagebox.askyesno('رد','این مورد رد شود؟ هیچ اثر مالی ایجاد نمی‌شود.',parent=self):return
        try:APPROVAL.reject(self.pid,actor_id='GUI_17');self.on_done();self.destroy()
        except Exception as exc:messagebox.showerror('رد',str(exc),parent=self)

# ---------- data-entry center ----------
class DataEntryCenter17(v16.DataEntryCenter163):
    def __init__(self,parent,rich,on_posted=None):self._shown_pid='';self.status_buttons={};super().__init__(parent,rich,on_posted)
    def _build(self):
        top=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);top.pack(fill='x',pady=(0,6));tk.Label(top,text='ثبت دیتا — مرکز تأیید تراکنش‌ها',bg=DARK['surface'],fg=DARK['text'],font=('Tahoma',10,'bold')).pack(side='right',padx=10,pady=7);self.bot=tk.StringVar(value='ربات: در حال بررسی...');tk.Label(top,textvariable=self.bot,bg=DARK['surface'],fg=DARK['green'],font=('Tahoma',8,'bold')).pack(side='left',padx=8)
        tools=tk.Frame(self,bg=DARK['surface']);tools.pack(fill='x',pady=(0,5));self.filter=tk.StringVar(value='Pending')
        for key,label,col in [('همه','همه',DARK['glass']),('Pending','Pending',DARK['orange']),('تأییدشده','تأییدشده',DARK['green']),('ردشده','ردشده',DARK['red'])]:
            b=tk.Button(tools,text=label,command=lambda k=key:self._set_status(k),bg=DARK['glass'],fg='white',relief='flat',font=('Tahoma',8,'bold'),padx=12,pady=5);b.pack(side='right',padx=3);self.status_buttons[key]=(b,col)
        ttk.Button(tools,text='🔄',command=self.refresh,style='Toolbar.TButton').pack(side='left',padx=2);ttk.Button(tools,text='🧪 اتصال',command=self.status_dialog,style='Toolbar.TButton').pack(side='left',padx=2);ttk.Button(tools,text='🤖 تحلیل انتخاب‌ها',command=self.analyze_selected,style='Toolbar.TButton').pack(side='left',padx=2);ttk.Button(tools,text='🔗 تجمیع',command=self.merge_selected,style='Toolbar.TButton').pack(side='left',padx=2);ttk.Button(tools,text='🧹 پاک‌سازی تعیین‌تکلیف‌شده',command=self.clear_finished,style='Toolbar.TButton').pack(side='left',padx=2)
        pane=ttk.Panedwindow(self,orient='horizontal');pane.pack(fill='both',expand=True);left=tk.Frame(pane,bg=DARK['panel']);right=tk.Frame(pane,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);pane.add(left,weight=7);pane.add(right,weight=3)
        self.table=SmartTable(left,[('doc','سند',55),('date','تاریخ',105),('type','نوع',90),('text','متن کاربر / بابت',280),('amount','مبلغ AI',125),('phase','فاز اصلی',170),('sub','فاز فرعی',170),('pay','پرداخت',105),('conf','AI',65),('status','وضعیت',95)],title='رکوردهای ثبت دیتا');self.table.pack(fill='both',expand=True);self.table.tree.bind('<<TreeviewSelect>>',self._select,add='+');self.table.tree.bind('<Double-1>',lambda e:self.open_editor(),add='+');self.table.set_edit_handler(lambda r:self.open_editor(r));self.table.set_delete_handler(self._delete_row)
        rb=tk.Frame(right,bg=DARK['panel']);rb.pack(fill='x',padx=7,pady=7);tk.Label(rb,text='پیش‌نمایش سند + متن',bg=DARK['panel'],fg='#7FC9FF',font=('Tahoma',9,'bold')).pack(side='right');tk.Button(rb,text='✅ تأیید سریع',command=self.quick_approve,bg=DARK['green'],fg='white',relief='flat',padx=8,pady=5).pack(side='left');tk.Button(rb,text='✏️ اصلاح و تأیید',command=self.open_editor,bg=DARK['blue'],fg='white',relief='flat',padx=8,pady=5).pack(side='left',padx=3)
        self.preview=tk.Canvas(right,bg='#07101B',highlightthickness=0,height=310);self.preview.pack(fill='both',expand=True,padx=7);self.preview.bind('<MouseWheel>',self._wheel);self.preview.bind('<ButtonPress-1>',lambda e:self.preview.scan_mark(e.x,e.y));self.preview.bind('<B1-Motion>',lambda e:self.preview.scan_dragto(e.x,e.y,gain=1));zb=tk.Frame(right,bg=DARK['panel']);zb.pack(fill='x',padx=7);tk.Button(zb,text='Fit',command=self._fit,bg=DARK['glass'],fg='white',relief='flat').pack(side='left',padx=2,pady=3);tk.Button(zb,text='+',command=lambda:self._set_zoom(self.zoom*1.2),bg=DARK['glass'],fg='white',relief='flat').pack(side='left');tk.Button(zb,text='−',command=lambda:self._set_zoom(self.zoom/1.2),bg=DARK['glass'],fg='white',relief='flat').pack(side='left',padx=2)
        self.text=tk.Text(right,height=11,wrap='word',bg='#091726',fg=DARK['text'],relief='flat',font=('Tahoma',8),padx=7,pady=7);self.text.pack(fill='x',padx=7,pady=7);self.text.configure(state='disabled');self.action=tk.StringVar();tk.Label(right,textvariable=self.action,bg=DARK['panel'],fg=DARK['muted'],font=('Tahoma',8),wraplength=340,justify='right').pack(fill='x',padx=7,pady=(0,7));self._update_status_buttons();self.after(4000,self._periodic)
    def _set_status(self,k):self.filter.set(k);self._update_status_buttons();self.refresh()
    def _update_status_buttons(self,counts=None):
        for k,(b,col) in self.status_buttons.items():
            selected=self.filter.get()==k;b.configure(bg=col if selected else '#13243A',relief='raised' if selected else 'flat',bd=1 if selected else 0)
            if counts is not None:b.configure(text=f"{k} ({fa(counts.get(k,0))})")
    def refresh(self):
        hidden=self.rich.hidden_review_ids();allrows=[r for r in APPROVAL.list_reviews(limit=3000) if str(r.get('pending_id')) not in hidden];counts={'همه':len(allrows),'Pending':sum(r.get('status') in {'PENDING_REVIEW','NEEDS_REVIEW','EDIT_PENDING'} for r in allrows),'تأییدشده':sum(r.get('status')=='APPROVED' for r in allrows),'ردشده':sum(r.get('status')=='REJECTED' for r in allrows)};self._update_status_buttons(counts)
        f=self.filter.get();rows=allrows
        if f=='Pending':rows=[r for r in rows if r.get('status') in {'PENDING_REVIEW','NEEDS_REVIEW','EDIT_PENDING'}]
        elif f=='تأییدشده':rows=[r for r in rows if r.get('status')=='APPROVED']
        elif f=='ردشده':rows=[r for r in rows if r.get('status')=='REJECTED']
        self.rows=rows
        def rv(r):
            p=r.get('payload') or {};raw=str(r.get('raw_text') or '').strip();desc=raw or str(p.get('description') or '');amt=p.get('amount') or p.get('final_amount') or 0;phase=str(p.get('main_phase') or p.get('construction_stage') or '-');sub=str(p.get('sub_phase') or p.get('expense_category') or '-');fc=r.get('field_confidences') or p.get('field_confidences') or {};conf=fc.get('amount',p.get('confidence',0))
            return ['🖼' if self._path(r) else '📝',r.get('message_date') or '-',TYPE_FA.get(str(p.get('detected_type') or 'UNKNOWN').upper(),'نامشخص'),desc[:110],fmt_money(amt),phase,sub,METHOD_FA.get(str(p.get('payment_method') or 'UNKNOWN').upper(),'نامشخص'),fa(f'{float(conf or 0)*100:.0f}%'),STATUS_FA.get(r.get('status'),r.get('status'))]
        self.table.set_rows(rows,rv)
        for iid,r in getattr(self.table,'_iid_to_row',{}).items():
            st=r.get('status');tag='approved' if st=='APPROVED' else ('rejected' if st=='REJECTED' else ('needs' if st=='NEEDS_REVIEW' else 'pending'))
            try:self.table.tree.item(iid,tags=(tag,))
            except Exception:pass
        self.table.tree.tag_configure('approved',background='#10392E',foreground='#DFFFF3');self.table.tree.tag_configure('rejected',background='#40212A',foreground='#FFE8EC');self.table.tree.tag_configure('needs',background='#443718',foreground='#FFF5CE');self.table.tree.tag_configure('pending',background='#102238',foreground=DARK['text'])
    def _show(self,r):
        pid=str(r.get('pending_id'));path=self._path(r);same=(pid==self._shown_pid and path==getattr(self,'_shown_path',''))
        if not same:
            self._shown_pid=pid;self._shown_path=path;self.preview.delete('all');self._image=None;self._tkimg=None;self.zoom=.7
            if path and Image is not None:
                try:self._image=ImageOps.exif_transpose(Image.open(path)).convert('RGB');self.after(40,self._fit)
                except Exception:pass
            if not self._image:self.preview.create_text(160,120,text='بدون تصویر',fill=DARK['muted'],font=('Tahoma',10))
        p=r.get('payload') or {};lines=[];raw=str(r.get('raw_text') or '').strip()
        if raw:lines.append('متن کاربر / کپشن:\n'+raw)
        try:
            b=APPROVAL.evidence_bundle(pid,window=2);near=[]
            for m in b.get('nearby') or []:
                t=str(m.get('raw_text') or '').strip()
                if t:near.append(t)
            if near:lines.append('پیام‌های مرتبط:\n'+'\n'.join(near))
        except Exception:pass
        ana=DB.get_receipt_analysis(pid) or {};ocr=str(ana.get('ocr_text') or '').strip()
        if ocr:lines.append('OCR/متن داخل تصویر:\n'+ocr[:2500])
        lines.append(f"خلاصه AI: {TYPE_FA.get(str(p.get('detected_type') or 'UNKNOWN').upper(),'نامشخص')} | {fmt_money(p.get('amount') or p.get('final_amount') or 0)}")
        self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('1.0','\n\n'.join(lines));self.text.configure(state='disabled')
    def _fit(self):
        if not self._image:return
        self.preview.update_idletasks();cw=max(200,self.preview.winfo_width()-18);ch=max(160,self.preview.winfo_height()-18);self.zoom=min(.82,cw/self._image.width,ch/self._image.height);self._render()
    def open_editor(self,row=None):
        row=row or self.current
        if not row:return messagebox.showwarning('ثبت دیتا','یک سطر را انتخاب کن.',parent=self)
        UnifiedPendingEditor17(self,row,self.rich,self.refresh)
    def quick_approve(self):
        if not self.current:return
        if self.current.get('status') in {'APPROVED','REJECTED'}:return messagebox.showinfo('ثبت دیتا','این رکورد قبلاً تعیین تکلیف شده است.',parent=self)
        p=dict(self.current.get('payload') or {})
        if not messagebox.askyesno('تأیید سریع',f"{TYPE_FA.get(str(p.get('detected_type') or 'UNKNOWN').upper(),'نامشخص')} | {fmt_money(p.get('amount') or p.get('final_amount') or 0)}\n\nتأیید شود؟",parent=self):return
        try:msg=approve_v17(self.current['pending_id'],p,self.rich);self.action.set(msg);self.refresh();self.on_posted and self.on_posted()
        except Exception as exc:messagebox.showerror('تأیید',str(exc),parent=self)

# ---------- generic market dialogs ----------
class SimpleFormDialog(tk.Toplevel):
    def __init__(self,parent,title,fields:list[tuple[str,str,str]],initial:dict,on_save):
        super().__init__(parent);self.vars={};self.fields=fields;self.on_save=on_save;std_window(self,title,'700x620',(560,420));body=tk.Frame(self,bg=DARK['panel']);body.pack(fill='both',expand=True,padx=12,pady=12);body.grid_columnconfigure(0,weight=1)
        for i,(k,l,kind) in enumerate(fields):tk.Label(body,text=l+':',bg=DARK['panel'],fg=DARK['muted']).grid(row=i,column=1,sticky='e',padx=5,pady=4);v=tk.StringVar(value=str(initial.get(k,'') or ''));self.vars[k]=v
        for i,(k,l,kind) in enumerate(fields):
            v=self.vars[k]
            if kind=='date':w=DateField(body,v,width=32)
            elif kind=='num':w=ttk.Entry(body,textvariable=v,justify='right',width=35);bind_grouped_number(w,v)
            elif kind.startswith('combo:'):w=ttk.Combobox(body,textvariable=v,state='readonly',values=kind.split(':',1)[1].split('|'),width=34)
            else:w=ttk.Entry(body,textvariable=v,justify='right',width=36)
            w.grid(row=i,column=0,sticky='ew',padx=5,pady=4)
        tk.Button(body,text='ذخیره',command=self.save,bg=DARK['blue'],fg='white',relief='flat',padx=16,pady=7).grid(row=len(fields)+1,column=0,columnspan=2,pady=10)
    def save(self):
        d={k:v.get().strip() for k,v in self.vars.items()}
        for k,l,kind in self.fields:
            if kind=='num':d[k]=parse_int(d[k])
        try:self.on_save(d);self.destroy()
        except Exception as exc:messagebox.showerror('ذخیره',str(exc),parent=self)

class ItemGridDialog(tk.Toplevel):
    def __init__(self,parent,title,rows,columns,save_item,new_fields,new_cb,edit_cb):
        super().__init__(parent);std_window(self,title,'980x650',(760,500));self.rows=rows;self.columns=columns;self.new_fields=new_fields;self.new_cb=new_cb;self.edit_cb=edit_cb;bar=tk.Frame(self,bg=DARK['panel']);bar.pack(fill='x',padx=8,pady=7);tk.Button(bar,text='+ ردیف جدید',command=self.add,bg=DARK['blue'],fg='white',relief='flat',padx=10,pady=5).pack(side='right');self.table=SmartTable(self,columns,title=title);self.table.pack(fill='both',expand=True,padx=8,pady=(0,8));self.refresh()
    def refresh(self):self.rows=self.new_cb('list');self.table.set_rows(self.rows,self.edit_cb('row_values'));self.table.set_edit_handler(self.edit)
    def add(self):SimpleFormDialog(self,'ردیف جدید',self.new_fields,{},lambda d:(self.new_cb('save',d),self.refresh()))
    def edit(self,r):SimpleFormDialog(self,'ویرایش ردیف',self.new_fields,r,lambda d:(self.new_cb('save',d,r),self.refresh()))

class MarketTab17(ttk.Frame):
    def __init__(self,parent,market:MarketServiceV17,rich:RichBudgetService):super().__init__(parent,padding=7);self.market=market;self.rich=rich;self.current_contractor=None;self.current_supplier=None;self._build();self.refresh_all()
    def _build(self):
        nb=ttk.Notebook(self);nb.pack(fill='both',expand=True);self.nb=nb
        self.contractors=ttk.Frame(nb,padding=5);self.suppliers=ttk.Frame(nb,padding=5);self.bank=ttk.Frame(nb,padding=5);nb.add(self.contractors,text='پیمانکاران');nb.add(self.suppliers,text='تأمین‌کنندگان');nb.add(self.bank,text='بانک اطلاعاتی')
        self._build_contractors();self._build_suppliers();self._build_bank()
    def _build_contractors(self):
        top=tk.Frame(self.contractors,bg=DARK['surface']);top.pack(fill='x',pady=(0,4));tk.Button(top,text='+ پیمانکار',command=self.add_contractor,bg=DARK['blue'],fg='white',relief='flat',padx=10,pady=5).pack(side='right');tk.Button(top,text='+ قرارداد',command=self.add_contract,bg=DARK['glass'],fg='white',relief='flat',padx=10,pady=5).pack(side='right',padx=3)
        self.contractor_table=SmartTable(self.contractors,[('name','نام / شرکت',170),('nid','کد ملی/اتباع',115),('date','تاریخ قرارداد',105),('subject','موضوع قرارداد',190),('phase','فاز',65),('dur','مدت',70),('amount','رقم قرارداد',125),('paid','واریزی',120),('balance','مانده حساب',120),('phone','تماس',110)],title='پیمانکاران و قراردادها');self.contractor_table.pack(fill='both',expand=True);self.contractor_table.tree.bind('<<TreeviewSelect>>',lambda e:self._select_contractor(),add='+');self.contractor_table.set_edit_handler(self.edit_contractor_contract)
        self.cdetail=ttk.Notebook(self.contractors);self.cdetail.pack(fill='both',expand=True,pady=(5,0));self.cfiles=ttk.Frame(self.cdetail,padding=4);self.cstmt=ttk.Frame(self.cdetail,padding=4);self.cpay=ttk.Frame(self.cdetail,padding=4);self.creport=ttk.Frame(self.cdetail,padding=4);self.cdetail.add(self.cfiles,text='فایل قرارداد و صورت‌وضعیت‌ها');self.cdetail.add(self.cstmt,text='صورت‌وضعیت');self.cdetail.add(self.cpay,text='واریزی‌ها');self.cdetail.add(self.creport,text='گزارش مالی')
        fb=tk.Frame(self.cfiles,bg=DARK['panel']);fb.pack(fill='x');tk.Button(fb,text='آپلود فایل',command=lambda:self.upload_market_file('contractor'),bg=DARK['blue'],fg='white',relief='flat').pack(side='right');self.contract_file_table=SmartTable(self.cfiles,[('kind','نوع',110),('title','عنوان',250),('date','ثبت',140),('path','فایل',300)],title='قرارداد، الحاقیه، صورت‌وضعیت و سایر اسناد');self.contract_file_table.pack(fill='both',expand=True)
        sb=tk.Frame(self.cstmt,bg=DARK['panel']);sb.pack(fill='x');tk.Button(sb,text='+ صورت‌وضعیت',command=self.add_statement,bg=DARK['blue'],fg='white',relief='flat').pack(side='right');tk.Button(sb,text='آیتم‌های صورت‌وضعیت',command=self.open_statement_items,bg=DARK['glass'],fg='white',relief='flat').pack(side='right',padx=3);self.statement_table=SmartTable(self.cstmt,[('no','شماره',70),('date','تاریخ',100),('gross','کارکرد',125),('ded','کسورات',110),('net','خالص',125),('paid','واریزی',125),('bal','مانده',125)],title='صورت‌وضعیت‌ها');self.statement_table.pack(fill='both',expand=True)
        pb=tk.Frame(self.cpay,bg=DARK['panel']);pb.pack(fill='x');tk.Button(pb,text='+ واریزی',command=lambda:self.add_market_payment('contractor'),bg=DARK['blue'],fg='white',relief='flat').pack(side='right');self.contract_payment_table=SmartTable(self.cpay,[('date','تاریخ',100),('amount','مبلغ',125),('method','روش',100),('from','حساب مبدأ',120),('to','حساب گیرنده',140),('owner','صاحب حساب',130),('track','پیگیری',110)],title='واریزی‌های پیمانکار');self.contract_payment_table.pack(fill='both',expand=True)
        self.contract_report_text=tk.Text(self.creport,bg='#091726',fg=DARK['text'],font=('Tahoma',9),wrap='word',relief='flat');self.contract_report_text.pack(fill='both',expand=True)
    def _build_suppliers(self):
        top=tk.Frame(self.suppliers,bg=DARK['surface']);top.pack(fill='x',pady=(0,4));tk.Button(top,text='+ تأمین‌کننده',command=self.add_supplier,bg=DARK['blue'],fg='white',relief='flat',padx=10,pady=5).pack(side='right')
        self.supplier_table=SmartTable(self.suppliers,[('name','تأمین‌کننده',190),('cat','حوزه فعالیت',140),('phone','تماس',110),('invoices','جمع فاکتورها',130),('paid','واریزی',120),('balance','مانده حساب',125),('rating','امتیاز',75)],title='تأمین‌کنندگان بازار');self.supplier_table.pack(fill='both',expand=True);self.supplier_table.tree.bind('<<TreeviewSelect>>',lambda e:self._select_supplier(),add='+');self.supplier_table.set_edit_handler(self.edit_supplier)
        self.sdetail=ttk.Notebook(self.suppliers);self.sdetail.pack(fill='both',expand=True,pady=(5,0));self.sinv=ttk.Frame(self.sdetail,padding=4);self.spay=ttk.Frame(self.sdetail,padding=4);self.sreport=ttk.Frame(self.sdetail,padding=4);self.sdetail.add(self.sinv,text='فاکتورهای دریافتی');self.sdetail.add(self.spay,text='واریزی‌ها');self.sdetail.add(self.sreport,text='گزارش مالی')
        ib=tk.Frame(self.sinv,bg=DARK['panel']);ib.pack(fill='x');tk.Button(ib,text='+ فاکتور',command=self.add_invoice,bg=DARK['blue'],fg='white',relief='flat').pack(side='right');tk.Button(ib,text='آپلود فایل فاکتور',command=lambda:self.upload_market_file('invoice'),bg=DARK['glass'],fg='white',relief='flat').pack(side='right',padx=3);self.invoice_table=SmartTable(self.sinv,[('no','شماره',90),('date','تاریخ',100),('invoice','فاکتور',120),('final','نهایی',120),('disc','تخفیف',100),('paid','پرداخت',120),('bal','مانده',120)],title='فاکتورها — دابل‌کلیک برای اقلام');self.invoice_table.pack(fill='both',expand=True);self.invoice_table.set_edit_handler(self.open_invoice_items)
        pb=tk.Frame(self.spay,bg=DARK['panel']);pb.pack(fill='x');tk.Button(pb,text='+ واریزی',command=lambda:self.add_market_payment('supplier'),bg=DARK['blue'],fg='white',relief='flat').pack(side='right');self.supplier_payment_table=SmartTable(self.spay,[('date','تاریخ',100),('amount','مبلغ',125),('method','روش',100),('from','حساب مبدأ',120),('to','حساب گیرنده',140),('owner','صاحب حساب',130),('track','پیگیری',110)],title='واریزی‌های تأمین‌کننده');self.supplier_payment_table.pack(fill='both',expand=True)
        self.supplier_report_text=tk.Text(self.sreport,bg='#091726',fg=DARK['text'],font=('Tahoma',9),wrap='word',relief='flat');self.supplier_report_text.pack(fill='both',expand=True)
    def _build_bank(self):
        bar=tk.Frame(self.bank,bg=DARK['surface']);bar.pack(fill='x');tk.Button(bar,text='امتیازدهی',command=self.rate_entity,bg=DARK['blue'],fg='white',relief='flat').pack(side='right');self.bank_table=SmartTable(self.bank,[('type','نوع',95),('name','نام/شرکت',200),('cat','تخصص/حوزه',150),('city','شهر',100),('phone','تماس',110),('total','اسناد/کارکرد',125),('paid','واریزی',120),('balance','مانده',120),('rating','امتیاز',75)],title='بانک اطلاعاتی پیمانکاران و تأمین‌کنندگان');self.bank_table.pack(fill='both',expand=True)
    def refresh_all(self):self.refresh_contractors();self.refresh_suppliers();self.refresh_bank()
    def add_contractor(self):
        fields=[('first_name','نام','entry'),('last_name','نام خانوادگی','entry'),('national_id','کد ملی','entry'),('foreign_id','کد اتباع','entry'),('phone','شماره تماس','entry'),('city','شهر','entry'),('category','تخصص','entry')]
        SimpleFormDialog(self,'پیمانکار جدید',fields,{},lambda d:(self.market.save_entity({**d,'entity_type':'CONTRACTOR'}),self.refresh_all()))
    def add_supplier(self):
        fields=[('company_name','نام فروشگاه/شرکت','entry'),('first_name','نام شخص','entry'),('last_name','نام خانوادگی','entry'),('category','حوزه فعالیت','entry'),('phone','شماره تماس','entry'),('city','شهر','entry'),('national_id','شناسه/کد ملی','entry')]
        SimpleFormDialog(self,'تأمین‌کننده جدید',fields,{},lambda d:(self.market.save_entity({**d,'entity_type':'SUPPLIER'}),self.refresh_all()))
    def add_contract(self):
        ents=self.market.list_entities('CONTRACTOR')
        if not ents:return messagebox.showwarning('قرارداد','ابتدا پیمانکار ثبت کن.',parent=self)
        names={f"{e.get('first_name','')} {e.get('last_name','')} {e.get('company_name','')} [{e['entity_id']}]".strip():e['entity_id'] for e in ents};fields=[('contractor','پیمانکار','combo:'+'|'.join(names)),('contract_date_shamsi','تاریخ قرارداد','date'),('subject','موضوع قرارداد','entry'),('phase_no','شماره فاز','entry'),('duration_days','مدت قرارداد (روز)','num'),('contract_amount','رقم قرارداد','num'),('start_date_shamsi','شروع','date'),('end_date_shamsi','پایان','date')]
        def save(d):d['contractor_id']=names.get(d.pop('contractor'));self.market.save_contract(d);self.refresh_all()
        SimpleFormDialog(self,'قرارداد پیمانکار',fields,{},save)
    def refresh_contractors(self):
        rows=self.market.list_contracts();self.contractor_table.set_rows(rows,lambda r:[(str(r.get('company_name') or '') or f"{r.get('first_name','')} {r.get('last_name','')}").strip(),self.market.get_entity(r['contractor_id']).get('national_id') or self.market.get_entity(r['contractor_id']).get('foreign_id') or '-',r.get('contract_date_shamsi') or '-',r.get('subject') or '-',fa(r.get('phase_no') or '-'),fa(r.get('duration_days') or 0),fmt_money(r.get('contract_amount')),fmt_money(r.get('paid_total')),fmt_money(r.get('balance')),r.get('phone') or '-'])
    def _select_contractor(self):
        rs=self.contractor_table.selected_rows();self.current_contractor=rs[0] if rs else None;self.refresh_contractor_detail()
    def refresh_contractor_detail(self):
        r=self.current_contractor
        if not r:return
        files=self.market.list_files(contract_id=r['contract_id']);self.contract_file_table.set_rows(files,lambda x:[x.get('file_kind') or '-',x.get('title') or '-',x.get('created_at') or '-',x.get('original_name') or '-']);sts=self.market.list_statements(r['contract_id']);self.statement_table.set_rows(sts,lambda x:[x.get('statement_no') or '-',x.get('statement_date_shamsi') or '-',fmt_money(x.get('gross_amount')),fmt_money(x.get('deductions')),fmt_money(x.get('net_amount')),fmt_money(x.get('paid_amount')),fmt_money(x.get('balance'))]);pays=self.market.list_payments(r['contractor_id']);self.contract_payment_table.set_rows(pays,lambda x:[x.get('payment_date_shamsi') or '-',fmt_money(x.get('amount')),x.get('method') or '-',x.get('from_account') or '-',x.get('to_account') or '-',x.get('receiver_account_owner') or '-',x.get('tracking_no') or '-']);lines=[f"قرارداد: {r.get('subject') or '-'}",f"رقم قرارداد: {fmt_money(r.get('contract_amount'))}",f"جمع صورت‌وضعیت خالص: {fmt_money(r.get('statement_total'))}",f"جمع واریزی: {fmt_money(r.get('paid_total'))}",f"مانده حساب پیمانکار: {fmt_money(r.get('balance'))}",'']
        for x in sts:lines.append(f"صورت‌وضعیت {x.get('statement_no') or '-'} | خالص {fmt_money(x.get('net_amount'))} | واریزی {fmt_money(x.get('paid_amount'))} | مانده {fmt_money(x.get('balance'))}")
        self.contract_report_text.delete('1.0','end');self.contract_report_text.insert('1.0','\n'.join(lines))
    def edit_contractor_contract(self,r):
        e=self.market.get_entity(r['contractor_id']);fields=[('first_name','نام','entry'),('last_name','نام خانوادگی','entry'),('national_id','کد ملی','entry'),('foreign_id','کد اتباع','entry'),('phone','تماس','entry')];SimpleFormDialog(self,'ویرایش پیمانکار',fields,e,lambda d:(self.market.save_entity({**e,**d},e['entity_id']),self.refresh_all()))
    def upload_market_file(self,kind):
        path=filedialog.askopenfilename(parent=self,filetypes=[('اسناد','*.pdf *.xlsx *.xls *.png *.jpg *.jpeg'),('همه','*.*')]);
        if not path:return
        if kind=='contractor' and self.current_contractor:self.market.add_file(path,entity_id=self.current_contractor['contractor_id'],contract_id=self.current_contractor['contract_id'],file_kind='CONTRACT_OR_STATEMENT');self.refresh_contractor_detail()
        elif kind=='invoice' and self.current_supplier:
            invs=self.market.list_invoices(self.current_supplier['entity_id']);iid=(invs[0]['invoice_id'] if invs else '');self.market.add_file(path,entity_id=self.current_supplier['entity_id'],invoice_id=iid,file_kind='INVOICE');self.refresh_supplier_detail()
    def add_statement(self):
        if not self.current_contractor:return
        fields=[('statement_no','شماره صورت‌وضعیت','entry'),('statement_date_shamsi','تاریخ','date'),('gross_amount','مبلغ کارکرد','num'),('deductions','کسورات','num'),('net_amount','مبلغ خالص','num'),('notes','توضیحات','entry')];SimpleFormDialog(self,'صورت‌وضعیت جدید',fields,{},lambda d:(self.market.save_statement({**d,'contract_id':self.current_contractor['contract_id']}),self.refresh_contractor_detail()))
    def open_statement_items(self):
        if not self.current_contractor:return
        sts=self.statement_table.selected_rows();
        if not sts:return messagebox.showinfo('صورت‌وضعیت','یک صورت‌وضعیت را انتخاب کن.',parent=self)
        sid=sts[0]['statement_id'];fields=[('description','شرح آیتم','entry'),('unit','واحد','entry'),('contract_rate','نرخ قرارداد','num'),('quantity','حجم/مقدار','entry'),('total','مبلغ','num'),('source','منبع AI/دستی','entry')]
        def cb(op,d=None,r=None):
            if op=='list':return self.market.list_statement_items(sid)
            if op=='save':d['statement_id']=sid;self.market.save_statement_item(d,r.get('item_id') if r else None)
        ItemGridDialog(self,'آیتم‌های صورت‌وضعیت',[],[('desc','شرح',240),('unit','واحد',80),('rate','نرخ قرارداد',120),('qty','حجم',90),('total','مبلغ',125),('source','منبع',100)],None,fields,cb,lambda op:(lambda x:[x.get('description'),x.get('unit'),fmt_money(x.get('contract_rate')),fa(x.get('quantity')),fmt_money(x.get('total')),x.get('source')]) if op=='row_values' else None)
    def add_market_payment(self,kind):
        r=self.current_contractor if kind=='contractor' else self.current_supplier
        if not r:return
        eid=r['contractor_id'] if kind=='contractor' else r['entity_id'];fields=[('payment_date_shamsi','تاریخ','date'),('amount','مبلغ','num'),('method','روش پرداخت','entry'),('from_account','حساب مبدأ','entry'),('to_account','حساب مقصد','entry'),('receiver_account_owner','صاحب حساب گیرنده','entry'),('tracking_no','شماره پیگیری','entry')]
        initial={'from_account':'تنخواه'}
        def save(d):d['entity_id']=eid;d['contract_id']=r.get('contract_id') or '';self.market.save_payment(d);self.refresh_all();self.refresh_contractor_detail() if kind=='contractor' else self.refresh_supplier_detail()
        SimpleFormDialog(self,'ثبت واریزی',fields,initial,save)
    def refresh_suppliers(self):
        rows=self.market.list_entities('SUPPLIER');self.supplier_table.set_rows(rows,lambda r:[r.get('company_name') or f"{r.get('first_name','')} {r.get('last_name','')}",r.get('category') or '-',r.get('phone') or '-',fmt_money(r.get('document_total')),fmt_money(r.get('paid_total')),fmt_money(r.get('balance')),fa(r.get('rating_total'))])
    def _select_supplier(self):rs=self.supplier_table.selected_rows();self.current_supplier=rs[0] if rs else None;self.refresh_supplier_detail()
    def edit_supplier(self,r):
        fields=[('company_name','نام فروشگاه/شرکت','entry'),('first_name','نام شخص','entry'),('last_name','نام خانوادگی','entry'),('category','حوزه فعالیت','entry'),('phone','تماس','entry'),('city','شهر','entry')];SimpleFormDialog(self,'ویرایش تأمین‌کننده',fields,r,lambda d:(self.market.save_entity({**r,**d},r['entity_id']),self.refresh_all()))
    def add_invoice(self):
        if not self.current_supplier:return
        fields=[('invoice_no','شماره فاکتور','entry'),('invoice_date_shamsi','تاریخ فاکتور','date'),('invoice_amount','مبلغ فاکتور','num'),('final_amount','مبلغ نهایی','num'),('discount_amount','تخفیف','num'),('notes','توضیحات','entry')];SimpleFormDialog(self,'فاکتور تأمین‌کننده',fields,{},lambda d:(self.market.save_invoice({**d,'supplier_id':self.current_supplier['entity_id']}),self.refresh_supplier_detail(),self.refresh_suppliers()))
    def refresh_supplier_detail(self):
        r=self.current_supplier
        if not r:return
        invs=self.market.list_invoices(r['entity_id']);self.invoice_table.set_rows(invs,lambda x:[x.get('invoice_no') or '-',x.get('invoice_date_shamsi') or '-',fmt_money(x.get('invoice_amount')),fmt_money(x.get('final_amount')),fmt_money(x.get('discount_amount')),fmt_money(x.get('paid_amount')),fmt_money(x.get('balance'))]);pays=self.market.list_payments(r['entity_id']);self.supplier_payment_table.set_rows(pays,lambda x:[x.get('payment_date_shamsi') or '-',fmt_money(x.get('amount')),x.get('method') or '-',x.get('from_account') or '-',x.get('to_account') or '-',x.get('receiver_account_owner') or '-',x.get('tracking_no') or '-']);lines=[f"تأمین‌کننده: {r.get('company_name') or r.get('first_name') or '-'}",f"جمع فاکتورها: {fmt_money(sum(int(x.get('final_amount') or 0) for x in invs))}",f"جمع واریزی: {fmt_money(sum(int(x.get('amount') or 0) for x in pays))}",'']
        for x in invs:lines.append(f"فاکتور {x.get('invoice_no') or '-'} | نهایی {fmt_money(x.get('final_amount'))} | پرداخت {fmt_money(x.get('paid_amount'))} | مانده {fmt_money(x.get('balance'))}")
        self.supplier_report_text.delete('1.0','end');self.supplier_report_text.insert('1.0','\n'.join(lines))
    def open_invoice_items(self,r):
        iid=r['invoice_id'];fields=[('description','شرح قلم','entry'),('unit','واحد','entry'),('quantity','مقدار','entry'),('unit_rate','قیمت واحد','num'),('total','مبلغ','num'),('price_id','Price ID','entry')]
        def cb(op,d=None,row=None):
            if op=='list':return self.market.list_invoice_items(iid)
            if op=='save':d['invoice_id']=iid;self.market.save_invoice_item(d,row.get('item_id') if row else None)
        ItemGridDialog(self,'اقلام فاکتور',[],[('desc','شرح',240),('unit','واحد',80),('qty','مقدار',90),('rate','قیمت واحد',120),('total','مبلغ',125),('price','Price ID',130)],None,fields,cb,lambda op:(lambda x:[x.get('description'),x.get('unit'),fa(x.get('quantity')),fmt_money(x.get('unit_rate')),fmt_money(x.get('total')),x.get('price_id') or '-']) if op=='row_values' else None)
    def refresh_bank(self):
        rows=self.market.list_entities();self.bank_table.set_rows(rows,lambda r:['پیمانکار' if r['entity_type']=='CONTRACTOR' else 'تأمین‌کننده',r.get('company_name') or f"{r.get('first_name','')} {r.get('last_name','')}",r.get('category') or '-',r.get('city') or '-',r.get('phone') or '-',fmt_money(r.get('document_total')),fmt_money(r.get('paid_total')),fmt_money(r.get('balance')),fa(r.get('rating_total'))])
    def rate_entity(self):
        rows=self.bank_table.selected_rows();
        if not rows:return
        r=rows[0];old=self.market.get_rating(r['entity_id']);fields=[('quality','کیفیت ۰ تا ۱۰','entry'),('price','قیمت ۰ تا ۱۰','entry'),('punctuality','خوش‌قولی ۰ تا ۱۰','entry'),('speed','سرعت ۰ تا ۱۰','entry'),('cooperation','همکاری ۰ تا ۱۰','entry'),('document_quality','کیفیت اسناد ۰ تا ۱۰','entry'),('financial_history','سابقه مالی ۰ تا ۱۰','entry'),('notes','توضیحات','entry')];SimpleFormDialog(self,'امتیازدهی',fields,old,lambda d:(self.market.save_rating(r['entity_id'],d),self.refresh_bank(),self.refresh_suppliers()))

# ---------- cheque / phase windows ----------
class ChequeEditDialog17(tk.Toplevel):
    def __init__(self,parent,row,on_refresh):
        super().__init__(parent);self.row=row;self.on_refresh=on_refresh;self.vars={};std_window(self,'مشخصات چک','760x700',(620,520));body=tk.Frame(self,bg=DARK['panel']);body.pack(fill='both',expand=True,padx=12,pady=12);body.grid_columnconfigure(0,weight=1)
        vals={'issue':row.get('issue_date_shamsi') or '','due':row.get('due_date_shamsi') or '','amount':group_int(row.get('amount') or 0),'issuer_name':row.get('issuer_name') or '','receiver_name':row.get('receiver_name') or '','issuer_bank':row.get('issuer_bank') or '','cheque_serial':row.get('cheque_serial') or '','description':row.get('description') or '','cheque_type':CHEQUE_TYPE_FA.get(str(row.get('cheque_type') or 'PHYSICAL').upper(),'فیزیکی'),'registration_state':REG_FA.get(str(row.get('registration_state') or 'UNREGISTERED').upper(),'ثبت‌نشده'),'is_guarantee':'1' if row.get('is_guarantee') else '0'}
        fields=[('issue','تاریخ صدور','date'),('due','تاریخ سررسید','date'),('amount','مبلغ','num'),('issuer_name','صاحب حساب','entry'),('receiver_name','گیرنده','entry'),('issuer_bank','بانک','entry'),('cheque_serial','شماره/صیادی','entry'),('cheque_type','نوع چک','type'),('registration_state','وضعیت ثبت','reg'),('description','بابت','entry')]
        for i,(k,l,kind) in enumerate(fields):v=tk.StringVar(value=str(vals[k]));self.vars[k]=v;tk.Label(body,text=l+':',bg=DARK['panel'],fg=DARK['muted']).grid(row=i,column=1,sticky='e',padx=5,pady=4)
        for i,(k,l,kind) in enumerate(fields):
            v=self.vars[k]
            if kind=='date':w=DateField(body,v,width=30)
            elif kind=='type':w=ttk.Combobox(body,textvariable=v,state='readonly',values=list(CHEQUE_TYPE_BY_FA),width=32)
            elif kind=='reg':w=ttk.Combobox(body,textvariable=v,state='readonly',values=list(REG_BY_FA),width=32)
            else:w=ttk.Entry(body,textvariable=v,width=34,justify='right');bind_grouped_number(w,v) if kind=='num' else None
            w.grid(row=i,column=0,padx=5,pady=4,sticky='ew')
        self.guarantee=tk.BooleanVar(value=bool(row.get('is_guarantee')));tk.Checkbutton(body,text='بابت ضمانت (در تعهد مالی محاسبه نشود)',variable=self.guarantee,bg=DARK['panel'],fg=DARK['text'],selectcolor=DARK['surface'],activebackground=DARK['panel'],activeforeground='white').grid(row=len(fields),column=0,columnspan=2,sticky='e',pady=7)
        tk.Label(body,text=f"وضعیت وصول: {v16.d12.fa_status(row.get('status'))} — از رویداد واقعی پاس/برگشت تعیین می‌شود.",bg=DARK['panel'],fg=DARK['orange']).grid(row=len(fields)+1,column=0,columnspan=2,sticky='e',pady=5);tk.Button(body,text='ذخیره',command=self.save,bg=DARK['blue'],fg='white',relief='flat',padx=15,pady=7).grid(row=len(fields)+2,column=0,columnspan=2,pady=10)
    def save(self):
        try:
            ish=normalize_shamsi(self.vars['issue'].get());due=normalize_shamsi(self.vars['due'].get());
            if not ish or not due:raise ValueError('تاریخ صدور/سررسید نامعتبر است.')
            DB.update_cheque_details(self.row['cheque_id'],amount=parse_int(self.vars['amount'].get()),issue_date=shamsi_to_gregorian(ish),issue_date_shamsi=ish,due_date=shamsi_to_gregorian(due),due_date_shamsi=due,issuer_name=self.vars['issuer_name'].get().strip(),cheque_type=CHEQUE_TYPE_BY_FA.get(self.vars['cheque_type'].get(),'PHYSICAL'),receiver_name=self.vars['receiver_name'].get().strip(),issuer_bank=self.vars['issuer_bank'].get().strip(),cheque_serial=self.vars['cheque_serial'].get().strip(),description=self.vars['description'].get().strip(),is_guarantee=self.guarantee.get())
            with DB.tx() as con:con.execute('UPDATE cheques SET registration_state=?,updated_at=? WHERE cheque_id=?',(REG_BY_FA.get(self.vars['registration_state'].get(),'UNREGISTERED'),datetime.now().isoformat(timespec='seconds'),self.row['cheque_id']))
            self.destroy();self.on_refresh()
        except Exception as exc:messagebox.showerror('چک',str(exc),parent=self)

class PhaseDetailDialog17(v16.PhaseDetailDialog163):
    def __init__(self,parent,rich,phase_no,phase_name,on_refresh):super().__init__(parent,rich,phase_no,phase_name,on_refresh);std_window(self,f'ریز فاز {phase_no:02d} — {phase_name}','1180x760',(900,580))

class PriceDetailDialog17(PriceDetailDialog):
    def __init__(self,parent,rich,row,on_refresh):super().__init__(parent,rich,row,on_refresh);std_window(self,f"جزئیات قیمت — {row.get('description') or ''}",'1020x720',(760,540))

# ---------- system status dialog ----------
class SystemStatusDialog17(tk.Toplevel):
    def __init__(self,parent):
        super().__init__(parent)
        std_window(self,'سیستم — وضعیت سرویس‌ها','860x620',(680,460))
        self.parent_app=parent
        head=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1)
        head.pack(fill='x',padx=8,pady=8)
        tk.Label(head,text='وضعیت سیستم',bg=DARK['surface'],fg=DARK['text'],font=('Tahoma',12,'bold')).pack(side='right',padx=10,pady=8)
        tk.Button(head,text='بروزرسانی',command=self.refresh,bg=DARK['blue'],fg='white',activebackground='#1B79DB',activeforeground='white',relief='flat',padx=12,pady=5).pack(side='left',padx=8)
        self.text=tk.Text(self,wrap='word',bg=DARK['panel'],fg=DARK['text'],insertbackground='white',relief='flat',font=('Tahoma',9),padx=14,pady=12)
        self.text.pack(fill='both',expand=True,padx=8,pady=(0,8))
        self.refresh()
    def refresh(self):
        try:
            snap=preflight_snapshot(BASE_DIR)
            h=DB.health_check();o=SERVICE.overview();v=SERVICE.budget.latest_version();p=SERVICE.project.get_project()
            proc=getattr(self.parent_app,'_bot_process',None)
            bot_alive=proc is not None and proc.poll() is None
            ready=(BASE_DIR/'runtime'/'telegram_bot_ready.flag').exists()
            bot_state='آنلاین' if bot_alive and ready else ('در حال اتصال' if bot_alive else 'خاموش')
            lines=[
                f"پروژه: {p.get('name') or '-'}",
                f"نسخه برنامه: {VERSION}",
                f"SQLite: {'سالم' if str(h.get('sqlite_integrity')).lower()=='ok' else h.get('sqlite_integrity')}",
                f"نسخه Schema: {h.get('schema_version')}",
                f"ربات تلگرام: {bot_state}",
                f"شناسه گروه: {snap.get('group_id') or '-'}",
                f"Gemini API Key: {'موجود' if snap.get('gemini_key') else 'ناموجود'}",
                f"Gemini SDK: {'آماده' if snap.get('gemini_sdk') else 'نصب نیست'}",
                f"Telegram SDK: {'آماده' if snap.get('telegram_sdk') else 'نصب نیست'}",
                f"Pillow: {'آماده' if snap.get('pil_sdk') else 'نصب نیست'}",
                f"jdatetime: {'آماده' if snap.get('jdatetime_sdk') else 'نصب نیست'}",
                f"نسخه برآورد: {v.get('version_no') if v else '-'}",
                f"Pending Sync: {getattr(o,'pending_sync',0)}",
                f"Failed Sync: {getattr(o,'failed_sync',0)}",
                '',
                'آخرین لاگ ربات:',
                runtime_tail(getattr(self.parent_app,'_bot_log',''),20) if getattr(self.parent_app,'_bot_log',None) else 'لاگ ربات در دسترس نیست.'
            ]
            txt='\n'.join(str(x) for x in lines)
        except Exception as exc:
            txt=f'خواندن وضعیت سیستم ناموفق بود:\n{exc}'
        self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('1.0',txt);self.text.configure(state='disabled')

# ---------- main dashboard ----------
class Stage17Dashboard(v16.Stage163Dashboard):
    def __init__(self):
        # Migrate new market/guarantee structures before Stage-12 overview queries.
        self.market=MarketServiceV17(DB,BASE_DIR);self.history=HistoricalLearningV17(DB);self._budget_sync_message=''
        super().__init__();self.title('BARKAV — Engineering & Construction — Version 17.4');self.after(300,self._ensure_v17_budget);self.after(800,self._seed_historical)
    def _style(self):
        super()._style();st=ttk.Style(self);st.configure('TNotebook.Tab',padding=(16,8),font=('Tahoma',8,'bold'),background='#102034',foreground='#71869F');st.map('TNotebook.Tab',background=[('selected','#176FD1'),('active','#1B3F62')],foreground=[('selected','#FFFFFF'),('active','#EAF5FF')],expand=[('selected',(1,2,1,0))]);st.configure('Treeview',rowheight=26,background='#0B1828',fieldbackground='#0B1828',foreground='#EEF5FF');st.configure('Treeview.Heading',background='#152A43',foreground='#EEF5FF',font=('Tahoma',7,'bold'))
    def _build(self):
        # Same V15 functional skeleton; only presentation and additive tabs change.
        top=tk.Frame(self,bg='#081421',height=58,highlightbackground=DARK['line'],highlightthickness=1);top.pack(fill='x')
        brand=tk.Frame(top,bg='#081421');brand.pack(side='left',padx=10,pady=5);logo=BASE_DIR/'assets'/'barkav_brand_header.png';loaded=False
        if logo.exists() and Image is not None:
            try:im=Image.open(logo).convert('RGB');im.thumbnail((190,50));self._logo_img=ImageTk.PhotoImage(im);tk.Label(brand,image=self._logo_img,bg='white').pack(side='left',padx=(0,8));loaded=True
            except Exception:pass
        if not loaded:bt=tk.Frame(brand,bg='#081421');bt.pack(side='left');tk.Label(bt,text='BARKAV',bg='#081421',fg='white',font=('Arial',13,'bold')).pack(anchor='w');tk.Label(bt,text='ENGINEERING & CONSTRUCTION',bg='#081421',fg='#91A5BB',font=('Arial',6)).pack(anchor='w')
        right=tk.Frame(top,bg='#081421');right.pack(side='right',padx=12,pady=5);self.project_name_top=tk.StringVar(value='پروژه');self.datetime_top=tk.StringVar(value='');tk.Label(right,textvariable=self.project_name_top,bg='#081421',fg='#A7D9FF',font=('Tahoma',8,'bold')).pack(side='right',padx=7);tk.Label(right,textvariable=self.datetime_top,bg='#081421',fg=DARK['text'],font=('Tahoma',7)).pack(side='right',padx=10)
        tools=tk.Frame(top,bg='#081421');tools.pack(side='right',padx=8)
        for text,cmd,tip in [('💾 ذخیره',self.manual_save,'بکاپ دستی'),('ذخیره با نام',self.save_as,'کپی مستقل دیتابیس'),('↶ بازگشت',self.undo,'Undo'),('↷ جلو',self.redo,'Redo'),('📚 تاریخچه',self.import_historical_reference,'ورود تاریخچه Telegram JSON یا WhatsApp ZIP فقط برای یادگیری'),('📦 بسته توسعه',self.export_development_package,'ساخت بسته امن برای ادامه توسعه در چت جدید'),('🔄',self.refresh_all,'بروزرسانی'),('⚙ سیستم',self.show_health,'وضعیت ربات، AI، دیتابیس و سرویس‌ها')]:b=tk.Button(tools,text=text,command=cmd,bg='#14263A',fg='white',activebackground='#176FD1',activeforeground='white',relief='flat',font=('Tahoma',7),padx=7,pady=4);b.pack(side='right',padx=2);add_tooltip(b,tip)
        self.notebook=ttk.Notebook(self);self.notebook.pack(fill='both',expand=True,padx=6,pady=5);self._build_overview();self._build_manager();self._build_financial();self._build_cheques();self._build_sales();self._build_reconciliation();self._build_reports();self._build_market();self._attach_common_tooltips(self);self._tick_clock()
        # intentionally no duplicate "عملکرد سیستم" tab; the System button above owns diagnostics.
    def _build_approval_center(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.approval_tab=tab;self.notebook.insert(1,tab,text='ثبت دیتا');self.approval_center=DataEntryCenter17(tab,self.rich,on_posted=self.refresh_all);self.approval_center.pack(fill='both',expand=True)
        if self._bot_process:self.approval_center.set_bot_process(self._bot_process,self._bot_log)
    def _build_market(self):
        tab=ttk.Frame(self.notebook,padding=4);self.notebook.add(tab,text='پیمانکار-بازار');self.market_tab=MarketTab17(tab,self.market,self.rich);self.market_tab.pack(fill='both',expand=True)
    def _build_cheques(self):
        tab=ttk.Frame(self.notebook,padding=6);self.notebook.add(tab,text='چک‌ها');bar=ttk.Frame(tab);bar.pack(fill='x',pady=(0,4));self.ch_filter=tk.StringVar(value='همه');c=ttk.Combobox(bar,textvariable=self.ch_filter,state='readonly',values=['همه','ثبت‌نشده','ثبت‌شده','باز','پاس‌شده','ضمانتی'],width=14);c.pack(side='right');c.bind('<<ComboboxSelected>>',lambda e:self.refresh_cheques());ttk.Button(bar,text='✏️ ویرایش چک',command=self.edit_cheque).pack(side='right',padx=3)
        self.cheque_table=SmartTable(tab,[('issue','تاریخ صدور',100),('due','سررسید',105),('amount','مبلغ',125),('issuer','صاحب حساب',120),('type','فیزیکی/دیجیتال',105),('reg','وضعیت ثبت',90),('guarantee','ضمانت',75),('receiver','گیرنده',120),('bank','بانک',100),('serial','شماره/صیادی',115),('desc','بابت',200),('status','وضعیت وصول',95),('id','Cheque ID',145)],title='چک‌ها');self.cheque_table.pack(fill='both',expand=True);self.cheque_table.set_edit_handler(self.edit_cheque_row);self.cheque_table.set_delete_handler(self._cancel_cheque_row)
    def refresh_cheques(self):
        rows=SERVICE.list_cheques(open_only=False);f=getattr(self,'ch_filter',tk.StringVar(value='همه')).get()
        if f=='ثبت‌نشده':rows=[r for r in rows if str(r.get('registration_state') or 'UNREGISTERED')=='UNREGISTERED']
        elif f=='ثبت‌شده':rows=[r for r in rows if str(r.get('registration_state') or '')=='REGISTERED']
        elif f=='باز':rows=[r for r in rows if r.get('status') in {'ISSUED','DUE','PENDING_DUE'} and not r.get('is_guarantee')]
        elif f=='پاس‌شده':rows=[r for r in rows if r.get('status')=='CASHED']
        elif f=='ضمانتی':rows=[r for r in rows if int(r.get('is_guarantee') or 0)==1]
        for r in rows:r['_sum_amount']=int(r.get('amount') or 0)
        self.cheque_table.set_rows(rows,lambda r:[r.get('issue_date_shamsi') or '-',r.get('due_date_shamsi') or '-',fmt_money(r['amount']),r.get('issuer_name') or '-',CHEQUE_TYPE_FA.get(str(r.get('cheque_type') or 'PHYSICAL').upper(),'فیزیکی'),REG_FA.get(str(r.get('registration_state') or 'UNREGISTERED').upper(),'ثبت‌نشده'),'بله' if r.get('is_guarantee') else 'خیر',r.get('receiver_name') or '-',r.get('issuer_bank') or '-',r.get('cheque_serial') or '-',r.get('description') or r.get('expense_description') or '-',v16.d12.fa_status(r['status']),r['cheque_id']])
    def edit_cheque_row(self,r):ChequeEditDialog17(self,r,self.refresh_all)
    def open_phase_by_no(self,no:int):
        row=next((r for r in self._phase_summary_live() if r['phase_no']==int(no)),None)
        if row:PhaseDetailDialog17(self,self.rich,int(no),row['phase'],self.refresh_all)
    def _build_reports(self):
        # Reuse the V16 report design, then replace detail handlers with V17 windows.
        super()._build_reports();self.price_table.set_edit_handler(lambda r:PriceDetailDialog17(self,self.rich,r,self.refresh_reports));self.phase_table.set_edit_handler(lambda r:self.open_phase_by_no(r['phase_no']))
    def refresh_health(self):
        # V17 intentionally removed the duplicate health tab.  Inherited refresh_all()
        # still calls refresh_health(), so this method must be safe without health_text.
        return None
    def show_health(self):
        SystemStatusDialog17(self)
    def refresh_all(self):
        super().refresh_all()
        try:self.market_tab.refresh_all()
        except Exception:pass
    def _ensure_v17_budget(self):
        marker=BASE_DIR/'data'/'.budget_sync_v17';book=BASE_DIR/'phase_budget_current.xlsx'
        if marker.exists() or not book.exists():return
        try:
            res=self.rich.import_workbook(book,'BARKAV V17 bundled estimate',preserve_manual=True);marker.write_text(datetime.now().isoformat(),encoding='utf-8');self._budget_sync_message=f'{res.phase_count} فاز / {res.phase_item_count} ردیف';self.refresh_reports()
        except Exception as exc:self._budget_sync_message='خطا: '+str(exc)
    def _seed_historical(self):
        marker=BASE_DIR/'data'/'.historical_seed_v17';seed=BASE_DIR/'docs'/'handoff'/'historical_seed_barkav0.jsonl'
        if marker.exists() or not seed.exists():return
        try:
            n=0
            for line in seed.read_text(encoding='utf-8').splitlines():
                if not line.strip():continue
                d=json.loads(line);self.history.add(**d);n+=1
            marker.write_text(str(n),encoding='utf-8')
        except Exception:pass

    def import_historical_reference(self):
        path=filedialog.askopenfilename(parent=self,title='ورود تاریخچه فقط برای یادگیری',filetypes=[('Telegram JSON / WhatsApp ZIP','*.json *.zip'),('JSON','*.json'),('ZIP','*.zip')])
        if not path:return
        try:
            pp=Path(path);label=simpledialog.askstring('نام پروژه تاریخی','یک نام برای این پروژه تاریخی وارد کن:',initialvalue=('barkav0' if pp.suffix.lower()=='.zip' else 'telegram_history'),parent=self)
            if not label:return
            if pp.suffix.lower()=='.json':n=self.history.import_telegram_json(pp,label)
            elif pp.suffix.lower()=='.zip':n=self.history.import_whatsapp_zip(pp,label)
            else:raise ValueError('فرمت پشتیبانی‌شده JSON یا ZIP است. برای RAR ابتدا result.json را Extract کن.')
            messagebox.showinfo('تاریخچه',f'{fa(n)} نمونه متنی به بانک یادگیری تاریخی اضافه شد.\nاین داده‌ها وارد حساب پروژه جاری نمی‌شوند.',parent=self)
        except Exception as exc:messagebox.showerror('تاریخچه',str(exc),parent=self)

    def export_development_package(self):
        dest=filedialog.asksaveasfilename(parent=self,defaultextension='.zip',initialfile=f'BARKAV_Development_Package_{VERSION}.zip',filetypes=[('ZIP','*.zip')])
        if not dest:return
        try:
            result=build_development_package(BASE_DIR,Path(dest),VERSION)
            messagebox.showinfo('بسته توسعه',f"بسته توسعه ساخته شد:\n{result['path']}\n\nفایل‌های حساس و دیتابیس زنده وارد بسته نشده‌اند.\nتعداد فایل‌ها: {fa(result['file_count'])}",parent=self)
        except Exception as exc:
            messagebox.showerror('بسته توسعه',str(exc),parent=self)

    def edit_transaction_row(self,r):
        if r.get('pending_id'):
            p=DB.get_pending_item(r['pending_id']);row=dict(p or {});row['raw_text']=_raw_text_for_pending(r['pending_id']);UnifiedPendingEditor17(self,row,self.rich,self.refresh_all);return
        super().edit_transaction_row(r)
    def edit_expense_row(self,r):
        if r.get('pending_id'):
            p=DB.get_pending_item(r['pending_id']);row=dict(p or {});row['raw_text']=_raw_text_for_pending(r['pending_id']);UnifiedPendingEditor17(self,row,self.rich,self.refresh_all);return
        super().edit_expense_row(r)

if __name__=='__main__':Stage17Dashboard().mainloop()
