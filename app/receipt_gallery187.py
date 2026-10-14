"""Shared attachment collection and paged document preview."""
from pathlib import Path
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageOps, ImageTk

from barkav_ui.bidi import fa_grouped_number, rtl


def receipt_paths(db, pending_id='', row=None):
    row = dict(row or {})
    entities = []
    ids = [str(pending_id)] if pending_id else []
    for key, kind in (('cheque_id','CHEQUE'),('expense_id','EXPENSE'),
                      ('transaction_id','TRANSACTION'),('loan_id','LOAN'),('document_id','DOCUMENT')):
        if row.get(key):
            entities.append((kind,str(row[key])))
    for pid in tuple(ids):
        item = db.get_pending_item(pid) or {}
        if item:
            message=db.get_telegram_message(item['telegram_chat_id'],item['telegram_message_id']) or {}
            if message.get('linked_entity_id'):
                entities.append((str(message['linked_entity_type']).upper(),str(message['linked_entity_id'])))
        payload=item.get('payload') or {}
        for key,kind in (('cheque_id','CHEQUE'),('selected_cheque_id187','CHEQUE')):
            if payload.get(key):entities.append((kind,str(payload[key])))
    with db.read() as con:
        for kind, ident in tuple(entities):
            ids += [str(r['pending_id']) for r in con.execute(
                "SELECT p.pending_id FROM pending_items p JOIN telegram_messages m "
                "ON p.telegram_chat_id=m.chat_id AND p.telegram_message_id=m.message_id "
                "WHERE m.linked_entity_type=? AND m.linked_entity_id=?",(kind,ident))]
        for key in ('transaction_id','expense_id','cheque_id'):
            if row.get(key):
                ids += [str(r['pending_id']) for r in con.execute(
                    f'SELECT pending_id FROM financial_postings WHERE {key}=?',(row[key],))]
    # a cheque's record shows the receipts of all its records, the issue's and every resolution's
    if any(kind=='CHEQUE' for kind,_ in entities):
        from cheque_documents187 import cheque_sources
        more_ids,more_entities=cheque_sources(db,pending_id,row)
        ids+=more_ids
        entities+=more_entities
    paths=[]
    def add(path):
        path=str(path or '')
        if path and Path(path).is_file() and path not in paths:paths.append(path)
    for pid in dict.fromkeys(ids):
        for attachment in db.list_pending_attachments(pid):add(attachment.get('local_path'))
        item=db.get_pending_item(pid) or {}
        payload=item.get('payload') or {}
        if not payload.get('receipt_image_deleted187'):add(payload.get('receipt_image_path'))
    for kind,ident in dict.fromkeys(entities):
        for attachment in db.list_entity_attachments(kind,ident):add(attachment.get('local_path'))
    for key in ('receipt_path','local_path','attachment_path','document_path'):add(row.get(key))
    if any(kind=='CHEQUE' for kind,_ in entities):
        from cheque_documents187 import order_by_record
        paths=order_by_record(db,pending_id,row,paths)
    return paths


def render_document(canvas, path):
    canvas.delete('all')
    try:
        if Path(path).suffix.lower()=='.pdf':
            import pypdfium2
            pdf=pypdfium2.PdfDocument(path)
            try:
                page=pdf[0]
                try:
                    bitmap=page.render(scale=1.5)
                    try:image=bitmap.to_pil().copy()
                    finally:bitmap.close()
                finally:page.close()
            finally:pdf.close()
        else:
            with Image.open(path) as original:image=ImageOps.exif_transpose(original).convert('RGB')
        canvas._receipt_source_image187=image.copy()
        canvas.update_idletasks()
        image.thumbnail((max(200,canvas.winfo_width()-20),max(200,canvas.winfo_height()-20)))
        canvas._receipt_photo187=ImageTk.PhotoImage(image,master=canvas)
        canvas.create_image(10,10,image=canvas._receipt_photo187,anchor='nw')
    except Exception:
        canvas._receipt_photo187=None
        canvas._receipt_source_image187=None
        canvas.create_text(20,40,text=rtl(Path(path).name),anchor='nw',
                           fill=ttk.Style(canvas).lookup('TLabel','foreground') or 'black')


