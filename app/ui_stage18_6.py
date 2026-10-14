from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from ui_stage18_3 import en, fa, parse_int
from ui_stage18_5 import (
    TreeGridOverlay185,
    bind_persian_digits,
    floor_name_185,
    normalize_floor_structure,
)


DARK_186 = {
    'bg': '#091423',
    'surface': '#0D192A',
    'panel': '#111F33',
    'panel2': '#17283F',
    'glass': '#132238',
    'line': '#22344B',
    'text': '#F1F5FA',
    'muted': '#96A4B7',
    'blue': '#2F78EE',
    'green': '#43BE82',
    'orange': '#E4A34C',
    'red': '#DE6671',
    'cyan': '#58A8F8',
    'violet': '#9A83E7',
    'yellow': '#E7C158',
}

LIGHT_186 = {
    'bg': '#F5F7FA',
    'surface': '#FFFFFF',
    'panel': '#FFFFFF',
    'panel2': '#F2F5F9',
    'glass': '#F7F9FC',
    'line': '#E1E7EE',
    'text': '#1B2738',
    'muted': '#6B788A',
    'blue': '#2D72DE',
    'green': '#27855E',
    'orange': '#B87317',
    'red': '#C34F5B',
    'cyan': '#2479D0',
    'violet': '#7057BE',
    'yellow': '#A97B13',
}

ROOF_LEVEL_186 = 10_000
CURRENCY_UNITS = ('تومان', 'ریال', 'دلار')
MONEY_HEADING_WORDS = (
    'مبلغ', 'هزینه', 'قیمت', 'پرداخت', 'وصول', 'مانده', 'بدهی', 'مطالبات',
    'طلب', 'قرارداد', 'برآورد', 'واقعی', 'پیش‌بینی', 'انحراف', 'درآمد',
    'ورودی', 'خروجی', 'فروش', 'خرید', 'تزریق', 'اصل تسهیلات', 'اقساط',
    'تأمین مالی', 'حقوق مدیر', 'برداشت', 'تمام‌شده',
)

# Checked first: these name a quantity, a proportion or a count, so no
# currency belongs after them however the rest of the heading reads.
NON_MONEY_HEADING_WORDS = (
    'مقدار', 'حجم', 'تعداد', 'متراژ', 'درصد', 'ضریب', 'واحد اندازه',
)


def palette_186(light: bool = False) -> dict[str, str]:
    return dict(LIGHT_186 if light else DARK_186)


