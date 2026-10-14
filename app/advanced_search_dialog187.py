"""RTL advanced-search window using the existing branded export preview."""
from __future__ import annotations
import threading
from queue import Queue, Empty
from pathlib import Path
import tempfile
import os
import logging
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from barkav_ui.window import BarkavWindow
from barkav_ui.clipboard import install as install_clipboard
from barkav_ui.theme import metrics as kit_metrics
from barkav_ui.line_icons import icon
from ui_stage18_7 import palette_187
from ui_stage18_3 import fa
from barkav_ui.bidi import fa_grouped_number, rtl
from ai_section_models187 import AIModelPicker187
from advanced_search187 import AdvancedSearchService187, SCOPES, DATE_BASES, HEADERS, validate_range, requested_period, period_request
from advanced_search_requests187 import REQUEST_TYPES, questions_for
from calendar_report_tables_187 import ReportTable187
from sales_claims_stage18_7 import ShamsiDatePicker187, show_export_preview_187, export_receipts_pdf_187
from export_utils import export_xlsx, print_file
from v18_store import load_ui


class AdvancedSearchDialog187(BarkavWindow):
    size_class = 'large'
    page_size = 100
    def __init__(self, parent, *, service, rich=None, initial_query=''):
        super().__init__(parent, 'جستجوی پیشرفته', subtitle='جستجو در اطلاعات پروژه و درخواست از هوش مصنوعی', show_footer=False)
        self.service, self.rich = service, rich
        self.document_service = rich
        self._ai_section187 = 'management'
        self.search_service = AdvancedSearchService187(service,rich)
        self._running = False
        self.headers, self.rows = list(HEADERS), []
        self.result_metadata = None
        self._queue = Queue()
        self._cancelled = threading.Event()
        self._poll_id = None
        p=palette_187()
        m=kit_metrics();pad=m['outer_pad'];gap=m['gap']
        self.request_type=tk.StringVar(value=REQUEST_TYPES[0])
        self.full_report=tk.BooleanVar(value=False)
        self.show_documents=tk.BooleanVar(value=True)
        mode_bar=ttk.Frame(self.body);mode_bar.pack(fill='x',padx=pad,pady=(gap,0))
        ttk.Label(mode_bar,text='نوع درخواست',anchor='e').pack(side='right',padx=gap)
        self.request_combo=ttk.Combobox(mode_bar,textvariable=self.request_type,values=REQUEST_TYPES,state='readonly',justify='right',width=24)
        self.request_combo.pack(side='right');self.request_combo.bind('<<ComboboxSelected>>',lambda _:self._mode_changed())
        ttk.Checkbutton(mode_bar,text='نمایش سند',variable=self.show_documents,command=self._documents_changed).pack(side='right',padx=gap)
        ttk.Checkbutton(mode_bar,text='گزارش کامل',variable=self.full_report,command=self._full_changed).pack(side='right',padx=gap)
        query_box=self.query_box=tk.Frame(self.body,bg=p['surface'])
        query_box.pack(fill='x',padx=pad,pady=gap)
        query_box.columnconfigure(1,weight=1)
        self.query=tk.StringVar(value=initial_query)
        self.ai=tk.BooleanVar(value=False)
        self.query_caption=ttk.Label(query_box,text=rtl('عبارت جستجو یا پرسش'),anchor='e')
        self.query_caption.grid(row=0,column=1,sticky='e',padx=gap,pady=(0,gap//2))
        entry=self.query_entry=ttk.Entry(query_box,textvariable=self.query,justify='right',width=70)
        entry.grid(row=1,column=1,sticky='ew',padx=gap)
        entry.bind('<Return>',lambda _:self.run())
        self.run_button=ttk.Button(query_box,text='جستجو',command=self.run,style='Primary.TButton')
        self.run_button.grid(row=1,column=0,padx=gap)
        self.bind('<Control-Return>',lambda _:self.run(),add='+')
        self.ai_host=ttk.Frame(self.body)
        for column in range(3):self.ai_host.columnconfigure(column,weight=1)
        ttk.Label(self.ai_host,text='مدل هوش مصنوعی',anchor='e').grid(row=0,column=3,sticky='e',padx=gap)
        self.models=AIModelPicker187(self.ai_host,section='management',base_dir=self.search_service.base_dir)
        self.models.grid(row=0,column=0,columnspan=3,sticky='ew',padx=gap,pady=gap//2)
        self.audience=tk.StringVar(value='کارفرما')
        ttk.Label(self.ai_host,text='جهت ارائه به',anchor='e').grid(row=1,column=3,sticky='e',padx=gap)
        ttk.Combobox(self.ai_host,textvariable=self.audience,values=('کارفرما','مجری','ناظرها'),state='readonly',justify='right',width=12).grid(row=1,column=2,sticky='ew',padx=gap)
        self.detail=tk.StringVar(value='خلاصه')
        details=ttk.Frame(self.ai_host);details.grid(row=1,column=1,sticky='ew',padx=gap)
        ttk.Label(details,text='جزئیات گزارش',anchor='e').pack(side='right',padx=(gap//2,0))
        ttk.Combobox(details,textvariable=self.detail,values=('خلاصه','کامل'),state='readonly',justify='right',width=8).pack(side='right',fill='x',expand=True)
        self.faq_host=ttk.Frame(self.body)
        self.faq_host.columnconfigure(0,weight=1)
        ttk.Label(self.faq_host,text='سؤالات پرتکرار',anchor='e').grid(row=0,column=1,padx=gap)
        self.faq=tk.StringVar()
        self.faq_combo=ttk.Combobox(self.faq_host,textvariable=self.faq,state='readonly',justify='right')
        self.faq_combo.grid(row=0,column=0,sticky='ew',padx=gap)
        self.faq_combo.bind('<<ComboboxSelected>>',lambda _:self._choose_question())
        filters=ttk.Frame(self.body);filters.pack(fill='x',padx=pad,pady=gap)
        self.filters=filters;self.filter_widgets={}
        for column in range(4):filters.columnconfigure(column,weight=1,uniform='search-filter')
        self.scope=tk.StringVar(value='همه');self.date_basis=tk.StringVar(value='همه')
        for column,label,variable,values in [(3,'جستجو در',self.scope,SCOPES),(0,'مبنای تاریخ',self.date_basis,DATE_BASES)]:
            caption=ttk.Label(filters,text=label,anchor='e');caption.grid(row=0,column=column,sticky='e',padx=gap,pady=(0,gap//2))
            combo=ttk.Combobox(filters,textvariable=variable,values=values,state='readonly',justify='right',width=16)
            combo.grid(row=1,column=column,sticky='ew',padx=gap)
            self.filter_widgets[column]=[caption,combo]
            if column==3:
                self.scope_label=caption;self.scope_combo=combo
                combo.bind('<<ComboboxSelected>>',lambda _:self._update_questions())
        self.start=tk.StringVar();self.end=tk.StringVar()
        for column,label,variable in [(2,'از تاریخ',self.start),(1,'تا تاریخ',self.end)]:
            caption=ttk.Label(filters,text=label,anchor='e');caption.grid(row=0,column=column,sticky='e',padx=gap,pady=(0,gap//2))
            cell=ttk.Frame(filters);cell.grid(row=1,column=column,sticky='ew',padx=gap)
            self.filter_widgets[column]=[caption,cell]
            cell.columnconfigure(1,weight=1)
            ttk.Entry(cell,textvariable=variable,justify='right',width=13).grid(row=0,column=1,sticky='ew')
            calendar_icon=icon('calendar',size=18,colour=p['text'],background=None,master=self)
            button=ttk.Button(cell,text='تقویم',image=calendar_icon,compound='image',style='Toolbar.TButton',
                command=lambda v=variable:ShamsiDatePicker187(self,v))
            button._calendar_icon187=calendar_icon
            button.grid(row=0,column=0,padx=(0,gap//2))
        actions=ttk.Frame(self.body);actions.pack(fill='x',padx=12,pady=5)
        self.export_format=tk.StringVar(value='خروجی')
        combo=ttk.Combobox(actions,textvariable=self.export_format,values=('خروجی','PDF','Excel','پرینت'),state='readonly',justify='right',width=12)
        self.export_combo=combo
        combo.pack(side='right');combo.bind('<<ComboboxSelected>>',lambda _:self.preview())
        self.preview_button=ttk.Button(actions,text='پیش‌نمایش',command=lambda:self.preview('PDF'))
        self.preview_button.pack(side='right',padx=5)
        self.period=tk.StringVar(value='روزانه')
        self.period_host=ttk.Frame(filters)
        ttk.Label(self.period_host,text='نوع گزارش',anchor='e').pack(fill='x',pady=(0,gap//2))
        ttk.Combobox(self.period_host,textvariable=self.period,values=('روزانه','هفتگی','ماهانه','مراحل ساخت'),state='readonly',justify='right',width=16).pack(fill='x')
        self.period_ai=tk.BooleanVar(value=False)
        self.period_ai_check=ttk.Checkbutton(actions,text='تهیه با هوش مصنوعی',variable=self.period_ai,command=self._mode_changed)
        self.status=tk.StringVar(value='آمادهٔ جستجو')
        ttk.Label(actions,textvariable=self.status,anchor='e',justify='right').pack(side='right',fill='x',expand=True,padx=8)
        self.progress=ttk.Progressbar(actions,mode='indeterminate',length=100)
        self.progress.pack(side='left',padx=gap)
        self.table_host=ttk.Frame(self.body);self.table_host.pack(fill='both',expand=True,padx=12,pady=8)
        self._display(self.headers,[])
        self._mode_changed()
        install_clipboard(self)
        entry.focus_set()

    def _toggle_ai(self):
        self.request_type.set(REQUEST_TYPES[2] if self.ai.get() else REQUEST_TYPES[0])
        self._mode_changed()

    def _mode_changed(self):
        mode=self.request_type.get();is_ai=mode==REQUEST_TYPES[2];is_report=mode==REQUEST_TYPES[1]
        self.ai.set(is_ai)
        self.query_box.pack_forget();self.faq_host.pack_forget();self.ai_host.pack_forget()
        if not is_report:self.query_box.pack(fill='x',padx=12,pady=5,before=self.filters)
        for column,widgets in self.filter_widgets.items():
            for widget in widgets:
                if (is_ai and column!=3) or (is_report and column in {0,3}):widget.grid_remove()
                else:widget.grid()
        self.scope_label.configure(text='درخواست از' if is_ai else 'جستجو در')
        self.period_host.grid_remove();self.period_ai_check.pack_forget()
        if is_report:
            self.period_host.grid(row=0,column=3,rowspan=2,sticky='ew',padx=8)
            self.period_ai_check.pack(side='right',padx=5)
            # The shared run action remains visible in report mode.
            self.query_box.pack(fill='x',padx=12,pady=3,before=self.filters)
            self.query_entry.grid_remove()
            self.query_caption.grid_remove()
        else:
            self.query_entry.grid()
            self.query_caption.grid()
        if is_ai:
            self.faq_host.pack(fill='x',padx=12,pady=4,after=self.filters)
        if is_ai or (is_report and self.period_ai.get()):
            self.ai_host.pack(fill='x',padx=12,pady=4,after=self.filters)
        self.run_button.configure(text='تهیه گزارش' if is_report else 'دریافت پاسخ' if is_ai else 'جستجو')
        self._update_questions()

    def _update_questions(self):
        self.faq.set('');self.faq_combo.configure(values=questions_for(self.scope.get()))

    def _choose_question(self):
        self.query.set(self.faq.get())
        self.run()

    def _full_changed(self):
        self.detail.set('کامل' if self.full_report.get() else 'خلاصه')
        self._draw_page()

    def _documents_changed(self):
        self._display(self.headers,self.rows)

    def _preview_document(self):
        index=self.document_combo.current()
        if 0<=index<len(self.document_rows):self.preview('PDF',rows_override=[self.document_rows[index]])

    def _display(self, headers, rows):
        self.headers,self.rows=list(headers),list(rows)
        for child in self.table_host.winfo_children():child.destroy()
        self.page=0
        self.page_body=ttk.Frame(self.table_host);self.page_body.pack(fill='both',expand=True)
        self.document_rows=[row for row in rows if row.get('__document_paths_187')]
        if self.show_documents.get() and self.document_rows:
            doc_bar=ttk.Frame(self.table_host);doc_bar.pack(fill='x',pady=4)
            ttk.Label(doc_bar,text='اسناد نتایج',anchor='e').pack(side='right',padx=5)
            self.document_combo=ttk.Combobox(doc_bar,state='readonly',justify='right',
                values=[fa(f"{index}، {str(row.get('شرح') or row.get('شرح گزارش') or row.get('مرجع',''))[:70]}")
                    for index,row in enumerate(self.document_rows,1)])
            self.document_combo.pack(side='right',fill='x',expand=True);self.document_combo.current(0)
            ttk.Button(doc_bar,text='پیش‌نمایش سند',command=self._preview_document).pack(side='right',padx=5)
        self.page_bar=ttk.Frame(self.table_host)
        self.page_status=tk.StringVar()
        self.previous_page=ttk.Button(self.page_bar,text='صفحهٔ قبل',command=lambda:self._page(-1))
        self.previous_page.pack(side='right')
        self.next_page=ttk.Button(self.page_bar,text='صفحهٔ بعد',command=lambda:self._page(1))
        self.next_page.pack(side='right',padx=5)
        ttk.Label(self.page_bar,textvariable=self.page_status,anchor='e').pack(side='right',padx=8)
        if len(self.rows)>self.page_size:self.page_bar.pack(fill='x',pady=5)
        self._draw_page()

    def _page(self, step):
        last=max(0,(len(self.rows)-1)//self.page_size)
        self.page=max(0,min(last,self.page+step));self._draw_page()

    def _draw_page(self):
        for child in self.page_body.winfo_children():child.destroy()
        first=self.page*self.page_size;last=min(len(self.rows),first+self.page_size)
        visible=self.rows[first:last]
        if not self.full_report.get():
            visible=[{key:(value[:400]+'…' if isinstance(value,str) and len(value)>400 and not key.startswith('__') else value)
                for key,value in row.items()} for row in visible]
        table=ReportTable187(self.page_body,self.headers,visible);table.pack(fill='both',expand=True)
        self.previous_page.configure(state='normal' if first else 'disabled')
        self.next_page.configure(state='normal' if last<len(self.rows) else 'disabled')
        self.page_status.set(fa(f'ردیف {first+1} تا {last} از {len(self.rows)}') if self.rows else '')

    def _range(self):
        if self.request_type.get()==REQUEST_TYPES[2]:return requested_period(self.query.get())
        first,last=validate_range(self.start.get(),self.end.get())
        if not first and not last:
            first,last=requested_period(self.query.get())
        if first or last:
            self.start.set(fa(first));self.end.set(fa(last))
        return first,last

    def run(self):
        if self._running:return
        if self.request_type.get()==REQUEST_TYPES[1]:return self.period_report(generate=self.period_ai.get())
        try:first,last=self._range()
        except ValueError as exc:return self._notice(str(exc))
        query=self.query.get().strip()
        if self.ai.get() and not query:return self._notice('پرسش را وارد کنید یا یکی از سؤالات پرتکرار را انتخاب کنید.')
        label=period_request(query) if self.ai.get() else ''
        if label:
            self.period.set(label)
            return self.period_report(generate=True)
        filters=dict(scope=self.scope.get(),start=first,end=last,date_basis=self.date_basis.get())
        try:settings=load_ui();choice=dict(self.models.choice)
        except Exception as exc:
            logging.getLogger(__name__).warning('Search settings unavailable (%s)',type(exc).__name__)
            return self._notice('تنظیمات مدل خوانده نشد؛ تنظیمات را بررسی و دوباره تلاش کنید.')
        use_ai=self.ai.get()
        metadata={'query':query, **filters, 'audience':self.audience.get(), 'documents':self.show_documents.get(),
                  'request_type':self.request_type.get(),'complete':self.full_report.get()}
        self._set_busy(True);self.status.set('در حال بررسی اطلاعات پروژه…')
        def job():
            try:
                if use_ai:model,(headers,rows)=self.search_service.ask_safe(query,**filters,settings=settings,selection=choice,cancelled=self._cancelled.is_set)
                else:
                    records=self.search_service.search(query,**filters)
                    headers,rows=self.search_service.table(records);model=''
                self._queue.put((headers,rows,model,None,metadata))
            except Exception as exc:
                logging.getLogger(__name__).warning('Search job incomplete (%s)',type(exc).__name__)
                self._queue.put(([],[],'','اطلاعات این درخواست خوانده نشد؛ دوباره تلاش کنید.',metadata))
        threading.Thread(target=job,daemon=True).start()
        self._poll_id=self.after(40,self._poll)

    def _set_busy(self, busy):
        self._running=busy
        self.run_button.configure(state='disabled' if busy else 'normal')
        self.export_combo.configure(state='disabled' if busy else 'readonly')
        self.preview_button.configure(state='disabled' if busy else 'normal')
        self.request_combo.configure(state='disabled' if busy else 'readonly')
        self.faq_combo.configure(state='disabled' if busy else 'readonly')
        if busy:
            self.progress.start()
        else:
            self.progress.stop();self.progress.configure(value=0)

    def _poll(self):
        self._poll_id=None
        try:headers,rows,model,error,metadata=self._queue.get_nowait()
        except Empty:
            if self.winfo_exists():self._poll_id=self.after(40,self._poll)
            return
        self._set_busy(False)
        if error:
            self._notice(error);return
        self._display(headers,rows)
        self.result_metadata=metadata
        count=sum(type(row.get('ردیف')) is int for row in rows)
        incomplete=any(row.get('ردیف')=='وضعیت' for row in rows)
        self.status.set(rtl('پاسخ AI تکمیل نشد؛ نتیجهٔ محلی نمایش داده شد' if incomplete else
            f'{fa_grouped_number(count)} ردیف نمایش داده شد'+(f'، {model}' if model else '')))

    def _notice(self, text):
        self.status.set(text)
        self._display(list(HEADERS),[{'ردیف':'وضعیت','شرح':text}])

    def destroy(self):
        if hasattr(self,'_cancelled'):self._cancelled.set()
        if hasattr(self,'progress'):self.progress.stop()
        if getattr(self,'_poll_id',None) is not None:
            self.after_cancel(self._poll_id);self._poll_id=None
        super().destroy()

    def period_report(self, generate=False):
        if self._running:return
        try:
            first,last=self._range()
            label=self.period.get()
            docs=self.show_documents.get();choice=dict(self.models.choice);settings=load_ui()
        except Exception as exc:
            logging.getLogger(__name__).warning('Period report settings unavailable (%s)',type(exc).__name__)
            return self._notice('بازهٔ تاریخ و تنظیمات گزارش را بررسی کنید.')
        metadata={'query':f'گزارش {label}','scope':'مدیریت پروژه' if label=='مراحل ساخت' else 'تقویم',
            'start':first,'end':last,'date_basis':'تاریخ اجرا','audience':self.audience.get(),'documents':docs,
            'request_type':REQUEST_TYPES[1],'complete':self.full_report.get()}
        self._set_busy(True);self.status.set('در حال تهیهٔ گزارش…')
        def job():
            try:
                headers,rows=self.search_service.period_table(label,first,last,documents=docs)
                model='اطلاعات ثبت‌شده'
                if generate:
                    model,(ai_headers,ai_rows)=self.search_service.ask_safe(metadata['query'],
                        scope=metadata['scope'],start=first,end=last,date_basis='تاریخ اجرا',
                        settings=settings,selection=choice,cancelled=self._cancelled.is_set)
                    # Keep deterministic source reports if the provider is unavailable.
                    notices=[row for row in ai_rows if row.get('ردیف')=='وضعیت']
                    if notices:
                        rows.extend({**row,'شرح گزارش':row.get('شرح','')} for row in notices)
                    else:headers,rows=ai_headers,ai_rows
                self._queue.put((headers,rows,model,None,metadata))
            except Exception as exc:
                logging.getLogger(__name__).warning('Period report incomplete (%s)',type(exc).__name__)
                self._queue.put(([],[],'','گزارش خوانده نشد؛ بازه و داده‌های ثبت‌شده را بررسی و دوباره تلاش کنید.',metadata))
        threading.Thread(target=job,daemon=True).start()
        self._poll_id=self.after(40,self._poll)

    def preview(self, selected=None, *, rows_override=None):
        if self._running:return
        selected=selected or self.export_format.get();self.export_format.set('خروجی')
        if selected=='خروجی':return
        if not self.rows:return messagebox.showinfo('خروجی','ابتدا جستجو کنید.',parent=self)
        from financial_calendar_stage18_7 import _project_report_name_187, _project_report_audience_187, _project_report_overall_progress_187
        name=_project_report_name_187(self.service)
        metadata=self.result_metadata or {'query':self.query.get(),'start':self.start.get(),'end':self.end.get(),
            'scope':self.scope.get(),'date_basis':self.date_basis.get(),'audience':self.audience.get(),'documents':self.show_documents.get()}
        audience=_project_report_audience_187(self.service,metadata['audience'])
        title='گزارش جستجوی پیشرفته'
        specs=[('گزارش','عنوان گزارش',metadata['query'] or title),('گزارش','بازهٔ تاریخ',f"{metadata['start']} تا {metadata['end']}"),
               ('گزارش','جستجو در',metadata['scope']),('گزارش','مبنای تاریخ',metadata['date_basis'])]
        headers,rows=list(self.headers),list(self.rows if rows_override is None else rows_override)
        preview_rows=[{key:fa_grouped_number(value) for key,value in row.items()} for row in rows]
        document_paths=list(dict.fromkeys(path for row in rows for path in row.get('__document_paths_187',[])))
        def save(choice, orientation, include_documents=True):
            is_print=choice=='پرینت';extension='.xlsx' if choice=='Excel' else '.pdf'
            if is_print:
                handle,destination=tempfile.mkstemp(suffix='.pdf');os.close(handle)
            else:
                destination=filedialog.asksaveasfilename(parent=self,title='خروجی جستجوی پیشرفته',defaultextension=extension,
                    filetypes=[('Excel','*.xlsx')] if choice=='Excel' else [('PDF','*.pdf')])
                if not destination:return False
            payload=[[row.get(header,'') for header in headers] for row in rows]
            try:
                if choice=='Excel':
                    export_xlsx(destination,headers,payload,title=title,
                        summary_lines=[f'جهت ارائه به: {audience}',*[f'{key}: {value}' for _,key,value in specs]])
                    from openpyxl import load_workbook
                    from sales_claims_stage18_7 import apply_export_workbook_header_187
                    book=load_workbook(destination);sheet=book.active;sheet.insert_rows(1,3)
                    apply_export_workbook_header_187(sheet,headers=headers,specs=[('پروژه','نام پروژه',name)],output_title=title)
                    book.save(destination);book.close()
                else:
                    export_receipts_pdf_187(destination,headers,payload,title,
                        [f'{group} — {key}: {value}' for group,key,value in specs],document_paths if include_documents else [],orientation=orientation,
                        report_project_name=name,report_audience=audience,
                        report_progress=_project_report_overall_progress_187(self.service),blank_missing=True)
                    if is_print:print_file(destination)
                return True
            except Exception as exc:
                messagebox.showerror('خروجی',str(exc),parent=self);return False
        preview=show_export_preview_187(self,export_format=selected,headers=headers,rows=preview_rows,title=title,
            specs=specs,document_paths=document_paths,on_confirm=save,on_confirm_with_documents=True,
            report_project_name=name,report_audience=audience,
            report_progress=_project_report_overall_progress_187(self.service),include_addressee=True)
        if preview is not None and hasattr(preview,'include_documents'):
            preview.include_documents.set(metadata['documents'])
            if not metadata['documents'] and hasattr(preview,'_render'):preview._render()
        return preview