class ReceiptGallery187:
    """The documents of one record, one at a time on ``canvas``.

    Default: a strip of controls in ``bar`` (the receipts window). ``compact``: the two arrows sit on the left and
    right edges of the canvas, with a small «۲ از ۳» badge at its foot, and only appear when there is more than one
    document; «باز کردن فایل» is made in ``bar`` for its owner to place."""

    def __init__(self, canvas, bar, paths, *, changed=None, compact=False, button_style='TButton'):
        self.canvas,self.paths,self.index,self.changed=canvas,[],0,changed
        self.compact=compact
        self.count=tk.StringVar(canvas)
        if compact:
            self._build_compact(bar,button_style)
        else:
            controls=ttk.Frame(bar)
            self.open_button=ttk.Button(controls,text='باز کردن فایل',command=self.open_current)
            self.next=ttk.Button(controls,text='←',command=lambda:self.move(1))
            counter=ttk.Label(controls,textvariable=self.count,anchor='center')
            self.previous=ttk.Button(controls,text='→',command=lambda:self.move(-1))
            controls.pack(fill='x',expand=True,side='left')
            controls.grid_columnconfigure(2,weight=1)
            self.open_button.grid(row=0,column=0,sticky='w',padx=3)
            self.next.grid(row=0,column=1,sticky='w',padx=3)
            counter.grid(row=0,column=2,sticky='ew',padx=4)
            self.previous.grid(row=0,column=3,sticky='e',padx=3)
        self.set_paths(paths)

    def _build_compact(self, bar, button_style):
        from barkav_ui.icon_button import IconButton
        from barkav_ui.theme import palette
        from barkav_themes.tokens import mix
        self.open_button=ttk.Button(bar,text='باز کردن فایل',style=button_style,command=self.open_current)
        parent=self.canvas.master
        ground=str(self.canvas.cget('bg'))
        shape=dict(size=18,box=30,radius=8,hint_side='below',ground=ground)
        # ← is the next document and → the previous one, as the page arrows of right-to-left text
        self.next=IconButton(parent,'chevron_left','سند بعدی',lambda:self.move(1),**shape)
        self.previous=IconButton(parent,'chevron_right','سند قبلی',lambda:self.move(-1),**shape)
        p=palette()
        self.badge_text=tk.StringVar(self.canvas)
        self.badge=tk.Label(parent,textvariable=self.badge_text,bg=mix(ground,p['text_primary'],0.16),
                            fg=p['text_primary'],padx=8,pady=1,bd=0)

    def _place_compact(self, several):
        edges=((self.next,0.0,'w',6),(self.previous,1.0,'e',-6))
        for button,relx,anchor,x in edges:
            if several:
                button.place(in_=self.canvas,relx=relx,rely=0.5,anchor=anchor,x=x)
                button.lift()
            else:
                button.place_forget()
        if several:
            self.badge.place(in_=self.canvas,relx=0.5,rely=1.0,anchor='s',y=-8)
            self.badge.lift()
        else:
            self.badge.place_forget()

    def set_paths(self, paths):
        self.paths=list(paths)
        self.index=min(self.index,max(0,len(self.paths)-1))
        self.show()

    @property
    def path(self):
        return self.paths[self.index] if self.paths else ''

    def select(self, path):
        """Show the given document when the collection holds it."""
        if path in self.paths:
            self.index=self.paths.index(path)
            self.show()

    def move(self, offset):
        if len(self.paths)>1:
            self.index=(self.index+offset)%len(self.paths)
            self.show()

    def open_current(self):
        if not self.path:
            return
        try:
            if os.name=='nt':
                os.startfile(self.path)
            elif sys.platform=='darwin':
                subprocess.Popen(['open',self.path])
            else:
                subprocess.Popen(['xdg-open',self.path])
        except (OSError,AttributeError) as exc:
            messagebox.showerror('باز کردن فایل',f'فایل باز نشد: {exc}',parent=self.canvas.winfo_toplevel())

    def show(self):
        self.count.set(f'تعداد اسناد: {fa_grouped_number(len(self.paths))} — {fa_grouped_number(self.index+1 if self.paths else 0)}')
        several=len(self.paths)>1
        state='normal' if several else 'disabled'
        if self.compact:
            self.badge_text.set(rtl(f'{fa_grouped_number(self.index+1)} از {fa_grouped_number(len(self.paths))}'))
            self.previous.set_enabled(several)
            self.next.set_enabled(several)
            self._place_compact(several)
        else:
            self.previous.configure(state=state)
            self.next.configure(state=state)
        self.open_button.configure(state='normal' if self.paths else 'disabled')
        if self.path:
            render_document(self.canvas,self.path)
            if self.changed:self.changed(self.path)


def show_receipts(parent, paths):
    from barkav_ui.window import BarkavWindow
    window=BarkavWindow(parent,'رسیدهای تراکنش',size_class='large',show_footer=False)
    bar=ttk.Frame(window.body);bar.pack(fill='x')
    canvas=tk.Canvas(window.body,highlightthickness=0)
    canvas.pack(fill='both',expand=True)
    window.gallery187=ReceiptGallery187(canvas,bar,paths)
    return window
