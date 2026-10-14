from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

try:
    from PIL import Image, ImageOps, ImageTk
except Exception:
    Image=ImageOps=ImageTk=None  # type: ignore

from dashboard_stage15 import Stage15Dashboard
import dashboard_stage12 as d12
from dashboard_stage14 import APPROVAL
from dashboard_stage12 import (
    DB, SERVICE, CONFIG, BASE_DIR, SmartTable, CompactTable, add_tooltip,
    DateField, bind_grouped_number, group_int, parse_int, money,
)
from revenue_service import normalize_shamsi, shamsi_to_gregorian, gregorian_to_shamsi
from export_utils import export_pdf, export_xlsx, print_file
from budget_rich_v163 import RichBudgetService, as_int, as_float, norm

VERSION='16.3'

# ---------- visual identity ----------
DARK={
    'bg':'#07111F','surface':'#0B1727','panel':'#0F1C2D','panel2':'#122238','glass':'#15263B',
    'line':'#263B55','text':'#EEF5FF','muted':'#91A4BC','blue':'#2684FF','violet':'#6E55E8',
    'green':'#2EC58D','orange':'#F3A83B','red':'#F15B64','cyan':'#32C7D9','yellow':'#F5C451',
}
FA_MAP=str.maketrans('0123456789','۰۱۲۳۴۵۶۷۸۹')

def fa(s:Any)->str:return str(s).translate(FA_MAP)
def fmt_money(v:Any,fa_num:bool=True)->str:
    try:s=f"{int(float(v or 0)):,} تومان"
    except Exception:s='-'
    return fa(s) if fa_num else s

def short_money(v:Any)->str:
    try:n=float(v or 0)
    except Exception:return '-'
    a=abs(n)
    if a>=1_000_000_000:return fa(f'{n/1_000_000_000:.1f}B')
    if a>=1_000_000:return fa(f'{n/1_000_000:.1f}M')
    if a>=1_000:return fa(f'{n/1_000:.0f}K')
    return fa(str(int(n)))

TYPE_FA={'EXPENSE':'هزینه','INCOME':'ورودی','OUTFLOW':'خروجی','CHEQUE':'چک','DOCUMENT':'داکیومنت','INFO':'اطلاع‌رسانی','UNKNOWN':'نامشخص'}
TYPE_BY_FA={v:k for k,v in TYPE_FA.items()}
METHOD_FA={'CASH':'نقدی','BANK_TRANSFER':'واریز بانکی','CARD':'کارت/کارتخوان','CHEQUE':'چک','OTHER':'سایر','UNKNOWN':'نامشخص'}
METHOD_BY_FA={v:k for k,v in METHOD_FA.items()}
STATE_FA={'PAID':'پرداخت کامل','PARTIAL':'پرداخت بخشی','UNPAID':'پرداخت‌نشده','CHEQUE_CLEARING':'پاس کردن چک','UNKNOWN':'نامشخص'}
STATE_BY_FA={v:k for k,v in STATE_FA.items()}
CHEQUE_TYPE_FA={'PHYSICAL':'فیزیکی','DIGITAL':'دیجیتال'}
CHEQUE_TYPE_BY_FA={v:k for k,v in CHEQUE_TYPE_FA.items()}
REG_FA={'REGISTERED':'ثبت‌شده','UNREGISTERED':'ثبت‌نشده','UNKNOWN':'نامشخص'}
REG_BY_FA={v:k for k,v in REG_FA.items()}
STATUS_FA={'PENDING_REVIEW':'در انتظار','NEEDS_REVIEW':'نیازمند بررسی','APPROVED':'تأییدشده','REJECTED':'ردشده','EDIT_PENDING':'در حال اصلاح'}

class SearchableCombo(ttk.Combobox):
    """Editable combobox that narrows its values while typing."""
    def __init__(self,parent,variable:tk.StringVar,values:list[str]|None=None,on_pick:Callable[[str],None]|None=None,**kw):
        self._all=list(values or []);self._on_pick=on_pick
        super().__init__(parent,textvariable=variable,values=self._all,state='normal',**kw)
        self.variable=variable
        self.bind('<KeyRelease>',self._filter,add='+');self.bind('<<ComboboxSelected>>',self._picked,add='+')
    def set_all(self,values:list[str]):
        self._all=list(values);self.configure(values=self._all)
    def _filter(self,e=None):
        if e and e.keysym in {'Up','Down','Return','Tab','Escape'}:return
        q=self.variable.get().strip().replace('ي','ی').replace('ك','ک').lower()
        vals=self._all if not q else [v for v in self._all if all(t in v.replace('ي','ی').replace('ك','ک').lower() for t in q.split())]
        self.configure(values=vals[:100])
        if vals:
            try:self.event_generate('<Down>')
            except Exception:pass
    def _picked(self,e=None):
        if self._on_pick:self._on_pick(self.variable.get())

