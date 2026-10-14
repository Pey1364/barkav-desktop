from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import messagebox, ttk
import uuid

from dashboard import PhaseDetailDialog17
from ui import en, fa, parse_int
from ui import palette_187


CATEGORY_LABELS_187 = {
    'MATERIAL': 'مصالح',
    'LABOR': 'دستمزد/اجرا',
    'SERVICE': 'اداری/خدمات',
    'INSTALLATION_GROUP': 'تأسیسات تجمیعی',
}
CATEGORY_CODES_187 = {value: key for key, value in CATEGORY_LABELS_187.items()}


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def install_checkbox_column_187(table) -> None:
    if getattr(table, '_checkbox_column_187', False):
        return
    old_columns = list(table.columns)
    old_keys = [item[0] for item in old_columns]
    check_key = '_check187'
    table.columns = [(check_key, 'انتخاب', 55)] + old_columns
    table.tree.configure(columns=(check_key, *old_keys))
    table.tree.heading(check_key, text='✓', anchor='center')
    table.tree.column(check_key, width=55, minwidth=45, stretch=False, anchor='center')
    for key, label, width in old_columns:
        table.tree.heading(key, text=label, anchor='e')
        table.tree.column(key, width=width, anchor='e')
    table.tree.configure(displaycolumns=tuple(reversed((check_key, *old_keys))))
    original_set_rows = table.set_rows

    def set_rows_with_check(rows, renderer):
        return original_set_rows(rows, lambda row: ['☐', *renderer(row)])

    table.set_rows = set_rows_with_check

    def sync_checks(_event=None):
        selected = set(table.tree.selection())
        for item in table.tree.get_children(''):
            values = list(table.tree.item(item, 'values') or ())
            if values:
                values[0] = '☑' if item in selected else '☐'
                table.tree.item(item, values=values)

    table.tree.bind('<<TreeviewSelect>>', sync_checks, add='+')
    table._checkbox_column_187 = True


class PhaseDetailDialog187(PhaseDetailDialog17):
    """Existing phase detail with an explicit phase selector and left/right navigation."""

    def __init__(self, parent, rich, phase_no: int, phase_name: str, on_refresh):
        self.dashboard = parent
        super().__init__(parent, rich, phase_no, phase_name, on_refresh)
        self.title(f'ریز فاز {phase_no:02d} — {phase_name} — BARKAV 18.7')
        self._install_phase_navigation()

    def _install_phase_navigation(self):
        try:
            head = self.winfo_children()[0]
        except Exception:
            return
        p = palette_187()
        rows = list(self.dashboard._phase_summary_live())
        values = [f"{int(row['phase_no']):02d} — {row['phase']}" for row in rows]
        self.phase_selector187 = tk.StringVar(value=f'{self.phase_no:02d} — {self.phase_name}')
        ttk.Combobox(
            head, textvariable=self.phase_selector187, values=values,
            state='readonly', justify='right', width=34,
        ).pack(side='right', padx=6, pady=6)
        selector = head.winfo_children()[-1]
        selector.bind('<<ComboboxSelected>>', lambda _event: self._open_selected(), add='+')
        tk.Button(head, text='← فاز بعد', command=lambda: self._move(1),
                  bg=p['glass'], fg=p['text'], relief='flat', padx=10, pady=5).pack(side='left', padx=3)
        tk.Button(head, text='فاز قبل →', command=lambda: self._move(-1),
                  bg=p['glass'], fg=p['text'], relief='flat', padx=10, pady=5).pack(side='left', padx=3)

    def _open_selected(self):
        try:
            number = int(en(self.phase_selector187.get()).split('—', 1)[0].strip())
        except Exception:
            return
        self.destroy()
        self.dashboard.open_phase_by_no(number)

    def _move(self, delta: int):
        number = max(1, min(32, self.phase_no + int(delta)))
        if number == self.phase_no:
            return
        self.destroy()
        self.dashboard.open_phase_by_no(number)


