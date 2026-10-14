"""Receipt actions on the active full record editor."""
from __future__ import annotations

import asyncio
from pathlib import Path
from queue import Queue, Empty
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageOps

from receipt_evidence187 import (
    clipboard_image, copy_image, is_image_file, replace_image, upload_file, upload_image,
    remove_image, save_evidence,
)


class RecordReceipt187:
    def __init__(self, form, db, approval):
        self.form, self.db, self.approval = form, db, approval
        self.canvas = form.canvas
        self.busy = False
        self._icon_only, self._need, self._zoom = False, None, None
        tools, self.bar = self._layout()
        # On the right of the picture only the three that change it, as icons: the word appears under the pointer.
        from barkav_ui.icon_button import IconButton
        self.edit_buttons = []
        for icon, hint, command in (('rotate_right', 'چرخش به راست', 'rotate_right'),
                                    ('rotate_left', 'چرخش به چپ', 'rotate_left'),
                                    ('crop', 'برش تصویر', 'crop')):
            button = IconButton(tools, icon, hint, lambda value=command: self.image_action(value))
            button.pack(side='top', pady=(0, 4))
            self.edit_buttons.append(button)
        # Everything else is one row under the picture.
        plain, primary = self._compact_style('Toolbar.TButton'), self._compact_style('Primary.TButton')
        self.upload_button = ttk.Button(self.bar, text='بارگذاری رسید/فایل', command=self.upload, style=plain)
        self.process_button = ttk.Button(self.bar, text='پردازش مجدد', command=self.reprocess, style=primary)
        from receipt_gallery187 import ReceiptGallery187
        self.gallery = ReceiptGallery187(self.canvas, self.bar, [], changed=self._document_changed,
                                         compact=True, button_style=plain)
        self._row = ((self.upload_button, 'بارگذاری رسید/فایل', 'upload', 'text_primary'),
                     (self.process_button, 'پردازش مجدد', 'refresh', 'on_accent'),
                     (self.gallery.open_button, 'باز کردن فایل', 'file', 'text_primary'))
        from barkav_ui.window import attach_tooltip
        for column, (button, title, _icon, _ink) in zip((3, 2, 1), self._row):
            button.grid(row=0, column=column, sticky='ew', padx=2)
            self.bar.grid_columnconfigure(column, weight=1, uniform='receipt')
            attach_tooltip(button, lambda value=title: value if self._icon_only else '', delay_ms=300, side='below')
        self._move_zoom_buttons()
        self.bar.bind('<Configure>', self._fit_bar, add='+')
        self.canvas.configure(takefocus=True)
        self.canvas.bind('<Button-1>', lambda _event: self.canvas.focus_set(), add='+')
        self.canvas.bind('<Button-3>', self.image_menu)
        self.canvas.bind('<Control-KeyPress>', self.image_key)
        self.canvas.bind('<Delete>', lambda _event: self.image_action('delete'))
        self.bind_text()

    def _preview_box(self):
        """The framed picture area the options sit beside."""
        return self.canvas.master

    def _layout(self):
        """The tools column on the right of the preview box and the option row under it; both are returned."""
        box = self._preview_box()
        parent = box.master
        if box.winfo_manager() != 'pack':
            tools, bar = tk.Frame(parent), tk.Frame(parent)
            for frame in (tools, bar):
                frame.pack(fill='x', padx=7, pady=3, before=self.form.caption)
            return tools, bar
        info = box.pack_info()
        keep = {key: info[key] for key in ('side', 'fill', 'expand', 'padx', 'pady', 'anchor') if key in info}
        try:
            ground = str(parent.cget('bg'))
        except tk.TclError:
            ground = None
        holder = tk.Frame(parent, **({'bg': ground} if ground else {}))
        holder.pack(before=box, **keep)
        box.pack_configure(in_=holder, side='left', fill='both', expand=True, padx=0, pady=0)
        tk.Misc.lift(box)  # a Canvas.lift would raise canvas items
        tools = tk.Frame(holder, **({'bg': ground} if ground else {}))
        tools.pack(side='right', fill='y', padx=(6, 0), before=box)
        bar = tk.Frame(parent, **({'bg': ground} if ground else {}))
        bar.pack(after=holder, fill='x', padx=keep.get('padx', 7), pady=(3, 2))
        return tools, bar

    def _compact_style(self, base):
        """The button style of the row under the picture: the app's own pill with less padding, so three of
        them and the zoom buttons fit one row."""
        name = f'Receipt.{base}'
        ttk.Style(self.canvas).configure(name, padding=(4, 1))
        return name

    def _move_zoom_buttons(self):
        """The record's zoom buttons (−, Fit, +) join the row, at its left end."""
        try:
            for frame in self._preview_box().master.winfo_children():
                if isinstance(frame, tk.Frame) and any(
                        isinstance(child, tk.Button) and str(child.cget('text')) == 'Fit'
                        for child in frame.winfo_children()):
                    frame.pack_forget()
                    frame.grid(in_=self.bar, row=0, column=0, sticky='w', padx=(0, 4))
                    frame.lift()
                    for child in frame.winfo_children():
                        child.pack_configure(side='left', fill='none', padx=1, pady=0)
                        child.configure(width=3)
                    self._zoom = frame
                    return
        except tk.TclError:
            return

    def _fit_bar(self, _event=None):
        """One row at any width: the words while they fit, an icon for each when the pane is too narrow."""
        width = self.bar.winfo_width()
        if width <= 1:
            return
        if self._need is None:
            widest = max(button.winfo_reqwidth() for button, *_rest in self._row)
            zoom = self._zoom.winfo_reqwidth() if self._zoom is not None else 0
            self._need = widest * len(self._row) + zoom + 8 * (len(self._row) + 2)
        icon_only = width < self._need
        if icon_only != self._icon_only:
            self._icon_only = icon_only
            self._show_row_labels()

    def _show_row_labels(self):
        from barkav_ui.line_icons import icon as line_icon
        from barkav_ui.theme import palette
        p = palette()
        for button, title, icon, ink in self._row:
            if self._icon_only:
                image = line_icon(icon, size=15, colour=p[ink], background=None, weight=1.15, master=self.bar)
                button.configure(text='', image=image, compound='image')
                button._barkav_icon_image187 = image
            else:
                button.configure(text=title, image='', compound='none')

    def bind_text(self):
        text = self.form.caption
        text._barkav_clipboard_action187 = self.text_action
        text._barkav_clipboard_menu187 = self.text_menu
        def key(event):
            command = {65: 'select', 67: 'copy', 86: 'paste', 88: 'cut'}.get(event.keycode)
            return self.text_action(command) if command else None
        text.bind('<Control-KeyPress>', key)
        text.bind('<Control-Insert>', lambda _event: self.text_action('copy'))
        text.bind('<Shift-Insert>', lambda _event: self.text_action('paste'))
        text.bind('<Button-3>', self.text_menu)

    def caption(self):
        return self.form.caption.get('1.0', 'end-1c')

    def refresh_gallery(self):
        from receipt_gallery187 import receipt_paths
        row = dict(self.form.row or {})
        payload = self.form.payload or {}
        if payload.get('_cheque_record_id187'):
            row['cheque_id'] = payload['_cheque_record_id187']
        self.gallery.set_paths(receipt_paths(self.db, self.form.pid, row))

    def _document_changed(self, path):
        target=getattr(self.form,'center',self.form)
        target._image=getattr(self.canvas,'_receipt_source_image187',None)

    def changed(self, row):
        saved = row['payload']
        # Removing a document that is not the record's own receipt image (an attachment, a Telegram photo)
        # leaves the receipt keys untouched, so they may be missing from the saved payload.
        for key, empty in (('receipt_image_path', ''), ('receipt_image_deleted187', False), ('receipt_caption', '')):
            self.form.payload[key] = saved.get(key, empty)
        self.form.row['receipt_image_path'] = saved.get('receipt_image_path', '')
        self.form._load_evidence()
        self.refresh_gallery()
        refresh = getattr(self.form.master, 'refresh', None)
        if refresh:
            refresh()

    def upload(self, path=None):
        if self.busy:
            return
        if not self.form.pid:
            return messagebox.showinfo('رسید تراکنش', 'ابتدا یک تراکنش را انتخاب کنید.', parent=self.form)
        path = path or filedialog.askopenfilename(
            parent=self.form, title='بارگذاری رسید یا فایل برای تراکنش',
            filetypes=[
                ('همهٔ فرمت‌ها', '*.*'),
                ('تصاویر', '*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp'),
                ('PDF', '*.pdf'), ('CAD', '*.dwg *.dxf'),
                ('اسناد و صفحه‌گسترده‌ها', '*.doc *.docx *.xls *.xlsx *.txt *.rtf *.odt *.ods'),
            ],
        )
        if not path:
            return
        try:
            if is_image_file(path):
                self.changed(upload_image(self.db, self.form.pid, path, self.caption()))
            else:
                attachment = upload_file(self.db, self.form.pid, path)
                try:
                    self.form.msg.set(f"فایل «{attachment['file_name']}» به رکورد پیوست شد.")
                except (AttributeError, tk.TclError):
                    pass
                self.refresh_gallery()
        except Exception as exc:
            messagebox.showerror('بارگذاری رسید', str(exc), parent=self.form)

    def edit_image(self, command):
        """Rotate or crop the shown document; the edited picture replaces it, the original stays archived."""
        path = self.gallery.path
        if not path or not is_image_file(path):
            messagebox.showinfo('ویرایش تصویر', 'تصویر رسیدی برای چرخاندن یا برش وجود ندارد.', parent=self.form)
            return 'break'
        try:
            with Image.open(path) as original:
                image = ImageOps.exif_transpose(original).convert('RGB')
            from receipt_image_edit187 import ask_crop, rotated
            if command == 'crop':
                box = ask_crop(self.canvas, image)
                if box is None:
                    return 'break'
                edited = image.crop(box)
            else:
                edited = rotated(image, command)
            saved = replace_image(self.db, self.form.pid, path, edited, self.caption())
            self.changed(saved)
            self.gallery.select(saved['payload'].get('receipt_image_path'))
        except Exception as exc:
            messagebox.showerror('ویرایش تصویر', str(exc), parent=self.form)
        return 'break'

    def download(self):
        """Save a copy of the shown document where the user chooses."""
        path = self.gallery.path
        if not path or not Path(path).is_file():
            messagebox.showinfo('دانلود رسید', 'رسیدی برای دانلود وجود ندارد.', parent=self.form)
            return
        source = Path(path)
        target = filedialog.asksaveasfilename(parent=self.form, title='دانلود رسید', initialfile=source.name,
                                              defaultextension=source.suffix)
        if not target:
            return
        try:
            shutil.copy2(source, target)
            try:
                self.form.msg.set('رسید دانلود شد.')
            except (AttributeError, tk.TclError):
                pass
        except OSError as exc:
            messagebox.showerror('دانلود رسید', str(exc), parent=self.form)

    def image_action(self, command):
        if self.busy:
            return 'break'
        if not self.form.pid:
            return 'break'
        if command in ('rotate_left', 'rotate_right', 'crop'):
            return self.edit_image(command)
        try:
            if command in ('copy', 'cut') and self.form._image is not None:
                copy_image(self.form._image, self.form.winfo_id())
            if command in ('delete', 'cut'):
                self.changed(remove_image(self.db, self.form.pid,
                    self.gallery.path or self.form.row.get('receipt_image_path') or self.form.payload.get('receipt_image_path'), self.caption()))
            elif command == 'paste':
                image = clipboard_image()
                if image is None:
                    messagebox.showinfo('چسباندن رسید', 'ابتدا تصویر رسید را کپی کنید.', parent=self.form)
                else:
                    self.changed(upload_image(self.db, self.form.pid, image, self.caption()))
        except Exception as exc:
            messagebox.showerror('رسید تراکنش', str(exc), parent=self.form)
        return 'break'

    def image_key(self, event):
        command = {67: 'copy', 86: 'paste', 88: 'cut'}.get(event.keycode)
        return self.image_action(command) if command else None

    def image_menu(self, _event=None):
        from barkav_ui.window import PopupMenu
        PopupMenu(self.canvas, [(None, [
            {'label': label, 'command': lambda value=value: self.image_action(value)}
            for label, value in (('کپی رسید', 'copy'), ('برش رسید', 'cut'),
                                 ('چسباندن رسید', 'paste'), ('حذف سند انتخاب‌شده', 'delete'))
        ]), (None, [{'label': label, 'command': lambda value=value: self.image_action(value)}
                    for label, value in (('چرخش به راست', 'rotate_right'), ('چرخش به چپ', 'rotate_left'),
                                         ('برش تصویر', 'crop'))]),
            (None, [{'label': 'دانلود رسید', 'command': self.download},
                    {'label': 'بارگذاری رسید/فایل', 'command': self.upload},
                    {'label': 'پردازش مجدد', 'command': self.reprocess}])], compact=True)
        return 'break'

    def text_action(self, command):
        if command == 'paste' and not self.busy:
            try:
                image = clipboard_image()
            except OSError:
                image = None
            if image is not None:
                try:
                    self.changed(upload_image(self.db, self.form.pid, image, self.caption()))
                except Exception as exc:
                    messagebox.showerror('چسباندن رسید', str(exc), parent=self.form)
                return 'break'
        return self.form.caption._clipboard_action187(command)

    def delete_text(self):
        text = self.form.caption
        if text.tag_ranges('sel'):
            text.delete('sel.first', 'sel.last')
        else:
            text.delete('1.0', 'end')

    def text_menu(self, _event=None):
        from barkav_ui.window import PopupMenu
        PopupMenu(self.form.caption, [(None, [
            {'label': label, 'command': lambda value=value: self.text_action(value)}
            for label, value in (('کپی متن', 'copy'), ('برش متن', 'cut'),
                                 ('چسباندن عکس یا متن', 'paste'), ('انتخاب همه', 'select'))
        ]), (None, [{'label': 'حذف متن', 'command': self.delete_text},
                    {'label': 'بارگذاری رسید/فایل', 'command': self.upload}])], compact=True)
        return 'break'

    def reprocess(self):
        if self.busy:
            return
        row = self.db.get_pending_item(self.form.pid)
        if row['status'] not in {'PENDING_REVIEW', 'NEEDS_REVIEW'}:
            return messagebox.showinfo('پردازش مجدد', 'فقط تراکنش در دست بررسی قابل پردازش است.', parent=self.form)
        draft = self.form.payload_from_form()
        draft['v18_manual_fields'] = sorted(self.form.manual_fields)
        pid = self.form.pid
        with self.db.atomic():
            fresh = self.db.get_pending_item(pid)
            if fresh['status'] not in {'PENDING_REVIEW', 'NEEDS_REVIEW'}:
                return
            self.db.update_pending(pid, payload=draft)
        image = not draft.get('receipt_image_deleted187') and (
            draft.get('receipt_image_path') or self.form._image is not None)
        text = str(draft.get('receipt_caption') or draft.get('description') or '').strip()
        if not image and not text:
            return messagebox.showinfo('پردازش مجدد', 'تصویر رسید یا متن آن را وارد کنید.', parent=self.form)
        self.busy = True
        self.process_button.configure(state='disabled')
        self.upload_button.configure(state='disabled')
        for button in self.edit_buttons:
            button.set_enabled(False)
        controls = list(self.form.widgets.values()) + [self.form.caption, self.form.about_text187,
            self.form._confirm_button_182, self.form._previous_button_182, self.form._next_button_182]
        states = []
        for widget in controls:
            try:
                states.append((widget, widget.cget('state')))
                widget.configure(state='disabled')
            except tk.TclError:
                continue
        self.form.msg.set('در حال پردازش رسید و متن با AI…')
        results = Queue(maxsize=1)

        def worker():
            try:
                operation = (self.approval.analyze_pending_with_ai(pid) if image
                             else self.approval.analyze_pending_text_only(pid, text))
                asyncio.run(operation)
                fresh = self.db.get_pending_item(pid)
                payload = dict(fresh['payload'])
                if not payload.get('event_date_shamsi'):
                    payload['event_date_shamsi'] = draft.get('event_date_shamsi')
                suggestions = {}
                for key in draft['v18_manual_fields']:
                    if key in draft and payload.get(key) != draft[key]:
                        suggestions[key] = payload.get(key)
                        payload[key] = draft[key]
                payload['v18_manual_fields'] = draft['v18_manual_fields']
                if suggestions:
                    payload['v18_reprocess_suggestions'] = suggestions
                self.db.update_pending(pid, payload=payload)
                results.put((self.db.get_pending_item(pid), None))
            except Exception as exc:
                results.put((None, exc))
        threading.Thread(target=worker, daemon=True).start()

        def poll():
            if not self.form.winfo_exists():
                return
            try:
                fresh, error = results.get_nowait()
            except Empty:
                self.form.after(60, poll)
                return
            self.busy = False
            self.process_button.configure(state='normal')
            self.upload_button.configure(state='normal')
            for button in self.edit_buttons:
                button.set_enabled(True)
            for widget, state in states:
                if widget.winfo_exists():
                    widget.configure(state=state)
            if error:
                self.form.msg.set('پردازش انجام نشد.')
                return messagebox.showerror('پردازش مجدد', str(error), parent=self.form)
            self.form._record_drafts187.pop(pid, None)
            self.form._reload_record_182(fresh, self.form._navigation_index_182)
            self.form.msg.set('مقادیر رسید با AI وارد شد؛ برای ثبت مالی «تأیید و ثبت» را بزنید.')
            refresh = getattr(self.form.master, 'refresh', None)
            if refresh:
                refresh()
        self.form.after(60, poll)


