from __future__ import annotations

import os
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable
from ui_stage10 import DateField, SignedMetric, bind_grouped_number, group_int, parse_int
from unit_service import UnitService

from config_loader import load_config
from dashboard_service_stage12 import DashboardServiceStage12
from export_utils import export_pdf, export_xlsx, print_file
from finance_db import FinanceDB
from reaction_cleanup import clear_group_reaction
from revenue_service import gregorian_to_shamsi, shamsi_to_gregorian, normalize_shamsi
from telegram_history_import import import_telegram_export

BASE_DIR=Path(__file__).resolve().parent
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
        if self.delete_handler:menu.add_command(label='🗑 حذف/ابطال',command=self._delete_selected)
        if self.edit_handler or self.delete_handler:menu.add_separator()
        menu.add_command(label='📋 کپی',command=self.copy_selected);menu.add_command(label='📥 پیست در فیلتر',command=self.paste_filter)
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
    def _confirm_row_action(self,title,message):
        """A single-row action asks for itself; a bulk delete has already asked once for the whole selection."""
        if getattr(self,'_bulk_delete_confirmed',False):return True
        return messagebox.askyesno(title,message,parent=self)

    def _delete_tx_row(self,r):
        if not r:return
        if not self._confirm_row_action('حذف','ثبت انتخاب‌شده Soft Delete شود؟'):return
        try:
            if r.get('pending_id'):SERVICE.delete_posting(r['pending_id'])
            else:SERVICE.delete_manual_transaction(r['transaction_id'])
            self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

    def _delete_expense_row(self,r):
        if not r:return
        if not r.get('pending_id'):
            messagebox.showwarning('حذف','این هزینه Posting متصل ندارد و از این مسیر حذف نمی‌شود.',parent=self);return
        if not self._confirm_row_action('حذف','هزینه و اثر مالی آن Soft Delete شود؟'):return
        try:SERVICE.delete_posting(r['pending_id']);self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

    def _cancel_loan_row(self,r):
        if r and self._confirm_row_action('لغو وام','وام انتخاب‌شده لغو شود؟ تراکنش‌های قبلی حذف نمی‌شوند.'):
            try:SERVICE.loans.cancel_loan(r['loan_id']);self.refresh_all()
            except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

    def _cancel_cheque_row(self,r):
        if not r:return
        if not self._confirm_row_action('لغو چک','چک انتخاب‌شده لغو شود؟ هزینه اصلی حذف نمی‌شود.'):return
        try:DB.cancel_cheque(r['cheque_id'],source='GUI',actor_id='GUI');self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

    def _cancel_sale_row(self,r):
        if not r:return
        if not self._confirm_row_action('لغو قرارداد',f"قرارداد فروش واحد {r.get('unit_number') or '-'} لغو شود؟"):return
        try:SERVICE.revenue.cancel_sale(r['sale_id']);self.refresh_all()
        except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

    def _delete_rec_row(self,r):
        if r and self._confirm_row_action('حذف تطبیق','این رکورد تطبیق بانک Soft Delete شود؟'):
            try:SERVICE.delete_reconciliation(r['reconciliation_id']);self.refresh_all()
            except Exception as e:messagebox.showerror('خطا',str(e),parent=self)

    def _delete_phase_row(self,r):
        if not r or r.get('phase_id')=='UNCLASSIFIED':return
        if not self._confirm_row_action('حذف فاز',f"فاز «{r.get('phase')}» حذف شود؟"):return
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
