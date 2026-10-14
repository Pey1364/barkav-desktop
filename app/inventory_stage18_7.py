"""مدیریت انبار خواندنی از هزینه‌های مصالح ثبت‌شده در تراکنش‌ها."""
from __future__ import annotations
import os, subprocess, tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable
from barkav.features.dashboard import SmartTable
from sales_claims_stage18_7 import show_export_preview_187
from ui_stage18_3 import en, fa, group_int_fa

INVENTORY_COLUMNS_187 = (
 ('row','ردیف',82),('date','تاریخ خرید',120),('material','نام مصالح',220),
 ('unit','واحد',82),('quantity','مقدار',105),('unit_price','قیمت واحد',145),
 ('total','قیمت کل',155),('phase','فاز ساخت',175),('invoice','فاکتور',115))
INVENTORY_FILTER_KEYS_187=('نام مصالح','فاز ساخت','تاریخ')
INVENTORY_EXPORT_VALUES_187=('خروجی','PDF','Excel','پرینت')
MATERIAL_MARKERS_187=('مصالح','مواد','material','materials')

def _text(v:Any)->str:return str(v if v is not None else '').strip()
def _norm(v:Any)->str:return en(_text(v)).replace('ي','ی').replace('ك','ک').lower()
def _first(*vs:Any)->Any:
    for v in vs:
        if v not in (None,''): return v
    return ''
def _num(v:Any)->float|None:
    if v in (None,''): return None
    try:return float(str(en(str(v))).replace(',','').strip())
    except (TypeError,ValueError):return None
def _money(v:Any)->str:
    n=_num(v);return '' if n is None else group_int_fa(int(round(n)))
def _qty(v:Any)->str:
    n=_num(v);return '' if n is None else fa(f'{n:g}')
def _is_material(exp:dict[str,Any],payload:dict[str,Any])->bool:
    vals=(exp.get('category'),exp.get('cost_group'),exp.get('activity_name_display'),
          exp.get('activity_name'),payload.get('category'),payload.get('cost_group'),
          payload.get('expense_category'),payload.get('v18_subtype'))
    hay=' '.join(_norm(v) for v in vals)
    return any(marker in hay for marker in MATERIAL_MARKERS_187)

def build_inventory_rows_187(expenses,transactions,payload_resolver:Callable|None=None)->list[dict[str,Any]]:
    tx={_text(r.get('transaction_id')):dict(r) for r in transactions or ()
        if _text(r.get('transaction_id'))}
    out=[]
    for expense in expenses or ():
        src=dict(expense or {}); linked=tx.get(_text(src.get('transaction_id')),{}); merged={**src,**linked}
        try: payload=dict(payload_resolver(merged) or {}) if payload_resolver else {}
        except (AttributeError,KeyError,TypeError,ValueError): payload={}
        if not _is_material(src,payload): continue
        total=_first(linked.get('amount'),payload.get('final_amount'),payload.get('amount'),src.get('final_amount'))
        out.append({'transaction_id':src.get('transaction_id') or linked.get('transaction_id') or '',
          'expense_id':src.get('expense_id') or '','pending_id':src.get('pending_id') or '',
          'posting_id':src.get('posting_id') or '','receipt_count':int(src.get('receipt_count') or 0),
          'date_value':_first(src.get('shamsi_date'),payload.get('event_date_shamsi'),src.get('event_date')),
          'material_value':_text(_first(payload.get('material_name'),payload.get('material'),payload.get('item_name'),src.get('material_name'),src.get('material'),src.get('description'))),
          'unit_value':_text(_first(payload.get('unit'),payload.get('material_unit'),payload.get('unit_name'),src.get('unit'))),
          'quantity_value':_first(payload.get('quantity'),payload.get('qty'),payload.get('material_quantity'),payload.get('material_qty')),
          'unit_price_value':_first(payload.get('unit_price'),payload.get('unit_rate'),payload.get('material_unit_price'),payload.get('price_unit')),
          'total_value':total,'phase_value':_text(_first(payload.get('main_phase'),payload.get('construction_stage'),src.get('phase_name'),src.get('construction_stage'))),
          '_sum_amount':_num(total) or 0})
    return out

