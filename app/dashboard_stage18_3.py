from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
import os, sys, tempfile, threading, subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import dashboard_stage18_2 as v182
import dashboard_stage18_1 as v181
import dashboard_stage18 as v18
import dashboard_stage16_3 as v163
from v18_store import load_ui, save_ui, load_profile, save_profile
from unit_service import UnitService
from attachment_service import AttachmentService
from ui_stage18_3 import (
    fa, en, parse_int, parse_decimal, group_int_fa,
    bind_grouped_number_fa, bind_grouped_decimal_fa,
    RtlNotebookStrip, attach_grids_recursive, attach_tree_grid,
    install_smarttable_export_dropdown, themed_brand_image,
    fetch_tgju_usd_toman,
)

VERSION='18.3'
v182.VERSION=VERSION; v181.VERSION=VERSION; v18.VERSION=VERSION
BASE_DIR=v182.BASE_DIR; DB=v182.DB; APPROVAL=v182.APPROVAL; SERVICE=v181.SERVICE
DARK=v182.DARK

# 18.3 keeps shared 18.2 modules untouched; Persian numeric binders are applied only inside 18.3 forms.

_THEME_DARK_183={
    'bg':'#071523','surface':'#0B1B2C','panel':'#102238','panel2':'#162D46','glass':'#17334F',
    'line':'#35516C','text':'#F4F7FA','muted':'#9BAFC1','blue':'#45A5EB','green':'#46C48E',
    'orange':'#F0B44D','red':'#F06B78','cyan':'#24B7C6','violet':'#8F87E2','yellow':'#F6CD52',
}
_THEME_LIGHT_183={
    'bg':'#EEF1F4','surface':'#F7F8FA','panel':'#F4F6F8','panel2':'#E8EDF2','glass':'#EDF2F5',
    'line':'#C5CFD9','text':'#263746','muted':'#6F8192','blue':'#328ED1','green':'#32AE7A',
    'orange':'#D99B30','red':'#DD5E69','cyan':'#169FAF','violet':'#8275CB','yellow':'#D9B63A',
}

def _is_light():
    try: return str(load_ui().get('appearance') or 'dark').lower()=='light'
    except Exception: return False

def _palette(): return _THEME_LIGHT_183 if _is_light() else _THEME_DARK_183

def _walk(root):
    stack=[root]
    while stack:
        w=stack.pop(); yield w
        try: stack.extend(w.winfo_children())
        except Exception: pass

def _persianize_tree(tree):
    if not isinstance(tree,ttk.Treeview): return
    for iid in tree.get_children(''):
        vals=list(tree.item(iid,'values') or ())
        if vals: tree.item(iid,values=[fa(v) for v in vals])

def _persianize_region(root):
    for w in _walk(root):
        if isinstance(w,ttk.Treeview): _persianize_tree(w)
        try:
            var=getattr(w,'total',None)
            if isinstance(var,tk.StringVar): var.set(fa(var.get()))
        except Exception: pass

def _retarget_region(root):
    """Make all legacy Tahoma/Arial widgets match Dashboard/Data Entry Segoe UI."""
    fs=int(load_ui().get('font_size') or 11)
    for w in _walk(root):
        try:
            f=w.cget('font')
            if f:
                import tkinter.font as tkfont
                font=tkfont.Font(font=f); font.configure(family='Segoe UI'); w.configure(font=font)
        except Exception: pass
    # Table font is style-driven, not per-widget.
    st=ttk.Style(root)
    try:
        st.configure('Treeview',font=('Segoe UI',fs),rowheight=max(34,int(load_ui().get('row_height') or 38)))
        st.configure('Treeview.Heading',font=('Segoe UI',max(9,fs-1),'bold'))
    except Exception: pass

def _selected_row(table):
    try:
        rows=table.selected_rows()
        return rows[0] if rows else None
    except Exception: return None

def _install_output_dropdowns(root):
    for w in _walk(root):
        if all(hasattr(w,n) for n in ('export_excel','export_pdf','print_report')):
            try: install_smarttable_export_dropdown(w)
            except Exception: pass

class _PersianNumericFieldMixin:
    def _field(self,*args,**kwargs):
        old_n=getattr(v18,'bind_grouped_number',None);old_d=getattr(v18,'bind_grouped_decimal',None)
        v18.bind_grouped_number=bind_grouped_number_fa;v18.bind_grouped_decimal=bind_grouped_decimal_fa
        try:return super()._field(*args,**kwargs)
        finally:
            if old_n is not None:v18.bind_grouped_number=old_n
            if old_d is not None:v18.bind_grouped_decimal=old_d

class PendingTable183(v182.PendingTable182):
    """Brighter transaction coding while keeping review states visually distinct."""
    def set_rows(self, rows, renderer):
        super().set_rows(rows, renderer)
        # در انتظار بررسی همیشه زرد روشن است، صرف‌نظر از عنوان تراکنش - تفکیک
        # رنگی بر اساس عنوان اینجا کنار گذاشته شد چون با درخواست «زرد روشن
        # برای در انتظار» یکی نبود.
        colors={
            'هزینه ساخت':('#F5C842','#4A3800'),
            'ورودی':('#F5C842','#4A3800'),
            'خروجی':('#F5C842','#4A3800'),
            'یادداشت':('#F5C842','#4A3800'),
        }
        for title,(bg,fg) in colors.items():
            tag='tx183_'+title.replace(' ','_')
            try:self.tree.tag_configure(tag,background=bg,foreground=fg)
            except Exception:pass
        for iid in self.tree.get_children():
            r=self.iid_to_row.get(iid)
            if not r: continue
            status=str(r.get('status') or '')
            if status not in {'PENDING_REVIEW','NEEDS_REVIEW','EDIT_PENDING'}: continue
            p=r.get('payload') or {}; title=str(p.get('v18_title') or '')
            if title in colors:
                try:self.tree.item(iid,tags=(f"tx183_{title.replace(' ','_')}",))
                except Exception:pass

class UnifiedPendingEditor183(_PersianNumericFieldMixin, v182.UnifiedPendingEditor182):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        self.title('ویرایش و تأیید رکورد — BARKAV 18.3')
        self.after_idle(self._align_financial_group)
        self.after_idle(lambda:_retarget_region(self))
        self.after_idle(lambda:attach_grids_recursive(self,light=_is_light()))

    def _align_financial_group(self):
        """Invoice/final/discount are one right-anchored triplet (request #2)."""
        for key,col in [('invoice_amount',3),('final_amount',2),('discount_amount',1)]:
            try:
                host=v182._widget_host(self.widgets.get(key)); host.grid_configure(column=col)
            except Exception: pass
        # payment method remains present, but no longer pushes that triplet left.
        try:
            host=v182._widget_host(self.widgets.get('payment_method'))
            if host:
                info=host.grid_info(); row=max(0,int(info.get('row',0))-1)
                host.grid_configure(row=row,column=0)
        except Exception: pass