class PriceEditor187(tk.Toplevel):
    def __init__(self, parent, rich, row: dict | None, on_done):
        super().__init__(parent)
        self.rich = rich
        self.row = dict(row or {})
        self.on_done = on_done
        self.title('ویرایش قیمت' if row else 'افزودن قیمت')
        self.geometry('620x570')
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        p = palette_187()
        self.configure(bg=p['bg'])
        body = tk.Frame(self, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
        body.pack(fill='both', expand=True, padx=12, pady=12)
        labels = [
            ('category', 'گروه قیمت'), ('code', 'کد'), ('description', 'شرح'), ('unit', 'واحد'),
            ('estimate_rate', 'قیمت برآورد'), ('actual_rate', 'قیمت واقعی مرجع'),
            ('forecast_rate', 'قیمت پیش‌بینی'), ('source', 'منبع'),
        ]
        self.vars = {}
        for index, (key, label) in enumerate(labels):
            tk.Label(body, text=label, bg=p['panel'], fg=p['text'], anchor='e',
                     font=('Segoe UI', 9, 'bold')).grid(row=index, column=1, sticky='e', padx=8, pady=7)
            value = CATEGORY_LABELS_187.get(self.row.get(key), self.row.get(key, ''))
            variable = tk.StringVar(value=str(value or ''))
            self.vars[key] = variable
            if key == 'category':
                widget = ttk.Combobox(
                    body, textvariable=variable,
                    values=('مصالح', 'دستمزد/اجرا', 'اداری/خدمات'),
                    state='readonly', justify='right', width=38,
                )
                if not variable.get():
                    variable.set('مصالح')
            else:
                widget = ttk.Entry(body, textvariable=variable, justify='right', width=40)
            widget.grid(row=index, column=0, sticky='ew', padx=8, pady=7)
        body.grid_columnconfigure(0, weight=1)
        tk.Button(body, text='ذخیره', command=self.save, bg=p['blue'], fg='#FFFFFF',
                  relief='flat', padx=18, pady=8, font=('Segoe UI', 10, 'bold')).grid(
                      row=len(labels), column=0, columnspan=2, pady=14
                  )

    def save(self):
        try:
            data = {key: value.get().strip() for key, value in self.vars.items()}
            category = CATEGORY_CODES_187.get(data['category'])
            if not category:
                raise ValueError('گروه قیمت را انتخاب کنید.')
            if not data['description']:
                raise ValueError('شرح قیمت الزامی است.')
            rates = {key: max(0, parse_int(data[key])) for key in (
                'estimate_rate', 'actual_rate', 'forecast_rate',
            )}
            now = _now()
            if self.row:
                price_id = str(self.row['price_id'])
                before = self.rich.get_price(price_id) or {}
                with self.rich.db.tx() as connection:
                    connection.execute(
                        """UPDATE rich_price_items SET category=?,code=?,description=?,unit=?,
                           estimate_rate=?,actual_rate=?,forecast_rate=?,source=?,updated_at=? WHERE price_id=?""",
                        (category, data['code'], data['description'], data['unit'],
                         rates['estimate_rate'], rates['actual_rate'], rates['forecast_rate'],
                         data['source'] or 'GUI_18_7', now, price_id),
                    )
                try:
                    self.rich._log('PRICE', price_id, 'UPDATE_18_7', before, self.rich.get_price(price_id) or {})
                except Exception:
                    pass
            else:
                price_id = 'PPRICE_' + uuid.uuid4().hex[:18].upper()
                with self.rich.db.tx() as connection:
                    connection.execute(
                        """INSERT INTO rich_price_items(
                           price_id,code,description,category,unit,estimate_rate,actual_rate,
                           forecast_rate,status,source,visible,aggregate,group_key,active,created_at,updated_at
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
                        (price_id, data['code'], data['description'], category, data['unit'],
                         rates['estimate_rate'], rates['actual_rate'], rates['forecast_rate'],
                         'MANUAL', data['source'] or 'GUI_18_7', 1, 0, '', now, now),
                    )
                try:
                    self.rich._log('PRICE', price_id, 'CREATE_18_7', {}, self.rich.get_price(price_id) or {})
                except Exception:
                    pass
            self.destroy()
            self.on_done()
        except Exception as exc:
            messagebox.showerror('قیمت', str(exc), parent=self)


class PriceCatalogDialog187(tk.Toplevel):
    def __init__(self, parent, rich, on_refresh):
        super().__init__(parent)
        self.rich = rich
        self.on_refresh = on_refresh
        self.title('مدیریت کامل قیمت‌ها — BARKAV 18.7')
        self.geometry('1050x680')
        self.minsize(820, 540)
        self.transient(parent)
        p = palette_187()
        self.configure(bg=p['bg'])
        bar = tk.Frame(self, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
        bar.pack(fill='x', padx=10, pady=10)
        self.category = tk.StringVar(value='همه')
        ttk.Combobox(bar, textvariable=self.category,
                     values=('همه', 'مصالح', 'دستمزد/اجرا', 'اداری/خدمات'),
                     state='readonly', justify='right', width=20).pack(side='right', padx=7, pady=7)
        self.category.trace_add('write', lambda *_: self.refresh())
        tk.Button(bar, text='افزودن قیمت', command=self.add, bg=p['green'], fg='#FFFFFF',
                  relief='flat', padx=13, pady=7).pack(side='left', padx=4)
        tk.Button(bar, text='ویرایش', command=self.edit, bg=p['blue'], fg='#FFFFFF',
                  relief='flat', padx=13, pady=7).pack(side='left', padx=4)
        tk.Button(bar, text='حذف', command=self.delete, bg=p['red'], fg='#FFFFFF',
                  relief='flat', padx=13, pady=7).pack(side='left', padx=4)
        self.tree = ttk.Treeview(
            self, columns=('category', 'code', 'description', 'unit', 'estimate', 'actual', 'forecast', 'source'),
            show='headings', selectmode='browse',
        )
        specs = [
            ('category', 'گروه', 135), ('code', 'کد', 90), ('description', 'شرح', 280),
            ('unit', 'واحد', 80), ('estimate', 'برآورد', 125), ('actual', 'واقعی', 125),
            ('forecast', 'پیش‌بینی', 125), ('source', 'منبع', 130),
        ]
        for key, label, width in specs:
            self.tree.heading(key, text=label, anchor='e')
            self.tree.column(key, width=width, anchor='e')
        self.tree.configure(displaycolumns=tuple(reversed([item[0] for item in specs])))
        self.tree.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        self.tree.bind('<Double-1>', lambda _event: self.edit(), add='+')
        self.rows = []
        self.refresh()

    def refresh(self):
        wanted = CATEGORY_CODES_187.get(self.category.get())
        rows = list(self.rich.list_prices(category=wanted, visible_only=True))
        if self.category.get() in CATEGORY_CODES_187:
            rows = [row for row in rows if row.get('category') == wanted]
        elif self.category.get() == 'همه':
            rows = [row for row in rows if row.get('category') in {'MATERIAL', 'LABOR', 'SERVICE'}]
        self.rows = rows
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, row in enumerate(rows):
            self.tree.insert('', 'end', iid=str(index), values=(
                CATEGORY_LABELS_187.get(row.get('category'), row.get('category')),
                row.get('code') or '-', row.get('description') or '-', row.get('unit') or '-',
                fa(f"{int(row.get('estimate_rate') or 0):,}"),
                fa(f"{int(row.get('actual_rate') or 0):,}"),
                fa(f"{int(row.get('forecast_rate') or 0):,}"), row.get('source') or '-',
            ))

    def one(self):
        selected = self.tree.selection()
        if not selected:
            return None
        return self.rows[int(selected[0])]

    def add(self):
        PriceEditor187(self, self.rich, None, self._done)

    def edit(self):
        row = self.one()
        if row:
            PriceEditor187(self, self.rich, row, self._done)

    def delete(self):
        row = self.one()
        if not row:
            return
        if not messagebox.askyesno('حذف قیمت', f"«{row.get('description')}» از فهرست فعال حذف شود؟", parent=self):
            return
        before = dict(row)
        with self.rich.db.tx() as connection:
            connection.execute('UPDATE rich_price_items SET active=0,updated_at=? WHERE price_id=?',
                               (_now(), row['price_id']))
        try:
            self.rich._log('PRICE', row['price_id'], 'DELETE_18_7', before, {'active': 0})
        except Exception:
            pass
        self._done()

    def _done(self):
        self.refresh()
        self.on_refresh()


def _selected_one(table):
    rows = table.selected_rows()
    return rows[0] if rows else None


def _soft_delete_price(app, row):
    if not row:
        return
    if not messagebox.askyesno('حذف قیمت', f"«{row.get('description')}» حذف شود؟", parent=app):
        return
    before = dict(row)
    with app.rich.db.tx() as connection:
        connection.execute('UPDATE rich_price_items SET active=0,updated_at=? WHERE price_id=?',
                           (_now(), row['price_id']))
    try:
        app.rich._log('PRICE', row['price_id'], 'DELETE_18_7', before, {'active': 0})
    except Exception:
        pass
    app.refresh_reports()


def _price_context_menu(app, event):
    tree = app.price_table.tree
    item = tree.identify_row(event.y)
    if item:
        tree.selection_set(item)
        tree.focus(item)
    menu = tk.Menu(tree, tearoff=0)
    menu.add_command(label='➕ افزودن قیمت', command=lambda: PriceEditor187(app, app.rich, None, app.refresh_reports))
    menu.add_command(label='✏️ ویرایش قیمت', command=lambda: PriceEditor187(
        app, app.rich, _selected_one(app.price_table), app.refresh_reports
    ) if _selected_one(app.price_table) else None)
    menu.add_command(label='🗑 حذف قیمت', command=lambda: _soft_delete_price(app, _selected_one(app.price_table)))
    menu.add_separator()
    menu.add_command(label='📋 کپی', command=app.price_table.copy_selected)
    menu.add_command(label='📌 پیست در فیلتر', command=app.price_table.paste_filter)
    menu.add_command(label='مدیریت کامل قیمت‌ها', command=lambda: PriceCatalogDialog187(app, app.rich, app.refresh_reports))
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def open_estimate_file_187(app):
    version = app.SERVICE.budget.latest_version() if hasattr(app, 'SERVICE') else None
    if version is None:
        try:
            version = app._barkav_service_187.budget.latest_version()
        except Exception:
            version = None
    path = Path(str((version or {}).get('source_file') or app._barkav_base_187 / 'phase_budget_current.xlsx'))
    if not path.is_file():
        messagebox.showwarning('فایل برآورد', 'فایل منبع آخرین برآورد پیدا نشد.', parent=app)
        return
    try:
        modified = path.stat().st_mtime_ns
        os.startfile(str(path))
        app._estimate_watch_187 = {'path': path, 'mtime': modified, 'active': False}
        app.after(1800, lambda: app._estimate_watch_187.update(active=True))
    except Exception as exc:
        messagebox.showerror('فایل برآورد', str(exc), parent=app)


def check_estimate_file_187(app, _event=None):
    watch = getattr(app, '_estimate_watch_187', None)
    if not watch or not watch.get('active'):
        return
    path = Path(watch['path'])
    try:
        modified = path.stat().st_mtime_ns
    except Exception:
        return
    if modified == watch.get('mtime'):
        return
    watch['active'] = False
    watch['mtime'] = modified
    if not messagebox.askyesno(
        'بروزرسانی برآورد',
        'فایل اکسل تغییر کرده است. تغییرات به‌عنوان نسخهٔ جدید برآورد وارد شوند؟',
        parent=app,
    ):
        return
    try:
        title = 'ویرایش فایل برآورد — ' + datetime.now().strftime('%Y-%m-%d %H:%M')
        app._barkav_service_187.budget.import_budget_xlsx(path, title)
        rich_result = app.rich.import_workbook(path, title, preserve_manual=True)
        app._barkav_apply_phase04_187(app.rich)
        destination = app._barkav_base_187 / 'phase_budget_current.xlsx'
        if path.resolve() != destination.resolve():
            shutil.copy2(path, destination)
        app.refresh_reports()
        messagebox.showinfo(
            'بروزرسانی برآورد',
            f'نسخهٔ جدید ثبت شد؛ {fa(rich_result.phase_count)} فاز بروزرسانی شد.',
            parent=app,
        )
    except Exception as exc:
        messagebox.showerror('بروزرسانی برآورد', str(exc), parent=app)


def install_report_controls_187(app) -> None:
    if getattr(app, '_report_controls_installed_187', False):
        return
    app._report_controls_installed_187 = True
    install_checkbox_column_187(app.price_table)
    install_checkbox_column_187(app.phase_table)
    p = palette_187()

    price_top = app.price_table.winfo_children()[0]
    app.price_category187 = tk.StringVar(value='همه')
    ttk.Combobox(
        price_top, textvariable=app.price_category187,
        values=('همه', 'مصالح', 'دستمزد/اجرا', 'اداری/خدمات'),
        state='readonly', justify='right', width=18,
    ).pack(side='right', padx=4)
    tk.Button(
        price_top, text='مدیریت کامل قیمت‌ها',
        command=lambda: PriceCatalogDialog187(app, app.rich, app.refresh_reports),
        bg=p['blue'], fg='#FFFFFF', relief='flat', padx=9, pady=4,
    ).pack(side='right', padx=4)

    def filter_price(*_args):
        value = app.price_category187.get()
        search = {'همه': '', 'مصالح': 'مصالح', 'دستمزد/اجرا': 'اجرت/اجرا', 'اداری/خدمات': 'خدمات'}[value]
        app.price_table.quick.set(search)
        app.price_table.apply_filter()

    app.price_category187.trace_add('write', filter_price)

    price_bottom = tk.Frame(app.price_table.master, bg=p['panel'])
    price_bottom.pack(side='bottom', fill='x', padx=4, pady=4)
    for text, command, color in [
        ('حذف', lambda: _soft_delete_price(app, _selected_one(app.price_table)), p['red']),
        ('کپی', app.price_table.copy_selected, p['yellow']),
        ('پیست', app.price_table.paste_filter, p['blue']),
        ('افزودن', lambda: PriceEditor187(app, app.rich, None, app.refresh_reports), p['green']),
    ]:
        tk.Button(price_bottom, text=text, command=command, bg=color,
                  fg='#FFFFFF' if text != 'کپی' else '#171A1F', relief='flat',
                  padx=14, pady=6).pack(side='right', padx=3)

    phase_bottom = tk.Frame(app.phase_table.master, bg=p['panel'])
    phase_bottom.pack(side='bottom', fill='x', padx=4, pady=4)
    for text, command, color in [
        ('حذف ریز', lambda: app.open_phase_by_no(int((_selected_one(app.phase_table) or {'phase_no': 1})['phase_no'])), p['red']),
        ('کپی', app.phase_table.copy_selected, p['yellow']),
        ('پیست در فیلتر', app.phase_table.paste_filter, p['blue']),
        ('افزودن ریز', lambda: app.open_phase_by_no(int((_selected_one(app.phase_table) or {'phase_no': 1})['phase_no'])), p['green']),
    ]:
        tk.Button(phase_bottom, text=text, command=command, bg=color,
                  fg='#FFFFFF' if text != 'کپی' else '#171A1F', relief='flat',
                  padx=12, pady=6).pack(side='right', padx=3)

    app.price_table.tree.unbind('<Button-3>')
    app.price_table.tree.bind('<Button-3>', lambda event: _price_context_menu(app, event))

    phase_root = app.report_nb.master
    top = phase_root.winfo_children()[0]
    tk.Button(
        top, text='باز کردن فایل برآورد', command=lambda: open_estimate_file_187(app),
        bg=p['glass'], fg=p['text'], relief='flat', padx=12, pady=7,
    ).pack(side='left', padx=5, pady=5)
    app.bind('<FocusIn>', lambda event: check_estimate_file_187(app, event), add='+')
