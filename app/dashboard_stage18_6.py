from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import dashboard_stage18_5 as v185
import dashboard_stage18_4 as v184
import dashboard_stage18_3 as v183
import dashboard_stage18 as v18
from unit_service import UnitService
from v18_store import load_ui, save_profile
from ui_stage18_3 import (
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
from ui_stage18_6 import (
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
        # همهٔ تراکنش‌های در انتظار بررسی زرد روشن‌اند، صرف‌نظر از عنوان -
        # رنگ‌های قبلی (آبی/سبز/بنفش/خاکستری تیره بر اساس عنوان) دقیقاً همان
        # چیزی بود که کاربر «آبی» دید و خواست به جایش زرد روشن باشد.
        colors = {
            'tx183_هزینه_ساخت': ('#F5C842', '#4A3800'),
            'tx183_ورودی': ('#F5C842', '#4A3800'),
            'tx183_خروجی': ('#F5C842', '#4A3800'),
            'tx183_یادداشت': ('#F5C842', '#4A3800'),
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
        self.notebook.bind(
            '<<NotebookTabChanged>>',
            lambda _e: (
                self._sync_nav(),
                v18._maximize(self) if self.state() != 'zoomed' else None,
            ),
            add='+',
        )
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
                # A barkav_ui.table.DataTable already stripes its rows, sizes
                # its columns to its own headings, and decided it wants no
                # grid - see barkav_ui/table.py. Restyling it here undoes that
                # decision, and for the currency pass actively breaks it: it
                # renames a heading like 'مدت پرداخت' to 'مدت پرداخت (تومان)'
                # for containing the word 'پرداخت', after the column was
                # already sized for the shorter, correct one.
                if getattr(getattr(widget, 'tree', None), '_barkav_kit_table_187', False):
                    continue
                if hasattr(widget, 'tree') and hasattr(widget, 'set_rows'):
                    try:
                        retarget_smarttable_186(widget, light=light)
                    except Exception:
                        pass
                if isinstance(widget, ttk.Treeview):
                    if getattr(widget, '_barkav_kit_table_187', False):
                        continue
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