class GlassMetricCard(tk.Frame):
    def __init__(self,parent,title:str,accent:str,icon:str,info:str='',on_open:Callable[[],None]|None=None):
        super().__init__(parent,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1)
        self.title=title;self.info=info;self.on_open=on_open
        tk.Frame(self,bg=accent,height=3).pack(fill='x')
        body=tk.Frame(self,bg=DARK['panel']);body.pack(fill='both',expand=True,padx=10,pady=7)
        tk.Label(body,text=icon,bg=DARK['panel'],fg=accent,font=('Segoe UI Symbol',19,'bold')).pack(side='left',padx=(0,9))
        tb=tk.Frame(body,bg=DARK['panel']);tb.pack(side='right',fill='both',expand=True)
        head=tk.Frame(tb,bg=DARK['panel']);head.pack(fill='x')
        tk.Label(head,text=title,bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',8,'bold')).pack(side='right')
        if info:
            i=tk.Label(head,text='ⓘ',bg=DARK['panel'],fg=accent,font=('Segoe UI',8,'bold'),cursor='hand2');i.pack(side='left');add_tooltip(i,info);i.bind('<Button-1>',lambda e:messagebox.showinfo(title,info,parent=self))
        self.var=tk.StringVar(value='۰ تومان')
        self.value=tk.Label(tb,textvariable=self.var,bg=DARK['panel'],fg=DARK['text'],font=('Segoe UI',12,'bold'),anchor='e');self.value.pack(fill='x',pady=(4,0));self.value_label=self.value
        if on_open:
            for w in (self,self.value,body,tb):w.bind('<Double-1>',lambda e:on_open())

class MiniLineChart(tk.Canvas):
    def __init__(self,parent,title:str,height=170):
        super().__init__(parent,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1,height=height)
        self.title=title;self.series=[];self.bind('<Configure>',lambda e:self.redraw())
    def set_series(self,series:list[tuple[str,list[float],str]]):self.series=series;self.redraw()
    def redraw(self):
        self.delete('all');w=max(self.winfo_width(),300);h=max(self.winfo_height(),120)
        self.create_text(w-12,12,text=self.title,anchor='ne',fill=DARK['text'],font=('Segoe UI',9,'bold'))
        x0,y0,x1,y1=34,32,w-18,h-25
        self.create_line(x0,y1,x1,y1,fill=DARK['line']);self.create_line(x0,y0,x0,y1,fill=DARK['line'])
        vals=[v for _,arr,_ in self.series for v in arr]
        vmax=max(vals) if vals else 1;vmax=max(vmax,1)
        colors={'blue':DARK['blue'],'green':DARK['green'],'orange':DARK['orange'],'red':DARK['red'],'cyan':DARK['cyan']}
        for label,arr,cname in self.series:
            if not arr:continue
            pts=[]
            for i,v in enumerate(arr):
                x=x0+(x1-x0)*(i/max(1,len(arr)-1));y=y1-(y1-y0)*(v/vmax);pts.extend([x,y])
            if len(pts)>=4:self.create_line(*pts,fill=colors.get(cname,cname),width=2,smooth=True)
        lx=45
        for label,arr,cname in self.series:
            c=colors.get(cname,cname);self.create_rectangle(lx,y0-15,lx+10,y0-5,fill=c,outline='');self.create_text(lx+15,y0-10,text=label,anchor='w',fill=DARK['muted'],font=('Segoe UI',7));lx+=100

class ProjectProgressBar(tk.Canvas):
    def __init__(self,parent,on_open=None):
        super().__init__(parent,height=44,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1,cursor='hand2')
        self.percent=0.0;self.on_open=on_open;self.bind('<Configure>',lambda e:self.redraw());self.bind('<Double-1>',lambda e:on_open() if on_open else None)
    def set(self,p:float):self.percent=max(0,min(float(p or 0),100));self.redraw()
    def redraw(self):
        self.delete('all');w=max(self.winfo_width(),100);h=max(self.winfo_height(),40);m=6
        self.create_rectangle(m,m,w-m,h-m,fill='#0A1421',outline=DARK['line'],width=1)
        fill=(w-2*m)*self.percent/100
        if fill>0:self.create_rectangle(m,m,m+fill,h-m,fill=DARK['blue'],outline='')
        self.create_text(w/2,h/2,text=f"پیشرفت کلی پروژه  {fa(f'{self.percent:.1f}')}٪",fill='white',font=('Segoe UI',10,'bold'))

# ---------- special approval / evidence ----------
def _raw_text_for_pending(pid:str)->str:
    item=DB.get_pending_item(pid)
    if not item:return ''
    tg=DB.get_telegram_message(item['telegram_chat_id'],item['telegram_message_id'])
    return str((tg or {}).get('raw_text') or '')

def _mark_nonfinancial_approved(pid:str,entity_type:str='',entity_id:str=''):
    item=DB.get_pending_item(pid)
    if not item:return
    DB.update_pending(pid,status='APPROVED')
    try:DB.update_telegram_message(chat_id=item['telegram_chat_id'],message_id=item['telegram_message_id'],state='APPROVED',linked_entity_type=entity_type or None,linked_entity_id=entity_id or None)
    except TypeError:
        try:DB.update_telegram_message(chat_id=item['telegram_chat_id'],message_id=item['telegram_message_id'],state='APPROVED')
        except Exception:pass

def _approve_v163(pid:str,payload:dict[str,Any],rich:RichBudgetService):
    typ=str(payload.get('detected_type') or 'UNKNOWN').upper();state=str(payload.get('payment_state') or 'UNKNOWN').upper()
    if typ=='INFO':
        _mark_nonfinancial_approved(pid,'INFO',pid);return 'اطلاع‌رسانی ثبت شد؛ اثر مالی ندارد.'
    if typ=='DOCUMENT':
        raw=_raw_text_for_pending(pid);links=[]
        lp=str(payload.get('link_pending_id') or '')
        if lp:
            post=DB.get_financial_posting(lp)
            if post and post.get('primary_entity_type') and post.get('primary_entity_id'):links=[(post['primary_entity_type'],post['primary_entity_id'])]
        did=rich.add_financial_document(pid,payload,raw,links)
        DB.relink_pending_attachments(pid,entity_type='DOCUMENT',entity_id=did);_mark_nonfinancial_approved(pid,'DOCUMENT',did)
        return 'داکیومنت ثبت و به پرونده اسناد اضافه شد.'
    multi=payload.get('cheques') if isinstance(payload.get('cheques'),list) else []
    if typ=='CHEQUE' and state!='CHEQUE_CLEARING' and len(multi)>1:
        # One photograph can contain several physical/digital cheques. Never collapse
        # that image into a single guessed cheque: create one cheque object per row.
        created=[];raw=_raw_text_for_pending(pid)
        for idx,c in enumerate(multi,1):
            amount=as_int(c.get('amount'));due=normalize_shamsi(str(c.get('due_date_shamsi') or ''));issue=normalize_shamsi(str(c.get('issue_date_shamsi') or payload.get('event_date_shamsi') or ''))
            if amount<=0 or not due:
                raise ValueError(f'چک شماره {idx} مبلغ یا تاریخ سررسید کامل ندارد. ابتدا همان چک را در جزئیات اصلاح کن.')
            issue=issue or due
            cid=DB.create_cheque(amount=amount,issue_date=shamsi_to_gregorian(issue),issue_date_shamsi=issue,due_date=shamsi_to_gregorian(due),due_date_shamsi=due,cheque_serial=str(c.get('cheque_serial') or ''),issuer_bank=str(c.get('issuer_bank') or ''),issuer_name=str(c.get('issuer_name') or ''),cheque_type=str(c.get('cheque_type') or 'PHYSICAL'),receiver_name=str(c.get('receiver_name') or payload.get('receiver_name') or ''),description=str(payload.get('description') or raw),source='GUI_MULTI_CHEQUE',actor_id='GUI')
            try:
                with DB.tx() as con:con.execute('UPDATE cheques SET registration_state=?,updated_at=? WHERE cheque_id=?',(str(c.get('cheque_registration_state') or payload.get('cheque_registration_state') or 'UNKNOWN').upper(),datetime.now().isoformat(timespec='seconds'),cid))
            except Exception:pass
            created.append(cid)
        did=rich.add_financial_document(pid,{**payload,'document_type':'CHEQUE_BUNDLE','amount':sum(as_int(c.get('amount')) for c in multi)},raw,[('CHEQUE',cid) for cid in created]);DB.relink_pending_attachments(pid,entity_type='DOCUMENT',entity_id=did);_mark_nonfinancial_approved(pid,'DOCUMENT',did)
        return f'{len(created)} چک جداگانه از یک تصویر ثبت شد؛ تصویر به‌عنوان سند مشترک به همه آنها متصل است.'
    if state=='CHEQUE_CLEARING':
        amount=as_int(payload.get('amount') or payload.get('paid_amount') or payload.get('final_amount'));sh=str(payload.get('event_date_shamsi') or '')
        rows=DB.list_cheques(open_only=True,limit=1000);cand=[]
        for r in rows:
            if amount and int(r.get('amount') or 0)!=amount:continue
            score=0
            if amount:score+=50
            if sh and sh in {str(r.get('due_date_shamsi') or ''),str(r.get('issue_date_shamsi') or '')}:score+=45
            desc=(str(payload.get('description') or '')+' '+str(payload.get('receiver_name') or '')).replace('ي','ی').replace('ك','ک')
            hay=(str(r.get('receiver_name') or '')+' '+str(r.get('description') or '')).replace('ي','ی').replace('ك','ک')
            if desc and hay and any(t in hay for t in desc.split() if len(t)>2):score+=10
            if score:cand.append((score,r))
        cand.sort(key=lambda x:-x[0])
        if not cand:raise ValueError('چک بازی با مبلغ/تاریخ این رسید پیدا نشد. ابتدا چک را از تب چک‌ها ثبت یا مشخصات را اصلاح کن.')
        if len(cand)>1 and cand[0][0]==cand[1][0]:raise ValueError('بیش از یک چک مشابه پیدا شد. از پنجره جزئیات چک صحیح را مشخص کن.')
        ch=cand[0][1];cash_sh=normalize_shamsi(sh) or gregorian_to_shamsi(datetime.now().date());cash_g=shamsi_to_gregorian(cash_sh)
        DB.cash_cheque(ch['cheque_id'],cashed_date=cash_g,cashed_date_shamsi=cash_sh,source='GUI_RECEIPT',actor_id='GUI')
        DB.relink_pending_attachments(pid,entity_type='CHEQUE',entity_id=ch['cheque_id']);_mark_nonfinancial_approved(pid,'CHEQUE',ch['cheque_id'])
        return f"چک {ch['cheque_id']} پاس شد؛ هزینه دوباره ثبت نشد."
    result=APPROVAL.approve(pid,actor_id='GUI_16_3')
    return f"ثبت شد: {TYPE_FA.get(str(result.posting.posting_type),'ثبت مالی')}"

class PhaseChoiceDialog:
    @staticmethod
    def choose(parent,cands:list[dict[str,Any]])->dict[str,Any]|None:
        if not cands:return None
        if len(cands)==1:return cands[0]
        win=tk.Toplevel(parent);win.title('انتخاب فاز اصلی');win.transient(parent);win.grab_set();win.configure(bg=DARK['bg']);result={'v':None};tk.Label(win,text='عبارت فاز فرعی با چند فاز اصلی تطبیق دارد؛ یکی را انتخاب کن:',bg=DARK['bg'],fg=DARK['text'],padx=10,pady=8).pack()
        lb=tk.Listbox(win,width=58,height=min(10,len(cands)),bg=DARK['panel'],fg=DARK['text'],selectbackground=DARK['blue'],font=('Segoe UI',9));lb.pack(fill='both',expand=True,padx=10,pady=5)
        for c in cands:lb.insert('end',f"{int(c['phase_no']):02d} — {c['phase_name']}")
        def ok():
            s=lb.curselection();
            if s:result['v']=cands[int(s[0])];win.destroy()
        tk.Button(win,text='انتخاب',command=ok,bg=DARK['blue'],fg='white',relief='flat',padx=12,pady=5).pack(pady=8);lb.bind('<Double-1>',lambda e:ok());parent.wait_window(win);return result['v']

class UnifiedPendingEditor(tk.Toplevel):
    def __init__(self,parent,row:dict[str,Any],rich:RichBudgetService,on_done:Callable[[],None]):
        super().__init__(parent);self.row=row;self.rich=rich;self.on_done=on_done;self.pid=str(row['pending_id']);self.payload=dict(row.get('payload') or {})
        self.title(f'جزئیات ثبت دیتا — {self.pid}');self.geometry('1480x880');self.minsize(1180,720);self.configure(bg=DARK['bg']);self.transient(parent)
        self.vars:dict[str,tk.StringVar]={};self.widgets={};self._image=None;self._tkimg=None;self._zoom=1.0
        self._build();self._load();self.after(150,self._fit_image)
    def _build(self):
        head=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);head.pack(fill='x',padx=8,pady=8)
        tk.Label(head,text='ویرایش و تأیید رکورد',bg=DARK['surface'],fg=DARK['text'],font=('Segoe UI',12,'bold')).pack(side='right',padx=12,pady=8)
        self.status_lbl=tk.Label(head,text=f"● {STATUS_FA.get(self.row.get('status'),self.row.get('status'))}",bg=DARK['surface'],fg=DARK['yellow'],font=('Segoe UI',9,'bold'));self.status_lbl.pack(side='left',padx=12)
        pane=ttk.Panedwindow(self,orient='horizontal');pane.pack(fill='both',expand=True,padx=8,pady=(0,8))
        evidence=tk.Frame(pane,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);form=tk.Frame(pane,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);pane.add(evidence,weight=5);pane.add(form,weight=5)
        tk.Label(evidence,text='شواهد: رسید + متن پیام',bg=DARK['panel'],fg='#7FC9FF',font=('Segoe UI',10,'bold')).pack(anchor='e',padx=10,pady=(8,4))
        ep=ttk.Panedwindow(evidence,orient='horizontal');ep.pack(fill='both',expand=True,padx=8,pady=(0,8))
        imgf=tk.Frame(ep,bg='#07101B');txtf=tk.Frame(ep,bg=DARK['panel2']);ep.add(imgf,weight=3);ep.add(txtf,weight=2)
        self.canvas=tk.Canvas(imgf,bg='#07101B',highlightthickness=0);ys=ttk.Scrollbar(imgf,orient='vertical',command=self.canvas.yview);xs=ttk.Scrollbar(imgf,orient='horizontal',command=self.canvas.xview);self.canvas.configure(yscrollcommand=ys.set,xscrollcommand=xs.set);self.canvas.grid(row=0,column=0,sticky='nsew');ys.grid(row=0,column=1,sticky='ns');xs.grid(row=1,column=0,sticky='ew');imgf.grid_rowconfigure(0,weight=1);imgf.grid_columnconfigure(0,weight=1)
        self.canvas.bind('<MouseWheel>',self._wheel);self.canvas.bind('<ButtonPress-1>',lambda e:self.canvas.scan_mark(e.x,e.y));self.canvas.bind('<B1-Motion>',lambda e:self.canvas.scan_dragto(e.x,e.y,gain=1))
        ib=tk.Frame(imgf,bg='#07101B');ib.grid(row=2,column=0,columnspan=2,sticky='ew');
        for t,cmd in [('−',lambda:self._set_zoom(self._zoom/1.2)),('Fit',self._fit_image),('+',lambda:self._set_zoom(self._zoom*1.2))]:tk.Button(ib,text=t,command=cmd,bg=DARK['glass'],fg='white',relief='flat',width=5).pack(side='left',padx=2,pady=4)
        self.evidence_text=tk.Text(txtf,wrap='word',bg='#0A1625',fg=DARK['text'],insertbackground='white',relief='flat',font=('Segoe UI',9),padx=8,pady=8);self.evidence_text.pack(fill='both',expand=True)
        self.evidence_text.configure(state='disabled')
        # Form on right
        title=tk.Label(form,text='اطلاعات ثبت مالی',bg=DARK['panel'],fg='#7FC9FF',font=('Segoe UI',10,'bold'));title.pack(anchor='e',padx=10,pady=(8,4))
        body=tk.Frame(form,bg=DARK['panel']);body.pack(fill='both',expand=True,padx=10)
        for c in (0,2):body.grid_columnconfigure(c,weight=1)
        fields=[
            ('event_date_shamsi','تاریخ','date'),('detected_type','نوع','type'),
            ('payer_name','واریزکننده','entry'),('amount','مبلغ پرداختی','num'),
            ('payment_state','وضعیت پرداخت','state'),('invoice_amount','مبلغ فاکتور','num'),
            ('final_amount','مبلغ نهایی','num'),('remaining_debt','مانده بدهی','num'),
            ('discount_amount','تخفیف','num'),('receiver_name','گیرنده','entry'),
            ('description','بابت','entry'),('main_phase','فاز اصلی','phase'),
            ('sub_phase','فاز فرعی','subphase'),('payment_method','روش پرداخت','method'),
        ]
        self._field_specs={k:(l,kind) for k,l,kind in fields}
        for i,(k,l,kind) in enumerate(fields):self._make_field(body,i,k,l,kind)
        sep=tk.Frame(body,bg=DARK['line'],height=1);sep.grid(row=7,column=0,columnspan=4,sticky='ew',pady=7)
        cheque=[('issue_date_shamsi','تاریخ صدور چک','date'),('due_date_shamsi','تاریخ سررسید چک','date'),('issuer_bank','بانک','entry'),('issuer_name','صاحب حساب','entry'),('cheque_serial','شماره/صیادی','entry'),('cheque_type','نوع چک','chequetype'),('cheque_registration_state','وضعیت ثبت چک','reg')]
        for j,(k,l,kind) in enumerate(cheque,14):self._make_field(body,j+1,k,l,kind)
        # multi-cheque extraction preview
        self.multi_cheque_var=tk.StringVar(value='');mc=tk.Label(form,textvariable=self.multi_cheque_var,bg=DARK['panel'],fg=DARK['orange'],font=('Segoe UI',8,'bold'),justify='right');mc.pack(fill='x',padx=10,pady=(2,4))
        self.multi_cheque_tree=ttk.Treeview(form,columns=('amount','issue','due','serial','bank'),show='headings',height=3)
        for k,l,w in [('amount','مبلغ',115),('issue','صدور',90),('due','سررسید',90),('serial','صیادی',110),('bank','بانک',100)]:self.multi_cheque_tree.heading(k,text=l);self.multi_cheque_tree.column(k,width=w,anchor='center')
        self.multi_cheque_tree.bind('<Double-1>',lambda e:self._copy_multi_cheque());self.multi_cheque_tree.pack_forget()
        act=tk.Frame(form,bg=DARK['panel']);act.pack(fill='x',padx=10,pady=10)
        tk.Button(act,text='💾 ذخیره اصلاحات',command=self.save_only,bg=DARK['blue'],fg='white',relief='flat',font=('Segoe UI',9,'bold'),padx=12,pady=7).pack(side='right',padx=3)
        tk.Button(act,text='✅ تأیید نهایی',command=self.approve,bg='#1B9B6B',fg='white',relief='flat',font=('Segoe UI',9,'bold'),padx=12,pady=7).pack(side='right',padx=3)
        tk.Button(act,text='❌ رد',command=self.reject,bg='#9D3443',fg='white',relief='flat',padx=12,pady=7).pack(side='right',padx=3)
        self.msg=tk.StringVar();tk.Label(act,textvariable=self.msg,bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',8)).pack(side='left')
    def _make_field(self,parent,i,key,label,kind):
        r=i//2;c=(i%2)*2
        tk.Label(parent,text=label+':',bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',8),anchor='e').grid(row=r,column=c+1,sticky='e',padx=(5,2),pady=3)
        v=tk.StringVar();self.vars[key]=v
        if kind=='date':w=DateField(parent,v,width=18)
        elif kind=='type':w=ttk.Combobox(parent,textvariable=v,state='readonly',values=list(TYPE_BY_FA),width=23);w.bind('<<ComboboxSelected>>',lambda e:self._sync_dynamic())
        elif kind=='state':w=ttk.Combobox(parent,textvariable=v,state='readonly',values=list(STATE_BY_FA),width=23);w.bind('<<ComboboxSelected>>',lambda e:self._sync_amounts())
        elif kind=='method':w=ttk.Combobox(parent,textvariable=v,state='readonly',values=list(METHOD_BY_FA),width=23);w.bind('<<ComboboxSelected>>',lambda e:self._sync_dynamic())
        elif kind=='chequetype':w=ttk.Combobox(parent,textvariable=v,state='readonly',values=list(CHEQUE_TYPE_BY_FA),width=23)
        elif kind=='reg':w=ttk.Combobox(parent,textvariable=v,state='readonly',values=list(REG_BY_FA),width=23)
        elif kind=='phase':w=SearchableCombo(parent,v,[],on_pick=self._phase_picked,width=24)
        elif kind=='subphase':w=SearchableCombo(parent,v,[],on_pick=self._subphase_picked,width=24)
        else:
            w=ttk.Entry(parent,textvariable=v,justify='right',width=26)
            if kind=='num':bind_grouped_number(w,v)
        w.grid(row=r,column=c,sticky='ew',padx=3,pady=3);self.widgets[key]=w
        if key in {'amount','invoice_amount','final_amount'}:v.trace_add('write',lambda *_:self.after_idle(self._sync_amounts))
    def _phase_values(self):
        summ=self.rich.list_phase_summary();return [f"{r['phase_no']:02d} — {r['phase']}" for r in summ]
    def _load(self):
        p=self.payload
        # legacy construction stage/activity mapping
        main=str(p.get('main_phase') or p.get('construction_stage') or '')
        sub=str(p.get('sub_phase') or p.get('expense_category') or '')
        vals={
            'event_date_shamsi':p.get('event_date_shamsi') or self.row.get('message_date') or '',
            'detected_type':TYPE_FA.get(str(p.get('detected_type') or 'UNKNOWN').upper(),'نامشخص'),
            'payer_name':p.get('payer_name') or 'تنخواه','amount':group_int(p.get('amount') or 0),
            'payment_state':STATE_FA.get(str(p.get('payment_state') or 'UNKNOWN').upper(),'نامشخص'),
            'invoice_amount':group_int(p.get('invoice_amount') or 0),'final_amount':group_int(p.get('final_amount') or 0),
            'remaining_debt':group_int(p.get('remaining_debt') or 0),'discount_amount':group_int(p.get('discount_amount') or 0),
            'receiver_name':p.get('receiver_name') or '','description':p.get('description') or self.row.get('raw_text') or '',
            'main_phase':main,'sub_phase':sub,'payment_method':METHOD_FA.get(str(p.get('payment_method') or 'UNKNOWN').upper(),'نامشخص'),
            'issue_date_shamsi':p.get('issue_date_shamsi') or '','due_date_shamsi':p.get('due_date_shamsi') or '',
            'issuer_bank':p.get('issuer_bank') or p.get('bank_name') or '','issuer_name':p.get('issuer_name') or '',
            'cheque_serial':p.get('cheque_serial') or '','cheque_type':CHEQUE_TYPE_FA.get(str(p.get('cheque_type') or 'PHYSICAL').upper(),'فیزیکی'),
            'cheque_registration_state':REG_FA.get(str(p.get('cheque_registration_state') or 'UNKNOWN').upper(),'نامشخص'),
        }
        for k,v in vals.items():self.vars[k].set(str(v or ''))
        self.widgets['main_phase'].set_all(self._phase_values());self._update_sub_values()
        self._load_evidence();self._sync_amounts();self._sync_dynamic()
        ch=p.get('cheques') if isinstance(p.get('cheques'),list) else [];self._multi_cheques=ch
        if ch:
            self.multi_cheque_var.set(f"AI در این تصویر {fa(len(ch))} چک تشخیص داده است؛ دابل‌کلیک روی هر چک، اطلاعات آن را به فرم بالا منتقل می‌کند.")
            self.multi_cheque_tree.pack(fill='x',padx=10,pady=(0,5))
            for x in self.multi_cheque_tree.get_children():self.multi_cheque_tree.delete(x)
            for i,c in enumerate(ch):self.multi_cheque_tree.insert('', 'end',iid=str(i),values=(fmt_money(c.get('amount')),c.get('issue_date_shamsi') or '-',c.get('due_date_shamsi') or '-',c.get('cheque_serial') or '-',c.get('issuer_bank') or '-'))
    def _copy_multi_cheque(self):
        s=self.multi_cheque_tree.selection()
        if not s:return
        try:c=self._multi_cheques[int(s[0])]
        except Exception:return
        self.vars['detected_type'].set('چک');self.vars['amount'].set(group_int(c.get('amount') or 0));self.vars['issue_date_shamsi'].set(str(c.get('issue_date_shamsi') or ''));self.vars['due_date_shamsi'].set(str(c.get('due_date_shamsi') or ''));self.vars['issuer_bank'].set(str(c.get('issuer_bank') or ''));self.vars['issuer_name'].set(str(c.get('issuer_name') or ''));self.vars['cheque_serial'].set(str(c.get('cheque_serial') or ''));self.vars['cheque_type'].set(CHEQUE_TYPE_FA.get(str(c.get('cheque_type') or 'PHYSICAL').upper(),'فیزیکی'));self._sync_dynamic()

    def _load_evidence(self):
        try:bundle=APPROVAL.evidence_bundle(self.pid,window=3)
        except Exception:bundle={'current':{'raw_text':self.row.get('raw_text') or ''},'nearby':[],'attachments':[]}
        cur=bundle.get('current') or {};lines=[]
        if cur.get('raw_text'):lines.append('متن اصلی:\n'+str(cur.get('raw_text')))
        for m in bundle.get('nearby') or []:
            if str(m.get('raw_text') or '').strip():lines.append(f"پیام نزدیک ({m.get('message_id')}):\n{m.get('raw_text')}")
        ocr=str(self.row.get('receipt_ocr_text') or '').strip()
        if ocr:lines.append('OCR کمکی:\n'+ocr[:5000])
        self.evidence_text.configure(state='normal');self.evidence_text.delete('1.0','end');self.evidence_text.insert('1.0','\n\n'.join(lines) or 'برای این رکورد متن همراه ثبت نشده است.');self.evidence_text.configure(state='disabled')
        path=str(self.row.get('receipt_image_path') or '')
        if not path:
            for a in bundle.get('attachments') or []:
                if str(a.get('mime_type') or '').startswith('image/'):path=str(a.get('local_path') or '');break
        if path and Path(path).exists() and Image is not None:
            try:self._image=ImageOps.exif_transpose(Image.open(path)).convert('RGB')
            except Exception:self._image=None
        if not self._image:self.canvas.create_text(220,180,text='رسید تصویری ندارد',fill=DARK['muted'],font=('Segoe UI',10))
    def _fit_image(self):
        if not self._image:return
        self.canvas.update_idletasks();cw=max(200,self.canvas.winfo_width()-24);ch=max(200,self.canvas.winfo_height()-24);self._zoom=min(1.0,cw/self._image.width,ch/self._image.height);self._render_image()
    def _set_zoom(self,z):self._zoom=max(.1,min(4,float(z)));self._render_image()
    def _wheel(self,e):self._set_zoom(self._zoom*(1.12 if e.delta>0 else 1/1.12))
    def _render_image(self):
        if not self._image or ImageTk is None:return
        w=max(1,int(self._image.width*self._zoom));h=max(1,int(self._image.height*self._zoom));im=self._image.resize((w,h)) if (w,h)!=self._image.size else self._image;self._tkimg=ImageTk.PhotoImage(im);self.canvas.delete('all');self.canvas.create_image(8,8,image=self._tkimg,anchor='nw');self.canvas.configure(scrollregion=(0,0,w+16,h+16))
    def _phase_picked(self,value):
        self._update_sub_values()
    def _update_sub_values(self):
        txt=self.vars['main_phase'].get();no=None
        try:no=int(txt.split('—',1)[0].strip())
        except Exception:
            cand=self.rich.phase_candidates(txt,1);no=cand[0]['phase_no'] if cand else None
            if cand and txt.strip():self.vars['main_phase'].set(f"{no:02d} — {cand[0]['phase_name']}")
        rows=self.rich.subphase_candidates(no,'');self.widgets['sub_phase'].set_all([r['description'] for r in rows])
    def _subphase_picked(self,value):
        # Reverse lookup: if main is empty/ambiguous, propose phases containing the activity.
        main=self.vars['main_phase'].get().strip()
        if not main:
            cand=self.rich.subphase_candidates(None,value)
            phases=[]
            for r in cand:
                k=(r['phase_no'],r['phase_name'])
                if k not in phases:phases.append(k)
            if len(phases)==1:self.vars['main_phase'].set(f"{phases[0][0]:02d} — {phases[0][1]}")
            elif len(phases)>1:self.widgets['main_phase'].set_all([f"{n:02d} — {name}" for n,name in phases])
    def _sync_amounts(self):
        try:
            inv=parse_int(self.vars.get('invoice_amount',tk.StringVar()).get());fin=parse_int(self.vars.get('final_amount',tk.StringVar()).get());paid=parse_int(self.vars.get('amount',tk.StringVar()).get())
            disc=max(inv-fin,0) if inv and fin and fin<inv else parse_int(self.vars.get('discount_amount',tk.StringVar()).get())
            if inv and fin and fin<inv:self.vars['discount_amount'].set(group_int(disc))
            state=STATE_BY_FA.get(self.vars.get('payment_state',tk.StringVar()).get(),'UNKNOWN')
            if state=='PARTIAL':self.vars['remaining_debt'].set(group_int(max(fin-paid,0)))
            elif state=='PAID':self.vars['remaining_debt'].set('0')
            elif state=='UNPAID':self.vars['remaining_debt'].set(group_int(fin))
        except Exception:pass
    def _sync_dynamic(self):
        typ=TYPE_BY_FA.get(self.vars['detected_type'].get(),'UNKNOWN');method=METHOD_BY_FA.get(self.vars['payment_method'].get(),'UNKNOWN');is_ch=typ=='CHEQUE' or method=='CHEQUE'
        for k in ('issue_date_shamsi','due_date_shamsi','issuer_bank','issuer_name','cheque_serial','cheque_type','cheque_registration_state'):
            w=self.widgets.get(k)
            try:
                if isinstance(w,DateField):w.entry.configure(state='normal' if is_ch else 'disabled')
                else:w.configure(state='readonly' if is_ch and k in {'cheque_type','cheque_registration_state'} else ('normal' if is_ch else 'disabled'))
            except Exception:pass
    def payload_from_form(self):
        p=dict(self.payload);typ=TYPE_BY_FA.get(self.vars['detected_type'].get(),'UNKNOWN');method=METHOD_BY_FA.get(self.vars['payment_method'].get(),'UNKNOWN');state=STATE_BY_FA.get(self.vars['payment_state'].get(),'UNKNOWN')
        p.update({'detected_type':typ,'event_date_shamsi':self.vars['event_date_shamsi'].get().strip(),'payer_name':self.vars['payer_name'].get().strip() or 'تنخواه','receiver_name':self.vars['receiver_name'].get().strip(),'description':self.vars['description'].get().strip(),'payment_method':method,'payment_state':state})
        for k in ('amount','invoice_amount','final_amount','remaining_debt','discount_amount'):p[k]=parse_int(self.vars[k].get())
        p['paid_amount']=p['amount'] if state in {'PAID','PARTIAL','CHEQUE_CLEARING'} else int(p.get('paid_amount') or 0)
        main=self.vars['main_phase'].get().strip();sub=self.vars['sub_phase'].get().strip()
        # Resolve typed free text to the 32-phase master. Reverse lookup from a
        # sub-phase can legitimately produce more than one phase (e.g. work around a well).
        selected=None
        try:
            no=int(main.split('—',1)[0].strip());selected=next((x for x in self.rich.list_phase_summary() if x['phase_no']==no),None)
        except Exception:selected=None
        if not selected and main:selected=(self.rich.phase_candidates(main,1) or [None])[0]
        if not selected and sub:
            matches=self.rich.subphase_candidates(None,sub);uniq=[]
            for x in matches:
                c={'phase_no':x['phase_no'],'phase_name':x['phase_name']}
                if c not in uniq:uniq.append(c)
            selected=PhaseChoiceDialog.choose(self,uniq[:8])
        if selected:
            main=f"{int(selected['phase_no']):02d} — {selected.get('phase') or selected.get('phase_name')}";self.vars['main_phase'].set(main)
        p['main_phase']=main;p['sub_phase']=sub;p['construction_stage']=main;p['expense_category']=sub or str(p.get('expense_category') or '')
        p['is_cheque']=typ=='CHEQUE' or method=='CHEQUE'
        for k in ('issue_date_shamsi','due_date_shamsi','issuer_bank','issuer_name','cheque_serial'):p[k]=self.vars[k].get().strip()
        p['cheque_type']=CHEQUE_TYPE_BY_FA.get(self.vars['cheque_type'].get(),'PHYSICAL');p['cheque_registration_state']=REG_BY_FA.get(self.vars['cheque_registration_state'].get(),'UNKNOWN')
        p['manager_fee_eligible']=typ=='EXPENSE';return p
    def save_only(self):
        try:self.payload=self.payload_from_form();APPROVAL.save_payload(self.pid,self.payload,learn=True);self.msg.set('اصلاحات ذخیره شد (هنوز اثر مالی ندارد).');self.on_done()
        except Exception as exc:messagebox.showerror('ذخیره',str(exc),parent=self)
    def approve(self):
        try:
            self.payload=self.payload_from_form();APPROVAL.save_payload(self.pid,self.payload,learn=True);msg=_approve_v163(self.pid,self.payload,self.rich);messagebox.showinfo('ثبت',msg,parent=self);self.on_done();self.destroy()
        except Exception as exc:messagebox.showerror('تأیید انجام نشد',str(exc),parent=self)
    def reject(self):
        if not messagebox.askyesno('رد','این مورد رد شود؟ هیچ اثر مالی ایجاد نمی‌شود.',parent=self):return
        try:APPROVAL.reject(self.pid,actor_id='GUI_16_3');self.on_done();self.destroy()
        except Exception as exc:messagebox.showerror('رد',str(exc),parent=self)

class DataEntryCenter163(ttk.Frame):
    def __init__(self,parent,rich:RichBudgetService,on_posted=None):
        super().__init__(parent,padding=7);self.rich=rich;self.on_posted=on_posted;self.current=None;self.rows=[];self._image=None;self._tkimg=None;self.zoom=1.0;self._bot_process=None;self._bot_log=None;self._build();self.refresh()
    def set_bot_process(self,p,log=None):self._bot_process=p;self._bot_log=log;self._update_bot()
    def _build(self):
        top=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);top.pack(fill='x',pady=(0,7))
        tk.Label(top,text='ثبت دیتا — مرکز بررسی و تأیید',bg=DARK['surface'],fg=DARK['text'],font=('Segoe UI',11,'bold')).pack(side='right',padx=10,pady=8)
        self.bot=tk.StringVar(value='ربات: در حال بررسی...');tk.Label(top,textvariable=self.bot,bg=DARK['surface'],fg=DARK['green'],font=('Segoe UI',8,'bold')).pack(side='left',padx=8)
        self.filter=tk.StringVar(value='همه');fc=ttk.Combobox(top,textvariable=self.filter,state='readonly',values=['همه','در انتظار','نیازمند بررسی','تأییدشده','ردشده'],width=15);fc.pack(side='right',padx=4);fc.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        ttk.Button(top,text='🔄',command=self.refresh,style='Toolbar.TButton').pack(side='right')
        ttk.Button(top,text='🧪 وضعیت اتصال',command=self.status_dialog,style='Toolbar.TButton').pack(side='right',padx=3)
        ttk.Button(top,text='🤖 تحلیل تصاویر انتخاب‌شده',command=self.analyze_selected,style='Toolbar.TButton').pack(side='right',padx=3)
        ttk.Button(top,text='🔗 تجمیع انتخاب‌ها',command=self.merge_selected,style='Toolbar.TButton').pack(side='right',padx=3)
        ttk.Button(top,text='🧹 پاک‌سازی تأیید/ردشده از لیست',command=self.clear_finished,style='Toolbar.TButton').pack(side='right',padx=3)
        pane=ttk.Panedwindow(self,orient='horizontal');pane.pack(fill='both',expand=True)
        left=tk.Frame(pane,bg=DARK['panel']);right=tk.Frame(pane,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);pane.add(left,weight=7);pane.add(right,weight=3)
        self.table=SmartTable(left,[('doc','سند',55),('date','تاریخ',95),('type','نوع',90),('text','متن/بابت',270),('amount','مبلغ AI',125),('phase','فاز اصلی',145),('sub','فاز فرعی',145),('pay','پرداخت',105),('conf','AI',65),('status','وضعیت',95)],title='رکوردها')
        self.table.pack(fill='both',expand=True);self.table.tree.bind('<<TreeviewSelect>>',self._select,add='+');self.table.tree.bind('<Double-1>',lambda e:self.open_editor(),add='+');self.table.set_edit_handler(lambda r:self.open_editor(r));self.table.set_delete_handler(self._delete_row)
        rb=tk.Frame(right,bg=DARK['panel']);rb.pack(fill='x',padx=7,pady=7);tk.Label(rb,text='پیش‌نمایش سند و متن',bg=DARK['panel'],fg='#7FC9FF',font=('Segoe UI',9,'bold')).pack(side='right');tk.Button(rb,text='✅ تأیید سریع',command=self.quick_approve,bg='#198B61',fg='white',relief='flat',padx=9,pady=5).pack(side='left');tk.Button(rb,text='✏️ اصلاح',command=self.open_editor,bg=DARK['blue'],fg='white',relief='flat',padx=9,pady=5).pack(side='left',padx=3)
        self.preview=tk.Canvas(right,bg='#07101B',highlightthickness=0,height=340);self.preview.pack(fill='both',expand=True,padx=7);self.preview.bind('<MouseWheel>',self._wheel);self.preview.bind('<ButtonPress-1>',lambda e:self.preview.scan_mark(e.x,e.y));self.preview.bind('<B1-Motion>',lambda e:self.preview.scan_dragto(e.x,e.y,gain=1))
        zb=tk.Frame(right,bg=DARK['panel']);zb.pack(fill='x',padx=7);tk.Button(zb,text='Fit',command=self._fit,bg=DARK['glass'],fg='white',relief='flat').pack(side='left',padx=2,pady=3);tk.Button(zb,text='+',command=lambda:self._set_zoom(self.zoom*1.2),bg=DARK['glass'],fg='white',relief='flat').pack(side='left');tk.Button(zb,text='−',command=lambda:self._set_zoom(self.zoom/1.2),bg=DARK['glass'],fg='white',relief='flat').pack(side='left',padx=2)
        self.text=tk.Text(right,height=9,wrap='word',bg='#0A1625',fg=DARK['text'],relief='flat',font=('Segoe UI',8),padx=7,pady=7);self.text.pack(fill='x',padx=7,pady=7);self.text.configure(state='disabled')
        self.action=tk.StringVar();tk.Label(right,textvariable=self.action,bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',8),wraplength=320,justify='right').pack(fill='x',padx=7,pady=(0,7))
        self.after(4000,self._periodic)
    def _periodic(self):
        try:self.refresh();self._update_bot()
        finally:self.after(4000,self._periodic)
    def _update_bot(self):
        ready=(BASE_DIR/'runtime'/'telegram_bot_ready.flag').exists()
        if self._bot_process is None:self.bot.set('● ربات تلگرام: وضعیت نامشخص');return
        code=self._bot_process.poll()
        if code is not None:self.bot.set('● ربات تلگرام: خاموش')
        elif ready:self.bot.set('● ربات تلگرام: آنلاین و آماده')
        else:self.bot.set('● ربات تلگرام: در حال اتصال...')
    def status_dialog(self):
        ready=(BASE_DIR/'runtime'/'telegram_bot_ready.flag').exists();alive=self._bot_process is not None and self._bot_process.poll() is None
        gem='فعال' if str(getattr(CONFIG,'gemini_api_key','')).strip() else 'کلید ثبت نشده';grp=getattr(CONFIG,'group_chat_id',None)
        lines=[f"ربات تلگرام: {'آنلاین' if alive and ready else ('در حال اتصال' if alive else 'خاموش')}",f"گروه پروژه: {'تنظیم شده' if grp else 'Group ID ثبت نشده'}",f"Gemini: {gem}"]
        if self._bot_log and Path(self._bot_log).exists():
            try:
                tail=Path(self._bot_log).read_text(encoding='utf-8',errors='replace').splitlines()[-8:]
                friendly=[]
                for x in tail:
                    low=x.lower()
                    if 'unauthorized' in low or 'invalid token' in low:friendly.append('توکن ربات پذیرفته نشد.')
                    elif 'forbidden' in low:friendly.append('ربات اجازه دسترسی به گروه را ندارد.')
                    elif 'network' in low or 'timeout' in low:friendly.append('ارتباط شبکه با تلگرام قطع/کند است.')
                    elif 'ready' in low:friendly.append('ربات آماده دریافت پیام است.')
                if friendly:lines.append('آخرین وضعیت:\n'+'\n'.join(dict.fromkeys(friendly)))
            except Exception:pass
        messagebox.showinfo('وضعیت اتصال','\n\n'.join(lines),parent=self)
    def refresh(self):
        hidden=self.rich.hidden_review_ids();rows=[r for r in APPROVAL.list_reviews(limit=3000) if str(r.get('pending_id')) not in hidden]
        f=self.filter.get();want={'در انتظار':{'PENDING_REVIEW'},'نیازمند بررسی':{'NEEDS_REVIEW'},'تأییدشده':{'APPROVED'},'ردشده':{'REJECTED'}}.get(f)
        if want:rows=[r for r in rows if r.get('status') in want]
        self.rows=rows
        def rv(r):
            p=r.get('payload') or {};amt=p.get('amount') or p.get('final_amount') or 0;raw=str(r.get('raw_text') or '');desc=str(p.get('description') or '') or raw
            phase=str(p.get('main_phase') or p.get('construction_stage') or '-');sub=str(p.get('sub_phase') or p.get('expense_category') or '-')
            fc=r.get('field_confidences') or p.get('field_confidences') or {};conf=fc.get('amount',p.get('confidence',0))
            return ['🖼' if self._path(r) else '📝',r.get('message_date') or '-',TYPE_FA.get(str(p.get('detected_type') or 'UNKNOWN').upper(),'نامشخص'),desc[:90],fmt_money(amt),phase,sub,METHOD_FA.get(str(p.get('payment_method') or 'UNKNOWN').upper(),'نامشخص'),fa(f'{float(conf or 0)*100:.0f}%'),STATUS_FA.get(r.get('status'),r.get('status'))]
        self.table.set_rows(rows,rv)
        # status colors stay visible after approval/rejection
        for iid,r in getattr(self.table,'_iid_to_row',{}).items():
            st=r.get('status');tag='approved' if st=='APPROVED' else ('rejected' if st=='REJECTED' else ('needs' if st=='NEEDS_REVIEW' else 'pending'))
            try:self.table.tree.item(iid,tags=(tag,));
            except Exception:pass
        self.table.tree.tag_configure('approved',background='#10392E',foreground='#DFFFF3');self.table.tree.tag_configure('rejected',background='#40212A',foreground='#FFE8EC');self.table.tree.tag_configure('needs',background='#443718',foreground='#FFF5CE');self.table.tree.tag_configure('pending',background='#102238',foreground=DARK['text'])
    def _path(self,r):
        p=str(r.get('receipt_image_path') or '')
        if p and Path(p).exists():return p
        try:
            for a in DB.list_pending_attachments(r.get('pending_id')):
                q=str(a.get('local_path') or '')
                if q and str(a.get('mime_type') or '').startswith('image/') and Path(q).exists():return q
        except Exception:pass
        return ''
    def _select(self,e=None):
        rows=self.table.selected_rows();self.current=rows[0] if rows else None
        if self.current:self._show(self.current)
    def _show(self,r):
        self.preview.delete('all');self._image=None;self._tkimg=None;self.zoom=1
        path=self._path(r)
        if path and Image is not None:
            try:self._image=ImageOps.exif_transpose(Image.open(path)).convert('RGB');self.after(30,self._fit)
            except Exception:pass
        if not self._image:self.preview.create_text(160,120,text='بدون تصویر',fill=DARK['muted'],font=('Segoe UI',10))
        p=r.get('payload') or {};lines=[]
        raw=str(r.get('raw_text') or '').strip()
        if raw:lines.append('پیام:\n'+raw)
        try:
            b=APPROVAL.evidence_bundle(r['pending_id'],window=2)
            for m in b.get('nearby') or []:
                t=str(m.get('raw_text') or '').strip()
                if t:lines.append(f"پیام نزدیک:\n{t}")
        except Exception:pass
        lines.append(f"AI: {TYPE_FA.get(str(p.get('detected_type') or 'UNKNOWN').upper(),'نامشخص')} | {fmt_money(p.get('amount') or p.get('final_amount') or 0)}")
        self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('1.0','\n\n'.join(lines));self.text.configure(state='disabled')
    def _fit(self):
        if not self._image:return
        self.preview.update_idletasks();cw=max(200,self.preview.winfo_width()-18);ch=max(160,self.preview.winfo_height()-18);self.zoom=min(1,cw/self._image.width,ch/self._image.height);self._render()
    def _set_zoom(self,z):self.zoom=max(.1,min(4,float(z)));self._render()
    def _wheel(self,e):self._set_zoom(self.zoom*(1.12 if e.delta>0 else 1/1.12))
    def _render(self):
        if not self._image or ImageTk is None:return
        w=max(1,int(self._image.width*self.zoom));h=max(1,int(self._image.height*self.zoom));im=self._image.resize((w,h)) if (w,h)!=self._image.size else self._image;self._tkimg=ImageTk.PhotoImage(im);self.preview.delete('all');self.preview.create_image(6,6,image=self._tkimg,anchor='nw');self.preview.configure(scrollregion=(0,0,w+12,h+12))
    def open_editor(self,row=None):
        row=row or self.current
        if not row:return messagebox.showwarning('ثبت دیتا','یک سطر را انتخاب کن.',parent=self)
        UnifiedPendingEditor(self,row,self.rich,self.refresh)
    def quick_approve(self):
        if not self.current:return
        if self.current.get('status') in {'APPROVED','REJECTED'}:return messagebox.showinfo('ثبت دیتا','این رکورد قبلاً تعیین تکلیف شده است.',parent=self)
        p=dict(self.current.get('payload') or {})
        if not messagebox.askyesno('تأیید سریع',f"{TYPE_FA.get(str(p.get('detected_type') or 'UNKNOWN').upper(),'نامشخص')} | {fmt_money(p.get('amount') or p.get('final_amount') or 0)}\n\nتأیید شود؟",parent=self):return
        try:msg=_approve_v163(self.current['pending_id'],p,self.rich);self.action.set(msg);self.refresh();self.on_posted and self.on_posted()
        except Exception as exc:messagebox.showerror('تأیید',str(exc),parent=self)
    def _delete_row(self,r):
        pid=str(r.get('pending_id'));st=r.get('status')
        if st not in {'APPROVED','REJECTED'}:
            try:APPROVAL.reject(pid,actor_id='GUI_BULK')
            except Exception:pass
        self.rich.hide_review([pid]);self.refresh()
    def clear_finished(self):
        ids=[str(r['pending_id']) for r in self.rows if r.get('status') in {'APPROVED','REJECTED'}]
        if not ids:return messagebox.showinfo('پاک‌سازی','مورد تأیید/ردشده‌ای در نمای فعلی نیست.',parent=self)
        if messagebox.askyesno('پاک‌سازی',f'{len(ids)} ردیف از نمای ثبت دیتا مخفی شود؟ اطلاعات مالی و Audit حذف نمی‌شوند.',parent=self):self.rich.hide_review(ids);self.refresh()
    def merge_selected(self):
        rows=self.table.selected_rows()
        if len(rows)<2:return messagebox.showwarning('تجمیع','حداقل دو ردیف Pending را انتخاب کن.',parent=self)
        if any(str((r.get('payload') or {}).get('detected_type') or '').upper()=='CHEQUE' for r in rows):
            return messagebox.showwarning('تجمیع','چک‌ها را با رسیدهای عادی Merge نکن. چک‌ها جدا ثبت می‌شوند و بعد به هزینه اصلی لینک می‌شوند.',parent=self)
        rows=[r for r in rows if r.get('status') in {'PENDING_REVIEW','NEEDS_REVIEW'}]
        if len(rows)<2:return
        total=sum(as_int((r.get('payload') or {}).get('amount') or (r.get('payload') or {}).get('final_amount')) for r in rows)
        desc=simpledialog.askstring('تجمیع رسیدها','شرح هزینه اصلی:',initialvalue=str((rows[0].get('payload') or {}).get('description') or rows[0].get('raw_text') or ''),parent=self)
        if desc is None:return
        invoice=simpledialog.askinteger('مبلغ فاکتور/تعهد','مبلغ کل فاکتور یا تعهد (تومان):',initialvalue=total,parent=self,minvalue=0)
        if invoice is None:return
        primary=rows[0];pp=dict(primary.get('payload') or {});pp.update({'detected_type':'EXPENSE','description':desc,'payer_name':pp.get('payer_name') or 'تنخواه','amount':total,'paid_amount':total,'invoice_amount':invoice,'final_amount':invoice,'payment_state':'PAID' if total>=invoice else 'PARTIAL','remaining_debt':max(invoice-total,0)})
        APPROVAL.save_payload(primary['pending_id'],pp,learn=False)
        for r in rows[1:]:
            p=dict(r.get('payload') or {});p.update({'detected_type':'DOCUMENT','document_type':p.get('document_type') or 'RECEIPT','link_pending_id':primary['pending_id'],'description':p.get('description') or desc});APPROVAL.save_payload(r['pending_id'],p,learn=False)
        msg=f"{len(rows)} سند در یک پرونده آماده شد.\nپرداخت جمع‌شده: {fmt_money(total)}\nتعهد/فاکتور: {fmt_money(invoice)}\n\nابتدا ردیف اصلی را تأیید کن؛ بقیه به‌عنوان داکیومنت به آن متصل می‌شوند."
        messagebox.showinfo('تجمیع',msg,parent=self);self.refresh()

    def analyze_selected(self):
        rows=self.table.selected_rows() or ([self.current] if self.current else []);ids=[str(r['pending_id']) for r in rows if r and self._path(r) and r.get('status') in {'PENDING_REVIEW','NEEDS_REVIEW'}]
        if not ids:return messagebox.showinfo('AI','تصویر قابل تحلیل در انتخاب وجود ندارد.',parent=self)
        self.action.set(f'در حال تحلیل {len(ids)} تصویر...')
        def worker():
            ok=0;errs=[]
            for pid in ids:
                try:asyncio.run(APPROVAL.analyze_pending_with_ai(pid));ok+=1
                except Exception as exc:errs.append(str(exc))
            self.after(0,lambda:(self.action.set(f'{ok} تحلیل موفق | {len(errs)} خطا'),self.refresh()))
        threading.Thread(target=worker,daemon=True).start()


# ---------- price / phase drilldown ----------
class ComponentEditDialog(tk.Toplevel):
    def __init__(self,parent,row:dict[str,Any]|None,on_save):
        super().__init__(parent);self.row=row or {};self.on_save=on_save;self.title('جزئیات قلم قیمت');self.configure(bg=DARK['bg']);self.transient(parent);self.grab_set()
        self.vars={k:tk.StringVar(value=str(self.row.get(k) or '')) for k in ('description','unit','quantity','coefficient','unit_rate','source')}
        self.vars['quantity'].set(str(self.row.get('quantity') if self.row.get('quantity') is not None else 1));self.vars['coefficient'].set(str(self.row.get('coefficient') if self.row.get('coefficient') is not None else 1));self.vars['unit_rate'].set(group_int(self.row.get('unit_rate') or 0))
        body=tk.Frame(self,bg=DARK['panel']);body.pack(fill='both',expand=True,padx=10,pady=10)
        for i,(k,l) in enumerate([('description','شرح'),('unit','واحد'),('quantity','مقدار'),('coefficient','ضریب'),('unit_rate','قیمت واحد'),('source','منبع/توضیح')]):
            tk.Label(body,text=l+':',bg=DARK['panel'],fg=DARK['muted']).grid(row=i,column=1,sticky='e',padx=5,pady=4);e=ttk.Entry(body,textvariable=self.vars[k],width=42,justify='right');e.grid(row=i,column=0,padx=5,pady=4)
            if k=='unit_rate':bind_grouped_number(e,self.vars[k])
        tk.Button(body,text='ذخیره',command=self.save,bg=DARK['blue'],fg='white',relief='flat',padx=16,pady=7).grid(row=7,column=0,columnspan=2,pady=10)
    def save(self):
        try:
            d={k:v.get().strip() for k,v in self.vars.items()};d['quantity']=float(d['quantity'] or 0);d['coefficient']=float(d['coefficient'] or 0);d['unit_rate']=parse_int(d['unit_rate']);self.destroy();self.on_save(d)
        except Exception as exc:messagebox.showerror('خطا',str(exc),parent=self)

class PriceDetailDialog(tk.Toplevel):
    def __init__(self,parent,rich:RichBudgetService,row:dict[str,Any],on_refresh):
        super().__init__(parent);self.rich=rich;self.row=row;self.pid=row['price_id'];self.on_refresh=on_refresh;self.title(f"قیمت — {row['description']}");self.geometry('1120x720');self.configure(bg=DARK['bg']);self.transient(parent)
        head=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);head.pack(fill='x',padx=8,pady=8)
        tk.Label(head,text=row['description'],bg=DARK['surface'],fg=DARK['text'],font=('Segoe UI',12,'bold')).pack(side='right',padx=10,pady=8);tk.Label(head,text=row.get('unit') or '-',bg=DARK['surface'],fg=DARK['muted'],font=('Segoe UI',9)).pack(side='right')
        rates=tk.Frame(self,bg=DARK['panel']);rates.pack(fill='x',padx=8,pady=(0,7));self.rv={}
        for i,(k,l) in enumerate([('estimate_rate','قیمت برآورد'),('actual_rate','قیمت واقعی مرجع'),('forecast_rate','قیمت پیش‌بینی')]):
            box=tk.Frame(rates,bg=DARK['panel2'],highlightbackground=DARK['line'],highlightthickness=1);box.pack(side='right',fill='x',expand=True,padx=3,pady=5);tk.Label(box,text=l,bg=DARK['panel2'],fg=DARK['muted'],font=('Segoe UI',8)).pack(anchor='e',padx=8,pady=(5,2));v=tk.StringVar(value=group_int(row.get(k) or 0));self.rv[k]=v;e=ttk.Entry(box,textvariable=v,justify='center');e.pack(fill='x',padx=8,pady=(0,7));bind_grouped_number(e,v)
        tk.Button(rates,text='ذخیره قیمت‌ها',command=self.save_rates,bg=DARK['blue'],fg='white',relief='flat',padx=12,pady=6).pack(side='left',padx=6)
        mid=ttk.Panedwindow(self,orient='horizontal');mid.pack(fill='both',expand=True,padx=8,pady=(0,8))
        cbox=tk.Frame(mid,bg=DARK['panel']);abox=tk.Frame(mid,bg=DARK['panel']);mid.add(cbox,weight=7);mid.add(abox,weight=3)
        self.table=SmartTable(cbox,[('desc','قلم',260),('unit','واحد',75),('qty','مقدار',90),('coef','ضریب',75),('rate','قیمت واحد',120),('total','جمع',125),('src','منبع',140)],title='نحوه محاسبه قیمت')
        self.table.pack(fill='both',expand=True,padx=5,pady=5);self.table.set_edit_handler(self.edit_comp);self.table.set_delete_handler(self.delete_comp)
        bar=tk.Frame(cbox,bg=DARK['panel']);bar.pack(fill='x',padx=5,pady=(0,5));tk.Button(bar,text='➕ قلم',command=self.add_comp,bg=DARK['glass'],fg='white',relief='flat',padx=10,pady=4).pack(side='right');tk.Label(bar,text='برای اقلام ساده یک سطر ۱ × قیمت واحد است؛ ضریب قابل تغییر است.',bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',7)).pack(side='left')
        tk.Label(abox,text='پیش‌فاکتورها و فایل‌های مرجع',bg=DARK['panel'],fg='#7FC9FF',font=('Segoe UI',9,'bold')).pack(anchor='e',padx=7,pady=7)
        self.atree=ttk.Treeview(abox,columns=('file','total'),show='headings',height=12);self.atree.heading('file',text='فایل');self.atree.heading('total',text='جمع ثبت‌شده');self.atree.column('file',width=190);self.atree.column('total',width=120);self.atree.pack(fill='both',expand=True,padx=7)
        ab=tk.Frame(abox,bg=DARK['panel']);ab.pack(fill='x',padx=7,pady=7);tk.Button(ab,text='📎 اتصال پیش‌فاکتور',command=self.attach,bg=DARK['blue'],fg='white',relief='flat',padx=8,pady=5).pack(side='right');tk.Button(ab,text='👁 باز کردن',command=self.open_att,bg=DARK['glass'],fg='white',relief='flat',padx=8,pady=5).pack(side='right',padx=3)
        self.refresh()
    def refresh(self):
        p=self.rich.get_price(self.pid) or self.row
        if not p.get('aggregate'):self.rich.ensure_single_component(self.pid)
        rows=self.rich.list_components(self.pid);self.table.set_rows(rows,lambda r:[r['description'],r.get('unit') or '-',f"{float(r.get('quantity') or 0):,.3f}",f"{float(r.get('coefficient') or 0):,.3f}",fmt_money(r.get('unit_rate')),fmt_money(r.get('total')),r.get('source') or '-'])
        for x in self.atree.get_children():self.atree.delete(x)
        self.atts=self.rich.list_attachments(self.pid)
        for i,a in enumerate(self.atts):self.atree.insert('', 'end',iid=str(i),values=(a.get('file_name') or Path(a['local_path']).name,fmt_money(a.get('quoted_total'))))
        p=self.rich.get_price(self.pid) or {}
        for k in self.rv:self.rv[k].set(group_int(p.get(k) or 0))
    def save_rates(self):
        try:self.rich.save_price_rates(self.pid,parse_int(self.rv['estimate_rate'].get()),parse_int(self.rv['actual_rate'].get()),parse_int(self.rv['forecast_rate'].get()));self.on_refresh();self.refresh()
        except Exception as exc:messagebox.showerror('قیمت',str(exc),parent=self)
    def add_comp(self):ComponentEditDialog(self,None,lambda d:(self.rich.upsert_component(self.pid,d),self.refresh(),self.on_refresh()))
    def edit_comp(self,r):ComponentEditDialog(self,r,lambda d:(self.rich.upsert_component(self.pid,d,r['component_id']),self.refresh(),self.on_refresh()))
    def delete_comp(self,r):
        if messagebox.askyesno('حذف قلم',f"قلم «{r.get('description')}» حذف شود؟",parent=self):self.rich.delete_component(r['component_id']);self.refresh();self.on_refresh()
    def attach(self):
        p=filedialog.askopenfilename(parent=self,filetypes=[('پیش‌فاکتور','*.xlsx *.pdf *.jpg *.jpeg *.png *.webp'),('همه فایل‌ها','*.*')])
        if not p:return
        detected=0
        if Path(p).suffix.lower()=='.xlsx':
            try:detected=self.rich._detect_excel_total(Path(p))
            except Exception:pass
        total=simpledialog.askinteger('جمع پیش‌فاکتور','جمع مؤثر این پیش‌فاکتور (تومان):',initialvalue=detected,parent=self,minvalue=0)
        if total is None:return
        self.rich.add_quote_attachment(self.pid,p,total);self.refresh();self.on_refresh()
    def open_att(self):
        s=self.atree.selection()
        if not s:return
        path=self.atts[int(s[0])]['local_path']
        try:os.startfile(path) if os.name=='nt' else subprocess.Popen(['xdg-open',path])
        except Exception as exc:messagebox.showerror('فایل',str(exc),parent=self)

class PhaseItemEditDialog(tk.Toplevel):
    def __init__(self,parent,rich:RichBudgetService,row:dict[str,Any],on_save):
        super().__init__(parent);self.rich=rich;self.row=row;self.on_save=on_save;self.title('نحوه محاسبه ریز فاز');self.geometry('760x600');self.configure(bg=DARK['bg']);self.transient(parent);self.grab_set()
        p=rich.get_price(row.get('price_id')) or {};self.vars={}
        vals={'description':row.get('description') or '','section':row.get('section') or '','cost_type':row.get('cost_type') or '','unit':row.get('unit') or '',
              'qty_estimate':str(row.get('qty_estimate') or 0),'qty_actual':str(row.get('qty_actual') or 0),'qty_forecast':str(row.get('qty_forecast') or 0),'factor':str(row.get('factor') or 1)}
        body=tk.Frame(self,bg=DARK['panel']);body.pack(fill='both',expand=True,padx=10,pady=10)
        for i,(k,l) in enumerate([('description','شرح'),('section','بخش'),('cost_type','نوع هزینه'),('unit','واحد'),('qty_estimate','حجم برآورد'),('qty_actual','حجم واقعی'),('qty_forecast','حجم پیش‌بینی'),('factor','ضریب')]):
            v=tk.StringVar(value=vals[k]);self.vars[k]=v;tk.Label(body,text=l+':',bg=DARK['panel'],fg=DARK['muted']).grid(row=i,column=1,sticky='e',padx=5,pady=4);ttk.Entry(body,textvariable=v,justify='right',width=42).grid(row=i,column=0,sticky='ew',padx=5,pady=4)
        rates=tk.Label(body,text=f"قیمت واحد از تب قیمت‌ها می‌آید:  برآورد {fmt_money(p.get('estimate_rate'))}  |  واقعی {fmt_money(p.get('actual_rate'))}  |  پیش‌بینی {fmt_money(p.get('forecast_rate'))}",bg=DARK['panel2'],fg='#A8D8FF',font=('Segoe UI',8),padx=8,pady=8);rates.grid(row=8,column=0,columnspan=2,sticky='ew',pady=7)
        calc=tk.Label(body,text='',bg=DARK['panel'],fg=DARK['text'],font=('Segoe UI',9,'bold'),justify='right');calc.grid(row=9,column=0,columnspan=2,sticky='ew',pady=5);self.calc=calc
        for k in ('qty_estimate','qty_actual','qty_forecast','factor'):self.vars[k].trace_add('write',lambda *_:self._recalc(p))
        b=tk.Frame(body,bg=DARK['panel']);b.grid(row=10,column=0,columnspan=2,sticky='ew',pady=8);tk.Button(b,text='💰 باز کردن قیمت مرجع',command=lambda:PriceDetailDialog(self,self.rich,p,lambda:self._reload_price()),bg=DARK['glass'],fg='white',relief='flat',padx=9,pady=5).pack(side='right');tk.Button(b,text='ذخیره',command=self.save,bg=DARK['blue'],fg='white',relief='flat',padx=14,pady=6).pack(side='right',padx=4)
        self._recalc(p)
    def _reload_price(self):pass
    def _recalc(self,p):
        try:
            f=float(self.vars['factor'].get() or 0);qe=float(self.vars['qty_estimate'].get() or 0);qa=float(self.vars['qty_actual'].get() or 0);qf=float(self.vars['qty_forecast'].get() or 0)
            self.calc.configure(text=f"برآورد = {fmt_money(qe*f*int(p.get('estimate_rate') or 0))}\nواقعی = {fmt_money(qa*f*int(p.get('actual_rate') or p.get('estimate_rate') or 0))}\nپیش‌بینی = {fmt_money(qf*f*int(p.get('forecast_rate') or p.get('estimate_rate') or 0))}")
        except Exception:pass
    def save(self):
        try:
            d={k:v.get().strip() for k,v in self.vars.items()};
            for k in ('qty_estimate','qty_actual','qty_forecast','factor'):d[k]=float(d[k] or 0)
            self.rich.save_phase_item(self.row['phase_item_id'],**d);self.destroy();self.on_save()
        except Exception as exc:messagebox.showerror('ریز فاز',str(exc),parent=self)

class PhaseDetailDialog163(tk.Toplevel):
    def __init__(self,parent,rich:RichBudgetService,phase_no:int,phase_name:str,on_refresh):
        super().__init__(parent);self.rich=rich;self.phase_no=int(phase_no);self.phase_name=phase_name;self.on_refresh=on_refresh;self.title(f"فاز {phase_no:02d} — {phase_name}");self.geometry('1360x760');self.configure(bg=DARK['bg']);self.transient(parent)
        head=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);head.pack(fill='x',padx=8,pady=8);tk.Label(head,text=f"فاز {fa(f'{phase_no:02d}')} — {phase_name}",bg=DARK['surface'],fg=DARK['text'],font=('Segoe UI',12,'bold')).pack(side='right',padx=10,pady=8);tk.Button(head,text='⚙ وضعیت و پیشرفت فاز',command=self.edit_progress,bg=DARK['glass'],fg='white',relief='flat',padx=9,pady=5).pack(side='left',padx=5)
        self.table=SmartTable(self,[('section','بخش',125),('desc','شرح/فعالیت',235),('type','نوع',75),('unit','واحد',80),('qe','حجم برآورد',95),('qa','حجم واقعی',95),('qf','حجم پیش‌بینی',100),('rate','نرخ برآورد',115),('est','برآورد',125),('actual','واقعی',125),('remain','مانده پایه',125),('forecast','پیش‌بینی',125),('var','انحراف',115)],title='ریز فاز — دابل‌کلیک برای نحوه محاسبه و اصلاح احجام')
        self.table.pack(fill='both',expand=True,padx=8,pady=(0,6));self.table.set_edit_handler(self.edit_item);self.table.set_delete_handler(self.delete_item)
        bar=tk.Frame(self,bg=DARK['bg']);bar.pack(fill='x',padx=8,pady=(0,8));tk.Button(bar,text='➕ افزودن فعالیت',command=self.add_item,bg=DARK['blue'],fg='white',relief='flat',padx=10,pady=5).pack(side='right');tk.Button(bar,text='✏️ ویرایش کامل',command=lambda:self.edit_item(self.one()),bg=DARK['glass'],fg='white',relief='flat',padx=10,pady=5).pack(side='right',padx=3);tk.Label(bar,text='قیمت‌های واحد از تب «قیمت‌ها» خوانده می‌شوند؛ در اینجا حجم و ضریب اصلاح می‌شود.',bg=DARK['bg'],fg=DARK['muted'],font=('Segoe UI',8)).pack(side='left')
        self.refresh()
    def rows(self):return self.rich.list_phase_items(self.phase_no)
    def refresh(self):
        rows=self.rows();legacy={}
        try:
            for x in SERVICE.budget.report_rows():
                if norm(x.get('phase'))==norm(self.phase_name):legacy[norm(x.get('activity'))]=int(x.get('actual') or 0)
        except Exception:pass
        def rv(r):
            f=float(r.get('factor') or 1);qe=float(r.get('qty_estimate') or 0);qa=float(r.get('qty_actual') or 0);qf=float(r.get('qty_forecast') or qe);er=int(r.get('estimate_rate') or r.get('local_estimate_rate') or 0);ar=int(r.get('actual_rate') or er);fr=int(r.get('forecast_rate') or er);est=int(qe*f*er);act=legacy.get(norm(r['description']),int(qa*f*ar));
            inferred_qa=qa
            if act>0 and qa<=0 and ar>0 and f>0:inferred_qa=min(qf,act/(ar*f))
            remaining_qty=max(qf-inferred_qa,0);fc=max(act,int(act+remaining_qty*f*fr));return [r.get('section') or '-',r['description'],r.get('cost_type') or '-',r.get('unit') or '-',fa(f'{qe:,.3f}'),fa(f'{qa:,.3f}'),fa(f'{qf:,.3f}'),fmt_money(er),fmt_money(est),fmt_money(act),fmt_money(max(est-act,0)),fmt_money(fc),fmt_money(fc-est)]
        self.table.set_rows(rows,rv)
    def one(self):
        r=self.table.selected_rows();return r[0] if r else None
    def edit_item(self,r):
        if r:PhaseItemEditDialog(self,self.rich,r,lambda:(self.refresh(),self.on_refresh()))
    def delete_item(self,r):
        if r and messagebox.askyesno('حذف فعالیت',f"«{r.get('description')}» حذف شود؟",parent=self):self.rich.delete_phase_item(r['phase_item_id']);self.refresh();self.on_refresh()
    def add_item(self):
        PhaseNewItemDialog(self,self.rich,self.phase_no,self.phase_name,lambda:(self.refresh(),self.on_refresh()))
    def edit_progress(self):PhaseProgressDialog(self,self.rich,self.phase_no,self.phase_name,lambda:(self.refresh(),self.on_refresh()))

class PhaseNewItemDialog(tk.Toplevel):
    def __init__(self,parent,rich,phase_no,phase_name,on_save):
        super().__init__(parent);self.rich=rich;self.no=phase_no;self.name=phase_name;self.on_save=on_save;self.title('افزودن فعالیت');self.transient(parent);self.grab_set();self.configure(bg=DARK['bg'])
        keys=[('description','شرح'),('section','بخش'),('cost_type','نوع هزینه'),('unit','واحد'),('qty_estimate','حجم برآورد'),('qty_actual','حجم واقعی'),('qty_forecast','حجم پیش‌بینی'),('factor','ضریب'),('estimate_rate','قیمت برآورد اولیه')];self.vars={k:tk.StringVar() for k,_ in keys};self.vars['factor'].set('1')
        body=tk.Frame(self,bg=DARK['panel']);body.pack(padx=10,pady=10)
        for i,(k,l) in enumerate(keys):tk.Label(body,text=l+':',bg=DARK['panel'],fg=DARK['muted']).grid(row=i,column=1,sticky='e',padx=4,pady=3);ttk.Entry(body,textvariable=self.vars[k],width=40,justify='right').grid(row=i,column=0,padx=4,pady=3)
        tk.Button(body,text='افزودن',command=self.save,bg=DARK['blue'],fg='white',relief='flat',padx=14,pady=6).grid(row=len(keys),column=0,columnspan=2,pady=8)
    def save(self):
        try:
            d={k:v.get().strip() for k,v in self.vars.items()};
            for k in ('qty_estimate','qty_actual','qty_forecast','factor'):d[k]=float(d[k] or 0)
            d['estimate_rate']=parse_int(d['estimate_rate']);self.rich.add_phase_item(self.no,self.name,d);self.destroy();self.on_save()
        except Exception as exc:messagebox.showerror('افزودن فعالیت',str(exc),parent=self)

class PhaseProgressDialog(tk.Toplevel):
    def __init__(self,parent,rich,phase_no,phase_name,on_save):
        super().__init__(parent);self.rich=rich;self.no=phase_no;self.on_save=on_save;self.title(f'پیشرفت فاز {phase_no:02d}');self.transient(parent);self.grab_set();self.configure(bg=DARK['bg']);cur=rich.get_phase_progress().get(phase_no,{})
        self.status=tk.StringVar(value={'NOT_STARTED':'شروع نشده','ACTIVE':'در حال اجرا','PAUSED':'متوقف','COMPLETED':'تکمیل'}.get(cur.get('status'),'شروع نشده'));self.progress=tk.StringVar(value=str(cur.get('physical_progress') or 0));self.start=tk.StringVar(value=cur.get('actual_start_shamsi') or '');self.end=tk.StringVar(value=cur.get('actual_end_shamsi') or '');self.notes=tk.StringVar(value=cur.get('notes') or '')
        body=tk.Frame(self,bg=DARK['panel']);body.pack(padx=12,pady=12)
        ttk.Label(body,text=phase_name).grid(row=0,column=0,columnspan=2,pady=5)
        for i,(l,w) in enumerate([('وضعیت',ttk.Combobox(body,textvariable=self.status,state='readonly',values=['شروع نشده','در حال اجرا','متوقف','تکمیل'],width=28)),('درصد پیشرفت',ttk.Entry(body,textvariable=self.progress,width=30,justify='center')),('شروع واقعی',DateField(body,self.start,width=26)),('پایان واقعی',DateField(body,self.end,width=26)),('یادداشت',ttk.Entry(body,textvariable=self.notes,width=31,justify='right'))],1):tk.Label(body,text=l+':',bg=DARK['panel'],fg=DARK['muted']).grid(row=i,column=1,sticky='e',padx=4,pady=4);w.grid(row=i,column=0,padx=4,pady=4,sticky='ew')
        tk.Button(body,text='ذخیره',command=self.save,bg=DARK['blue'],fg='white',relief='flat',padx=12,pady=6).grid(row=7,column=0,columnspan=2,pady=8)
    def save(self):
        try:
            st={'شروع نشده':'NOT_STARTED','در حال اجرا':'ACTIVE','متوقف':'PAUSED','تکمیل':'COMPLETED'}[self.status.get()];self.rich.set_phase_progress(self.no,st,float(self.progress.get() or 0),self.start.get(),self.end.get(),self.notes.get());self.destroy();self.on_save()
        except Exception as exc:messagebox.showerror('پیشرفت',str(exc),parent=self)

class KPIDetailDialog(tk.Toplevel):
    def __init__(self,parent,title,formula,details):
        super().__init__(parent);self.title(title);self.geometry('720x470');self.configure(bg=DARK['bg']);self.transient(parent)
        tk.Label(self,text=title,bg=DARK['surface'],fg=DARK['text'],font=('Segoe UI',12,'bold'),padx=12,pady=10).pack(fill='x')
        t=tk.Text(self,wrap='word',bg=DARK['panel'],fg=DARK['text'],relief='flat',font=('Segoe UI',9),padx=12,pady=12);t.pack(fill='both',expand=True,padx=8,pady=8);t.insert('1.0',f"نحوه محاسبه:\n{formula}\n\nجزئیات فعلی:\n{details}");t.configure(state='disabled')


class MiniBarChart(tk.Canvas):
    def __init__(self,parent,title:str,height=180):
        super().__init__(parent,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1,height=height);self.title=title;self.rows=[];self.bind('<Configure>',lambda e:self.redraw())
    def set_rows(self,rows:list[tuple[str,float,float,float]]):self.rows=rows;self.redraw()
    def redraw(self):
        self.delete('all');w=max(400,self.winfo_width());h=max(140,self.winfo_height());self.create_text(w-12,13,text=self.title,anchor='ne',fill=DARK['text'],font=('Segoe UI',9,'bold'))
        if not self.rows:return
        maxv=max([v for _,a,b,c in self.rows for v in (a,b,c)]+[1]);x0,y0,x1,y1=32,35,w-12,h-22;n=len(self.rows);gw=(x1-x0)/max(1,n)
        colors=[DARK['muted'],DARK['green'],DARK['blue']]
        for i,(lab,a,b,c) in enumerate(self.rows):
            base=x0+i*gw;bw=max(2,(gw-4)/3)
            for j,v in enumerate((a,b,c)):
                hh=(y1-y0)*(v/maxv);self.create_rectangle(base+2+j*bw,y1-hh,base+2+(j+1)*bw-1,y1,fill=colors[j],outline='')
            if n<=16 or i%2==0:self.create_text(base+gw/2,y1+9,text=fa(lab),fill=DARK['muted'],font=('Segoe UI',6))
        lx=42
        for label,c in [('برآورد',colors[0]),('واقعی',colors[1]),('پیش‌بینی',colors[2])]:self.create_rectangle(lx,y0-15,lx+9,y0-6,fill=c,outline='');self.create_text(lx+13,y0-10,text=label,anchor='w',fill=DARK['muted'],font=('Segoe UI',7));lx+=82

class ProjectFinancialOverview(tk.Toplevel):
    def __init__(self,parent,rich:RichBudgetService):
        super().__init__(parent);self.rich=rich;self.title('مشخصات کلی مالی پروژه');self.geometry('980x650');self.configure(bg=DARK['bg']);self.transient(parent);self._build()
    def _build(self):
        o=SERVICE.overview();s=self.rich.list_phase_summary();est=sum(r['estimate'] for r in s);actual=int(o.construction_cost);remain=max(est-actual,0);forecast=max(sum(r['forecast'] for r in s),actual);settings=SERVICE.budget.get_settings();area=float(settings.get('gross_area') or 0)+float(settings.get('saleable_area') or 0)
        tk.Label(self,text='مشخصات کلی مالی پروژه',bg=DARK['surface'],fg=DARK['text'],font=('Segoe UI',13,'bold'),pady=12).pack(fill='x')
        g=tk.Frame(self,bg=DARK['bg']);g.pack(fill='x',padx=10,pady=10)
        vals=[('پیشرفت فیزیکی',f"{fa(f'{self.rich.overall_physical_progress():.1f}')}٪",DARK['blue']),('برآورد پایه',fmt_money(est),DARK['muted']),('هزینه انجام‌شده',fmt_money(actual),DARK['green']),('مانده با نرخ پایه',fmt_money(remain),DARK['orange']),('پیش‌بینی پایان',fmt_money(forecast),DARK['blue']),('انحراف',fmt_money(forecast-est),DARK['red'] if forecast>est else DARK['green']),('تنخواه',fmt_money(o.cash_balance),DARK['cyan']),('تعهد چک',fmt_money(o.open_cheque_commitments),DARK['red']),('ساخت/مترمربع',fmt_money(actual/area if area else 0),DARK['orange'])]
        for i,(t,v,c) in enumerate(vals):
            card=tk.Frame(g,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);card.grid(row=i//3,column=i%3,sticky='nsew',padx=4,pady=4);g.grid_columnconfigure(i%3,weight=1);tk.Label(card,text=t,bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',8)).pack(anchor='e',padx=8,pady=(7,1));tk.Label(card,text=v,bg=DARK['panel'],fg=c,font=('Segoe UI',11,'bold')).pack(anchor='e',padx=8,pady=(1,8))
        table=SmartTable(self,[('no','فاز',55),('name','عنوان',220),('est','برآورد',130),('act','واقعی',130),('rem','مانده پایه',130),('fc','پیش‌بینی',130),('var','انحراف',120)],title='جمع‌بندی ۳۲ فاز');table.pack(fill='both',expand=True,padx=10,pady=(0,10));table.set_rows(s,lambda r:[fa(f"{r['phase_no']:02d}"),r['phase'],fmt_money(r['estimate']),fmt_money(r['actual']),fmt_money(r['remaining_base']),fmt_money(r['forecast']),fmt_money(r['variance'])])

class Stage163Dashboard(Stage15Dashboard):
    def __init__(self):
        self.rich=RichBudgetService(DB,BASE_DIR);self._bot_process=None;self._bot_log=None;self._logo_img=None
        super().__init__();self.title('BARKAV — Engineering & Construction — Peymaan 16.3');self.after(1200,self._autosave_loop)
    def set_bot_process(self,p,log=None):
        self._bot_process=p;self._bot_log=log
        if self.approval_center and hasattr(self.approval_center,'set_bot_process'):self.approval_center.set_bot_process(p,log)
    def _style(self):
        st=ttk.Style(self)
        try:st.theme_use('clam')
        except Exception:pass
        st.configure('.',font=('Segoe UI',8),background=DARK['bg'],foreground=DARK['text']);st.configure('TFrame',background=DARK['bg']);st.configure('Panel.TFrame',background=DARK['panel']);st.configure('TLabel',background=DARK['bg'],foreground=DARK['text'])
        st.configure('TNotebook',background=DARK['bg'],borderwidth=0,tabmargins=(0,4,0,0));st.configure('TNotebook.Tab',padding=(15,8),font=('Segoe UI',8,'bold'),background='#0D1928',foreground='#8092A9',borderwidth=0)
        # Active tab is intentionally brighter/raised; this corrects the old reversed state.
        st.map('TNotebook.Tab',background=[('selected','#245A96'),('active','#183552')],foreground=[('selected','#FFFFFF'),('active','#EAF5FF')],expand=[('selected',(1,2,1,0))])
        st.configure('TButton',padding=(7,5),background=DARK['glass'],foreground=DARK['text'],bordercolor=DARK['line']);st.map('TButton',background=[('active','#223B58')]);st.configure('Primary.TButton',background=DARK['blue'],foreground='white',font=('Segoe UI',8,'bold'));st.configure('Toolbar.TButton',padding=(5,3),font=('Segoe UI',7),background='#14263A');st.configure('Compact.TButton',padding=(4,2),font=('Segoe UI',7),background='#14263A');st.configure('Danger.TButton',background=DARK['red'],foreground='white')
        st.configure('TEntry',fieldbackground='#0A1624',foreground=DARK['text'],insertcolor='white',bordercolor=DARK['line']);st.configure('Compact.TEntry',fieldbackground='#0A1624',foreground=DARK['text']);st.configure('TCombobox',fieldbackground='#0A1624',background='#0A1624',foreground=DARK['text'],arrowcolor=DARK['text'])
        st.configure('TLabelframe',background=DARK['panel'],bordercolor=DARK['line'],relief='solid',borderwidth=1);st.configure('TLabelframe.Label',background=DARK['panel'],foreground='#7FC9FF',font=('Segoe UI',8,'bold'));st.configure('Dashboard.TLabelframe',background=DARK['panel'],bordercolor=DARK['line']);st.configure('Dashboard.TLabelframe.Label',background=DARK['panel'],foreground='#7FC9FF',font=('Segoe UI',9,'bold'));st.configure('Report.TLabelframe',background=DARK['panel'],bordercolor=DARK['line']);st.configure('Report.TLabelframe.Label',background=DARK['panel'],foreground='#7FC9FF',font=('Segoe UI',8,'bold'))
        st.configure('Treeview',rowheight=25,background='#0C1827',fieldbackground='#0C1827',foreground=DARK['text'],bordercolor=DARK['line'],font=('Segoe UI',8));st.configure('Treeview.Heading',font=('Segoe UI',7,'bold'),background='#162B43',foreground='#EAF5FF',padding=(3,4));st.map('Treeview',background=[('selected','#245B8B')],foreground=[('selected','#FFFFFF')])
    def _build(self):
        top=tk.Frame(self,bg='#081421',height=58,highlightbackground=DARK['line'],highlightthickness=1);top.pack(fill='x')
        brand=tk.Frame(top,bg='#081421');brand.pack(side='left',padx=10,pady=5)
        # Optional image logo; English descriptor is separate so the Persian subtitle is not used.
        logo=BASE_DIR/'assets'/'barkav_brand_header.png'
        logo_loaded=False
        if logo.exists() and Image is not None:
            try:
                im=Image.open(logo).convert('RGB');im.thumbnail((185,50));self._logo_img=ImageTk.PhotoImage(im);tk.Label(brand,image=self._logo_img,bg='white').pack(side='left',padx=(0,8));logo_loaded=True
            except Exception:pass
        if not logo_loaded:
            bt=tk.Frame(brand,bg='#081421');bt.pack(side='left');tk.Label(bt,text='BARKAV',bg='#081421',fg='white',font=('Arial',13,'bold')).pack(anchor='w');tk.Label(bt,text='ENGINEERING & CONSTRUCTION',bg='#081421',fg='#91A5BB',font=('Arial',6)).pack(anchor='w')
        right=tk.Frame(top,bg='#081421');right.pack(side='right',padx=12,pady=5);self.project_name_top=tk.StringVar(value='پروژه');self.datetime_top=tk.StringVar(value='');tk.Label(right,textvariable=self.project_name_top,bg='#081421',fg='#A7D9FF',font=('Segoe UI',9,'bold')).pack(side='right',padx=7);tk.Label(right,textvariable=self.datetime_top,bg='#081421',fg=DARK['text'],font=('Segoe UI',8)).pack(side='right',padx=10)
        tools=tk.Frame(top,bg='#081421');tools.pack(side='right',padx=8)
        for text,cmd,tip in [('💾 ذخیره',self.manual_save,'ساخت بکاپ دستی از دیتابیس فعال'),('Save As',self.save_as,'ذخیره کپی دیتابیس در مسیر دلخواه'),('↶ Undo',self.undo,'برگرداندن آخرین تغییر قیمت/ریزفاز'),('↷ Redo',self.redo,'اجرای دوباره آخرین تغییر Undo شده'),('🔄',self.refresh_all,'بروزرسانی همه اطلاعات'),('⚙ سیستم',self.show_health,'وضعیت عملکرد سیستم')]:
            b=tk.Button(tools,text=text,command=cmd,bg='#14263A',fg='white',activebackground='#245A96',activeforeground='white',relief='flat',font=('Segoe UI',7),padx=7,pady=4);b.pack(side='right',padx=2);add_tooltip(b,tip)
        self.notebook=ttk.Notebook(self);self.notebook.pack(fill='both',expand=True,padx=6,pady=5)
        self._build_overview();self._build_manager();self._build_financial();self._build_cheques();self._build_sales();self._build_reconciliation();self._build_reports();self._build_health();self._attach_common_tooltips(self);self._tick_clock()
    def _build_approval_center(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.approval_tab=tab;self.notebook.insert(1,tab,text='ثبت دیتا');self.approval_center=DataEntryCenter163(tab,self.rich,on_posted=self.refresh_all);self.approval_center.pack(fill='both',expand=True)
        if self._bot_process:self.approval_center.set_bot_process(self._bot_process,self._bot_log)
    def _update_approval_tab_text(self,count:int):
        # Keep the selected-tab geometry stable; count is visible inside the table instead.
        try:self.notebook.tab(self.approval_tab,text='ثبت دیتا')
        except Exception:pass
    def _build_overview(self):
        tab=ttk.Frame(self.notebook,padding=5);self.notebook.add(tab,text='داشبورد');wrap=ttk.Frame(tab);wrap.pack(fill='both',expand=True);canvas=tk.Canvas(wrap,bg=DARK['bg'],highlightthickness=0);vs=ttk.Scrollbar(wrap,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=vs.set);canvas.pack(side='left',fill='both',expand=True);vs.pack(side='right',fill='y');inner=tk.Frame(canvas,bg=DARK['bg']);win=canvas.create_window((0,0),window=inner,anchor='nw');inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')));canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width));canvas.bind('<Enter>',lambda e:canvas.bind_all('<MouseWheel>',lambda ev:canvas.yview_scroll(int(-1*(ev.delta/120)),'units')));canvas.bind('<Leave>',lambda e:canvas.unbind_all('<MouseWheel>'))
        proj=tk.Frame(inner,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);proj.pack(fill='x',padx=4,pady=(3,7));self.project_info=tk.StringVar(value='مشخصات پروژه');tk.Label(proj,text='نمای کلی پروژه',bg=DARK['surface'],fg='#7FC9FF',font=('Segoe UI',10,'bold')).pack(side='right',padx=10,pady=8);tk.Label(proj,textvariable=self.project_info,bg=DARK['surface'],fg=DARK['muted'],font=('Segoe UI',7),justify='right').pack(side='right',padx=8)
        self.cards={}
        def make_section(title,defs,cols=4):
            sec=tk.Frame(inner,bg=DARK['bg']);sec.pack(fill='x',padx=4,pady=4);tk.Label(sec,text=title,bg=DARK['bg'],fg='#7FC9FF',font=('Segoe UI',9,'bold')).pack(anchor='e',pady=(2,4));g=tk.Frame(sec,bg=DARK['bg']);g.pack(fill='x');
            for c in range(cols):g.grid_columnconfigure(c,weight=1,uniform=title)
            icons=['▣','◈','◉','▤','◫','◇','⌁','◎']
            for i,(k,t,c,info) in enumerate(defs):card=GlassMetricCard(g,t,c,icons[i%len(icons)],info);card.grid(row=i//cols,column=i%cols,sticky='nsew',padx=3,pady=3);self.cards[k]=card
            return sec,g
        make_section('گزارش مالی',[('cost','هزینه ساخت',DARK['orange'],'کل هزینه ساخت تحقق‌یافته تا امروز.'),('cash','مانده تنخواه',DARK['blue'],'مانده نقدی جاری.'),('free','مانده آزاد پس از چک',DARK['green'],'تنخواه پس از کسر تعهد چک‌های باز.'),('total_in','کل ورودی',DARK['cyan'],'جمع ورود وجه.'),('total_out','کل خروجی',DARK['red'],'جمع خروجی غیرساخت.'),('liq_obligation','تعهد ۳۰ روز',DARK['orange'],'تعهدات ۳۰ روز آینده.'),('liq_inflow','وصول ۳۰ روز',DARK['cyan'],'وصول برنامه‌ریزی‌شده ۳۰ روز آینده.'),('liq_projected','تراز ۳۰ روز',DARK['green'],'پیش‌بینی تراز نقدینگی ۳۰ روز آینده.')],4)
        sec,g=make_section('چک‌ها و تعهدات',[('ch_all_total','کل چک‌ها',DARK['blue'],'جمع همه چک‌های ثبت‌شده.'),('ch_open_total','چک‌های پاس‌نشده',DARK['red'],'تعهد باز چک‌ها.'),('ch30_count','تعداد سررسید ۳۰ روز',DARK['cyan'],'تعداد چک‌های سررسید ۳۰ روز آینده.'),('ch30_amount','مبلغ سررسید ۳۰ روز',DARK['orange'],'مبلغ چک‌های سررسید ۳۰ روز آینده.')],4);self.overview_cheque_table=CompactTable(sec,[('due','سررسید',90),('days','روز',65),('amount','مبلغ',120),('issuer','صاحب حساب',125),('bank','بانک',100),('receiver','گیرنده',125)],height=3);self.overview_cheque_table.pack(fill='x',padx=3,pady=4)
        sec,g=make_section('فروش و مطالبات',[('sales_contract','کل قراردادها',DARK['green'],'جمع قراردادهای فروش.'),('sales_received','وصول خریداران',DARK['cyan'],'دریافت واقعی از خریداران.'),('sales_receivable','کل مطالبات',DARK['blue'],'مانده طلب از خریداران.'),('sales_30','مطالبات ۳۰ روز',DARK['orange'],'سررسید تا ۳۰ روز.'),('sales_overdue','مطالبات معوق',DARK['red'],'مانده گذشته از سررسید.')],5);sf=tk.Frame(sec,bg=DARK['bg']);sf.pack(fill='x');sf.grid_columnconfigure(0,weight=1);sf.grid_columnconfigure(1,weight=1);f1=ttk.LabelFrame(sf,text='وصول ۳۰ روز آینده');f1.grid(row=0,column=1,sticky='nsew',padx=2);self.overview_sales_upcoming=CompactTable(f1,[('buyer','خریدار',130),('unit','واحد',65),('due','سررسید',90),('amount','مانده',110),('days','روز',55)],height=3);self.overview_sales_upcoming.pack(fill='x');f2=ttk.LabelFrame(sf,text='مطالبات معوق');f2.grid(row=0,column=0,sticky='nsew',padx=2);self.overview_sales_overdue=CompactTable(f2,[('buyer','خریدار',130),('unit','واحد',65),('due','سررسید',90),('amount','مانده',110),('days','تأخیر',55)],height=3);self.overview_sales_overdue.pack(fill='x')
        sec,g=make_section('تسهیلات',[('loan_principal','اصل تسهیلات',DARK['blue'],'کل اصل وام‌ها.'),('loan_paid','اقساط پرداختی',DARK['cyan'],'جمع اقساط پرداخت‌شده.'),('loan_remaining','مانده تسهیلات',DARK['red'],'بدهی باقی‌مانده.'),('loan_30','اقساط ۳۰ روز',DARK['orange'],'اقساط سررسید ۳۰ روز آینده.')],4);self.overview_loan_table=CompactTable(sec,[('lender','بانک',110),('title','عنوان',150),('no','قسط',50),('due','تاریخ',90),('amount','مانده',110),('days','روز',70)],height=3);self.overview_loan_table.pack(fill='x',padx=3,pady=4)
        # 32 phases + overall progress, as requested.
        phase=tk.Frame(inner,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);phase.pack(fill='x',padx=4,pady=6);tk.Label(phase,text='پیشرفت ۳۲ فاز پروژه',bg=DARK['surface'],fg='#7FC9FF',font=('Segoe UI',9,'bold')).pack(anchor='e',padx=8,pady=(7,3));self.phase_strip=tk.Frame(phase,bg=DARK['surface']);self.phase_strip.pack(fill='x',padx=7,pady=4);self.phase_buttons={}
        for i in range(1,33):
            b=tk.Button(self.phase_strip,text=f'{i:02d}',bg='#172437',fg='#92A4BA',relief='flat',font=('Segoe UI',6,'bold'),width=3,pady=4,command=lambda n=i:self.open_phase_by_no(n));b.pack(side='left',fill='x',expand=True,padx=1);b.bind('<Double-1>',lambda e,n=i:self.edit_phase_progress(n));self.phase_buttons[i]=b
        self.overall_progress=ProjectProgressBar(phase,on_open=lambda:ProjectFinancialOverview(self,self.rich));self.overall_progress.pack(fill='x',padx=7,pady=(4,8))
        charts=tk.Frame(inner,bg=DARK['bg']);charts.pack(fill='x',padx=4,pady=5);charts.grid_columnconfigure(0,weight=1);charts.grid_columnconfigure(1,weight=1);self.phase_chart=MiniBarChart(charts,'برآورد، واقعی و پیش‌بینی فازها',180);self.phase_chart.grid(row=0,column=1,sticky='nsew',padx=3);self.liquidity_chart=MiniLineChart(charts,'نمای تجمعی هزینه پروژه',180);self.liquidity_chart.grid(row=0,column=0,sticky='nsew',padx=3)
        rec=ttk.LabelFrame(inner,text='تطبیق سریع بانک',padding=6);rec.pack(fill='x',padx=4,pady=(6,12));self.bank_var=tk.StringVar();self.bank_date=tk.StringVar();ttk.Label(rec,text='موجودی واقعی:').pack(side='right');be=ttk.Entry(rec,textvariable=self.bank_var,width=18,justify='center');be.pack(side='right',padx=3);bind_grouped_number(be,self.bank_var,allow_negative=True);ttk.Label(rec,text='تاریخ:').pack(side='right',padx=(8,0));DateField(rec,self.bank_date,width=11).pack(side='right',padx=3);ttk.Button(rec,text='ثبت',command=self.record_reconciliation,style='Primary.TButton').pack(side='right',padx=4);self.bank_info=tk.StringVar(value='آخرین تطبیق: -');self.bank_info_label=tk.Label(rec,textvariable=self.bank_info,bg=DARK['panel'],fg=DARK['text'],font=('Segoe UI',7,'bold'));self.bank_info_label.pack(side='left',padx=6)
    def _build_manager(self):
        before=set(self.notebook.tabs());super()._build_manager();new=[x for x in self.notebook.tabs() if x not in before];tab_id=new[-1] if new else self.notebook.tabs()[-1];self.notebook.tab(tab_id,text='حساب مدیر پروژه');tab=self.nametowidget(tab_id);self.manager_basis_var=tk.StringVar(value='مبنای محاسبه: -');tk.Label(tab,textvariable=self.manager_basis_var,bg=DARK['surface'],fg='#A8D8FF',font=('Segoe UI',8,'bold'),padx=8,pady=5).pack(fill='x',pady=(4,0),before=tab.winfo_children()[0] if tab.winfo_children() else None)
    def _build_financial(self):
        before=set(self.notebook.tabs());super()._build_financial();new=[x for x in self.notebook.tabs() if x not in before];self.transactions_tab=new[-1] if new else self.notebook.tabs()[-1];self.notebook.tab(self.transactions_tab,text='تراکنش‌ها')
        for t in self.fin_nb.tabs():
            if self.fin_nb.tab(t,'text')=='وام‌ها':self.fin_nb.tab(t,text='تسهیلات')
        doc=ttk.Frame(self.fin_nb,padding=6);self.fin_nb.add(doc,text='داکیومنت‌ها');self.document_table=SmartTable(doc,[('date','تاریخ',95),('type','نوع سند',105),('desc','شرح',260),('amount','مبلغ مرجع',125),('links','اتصال به',260),('id','Document ID',150)],title='اسناد مرتبط با پرداخت‌ها / فاکتورها');self.document_table.pack(fill='both',expand=True);self.document_table.set_delete_handler(lambda r:(self.rich.delete_document(r['document_id']),self.refresh_financial()))
    def _build_cheques(self):
        tab=ttk.Frame(self.notebook,padding=6);self.notebook.add(tab,text='چک‌ها');bar=ttk.Frame(tab);bar.pack(fill='x',pady=(0,4));self.ch_filter=tk.StringVar(value='همه');c=ttk.Combobox(bar,textvariable=self.ch_filter,state='readonly',values=['همه','ثبت‌نشده','ثبت‌شده','باز','پاس‌شده'],width=13);c.pack(side='right');c.bind('<<ComboboxSelected>>',lambda e:self.refresh_cheques());ttk.Button(bar,text='✏️ ویرایش چک',command=self.edit_cheque).pack(side='right',padx=3)
        self.cheque_table=SmartTable(tab,[('issue','تاریخ صدور',100),('due','سررسید',105),('amount','مبلغ',125),('issuer','صاحب حساب',120),('type','فیزیکی/دیجیتال',105),('reg','ثبت صیادی',90),('receiver','گیرنده',120),('bank','بانک',100),('serial','شماره/صیادی',115),('desc','بابت',200),('status','وضعیت',95),('id','Cheque ID',145)],title='چک‌ها');self.cheque_table.pack(fill='both',expand=True);self.cheque_table.set_edit_handler(self.edit_cheque_row);self.cheque_table.set_delete_handler(self._cancel_cheque_row)
    def _build_reports(self):
        tab=ttk.Frame(self.notebook,padding=5);self.notebook.add(tab,text='گزارش‌گیری');top=tk.Frame(tab,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);top.pack(fill='x',pady=(0,5));self.report_vars={k:tk.StringVar() for k in ['gross_area','saleable_area','unit_count','inflation','months','presale','end_price','misc','target']}
        fields=[('gross_area','متراژ غیرمفید'),('inflation','تورم ماهانه %'),('months','ماه تا اتمام'),('presale','پیش‌فروش/متر'),('end_price','فروش پایان/متر'),('misc','متفرقه خارج برآورد'),('target','سود هدف %')];self.report_entries={}
        fgrid=tk.Frame(top,bg=DARK['surface']);fgrid.pack(fill='x',padx=6,pady=5)
        for i,(k,l) in enumerate(fields):tk.Label(fgrid,text=l+':',bg=DARK['surface'],fg=DARK['muted'],font=('Segoe UI',7)).grid(row=i//4*2,column=(i%4)*2+1,sticky='e',padx=2);e=ttk.Entry(fgrid,textvariable=self.report_vars[k],width=15,justify='right');e.grid(row=i//4*2,column=(i%4)*2,sticky='ew',padx=2);self.report_entries[k]=e;bind_grouped_number(e,self.report_vars[k]) if k in ('presale','end_price','misc') else None
        self.unit_summary_var=tk.StringVar(value='واحدها: -');tk.Label(fgrid,textvariable=self.unit_summary_var,bg=DARK['surface'],fg='#A8D8FF',font=('Segoe UI',7,'bold')).grid(row=3,column=0,columnspan=6,sticky='w')
        act=tk.Frame(top,bg=DARK['surface']);act.pack(fill='x',padx=6,pady=(0,5));tk.Button(act,text='💾 ذخیره پارامترها',command=self.save_report_settings,bg=DARK['blue'],fg='white',relief='flat',padx=8,pady=4).pack(side='right');tk.Button(act,text='📥 بارگذاری فایل برآورد',command=self.import_budget,bg=DARK['glass'],fg='white',relief='flat',padx=8,pady=4).pack(side='right',padx=3);tk.Button(act,text='📤 خروجی انتخابی',command=self.export_report_choose,bg=DARK['glass'],fg='white',relief='flat',padx=8,pady=4).pack(side='right',padx=3);self.budget_version=tk.StringVar(value='نسخه برآورد: -');tk.Label(act,textvariable=self.budget_version,bg=DARK['surface'],fg=DARK['muted'],font=('Segoe UI',7)).pack(side='left')
        kgrid=tk.Frame(tab,bg=DARK['bg']);kgrid.pack(fill='x',pady=(0,5));self.report_cards={};defs=[('eac','برآورد نهایی پروژه',DARK['orange'],'Actual + باقی‌مانده برآوردشده تا پایان پروژه.'),('cmp','اختلاف با برآورد اولیه',DARK['blue'],'برآورد نهایی منهای برآورد اولیه؛ مثبت یعنی افزایش هزینه.'),('profit','سود/زیان پیش‌بینی',DARK['green'],'درآمد پیش‌بینی‌شده منهای هزینه نهایی پیش‌بینی‌شده.'),('targetprice','فروش لازم برای سود هدف',DARK['cyan'],'قیمت فروش لازم برای رسیدن به درصد سود هدف.'),('funding','کسری تأمین مالی',DARK['red'],'منابع موجود/پیش‌بینی‌شده در برابر هزینه‌های باقی‌مانده.'),('area','متراژ لازم پیش‌فروش',DARK['orange'],'متراژ موردنیاز پیش‌فروش برای پوشش کسری نقدینگی.'),('m2_build_gross','ساخت/متر غیرمفید',DARK['blue'],'هزینه ساخت تقسیم بر متراژ کل.'),('m2_build_saleable','ساخت/متر مفید',DARK['cyan'],'هزینه ساخت تقسیم بر متراژ مفید.'),('m2_total_gross','تمام‌شده/متر غیرمفید',DARK['orange'],'کل هزینه پروژه تقسیم بر متراژ کل.'),('m2_total_saleable','تمام‌شده/متر مفید',DARK['green'],'کل هزینه پروژه تقسیم بر متراژ مفید.')]
        for c in range(5):kgrid.grid_columnconfigure(c,weight=1)
        for i,(k,t,col,info) in enumerate(defs):card=GlassMetricCard(kgrid,t,col,'◈',info,on_open=lambda kk=k,tt=t,ii=info:self.open_report_kpi(kk,tt,ii));card.grid(row=i//5,column=i%5,sticky='nsew',padx=2,pady=2);self.report_cards[k]=card
        self.report_nb=ttk.Notebook(tab);self.report_nb.pack(fill='both',expand=True)
        price=ttk.Frame(self.report_nb,padding=5);phase=ttk.Frame(self.report_nb,padding=5);self.report_nb.add(price,text='قیمت‌ها');self.report_nb.add(phase,text='فازها')
        self.price_table=SmartTable(price,[('cat','گروه',105),('code','کد',90),('desc','شرح',245),('unit','واحد',80),('est','برآورد',125),('actual','واقعی مرجع',125),('fc','پیش‌بینی',125),('src','منبع',180)],title='قیمت مصالح، اجرت/اجرا و خدمات — دابل‌کلیک برای پیش‌فاکتور و نحوه محاسبه');self.price_table.pack(fill='both',expand=True);self.price_table.set_edit_handler(lambda r:PriceDetailDialog(self,self.rich,r,self.refresh_reports))
        self.phase_table=SmartTable(phase,[('no','شماره فاز',75),('phase','فاز',230),('est','برآورد',125),('actual','واقعی',125),('rem','مانده پایه',125),('fc','پیش‌بینی',125),('id','ID',90),('var','انحراف',120)],title='کنترل فازها — دابل‌کلیک برای ریز فاز و احجام');self.phase_table.pack(fill='both',expand=True);self.phase_table.set_edit_handler(lambda r:self.open_phase_by_no(r['phase_no']))
    def _build_health(self):
        tab=ttk.Frame(self.notebook,padding=10);self.notebook.add(tab,text='عملکرد سیستم')
        hb=ttk.Frame(tab);hb.pack(fill='x',pady=(0,5));ttk.Button(hb,text='بروزرسانی وضعیت',command=self.refresh_health).pack(side='right');ttk.Button(hb,text='🖼 تغییر لوگوی برنامه',command=self.choose_logo).pack(side='right',padx=4)
        self.health_text=tk.Text(tab,wrap='word',bg='#091523',fg=DARK['text'],insertbackground='white',relief='flat',font=('Consolas',9));self.health_text.pack(fill='both',expand=True)
    def refresh_overview(self):
        super().refresh_overview()
        for card in self.cards.values():
            try:card.var.set(fa(card.var.get()))
            except Exception:pass
        self.refresh_phase_strip()
        try:
            s=self._phase_summary_live();self.phase_chart.set_rows([(f"{r['phase_no']:02d}",r['estimate'],r['actual'],r['forecast']) for r in s]);cum=[];a=e=f=0
            for r in s:e+=r['estimate'];a+=r['actual'];f+=r['forecast'];cum.append((e,a,f))
            self.liquidity_chart.set_series([('برآورد',[x[0] for x in cum],'orange'),('واقعی',[x[1] for x in cum],'green'),('پیش‌بینی',[x[2] for x in cum],'blue')])
        except Exception:pass
    def refresh_phase_strip(self):
        prog=self.rich.get_phase_progress();summ={r['phase_no']:r for r in self._phase_summary_live()}
        for n,b in self.phase_buttons.items():
            p=prog.get(n,{});st=p.get('status','NOT_STARTED');pct=float(p.get('physical_progress') or 0);colors={'NOT_STARTED':('#172437','#91A4BC'),'ACTIVE':('#164E7A','white'),'PAUSED':('#7A4F12','white'),'COMPLETED':('#176044','white')};bg,fg=colors.get(st,colors['NOT_STARTED']);b.configure(bg=bg,fg=fg,text=f"{n:02d}\n{fa(f'{pct:.0f}%') if pct else ''}")
        self.overall_progress.set(self.rich.overall_physical_progress())
    def refresh_manager(self):
        super().refresh_manager()
        try:self.manager_basis_var.set(f"مبنای حق‌الزحمه مدیر پروژه: کل هزینه ساخت تحقق‌یافته تا امروز (نقد + تعهد/هزینه چکی) = {fmt_money(SERVICE.overview().construction_cost)}")
        except Exception:pass
    def refresh_financial(self):
        # Correct EXPENSE vs OUTFLOW label in the 'all transactions' view.
        tx=SERVICE.list_transactions();self.all_tx_table.set_rows(tx,lambda r:[r.get('shamsi_date') or '-', 'هزینه' if r.get('expense_id') else ('ورودی' if r['direction']=='IN' else 'خروجی'),money(r['amount']),r.get('category') or '-',r.get('payer_name') or 'تنخواه',r.get('receiver_name') or '-',r.get('description') or '-',f"📎 {r.get('receipt_count',0)}",d12.fa_status(r['status']),r['transaction_id']])
        ex=SERVICE.list_construction_expenses();self.exp_table.set_rows(ex,lambda r:[r.get('shamsi_date') or '-',money(r['final_amount']),money(r['paid_amount']),r.get('phase_name') or '⚠️ تعیین نشده',r.get('activity_name_display') or '⚠️ تعیین نشده',r.get('payer_name_display') or 'تنخواه',r.get('receiver_name_display') or '-',r.get('description') or '-',f"📎 {r.get('receipt_count',0)}",d12.fa_status(r['status']),r['expense_id']])
        ins=SERVICE.list_transactions(direction='IN');self.in_table.set_rows(ins,lambda r:[r.get('shamsi_date') or '-',money(r['amount']),r.get('category') or '-',r.get('payer_name') or '-',r.get('description') or '-',f"📎 {r.get('receipt_count',0)}",r['transaction_id']]);outs=SERVICE.list_transactions(direction='OUT',nonconstruction_only=True);self.out_table.set_rows(outs,lambda r:[r.get('shamsi_date') or '-',money(r['amount']),r.get('category') or '-',r.get('receiver_name') or '-',r.get('description') or '-',f"📎 {r.get('receipt_count',0)}",r['transaction_id']]);loans=SERVICE.loans.list_loans();self.loan_table.set_rows(loans,lambda r:[r.get('received_date_shamsi') or '-',r.get('lender_name') or '-',money(r['principal_amount']),money(r.get('net_received_amount')),money(int(r.get('total_interest') or 0)+int(r.get('bank_fees') or 0)),money(r.get('paid_total')),money(r.get('remaining_debt')),f"{r.get('paid_installments',0)}/{r.get('installment_count',0)}",f"{r.get('next_due_shamsi') or '-'} | {money(r.get('next_due_amount'))}",d12.fa_status(r['status']),r['loan_id']])
        if hasattr(self,'document_table'):
            docs=self.rich.list_documents();self.document_table.set_rows(docs,lambda r:[r.get('event_date_shamsi') or '-',r.get('document_type') or '-',r.get('description') or '-',fmt_money(r.get('amount')),r.get('links') or 'بدون اتصال',r['document_id']])
    def refresh_cheques(self):
        rows=SERVICE.list_cheques(open_only=False);f=getattr(self,'ch_filter',tk.StringVar(value='همه')).get()
        if f=='ثبت‌نشده':rows=[r for r in rows if str(r.get('registration_state') or 'UNKNOWN')=='UNREGISTERED']
        elif f=='ثبت‌شده':rows=[r for r in rows if str(r.get('registration_state') or 'UNKNOWN')=='REGISTERED']
        elif f=='باز':rows=[r for r in rows if r.get('status') in {'ISSUED','DUE'}]
        elif f=='پاس‌شده':rows=[r for r in rows if r.get('status')=='CASHED']
        for r in rows:r['_sum_amount']=int(r.get('amount') or 0)
        self.cheque_table.set_rows(rows,lambda r:[r.get('issue_date_shamsi') or '-',r.get('due_date_shamsi') or '-',fmt_money(r['amount']),r.get('issuer_name') or '-',CHEQUE_TYPE_FA.get(str(r.get('cheque_type') or 'PHYSICAL').upper(),'فیزیکی'),REG_FA.get(str(r.get('registration_state') or 'UNKNOWN').upper(),'نامشخص'),r.get('receiver_name') or '-',r.get('issuer_bank') or '-',r.get('cheque_serial') or '-',r.get('description') or r.get('expense_description') or '-',d12.fa_status(r['status']),r['cheque_id']])
    def _phase_summary_live(self):
        """What each phase has actually cost, as the project plan states it.

        The legacy budget service groups spend by the old activity taxonomy,
        and this used to take its figure instead - so the فازها tab and the
        plan sheet could report different actuals for the same phase. The plan
        is the authority: it counts what was posted to its own lines, from the
        transactions and from the contracts alike.

        The two disagree where a construction cost never reached a line - no
        دسته‌بندی, or wording that named nothing. Such a cost shows a dash in
        the ردیف پلان column of the هزینه ساخت table, which is where it is
        fixed; it is not quietly added to a phase here.
        """

        return [dict(r) for r in self.rich.list_phase_summary()]

    def refresh_reports(self):
        # Preserve Stage-15 forecast formula cards/settings, then use rich imported quantities for tables.
        st=SERVICE.budget.get_settings();us=d12.UNITS.summary()
        mapping={'gross_area':'gross_area','inflation':'monthly_inflation','months':'remaining_months','presale':'presale_price_per_m2','end_price':'end_sale_price_override','misc':'unbudgeted_misc','target':'target_profit_percent'}
        for vk,sk in mapping.items():
            val=st.get(sk);self.report_vars[vk].set('' if val is None else (group_int(val,blank_zero=(vk=='end_price')) if vk in ('presale','end_price','misc') else str(val or '')))
        self.report_vars['unit_count'].set(str(us['count']));self.report_vars['saleable_area'].set(str(us['area']));self.unit_summary_var.set(f"واحدها: {us['count']:,} | متراژ مفید: {us['area']:,.2f} مترمربع | فروخته‌شده: {us['sold']:,} واحد")
        v=SERVICE.budget.latest_version();self.budget_version.set(f"نسخه برآورد: {v.get('version_no')} — {v.get('title')}" if v else 'نسخه برآورد: -')
        try:
            f=SERVICE.budget.forecast();diff=f.forecast_total_cost-f.initial_budget;self.report_cards['eac'].var.set(fmt_money(f.forecast_total_cost));self.report_cards['cmp'].var.set(f"{fmt_money(diff)} ({fa(f'{(diff/f.initial_budget*100 if f.initial_budget else 0):+.1f}')}٪)");self.report_cards['profit'].var.set(f"{fmt_money(f.projected_profit)} | {fa(f'{f.projected_profit_percent:+.1f}')}٪");self.report_cards['targetprice'].var.set(fmt_money(f.suggested_remaining_sale_price_per_m2)+'/متر');self.report_cards['funding'].var.set(fmt_money(f.funding_gap));self.report_cards['area'].var.set(fa(f'{f.presale_area_needed_m2:,.1f}')+' مترمربع');self.report_cards['m2_build_gross'].var.set(fmt_money(f.construction_cost_per_gross_m2)+'/متر');self.report_cards['m2_build_saleable'].var.set(fmt_money(f.construction_cost_per_saleable_m2)+'/متر');self.report_cards['m2_total_gross'].var.set(fmt_money(f.total_cost_per_gross_m2)+'/متر');self.report_cards['m2_total_saleable'].var.set(fmt_money(f.total_cost_per_saleable_m2)+'/متر')
        except Exception:pass
        prices=self.rich.list_prices(visible_only=True);catfa={'MATERIAL':'مصالح','LABOR':'اجرت/اجرا','SERVICE':'خدمات','INSTALLATION_GROUP':'تأسیسات (تجمیعی)'};self.price_table.set_rows(prices,lambda r:[catfa.get(r['category'],r['category']),r.get('code') or '-',r['description'],r.get('unit') or '-',fmt_money(r['estimate_rate']),fmt_money(r['actual_rate']),fmt_money(r['forecast_rate']),r.get('source') or '-'])
        phases=self._phase_summary_live();self.phase_table.set_rows(phases,lambda r:[fa(f"{r['phase_no']:02d}"),r['phase'],fmt_money(r['estimate']),fmt_money(r['actual']),fmt_money(r['remaining_base']),fmt_money(r['forecast']),r['phase_id'],fmt_money(r['variance'])]);self.refresh_phase_strip() if hasattr(self,'phase_buttons') else None
    def import_budget(self):
        path=filedialog.askopenfilename(parent=self,filetypes=[('Excel','*.xlsx')]);
        if not path:return
        title=simpledialog.askstring('عنوان نسخه','عنوان این نسخه برآورد:',parent=self) or Path(path).stem
        try:
            legacy=SERVICE.budget.import_budget_xlsx(path,title);rich=self.rich.import_workbook(path,title,preserve_manual=True);shutil.copy2(path,BASE_DIR/'phase_budget_current.xlsx');self.refresh_reports();messagebox.showinfo('برآورد بارگذاری شد',f"اکسل به‌صورت همزمان در تب قیمت‌ها و فازها اعمال شد.\n\nفازها: {rich.phase_count}\nریز ردیف‌ها: {rich.phase_item_count}\nجمع برآورد: {fmt_money(rich.total_estimate)}",parent=self)
        except Exception as exc:messagebox.showerror('Import برآورد',str(exc),parent=self)
    def open_phase_by_no(self,no:int):
        row=next((r for r in self._phase_summary_live() if r['phase_no']==int(no)),None)
        if row:PhaseDetailDialog163(self,self.rich,int(no),row['phase'],self.refresh_all)
    def edit_phase_progress(self,no:int):
        row=next((r for r in self._phase_summary_live() if r['phase_no']==int(no)),{'phase':'فاز'});PhaseProgressDialog(self,self.rich,int(no),row['phase'],self.refresh_all)
    def open_report_kpi(self,key,title,info):
        try:f=SERVICE.budget.forecast();details=json.dumps(f.__dict__,ensure_ascii=False,indent=2)
        except Exception:details='اطلاعات محاسبه در دسترس نیست.'
        KPIDetailDialog(self,title,info,details)
    def edit_transaction_row(self,r):
        if r.get('pending_id'):
            p=DB.get_pending_item(r['pending_id']);row=dict(p or {});row['raw_text']=_raw_text_for_pending(r['pending_id']);row['receipt_image_path']='';UnifiedPendingEditor(self,row,self.rich,self.refresh_all);return
        super().edit_transaction_row(r)
    def edit_expense_row(self,r):
        if r.get('pending_id'):
            p=DB.get_pending_item(r['pending_id']);row=dict(p or {});row['raw_text']=_raw_text_for_pending(r['pending_id']);UnifiedPendingEditor(self,row,self.rich,self.refresh_all);return
        super().edit_expense_row(r)
    def edit_cheque_row(self,r):ChequeEditDialog163(self,r,self.refresh_all)
    def choose_logo(self):
        path=filedialog.askopenfilename(parent=self,filetypes=[('تصویر','*.png *.jpg *.jpeg *.webp'),('همه فایل‌ها','*.*')])
        if not path:return
        try:
            dst=BASE_DIR/'assets'/'barkav_brand_header.png';shutil.copy2(path,dst);messagebox.showinfo('لوگو','لوگو ذخیره شد. برای اعمال کامل در هدر، برنامه را یک بار ببند و باز کن.',parent=self)
        except Exception as exc:messagebox.showerror('لوگو',str(exc),parent=self)

    def manual_save(self):
        try:
            import sqlite3
            dst=BASE_DIR/'data'/'backups';dst.mkdir(parents=True,exist_ok=True);p=dst/f"manual_{datetime.now():%Y%m%d_%H%M%S}.sqlite3";src=sqlite3.connect(str(CONFIG.db_path));out=sqlite3.connect(str(p));src.backup(out);out.close();src.close();messagebox.showinfo('ذخیره',f'بکاپ ذخیره شد:\n{p}',parent=self)
        except Exception as exc:messagebox.showerror('ذخیره',str(exc),parent=self)
    def save_as(self):
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.sqlite3',filetypes=[('SQLite','*.sqlite3')]);
        if not path:return
        try:
            import sqlite3
            src=sqlite3.connect(str(CONFIG.db_path));out=sqlite3.connect(path);src.backup(out);out.close();src.close();messagebox.showinfo('Save As',f'نسخه مستقل ذخیره شد:\n{path}',parent=self)
        except Exception as exc:messagebox.showerror('Save As',str(exc),parent=self)
    def _autosave_loop(self):
        try:
            import sqlite3
            dst=BASE_DIR/'data'/'autosave';dst.mkdir(parents=True,exist_ok=True);p=dst/'latest.sqlite3';src=sqlite3.connect(str(CONFIG.db_path));out=sqlite3.connect(str(p));src.backup(out);out.close();src.close()
        except Exception:pass
        finally:self.after(300000,self._autosave_loop)
    def undo(self):messagebox.showinfo('Undo',self.rich.undo_last(),parent=self);self.refresh_all()
    def redo(self):messagebox.showinfo('Redo',self.rich.redo_last(),parent=self);self.refresh_all()
    def export_report_choose(self):ReportExportChooser(self)

class ChequeEditDialog163(tk.Toplevel):
    def __init__(self,parent,row,on_refresh):
        super().__init__(parent);self.row=row;self.on_refresh=on_refresh;self.title('مشخصات چک');self.configure(bg=DARK['bg']);self.transient(parent);self.grab_set();self.vars={}
        vals={'issue':row.get('issue_date_shamsi') or '','due':row.get('due_date_shamsi') or '','amount':group_int(row.get('amount') or 0),'issuer_name':row.get('issuer_name') or '','receiver_name':row.get('receiver_name') or '','issuer_bank':row.get('issuer_bank') or '','cheque_serial':row.get('cheque_serial') or '','description':row.get('description') or '','cheque_type':CHEQUE_TYPE_FA.get(str(row.get('cheque_type') or 'PHYSICAL').upper(),'فیزیکی'),'registration_state':REG_FA.get(str(row.get('registration_state') or 'UNKNOWN').upper(),'نامشخص')}
        body=tk.Frame(self,bg=DARK['panel']);body.pack(padx=12,pady=12)
        fields=[('issue','تاریخ صدور','date'),('due','تاریخ سررسید','date'),('amount','مبلغ','num'),('issuer_name','صاحب حساب','entry'),('receiver_name','گیرنده','entry'),('issuer_bank','بانک','entry'),('cheque_serial','شماره/صیادی','entry'),('cheque_type','نوع چک','type'),('registration_state','وضعیت ثبت','reg'),('description','بابت','entry')]
        for i,(k,l,kind) in enumerate(fields):v=tk.StringVar(value=str(vals[k]));self.vars[k]=v;tk.Label(body,text=l+':',bg=DARK['panel'],fg=DARK['muted']).grid(row=i,column=1,sticky='e',padx=5,pady=3)
        for i,(k,l,kind) in enumerate(fields):
            v=self.vars[k]
            if kind=='date':w=DateField(body,v,width=30)
            elif kind=='type':w=ttk.Combobox(body,textvariable=v,state='readonly',values=list(CHEQUE_TYPE_BY_FA),width=32)
            elif kind=='reg':w=ttk.Combobox(body,textvariable=v,state='readonly',values=list(REG_BY_FA),width=32)
            else:w=ttk.Entry(body,textvariable=v,width=34,justify='right');bind_grouped_number(w,v) if kind=='num' else None
            w.grid(row=i,column=0,padx=5,pady=3,sticky='ew')
        tk.Button(body,text='ذخیره',command=self.save,bg=DARK['blue'],fg='white',relief='flat',padx=14,pady=6).grid(row=len(fields)+1,column=0,columnspan=2,pady=9)
    def save(self):
        try:
            ish=normalize_shamsi(self.vars['issue'].get());due=normalize_shamsi(self.vars['due'].get());
            if not ish or not due:raise ValueError('تاریخ صدور/سررسید نامعتبر است.')
            DB.update_cheque_details(self.row['cheque_id'],amount=parse_int(self.vars['amount'].get()),issue_date=shamsi_to_gregorian(ish),issue_date_shamsi=ish,due_date=shamsi_to_gregorian(due),due_date_shamsi=due,issuer_name=self.vars['issuer_name'].get().strip(),cheque_type=CHEQUE_TYPE_BY_FA.get(self.vars['cheque_type'].get(),'PHYSICAL'),receiver_name=self.vars['receiver_name'].get().strip(),issuer_bank=self.vars['issuer_bank'].get().strip(),cheque_serial=self.vars['cheque_serial'].get().strip(),description=self.vars['description'].get().strip())
            with DB.tx() as con:con.execute('UPDATE cheques SET registration_state=?,updated_at=? WHERE cheque_id=?',(REG_BY_FA.get(self.vars['registration_state'].get(),'UNKNOWN'),datetime.now().isoformat(timespec='seconds'),self.row['cheque_id']))
            self.destroy();self.on_refresh()
        except Exception as exc:messagebox.showerror('چک',str(exc),parent=self)

class ReportExportChooser(tk.Toplevel):
    def __init__(self,parent:Stage163Dashboard):
        super().__init__(parent);self.parent=parent;self.title('انتخاب خروجی گزارش');self.configure(bg=DARK['bg']);self.transient(parent);self.grab_set();self.vars={k:tk.BooleanVar(value=True) for k in ('summary','prices','phases')}
        body=tk.Frame(self,bg=DARK['panel']);body.pack(padx=12,pady=12);tk.Label(body,text='بخش‌های موردنظر برای خروجی را انتخاب کن:',bg=DARK['panel'],fg=DARK['text'],font=('Segoe UI',9,'bold')).pack(anchor='e',pady=5)
        for k,l in [('summary','خلاصه شاخص‌های گزارش'),('prices','تب قیمت‌ها'),('phases','تب فازها')]:tk.Checkbutton(body,text=l,variable=self.vars[k],bg=DARK['panel'],fg=DARK['text'],selectcolor=DARK['surface'],activebackground=DARK['panel'],activeforeground='white').pack(anchor='e')
        b=tk.Frame(body,bg=DARK['panel']);b.pack(fill='x',pady=8);tk.Button(b,text='Excel',command=lambda:self.go('xlsx'),bg=DARK['green'],fg='white',relief='flat',padx=10,pady=5).pack(side='right',padx=2);tk.Button(b,text='PDF',command=lambda:self.go('pdf'),bg=DARK['blue'],fg='white',relief='flat',padx=10,pady=5).pack(side='right',padx=2);tk.Button(b,text='Print',command=lambda:self.go('print'),bg=DARK['glass'],fg='white',relief='flat',padx=10,pady=5).pack(side='right',padx=2)
    def _rows(self):
        headers=['بخش','عنوان','مقدار','جزئیات'];rows=[]
        if self.vars['summary'].get():
            for k,card in self.parent.report_cards.items():rows.append(['خلاصه',card.title,card.var.get(),''])
        if self.vars['prices'].get():
            for r in self.parent.rich.list_prices(visible_only=True):rows.append(['قیمت‌ها',r['description'],fmt_money(r['forecast_rate']),f"برآورد {fmt_money(r['estimate_rate'])} | واقعی {fmt_money(r['actual_rate'])} | {r.get('unit') or '-'}"])
        if self.vars['phases'].get():
            for r in self.parent.rich.list_phase_summary():rows.append(['فازها',f"{r['phase_no']:02d} — {r['phase']}",fmt_money(r['forecast']),f"برآورد {fmt_money(r['estimate'])} | واقعی {fmt_money(r['actual'])} | انحراف {fmt_money(r['variance'])}"])
        return headers,rows
    def go(self,kind):
        h,r=self._rows();
        if not r:return messagebox.showwarning('خروجی','حداقل یک بخش را انتخاب کن.',parent=self)
        if kind=='print':fd,path=tempfile.mkstemp(suffix='.pdf');os.close(fd);export_pdf(path,h,r,title='BARKAV — گزارش پروژه');print_file(path);self.destroy();return
        ext='.xlsx' if kind=='xlsx' else '.pdf';path=filedialog.asksaveasfilename(parent=self,defaultextension=ext,filetypes=[('Excel','*.xlsx')] if kind=='xlsx' else [('PDF','*.pdf')]);
        if not path:return
        export_xlsx(path,h,r,title='BARKAV — گزارش پروژه') if kind=='xlsx' else export_pdf(path,h,r,title='BARKAV — گزارش پروژه');messagebox.showinfo('خروجی',f'فایل ساخته شد:\n{path}',parent=self);self.destroy()

if __name__=='__main__':Stage163Dashboard().mainloop()