class TransactionWizard183(_PersianNumericFieldMixin, v182.TransactionWizard182):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        self.title('ثبت تراکنش — Wizard — BARKAV 18.3')
        self.after_idle(lambda:_retarget_region(self))

class DataEntryCenter183(v182.DataEntryCenter182):
    def _build(self):
        # Ensure inherited builder instantiates 18.3 table.
        old=v182.PendingTable182; v182.PendingTable182=PendingTable183
        try: super()._build()
        finally: v182.PendingTable182=old
        self._compact_bottom_buttons()
        self._center_reprocess_actions()
        self._install_output_combo()
        self.after_idle(lambda:attach_grids_recursive(self,light=_is_light()))

    def _install_output_combo(self):
        try:
            top=self.winfo_children()[0]
            self.output_var=tk.StringVar(value='انتخاب فرمت خروجی')
            cb=ttk.Combobox(top,textvariable=self.output_var,state='readonly',values=['انتخاب فرمت خروجی','پرینت','Excel','PDF'],width=18,justify='right')
            cb.pack(side='right',padx=4,pady=5);cb.bind('<<ComboboxSelected>>',self._output_selected,add='+');self.output_combo=cb
        except Exception:pass
    def _output_selected(self,_=None):
        mode=getattr(self,'output_var',tk.StringVar(value='')).get();
        try:self.output_var.set('انتخاب فرمت خروجی')
        except Exception:pass
        if mode=='انتخاب فرمت خروجی':return
        headers=[x[1] for x in getattr(self.table,'COLUMNS',[])];rows=[list(self.table.tree.item(i,'values')) for i in self.table.tree.get_children()]
        if not rows:return messagebox.showinfo('خروجی','داده‌ای برای خروجی وجود ندارد.',parent=self)
        try:
            if mode=='پرینت':
                fd,path=tempfile.mkstemp(suffix='.pdf');os.close(fd);v163.export_pdf(path,headers,rows,title='BARKAV — ثبت دیتا');v163.print_file(path);return
            ext='.xlsx' if mode=='Excel' else '.pdf';path=filedialog.asksaveasfilename(parent=self,defaultextension=ext,filetypes=[(mode,f'*{ext}')],initialfile=f'BARKAV_DataEntry{ext}')
            if not path:return
            (v163.export_xlsx if mode=='Excel' else v163.export_pdf)(path,headers,rows,title='BARKAV — ثبت دیتا')
            messagebox.showinfo('خروجی',f'فایل ساخته شد:\n{path}',parent=self)
        except Exception as exc:messagebox.showerror('خروجی',str(exc),parent=self)

    def _compact_bottom_buttons(self):
        for w in _walk(self):
            if isinstance(w,tk.Button) and str(w.cget('text')) in {'حذف','کپی','پیست','اضافه کردن'}:
                try:w.configure(pady=3)
                except Exception:pass

    def _center_reprocess_actions(self):
        buttons=[]
        for w in _walk(self):
            if isinstance(w,tk.Button) and str(w.cget('text')) in {'بازخوانی پیام‌ها','پردازش مجدد'}:
                buttons.append(w)
        if len(buttons)!=2:return
        parent=buttons[0].master
        try:
            center=tk.Frame(parent,bg=DARK['surface']); center.place(relx=.52,rely=.5,anchor='center')
            for b in buttons:
                b.pack_forget(); b.pack(in_=center,side='right',padx=4,pady=4)
            self._center_data_actions=center
        except Exception:pass

    def copy_rows(self, rows):
        """Copy from DB source-of-truth so payload values cannot become empty (#3)."""
        if not rows: return messagebox.showwarning('کپی','یک سطر را انتخاب کن.',parent=self)
        copied=[]
        for r in rows:
            pid=str(r.get('pending_id') or '')
            fresh=DB.get_pending_item(pid) if pid else None
            src=dict(fresh or r)
            src['payload']=deepcopy(dict(src.get('payload') or {}))
            src['raw_text']=src.get('raw_text') or r.get('raw_text') or ''
            copied.append(src)
        self._copied_rows=copied
        self.action.set(f'{fa(len(copied))} سطر با همه مقادیر کپی شد.')

    def open_editor(self,row=None):
        row=row or getattr(self,'current',None)
        if not row:return
        pid=str(row.get('pending_id') or ''); before=self._pending_snapshot(pid)
        def done():self._record_pending_edit(before);self.refresh()
        UnifiedPendingEditor183(self,row,self.rich,done)

    def open_wizard(self,row=None):
        row=row or getattr(self,'current',None)
        if not row:return messagebox.showwarning('ثبت دیتا','یک سطر را انتخاب کن.',parent=self)
        pid=str(row.get('pending_id') or ''); before=self._pending_snapshot(pid)
        def done():self._record_pending_edit(before);self.refresh()
        def full():
            fresh=DB.get_pending_item(pid) or row; fresh=dict(fresh); fresh['raw_text']=v18._raw_text(pid,row); self.open_editor(fresh)
        TransactionWizard183(self,row,self.rich,done,full)