class _PreviewRecord:
    """Expose the table preview to the same receipt actions as the record."""
    def __init__(self, center):
        self.center = center
        self.canvas, self.caption = center.preview, center.text
        self.master, self.msg = center, center.action

    @property
    def row(self):
        return self.center.current or {}

    @property
    def pid(self):
        return str(self.row.get('pending_id') or '')

    @property
    def payload(self):
        return self.row.get('payload') or {}

    @property
    def _image(self):
        return self.center._image

    def _load_evidence(self):
        self.center._show(self.row)

    def __getattr__(self, name):
        return getattr(self.center, name)

    def __str__(self):
        return str(self.center)


class DataEntryReceipt187(RecordReceipt187):
    def _preview_box(self):
        return self.canvas

    def __init__(self, center, db, approval):
        super().__init__(_PreviewRecord(center), db, approval)
        self.center = center
        self.last_pid, self.last_caption = None, ''
        center.text._clipboard_action187 = self.plain_text_action
        center.text.bind('<FocusOut>', lambda _event: self.save_caption(), add='+')
        def changed(_event):
            if center.text.edit_modified():
                center.text.tag_add('rtl187', '1.0', 'end')
                center.text.edit_modified(False)
        center.text.bind('<<Modified>>', changed, add='+')

    def plain_text_action(self, command):
        # Use the shared text implementation without redispatching this hook.
        from barkav_ui.clipboard import action
        widget = self.center.text
        custom = widget._barkav_clipboard_action187
        del widget._barkav_clipboard_action187
        try:
            return action(widget, command)
        finally:
            widget._barkav_clipboard_action187 = custom

    def set_row(self, row):
        self.last_pid = str(row.get('pending_id') or '')
        self.last_caption = self.caption()
        self.gallery.index = 0
        self.refresh_gallery()

    def save_caption(self):
        if not self.last_pid:
            return
        caption = self.caption()
        if caption == self.last_caption:
            return
        row = save_evidence(self.db, self.last_pid, {'receipt_caption': caption})
        self.last_caption = caption
        if self.form.pid == self.last_pid:
            self.center.current['payload']['receipt_caption'] = row['payload']['receipt_caption']

    def _history_snapshot(self, pending_id):
        row = self.db.get_pending_item(str(pending_id)) or {}
        payload = dict(row.get('payload') or {})
        deleted = bool(payload.get('receipt_image_deleted187'))
        path = '' if deleted else str(payload.get('receipt_image_path') or '')
        if not path and not deleted and str(pending_id) == self.last_pid:
            path = str(self.center._path(row) or '')
        return {
            'receipt_image_path': path,
            'receipt_image_deleted187': deleted,
            'receipt_caption': str(payload.get('receipt_caption') or ''),
        }

    def _record_image_history(self, pending_id, before):
        after = self._history_snapshot(pending_id)
        if (before.get('receipt_image_path'), before.get('receipt_image_deleted187')) == (
                after.get('receipt_image_path'), after.get('receipt_image_deleted187')):
            return
        push = getattr(self.center, '_push_history', None)
        if callable(push):
            push({
                'kind': 'receipt_image', 'pending_id': str(pending_id),
                'before': before, 'after': after, 'undo_expected': after,
            })

    def upload(self, path=None):
        if not self.busy and self.form.pid:
            self.save_caption()
            pending_id = self.form.pid
            before = self._history_snapshot(pending_id)
            super().upload(path)
            self._record_image_history(pending_id, before)
            return
        return super().upload(path)

    def image_action(self, command):
        if command not in ('cut', 'delete', 'paste', 'rotate_left', 'rotate_right', 'crop') or self.busy \
                or not self.form.pid:
            return super().image_action(command)
        self.save_caption()
        pending_id = self.form.pid
        before = self._history_snapshot(pending_id)
        result = super().image_action(command)
        self._record_image_history(pending_id, before)
        return result

    def reprocess(self):
        self.save_caption()
        return self.center._reprocess_selected_with_choice_187()
