"""Consolidated active BARKAV 18.7 Dashboard runtime."""
from __future__ import annotations

import types as _types

def _legacy_snapshot():
    return _types.SimpleNamespace(**globals().copy())


# ---- Extracted from dashboard_stage12.py ----

import os
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable
from ui import DateField, SignedMetric, bind_grouped_number, group_int, parse_int
from unit_service import UnitService

from config_loader import load_config
from dashboard_read_model import DashboardServiceStage12
from export_utils import export_pdf, export_xlsx, print_file
from finance_db import FinanceDB
from reaction_cleanup import clear_group_reaction
from revenue_service import gregorian_to_shamsi, shamsi_to_gregorian, normalize_shamsi
from telegram_history_import import import_telegram_export

BASE_DIR=Path(__file__).resolve().parents[2]
CONFIG=load_config(BASE_DIR)
DB=FinanceDB(CONFIG.db_path)
SERVICE=DashboardServiceStage12(DB,BASE_DIR)
UNITS=UnitService(DB)

COLORS={
    'navy':'#153B5B','blue':'#2D6F9F','cyan':'#2C8E9E','green':'#2F7D63','orange':'#C17C2C',
    'red':'#B84B4B','bg':'#EEF3F7','panel':'#FFFFFF','muted':'#637381','line':'#D8E2EA','text':'#1E2D3D','soft':'#F7FAFC','rowblue':'#D7E8F5'
}


FA_DIGITS=str.maketrans('0123456789','۰۱۲۳۴۵۶۷۸۹')
def money(v:Any)->str:
    try:return f"{int(float(v or 0)):,} تومان".translate(FA_DIGITS)
    except Exception:return '-'

def num(v:Any)->str:
    try:return f"{int(float(v or 0)):,}".translate(FA_DIGITS)
    except Exception:return '-'

def fa_status(v:str)->str:
    return {'ACTIVE':'فعال','DELETED':'حذف‌شده','APPROVED':'تأییدشده','PAID':'پرداخت‌شده','PARTIALLY_PAID':'پرداخت جزئی','POSTED':'ثبت‌شده','VOIDED':'باطل‌شده','ISSUED':'صادرشده','PENDING_DUE':'در انتظار سررسید','CASHED':'پاس‌شده','RETURNED':'برگشتی','CANCELLED':'لغوشده','COMPLETED':'تکمیل‌شده','UPCOMING':'آینده','DUE':'سررسید','OVERDUE':'معوق','UNMATCHED':'تطبیق‌نشده','MATCHED':'تطبیق‌شده','FAILED':'خطا','PENDING':'در انتظار','SYNCED':'همگام','CLOSED':'تسویه‌شده'}.get(str(v or '').upper(),str(v or '-'))


class ToolTip:
    """Small hover tooltip used by compact icon/action controls."""
    def __init__(self, widget: tk.Misc, text: str, delay: int = 450):
        self.widget=widget;self.text=text;self.delay=delay;self._job=None;self._tip=None
        widget.bind('<Enter>',self._schedule,add='+');widget.bind('<Leave>',self._hide,add='+');widget.bind('<ButtonPress>',self._hide,add='+')
    def _schedule(self,event=None):
        self._cancel();self._job=self.widget.after(self.delay,self._show)
    def _cancel(self):
        if self._job:
            try:self.widget.after_cancel(self._job)
            except Exception:pass
            self._job=None
    def _show(self):
        self._job=None
        try:
            self._tip=tk.Toplevel(self.widget);self._tip.wm_overrideredirect(True)
            label=tk.Label(self._tip,text=self.text,bg='#1D3853',fg='#FFFFFF',relief='solid',bd=1,font=('Tahoma',9,'bold'),padx=8,pady=5,justify='right',wraplength=360)
            label.pack();self._tip.update_idletasks()
            tw=max(1,self._tip.winfo_reqwidth());th=max(1,self._tip.winfo_reqheight())
            wx=self.widget.winfo_rootx();wy=self.widget.winfo_rooty();wh=self.widget.winfo_height();ww=self.widget.winfo_width()
            # Prefer the Windows work-area so tooltips never disappear behind
            # the taskbar. Other platforms fall back to the Tk screen bounds.
            left=top=0;right=self.widget.winfo_screenwidth();bottom=self.widget.winfo_screenheight()
            try:
                if os.name=='nt':
                    import ctypes
                    class RECT(ctypes.Structure):
                        _fields_=[('left',ctypes.c_long),('top',ctypes.c_long),('right',ctypes.c_long),('bottom',ctypes.c_long)]
                    rect=RECT()
                    if ctypes.windll.user32.SystemParametersInfoW(0x0030,0,ctypes.byref(rect),0):
                        left,top,right,bottom=rect.left,rect.top,rect.right,rect.bottom
            except Exception:
                pass
            x=wx+12;y=wy+wh+5
            if y+th>bottom-4:
                y=wy-th-6
            if y<top+4:
                y=top+4
            if x+tw>right-4:
                x=max(left+4,right-tw-4)
            if x<left+4:
                x=left+4
            self._tip.wm_geometry(f'+{int(x)}+{int(y)}')
        except Exception:self._tip=None
    def _hide(self,event=None):
        self._cancel()
        if self._tip:
            try:self._tip.destroy()
            except Exception:pass
            self._tip=None


def add_tooltip(widget: tk.Misc, text: str) -> tk.Misc:
    if not getattr(widget,'_peymaan_tooltip',None):
        widget._peymaan_tooltip=ToolTip(widget,text)
    return widget


class DashboardMetric(tk.Frame):
    """One compact dashboard metric line with bold title and zebra background."""
    def __init__(self,parent,title:str,accent:str,info:str='',row_bg:str|None=None):
        bg=row_bg or COLORS['panel']
        super().__init__(parent,bg=bg,highlightbackground=COLORS['line'],highlightthickness=0)
        tk.Frame(self,bg=accent,width=4).pack(side='right',fill='y')
        titlebox=tk.Frame(self,bg=bg);titlebox.pack(side='right',fill='x',expand=True,padx=(6,8),pady=3)
        tk.Label(titlebox,text=title,bg=bg,fg=COLORS['text'],font=('Tahoma',9,'bold'),anchor='e').pack(side='right')
        if info:
            b=tk.Button(titlebox,text='ⓘ',bg=bg,fg=accent,activebackground=bg,activeforeground=accent,relief='flat',bd=0,font=('Tahoma',8,'bold'),padx=3,pady=0,command=lambda:messagebox.showinfo(title,info,parent=self))
            b.pack(side='right',padx=(2,0));add_tooltip(b,'تعریف و نحوه محاسبه این شاخص')
        self.var=tk.StringVar(value='0 تومان')
        self.value_label=tk.Label(self,textvariable=self.var,bg=bg,fg=accent,font=('Tahoma',10,'bold'),anchor='w')
        self.value_label.pack(side='left',padx=10,pady=3)
        tk.Frame(self,bg=COLORS['line'],height=1).pack(side='bottom',fill='x')


class CompactKPI(tk.Frame):
    """Half-height KPI used in the report tab."""
    def __init__(self,parent,title:str,accent:str,info:str=''):
        super().__init__(parent,bg=COLORS['panel'],highlightbackground=COLORS['line'],highlightthickness=1)
        self.var=tk.StringVar(value='0 تومان')
        tk.Frame(self,bg=accent,width=3).pack(side='right',fill='y')
        tk.Label(self,text=title,bg=COLORS['panel'],fg=COLORS['text'],font=('Tahoma',7,'bold'),anchor='e').pack(side='right',padx=(3,4),pady=2)
        self.value_label=tk.Label(self,textvariable=self.var,bg=COLORS['panel'],fg=accent,font=('Tahoma',8,'bold'),anchor='w')
        self.value_label.pack(side='left',padx=4,pady=2)


class KPI(tk.Frame):
    def __init__(self,parent,title:str,accent:str,info:str=''):
        super().__init__(parent,bg=COLORS['panel'],highlightbackground=COLORS['line'],highlightthickness=1)
        tk.Frame(self,bg=accent,height=3).pack(fill='x')
        head=tk.Frame(self,bg=COLORS['panel']);head.pack(fill='x',padx=5,pady=(5,0))
        if info:
            tk.Button(head,text='ⓘ',command=lambda:messagebox.showinfo(title,info,parent=self),bg=COLORS['panel'],fg=accent,
                      activebackground=COLORS['panel'],activeforeground=accent,relief='flat',bd=0,font=('Tahoma',9,'bold'),padx=2,pady=0).pack(side='left')
        tk.Label(head,text=title,bg=COLORS['panel'],fg=COLORS['muted'],font=('Tahoma',8)).pack(side='right',expand=True)
        self.var=tk.StringVar(value='0 تومان')
        self.value_label=tk.Label(self,textvariable=self.var,bg=COLORS['panel'],fg=COLORS['text'],font=('Tahoma',10,'bold'));self.value_label.pack(pady=(1,6))


class SmartTable(ttk.Frame):
    _counter=0
    def __init__(self,parent,columns:list[tuple[str,str,int]],title:str=''):
        super().__init__(parent)
        SmartTable._counter += 1
        self.columns=columns; self.all_rows:list[dict[str,Any]]=[]; self.filtered_rows:list[dict[str,Any]]=[]; self.row_values:Callable[[dict[str,Any]],list[Any]]|None=None
        self.edit_handler:Callable[[dict[str,Any]],None]|None=None; self.delete_handler:Callable[[dict[str,Any]],None]|None=None
        self.quick=tk.StringVar(); self.total=tk.StringVar(value='0 مورد | جمع: 0 تومان'); self.row_height=20
        self.style_name=f'PeymaanTable{SmartTable._counter}.Treeview';self.heading_style_name=f'{self.style_name}.Heading'
        style=ttk.Style(self);style.configure(self.style_name,rowheight=self.row_height,background=COLORS['soft'],fieldbackground=COLORS['soft'],foreground=COLORS['text'],font=('Tahoma',8));style.configure(self.heading_style_name,font=('Tahoma',8,'bold'),padding=(3,2))
        bar=ttk.Frame(self); bar.pack(fill='x',pady=(0,1))
        if title: ttk.Label(bar,text=title,style='Section.TLabel').pack(side='right',padx=(0,5))
        ttk.Label(bar,text='فیلتر:',font=('Tahoma',8)).pack(side='right'); ent=ttk.Entry(bar,textvariable=self.quick,width=22,justify='right',style='Compact.TEntry'); ent.pack(side='right',padx=2); ent.bind('<KeyRelease>',lambda e:self.apply_filter());add_tooltip(ent,'فیلتر سریع همین جدول؛ هر کلمه‌ای در سطر باشد نمایش داده می‌شود.')
        bclear=ttk.Button(bar,text='✖',width=3,style='Toolbar.TButton',command=lambda:(self.quick.set(''),self.apply_filter()));bclear.pack(side='right');add_tooltip(bclear,'پاک کردن فیلتر')
        bminus=ttk.Button(bar,text='↕−',width=4,style='Toolbar.TButton',command=lambda:self.change_row_height(-2));bminus.pack(side='left');add_tooltip(bminus,'کاهش همزمان ارتفاع سطرها و سربرگ جدول')
        bplus=ttk.Button(bar,text='↕+',width=4,style='Toolbar.TButton',command=lambda:self.change_row_height(2));bplus.pack(side='left',padx=(1,3));add_tooltip(bplus,'افزایش همزمان ارتفاع سطرها و سربرگ جدول')
        self.b_select_all=ttk.Button(bar,text='☑ همه',style='Toolbar.TButton',command=self.select_all);self.b_select_all.pack(side='left',padx=(0,2));add_tooltip(self.b_select_all,'انتخاب همه ردیف‌های قابل مشاهده')
        self.b_bulk_delete=ttk.Button(bar,text='🗑 انتخاب‌ها',style='Toolbar.TButton',command=self._delete_selected_many,state='disabled');self.b_bulk_delete.pack(side='left',padx=(0,2));add_tooltip(self.b_bulk_delete,'حذف/ابطال گروهی ردیف‌های انتخاب‌شده')
        bcopy=ttk.Button(bar,text='📋',width=4,style='Toolbar.TButton',command=self.copy_selected);bcopy.pack(side='left');add_tooltip(bcopy,'کپی ردیف‌های انتخاب‌شده')
        bx=ttk.Button(bar,text='📊',width=4,style='Toolbar.TButton',command=self.export_excel);bx.pack(side='left',padx=1);add_tooltip(bx,'خروجی Excel از نتیجه فعلی فیلتر')
        bp=ttk.Button(bar,text='📄',width=4,style='Toolbar.TButton',command=self.export_pdf);bp.pack(side='left',padx=1);add_tooltip(bp,'خروجی PDF از نتیجه فعلی فیلتر')
        bprint=ttk.Button(bar,text='🖨',width=4,style='Toolbar.TButton',command=self.print_report);bprint.pack(side='left',padx=1);add_tooltip(bprint,'چاپ نتیجه فعلی فیلتر')
        frame=ttk.Frame(self); frame.pack(fill='both',expand=True)
        cols=[c[0] for c in columns]
        self.tree=ttk.Treeview(frame,columns=cols,show='headings',selectmode='extended',style=self.style_name)
        vs=ttk.Scrollbar(frame,orient='vertical',command=self.tree.yview); hs=ttk.Scrollbar(frame,orient='horizontal',command=self.tree.xview); self.tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set)
        self.tree.grid(row=0,column=0,sticky='nsew'); vs.grid(row=0,column=1,sticky='ns'); hs.grid(row=1,column=0,sticky='ew'); frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)
        for key,label,width in columns:
            self.tree.heading(key,text=label); self.tree.column(key,width=width,anchor='center',stretch=True)
        self.tree.tag_configure('odd',background=COLORS['rowblue'],foreground=COLORS['text']); self.tree.tag_configure('even',background=COLORS['panel'])
        ttk.Label(self,textvariable=self.total,style='Summary.TLabel').pack(fill='x',pady=(2,0))
        self.tree.bind('<Control-c>',lambda e:self.copy_selected());self.tree.bind('<Control-C>',lambda e:self.copy_selected())
        self.tree.bind('<Double-1>', self._double_edit);self.tree.bind('<Return>', self._double_edit);self.tree.bind('<F2>', self._double_edit)
        self.tree.bind('<Control-v>', lambda e:self.paste_filter());self.tree.bind('<Control-V>', lambda e:self.paste_filter())
        self.tree.bind('<<TreeviewSelect>>', lambda e:self._update_total());self.tree.bind('<Button-3>', self._context_menu)

    def set_edit_handler(self, handler:Callable[[dict[str,Any]],None]|None): self.edit_handler=handler
    def set_delete_handler(self, handler:Callable[[dict[str,Any]],None]|None):
        self.delete_handler=handler
        try:self.b_bulk_delete.configure(state='normal' if handler else 'disabled')
        except Exception:pass

    @staticmethod
    def _row_uid(r:dict[str,Any], index:int=0)->str:
        for key in ('pending_id','transaction_id','expense_id','cheque_id','sale_id','loan_id','reconciliation_id','activity_id','phase_id','unit_id','attachment_id','payment_id','id'):
            v=r.get(key)
            if v not in (None,''):
                return f'{key}:{v}'
        return f'row:{index}'

    def select_all(self):
        kids=self.tree.get_children()
        if kids:
            self.tree.selection_set(kids)
            self.tree.focus(kids[0])
            self._update_total()

    def _delete_selected_many(self):
        if not self.delete_handler:return
        rows=self.selected_rows()
        if not rows:return
        bulk=len(rows)>1
        if bulk and not messagebox.askyesno('عملیات گروهی',f'{len(rows):,} ردیف انتخاب شده است. حذف/ابطال روی همه اجرا شود؟',parent=self):return
        # Handlers remain the source of truth. Run one-by-one so existing safety
        # checks/audit paths are preserved. A handler may refresh the table; use a copy.
        # The group prompt above is the one decision for the whole selection: while the
        # loop runs, the owning window tells each handler not to ask a second time.
        owner=self.winfo_toplevel()
        if bulk:owner._bulk_delete_confirmed=True
        try:
            for r in list(rows):
                try:self.delete_handler(r)
                except Exception as exc:messagebox.showerror('عملیات گروهی',str(exc),parent=self);break
        finally:
            if bulk:owner._bulk_delete_confirmed=False

    def change_row_height(self,delta:int):
        self.row_height=max(18,min(44,self.row_height+int(delta)))
        style=ttk.Style(self);style.configure(self.style_name,rowheight=self.row_height)
        # Keep the heading and data rows visually proportional so neither becomes
        # cramped or disappears below the table viewport.
        heading_pad=max(1,min(7,round((self.row_height-14)/3)))
        style.configure(self.heading_style_name,font=('Tahoma',8,'bold'),padding=(3,heading_pad))

    def _double_edit(self,event=None):
        if not self.edit_handler:return
        rows=self.selected_rows()
        if rows:self.edit_handler(rows[0])

    def _delete_selected(self):
        if not self.delete_handler:return
        rows=self.selected_rows()
        if rows:self.delete_handler(rows[0])

    def set_rows(self,rows:list[dict[str,Any]],row_values:Callable[[dict[str,Any]],list[Any]]):
        self.all_rows=rows; self.row_values=row_values; self.apply_filter()

    def apply_filter(self):
        try: _yview = self.tree.yview()
        except Exception: _yview = ()
        q=self.quick.get().strip().lower().replace('ي','ی').replace('ك','ک')
        if q:
            toks=q.split(); out=[]
            for r in self.all_rows:
                vals=self.row_values(r) if self.row_values else list(r.values()); hay=' '.join(str(v or '') for v in vals).lower().replace('ي','ی').replace('ك','ک')
                if all(t in hay for t in toks):out.append(r)
            self.filtered_rows=out
        else:self.filtered_rows=list(self.all_rows)
        selected_uids={self._row_uid(r) for r in self.selected_rows()}
        focused_row=None
        try:
            f=self.tree.focus(); focused_row=self._iid_to_row.get(f) if hasattr(self,'_iid_to_row') else None
        except Exception:pass
        for x in self.tree.get_children():self.tree.delete(x)
        self._iid_to_row={}
        total_amount=0; restore=[]
        used=set()
        for i,r in enumerate(self.filtered_rows):
            vals=self.row_values(r) if self.row_values else list(r.values())
            base=self._row_uid(r,i);iid=base;n=2
            while iid in used:iid=f'{base}#{n}';n+=1
            used.add(iid);self._iid_to_row[iid]=r
            self.tree.insert('', 'end', iid=iid, values=vals, tags=('even' if i%2==0 else 'odd',))
            if self._row_uid(r) in selected_uids:restore.append(iid)
            try: total_amount += int(r.get('_sum_amount',r.get('amount',r.get('final_amount',r.get('contract_amount',0)))) or 0)
            except Exception:pass
        if restore:
            try:self.tree.selection_set(restore);self.tree.focus(restore[0])
            except Exception:pass
        # Automatic refresh must never jump the operator back to the top. Restore
        # the previous viewport after rebuilding rows; selection is restored independently.
        if _yview:
            try:self.tree.yview_moveto(_yview[0])
            except Exception:pass
        self._filtered_total_amount=total_amount;self._update_total()

    def _row_amount(self,r:dict[str,Any])->int:
        try:return int(r.get('_sum_amount',r.get('amount',r.get('final_amount',r.get('contract_amount',0)))) or 0)
        except Exception:return 0

    def _update_total(self):
        total_amount=getattr(self,'_filtered_total_amount',0); selected=self.selected_rows()
        if selected:
            sel=sum(self._row_amount(r) for r in selected)
            self.total.set(f"{len(self.filtered_rows):,} مورد | جمع: {total_amount:,} تومان | انتخاب: {len(selected):,} / {sel:,} تومان")
        else:self.total.set(f"{len(self.filtered_rows):,} مورد | جمع: {total_amount:,} تومان")

    def _context_menu(self,event):
        iid=self.tree.identify_row(event.y)
        if iid:self.tree.selection_set(iid);self.tree.focus(iid)
        menu=tk.Menu(self,tearoff=0)
        if self.edit_handler:menu.add_command(label='✏️ ویرایش',command=self._double_edit)
        if self.delete_handler:
            label='🗑 حذف/ابطال انتخاب‌ها' if len(self.selected_rows())>1 else '🗑 حذف/ابطال'
            menu.add_command(label=label,command=self._delete_selected_many)
        if self.edit_handler or self.delete_handler:menu.add_separator()
        menu.add_command(label='📋 کپی',command=self.copy_selected);menu.add_command(label='📥 پیست در فیلتر',command=self.paste_filter)
        refresh=getattr(self,'_barkav_refresh_187',None)
        menu.add_command(label='🔄 بروزرسانی',command=refresh if callable(refresh) else self.apply_filter)
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()

    def selected_rows(self)->list[dict[str,Any]]:
        out=[]
        mapping=getattr(self,'_iid_to_row',{})
        for iid in self.tree.selection():
            if iid in mapping:
                out.append(mapping[iid]);continue
            try:out.append(self.filtered_rows[int(iid)])
            except Exception:pass
        return out

    def current_report_rows(self,selected_only=False)->tuple[list[str],list[list[Any]]]:
        rows=self.selected_rows() if selected_only and self.selected_rows() else self.filtered_rows
        headers=[c[1] for c in self.columns];vals=[self.row_values(r) if self.row_values else list(r.values()) for r in rows];return headers,vals

    def copy_selected(self):
        headers,rows=self.current_report_rows(selected_only=True)
        if not rows:return
        text='\t'.join(headers)+'\n'+'\n'.join('\t'.join(str(v or '') for v in row) for row in rows);self.clipboard_clear();self.clipboard_append(text)

    def paste_filter(self):
        try:text=self.clipboard_get().strip()
        except Exception:return
        self.quick.set((text.splitlines()[0] if text else '')[:300]);self.apply_filter()

    def _save(self,kind:str,do_print=False):
        headers,rows=self.current_report_rows(selected_only=False);ext='.xlsx' if kind=='xlsx' else '.pdf';path=filedialog.asksaveasfilename(defaultextension=ext,filetypes=[('Excel','*.xlsx')] if kind=='xlsx' else [('PDF','*.pdf')])
        if not path:return
        if kind=='xlsx':export_xlsx(path,headers,rows,title='گزارش')
        else:export_pdf(path,headers,rows,title='گزارش',summary_lines=[self.total.get()])
        if do_print:print_file(path)
        else:messagebox.showinfo('خروجی',f'فایل ساخته شد:\n{path}')
    def export_excel(self):self._save('xlsx')
    def export_pdf(self):self._save('pdf')
    def print_report(self):
        fd,path=tempfile.mkstemp(suffix='.pdf');os.close(fd);headers,rows=self.current_report_rows(False);export_pdf(path,headers,rows,title='گزارش',summary_lines=[self.total.get()]);print_file(path)


def bind_enter_action(window: tk.Misc, action: Callable[[],None]) -> None:
    """Make Enter behave like the primary action in data-entry dialogs."""
    def _go(event=None):
        # Keep Enter available for Treeview row activation and multi-line text.
        w=getattr(event,'widget',None)
        if isinstance(w,(ttk.Treeview,tk.Text)): return None
        action(); return 'break'
    window.bind('<Return>',_go,add='+')


class CompactTable(ttk.Frame):
    """Read-only compact table used on the executive overview."""
    _counter=0
    def __init__(self,parent,columns:list[tuple[str,str,int]],height:int=3):
        super().__init__(parent);CompactTable._counter+=1;keys=[c[0] for c in columns]
        self.style_name=f'CompactDashboard{CompactTable._counter}.Treeview'
        st=ttk.Style(self);st.configure(self.style_name,rowheight=21,background='#0C1827',fieldbackground='#0C1827',foreground='#EAF2FA',font=('Tahoma',8))
        self.tree=ttk.Treeview(self,columns=keys,show='headings',height=height,style=self.style_name)
        for k,l,w in columns:self.tree.heading(k,text=l);self.tree.column(k,width=w,anchor='center',stretch=True)
        self.tree.tag_configure('odd',background='#102238',foreground='#EAF2FA');self.tree.tag_configure('even',background='#0C1827',foreground='#EAF2FA')
        vs=ttk.Scrollbar(self,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=vs.set);self.tree.pack(side='left',fill='both',expand=True);vs.pack(side='right',fill='y')
    def set_rows(self,rows:list[list[Any]]):
        for x in self.tree.get_children():self.tree.delete(x)
        for i,row in enumerate(rows):self.tree.insert('', 'end',iid=str(i),values=row,tags=('even' if i%2==0 else 'odd',))


class Stage12Dashboard(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('Peymaan V2 — Stage 13 Management'); self.geometry('1440x900'); self.minsize(1180,720); self.option_add('*Font',('Tahoma',9)); self.configure(bg=COLORS['bg']); self._style(); self._build(); self.after(200,self.refresh_all); self.after(15000,self._periodic)

    def _style(self):
        st=ttk.Style(self)
        try:st.theme_use('clam')
        except Exception:pass
        st.configure('.',font=('Tahoma',8),background=COLORS['bg'],foreground=COLORS['text'])
        st.configure('TFrame',background=COLORS['bg']);st.configure('Panel.TFrame',background=COLORS['panel'])
        st.configure('TNotebook',background=COLORS['bg'],borderwidth=0);st.configure('TNotebook.Tab',padding=(10,4),font=('Tahoma',8,'bold'));st.map('TNotebook.Tab',background=[('selected',COLORS['panel'])],foreground=[('selected',COLORS['navy'])])
        st.configure('TButton',padding=(6,3));st.configure('Primary.TButton',background=COLORS['blue'],foreground='white');st.map('Primary.TButton',background=[('active',COLORS['navy'])])
        st.configure('Toolbar.TButton',padding=(3,1),font=('Tahoma',8));st.configure('Compact.TButton',padding=(4,1),font=('Tahoma',8));st.configure('Compact.TEntry',padding=(2,1),font=('Tahoma',8))
        st.configure('Danger.TButton',background=COLORS['red'],foreground='white')
        st.configure('Section.TLabel',font=('Tahoma',9,'bold'),foreground=COLORS['navy'],background=COLORS['bg'])
        st.configure('Summary.TLabel',font=('Tahoma',8,'bold'),foreground=COLORS['navy'],padding=(5,2),background='#E3EDF4')
        st.configure('Dashboard.TLabelframe',background=COLORS['panel'],bordercolor=COLORS['line'],relief='solid',borderwidth=1)
        st.configure('Dashboard.TLabelframe.Label',font=('Tahoma',10,'bold'),foreground=COLORS['navy'],background=COLORS['panel'])
        st.configure('Report.TLabelframe',padding=0);st.configure('Report.TLabelframe.Label',font=('Tahoma',8,'bold'),foreground=COLORS['navy'])
        st.configure('Treeview',rowheight=22,background=COLORS['soft'],fieldbackground=COLORS['soft'],foreground=COLORS['text'],font=('Tahoma',8));st.configure('Treeview.Heading',font=('Tahoma',8,'bold'),background='#DDE8F0',foreground=COLORS['navy'],padding=(3,2))

    def _build(self):
        top=tk.Frame(self,bg='#0B1726',height=50);top.pack(fill='x')
        right=tk.Frame(top,bg='#0B1726');right.pack(side='right',padx=12,pady=6)
        self.project_name_top=tk.StringVar(value='پروژه');self.datetime_top=tk.StringVar(value='')
        tk.Label(right,text='پیمان',bg='#0B1726',fg='white',font=('Tahoma',15,'bold')).pack(side='right')
        tk.Label(right,textvariable=self.project_name_top,bg='#0B1726',fg='#B9D8EA',font=('Tahoma',9)).pack(side='right',padx=10)
        tk.Label(right,textvariable=self.datetime_top,bg='#0B1726',fg='#E8F3F8',font=('Tahoma',9,'bold')).pack(side='right',padx=12)
        left=tk.Frame(top,bg='#0B1726');left.pack(side='left',padx=10,pady=6)
        for text,cmd,tip in [
            ('🔍 جستجو',self.open_search,'جستجوی سراسری و فیلتر پیشرفته در اطلاعات مالی'),
            ('🏢 پروژه',self.open_project,'مشخصات پروژه و آرشیو اسناد'),
            ('🏠 واحدها',self.open_units,'مدیریت واحدها، پارکینگ‌ها و انباری‌ها'),
            ('🔄 بروزرسانی',self.refresh_all,'بروزرسانی همه گزارش‌ها از SQLite'),
            ('🧪 سلامت',self.show_health,'نمایش وضعیت دیتابیس، همگام‌سازی و سرویس‌ها')]:
            b=tk.Button(left,text=text,command=cmd,bg='#214E70',fg='white',activebackground='#2D6F9F',activeforeground='white',relief='flat',padx=8,pady=4);b.pack(side='left',padx=2);add_tooltip(b,tip)
        self.notebook=ttk.Notebook(self);self.notebook.pack(fill='both',expand=True,padx=7,pady=6)
        self._build_overview();self._build_manager();self._build_financial();self._build_cheques();self._build_sales();self._build_reconciliation();self._build_reports();self._build_health()
        self._attach_common_tooltips(self)
        self._tick_clock()

    def _attach_common_tooltips(self,root):
        tips={
            '✏️ ویرایش':'ویرایش ردیف انتخاب‌شده','🗑 حذف':'حذف/ابطال امن ردیف انتخاب‌شده','📎 رسید':'مشاهده یا افزودن رسید و مدرک',
            '➕ ثبت وام':'ثبت پرونده وام جدید و ورودی نقدی مرتبط','📅 اقساط / پرداخت':'مشاهده اقساط و ثبت پرداخت وام','🚫 لغو وام':'لغو پرونده وام بدون حذف تراکنش‌های تاریخی',
            '✏️ ویرایش چک':'ویرایش مشخصات چک انتخاب‌شده','✏️ ویرایش قرارداد':'ویرایش مشخصات قرارداد فروش','📅 اقساط فروش':'مشاهده و ویرایش اقساط قرارداد','🚫 لغو قرارداد':'لغو قرارداد فروش',
            '✏️ ویرایش تطبیق':'ویرایش رکورد تطبیق بانک','🗑 حذف تطبیق':'حذف رکورد تطبیق بانک','بروزرسانی وضعیت':'بروزرسانی وضعیت سلامت سیستم',
            '➕ افزودن اسکن/فایل':'افزودن فایل سند به آرشیو پروژه','👁 باز کردن':'باز کردن سند انتخاب‌شده','🖨 پرینت سند':'چاپ سند انتخاب‌شده','🗑 حذف از آرشیو':'حذف نرم سند از فهرست آرشیو',
            '💸 ثبت پرداخت قسط':'ثبت مبلغ و تاریخ پرداخت قسط انتخاب‌شده'
        }
        try:
            txt=str(root.cget('text')) if isinstance(root,(ttk.Button,tk.Button)) else ''
            if txt in tips:add_tooltip(root,tips[txt])
        except Exception:pass
        try:
            for child in root.winfo_children():self._attach_common_tooltips(child)
        except Exception:pass

    def _tick_clock(self):
        try:
            dt=__import__('datetime').datetime.now();self.datetime_top.set(f"📅 {gregorian_to_shamsi(dt.date())}   ⏰ {dt:%H:%M:%S}")
        finally:self.after(1000,self._tick_clock)

    def _build_overview(self):
        tab=ttk.Frame(self.notebook,padding=4);self.notebook.add(tab,text='داشبورد')
        # Stage 12 uses a vertically stacked, scrollable executive dashboard.
        wrap=ttk.Frame(tab);wrap.pack(fill='both',expand=True)
        canvas=tk.Canvas(wrap,bg=COLORS['bg'],highlightthickness=0)
        vs=ttk.Scrollbar(wrap,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=vs.set)
        canvas.pack(side='left',fill='both',expand=True);vs.pack(side='right',fill='y')
        inner=tk.Frame(canvas,bg=COLORS['bg']);win=canvas.create_window((0,0),window=inner,anchor='nw')
        inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width))
        def wheel(e):
            try:canvas.yview_scroll(int(-1*(e.delta/120)),'units')
            except Exception:pass
        canvas.bind('<Enter>',lambda e:canvas.bind_all('<MouseWheel>',wheel));canvas.bind('<Leave>',lambda e:canvas.unbind_all('<MouseWheel>'))

        project=tk.Frame(inner,bg=COLORS['panel'],highlightbackground=COLORS['line'],highlightthickness=1);project.pack(fill='x',padx=3,pady=(2,5))
        ptxt=tk.Frame(project,bg=COLORS['panel']);ptxt.pack(side='right',fill='x',expand=True,padx=10,pady=6)
        self.project_info=tk.StringVar(value='مشخصات پروژه ثبت نشده')
        ttk.Label(ptxt,text='مشخصات پروژه',font=('Tahoma',10,'bold'),background=COLORS['panel'],foreground=COLORS['navy']).pack(anchor='e')
        ttk.Label(ptxt,textvariable=self.project_info,font=('Tahoma',8),background=COLORS['panel'],foreground=COLORS['text'],justify='right').pack(anchor='e',pady=(2,0))
        pactions=ttk.Frame(project);pactions.pack(side='left',padx=8,pady=5)
        pbtn=ttk.Button(pactions,text='🏢 مشخصات و اسناد',command=self.open_project,style='Compact.TButton');pbtn.pack(side='right',padx=2);add_tooltip(pbtn,'ویرایش مشخصات پروژه و آرشیو/پرینت اسناد')
        hx=ttk.Button(pactions,text='📥 تاریخچه تلگرام',command=self.import_old_telegram_history,style='Compact.TButton');hx.pack(side='right',padx=2);add_tooltip(hx,'Import پیام‌های قدیمی گروه از فایل JSON خروجی Telegram Desktop؛ موارد مالی وارد صف بررسی می‌شوند.')
        ex=ttk.Button(pactions,text='📊 Excel',command=self.export_dashboard_excel,style='Compact.TButton');ex.pack(side='right',padx=2);add_tooltip(ex,'خروجی Excel از کل داشبورد مدیریتی')
        ep=ttk.Button(pactions,text='📄 PDF',command=self.export_dashboard_pdf,style='Compact.TButton');ep.pack(side='right',padx=2);add_tooltip(ep,'خروجی PDF از کل داشبورد مدیریتی')
        pr=ttk.Button(pactions,text='🖨 پرینت',command=self.print_dashboard,style='Compact.TButton');pr.pack(side='right',padx=2);add_tooltip(pr,'چاپ گزارش کامل داشبورد')

        self.cards={};self._dashboard_row_counter={}
        def make_section(title:str):
            f=ttk.LabelFrame(inner,text=title,style='Dashboard.TLabelframe',padding=4);f.pack(fill='x',padx=3,pady=4);self._dashboard_row_counter[f]=0;return f
        def add_metric(parent,key,title,color,info):
            idx=self._dashboard_row_counter.get(parent,0);bg=COLORS['panel'] if idx%2==0 else COLORS['rowblue'];self._dashboard_row_counter[parent]=idx+1
            row=DashboardMetric(parent,title,color,info,row_bg=bg);row.pack(fill='x');self.cards[key]=row;return row

        financial=make_section('گزارش مالی')
        for k,t,c,info in [
            ('cost','هزینه ساخت',COLORS['orange'],'جمع هزینه‌های واقعی ساخت تحقق‌یافته؛ مستقل از اینکه وجه آن کامل پرداخت شده باشد یا نه.'),
            ('cash','مانده تنخواه',COLORS['blue'],'مانده نقدی فعلی دفتر: مجموع تمام ورودی‌های نقدی منهای تمام خروج‌های نقدی.'),
            ('free','مانده آزاد پس از چک',COLORS['green'],'مانده تنخواه منهای تعهد چک‌های باز فعلی.'),
            ('total_in','مجموع ورودی',COLORS['cyan'],'جمع تمام تراکنش‌های ورودی ثبت‌شده در تنخواه.'),
            ('total_out','مجموع خروجی',COLORS['red'],'دقیقاً جمع زیرتب «خروجی‌ها» در ثبت‌های مالی؛ پرداخت‌های ساخت در این عدد دوباره شمرده نمی‌شوند.'),
            ('liq_obligation','تعهدات ۳۰ روز آینده',COLORS['orange'],'جمع چک‌های سررسیدشونده و اقساط وام طی ۳۰ روز آینده.'),
            ('liq_inflow','وصول برنامه‌ریزی‌شده ۳۰ روز آینده',COLORS['cyan'],'جمع اقساط خریداران که طی ۳۰ روز آینده سررسید می‌شوند؛ این مبلغ هنوز پول نقد قطعی نیست.'),
            ('liq_projected','کسری/مازاد نقدینگی تا ۳۰ روز آینده',COLORS['green'],'مانده تنخواه + وصول‌های ۳۰ روز آینده - چک‌های ۳۰ روز آینده - اقساط وام ۳۰ روز آینده. منفی یعنی برای تعهدات ماه آینده کسری داری.')
        ]:add_metric(financial,k,t,c,info)

        ch=make_section('گزارش چک‌ها')
        for k,t,c,info in [
            ('ch_all_total','مجموع کل چک‌های ثبت‌شده',COLORS['blue'],'جمع مبلغ تمام چک‌های ثبت‌شده به‌جز چک‌های لغوشده؛ شامل چک‌های پاس‌شده، برگشتی و باز.'),
            ('ch_open_total','مجموع چک‌های پاس‌نشده',COLORS['red'],'جمع مبلغ چک‌های باز شامل صادرشده، در انتظار سررسید و برگشتی؛ چک‌های پاس‌شده و لغوشده در این عدد نیستند.'),
            ('ch30_count','تعداد چک‌های ۳۰ روز آینده',COLORS['cyan'],'تعداد چک‌های باز با سررسید از امروز تا ۳۰ روز آینده.'),
            ('ch30_amount','جمع چک‌های ۳۰ روز آینده',COLORS['orange'],'جمع مبلغ چک‌های باز که طی ۳۰ روز آینده باید تأمین شوند.')
        ]:add_metric(ch,k,t,c,info)
        self.overview_cheque_table=CompactTable(ch,[('due','سررسید',90),('days','روز مانده',80),('amount','مبلغ',120),('issuer','صاحب حساب',130),('bank','بانک',110),('receiver','گیرنده',130)],height=4);self.overview_cheque_table.pack(fill='x',pady=(4,0))

        sales=make_section('گزارش فروش و مطالبات')
        for k,t,c,info in [
            ('sales_contract','کل قرارداد خریداران',COLORS['green'],'جمع مبلغ قراردادهای فروش غیرلغوشده.'),
            ('sales_received','وصول خریداران',COLORS['cyan'],'جمع وجوه واقعی دریافت‌شده از خریداران.'),
            ('sales_receivable','کل طلب از خریداران',COLORS['blue'],'مبلغ قراردادها منهای وجوه وصول‌شده.'),
            ('sales_30','طلب خریداران تا ۳۰ روز آینده',COLORS['orange'],'مانده اقساط خریداران که از امروز تا ۳۰ روز آینده سررسید می‌شوند.'),
            ('sales_overdue','مطالبات معوق خریداران',COLORS['red'],'مانده اقساط خریداران که تاریخ سررسیدشان گذشته است.')
        ]:add_metric(sales,k,t,c,info)
        f1=ttk.LabelFrame(sales,text='وصول‌های مورد انتظار تا ۳۰ روز',padding=2,style='Report.TLabelframe');f1.pack(fill='x',pady=(4,2))
        self.overview_sales_upcoming=CompactTable(f1,[('buyer','خریدار',140),('unit','واحد',75),('due','سررسید',95),('amount','مانده',120),('days','روز',60)],height=3);self.overview_sales_upcoming.pack(fill='x')
        f2=ttk.LabelFrame(sales,text='مطالبات معوق',padding=2,style='Report.TLabelframe');f2.pack(fill='x',pady=(2,0))
        self.overview_sales_overdue=CompactTable(f2,[('buyer','خریدار',140),('unit','واحد',75),('due','سررسید',95),('amount','مانده',120),('days','تأخیر',60)],height=3);self.overview_sales_overdue.pack(fill='x')

        loans=make_section('گزارش وام‌ها')
        for k,t,c,info in [
            ('loan_principal','کل تسهیلات دریافتی',COLORS['blue'],'جمع اصل وام‌ها و تسهیلات ثبت‌شده غیرلغوشده.'),
            ('loan_paid','جمع اقساط واریزی',COLORS['cyan'],'جمع مبالغی که تا امروز بابت اقساط وام‌ها واقعاً پرداخت شده است.'),
            ('loan_remaining','مانده بدهی وام‌ها',COLORS['red'],'کل مبلغ باقی‌مانده برای بازپرداخت وام‌ها.'),
            ('loan_30','اقساط وام ۳۰ روز آینده',COLORS['orange'],'جمع مانده اقساط وام که از امروز تا ۳۰ روز آینده سررسید می‌شوند.')
        ]:add_metric(loans,k,t,c,info)
        lf=ttk.LabelFrame(loans,text='ریز اقساط ۳۰ روز آینده',padding=2,style='Report.TLabelframe');lf.pack(fill='x',pady=(4,0))
        self.overview_loan_table=CompactTable(lf,[('lender','بانک',115),('title','عنوان وام',170),('no','قسط',55),('due','تاریخ',95),('amount','مانده',115),('days','روز مانده',75)],height=4);self.overview_loan_table.pack(fill='x')

        rec=ttk.LabelFrame(inner,text='تطبیق سریع بانک',style='Dashboard.TLabelframe',padding=4);rec.pack(fill='x',padx=3,pady=(4,8))
        self.bank_var=tk.StringVar();self.bank_date=tk.StringVar();ttk.Label(rec,text='موجودی واقعی:').pack(side='right');bank_ent=ttk.Entry(rec,textvariable=self.bank_var,width=18,justify='center',style='Compact.TEntry');bank_ent.pack(side='right',padx=3);bind_grouped_number(bank_ent,self.bank_var,allow_negative=True);bank_ent.bind('<Return>',lambda ev:self.record_reconciliation(),add='+');ttk.Label(rec,text='تاریخ:').pack(side='right',padx=(10,0));DateField(rec,self.bank_date,width=11).pack(side='right',padx=3);rbtn=ttk.Button(rec,text='ثبت',command=self.record_reconciliation,style='Primary.TButton');rbtn.pack(side='right',padx=5);add_tooltip(rbtn,'ثبت موجودی واقعی بانک و محاسبه اختلاف با مانده تنخواه سیستم');self.bank_info=tk.StringVar(value='آخرین تطبیق: -');self.bank_info_label=tk.Label(rec,textvariable=self.bank_info,bg=COLORS['panel'],fg=COLORS['text'],font=('Tahoma',8,'bold'));self.bank_info_label.pack(side='left',padx=5)

    def _build_manager(self):
        tab=ttk.Frame(self.notebook,padding=6);self.notebook.add(tab,text='حساب مدیر')
        controls=ttk.Frame(tab);controls.pack(fill='x',pady=(0,4));self.mgr_start=tk.StringVar();self.mgr_end=tk.StringVar()
        try:a,b=SERVICE.manager_activity_bounds();self.mgr_start.set(a);self.mgr_end.set(b)
        except Exception:pass
        ttk.Label(controls,text='از:').pack(side='right');DateField(controls,self.mgr_start,width=11).pack(side='right',padx=3);ttk.Label(controls,text='تا:').pack(side='right',padx=(8,0));DateField(controls,self.mgr_end,width=11).pack(side='right',padx=3);ttk.Button(controls,text='محاسبه',command=self.refresh_manager,style='Primary.TButton').pack(side='right',padx=5);ttk.Label(controls,text='مثبت = طلبکار | منفی = بدهکار',foreground=COLORS['muted']).pack(side='left')
        box=ttk.LabelFrame(tab,text='برداشت‌های مدیر پروژه',padding=4);box.pack(fill='both',expand=True)
        self.manager_withdraw_table=SmartTable(box,[('date','تاریخ',95),('amount','مبلغ برداشت',135),('desc','شرح',280),('id','Transaction ID',160)],title='برداشت‌ها')
        self.manager_withdraw_table.pack(fill='both',expand=True);self.manager_withdraw_table.set_edit_handler(lambda r:self.edit_transaction_row(r));self.manager_withdraw_table.set_delete_handler(lambda r:self._delete_tx_row(r))
        metrics=ttk.Frame(tab);metrics.pack(fill='x',pady=(5,0));defs=[('days','روز طلب/بدهی','روز'),('avg','میانگین طلب/بدهی','تومان'),('tm','تومان‌ماه طلب/بدهی','تومان‌ماه'),('fee','حقوق مدیر پروژه','تومان'),('withdraw','برداشت','تومان'),('balance','مانده','تومان')];self.manager_metrics={}
        for i,(k,t,u) in enumerate(defs):w=SignedMetric(metrics,t,u);w.grid(row=0,column=i,sticky='nsew',padx=2);metrics.columnconfigure(i,weight=1);self.manager_metrics[k]=w

    def _build_financial(self):
        tab=ttk.Frame(self.notebook,padding=8);self.notebook.add(tab,text='ثبت‌های مالی');self.fin_nb=ttk.Notebook(tab);self.fin_nb.pack(fill='both',expand=True)
        # all transactions
        t1=ttk.Frame(self.fin_nb,padding=6);self.fin_nb.add(t1,text='کلیه تراکنش‌ها');actions=ttk.Frame(t1);actions.pack(fill='x');ttk.Button(actions,text='✏️ ویرایش',command=lambda:self.edit_transaction(self.all_tx_table)).pack(side='right');ttk.Button(actions,text='🗑 حذف',command=lambda:self.delete_transaction(self.all_tx_table)).pack(side='right',padx=3);ttk.Button(actions,text='📎 رسید',command=lambda:self.receipts_for_transaction(self.all_tx_table)).pack(side='right',padx=3)
        self.all_tx_table=SmartTable(t1,[('date','تاریخ',100),('dir','نوع',70),('amount','مبلغ',130),('cat','دسته',130),('payer','واریزکننده',130),('receiver','دریافت‌کننده',130),('desc','شرح',220),('receipt','رسید',70),('status','وضعیت',90),('id','Transaction ID',150)]);self.all_tx_table.pack(fill='both',expand=True);self.all_tx_table.set_edit_handler(lambda r:self.edit_transaction_row(r));self.all_tx_table.set_delete_handler(lambda r:self._delete_tx_row(r))
        # expenses
        t2=ttk.Frame(self.fin_nb,padding=6);self.fin_nb.add(t2,text='هزینه ساخت');actions=ttk.Frame(t2);actions.pack(fill='x');ttk.Button(actions,text='🏗 تعیین فاز/فعالیت',command=self.classify_expense).pack(side='right');ttk.Button(actions,text='✏️ ویرایش مالی',command=self.edit_expense).pack(side='right',padx=3);ttk.Button(actions,text='🗑 حذف',command=self.delete_expense).pack(side='right',padx=3);ttk.Button(actions,text='📎 رسید',command=self.receipts_for_expense).pack(side='right',padx=3)
        self.exp_table=SmartTable(t2,[('date','تاریخ',95),('final','مبلغ نهایی',125),('paid','پرداخت‌شده',120),('phase','مرحله ساخت',155),('activity','نوع هزینه/فعالیت',165),('payer','واریزکننده',125),('receiver','دریافت‌کننده',125),('desc','شرح',190),('receipt','رسید',65),('status','وضعیت',90),('id','Expense ID',145)]);self.exp_table.pack(fill='both',expand=True);self.exp_table.set_edit_handler(lambda r:self.edit_expense_row(r));self.exp_table.set_delete_handler(lambda r:self._delete_expense_row(r))
        # inflows
        t3=ttk.Frame(self.fin_nb,padding=6);self.fin_nb.add(t3,text='ورودی‌ها');a=ttk.Frame(t3);a.pack(fill='x');ttk.Button(a,text='✏️ ویرایش',command=lambda:self.edit_transaction(self.in_table)).pack(side='right');ttk.Button(a,text='🗑 حذف',command=lambda:self.delete_transaction(self.in_table)).pack(side='right',padx=3);ttk.Button(a,text='📎 رسید',command=lambda:self.receipts_for_transaction(self.in_table)).pack(side='right',padx=3)
        self.in_table=SmartTable(t3,[('date','تاریخ',100),('amount','مبلغ ورودی',130),('cat','نوع ورودی',140),('payer','واریزکننده',150),('desc','شرح',250),('receipt','رسید',70),('id','Transaction ID',160)]);self.in_table.pack(fill='both',expand=True);self.in_table.set_edit_handler(lambda r:self.edit_transaction_row(r));self.in_table.set_delete_handler(lambda r:self._delete_tx_row(r))
        # outflows
        t4=ttk.Frame(self.fin_nb,padding=6);self.fin_nb.add(t4,text='خروجی‌ها');a=ttk.Frame(t4);a.pack(fill='x');ttk.Button(a,text='✏️ ویرایش',command=lambda:self.edit_transaction(self.out_table)).pack(side='right');ttk.Button(a,text='🗑 حذف',command=lambda:self.delete_transaction(self.out_table)).pack(side='right',padx=3);ttk.Button(a,text='📎 رسید',command=lambda:self.receipts_for_transaction(self.out_table)).pack(side='right',padx=3)
        self.out_table=SmartTable(t4,[('date','تاریخ',100),('amount','مبلغ خروجی',130),('cat','نوع خروجی',140),('receiver','دریافت‌کننده',150),('desc','شرح',250),('receipt','رسید',70),('id','Transaction ID',160)]);self.out_table.pack(fill='both',expand=True);self.out_table.set_edit_handler(lambda r:self.edit_transaction_row(r));self.out_table.set_delete_handler(lambda r:self._delete_tx_row(r))
        # loans
        t5=ttk.Frame(self.fin_nb,padding=6);self.fin_nb.add(t5,text='وام‌ها');a=ttk.Frame(t5);a.pack(fill='x');ttk.Button(a,text='➕ ثبت وام',command=self.add_loan,style='Primary.TButton').pack(side='right');ttk.Button(a,text='📅 اقساط / پرداخت',command=self.loan_installments).pack(side='right',padx=3);ttk.Button(a,text='🚫 لغو وام',command=self.cancel_loan).pack(side='right',padx=3)
        self.loan_table=SmartTable(t5,[('date','تاریخ دریافت',105),('lender','بانک/وام‌دهنده',150),('principal','اصل وام',125),('received','دریافتی واقعی',125),('interest','سود+کارمزد',120),('paid','اقساط پرداختی',125),('remain','مانده بدهی',125),('count','اقساط',80),('next','قسط بعدی',105),('status','وضعیت',90),('id','Loan ID',145)]);self.loan_table.pack(fill='both',expand=True);self.loan_table.set_edit_handler(lambda r:self.edit_loan_row(r));self.loan_table.set_delete_handler(lambda r:self._cancel_loan_row(r))

    def _build_cheques(self):
        tab=ttk.Frame(self.notebook,padding=8);self.notebook.add(tab,text='چک‌ها')
        bar=ttk.Frame(tab);bar.pack(fill='x',pady=(0,5));ttk.Button(bar,text='✏️ ویرایش چک',command=self.edit_cheque).pack(side='right')
        self.cheque_table=SmartTable(tab,[('issue','تاریخ صدور',105),('due','سررسید شمسی',110),('amount','مبلغ',130),('issuer','صادرکننده',140),('type','نوع چک',90),('receiver','گیرنده',140),('bank','بانک',120),('serial','شماره/صیادی',120),('desc','بابت',220),('status','وضعیت',100),('id','Cheque ID',160)])
        self.cheque_table.pack(fill='both',expand=True);self.cheque_table.set_edit_handler(lambda r:self.edit_cheque_row(r));self.cheque_table.set_delete_handler(lambda r:self._cancel_cheque_row(r))

    def _build_sales(self):
        tab=ttk.Frame(self.notebook,padding=8);self.notebook.add(tab,text='فروش و مطالبات')
        bar=ttk.Frame(tab);bar.pack(fill='x',pady=(0,5))
        ttk.Button(bar,text='✏️ ویرایش قرارداد',command=self.edit_sale).pack(side='right')
        ttk.Button(bar,text='📅 اقساط فروش',command=self.sale_installments).pack(side='right',padx=4)
        ttk.Button(bar,text='🚫 لغو قرارداد',command=self.cancel_sale).pack(side='right',padx=4)
        self.sales_table=SmartTable(tab,[('unit','واحد',80),('buyer','خریدار',150),('contract','قرارداد',130),('received','وصول',125),('remain','مانده',125),('overdue','معوق',120),('next','سررسید بعدی',110),('status','وضعیت',90),('id','Sale ID',150)])
        self.sales_table.pack(fill='both',expand=True);self.sales_table.set_edit_handler(lambda r:self.edit_sale_row(r));self.sales_table.set_delete_handler(lambda r:self._cancel_sale_row(r))
    def _build_reconciliation(self):
        tab=ttk.Frame(self.notebook,padding=8);self.notebook.add(tab,text='تاریخچه تطبیق بانک')
        bar=ttk.Frame(tab);bar.pack(fill='x',pady=(0,5))
        ttk.Button(bar,text='✏️ ویرایش تطبیق',command=self.edit_reconciliation).pack(side='right')
        ttk.Button(bar,text='🗑 حذف تطبیق',command=self.delete_reconciliation).pack(side='right',padx=4)
        self.rec_table=SmartTable(tab,[('date','تاریخ',100),('system','مانده سیستم',140),('bank','مانده بانک',140),('diff','اختلاف',140),('notes','توضیح',280),('id','ID',150)])
        self.rec_table.pack(fill='both',expand=True);self.rec_table.set_edit_handler(lambda r:self.edit_reconciliation_row(r));self.rec_table.set_delete_handler(lambda r:self._delete_rec_row(r))

    def _build_reports(self):
        tab=ttk.Frame(self.notebook,padding=3);self.notebook.add(tab,text='گزارش‌گیری')
        pane=ttk.Panedwindow(tab,orient='vertical');pane.pack(fill='both',expand=True)
        upper=ttk.Frame(pane);lower=ttk.Frame(pane);pane.add(upper,weight=0);pane.add(lower,weight=1)
        # ~20% shorter than Stage 11: tighter field padding and compact controls.
        settings=ttk.LabelFrame(upper,text='پارامترهای پروژه و پیش‌بینی',padding=2,style='Report.TLabelframe');settings.pack(fill='x')
        self.report_vars={k:tk.StringVar() for k in ['gross_area','saleable_area','unit_count','inflation','months','presale','end_price','misc','target']}
        fields=[('gross_area','متراژ غیرمفید'),('inflation','تورم ماهانه %'),('months','ماه تا اتمام'),('presale','پیش‌فروش/متر'),('end_price','فروش پایان/متر'),('misc','متفرقه خارج برآورد'),('target','سود هدف %')]
        self.report_entries={}
        for i,(k,label) in enumerate(fields):
            r=i//4;c=(i%4)*2;ttk.Label(settings,text=label+':',font=('Tahoma',7)).grid(row=r,column=c+1,sticky='e',padx=1,pady=0)
            e=ttk.Entry(settings,textvariable=self.report_vars[k],width=16,justify='right',style='Compact.TEntry');e.grid(row=r,column=c,sticky='ew',padx=1,pady=0);self.report_entries[k]=e
            if k in ('presale','end_price','misc'):bind_grouped_number(e,self.report_vars[k])
            e.bind('<Return>',lambda ev:self.save_report_settings(),add='+')
        self.unit_summary_var=tk.StringVar(value='واحدها: -');ttk.Label(settings,textvariable=self.unit_summary_var,foreground=COLORS['navy'],font=('Tahoma',7,'bold')).grid(row=2,column=0,columnspan=6,sticky='w',padx=1,pady=0)
        ub=ttk.Button(settings,text='🏢 واحدها',command=self.open_units,style='Compact.TButton');ub.grid(row=2,column=6,columnspan=2,sticky='e',padx=1,pady=0);add_tooltip(ub,'باز کردن جدول واحدها، متراژ، پارکینگ و انباری')

        actions=ttk.Frame(upper);actions.pack(fill='x',pady=1)
        bsave=ttk.Button(actions,text='💾 ذخیره پارامترها',command=self.save_report_settings,style='Compact.TButton');bsave.pack(side='right');add_tooltip(bsave,'ذخیره پارامترهای پیش‌بینی و محاسبه دوباره گزارش')
        bimport=ttk.Button(actions,text='📥 اکسل برآورد',command=self.import_budget,style='Compact.TButton');bimport.pack(side='right',padx=2);add_tooltip(bimport,'بارگذاری یا به‌روزرسانی برآورد فعالیت‌ها از فایل Excel')
        self.budget_version=tk.StringVar(value='نسخه برآورد: -');ttk.Label(actions,textvariable=self.budget_version,font=('Tahoma',7)).pack(side='left')

        # Compact three-row executive summary. The four per-m² KPIs are all
        # shown explicitly so construction-only and total-cost views are never
        # confused with each other.
        kgrid=ttk.Frame(upper);kgrid.pack(fill='x',pady=(0,1));keys=[
            ('eac','برآورد نهایی پروژه',COLORS['orange']),
            ('cmp','اختلاف با برآورد اولیه',COLORS['blue']),
            ('profit','سود/زیان پیش‌بینی',COLORS['green']),
            ('targetprice','فروش لازم برای سود هدف',COLORS['cyan']),
            ('funding','کسری تأمین مالی',COLORS['red']),
            ('area','متراژ لازم پیش‌فروش',COLORS['orange']),
            ('m2_build_gross','ساخت/متر غیرمفید',COLORS['blue']),
            ('m2_build_saleable','ساخت/متر مفید',COLORS['cyan']),
            ('m2_total_gross','تمام‌شده/متر غیرمفید',COLORS['orange']),
            ('m2_total_saleable','تمام‌شده/متر مفید',COLORS['green']),
        ];self.report_cards={}
        for i,(k,t,c) in enumerate(keys):
            card=CompactKPI(kgrid,t,c);card.grid(row=i//5,column=i%5,sticky='nsew',padx=1,pady=1);kgrid.columnconfigure(i%5,weight=1);self.report_cards[k]=card

        self.phase_table=SmartTable(lower,[('phase','فاز',220),('estimate','برآورد',130),('actual','واقعی تا امروز',130),('forecast','پیش‌بینی پایان',130),('variance','انحراف',130)],title='کنترل بودجه بر اساس فاز')
        self.phase_table.pack(fill='both',expand=True,pady=(0,0));self.phase_table.set_edit_handler(lambda r:self.open_phase_detail_row(r));self.phase_table.set_delete_handler(lambda r:self._delete_phase_row(r))
        pbar=ttk.Frame(lower);pbar.pack(fill='x',pady=(1,0))
        badd=ttk.Button(pbar,text='➕ اضافه زیر سطر موجود',command=self.add_phase_after,style='Compact.TButton');badd.pack(side='right');add_tooltip(badd,'یک فاز جدید دقیقاً بعد از فاز انتخاب‌شده ایجاد می‌کند')
        brename=ttk.Button(pbar,text='✏️ ویرایش نام فاز',command=self.rename_phase,style='Compact.TButton');brename.pack(side='right',padx=2);add_tooltip(brename,'فقط نام فاز انتخاب‌شده را تغییر می‌دهد؛ هزینه‌ها و شناسه فاز حفظ می‌شوند')
        bdelete=ttk.Button(pbar,text='🗑 حذف فاز',command=self.delete_phase,style='Compact.TButton');bdelete.pack(side='right',padx=2);add_tooltip(bdelete,'فاز انتخاب‌شده را حذف می‌کند؛ اگر داده وابسته داشته باشد سیستم از حذف ناامن جلوگیری می‌کند')
        hint=ttk.Label(pbar,text='دبل‌کلیک روی فاز = ورود به ریز فعالیت‌ها و اصلاح برآورد',foreground=COLORS['muted'],font=('Tahoma',7));hint.pack(side='left');add_tooltip(hint,'جمع برآورد فاز از فعالیت‌های زیرمجموعه محاسبه می‌شود و مستقیماً قابل تایپ نیست.')
        # Keep enough phase rows visible by default; user can still drag the sash.
        self.after(350,lambda: self._set_report_sash(pane))

    def _set_report_sash(self,pane):
        try:
            total=max(500,pane.winfo_height());pane.sashpos(0,max(145,int(total*0.28)))
        except Exception:pass

    def _build_health(self):
        tab=ttk.Frame(self.notebook,padding=12);self.notebook.add(tab,text='سلامت سیستم');self.health_text=tk.Text(tab,wrap='word',bg='white',fg=COLORS['text']);self.health_text.pack(fill='both',expand=True);ttk.Button(tab,text='بروزرسانی وضعیت',command=self.refresh_health).pack(pady=6)

    # ---------- refresh ----------
    def _periodic(self):
        try:self.refresh_overview()
        finally:self.after(15000,self._periodic)
    def refresh_all(self):
        self.refresh_overview();self.refresh_manager();self.refresh_financial();self.refresh_cheques();self.refresh_sales();self.refresh_reconciliation();self.refresh_reports();self.refresh_health()
    def refresh_overview(self):
        o=SERVICE.overview();flows=SERVICE.financial_flow_totals();p=SERVICE.project.get_project();ch=SERVICE.cheque_30d_summary();chall=SERVICE.cheque_total_summary();sales=SERVICE.sales_30d_summary();loans=SERVICE.loans_30d_summary();liq=SERVICE.liquidity_30d_summary()
        self.project_name_top.set(p.get('name') or 'پروژه بدون نام')
        self.project_info.set(
            f"{p.get('name') or 'نام پروژه ثبت نشده'}  |  {p.get('address') or 'آدرس ثبت نشده'}\n"
            f"کدپستی: {p.get('postal_code') or '-'}   |   پلاک ثبتی: {p.get('registration_plate') or '-'}   |   پرونده شهرداری: {p.get('municipal_file_no') or '-'}"
        )
        vals={
            'cost':o.construction_cost,'cash':o.cash_balance,'free':o.free_cash_after_cheques,'total_in':flows['total_in'],'total_out':flows['total_out'],
            'liq_obligation':liq['obligations'],'liq_inflow':liq['expected_inflows'],'liq_projected':liq['projected_balance'],
            'ch_all_total':chall['amount'],'ch_open_total':o.open_cheque_commitments,'ch30_count':ch['count'],'ch30_amount':ch['amount'],
            'sales_contract':sales['contract_sales'],'sales_received':sales['cash_received'],'sales_receivable':sales['receivable'],'sales_30':sales['upcoming_amount'],'sales_overdue':sales['overdue_amount'],
            'loan_principal':loans['principal'],'loan_paid':loans['paid'],'loan_remaining':loans['remaining'],'loan_30':loans['upcoming_amount'],
        }
        for k,v in vals.items():
            if k=='ch30_count':self.cards[k].var.set(f"{int(v):,} فقره")
            else:self.cards[k].var.set(money(v))
        # Meaningful dashboard colors: deficit/debt red, surplus green.
        self.cards['liq_projected'].value_label.configure(fg=COLORS['green'] if int(vals['liq_projected'])>=0 else COLORS['red'])
        self.cards['cash'].value_label.configure(fg=COLORS['green'] if int(vals['cash'])>=0 else COLORS['red'])
        self.cards['free'].value_label.configure(fg=COLORS['green'] if int(vals['free'])>=0 else COLORS['red'])
        self.cards['sales_overdue'].value_label.configure(fg=COLORS['red'] if int(vals['sales_overdue'])>0 else COLORS['green'])
        self.cards['loan_remaining'].value_label.configure(fg=COLORS['red'] if int(vals['loan_remaining'])>0 else COLORS['green'])
        self.overview_cheque_table.set_rows([[r.get('due_date_shamsi') or '-',f"{r.get('days_to_due',0)} روز",money(r.get('amount')),r.get('issuer_name') or '-',r.get('issuer_bank') or '-',r.get('receiver_name') or '-'] for r in ch['rows']])
        self.overview_sales_upcoming.set_rows([[r.get('buyer_name') or '-',r.get('display_unit_id') or r.get('unit_number') or '-',r.get('due_date_shamsi') or '-',money(r.get('outstanding')),f"{r.get('days_to_due',0)}"] for r in sales['upcoming_rows']])
        self.overview_sales_overdue.set_rows([[r.get('buyer_name') or '-',r.get('display_unit_id') or r.get('unit_number') or '-',r.get('due_date_shamsi') or '-',money(r.get('outstanding')),f"{r.get('days_overdue',0)}"] for r in sales['overdue_rows']])
        self.overview_loan_table.set_rows([[
            r.get('lender_name') or '-',
            r.get('loan_title') or r.get('contract_number') or r.get('loan_type') or 'وام',
            r.get('installment_number') or '-',
            r.get('due_date_shamsi') or '-',
            money(r.get('outstanding')),
            f"{r.get('days_to_due',0)} روز"
        ] for r in loans['upcoming_rows']])
        try:self.bank_date.set(gregorian_to_shamsi(__import__('datetime').date.today())) if not self.bank_date.get() else None
        except Exception:pass
        self.bank_info.set('آخرین تطبیق: ثبت نشده' if o.bank_balance is None else f"آخرین تطبیق {o.bank_reconciled_shamsi}: بانک {money(o.bank_balance)} | اختلاف {money(o.bank_difference)}")
        if o.bank_difference is None:self.bank_info_label.configure(fg=COLORS['text'])
        elif int(o.bank_difference)>0:self.bank_info_label.configure(fg=COLORS['green'])
        elif int(o.bank_difference)<0:self.bank_info_label.configure(fg=COLORS['red'])
        else:self.bank_info_label.configure(fg=COLORS['blue'])

    def refresh_manager(self):
        try:
            if not self.mgr_start.get() or not self.mgr_end.get():
                a,b=SERVICE.manager_activity_bounds();self.mgr_start.set(a);self.mgr_end.set(b)
            m=SERVICE.manager_summary_shamsi(self.mgr_start.get(),self.mgr_end.get())
            self.manager_metrics['days'].set(m.signed_days,lambda v:f'{int(v):+,} روز')
            self.manager_metrics['avg'].set(m.signed_average,lambda v:f'{int(v):+,} تومان')
            self.manager_metrics['tm'].set(m.toman_month,lambda v:f'{int(v):+,} تومان‌ماه')
            self.manager_metrics['fee'].set(m.manager_fee,lambda v:f'{int(v):+,} تومان')
            self.manager_metrics['withdraw'].set(m.withdrawals_signed,lambda v:f'{int(v):+,} تومان')
            self.manager_metrics['balance'].set(m.balance,lambda v:f'{int(v):+,} تومان')
            with DB.read() as con:
                rows=[dict(r) for r in con.execute("""SELECT transaction_id,shamsi_date,amount,description FROM transactions
                    WHERE category='CONTRACTOR_FEE' AND direction='OUT' AND status='POSTED' AND deleted_at IS NULL
                    ORDER BY event_date DESC,created_at DESC""").fetchall()]
            for r in rows:r['_sum_amount']=int(r.get('amount') or 0)
            self.manager_withdraw_table.set_rows(rows,lambda r:[r.get('shamsi_date') or '-',money(r.get('amount')),r.get('description') or '-',r['transaction_id']])
        except Exception as e:
            # Never leave the manager line visually blank; snapshot values are still authoritative.
            snap=DB.snapshot();fallback={'days':0,'avg':0,'tm':0,'fee':snap.manager_fee_accrued,'withdraw':-snap.manager_withdrawals,'balance':snap.manager_balance}
            self.manager_metrics['days'].set(fallback['days'],lambda v:f'{int(v):+,} روز');self.manager_metrics['avg'].set(fallback['avg'],lambda v:f'{int(v):+,} تومان');self.manager_metrics['tm'].set(fallback['tm'],lambda v:f'{int(v):+,} تومان‌ماه');self.manager_metrics['fee'].set(fallback['fee'],lambda v:f'{int(v):+,} تومان');self.manager_metrics['withdraw'].set(fallback['withdraw'],lambda v:f'{int(v):+,} تومان');self.manager_metrics['balance'].set(fallback['balance'],lambda v:f'{int(v):+,} تومان')
            messagebox.showerror('حساب مدیر',str(e),parent=self)

    def refresh_financial(self):
        tx=SERVICE.list_transactions();self.all_tx_table.set_rows(tx,lambda r:[r.get('shamsi_date') or '-', 'ورودی' if r['direction']=='IN' else 'خروجی',money(r['amount']),r.get('category') or '-',r.get('payer_name') or '-',r.get('receiver_name') or '-',r.get('description') or '-',f"📎 {r.get('receipt_count',0)}",fa_status(r['status']),r['transaction_id']])
        ex=SERVICE.list_construction_expenses();self.exp_table.set_rows(ex,lambda r:[r.get('shamsi_date') or '-',money(r['final_amount']),money(r['paid_amount']),r.get('phase_name') or '⚠️ تعیین نشده',r.get('activity_name_display') or '⚠️ تعیین نشده',r.get('payer_name_display') or '-',r.get('receiver_name_display') or '-',r.get('description') or '-',f"📎 {r.get('receipt_count',0)}",fa_status(r['status']),r['expense_id']])
        ins=SERVICE.list_transactions(direction='IN');self.in_table.set_rows(ins,lambda r:[r.get('shamsi_date') or '-',money(r['amount']),r.get('category') or '-',r.get('payer_name') or '-',r.get('description') or '-',f"📎 {r.get('receipt_count',0)}",r['transaction_id']])
        outs=SERVICE.list_transactions(direction='OUT',nonconstruction_only=True);self.out_table.set_rows(outs,lambda r:[r.get('shamsi_date') or '-',money(r['amount']),r.get('category') or '-',r.get('receiver_name') or '-',r.get('description') or '-',f"📎 {r.get('receipt_count',0)}",r['transaction_id']])
        loans=SERVICE.loans.list_loans();self.loan_table.set_rows(loans,lambda r:[r.get('received_date_shamsi') or '-',r.get('lender_name') or '-',money(r['principal_amount']),money(r.get('net_received_amount')),money(int(r.get('total_interest') or 0)+int(r.get('bank_fees') or 0)),money(r.get('paid_total')),money(r.get('remaining_debt')),f"{r.get('paid_installments',0)}/{r.get('installment_count',0)}",f"{r.get('next_due_shamsi') or '-'} | {money(r.get('next_due_amount'))}",fa_status(r['status']),r['loan_id']])
    def refresh_cheques(self):
        rows=SERVICE.list_cheques(open_only=False)
        for r in rows:r['_sum_amount']=int(r.get('amount') or 0)
        self.cheque_table.set_rows(rows,lambda r:[r.get('issue_date_shamsi') or '-',r.get('due_date_shamsi') or '-',money(r['amount']),r.get('issuer_name') or '-', 'دیجیتال' if str(r.get('cheque_type') or '').upper()=='DIGITAL' else 'فیزیکی',r.get('receiver_name') or '-',r.get('issuer_bank') or '-',r.get('cheque_serial') or '-',r.get('description') or r.get('expense_description') or '-',fa_status(r['status']),r['cheque_id']])

    def refresh_sales(self):
        rows=SERVICE.list_sales_summary();self.sales_table.set_rows(rows,lambda r:[r.get('unit_number') or '-',r.get('buyer_name') or '-',money(r['contract_amount']),money(r['cash_received']),money(r['receivable']),money(r['overdue_amount']),r.get('next_due_shamsi') or '-',fa_status(r['status']),r['sale_id']])
    def refresh_reconciliation(self):
        rows=SERVICE.list_reconciliations();self.rec_table.set_rows(rows,lambda r:[r.get('shamsi_date') or '-',money(r['system_balance']),money(r['bank_balance']),money(r['difference']),r.get('notes') or '-',r.get('reconciliation_id') or '-'])
    def refresh_reports(self):
        st=SERVICE.budget.get_settings();us=UNITS.summary()
        # Unit master is the source for unit count and useful/saleable area when units exist.
        if us['count']>0 and (int(st.get('unit_count') or 0)!=us['count'] or abs(float(st.get('saleable_area') or 0)-float(us['area']))>0.001):
            st=SERVICE.budget.save_settings(unit_count=us['count'],unit_areas=[float(r.get('area') or 0) for r in UNITS.list_units()],saleable_area=float(us['area']))
        mapping={'gross_area':'gross_area','inflation':'monthly_inflation','months':'remaining_months','presale':'presale_price_per_m2','end_price':'end_sale_price_override','misc':'unbudgeted_misc','target':'target_profit_percent'}
        for vk,sk in mapping.items():
            val=st.get(sk)
            if vk in ('presale','end_price','misc'):
                self.report_vars[vk].set('' if val is None else group_int(val,blank_zero=(vk=='end_price')))
            else:self.report_vars[vk].set('' if val is None else str(val or ''))
        self.report_vars['unit_count'].set(str(us['count']))
        self.report_vars['saleable_area'].set(str(us['area']))
        self.unit_summary_var.set(f"واحدها: {us['count']:,} | متراژ مفید از جدول واحدها: {us['area']:,.2f} مترمربع | فروخته‌شده: {us['sold']:,} واحد / {us['sold_area']:,.2f} متر")
        v=SERVICE.budget.latest_version();self.budget_version.set(f"نسخه برآورد: {v.get('version_no')} — {v.get('title')}" if v else 'نسخه برآورد: -')
        f=SERVICE.budget.forecast();diff=f.forecast_total_cost-f.initial_budget
        self.report_cards['eac'].var.set(money(f.forecast_total_cost));self.report_cards['cmp'].var.set(f"{money(diff)} ({(diff/f.initial_budget*100 if f.initial_budget else 0):+.1f}%)")
        self.report_cards['profit'].var.set(f"{money(f.projected_profit)} | {f.projected_profit_percent:+.1f}%");self.report_cards['targetprice'].var.set(f"{money(f.suggested_remaining_sale_price_per_m2)}/متر")
        self.report_cards['funding'].var.set(money(f.funding_gap));self.report_cards['area'].var.set(f"{f.presale_area_needed_m2:,.1f} مترمربع")
        self.report_cards['m2_build_gross'].var.set(f"{money(f.construction_cost_per_gross_m2)}/مترمربع")
        self.report_cards['m2_build_saleable'].var.set(f"{money(f.construction_cost_per_saleable_m2)}/مترمربع")
        self.report_cards['m2_total_gross'].var.set(f"{money(f.total_cost_per_gross_m2)}/مترمربع")
        self.report_cards['m2_total_saleable'].var.set(f"{money(f.total_cost_per_saleable_m2)}/مترمربع")
        rows=SERVICE.budget.phase_summary();self.phase_table.set_rows(rows,lambda r:[r['phase'],money(r['estimate']),money(r['actual']),money(r['forecast']),money(r['variance'])])

    def refresh_health(self):
        h=DB.health_check();o=SERVICE.overview();v=SERVICE.budget.latest_version();p=SERVICE.project.get_project();text=f"SQLite integrity: {h['sqlite_integrity']}\nSchema version: {h['schema_version']}\nDB: {CONFIG.db_path}\nGoogle Sheets: {'فعال' if CONFIG.sheets_enabled else 'خاموش'} — {CONFIG.spreadsheet_name}\nTelegram group: {CONFIG.group_chat_id or '-'}\nSync pending/failed: {o.pending_sync}/{o.failed_sync}\nپروژه: {p.get('name') or '-'}\nنسخه برآورد: {v.get('version_no') if v else '-'}\n\nSQLite مرجع اصلی سیستم است. Google Sheets فقط Mirror است."
        self.health_text.delete('1.0','end');self.health_text.insert('1.0',text)
    def show_health(self):self.refresh_health();self.notebook.select(self.notebook.tabs()[-1])

    def _dashboard_report_rows(self):
        o=SERVICE.overview();flows=SERVICE.financial_flow_totals();p=SERVICE.project.get_project();ch=SERVICE.cheque_30d_summary();chall=SERVICE.cheque_total_summary();sales=SERVICE.sales_30d_summary();loans=SERVICE.loans_30d_summary();liq=SERVICE.liquidity_30d_summary()
        rows=[]
        def add(section,item,value,detail=''):
            rows.append([section,item,value,detail])
        add('مشخصات پروژه','نام پروژه',p.get('name') or '-')
        add('مشخصات پروژه','آدرس',p.get('address') or '-')
        add('مشخصات پروژه','کدپستی',p.get('postal_code') or '-')
        add('مشخصات پروژه','پلاک ثبتی',p.get('registration_plate') or '-')
        add('مشخصات پروژه','شماره پرونده شهرداری',p.get('municipal_file_no') or '-')
        add('گزارش مالی','هزینه ساخت',money(o.construction_cost))
        add('گزارش مالی','مانده تنخواه',money(o.cash_balance))
        add('گزارش مالی','مانده آزاد پس از چک',money(o.free_cash_after_cheques))
        add('گزارش مالی','مجموع ورودی',money(flows['total_in']))
        add('گزارش مالی','مجموع خروجی',money(flows['total_out']))
        add('گزارش مالی','تعهدات ۳۰ روز آینده',money(liq['obligations']))
        add('گزارش مالی','وصول برنامه‌ریزی‌شده ۳۰ روز آینده',money(liq['expected_inflows']))
        add('گزارش مالی','کسری/مازاد نقدینگی تا ۳۰ روز آینده',money(liq['projected_balance']))
        add('چک‌ها','مجموع کل چک‌های ثبت‌شده',money(chall['amount']))
        add('چک‌ها','مجموع چک‌های پاس‌نشده',money(o.open_cheque_commitments))
        add('چک‌ها','جمع چک‌های ۳۰ روز آینده',money(ch['amount']))
        for r in ch['rows']:
            add('ریز چک ۳۰ روزه',r.get('receiver_name') or '-',money(r.get('amount')),f"سررسید {r.get('due_date_shamsi') or '-'} | {r.get('days_to_due',0)} روز | صاحب حساب {r.get('issuer_name') or '-'} | بانک {r.get('issuer_bank') or '-'}")
        add('فروش','کل قرارداد خریداران',money(sales['contract_sales']))
        add('فروش','وصول خریداران',money(sales['cash_received']))
        add('فروش','کل طلب از خریداران',money(sales['receivable']))
        add('فروش','طلب ۳۰ روز آینده',money(sales['upcoming_amount']))
        add('فروش','مطالبات معوق',money(sales['overdue_amount']))
        for r in sales['upcoming_rows']:
            add('ریز وصول ۳۰ روزه',r.get('buyer_name') or '-',money(r.get('outstanding')),f"واحد {r.get('display_unit_id') or r.get('unit_number') or '-'} | سررسید {r.get('due_date_shamsi') or '-'}")
        for r in sales['overdue_rows']:
            add('ریز مطالبات معوق',r.get('buyer_name') or '-',money(r.get('outstanding')),f"واحد {r.get('display_unit_id') or r.get('unit_number') or '-'} | {r.get('days_overdue',0)} روز تأخیر")
        add('وام‌ها','کل تسهیلات دریافتی',money(loans['principal']))
        add('وام‌ها','جمع اقساط واریزی',money(loans['paid']))
        add('وام‌ها','مانده بدهی وام‌ها',money(loans['remaining']))
        add('وام‌ها','اقساط ۳۰ روز آینده',money(loans['upcoming_amount']))
        for r in loans['upcoming_rows']:
            add('ریز اقساط وام ۳۰ روزه',r.get('lender_name') or '-',money(r.get('outstanding')),f"{r.get('loan_title') or r.get('contract_number') or r.get('loan_type') or 'وام'} | قسط {r.get('installment_number') or '-'} | {r.get('due_date_shamsi') or '-'}")
        if o.bank_balance is not None:
            add('تطبیق بانک','موجودی واقعی بانک',money(o.bank_balance),f"تاریخ {o.bank_reconciled_shamsi}")
            add('تطبیق بانک','اختلاف بانک با سیستم',money(o.bank_difference))
        return ['بخش','عنوان','مقدار','جزئیات'],rows

    def _save_dashboard_report(self, kind:str, do_print:bool=False):
        headers,rows=self._dashboard_report_rows()
        if do_print:
            fd,path=tempfile.mkstemp(suffix='.pdf');os.close(fd);export_pdf(path,headers,rows,title='داشبورد مدیریتی پروژه');print_file(path);return
        ext='.xlsx' if kind=='xlsx' else '.pdf'
        path=filedialog.asksaveasfilename(defaultextension=ext,filetypes=[('Excel','*.xlsx')] if kind=='xlsx' else [('PDF','*.pdf')])
        if not path:return
        if kind=='xlsx':export_xlsx(path,headers,rows,title='داشبورد مدیریتی پروژه')
        else:export_pdf(path,headers,rows,title='داشبورد مدیریتی پروژه')
        messagebox.showinfo('خروجی',f'فایل ساخته شد:\n{path}',parent=self)

    def export_dashboard_excel(self):self._save_dashboard_report('xlsx')
    def export_dashboard_pdf(self):self._save_dashboard_report('pdf')
    def print_dashboard(self):self._save_dashboard_report('pdf',do_print=True)

    def import_old_telegram_history(self):
        path=filedialog.askopenfilename(title='انتخاب JSON خروجی Telegram Desktop',filetypes=[('Telegram JSON','*.json'),('JSON','*.json')])
        if not path:return
        if not messagebox.askyesno('Import تاریخچه قدیمی',
            'پیام‌های مالی فایل با تاریخ اصلی وارد صف بررسی می‌شوند و هیچ اثر مالی خودکار ندارند.\n\nادامه دهیم؟',parent=self):return
        try:
            result=import_telegram_export(DB,path)
            messagebox.showinfo('Import انجام شد',
                f"چت‌ها: {result.chats:,}\nپیام‌های بررسی‌شده: {result.scanned:,}\nکاندید مالی: {result.candidates:,}\nپیش‌نویس جدید: {result.created:,}\nتکراری: {result.duplicates:,}\nنادیده‌گرفته‌شده: {result.skipped:,}\n\nبرای بررسی و تأیید در خصوصی ربات دستور /historypending را بزن.",parent=self)
            self.refresh_health()
        except Exception as e:messagebox.showerror('Import تاریخچه',str(e),parent=self)

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
    def _delete_tx_row(self,r):
        if not r:return
        if not messagebox.askyesno('حذف','ثبت انتخاب‌شده Soft Delete شود؟',parent=self):return
        try:
            if r.get('pending_id'):SERVICE.delete_posting(r['pending_id'])
            else:SERVICE.delete_manual_transaction(r['transaction_id'])
            self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

    def _delete_expense_row(self,r):
        if not r:return
        if not r.get('pending_id'):
            messagebox.showwarning('حذف','این هزینه Posting متصل ندارد و از این مسیر حذف نمی‌شود.',parent=self);return
        if not messagebox.askyesno('حذف','هزینه و اثر مالی آن Soft Delete شود؟',parent=self):return
        try:SERVICE.delete_posting(r['pending_id']);self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

    def _cancel_loan_row(self,r):
        if r and messagebox.askyesno('لغو وام','وام انتخاب‌شده لغو شود؟ تراکنش‌های قبلی حذف نمی‌شوند.',parent=self):
            try:SERVICE.loans.cancel_loan(r['loan_id']);self.refresh_all()
            except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

    def _cancel_cheque_row(self,r):
        if not r:return
        if not messagebox.askyesno('لغو چک','چک انتخاب‌شده لغو شود؟ هزینه اصلی حذف نمی‌شود.',parent=self):return
        try:DB.cancel_cheque(r['cheque_id'],source='GUI',actor_id='GUI');self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

    def _cancel_sale_row(self,r):
        if not r:return
        if not messagebox.askyesno('لغو قرارداد',f"قرارداد فروش واحد {r.get('unit_number') or '-'} لغو شود؟",parent=self):return
        try:SERVICE.revenue.cancel_sale(r['sale_id']);self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

    def _delete_rec_row(self,r):
        if r and messagebox.askyesno('حذف تطبیق','این رکورد تطبیق بانک Soft Delete شود؟',parent=self):
            try:SERVICE.delete_reconciliation(r['reconciliation_id']);self.refresh_all()
            except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

    def _delete_phase_row(self,r):
        if not r or r.get('phase_id')=='UNCLASSIFIED':return
        if not messagebox.askyesno('حذف فاز',f"فاز «{r.get('phase')}» حذف شود؟",parent=self):return
        try:SERVICE.budget.delete_phase(r['phase_id']);self.refresh_reports()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

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
            units=UNITS.list_units();areas=[float(r.get('area') or 0) for r in units];saleable=sum(areas)
            SERVICE.budget.save_settings(
                gross_area=float(str(self.report_vars['gross_area'].get()).replace(',','') or 0),
                saleable_area=saleable,
                unit_count=len(units),
                unit_areas=areas,
                monthly_inflation=float(str(self.report_vars['inflation'].get()).replace(',','') or 0),
                remaining_months=int(float(str(self.report_vars['months'].get()).replace(',','') or 0)),
                presale_price_per_m2=parse_int(self.report_vars['presale'].get()),
                end_sale_price_override=(parse_int(self.report_vars['end_price'].get()) if self.report_vars['end_price'].get().strip() else None),
                unbudgeted_misc=parse_int(self.report_vars['misc'].get()),
                target_profit_percent=float(str(self.report_vars['target'].get()).replace(',','') or 0),
            );self.refresh_reports();messagebox.showinfo('ذخیره شد','پارامترهای گزارش‌گیری ذخیره شدند. تعداد و متراژ واحدها از جدول واحدها خوانده شد.')
        except Exception as e:messagebox.showerror('خطا',str(e))

    def import_budget(self):
        path=filedialog.askopenfilename(filetypes=[('Excel','*.xlsx')]);
        if not path:return
        title=simpledialog.askstring('عنوان نسخه','عنوان این نسخه برآورد:',parent=self) or ''
        try:r=SERVICE.budget.import_budget_xlsx(path,title);self.refresh_reports();messagebox.showinfo('برآورد بارگذاری شد',f"نسخه {r['version_no']} | جمع برآورد فایل: {money(r['total_estimate'])}")
        except Exception as e:messagebox.showerror('خطا',str(e))
    def edit_transaction_row(self,r):
        if r.get('pending_id'):
            p=DB.get_pending_item(r['pending_id']);PostingEditDialog(self,r['pending_id'],dict(p['payload']) if p else {},lambda changes:self._save_posting_edit(r['pending_id'],changes));return
        TransactionEditDialog(self,r,lambda changes:self._save_tx_edit(r['transaction_id'],changes))
    def edit_expense_row(self,r):
        if not r.get('pending_id'):
            ExpenseClassifyDialog(self,r,lambda p,a,py,rc:self._save_classification(r['expense_id'],p,a,py,rc));return
        p=DB.get_pending_item(r['pending_id']);PostingEditDialog(self,r['pending_id'],dict(p['payload']) if p else {},lambda changes:self._save_posting_edit(r['pending_id'],changes))
    def edit_loan_row(self,r):LoanEditDialog(self,r,self.refresh_all)
    def edit_cheque(self):
        r=self._one(self.cheque_table)
        if r:self.edit_cheque_row(r)
    def edit_cheque_row(self,r):ChequeEditDialog(self,r,self.refresh_all)
    def open_phase_detail(self,event=None):
        r=self._one(self.phase_table)
        if r:self.open_phase_detail_row(r)
    def open_phase_detail_row(self,r):
        if r.get('phase_id')=='UNCLASSIFIED':return
        PhaseDetailDialog(self,r.get('phase_id'),r.get('phase'),self.refresh_reports)
    def add_phase_after(self):
        rows=self.phase_table.selected_rows();after=rows[0].get('phase_id') if rows else None
        name=simpledialog.askstring('فاز جدید','نام فاز جدید:',parent=self)
        if not name:return
        try:SERVICE.budget.add_phase_after(after,name);self.refresh_reports()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def rename_phase(self):
        r=self._one(self.phase_table)
        if not r or r.get('phase_id')=='UNCLASSIFIED':return
        name=simpledialog.askstring('ویرایش نام فاز','نام جدید:',initialvalue=r.get('phase'),parent=self)
        if not name:return
        try:SERVICE.budget.rename_phase(r['phase_id'],name);self.refresh_reports()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def delete_phase(self):
        r=self._one(self.phase_table)
        if not r or r.get('phase_id')=='UNCLASSIFIED':return
        if not messagebox.askyesno('حذف فاز',f"فاز «{r.get('phase')}» حذف شود؟",parent=self):return
        try:SERVICE.budget.delete_phase(r['phase_id']);self.refresh_reports()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def edit_sale(self):
        r=self._one(self.sales_table)
        if r:self.edit_sale_row(r)
    def edit_sale_row(self,r):SaleEditDialog(self,r,self.refresh_all)
    def sale_installments(self):
        r=self._one(self.sales_table)
        if r:SaleInstallmentsDialog(self,r['sale_id'],self.refresh_all)
    def cancel_sale(self):
        r=self._one(self.sales_table)
        if not r:return
        if not messagebox.askyesno('لغو قرارداد',f"قرارداد فروش واحد {r.get('unit_number') or '-'} لغو شود؟",parent=self):return
        try:SERVICE.revenue.cancel_sale(r['sale_id']);self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def edit_reconciliation(self):
        r=self._one(self.rec_table)
        if r:self.edit_reconciliation_row(r)
    def edit_reconciliation_row(self,r):ReconciliationEditDialog(self,r,self.refresh_all)
    def delete_reconciliation(self):
        r=self._one(self.rec_table)
        if not r:return
        if not messagebox.askyesno('حذف تطبیق','این رکورد تطبیق بانک Soft Delete شود؟',parent=self):return
        try:SERVICE.delete_reconciliation(r['reconciliation_id']);self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def open_units(self):UnitMasterDialog(self,self.refresh_all)
    def open_search(self):SearchWindow(self)
    def open_project(self):ProjectDialog(self,self.refresh_all)


class PostingEditDialog(tk.Toplevel):
    def __init__(self,parent,pid,payload,on_save):
        super().__init__(parent);self.title('ویرایش ثبت مالی');self.transient(parent);self.grab_set();self.on_save=on_save;self.vars={};self.orig={}
        fields=[('event_date_shamsi','تاریخ شمسی'),('amount','مبلغ'),('final_amount','مبلغ نهایی'),('invoice_amount','مبلغ فاکتور'),('paid_amount','پرداخت‌شده'),('description','شرح'),('expense_category','دسته'),('payment_method','روش پرداخت'),('due_date_shamsi','سررسید چک'),('issuer_name','صادرکننده چک'),('issuer_bank','بانک چک'),('cheque_serial','شماره/صیادی چک'),('cheque_type','نوع چک')]
        ttk.Label(self,text=f'Posting: {pid}',font=('Tahoma',10,'bold')).grid(row=0,column=0,columnspan=2,padx=10,pady=8)
        nums={'amount','final_amount','invoice_amount','paid_amount'}
        for i,(k,l) in enumerate(fields,1):
            val=payload.get(k)
            if k in nums and val not in (None,''):v=group_int(val)
            elif k=='cheque_type':v=str(val or 'PHYSICAL').upper()
            else:v=str(val if val is not None else '')
            self.orig[k]=v;self.vars[k]=tk.StringVar(value=v);ttk.Label(self,text=l+':').grid(row=i,column=1,sticky='e',padx=5,pady=3)
            if k in ('due_date_shamsi','event_date_shamsi'):w=DateField(self,self.vars[k],width=34);w.grid(row=i,column=0,padx=5,pady=3,sticky='ew')
            elif k=='cheque_type':w=ttk.Combobox(self,textvariable=self.vars[k],values=['PHYSICAL','DIGITAL'],state='readonly',width=36);w.grid(row=i,column=0,padx=5,pady=3)
            else:
                e=ttk.Entry(self,textvariable=self.vars[k],width=38,justify='right');e.grid(row=i,column=0,padx=5,pady=3)
                if k in nums:bind_grouped_number(e,self.vars[k])
        ttk.Button(self,text='ذخیره',command=self.save,style='Primary.TButton').grid(row=len(fields)+1,column=0,columnspan=2,pady=10)
        bind_enter_action(self,self.save)
    def save(self):
        ch={};nums={'amount','final_amount','invoice_amount','paid_amount'}
        for k,v in self.vars.items():
            val=v.get().strip()
            if val==self.orig[k]:continue
            ch[k]=parse_int(val) if k in nums else val
        if ch:self.destroy();self.on_save(ch)


class TransactionEditDialog(tk.Toplevel):
    def __init__(self,parent,row,on_save):
        super().__init__(parent);self.title('ویرایش تراکنش');self.transient(parent);self.grab_set();self.on_save=on_save
        vals={'amount':group_int(row.get('amount') or 0),'shamsi_date':row.get('shamsi_date') or '','payer_name':row.get('payer_name') or '','receiver_name':row.get('receiver_name') or '','description':row.get('description') or ''};self.vars={k:tk.StringVar(value=v) for k,v in vals.items()}
        fields=[('amount','مبلغ'),('shamsi_date','تاریخ شمسی'),('payer_name','واریزکننده'),('receiver_name','دریافت‌کننده'),('description','شرح')]
        for i,(k,l) in enumerate(fields):
            ttk.Label(self,text=l+':').grid(row=i,column=1,sticky='e',padx=6,pady=4)
            if k=='shamsi_date':DateField(self,self.vars[k],width=37).grid(row=i,column=0,padx=6,pady=4,sticky='ew')
            else:
                e=ttk.Entry(self,textvariable=self.vars[k],width=42,justify='right');e.grid(row=i,column=0,padx=6,pady=4)
                if k=='amount':bind_grouped_number(e,self.vars[k])
        ttk.Button(self,text='ذخیره',command=self.save,style='Primary.TButton').grid(row=6,column=0,columnspan=2,pady=10)
        bind_enter_action(self,self.save)
    def save(self):
        try:d={k:v.get().strip() for k,v in self.vars.items()};d['amount']=parse_int(d['amount']);self.destroy();self.on_save(d)
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)


class ExpenseClassifyDialog(tk.Toplevel):
    def __init__(self,parent,row,on_save):
        super().__init__(parent);self.title('مرحله ساخت و نوع هزینه');self.transient(parent);self.grab_set();self.on_save=on_save;self.phases=SERVICE.budget.list_phases();self.phase_map={p['name']:p['phase_id'] for p in self.phases};self.pv=tk.StringVar(value=row.get('phase_name') or '');self.av=tk.StringVar(value=row.get('activity_name_display') or '');self.py=tk.StringVar(value=row.get('payer_name_display') or '');self.rc=tk.StringVar(value=row.get('receiver_name_display') or '')
        ttk.Label(self,text='مرحله ساخت:').grid(row=0,column=1,sticky='e',padx=6,pady=5);self.pc=ttk.Combobox(self,textvariable=self.pv,values=list(self.phase_map),state='readonly',width=42);self.pc.grid(row=0,column=0,padx=6,pady=5);self.pc.bind('<<ComboboxSelected>>',lambda e:self.load_acts())
        ttk.Label(self,text='نوع هزینه/فعالیت:').grid(row=1,column=1,sticky='e',padx=6,pady=5);self.ac=ttk.Combobox(self,textvariable=self.av,state='readonly',width=42);self.ac.grid(row=1,column=0,padx=6,pady=5)
        for i,(v,l) in enumerate([(self.py,'نام واریزکننده'),(self.rc,'نام دریافت‌کننده')],2):ttk.Label(self,text=l+':').grid(row=i,column=1,sticky='e',padx=6,pady=5);ttk.Entry(self,textvariable=v,width=44,justify='right').grid(row=i,column=0,padx=6,pady=5)
        self.load_acts();ttk.Button(self,text='ذخیره دسته‌بندی',command=self.save,style='Primary.TButton').grid(row=5,column=0,columnspan=2,pady=10)
        bind_enter_action(self,self.save)
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
        super().__init__(parent);self.title('ثبت وام جدید');self.transient(parent);self.grab_set();self.on_save=on_save;keys=[('lender_name','بانک/وام‌دهنده'),('principal_amount','اصل وام'),('net_received_amount','مبلغ واقعی واریزی'),('received_date_shamsi','تاریخ دریافت'),('interest_rate','نرخ سود %'),('total_interest','کل سود'),('bank_fees','کارمزد'),('installment_count','تعداد اقساط'),('installment_amount','مبلغ هر قسط'),('first_due_date_shamsi','تاریخ اولین قسط'),('guarantors','ضامنین'),('collateral','وثیقه'),('contract_number','شماره قرارداد'),('description','توضیحات')];self.vars={k:tk.StringVar() for k,_ in keys};nums={'principal_amount','net_received_amount','total_interest','bank_fees','installment_count','installment_amount'}
        for i,(k,l) in enumerate(keys):
            ttk.Label(self,text=l+':').grid(row=i,column=1,sticky='e',padx=6,pady=3)
            if k in ('received_date_shamsi','first_due_date_shamsi'):DateField(self,self.vars[k],width=37).grid(row=i,column=0,padx=6,pady=3,sticky='ew')
            else:
                e=ttk.Entry(self,textvariable=self.vars[k],width=42,justify='right');e.grid(row=i,column=0,padx=6,pady=3)
                if k in nums:bind_grouped_number(e,self.vars[k])
        ttk.Button(self,text='ثبت وام + ورودی تنخواه',command=self.save,style='Primary.TButton').grid(row=len(keys)+1,column=0,columnspan=2,pady=10)
        bind_enter_action(self,self.save)
    def save(self):
        try:
            d={k:v.get().strip() for k,v in self.vars.items()}
            for k in ['principal_amount','net_received_amount','total_interest','bank_fees','installment_count','installment_amount']:d[k]=parse_int(d[k])
            d['interest_rate']=float(str(d['interest_rate']).replace(',','.') or 0);d['loan_type']='BANK';self.destroy();self.on_save(d)
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)


class LoanInstallmentDialog(tk.Toplevel):
    def __init__(self,parent,loan_id,on_refresh):
        super().__init__(parent);self.title('اقساط وام');self.geometry('1000x580');self.transient(parent);self.loan_id=loan_id;self.on_refresh=on_refresh
        self.table=SmartTable(self,[('no','قسط',65),('due','سررسید',105),('amount','مبلغ',130),('paid','پرداخت‌شده',130),('principal','اصل',125),('interest','سود/کارمزد',125),('status','وضعیت',105),('id','Installment ID',155)],title='اقساط وام')
        self.table.pack(fill='both',expand=True,padx=8,pady=8);self.table.set_delete_handler(self._delete_row)
        bar=ttk.Frame(self);bar.pack(fill='x',padx=8,pady=(0,8));ttk.Button(bar,text='💸 ثبت پرداخت قسط',command=self.pay,style='Primary.TButton').pack(side='right');ttk.Label(bar,text='قسط پرداخت‌شده قابل حذف نیست.',foreground=COLORS['muted']).pack(side='left');self.refresh()
    def refresh(self):
        self.rows=SERVICE.loans.list_installments(self.loan_id)
        for r in self.rows:r['_sum_amount']=max(0,int(r.get('amount') or 0)-int(r.get('paid_amount') or 0))
        self.table.set_rows(self.rows,lambda r:[r['installment_number'],r.get('due_date_shamsi') or '-',money(r['amount']),money(r['paid_amount']),money(r['principal_component']),money(r['interest_component']),fa_status(r['status']),r['loan_installment_id']])
    def pay(self):
        rows=self.table.selected_rows()
        if not rows:return
        r=rows[0];remain=int(r['amount'])-int(r['paid_amount'])
        if remain<=0:messagebox.showinfo('قسط','این قسط تسویه شده است.',parent=self);return
        PaymentDateDialog(self,remain,lambda amount,sh:self._do_pay(r,amount,sh))
    def _delete_row(self,r):
        if not r:return
        if not messagebox.askyesno('حذف قسط',f"قسط {r.get('installment_number')} حذف/لغو شود؟",parent=self):return
        try:SERVICE.loans.cancel_installment(r['loan_installment_id']);self.refresh();self.on_refresh()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def _do_pay(self,r,amount,sh):
        try:SERVICE.loans.pay_installment(r['loan_installment_id'],amount=amount,paid_date_shamsi=sh);self.refresh();self.on_refresh()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)


class ProjectDialog(tk.Toplevel):
    def __init__(self,parent,on_refresh):
        super().__init__(parent);self.title('مشخصات پروژه و آرشیو اسناد');self.geometry('1050x690');self.transient(parent);self.grab_set();self.on_refresh=on_refresh;p=SERVICE.project.get_project();self.vars={k:tk.StringVar(value=p.get(k) or '') for k in ['name','address','postal_code','registration_plate','municipal_file_no','description']}
        form=ttk.LabelFrame(self,text='مشخصات پروژه',padding=8);form.pack(fill='x',padx=8,pady=8)
        fields=[('name','نام پروژه'),('address','آدرس'),('postal_code','کد پستی'),('registration_plate','پلاک ثبتی'),('municipal_file_no','شماره پرونده شهرداری'),('description','توضیحات')]
        for i,(k,l) in enumerate(fields):ttk.Label(form,text=l+':').grid(row=i//2,column=(i%2)*2+1,sticky='e',padx=4,pady=3);ttk.Entry(form,textvariable=self.vars[k],width=45,justify='right').grid(row=i//2,column=(i%2)*2,padx=4,pady=3)
        savebtn=ttk.Button(form,text='💾 ذخیره مشخصات',command=self.save,style='Primary.TButton');savebtn.grid(row=3,column=0,columnspan=4,pady=5);add_tooltip(savebtn,'ذخیره مشخصات پایه پروژه در SQLite')
        bind_enter_action(self,self.save)
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

class PaymentDateDialog(tk.Toplevel):
    def __init__(self,parent,max_amount,on_save):
        super().__init__(parent);self.title('ثبت پرداخت');self.transient(parent);self.grab_set();self.on_save=on_save;self.max_amount=int(max_amount)
        self.amount=tk.StringVar(value=group_int(max_amount));self.date=tk.StringVar(value=gregorian_to_shamsi(__import__('datetime').date.today()))
        ttk.Label(self,text='مبلغ پرداخت:').grid(row=0,column=1,sticky='e',padx=6,pady=6);e=ttk.Entry(self,textvariable=self.amount,width=28,justify='right');e.grid(row=0,column=0,padx=6,pady=6);bind_grouped_number(e,self.amount)
        ttk.Label(self,text='تاریخ شمسی:').grid(row=1,column=1,sticky='e',padx=6,pady=6);DateField(self,self.date,width=24).grid(row=1,column=0,padx=6,pady=6,sticky='ew')
        ttk.Button(self,text='ثبت',command=self.save,style='Primary.TButton').grid(row=2,column=0,columnspan=2,pady=8)
        bind_enter_action(self,self.save)
    def save(self):
        try:
            a=parse_int(self.amount.get());sh=normalize_shamsi(self.date.get())
            if a<=0 or a>self.max_amount:raise ValueError('مبلغ پرداخت نامعتبر است.')
            if not sh:raise ValueError('تاریخ شمسی نامعتبر است.')
            self.destroy();self.on_save(a,sh)
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)


class EstimateEditDialog(tk.Toplevel):
    def __init__(self,parent,row,on_save):
        super().__init__(parent);self.title('اصلاح برآورد فعالیت');self.transient(parent);self.grab_set();self.on_save=on_save;self.amount=tk.StringVar(value=group_int(row.get('estimate') or 0))
        ttk.Label(self,text=f"{row.get('phase')} ← {row.get('activity')}",font=('Tahoma',10,'bold')).pack(padx=12,pady=(12,6))
        line=ttk.Frame(self);line.pack(padx=12,pady=6);ttk.Label(line,text='برآورد (تومان):').pack(side='right');e=ttk.Entry(line,textvariable=self.amount,width=26,justify='right');e.pack(side='right',padx=6);bind_grouped_number(e,self.amount);e.focus_set();e.select_range(0,'end')
        ttk.Button(self,text='ذخیره',command=self.save,style='Primary.TButton').pack(pady=(4,12))
        bind_enter_action(self,self.save)
    def save(self):
        try:a=parse_int(self.amount.get());self.destroy();self.on_save(a)
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)


class ChequeEditDialog(tk.Toplevel):
    def __init__(self,parent,row,on_refresh):
        super().__init__(parent);self.title('ویرایش مشخصات چک');self.transient(parent);self.grab_set();self.row=row;self.on_refresh=on_refresh
        self.vars={
            'amount':tk.StringVar(value=group_int(row.get('amount') or 0)),
            'issue':tk.StringVar(value=row.get('issue_date_shamsi') or ''),
            'due':tk.StringVar(value=row.get('due_date_shamsi') or ''),
            'issuer_name':tk.StringVar(value=row.get('issuer_name') or ''),
            'cheque_type':tk.StringVar(value='دیجیتال' if str(row.get('cheque_type') or '').upper()=='DIGITAL' else 'فیزیکی'),
            'receiver_name':tk.StringVar(value=row.get('receiver_name') or ''),
            'issuer_bank':tk.StringVar(value=row.get('issuer_bank') or ''),
            'cheque_serial':tk.StringVar(value=row.get('cheque_serial') or ''),
            'description':tk.StringVar(value=row.get('description') or row.get('expense_description') or ''),
        }
        fields=[('amount','مبلغ'),('issue','تاریخ صدور'),('due','سررسید شمسی'),('issuer_name','صادرکننده چک'),('cheque_type','نوع چک'),('receiver_name','دریافت‌کننده'),('issuer_bank','بانک'),('cheque_serial','شماره/شناسه صیادی'),('description','بابت/شرح')]
        for i,(k,l) in enumerate(fields):
            ttk.Label(self,text=l+':').grid(row=i,column=1,sticky='e',padx=6,pady=4)
            if k in ('issue','due'):DateField(self,self.vars[k],width=35).grid(row=i,column=0,padx=6,pady=4,sticky='ew')
            elif k=='cheque_type':ttk.Combobox(self,textvariable=self.vars[k],values=['فیزیکی','دیجیتال'],state='readonly',width=37).grid(row=i,column=0,padx=6,pady=4)
            else:
                e=ttk.Entry(self,textvariable=self.vars[k],width=42,justify='right');e.grid(row=i,column=0,padx=6,pady=4)
                if k=='amount':bind_grouped_number(e,self.vars[k])
        ttk.Button(self,text='ذخیره',command=self.save,style='Primary.TButton').grid(row=len(fields)+1,column=0,columnspan=2,pady=10)
        bind_enter_action(self,self.save)
    def save(self):
        try:
            ish=normalize_shamsi(self.vars['issue'].get());sh=normalize_shamsi(self.vars['due'].get())
            if not ish:raise ValueError('تاریخ صدور نامعتبر است.')
            if not sh:raise ValueError('سررسید نامعتبر است.')
            DB.update_cheque_details(self.row['cheque_id'],amount=parse_int(self.vars['amount'].get()),issue_date=shamsi_to_gregorian(ish),issue_date_shamsi=ish,due_date=shamsi_to_gregorian(sh),due_date_shamsi=sh,
                issuer_name=self.vars['issuer_name'].get().strip(),cheque_type='DIGITAL' if self.vars['cheque_type'].get()=='دیجیتال' else 'PHYSICAL',
                receiver_name=self.vars['receiver_name'].get().strip(),issuer_bank=self.vars['issuer_bank'].get().strip(),cheque_serial=self.vars['cheque_serial'].get().strip(),description=self.vars['description'].get().strip())
            self.destroy();self.on_refresh()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)


class LoanEditDialog(tk.Toplevel):
    def __init__(self,parent,row,on_refresh):
        super().__init__(parent);self.title('ویرایش مشخصات وام');self.transient(parent);self.grab_set();self.row=row;self.on_refresh=on_refresh
        keys=[('lender_name','بانک/وام‌دهنده'),('interest_rate','نرخ سود %'),('total_interest','کل سود'),('bank_fees','کارمزد'),('guarantors','ضامنین'),('collateral','وثیقه'),('contract_number','شماره قرارداد'),('description','توضیحات')]
        self.vars={k:tk.StringVar(value=group_int(row.get(k) or 0) if k in ('total_interest','bank_fees') else str(row.get(k) or '')) for k,_ in keys}
        for i,(k,l) in enumerate(keys):
            ttk.Label(self,text=l+':').grid(row=i,column=1,sticky='e',padx=6,pady=4);e=ttk.Entry(self,textvariable=self.vars[k],width=42,justify='right');e.grid(row=i,column=0,padx=6,pady=4)
            if k in ('total_interest','bank_fees'):bind_grouped_number(e,self.vars[k])
        ttk.Label(self,text='اصل وام، مبلغ دریافتی و برنامه اقساط برای حفظ یکپارچگی از این پنجره قفل هستند.',foreground=COLORS['muted']).grid(row=len(keys),column=0,columnspan=2,padx=8,pady=4)
        ttk.Button(self,text='ذخیره',command=self.save,style='Primary.TButton').grid(row=len(keys)+1,column=0,columnspan=2,pady=10)
        bind_enter_action(self,self.save)
    def save(self):
        try:
            now=__import__('datetime').datetime.now().isoformat(timespec='seconds')
            with DB.tx() as con:
                con.execute('''UPDATE loans SET lender_name=?,interest_rate=?,total_interest=?,bank_fees=?,guarantors=?,collateral=?,contract_number=?,description=?,updated_at=? WHERE loan_id=?''',
                    (self.vars['lender_name'].get().strip(),float(self.vars['interest_rate'].get() or 0),parse_int(self.vars['total_interest'].get()),parse_int(self.vars['bank_fees'].get()),self.vars['guarantors'].get().strip(),self.vars['collateral'].get().strip(),self.vars['contract_number'].get().strip(),self.vars['description'].get().strip(),now,self.row['loan_id']))
                after=dict(con.execute('SELECT * FROM loans WHERE loan_id=?',(self.row['loan_id'],)).fetchone());DB._enqueue_sync(con,'loan',self.row['loan_id'],'UPDATE',after)
            self.destroy();self.on_refresh()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)


class UnitMasterDialog(tk.Toplevel):
    def __init__(self,parent,on_refresh):
        super().__init__(parent);self.title('مشخصات واحدها، پارکینگ‌ها و انباری‌ها');self.geometry('1180x720');self.transient(parent);self.on_refresh=on_refresh
        top=ttk.Frame(self,padding=8);top.pack(fill='x');ttk.Button(top,text='➕ واحد جدید',command=self.add).pack(side='right');ttk.Button(top,text='⚡ ساخت گروهی',command=self.bulk).pack(side='right',padx=4);ttk.Button(top,text='✏️ ویرایش',command=self.edit).pack(side='right',padx=4);ttk.Button(top,text='🗑 حذف/لغو',command=self.delete).pack(side='right',padx=4)
        self.table=SmartTable(self,[('id','ID واحد',100),('floor','طبقه',90),('unit','شماره واحد',90),('area','متراژ مفید',110),('parkingid','ID پارکینگ',100),('parking','شماره پارکینگ',110),('storageid','ID انباری',100),('storage','شماره انباری',110),('status','وضعیت',100),('buyer','خریدار',150)],title='Unit Master')
        self.table.pack(fill='both',expand=True,padx=8,pady=8);self.table.set_edit_handler(lambda r:self.edit_row(r));self.table.set_delete_handler(lambda r:self._delete_row(r));self.refresh()
    def refresh(self):
        rows=UNITS.list_units();self.table.set_rows(rows,lambda r:[r.get('display_unit_id') or r['unit_id'],r.get('floor') or '-',r.get('unit_number') or '-',f"{float(r.get('area') or 0):,.2f}",r.get('parking_display_id') or '-',r.get('parking') or '-',r.get('storage_display_id') or '-',r.get('storage') or '-',fa_status(r.get('status')),r.get('buyer_name') or '-'])
    def one(self):
        r=self.table.selected_rows();return r[0] if r else None
    def add(self):UnitEditDialog(self,None,lambda:self._done())
    def edit(self):
        r=self.one()
        if r:self.edit_row(r)
    def edit_row(self,r):UnitEditDialog(self,r,lambda:self._done())
    def bulk(self):BulkUnitDialog(self,lambda:self._done())
    def delete(self):
        r=self.one()
        if not r:return
        if not messagebox.askyesno('حذف واحد',f"واحد {r.get('unit_number')} حذف/لغو شود؟",parent=self):return
        try:UNITS.cancel_unit(r['unit_id']);self._done()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def _delete_row(self,r):
        if not r:return
        if not messagebox.askyesno('حذف واحد',f"واحد {r.get('unit_number')} حذف/لغو شود؟",parent=self):return
        try:UNITS.cancel_unit(r['unit_id']);self._done()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def _done(self):self.refresh();self.on_refresh()


class UnitEditDialog(tk.Toplevel):
    def __init__(self,parent,row,on_save):
        super().__init__(parent);self.title('ویرایش واحد' if row else 'واحد جدید');self.transient(parent);self.grab_set();self.row=row;self.on_save=on_save;p=SERVICE.project.get_project()
        defaults={'display_unit_id':'','project_name':p.get('name') or '','block_name':'','floor':'','unit_number':'','area':'0','parking_display_id':'','parking':'','storage_display_id':'','storage':'','notes':''}
        if row:defaults.update({k:str(row.get(k) or '') for k in defaults})
        self.vars={k:tk.StringVar(value=v) for k,v in defaults.items()}
        fields=[('display_unit_id','ID واحد (قابل ویرایش)'),('project_name','پروژه'),('block_name','بلوک'),('floor','طبقه'),('unit_number','شماره واحد'),('area','متراژ مفید'),('parking_display_id','ID پارکینگ'),('parking','شماره پارکینگ'),('storage_display_id','ID انباری'),('storage','شماره انباری'),('notes','توضیحات')]
        for i,(k,l) in enumerate(fields):ttk.Label(self,text=l+':').grid(row=i,column=1,sticky='e',padx=5,pady=2);ttk.Entry(self,textvariable=self.vars[k],width=40,justify='right').grid(row=i,column=0,padx=5,pady=2)
        ttk.Label(self,text='IDهای این فرم نمایشی و قابل ویرایش‌اند؛ شناسه داخلی دیتابیس ثابت می‌ماند تا قراردادهای قبلی خراب نشوند.',foreground=COLORS['muted']).grid(row=len(fields),column=0,columnspan=2,padx=6,pady=3)
        ttk.Button(self,text='ذخیره',command=self.save,style='Primary.TButton').grid(row=len(fields)+1,column=0,columnspan=2,pady=7);bind_enter_action(self,self.save)
    def save(self):
        try:
            d={k:v.get().strip() for k,v in self.vars.items()};d['area']=float(str(d['area']).replace(',','') or 0)
            if self.row:UNITS.update_unit(self.row['unit_id'],**d)
            else:UNITS.add_unit(**d)
            self.destroy();self.on_save()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)


class BulkUnitDialog(tk.Toplevel):
    def __init__(self,parent,on_save):
        super().__init__(parent);self.title('ساخت گروهی واحدها');self.transient(parent);self.grab_set();self.on_save=on_save;p=SERVICE.project.get_project();rows=UNITS.list_units();nums=[]
        for r in rows:
            try:nums.append(int(r.get('unit_number')))
            except Exception:pass
        self.vars={'project_name':tk.StringVar(value=p.get('name') or ''),'block_name':tk.StringVar(),'floor':tk.StringVar(),'count':tk.StringVar(value='4'),'start':tk.StringVar(value=str(max(nums+[0])+1)),'area':tk.StringVar(value='0')}
        fields=[('project_name','پروژه'),('block_name','بلوک'),('floor','طبقه'),('count','تعداد واحد در این طبقه'),('start','شماره اولین واحد'),('area','متراژ پیش‌فرض')]
        for i,(k,l) in enumerate(fields):ttk.Label(self,text=l+':').grid(row=i,column=1,sticky='e',padx=6,pady=4);ttk.Entry(self,textvariable=self.vars[k],width=38,justify='right').grid(row=i,column=0,padx=6,pady=4)
        ttk.Label(self,text='پارکینگ و انباری به‌صورت اولیه هم‌شماره واحد ساخته می‌شوند و بعداً قابل ویرایش‌اند.',foreground=COLORS['muted']).grid(row=len(fields),column=0,columnspan=2,padx=6,pady=4)
        ttk.Button(self,text='ساخت',command=self.save,style='Primary.TButton').grid(row=len(fields)+1,column=0,columnspan=2,pady=10)
        bind_enter_action(self,self.save)
    def save(self):
        try:
            UNITS.bulk_create(floor=self.vars['floor'].get().strip(),count=int(self.vars['count'].get()),start_number=int(self.vars['start'].get()),default_area=float(self.vars['area'].get() or 0),project_name=self.vars['project_name'].get().strip(),block_name=self.vars['block_name'].get().strip());self.destroy();self.on_save()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)



class SaleEditDialog(tk.Toplevel):
    def __init__(self,parent,row,on_refresh):
        super().__init__(parent);self.title('ویرایش قرارداد فروش');self.transient(parent);self.grab_set();self.row=row;self.on_refresh=on_refresh
        self.vars={
            'buyer_name':tk.StringVar(value=row.get('buyer_name') or ''),
            'buyer_phone':tk.StringVar(value=row.get('buyer_phone') or ''),
            'contract_number':tk.StringVar(value=row.get('contract_number') or ''),
            'contract_date_shamsi':tk.StringVar(value=row.get('contract_date_shamsi') or ''),
            'notes':tk.StringVar(value=row.get('notes') or ''),
        }
        ttk.Label(self,text=f"واحد: {row.get('unit_number') or '-'}   |   مبلغ قرارداد: {money(row.get('contract_amount'))}",font=('Tahoma',10,'bold')).grid(row=0,column=0,columnspan=2,padx=10,pady=(10,7))
        fields=[('buyer_name','نام خریدار'),('buyer_phone','شماره تماس'),('contract_number','شماره قرارداد'),('contract_date_shamsi','تاریخ قرارداد'),('notes','توضیحات')]
        for i,(k,l) in enumerate(fields,1):
            ttk.Label(self,text=l+':').grid(row=i,column=1,sticky='e',padx=6,pady=4)
            if k=='contract_date_shamsi':DateField(self,self.vars[k],width=35).grid(row=i,column=0,padx=6,pady=4,sticky='ew')
            else:ttk.Entry(self,textvariable=self.vars[k],width=42,justify='right').grid(row=i,column=0,padx=6,pady=4)
        ttk.Label(self,text='مبلغ قرارداد از جمع اقساط محاسبه می‌شود؛ برای تغییر مبلغ، وارد «اقساط فروش» شو.',foreground=COLORS['muted']).grid(row=len(fields)+1,column=0,columnspan=2,padx=8,pady=4)
        ttk.Button(self,text='ذخیره',command=self.save,style='Primary.TButton').grid(row=len(fields)+2,column=0,columnspan=2,pady=10)
        bind_enter_action(self,self.save)
    def save(self):
        try:
            SERVICE.revenue.update_sale_metadata(self.row['sale_id'],buyer_name=self.vars['buyer_name'].get(),buyer_phone=self.vars['buyer_phone'].get(),contract_number=self.vars['contract_number'].get(),contract_date_shamsi=self.vars['contract_date_shamsi'].get(),notes=self.vars['notes'].get())
            self.destroy();self.on_refresh()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)


class SaleInstallmentEditDialog(tk.Toplevel):
    def __init__(self,parent,row,on_refresh):
        super().__init__(parent);self.title('ویرایش قسط فروش');self.transient(parent);self.grab_set();self.row=row;self.on_refresh=on_refresh
        self.amount=tk.StringVar(value=group_int(row.get('amount') or 0));self.due=tk.StringVar(value=row.get('due_date_shamsi') or '');self.desc=tk.StringVar(value=row.get('description') or '')
        ttk.Label(self,text=f"قسط {row.get('sequence_no') or '-'} | پرداخت‌شده: {money(row.get('paid_amount'))}",font=('Tahoma',10,'bold')).grid(row=0,column=0,columnspan=2,padx=8,pady=8)
        ttk.Label(self,text='مبلغ:').grid(row=1,column=1,sticky='e',padx=6,pady=4);e=ttk.Entry(self,textvariable=self.amount,width=38,justify='right');e.grid(row=1,column=0,padx=6,pady=4);bind_grouped_number(e,self.amount)
        ttk.Label(self,text='سررسید:').grid(row=2,column=1,sticky='e',padx=6,pady=4);DateField(self,self.due,width=34).grid(row=2,column=0,padx=6,pady=4,sticky='ew')
        ttk.Label(self,text='شرح:').grid(row=3,column=1,sticky='e',padx=6,pady=4);ttk.Entry(self,textvariable=self.desc,width=42,justify='right').grid(row=3,column=0,padx=6,pady=4)
        ttk.Button(self,text='ذخیره',command=self.save,style='Primary.TButton').grid(row=4,column=0,columnspan=2,pady=10)
        bind_enter_action(self,self.save)
    def save(self):
        try:
            SERVICE.revenue.update_installment_details(self.row['installment_id'],due_date_shamsi=self.due.get(),amount=parse_int(self.amount.get()),description=self.desc.get())
            self.destroy();self.on_refresh()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)


class SaleInstallmentsDialog(tk.Toplevel):
    def __init__(self,parent,sale_id,on_refresh):
        super().__init__(parent);self.title('اقساط فروش');self.geometry('980x620');self.sale_id=sale_id;self.on_refresh=on_refresh;self.transient(parent)
        self.table=SmartTable(self,[('no','قسط',70),('due','سررسید',110),('amount','مبلغ',140),('paid','پرداخت‌شده',140),('remain','مانده',140),('desc','شرح',220),('status','وضعیت',110),('id','Installment ID',155)],title='برنامه اقساط')
        self.table.pack(fill='both',expand=True,padx=8,pady=8);self.table.set_edit_handler(lambda r:self.edit_row(r));self.table.set_delete_handler(lambda r:self._delete_row(r));self.refresh()
    def refresh(self):
        rows=SERVICE.revenue.list_installments(self.sale_id);self.table.set_rows(rows,lambda r:[r.get('sequence_no') or '-',r.get('due_date_shamsi') or '-',money(r.get('amount')),money(r.get('paid_amount')),money(max(0,int(r.get('amount') or 0)-int(r.get('paid_amount') or 0))),r.get('description') or '-',fa_status(r.get('status')),r.get('installment_id')])
    def edit_row(self,r):SaleInstallmentEditDialog(self,r,lambda:self._done())
    def _delete_row(self,r):
        if not r:return
        if not messagebox.askyesno('حذف قسط فروش',f"قسط {r.get('sequence_no') or '-'} حذف/لغو شود؟",parent=self):return
        try:SERVICE.revenue.cancel_installment(r['installment_id']);self._done()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def _done(self):self.refresh();self.on_refresh()


class ReconciliationEditDialog(tk.Toplevel):
    def __init__(self,parent,row,on_refresh):
        super().__init__(parent);self.title('ویرایش تطبیق بانک');self.transient(parent);self.grab_set();self.row=row;self.on_refresh=on_refresh
        self.bank=tk.StringVar(value=group_int(row.get('bank_balance') or 0));self.date=tk.StringVar(value=row.get('shamsi_date') or '');self.notes=tk.StringVar(value=row.get('notes') or '')
        ttk.Label(self,text='موجودی واقعی بانک:').grid(row=0,column=1,sticky='e',padx=6,pady=5);e=ttk.Entry(self,textvariable=self.bank,width=34,justify='right');e.grid(row=0,column=0,padx=6,pady=5);bind_grouped_number(e,self.bank,allow_negative=True)
        ttk.Label(self,text='تاریخ شمسی:').grid(row=1,column=1,sticky='e',padx=6,pady=5);DateField(self,self.date,width=30).grid(row=1,column=0,padx=6,pady=5,sticky='ew')
        ttk.Label(self,text='توضیحات:').grid(row=2,column=1,sticky='e',padx=6,pady=5);ttk.Entry(self,textvariable=self.notes,width=38,justify='right').grid(row=2,column=0,padx=6,pady=5)
        ttk.Button(self,text='ذخیره',command=self.save,style='Primary.TButton').grid(row=3,column=0,columnspan=2,pady=10)
        bind_enter_action(self,self.save)
    def save(self):
        try:
            SERVICE.update_reconciliation(self.row['reconciliation_id'],bank_balance=parse_int(self.bank.get()),shamsi_date=self.date.get(),notes=self.notes.get());self.destroy();self.on_refresh()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)


class SearchWindow(tk.Toplevel):
    def __init__(self,parent):
        super().__init__(parent);self.title('جستجوی سراسری');self.geometry('1280x720');self.transient(parent)
        top=ttk.Frame(self,padding=8);top.pack(fill='x');self.scope=tk.StringVar(value='همه');self.query=tk.StringVar();self.dfrom=tk.StringVar();self.dto=tk.StringVar();self.amin=tk.StringVar();self.amax=tk.StringVar()
        ttk.Label(top,text='جستجو در:').pack(side='right');ttk.Combobox(top,textvariable=self.scope,values=['همه','کلیه تراکنش‌ها','هزینه ساخت','ورودی‌ها','خروجی‌ها','وام‌ها','چک‌ها','فروش و مطالبات'],state='readonly',width=18).pack(side='right',padx=4)
        ttk.Label(top,text='عبارت:').pack(side='right');e=ttk.Entry(top,textvariable=self.query,width=25,justify='right');e.pack(side='right',padx=4);e.bind('<Return>',lambda ev:self.run())
        ttk.Label(top,text='از تاریخ:').pack(side='right');DateField(top,self.dfrom,width=11).pack(side='right',padx=2);ttk.Label(top,text='تا:').pack(side='right');DateField(top,self.dto,width=11).pack(side='right',padx=2)
        second=ttk.Frame(self,padding=(8,0,8,5));second.pack(fill='x');ttk.Label(second,text='مبلغ از:').pack(side='right');a=ttk.Entry(second,textvariable=self.amin,width=16,justify='right');a.pack(side='right',padx=3);bind_grouped_number(a,self.amin);ttk.Label(second,text='تا:').pack(side='right');b=ttk.Entry(second,textvariable=self.amax,width=16,justify='right');b.pack(side='right',padx=3);bind_grouped_number(b,self.amax);ttk.Button(second,text='🔎 جستجو',command=self.run,style='Primary.TButton').pack(side='right',padx=10)
        self.table=SmartTable(self,[('source','نوع',100),('date','تاریخ',100),('amount','مبلغ',130),('dir','جهت',70),('person','شخص/طرف حساب',160),('desc','شرح',300),('status','وضعیت',100),('receipt','رسید',70),('id','ID',160)]);self.table.pack(fill='both',expand=True,padx=8,pady=8);self.table.set_edit_handler(self.edit_row);self.table.set_delete_handler(self.delete_row);self.run()
    def run(self):
        try:
            rows=SERVICE.search(self.query.get(),self.scope.get(),date_from=self.dfrom.get().strip(),date_to=self.dto.get().strip(),amount_min=(parse_int(self.amin.get()) if self.amin.get().strip() else None),amount_max=(parse_int(self.amax.get()) if self.amax.get().strip() else None))
            for r in rows:r['_sum_amount']=int(r.get('amount') or 0)
            self.table.set_rows(rows,lambda r:[r['source'],r['date'],money(r['amount']),'ورودی' if r['direction']=='IN' else 'خروجی',r['person'],r['description'],fa_status(r['status']),f"📎 {r['receipt_count']}",r['id']])
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def edit_row(self,r):
        raw=r.get('raw') or {}; src=r.get('source')
        if src=='تراکنش':self.master.edit_transaction_row(raw)
        elif src=='هزینه ساخت':self.master.edit_expense_row(raw)
        elif src=='وام':LoanEditDialog(self,raw,lambda:(self.run(),self.master.refresh_all()))
        elif src=='چک':ChequeEditDialog(self,raw,lambda:(self.run(),self.master.refresh_all()))
        elif src=='فروش':SaleEditDialog(self,raw,lambda:(self.run(),self.master.refresh_all()))
    def delete_row(self,r):
        raw=r.get('raw') or {};src=r.get('source')
        if src=='تراکنش':self.master._delete_tx_row(raw)
        elif src=='هزینه ساخت':self.master._delete_expense_row(raw)
        elif src=='وام':self.master._cancel_loan_row(raw)
        elif src=='چک':self.master._cancel_cheque_row(raw)
        elif src=='فروش':self.master._cancel_sale_row(raw)
        self.run()


class PhaseDetailDialog(tk.Toplevel):
    def __init__(self,parent,phase_id,phase_name,on_refresh):
        super().__init__(parent);self.title(f'جزئیات فاز — {phase_name}');self.geometry('1050x680');self.phase_id=phase_id;self.phase_name=phase_name;self.on_refresh=on_refresh
        self.table=SmartTable(self,[('act','فعالیت',280),('estimate','برآورد',145),('actual','واقعی',145),('remain','مانده بودجه',145),('forecast','پیش‌بینی پایان',145),('var','انحراف',145)],title=phase_name);self.table.pack(fill='both',expand=True,padx=8,pady=8);self.table.set_edit_handler(self.edit_estimate);self.table.set_delete_handler(lambda r:self._delete_activity_row(r))
        bar=ttk.Frame(self);bar.pack(fill='x',padx=8,pady=(0,5));b1=ttk.Button(bar,text='➕ افزودن فعالیت',command=self.add_activity,style='Compact.TButton');b1.pack(side='right');add_tooltip(b1,'افزودن یک فعالیت جدید به همین فاز');b2=ttk.Button(bar,text='✏️ تغییر نام فعالیت',command=self.rename_activity,style='Compact.TButton');b2.pack(side='right',padx=2);add_tooltip(b2,'تغییر نام فعالیت بدون تغییر شناسه و هزینه‌های متصل');b3=ttk.Button(bar,text='🗑 حذف فعالیت',command=self.delete_activity,style='Compact.TButton');b3.pack(side='right',padx=2);add_tooltip(b3,'حذف فعالیت انتخاب‌شده در صورت مجاز بودن');hint=ttk.Label(bar,text='دبل‌کلیک فعالیت = اصلاح مبلغ برآورد',foreground=COLORS['muted'],font=('Tahoma',7));hint.pack(side='left');add_tooltip(hint,'مبلغ برآورد فعالیت از این مسیر قابل ویرایش است.');self.refresh()
    def refresh(self):
        rows=[r for r in SERVICE.budget.report_rows() if r.get('phase_id')==self.phase_id];self.table.set_rows(rows,lambda r:[r['activity'],money(r['estimate']),money(r['actual']),money(r['remaining_budget']),money(r['forecast']),money(r['variance'])])
    def one(self):
        r=self.table.selected_rows();return r[0] if r else None
    def edit_estimate(self,r):EstimateEditDialog(self,r,lambda amount:self._save_estimate(r['activity_id'],amount))
    def _save_estimate(self,aid,amount):
        try:SERVICE.budget.update_activity_estimate(aid,amount);self.refresh();self.on_refresh()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def _delete_activity_row(self,r):
        if not r:return
        if not messagebox.askyesno('حذف',f"فعالیت «{r.get('activity')}» حذف شود؟",parent=self):return
        try:SERVICE.budget.delete_activity(r['activity_id']);self.refresh();self.on_refresh()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def add_activity(self):
        name=simpledialog.askstring('فعالیت جدید','نام فعالیت:',parent=self)
        if not name:return
        amount=simpledialog.askinteger('برآورد','برآورد اولیه (تومان، می‌تواند صفر باشد):',parent=self,minvalue=0) or 0
        try:SERVICE.budget.add_activity(self.phase_id,name,amount);self.refresh();self.on_refresh()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def rename_activity(self):
        r=self.one()
        if not r:return
        name=simpledialog.askstring('تغییر نام','نام جدید فعالیت:',initialvalue=r['activity'],parent=self)
        if not name:return
        try:SERVICE.budget.rename_activity(r['activity_id'],name);self.refresh();self.on_refresh()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)
    def delete_activity(self):
        r=self.one()
        if not r:return
        if not messagebox.askyesno('حذف',f"فعالیت «{r['activity']}» حذف شود؟",parent=self):return
        try:SERVICE.budget.delete_activity(r['activity_id']);self.refresh();self.on_refresh()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)


if __name__=='__main__':Stage12Dashboard().mainloop()

d12 = _legacy_snapshot()

# ---- Extracted from dashboard_stage14.py ----

import asyncio
import json
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from approval_service import ApprovalCenterService
from ui import parse_int
from finance_db import FinanceDB
from receipt_ai_provider import build_receipt_vision_parser

AI_PARSER = build_receipt_vision_parser(BASE_DIR, gemini_api_key=CONFIG.gemini_api_key, gemini_model=CONFIG.gemini_model)
APPROVAL = ApprovalCenterService(DB, BASE_DIR, parser=AI_PARSER)

TYPE_LABELS = {
    "EXPENSE": "هزینه ساخت",
    "INCOME": "ورودی",
    "OUTFLOW": "خروجی",
    "CHEQUE": "چک",
    "DOCUMENT": "داکیومنت",
    "INFO": "اطلاع‌رسانی",
    "UNKNOWN": "نامشخص",
}
TYPE_VALUES = ["EXPENSE", "INCOME", "OUTFLOW", "CHEQUE", "DOCUMENT", "INFO", "UNKNOWN"]
PAYMENT_METHODS = ["CASH", "BANK_TRANSFER", "CARD", "CHEQUE", "UNKNOWN"]
PAYMENT_STATES = ["PAID", "PARTIAL", "UNPAID", "CHEQUE_CLEARING", "UNKNOWN"]


def _fmt_conf(v: Any) -> str:
    try:
        return f"{float(v) * 100:.0f}%"
    except Exception:
        return "-"


class ApprovalCenter(ttk.Frame):
    """GUI approval center for Telegram financial messages and receipts."""

    def __init__(self, parent: tk.Misc, on_posted=None):
        super().__init__(parent, padding=6)
        self.on_posted = on_posted
        self.rows: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.vars: dict[str, tk.StringVar] = {}
        self._build()
        self.refresh()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 4))
        ttk.Label(top, text="مرکز تأیید رسیدها و پیام‌های مالی", font=("Tahoma", 10, "bold")).pack(side="right")
        ttk.Label(top, text="روش تأیید:").pack(side="right", padx=(16, 3))
        self.channel = tk.StringVar(value=self._channel_label(DB.get_setting("approval_channels", "BOTH") or "BOTH"))
        cmb = ttk.Combobox(top, textvariable=self.channel, state="readonly", width=18,
                           values=["هر دو (برنامه + تلگرام)", "فقط برنامه", "فقط تلگرام"])
        cmb.pack(side="right")
        cmb.bind("<<ComboboxSelected>>", lambda e: self._save_channel())
        add_tooltip(cmb, "مشخص می‌کند کارت تأیید در خصوصی تلگرام هم ارسال شود یا فقط در برنامه دیده شود.")
        b = ttk.Button(top, text="🔄 بروزرسانی", command=self.refresh)
        b.pack(side="left")
        add_tooltip(b, "بارگذاری دوباره موارد در انتظار از SQLite")
        try:
            ocr_ok = APPROVAL.receipts.ocr.available()
            lang = APPROVAL.receipts.ocr.effective_lang() if ocr_ok else "-"
            ocr_text = f"OCR محلی: آماده ({lang})" if ocr_ok else "OCR محلی: نصب/در دسترس نیست"
            ttk.Label(top, text=ocr_text, foreground=COLORS["green"] if ocr_ok else COLORS["orange"]).pack(side="left", padx=10)
        except Exception:
            pass

        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True)
        left = ttk.Frame(pane, padding=(0, 0, 4, 0))
        right = ttk.Frame(pane, padding=(4, 0, 0, 0))
        pane.add(left, weight=3)
        pane.add(right, weight=4)

        self.table = SmartTable(left, [
            ("date", "تاریخ", 105),
            ("type", "نوع", 95),
            ("amount", "مبلغ", 125),
            ("desc", "بابت", 220),
            ("conf", "اطمینان مبلغ", 95),
            ("provider", "موتور", 115),
            ("warn", "هشدار", 70),
        ], title="موارد در انتظار تأیید")
        self.table.pack(fill="both", expand=True)
        self.table.tree.bind("<<TreeviewSelect>>", self._select, add="+")
        self.table.tree.bind("<Double-1>", lambda e: self.open_receipt(), add="+")

        # Right: compact source/receipt information
        src = ttk.LabelFrame(right, text="منبع و تحلیل رسید", padding=5)
        src.pack(fill="x", pady=(0, 4))
        self.source_text = tk.Text(src, height=5, wrap="word", font=("Tahoma", 8), bg="white")
        self.source_text.pack(fill="x")
        info = ttk.Frame(src)
        info.pack(fill="x", pady=(4, 0))
        self.receipt_info = tk.StringVar(value="موردی انتخاب نشده")
        ttk.Label(info, textvariable=self.receipt_info, foreground=COLORS["muted"]).pack(side="right")
        open_btn = ttk.Button(info, text="🖼 مشاهده رسید", command=self.open_receipt)
        open_btn.pack(side="left")
        add_tooltip(open_btn, "باز کردن فایل اصلی آرشیوشده رسید/فاکتور")
        ai_btn = ttk.Button(info, text="🤖 تحلیل AI این تصویر", command=self.analyze_current_ai)
        ai_btn.pack(side="left", padx=4)
        add_tooltip(ai_btn, "تصویر آرشیوشده را دوباره با AI Vision تحلیل می‌کند؛ برای موارد Import شده یا تحلیل ناموفق استفاده کن.")
        ai_all = ttk.Button(info, text="🤖 تحلیل همه تصاویر", command=self.analyze_all_ai)
        ai_all.pack(side="left", padx=2)
        add_tooltip(ai_all, "تمام تصاویر در انتظار را در پس‌زمینه با AI Vision تحلیل می‌کند. نتیجه‌ها قبل از ثبت همچنان نیازمند تأیید تو هستند.")

        edit = ttk.LabelFrame(right, text="اطلاعات قابل اصلاح قبل از ثبت", padding=5)
        edit.pack(fill="x", pady=(0, 4))
        fields = [
            ("detected_type", "نوع", "combo_type"),
            ("amount", "مبلغ", "entry"),
            ("invoice_amount", "مبلغ فاکتور", "entry"),
            ("final_amount", "مبلغ نهایی", "entry"),
            ("paid_amount", "پرداخت‌شده", "entry"),
            ("event_date_shamsi", "تاریخ", "entry"),
            ("description", "بابت", "entry"),
            ("expense_category", "نوع هزینه", "entry"),
            ("construction_stage", "مرحله ساخت", "entry"),
            ("payer_name", "واریزکننده", "entry"),
            ("receiver_name", "دریافت‌کننده", "entry"),
            ("payment_method", "روش پرداخت", "combo_method"),
            ("payment_state", "وضعیت پرداخت", "combo_state"),
            ("due_date_shamsi", "سررسید چک", "entry"),
        ]
        for i, (key, label, kind) in enumerate(fields):
            r, c = divmod(i, 2)
            cell = ttk.Frame(edit)
            cell.grid(row=r, column=c, sticky="ew", padx=3, pady=2)
            edit.columnconfigure(c, weight=1)
            ttk.Label(cell, text=label + ":", width=14, anchor="e").pack(side="right")
            var = tk.StringVar()
            self.vars[key] = var
            if kind == "combo_type":
                w = ttk.Combobox(cell, textvariable=var, values=TYPE_VALUES, state="readonly", width=24)
            elif kind == "combo_method":
                w = ttk.Combobox(cell, textvariable=var, values=PAYMENT_METHODS, state="readonly", width=24)
            elif kind == "combo_state":
                w = ttk.Combobox(cell, textvariable=var, values=PAYMENT_STATES, state="readonly", width=24)
            else:
                w = ttk.Entry(cell, textvariable=var, justify="right")
            w.pack(side="right", fill="x", expand=True)

        details = ttk.Panedwindow(right, orient="horizontal")
        details.pack(fill="both", expand=True, pady=(0, 4))
        cframe = ttk.LabelFrame(details, text="هشدارها / اختلاف‌ها", padding=4)
        dframe = ttk.LabelFrame(details, text="موارد مشابه احتمالی", padding=4)
        details.add(cframe, weight=1)
        details.add(dframe, weight=1)
        self.conflicts_text = tk.Text(cframe, height=6, wrap="word", font=("Tahoma", 8), bg="#FFF7E6")
        self.conflicts_text.pack(fill="both", expand=True)
        self.dupes_text = tk.Text(dframe, height=6, wrap="word", font=("Tahoma", 8), bg="#F4F9FD")
        self.dupes_text.pack(fill="both", expand=True)

        actions = ttk.Frame(right)
        actions.pack(fill="x")
        save = ttk.Button(actions, text="💾 ذخیره اصلاحات", command=self.save_edits)
        save.pack(side="right")
        add_tooltip(save, "اصلاحات را روی Pending ذخیره می‌کند؛ هنوز اثر مالی ایجاد نمی‌شود.")
        approve = ttk.Button(actions, text="✅ تأیید و ثبت قطعی", command=self.approve, style="Primary.TButton")
        approve.pack(side="right", padx=4)
        add_tooltip(approve, "همان ثبت قطعی مالی Telegram را از داخل GUI انجام می‌دهد.")
        reject = ttk.Button(actions, text="❌ رد", command=self.reject, style="Danger.TButton")
        reject.pack(side="right")
        add_tooltip(reject, "مورد رد می‌شود و هیچ اثر مالی در Ledger ندارد.")
        link = ttk.Button(actions, text="🔗 اتصال به ثبت موجود", command=self.link_existing)
        link.pack(side="right", padx=4)
        add_tooltip(link, "اگر رسید/فاکتور مربوط به ثبت مالی موجود است، فقط مدرک را متصل می‌کند و هزینه جدید نمی‌سازد.")
        self.status = tk.StringVar(value="")
        ttk.Label(actions, textvariable=self.status, foreground=COLORS["navy"]).pack(side="left")

    @staticmethod
    def _channel_label(v: str) -> str:
        return {"BOTH": "هر دو (برنامه + تلگرام)", "GUI": "فقط برنامه", "TELEGRAM": "فقط تلگرام"}.get(v.upper(), "هر دو (برنامه + تلگرام)")

    def _save_channel(self):
        value = {"هر دو (برنامه + تلگرام)": "BOTH", "فقط برنامه": "GUI", "فقط تلگرام": "TELEGRAM"}.get(self.channel.get(), "BOTH")
        DB.set_setting("approval_channels", value)
        self.status.set("روش تأیید ذخیره شد")

    def refresh(self):
        self.rows = APPROVAL.list_pending(limit=1000)
        def vals(r: dict[str, Any]):
            p = r.get("payload") or {}
            fc = r.get("field_confidences") or p.get("field_confidences") or {}
            conflicts = r.get("conflicts") or []
            amount = p.get("final_amount") or p.get("amount") or 0
            return [
                r.get("message_date") or "-",
                TYPE_LABELS.get(str(p.get("detected_type") or "UNKNOWN"), str(p.get("detected_type") or "UNKNOWN")),
                money(amount),
                p.get("description") or r.get("raw_text") or "-",
                _fmt_conf(fc.get("amount", p.get("confidence", 0))),
                r.get("receipt_provider") or ("متن" if r.get("content_type") == "TEXT" else "-"),
                f"⚠ {len(conflicts)}" if conflicts else "-",
            ]
        self.table.set_rows(self.rows, vals)
        self._update_tab_count()
        if self.current:
            pid = self.current.get("pending_id")
            fresh = next((x for x in self.rows if x.get("pending_id") == pid), None)
            if fresh:
                self.current = fresh
                self._load_current()
            else:
                self.current = None
                self._clear()

    def _update_tab_count(self):
        # Parent notebook tab text gets updated by Stage14Dashboard.
        root = self.winfo_toplevel()
        if hasattr(root, "_update_approval_tab_text"):
            root._update_approval_tab_text(len(self.rows))

    def _select(self, event=None):
        rows = self.table.selected_rows()
        if not rows:
            return
        self.current = rows[0]
        self._load_current()

    def _load_current(self):
        r = self.current or {}
        p = dict(r.get("payload") or {})
        self.source_text.configure(state="normal")
        self.source_text.delete("1.0", "end")
        self.source_text.insert("end", f"پیام اصلی:\n{r.get('raw_text') or '-'}\n")
        ocr = r.get("receipt_ocr_text") or ""
        if ocr:
            self.source_text.insert("end", f"\nOCR محلی:\n{ocr[:2500]}")
        self.source_text.configure(state="disabled")
        for key, var in self.vars.items():
            value = p.get(key, "")
            if key in {"amount", "invoice_amount", "final_amount", "paid_amount"}:
                try: value = f"{int(value or 0):,}"
                except Exception: value = str(value or "")
            var.set(str(value or ""))
        fc = r.get("field_confidences") or p.get("field_confidences") or {}
        vision=p.get("vision_status") or ("در انتظار" if str(r.get("receipt_provider") or "").startswith("PENDING") else "-")
        self.receipt_info.set(
            f"ID: {r.get('pending_id')} | منبع: {r.get('content_type') or '-'} | موتور: {r.get('receipt_provider') or '-'} | "
            f"Vision: {vision} | نوع سند: {r.get('receipt_document_type') or p.get('document_type') or '-'} | "
            f"اعتماد مبلغ: {_fmt_conf(fc.get('amount', p.get('confidence', 0)))}"
        )
        self.conflicts_text.delete("1.0", "end")
        conflicts = r.get("conflicts") or []
        if not conflicts:
            self.conflicts_text.insert("end", "اختلاف مهمی بین پیام، OCR و تحلیل تصویر ثبت نشده است.")
        else:
            for c in conflicts:
                self.conflicts_text.insert("end", "• " + json.dumps(c, ensure_ascii=False) + "\n")
        self.dupes_text.delete("1.0", "end")
        dupes = r.get("duplicate_candidates") or []
        if not dupes:
            self.dupes_text.insert("end", "مورد هم‌مبلغ ثبت‌شده‌ای پیدا نشد.")
        else:
            for d in dupes:
                self.dupes_text.insert(
                    "end", f"• {d.get('entity_type')} | {d.get('entity_id')} | {money(d.get('amount'))} | "
                           f"{d.get('event_date') or '-'} | {d.get('counterparty') or '-'} | امتیاز {d.get('match_score') or 0}\n"
                )

    def _clear(self):
        for v in self.vars.values(): v.set("")
        self.source_text.configure(state="normal"); self.source_text.delete("1.0", "end"); self.source_text.configure(state="disabled")
        self.conflicts_text.delete("1.0", "end"); self.dupes_text.delete("1.0", "end")
        self.receipt_info.set("موردی انتخاب نشده")

    def _payload_from_form(self) -> dict[str, Any]:
        if not self.current:
            raise ValueError("ابتدا یک مورد را انتخاب کن.")
        p = dict(self.current.get("payload") or {})
        for key, var in self.vars.items():
            raw = var.get().strip()
            if key in {"amount", "invoice_amount", "final_amount", "paid_amount"}:
                p[key] = parse_int(raw)
            else:
                p[key] = raw
        p["is_cheque"] = p.get("payment_method") == "CHEQUE" or p.get("detected_type") == "CHEQUE" or bool(p.get("is_cheque"))
        p["manager_fee_eligible"] = p.get("detected_type") == "EXPENSE"
        return p

    def _run_ai_ids(self, pending_ids: list[str]):
        if not pending_ids:
            self.status.set("تصویری برای تحلیل پیدا نشد")
            return
        self.status.set(f"AI: شروع تحلیل {len(pending_ids)} تصویر...")
        def worker():
            ok=fail=0;last_error=""
            for pid in pending_ids:
                try:
                    asyncio.run(APPROVAL.analyze_pending_with_ai(pid));ok+=1
                except Exception as exc:
                    fail+=1;last_error=f"{exc.__class__.__name__}: {exc}"
            def done():
                self.status.set(f"AI: {ok} موفق | {fail} ناموفق" + (f" | {last_error[:90]}" if fail else ""))
                self.refresh()
            self.after(0,done)
        threading.Thread(target=worker,daemon=True,name="peymaan-ai-receipts").start()

    def analyze_current_ai(self):
        if not self.current:
            messagebox.showwarning("تحلیل AI","ابتدا یک مورد تصویری را انتخاب کن.",parent=self);return
        self._run_ai_ids([str(self.current.get("pending_id"))])

    def analyze_all_ai(self):
        ids=[]
        for r in self.rows:
            path=str(r.get("receipt_image_path") or "")
            if not path:
                try:
                    atts=DB.list_pending_attachments(r.get("pending_id"))
                    path=next((str(a.get("local_path") or "") for a in atts if str(a.get("mime_type") or "").lower().startswith("image/")),"")
                except Exception:
                    path=""
            if path and Path(path).exists(): ids.append(str(r.get("pending_id")))
        if not ids:
            messagebox.showinfo("تحلیل AI","هیچ تصویر آرشیوشده‌ای در صف نیست.",parent=self);return
        if len(ids)>50 and not messagebox.askyesno("تحلیل AI",f"{len(ids)} تصویر در صف است. تحلیل همه ممکن است زمان‌بر و دارای هزینه API باشد. ادامه؟",parent=self):return
        self._run_ai_ids(ids)

    def save_edits(self):
        if not self.current:
            messagebox.showwarning("مرکز تأیید", "یک مورد را انتخاب کن.", parent=self)
            return
        try:
            payload = self._payload_from_form()
            APPROVAL.save_payload(self.current["pending_id"], payload, learn=True)
            self.status.set("اصلاحات ذخیره شد؛ هنوز ثبت مالی نشده است.")
            self.refresh()
        except Exception as exc:
            messagebox.showerror("خطا", str(exc), parent=self)

    def approve(self):
        if not self.current:
            messagebox.showwarning("مرکز تأیید", "یک مورد را انتخاب کن.", parent=self)
            return
        pid = self.current["pending_id"]
        try:
            payload = self._payload_from_form()
            APPROVAL.save_payload(pid, payload, learn=True)
            if (self.current.get("conflicts") or []) and not messagebox.askyesno(
                "هشدار اختلاف", "برای این رسید اختلاف بین پیام/OCR/تحلیل ثبت شده است. با همین اطلاعات ثبت قطعی شود؟", parent=self
            ):
                return
            result = APPROVAL.approve(pid, actor_id="GUI")
            self.status.set(f"ثبت شد: {result.posting.posting_type}")
            self.current = None
            self.refresh()
            if self.on_posted:
                self.on_posted()
        except Exception as exc:
            messagebox.showerror("ثبت انجام نشد", str(exc), parent=self)

    def link_existing(self):
        if not self.current:
            return
        candidates = [d for d in (self.current.get("duplicate_candidates") or []) if str(d.get("entity_type") or "").upper() in {"EXPENSE", "TRANSACTION", "CHEQUE"}]
        if not candidates:
            messagebox.showinfo("اتصال", "ثبت مالی مناسبی برای اتصال خودکار پیشنهاد نشده است.", parent=self)
            return
        d = candidates[0]
        msg = (
            "این رسید بدون ایجاد اثر مالی جدید به ثبت زیر متصل شود؟\n\n"
            f"نوع: {d.get('entity_type')}\nID: {d.get('entity_id')}\nمبلغ: {money(d.get('amount'))}\n"
            f"تاریخ: {d.get('event_date') or '-'}\nشرح: {d.get('description') or '-'}"
        )
        if not messagebox.askyesno("اتصال به ثبت موجود", msg, parent=self):
            return
        try:
            APPROVAL.link_existing(
                self.current["pending_id"], entity_type=str(d.get("entity_type")),
                entity_id=str(d.get("entity_id")), actor_id="GUI",
            )
            self.status.set("رسید به ثبت موجود متصل شد؛ هزینه جدید ساخته نشد.")
            self.current = None
            self.refresh()
            if self.on_posted:
                self.on_posted()
        except Exception as exc:
            messagebox.showerror("اتصال انجام نشد", str(exc), parent=self)

    def reject(self):
        if not self.current:
            return
        if not messagebox.askyesno("رد مورد", "این مورد رد شود و هیچ اثر مالی نداشته باشد؟", parent=self):
            return
        try:
            APPROVAL.reject(self.current["pending_id"], actor_id="GUI")
            self.current = None
            self.status.set("مورد رد شد")
            self.refresh()
        except Exception as exc:
            messagebox.showerror("خطا", str(exc), parent=self)

    def open_receipt(self):
        if not self.current:
            return
        path = str(self.current.get("receipt_image_path") or "")
        if not path:
            atts = DB.list_pending_attachments(self.current.get("pending_id"))
            path = str((atts[0] if atts else {}).get("local_path") or "")
        if not path or not Path(path).exists():
            messagebox.showinfo("رسید", "فایل تصویر آرشیوشده برای این مورد موجود نیست.", parent=self)
            return
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            messagebox.showerror("باز کردن فایل", str(exc), parent=self)


class Stage14Dashboard(Stage12Dashboard):
    def __init__(self):
        self.approval_center: ApprovalCenter | None = None
        self.approval_tab: ttk.Frame | None = None
        super().__init__()
        self.title("Peymaan V2 — Stage 14 Receipt Intelligence")
        self._build_approval_center()
        self.after(4000, self._approval_periodic)

    def _build_approval_center(self):
        tab = ttk.Frame(self.notebook)
        self.approval_tab = tab
        self.notebook.insert(1, tab, text="مرکز تأیید")
        self.approval_center = ApprovalCenter(tab, on_posted=self.refresh_all)
        self.approval_center.pack(fill="both", expand=True)

    def _update_approval_tab_text(self, count: int):
        if self.approval_tab is not None:
            try:
                self.notebook.tab(self.approval_tab, text=f"مرکز تأیید ({count})" if count else "مرکز تأیید")
            except Exception:
                pass

    def _approval_periodic(self):
        try:
            if self.approval_center:
                self.approval_center.refresh()
        finally:
            self.after(4000, self._approval_periodic)

    def refresh_all(self):
        super().refresh_all()
        if self.approval_center:
            self.approval_center.refresh()


if __name__ == "__main__":
    Stage14Dashboard().mainloop()

d14 = _legacy_snapshot()

# ---- Extracted from dashboard_stage15.py ----

import os
import tkinter as tk
from tkinter import filedialog, messagebox

from telegram_history_import import import_telegram_export


class Stage15Dashboard(Stage14Dashboard):
    def __init__(self):
        super().__init__()
        name=os.getenv("PEYMAAN_ACTIVE_PROJECT_NAME","").strip()
        pid=os.getenv("PEYMAAN_ACTIVE_PROJECT_ID","").strip()
        suffix=f" — {name} ({pid})" if name or pid else ""
        self.title("Peymaan V2 — Stage 15 Receipt Vision"+suffix)

    def import_old_telegram_history(self):
        path=filedialog.askopenfilename(
            title="انتخاب JSON خروجی Telegram Desktop",
            filetypes=[("Telegram JSON","*.json"),("JSON","*.json")],
            parent=self,
        )
        if not path:return
        try:
            result=import_telegram_export(d14.DB,path,receipt_service=d14.APPROVAL.receipts)
            msg=(
                f"چت‌ها: {result.chats:,}\n"
                f"کل پیام‌های بررسی‌شده: {result.scanned:,}\n"
                f"کاندیدهای واردشده: {result.candidates:,}\n"
                f"  • دارای عکس/رسانه: {result.media_candidates:,}\n"
                f"  • متن مالی محتمل: {result.text_candidates:,}\n"
                f"پیش‌نویس جدید: {result.created:,}\n"
                f"تکراری: {result.duplicates:,}\n"
                f"نادیده‌گرفته‌شده: {result.skipped:,}\n"
                f"فایل رسانه پیدا نشد: {result.media_missing:,}\n"
            )
            if result.media_missing:
                msg += "\n⚠️ برای موارد Media Missing، هنگام Export تلگرام گزینه Photos/Files را هم فعال کن و پوشه خروجی را جابه‌جا نکن.\n"
            if result.media_pending_ids:
                msg += f"\n{len(result.media_pending_ids):,} تصویر برای AI Vision آماده است."
            messagebox.showinfo("Import تاریخچه تلگرام",msg,parent=self)
            if self.approval_center:
                self.approval_center.refresh()
                if result.media_pending_ids and messagebox.askyesno(
                    "AI Vision",
                    f"{len(result.media_pending_ids):,} تصویر آرشیو شد. همین حالا تحلیل AI آنها در پس‌زمینه شروع شود؟\n\n"
                    "هیچ موردی خودکار ثبت مالی نمی‌شود؛ همه در مرکز تأیید باقی می‌مانند.",
                    parent=self,
                ):
                    self.approval_center._run_ai_ids(list(result.media_pending_ids))
        except Exception as exc:
            messagebox.showerror("Import تاریخچه تلگرام",str(exc),parent=self)


if __name__=="__main__":
    Stage15Dashboard().mainloop()


# ---- Extracted from dashboard_stage16_3.py ----

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
        rows=[dict(r) for r in self.rich.list_phase_summary()]
        try:
            legacy=SERVICE.budget.phase_summary();amap={norm(r.get('phase')):int(r.get('actual') or 0) for r in legacy}
            for r in rows:
                actual=amap.get(norm(r.get('phase')),int(r.get('actual') or 0));r['actual']=actual;r['remaining_base']=max(int(r.get('estimate') or 0)-actual,0);r['forecast']=max(int(r.get('forecast') or 0),actual);r['variance']=r['forecast']-int(r.get('estimate') or 0)
        except Exception:pass
        return rows

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

v16 = _legacy_snapshot()
v163 = _legacy_snapshot()

# ---- Extracted from dashboard_stage17.py ----

import json, os, re, shutil, tempfile, threading, asyncio, zipfile
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from typing import Any, Callable

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

v174 = _legacy_snapshot()

# ---- Extracted from dashboard_stage17_5.py ----

import asyncio
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

from phase_intelligence_v175 import apply_suggestion_to_payload, suggest_phase

VERSION = '17.5'

# More explicit lifecycle vocabulary.  Registration status remains a separate field.
CHEQUE_STATUS_FA = {
    'ISSUED': 'صادرشده',
    'PENDING_DUE': 'در انتظار سررسید',
    'CASHED': 'پاس‌شده',
    'RETURNED': 'برگشتی',
    'CANCELLED': 'لغوشده / باطل‌شده',
}
CHEQUE_STATUS_BY_FA = {v: k for k, v in CHEQUE_STATUS_FA.items()}

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
        rows=[r for r in DB.list_cheques(open_only=True,limit=1000) if not int(r.get('is_guarantee') or 0)]; cand=[]
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
        ch=cand[0][1]; cash_sh=sh or gregorian_to_shamsi(datetime.now().date())
        DB.cash_cheque(ch['cheque_id'],cashed_date=shamsi_to_gregorian(cash_sh),cashed_date_shamsi=cash_sh,source='GUI_RECEIPT_17_5',actor_id='GUI')
        DB.relink_pending_attachments(pid,entity_type='CHEQUE',entity_id=ch['cheque_id']); _mark_nonfinancial_approved(pid,'CHEQUE',ch['cheque_id'])
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
        vals={'issue':row.get('issue_date_shamsi') or '','due':row.get('due_date_shamsi') or '','amount':group_int(row.get('amount') or 0),'issuer_name':row.get('issuer_name') or '','receiver_name':row.get('receiver_name') or '','issuer_bank':row.get('issuer_bank') or '','cheque_serial':row.get('cheque_serial') or '','description':row.get('description') or '','cheque_type':CHEQUE_TYPE_FA.get(str(row.get('cheque_type') or 'PHYSICAL').upper(),'فیزیکی'),'registration_state':REG_FA.get(str(row.get('registration_state') or 'UNREGISTERED').upper(),'ثبت‌نشده'),'lifecycle':CHEQUE_STATUS_FA.get(str(row.get('status') or 'ISSUED').upper(),'صادرشده'),'status_date':row.get('cashed_date_shamsi') or row.get('due_date_shamsi') or gregorian_to_shamsi(datetime.now().date())}
        fields=[('issue','تاریخ صدور','date'),('due','تاریخ سررسید','date'),('amount','مبلغ','num'),('issuer_name','صاحب حساب','entry'),('receiver_name','گیرنده','entry'),('issuer_bank','بانک','entry'),('cheque_serial','شماره/صیادی','entry'),('cheque_type','نوع چک','type'),('registration_state','وضعیت ثبت صیادی','reg'),('lifecycle','وضعیت چک','life'),('status_date','تاریخ رویداد وضعیت','date'),('description','بابت','entry')]
        for i,(k,l,kind) in enumerate(fields):
            v=tk.StringVar(value=str(vals[k]));self.vars[k]=v;tk.Label(card,text=l+':',bg=DARK['panel'],fg=DARK['muted']).grid(row=i,column=1,sticky='e',padx=8,pady=5)
            if kind=='date':w=DateField(card,v,width=32)
            elif kind=='type':w=ttk.Combobox(card,textvariable=v,state='readonly',values=list(CHEQUE_TYPE_BY_FA),width=34)
            elif kind=='reg':w=ttk.Combobox(card,textvariable=v,state='readonly',values=list(REG_BY_FA),width=34)
            elif kind=='life':w=ttk.Combobox(card,textvariable=v,state='readonly',values=list(CHEQUE_STATUS_BY_FA),width=34)
            else:w=ttk.Entry(card,textvariable=v,width=36,justify='right');bind_grouped_number(w,v) if kind=='num' else None
            w.grid(row=i,column=0,padx=8,pady=5,sticky='ew')
        self.guarantee=tk.BooleanVar(value=bool(row.get('is_guarantee')));tk.Checkbutton(card,text='بابت ضمانت (در تعهد مالی محاسبه نشود)',variable=self.guarantee,bg=DARK['panel'],fg=DARK['text'],selectcolor=DARK['surface'],activebackground=DARK['panel'],activeforeground='white').grid(row=len(fields),column=0,columnspan=2,sticky='e',pady=7,padx=8)
        tk.Label(card,text='تغییر وضعیت پاس/برگشت/لغو از مسیر حسابداری امن انجام می‌شود و در Audit ثبت می‌شود.',bg=DARK['panel2'],fg=DARK['cyan'],font=('Segoe UI',7,'bold'),padx=8,pady=7,wraplength=620,justify='right').grid(row=len(fields)+1,column=0,columnspan=2,sticky='ew',padx=8,pady=5)
        tk.Button(card,text='💾 ذخیره مشخصات و وضعیت',command=self.save,bg=DARK['green'],fg='white',relief='flat',padx=18,pady=8,font=('Segoe UI',9,'bold')).grid(row=len(fields)+2,column=0,columnspan=2,pady=12)
    def save(self):
        try:
            ish=normalize_shamsi(self.vars['issue'].get());due=normalize_shamsi(self.vars['due'].get())
            if not ish or not due:raise ValueError('تاریخ صدور/سررسید نامعتبر است.')
            old_status=str(self.row.get('status') or 'ISSUED').upper();new_status=CHEQUE_STATUS_BY_FA.get(self.vars['lifecycle'].get(),'ISSUED')
            if old_status not in {'CASHED','CANCELLED'}:
                DB.update_cheque_details(self.row['cheque_id'],amount=parse_int(self.vars['amount'].get()),issue_date=shamsi_to_gregorian(ish),issue_date_shamsi=ish,due_date=shamsi_to_gregorian(due),due_date_shamsi=due,issuer_name=self.vars['issuer_name'].get().strip(),cheque_type=CHEQUE_TYPE_BY_FA.get(self.vars['cheque_type'].get(),'PHYSICAL'),receiver_name=self.vars['receiver_name'].get().strip(),issuer_bank=self.vars['issuer_bank'].get().strip(),cheque_serial=self.vars['cheque_serial'].get().strip(),description=self.vars['description'].get().strip(),is_guarantee=self.guarantee.get(),source='GUI_17_5',actor_id='GUI')
            with DB.tx() as con:con.execute('UPDATE cheques SET registration_state=?,is_guarantee=?,updated_at=? WHERE cheque_id=?',(REG_BY_FA.get(self.vars['registration_state'].get(),'UNREGISTERED'),1 if self.guarantee.get() else 0,datetime.now().isoformat(timespec='seconds'),self.row['cheque_id']))
            if new_status!=old_status:
                if new_status in {'CASHED','CANCELLED'} and not messagebox.askyesno('تغییر وضعیت',f"وضعیت چک به «{CHEQUE_STATUS_FA[new_status]}» تغییر کند؟ این عملیات اثر حسابداری دارد.",parent=self):return
                sh=normalize_shamsi(self.vars['status_date'].get());event=shamsi_to_gregorian(sh) if sh else None
                DB.set_cheque_lifecycle_status(self.row['cheque_id'],new_status,event_date=event,event_date_shamsi=sh or None,source='GUI_17_5',actor_id='GUI')
            self.destroy();self.on_refresh()
        except Exception as exc:messagebox.showerror('چک',str(exc),parent=self)


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
        self.ch_filter=tk.StringVar(value='همه');vals=['همه','ثبت‌نشده','ثبت‌شده','صادرشده','در انتظار سررسید','پاس‌شده','برگشتی','لغوشده','ضمانتی'];c=ttk.Combobox(bar,textvariable=self.ch_filter,state='readonly',values=vals,width=18);c.pack(side='right',padx=4);c.bind('<<ComboboxSelected>>',lambda e:self.refresh_cheques());ttk.Button(bar,text='✏️ ویرایش مشخصات/وضعیت',command=self.edit_cheque).pack(side='right',padx=3);tk.Label(bar,text='هر چک = یک ردیف مستقل؛ حتی اگر چند چک از یک تصویر ثبت شده باشند.',bg=DARK['surface'],fg=DARK['muted'],font=('Segoe UI',7)).pack(side='left',padx=8)
        self.cheque_table=SmartTable(tab,[('issue','تاریخ صدور',100),('due','سررسید',105),('amount','مبلغ',125),('issuer','صاحب حساب',120),('type','نوع',90),('reg','ثبت صیادی',90),('guarantee','ضمانت',70),('receiver','گیرنده',120),('bank','بانک',100),('serial','شماره/صیادی',120),('desc','بابت',200),('status','وضعیت چک',110),('id','Cheque ID',145)],title='چک‌ها — Ctrl/Shift برای چندانتخاب');self.cheque_table.pack(fill='both',expand=True);self.cheque_table.set_edit_handler(self.edit_cheque_row);self.cheque_table.set_delete_handler(self._cancel_cheque_row)

    def refresh_cheques(self):
        rows=SERVICE.list_cheques(open_only=False);f=getattr(self,'ch_filter',tk.StringVar(value='همه')).get();status_filter={'صادرشده':'ISSUED','در انتظار سررسید':'PENDING_DUE','پاس‌شده':'CASHED','برگشتی':'RETURNED','لغوشده':'CANCELLED'}
        if f=='ثبت‌نشده':rows=[r for r in rows if str(r.get('registration_state') or 'UNREGISTERED')=='UNREGISTERED']
        elif f=='ثبت‌شده':rows=[r for r in rows if str(r.get('registration_state') or '')=='REGISTERED']
        elif f=='ضمانتی':rows=[r for r in rows if int(r.get('is_guarantee') or 0)==1]
        elif f in status_filter:rows=[r for r in rows if str(r.get('status') or '').upper()==status_filter[f]]
        for r in rows:r['_sum_amount']=int(r.get('amount') or 0)
        self.cheque_table.set_rows(rows,lambda r:[r.get('issue_date_shamsi') or '-',r.get('due_date_shamsi') or '-',fmt_money(r['amount']),r.get('issuer_name') or '-',CHEQUE_TYPE_FA.get(str(r.get('cheque_type') or 'PHYSICAL').upper(),'فیزیکی'),REG_FA.get(str(r.get('registration_state') or 'UNREGISTERED').upper(),'ثبت‌نشده'),'بله' if r.get('is_guarantee') else 'خیر',r.get('receiver_name') or '-',r.get('issuer_bank') or '-',r.get('cheque_serial') or '-',r.get('description') or r.get('expense_description') or '-',CHEQUE_STATUS_FA.get(str(r.get('status') or '').upper(),v16.d12.fa_status(r.get('status'))),r['cheque_id']])
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

v175 = _legacy_snapshot()

# ---- Extracted from dashboard_stage18.py ----

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

from loan_service import LoanService, _add_months
from ui import bind_grouped_decimal, parse_decimal
from revenue_service import RevenueService
from v18_store import load_profile, save_profile, load_ui, save_ui
from phase04_v18 import apply_phase04_rules_v18

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
    if typ == 'DOCUMENT': return 'یادداشت', 'داکیومنت'
    if typ == 'INFO': return 'یادداشت', 'اطلاع‌رسانی'
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
            FieldDef('description','بابت'), FieldDef('payment_method','روش پرداخت','combo',('واریز بانکی','نقدی/کارتخوان')),
            FieldDef('invoice_amount','مبلغ فاکتور','money'), FieldDef('final_amount','مبلغ نهایی','money'), FieldDef('discount_amount','تخفیف','money'),
            FieldDef('payment_state','وضعیت پرداخت','combo',tuple(PAYMENT_STATE)), FieldDef('total_debt','کل بدهی','money'), FieldDef('remaining_debt','مانده بدهی','money'),
            FieldDef('main_phase','فاز اصلی','phase'), FieldDef('sub_phase','فاز فرعی','subphase'),
        ]
    if title == 'هزینه ساخت' and subtype == 'چک':
        return [
            FieldDef('payer_name','واریزکننده'), FieldDef('receiver_name','گیرنده'), FieldDef('description','بابت'),
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
        self.pages=[[FieldDef('event_date_shamsi','تاریخ','date'),FieldDef('amount','مبلغ','money'),FieldDef('v18_title','عنوان تراکنش','titlecombo'),FieldDef('v18_subtype','نوع تراکنش','subcombo')]] + _wizard_steps(title,sub) + [[]]
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
            return
        if self.pages[self.page_index]:self.payload=self._payload_from_vars(self.title_var.get(),self.subtype_var.get())
    def next(self):
        try:self._capture()
        except Exception as exc:return messagebox.showerror('ثبت مرحله‌ای',str(exc),parent=self)
        if self.page_index>=len(self.pages)-1:
            try:
                p=dict(self.payload);p['v18_manual_fields']=sorted(self.manual_fields);APPROVAL.save_payload(self.pid,p,learn=True);msg=approve_v18(self.pid,p,self.rich);messagebox.showinfo('ثبت',msg,parent=self);self.on_done();self.destroy()
            except Exception as exc:messagebox.showerror('تأیید انجام نشد',str(exc),parent=self)
            return
        self.page_index+=1;self._show_page()
    def prev(self):
        try:self._capture()
        except Exception:pass
        if self.page_index>0:self.page_index-=1;self._show_page()
    def _open_full(self):
        try:self._capture();APPROVAL.save_payload(self.pid,self.payload,learn=False)
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
        try:self.payload=self.payload_from_form();APPROVAL.save_payload(self.pid,self.payload,learn=True);self.msg.set('اصلاحات ذخیره شد؛ هنوز اثر مالی ندارد.');self.on_done()
        except Exception as exc:messagebox.showerror('ذخیره',str(exc),parent=self)
    def approve(self):
        try:self.payload=self.payload_from_form();APPROVAL.save_payload(self.pid,self.payload,learn=True);msg=approve_v18(self.pid,self.payload,self.rich);messagebox.showinfo('ثبت',msg,parent=self);self.on_done();self.destroy()
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
    return v175.approve_v175(pid,p,rich)


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
        self.tree.tag_configure('pending',background='#766515',foreground='#FFFBE6');self.tree.tag_configure('approved',background='#16372D',foreground='#E8FFF5');self.tree.tag_configure('rejected',background='#3A2429',foreground='#FFECEF')
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
            return [f'☐ {fa(idx)}',str(r.get('message_date') or p.get('event_date_shamsi') or '-').split()[0],title,sub,desc[:80],_group_money(amt),p.get('receiver_name') or '—',_display_payment(p,title,sub),due or '—',p.get('main_phase') or '—',p.get('sub_phase') or '—']
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
        self.ch_filter=tk.StringVar(value='همه');vals=['همه','ثبت‌نشده','ثبت‌شده','صادرشده','پاس‌شده','برگشتی','عودتی به شرط تسویه','باطل‌شده','ضمانتی']
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

v18 = _legacy_snapshot()

# ---- Extracted from dashboard_stage18_1.py ----

import json
import math
import os
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

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
            F('payment_method','روش پرداخت','combo',('واریز بانکی','نقدی/کارتخوان')),
            F('invoice_amount','مبلغ فاکتور','money'), F('final_amount','مبلغ نهایی','money'), F('discount_amount','تخفیف','money'),
            F('payment_state','وضعیت پرداخت','combo',tuple(v18.PAYMENT_STATE)), F('total_debt','کل بدهی','money'), F('remaining_debt','مانده بدهی','money'),
            F('main_phase','فاز اصلی','phase'), F('sub_phase','فاز فرعی','subphase'),
        ]
    if title == 'هزینه ساخت' and subtype == 'چک':
        return [
            F('payer_name','واریزکننده'), F('receiver_name','گیرنده'), F('description','بابت'),
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
    rest=[f for f in fields if f.key not in used]
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
            rows=[['payer_name','receiver_name','description'],['payment_method','invoice_amount','final_amount','discount_amount'],['payment_state','total_debt','remaining_debt'],['main_phase','sub_phase']]
        elif title=='هزینه ساخت' and sub=='چک':
            rows=[['payer_name','receiver_name','description'],['issuer_name','issuer_bank','cheque_type','cheque_registration_state'],['due_date_shamsi','cheque_amount','cheque_status','is_guarantee'],['payment_method','invoice_amount','final_amount','discount_amount'],['payment_state','total_debt','remaining_debt'],['main_phase','sub_phase']]
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
        ('amount','مبلغ (تومان)',118),('receiver','گیرنده',110),('payment','نوع پرداخت',105),('due','سررسید',95),('phase','فاز اصلی',130),('subphase','فاز فرعی',130),
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
        self.tree.tag_configure('pending',background='#8B781B',foreground='#FFF9D2')
        self.tree.tag_configure('approved',background='#1E503D',foreground='#E9FFF4')
        self.tree.tag_configure('rejected',background='#5A2B33',foreground='#FFF0F2')
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

v181 = _legacy_snapshot()

# ---- Extracted from dashboard_stage18_2.py ----

from datetime import date, datetime, timedelta
from pathlib import Path
from copy import deepcopy
import asyncio
import threading
import tempfile
import os
import json
import sqlite3
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


from loan_service import LoanService, _add_months

VERSION = '18.2'
v18.VERSION = VERSION
v181.VERSION = VERSION

_PARTNER_NAMES = ('پیمان', 'پیام', 'سامان', 'سایر')
_PARTNER_KINDS = ('قرض', 'تزریق پول')

# Visual reference palettes sampled from the user-provided 2560x1440 target screens.
_THEME_DARK = {
    'bg': '#0C192A', 'surface': '#0E1E31', 'panel': '#152639', 'panel2': '#1B2D40',
    'glass': '#263648', 'line': '#384657', 'text': '#F3F5F7', 'muted': '#9AA8B8',
    'blue': '#55A3EC', 'green': '#57C894', 'orange': '#E6B34F', 'red': '#F1767D',
    'cyan': '#28AEB8', 'violet': '#9C8DDB', 'yellow': '#F4CE5B',
}
_THEME_LIGHT = {
    'bg': '#F8F9FA', 'surface': '#FFFFFF', 'panel': '#FDFDFD', 'panel2': '#F4F7FA',
    'glass': '#F3F6F9', 'line': '#D6DCE3', 'text': '#263442', 'muted': '#748292',
    'blue': '#3C8ED4', 'green': '#45B987', 'orange': '#E3A93F', 'red': '#E96F78',
    'cyan': '#20AEB9', 'violet': '#8F82D0', 'yellow': '#EFC95A',
}


def _is_light() -> bool:
    try:
        return str(load_ui().get('appearance') or 'dark').lower() == 'light'
    except Exception:
        return False


def _receipt_caption(row: dict, payload: dict | None = None) -> str:
    """Return only text directly attached to the receipt/message.

    New receipt analyses persist ``receipt_caption`` explicitly.  Older records
    fall back to Telegram ``raw_text`` which, for live photo messages, is the
    exact Telegram caption rather than the evidence window.
    """
    p = payload or row.get('payload') or {}
    for value in (p.get('receipt_caption'), row.get('raw_text')):
        text = str(value or '').strip()
        if text:
            return text
    return ''


def wizard_steps_182(title: str, subtype: str):
    """Final V18.2 wizard grouping locked by the user."""
    fields = v181.special_fields_181(title, subtype)
    by = {f.key: f for f in fields}
    preferred: list[list[str]] = []
    if title == 'هزینه ساخت' and subtype == 'نقدی':
        preferred = [
            ['payer_name', 'receiver_name'],
            ['description', 'payment_method'],
            ['invoice_amount', 'final_amount', 'discount_amount'],
            ['payment_state', 'total_debt', 'remaining_debt'],
            ['main_phase', 'sub_phase'],
        ]
    elif title == 'هزینه ساخت' and subtype == 'چک':
        preferred = [
            ['payer_name', 'receiver_name', 'description', 'is_guarantee'],
            ['issuer_name', 'issuer_bank', 'cheque_type'],
            ['cheque_registration_state', 'due_date_shamsi', 'cheque_status'],
            ['invoice_amount', 'final_amount', 'discount_amount'],
            ['payment_state', 'total_debt', 'remaining_debt'],
            ['main_phase', 'sub_phase'],
        ]
    elif title == 'ورودی' and subtype == 'فروش':
        preferred = [
            ['sale_id', 'sale_unit', 'sold_area'],
            ['payer_name', 'buyer_name'],
        ]
    elif title == 'ورودی' and subtype == 'تسهیلات':
        preferred = [
            ['loan_name', 'loan_bank', 'loan_total_amount'],
            ['installment_count', 'interest_rate'],
            ['guarantor_1', 'guarantor_2', 'guarantor_3'],
            ['loan_start_date', 'loan_end_date'],
        ]
    elif title == 'ورودی' and subtype == 'شرکا/قرض':
        preferred = [
            ['partner_name', 'partner_other_name'],
            ['partner_kind', 'loan_days', 'partner_return_date'],
        ]
    elif title == 'خروجی' and subtype == 'اقساط':
        preferred = [
            ['payer_name', 'loan_id'],
            ['loan_bank', 'loan_total_amount'],
            ['installment_count', 'paid_installments_before'],
            ['installments_paid_now', 'remaining_installments'],
        ]

    groups = []
    for keys in preferred:
        arr = [by[k] for k in keys if k in by]
        if arr:
            groups.append(arr)
    used = {f.key for group in groups for f in group}
    rest = [f for f in fields if f.key not in used and f.key != 'cheque_amount']
    for i in range(0, len(rest), 3):
        groups.append(rest[i:i + 3])
    return groups


def _retarget_fonts(root: tk.Misc, family: str = 'Segoe UI') -> None:
    """Normalize legacy explicit Tahoma/Arial widgets without changing sizes."""
    stack = [root]
    while stack:
        w = stack.pop()
        try:
            stack.extend(w.winfo_children())
        except Exception:
            pass
        try:
            font_value = w.cget('font')
        except Exception:
            continue
        if not font_value:
            continue
        try:
            import tkinter.font as tkfont
            actual = tkfont.Font(font=font_value).actual()
            fam = str(actual.get('family') or '')
            if fam.lower() in {'tahoma', 'arial', 'sans', 'sans-serif'}:
                weight = actual.get('weight', 'normal')
                slant = actual.get('slant', 'roman')
                size = int(actual.get('size') or 10)
                spec = [family, size]
                if weight == 'bold':
                    spec.append('bold')
                if slant == 'italic':
                    spec.append('italic')
                w.configure(font=tuple(spec))
        except Exception:
            pass



def _field_keys(title: str, subtype: str) -> set[str]:
    return {f.key for f in v181.special_fields_181(title, subtype)}


def _widget_host(widget):
    try:
        return widget.master if widget is not None else None
    except Exception:
        return None


class TransactionWizard182(v181.TransactionWizard181):
    """V18.2 wizard: persistent payload, true RTL pages and cross-step dependencies."""

    def __init__(self, parent, row, rich, on_done, on_full):
        self._closing_to_full = False
        # Work on a shallow row/deep payload copy so the cheque Wizard can use
        # the exact receipt caption as «بابت» without mutating the table object.
        row = dict(row or {})
        payload = deepcopy(dict(row.get('payload') or {}))
        title, subtype = v18._title_type_from_payload(payload)
        if title == 'هزینه ساخت' and subtype == 'چک':
            caption = _receipt_caption(row, payload)
            if caption:
                payload['description'] = caption
                payload['receipt_caption'] = caption
            # Keep backend compatibility even though cheque amount is no longer
            # displayed twice in the Wizard.
            payload['cheque_amount'] = int(payload.get('amount') or payload.get('paid_amount') or payload.get('cheque_amount') or 0)
        row['payload'] = payload
        super().__init__(parent, row, rich, on_done, on_full)
        self.font_family = 'Segoe UI'
        self.title('ثبت مرحله‌ای تراکنش — BARKAV 18.2')
        self.geometry('780x560')
        self.minsize(720, 520)

    def _build_shell(self):
        top = tk.Frame(self, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1)
        top.pack(fill='x', padx=10, pady=10)
        tk.Label(top, text='ثبت مرحله‌ای', bg=DARK['surface'], fg=DARK['text'],
                 font=(self.font_family, self.font_size + 2, 'bold')).pack(side='right', padx=10, pady=(7, 2))
        tk.Label(top, text='هر مرحله فقط اطلاعات مرتبط با همان تراکنش را نشان می‌دهد.',
                 bg=DARK['surface'], fg=DARK['muted'],
                 font=(self.font_family, max(9, self.font_size - 1))).pack(side='right', padx=4, pady=(9, 2))
        self.step_lbl = tk.Label(top, text='', bg=DARK['surface'], fg=DARK['muted'],
                                 font=(self.font_family, self.font_size - 1, 'bold'))
        self.step_lbl.pack(side='left', padx=10)
        self.progress = ttk.Progressbar(top, mode='determinate', maximum=100, length=130)
        self.progress.pack(side='left', padx=8, pady=12)

        self.host = tk.Frame(self, bg=DARK['panel'], highlightbackground=DARK['line'], highlightthickness=1)
        self.host.pack(fill='both', expand=True, padx=10, pady=(0, 8))

        nav = tk.Frame(self, bg=DARK['bg'])
        nav.pack(fill='x', padx=10, pady=(0, 10))
        self.next_b = tk.Button(nav, text='بعدی', command=self.next, bg=DARK['blue'], fg='#FFFFFF',
                                activebackground='#8BC3F2', relief='flat', padx=22, pady=9,
                                font=(self.font_family, self.font_size, 'bold'))
        self.next_b.pack(side='right', padx=3)
        self.prev_b = tk.Button(nav, text='قبلی', command=self.prev, bg=DARK['glass'], fg=DARK['text'],
                                relief='flat', padx=16, pady=9, font=(self.font_family, self.font_size, 'bold'))
        self.prev_b.pack(side='right', padx=3)
        tk.Button(nav, text='رد کردن مرحله', command=self.next, bg=DARK['surface'], fg=DARK['muted'],
                  relief='flat', padx=12, pady=9).pack(side='left', padx=3)
        tk.Button(nav, text='فرم کامل', command=self._open_full, bg=DARK['surface'], fg=DARK['text'],
                  relief='flat', padx=12, pady=9).pack(side='left', padx=3)

    def _payload_from_vars(self, title: str, subtype: str):
        # The V18 base renderer recreates self.vars on every page.  Preserve the
        # four common values when the current specialization page does not have them.
        before = dict(self.payload or {})
        p = super()._payload_from_vars(title, subtype)
        if 'event_date_shamsi' not in self.vars:
            p['event_date_shamsi'] = before.get('event_date_shamsi') or ''
        if 'amount' not in self.vars:
            amount = int(before.get('amount') or before.get('paid_amount') or 0)
            p['amount'] = amount
            p['paid_amount'] = amount
        return p

    def _clear(self):
        for w in self.host.winfo_children():
            w.destroy()
        self.vars = {}
        self.widgets = {}

    def _show_page(self, load=False):
        self._clear()
        page = self.pages[self.page_index]

        # Every page lives in a scrollable canvas; navigation remains fixed below.
        shell = tk.Frame(self.host, bg=DARK['panel'])
        shell.pack(fill='both', expand=True)
        canvas = tk.Canvas(shell, bg=DARK['panel'], highlightthickness=0)
        scroll = ttk.Scrollbar(shell, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        body = tk.Frame(canvas, bg=DARK['panel'])
        body_id = canvas.create_window((0, 0), window=body, anchor='nw')
        body.grid_columnconfigure((0, 1), weight=1, uniform='wizard182')
        body.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')), add='+')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(body_id, width=e.width), add='+')
        canvas.bind('<MouseWheel>', lambda e: (canvas.yview_scroll(int(-e.delta / 120), 'units'), 'break')[1], add='+')
        self._page_canvas = canvas

        content = tk.Frame(body, bg=DARK['panel'])
        content.pack(fill='both', expand=True, padx=20, pady=18)
        content.grid_columnconfigure((0, 1), weight=1, uniform='wizard182content')

        if self.page_index == 0:
            fds = page
            for i, fd in enumerate(fds):
                row, col = i // 2, 1 - (i % 2)  # true RTL: first field is right column
                if fd.key in {'event_date_shamsi', 'amount'}:
                    self._field(content, fd, row, col, width=29)
                    continue
                box = tk.Frame(content, bg=DARK['panel'])
                box.grid(row=row, column=col, sticky='nsew', padx=7, pady=8)
                box.grid_columnconfigure(0, weight=1)
                tk.Label(box, text=fd.label, bg=DARK['panel'], fg=DARK['text'],
                         font=(self.font_family, self.font_size, 'bold')).grid(row=0, column=0, sticky='e')
                if fd.key == 'v18_title':
                    value = tk.StringVar(value=self.title_var.get())
                    widget = ttk.Combobox(box, textvariable=value, state='readonly',
                                          values=list(v18.TITLE_TYPES), width=29)
                    widget.bind('<<ComboboxSelected>>',
                                lambda e, vv=value: self._title_changed(vv.get()), add='+')
                else:
                    values = list(v18.TITLE_TYPES.get(self.title_var.get(), []))
                    current = self.subtype_var.get()
                    if current not in values:
                        current = values[0] if values else ''
                        self.subtype_var.set(current)
                    value = tk.StringVar(value=current)
                    widget = ttk.Combobox(box, textvariable=value, state='readonly',
                                          values=values, width=29)
                    widget.bind('<<ComboboxSelected>>',
                                lambda e, vv=value: self._sub_changed(vv.get()), add='+')
                widget.grid(row=1, column=0, sticky='ew', pady=(5, 0))
                self.vars[fd.key] = value
                self.widgets[fd.key] = widget
                tk.Label(box, text=f"AI: {v18._ai_value(self.ai_original, fd.key)}",
                         bg=DARK['panel'], fg=DARK['muted'],
                         font=(self.font_family, max(8, self.font_size - 2))).grid(
                             row=2, column=0, sticky='e', pady=2)

            self._loading = True
            raw_date = str(self.payload.get('event_date_shamsi') or self.row.get('message_date') or '').strip()
            self.vars['event_date_shamsi'].set(raw_date.split()[0] if raw_date else '')
            self.vars['amount'].set(v18._group_money(
                self.payload.get('amount') or self.payload.get('paid_amount')
                or self.payload.get('final_amount') or 0))
            self._loading = False
        elif page:
            keys = [fd.key for fd in page]
            # Sale payer/buyer is intentionally vertical, payer first.
            if self.title_var.get() == 'ورودی' and self.subtype_var.get() == 'فروش' and keys == ['payer_name', 'buyer_name']:
                stack = tk.Frame(content, bg=DARK['panel'])
                stack.grid(row=0, column=0, columnspan=2, sticky='nsew', padx=40)
                stack.grid_columnconfigure(0, weight=1)
                for i, fd in enumerate(page):
                    self._field(stack, fd, i, 0, width=52)
            else:
                for i, fd in enumerate(page):
                    self._field(content, fd, i // 2, 1 - (i % 2), width=31)
            self._load_values(self.title_var.get(), self.subtype_var.get())
            self._after_page_render()
        else:
            self._render_review(content)

        total = max(1, len(self.pages))
        self.step_lbl.configure(text=f"مرحله {fa(self.page_index + 1)} از {fa(total)}")
        try:
            self.progress['value'] = ((self.page_index + 1) / total) * 100
        except Exception:
            pass
        self.prev_b.configure(state='normal' if self.page_index > 0 else 'disabled')
        self.next_b.configure(text='تأیید و ثبت' if self.page_index == len(self.pages) - 1 else 'بعدی')

    def _render_review(self, body):
        tk.Label(body, text='مرور نهایی', bg=DARK['panel'], fg=DARK['text'],
                 font=(self.font_family, self.font_size + 3, 'bold')).pack(anchor='e', pady=(8, 12))
        p = self.payload
        lines = [
            f"تاریخ: {fa(p.get('event_date_shamsi') or '-')}",
            f"مبلغ: {v18._group_money(p.get('amount'))}",
            f"عنوان: {self.title_var.get()}",
            f"نوع: {self.subtype_var.get()}",
        ]
        for fd in v181.special_fields_181(self.title_var.get(), self.subtype_var.get()):
            value = p.get(fd.key)
            if fd.key == 'partner_other_name' or value in (None, '', False):
                continue
            if fd.kind in {'money', 'int'}:
                value = v18._group_money(value)
            elif isinstance(value, (int, float)):
                value = fa(value)
            lines.append(f"{fd.label}: {value}")
        tk.Label(body, text='\n'.join(lines), bg=DARK['panel2'], fg=DARK['text'], justify='right', anchor='ne',
                 font=(self.font_family, self.font_size), padx=18, pady=16, wraplength=690).pack(fill='both', expand=True)

    def _after_page_render(self):
        title, subtype = self.title_var.get(), self.subtype_var.get()

        if title == 'ورودی' and subtype == 'شرکا/قرض':
            self._normalize_partner_display()
            if 'partner_name' in self.vars:
                self.vars['partner_name'].trace_add('write', lambda *_: self._partner_visibility_182())
            if 'partner_kind' in self.vars:
                self.vars['partner_kind'].trace_add('write', lambda *_: self._partner_visibility_182())
            if 'loan_days' in self.vars:
                self.vars['loan_days'].trace_add('write', lambda *_: self._partner_date_sync_182())
            self._partner_visibility_182()

        if title == 'ورودی' and subtype == 'فروش':
            if 'sale_unit' in self.vars:
                self.vars['sale_unit'].trace_add('write', lambda *_: self._sale_area_visibility_182())
            self._sale_area_visibility_182()

        if title == 'ورودی' and subtype == 'تسهیلات':
            if 'loan_start_date' in self.vars:
                self.vars['loan_start_date'].trace_add('write', lambda *_: self._loan_date_sync_182())
            if 'installment_count' in self.vars:
                self.vars['installment_count'].trace_add('write', lambda *_: self._loan_date_sync_182())
            self._loan_date_sync_182()

        if title == 'خروجی' and subtype == 'اقساط':
            if 'installments_paid_now' in self.vars:
                self.vars['installments_paid_now'].trace_add('write', lambda *_: self._installment_count_sync_182())
            self._installment_count_sync_182()

        if title == 'هزینه ساخت':
            if 'invoice_amount' in self.vars:
                self.vars['invoice_amount'].trace_add('write', lambda *_: self._sync_discount_182())
            if 'final_amount' in self.vars:
                self.vars['final_amount'].trace_add('write', lambda *_: self._sync_discount_182())
            if 'payment_state' in self.vars:
                self.vars['payment_state'].trace_add('write', lambda *_: self._sync_remaining_debt_182())
            if 'total_debt' in self.vars:
                self.vars['total_debt'].trace_add('write', lambda *_: self._sync_remaining_debt_182())
            self._sync_discount_182()
            self._sync_remaining_debt_182()

    def _title_changed(self, title):
        self.title_var.set(title)
        values = list(v18.TITLE_TYPES.get(title, []))
        first = values[0] if values else ''
        self.subtype_var.set(first)
        w = self.widgets.get('v18_subtype')
        if w is not None:
            try:
                w.configure(values=values)
                if 'v18_subtype' in self.vars:
                    self.vars['v18_subtype'].set(first)
            except Exception:
                pass

    def _sub_changed(self, sub):
        self.subtype_var.set(sub)

    def _refresh_subphase(self):
        super()._refresh_subphase()
        try:
            var = self.vars.get('sub_phase')
            widget = self.widgets.get('sub_phase')
            if var is not None and widget is not None and not str(var.get() or '').strip():
                vals = list(getattr(widget, '_all', []) or widget.cget('values') or [])
                if vals:
                    var.set(vals[0])
        except Exception:
            pass

    def _sync_discount_182(self):
        if getattr(self, '_loading', False):
            return
        if not all(k in self.vars for k in ('invoice_amount', 'final_amount', 'discount_amount')):
            return
        try:
            invoice = parse_int(self.vars['invoice_amount'].get())
            final = parse_int(self.vars['final_amount'].get())
            value = max(invoice - final, 0) if invoice > 0 and final >= 0 else 0
            self._loading = True
            self.vars['discount_amount'].set(v18._group_money(value))
            self.payload['discount_amount'] = value
        finally:
            self._loading = False

    def _sync_remaining_debt_182(self):
        if getattr(self, '_loading', False):
            return
        if not all(k in self.vars for k in ('payment_state', 'total_debt', 'remaining_debt')):
            return
        try:
            state = str(self.vars['payment_state'].get() or '')
            total = max(0, parse_int(self.vars['total_debt'].get()))
            paid = max(0, int(self.payload.get('amount') or self.payload.get('paid_amount') or 0))
            if state == 'تسویه':
                remaining = 0
            elif state == 'پرداخت‌نشده':
                remaining = total
            else:
                remaining = max(total - paid, 0)
            self._loading = True
            self.vars['remaining_debt'].set(v18._group_money(remaining))
            self.payload['remaining_debt'] = remaining
        finally:
            self._loading = False

    def _normalize_partner_display(self):
        actual = str(self.payload.get('partner_name') or '').strip()
        other = str(self.payload.get('partner_other_name') or '').strip()
        self._loading = True
        try:
            if 'partner_name' in self.vars:
                if actual and actual not in _PARTNER_NAMES:
                    self.vars['partner_name'].set('سایر')
                    if 'partner_other_name' in self.vars:
                        self.vars['partner_other_name'].set(other or actual)
                elif not actual:
                    self.vars['partner_name'].set('پیمان')
            if 'partner_kind' in self.vars and self.vars['partner_kind'].get() not in _PARTNER_KINDS:
                self.vars['partner_kind'].set(str(self.payload.get('partner_kind') or 'تزریق پول') if str(self.payload.get('partner_kind') or '') in _PARTNER_KINDS else 'تزریق پول')
        finally:
            self._loading = False

    def _partner_visibility_182(self):
        name = str(self.vars['partner_name'].get() if self.vars.get('partner_name') else self.payload.get('partner_name') or '')
        kind = str(self.vars['partner_kind'].get() if self.vars.get('partner_kind') else self.payload.get('partner_kind') or 'تزریق پول')
        if kind not in _PARTNER_KINDS:
            kind = 'تزریق پول'
            if self.vars.get('partner_kind'):
                self.vars['partner_kind'].set(kind)
        w = self.widgets.get('partner_other_name')
        host = _widget_host(w)
        try:
            (host.grid() if name == 'سایر' else host.grid_remove())
            w.configure(state='normal' if name == 'سایر' else 'disabled')
        except Exception:
            pass
        for key in ('loan_days', 'partner_return_date'):
            w = self.widgets.get(key)
            host = _widget_host(w)
            try:
                if kind == 'قرض':
                    host.grid()
                else:
                    host.grid_remove()
                if isinstance(w, DateField):
                    w.entry.configure(state='normal' if kind == 'قرض' else 'disabled')
                else:
                    w.configure(state='normal' if kind == 'قرض' else 'disabled')
            except Exception:
                pass

    def _partner_date_sync_182(self):
        if 'partner_return_date' not in self.vars:
            return
        try:
            days = parse_int(self.vars['loan_days'].get() if self.vars.get('loan_days') else self.payload.get('loan_days'))
            sh = normalize_shamsi(str(self.payload.get('event_date_shamsi') or ''))
            if not sh or days <= 0:
                return
            gd = date.fromisoformat(shamsi_to_gregorian(sh)) + timedelta(days=days)
            self._loading = True
            self.vars['partner_return_date'].set(gregorian_to_shamsi(gd))
        except Exception:
            pass
        finally:
            self._loading = False

    def _loan_date_sync_182(self):
        if 'loan_end_date' not in self.vars:
            return
        try:
            start = str(self.vars['loan_start_date'].get() if self.vars.get('loan_start_date') else self.payload.get('loan_start_date') or '')
            count = parse_int(self.vars['installment_count'].get() if self.vars.get('installment_count') else self.payload.get('installment_count'))
            sh = normalize_shamsi(start)
            if not sh or count <= 0:
                return
            gd = date.fromisoformat(shamsi_to_gregorian(sh))
            self._loading = True
            self.vars['loan_end_date'].set(gregorian_to_shamsi(_add_months(gd, count)))
        except Exception:
            pass
        finally:
            self._loading = False

    def _installment_count_sync_182(self):
        if 'remaining_installments' not in self.vars:
            return
        total = parse_int(self.vars['installment_count'].get() if self.vars.get('installment_count') else self.payload.get('installment_count'))
        before = parse_int(self.vars['paid_installments_before'].get() if self.vars.get('paid_installments_before') else self.payload.get('paid_installments_before'))
        now = max(0, parse_int(self.vars['installments_paid_now'].get() if self.vars.get('installments_paid_now') else self.payload.get('installments_paid_now')))
        self._loading = True
        try:
            self.vars['remaining_installments'].set(v18._group_money(max(total - before - now, 0)))
        finally:
            self._loading = False

    def _loan_selected(self, value: str):
        lid = str(value or '').split('|', 1)[0].strip()
        if not lid:
            return
        try:
            loan = LoanService(DB).get_loan(lid) or {}
            paid = int(loan.get('paid_installments') or 0)
            if not paid:
                with DB.read() as con:
                    paid = con.execute("SELECT COUNT(*) FROM loan_installments WHERE loan_id=? AND status='PAID'", (lid,)).fetchone()[0]
            vals = {
                'loan_id': value,
                'loan_bank': loan.get('lender_name') or '',
                'loan_total_amount': loan.get('principal_amount') or 0,
                'installment_count': loan.get('installment_count') or 0,
                'paid_installments_before': paid,
                'installments_paid_now': 1,
                'remaining_installments': max(int(loan.get('installment_count') or 0) - paid - 1, 0),
            }
            self.payload['selected_loan_name'] = loan.get('description') or loan.get('lender_name') or lid
            self.payload.update(vals)
            self._loading = True
            for key, val in vals.items():
                if key in self.vars:
                    self.vars[key].set(v18._group_money(val) if isinstance(val, (int, float)) else str(val))
        finally:
            self._loading = False

    def _sale_selected_181(self, value: str):
        sid = str(value or '').split('|', 1)[0].strip()
        if not sid:
            return
        try:
            with DB.read() as con:
                r = con.execute("""
                    SELECT s.sale_id,s.buyer_name,s.unit_id,u.display_unit_id,u.unit_number,u.floor,u.area
                    FROM sales s LEFT JOIN units u ON u.unit_id=s.unit_id WHERE s.sale_id=?
                """, (sid,)).fetchone()
            if not r:
                return
            unit_display = 'سایر'
            if r['unit_id']:
                unit_display = f"{r['unit_id']} | {r['display_unit_id'] or r['unit_number'] or '-'} | طبقه {r['floor'] or '-'} | {r['area'] or 0} M2"
            vals = {
                'sale_id': sid,
                'sale_unit': unit_display,
                'buyer_name': r['buyer_name'] or '',
                'payer_name': r['buyer_name'] or '',
                'sold_area': r['area'] or 0,
            }
            self.payload.update(vals)
            self._loading = True
            for key, val in vals.items():
                if key in self.vars:
                    self.vars[key].set(str(val))
        finally:
            self._loading = False
        self._sale_area_visibility_182()

    def _sale_unit_selected_181(self, value: str):
        value = str(value or '').strip()
        if not value:
            return
        if value == 'سایر':
            self.payload['sale_unit'] = 'سایر'
            if 'sale_unit' in self.vars:
                self.vars['sale_unit'].set('سایر')
            self._sale_area_visibility_182()
            return
        uid = value.split('|', 1)[0].strip()
        try:
            with DB.read() as con:
                r = con.execute("""
                    SELECT u.area,s.sale_id,s.buyer_name
                    FROM units u LEFT JOIN sales s ON s.unit_id=u.unit_id AND s.status!='CANCELLED'
                    WHERE u.unit_id=? ORDER BY s.created_at DESC LIMIT 1
                """, (uid,)).fetchone()
            vals = {'sale_unit': value, 'sold_area': (r['area'] if r else 0) or 0}
            if r and r['sale_id']:
                vals.update({'sale_id': r['sale_id'], 'buyer_name': r['buyer_name'] or '', 'payer_name': r['buyer_name'] or ''})
            self.payload.update(vals)
            self._loading = True
            for key, val in vals.items():
                if key in self.vars:
                    self.vars[key].set(str(val))
        finally:
            self._loading = False
        self._sale_area_visibility_182()

    def _sale_area_visibility_182(self):
        selected = str(self.vars['sale_unit'].get() if self.vars.get('sale_unit') else self.payload.get('sale_unit') or '')
        other = selected == 'سایر'
        w = self.widgets.get('sold_area')
        host = _widget_host(w)
        try:
            (host.grid() if other else host.grid_remove())
            w.configure(state='normal' if other else 'disabled')
        except Exception:
            pass

    def _capture(self):
        if self.page_index == 0:
            self.title_var.set(self.vars['v18_title'].get())
            self.subtype_var.set(self.vars['v18_subtype'].get())
            self.payload['event_date_shamsi'] = self.vars['event_date_shamsi'].get().strip()
            self.payload['amount'] = parse_int(self.vars['amount'].get())
            self.payload['paid_amount'] = self.payload['amount']
            self.payload['v18_title'] = self.title_var.get()
            self.payload['v18_subtype'] = self.subtype_var.get()
            return
        if self.pages[self.page_index]:
            self.payload = self._payload_from_vars(self.title_var.get(), self.subtype_var.get())

    def _validate_current(self):
        title, sub = self.title_var.get(), self.subtype_var.get()
        if self.page_index == 0:
            if not title or not sub:
                raise ValueError('عنوان تراکنش و نوع تراکنش را انتخاب کن.')
            return
        if title == 'ورودی' and sub == 'شرکا/قرض':
            visible_name = str(self.vars['partner_name'].get() if self.vars.get('partner_name') else '')
            name = str(self.payload.get('partner_name') or '')
            other = str(self.payload.get('partner_other_name') or '')
            if visible_name == 'سایر' and not other:
                raise ValueError('نام واریزکننده را برای گزینه «سایر» وارد کن.')
            kind = str(self.payload.get('partner_kind') or 'تزریق پول')
            if kind == 'قرض' and self.page_index >= 2:
                if parse_int(self.payload.get('loan_days')) <= 0 and not normalize_shamsi(str(self.payload.get('partner_return_date') or '')):
                    raise ValueError('برای قرض، مدت قرض یا تاریخ برگشت را وارد کن.')
        if title == 'ورودی' and sub == 'فروش' and str(self.payload.get('sale_unit') or '') == 'سایر':
            if float(self.payload.get('sold_area') or 0) <= 0:
                raise ValueError('متراژ فروخته‌شده را برای گزینه «سایر» وارد کن.')

    def next(self):
        try:
            self._capture()
            self._validate_current()
        except Exception as exc:
            return messagebox.showwarning('ثبت مرحله‌ای', str(exc), parent=self)

        if self.page_index == 0:
            self.pages = [[
                v18.FieldDef('event_date_shamsi', 'تاریخ', 'date'),
                v18.FieldDef('amount', 'مبلغ', 'money'),
                v18.FieldDef('v18_title', 'عنوان تراکنش', 'titlecombo'),
                v18.FieldDef('v18_subtype', 'نوع تراکنش', 'subcombo'),
            ]] + wizard_steps_182(self.title_var.get(), self.subtype_var.get()) + [[]]
            self.page_index = 1 if len(self.pages) > 1 else 0
            return self._show_page()

        if self.page_index >= len(self.pages) - 1:
            try:
                p = dict(self.payload)
                p['v18_manual_fields'] = sorted(self.manual_fields)
                APPROVAL.save_payload(self.pid, p, learn=True)
                msg = v18.approve_v18(self.pid, p, self.rich)
                messagebox.showinfo('ثبت', msg, parent=self)
                self.on_done()
                self.destroy()
            except Exception as exc:
                messagebox.showerror('تأیید انجام نشد', str(exc), parent=self)
            return

        self.page_index += 1
        self._show_page()

    def prev(self):
        try:
            self._capture()
        except Exception:
            pass
        if self.page_index > 0:
            self.page_index -= 1
            self._show_page()

    def _open_full(self):
        if self._closing_to_full:
            return
        self._closing_to_full = True
        try:
            self._capture()
            APPROVAL.save_payload(self.pid, self.payload, learn=False)
        except Exception:
            pass
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        self.on_full()


class UnifiedPendingEditor182(v181.UnifiedPendingEditor181):
    """Full editor with the same partner defaults/conditional behavior as the wizard."""

    def _load_values(self, title: str, subtype: str):
        super()._load_values(title, subtype)
        if title == 'ورودی' and subtype == 'شرکا/قرض':
            actual = str(self.payload.get('partner_name') or '').strip()
            other = str(self.payload.get('partner_other_name') or '').strip()
            self._loading = True
            try:
                if 'partner_name' in self.vars:
                    if actual and actual not in _PARTNER_NAMES:
                        self.vars['partner_name'].set('سایر')
                        if 'partner_other_name' in self.vars:
                            self.vars['partner_other_name'].set(other or actual)
                    elif not actual:
                        self.vars['partner_name'].set('پیمان')
                if 'partner_kind' in self.vars and self.vars['partner_kind'].get() not in _PARTNER_KINDS:
                    self.vars['partner_kind'].set('تزریق پول')
            finally:
                self._loading = False

    def payload_from_form(self):
        p = super().payload_from_form()
        title, subtype = self.title_var.get(), self.subtype_var.get()
        if title == 'ورودی' and subtype == 'شرکا/قرض':
            if str(p.get('partner_kind') or '') not in _PARTNER_KINDS:
                p['partner_kind'] = 'تزریق پول'
            if str(self.vars.get('partner_name').get() if self.vars.get('partner_name') else '') == 'سایر' and not str(p.get('partner_name') or '').strip():
                raise ValueError('نام واریزکننده را برای گزینه «سایر» وارد کن.')
            if p.get('partner_kind') == 'قرض' and parse_int(p.get('loan_days')) <= 0 and not normalize_shamsi(str(p.get('partner_return_date') or '')):
                raise ValueError('برای قرض، مدت قرض یا تاریخ برگشت را وارد کن.')
        if title == 'ورودی' and subtype == 'فروش' and str(p.get('sale_unit') or '') == 'سایر' and float(p.get('sold_area') or 0) <= 0:
            raise ValueError('متراژ فروخته‌شده را برای گزینه «سایر» وارد کن.')
        return p


class DataEntryCenter182(v181.DataEntryCenter181):
    def open_wizard(self, row=None):
        row = row or self.current
        if not row:
            return messagebox.showwarning('ثبت دیتا', 'یک سطر را انتخاب کن.', parent=self)

        def full():
            fresh = DB.get_pending_item(str(row['pending_id'])) or row
            fresh = dict(fresh)
            fresh['raw_text'] = v18._raw_text(str(row['pending_id']), row)
            UnifiedPendingEditor182(self, fresh, self.rich, self.refresh)

        TransactionWizard182(self, row, self.rich, self.refresh, full)

    def open_editor(self, row=None):
        row = row or self.current
        if row:
            UnifiedPendingEditor182(self, row, self.rich, self.refresh)


class Stage182Dashboard(v181.Stage181Dashboard):
    def __init__(self):
        super().__init__()
        self.title('BARKAV — Engineering & Construction — Version 18.2')

    def _build_approval_center(self):
        tab = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.approval_tab = tab
        self.notebook.insert(1, tab, text='ثبت دیتا')
        self.approval_center = DataEntryCenter182(tab, self.rich, on_posted=self.refresh_all)
        self.approval_center.pack(fill='both', expand=True)
        if self._bot_process:
            self.approval_center.set_bot_process(self._bot_process, self._bot_log)
        self.after_idle(self._rebuild_navbar)

    def export_development_package(self):
        from tkinter import filedialog
        dest = filedialog.asksaveasfilename(parent=self, defaultextension='.zip',
                                            initialfile='BARKAV_Development_Package_18.2.zip',
                                            filetypes=[('ZIP', '*.zip')])
        if not dest:
            return
        try:
            res = v18.v175.v174.build_development_package(BASE_DIR, Path(dest), VERSION)
            messagebox.showinfo('بسته توسعه', f"بسته توسعه {VERSION} ساخته شد:\n{res['path']}\n\nدیتابیس زنده و secrets وارد بسته نشده‌اند.", parent=self)
        except Exception as exc:
            messagebox.showerror('بسته توسعه', str(exc), parent=self)


# ---------------------------------------------------------------------------
# V18.2 final stabilization layer — user-locked Data Entry + visual behavior
# ---------------------------------------------------------------------------
class PendingTable182(v181.PendingTable181):
    """V18.2 table with deterministic paste below the selected target row."""
    def __init__(self, parent, on_open, on_delete, on_copy, on_paste, on_add,
                 on_approve, on_reject, on_reprocess, on_export):
        super().__init__(parent, on_open, on_delete, on_copy, on_add,
                         on_approve, on_reject, on_reprocess, on_export)
        self.on_paste = on_paste
        try:
            self.menu.insert_command(6, label='📌 چسباندن زیر سطر', command=lambda: self.on_paste(self.selected_rows()))
        except Exception:
            self.menu.add_command(label='📌 چسباندن زیر سطر', command=lambda: self.on_paste(self.selected_rows()))


class _UnifiedPendingEditor182Final(UnifiedPendingEditor182):
    """Scrollable RTL full editor matching the final 18.2 specification."""
    def __init__(self, parent, row, rich, on_done):
        row = dict(row or {})
        payload = deepcopy(dict(row.get('payload') or {}))
        title, subtype = v18._title_type_from_payload(payload)
        if title == 'هزینه ساخت' and subtype == 'چک':
            caption = _receipt_caption(row, payload)
            if caption:
                payload['description'] = caption
                payload['receipt_caption'] = caption
            payload['cheque_amount'] = int(payload.get('amount') or payload.get('paid_amount') or payload.get('cheque_amount') or 0)
        row['payload'] = payload
        super().__init__(parent, row, rich, on_done)
        self.font_family = 'Segoe UI'
        _retarget_fonts(self)

    def _build(self):
        head = tk.Frame(self, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1)
        head.pack(fill='x', padx=10, pady=8)
        tk.Label(head, text='ویرایش و تأیید رکورد', bg=DARK['surface'], fg=DARK['text'],
                 font=('Segoe UI', self.font_size + 2, 'bold')).pack(side='right', padx=12, pady=8)
        self.msg = tk.StringVar(value='')
        tk.Label(head, textvariable=self.msg, bg=DARK['surface'], fg=DARK['muted'],
                 font=('Segoe UI', max(8, self.font_size - 1))).pack(side='left', padx=10)

        pane = ttk.Panedwindow(self, orient='horizontal')
        pane.pack(fill='both', expand=True, padx=10, pady=(0, 8))
        left = tk.Frame(pane, bg=DARK['panel'], highlightbackground=DARK['line'], highlightthickness=1)
        right = tk.Frame(pane, bg=DARK['panel'], highlightbackground=DARK['line'], highlightthickness=1)
        pane.add(left, weight=35)
        pane.add(right, weight=65)

        # Evidence / receipt side.
        imgf = tk.Frame(left, bg=DARK['surface'])
        imgf.pack(fill='both', expand=True, padx=7, pady=(7, 4))
        imgf.grid_rowconfigure(0, weight=1); imgf.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(imgf, bg=DARK['surface'], highlightthickness=0)
        ys = ttk.Scrollbar(imgf, orient='vertical', command=self.canvas.yview)
        xs = ttk.Scrollbar(imgf, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.canvas.grid(row=0, column=0, sticky='nsew'); ys.grid(row=0, column=1, sticky='ns'); xs.grid(row=1, column=0, sticky='ew')
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.canvas.bind('<ButtonPress-1>', lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind('<B1-Motion>', lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        z = tk.Frame(left, bg=DARK['panel']); z.pack(fill='x', padx=7)
        for text, cmd in [('−', lambda: self._set_zoom(self._zoom / 1.2)), ('Fit', self._fit_image), ('+', lambda: self._set_zoom(self._zoom * 1.2))]:
            tk.Button(z, text=text, command=cmd, bg=DARK['glass'], fg=DARK['text'], relief='flat', width=5).pack(side='left', padx=2, pady=3)
        self.caption = tk.Text(left, height=7, wrap='word', bg=DARK['surface'], fg=DARK['text'],
                               insertbackground=DARK['text'], relief='flat', font=('Segoe UI', self.font_size + 1), padx=10, pady=8)
        self.caption.pack(fill='x', padx=7, pady=(3, 7)); self.caption.configure(state='disabled')

        # Right side is one scrollable form canvas; action buttons stay fixed below.
        scroll_shell = tk.Frame(right, bg=DARK['panel'])
        scroll_shell.pack(fill='both', expand=True)
        form_canvas = tk.Canvas(scroll_shell, bg=DARK['panel'], highlightthickness=0)
        form_scroll = ttk.Scrollbar(scroll_shell, orient='vertical', command=form_canvas.yview)
        form_canvas.configure(yscrollcommand=form_scroll.set)
        form_canvas.pack(side='left', fill='both', expand=True); form_scroll.pack(side='right', fill='y')
        form_body = tk.Frame(form_canvas, bg=DARK['panel'])
        form_id = form_canvas.create_window((0, 0), window=form_body, anchor='nw')
        form_body.bind('<Configure>', lambda e: form_canvas.configure(scrollregion=form_canvas.bbox('all')), add='+')
        form_canvas.bind('<Configure>', lambda e: form_canvas.itemconfigure(form_id, width=e.width), add='+')
        form_canvas.bind('<MouseWheel>', lambda e: (form_canvas.yview_scroll(int(-e.delta / 120), 'units'), 'break')[1], add='+')
        self._form_canvas = form_canvas

        self.main = v18.GlassSection(form_body, 'مشخصات تراکنش')
        self.main.pack(fill='both', expand=True, padx=8, pady=8)
        b = self.main.body; b.grid_columnconfigure((0, 1), weight=1, uniform='editor182')
        self.title_var = tk.StringVar(); self.subtype_var = tk.StringVar()

        # User-locked RTL pairing: date right / amount left.
        for fd, col in [(v18.FieldDef('event_date_shamsi', 'تاریخ', 'date'), 1),
                        (v18.FieldDef('amount', 'مبلغ', 'money'), 0)]:
            self._field(b, fd, 0, col, width=28)

        # User-locked RTL pairing: title right / subtype left.
        for key, label, col in [('v18_title', 'عنوان تراکنش', 1), ('v18_subtype', 'نوع تراکنش', 0)]:
            box = tk.Frame(b, bg=DARK['panel']); box.grid(row=1, column=col, sticky='nsew', padx=5, pady=4); box.grid_columnconfigure(0, weight=1)
            tk.Label(box, text=label, bg=DARK['panel'], fg=DARK['text'], font=('Segoe UI', self.font_size, 'bold')).grid(row=0, column=0, sticky='e')
            var = self.title_var if key == 'v18_title' else self.subtype_var
            vals = list(v18.TITLE_TYPES) if key == 'v18_title' else []
            w = ttk.Combobox(box, textvariable=var, state='readonly', values=vals, width=28)
            w.grid(row=1, column=0, sticky='ew', pady=(3, 0)); self.vars[key] = var; self.widgets[key] = w
            tk.Label(box, text=f"AI: {v18._ai_value(self.ai_original, key)}", bg=DARK['panel'], fg=DARK['muted'],
                     font=('Segoe UI', max(7, self.font_size - 2))).grid(row=2, column=0, sticky='e', pady=2)
        self.widgets['v18_title'].bind('<<ComboboxSelected>>', lambda e: self._title_changed(), add='+')
        self.widgets['v18_subtype'].bind('<<ComboboxSelected>>', lambda e: self._sub_changed(), add='+')

        self.special_host = tk.Frame(b, bg=DARK['panel'])
        self.special_host.grid(row=2, column=0, columnspan=2, sticky='nsew', pady=(8, 0)); b.grid_rowconfigure(2, weight=1)
        title, sub = v18._title_type_from_payload(self.payload)
        valid = list(v18.TITLE_TYPES.get(title, []))
        if sub not in valid: sub = valid[0] if valid else ''
        self.title_var.set(title); self.subtype_var.set(sub); self.widgets['v18_subtype'].configure(values=valid)
        self._build_special(title, sub); self._load_values(title, sub)

        action = tk.Frame(self, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1)
        action.pack(fill='x', padx=10, pady=(0, 10))
        tk.Button(action, text='تأیید و ثبت', command=self.approve, bg=DARK['green'], fg='#102018', relief='flat',
                  padx=18, pady=9, font=('Segoe UI', self.font_size, 'bold')).pack(side='right', padx=4, pady=5)
        tk.Button(action, text='ذخیره اصلاحات', command=self.save_only, bg=DARK['blue'], fg='#FFFFFF', relief='flat',
                  padx=15, pady=9).pack(side='right', padx=4, pady=5)
        tk.Button(action, text='رد', command=self.reject, bg=DARK['red'], fg='#FFFFFF', relief='flat',
                  padx=15, pady=9).pack(side='right', padx=4, pady=5)

    def _title_changed(self):
        title = self.title_var.get(); subs = list(v18.TITLE_TYPES.get(title, []))
        current = self.subtype_var.get()
        sub = current if current in subs else (subs[0] if subs else '')
        self.subtype_var.set(sub)
        try: self.widgets['v18_subtype'].configure(values=subs)
        except Exception: pass
        if sub: self._build_special(title, sub)

    def _build_special(self, title, sub):
        try:
            if getattr(self, '_special_initialized', False) and self.vars and 'event_date_shamsi' in self.vars:
                self.payload = self._payload_from_vars(self.title_var.get(), self.subtype_var.get())
        except Exception:
            pass
        for w in self.special_host.winfo_children(): w.destroy()
        keep = {'event_date_shamsi', 'amount', 'v18_title', 'v18_subtype'}
        self.vars = {k: v for k, v in self.vars.items() if k in keep}; self.widgets = {k: v for k, v in self.widgets.items() if k in keep}
        card = v18.GlassSection(self.special_host, f'{title} — {sub}'); card.pack(fill='both', expand=True)
        body = card.body; body.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform='special182')
        fields = v181.special_fields_181(title, sub); by = {f.key: f for f in fields}
        if title == 'هزینه ساخت' and sub == 'نقدی':
            rows = [['payer_name', 'receiver_name', 'description'],
                    ['payment_method', 'invoice_amount', 'final_amount', 'discount_amount'],
                    ['payment_state', 'total_debt', 'remaining_debt'], ['main_phase', 'sub_phase']]
        elif title == 'هزینه ساخت' and sub == 'چک':
            rows = [['payer_name', 'receiver_name', 'description', 'is_guarantee'],
                    ['issuer_name', 'issuer_bank', 'cheque_type'],
                    ['cheque_registration_state', 'due_date_shamsi', 'cheque_status'],
                    ['payment_method', 'invoice_amount', 'final_amount', 'discount_amount'],
                    ['payment_state', 'total_debt', 'remaining_debt'], ['main_phase', 'sub_phase']]
        elif title == 'ورودی' and sub == 'فروش':
            rows = [['sale_id', 'sale_unit', 'sold_area'], ['payer_name', 'buyer_name']]
        elif title == 'ورودی' and sub == 'تسهیلات':
            rows = [['loan_name', 'loan_bank', 'loan_total_amount'], ['installment_count', 'interest_rate'],
                    ['guarantor_1', 'guarantor_2', 'guarantor_3'], ['loan_start_date', 'loan_end_date']]
        elif title == 'ورودی' and sub == 'شرکا/قرض':
            rows = [['partner_name', 'partner_other_name', 'partner_kind'], ['loan_days', 'partner_return_date']]
        elif title == 'خروجی' and sub == 'اقساط':
            rows = [['payer_name', 'loan_id'], ['loan_bank', 'loan_total_amount'],
                    ['installment_count', 'paid_installments_before'], ['installments_paid_now', 'remaining_installments']]
        else:
            ks = [f.key for f in fields if f.key != 'cheque_amount']; rows = [ks[i:i+4] for i in range(0, len(ks), 4)]
        for rr, keys in enumerate(rows):
            for cc, key in enumerate(keys):
                if key in by: self._field(body, by[key], rr, 3 - cc, width=20)
        self._load_values(title, sub); self._special_initialized = True

        if 'partner_kind' in self.vars:
            self.vars['partner_kind'].trace_add('write', lambda *_: self._partner_sync_181()); self._partner_sync_181()
        if 'partner_name' in self.vars:
            self.vars['partner_name'].trace_add('write', lambda *_: self._partner_sync_181()); self._partner_sync_181()
        if 'loan_days' in self.vars: self.vars['loan_days'].trace_add('write', lambda *_: self._partner_date_sync())
        if 'loan_start_date' in self.vars: self.vars['loan_start_date'].trace_add('write', lambda *_: self._loan_date_sync())
        if 'installment_count' in self.vars: self.vars['installment_count'].trace_add('write', lambda *_: self._loan_date_sync())
        if 'installments_paid_now' in self.vars: self.vars['installments_paid_now'].trace_add('write', lambda *_: self._installment_count_sync())
        if 'sale_unit' in self.vars:
            self.vars['sale_unit'].trace_add('write', lambda *_: self._sync_sale_area_181()); self._sync_sale_area_181()
        if title == 'هزینه ساخت':
            for key in ('invoice_amount', 'final_amount'):
                if key in self.vars: self.vars[key].trace_add('write', lambda *_: self._sync_discount_182_editor())
            for key in ('payment_state', 'total_debt', 'amount'):
                if key in self.vars: self.vars[key].trace_add('write', lambda *_: self._sync_debt_182_editor())
            self._sync_discount_182_editor(); self._sync_debt_182_editor()
            bar = tk.Frame(body, bg=DARK['panel']); bar.grid(row=len(rows), column=0, columnspan=4, sticky='ew', padx=5, pady=7)
            self.phase_hint = tk.StringVar(value='')
            tk.Label(bar, textvariable=self.phase_hint, bg=DARK['panel'], fg=DARK['muted'], font=('Segoe UI', max(8, self.font_size - 1))).pack(side='right', padx=7)
            tk.Button(bar, text='پیشنهاد فاز', command=self._phase_suggest, bg=DARK['glass'], fg=DARK['text'], relief='flat', padx=10, pady=6).pack(side='left')

    def _sync_discount_182_editor(self):
        if getattr(self, '_loading', False) or not all(k in self.vars for k in ('invoice_amount', 'final_amount', 'discount_amount')): return
        invoice = parse_int(self.vars['invoice_amount'].get()); final = parse_int(self.vars['final_amount'].get())
        value = max(invoice - final, 0) if invoice > 0 else 0
        self._loading = True
        try: self.vars['discount_amount'].set(v18._group_money(value)); self.payload['discount_amount'] = value
        finally: self._loading = False

    def _sync_debt_182_editor(self):
        if getattr(self, '_loading', False) or not all(k in self.vars for k in ('payment_state', 'total_debt', 'remaining_debt')): return
        state = str(self.vars['payment_state'].get() or ''); total = max(0, parse_int(self.vars['total_debt'].get()))
        paid = max(0, parse_int(self.vars['amount'].get()) if self.vars.get('amount') else int(self.payload.get('amount') or 0))
        remaining = 0 if state == 'تسویه' else (total if state == 'پرداخت‌نشده' else max(total - paid, 0))
        self._loading = True
        try: self.vars['remaining_debt'].set(v18._group_money(remaining)); self.payload['remaining_debt'] = remaining
        finally: self._loading = False

    def _load_evidence(self):
        super()._load_evidence()
        direct = _receipt_caption(self.row, self.payload)
        self.caption.configure(state='normal'); self.caption.delete('1.0', 'end')
        self.caption.insert('1.0', direct or 'متن همراه همین رسید ثبت نشده است.')
        self.caption.configure(state='disabled')


def _editor_refresh_subphase_182(self):
    v18.DynamicFormMixin._refresh_subphase(self)
    try:
        var = self.vars.get('sub_phase'); widget = self.widgets.get('sub_phase')
        if var is not None and widget is not None and not str(var.get() or '').strip():
            vals = list(getattr(widget, '_all', []) or widget.cget('values') or [])
            if vals: var.set(vals[0])
    except Exception:
        pass

_UnifiedPendingEditor182Final._refresh_subphase = _editor_refresh_subphase_182


UnifiedPendingEditor182 = _UnifiedPendingEditor182Final


class _DataEntryCenter182Final(DataEntryCenter182):
    """Final Data Entry behavior: 70/30 layout, local history and clear AI status."""
    def __init__(self, parent, rich, on_posted=None):
        self._undo_stack = []
        self._redo_stack = []
        self._copied_rows = []
        self._layout_ratio = (70, 30)
        self._reprocess_dialog = None
        super().__init__(parent, rich, on_posted)

    def _build(self):
        ui = load_ui(); self.font_family = 'Segoe UI'; self.font_size = int(ui.get('font_size', 11))
        top = tk.Frame(self, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1); top.pack(fill='x', pady=(0, 5)); tb = top
        self.filter = tk.StringVar(value='Pending'); self.status_buttons = {}
        for key, label in [('همه', 'همه'), ('Pending', 'در انتظار بررسی'), ('تأییدشده', 'تأییدشده'), ('ردشده', 'ردشده')]:
            b = tk.Button(tb, text=label, command=lambda k=key: self._set_status(k), bg=DARK['glass'], fg=DARK['text'],
                          activebackground=DARK['panel2'], relief='flat', font=('Segoe UI', self.font_size, 'bold'), padx=11, pady=7)
            b.pack(side='right', padx=3, pady=5); self.status_buttons[key] = (b, '')
        self.bot = tk.StringVar(value='تلگرام: بررسی...'); self.gemini = tk.StringVar(value='جمینای: بررسی...')
        self.bot_label = tk.Label(tb, textvariable=self.bot, bg=DARK['surface'], fg=DARK['muted'], font=('Segoe UI', max(9, self.font_size - 1), 'bold')); self.bot_label.pack(side='left', padx=6)
        self.gemini_label = tk.Label(tb, textvariable=self.gemini, bg=DARK['surface'], fg=DARK['muted'], font=('Segoe UI', max(9, self.font_size - 1), 'bold')); self.gemini_label.pack(side='left', padx=6)
        tk.Button(tb, text='بازخوانی پیام‌ها', command=self.re_read_messages, bg=DARK['glass'], fg=DARK['text'], relief='flat', padx=10, pady=7).pack(side='left', padx=3)
        tk.Button(tb, text='پردازش مجدد', command=lambda: self.reprocess_rows(self.table.selected_rows()), bg=DARK['glass'], fg=DARK['text'], relief='flat', padx=10, pady=7).pack(side='left', padx=3)

        pane = ttk.Panedwindow(self, orient='horizontal'); pane.pack(fill='both', expand=True); self._data_pane = pane
        preview = tk.Frame(pane, bg=DARK['panel'], highlightbackground=DARK['line'], highlightthickness=1)
        table_side = tk.Frame(pane, bg=DARK['panel'])
        # Left preview = 30%, right table = 70%.
        pane.add(preview, weight=30); pane.add(table_side, weight=70)
        def _settle_data_entry_split(event=None):
            try:
                width = pane.winfo_width()
                # This panel is initially built while its hidden notebook tab is
                # unmapped (width==1).  Only set the real 30/70 sash once the
                # tab has an actual width; keep it proportional on window resize.
                if width > 200:
                    pane.sashpos(0, int(width * 0.30))
            except Exception:
                pass
        pane.bind('<Configure>', _settle_data_entry_split, add='+')
        self.after_idle(_settle_data_entry_split)
        self.after(250, _settle_data_entry_split)

        bottom = tk.Frame(table_side, bg=DARK['bg']); bottom.pack(side='bottom', fill='x', pady=5)
        tk.Button(bottom, text='حذف', command=lambda: self.batch_delete18(self.table.selected_rows()), bg=DARK['red'], fg='#FFFFFF', relief='flat', font=('Segoe UI', self.font_size, 'bold'), padx=18, pady=9).pack(side='right', padx=3)
        tk.Button(bottom, text='کپی', command=lambda: self.copy_rows(self.table.selected_rows()), bg=DARK['yellow'], fg='#171A1F', relief='flat', font=('Segoe UI', self.font_size, 'bold'), padx=18, pady=9).pack(side='right', padx=3)
        tk.Button(bottom, text='پیست', command=lambda: self.paste_rows(self.table.selected_rows()), bg=DARK['blue'], fg='#FFFFFF', relief='flat', font=('Segoe UI', self.font_size, 'bold'), padx=18, pady=9).pack(side='right', padx=3)
        tk.Button(bottom, text='اضافه کردن', command=self.manual_transaction, bg=DARK['green'], fg='#102018', relief='flat', font=('Segoe UI', self.font_size, 'bold'), padx=18, pady=9).pack(side='right', padx=3)
        self.table = PendingTable182(table_side, self.open_wizard, self.batch_delete18, self.copy_rows, self.paste_rows,
                                     self.manual_transaction, self.batch_approve18, self.batch_reject18, self.reprocess_rows, self.export_rows)
        self.table.pack(side='top', fill='both', expand=True)

        tk.Label(preview, text='پیش‌نمایش', bg=DARK['panel'], fg=DARK['text'], font=('Segoe UI', self.font_size + 1, 'bold')).pack(anchor='e', padx=8, pady=7)
        self.preview = tk.Canvas(preview, bg=DARK['surface'], highlightthickness=0, height=260); self.preview.pack(fill='both', expand=True, padx=7)
        self.preview.bind('<MouseWheel>', self._wheel); self.preview.bind('<ButtonPress-1>', lambda e: self.preview.scan_mark(e.x, e.y)); self.preview.bind('<B1-Motion>', lambda e: self.preview.scan_dragto(e.x, e.y, gain=1))
        self.text = tk.Text(preview, height=8, wrap='word', bg=DARK['surface'], fg=DARK['text'], relief='flat', font=('Segoe UI', self.font_size + 1), padx=8, pady=8)
        self.text.pack(fill='x', padx=7, pady=7); self.text.configure(state='disabled')
        self.action = tk.StringVar(); tk.Label(preview, textvariable=self.action, bg=DARK['panel'], fg=DARK['muted'], font=('Segoe UI', max(9, self.font_size - 1)), wraplength=320, justify='right').pack(fill='x', padx=7, pady=(0, 7))
        self._update_status_buttons(); self.after(1200, self._service_status_181); self.after(4000, self._periodic); self.table.tree.bind('<<TreeviewSelect>>', self._select18, add='+')

    @staticmethod
    def _pending_snapshot(pending_id):
        row = DB.get_pending_item(str(pending_id)) or {}
        return {
            'pending_id': str(pending_id),
            'payload': deepcopy(dict(row.get('payload') or {})),
            'detected_type': row.get('detected_type'),
            'confidence': row.get('confidence'),
            'status': row.get('status'),
        }

    def _record_pending_edit(self, before):
        """Record a reversible pending-only edit, never a posted financial action."""
        if not before or not before.get('pending_id'):
            return
        after = self._pending_snapshot(before['pending_id'])
        if after.get('status') not in {'PENDING_REVIEW', 'NEEDS_REVIEW', 'EDIT_PENDING'}:
            return
        same = all(before.get(k) == after.get(k) for k in ('payload', 'detected_type', 'confidence', 'status'))
        if not same:
            self._push_history({'kind': 'edit', 'before': before, 'after': after})

    def open_editor(self, row=None):
        row = row or getattr(self, 'current', None)
        if not row:
            return
        pid = str(row.get('pending_id') or '')
        before = self._pending_snapshot(pid)
        def done():
            self._record_pending_edit(before)
            self.refresh()
        UnifiedPendingEditor182(self, row, self.rich, done)

    def open_wizard(self, row=None):
        row = row or getattr(self, 'current', None)
        if not row:
            return messagebox.showwarning('ثبت دیتا', 'یک سطر را انتخاب کن.', parent=self)
        pid = str(row.get('pending_id') or '')
        before = self._pending_snapshot(pid)
        def done():
            # Wizard approval may post financially. Only record an edit while
            # the pending record is still in a review state.
            self._record_pending_edit(before)
            self.refresh()
        def full():
            fresh = DB.get_pending_item(pid) or row
            fresh = dict(fresh); fresh['raw_text'] = v18._raw_text(pid, row)
            self.open_editor(fresh)
        TransactionWizard182(self, row, self.rich, done, full)

    def manual_transaction(self):
        mid = int(datetime.now().timestamp() * 1_000_000)
        sh = gregorian_to_shamsi(datetime.now().date())
        p = {'detected_type':'EXPENSE','v18_title':'هزینه ساخت','v18_subtype':'نقدی',
             'event_date_shamsi':sh,'amount':0,'payment_state':'UNPAID','source':'MANUAL_GUI_18_2'}
        DB.register_telegram_message(chat_id=-180, message_id=mid, raw_text='', content_type='manual_gui',
                                     message_date=datetime.now().isoformat(timespec='seconds'), state='RECEIVED')
        pid = DB.create_or_replace_pending(telegram_chat_id=-180, telegram_message_id=mid,
                                           detected_type='EXPENSE', payload=p, confidence=1.0,
                                           status='PENDING_REVIEW')
        self._push_history({'kind':'add', 'pending_ids':[str(pid)]})
        self.refresh()
        row = next((x for x in self.rows if str(x.get('pending_id')) == str(pid)), None)
        if row:
            self.open_wizard(row)

    def _service_status_181(self):
        try:
            proc = getattr(self, '_bot_process', None); ready = (BASE_DIR / 'runtime' / 'telegram_bot_ready.flag').exists(); bot_ok = bool(proc and proc.poll() is None and ready)
            inbound = None
            try:
                hb = BASE_DIR / 'runtime' / 'telegram_inbound_last.json'
                if hb.exists(): inbound = json.loads(hb.read_text(encoding='utf-8'))
            except Exception: inbound = None
            if bot_ok:
                suffix = f" | آخرین پیام #{fa(inbound.get('message_id'))}" if inbound and inbound.get('message_id') else ''
                self.bot.set('تلگرام: آنلاین و آماده' + suffix); self.bot_label.configure(fg=DARK['green'])
            elif proc and proc.poll() is None:
                self.bot.set('تلگرام: در حال اتصال'); self.bot_label.configure(fg=DARK['yellow'])
            else:
                self.bot.set('تلگرام: قطع'); self.bot_label.configure(fg=DARK['red'])

            parser = getattr(getattr(APPROVAL, 'receipts', None), 'parser', None)
            names = [str(x[0]) for x in getattr(parser, 'providers', [])]; configured = any('GEMINI' in n.upper() for n in names)
            last = None
            try:
                with DB.read() as con: last = con.execute("SELECT provider,status,created_at FROM receipt_analyses ORDER BY created_at DESC LIMIT 1").fetchone()
            except Exception: pass
            failed = bool(last and 'VISION_FAILED' in str(last['provider']))
            if not configured:
                self.gemini.set('جمینای: تنظیم نشده'); self.gemini_label.configure(fg=DARK['red'])
            elif failed:
                self.gemini.set('جمینای: خطای آخرین تحلیل'); self.gemini_label.configure(fg=DARK['red'])
            elif last:
                self.gemini.set('جمینای: آماده | آخرین تحلیل انجام شد'); self.gemini_label.configure(fg=DARK['green'])
            else:
                self.gemini.set('جمینای: تنظیم شده | در انتظار اولین تحلیل'); self.gemini_label.configure(fg=DARK['yellow'])
        except Exception:
            pass
        self.after(4000, self._service_status_181)

    def _show(self, row):
        self.preview.delete('all'); self._image = None; self._tkimg = None; self.zoom = 1
        path = self._path(row)
        if path and v18.Image is not None:
            try: self._image = v18.ImageOps.exif_transpose(v18.Image.open(path)).convert('RGB'); self.after(30, self._fit)
            except Exception: pass
        if not self._image: self.preview.create_text(150, 120, text='بدون تصویر', fill=DARK['muted'], font=('Segoe UI', 10))
        p = row.get('payload') or {}; direct = _receipt_caption(row, p)
        lines = []
        # Preview is intentionally narrow-context: the direct receipt text plus
        # at most one immediately adjacent message on each side.  It never shows
        # the former multi-message evidence window, and AI metadata stays out of
        # this text box because the user asked for receipt-associated text only.
        try:
            pid = str(row.get('pending_id') or '')
            bundle = APPROVAL.evidence_bundle(pid, window=1) if pid else {}
            nearby = list(bundle.get('nearby') or [])
            before = [x for x in nearby if int(x.get('message_id') or 0) < int(row.get('telegram_message_id') or 0)]
            after = [x for x in nearby if int(x.get('message_id') or 0) > int(row.get('telegram_message_id') or 0)]
            if before:
                txt = str(before[-1].get('raw_text') or '').strip()
                if txt and txt != direct: lines.append(txt)
            if direct: lines.append(direct)
            if after:
                txt = str(after[0].get('raw_text') or '').strip()
                if txt and txt != direct: lines.append(txt)
        except Exception:
            lines = [direct] if direct else []
        if not lines:
            lines = ['متن همراه همین رسید ثبت نشده است.']
        self.text.configure(state='normal'); self.text.delete('1.0', 'end'); self.text.insert('1.0', '\n'.join(lines)); self.text.configure(state='disabled')

    def copy_rows(self, rows):
        if not rows: return
        self._copied_rows = [deepcopy(dict(r)) for r in rows]
        lines = []
        for r in rows:
            p = r.get('payload') or {}; title, sub = v18._title_type_from_payload(p)
            lines.append(f"{r.get('message_date') or '-'}\t{title}\t{sub}\t{p.get('description') or _receipt_caption(r,p)}\t{int(p.get('amount') or 0):,}")
        try: self.clipboard_clear(); self.clipboard_append('\n'.join(lines))
        except Exception: pass
        self.action.set(f'{fa(len(rows))} ردیف کپی شد؛ سطر مقصد را انتخاب و «پیست» را بزن.')

    def _set_hidden(self, pending_ids, hidden):
        now = datetime.now().isoformat(timespec='seconds')
        with DB.tx() as con:
            for pid in pending_ids:
                con.execute("INSERT INTO rich_ui_hidden_reviews(pending_id,hidden,updated_at) VALUES(?,?,?) ON CONFLICT(pending_id) DO UPDATE SET hidden=excluded.hidden,updated_at=excluded.updated_at", (str(pid), 1 if hidden else 0, now))

    def _push_history(self, action):
        self._undo_stack.append(action); self._undo_stack = self._undo_stack[-100:]; self._redo_stack.clear()

    def paste_rows(self, target_rows=None):
        if not self._copied_rows:
            return messagebox.showinfo('پیست', 'ابتدا یک یا چند سطر را کپی کن.', parent=self)
        target_rows = target_rows or self.table.selected_rows()
        target = target_rows[-1] if target_rows else None
        target_dt = None
        if target:
            # Query the source of truth instead of trusting a possibly stale
            # table-row copy. This makes paste positioning deterministic after
            # refreshes and external status updates.
            try:
                fresh_target = DB.get_pending_item(str(target.get('pending_id') or '')) or target
                target_dt = datetime.fromisoformat(str(fresh_target.get('created_at') or ''))
            except Exception:
                target_dt = None
        new_ids = []
        base_mid = int(datetime.now().timestamp() * 1_000_000)
        for i, src in enumerate(self._copied_rows):
            p = deepcopy(dict(src.get('payload') or {})); p['source'] = 'COPY_GUI_18_2'; p['copied_from_pending_id'] = str(src.get('pending_id') or '')
            raw = _receipt_caption(src, p)
            mid = base_mid + i
            DB.register_telegram_message(chat_id=-182, message_id=mid, raw_text=raw, content_type='copy_gui', message_date=datetime.now().isoformat(timespec='seconds'), state='RECEIVED')
            pid = DB.create_or_replace_pending(telegram_chat_id=-182, telegram_message_id=mid,
                                               detected_type=str(src.get('detected_type') or p.get('detected_type') or 'UNKNOWN'),
                                               payload=p, confidence=float(src.get('confidence') or 1.0), status='PENDING_REVIEW')
            if target_dt:
                stamp = (target_dt + timedelta(microseconds=i + 1)).isoformat(timespec='microseconds')
                with DB.tx() as con: con.execute('UPDATE pending_items SET created_at=?,updated_at=? WHERE pending_id=?', (stamp, stamp, pid))
            new_ids.append(str(pid))
        self._set_hidden(new_ids, False); self._push_history({'kind': 'paste', 'pending_ids': new_ids})
        self.filter.set('Pending'); self.refresh(); self._select_pending_ids(new_ids)
        self.action.set(f'{fa(len(new_ids))} سطر زیر سطر انتخاب‌شده درج شد.' if target else f'{fa(len(new_ids))} سطر به انتهای جدول اضافه شد.')

    def _select_pending_ids(self, ids):
        wanted = set(map(str, ids)); found = []
        mapping = getattr(self.table, 'iid_to_row', {})
        for iid, row in mapping.items():
            if str(row.get('pending_id')) in wanted: found.append(iid)
        if found:
            self.table.tree.selection_set(found); self.table.tree.see(found[-1]); self.table._sync_checks()

    def batch_delete18(self, rows):
        if not rows: return
        if not messagebox.askyesno('حذف', f'{fa(len(rows))} ردیف انتخاب‌شده حذف/مخفی شوند؟\nاین عملیات با Undo قابل بازگشت است.', parent=self): return
        states = []
        hidden_now = self.rich.hidden_review_ids()
        ids = []
        for r in rows:
            pid = str(r.get('pending_id') or '')
            if not pid: continue
            states.append({'pending_id': pid, 'status': str(r.get('status') or 'PENDING_REVIEW'), 'hidden': pid in hidden_now})
            if r.get('status') not in {'APPROVED', 'REJECTED'}:
                try: APPROVAL.reject(pid, actor_id='GUI_18_2_DELETE')
                except Exception: pass
            ids.append(pid)
        if ids: self.rich.hide_review(ids); self._push_history({'kind': 'delete', 'states': states})
        self.refresh(); self.action.set(f'{fa(len(ids))} سطر حذف/مخفی شد؛ Undo برای بازگردانی آماده است.')

    def undo_data_entry(self):
        if not self._undo_stack: return 'عملیات قابل بازگشتی در ثبت دیتا وجود ندارد.'
        a = self._undo_stack.pop(); kind = a.get('kind')
        if kind == 'delete':
            for st in a['states']:
                try: DB.update_pending(st['pending_id'], status=st['status'])
                except Exception: pass
            self._set_hidden([st['pending_id'] for st in a['states']], False)
            msg = 'حذف سطرها بازگردانی شد.'
        elif kind == 'paste':
            self._set_hidden(a['pending_ids'], True); msg = 'پیست سطرها بازگردانی شد.'
        elif kind == 'add':
            blocked = [pid for pid in a['pending_ids'] if str((DB.get_pending_item(pid) or {}).get('status')) == 'APPROVED']
            if blocked:
                self._undo_stack.append(a)
                return 'رکورد اضافه‌شده قبلاً ثبت مالی شده و از ثبت دیتا قابل Undo نیست.'
            self._set_hidden(a['pending_ids'], True); msg = 'اضافه‌کردن رکورد بازگردانی شد.'
        elif kind == 'edit':
            b = a['before']; DB.update_pending(b['pending_id'], payload=b['payload'], detected_type=b.get('detected_type'),
                                              confidence=b.get('confidence'), status=b.get('status'))
            msg = 'ویرایش رکورد بازگردانی شد.'
        else: msg = 'Undo انجام شد.'
        self._redo_stack.append(a); self.refresh(); self.action.set(msg); return msg

    def redo_data_entry(self):
        if not self._redo_stack: return 'عملیات قابل Redo در ثبت دیتا وجود ندارد.'
        a = self._redo_stack.pop(); kind = a.get('kind')
        if kind == 'delete':
            for st in a['states']:
                if st['status'] not in {'APPROVED', 'REJECTED'}:
                    try: APPROVAL.reject(st['pending_id'], actor_id='GUI_18_2_REDO')
                    except Exception: pass
            self._set_hidden([st['pending_id'] for st in a['states']], True); msg = 'حذف سطرها دوباره اعمال شد.'
        elif kind == 'paste':
            self._set_hidden(a['pending_ids'], False); msg = 'پیست سطرها دوباره اعمال شد.'
        elif kind == 'add':
            self._set_hidden(a['pending_ids'], False); msg = 'اضافه‌کردن رکورد دوباره اعمال شد.'
        elif kind == 'edit':
            aft = a['after']; DB.update_pending(aft['pending_id'], payload=aft['payload'], detected_type=aft.get('detected_type'),
                                                confidence=aft.get('confidence'), status=aft.get('status'))
            msg = 'ویرایش رکورد دوباره اعمال شد.'
        else: msg = 'Redo انجام شد.'
        self._undo_stack.append(a); self.refresh(); self.action.set(msg); return msg

    def can_undo(self): return bool(self._undo_stack)
    def can_redo(self): return bool(self._redo_stack)

    def reprocess_rows(self, rows):
        rows = rows or ([self.current] if getattr(self, 'current', None) else [])
        rows = [r for r in rows if r and r.get('status') in {'PENDING_REVIEW', 'NEEDS_REVIEW', 'EDIT_PENDING'}]
        if not rows: return messagebox.showinfo('پردازش مجدد', 'رکورد قابل پردازش انتخاب نشده است.', parent=self)
        dlg = tk.Toplevel(self); self._reprocess_dialog = dlg; dlg.title('پردازش مجدد فیش'); dlg.configure(bg=DARK['surface']); dlg.transient(self); dlg.resizable(False, False)
        status = tk.StringVar(value=f'در حال پردازش {fa(len(rows))} فیش...')
        tk.Label(dlg, textvariable=status, bg=DARK['surface'], fg=DARK['text'], font=('Segoe UI', self.font_size + 1, 'bold'), padx=28, pady=18).pack(fill='x')
        pb = ttk.Progressbar(dlg, mode='indeterminate', length=380); pb.pack(fill='x', padx=24, pady=(0, 18)); pb.start(10)
        dlg.update_idletasks(); dlg.geometry(f'440x130+{self.winfo_rootx()+max(20,(self.winfo_width()-440)//2)}+{self.winfo_rooty()+100}')
        self.action.set(status.get())

        async def analyze_one(r):
            pid = str(r['pending_id']); old = dict(r.get('payload') or {}); manual = set(old.get('v18_manual_fields') or [])
            await APPROVAL.analyze_pending_with_ai(pid)
            fresh = DB.get_pending_item(pid) or {}; new = dict(fresh.get('payload') or {}); suggest = {}
            for k in manual:
                if k in old and new.get(k) != old.get(k): suggest[k] = new.get(k); new[k] = old.get(k)
            new['v18_manual_fields'] = sorted(manual)
            if suggest: new['v18_reprocess_suggestions'] = suggest
            APPROVAL.save_payload(pid, new, learn=False)
            return pid

        results = queue.Queue(maxsize=1)
        def worker():
            ok = 0; errs = []
            async def batch():
                nonlocal ok
                # A small concurrency cap reduces multi-receipt waiting time while
                # avoiding aggressive provider/SQLite contention.
                sem = asyncio.Semaphore(2)
                async def run(r):
                    nonlocal ok
                    try:
                        async with sem: await analyze_one(r)
                        ok += 1
                    except Exception as exc: errs.append(f"{r.get('pending_id')}: {exc}")
                await asyncio.gather(*(run(r) for r in rows))
            try: asyncio.run(batch())
            except Exception as exc: errs.append(str(exc))
            # Tk must never be touched from the worker thread.
            try: results.put_nowait((ok, errs))
            except Exception: pass

        def poll_result():
            try:
                ok, errs = results.get_nowait()
            except queue.Empty:
                try:
                    if dlg.winfo_exists(): self.after(40, poll_result)
                except Exception:
                    pass
                return
            self._finish_reprocess_182(ok, errs, status, pb, dlg)

        threading.Thread(target=worker, daemon=True).start()
        self.after(40, poll_result)

    def _finish_reprocess_182(self, ok, errs, status, pb, dlg):
        try: pb.stop()
        except Exception: pass
        self.refresh()
        if errs and not ok:
            text = 'پردازش انجام نشد.'; detail = '\n'.join(errs[:6])
            status.set(text); self.action.set(text)
            try: dlg.destroy()
            except Exception: pass
            messagebox.showerror('پردازش مجدد', text + '\n\n' + detail, parent=self)
        elif errs:
            text = f'{fa(ok)} فیش به‌روزرسانی شد؛ {fa(len(errs))} خطا.'; status.set(text); self.action.set(text)
            try: dlg.destroy()
            except Exception: pass
            messagebox.showwarning('پردازش مجدد', text + '\n\n' + '\n'.join(errs[:6]), parent=self)
        else:
            text = f'پردازش با موفقیت انجام شد — {fa(ok)} فیش به‌روزرسانی شد.'; status.set(text); self.action.set(text)
            try: dlg.destroy()
            except Exception: pass
            messagebox.showinfo('پردازش مجدد', text, parent=self)


DataEntryCenter182 = _DataEntryCenter182Final

class _Stage182DashboardFinal(Stage182Dashboard):
    """Final 18.2 shell using the user-supplied dark/light reference screens."""
    _VISIBLE_NAV = ['داشبورد', 'ثبت دیتا', 'تراکنش‌ها', 'فروش و مطالبات', 'گزارش‌گیری', 'حساب مدیر']

    def __init__(self):
        super().__init__()
        self.title('BARKAV — Engineering & Construction — Version 18.2')
        try: self.iconbitmap(default=str(BASE_DIR / 'assets' / 'BARKAV.ico'))
        except Exception: pass
        self.after_idle(lambda: _retarget_fonts(self, 'Segoe UI'))

    def _style(self):
        palette = dict(_THEME_LIGHT if _is_light() else _THEME_DARK)
        DARK.update(palette)
        light = _is_light()
        try:
            v18.v175.v16.d12.COLORS.update({
                'bg': DARK['bg'], 'panel': DARK['panel'], 'soft': DARK['surface'],
                'rowblue': '#F4F7FA' if light else '#10243A', 'text': DARK['text'],
                'muted': DARK['muted'], 'line': DARK['line'], 'navy': DARK['blue'],
                'blue': DARK['blue'], 'cyan': DARK['cyan'], 'green': DARK['green'],
                'yellow': DARK['yellow'], 'orange': DARK['orange'], 'red': DARK['red'],
            })
        except Exception:
            pass
        st = ttk.Style(self)
        try: st.theme_use('clam')
        except Exception: pass
        fs = int(load_ui().get('font_size') or 11); ff = 'Segoe UI'; rh = int(load_ui().get('row_height') or 40)
        entry_bg = '#FFFFFF' if light else '#102238'
        tree_bg = '#FFFFFF' if light else '#10243A'
        tree_alt = '#F7F9FB' if light else '#132A43'
        head_bg = '#F1F5F8' if light else '#1B3653'
        tab_bg = '#FFFFFF' if light else '#11243A'
        tab_active = '#EAF8FB' if light else '#214B6E'
        select_bg = '#DCEFF8' if light else '#315D86'
        select_fg = '#16324C' if light else '#FFFFFF'
        st.configure('.', font=(ff, fs), background=DARK['bg'], foreground=DARK['text'])
        st.configure('TFrame', background=DARK['bg']); st.configure('Panel.TFrame', background=DARK['panel'])
        st.configure('TLabel', background=DARK['bg'], foreground=DARK['text'])
        st.configure('TButton', padding=(11, 7), background=DARK['glass'], foreground=DARK['text'], bordercolor=DARK['line'], relief='flat', font=(ff, fs))
        st.map('TButton', background=[('active', DARK['panel2']), ('pressed', select_bg)], foreground=[('disabled', DARK['muted'])])
        st.configure('Primary.TButton', background=DARK['blue'], foreground='#FFFFFF', font=(ff, fs, 'bold'))
        st.configure('Toolbar.TButton', padding=(7, 5), font=(ff, max(9, fs-1)), background=DARK['glass'])
        st.configure('Compact.TButton', padding=(6, 4), font=(ff, max(8, fs-2)), background=DARK['glass'])
        st.configure('Danger.TButton', background=DARK['red'], foreground='#FFFFFF')
        st.configure('TEntry', fieldbackground=entry_bg, foreground=DARK['text'], insertcolor=DARK['text'], bordercolor=DARK['line'], padding=6)
        st.configure('Compact.TEntry', fieldbackground=entry_bg, foreground=DARK['text'])
        st.configure('TCombobox', fieldbackground=entry_bg, background=entry_bg, foreground=DARK['text'], arrowcolor=DARK['text'], bordercolor=DARK['line'], padding=5)
        st.map('TCombobox', fieldbackground=[('readonly', entry_bg)], foreground=[('readonly', DARK['text'])], selectbackground=[('readonly', entry_bg)], selectforeground=[('readonly', DARK['text'])])
        st.configure('TScrollbar', background=DARK['glass'], troughcolor=DARK['surface'], bordercolor=DARK['line'], arrowcolor=DARK['muted'], relief='flat')
        st.configure('TPanedwindow', background=DARK['bg']); st.configure('TCheckbutton', background=DARK['panel'], foreground=DARK['text'])
        st.configure('TLabelframe', background=DARK['panel'], bordercolor=DARK['line'], relief='solid', borderwidth=1)
        st.configure('TLabelframe.Label', background=DARK['panel'], foreground=DARK['blue'], font=(ff, fs, 'bold'))
        st.configure('Dashboard.TLabelframe', background=DARK['panel'], bordercolor=DARK['line'])
        st.configure('Dashboard.TLabelframe.Label', background=DARK['panel'], foreground=DARK['blue'], font=(ff, fs+1, 'bold'))
        st.configure('Report.TLabelframe', background=DARK['panel'], bordercolor=DARK['line'])
        st.configure('Report.TLabelframe.Label', background=DARK['panel'], foreground=DARK['blue'], font=(ff, fs, 'bold'))
        st.configure('Treeview', rowheight=rh, background=tree_bg, fieldbackground=tree_bg, foreground=DARK['text'], bordercolor=DARK['line'], font=(ff, fs))
        st.configure('Treeview.Heading', background=head_bg, foreground=DARK['text'], font=(ff, max(9, fs-1), 'bold'), padding=(6, 9), relief='flat')
        st.map('Treeview', background=[('selected', select_bg)], foreground=[('selected', select_fg)])
        # Strong active/inactive contrast for Transactions and Reporting subtabs.
        st.configure('TNotebook', background=DARK['bg'], borderwidth=0, tabmargins=(0, 3, 0, 0))
        st.configure('TNotebook.Tab', background=tab_bg, foreground=DARK['muted'], padding=(18, 9), font=(ff, max(9, fs-1), 'bold'), borderwidth=1)
        st.map('TNotebook.Tab', background=[('selected', tab_active), ('active', DARK['panel2'])], foreground=[('selected', DARK['text']), ('active', DARK['text'])], expand=[('selected', (1, 1, 1, 0))])
        st.configure('Hidden.TNotebook', background=DARK['bg'], borderwidth=0, tabmargins=0)
        try: st.layout('Hidden.TNotebook.Tab', [])
        except Exception: pass
        self._theme_tree_alt = tree_alt

    def _load_nav_icon(self, name):
        # Bind PhotoImage explicitly to this Tk interpreter. This also makes
        # repeated GUI smoke construction reliable and avoids stale pyimage IDs.
        if not hasattr(self, '_nav_images'):
            self._nav_images = {}
        if name in self._nav_images:
            return self._nav_images[name]
        p = BASE_DIR / 'assets' / f'nav_{name}.png'
        try:
            im = v181.Image.open(p).convert('RGBA').resize((28, 28), v181.Image.Resampling.LANCZOS)
            img = v181.ImageTk.PhotoImage(im, master=self)
            self._nav_images[name] = img
            return img
        except Exception:
            return None

    def _build(self):
        self.configure(bg=DARK['bg']); fs = int(load_ui().get('font_size') or 11); ff = 'Segoe UI'; light = _is_light()
        top_bg = '#FBFCFD' if light else '#07192B'; top_line = '#DCE3E9' if light else '#29445F'
        button_bg = '#FFFFFF' if light else '#10243A'; button_active = '#EAF4F8' if light else '#1D3B58'
        button_fg = '#284A6A' if light else '#F2F5F8'
        top = tk.Frame(self, bg=top_bg, height=70, highlightbackground=top_line, highlightthickness=1); top.pack(fill='x'); top.pack_propagate(False)
        self.datetime_top = tk.StringVar(value='')
        tk.Label(top, textvariable=self.datetime_top, bg=top_bg, fg=button_fg, font=(ff, fs+1, 'bold')).pack(side='left', padx=(20, 10))
        tk.Label(top, text='BARKAV — Engineering & Construction — Version 18.2', bg=top_bg, fg=button_fg, font=(ff, fs, 'bold')).pack(side='left', padx=18)
        # No BARKAV image/logo in this area — user explicitly requested removal.
        tools = tk.Frame(top, bg=top_bg); tools.pack(side='right', padx=10, pady=10)
        commands = [
            ('ذخیره', self.manual_save, 'بکاپ دستی'),
            ('Undo', self.undo, 'بازگشت آخرین عملیات'),
            ('Redo', self.redo, 'اجرای دوباره'),
            ('بروزرسانی', self.refresh_all, 'بروزرسانی همه اطلاعات'),
            ('تنظیمات', lambda: self._select_tab_text('تنظیمات'), 'تنظیمات'),
            ('بسته توسعه', self.export_development_package, 'خروجی امن توسعه'),
            ('سیستم', lambda: self._select_tab_text('سیستم'), 'وضعیت سیستم'),
        ]
        self.command_buttons = []
        for text, cmd, tip in commands:
            b = tk.Button(tools, text=text, command=cmd, bg=button_bg, fg=button_fg, activebackground=button_active,
                          activeforeground=button_fg, relief='flat', bd=0, highlightbackground=top_line, highlightthickness=1,
                          font=(ff, max(9, fs-1), 'bold'), padx=12, pady=8, cursor='hand2')
            b.pack(side='right', padx=4); v18.add_tooltip(b, tip); self.command_buttons.append(b)
        self.project_name_top = tk.StringVar(value='پروژه')

        nav_bg = '#FFFFFF' if light else '#0A1C2F'
        self.navbar = tk.Frame(self, bg=nav_bg, height=66, highlightbackground=DARK['line'], highlightthickness=1)
        self.navbar.pack(fill='x', padx=10, pady=(8, 0)); self.navbar.pack_propagate(False)
        self.notebook = ttk.Notebook(self, style='Hidden.TNotebook'); self.notebook.pack(fill='both', expand=True, padx=10, pady=(7, 9))
        self._build_overview(); self._build_manager(); self._build_financial(); self._build_cheques(); self._build_sales(); self._build_reconciliation(); self._build_reports(); self._build_market(); self._build_system(); self._build_settings()
        self._rebuild_navbar()
        self.notebook.bind('<<NotebookTabChanged>>', lambda e: (self._sync_nav(), v18._maximize(self)), add='+')
        self._attach_common_tooltips(self); self._tick_clock(); self.after_idle(lambda: _retarget_fonts(self, 'Segoe UI'))

    def _build_overview(self):
        super()._build_overview()
        # Stage 18.1 had a hard-coded dark phase strip. Repaint it so the
        # supplied light reference stays genuinely light while preserving the
        # same compact 32-phase geometry in both appearances.
        light = _is_light()
        try:
            self.phase_strip.configure(bg=DARK['panel'])
            for b in self.phase_buttons.values():
                b.configure(
                    bg='#F7F9FB' if light else '#10243A',
                    fg='#4A6178' if light else '#C8D7E5',
                    activebackground='#E5F5F8' if light else '#214B6E',
                    activeforeground='#147F91' if light else '#FFFFFF',
                    highlightbackground=DARK['line'],
                    highlightthickness=1,
                )
            # The inherited progress canvas hard-coded a dark track.  Replace
            # only its paint routine so Light and Dark both match the supplied
            # reference, while preserving all existing progress semantics.
            bar = self.overall_progress
            bar.configure(bg=DARK['surface'], highlightbackground=DARK['line'])
            def _theme_progress_redraw():
                bar.delete('all')
                w=max(bar.winfo_width(),100); h=max(bar.winfo_height(),40); m=6
                track='#EEF3F6' if light else '#0A1421'
                outline='#D7E0E7' if light else DARK['line']
                bar.create_rectangle(m,m,w-m,h-m,fill=track,outline=outline,width=1)
                fill=(w-2*m)*bar.percent/100
                if fill>0:
                    bar.create_rectangle(m,m,m+fill,h-m,fill=DARK['blue'],outline='')
                text_fill='#27445E' if light else '#FFFFFF'
                bar.create_text(w/2,h/2,text=f"پیشرفت کلی پروژه  {fa(f'{bar.percent:.1f}')}٪",fill=text_fill,font=('Segoe UI',10,'bold'))
            bar.redraw = _theme_progress_redraw
            bar.redraw()
        except Exception:
            pass

    def refresh_phase_strip(self):
        # Preserve the phase/status semantics, but use the reference-theme
        # colors instead of the legacy hard-coded dark palette.
        super().refresh_phase_strip()
        light = _is_light()
        try:
            progress = self.rich.get_phase_progress()
            colors = ({
                'NOT_STARTED': ('#FFFFFF', '#536579'),
                'ACTIVE': ('#28A875', '#FFFFFF'),
                'PAUSED': ('#D8A33D', '#FFFFFF'),
                'COMPLETED': ('#239A70', '#FFFFFF'),
            } if light else {
                'NOT_STARTED': ('#10243A', '#C8D7E5'),
                'ACTIVE': ('#177A59', '#FFFFFF'),
                'PAUSED': ('#76571C', '#FFFFFF'),
                'COMPLETED': ('#16805D', '#FFFFFF'),
            })
            for n, b in self.phase_buttons.items():
                st = str((progress.get(n) or {}).get('status') or 'NOT_STARTED')
                bg, fg = colors.get(st, colors['NOT_STARTED'])
                b.configure(bg=bg, fg=fg, activebackground=('#DDF4ED' if light else '#214B6E'),
                            activeforeground=('#176B59' if light else '#FFFFFF'),
                            highlightbackground=DARK['line'], highlightthickness=1)
        except Exception:
            pass

    def _build_manager(self):
        before = set(self.notebook.tabs()); super()._build_manager(); new = [x for x in self.notebook.tabs() if x not in before]
        tid = new[-1] if new else self.notebook.tabs()[-1]; self.manager_tab_id = tid; self.notebook.tab(tid, text='حساب مدیر')
        tab = self.nametowidget(tid)
        bar = tk.Frame(tab, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1)
        first = tab.winfo_children()[0] if tab.winfo_children() else None
        try: bar.pack(fill='x', padx=6, pady=(5, 1), before=first)
        except Exception: bar.pack(fill='x', padx=6, pady=(5, 1))
        tk.Label(bar, text='دسترسی‌های مدیریتی', bg=DARK['surface'], fg=DARK['muted'], font=('Segoe UI', 10, 'bold')).pack(side='right', padx=10, pady=8)
        tk.Button(bar, text='تطبیق بانک', command=lambda: self._select_tab_text('تطبیق بانکی'), bg=DARK['glass'], fg=DARK['text'], relief='flat', padx=14, pady=7, font=('Segoe UI', 10, 'bold')).pack(side='right', padx=4, pady=5)
        self.manager_bank_button = bar.winfo_children()[-1]

    def _rebuild_navbar(self):
        if not getattr(self, 'navbar', None): return
        for w in self.navbar.winfo_children(): w.destroy()
        self.nav_buttons = {}; fs = int(load_ui().get('font_size') or 11); light = _is_light()
        by_text = {self.notebook.tab(t, 'text'): t for t in self.notebook.tabs()}
        # Backward compatibility if an inherited builder still used the old manager label.
        if 'حساب مدیر' not in by_text and 'حساب مدیر پروژه' in by_text:
            tid = by_text['حساب مدیر پروژه']; self.notebook.tab(tid, text='حساب مدیر'); by_text['حساب مدیر'] = tid
        icon_map = {'داشبورد':'dashboard','ثبت دیتا':'data','تراکنش‌ها':'transactions','فروش و مطالبات':'sales','گزارش‌گیری':'reports','حساب مدیر':'manager'}
        inactive_bg = '#FFFFFF' if light else '#0E2237'; active_bg = '#F0FBFD' if light else '#153653'
        inactive_fg = '#294A69' if light else '#E7EDF3'; active_fg = '#129EAE' if light else '#FFFFFF'
        for label in self._VISIBLE_NAV:
            tid = by_text.get(label)
            if not tid: continue
            img = self._load_nav_icon(icon_map[label])
            b = tk.Button(self.navbar, text=label, image=img, compound='right' if img else 'none', command=lambda t=tid: self.notebook.select(t),
                          bg=inactive_bg, fg=inactive_fg, activebackground=active_bg, activeforeground=active_fg, relief='flat', bd=0,
                          font=('Segoe UI', fs, 'bold'), padx=16, pady=8, cursor='hand2', highlightbackground=DARK['line'], highlightthickness=1)
            b.pack(side='right', fill='y', padx=2, pady=5); self.nav_buttons[tid] = b
        self._sync_nav()

    def _sync_nav(self):
        try: sel = str(self.notebook.select())
        except Exception: return
        light = _is_light(); active_bg = '#F0FBFD' if light else '#153653'; inactive_bg = '#FFFFFF' if light else '#0E2237'
        for tid, b in self.nav_buttons.items():
            active = str(tid) == sel
            b.configure(bg=active_bg if active else inactive_bg,
                        fg=('#129EAE' if light else '#FFFFFF') if active else ('#294A69' if light else '#E7EDF3'),
                        relief='raised' if active else 'flat', bd=1 if active else 0)

    def _build_reports(self):
        super()._build_reports()
        # Keep output controls available regardless of which valid report tab is active.
        report_root = self.report_main.master
        export_bar = tk.Frame(report_root, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1)
        try: export_bar.pack(fill='x', padx=5, pady=(0,5), before=self.report_main)
        except Exception: export_bar.pack(fill='x', padx=5, pady=(0,5))
        tk.Label(export_bar, text='خروجی گزارش فعال', bg=DARK['surface'], fg=DARK['muted'], font=('Segoe UI',10,'bold')).pack(side='right', padx=8, pady=6)
        ttk.Combobox(export_bar, textvariable=self.report_export_mode, state='readonly', values=['Print','PDF','Excel'], width=10).pack(side='right', padx=4, pady=5)
        tk.Button(export_bar, text='خروجی', command=self.export_report_choose, bg=DARK['glass'], fg=DARK['text'], relief='flat', padx=14, pady=7).pack(side='right', padx=4, pady=5)
        self.report_export_bar = export_bar
        # Add the valid summary/trend report target requested by the user.
        summary = ttk.Frame(self.report_nb, style='Panel.TFrame'); self.report_nb.add(summary, text='خلاصه روندهای گزارش'); self.report_summary_tab = summary
        head = tk.Frame(summary, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1); head.pack(fill='x', padx=5, pady=5)
        tk.Label(head, text='خلاصه روندهای برآورد، واقعی و پیش‌بینی', bg=DARK['surface'], fg=DARK['text'], font=('Segoe UI', 12, 'bold')).pack(side='right', padx=10, pady=8)
        self.report_summary_tree = ttk.Treeview(summary, columns=('metric','value','details'), show='headings', height=13)
        self.report_summary_tree.heading('metric', text='شاخص'); self.report_summary_tree.heading('value', text='مقدار'); self.report_summary_tree.heading('details', text='جزئیات')
        self.report_summary_tree.column('metric', width=250, anchor='e'); self.report_summary_tree.column('value', width=180, anchor='center'); self.report_summary_tree.column('details', width=520, anchor='e')
        self.report_summary_tree.pack(fill='both', expand=True, padx=5, pady=(0,5))
        # Explicit RTL/right-alignment for the financial indicators tab.
        try:
            idx_tid = self.report_main.tabs()[1]; self.report_indices_root = self.nametowidget(idx_tid)
            self.index_table.column('metric', anchor='e')
            self.index_table.configure(displaycolumns=('s3','s2','s1','metric'))
        except Exception: pass

    def _report_export_rows(self):
        """Return active report headers/rows/title. No checkbox chooser ambiguity."""
        main_text = self.report_main.tab(self.report_main.select(), 'text') if self.report_main.select() else ''
        if main_text == 'شاخص‌های مالی':
            headers = ['شاخص', 'برآورد اولیه', 'انجام‌شده + بروز تا پایان', 'بروز صفر تا ۱۰۰']
            rows = [list(self.index_table.item(i, 'values')) for i in self.index_table.get_children()]
            return headers, rows, 'شاخص‌های مالی'
        sub_text = self.report_nb.tab(self.report_nb.select(), 'text') if self.report_nb.select() else ''
        if sub_text == 'قیمت':
            headers = ['گروه','کد','شرح','واحد','برآورد','واقعی مرجع','پیش‌بینی','منبع']; rows = []
            catfa = {'MATERIAL':'مصالح','LABOR':'اجرت/اجرا','SERVICE':'خدمات','INSTALLATION_GROUP':'تأسیسات (تجمیعی)'}
            for r in self.rich.list_prices(visible_only=True):
                rows.append([catfa.get(r.get('category'), r.get('category') or '-'), r.get('code') or '-', r.get('description') or '-', r.get('unit') or '-', fa(f"{int(r.get('estimate_rate') or 0):,}"), fa(f"{int(r.get('actual_rate') or 0):,}"), fa(f"{int(r.get('forecast_rate') or 0):,}"), r.get('source') or '-'])
            return headers, rows, 'گزارش قیمت‌ها'
        if sub_text == 'فازها':
            headers = ['شماره فاز','فاز','برآورد','واقعی','مانده پایه','پیش‌بینی','ID','انحراف']; rows = []
            for r in self._phase_summary_live():
                rows.append([fa(f"{int(r['phase_no']):02d}"), r['phase'], fa(f"{int(r['estimate']):,}"), fa(f"{int(r['actual']):,}"), fa(f"{int(r['remaining_base']):,}"), fa(f"{int(r['forecast']):,}"), r['phase_id'], fa(f"{int(r['variance']):,}")])
            return headers, rows, 'گزارش فازها'
        if sub_text == 'خلاصه روندهای گزارش':
            headers = ['شاخص','مقدار','جزئیات']; rows = [list(self.report_summary_tree.item(i,'values')) for i in self.report_summary_tree.get_children()]
            return headers, rows, 'خلاصه روندهای گزارش'
        return [], [], ''

    def export_report_choose(self):
        headers, rows, title = self._report_export_rows()
        if not title:
            return messagebox.showwarning('خروجی', 'تب گزارش فعال قابل شناسایی نیست.', parent=self)
        if not rows:
            return messagebox.showinfo('خروجی', f'تب «{title}» شناسایی شد، اما هنوز داده‌ای برای خروجی ندارد.', parent=self)
        mode = str(getattr(self, 'report_export_mode', tk.StringVar(value='PDF')).get() or 'PDF')
        try:
            if mode == 'Print':
                fd, path = tempfile.mkstemp(suffix='.pdf'); os.close(fd); v163.export_pdf(path, headers, rows, title=f'BARKAV — {title}'); v163.print_file(path); return
            is_xlsx = mode == 'Excel'; ext = '.xlsx' if is_xlsx else '.pdf'
            types = [('Excel','*.xlsx')] if is_xlsx else [('PDF','*.pdf')]
            path = filedialog.asksaveasfilename(parent=self, defaultextension=ext, filetypes=types, initialfile=f'BARKAV_{title}{ext}')
            if not path: return
            if is_xlsx: v163.export_xlsx(path, headers, rows, title=f'BARKAV — {title}')
            else: v163.export_pdf(path, headers, rows, title=f'BARKAV — {title}')
            messagebox.showinfo('خروجی', f'فایل ساخته شد:\n{path}', parent=self)
        except Exception as exc:
            messagebox.showerror('خروجی', str(exc), parent=self)

    def refresh_reports(self):
        super().refresh_reports()
        if not hasattr(self, 'report_summary_tree'): return
        phases = self._phase_summary_live(); est = sum(int(r.get('estimate') or 0) for r in phases); actual = sum(int(r.get('actual') or 0) for r in phases); forecast = sum(int(r.get('forecast') or 0) for r in phases)
        done = sum(1 for r in phases if int(r.get('actual') or 0) > 0); variance = forecast - est
        rows = [
            ('برآورد کل فازها', fa(f'{est:,}'), 'جمع برآورد اولیه فازهای پروژه'),
            ('واقعی ثبت‌شده', fa(f'{actual:,}'), 'جمع هزینه واقعی متصل به فازها'),
            ('پیش‌بینی نهایی', fa(f'{forecast:,}'), 'جمع پیش‌بینی به‌روز فازها'),
            ('انحراف پیش‌بینی', fa(f'{variance:,}'), 'پیش‌بینی منهای برآورد اولیه'),
            ('فازهای دارای عملکرد واقعی', fa(done), f'از {fa(len(phases))} فاز'),
        ]
        for i in self.report_summary_tree.get_children(): self.report_summary_tree.delete(i)
        for r in rows: self.report_summary_tree.insert('', 'end', values=r)

    def undo(self):
        ac = getattr(self, 'approval_center', None)
        try: in_data = bool(ac and getattr(self, 'approval_tab', None) and str(self.notebook.select()) == str(self.approval_tab))
        except Exception: in_data = False
        if in_data:
            msg = ac.undo_data_entry() if ac.can_undo() else 'عملیات قابل بازگشتی در ثبت دیتا وجود ندارد.'
            messagebox.showinfo('Undo', msg, parent=self); return
        messagebox.showinfo('Undo', self.rich.undo_last(), parent=self); self.refresh_all()

    def redo(self):
        ac = getattr(self, 'approval_center', None)
        try: in_data = bool(ac and getattr(self, 'approval_tab', None) and str(self.notebook.select()) == str(self.approval_tab))
        except Exception: in_data = False
        if in_data:
            msg = ac.redo_data_entry() if ac.can_redo() else 'عملیات قابل Redo در ثبت دیتا وجود ندارد.'
            messagebox.showinfo('Redo', msg, parent=self); return
        messagebox.showinfo('Redo', self.rich.redo_last(), parent=self); self.refresh_all()


Stage182Dashboard = _Stage182DashboardFinal
Stage18Dashboard = Stage182Dashboard
Stage181Dashboard = Stage182Dashboard
Stage175Dashboard = Stage182Dashboard
Stage17Dashboard = Stage182Dashboard


if __name__ == '__main__':
    Stage182Dashboard().mainloop()

v182 = _legacy_snapshot()

# ---- Extracted from dashboard_stage18_3.py ----

from copy import deepcopy
from datetime import datetime
from pathlib import Path
import os, sys, tempfile, threading, subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from v18_store import load_ui, save_ui, load_profile, save_profile
from unit_service import UnitService
from attachment_service import AttachmentService
from ui import (
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
        light=_is_light()
        colors={
            'هزینه ساخت':('#EAF5FA','#175A74') if light else ('#173E54','#E9FAFF'),
            'ورودی':('#E8F7F0','#176749') if light else ('#164B3A','#E7FFF5'),
            'خروجی':('#F5EAF8','#6D367C') if light else ('#493052','#FBEAFF'),
            'یادداشت':('#EEF1F5','#4B6071') if light else ('#314153','#EFF6FC'),
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
            self.output_var=tk.StringVar(value='خروجی')
            cb=ttk.Combobox(top,textvariable=self.output_var,state='readonly',values=['خروجی','PDF','Excel','پرینت'],width=18,justify='right')
            cb.pack(side='right',padx=4,pady=5);cb.bind('<<ComboboxSelected>>',self._output_selected,add='+');self.output_combo=cb
        except Exception:pass
    def _output_selected(self,_=None):
        mode=getattr(self,'output_var',tk.StringVar(value='')).get();
        try:self.output_var.set('خروجی')
        except Exception:pass
        if mode=='خروجی':return
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
        self.output_var=tk.StringVar(value='خروجی');out=ttk.Combobox(toolbar,textvariable=self.output_var,state='readonly',values=['خروجی','PDF','Excel','پرینت'],width=21,justify='right');out.pack(side='right',padx=5,pady=6);out.bind('<<ComboboxSelected>>',self._export_active,add='+')
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
        mode=self.output_var.get();self.output_var.set('خروجی')
        if mode=='خروجی':return
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
            self.report_export_mode.set('خروجی');cb=ttk.Combobox(bar,textvariable=self.report_export_mode,state='readonly',values=['خروجی','PDF','Excel','پرینت'],width=19,justify='right');cb.pack(side='right',padx=5,pady=5);cb.bind('<<ComboboxSelected>>',lambda e:self._report_output_selected(),add='+')
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
        mode=self.report_export_mode.get();self.report_export_mode.set('خروجی')
        mapping={'پرینت':'Print','PDF':'PDF','Excel':'Excel'}
        if mode not in mapping:return
        self.report_export_mode.set(mapping[mode]);self.export_report_choose();self.report_export_mode.set('خروجی')
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

v183 = _legacy_snapshot()

# ---- Extracted from dashboard_stage18_4.py ----

from copy import deepcopy
from pathlib import Path
import mimetypes, threading, tkinter as tk
from tkinter import ttk, messagebox, filedialog

from v18_store import load_ui, save_ui
from attachment_service import AttachmentService
from ui import fa, en, parse_int, group_int_fa, bind_grouped_number_fa, fetch_tgju_usd_toman
from ui import (
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
            'tx183_هزینه_ساخت':('#D9F1FB','#0C5878') if light else ('#145D7D','#F2FCFF'),
            'tx183_ورودی':('#DDF8EA','#126040') if light else ('#126846','#EFFFF7'),
            'tx183_خروجی':('#F2DFF8','#6A2479') if light else ('#693879','#FFF0FF'),
            'tx183_یادداشت':('#E6EDF5','#3E5870') if light else ('#3A5670','#F4FAFF'),
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

v184 = _legacy_snapshot()

# ---- Extracted from dashboard_stage18_5.py ----

import json
import tempfile
import threading
import zipfile
from copy import deepcopy
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from unit_service import UnitService
from telegram_history_import import import_telegram_export
from v18_store import load_profile, save_profile, load_ui, save_ui
from ui import (
    RtlNotebookStrip, fa, en, parse_int, parse_decimal, group_int_fa,
    group_decimal_fa, bind_grouped_number_fa, bind_grouped_decimal_fa,
    fetch_tgju_usd_toman,
)
from ui import retarget_smarttable_instance_184
from ui import (
    DARK_185, LIGHT_185, palette_185, bind_persian_digits,
    floor_name_185, normalize_floor_structure,
    attach_tree_grid_185, attach_table_visuals_recursive_185,
    build_brand_widget_185, style_ttk_185,
)


VERSION = '18.5'
BASE_DIR = v184.BASE_DIR
DB = v184.DB
APPROVAL = v184.APPROVAL
SERVICE = v184.SERVICE
DARK = v184.DARK
UNIT_USES = ('مسکونی', 'تجاری', 'اداری', 'آموزشی', 'سایر')


def _is_light() -> bool:
    try:
        return str(load_ui().get('appearance') or 'dark').lower() == 'light'
    except Exception:
        return False


def _walk(root):
    stack = [root]
    while stack:
        widget = stack.pop()
        yield widget
        try:
            stack.extend(widget.winfo_children())
        except Exception:
            pass


def _display_measure(value) -> str:
    number = parse_decimal(value)
    if float(number).is_integer():
        return group_int_fa(int(number), blank_zero=True)
    return group_decimal_fa(number)


def _bring_to_front(window: tk.Toplevel) -> None:
    """Raise a just-created editor after the Wizard has fully released its grab."""
    try:
        window.deiconify()
        window.lift()
        window.focus_force()
        window.attributes('-topmost', True)
        window.after(140, lambda: window.attributes('-topmost', False) if window.winfo_exists() else None)
    except Exception:
        pass


class UnifiedPendingEditor185(v184.UnifiedPendingEditor184):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title('ویرایش و تأیید رکورد — BARKAV 18.5')
        self.after_idle(lambda: _bring_to_front(self))


class TransactionWizard185(v184.TransactionWizard184):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title('ثبت تراکنش — Wizard — BARKAV 18.5')


class DataEntryCenter185(v184.DataEntryCenter184):
    """Stable preview, real Telegram-backup recall and fixed-size service badges."""

    def _build(self):
        # Skip the two 18.4 attachment-only chat buttons. 18.5 imports the backup
        # into Pending instead, using the existing approval-safe importer.
        v183.DataEntryCenter183._build(self)
        self._preview_signature_185 = None
        self._install_chat_backup_action()
        self._fix_service_badges()
        self.after_idle(self._row_colors_185)

    def _install_chat_backup_action(self):
        parent = getattr(self, '_center_data_actions', None)
        if parent is None:
            return
        p = palette_185(_is_light())
        self.chat_backup_button = tk.Button(
            parent,
            text='فراخوانی بکاپ چت',
            command=self.import_chat_backup,
            bg=p['glass'], fg=p['text'], activebackground=p['panel2'],
            relief='flat', padx=10, pady=6,
            font=('Segoe UI', max(9, int(load_ui().get('font_size') or 11) - 1), 'bold'),
        )
        self.chat_backup_button.pack(side='right', padx=4, pady=4)

    def _fix_service_badges(self):
        # Fixed character widths prevent Telegram/Gemini text changes from moving
        # the buttons beside them.
        for label in (getattr(self, 'bot_label', None), getattr(self, 'gemini_label', None)):
            if isinstance(label, tk.Label):
                label.configure(width=35, anchor='w', justify='left', padx=5)

    @staticmethod
    def _safe_zip_json(zip_path: Path, target: Path) -> Path:
        with zipfile.ZipFile(zip_path, 'r') as archive:
            root = target.resolve()
            for member in archive.infolist():
                resolved = (target / member.filename).resolve()
                if resolved != root and root not in resolved.parents:
                    raise ValueError('ساختار فایل ZIP امن نیست.')
            archive.extractall(target)
        json_files = list(target.rglob('result.json')) or list(target.rglob('*.json'))
        if not json_files:
            raise ValueError('فایل JSON تاریخچه در ZIP پیدا نشد.')
        return json_files[0]

    def import_chat_backup(self):
        path = filedialog.askopenfilename(
            parent=self,
            title='انتخاب بکاپ Telegram Desktop',
            filetypes=[('Telegram backup', '*.json *.zip'), ('JSON', '*.json'), ('ZIP', '*.zip')],
        )
        if not path:
            return
        try:
            source = Path(path)
            with tempfile.TemporaryDirectory(prefix='barkav_chat_') as temp_dir:
                json_path = self._safe_zip_json(source, Path(temp_dir)) if source.suffix.lower() == '.zip' else source
                result = import_telegram_export(DB, json_path, receipt_service=getattr(APPROVAL, 'receipts', None))
            summary = (
                f'چت‌ها: {fa(result.chats)}\n'
                f'پیام‌های بررسی‌شده: {fa(result.scanned)}\n'
                f'کاندیدهای مالی: {fa(result.candidates)}\n'
                f'پیش‌نویس جدید: {fa(result.created)}\n'
                f'تکراری: {fa(result.duplicates)}\n'
                f'رسانه پیدا نشده: {fa(result.media_missing)}'
            )
            messagebox.showinfo('فراخوانی بکاپ چت', summary, parent=self)
            self.refresh()
            ids = list(result.media_pending_ids or [])
            if ids and messagebox.askyesno(
                'تحلیل رسیدها',
                f'{fa(len(ids))} تصویر آماده تحلیل است. تحلیل در پس‌زمینه شروع شود؟\n\n'
                'هیچ رکوردی بدون تأیید شما اثر مالی نمی‌گیرد.',
                parent=self,
            ):
                self._run_ai_ids(ids)
        except Exception as exc:
            messagebox.showerror('فراخوانی بکاپ چت', str(exc), parent=self)

    def _row_colors_185(self):
        tree = self.table.tree
        light = _is_light()
        colors = {
            'tx183_هزینه_ساخت': ('#E7F3FF', '#185A88') if light else ('#244C67', '#F4FAFF'),
            'tx183_ورودی': ('#E8F8EF', '#216B4B') if light else ('#23513F', '#F1FFF8'),
            'tx183_خروجی': ('#F7ECFC', '#744082') if light else ('#503C5D', '#FFF5FF'),
            'tx183_یادداشت': ('#EEF3F8', '#496276') if light else ('#39495A', '#F5F9FC'),
        }
        for tag, (background, foreground) in colors.items():
            tree.tag_configure(tag, background=background, foreground=foreground)
        attach_tree_grid_185(tree, light=light)

    def refresh(self, *args, **kwargs):
        result = super().refresh(*args, **kwargs)
        self._row_colors_185()
        return result

    @staticmethod
    def _preview_signature(row: dict, path: str) -> tuple[str, str, str]:
        payload = json.dumps(row.get('payload') or {}, ensure_ascii=False, sort_keys=True, default=str)
        return str(row.get('pending_id') or ''), str(path or ''), payload

    def _show(self, row):
        path = self._path(row)
        signature = self._preview_signature(row, path)
        if signature == getattr(self, '_preview_signature_185', None):
            return
        self._preview_signature_185 = signature
        return super()._show(row)

    def _select18(self, event=None):
        rows = self.table.selected_rows()
        self.current = rows[-1] if rows else None
        if self.current:
            self._show(self.current)
        self.table._sync_checks()

    def open_editor(self, row=None):
        row = row or getattr(self, 'current', None)
        if not row:
            return
        pid = str(row.get('pending_id') or '')
        before = self._pending_snapshot(pid)

        def done():
            self._record_pending_edit(before)
            self._preview_signature_185 = None
            self.refresh()

        UnifiedPendingEditor185(self, row, self.rich, done)

    def open_wizard(self, row=None):
        row = row or getattr(self, 'current', None)
        if not row:
            return messagebox.showwarning('ثبت دیتا', 'یک سطر را انتخاب کن.', parent=self)
        pid = str(row.get('pending_id') or '')
        before = self._pending_snapshot(pid)

        def done():
            self._record_pending_edit(before)
            self._preview_signature_185 = None
            self.refresh()

        def full():
            def open_full_editor():
                fresh = DB.get_pending_item(pid) or row
                fresh = dict(fresh)
                fresh['raw_text'] = v18._raw_text(pid, row)
                self.open_editor(fresh)
            self.after_idle(open_full_editor)

        TransactionWizard185(self, row, self.rich, done, full)


class SettingsTab185(v184.SettingsTab184):
    """Settings rate is refreshed asynchronously and persisted at every app start."""

    def refresh_usd(self, silent: bool = False):
        if getattr(self, '_usd_job_running_185', False):
            return
        self._usd_job_running_185 = True
        self.usd_status.set('در حال دریافت نرخ دلار...')

        def job():
            try:
                rate, timestamp = fetch_tgju_usd_toman(timeout=6.0)
                error = ''
            except Exception as exc:
                rate, timestamp, error = 0, '', str(exc)

            def done():
                self._usd_job_running_185 = False
                if rate > 0:
                    self.vars['usd_rate_current'].set(group_int_fa(rate))
                    ui = load_ui()
                    ui['usd_rate_current'] = int(rate)
                    ui['usd_rate_updated_at'] = timestamp
                    save_ui(ui)
                    self.usd_status.set(f'آخرین بروزرسانی: {fa(timestamp.replace("T", " "))}')
                else:
                    self.usd_status.set('دریافت آنلاین انجام نشد؛ مقدار ذخیره/دستی حفظ شد.')
                    if error and not silent:
                        messagebox.showwarning('نرخ دلار', 'ارتباط با TGJU برقرار نشد؛ نرخ ذخیره‌شده حفظ شد.', parent=self)

            try:
                self.after(0, done)
            except Exception:
                pass

        threading.Thread(target=job, daemon=True).start()


class ProjectSettingsDialog185(v184.ProjectSettingsDialog184):
    ROLE_SPECS = {
        'executor': ['مجری'],
        'supervisor': ['معماری', 'سازه', 'مکانیک/تأسیسات', 'برق', 'گاز', 'آبفا', 'نقشه‌برداری'],
        'designer': ['معماری', 'سازه', 'مکانیک/تأسیسات', 'برق'],
        'admin_followup': ['مسئول پیگیری اداری'],
    }
    ROLE_TITLES = {
        'executor': 'مجری', 'supervisor': 'ناظر', 'designer': 'طراح',
        'admin_followup': 'مسئول پیگیری اداری',
    }
    TEAM_FIELDS = {
        'executor': [('name', 'نام'), ('phone', 'شماره تماس'), ('license_no', 'شماره پروانه/عضویت'), ('company', 'شرکت/دفتر')],
        'supervisor': [('name', 'نام'), ('phone', 'شماره تماس'), ('license_no', 'شماره پروانه/عضویت'), ('company', 'شرکت/دفتر')],
        'designer': [('name', 'نام'), ('phone', 'شماره تماس'), ('license_no', 'شماره پروانه/عضویت'), ('company', 'شرکت/دفتر')],
        'admin_followup': [('name', 'نام'), ('company', 'نام شرکت'), ('phone', 'شماره تماس')],
    }

    def __init__(self, *args, **kwargs):
        self.floor_rows: list[dict] = []
        self.floor_cards: list[dict] = []
        self._floor_rebuild_after = None
        super().__init__(*args, **kwargs)
        self.title('مشخصات پروژه — BARKAV 18.5')
        self.minsize(1160, 760)
        self.after_idle(lambda: attach_table_visuals_recursive_185(self, light=_is_light()))

    def _field_box(self, parent, row, column, key, label, value, *, kind='text'):
        p = palette_185(_is_light())
        box = tk.Frame(parent, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
        box.grid(row=row, column=column, sticky='ew', padx=5, pady=5)
        tk.Label(box, text=label, bg=p['panel'], fg=p['text'], font=('Segoe UI', self.font_size, 'bold')).pack(anchor='e', padx=6, pady=(6, 1))
        if kind == 'measure':
            shown = _display_measure(value)
        elif kind == 'number':
            shown = group_int_fa(value, blank_zero=True)
        elif kind == 'digits':
            shown = fa(value)
        else:
            shown = str(value or '')
        var = tk.StringVar(value=shown)
        self.vars[key] = var
        entry = ttk.Entry(box, textvariable=var, justify='right')
        entry.pack(fill='x', padx=6, pady=(1, 6))
        if kind == 'measure':
            bind_grouped_decimal_fa(entry, var)
        elif kind == 'number':
            bind_grouped_number_fa(entry, var)
        elif kind == 'digits':
            bind_persian_digits(entry, var)
        return entry

    def _build(self):
        p = palette_185(_is_light())
        self.configure(bg=p['bg'])
        self.vars = {}
        self.team_vars = {}
        self._team_hosts = {}
        self._team_filters = {}

        toolbar = tk.Frame(self, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
        toolbar.pack(fill='x', padx=8, pady=(8, 0))
        self.output_var = tk.StringVar(value='خروجی')
        output = ttk.Combobox(toolbar, textvariable=self.output_var, state='readonly',
                              values=['خروجی', 'PDF', 'Excel', 'پرینت'], width=21, justify='right')
        output.pack(side='right', padx=5, pady=6)
        output.bind('<<ComboboxSelected>>', self._export_active, add='+')

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill='both', expand=True, padx=8, pady=8)
        basic = ttk.Frame(self.nb, style='Panel.TFrame')
        floors = ttk.Frame(self.nb, style='Panel.TFrame')
        team = ttk.Frame(self.nb, style='Panel.TFrame')
        self.nb.add(basic, text='مشخصات پایه')
        self.nb.add(floors, text='طبقات و واحدها')
        self.nb.add(team, text='عوامل پروژه')
        self._project_tabs = {'مشخصات پایه': basic, 'طبقات و واحدها': floors, 'عوامل پروژه': team}
        self._rtl = RtlNotebookStrip(self.nb, bg=p['surface'], line=p['line'], text=p['text'], muted=p['muted'], active_bg=p['panel2'], active_fg=p['blue'])

        project = SERVICE.project.get_project()
        settings = SERVICE.budget.get_settings()
        meta = dict(self.profile.get('floor_meta') or {})
        total = parse_int(meta.get('total_floor_count')) or len(self.profile.get('floors') or [])
        parking = parse_int(meta.get('parking_floor_count'))
        negative = parse_int(meta.get('negative_floor_count'))
        card = v18.GlassSection(basic, 'مشخصات پروژه')
        card.pack(fill='x', padx=8, pady=8)
        body = card.body
        body.grid_columnconfigure((0, 1, 2), weight=1)
        definitions = [
            ('name', 'نام پروژه', project.get('name') or '', 'text'),
            ('address', 'آدرس', project.get('address') or '', 'text'),
            ('postal_code', 'کدپستی', project.get('postal_code') or '', 'digits'),
            ('registration_plate', 'پلاک ثبتی', project.get('registration_plate') or '', 'digits'),
            ('municipal_file_no', 'شماره پرونده شهرداری', project.get('municipal_file_no') or '', 'digits'),
            ('gross_area', 'متراژ کل/غیرمفید (M2)', settings.get('gross_area') or 0, 'measure'),
            ('saleable_area', 'متراژ مفید/فروشی (M2)', settings.get('saleable_area') or 0, 'measure'),
            ('unit_count', 'تعداد کل واحدها', settings.get('unit_count') or 0, 'number'),
            ('floor_count', 'تعداد کل طبقات', total, 'number'),
            ('parking_floor_count', 'تعداد طبقات پارکینگ', parking, 'number'),
            ('negative_floor_count', 'تعداد طبقات منفی', negative, 'number'),
        ]
        for index, (key, label, value, kind) in enumerate(definitions):
            self._field_box(body, index // 3, 2 - (index % 3), key, label, value, kind=kind)

        actions = tk.Frame(basic, bg=p['panel'])
        actions.pack(fill='x', padx=8, pady=(0, 8))
        tk.Button(actions, text='ایجاد/به‌روزرسانی ردیف‌های طبقات', command=self.rebuild_floor_rows,
                  bg=p['glass'], fg=p['text'], activebackground=p['panel2'], relief='flat', padx=14, pady=7).pack(side='right', padx=4)
        tk.Button(actions, text='ذخیره مشخصات پایه', command=self.save_basic_185,
                  bg=p['blue'], fg='#FFFFFF', activebackground=p['cyan'], relief='flat', padx=18, pady=7,
                  font=('Segoe UI', self.font_size, 'bold')).pack(side='right', padx=4)
        for key in ('floor_count', 'parking_floor_count', 'negative_floor_count'):
            self.vars[key].trace_add('write', lambda *_args: self._queue_floor_rebuild())

        floor_top = tk.Frame(floors, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
        floor_top.pack(fill='x', padx=8, pady=(8, 4))
        self.floor_summary = tk.StringVar(value='')
        tk.Label(floor_top, textvariable=self.floor_summary, bg=p['surface'], fg=p['muted'], anchor='e', justify='right').pack(side='right', fill='x', expand=True, padx=8, pady=7)
        tk.Button(floor_top, text='افزودن طبقه', command=self.add_floor_185, bg=p['glass'], fg=p['text'], relief='flat', padx=12, pady=6).pack(side='left', padx=4, pady=4)
        tk.Button(floor_top, text='ذخیره و همگام‌سازی واحدها', command=self.save_floors_185, bg=p['blue'], fg='#FFFFFF', relief='flat', padx=14, pady=6).pack(side='left', padx=4, pady=4)

        floor_shell = tk.Frame(floors, bg=p['panel'])
        floor_shell.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.floor_canvas = tk.Canvas(floor_shell, bg=p['panel'], highlightthickness=0)
        floor_scroll = ttk.Scrollbar(floor_shell, orient='vertical', command=self.floor_canvas.yview)
        self.floor_canvas.configure(yscrollcommand=floor_scroll.set)
        self.floor_canvas.pack(side='left', fill='both', expand=True)
        floor_scroll.pack(side='right', fill='y')
        self.floor_body = tk.Frame(self.floor_canvas, bg=p['panel'])
        self._floor_window = self.floor_canvas.create_window((0, 0), window=self.floor_body, anchor='nw')
        self.floor_body.bind('<Configure>', lambda _e: self.floor_canvas.configure(scrollregion=self.floor_canvas.bbox('all')), add='+')
        self.floor_canvas.bind('<Configure>', lambda e: self.floor_canvas.itemconfigure(self._floor_window, width=e.width), add='+')
        self.floor_canvas.bind('<MouseWheel>', lambda e: (self.floor_canvas.yview_scroll(int(-e.delta / 120), 'units'), 'break')[1], add='+')

        self._build_team_tab(team, p)
        self.floor_rows = normalize_floor_structure(total, parking, negative, list(self.profile.get('floors') or []))
        self._render_floor_cards()

    def _queue_floor_rebuild(self):
        try:
            if self._floor_rebuild_after:
                self.after_cancel(self._floor_rebuild_after)
            self._floor_rebuild_after = self.after(450, self.rebuild_floor_rows)
        except Exception:
            pass

    @staticmethod
    def _resized(items: list, count: int, factory):
        values = list(items or [])[:count]
        while len(values) < count:
            values.append(factory(len(values)))
        return values

    def _capture_floor_cards(self) -> list[dict]:
        if not self.floor_cards:
            return list(self.floor_rows)
        rows = []
        for card in self.floor_cards:
            units = []
            for number, usage, area in card['unit_vars']:
                units.append({'unit_number': en(number.get()).strip(), 'usage': usage.get().strip() or 'مسکونی', 'area': parse_decimal(area.get())})
            storage_areas = [parse_decimal(value.get()) for value in card['storage_vars']]
            unit_count = max(0, parse_int(card['unit_count'].get()))
            storage_count = max(0, parse_int(card['storage_count'].get()))
            units = self._resized(units, unit_count, lambda i: {'unit_number': str(i + 1), 'usage': 'مسکونی', 'area': 0})
            storage_areas = self._resized(storage_areas, storage_count, lambda _i: 0)
            rows.append({
                **card['source'],
                'floor': card['name'].get().strip() or floor_name_185(card['source']['floor_level']),
                'unit_count': unit_count,
                'units': units,
                'areas': [unit.get('area') or 0 for unit in units],
                'storage_count': storage_count,
                'storage_areas': storage_areas,
                'parking_supplied': parse_int(card['parking'].get()) if card['source'].get('is_parking') else 0,
            })
        return rows

    def rebuild_floor_rows(self, preserve=True):
        self._floor_rebuild_after = None
        existing = self._capture_floor_cards() if preserve else list(self.profile.get('floors') or [])
        total = parse_int(self.vars['floor_count'].get())
        parking = min(total, parse_int(self.vars['parking_floor_count'].get()))
        negative = min(total, parse_int(self.vars['negative_floor_count'].get()))
        self.floor_rows = normalize_floor_structure(total, parking, negative, existing)
        self._render_floor_cards()

    def _render_floor_cards(self):
        p = palette_185(_is_light())
        for child in self.floor_body.winfo_children():
            child.destroy()
        self.floor_cards = []
        unit_sequence = 1
        for index, source in enumerate(self.floor_rows):
            source = deepcopy(source)
            unit_count = max(0, parse_int(source.get('unit_count')))
            storage_count = max(0, parse_int(source.get('storage_count')))
            source['units'] = self._resized(list(source.get('units') or []), unit_count,
                                            lambda _i: {'unit_number': '', 'usage': 'مسکونی', 'area': 0})
            source['storage_areas'] = self._resized(list(source.get('storage_areas') or []), storage_count, lambda _i: 0)
            card = tk.Frame(self.floor_body, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
            card.pack(fill='x', padx=4, pady=5)
            head = tk.Frame(card, bg=p['panel2'])
            head.pack(fill='x')
            tk.Label(head, text=f'ردیف {fa(index + 1)}', bg=p['panel2'], fg=p['muted'], width=10, anchor='e').pack(side='right', padx=5, pady=6)
            name = tk.StringVar(value=str(source.get('floor') or floor_name_185(source.get('floor_level', 0))))
            ttk.Entry(head, textvariable=name, justify='right', width=25).pack(side='right', padx=4, pady=5)
            tk.Label(head, text='نام طبقه', bg=p['panel2'], fg=p['text']).pack(side='right', padx=(8, 2))
            unit_var = tk.StringVar(value=group_int_fa(unit_count))
            unit_entry = ttk.Entry(head, textvariable=unit_var, justify='center', width=8)
            unit_entry.pack(side='right', padx=4, pady=5)
            bind_grouped_number_fa(unit_entry, unit_var)
            tk.Label(head, text='تعداد واحد', bg=p['panel2'], fg=p['text']).pack(side='right', padx=(8, 2))
            storage_var = tk.StringVar(value=group_int_fa(storage_count))
            storage_entry = ttk.Entry(head, textvariable=storage_var, justify='center', width=8)
            storage_entry.pack(side='right', padx=4, pady=5)
            bind_grouped_number_fa(storage_entry, storage_var)
            tk.Label(head, text='تعداد انباری', bg=p['panel2'], fg=p['text']).pack(side='right', padx=(8, 2))
            parking = tk.StringVar(value=group_int_fa(source.get('parking_supplied') or 0, blank_zero=True))
            parking_entry = ttk.Entry(head, textvariable=parking, justify='center', width=9,
                                      state='normal' if source.get('is_parking') else 'disabled')
            parking_entry.pack(side='right', padx=4, pady=5)
            bind_grouped_number_fa(parking_entry, parking)
            tk.Label(head, text='پارکینگ تأمین‌شده', bg=p['panel2'], fg=p['text' if source.get('is_parking') else 'muted']).pack(side='right', padx=(8, 2))
            tk.Button(head, text='اعمال تعداد', command=self._redraw_floor_details, bg=p['glass'], fg=p['text'], relief='flat', padx=8, pady=4).pack(side='left', padx=3, pady=4)
            tk.Button(head, text='حذف سطر', command=lambda i=index: self.remove_floor_185(i), bg=p['red'], fg='#FFFFFF', relief='flat', padx=8, pady=4).pack(side='left', padx=3, pady=4)
            for entry in (unit_entry, storage_entry):
                entry.bind('<FocusOut>', lambda _e: self._queue_floor_detail_redraw(), add='+')
                entry.bind('<Return>', lambda _e: self._redraw_floor_details(), add='+')

            details = tk.Frame(card, bg=p['surface'])
            details.pack(fill='x', padx=8, pady=7)
            unit_vars = []
            if unit_count:
                tk.Label(details, text='واحدها', bg=p['surface'], fg=p['blue'], font=('Segoe UI', self.font_size, 'bold')).grid(row=0, column=3, sticky='e', padx=4, pady=(0, 4))
                for column, title in [(3, 'ردیف'), (2, 'شماره واحد'), (1, 'کاربری'), (0, 'متراژ')]:
                    tk.Label(details, text=title, bg=p['panel2'], fg=p['text'], anchor='center').grid(row=1, column=column, sticky='ew', padx=2, pady=2)
                details.grid_columnconfigure((0, 1, 2), weight=1)
                for unit_index, unit in enumerate(source['units'], 2):
                    number_text = str(unit.get('unit_number') or unit_sequence)
                    unit_sequence += 1
                    number = tk.StringVar(value=fa(number_text))
                    usage = tk.StringVar(value=str(unit.get('usage') or 'مسکونی'))
                    area = tk.StringVar(value=_display_measure(unit.get('area') or 0))
                    tk.Label(details, text=fa(unit_index - 1), bg=p['surface'], fg=p['muted']).grid(row=unit_index, column=3, sticky='ew', padx=2, pady=2)
                    number_entry = ttk.Entry(details, textvariable=number, justify='center')
                    number_entry.grid(row=unit_index, column=2, sticky='ew', padx=2, pady=2)
                    bind_persian_digits(number_entry, number)
                    ttk.Combobox(details, textvariable=usage, values=UNIT_USES, state='readonly', justify='right').grid(row=unit_index, column=1, sticky='ew', padx=2, pady=2)
                    area_entry = ttk.Entry(details, textvariable=area, justify='center')
                    area_entry.grid(row=unit_index, column=0, sticky='ew', padx=2, pady=2)
                    bind_grouped_decimal_fa(area_entry, area)
                    unit_vars.append((number, usage, area))
            else:
                tk.Label(details, text='این طبقه واحدی ندارد.', bg=p['surface'], fg=p['muted']).grid(row=0, column=0, columnspan=4, sticky='e', pady=4)

            storage_vars = []
            storage_start = max(3, unit_count + 3)
            if storage_count:
                tk.Label(details, text='متراژ انباری‌ها', bg=p['surface'], fg=p['blue'], font=('Segoe UI', self.font_size, 'bold')).grid(row=storage_start, column=3, sticky='e', padx=4, pady=(8, 3))
                for storage_index, stored in enumerate(source['storage_areas'], 1):
                    value = tk.StringVar(value=_display_measure(stored))
                    tk.Label(details, text=f'انباری {fa(storage_index)}', bg=p['surface'], fg=p['text']).grid(row=storage_start + storage_index, column=3, sticky='e', padx=4, pady=2)
                    entry = ttk.Entry(details, textvariable=value, justify='center')
                    entry.grid(row=storage_start + storage_index, column=2, sticky='ew', padx=2, pady=2)
                    bind_grouped_decimal_fa(entry, value)
                    storage_vars.append(value)
            self.floor_cards.append({
                'source': source, 'name': name, 'unit_count': unit_var,
                'storage_count': storage_var, 'parking': parking,
                'unit_vars': unit_vars, 'storage_vars': storage_vars,
            })
        parking = sum(1 for row in self.floor_rows if row.get('is_parking'))
        self.floor_summary.set(
            f'چیدمان از پایین به بالا — {fa(len(self.floor_rows))} طبقه، '
            f'{fa(parking)} طبقه پارکینگ؛ پارکینگ فقط در پایین‌ترین طبقات فعال است.'
        )

    def _queue_floor_detail_redraw(self):
        try:
            if self._floor_rebuild_after:
                self.after_cancel(self._floor_rebuild_after)
            self._floor_rebuild_after = self.after(220, self._redraw_floor_details)
        except Exception:
            pass

    def _redraw_floor_details(self):
        self._floor_rebuild_after = None
        self.floor_rows = self._capture_floor_cards()
        self._render_floor_cards()

    def add_floor_185(self):
        existing = self._capture_floor_cards()
        total = len(existing) + 1
        self.vars['floor_count'].set(group_int_fa(total))
        self.floor_rows = normalize_floor_structure(total, self.vars['parking_floor_count'].get(), self.vars['negative_floor_count'].get(), existing)
        self._render_floor_cards()

    def remove_floor_185(self, index: int):
        rows = self._capture_floor_cards()
        if not (0 <= index < len(rows)):
            return
        removed = rows.pop(index)
        total = len(rows)
        negative = min(total, parse_int(self.vars['negative_floor_count'].get()) - (1 if int(removed.get('floor_level', 0)) < 0 else 0))
        parking = min(total, parse_int(self.vars['parking_floor_count'].get()) - (1 if removed.get('is_parking') else 0))
        self.vars['floor_count'].set(group_int_fa(total))
        self.vars['negative_floor_count'].set(group_int_fa(max(0, negative), blank_zero=True))
        self.vars['parking_floor_count'].set(group_int_fa(max(0, parking), blank_zero=True))
        self.floor_rows = normalize_floor_structure(total, parking, negative, rows)
        self._render_floor_cards()

    def save_basic_185(self):
        try:
            total = max(0, parse_int(self.vars['floor_count'].get()))
            parking = max(0, parse_int(self.vars['parking_floor_count'].get()))
            negative = max(0, parse_int(self.vars['negative_floor_count'].get()))
            if parking > total or negative > total:
                raise ValueError('تعداد طبقات پارکینگ و منفی نمی‌تواند از تعداد کل طبقات بیشتر باشد.')
            SERVICE.project.save_project(
                name=self.vars['name'].get(), address=self.vars['address'].get(),
                postal_code=en(self.vars['postal_code'].get()),
                registration_plate=en(self.vars['registration_plate'].get()),
                municipal_file_no=en(self.vars['municipal_file_no'].get()),
            )
            # Explicit parsing fixes the prior edit/save path that could append a zero.
            SERVICE.budget.save_settings(
                gross_area=parse_decimal(self.vars['gross_area'].get()),
                saleable_area=parse_decimal(self.vars['saleable_area'].get()),
                unit_count=parse_int(self.vars['unit_count'].get()),
            )
            self.profile['floor_meta'] = {
                'total_floor_count': total,
                'parking_floor_count': parking,
                'negative_floor_count': negative,
            }
            self.floor_rows = normalize_floor_structure(total, parking, negative, self._capture_floor_cards())
            self.profile['floors'] = self.floor_rows
            save_profile(self.profile)
            self._render_floor_cards()
            if self.on_refresh:
                self.on_refresh()
            messagebox.showinfo('مشخصات پروژه', 'مشخصات پایه با ارقام فارسی و مقادیر صحیح ذخیره شد.', parent=self)
        except Exception as exc:
            messagebox.showerror('مشخصات پروژه', str(exc), parent=self)

    def _validated_floor_rows(self) -> list[dict]:
        rows = self._capture_floor_cards()
        seen = set()
        for row in rows:
            for unit in row.get('units') or []:
                number = en(unit.get('unit_number') or '').strip()
                if not number:
                    raise ValueError(f"شماره یکی از واحدهای «{row.get('floor')}» خالی است.")
                if number in seen:
                    raise ValueError(f'شماره واحد {fa(number)} تکراری است.')
                seen.add(number)
                unit['unit_number'] = number
                if unit.get('usage') not in UNIT_USES:
                    unit['usage'] = 'سایر'
            row['unit_count'] = len(row.get('units') or [])
            row['areas'] = [unit.get('area') or 0 for unit in row.get('units') or []]
        return rows

    def save_floors_185(self):
        try:
            floors = self._validated_floor_rows()
            self.profile['floors'] = floors
            self.profile['floor_meta'] = {
                'total_floor_count': len(floors),
                'parking_floor_count': sum(1 for row in floors if row.get('is_parking')),
                'negative_floor_count': sum(1 for row in floors if int(row.get('floor_level', 0)) < 0),
            }
            save_profile(self.profile)
            units = UnitService(DB)
            existing = units.list_units(include_cancelled=False)
            by_number = {str(row.get('unit_number') or ''): row for row in existing}
            project_name = SERVICE.project.get_project().get('name') or ''
            sync_errors = []
            all_areas = []
            for floor in floors:
                for unit in floor.get('units') or []:
                    number = str(unit.get('unit_number') or '')
                    area = float(unit.get('area') or 0)
                    all_areas.append(area)
                    try:
                        if number in by_number:
                            units.update_unit(by_number[number]['unit_id'], floor=floor['floor'], area=area)
                        else:
                            units.add_unit(floor=floor['floor'], unit_number=number, area=area, project_name=project_name)
                    except Exception as exc:
                        sync_errors.append(f'{fa(number)}: {exc}')
            SERVICE.budget.save_settings(unit_count=len(all_areas), unit_areas=all_areas)
            self.vars['unit_count'].set(group_int_fa(len(all_areas), blank_zero=True))
            if sync_errors:
                messagebox.showwarning('همگام‌سازی واحدها', 'ساختار ذخیره شد، اما این واحدها همگام نشدند:\n' + '\n'.join(sync_errors[:8]), parent=self)
            else:
                messagebox.showinfo('طبقات و واحدها', 'ساختار طبقات، واحدها، انباری‌ها و پارکینگ‌ها ذخیره و همگام شد.', parent=self)
            if self.on_refresh:
                self.on_refresh()
        except Exception as exc:
            messagebox.showerror('طبقات و واحدها', str(exc), parent=self)

    # Compatibility with buttons/method references inherited from earlier stages.
    save_basic_183 = save_basic_185
    save_basic_181 = save_basic_185
    save_floors_181 = save_floors_185

    def _build_team_tab(self, team, p):
        shell = tk.Frame(team, bg=p['panel'])
        shell.pack(fill='both', expand=True, padx=8, pady=8)
        canvas = tk.Canvas(shell, bg=p['panel'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(shell, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        body = tk.Frame(canvas, bg=p['panel'])
        window = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')), add='+')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width), add='+')
        canvas.bind('<MouseWheel>', lambda e: (canvas.yview_scroll(int(-e.delta / 120), 'units'), 'break')[1], add='+')
        old = self.profile.get('team') or {}
        for role, disciplines in self.ROLE_SPECS.items():
            self.team_vars[role] = {}
            for discipline in disciplines:
                role_data = old.get(role) if isinstance(old.get(role), dict) else {}
                data = role_data.get(discipline, {}) if isinstance(role_data.get(discipline), dict) else role_data
                self.team_vars[role][discipline] = {
                    field: tk.StringVar(value=fa(str((data or {}).get(field, '') or '')))
                    for field, _label in self.TEAM_FIELDS[role]
                }
            section = v18.GlassSection(body, self.ROLE_TITLES[role])
            section.pack(fill='x', padx=4, pady=5)
            head = tk.Frame(section.body, bg=p['panel'])
            head.pack(fill='x')
            if len(disciplines) > 1:
                filter_var = tk.StringVar(value='همه')
                self._team_filters[role] = filter_var
                combo = ttk.Combobox(head, textvariable=filter_var, state='readonly', values=['همه'] + disciplines, width=22, justify='right')
                combo.pack(side='right', padx=4, pady=4)
                combo.bind('<<ComboboxSelected>>', lambda _e, r=role: self._render_team_role_185(r), add='+')
            host = tk.Frame(section.body, bg=p['panel'])
            host.pack(fill='x')
            self._team_hosts[role] = host
            self._render_team_role_185(role)
        tk.Button(body, text='ذخیره عوامل پروژه', command=self.save_team_185, bg=p['blue'], fg='#FFFFFF', relief='flat',
                  font=('Segoe UI', self.font_size, 'bold'), padx=18, pady=8).pack(anchor='e', padx=8, pady=8)

    def _render_team_role_185(self, role):
        p = palette_185(_is_light())
        host = self._team_hosts.get(role)
        if host is None:
            return
        for child in host.winfo_children():
            child.destroy()
        wanted = self._team_filters[role].get() if role in self._team_filters else self.ROLE_SPECS[role][0]
        disciplines = self.ROLE_SPECS[role] if wanted == 'همه' else [wanted]
        for discipline in disciplines:
            group = tk.LabelFrame(host, text=discipline, bg=p['panel'], fg=p['muted'])
            group.pack(fill='x', padx=4, pady=4)
            for field, label in self.TEAM_FIELDS[role]:
                row = tk.Frame(group, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
                row.pack(fill='x', padx=4, pady=2)
                tk.Label(row, text=label, bg=p['panel'], fg=p['text'], width=18, anchor='e').pack(side='right', padx=4)
                entry = ttk.Entry(row, textvariable=self.team_vars[role][discipline][field], justify='right')
                entry.pack(side='right', fill='x', expand=True, padx=4, pady=3)
                if field == 'phone':
                    bind_persian_digits(entry, self.team_vars[role][discipline][field])

    def save_team_185(self):
        self.profile['team'] = {
            role: {
                discipline: {field: value.get().strip() for field, value in values.items()}
                for discipline, values in disciplines.items()
            }
            for role, disciplines in self.team_vars.items()
        }
        save_profile(self.profile)
        messagebox.showinfo('عوامل پروژه', 'عوامل پروژه و مسئول پیگیری اداری ذخیره شدند.', parent=self)

    save_team_181 = save_team_185

    def _active_export_data(self):
        label = self.nb.tab(self.nb.select(), 'text')
        if label == 'مشخصات پایه':
            labels = {
                'name': 'نام پروژه', 'address': 'آدرس', 'postal_code': 'کدپستی',
                'registration_plate': 'پلاک ثبتی', 'municipal_file_no': 'شماره پرونده شهرداری',
                'gross_area': 'متراژ کل/غیرمفید', 'saleable_area': 'متراژ مفید/فروشی',
                'unit_count': 'تعداد کل واحدها', 'floor_count': 'تعداد کل طبقات',
                'parking_floor_count': 'تعداد طبقات پارکینگ', 'negative_floor_count': 'تعداد طبقات منفی',
            }
            return label, ['عنوان', 'مقدار'], [[title, self.vars[key].get()] for key, title in labels.items()]
        if label == 'طبقات و واحدها':
            headers = ['ردیف', 'نام طبقه', 'تعداد واحد', 'جزئیات واحدها', 'تعداد انباری', 'متراژ انباری‌ها', 'پارکینگ تأمین‌شده']
            rows = []
            for index, floor in enumerate(self._capture_floor_cards(), 1):
                units = ' | '.join(f"{fa(u.get('unit_number'))}، {u.get('usage')}، {fa(u.get('area'))}" for u in floor.get('units') or [])
                rows.append([fa(index), floor.get('floor'), fa(floor.get('unit_count')), units,
                             fa(floor.get('storage_count')), '، '.join(fa(x) for x in floor.get('storage_areas') or []),
                             fa(floor.get('parking_supplied')) if floor.get('is_parking') else 'غیرفعال'])
            return label, headers, rows
        headers = ['نقش', 'رشته', 'نام', 'نام شرکت', 'شماره تماس', 'شماره پروانه/عضویت']
        rows = []
        for role, disciplines in self.team_vars.items():
            for discipline, values in disciplines.items():
                value = lambda key: values[key].get() if key in values else ''
                rows.append([self.ROLE_TITLES[role], discipline, value('name'), value('company'),
                             value('phone'), value('license_no')])
        return label, headers, rows


class SystemTab185(tk.Frame):
    def __init__(self, parent, app):
        p = palette_185(_is_light())
        super().__init__(parent, bg=p['bg'])
        self.app = app
        card = v18.GlassSection(self, 'سیستم')
        card.pack(fill='x', padx=12, pady=12)
        self.status = tk.StringVar(value='')
        tk.Label(card.body, textvariable=self.status, bg=p['panel'], fg=p['text'], justify='right', anchor='ne',
                 font=('Segoe UI', 10), padx=12, pady=12).pack(fill='x')
        actions = tk.Frame(card.body, bg=p['panel'])
        actions.pack(fill='x', pady=8)
        ttk.Button(actions, text='بروزرسانی وضعیت', command=self.refresh).pack(side='right', padx=4)
        ttk.Button(actions, text='بسته توسعه', command=self.app.export_development_package).pack(side='right', padx=4)
        ttk.Button(actions, text='مشخصات پروژه', command=self.app.edit_project_settings).pack(side='right', padx=4)
        self.refresh()

    def refresh(self):
        process = getattr(self.app, '_bot_process', None)
        bot = 'در حال اجرا' if process and process.poll() is None else 'متوقف/نامشخص'
        db_path = getattr(DB, 'db_path', getattr(DB, 'path', '-'))
        self.status.set(
            f'نسخه برنامه: {fa(VERSION)}\n'
            f'وضعیت دیتابیس: آماده\nTelegram Bot: {bot}\nمسیر دیتابیس: {fa(db_path)}\n'
            'AutoSave و رخدادهای مالی از مسیر دیتابیس همین پروژه مدیریت می‌شوند.'
        )


class Stage185Dashboard(v184.Stage184Dashboard):
    _VISIBLE_NAV = v184.Stage184Dashboard._VISIBLE_NAV

    def __init__(self):
        self._table_upgrade_pending_185 = set()
        super().__init__()
        self.title('BARKAV — Engineering & Construction — Version 18.5')
        self.after_idle(self._finalize_185)
        self.after(650, self._startup_usd_refresh_185)

    def _style(self):
        v183._THEME_DARK_183.update(DARK_185)
        v183._THEME_LIGHT_183.update(LIGHT_185)
        super()._style()
        p = palette_185(_is_light())
        DARK.update(p)
        style_ttk_185(self, light=_is_light(), font_size=int(load_ui().get('font_size') or 11),
                      row_height=int(load_ui().get('row_height') or 38))

    def _build_approval_center(self):
        tab = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.approval_tab = tab
        self.notebook.insert(1, tab, text='ثبت دیتا')
        self.approval_center = DataEntryCenter185(tab, self.rich, on_posted=self.refresh_all)
        self.approval_center.pack(fill='both', expand=True)
        if self._bot_process:
            self.approval_center.set_bot_process(self._bot_process, self._bot_log)
        self.after_idle(self._rebuild_navbar)

    def _build_settings(self):
        tab = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.notebook.add(tab, text='تنظیمات')
        self.settings_tab185 = SettingsTab185(tab, self._settings_saved)
        self.settings_tab185.pack(fill='both', expand=True)

    def _build_system(self):
        tab = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.notebook.add(tab, text='سیستم')
        self.system_tab185 = SystemTab185(tab, self)
        self.system_tab185.pack(fill='both', expand=True)

    def _build_reports(self):
        super()._build_reports()
        self._rebuild_financial_indices_185()

    def _rebuild_financial_indices_185(self):
        p = palette_185(_is_light())
        target = None
        target_index = 1
        for index, tab_id in enumerate(self.report_main.tabs()):
            if self.report_main.tab(tab_id, 'text') == 'شاخص‌های مالی':
                target = self.nametowidget(tab_id)
                target_index = index
                break
        if target is not None:
            self.report_main.forget(target)
            target.destroy()
        root = ttk.Frame(self.report_main, style='Panel.TFrame')
        remaining_tabs = self.report_main.tabs()
        insert_at = target_index if 0 <= target_index < len(remaining_tabs) else 'end'
        self.report_main.insert(insert_at, root, text='شاخص‌های مالی')
        self.report_indices_root = root
        pane = ttk.Panedwindow(root, orient='horizontal')
        pane.pack(fill='both', expand=True, padx=6, pady=6)
        results = ttk.Frame(pane, style='Panel.TFrame')
        params = ttk.Frame(pane, style='Panel.TFrame')
        pane.add(results, weight=3)
        pane.add(params, weight=2)
        self.report_indices_pane185 = pane
        self._report_split_initialized_185 = False

        def initialize_split(_event=None):
            if self._report_split_initialized_185:
                return
            width = pane.winfo_width()
            if width > 600:
                pane.sashpos(0, int(width * 0.57))
                self._report_split_initialized_185 = True

        pane.bind('<Configure>', initialize_split, add='+')
        self.after(220, initialize_split)

        result_card = v18.GlassSection(results, 'شاخص‌ها و سه سناریوی برآورد')
        result_card.pack(fill='both', expand=True, padx=(0, 4))
        self.index_table = ttk.Treeview(result_card.body, columns=('metric', 's1', 's2', 's3'), show='headings', height=15)
        for column, title, width, anchor in [
            ('metric', 'شاخص', 250, 'e'), ('s1', 'برآورد اولیه', 170, 'center'),
            ('s2', 'انجام‌شده + بروز تا پایان', 190, 'center'), ('s3', 'بروز صفر تا ۱۰۰', 175, 'center'),
        ]:
            self.index_table.heading(column, text=title, anchor=anchor)
            self.index_table.column(column, width=width, anchor=anchor)
        self.index_table.configure(displaycolumns=('s3', 's2', 's1', 'metric'))
        self.index_table.pack(fill='both', expand=True, padx=5, pady=5)
        attach_tree_grid_185(self.index_table, light=_is_light())
        self.report_cards = {}

        param_card = v18.GlassSection(params, 'پارامترهای برآورد')
        param_card.pack(fill='both', expand=True, padx=(4, 0))
        body = param_card.body
        body.grid_columnconfigure((0, 1), weight=1)
        self.report_vars = {key: tk.StringVar() for key in [
            'gross_area', 'saleable_area', 'unit_count', 'inflation', 'months',
            'presale', 'end_price', 'misc', 'target', 'external_injection',
        ]}
        fields = [
            ('gross_area', 'زیربنای غیرمفید (M2)', 'decimal'), ('saleable_area', 'زیربنای مفید (M2)', 'decimal'),
            ('unit_count', 'تعداد واحدها', 'int'), ('inflation', 'تورم ماهانه %', 'decimal'),
            ('months', 'ماه تا اتمام', 'int'), ('presale', 'قیمت پیش‌فروش / M2', 'int'),
            ('end_price', 'قیمت فروش پایان / M2', 'int'), ('misc', 'متفرقه خارج برآورد', 'int'),
            ('target', 'سود هدف %', 'decimal'), ('external_injection', 'تزریق پول خارج پروژه', 'int'),
        ]
        for index, (key, label, kind) in enumerate(fields):
            box = tk.Frame(body, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
            box.grid(row=index // 2, column=1 - (index % 2), sticky='ew', padx=4, pady=4)
            tk.Label(box, text=label, bg=p['panel'], fg=p['text']).pack(anchor='e', padx=5, pady=(4, 1))
            entry = ttk.Entry(box, textvariable=self.report_vars[key], justify='right')
            entry.pack(fill='x', padx=5, pady=(1, 5))
            if kind == 'int':
                bind_grouped_number_fa(entry, self.report_vars[key])
            else:
                bind_grouped_decimal_fa(entry, self.report_vars[key])
        actions = tk.Frame(body, bg=p['panel'])
        actions.grid(row=5, column=0, columnspan=2, sticky='ew', padx=4, pady=8)
        tk.Button(actions, text='محاسبه', command=self.calculate_financial_indices, bg=p['blue'], fg='#FFFFFF', relief='flat', padx=18, pady=8,
                  font=('Segoe UI', 10, 'bold')).pack(side='right', padx=3)
        tk.Button(actions, text='ذخیره پارامترها', command=self.save_report_settings_181, bg=p['glass'], fg=p['text'], relief='flat', padx=12, pady=8).pack(side='right', padx=3)

    def save_report_settings_181(self):
        try:
            SERVICE.budget.save_settings(
                gross_area=parse_decimal(self.report_vars['gross_area'].get()),
                saleable_area=parse_decimal(self.report_vars['saleable_area'].get()),
                unit_count=parse_int(self.report_vars['unit_count'].get()),
                monthly_inflation=parse_decimal(self.report_vars['inflation'].get()),
                remaining_months=parse_int(self.report_vars['months'].get()),
                presale_price_per_m2=parse_int(self.report_vars['presale'].get()),
                end_sale_price_override=(parse_int(self.report_vars['end_price'].get()) if self.report_vars['end_price'].get().strip() else None),
                unbudgeted_misc=parse_int(self.report_vars['misc'].get()),
                target_profit_percent=parse_decimal(self.report_vars['target'].get()),
            )
            ui = load_ui()
            ui['external_injection'] = parse_int(self.report_vars['external_injection'].get())
            save_ui(ui)
            messagebox.showinfo('گزارش‌گیری', 'پارامترها ذخیره شدند.', parent=self)
        except Exception as exc:
            messagebox.showerror('گزارش‌گیری', str(exc), parent=self)

    def edit_project_settings(self):
        ProjectSettingsDialog185(self, self.refresh_all)

    def _replace_brand_184(self):
        if getattr(self, '_brand_host_185', None):
            return
        old_host = getattr(self, '_brand_host_184', None)
        if old_host is not None:
            try:
                old_host.destroy()
            except Exception:
                pass
        old = None
        top = None
        for widget in _walk(self):
            if isinstance(widget, tk.Label):
                try:
                    if str(widget.cget('image')) and widget.master is not None and int(widget.master.winfo_height() or 0) <= 110:
                        old = widget
                        top = widget.master
                        break
                except Exception:
                    pass
        if top is None:
            return
        try:
            old.destroy()
        except Exception:
            pass
        p = palette_185(_is_light())
        self._brand_host_185 = build_brand_widget_185(top, BASE_DIR / 'assets' / 'BARKAV_shortcut.png', bg=p['surface'], fg=p['text'], muted=p['muted'])
        self._brand_host_185.pack(side='left', padx=(14, 6), pady=4)

    def _fix_clock_185(self):
        label = self._find_datetime_label()
        if label is None:
            return
        p = palette_185(_is_light())
        label.configure(width=27, anchor='center', justify='center', bg=p['glass'], fg=p['text'],
                        highlightbackground=p['line'], highlightcolor=p['line'], highlightthickness=1,
                        padx=8, pady=5, font=('Segoe UI', max(9, int(load_ui().get('font_size') or 11) - 1), 'bold'))

    def _sync_nav(self):
        try:
            selected = str(self.notebook.select())
        except Exception:
            return
        p = palette_185(_is_light())
        for tab_id, button in self.nav_buttons.items():
            active = str(tab_id) == selected
            button.configure(
                bg=p['panel2'] if active else p['surface'],
                fg=p['blue'] if active else p['muted'],
                activebackground=p['panel2'], activeforeground=p['blue'],
                relief='flat', bd=0, highlightbackground=p['blue'] if active else p['line'],
                highlightthickness=1,
            )

    def _upgrade_tables_184(self, root=None):
        root = root or self
        key = str(root)
        if key in self._table_upgrade_pending_185:
            return
        self._table_upgrade_pending_185.add(key)

        def apply():
            self._table_upgrade_pending_185.discard(key)
            light = _is_light()
            font_size = int(load_ui().get('font_size') or 11)
            for widget in _walk(root):
                if hasattr(widget, 'tree') and hasattr(widget, 'set_rows'):
                    try:
                        retarget_smarttable_instance_184(widget, font_size=font_size, light=light)
                    except Exception:
                        pass
                if isinstance(widget, ttk.Treeview):
                    try:
                        attach_tree_grid_185(widget, light=light)
                        for iid in widget.get_children(''):
                            values = list(widget.item(iid, 'values') or ())
                            translated = [fa(value) for value in values]
                            if values != translated:
                                widget.item(iid, values=translated)
                    except Exception:
                        pass
            attach_table_visuals_recursive_185(root, light=light)

        try:
            root.after_idle(apply)
        except Exception:
            apply()

    def _startup_usd_refresh_185(self):
        settings = getattr(self, 'settings_tab185', None)
        if settings is not None:
            settings.refresh_usd(silent=True)

    def _finalize_185(self):
        p = palette_185(_is_light())
        self.configure(bg=p['bg'])
        self._replace_brand_184()
        self._fix_clock_185()
        self._sync_nav()
        self._upgrade_tables_184(self)
        try:
            self.approval_center._fix_service_badges()
            self.approval_center._row_colors_185()
        except Exception:
            pass
        try:
            self.iconbitmap(default=str(BASE_DIR / 'assets' / 'BARKAV_18_5.ico'))
        except Exception:
            pass

    def _open_new_record_editor_184(self, row: dict):
        pending_id = self._pending_from_posted_row(row)
        if not pending_id:
            return messagebox.showinfo('ویرایش رکورد', 'این رکورد قدیمی به Pending اصلی متصل نیست؛ برای حفظ ایمنی مالی ویرایش نشد.', parent=self)
        pending = DB.get_pending_item(pending_id)
        if not pending:
            return messagebox.showwarning('ویرایش رکورد', 'رکورد مبدا پیدا نشد.', parent=self)
        pending = dict(pending)
        pending['raw_text'] = v18._raw_text(pending_id, pending)
        UnifiedPendingEditor185(self, pending, self.rich, self.refresh_all)

    def export_development_package(self):
        destination = filedialog.asksaveasfilename(
            parent=self, defaultextension='.zip', initialfile='BARKAV_Development_Package_18.5.zip',
            filetypes=[('ZIP', '*.zip')],
        )
        if not destination:
            return
        try:
            from development_package_v185 import build_development_package
            result = build_development_package(BASE_DIR, Path(destination), VERSION)
            messagebox.showinfo('بسته توسعه', f"بسته توسعه {VERSION} ساخته شد:\n{result['path']}\n\nدیتابیس زنده و secrets وارد بسته نشده‌اند.", parent=self)
        except Exception as exc:
            messagebox.showerror('بسته توسعه', str(exc), parent=self)


Stage185DashboardFinal = Stage185Dashboard
Stage184Dashboard = Stage185Dashboard
Stage183Dashboard = Stage185Dashboard
Stage182Dashboard = Stage185Dashboard
Stage18Dashboard = Stage185Dashboard


if __name__ == '__main__':
    Stage185Dashboard().mainloop()

v185 = _legacy_snapshot()

# ---- Extracted from dashboard_stage18_6.py ----

from copy import deepcopy
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from unit_service import UnitService
from v18_store import load_ui, save_profile
from ui import (
    RtlNotebookStrip,
    en,
    fa,
    parse_int,
    parse_decimal,
    group_int_fa,
    group_decimal_fa,
    bind_grouped_number_fa,
    bind_grouped_decimal_fa,
)
from ui import (
    DARK_186,
    LIGHT_186,
    DashboardCard186,
    CompactMetric186,
    attach_tree_grid_186,
    bind_persian_digits,
    build_brand_widget_186,
    convert_tree_currency_186,
    currency_unit_186,
    format_currency_186,
    normalize_floor_structure_186,
    palette_186,
    parse_display_amount_186,
    retarget_smarttable_186,
    style_ttk_186,
)


VERSION = '18.6'
BASE_DIR = v185.BASE_DIR
DB = v185.DB
APPROVAL = v185.APPROVAL
SERVICE = v185.SERVICE
DARK = v185.DARK
UNIT_USES = v185.UNIT_USES

def _is_light() -> bool:
    try:
        return str(load_ui().get('appearance') or 'dark').lower() == 'light'
    except Exception:
        return False


def _walk(root):
    stack = [root]
    while stack:
        widget = stack.pop()
        yield widget
        try:
            stack.extend(widget.winfo_children())
        except Exception:
            pass


def _display_measure(value) -> str:
    number = parse_decimal(value)
    if float(number).is_integer():
        return group_int_fa(int(number), blank_zero=True)
    return group_decimal_fa(number)


class UnifiedPendingEditor186(v185.UnifiedPendingEditor185):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title('ویرایش و تأیید رکورد — BARKAV 18.6')


class TransactionWizard186(v185.TransactionWizard185):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title('ثبت تراکنش — Wizard — BARKAV 18.6')


class DataEntryCenter186(v185.DataEntryCenter185):
    """18.6 Data Entry styling: subtle grids, pastel grouping and framed service state."""

    def _fix_service_badges(self):
        p = palette_186(_is_light())
        for label in (getattr(self, 'bot_label', None), getattr(self, 'gemini_label', None)):
            if isinstance(label, tk.Label):
                label.configure(
                    width=33,
                    height=1,
                    anchor='w',
                    justify='left',
                    bg=p['panel2'],
                    fg=p['text'],
                    highlightbackground=p['line'],
                    highlightcolor=p['line'],
                    highlightthickness=1,
                    relief='flat',
                    padx=8,
                    pady=4,
                )

    def _row_colors_185(self):
        tree = self.table.tree
        light = _is_light()
        colors = {
            'tx183_هزینه_ساخت': ('#EDF6FF', '#245A7C') if light else ('#183047', '#EAF6FF'),
            'tx183_ورودی': ('#EFF9F3', '#286047') if light else ('#19372E', '#ECFAF2'),
            'tx183_خروجی': ('#F8F1FB', '#654A70') if light else ('#30283A', '#F7EEFB'),
            'tx183_یادداشت': ('#F3F6F9', '#536476') if light else ('#25303D', '#EEF3F8'),
        }
        for tag, (background, foreground) in colors.items():
            tree.tag_configure(tag, background=background, foreground=foreground)
        attach_tree_grid_186(tree, light=light)

    def open_editor(self, row=None):
        row = row or getattr(self, 'current', None)
        if not row:
            return
        pending_id = str(row.get('pending_id') or '')
        before = self._pending_snapshot(pending_id)

        def done():
            self._record_pending_edit(before)
            self._preview_signature_185 = None
            self.refresh()

        UnifiedPendingEditor186(self, row, self.rich, done)

    def open_wizard(self, row=None):
        row = row or getattr(self, 'current', None)
        if not row:
            return messagebox.showwarning('ثبت دیتا', 'یک سطر را انتخاب کن.', parent=self)
        pending_id = str(row.get('pending_id') or '')
        before = self._pending_snapshot(pending_id)

        def done():
            self._record_pending_edit(before)
            self._preview_signature_185 = None
            self.refresh()

        def full():
            def open_full_editor():
                fresh = DB.get_pending_item(pending_id) or row
                fresh = dict(fresh)
                fresh['raw_text'] = v18._raw_text(pending_id, row)
                self.open_editor(fresh)
            self.after_idle(open_full_editor)

        TransactionWizard186(self, row, self.rich, done, full)


class SettingsTab186(v185.SettingsTab185):
    pass


class SystemTab186(v185.SystemTab185):
    def refresh(self):
        process = getattr(self.app, '_bot_process', None)
        bot = 'در حال اجرا' if process and process.poll() is None else 'متوقف/نامشخص'
        db_path = getattr(DB, 'db_path', getattr(DB, 'path', '-'))
        self.status.set(
            f'نسخه برنامه: {fa(VERSION)}\n'
            f'وضعیت دیتابیس: آماده\nTelegram Bot: {bot}\nمسیر دیتابیس: {fa(db_path)}\n'
            'AutoSave و رخدادهای مالی از مسیر دیتابیس همین پروژه مدیریت می‌شوند.'
        )


class ProjectSettingsDialog186(v185.ProjectSettingsDialog185):
    """Two-column floors plus four fixed-width project-team columns."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title('مشخصات پروژه — BARKAV 18.6')
        self.minsize(1180, 780)

    def _field_box(self, parent, row, column, key, label, value, *, kind='text'):
        p = palette_186(_is_light())
        box = tk.Frame(parent, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
        box.grid(row=row, column=column, sticky='ew', padx=4, pady=4)
        box.grid_columnconfigure(0, weight=1)
        tk.Label(box, text=label, bg=p['panel'], fg=p['text'],
                 font=('Segoe UI', max(9, self.font_size - 1), 'bold'), width=22,
                 anchor='e').grid(row=0, column=1, sticky='e', padx=(4, 7), pady=6)
        if kind == 'measure':
            shown = _display_measure(value)
        elif kind == 'number':
            shown = group_int_fa(value, blank_zero=True)
        elif kind == 'digits':
            shown = fa(value)
        else:
            shown = str(value or '')
        var = tk.StringVar(value=shown)
        self.vars[key] = var
        entry = ttk.Entry(box, textvariable=var, justify='right')
        entry.grid(row=0, column=0, sticky='ew', padx=(7, 4), pady=5)
        if kind == 'measure':
            bind_grouped_decimal_fa(entry, var)
        elif kind == 'number':
            bind_grouped_number_fa(entry, var)
        elif kind == 'digits':
            bind_persian_digits(entry, var)
        return entry

    def _ensure_roof_186(self):
        if any(row.get('is_roof') or str(row.get('floor') or '').strip() == 'بام' for row in self.floor_rows):
            return
        regular = list(self.floor_rows)
        self.floor_rows = normalize_floor_structure_186(
            len(regular),
            sum(1 for row in regular if row.get('is_parking')),
            sum(1 for row in regular if int(row.get('floor_level', 0)) < 0),
            regular,
        )

    def rebuild_floor_rows(self, preserve=True):
        self._floor_rebuild_after = None
        existing = self._capture_floor_cards() if preserve else list(self.profile.get('floors') or [])
        total = max(0, parse_int(self.vars['floor_count'].get()))
        parking = min(total, max(0, parse_int(self.vars['parking_floor_count'].get())))
        negative = min(total, max(0, parse_int(self.vars['negative_floor_count'].get())))
        self.floor_rows = normalize_floor_structure_186(total, parking, negative, existing)
        self._render_floor_cards()

    def add_floor_185(self):
        existing = self._capture_floor_cards()
        regular_count = sum(1 for row in existing if not row.get('is_roof')) + 1
        self.vars['floor_count'].set(group_int_fa(regular_count))
        self.floor_rows = normalize_floor_structure_186(
            regular_count,
            self.vars['parking_floor_count'].get(),
            self.vars['negative_floor_count'].get(),
            existing,
        )
        self._render_floor_cards()

    def remove_floor_185(self, index: int):
        rows = self._capture_floor_cards()
        if not (0 <= index < len(rows)) or rows[index].get('is_roof'):
            return
        removed = rows.pop(index)
        regular = [row for row in rows if not row.get('is_roof')]
        total = len(regular)
        negative = max(0, min(total, parse_int(self.vars['negative_floor_count'].get()) - (1 if int(removed.get('floor_level', 0)) < 0 else 0)))
        parking = max(0, min(total, parse_int(self.vars['parking_floor_count'].get()) - (1 if removed.get('is_parking') else 0)))
        self.vars['floor_count'].set(group_int_fa(total))
        self.vars['negative_floor_count'].set(group_int_fa(negative, blank_zero=True))
        self.vars['parking_floor_count'].set(group_int_fa(parking, blank_zero=True))
        self.floor_rows = normalize_floor_structure_186(total, parking, negative, rows)
        self._render_floor_cards()

    def _render_floor_cards(self):
        self._ensure_roof_186()
        p = palette_186(_is_light())
        for child in self.floor_body.winfo_children():
            child.destroy()
        self.floor_cards = []
        self.floor_body.grid_columnconfigure((0, 1), weight=1, uniform='floor_half')
        unit_sequence = 1
        for index, source0 in enumerate(self.floor_rows):
            source = deepcopy(source0)
            is_roof = bool(source.get('is_roof'))
            unit_count = 0 if is_roof else max(0, parse_int(source.get('unit_count')))
            storage_count = max(0, parse_int(source.get('storage_count')))
            source['units'] = self._resized(
                list(source.get('units') or []),
                unit_count,
                lambda _i: {'unit_number': '', 'usage': 'مسکونی', 'area': 0},
            )
            source['storage_areas'] = self._resized(
                list(source.get('storage_areas') or []), storage_count, lambda _i: 0
            )
            card = tk.Frame(self.floor_body, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
            card.grid(row=index // 2, column=1 - (index % 2), sticky='nsew', padx=4, pady=4)
            head = tk.Frame(card, bg=p['panel2'])
            head.pack(fill='x')
            head.grid_columnconfigure((0, 2), weight=1)
            tk.Label(head, text=f'ردیف {fa(index + 1)}', bg=p['panel2'], fg=p['muted'],
                     anchor='e').grid(row=0, column=5, sticky='e', padx=6, pady=5)
            name = tk.StringVar(value='بام' if is_roof else str(source.get('floor') or ''))
            tk.Label(head, text='نام طبقه', bg=p['panel2'], fg=p['text'], anchor='e').grid(row=0, column=3, sticky='e', padx=(3, 6))
            name_entry = ttk.Entry(head, textvariable=name, justify='right', width=16,
                                   state='disabled' if is_roof else 'normal')
            name_entry.grid(row=0, column=2, sticky='ew', padx=(3, 8), pady=4)

            unit_var = tk.StringVar(value=group_int_fa(unit_count))
            tk.Label(head, text='تعداد واحد', bg=p['panel2'], fg=p['muted' if is_roof else 'text'],
                     anchor='e').grid(row=1, column=5, sticky='e', padx=(3, 6), pady=4)
            unit_entry = ttk.Entry(head, textvariable=unit_var, justify='center', width=7,
                                   state='disabled' if is_roof else 'normal')
            unit_entry.grid(row=1, column=4, sticky='ew', padx=3, pady=4)
            bind_grouped_number_fa(unit_entry, unit_var)

            storage_var = tk.StringVar(value=group_int_fa(storage_count))
            tk.Label(head, text='تعداد انباری', bg=p['panel2'], fg=p['text'], anchor='e').grid(row=1, column=3, sticky='e', padx=(3, 6), pady=4)
            storage_entry = ttk.Entry(head, textvariable=storage_var, justify='center', width=7)
            storage_entry.grid(row=1, column=2, sticky='ew', padx=3, pady=4)
            bind_grouped_number_fa(storage_entry, storage_var)

            parking = tk.StringVar(value=group_int_fa(source.get('parking_supplied') or 0, blank_zero=True))
            parking_enabled = bool(source.get('is_parking')) and not is_roof
            tk.Label(head, text='پارکینگ تأمین‌شده', bg=p['panel2'],
                     fg=p['text'] if parking_enabled else p['muted'], anchor='e').grid(row=2, column=5, sticky='e', padx=(3, 6), pady=4)
            parking_entry = ttk.Entry(head, textvariable=parking, justify='center', width=7,
                                      state='normal' if parking_enabled else 'disabled')
            parking_entry.grid(row=2, column=4, sticky='ew', padx=3, pady=4)
            bind_grouped_number_fa(parking_entry, parking)
            tk.Button(head, text='اعمال تعداد', command=self._redraw_floor_details,
                      bg=p['blue'], fg='#FFFFFF', relief='flat', padx=8, pady=3).grid(row=2, column=2, sticky='e', padx=3, pady=4)
            if not is_roof:
                tk.Button(head, text='حذف سطر', command=lambda i=index: self.remove_floor_185(i),
                          bg=p['red'], fg='#FFFFFF', relief='flat', padx=8, pady=3).grid(row=2, column=0, sticky='w', padx=4, pady=4)
            for entry in (unit_entry, storage_entry):
                entry.bind('<FocusOut>', lambda _e: self._queue_floor_detail_redraw(), add='+')
                entry.bind('<Return>', lambda _e: self._redraw_floor_details(), add='+')

            details = tk.Frame(card, bg=p['surface'])
            details.pack(fill='x', padx=7, pady=7)
            details.grid_columnconfigure((0, 2, 4), weight=1)
            unit_vars = []
            for unit_index, unit in enumerate(source['units']):
                row_no = unit_index
                number_text = str(unit.get('unit_number') or unit_sequence)
                unit_sequence += 1
                number = tk.StringVar(value=fa(number_text))
                usage = tk.StringVar(value=str(unit.get('usage') or 'مسکونی'))
                area = tk.StringVar(value=_display_measure(unit.get('area') or 0))
                tk.Label(details, text=f'واحد {fa(unit_index + 1)}', bg=p['surface'], fg=p['blue'],
                         anchor='e').grid(row=row_no, column=6, sticky='e', padx=(2, 5), pady=3)
                tk.Label(details, text='شماره', bg=p['surface'], fg=p['muted']).grid(row=row_no, column=5, sticky='e')
                number_entry = ttk.Entry(details, textvariable=number, justify='center', width=7)
                number_entry.grid(row=row_no, column=4, sticky='ew', padx=2, pady=3)
                bind_persian_digits(number_entry, number)
                tk.Label(details, text='کاربری', bg=p['surface'], fg=p['muted']).grid(row=row_no, column=3, sticky='e')
                ttk.Combobox(details, textvariable=usage, values=UNIT_USES, state='readonly',
                             justify='right', width=9).grid(row=row_no, column=2, sticky='ew', padx=2, pady=3)
                tk.Label(details, text='متراژ', bg=p['surface'], fg=p['muted']).grid(row=row_no, column=1, sticky='e')
                area_entry = ttk.Entry(details, textvariable=area, justify='center', width=8)
                area_entry.grid(row=row_no, column=0, sticky='ew', padx=2, pady=3)
                bind_grouped_decimal_fa(area_entry, area)
                unit_vars.append((number, usage, area))

            storage_vars = []
            storage_start = max(1, unit_count + 1)
            if storage_count:
                tk.Label(details, text='انباری‌های بام' if is_roof else 'انباری‌ها', bg=p['surface'],
                         fg=p['blue'], font=('Segoe UI', max(9, self.font_size - 1), 'bold')).grid(
                             row=storage_start, column=0, columnspan=7, sticky='e', pady=(5, 3)
                         )
                for storage_index, stored in enumerate(source['storage_areas'], 1):
                    row_no = storage_start + storage_index
                    value = tk.StringVar(value=_display_measure(stored))
                    tk.Label(details, text=f'انباری {fa(storage_index)}', bg=p['surface'], fg=p['text'],
                             anchor='e').grid(row=row_no, column=6, sticky='e', padx=(2, 5), pady=3)
                    tk.Label(details, text='متراژ', bg=p['surface'], fg=p['muted']).grid(row=row_no, column=5, sticky='e')
                    entry = ttk.Entry(details, textvariable=value, justify='center', width=10)
                    entry.grid(row=row_no, column=4, sticky='ew', padx=2, pady=3)
                    bind_grouped_decimal_fa(entry, value)
                    storage_vars.append(value)
            elif is_roof:
                tk.Label(details, text='تعداد انباری بام را وارد و «اعمال تعداد» را بزنید.',
                         bg=p['surface'], fg=p['muted'], anchor='e').grid(
                             row=0, column=0, columnspan=7, sticky='e', pady=5
                         )
            self.floor_cards.append({
                'source': source,
                'name': name,
                'unit_count': unit_var,
                'storage_count': storage_var,
                'parking': parking,
                'unit_vars': unit_vars,
                'storage_vars': storage_vars,
            })
        regular_count = sum(1 for row in self.floor_rows if not row.get('is_roof'))
        parking_count = sum(1 for row in self.floor_rows if row.get('is_parking'))
        self.floor_summary.set(
            f'دو ستون از پایین به بالا — {fa(regular_count)} طبقه + بام، '
            f'{fa(parking_count)} طبقه پارکینگ.'
        )

    def save_basic_185(self):
        try:
            total = max(0, parse_int(self.vars['floor_count'].get()))
            parking = max(0, parse_int(self.vars['parking_floor_count'].get()))
            negative = max(0, parse_int(self.vars['negative_floor_count'].get()))
            if parking > total or negative > total:
                raise ValueError('تعداد طبقات پارکینگ و منفی نمی‌تواند از تعداد کل طبقات بیشتر باشد.')
            SERVICE.project.save_project(
                name=self.vars['name'].get(),
                address=self.vars['address'].get(),
                postal_code=en(self.vars['postal_code'].get()),
                registration_plate=en(self.vars['registration_plate'].get()),
                municipal_file_no=en(self.vars['municipal_file_no'].get()),
            )
            SERVICE.budget.save_settings(
                gross_area=parse_decimal(self.vars['gross_area'].get()),
                saleable_area=parse_decimal(self.vars['saleable_area'].get()),
                unit_count=parse_int(self.vars['unit_count'].get()),
            )
            self.profile['floor_meta'] = {
                'total_floor_count': total,
                'parking_floor_count': parking,
                'negative_floor_count': negative,
                'roof_row': True,
            }
            self.floor_rows = normalize_floor_structure_186(
                total, parking, negative, self._capture_floor_cards()
            )
            self.profile['floors'] = self.floor_rows
            save_profile(self.profile)
            self._render_floor_cards()
            if self.on_refresh:
                self.on_refresh()
            messagebox.showinfo('مشخصات پروژه', 'مشخصات پایه و سطر مستقل بام ذخیره شد.', parent=self)
        except Exception as exc:
            messagebox.showerror('مشخصات پروژه', str(exc), parent=self)

    def save_floors_185(self):
        try:
            floors = self._validated_floor_rows()
            regular = [row for row in floors if not row.get('is_roof')]
            self.profile['floors'] = floors
            self.profile['floor_meta'] = {
                'total_floor_count': len(regular),
                'parking_floor_count': sum(1 for row in regular if row.get('is_parking')),
                'negative_floor_count': sum(1 for row in regular if int(row.get('floor_level', 0)) < 0),
                'roof_row': True,
            }
            save_profile(self.profile)
            units = UnitService(DB)
            existing = units.list_units(include_cancelled=False)
            by_number = {str(row.get('unit_number') or ''): row for row in existing}
            project_name = SERVICE.project.get_project().get('name') or ''
            sync_errors = []
            all_areas = []
            for floor in regular:
                for unit in floor.get('units') or []:
                    number = str(unit.get('unit_number') or '')
                    area = float(unit.get('area') or 0)
                    all_areas.append(area)
                    try:
                        if number in by_number:
                            units.update_unit(by_number[number]['unit_id'], floor=floor['floor'], area=area)
                        else:
                            units.add_unit(floor=floor['floor'], unit_number=number, area=area, project_name=project_name)
                    except Exception as exc:
                        sync_errors.append(f'{fa(number)}: {exc}')
            SERVICE.budget.save_settings(unit_count=len(all_areas), unit_areas=all_areas)
            self.vars['unit_count'].set(group_int_fa(len(all_areas), blank_zero=True))
            if sync_errors:
                messagebox.showwarning(
                    'همگام‌سازی واحدها',
                    'ساختار ذخیره شد، اما این واحدها همگام نشدند:\n' + '\n'.join(sync_errors[:8]),
                    parent=self,
                )
            else:
                messagebox.showinfo(
                    'طبقات و واحدها',
                    'طبقات، واحدها و انباری‌های بام ذخیره و همگام شدند.',
                    parent=self,
                )
            if self.on_refresh:
                self.on_refresh()
        except Exception as exc:
            messagebox.showerror('طبقات و واحدها', str(exc), parent=self)

    save_basic_183 = save_basic_185
    save_basic_181 = save_basic_185
    save_floors_181 = save_floors_185

    def _build_team_tab(self, team, p):
        actionbar = tk.Frame(team, bg=p['panel'])
        actionbar.pack(side='bottom', fill='x', padx=8, pady=(0, 8))
        tk.Button(actionbar, text='ذخیره عوامل پروژه', command=self.save_team_185,
                  bg=p['blue'], fg='#FFFFFF', relief='flat',
                  font=('Segoe UI', max(9, self.font_size - 1), 'bold'),
                  padx=18, pady=7).pack(side='right')
        shell = tk.Frame(team, bg=p['panel'])
        shell.pack(fill='both', expand=True, padx=8, pady=8)
        canvas = tk.Canvas(shell, bg=p['panel'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(shell, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        body = tk.Frame(canvas, bg=p['panel'])
        window = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')), add='+')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width), add='+')
        canvas.bind('<MouseWheel>', lambda e: (canvas.yview_scroll(int(-e.delta / 120), 'units'), 'break')[1], add='+')
        for column in range(4):
            body.grid_columnconfigure(column, weight=1, uniform='team_quarter')
        old = self.profile.get('team') or {}
        order = [('designer', 3), ('supervisor', 2), ('executor', 1), ('admin_followup', 0)]
        for role, column in order:
            disciplines = self.ROLE_SPECS[role]
            self.team_vars[role] = {}
            for discipline in disciplines:
                role_data = old.get(role) if isinstance(old.get(role), dict) else {}
                data = role_data.get(discipline, {}) if isinstance(role_data.get(discipline), dict) else role_data
                self.team_vars[role][discipline] = {
                    field: tk.StringVar(value=fa(str((data or {}).get(field, '') or '')))
                    for field, _label in self.TEAM_FIELDS[role]
                }
            section = tk.Frame(body, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
            section.grid(row=0, column=column, sticky='nsew', padx=3, pady=3)
            tk.Label(section, text=self.ROLE_TITLES[role], bg=p['panel2'], fg=p['text'],
                     font=('Segoe UI', max(9, self.font_size - 1), 'bold'),
                     anchor='center', pady=7).pack(fill='x')
            if len(disciplines) > 1:
                filter_var = tk.StringVar(value='همه')
                self._team_filters[role] = filter_var
                combo = ttk.Combobox(section, textvariable=filter_var, state='readonly',
                                     values=['همه'] + disciplines, justify='right', width=18)
                combo.pack(fill='x', padx=5, pady=5)
                combo.bind('<<ComboboxSelected>>', lambda _e, r=role: self._render_team_role_185(r), add='+')
            host = tk.Frame(section, bg=p['surface'])
            host.pack(fill='both', expand=True, padx=3, pady=3)
            self._team_hosts[role] = host
            self._render_team_role_185(role)

    def _render_team_role_185(self, role):
        p = palette_186(_is_light())
        host = self._team_hosts.get(role)
        if host is None:
            return
        for child in host.winfo_children():
            child.destroy()
        wanted = self._team_filters[role].get() if role in self._team_filters else self.ROLE_SPECS[role][0]
        disciplines = self.ROLE_SPECS[role] if wanted == 'همه' else [wanted]
        for discipline in disciplines:
            group = tk.Frame(host, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
            group.pack(fill='x', padx=2, pady=3)
            tk.Label(group, text=discipline, bg=p['panel2'], fg=p['blue'],
                     font=('Segoe UI', 8, 'bold'), anchor='e').pack(fill='x', padx=1, pady=1)
            for field, label in self.TEAM_FIELDS[role]:
                row = tk.Frame(group, bg=p['panel'])
                row.pack(fill='x', padx=4, pady=2)
                row.grid_columnconfigure(0, weight=1)
                tk.Label(row, text=label, bg=p['panel'], fg=p['muted'],
                         anchor='e', font=('Segoe UI', 8)).grid(row=0, column=1, sticky='e', padx=(3, 5))
                entry = ttk.Entry(row, textvariable=self.team_vars[role][discipline][field], justify='right')
                entry.grid(row=0, column=0, sticky='ew', pady=2)
                if field == 'phone':
                    bind_persian_digits(entry, self.team_vars[role][discipline][field])


class Stage186Dashboard(v185.Stage185Dashboard):
    _VISIBLE_NAV = v185.Stage185Dashboard._VISIBLE_NAV
    _MONEY_CARD_KEYS = {
        'total_in', 'cost', 'total_out', 'cash', 'free',
        'ch_all_total', 'ch_open_total', 'ch30_amount',
        'loan_principal', 'loan_paid', 'loan_remaining', 'loan_30',
        'sales_contract', 'sales_received', 'sales_receivable', 'sales_overdue', 'sales_30',
        'liq_obligation', 'liq_inflow', 'liq_projected',
    }

    def __init__(self):
        self._table_upgrade_pending_186 = set()
        super().__init__()
        self.title('BARKAV — Engineering & Construction — Version 18.6')
        self.after_idle(self._finalize_186)

    def _style(self):
        super()._style()
        v183._THEME_DARK_183.update(DARK_186)
        v183._THEME_LIGHT_183.update(LIGHT_186)
        p = palette_186(_is_light())
        DARK.update(p)
        ui = load_ui()
        style_ttk_186(
            self,
            light=_is_light(),
            font_size=int(ui.get('font_size') or 10),
            row_height=int(ui.get('row_height') or 31),
        )

    def _build(self):
        p = palette_186(_is_light())
        fs = max(9, min(12, int(load_ui().get('font_size') or 10)))
        self.configure(bg=p['bg'])
        top = tk.Frame(self, bg=p['surface'], height=62,
                       highlightbackground=p['line'], highlightthickness=1)
        top.pack(fill='x')
        top.pack_propagate(False)
        brand = build_brand_widget_186(
            top,
            BASE_DIR / 'assets' / 'barkav_brand_header.png',
            bg=p['surface'], fg=p['text'], muted=p['muted'], compact=True,
        )
        brand.pack(side='left', padx=(14, 8), pady=4)
        self._brand_host_184 = brand
        self._brand_host_185 = brand
        self._brand_host_186 = brand

        tools = tk.Frame(top, bg=p['surface'])
        tools.pack(side='right', padx=8, pady=8)
        commands = [
            ('ذخیره', self.manual_save, 'بکاپ دستی'),
            ('Undo', self.undo, 'بازگشت آخرین عملیات'),
            ('Redo', self.redo, 'اجرای دوباره'),
            ('بروزرسانی', self.refresh_all, 'بروزرسانی اطلاعات'),
            ('تنظیمات', lambda: self._select_tab_text('تنظیمات'), 'تنظیمات'),
            ('بسته توسعه', self.export_development_package, 'خروجی امن توسعه'),
            ('سیستم', lambda: self._select_tab_text('سیستم'), 'وضعیت سیستم'),
        ]
        self.command_buttons = []
        for text, command, tip in commands:
            button = tk.Button(
                tools, text=text, command=command,
                bg=p['glass'], fg=p['text'],
                activebackground=p['panel2'], activeforeground=p['text'],
                relief='flat', bd=0,
                highlightbackground=p['line'], highlightthickness=1,
                font=('Segoe UI', max(8, fs - 1), 'bold'),
                padx=9, pady=5, cursor='hand2',
            )
            button.pack(side='right', padx=2)
            v18.add_tooltip(button, tip)
            self.command_buttons.append(button)

        self.datetime_top = tk.StringVar(value='')
        self.datetime_label_186 = tk.Label(
            tools, textvariable=self.datetime_top, width=24,
            bg=p['glass'], fg=p['text'],
            highlightbackground=p['line'], highlightthickness=1,
            font=('Segoe UI', max(8, fs - 1), 'bold'),
            anchor='center', justify='center', padx=6, pady=5,
        )
        self.datetime_label_186.pack(side='right', padx=(8, 3))
        self.quick_theme_button = tk.Button(
            tools,
            text='☀' if _is_light() else '☾',
            command=self.toggle_theme_184,
            bg=p['glass'], fg=p['text'],
            activebackground=p['panel2'], relief='flat',
            highlightbackground=p['line'], highlightthickness=1,
            font=('Segoe UI Symbol', 12), padx=8, pady=3,
        )
        self.quick_theme_button.pack(side='right', padx=3)
        self.project_name_top = tk.StringVar(value='پروژه')

        self.navbar = tk.Frame(self, bg=p['surface'], height=46,
                               highlightbackground=p['line'], highlightthickness=1)
        self.navbar.pack(fill='x', padx=8, pady=(6, 0))
        self.navbar.pack_propagate(False)
        self.notebook = ttk.Notebook(self, style='Hidden.TNotebook')
        self.notebook.pack(fill='both', expand=True, padx=8, pady=(5, 7))

        self._build_overview()
        self._build_manager()
        self._build_financial()
        self._build_cheques()
        self._build_sales()
        self._build_reconciliation()
        self._build_reports()
        self._build_market()
        self._build_system()
        self._build_settings()
        self._rebuild_navbar()
        self.notebook.bind('<<NotebookTabChanged>>', lambda _e: (self._sync_nav(), v18._maximize(self)), add='+')
        self._attach_common_tooltips(self)
        self._tick_clock()

    def _build_overview(self):
        p = palette_186(_is_light())
        tab = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.notebook.add(tab, text='داشبورد')
        wrap = tk.Frame(tab, bg=p['bg'])
        wrap.pack(fill='both', expand=True)
        canvas = tk.Canvas(wrap, bg=p['bg'], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(wrap, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        inner = tk.Frame(canvas, bg=p['bg'])
        window = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')), add='+')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width), add='+')
        canvas.bind('<MouseWheel>', lambda e: (canvas.yview_scroll(int(-e.delta / 120), 'units'), 'break')[1], add='+')
        self.overview_canvas = canvas

        project = tk.Frame(inner, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
        project.pack(fill='x', padx=5, pady=(4, 6))
        self.project_info = tk.StringVar(value='مشخصات پروژه')
        self.project_meta_var = tk.StringVar(value='')
        tk.Label(project, text='نمای کلی پروژه', bg=p['panel'], fg=p['text'],
                 font=('Segoe UI', 9, 'bold'), anchor='e').pack(side='right', padx=10, pady=8)
        tk.Label(project, textvariable=self.project_info, bg=p['panel'], fg=p['muted'],
                 font=('Segoe UI', 8), justify='right', anchor='e').pack(side='right', fill='x', expand=True, padx=8)
        tk.Button(project, text='مشخصات پروژه', command=self.edit_project_settings,
                  bg=p['blue'], fg='#FFFFFF', activebackground=p['cyan'],
                  relief='flat', padx=12, pady=5).pack(side='left', padx=8, pady=6)

        self.cards = {}
        groups = tk.Frame(inner, bg=p['bg'])
        groups.pack(fill='x', padx=2, pady=2)
        for column in range(5):
            groups.grid_columnconfigure(column, weight=1, uniform='reference_five')
        definitions = [
            ('تراکنش‌ها', '⇄', [('total_in', 'کل ورودی', True), ('cost', 'هزینه کل ساخت', True), ('total_out', 'کل خروجی', True), ('cash', 'تنخواه فعلی', True), ('free', 'مانده آزاد', True)]),
            ('چک‌ها', '▱', [('ch_all_total', 'کل چک‌ها', True), ('ch_open_total', 'چک‌های پاس‌نشده', True), ('ch30_count', 'سررسید ۳۰ روز', False), ('ch30_amount', 'مبلغ سررسید ۳۰ روز', True)]),
            ('تسهیلات', '♜', [('loan_principal', 'اصل تسهیلات', True), ('loan_paid', 'اقساط پرداختی', True), ('loan_remaining', 'مانده تسهیلات', True)]),
            ('فروش و مطالبات', '◉', [('sales_contract', 'کل قرارداد فروش', True), ('sales_received', 'وصول خریداران', True), ('sales_receivable', 'مطالبات', True), ('sales_overdue', 'مطالبات معوق', True)]),
            ('۳۰ روز آینده', '▣', [('liq_obligation', 'تعهد ۳۰ روز', True), ('liq_inflow', 'وصول ۳۰ روز', True), ('liq_projected', 'تراز ۳۰ روز', True), ('sales_30', 'مطالبات ۳۰ روز', True), ('loan_30', 'اقساط ۳۰ روز', True)]),
        ]
        for order, (title, icon, items) in enumerate(definitions):
            section = DashboardCard186(groups, title, icon=icon, light=_is_light())
            section.grid(row=0, column=4 - order, sticky='nsew', padx=3, pady=2)
            for index, (key, label, monetary) in enumerate(items):
                metric = CompactMetric186(section.body, label, monetary=monetary, alternate=index % 2 == 0)
                metric.pack(fill='x', pady=1)
                metric.bind('<Double-1>', lambda _e, group=title: self._open_dashboard_summary(group), add='+')
                self.cards[key] = metric

        phase = DashboardCard186(inner, 'پیشرفت مراحل پروژه — ۳۲ فاز', icon='▥', light=_is_light())
        phase.pack(fill='x', padx=5, pady=6)
        self.phase_strip = tk.Frame(phase.body, bg=p['panel'])
        self.phase_strip.pack(fill='x')
        self.phase_buttons = {}
        for column in range(32):
            self.phase_strip.grid_columnconfigure(column, weight=1, uniform='phase32')
        for number in range(1, 33):
            button = tk.Button(
                self.phase_strip, text=fa(f'{number:02d}'),
                bg=p['panel2'], fg=p['muted'],
                activebackground=p['blue'], activeforeground='#FFFFFF',
                relief='flat', bd=0, font=('Segoe UI', 6, 'bold'),
                padx=0, pady=5, command=lambda n=number: self.open_phase_by_no(n),
            )
            button.grid(row=0, column=number - 1, sticky='nsew', padx=1)
            button.bind('<Double-1>', lambda _e, n=number: self.edit_phase_progress(n), add='+')
            self.phase_buttons[number] = button
        self.overall_progress = v18.v175.ProjectProgressBar(
            phase.body,
            on_open=lambda: v18.v175.v16.ProjectFinancialOverview(self, self.rich),
        )
        self.overall_progress.pack(fill='x', pady=(6, 0))

        charts = tk.Frame(inner, bg=p['bg'])
        charts.pack(fill='x', padx=2, pady=5)
        charts.grid_columnconfigure((0, 1, 2), weight=1, uniform='chart3')
        self.cost_donut = v18.v175.DonutChart175(charts, 'ترکیب برآورد فازها', 210)
        self.cost_donut.grid(row=0, column=0, sticky='nsew', padx=3)
        self.liquidity_chart = v18.v175.MiniLineChart(charts, 'روند تجمعی برآورد / واقعی / پیش‌بینی', 210)
        self.liquidity_chart.grid(row=0, column=1, sticky='nsew', padx=3)
        self.phase_chart = v18.v175.MiniBarChart(charts, 'مقایسه فازها', 210)
        self.phase_chart.grid(row=0, column=2, sticky='nsew', padx=3)

    def _build_approval_center(self):
        tab = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.approval_tab = tab
        self.notebook.insert(1, tab, text='ثبت دیتا')
        self.approval_center = DataEntryCenter186(tab, self.rich, on_posted=self.refresh_all)
        self.approval_center.pack(fill='both', expand=True)
        if self._bot_process:
            self.approval_center.set_bot_process(self._bot_process, self._bot_log)
        self.after_idle(self._rebuild_navbar)

    def _build_settings(self):
        tab = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.notebook.add(tab, text='تنظیمات')
        self.settings_tab186 = SettingsTab186(tab, self._settings_saved)
        self.settings_tab185 = self.settings_tab186
        self.settings_tab186.pack(fill='both', expand=True)

    def _build_system(self):
        tab = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.notebook.add(tab, text='سیستم')
        self.system_tab186 = SystemTab186(tab, self)
        self.system_tab185 = self.system_tab186
        self.system_tab186.pack(fill='both', expand=True)

    def _rebuild_navbar(self):
        if not getattr(self, 'navbar', None):
            return
        for child in self.navbar.winfo_children():
            child.destroy()
        self.nav_buttons = {}
        p = palette_186(_is_light())
        fs = max(8, min(11, int(load_ui().get('font_size') or 10) - 1))
        tabs = {self.notebook.tab(tab_id, 'text'): tab_id for tab_id in self.notebook.tabs()}
        if 'حساب مدیر' not in tabs and 'حساب مدیر پروژه' in tabs:
            self.notebook.tab(tabs['حساب مدیر پروژه'], text='حساب مدیر')
            tabs['حساب مدیر'] = tabs['حساب مدیر پروژه']
        icon_map = {
            'داشبورد': '▦', 'ثبت دیتا': '▤', 'تراکنش‌ها': '⇄',
            'فروش و مطالبات': '⌂', 'گزارش‌گیری': '▥', 'حساب مدیر': '♙',
        }
        for label in self._VISIBLE_NAV:
            tab_id = tabs.get(label)
            if not tab_id:
                continue
            button = tk.Button(
                self.navbar,
                text=f"{label}   {icon_map.get(label, '◈')}",
                command=lambda target=tab_id: self.notebook.select(target),
                bg=p['surface'], fg=p['muted'],
                activebackground=p['panel2'], activeforeground=p['blue'],
                relief='flat', bd=0,
                font=('Segoe UI', fs, 'bold'),
                padx=15, pady=5, cursor='hand2',
                highlightbackground=p['surface'], highlightthickness=1,
            )
            button.pack(side='right', fill='y', padx=1, pady=3)
            self.nav_buttons[tab_id] = button
        self._sync_nav()

    def _sync_nav(self):
        try:
            selected = str(self.notebook.select())
        except Exception:
            return
        p = palette_186(_is_light())
        for tab_id, button in self.nav_buttons.items():
            active = str(tab_id) == selected
            button.configure(
                bg=p['panel2'] if active else p['surface'],
                fg=p['blue'] if active else p['muted'],
                highlightbackground=p['blue'] if active else p['surface'],
                highlightthickness=1,
            )

    def _rebuild_financial_indices_185(self):
        p = palette_186(_is_light())
        target = None
        target_index = 1
        for index, tab_id in enumerate(self.report_main.tabs()):
            if self.report_main.tab(tab_id, 'text') == 'شاخص‌های مالی':
                target = self.nametowidget(tab_id)
                target_index = index
                break
        if target is not None:
            self.report_main.forget(target)
            target.destroy()
        root = ttk.Frame(self.report_main, style='Panel.TFrame')
        remaining = self.report_main.tabs()
        self.report_main.insert(target_index if target_index < len(remaining) else 'end', root, text='شاخص‌های مالی')
        self.report_indices_root = root
        pane = ttk.Panedwindow(root, orient='horizontal')
        pane.pack(fill='both', expand=True, padx=5, pady=5)
        results = ttk.Frame(pane, style='Panel.TFrame')
        params = ttk.Frame(pane, style='Panel.TFrame')
        pane.add(results, weight=3)
        pane.add(params, weight=2)
        self.report_indices_pane185 = pane
        self.report_indices_pane186 = pane
        self._report_split_initialized_186 = False

        def initialize_split(_event=None):
            if self._report_split_initialized_186:
                return
            width = pane.winfo_width()
            if width > 600:
                pane.sashpos(0, int(width * 0.60))
                self._report_split_initialized_186 = True

        pane.bind('<Configure>', initialize_split, add='+')
        self.after(220, initialize_split)

        result_card = DashboardCard186(results, 'شاخص‌ها و سه سناریوی برآورد', icon='▥', light=_is_light())
        result_card.pack(fill='both', expand=True, padx=(0, 3))
        self.index_table = ttk.Treeview(
            result_card.body,
            columns=('metric', 's1', 's2', 's3'),
            show='headings', height=15,
        )
        for column, title, width, anchor in [
            ('metric', 'شاخص', 250, 'e'),
            ('s1', 'برآورد اولیه', 170, 'center'),
            ('s2', 'انجام‌شده + بروز تا پایان', 190, 'center'),
            ('s3', 'بروز صفر تا ۱۰۰', 175, 'center'),
        ]:
            self.index_table.heading(column, text=title, anchor=anchor)
            self.index_table.column(column, width=width, anchor=anchor)
        self.index_table.configure(displaycolumns=('s3', 's2', 's1', 'metric'))
        self.index_table.pack(fill='both', expand=True)
        attach_tree_grid_186(self.index_table, light=_is_light())
        self.report_cards = {}

        param_card = DashboardCard186(params, 'پارامترهای برآورد', icon='⚙', light=_is_light())
        param_card.pack(fill='both', expand=True, padx=(3, 0))
        body = param_card.body
        body.grid_columnconfigure((0, 1), weight=1)
        self.report_vars = {key: tk.StringVar() for key in [
            'gross_area', 'saleable_area', 'unit_count', 'inflation', 'months',
            'presale', 'end_price', 'misc', 'target', 'external_injection',
        ]}
        fields = [
            ('gross_area', 'زیربنای غیرمفید (M2)', 'decimal'),
            ('saleable_area', 'زیربنای مفید (M2)', 'decimal'),
            ('unit_count', 'تعداد واحدها', 'int'),
            ('inflation', 'تورم ماهانه %', 'decimal'),
            ('months', 'ماه تا اتمام', 'int'),
            ('presale', 'قیمت پیش‌فروش / M2', 'int'),
            ('end_price', 'قیمت فروش پایان / M2', 'int'),
            ('misc', 'متفرقه خارج برآورد', 'int'),
            ('target', 'سود هدف %', 'decimal'),
            ('external_injection', 'تزریق پول خارج پروژه', 'int'),
        ]
        for index, (key, label, kind) in enumerate(fields):
            box = tk.Frame(body, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
            box.grid(row=index // 2, column=1 - (index % 2), sticky='ew', padx=3, pady=3)
            box.grid_columnconfigure(0, weight=1)
            tk.Label(box, text=label, bg=p['panel'], fg=p['text'], anchor='e').grid(
                row=0, column=1, sticky='e', padx=(3, 6), pady=5
            )
            entry = ttk.Entry(box, textvariable=self.report_vars[key], justify='right')
            entry.grid(row=0, column=0, sticky='ew', padx=(6, 3), pady=4)
            if kind == 'int':
                bind_grouped_number_fa(entry, self.report_vars[key])
            else:
                bind_grouped_decimal_fa(entry, self.report_vars[key])
        actions = tk.Frame(body, bg=p['panel'])
        actions.grid(row=5, column=0, columnspan=2, sticky='ew', padx=3, pady=(8, 3))
        self.calculate_indices_button186 = tk.Button(
            actions,
            text='محاسبه شاخص‌ها با پارامترهای بالا',
            command=self.calculate_financial_indices,
            bg=p['blue'], fg='#FFFFFF', activebackground=p['cyan'],
            relief='flat', padx=18, pady=8,
            font=('Segoe UI', 10, 'bold'),
        )
        self.calculate_indices_button186.pack(fill='x', pady=(0, 4))
        tk.Button(
            actions, text='ذخیره پارامترها', command=self.save_report_settings_181,
            bg=p['glass'], fg=p['text'], relief='flat', padx=12, pady=6,
        ).pack(fill='x')

    def edit_project_settings(self):
        ProjectSettingsDialog186(self, self.refresh_all)

    def refresh_overview(self):
        super().refresh_overview()
        unit = currency_unit_186(load_ui().get('currency_unit'))
        rate = parse_int(load_ui().get('usd_rate_current'))
        for key, card in self.cards.items():
            if hasattr(card, 'update_currency_title'):
                card.update_currency_title(unit)
            if key not in self._MONEY_CARD_KEYS:
                continue
            amount = parse_display_amount_186(card.var.get())
            if amount is not None:
                card.var.set(format_currency_186(amount, unit, rate))

    def refresh_manager(self):
        super().refresh_manager()
        unit = currency_unit_186(load_ui().get('currency_unit'))
        rate = parse_int(load_ui().get('usd_rate_current'))
        snapshot = DB.snapshot()
        values = {
            'fee': int(snapshot.manager_fee_accrued),
            'withdraw': -int(snapshot.manager_withdrawals),
            'balance': int(snapshot.manager_balance),
        }
        for key, value in values.items():
            metric = self.manager_metrics.get(key)
            if metric is not None:
                metric.set(value, lambda number, u=unit, r=rate: format_currency_186(number, u, r))
        try:
            bps = int(DB.get_setting('manager_fee_bps', '1000'))
            percent = bps / 100
            self.manager_basis_var.set(
                f'مبنای محاسبه: {fa(percent)}٪ هزینه‌های ساخت مشمول | '
                f'حقوق تحقق‌یافته ({unit}): {format_currency_186(snapshot.manager_fee_accrued, unit, rate)} | '
                f'مانده: {format_currency_186(snapshot.manager_balance, unit, rate)}'
            )
        except Exception:
            pass

    def _upgrade_tables_184(self, root=None):
        root = root or self
        super()._upgrade_tables_184(root)
        key = str(root)
        if key in self._table_upgrade_pending_186:
            return
        self._table_upgrade_pending_186.add(key)

        def apply():
            self._table_upgrade_pending_186.discard(key)
            light = _is_light()
            for widget in _walk(root):
                if hasattr(widget, 'tree') and hasattr(widget, 'set_rows'):
                    try:
                        retarget_smarttable_186(widget, light=light)
                    except Exception:
                        pass
                if isinstance(widget, ttk.Treeview):
                    try:
                        attach_tree_grid_186(widget, light=light)
                        convert_tree_currency_186(widget)
                    except Exception:
                        pass
        try:
            root.after_idle(apply)
        except Exception:
            apply()

    def _fix_clock_185(self):
        label = getattr(self, 'datetime_label_186', None) or self._find_datetime_label()
        if label is None:
            return
        p = palette_186(_is_light())
        label.configure(
            width=24, anchor='center', justify='center',
            bg=p['glass'], fg=p['text'],
            highlightbackground=p['line'], highlightthickness=1,
            padx=6, pady=5,
            font=('Segoe UI', max(8, int(load_ui().get('font_size') or 10) - 1), 'bold'),
        )

    def _finalize_186(self):
        p = palette_186(_is_light())
        self.configure(bg=p['bg'])
        self._fix_clock_185()
        self._sync_nav()
        self._upgrade_tables_184(self)
        try:
            self.approval_center._fix_service_badges()
            self.approval_center._row_colors_185()
        except Exception:
            pass
        try:
            self.iconbitmap(default=str(BASE_DIR / 'assets' / 'BARKAV_18_6.ico'))
        except Exception:
            pass

    def export_development_package(self):
        destination = filedialog.asksaveasfilename(
            parent=self,
            defaultextension='.zip',
            initialfile='BARKAV_Development_Package_18.6.zip',
            filetypes=[('ZIP', '*.zip')],
        )
        if not destination:
            return
        try:
            from development_package_v186 import build_development_package
            result = build_development_package(BASE_DIR, Path(destination), VERSION)
            messagebox.showinfo(
                'بسته توسعه',
                f"بسته توسعه {VERSION} ساخته شد:\n{result['path']}\n\nدیتابیس زنده و secrets وارد بسته نشده‌اند.",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror('بسته توسعه', str(exc), parent=self)


Stage186DashboardFinal = Stage186Dashboard
Stage185Dashboard = Stage186Dashboard


if __name__ == '__main__':
    Stage186Dashboard().mainloop()

v186 = _legacy_snapshot()

# ---- Extracted from dashboard_stage18_7.py ----

import json
import os
from pathlib import Path
import re
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

import ui as legacy_ui
from barkav_themes.engine import stripe_tree
from barkav_themes.tokens import get_theme
from ui import bind_grouped_number_fa, fa, group_int_fa, parse_int
from ui import (
    activate_theme_bridge_187,
    palette_187,
    BACKGROUND_COLORS_187,
    available_font_families_187,
    available_font_weights_187,
    font_catalog_families_187,
    font_display_name_187,
    font_status_label_187,
    resolve_font_family_187,
    resolve_font_weight_187,
    style_ttk_187,
    theme_id_187,
    theme_metrics_187,
    theme_selection_187,
)
from v18_store import load_ui, save_ui


VERSION = '18.7.1'
BASE_DIR = v186.BASE_DIR
DB = v186.DB
SERVICE = v186.SERVICE


activate_theme_bridge_187()
# Stage186 imported these callables by value. Redirect only inside this 18.7
# process so every inherited surface resolves the selected Theme 1/2 tokens.
v186.palette_186 = palette_187
v186.style_ttk_186 = style_ttk_187
v186.DARK_186.update(palette_187(False))
v186.LIGHT_186.update(palette_187(True))


def dashboard_font_187(widget, size: int, role: str = 'body') -> tuple[str, int, str]:
    """Use the single persisted font choice with Dashboard semantic weights."""
    ui = load_ui()
    family = resolve_font_family_187(widget, ui.get('font_family'))
    selected = resolve_font_weight_187(widget, family, ui.get('font_weight'))
    weight = 400 if role == 'body' else 700 if role in {'title', 'kpi'} else selected
    return family, max(7, int(size)), 'bold' if weight >= 700 else 'normal'


def safe_project_id_187(value: str | None = None) -> str:
    raw = value if value is not None else os.getenv('PEYMAAN_ACTIVE_PROJECT_ID', '')
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', str(raw or '').strip())[:80] or 'default'


def bot_runtime_paths_187(base_dir: str | Path, project_id: str | None = None) -> dict[str, Path]:
    runtime = Path(base_dir) / 'runtime'
    suffix = safe_project_id_187(project_id)
    return {
        'ready': runtime / f'telegram_bot_ready_{suffix}.flag',
        'inbound': runtime / f'telegram_inbound_last_{suffix}.json',
        'status': runtime / f'telegram_bot_status_{suffix}.json',
    }


def is_tab_close_hit_187(event_x: int, bbox: tuple[int, int, int, int] | list[int]) -> bool:
    """Only the explicit right-side × zone closes a project tab."""
    x, _y, width, _height = [int(value) for value in bbox]
    close_width = min(24, max(16, width // 7))
    return x + width - close_width <= int(event_x) <= x + width


def apply_tree_rtl_187(tree: ttk.Treeview) -> None:
    if getattr(tree, '_barkav_rtl_187', False):
        return
    columns = tuple(tree.cget('columns') or ())
    if not columns:
        return
    try:
        shown = tuple(tree.cget('displaycolumns') or ())
        if shown in (('#all',), columns):
            tree.configure(displaycolumns=tuple(reversed(columns)))
        elif shown != tuple(reversed(columns)):
            tree.configure(displaycolumns=tuple(reversed(shown)))
    except Exception:
        tree.configure(displaycolumns=tuple(reversed(columns)))
    for column in columns:
        try:
            tree.heading(column, anchor='e')
            tree.column(column, anchor='e')
        except Exception:
            pass
    tree._barkav_rtl_187 = True


def apply_donut_theme_187(canvas) -> None:
    def redraw(self):
        p = palette_187()
        self.configure(bg=p['panel'], highlightbackground=p['border_subtle'])
        self.delete('all')
        width = max(360, self.winfo_width())
        height = max(200, self.winfo_height())
        self.create_text(width - 12, 14, text=self.title, anchor='ne',
                         fill=p['text_primary'], font=dashboard_font_187(self, 9, 'title'))
        center_x, center_y = min(105, width * .25), height * .53
        radius = min(68, height * .32)
        inner = radius * .58
        colors = {
            'blue': p['blue'], 'green': p['green'], 'orange': p['orange'],
            'red': p['red'], 'cyan': p['cyan'], 'violet': p['violet'],
            'muted': p['muted'],
        }
        start = 90.0
        total = self.total or 1.0
        for label, value, color_name in self.items:
            extent = -360.0 * max(0, float(value)) / total
            self.create_arc(
                center_x - radius, center_y - radius, center_x + radius, center_y + radius,
                start=start, extent=extent, fill=colors.get(color_name, color_name),
                outline=p['surface_alt'],
            )
            start += extent
        self.create_oval(
            center_x - inner, center_y - inner, center_x + inner, center_y + inner,
            fill=p['panel'], outline=p['panel'],
        )
        number = self.total
        if abs(number) >= 1_000_000_000:
            short = fa(f'{number / 1_000_000_000:.1f}B')
        elif abs(number) >= 1_000_000:
            short = fa(f'{number / 1_000_000:.1f}M')
        else:
            short = fa(f'{number:,.0f}')
        self.create_text(center_x, center_y - 5, text=short, fill=p['text_primary'],
                         font=dashboard_font_187(self, 12, 'kpi'))
        self.create_text(center_x, center_y + 17, text='تومان', fill=p['text_secondary'],
                         font=dashboard_font_187(self, 7, 'body'))
        y = 45
        x = max(200, width * .52)
        for label, value, color_name in self.items[:6]:
            color = colors.get(color_name, color_name)
            self.create_rectangle(x, y - 5, x + 9, y + 4, fill=color, outline='')
            percent = float(value) / total * 100 if total else 0
            self.create_text(x + 15, y, text=f'{label}  {fa(f"{percent:.0f}")}٪',
                             anchor='w', fill=p['text_secondary'], font=dashboard_font_187(self, 7, 'body'))
            y += 25

    canvas.redraw = redraw.__get__(canvas, type(canvas))
    canvas.redraw()


def apply_progress_theme_187(canvas) -> None:
    def redraw(self):
        p = palette_187()
        self.configure(bg=p['surface'], highlightbackground=p['border_subtle'])
        self.delete('all')
        width = max(self.winfo_width(), 100)
        height = max(self.winfo_height(), 40)
        margin = 6
        self.create_rectangle(
            margin, margin, width - margin, height - margin,
            fill=p['surface_alt'], outline=p['border_subtle'], width=1,
        )
        filled = (width - 2 * margin) * self.percent / 100
        if filled > 0:
            self.create_rectangle(
                margin, margin, margin + filled, height - margin,
                fill=p['info'], outline='',
            )
        foreground = p['on_accent'] if self.percent >= 48 else p['text_primary']
        self.create_text(
            width / 2, height / 2,
            text=f"پیشرفت کلی پروژه  {fa(f'{self.percent:.1f}')}٪",
            fill=foreground, font=dashboard_font_187(self, 10, 'title'),
        )

    canvas.redraw = redraw.__get__(canvas, type(canvas))
    canvas.redraw()


def apply_line_theme_187(canvas) -> None:
    """Restyle the inherited chart without changing its series or calculations."""
    def redraw(self):
        p = palette_187()
        self.configure(bg=p['card'], highlightbackground=p['border_subtle'])
        self.delete('all')
        width, height = max(self.winfo_width(), 300), max(self.winfo_height(), 160)
        x0, y0, x1, y1 = 38, 42, width - 18, height - 28
        self.create_text(x1, 17, text=self.title, anchor='ne', fill=p['text_primary'],
                         font=dashboard_font_187(self, 10, 'title'))
        self.create_line(x0, y1, x1, y1, fill=p['border_subtle'], dash=(2, 4))
        self.create_line(x0, y0, x0, y1, fill=p['border_subtle'])
        values = [value for _label, series, _color in self.series for value in series]
        maximum = max(max(values, default=0), 1)
        colors = {name: p[name] for name in ('blue', 'green', 'orange', 'red', 'cyan')}
        for _label, series, color_name in self.series:
            if not series:
                continue
            points = []
            for index, value in enumerate(series):
                x = x0 + (x1 - x0) * (index / max(1, len(series) - 1))
                y = y1 - (y1 - y0) * (value / maximum)
                points.extend((x, y))
            if len(points) >= 4:
                self.create_line(*points, fill=colors.get(color_name, color_name), width=2, smooth=True)
        legend_x = x0 + 8
        for label, _series, color_name in self.series:
            color = colors.get(color_name, color_name)
            self.create_rectangle(legend_x, y0 - 20, legend_x + 9, y0 - 11, fill=color, outline='')
            self.create_text(legend_x + 14, y0 - 15, text=label, anchor='w',
                             fill=p['text_secondary'], font=dashboard_font_187(self, 7, 'body'))
            legend_x += 104

    canvas.redraw = redraw.__get__(canvas, type(canvas))
    canvas.redraw()


def apply_bar_theme_187(canvas) -> None:
    """Restyle the inherited phase chart while preserving every source row."""
    def redraw(self):
        p = palette_187()
        self.configure(bg=p['card'], highlightbackground=p['border_subtle'])
        self.delete('all')
        width, height = max(self.winfo_width(), 400), max(self.winfo_height(), 160)
        self.create_text(width - 12, 17, text=self.title, anchor='ne', fill=p['text_primary'],
                         font=dashboard_font_187(self, 10, 'title'))
        if not self.rows:
            return
        maximum = max([value for _label, estimate, actual, forecast in self.rows
                       for value in (estimate, actual, forecast)] + [1])
        x0, y0, x1, y1 = 34, 46, width - 14, height - 26
        self.create_line(x0, y1, x1, y1, fill=p['border_subtle'], dash=(2, 4))
        group_width = (x1 - x0) / max(1, len(self.rows))
        colors = (p['text_muted'], p['success'], p['info'])
        for index, (label, estimate, actual, forecast) in enumerate(self.rows):
            base = x0 + index * group_width
            bar_width = max(2, (group_width - 6) / 3)
            for offset, value in enumerate((estimate, actual, forecast)):
                bar_height = (y1 - y0) * (value / maximum)
                self.create_rectangle(base + 3 + offset * bar_width, y1 - bar_height,
                                      base + 2 + (offset + 1) * bar_width, y1,
                                      fill=colors[offset], outline='')
            if len(self.rows) <= 16 or index % 2 == 0:
                self.create_text(base + group_width / 2, y1 + 10, text=fa(label),
                                 fill=p['text_muted'], font=dashboard_font_187(self, 6, 'body'))
        legend_x = x0 + 8
        for label, color in zip(('برآورد', 'واقعی', 'پیش‌بینی'), colors):
            self.create_rectangle(legend_x, y0 - 20, legend_x + 9, y0 - 11, fill=color, outline='')
            self.create_text(legend_x + 14, y0 - 15, text=label, anchor='w',
                             fill=p['text_secondary'], font=dashboard_font_187(self, 7, 'body'))
            legend_x += 88

    canvas.redraw = redraw.__get__(canvas, type(canvas))
    canvas.redraw()


class SettingsTab187(v186.SettingsTab186):
    def _build(self):
        p = palette_187()
        self.configure(bg=p['bg'])
        self.data = load_ui()
        self.vars = {}
        self.controls187 = {}
        self._font_families = self._installed_fonts()
        self._font_values = tuple(font_status_label_187(self, name) for name in self._font_families)
        card = tk.Frame(self, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
        card.pack(fill='x', padx=12, pady=12)
        tk.Label(card, text='تنظیمات ظاهر و کاربری ۱۸.۷', bg=p['panel2'], fg=p['text'],
                 anchor='e', font=dashboard_font_187(self, 11, 'title'), padx=12, pady=9).pack(fill='x')
        body = tk.Frame(card, bg=p['panel'])
        body.pack(fill='x', padx=10, pady=10)
        body.grid_columnconfigure((0, 1), weight=1, uniform='settings')

        language = {'fa': 'فارسی (RTL)', 'en': 'English'}
        fields = (
            ('language', 'زبان رابط', tuple(language.values()), language.get(str(self.data.get('language') or 'fa'), 'فارسی (RTL)')),
            ('appearance', 'حالت نمایش', ('تیره', 'روشن'), 'روشن' if str(self.data.get('appearance') or 'dark').lower() == 'light' else 'تیره'),
            ('theme_id', 'تم رابط', ('۱', '۲'), '۲' if str(theme_id_187()) == '2' else '۱'),
            ('font_family', 'نوع فونت', tuple(self._font_values), self._safe_font_value()),
            ('font_weight', 'وزن فونت', tuple(str(x) for x in self._font_weights()), str(self.data.get('font_weight') or 400)),
            ('font_size', 'اندازه فونت', tuple(str(x) for x in range(9, 19)), str(self.data.get('font_size') or 11)),
            ('background_color', 'رنگ پس‌زمینه', ('پیش‌فرض',) + tuple(BACKGROUND_COLORS_187), str(self.data.get('background_color') or 'پیش‌فرض')),
            ('currency_unit', 'واحد پول', ('تومان', 'ریال', 'دلار'), str(self.data.get('currency_unit') or 'تومان')),
            ('row_height', 'ارتفاع ردیف', tuple(str(x) for x in range(28, 47, 2)), str(self.data.get('row_height') or 40)),
        )
        for index, (key, label, values, current) in enumerate(fields):
            box = tk.Frame(body, bg=p['panel'])
            box.grid(row=index // 2, column=index % 2, sticky='ew', padx=7, pady=7)
            tk.Label(box, text=label, bg=p['panel'], fg=p['text'], anchor='e',
                     font=dashboard_font_187(self, 10, 'control')).pack(fill='x')
            value = tk.StringVar(value=current if current in values else values[0])
            self.vars[key] = value
            control = ttk.Combobox(box, textvariable=value, values=values, state='readonly',
                                   justify='right')
            control.pack(fill='x', pady=(4, 0))
            self.controls187[key] = control

        rate = tk.Frame(body, bg=p['panel'])
        rate_row = (len(fields) + 1) // 2
        rate.grid(row=rate_row, column=0, columnspan=2, sticky='ew', padx=7, pady=7)
        rate.grid_columnconfigure((0, 1), weight=1, uniform='rates')
        for column, (key, label) in enumerate((
            ('usd_rate_current', 'قیمت روز دلار آمریکا (تومان)'),
            ('usd_rate_baseline', 'قیمت دلار زمان برآورد اولیه (تومان)'),
        )):
            box = tk.Frame(rate, bg=p['panel'])
            box.grid(row=0, column=1 - column, sticky='ew', padx=4)
            tk.Label(box, text=label, bg=p['panel'], fg=p['text'], anchor='e').pack(fill='x')
            value = tk.StringVar(value=group_int_fa(self.data.get(key, 0), blank_zero=True))
            self.vars[key] = value
            entry = ttk.Entry(box, textvariable=value, justify='right')
            entry.pack(fill='x', pady=4)
            bind_grouped_number_fa(entry, value)

        tk.Button(
            body, text='ذخیره تنظیمات', command=self.save,
            bg=p['green'], fg='#102018', relief='flat', padx=18, pady=8,
            font=dashboard_font_187(self, 10, 'control'), cursor='hand2',
        ).grid(row=rate_row + 1, column=0, columnspan=2, sticky='e', padx=7, pady=(10, 6))
        tk.Label(
            body,
            text='فارسی به‌صورت پیش‌فرض RTL است؛ تغییرات ظاهری پس از بازآفرینی برنامه اعمال می‌شوند.',
            bg=p['panel'], fg=p['muted'], anchor='e', justify='right',
        ).grid(row=rate_row + 2, column=0, columnspan=2, sticky='ew', padx=7, pady=(0, 5))

    def _installed_fonts(self):
        return font_catalog_families_187(self)

    def _font_weights(self):
        return available_font_weights_187(self, resolve_font_family_187(self, self.data.get('font_family')))

    def _safe_font_value(self):
        current = str(self.data.get('font_family') or '').strip()
        if current in self._font_families:
            return font_status_label_187(self, current)
        return font_status_label_187(self, resolve_font_family_187(self, current))

    def save(self):
        old = load_ui()
        data = dict(old)
        language = {'فارسی (RTL)': 'fa', 'English': 'en'}
        data.update({key: value.get() for key, value in self.vars.items()})
        selected_display = self.vars['font_family'].get()
        data['font_family'] = next(
            (name for name in self._font_families if font_status_label_187(self, name) == selected_display),
            self._font_families[0],
        )
        data['font_weight'] = resolve_font_weight_187(self, data['font_family'], data.get('font_weight'))
        data['language'] = language.get(self.vars['language'].get(), 'fa')
        data['appearance'] = 'light' if self.vars['appearance'].get() == 'روشن' else 'dark'
        data['theme_id'] = 2 if self.vars['theme_id'].get() == '۲' else 1
        data['font_size'] = max(9, min(18, int(data.get('font_size') or 11)))
        data['row_height'] = max(28, min(46, int(data.get('row_height') or 40)))
        data['usd_rate_current'] = parse_int(data.get('usd_rate_current'))
        data['usd_rate_baseline'] = parse_int(data.get('usd_rate_baseline'))
        if data.get('currency_unit') == 'دلار' and data['usd_rate_current'] <= 0:
            return messagebox.showwarning('واحد دلار', 'قیمت روز دلار آمریکا را وارد کن.', parent=self)
        save_ui(data)
        self.on_apply and self.on_apply(old, data)


class DataEntryCenter187(v186.DataEntryCenter186):
    """Keep earlier receipts visible and isolate Telegram status per project."""

    def _build(self):
        super()._build()
        record_bar = ttk.Frame(self)
        children = self.winfo_children()
        try:
            record_bar.pack(fill='x', padx=8, pady=(6, 0), before=children[0])
        except (IndexError, tk.TclError):
            record_bar.pack(fill='x', padx=8, pady=(6, 0))
        ttk.Button(record_bar, text='ثبت رکورد فروش', command=self._open_sales_wizard_187).pack(side='right')
        # The Word correction asks for previous receipts to be present in the
        # current view. All statuses already exist; 18.7 opens on that full list.
        self.filter.set('همه')
        self.after_idle(self.refresh)

    def _open_sales_wizard_187(self):
        opener = getattr(self.winfo_toplevel(), 'open_sales_wizard_187', None)
        if opener:
            opener()

    def open_wizard(self, row=None):
        """Keep sales receipt Add/Edit drafts reversible until their final approval."""
        row = row or getattr(self, 'current', None)
        if not row or not is_temporary_sales_finance_pending_187(dict(row.get('payload') or {})):
            return super().open_wizard(row)
        pending_id = str(row.get('pending_id') or '')
        before = self._pending_snapshot(pending_id)

        def done():
            self._record_pending_edit(before)
            self._preview_signature_185 = None
            self.refresh()

        def abandon():
            item = DB.get_pending_item(pending_id) or {}
            if is_temporary_sales_finance_pending_187(dict(item.get('payload') or {})) and item.get('status') in {
                'PENDING_REVIEW', 'NEEDS_REVIEW', 'EDIT_PENDING',
            }:
                v186.APPROVAL.reject(pending_id, actor_id='GUI_187_SALES_FINANCE_CANCEL')
            self._preview_signature_185 = None
            self.refresh()

        def full():
            fresh = dict(DB.get_pending_item(pending_id) or row)
            SalesFinancePendingEditor187(self, fresh, self.rich, done, on_abandon=abandon)

        SalesFinancePendingWizard187(self, row, self.rich, done, full)

    def _service_status_181(self):
        # Reuse the inherited Gemini diagnostics and scheduling, then replace the
        # legacy global Telegram flag with this project's isolated runtime files.
        super()._service_status_181()
        try:
            paths = bot_runtime_paths_187(BASE_DIR)
            process = getattr(self, '_bot_process', None)
            alive = bool(process and process.poll() is None)
            inbound = None
            status = None
            try:
                if paths['inbound'].exists():
                    inbound = json.loads(paths['inbound'].read_text(encoding='utf-8'))
            except Exception:
                inbound = None
            try:
                if paths['status'].exists():
                    status = json.loads(paths['status'].read_text(encoding='utf-8'))
            except Exception:
                status = None
            p = palette_187()
            if alive and paths['ready'].exists():
                suffix = f" | آخرین پیام #{fa(inbound.get('message_id'))}" if inbound and inbound.get('message_id') else ''
                self.bot.set('تلگرام: آنلاین و آماده' + suffix)
                self.bot_label.configure(fg=p['green'])
            elif alive:
                state = str((status or {}).get('state') or 'STARTING').upper()
                self.bot.set(
                    'تلگرام: در تلاش برای اتصال — شبکه و تنظیمات را بررسی کنید'
                    if state in {'STARTING', 'RETRYING'} else
                    'تلگرام: اتصال برقرار نشد؛ جزئیات در وضعیت سیستم'
                )
                self.bot_label.configure(fg=p['yellow'])
            else:
                self.bot.set('تلگرام: قطع')
                self.bot_label.configure(fg=p['red'])
        except Exception:
            pass


class SalesFinancePendingWizard187(v186.TransactionWizard186):
    """Never turn an edit preview into a duplicate buyer receipt."""
    def next(self):
        action = str((self.payload or {}).get('sales_pending_action') or '').upper()
        if action == 'EDIT' and self.page_index >= len(self.pages) - 1:
            return messagebox.showwarning(
                'ویرایش مالی',
                'ویرایش وصول تأییدشده باید از مسیر اصلاح حسابرسی انجام شود؛ ثبت جدید برای جلوگیری از واریزی تکراری متوقف شد.',
                parent=self,
            )
        return super().next()


class SalesFinancePendingEditor187(v186.UnifiedPendingEditor186):
    """Closing a temporary sales receipt draft is the same as rejecting it."""
    def __init__(self, parent, row, rich, on_done, *, on_abandon):
        self._on_abandon = on_abandon
        super().__init__(parent, row, rich, on_done)
        self.protocol('WM_DELETE_WINDOW', self._abandon)

    def _abandon(self):
        self.destroy()
        self._on_abandon()

    def approve(self):
        action = str((self.payload or {}).get('sales_pending_action') or '').upper()
        if action == 'EDIT':
            return messagebox.showwarning(
                'ویرایش مالی',
                'ویرایش وصول تأییدشده باید از مسیر اصلاح حسابرسی انجام شود؛ ثبت جدید برای جلوگیری از واریزی تکراری متوقف شد.',
                parent=self,
            )
        return super().approve()


class ChartDetailDialog187(tk.Toplevel):
    def __init__(self, parent: 'Stage187Dashboard', kind: str):
        super().__init__(parent)
        self.parent_app = parent
        self.kind = kind
        titles = {
            'donut': 'جزئیات ترکیب فازها',
            'line': 'جزئیات روند تجمعی',
            'bar': 'جزئیات مقایسه فازها',
        }
        self.title(titles[kind])
        self.geometry('1180x740')
        self.minsize(900, 600)
        self.transient(parent)
        p = palette_187()
        self.configure(bg=p['bg'])
        tk.Label(self, text=titles[kind], bg=p['surface'], fg=p['text'],
                 anchor='e', font=dashboard_font_187(self, 14, 'title'), padx=14, pady=10).pack(fill='x')
        if kind == 'donut':
            self._build_donut()
        elif kind == 'line':
            self._build_line()
        else:
            self._build_bar()

    def _table(self, columns):
        tree = ttk.Treeview(self, columns=tuple(key for key, _label, _width in columns), show='headings')
        for key, label, width in columns:
            tree.heading(key, text=label, anchor='e')
            tree.column(key, width=width, anchor='e')
        tree.configure(displaycolumns=tuple(reversed([item[0] for item in columns])))
        tree.pack(fill='both', expand=True, padx=10, pady=(4, 10))
        return tree

    def _build_donut(self):
        phases = list(self.parent_app._phase_summary_live())
        values = [
            (row, float(row.get('actual') or row.get('estimate') or 0))
            for row in phases
        ]
        total = sum(value for _row, value in values) or 1.0
        rows = [(row, value, value / total * 100) for row, value in values if value / total * 100 > 1.0]
        colors = ['blue', 'green', 'orange', 'violet', 'cyan', 'red']
        chart = v186.v18.v175.DonutChart175(self, 'همه فازهای دارای سهم بیشتر از ۱٪', 360)
        chart.pack(fill='x', padx=10, pady=10)
        apply_donut_theme_187(chart)
        chart.set_items([
            (str(row.get('phase') or ''), value, colors[index % len(colors)])
            for index, (row, value, _percent) in enumerate(rows)
        ])
        tree = self._table([
            ('no', 'شماره فاز', 90), ('phase', 'نام فاز', 350),
            ('amount', 'مبلغ مبنا (تومان)', 190), ('percent', 'سهم', 100),
        ])
        for index, (row, value, percent) in enumerate(rows):
            tree.insert('', 'end', iid=str(index), values=(
                fa(f"{int(row.get('phase_no') or 0):02d}"), row.get('phase') or '-',
                fa(f'{int(value):,}'), fa(f'{percent:.1f}') + '٪',
            ))

    def _build_line(self):
        series = list(getattr(self.parent_app.liquidity_chart, 'series', []) or [])
        chart = v186.v18.v175.MiniLineChart(self, 'روند تجمعی برآورد / واقعی / پیش‌بینی', 390)
        chart.pack(fill='x', padx=10, pady=10)
        chart.set_series(series)
        tree = self._table([
            ('point', 'نقطه/فاز', 100), ('estimate', 'برآورد', 190),
            ('actual', 'واقعی', 190), ('forecast', 'پیش‌بینی', 190),
        ])
        by_label = {label: list(values) for label, values, _color in series}
        count = max((len(values) for values in by_label.values()), default=0)
        for index in range(count):
            def value(label):
                items = by_label.get(label, [])
                return items[index] if index < len(items) else 0
            tree.insert('', 'end', values=(
                fa(index + 1), fa(f"{int(value('برآورد')):,}"),
                fa(f"{int(value('واقعی')):,}"), fa(f"{int(value('پیش‌بینی')):,}"),
            ))

    def _build_bar(self):
        rows = list(getattr(self.parent_app.phase_chart, 'rows', []) or [])
        chart = v186.v18.v175.MiniBarChart(self, 'مقایسه کامل فازها', 390)
        chart.pack(fill='x', padx=10, pady=10)
        chart.set_rows(rows)
        tree = self._table([
            ('phase', 'فاز', 100), ('estimate', 'برآورد', 190),
            ('actual', 'واقعی', 190), ('forecast', 'پیش‌بینی', 190),
        ])
        for label, estimate, actual, forecast in rows:
            tree.insert('', 'end', values=(
                fa(label), fa(f'{int(estimate):,}'), fa(f'{int(actual):,}'),
                fa(f'{int(forecast):,}'),
            ))


class Stage187Dashboard(v186.Stage186Dashboard):
    def __init__(self):
        activate_theme_bridge_187()
        v186.DARK_186.update(palette_187(False))
        v186.LIGHT_186.update(palette_187(True))
        self._startup_reminder_shown_187 = False
        super().__init__()
        self.title('BARKAV — Engineering & Construction — Version 18.7.1')
        self.after_idle(self._finalize_187)
        self.after(1300, self._show_startup_reminders_187)

    def _style(self):
        super()._style()
        ui = load_ui()
        style_ttk_187(
            self,
            light=str(ui.get('appearance') or 'dark').lower() == 'light',
            font_size=int(ui.get('font_size') or 10),
            row_height=int(ui.get('row_height') or theme_metrics_187()['row_height']),
        )

    def _build(self):
        """Rearrange the inherited widgets into the 18.7 shell without duplicating them."""
        super()._build()
        self._install_shell_187()

    def _shell_button_187(self, parent, text, command, fs, side='right'):
        p = palette_187()
        button = tk.Button(
            parent, text=text, command=command,
            bg=p['glass'], fg=p['text'],
            activebackground=p['panel2'], activeforeground=p['text'],
            relief='flat', bd=0,
            highlightbackground=p['line'], highlightthickness=1,
            font=dashboard_font_187(self, max(8, fs - 1), 'control'),
            padx=9, pady=5, cursor='hand2',
        )
        button.pack(side=side, padx=2)
        return button

    def _file_menu_icons_187(self, color: str):
        """Build menu images from the native Windows Fluent icon font."""
        glyphs = ('\ue74e', '\ue792', '\ue72c', '\ue713', '\ue7b8', '\ue770')
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageTk
            font_path = Path(os.environ.get('WINDIR', 'C:\\Windows')) / 'Fonts' / 'segmdl2.ttf'
            font = ImageFont.truetype(str(font_path), 22)
            icons = []
            for glyph in glyphs:
                canvas = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
                draw = ImageDraw.Draw(canvas)
                draw.text((16, 16), glyph, font=font, fill=color, anchor='mm')
                icons.append(ImageTk.PhotoImage(canvas, master=self))
            return icons
        except Exception:
            return [None] * len(glyphs)

    def _set_theme_mode_187(self, mode: str):
        ui = load_ui()
        mode = 'light' if str(mode).lower() == 'light' else 'dark'
        if str(ui.get('appearance') or 'dark').lower() == mode:
            return
        ui['appearance'] = mode
        save_ui(ui)
        self._restart_requested = True
        self.after(80, self.destroy)

    def _tick_clock(self):
        try:
            now = datetime.now()
            self.datetime_top.set(
                f"{fa(v186.v18.gregorian_to_shamsi(now.date()))}\n{fa(now.strftime('%H:%M:%S'))}"
            )
        finally:
            self.after(1000, self._tick_clock)

    def _show_footer_mode_menu_187(self, _event=None):
        menu = getattr(self, 'footer_theme_menu187', None)
        button = getattr(self, 'footer_mode_button187', None)
        if menu is None or button is None:
            return 'break'
        button.update_idletasks()
        x = button.winfo_rootx() + button.winfo_width() - menu.winfo_reqwidth()
        y = max(0, button.winfo_rooty() - menu.winfo_reqheight() - 4)
        menu.post(x, y)
        return 'break'

    def _show_footer_theme_menu_187(self, _event=None):
        menu = getattr(self, 'footer_themes_menu187', None)
        button = getattr(self, 'footer_theme_button187', None)
        if menu is None or button is None:
            return 'break'
        button.update_idletasks()
        x = button.winfo_rootx() + button.winfo_width() - menu.winfo_reqwidth()
        y = max(0, button.winfo_rooty() - menu.winfo_reqheight() - 4)
        menu.post(x, y)
        return 'break'

    def _set_theme_id_187(self, theme_id: int):
        ui = load_ui()
        try:
            selected = get_theme(theme_id).theme_id
        except (TypeError, ValueError):
            selected = 1
        if int(ui.get('theme_id') or 1) == selected:
            return
        ui['theme_id'] = selected
        save_ui(ui)
        self._restart_requested = True
        self.after(80, self.destroy)

    def _toggle_language_187(self):
        """Toggle the compact footer language control without opening Settings."""
        old = load_ui()
        current = str(old.get('language') or 'fa').lower()
        new = dict(old)
        new['language'] = 'fa' if current == 'en' else 'en'
        save_ui(new)
        self._settings_saved(old, new)

    def _apply_widget_font_187(self, widget, family: str, weight: int = 400, size: int | None = None):
        try:
            current = str(widget.cget('font') or '')
            if 'MDL2' in current or 'Symbol' in current:
                return
            actual = tkfont.Font(root=widget, font=current).actual() if current else {}
            actual_size = int(actual.get('size') or 10)
            target_size = int(size or actual_size)
            if target_size == 0:
                return
            widget.configure(font=(family, target_size, 'bold' if int(weight) >= 700 else 'normal', actual.get('slant', 'roman')))
        except (tk.TclError, ValueError, TypeError):
            return

    def _apply_settings_live_187(self, old, new):
        family = resolve_font_family_187(self, new.get('font_family'))
        weight = resolve_font_weight_187(self, family, new.get('font_weight'))
        size = max(9, min(18, int(new.get('font_size') or 11)))
        row_height = max(28, min(46, int(new.get('row_height') or 40)))
        style_ttk_187(
            self,
            light=str(new.get('appearance') or 'dark').lower() == 'light',
            font_size=size,
            row_height=row_height,
        )
        for root in (self, getattr(self, 'settings_window187', None)):
            if root is None or not root.winfo_exists():
                continue
            for widget in v186._walk(root):
                self._apply_widget_font_187(widget, family, weight, size)
        self._apply_financial_report_theme_187()
        if getattr(self, 'footer_language_button187', None):
            self.footer_language_button187.configure(
                text='ENG' if str(new.get('language') or 'fa').lower() == 'en' else 'فا'
            )
        self._refresh_footer_theme_button_187()

    def _refresh_footer_theme_button_187(self):
        mode_button = getattr(self, 'footer_mode_button187', None)
        theme_button = getattr(self, 'footer_theme_button187', None)
        if mode_button is None and theme_button is None:
            return
        p = palette_187()
        mode = str(load_ui().get('appearance') or 'dark').lower()
        if mode_button is not None:
            mode_button.configure(text='روشن' if mode == 'light' else 'تیره', bg=p['glass'], fg=p['text'])
        if theme_button is not None:
            theme_button.configure(bg=p['glass'], fg=p['text'])

    def _close_file_menu_187(self, _event=None):
        popup = getattr(self, 'file_menu187', None)
        if popup is not None and popup.winfo_exists():
            popup.destroy()
        self.file_menu187 = None

    def _run_file_menu_command_187(self, command):
        self._close_file_menu_187()
        command()

    def _file_menu_focus_out_187(self, _event=None):
        popup = getattr(self, 'file_menu187', None)
        if popup is None or not popup.winfo_exists():
            return

        def close_if_focus_left():
            current = popup.focus_get() if popup.winfo_exists() else None
            while current is not None:
                if current is popup:
                    return
                current = getattr(current, 'master', None)
            self._close_file_menu_187()

        popup.after(80, close_if_focus_left)

    def _show_file_menu_187(self, _event=None):
        current = getattr(self, 'file_menu187', None)
        if current is not None and current.winfo_exists():
            self._close_file_menu_187()
            return 'break'

        p = palette_187()
        fs = max(9, min(12, int(load_ui().get('font_size') or 10)))
        menu_width, menu_height = 272, 220
        popup = tk.Toplevel(self)
        self.file_menu187 = popup
        popup.overrideredirect(True)
        popup.configure(bg=p['line'])
        popup.geometry(f'{menu_width}x{menu_height}')

        self.file_button187.update_idletasks()
        x = self.file_button187.winfo_rootx() + self.file_button187.winfo_width() - menu_width
        y = self.file_button187.winfo_rooty() + self.file_button187.winfo_height()
        popup.geometry(f'+{x}+{y}')

        body = tk.Frame(popup, bg=p['surface'], bd=0)
        body.pack(fill='both', expand=True, padx=2, pady=2)
        body.grid_columnconfigure(0, weight=1)

        self.file_menu_rows187 = []
        self.file_menu_labels187 = []
        self.file_menu_icon_labels187 = []
        entries = (
            ('ذخیره', self.manual_save),
            ('ذخیره با نام', self.save_as),
            ('بروزرسانی', self.refresh_all),
            ('تنظیمات', self.open_settings_187),
            ('ذخیره بسته توسعه', self.export_development_package),
            ('سیستم', lambda: self._select_tab_text('سیستم')),
        )
        for index, (label, command) in enumerate(entries):
            row = tk.Frame(body, bg=p['surface'], height=36, cursor='hand2')
            row.grid(row=index, column=0, sticky='ew')
            row.grid_propagate(False)
            row.grid_columnconfigure(0, weight=1)
            text = tk.Label(
                row, text=f'\u200f{label}', anchor='e', justify='right',
                bg=p['surface'], fg=p['text'],
                font=dashboard_font_187(self, fs + 3, 'control'), padx=8, cursor='hand2',
            )
            text.grid(row=0, column=0, sticky='nsew')
            icon = tk.Label(
                row, image=self._file_menu_icons187[index], width=40,
                anchor='center', bg=p['surface'], cursor='hand2',
            )
            icon.grid(row=0, column=1, sticky='nsew')

            def highlight(
                _event, widgets=(row, text, icon), text_widget=text, active=True,
            ):
                color = p['blue'] if active else p['surface']
                foreground = '#FFFFFF' if active else p['text']
                for widget in widgets:
                    widget.configure(bg=color)
                text_widget.configure(fg=foreground)

            callback = lambda _event, action=command: self._run_file_menu_command_187(action)
            for widget in (row, text, icon):
                widget.bind('<Enter>', highlight)
                widget.bind('<Leave>', lambda event, hover=highlight: hover(event, active=False))
                widget.bind('<Button-1>', callback)
            self.file_menu_rows187.append(row)
            self.file_menu_labels187.append(text)
            self.file_menu_icon_labels187.append(icon)

        popup.bind('<Escape>', self._close_file_menu_187)
        popup.bind('<FocusOut>', self._file_menu_focus_out_187)
        popup.after_idle(popup.focus_force)
        return 'break'

    def _install_shell_187(self):
        p = palette_187()
        fs = max(9, min(12, int(load_ui().get('font_size') or 10)))
        clock = getattr(self, 'datetime_label_186', None)
        if clock is None:
            return
        tools = clock.master
        top = tools.master
        top.configure(bg=p['surface'], highlightbackground=p['border_subtle'], highlightthickness=1)
        tools.configure(bg=p['surface'])

        for button in getattr(self, 'command_buttons', []):
            button.destroy()
        old_theme = getattr(self, 'quick_theme_button', None)
        if old_theme is not None:
            old_theme.destroy()
        clock.destroy()

        self.file_button187 = tk.Menubutton(
            tools, text='File', direction='below',
            bg=p['glass'], fg=p['text'],
            activebackground=p['panel2'], activeforeground=p['text'],
            relief='flat', bd=0,
            highlightbackground=p['line'], highlightthickness=1,
            font=dashboard_font_187(self, max(8, fs - 1), 'control'),
            padx=11, pady=5, cursor='hand2',
        )
        self.file_menu187 = None
        self._file_menu_icons187 = self._file_menu_icons_187(p['text'])
        self.file_button187.bind('<Button-1>', self._show_file_menu_187)
        self.file_button187.bind('<Return>', self._show_file_menu_187)
        self.file_button187.bind('<space>', self._show_file_menu_187)
        self.file_button187.pack(side='right', padx=2)

        self.quick_commands_host187 = tk.Frame(top, bg=p['surface'])
        self.quick_commands_host187.pack(side='left', padx=(8, 2), pady=8)
        self.command_buttons = []
        for text, command, tip in (
            ('Save', self.manual_save, 'بکاپ دستی'),
            ('Undo', self.undo, 'بازگشت آخرین عملیات'),
            ('Redo', self.redo, 'اجرای دوباره'),
        ):
            button = self._shell_button_187(
                self.quick_commands_host187, text, command, fs, side='left',
            )
            v186.v18.add_tooltip(button, tip)
            self.command_buttons.append(button)

        top_height = int(top.cget('height') or 62)
        top_color = p['surface_alt']
        footer_height = min(54, top_height)
        self.footer187 = tk.Frame(
            self, bg=top_color, height=footer_height,
            highlightbackground=p['line'], highlightthickness=1,
        )
        self.footer187.pack(side='bottom', fill='x', before=self.notebook)
        self.footer187.pack_propagate(False)

        self.footer_messages_host187 = tk.Frame(self.footer187, bg=p['surface'], width=44, height=44)
        self.footer_messages_host187.pack(side='right', padx=(4, 8), pady=4)
        self.footer_messages_host187.pack_propagate(False)
        self.messages_button187 = tk.Button(
            self.footer_messages_host187, text='\ue7ed',
            command=lambda: FinancialMessagesDialog187(self, SERVICE),
            bg=p['glass'], fg=p['text'], activebackground=p['panel2'],
            relief='flat', highlightbackground=p['line'], highlightthickness=1,
            font=('Segoe MDL2 Assets', 16), padx=4, pady=2, cursor='hand2',
        )
        self.messages_button187.pack(fill='both', expand=True)
        self.messages_text187 = tk.StringVar(value='')
        v186.v18.add_tooltip(self.messages_button187, 'پیام‌ها')

        language_value = 'ENG' if str(load_ui().get('language') or 'fa').lower() == 'en' else 'فا'
        self.footer_language_button187 = tk.Button(
            self.footer187, text=language_value, command=self._toggle_language_187,
            bg=p['glass'], fg=p['text'], activebackground=p['panel2'],
            relief='flat', highlightbackground=p['line'], highlightthickness=1,
            font=dashboard_font_187(self, max(8, fs - 2), 'control'), padx=7, pady=4, cursor='hand2',
        )
        self.footer_language_button187.pack(side='right', padx=3, pady=4)

        current_mode = str(load_ui().get('appearance') or 'dark').lower()
        self.footer_mode_button187 = tk.Menubutton(
            self.footer187, text='روشن' if current_mode == 'light' else 'تیره',
            direction='above', bg=p['glass'], fg=p['text'],
            activebackground=p['panel2'], activeforeground=p['text'],
            relief='flat', highlightbackground=p['line'], highlightthickness=1,
            font=dashboard_font_187(self, max(8, fs - 2), 'control'), padx=9, pady=4, cursor='hand2',
        )
        self.footer_theme_menu187 = tk.Menu(
            self.footer_mode_button187, tearoff=False,
            bg=p['surface'], fg=p['text'], activebackground=p['blue'],
            activeforeground=p['on_accent'], font=dashboard_font_187(self, max(9, fs), 'control'),
        )
        self.footer_theme_menu187.add_command(label='روشن', command=lambda: self._set_theme_mode_187('dark'))
        self.footer_theme_menu187.add_command(label='خاموش', command=lambda: self._set_theme_mode_187('light'))
        self.footer_mode_button187.bind('<Button-1>', self._show_footer_mode_menu_187)
        self.footer_mode_button187.pack(side='right', padx=3, pady=4)

        self.footer_theme_button187 = tk.Menubutton(
            self.footer187, text='تم', direction='above', bg=p['glass'], fg=p['text'],
            activebackground=p['panel2'], activeforeground=p['text'],
            relief='flat', highlightbackground=p['line'], highlightthickness=1,
            font=dashboard_font_187(self, max(8, fs - 2), 'control'), padx=9, pady=4, cursor='hand2',
        )
        self.footer_themes_menu187 = tk.Menu(
            self.footer_theme_button187, tearoff=False,
            bg=p['surface'], fg=p['text'], activebackground=p['blue'],
            activeforeground=p['on_accent'], font=dashboard_font_187(self, max(9, fs), 'control'),
        )
        for theme_id in (1, 2):
            self.footer_themes_menu187.add_command(
                label=f'تم {fa(theme_id)}', command=lambda value=theme_id: self._set_theme_id_187(value),
            )
        self.footer_theme_button187.bind('<Button-1>', self._show_footer_theme_menu_187)
        self.footer_theme_button187.pack(side='right', padx=3, pady=4)
        self.quick_theme_button = self.footer_mode_button187

        self.footer_clock_host187 = tk.Frame(self.footer187, bg=p['surface'], width=116, height=46)
        self.footer_clock_host187.pack(side='right', padx=(3, 8), pady=3)
        self.footer_clock_host187.pack_propagate(False)
        self.datetime_label_186 = tk.Label(
            self.footer_clock_host187, textvariable=self.datetime_top,
            bg=p['glass'], fg=p['text'],
            highlightbackground=p['line'], highlightthickness=1,
            font=dashboard_font_187(self, max(8, fs - 1), 'control'),
            anchor='e', justify='right', padx=8, pady=2,
        )
        self.datetime_label_186.pack(fill='both', expand=True)
        for widget in (
            self.footer_clock_host187, self.footer_mode_button187,
            self.footer_theme_button187, self.footer_language_button187,
        ):
            widget.pack_forget()
        self.footer_clock_host187.pack(side='right', padx=(3, 8), pady=3)
        self.footer_mode_button187.pack(side='right', padx=3, pady=4)
        self.footer_theme_button187.pack(side='right', padx=3, pady=4)
        self.footer_language_button187.pack(side='right', padx=3, pady=4)

        system_tab = getattr(self, 'system_tab186', None)
        if system_tab is not None:
            for widget in v186._walk(system_tab):
                if isinstance(widget, (tk.Button, ttk.Button)):
                    try:
                        if widget.cget('text') == 'بسته توسعه':
                            widget.configure(text='ذخیره بسته توسعه')
                    except tk.TclError:
                        pass
        self._refresh_message_count_187()

    def _build_approval_center(self):
        tab = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.approval_tab = tab
        self.notebook.insert(1, tab, text='ثبت دیتا')
        self.approval_center = DataEntryCenter187(tab, self.rich, on_posted=self.refresh_all)
        self.approval_center.pack(fill='both', expand=True)
        # The record action above Pending is deliberately redirected to the
        # dedicated sales record, never to the data-entry/manual transaction UI.
        self.approval_center.open_selected_record_187 = self.open_selected_record_187
        if self._bot_process:
            self.approval_center.set_bot_process(self._bot_process, self._bot_log)
        self.after_idle(self._rebuild_navbar)

    def _build_sales(self):
        """Use one versioned sales workspace over the existing ledger."""
        root = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.notebook.add(root, text='فروش و مطالبات')
        self.sales_root = root
        self.sales_claims187 = SalesClaimsPanel187(
            root, db=DB, base_dir=BASE_DIR, on_changed=self.refresh_all,
        )
        self.sales_claims187.pack(fill='both', expand=True)
        self.sales_nb = self.sales_claims187.nb
        self.sales_table = self.sales_claims187.contract_tree

    def open_selected_record_187(self, sale_id: str = '', draft=None, document_path: str = ''):
        """Dashboard-level bridge used by the Pending record action and the sales wizard."""
        panel = getattr(self, 'sales_claims187', None)
        if panel is None:
            return None
        return panel.open_sales_record(sale_id=sale_id, draft=draft, document_path=document_path)

    def open_sales_wizard_187(self):
        """Record creation always starts in the dedicated sales-contract wizard."""
        panel = getattr(self, 'sales_claims187', None)
        if panel is None:
            return None
        return panel.open_wizard()

    def refresh_sales(self):
        panel = getattr(self, 'sales_claims187', None)
        if panel is not None:
            panel.refresh()

    def _build_settings(self):
        self.settings_window187 = None
        self.settings_tab187 = None
        self.settings_tab186 = None
        self.settings_tab185 = None

    def open_settings_187(self):
        window = getattr(self, 'settings_window187', None)
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            window.focus_force()
            return window
        p = palette_187()
        window = tk.Toplevel(self)
        self.settings_window187 = window
        window.title('تنظیمات — BARKAV 18.7.1')
        width, height = 760, 620
        window.update_idletasks()
        screen_width, screen_height = window.winfo_screenwidth(), window.winfo_screenheight()
        x = max(0, screen_width - width - 24)
        y = max(0, min((screen_height - height) // 2, screen_height - height - 48))
        window.geometry(f'{width}x{height}+{x}+{y}')
        window.minsize(620, 420)
        window.configure(bg=p['bg'])
        window.transient(self)
        shell = tk.Frame(window, bg=p['bg'])
        shell.pack(fill='both', expand=True)
        canvas = tk.Canvas(shell, bg=p['bg'], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(shell, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        body = tk.Frame(canvas, bg=p['bg'])
        item = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _event: canvas.configure(scrollregion=canvas.bbox('all')), add='+')
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width), add='+')
        canvas.bind('<MouseWheel>', lambda event: canvas.yview_scroll(int(-event.delta / 120), 'units'), add='+')
        canvas.bind('<Button-4>', lambda _event: canvas.yview_scroll(-3, 'units'), add='+')
        canvas.bind('<Button-5>', lambda _event: canvas.yview_scroll(3, 'units'), add='+')
        tab = SettingsTab187(body, self._settings_saved)
        self.settings_tab187 = tab
        self.settings_tab186 = tab
        self.settings_tab185 = tab
        tab.pack(fill='x', expand=True)
        window.protocol('WM_DELETE_WINDOW', lambda: (window.destroy(), setattr(self, 'settings_window187', None)))
        window.after_idle(window.focus_force)
        return window

    def _build_reports(self):
        super()._build_reports()
        self._barkav_service_187 = SERVICE
        self._barkav_base_187 = BASE_DIR
        self._barkav_apply_phase04_187 = v186.v18.apply_phase04_rules_v18
        install_report_controls_187(self)

    def open_phase_by_no(self, number: int):
        row = next(
            (item for item in self._phase_summary_live() if item['phase_no'] == int(number)),
            None,
        )
        if row:
            PhaseDetailDialog187(
                self, self.rich, int(number), row['phase'], self.refresh_all
            )

    def _settings_saved(self, old, new):
        changed = {key for key in (
            'appearance', 'font_family', 'font_weight', 'font_size', 'row_height', 'theme_id',
            'language', 'background_color',
        ) if old.get(key) != new.get(key)}
        live = changed & {'font_family', 'font_weight', 'font_size', 'row_height', 'language'}
        visual = bool(changed & {'appearance', 'theme_id', 'background_color'})
        self.ui = load_ui()
        if live:
            self._apply_settings_live_187(old, new)
        if visual:
            window = getattr(self, 'settings_window187', None)
            if window is not None and window.winfo_exists():
                window.destroy()
                self.settings_window187 = None
            messagebox.showinfo(
                'تنظیمات', 'تنظیمات پوسته ذخیره شد؛ رابط کاربری بازآفرینی می‌شود.', parent=self
            )
            self._restart_requested = True
            self.after(100, self.destroy)
        elif not live:
            self.refresh_all()
            messagebox.showinfo('تنظیمات', 'تنظیمات ذخیره و اعمال شد.', parent=self)

    def _rebuild_navbar(self):
        if not getattr(self, 'navbar', None):
            return
        if theme_id_187() == 1:
            return super()._rebuild_navbar()
        for child in self.navbar.winfo_children():
            child.destroy()
        metrics = get_theme(theme_id_187()).metrics
        self.navbar.configure(height=metrics['nav_height'])
        self.nav_buttons = {}
        self._nav_images187 = {}
        p = palette_187()
        tabs = {self.notebook.tab(tab_id, 'text'): tab_id for tab_id in self.notebook.tabs()}
        if 'حساب مدیر' not in tabs and 'حساب مدیر پروژه' in tabs:
            self.notebook.tab(tabs['حساب مدیر پروژه'], text='حساب مدیر')
            tabs['حساب مدیر'] = tabs['حساب مدیر پروژه']
        asset_map = {
            'داشبورد': 'nav_dashboard.png', 'ثبت دیتا': 'nav_data.png',
            'تراکنش‌ها': 'nav_transactions.png', 'فروش و مطالبات': 'nav_sales.png',
            'گزارش‌گیری': 'nav_reports.png', 'حساب مدیر': 'nav_manager.png',
        }
        for label in self._VISIBLE_NAV:
            target = tabs.get(label)
            if not target:
                continue
            image = None
            path = BASE_DIR / 'assets' / asset_map.get(label, '')
            try:
                from PIL import Image, ImageTk
                source = Image.open(path).convert('RGBA')
                source.thumbnail((28, 28), Image.Resampling.LANCZOS)
                image = ImageTk.PhotoImage(source, master=self)
                self._nav_images187[label] = image
            except Exception:
                image = None
            button = tk.Button(
                self.navbar, text=label if image else f'{label}  ◈', image=image,
                compound='top' if image else 'left',
                command=lambda tab_id=target: self.notebook.select(tab_id),
                bg=p['surface'], fg=p['muted'], activebackground=p['panel2'],
                activeforeground=p['cyan'], relief='flat', bd=0,
                font=dashboard_font_187(self, 8, 'control'), padx=14, pady=2, cursor='hand2',
                highlightbackground=p['surface'], highlightthickness=1,
            )
            button.pack(side='right', fill='y', padx=1, pady=2)
            self.nav_buttons[target] = button
        self._sync_nav()

    def _decorate_top_187(self):
        icons = ('💾', '↶', '↷', '⟳', '⚙', '⧉', '◉')
        for icon, button in zip(icons, getattr(self, 'command_buttons', [])):
            try:
                button.configure(text=f'{icon}  {button.cget("text")}')
            except Exception:
                pass
        tools = getattr(self, 'datetime_label_186', None)
        if tools is None or getattr(self, 'messages_button187', None):
            return
        p = palette_187()
        self.messages_text187 = tk.StringVar(value='پیام‌ها')
        self.messages_button187 = tk.Button(
            tools.master, textvariable=self.messages_text187,
            command=lambda: FinancialMessagesDialog187(self, SERVICE),
            bg=p['glass'], fg=p['text'], activebackground=p['panel2'],
            relief='flat', highlightbackground=p['line'], highlightthickness=1,
            font=('Segoe MDL2 Assets', 9), padx=9, pady=5, cursor='hand2',
        )
        # Packed after the clock/theme controls: visually left of the clock in RTL header.
        self.messages_button187.pack(side='right', padx=3)
        self._refresh_message_count_187()

    def _install_chart_details_187(self):
        try:
            apply_donut_theme_187(self.cost_donut)
            apply_progress_theme_187(self.overall_progress)
            apply_line_theme_187(self.liquidity_chart)
            apply_bar_theme_187(self.phase_chart)
        except Exception:
            pass
        bindings = (
            (getattr(self, 'cost_donut', None), 'donut'),
            (getattr(self, 'liquidity_chart', None), 'line'),
            (getattr(self, 'phase_chart', None), 'bar'),
        )
        for widget, kind in bindings:
            if widget is not None:
                widget.configure(cursor='hand2')
                widget.bind('<Double-1>', lambda _event, value=kind: ChartDetailDialog187(self, value), add='+')

    def _install_dashboard_links_187(self):
        mapping = {
            'تراکنش‌ها': 'تراکنش‌ها', 'چک‌ها': 'چک‌ها',
            'تسهیلات': 'گزارش‌گیری', 'فروش و مطالبات': 'فروش و مطالبات',
            '۳۰ روز آینده': '__calendar__',
        }
        sections = {}
        key_group = {
            'total_in': 'تراکنش‌ها', 'ch_all_total': 'چک‌ها',
            'loan_principal': 'تسهیلات', 'sales_contract': 'فروش و مطالبات',
            'liq_obligation': '۳۰ روز آینده',
        }
        for key, title in key_group.items():
            metric = getattr(self, 'cards', {}).get(key)
            if metric is not None:
                try:
                    sections[title] = metric.master.master
                except Exception:
                    pass
        for title, section in sections.items():
            target = mapping[title]
            try:
                header = section.winfo_children()[0]
            except Exception:
                continue
            callback = (
                (lambda _event: FinancialCalendarDialog187(self, SERVICE))
                if target == '__calendar__' else
                (lambda _event, value=target: self._select_tab_text(value))
            )
            header.configure(cursor='hand2')
            header.bind('<Button-1>', callback, add='+')
            for child in header.winfo_children():
                child.configure(cursor='hand2')
                child.bind('<Button-1>', callback, add='+')

    def _refresh_message_count_187(self):
        if getattr(self, 'messages_text187', None):
            self.messages_text187.set('')

    def _show_startup_reminders_187(self):
        if self._startup_reminder_shown_187:
            return
        self._startup_reminder_shown_187 = True
        try:
            if upcoming_events_187(SERVICE, 30):
                FinancialMessagesDialog187(self, SERVICE, startup=True)
        except Exception:
            pass

    def _upgrade_tables_184(self, root=None):
        super()._upgrade_tables_184(root)
        target = root or self

        def apply():
            for widget in v186._walk(target):
                if isinstance(widget, ttk.Treeview):
                    apply_tree_rtl_187(widget)
                    stripe_tree(widget, theme_selection_187())
        try:
            target.after_idle(apply)
        except Exception:
            apply()

    def _apply_financial_report_theme_187(self):
        """Retarget inherited transaction and manager-report widgets to 18.7 styles only."""
        p = palette_187()
        size = max(9, min(18, int(load_ui().get('font_size') or 11)))
        family = resolve_font_family_187(self, load_ui().get('font_family'))
        weight = resolve_font_weight_187(self, family, load_ui().get('font_weight'))
        notebook = getattr(self, 'fin_nb', None)
        if isinstance(notebook, ttk.Notebook):
            notebook.configure(style='Barkav.Data.TNotebook')

        table_names = (
            'all_tx_table', 'exp_table', 'cheque_table', 'in_table',
            'out_table', 'loan_table', 'document_table', 'manager_withdraw_table',
        )
        for name in table_names:
            table = getattr(self, name, None)
            tree = getattr(table, 'tree', None)
            if isinstance(tree, ttk.Treeview):
                tree.configure(style='Barkav.Data.Treeview')
                stripe_tree(tree, theme_selection_187())
            if isinstance(table, tk.Misc):
                for widget in v186._walk(table):
                    self._apply_widget_font_187(widget, family, weight, size)

        for metric in getattr(self, 'manager_metrics', {}).values():
            if isinstance(metric, tk.Misc):
                for widget in v186._walk(metric):
                    self._apply_widget_font_187(widget, family, weight, size)
        for widget in v186._walk(self):
            if isinstance(widget, ttk.Notebook) and widget is notebook:
                continue
            if getattr(widget, 'master', None) is notebook:
                self._apply_widget_font_187(widget, family, weight, size)
        try:
            self.configure(bg=p['bg'])
        except tk.TclError:
            pass

    def _restyle_dashboard_187(self):
        """Apply visible Dashboard-only hierarchy without touching presentation data."""
        p = palette_187()
        canvas = getattr(self, 'overview_canvas', None)
        if canvas is not None:
            canvas.configure(bg=p['bg'], highlightthickness=0)
            for child in canvas.winfo_children():
                child.configure(bg=p['bg'])

        sections = []
        for metric in getattr(self, 'cards', {}).values():
            try:
                section = metric.master.master
            except (AttributeError, tk.TclError):
                continue
            if section not in sections:
                sections.append(section)
        phase_strip = getattr(self, 'phase_strip', None)
        if phase_strip is not None:
            sections.append(phase_strip.master.master)

        for section in sections:
            try:
                section.configure(bg=p['card'], highlightbackground=p['border_subtle'], highlightthickness=1)
                section.grid_configure(padx=8, pady=8)
            except tk.TclError:
                continue
            children = section.winfo_children()
            if children:
                header = children[0]
                header.configure(bg=p['surface_alt'], height=theme_metrics_187()['card_header_height'])
                for label in header.winfo_children():
                    if isinstance(label, tk.Label):
                        label.configure(bg=p['surface_alt'], fg=p['text_primary'],
                                        font=dashboard_font_187(self, 10, 'title'))

        for index, metric in enumerate(getattr(self, 'cards', {}).values()):
            background = p['surface_alt'] if index % 2 == 0 else p['card']
            metric.configure(bg=background, highlightbackground=p['border_subtle'], highlightthickness=1)
            metric.title_label.configure(bg=background, fg=p['text_secondary'],
                                         font=dashboard_font_187(self, 8, 'body'))
            metric.value_label.configure(bg=background, fg=p['text_primary'],
                                         font=dashboard_font_187(self, 11, 'kpi'))
            metric.pack_configure(pady=3)

        if phase_strip is not None:
            phase_strip.configure(bg=p['card'])
        for button in getattr(self, 'phase_buttons', {}).values():
            button.configure(bg=p['glass'], fg=p['text_secondary'], activebackground=p['info'],
                             activeforeground=p['on_accent'], highlightbackground=p['border_subtle'],
                             highlightthickness=1, pady=6)
        for chart in (getattr(self, 'cost_donut', None), getattr(self, 'liquidity_chart', None),
                      getattr(self, 'phase_chart', None)):
            if chart is not None:
                chart.grid_configure(padx=8, pady=8)

    def refresh_overview(self):
        super().refresh_overview()
        if getattr(self, 'messages_text187', None):
            self._refresh_message_count_187()

    def refresh_reports(self):
        super().refresh_reports()
        self._apply_financial_report_theme_187()
        try:
            version = SERVICE.budget.latest_version()
            if version:
                created = str(version.get('created_at') or '').replace('T', ' ')[:16]
                self.budget_version.set(
                    f"نسخه برآورد: {fa(version.get('version_no'))} — "
                    f"{version.get('title')} — {fa(created)}"
                )
        except Exception:
            pass

    def _finalize_187(self):
        p = palette_187()
        self.configure(bg=p['bg'])
        self._decorate_top_187()
        self._restyle_dashboard_187()
        self._install_chart_details_187()
        self._install_dashboard_links_187()
        self._upgrade_tables_184(self)
        self._apply_financial_report_theme_187()
        try:
            # The approved brand mark is the 18.4 artwork referenced by the
            # 18.6 correction document. Keep the versioned reference explicit.
            self.iconbitmap(default=str(BASE_DIR / 'assets' / 'BARKAV_18_4.ico'))
        except Exception:
            pass

    def export_development_package(self):
        destination = filedialog.asksaveasfilename(
            parent=self, defaultextension='.zip',
            initialfile='BARKAV_Development_Package_18.7.zip',
            filetypes=[('ZIP', '*.zip')],
        )
        if not destination:
            return
        try:
            from development_package_v187 import build_development_package
            result = build_development_package(BASE_DIR, Path(destination), VERSION)
            messagebox.showinfo(
                'ذخیره بسته توسعه',
                f"بسته توسعه {VERSION} ذخیره شد:\n{result['path']}\n\n"
                'دیتابیس زنده، لاگ و فایل محرمانه وارد بسته نشده‌اند.',
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror('ذخیره بسته توسعه', str(exc), parent=self)


def run_dashboard_187() -> None:
    app = Stage187Dashboard()
    app.mainloop()


if __name__ == '__main__':
    run_dashboard_187()


# Deferred imports avoid a circular dependency while preserving runtime behaviour.
from financial_calendar import (
    FinancialCalendarDialog187, FinancialMessagesDialog187, upcoming_events_187,
)
from sales_claims import SalesClaimsPanel187, is_temporary_sales_finance_pending_187

def install_report_controls_187(app):
    from reports import install_report_controls_187 as implementation
    return implementation(app)

def PhaseDetailDialog187(*args, **kwargs):
    from reports import PhaseDetailDialog187 as implementation
    return implementation(*args, **kwargs)