class SettingsTab183(tk.Frame):
    def __init__(self,parent,on_apply):
        super().__init__(parent,bg=DARK['bg']); self.on_apply=on_apply; self.data=load_ui(); self.vars={}; self._build()
    def _build(self):
        card=v18.GlassSection(self,'تنظیمات ظاهر و کاربری'); card.pack(fill='x',padx=12,pady=12); b=card.body; b.grid_columnconfigure((0,1),weight=1)
        defs=[('font_family','نوع فونت',('Segoe UI',)),('font_size','اندازه فونت',tuple(str(x) for x in range(9,19))),('appearance','حالت نمایش',('dark','light')),('currency_unit','واحد پول',('تومان','ریال','دلار'))]
        for i,(k,l,vals) in enumerate(defs):
            box=tk.Frame(b,bg=DARK['panel']);box.grid(row=i//2,column=1-(i%2),sticky='ew',padx=7,pady=7)
            tk.Label(box,text=l,bg=DARK['panel'],fg=DARK['text'],font=('Segoe UI',10,'bold')).pack(anchor='e')
            v=tk.StringVar(value=str(self.data.get(k,'تومان' if k=='currency_unit' else '')));self.vars[k]=v
            ttk.Combobox(box,textvariable=v,state='readonly',values=vals,justify='right').pack(fill='x',pady=4)
        for c,(k,l) in enumerate([('usd_rate_current','قیمت روز دلار آمریکا (تومان)'),('usd_rate_baseline','قیمت دلار زمان برآورد اولیه (تومان)')]):
            box=tk.Frame(b,bg=DARK['panel']);box.grid(row=2,column=1-c,sticky='ew',padx=7,pady=7)
            tk.Label(box,text=l,bg=DARK['panel'],fg=DARK['text']).pack(anchor='e')
            v=tk.StringVar(value=group_int_fa(self.data.get(k,0),blank_zero=True));self.vars[k]=v;e=ttk.Entry(box,textvariable=v,justify='right');e.pack(fill='x',pady=4);bind_grouped_number_fa(e,v)
        tk.Button(b,text='ذخیره تنظیمات',command=self.save,bg=DARK['green'],fg='#102018',relief='flat',padx=18,pady=8,font=('Segoe UI',10,'bold')).grid(row=3,column=0,columnspan=2,sticky='e',padx=7,pady=10)
        tk.Label(b,text='تغییرات بلافاصله اعمال می‌شوند؛ در صورت نیاز، رابط کاربری خودکار بازآفرینی می‌شود.',bg=DARK['panel'],fg=DARK['muted'],font=('Segoe UI',9)).grid(row=4,column=0,columnspan=2,sticky='e',padx=7,pady=4)
    def save(self):
        old=load_ui(); d=dict(old); d.update({k:v.get() for k,v in self.vars.items()}); d['font_family']='Segoe UI'; d['font_size']=int(en(d.get('font_size') or 11));d['usd_rate_current']=parse_int(d.get('usd_rate_current'));d['usd_rate_baseline']=parse_int(d.get('usd_rate_baseline'))
        if d.get('currency_unit')=='دلار' and d['usd_rate_current']<=0:return messagebox.showwarning('واحد دلار','قیمت روز دلار آمریکا را وارد کن.',parent=self)
        save_ui(d); self.on_apply and self.on_apply(old,d)

class ProjectSettingsDialog183(v181.ProjectSettingsDialog181):
    """RTL, filterable/scrollable team, TGJU rate and per-tab unified export."""
    ROLE_SPECS={'executor':['مجری'],'supervisor':['معماری','سازه','مکانیک/تأسیسات','برق','گاز','آبفا','نقشه‌برداری'],'designer':['معماری','سازه','مکانیک/تأسیسات','برق']}
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw); self.title('مشخصات پروژه — BARKAV 18.3'); self.minsize(1050,700)
        self.after_idle(lambda:attach_grids_recursive(self,light=_is_light()))
        self.after_idle(lambda:_retarget_region(self))
    def _build(self):
        p=_palette(); self.vars={}; self.team_vars={}; self._team_hosts={}; self._team_filters={}
        toolbar=tk.Frame(self,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);toolbar.pack(fill='x',padx=8,pady=(8,0))
        tk.Label(toolbar,text='خروجی تب فعال',bg=DARK['surface'],fg=DARK['muted'],font=('Segoe UI',10,'bold')).pack(side='right',padx=8)
        self.output_var=tk.StringVar(value='انتخاب فرمت خروجی');out=ttk.Combobox(toolbar,textvariable=self.output_var,state='readonly',values=['انتخاب فرمت خروجی','پرینت','Excel','PDF'],width=21,justify='right');out.pack(side='right',padx=5,pady=6);out.bind('<<ComboboxSelected>>',self._export_active,add='+')
        self.nb=ttk.Notebook(self);self.nb.pack(fill='both',expand=True,padx=8,pady=8)
        basic=ttk.Frame(self.nb,style='Panel.TFrame');floors=ttk.Frame(self.nb,style='Panel.TFrame');team=ttk.Frame(self.nb,style='Panel.TFrame');self.nb.add(basic,text='مشخصات پایه');self.nb.add(floors,text='طبقات و واحدها');self.nb.add(team,text='عوامل پروژه')
        self._project_tabs={'مشخصات پایه':basic,'طبقات و واحدها':floors,'عوامل پروژه':team}
        self._rtl=RtlNotebookStrip(self.nb,bg=p['surface'],line=p['line'],text=p['text'],muted=p['muted'],active_bg=p['panel2'],active_fg=p['cyan'])
        project=SERVICE.project.get_project(); st=SERVICE.budget.get_settings(); ui=load_ui()
        defs=[('name','نام پروژه',project.get('name') or ''),('address','آدرس',project.get('address') or ''),('postal_code','کدپستی',project.get('postal_code') or ''),('registration_plate','پلاک ثبتی',project.get('registration_plate') or ''),('municipal_file_no','شماره پرونده شهرداری',project.get('municipal_file_no') or ''),('gross_area','متراژ کل/غیرمفید (M2)',st.get('gross_area') or 0),('saleable_area','متراژ مفید/فروشی (M2)',st.get('saleable_area') or 0),('unit_count','تعداد کل واحدها',st.get('unit_count') or 0),('floor_count','تعداد طبقات',len(self.profile.get('floors') or [])),('usd_rate_current','قیمت روز دلار (تومان)',ui.get('usd_rate_current') or 0)]
        card=v18.GlassSection(basic,'مشخصات پروژه');card.pack(fill='x',padx=8,pady=8);b=card.body;b.grid_columnconfigure((0,1,2),weight=1)
        for i,(k,l,val) in enumerate(defs):
            box=tk.Frame(b,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);box.grid(row=i//3,column=2-(i%3),sticky='ew',padx=5,pady=5);tk.Label(box,text=l,bg=DARK['panel'],fg=DARK['text'],font=('Segoe UI',self.font_size,'bold')).pack(anchor='e',padx=5,pady=(5,1));v=tk.StringVar(value=group_int_fa(val,blank_zero=True) if k in {'gross_area','saleable_area','unit_count','floor_count','usd_rate_current'} else str(val));self.vars[k]=v;e=ttk.Entry(box,textvariable=v,justify='right');e.pack(fill='x',padx=5,pady=(1,5));
            if k in {'gross_area','saleable_area','unit_count','floor_count','usd_rate_current'}:bind_grouped_number_fa(e,v)
        ratebar=tk.Frame(basic,bg=DARK['panel']);ratebar.pack(fill='x',padx=8,pady=(0,6));self.usd_status=tk.StringVar(value='قیمت دلار قابل ویرایش است.');tk.Label(ratebar,textvariable=self.usd_status,bg=DARK['panel'],fg=DARK['muted']).pack(side='right',padx=5);tk.Button(ratebar,text='بروزرسانی دلار از TGJU',command=self.refresh_usd,bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=12,pady=6).pack(side='right',padx=5)
        tk.Button(basic,text='ذخیره مشخصات پایه',command=self.save_basic_183,bg=DARK['green'],fg='#102018',relief='flat',font=('Segoe UI',self.font_size,'bold'),padx=18,pady=7).pack(anchor='e',padx=8,pady=6)
        # floors
        fc=v18.GlassSection(floors,'طبقات، تعداد واحد و متراژ واحدها');fc.pack(fill='both',expand=True,padx=8,pady=8);fb=fc.body
        self.floor_tree=ttk.Treeview(fb,columns=('floor','count','areas'),show='headings',height=13);self.floor_tree.heading('floor',text='طبقه');self.floor_tree.heading('count',text='تعداد واحد');self.floor_tree.heading('areas',text='متراژ واحدها (M2، با , جدا شود)');self.floor_tree.column('floor',width=140,anchor='center');self.floor_tree.column('count',width=120,anchor='center');self.floor_tree.column('areas',width=500,anchor='e');self.floor_tree.pack(fill='both',expand=True)
        for i,r in enumerate(self.profile.get('floors') or []):self.floor_tree.insert('', 'end',iid=str(i),values=(fa(r.get('floor','')),fa(r.get('unit_count',0)),fa(', '.join(str(x) for x in r.get('areas',[])))))
        bar=tk.Frame(fb,bg=DARK['panel']);bar.pack(fill='x',pady=6)
        for text,cmd,color in [('افزودن طبقه',self.add_floor,DARK['glass']),('ویرایش',self.edit_floor,DARK['glass']),('حذف',self.del_floor,DARK['red'])]:tk.Button(bar,text=text,command=cmd,bg=color,fg=DARK['text'],relief='flat',padx=12,pady=6).pack(side='right',padx=3)
        tk.Button(bar,text='ذخیره و همگام‌سازی واحدها',command=self.save_floors_181,bg=DARK['green'],fg='#102018',relief='flat',padx=14,pady=6).pack(side='left')
        # team scroll body
        shell=tk.Frame(team,bg=DARK['panel']);shell.pack(fill='both',expand=True,padx=8,pady=8);canvas=tk.Canvas(shell,bg=DARK['panel'],highlightthickness=0);ys=ttk.Scrollbar(shell,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=ys.set);canvas.pack(side='left',fill='both',expand=True);ys.pack(side='right',fill='y');body=tk.Frame(canvas,bg=DARK['panel']);wid=canvas.create_window((0,0),window=body,anchor='nw');body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')),add='+');canvas.bind('<Configure>',lambda e:canvas.itemconfigure(wid,width=e.width),add='+');canvas.bind('<MouseWheel>',lambda e:(canvas.yview_scroll(int(-e.delta/120),'units'),'break')[1],add='+')
        old=self.profile.get('team',{})
        for role in ('executor','supervisor','designer'):
            self.team_vars[role]={}
            for disc in self.ROLE_SPECS[role]:
                d=(old.get(role,{}).get(disc,{}) if isinstance(old.get(role,{}),dict) else {}) or {};self.team_vars[role][disc]={f:tk.StringVar(value=str(d.get(f,'') or '')) for f in ('name','phone','license_no','company')}
        for role,title in [('executor','مجری'),('supervisor','ناظر'),('designer','طراح')]:
            sec=v18.GlassSection(body,title);sec.pack(fill='x',padx=4,pady=5); head=tk.Frame(sec.body,bg=DARK['panel']);head.pack(fill='x')
            if role!='executor':
                fv=tk.StringVar(value='همه');self._team_filters[role]=fv;cb=ttk.Combobox(head,textvariable=fv,state='readonly',values=['همه']+self.ROLE_SPECS[role],width=22,justify='right');cb.pack(side='right',padx=4,pady=4);cb.bind('<<ComboboxSelected>>',lambda e,r=role:self._render_team_role(r),add='+')
            host=tk.Frame(sec.body,bg=DARK['panel']);host.pack(fill='x');self._team_hosts[role]=host;self._render_team_role(role)
        tk.Button(body,text='ذخیره عوامل پروژه',command=self.save_team_181,bg=DARK['green'],fg='#102018',relief='flat',font=('Segoe UI',self.font_size,'bold'),padx=18,pady=8).pack(anchor='e',padx=8,pady=8)
        self.after(250,self.refresh_usd)

    def _render_team_role(self,role):
        host=self._team_hosts.get(role)
        if not host:return
        for w in host.winfo_children():w.destroy()
        wanted=self._team_filters.get(role).get() if role in self._team_filters else self.ROLE_SPECS[role][0]
        discs=self.ROLE_SPECS[role] if wanted=='همه' else [wanted]
        for disc in discs:
            sub=tk.LabelFrame(host,text=disc,bg=DARK['panel'],fg=DARK['muted']);sub.pack(fill='x',padx=4,pady=4)
            for f,l in [('name','نام'),('phone','شماره تماس'),('license_no','شماره پروانه/عضویت'),('company','شرکت/دفتر')]:
                row=tk.Frame(sub,bg=DARK['panel'],highlightbackground=DARK['line'],highlightthickness=1);row.pack(fill='x',padx=4,pady=2);tk.Label(row,text=l,bg=DARK['panel'],fg=DARK['text'],width=18,anchor='e').pack(side='right',padx=4);ttk.Entry(row,textvariable=self.team_vars[role][disc][f],justify='right').pack(side='right',fill='x',expand=True,padx=4,pady=3)
    def refresh_usd(self):
        self.usd_status.set('در حال دریافت قیمت روز دلار...')
        def job():
            try:rate,ts=fetch_tgju_usd_toman();err=''
            except Exception as exc:rate=0;ts='';err=str(exc)
            def done():
                if rate>0:self.vars['usd_rate_current'].set(group_int_fa(rate));self.usd_status.set(f'آخرین بروزرسانی: {fa(ts.replace("T"," "))}')
                else:self.usd_status.set('بروزرسانی آنلاین انجام نشد؛ مقدار ذخیره/دستی حفظ شد.')
            try:self.after(0,done)
            except Exception:pass
        threading.Thread(target=job,daemon=True).start()
    def save_basic_183(self):
        self.save_basic_181();ui=load_ui();ui['usd_rate_current']=parse_int(self.vars['usd_rate_current'].get());save_ui(ui)
    def _active_export_data(self):
        label=self.nb.tab(self.nb.select(),'text')
        if label=='مشخصات پایه':
            headers=['عنوان','مقدار'];rows=[]
            labels={'name':'نام پروژه','address':'آدرس','postal_code':'کدپستی','registration_plate':'پلاک ثبتی','municipal_file_no':'شماره پرونده شهرداری','gross_area':'متراژ کل M2','saleable_area':'متراژ مفید M2','unit_count':'تعداد واحد','floor_count':'تعداد طبقات','usd_rate_current':'قیمت روز دلار (تومان)'}
            for k,l in labels.items():rows.append([l,self.vars[k].get()])
        elif label=='طبقات و واحدها':
            headers=['طبقه','تعداد واحد','متراژ واحدها'];rows=[list(self.floor_tree.item(i,'values')) for i in self.floor_tree.get_children()]
        else:
            headers=['نقش','رشته','نام','شماره تماس','شماره پروانه/عضویت','شرکت/دفتر'];rows=[]
            for role,rolefa in [('executor','مجری'),('supervisor','ناظر'),('designer','طراح')]:
                for disc,vals in self.team_vars[role].items():rows.append([rolefa,disc,vals['name'].get(),vals['phone'].get(),vals['license_no'].get(),vals['company'].get()])
        return label,headers,rows
    def _export_active(self,_=None):
        mode=self.output_var.get();self.output_var.set('انتخاب فرمت خروجی')
        if mode=='انتخاب فرمت خروجی':return
        title,headers,rows=self._active_export_data()
        try:
            if mode=='پرینت':
                fd,path=tempfile.mkstemp(suffix='.pdf');os.close(fd);v163.export_pdf(path,headers,rows,title=f'BARKAV — {title}');v163.print_file(path);return
            ext='.xlsx' if mode=='Excel' else '.pdf';path=filedialog.asksaveasfilename(parent=self,defaultextension=ext,filetypes=[(mode,f'*{ext}')],initialfile=f'BARKAV_{title}{ext}')
            if not path:return
            (v163.export_xlsx if mode=='Excel' else v163.export_pdf)(path,headers,rows,title=f'BARKAV — {title}')
            messagebox.showinfo('خروجی',f'فایل ساخته شد:\n{path}',parent=self)
        except Exception as exc:messagebox.showerror('خروجی',str(exc),parent=self)

class Stage183Dashboard(v182.Stage182Dashboard):
    _VISIBLE_NAV=('داشبورد','ثبت دیتا','تراکنش‌ها','فروش و مطالبات','گزارش‌گیری','حساب مدیر')
    def __init__(self):
        self._restart_requested=False; self._rtl_strips=[]; self._brand_photo=None
        super().__init__();self.title('BARKAV — Engineering & Construction — Version 18.3')
        self.after_idle(self._finalize_183)
    def _style(self):
        # Start from final 18.2 business-compatible style, then materially retarget visuals.
        super()._style();DARK.update(_palette());p=_palette();st=ttk.Style(self);fs=int(load_ui().get('font_size') or 11);rh=max(35,int(load_ui().get('row_height') or 38))
        try:st.theme_use('clam')
        except Exception:pass
        st.configure('.',font=('Segoe UI',fs),background=p['bg'],foreground=p['text'])
        st.configure('TFrame',background=p['bg']);st.configure('Panel.TFrame',background=p['panel']);st.configure('TLabel',background=p['bg'],foreground=p['text'])
        st.configure('TButton',font=('Segoe UI',max(9,fs-1),'bold'),padding=(11,7),background=p['glass'],foreground=p['text'],bordercolor=p['line'],relief='flat')
        st.map('TButton',background=[('active',p['panel2'])])
        st.configure('TEntry',fieldbackground=p['surface'],foreground=p['text'],insertcolor=p['text'],bordercolor=p['line'],padding=6)
        st.configure('TCombobox',fieldbackground=p['surface'],background=p['surface'],foreground=p['text'],arrowcolor=p['text'],bordercolor=p['line'],padding=5)
        st.map('TCombobox',fieldbackground=[('readonly',p['surface'])],foreground=[('readonly',p['text'])])
        st.configure('Treeview',rowheight=rh,background=p['surface'],fieldbackground=p['surface'],foreground=p['text'],bordercolor=p['line'],font=('Segoe UI',fs),relief='flat')
        st.configure('Treeview.Heading',background=p['panel2'],foreground=p['text'],font=('Segoe UI',max(9,fs-1),'bold'),padding=(7,9),relief='flat',bordercolor=p['line'])
        st.map('Treeview',background=[('selected',p['blue'])],foreground=[('selected','#FFFFFF')])
        st.configure('TNotebook',background=p['bg'],borderwidth=0);st.configure('TNotebook.Tab',background=p['surface'],foreground=p['muted'],padding=(18,9),font=('Segoe UI',max(9,fs-1),'bold'))
        st.map('TNotebook.Tab',background=[('selected',p['panel2']),('active',p['glass'])],foreground=[('selected',p['cyan']),('active',p['text'])])
        st.configure('Hidden.TNotebook',background=p['bg'],borderwidth=0);
        try:st.layout('Hidden.TNotebook.Tab',[])
        except Exception:pass
    def _build(self):
        # Same application sections as 18.2 FINAL; header/navigation are visually rebuilt.
        self.configure(bg=DARK['bg']);p=_palette();fs=int(load_ui().get('font_size') or 11)
        top=tk.Frame(self,bg=p['surface'],height=76,highlightbackground=p['line'],highlightthickness=1);top.pack(fill='x');top.pack_propagate(False)
        # requested BARKAV Persian brand at top-left, theme-blended.
        brand_path=BASE_DIR/'assets'/'barkav_brand_header.png'
        try:
            from PIL import ImageTk
            im=themed_brand_image(brand_path,fg=p['text'],bg=p['surface'],size=(260,64));self._brand_photo=ImageTk.PhotoImage(im,master=self);tk.Label(top,image=self._brand_photo,bg=p['surface'],bd=0).pack(side='left',padx=(14,6),pady=5)
        except Exception:
            tk.Label(top,text='BARKAV\nEngineering & Construction',bg=p['surface'],fg=p['text'],font=('Segoe UI',12,'bold'),justify='left').pack(side='left',padx=14)
        tools=tk.Frame(top,bg=p['surface']);tools.pack(side='right',padx=10,pady=10)
        commands=[('ذخیره',self.manual_save,'بکاپ دستی'),('Undo',self.undo,'بازگشت آخرین عملیات'),('Redo',self.redo,'اجرای دوباره'),('بروزرسانی',self.refresh_all,'بروزرسانی همه اطلاعات'),('تنظیمات',lambda:self._select_tab_text('تنظیمات'),'تنظیمات'),('بسته توسعه',self.export_development_package,'خروجی امن توسعه'),('سیستم',lambda:self._select_tab_text('سیستم'),'وضعیت سیستم')]
        self.command_buttons=[]
        for text,cmd,tip in commands:
            b=tk.Button(tools,text=text,command=cmd,bg=p['glass'],fg=p['text'],activebackground=p['panel2'],activeforeground=p['text'],relief='flat',bd=0,highlightbackground=p['line'],highlightthickness=1,font=('Segoe UI',max(9,fs-1),'bold'),padx=12,pady=8,cursor='hand2');b.pack(side='right',padx=3);v18.add_tooltip(b,tip);self.command_buttons.append(b)
        self.datetime_top=tk.StringVar(value='');tk.Label(tools,textvariable=self.datetime_top,bg=p['surface'],fg=p['muted'],font=('Segoe UI',max(9,fs-1),'bold')).pack(side='right',padx=(12,3))
        self.project_name_top=tk.StringVar(value='پروژه')
        self.navbar=tk.Frame(self,bg=p['surface'],height=62,highlightbackground=p['line'],highlightthickness=1);self.navbar.pack(fill='x',padx=10,pady=(7,0));self.navbar.pack_propagate(False)
        self.notebook=ttk.Notebook(self,style='Hidden.TNotebook');self.notebook.pack(fill='both',expand=True,padx=10,pady=(6,9))
        self._build_overview();self._build_manager();self._build_financial();self._build_cheques();self._build_sales();self._build_reconciliation();self._build_reports();self._build_market();self._build_system();self._build_settings();self._rebuild_navbar()
        self.notebook.bind('<<NotebookTabChanged>>',lambda e:(self._sync_nav(),v18._maximize(self)),add='+');self._attach_common_tooltips(self);self._tick_clock()
    def _build_approval_center(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.approval_tab=tab;self.notebook.insert(1,tab,text='ثبت دیتا');self.approval_center=DataEntryCenter183(tab,self.rich,on_posted=self.refresh_all);self.approval_center.pack(fill='both',expand=True)
        if self._bot_process:self.approval_center.set_bot_process(self._bot_process,self._bot_log)
        self.after_idle(self._rebuild_navbar)
    def _rebuild_navbar(self):
        if not getattr(self,'navbar',None):return
        for w in self.navbar.winfo_children():w.destroy()
        self.nav_buttons={};p=_palette();fs=int(load_ui().get('font_size') or 11);by={self.notebook.tab(t,'text'):t for t in self.notebook.tabs()}
        if 'حساب مدیر' not in by and 'حساب مدیر پروژه' in by:self.notebook.tab(by['حساب مدیر پروژه'],text='حساب مدیر');by['حساب مدیر']=by['حساب مدیر پروژه']
        icon_map={'داشبورد':'dashboard','ثبت دیتا':'data','تراکنش‌ها':'transactions','فروش و مطالبات':'sales','گزارش‌گیری':'reports','حساب مدیر':'manager'}
        for label in self._VISIBLE_NAV:
            tid=by.get(label)
            if not tid:continue
            img=self._load_nav_icon(icon_map[label]);b=tk.Button(self.navbar,text=label,image=img,compound='right' if img else 'none',command=lambda t=tid:self.notebook.select(t),bg=p['surface'],fg=p['text'],activebackground=p['panel2'],activeforeground=p['cyan'],relief='flat',bd=0,font=('Segoe UI',fs,'bold'),padx=18,pady=8,cursor='hand2',highlightbackground=p['line'],highlightthickness=1);b.pack(side='right',fill='y',padx=2,pady=5);self.nav_buttons[tid]=b
        self._sync_nav()
    def _sync_nav(self):
        try:sel=str(self.notebook.select())
        except Exception:return
        p=_palette()
        for tid,b in self.nav_buttons.items():
            active=str(tid)==sel;b.configure(bg=p['panel2'] if active else p['surface'],fg=p['cyan'] if active else p['text'],relief='raised' if active else 'flat',bd=1 if active else 0)
    def _build_financial(self):
        super()._build_financial(); self.after_idle(lambda:self._install_rtl(self.fin_nb))
    def _build_sales(self):
        # Same sales records/actions as 18.2, organized in RTL subtabs plus requested documents.
        root=ttk.Frame(self.notebook,style='Panel.TFrame',padding=6);self.notebook.add(root,text='فروش و مطالبات');self.sales_root=root
        self.sales_nb=ttk.Notebook(root);self.sales_nb.pack(fill='both',expand=True)
        sales_tab=ttk.Frame(self.sales_nb,style='Panel.TFrame',padding=5);docs_tab=ttk.Frame(self.sales_nb,style='Panel.TFrame',padding=5)
        self.sales_nb.add(sales_tab,text='فروش‌ها و مطالبات');self.sales_nb.add(docs_tab,text='اسناد فروش')
        bar=ttk.Frame(sales_tab);bar.pack(fill='x',pady=(0,5))
        ttk.Button(bar,text='ویرایش قرارداد',command=self.edit_sale).pack(side='right')
        ttk.Button(bar,text='اقساط فروش',command=self.sale_installments).pack(side='right',padx=4)
        ttk.Button(bar,text='لغو قرارداد',command=self.cancel_sale).pack(side='right',padx=4)
        ttk.Button(bar,text='بارگذاری قرارداد',command=lambda:self._upload_sale_doc('CONTRACT')).pack(side='right',padx=4)
        ttk.Button(bar,text='بارگذاری مبایعه‌نامه',command=lambda:self._upload_sale_doc('DEED')).pack(side='right',padx=4)
        self.sales_table=v181.SmartTable(sales_tab,[('unit','واحد',80),('buyer','خریدار',150),('contract','قرارداد',130),('received','وصول',125),('remain','مانده',125),('overdue','معوق',120),('next','سررسید بعدی',110),('status','وضعیت',90),('id','Sale ID',150)])
        self.sales_table.pack(fill='both',expand=True);self.sales_table.set_edit_handler(lambda r:self.edit_sale_row(r));self.sales_table.set_delete_handler(lambda r:self._cancel_sale_row(r))
        dbar=tk.Frame(docs_tab,bg=DARK['surface'],highlightbackground=DARK['line'],highlightthickness=1);dbar.pack(fill='x',pady=(0,5))
        tk.Label(dbar,text='اسناد رکورد فروش انتخاب‌شده',bg=DARK['surface'],fg=DARK['text'],font=('Segoe UI',10,'bold')).pack(side='right',padx=8,pady=7)
        tk.Button(dbar,text='بارگذاری قرارداد',command=lambda:self._upload_sale_doc('CONTRACT'),bg=DARK['glass'],fg=DARK['text'],relief='flat').pack(side='right',padx=3,pady=4)
        tk.Button(dbar,text='بارگذاری مبایعه‌نامه',command=lambda:self._upload_sale_doc('DEED'),bg=DARK['glass'],fg=DARK['text'],relief='flat').pack(side='right',padx=3,pady=4)
        tk.Button(dbar,text='بروزرسانی اسناد',command=self._refresh_sale_docs,bg=DARK['glass'],fg=DARK['text'],relief='flat').pack(side='right',padx=3,pady=4)
        self.sale_docs_tree=ttk.Treeview(docs_tab,columns=('type','file','date','id'),show='headings',height=12)
        for c,t,w in [('type','نوع سند',140),('file','نام فایل',430),('date','تاریخ ثبت',190),('id','Attachment ID',180)]:self.sale_docs_tree.heading(c,text=t);self.sale_docs_tree.column(c,width=w,anchor='e')
        self.sale_docs_tree.pack(fill='both',expand=True)
        self.sale_docs_tree.bind('<Double-1>',lambda e:self._open_sale_doc_tree(),add='+')
        self.sales_table.tree.bind('<<TreeviewSelect>>',lambda e:self._refresh_sale_docs(),add='+')
        self.after_idle(lambda:self._install_rtl(self.sales_nb))
    def _upload_sale_doc(self,doc_type):
        r=_selected_row(self.sales_table)
        if not r:return messagebox.showwarning('اسناد فروش','ابتدا یک فروش را انتخاب کن.',parent=self)
        path=filedialog.askopenfilename(parent=self,title='انتخاب فایل',filetypes=[('Documents','*.pdf *.jpg *.jpeg *.png *.doc *.docx'),('All files','*.*')])
        if not path:return
        try:AttachmentService(DB,BASE_DIR).add_local(entity_type='SALE',entity_id=str(r.get('sale_id') or ''),source_path=path,document_type=doc_type);self._refresh_sale_docs();messagebox.showinfo('اسناد فروش','فایل با موفقیت به رکورد فروش پیوست شد.',parent=self)
        except Exception as exc:messagebox.showerror('اسناد فروش',str(exc),parent=self)
    def _refresh_sale_docs(self):
        tree=getattr(self,'sale_docs_tree',None)
        if tree is None:return
        for i in tree.get_children():tree.delete(i)
        r=_selected_row(self.sales_table)
        if not r:return
        docs=AttachmentService(DB,BASE_DIR).list_for_entities([('SALE',str(r.get('sale_id') or ''))])
        for d in docs:
            typ='قرارداد' if d.get('document_type')=='CONTRACT' else ('مبایعه‌نامه' if d.get('document_type')=='DEED' else str(d.get('document_type') or '-'))
            tree.insert('', 'end',values=(typ,Path(d.get('local_path') or '').name,fa(d.get('created_at') or ''),d.get('attachment_id') or ''))
    def _open_sale_doc_tree(self):
        tree=getattr(self,'sale_docs_tree',None);sel=tree.selection() if tree is not None else ()
        if not sel:return
        aid=str(tree.item(sel[0],'values')[-1])
        try:AttachmentService(DB,BASE_DIR).open(aid)
        except Exception as exc:messagebox.showerror('فایل',str(exc),parent=self)
    def _show_sale_docs(self):
        r=_selected_row(self.sales_table)
        if not r:return messagebox.showwarning('اسناد فروش','ابتدا یک فروش را انتخاب کن.',parent=self)
        docs=AttachmentService(DB,BASE_DIR).list_for_entities([('SALE',str(r.get('sale_id') or ''))]);win=tk.Toplevel(self);win.title('اسناد فروش');win.geometry('850x430');tree=ttk.Treeview(win,columns=('type','file','date','id'),show='headings');
        for c,t,w in [('type','نوع سند',130),('file','فایل',390),('date','تاریخ ثبت',180),('id','ID',130)]:tree.heading(c,text=t);tree.column(c,width=w,anchor='e')
        tree.pack(fill='both',expand=True,padx=8,pady=8)
        for d in docs:tree.insert('', 'end',values=('قرارداد' if d.get('document_type')=='CONTRACT' else ('مبایعه‌نامه' if d.get('document_type')=='DEED' else d.get('document_type')),Path(d.get('local_path') or '').name,fa(d.get('created_at') or ''),d.get('attachment_id') or ''))
        attach_tree_grid(tree,light=_is_light())
        tk.Button(win,text='باز کردن فایل',command=lambda:self._open_selected_sale_doc(tree,docs),bg=DARK['glass'],fg=DARK['text'],relief='flat',padx=12,pady=6).pack(anchor='e',padx=8,pady=(0,8))
    def _open_selected_sale_doc(self,tree,docs):
        sel=tree.selection()
        if not sel:return
        aid=tree.item(sel[0],'values')[-1]
        try:AttachmentService(DB,BASE_DIR).open(aid)
        except Exception as exc:messagebox.showerror('فایل',str(exc),parent=self)
    def _build_reports(self):
        super()._build_reports(); self.after_idle(self._reports_183_finalize)
    def _reports_183_finalize(self):
        self._install_rtl(self.report_main);self._install_rtl(self.report_nb)
        # Collapse legacy output widgets into one dropdown that executes on selection (#11).
        bar=getattr(self,'report_export_bar',None)
        if bar:
            for w in list(bar.winfo_children()):w.destroy()
            tk.Label(bar,text='خروجی تب فعال',bg=DARK['surface'],fg=DARK['muted'],font=('Segoe UI',10,'bold')).pack(side='right',padx=8)
            self.report_export_mode.set('انتخاب فرمت خروجی');cb=ttk.Combobox(bar,textvariable=self.report_export_mode,state='readonly',values=['انتخاب فرمت خروجی','پرینت','Excel','PDF'],width=19,justify='right');cb.pack(side='right',padx=5,pady=5);cb.bind('<<ComboboxSelected>>',lambda e:self._report_output_selected(),add='+')
        # V18.3: report card heights are directly adjustable with the mouse (#5).
        # Stage18.1 report pages are pack-based rather than PanedWindow-based, so install
        # real draggable resize handles on their sizeable top panels instead of merely
        # changing a cursor. This keeps all report business logic untouched.
        for tab_id in self.report_main.tabs():
            try:
                page=self.report_main.nametowidget(tab_id)
                self._install_report_resize_handles(page)
            except Exception:
                pass
        for w in _walk(self.report_main.master):
            if isinstance(w,ttk.Panedwindow) and str(w.cget('orient'))=='vertical':
                try:w.configure(cursor='sb_v_double_arrow')
                except Exception:pass

    def _install_report_resize_handles(self,page):
        """Attach mouse-drag height handles to sizeable report panels.

        We intentionally do not rebuild/re-parent Stage18.1 report widgets; doing so
        would risk changing report behavior. A handle pins a panel's requested height
        only after the user drags it, so the default layout remains identical until
        interaction.
        """
        p=_palette(); candidates=[]
        try: page.update_idletasks()
        except Exception: pass
        for child in list(page.winfo_children()):
            # The financial-parameter GlassSection and any future packed report card are
            # useful resize targets. Skip notebooks/tables/action bars.
            if isinstance(child,ttk.Treeview):
                continue
            try:
                pm=child.pack_info()
            except Exception:
                continue
            if not pm:
                continue
            # Tiny action/legend bars are not height-adjustable cards.
            try:
                req=max(int(child.winfo_reqheight()),int(child.winfo_height()))
            except Exception:
                req=0
            if req < 70:
                continue
            candidates.append(child)
        handles=[]
        for target in candidates:
            h=tk.Frame(page,height=6,bg=p['line'],cursor='sb_v_double_arrow',takefocus=0)
            try:h.pack(fill='x',padx=7,pady=(0,2),after=target)
            except Exception:
                h.destroy();continue
            h._barkav_resize_target=target
            h._barkav_resize_state={'y':0,'height':0}
            def press(ev,handle=h,t=target):
                try:
                    handle._barkav_resize_state={'y':ev.y_root,'height':max(t.winfo_height(),t.winfo_reqheight())}
                except Exception:
                    pass
            def drag(ev,handle=h,t=target):
                try:
                    st=handle._barkav_resize_state;new_h=max(80,min(680,int(st['height'])+(ev.y_root-int(st['y']))))
                    t.configure(height=new_h)
                    if isinstance(t,ttk.Notebook):
                        t.pack_configure(expand=False)
                    else:
                        t.pack_propagate(False)
                except Exception:
                    pass
            h.bind('<ButtonPress-1>',press,add='+');h.bind('<B1-Motion>',drag,add='+')
            handles.append(h)
        page._barkav_resize_handles=handles
    def _report_output_selected(self):
        mode=self.report_export_mode.get();self.report_export_mode.set('انتخاب فرمت خروجی')
        mapping={'پرینت':'Print','PDF':'PDF','Excel':'Excel'}
        if mode not in mapping:return
        self.report_export_mode.set(mapping[mode]);self.export_report_choose();self.report_export_mode.set('انتخاب فرمت خروجی')
    def _install_rtl(self,nb):
        if not isinstance(nb,ttk.Notebook) or getattr(nb,'_barkav_rtl_strip',None):return
        p=_palette();strip=RtlNotebookStrip(nb,bg=p['surface'],line=p['line'],text=p['text'],muted=p['muted'],active_bg=p['panel2'],active_fg=p['cyan']);nb._barkav_rtl_strip=strip;self._rtl_strips.append(strip)
    def _build_settings(self):
        tab=ttk.Frame(self.notebook,style='Panel.TFrame');self.notebook.add(tab,text='تنظیمات');SettingsTab183(tab,self._settings_saved).pack(fill='both',expand=True)
    def _settings_saved(self,old,new):
        visual=any(old.get(k)!=new.get(k) for k in ('appearance','font_family','font_size','row_height'))
        self.ui=load_ui()
        if visual:
            messagebox.showinfo('تنظیمات','تنظیمات ذخیره شد؛ رابط کاربری اکنون خودکار بازآفرینی می‌شود.',parent=self);self._restart_requested=True;self.after(100,self.destroy)
        else:
            self.refresh_all();messagebox.showinfo('تنظیمات','تنظیمات ذخیره و بدون بستن برنامه اعمال شد.',parent=self)
    def edit_project_settings(self):ProjectSettingsDialog183(self,self.refresh_all)
    def export_development_package(self):
        dest=filedialog.asksaveasfilename(parent=self,defaultextension='.zip',initialfile='BARKAV_Development_Package_18.3.zip',filetypes=[('ZIP','*.zip')])
        if not dest:return
        try:
            res=v18.v175.v174.build_development_package(BASE_DIR,Path(dest),VERSION);messagebox.showinfo('بسته توسعه',f"بسته توسعه {VERSION} ساخته شد:\n{res['path']}\n\nدیتابیس زنده و secrets وارد بسته نشده‌اند.",parent=self)
        except Exception as exc:messagebox.showerror('بسته توسعه',str(exc),parent=self)
    def refresh_financial(self):
        super().refresh_financial();
        try:_persianize_region(self.fin_nb)
        except Exception:pass
    def refresh_sales(self):
        super().refresh_sales();
        try:_persianize_region(self.sales_root)
        except Exception:pass
    def refresh_manager(self):
        super().refresh_manager();
        try:_persianize_region(self.nametowidget(self.manager_tab_id))
        except Exception:pass
        try:
            for m in self.manager_metrics.values():m.var.set(fa(m.var.get()))
        except Exception:pass
    def refresh_reports(self):
        super().refresh_reports();
        try:_persianize_region(self.report_main.master)
        except Exception:pass
    def _finalize_183(self):
        _retarget_region(self);attach_grids_recursive(self,light=_is_light());_install_output_dropdowns(self)
        # RTL on all requested sub-tab families.
        for nb in (getattr(self,'fin_nb',None),getattr(self,'report_main',None),getattr(self,'report_nb',None)):
            if isinstance(nb,ttk.Notebook):self._install_rtl(nb)
        # Make all common table/action surfaces match the sharper reference-card system.
        p=_palette()
        for w in _walk(self):
            if isinstance(w,(tk.Frame,tk.LabelFrame)):
                try:
                    if int(str(w.cget('highlightthickness') or 0))>=1:w.configure(highlightbackground=p['line'])
                except Exception:pass

# Export compatibility aliases.
Stage183DashboardFinal=Stage183Dashboard
Stage183Dashboard=Stage183DashboardFinal
Stage182Dashboard=Stage183DashboardFinal
Stage18Dashboard=Stage183DashboardFinal

if __name__=='__main__':Stage183Dashboard().mainloop()