class InventoryPanel187(ttk.Frame):
    def __init__(self,parent:tk.Misc,app):
        super().__init__(parent,style='Panel.TFrame');self.app=app;self._source_rows=[]
        self.filter_key=tk.StringVar(value=INVENTORY_FILTER_KEYS_187[0]);self.filter_value=tk.StringVar(value='همه')
        self.export_choice=tk.StringVar(value=INVENTORY_EXPORT_VALUES_187[0]);self._build();self.refresh()
    def _build(self):
        f=ttk.Frame(self);f.pack(fill='x',pady=(0,4));self.filterbar=f;center=ttk.Frame(f);center.pack(side='left',fill='x',expand=True);f=center;ttk.Label(f,text='نمایش براساس').pack(side='right',padx=(0,6))
        k=ttk.Combobox(f,textvariable=self.filter_key,state='readonly',values=INVENTORY_FILTER_KEYS_187,width=15,justify='right');k.pack(side='right',padx=2)
        self.filter_value_combo=ttk.Combobox(f,textvariable=self.filter_value,state='readonly',values=('همه',),width=16,justify='right');self.filter_value_combo.pack(side='right',padx=2)
        k.bind('<<ComboboxSelected>>',self._key_changed,add='+');self.filter_value_combo.bind('<<ComboboxSelected>>',lambda e:self._apply(),add='+')
        self.table=SmartTable(self,INVENTORY_COLUMNS_187,title='');self.table.pack(fill='both',expand=True);self._toolbar()
        self.table.tree.heading('row',text='ردیف',command=self._toggle_all);self.table.tree.bind('<<TreeviewSelect>>',lambda e:self._sync(),add='+')
        self.table.tree.unbind('<Double-1>');self.table.tree.bind('<Double-1>',self._double,add='+')
        self.table.tree.unbind('<Button-3>');self.table.tree.bind('<Button-3>',self._menu,add='+')
        self.table.tree.bind('<Map>',lambda e:self._right(),add='+')
    def _toolbar(self):
        bar=self.table.winfo_children()[0]
        bar.destroy()
        host=getattr(self,'filterbar',self)
        actions=ttk.Frame(host)
        actions.pack(side='right',padx=2)
        for label,cmd in (('افزودن',self.add_row),('ویرایش',self.edit_row),('حذف',self.delete_rows),('کپی',self.copy_row)):
            ttk.Button(actions,text=label,command=cmd,style='TableToolbar.TButton').pack(side='right',padx=2)
        combo=ttk.Combobox(host,textvariable=self.export_choice,state='readonly',values=INVENTORY_EXPORT_VALUES_187,width=18,justify='right')
        combo.pack(side='left',padx=2)
        combo.bind('<<ComboboxSelected>>',lambda e:self._export(),add='+')
    def _source_key(self):return {'نام مصالح':'material_value','فاز ساخت':'phase_value','تاریخ':'date_value'}.get(self.filter_key.get(),'material_value')
    def _key_changed(self,_=None):self._values();self._apply()
    def _values(self):
        vals=sorted({_text(r.get(self._source_key())) for r in self._source_rows if _text(r.get(self._source_key()))},key=_norm)
        choices=('همه',*vals);self.filter_value_combo.configure(values=choices)
        if self.filter_value.get() not in choices:self.filter_value.set('همه')
    def _apply(self):
        chosen=self.filter_value.get();key=self._source_key();rows=[r for r in self._source_rows if chosen=='همه' or _norm(r.get(key))==_norm(chosen)]
        self.table.set_rows(rows,self._render);self._right();self._sync()
    def _render(self,row):
        row['_inventory_number187']=self.table.filtered_rows.index(row)+1 if row in self.table.filtered_rows else 0
        checked='☑' if row in self.table.selected_rows() else '☐'
        return [f'{checked} {fa(row.get("_inventory_number187") or 0)}',fa(_text(row.get('date_value'))),_text(row.get('material_value')),_text(row.get('unit_value')),_qty(row.get('quantity_value')),_money(row.get('unit_price_value')),_money(row.get('total_value')),_text(row.get('phase_value')),'🧾 نمایش فاکتور' if row.get('receipt_count') else '']
    def _sync(self):
        selected=set(self.table.tree.selection())
        try:idx=tuple(self.table.tree.cget('columns')).index('row')
        except (ValueError,tk.TclError):return
        for iid in self.table.tree.get_children():
            vals=list(self.table.tree.item(iid,'values') or ());row=getattr(self.table,'_iid_to_row',{}).get(iid)
            if row is not None and idx<len(vals):vals[idx]=f"{'☑' if iid in selected else '☐'} {fa(row.get('_inventory_number187') or 0)}";self.table.tree.item(iid,values=vals)
    def _toggle_all(self):
        children=self.table.tree.get_children()
        if children and len(self.table.tree.selection())==len(children):self.table.tree.selection_remove(children)
        elif children:self.table.tree.selection_set(children)
        self._sync()
    def _right(self):
        try:self.table.tree.xview_moveto(1.0)
        except tk.TclError:pass
    def refresh(self):
        service=getattr(self.app,'_barkav_service_187',None) or getattr(self.app,'service',None)
        if service is None:self._source_rows=[];self._apply();return
        try:
            ex=service.list_construction_expenses(limit=3000);tx=service.list_transactions(limit=3000)
            self._source_rows=build_inventory_rows_187(ex,tx,getattr(self.app,'_transaction_payload_187',None))
        except (AttributeError,TypeError,ValueError):self._source_rows=[]
        self._values();self._apply()
    def add_row(self):
        c=getattr(self.app,'approval_center',None)
        if c is not None and hasattr(c,'manual_transaction'):c.manual_transaction()
        else:messagebox.showwarning('مدیریت انبار','فرم ثبت تراکنش در دسترس نیست.',parent=self)
    def edit_row(self):
        rows=self.table.selected_rows();h=getattr(self.app,'edit_expense_row',None)
        if rows and callable(h):h(rows[0])
        elif not rows:messagebox.showinfo('مدیریت انبار','ابتدا یک ردیف را انتخاب کنید.',parent=self)
    def delete_rows(self):
        rows=list(self.table.selected_rows())
        if not rows:return messagebox.showinfo('مدیریت انبار','ابتدا ردیف‌های موردنظر را انتخاب کنید.',parent=self)
        bulk=getattr(self.app,'_delete_lifecycle_rows187',None)
        if callable(bulk):return bulk(rows)
        from table_actions import select_delete_rows,confirmed_delete,DeleteChoice
        rows=select_delete_rows(self,rows,messagebox=messagebox)
        if not rows:return
        h=getattr(self.app,'_delete_expense_row',None)
        if not callable(h):return messagebox.showerror('مدیریت انبار','handler حذف هزینه در دسترس نیست.',parent=self)
        with confirmed_delete(DeleteChoice()):
            for row in rows:h(row)
    def copy_row(self):
        h=getattr(self.app,'_copy_transaction_187',None)
        if callable(h):h(self.table)
    def _double(self,event):
        iid=self.table.tree.identify_row(event.y)
        if not iid:return 'break'
        self.table.tree.selection_set(iid);display=tuple(self.table.tree.cget('displaycolumns') or ())
        if self.table.tree.identify_column(event.x)==f"#{display.index('invoice')+1}":self._invoice(getattr(self.table,'_iid_to_row',{}).get(iid,{}))
        else:self.edit_row()
        return 'break'
    def _invoice(self,row):
        h=getattr(self.app,'_transaction_document_paths_187',None);paths=h(self.table,row) if callable(h) else []
        if not paths:return messagebox.showinfo('فاکتور','برای این ردیف فاکتوری ثبت نشده است.',parent=self)
        try:os.startfile(str(paths[0])) if os.name=='nt' else subprocess.Popen(['xdg-open',str(paths[0])])
        except (OSError,ValueError) as exc:messagebox.showerror('فاکتور',str(exc),parent=self)
    def _export(self):
        selected=self.export_choice.get();self.export_choice.set(INVENTORY_EXPORT_VALUES_187[0])
        if selected==INVENTORY_EXPORT_VALUES_187[0]:return
        headers,rows=self.table.current_report_rows(selected_only=bool(self.table.selected_rows()))
        show_export_preview_187(self,export_format=selected,headers=headers,rows=rows,title='پیش‌نمایش خروجی مدیریت انبار',table_caption='مدیریت انبار',row_label='ردیف',on_confirm=lambda fmt, orientation, addressee, include_documents: self._save(fmt, headers, rows, orientation, addressee, include_documents),include_addressee=True)
    def _save(self,selected,headers,rows,orientation=None,addressee='سایر',include_documents=True):
        from export_utils import export_pdf,export_xlsx,print_file
        summary=[f'جهت ارائه به: {addressee}']
        suffix='.xlsx' if selected=='Excel' else '.pdf'
        try:
            path=filedialog.asksaveasfilename(parent=self,title=f'خروجی {selected} مدیریت انبار',defaultextension=suffix,filetypes=[('Excel','*.xlsx')] if suffix=='.xlsx' else [('PDF','*.pdf')])
            if not path:return False
            if not include_documents:
                document_columns=[i for i,header in enumerate(headers) if header in {'نمایش سند','فیش واریزی','رسید','سند'}]
                rows=[list(row) for row in rows]
                for row in rows:
                    for index in document_columns:
                        if index < len(row):row[index]='-'
            if selected=='Excel':export_xlsx(Path(path),headers,rows,title='مدیریت انبار',summary_lines=summary)
            else:
                export_pdf(Path(path),headers,rows,title='مدیریت انبار',summary_lines=summary,orientation=orientation)
                if selected=='پرینت':print_file(Path(path))
            messagebox.showinfo('خروجی',f'فایل ساخته شد:\n{path}',parent=self);return True
        except Exception as exc:messagebox.showerror('خروجی',f'خروجی انجام نشد:\n{exc}',parent=self);return False
    def _menu(self,event):
        iid=self.table.tree.identify_row(event.y)
        if iid:
            if iid not in self.table.tree.selection():self.table.tree.selection_set(iid)
            self.table.tree.focus(iid)
        m=tk.Menu(self,tearoff=0)
        for label,cmd in (('افزودن',self.add_row),('ویرایش',self.edit_row),('حذف',self.delete_rows),('کپی',self.copy_row)):m.add_command(label=label,command=cmd)
        m.add_separator()
        for label,fmt in (('PDF','PDF'),('Excel','Excel'),('پرینت','پرینت')):m.add_command(label=label,command=lambda f=fmt:(self.export_choice.set(f),self._export()))
        try:m.tk_popup(event.x_root,event.y_root)
        finally:m.grab_release()
        return 'break'