def normalize_floor_structure_186(
    total: Any,
    parking_count: Any,
    negative_count: Any,
    existing: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build ordinary floors bottom-up and keep one permanent roof storage row."""
    rows = list(existing or [])
    roof_source = next(
        (
            dict(row)
            for row in rows
            if row.get('is_roof') or str(row.get('floor') or '').strip() == 'بام'
        ),
        {},
    )
    regular = normalize_floor_structure(
        total,
        parking_count,
        negative_count,
        [row for row in rows if not row.get('is_roof') and str(row.get('floor') or '').strip() != 'بام'],
    )
    storage_areas = list(roof_source.get('storage_areas') or [])
    storage_count = max(parse_int(roof_source.get('storage_count')), len(storage_areas))
    roof = {
        **roof_source,
        'floor_level': ROOF_LEVEL_186,
        'floor': 'بام',
        'is_roof': True,
        'is_parking': False,
        'unit_count': 0,
        'units': [],
        'areas': [],
        'storage_count': storage_count,
        'storage_areas': (storage_areas + [0] * storage_count)[:storage_count],
        'parking_supplied': 0,
    }
    return regular + [roof]


def currency_unit_186(value: Any) -> str:
    unit = str(value or 'تومان').strip()
    return unit if unit in CURRENCY_UNITS else 'تومان'


def convert_toman_186(amount_toman: float | int, unit: str, usd_rate_toman: float | int = 0) -> float:
    unit = currency_unit_186(unit)
    amount = float(amount_toman or 0)
    if unit == 'ریال':
        return amount * 10.0
    if unit == 'دلار':
        rate = float(usd_rate_toman or 0)
        return amount / rate if rate > 0 else 0.0
    return amount


def format_currency_186(amount_toman: float | int, unit: str, usd_rate_toman: float | int = 0) -> str:
    unit = currency_unit_186(unit)
    converted = convert_toman_186(amount_toman, unit, usd_rate_toman)
    if unit == 'دلار':
        return fa(f'{converted:,.2f}')
    return fa(f'{int(round(converted)):,}')


def parse_display_amount_186(value: Any) -> float | None:
    text = en(str(value or '')).strip()
    for word in CURRENCY_UNITS:
        text = text.replace(word, '')
    text = text.replace(',', '').replace('٬', '').replace('٫', '.').strip()
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)', text):
        return None
    try:
        return float(text)
    except Exception:
        return None


def is_money_heading_186(text: Any) -> bool:
    label = str(text or '')
    # A column of quantities is not a column of money, whichever money word
    # its name happens to contain: 'مقدار-واقعی' names how much, not how much
    # it cost, and was being labelled in تومان.
    if any(word in label for word in NON_MONEY_HEADING_WORDS):
        return False
    return any(word in label for word in MONEY_HEADING_WORDS)


def base_currency_heading_186(text: Any) -> str:
    label = str(text or '').strip()
    label = re.sub(r'\s*[\(（]\s*(?:تومان|ریال|دلار)\s*[\)）]\s*$', '', label)
    return label.strip()


def currency_heading_186(text: Any, unit: str) -> str:
    base = base_currency_heading_186(text)
    return f'{base} ({currency_unit_186(unit)})' if is_money_heading_186(base) else base


def _ui_currency_values() -> tuple[str, int]:
    try:
        from v18_store import load_ui
        data = load_ui()
        return currency_unit_186(data.get('currency_unit')), max(0, parse_int(data.get('usd_rate_current')))
    except Exception:
        return 'تومان', 0


def convert_tree_currency_186(tree: ttk.Treeview, unit: str | None = None, usd_rate: int | None = None) -> None:
    # A barkav_ui.table.DataTable already decided its own grid, its own
    # row colours and its own headings - see barkav_ui/table.py. This is
    # one of four generations of the same blanket pass (18.4/18.5/18.6),
    # each written before that kit existed, and each still walks every
    # Treeview in the window. The flag is the one thing they all check.
    if getattr(tree, '_barkav_kit_table_187', False):
        return
    unit0, rate0 = _ui_currency_values()
    unit = currency_unit_186(unit or unit0)
    rate = rate0 if usd_rate is None else max(0, int(usd_rate or 0))
    columns = list(tree.cget('columns') or ())
    base_headings = getattr(tree, '_barkav_currency_headings_186', {})
    excluded_columns = set(getattr(tree, '_barkav_non_currency_columns_186', ()))
    money_indexes: list[int] = []
    for index, column in enumerate(columns):
        try:
            current = str(tree.heading(column, 'text') or '')
        except Exception:
            continue
        stored = base_headings.get(column)
        if stored is None or current not in (stored, currency_heading_186(stored, getattr(tree, '_barkav_currency_unit_186', unit))):
            stored = base_currency_heading_186(current)
            base_headings[column] = stored
        if column in excluded_columns:
            tree.heading(column, text=stored)
        elif is_money_heading_186(stored):
            money_indexes.append(index)
            tree.heading(column, text=currency_heading_186(stored, unit))
        else:
            tree.heading(column, text=stored)
    tree._barkav_currency_headings_186 = base_headings
    previous_unit = getattr(tree, '_barkav_currency_unit_186', unit)
    cache = getattr(tree, '_barkav_currency_cache_186', {})
    active_keys = set()
    for iid in tree.get_children(''):
        values = list(tree.item(iid, 'values') or ())
        changed = False
        for index in money_indexes:
            if index >= len(values):
                continue
            key = (str(iid), index)
            active_keys.add(key)
            current = str(values[index] or '')
            cached = cache.get(key)
            raw_text = cached[0] if cached and current == cached[1] else current
            amount = parse_display_amount_186(raw_text)
            if amount is None:
                continue
            shown = format_currency_186(amount, unit, rate)
            values[index] = shown
            cache[key] = (raw_text, shown)
            changed = changed or shown != current
        if changed:
            tree.item(iid, values=values)
    tree._barkav_currency_cache_186 = {key: value for key, value in cache.items() if key in active_keys}
    tree._barkav_currency_unit_186 = unit


def attach_tree_grid_186(tree: ttk.Treeview, *, light: bool = False):
    # 18.7's card-table contract explicitly opts out of the inherited ruled
    # grid.  This guard has to live at the attachment point: later inherited
    # refreshes otherwise recreate the overlay after the active layer removes
    # it.
    if getattr(tree, '_barkav_line_free_187', False):
        old = getattr(tree, '_barkav_grid_overlay', None)
        if old is not None:
            try:
                old._dead = True
                for line in list(getattr(old, 'vlines', [])) + list(getattr(old, 'hlines', [])):
                    line.destroy()
            except Exception:
                pass
        tree._barkav_grid_overlay = None
        return None
    # A barkav_ui.table.DataTable already decided its own grid, its own
    # row colours and its own headings - see barkav_ui/table.py. This is
    # one of four generations of the same blanket pass (18.4/18.5/18.6),
    # each written before that kit existed, and each still walks every
    # Treeview in the window. The flag is the one thing they all check.
    if getattr(tree, '_barkav_kit_table_187', False):
        return getattr(tree, '_barkav_grid_overlay', None)
    colors = (
        ('#F7F9FC', '#E9EEF4', '#DEE6EF')
        if light else
        ('#142238', '#24344A', '#2A3D56')
    )
    old = getattr(tree, '_barkav_grid_overlay', None)
    if isinstance(old, TreeGridOverlay185):
        old.column_color, old.row_color, old.header_color = colors
        old.schedule()
        return old
    if old is not None:
        try:
            old._dead = True
            for line in list(getattr(old, 'vlines', [])) + list(getattr(old, 'hlines', [])):
                line.destroy()
        except Exception:
            pass
    overlay = TreeGridOverlay185(
        tree,
        column_color=colors[0],
        row_color=colors[1],
        header_color=colors[2],
    )
    tree._barkav_grid_overlay = overlay
    return overlay


def retarget_smarttable_186(table, *, light: bool = False) -> None:
    tree = getattr(table, 'tree', None)
    if not isinstance(tree, ttk.Treeview):
        return
    if getattr(tree, '_barkav_kit_table_187', False):
        return
    p = palette_186(light)
    tree.tag_configure('even', background=p['surface'], foreground=p['text'])
    tree.tag_configure('odd', background=p['panel2'], foreground=p['text'])
    attach_tree_grid_186(tree, light=light)

    if not getattr(table, '_barkav_total_186', False):
        original_apply = getattr(table, 'apply_filter', None)

        def update_total_186(*_args, **_kwargs):
            unit, rate = _ui_currency_values()
            filtered = list(getattr(table, 'filtered_rows', []) or [])
            amount = int(getattr(table, '_filtered_total_amount', 0) or 0)
            selected = list(table.selected_rows()) if hasattr(table, 'selected_rows') else []
            text = (
                f'{fa(len(filtered))} مورد | جمع مبلغ فیلترشده ({unit}): '
                f'{format_currency_186(amount, unit, rate)}'
            )
            if selected:
                selected_amount = sum(int(table._row_amount(row) or 0) for row in selected)
                text += (
                    f' | انتخاب: {fa(len(selected))} مورد / '
                    f'{format_currency_186(selected_amount, unit, rate)}'
                )
            table.total.set(text)

        table._update_total = update_total_186
        if callable(original_apply):
            def apply_filter_186(*args, **kwargs):
                result = original_apply(*args, **kwargs)
                convert_tree_currency_186(tree)
                update_total_186()
                attach_tree_grid_186(tree, light=light)
                return result
            table.apply_filter = apply_filter_186
        table._barkav_total_186 = True

    convert_tree_currency_186(tree)
    table._update_total()


def build_brand_widget_186(
    parent,
    source: str | Path,
    *,
    bg: str,
    fg: str,
    muted: str,
    compact: bool = False,
):
    """Use the 18.4 brand artwork; keep BARKAV visibly larger than its subtitle."""
    host = tk.Frame(parent, bg=bg, bd=0, highlightthickness=0)
    try:
        from PIL import Image, ImageTk
        image = Image.open(source).convert('RGBA')
        # Keep the graphic mark from the 18.4 artwork. The tiny embedded Latin
        # lines are cropped and rendered as real text at the requested ratio.
        image = image.crop((0, 0, image.width, max(1, int(image.height * 0.64))))
        red, green, blue = tuple(int(fg[index:index + 2], 16) for index in (1, 3, 5))
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                r0, g0, b0, alpha = pixels[x, y]
                luminance = (r0 + g0 + b0) // 3
                if luminance > 244:
                    pixels[x, y] = (0, 0, 0, 0)
                else:
                    pixels[x, y] = (red, green, blue, max(0, min(255, 255 - luminance)))
        image.thumbnail((135 if compact else 158, 38 if compact else 43), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image, master=parent)
        host._brand_photo = photo
        tk.Label(host, image=photo, bg=bg, bd=0).pack(side='left', padx=(0, 8))
    except Exception:
        pass
    words = tk.Frame(host, bg=bg)
    words.pack(side='left', anchor='w')
    tk.Label(words, text='BARKAV', bg=bg, fg=fg,
             font=('Segoe UI', 15 if compact else 18, 'bold')).pack(anchor='w')
    tk.Label(words, text='Engineering & Construction', bg=bg, fg=muted,
             font=('Segoe UI', 7 if compact else 8)).pack(anchor='w', pady=(0, 1))
    return host


class CompactMetric186(tk.Frame):
    def __init__(self, parent, title: str, *, monetary: bool = True, alternate: bool = False):
        p = palette_186(str(parent.tk.call('set', '::barkav_light_186')) == '1' if self._has_light_var(parent) else False)
        background = p['panel2'] if alternate else p['panel']
        super().__init__(parent, bg=background, bd=0, highlightthickness=0)
        self.title = title
        self.monetary = monetary
        self.var = tk.StringVar(value='۰')
        unit, _rate = _ui_currency_values()
        shown_title = f'{title} ({unit})' if monetary else title
        self.title_label = tk.Label(self, text=shown_title, bg=background, fg=p['muted'],
                                    font=('Segoe UI', 8), anchor='e')
        self.title_label.pack(side='right', fill='x', expand=True, padx=(4, 8), pady=5)
        self.value_label = tk.Label(self, textvariable=self.var, bg=background, fg=p['text'],
                                    font=('Segoe UI', 9, 'bold'), anchor='w')
        self.value_label.pack(side='left', padx=(8, 4), pady=5)

    @staticmethod
    def _has_light_var(parent) -> bool:
        try:
            parent.tk.call('set', '::barkav_light_186')
            return True
        except Exception:
            return False

    def update_currency_title(self, unit: str) -> None:
        self.title_label.configure(text=f'{self.title} ({unit})' if self.monetary else self.title)


class DashboardCard186(tk.Frame):
    def __init__(self, parent, title: str, *, icon: str = '◈', light: bool = False):
        p = palette_186(light)
        super().__init__(parent, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
        header = tk.Frame(self, bg=p['panel2'], height=36)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header, text=title, bg=p['panel2'], fg=p['text'],
                 font=('Segoe UI', 9, 'bold'), anchor='e').pack(side='right', fill='x', expand=True, padx=9)
        tk.Label(header, text=icon, bg=p['panel2'], fg=p['blue'],
                 font=('Segoe UI Symbol', 12), width=3).pack(side='left', padx=4)
        self.body = tk.Frame(self, bg=p['panel'])
        self.body.pack(fill='both', expand=True, padx=7, pady=7)


def style_ttk_186(root: tk.Misc, *, light: bool, font_size: int = 10, row_height: int = 31) -> None:
    p = palette_186(light)
    try:
        root.tk.call('set', '::barkav_light_186', '1' if light else '0')
    except Exception:
        pass
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except Exception:
        pass
    fs = max(9, min(12, int(font_size or 10)))
    rh = max(28, min(34, int(row_height or 31)))
    style.configure('.', font=('Segoe UI', fs), background=p['bg'], foreground=p['text'])
    style.configure('TFrame', background=p['bg'])
    style.configure('Panel.TFrame', background=p['panel'])
    style.configure('TLabel', background=p['bg'], foreground=p['text'])
    style.configure('Summary.TLabel', background=p['panel2'], foreground=p['text'],
                    font=('Segoe UI', max(9, fs - 1), 'bold'), padding=(8, 5), anchor='e')
    style.configure('TButton', background=p['glass'], foreground=p['text'], bordercolor=p['line'],
                    relief='flat', padding=(9, 5), font=('Segoe UI', max(8, fs - 1)))
    style.configure('Toolbar.TButton', background=p['glass'], foreground=p['text'],
                    padding=(6, 4), font=('Segoe UI', max(8, fs - 2)))
    style.configure('Primary.TButton', background=p['blue'], foreground='#FFFFFF',
                    padding=(10, 6), font=('Segoe UI', max(9, fs - 1), 'bold'))
    style.map('TButton', background=[('active', p['panel2']), ('pressed', p['blue'])])
    style.configure('TEntry', fieldbackground=p['surface'], foreground=p['text'], insertcolor=p['text'],
                    bordercolor=p['line'], lightcolor=p['line'], darkcolor=p['line'], padding=5)
    style.configure('TCombobox', fieldbackground=p['surface'], background=p['surface'], foreground=p['text'],
                    arrowcolor=p['text'], bordercolor=p['line'], padding=4)
    style.map('TCombobox', fieldbackground=[('readonly', p['surface'])],
              foreground=[('readonly', p['text'])])
    style.configure('Treeview', rowheight=rh, background=p['surface'], fieldbackground=p['surface'],
                    foreground=p['text'], bordercolor=p['line'], relief='flat', font=('Segoe UI', fs))
    style.configure('Treeview.Heading', background=p['panel2'], foreground=p['text'],
                    bordercolor=p['line'], relief='flat', padding=(6, 6),
                    font=('Segoe UI', max(8, fs - 1), 'bold'))
    style.map('Treeview', background=[('selected', p['blue'])], foreground=[('selected', '#FFFFFF')])
    style.configure('TNotebook', background=p['bg'], borderwidth=0, tabmargins=(0, 1, 0, 0))
    style.configure('TNotebook.Tab', background=p['surface'], foreground=p['muted'],
                    padding=(13, 6), font=('Segoe UI', max(8, fs - 1), 'bold'), borderwidth=0)
    style.map('TNotebook.Tab', background=[('selected', p['panel2']), ('active', p['glass'])],
              foreground=[('selected', p['blue']), ('active', p['text'])])
    style.configure('Hidden.TNotebook', background=p['bg'], borderwidth=0, tabmargins=0)
    try:
        style.layout('Hidden.TNotebook.Tab', [])
    except Exception:
        pass
    style.configure('TLabelframe', background=p['panel'], bordercolor=p['line'], relief='solid')
    style.configure('TLabelframe.Label', background=p['panel'], foreground=p['text'],
                    font=('Segoe UI', max(8, fs - 1), 'bold'))
    style.configure('TPanedwindow', background=p['line'])
    style.configure('TScrollbar', background=p['panel2'], troughcolor=p['bg'],
                    bordercolor=p['line'], arrowcolor=p['muted'])
