from __future__ import annotations

import json
import tempfile
import threading
import zipfile
from copy import deepcopy
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import dashboard_stage18_4 as v184
import dashboard_stage18_3 as v183
import dashboard_stage18_2 as v182
import dashboard_stage18 as v18
from unit_service import UnitService
from telegram_history_import import import_telegram_export
from v18_store import load_profile, save_profile, load_ui, save_ui
from ui_stage18_3 import (
    RtlNotebookStrip, fa, en, parse_int, parse_decimal, group_int_fa,
    group_decimal_fa, bind_grouped_number_fa, bind_grouped_decimal_fa,
    fetch_tgju_usd_toman,
)
from ui_stage18_4 import retarget_smarttable_instance_184
from ui_stage18_5 import (
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
            'tx183_هزینه_ساخت': ('#F5C842', '#4A3800'),
            'tx183_ورودی': ('#F5C842', '#4A3800'),
            'tx183_خروجی': ('#F5C842', '#4A3800'),
            'tx183_یادداشت': ('#F5C842', '#4A3800'),
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
        tk.Label(toolbar, text='خروجی تب فعال', bg=p['surface'], fg=p['muted'], font=('Segoe UI', 10, 'bold')).pack(side='right', padx=8)
        self.output_var = tk.StringVar(value='انتخاب فرمت خروجی')
        output = ttk.Combobox(toolbar, textvariable=self.output_var, state='readonly',
                              values=['انتخاب فرمت خروجی', 'پرینت', 'Excel', 'PDF'], width=21, justify='right')
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
