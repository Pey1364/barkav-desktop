from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from ui_stage18_3 import fa, en, parse_int
from ui_stage18_4 import enable_tree_checkboxes


DARK_185 = {
    'bg': '#0A1322',
    'surface': '#0E192A',
    'panel': '#111E31',
    'panel2': '#16263C',
    'glass': '#142238',
    'line': '#26364D',
    'text': '#F2F6FB',
    'muted': '#9EACC0',
    'blue': '#2E78F3',
    'green': '#45C58A',
    'orange': '#E8A854',
    'red': '#E86774',
    'cyan': '#55A8FF',
    'violet': '#A78BFA',
    'yellow': '#F0C65A',
}

LIGHT_185 = {
    'bg': '#F5F7FA',
    'surface': '#FFFFFF',
    'panel': '#FFFFFF',
    'panel2': '#F2F6FC',
    'glass': '#F7F9FC',
    'line': '#E2E8F0',
    'text': '#172033',
    'muted': '#68758A',
    'blue': '#2573E8',
    'green': '#238A62',
    'orange': '#B97517',
    'red': '#C34E5B',
    'cyan': '#2477D4',
    'violet': '#7357C7',
    'yellow': '#B88718',
}


def palette_185(light: bool = False) -> dict[str, str]:
    return dict(LIGHT_185 if light else DARK_185)


def bind_persian_digits(entry: tk.Misc, var: tk.StringVar) -> None:
    """Translate digits as the user types without stripping letters or separators."""
    busy = {'value': False}

    def normalize(*_args):
        if busy['value']:
            return
        old = str(var.get() or '')
        new = fa(old)
        if old == new:
            return
        try:
            caret = int(entry.index(tk.INSERT))
        except Exception:
            caret = len(new)
        busy['value'] = True
        try:
            var.set(new)
            entry.icursor(min(caret, len(new)))
        finally:
            busy['value'] = False

    try:
        var.trace_add('write', normalize)
    except Exception:
        entry.bind('<KeyRelease>', normalize, add='+')


_ORDINAL_FA = {
    1: 'اول', 2: 'دوم', 3: 'سوم', 4: 'چهارم', 5: 'پنجم', 6: 'ششم',
    7: 'هفتم', 8: 'هشتم', 9: 'نهم', 10: 'دهم', 11: 'یازدهم',
    12: 'دوازدهم', 13: 'سیزدهم', 14: 'چهاردهم', 15: 'پانزدهم',
    16: 'شانزدهم', 17: 'هفدهم', 18: 'هجدهم', 19: 'نوزدهم', 20: 'بیستم',
}


def floor_name_185(level: int) -> str:
    if level < 0:
        return f'طبقه منفی {fa(abs(level))}'
    if level == 0:
        return 'همکف'
    return f"طبقه {_ORDINAL_FA.get(level, fa(level))}"


def generated_floor_levels(total: Any, negative_count: Any) -> list[int]:
    total_n = max(0, parse_int(total))
    negative_n = min(total_n, max(0, parse_int(negative_count)))
    return list(range(-negative_n, 0)) + list(range(0, total_n - negative_n))


def normalize_floor_structure(
    total: Any,
    parking_count: Any,
    negative_count: Any,
    existing: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return bottom-to-top floor rows while preserving matching user details."""
    levels = generated_floor_levels(total, negative_count)
    parking_n = min(len(levels), max(0, parse_int(parking_count)))
    rows = list(existing or [])
    by_level = {}
    for row in rows:
        try:
            by_level[int(en(row.get('floor_level')))] = row
        except Exception:
            pass
    out = []
    for index, level in enumerate(levels):
        source = dict(by_level.get(level) or (rows[index] if index < len(rows) else {}) or {})
        raw_floor_name = str(source.get('floor') or '').strip()
        # 18.4 commonly stored bare numeric names (1, 2, ...). Convert those
        # legacy rows to the requested منفی/همکف/اول... naming convention.
        generated_name = not raw_floor_name or en(raw_floor_name).lstrip('-').isdigit()
        units = list(source.get('units') or [])
        if not units:
            areas = list(source.get('areas') or [])
            for unit_index in range(max(parse_int(source.get('unit_count')), len(areas))):
                units.append({
                    'unit_number': '',
                    'usage': 'مسکونی',
                    'area': areas[unit_index] if unit_index < len(areas) else 0,
                })
        storage_areas = list(source.get('storage_areas') or [])
        storage_count = max(parse_int(source.get('storage_count')), len(storage_areas))
        row = {
            **source,
            'floor_level': level,
            'floor': floor_name_185(level) if generated_name else raw_floor_name,
            'is_parking': index < parking_n,
            'unit_count': len(units),
            'units': units,
            'areas': [u.get('area') or 0 for u in units],
            'storage_count': storage_count,
            'storage_areas': (storage_areas + [0] * storage_count)[:storage_count],
            'parking_supplied': parse_int(source.get('parking_supplied')) if index < parking_n else 0,
        }
        out.append(row)
    # Legacy rows numbered units from 1 on every floor, while UnitService uses
    # a project-wide unique unit number. Preserve unique explicit values and
    # fill blanks/duplicates with the next available global number.
    used: set[str] = set()
    next_number = 1
    for row in out:
        for unit in row['units']:
            number = en(unit.get('unit_number') or '').strip()
            if not number or number in used:
                while str(next_number) in used:
                    next_number += 1
                number = str(next_number)
            used.add(number)
            if number.isdigit():
                next_number = max(next_number, int(number) + 1)
            unit['unit_number'] = number
    return out


class TreeGridOverlay185:
    """Event-driven faint grid; unlike 18.3/18.4 it never runs a polling loop."""

    def __init__(self, tree: ttk.Treeview, *, column_color: str, row_color: str, header_color: str):
        self.tree = tree
        self.column_color = column_color
        self.row_color = row_color
        self.header_color = header_color
        self.vlines: list[tk.Frame] = []
        self.hlines: list[tk.Frame] = []
        self._dead = False
        self._pending = False
        for event in ('<Configure>', '<MouseWheel>', '<ButtonRelease-1>', '<KeyRelease>', '<<TreeviewSelect>>'):
            tree.bind(event, lambda _e: self.schedule(), add='+')
        self.schedule()

    def _line(self, pool: list[tk.Frame], index: int, color: str) -> tk.Frame:
        while len(pool) <= index:
            pool.append(tk.Frame(self.tree, bg=color, bd=0, highlightthickness=0))
        line = pool[index]
        line.configure(bg=color)
        return line

    def schedule(self):
        if self._dead or self._pending:
            return
        self._pending = True
        try:
            self.tree.after_idle(self.update)
        except Exception:
            self._dead = True

    def update(self):
        self._pending = False
        try:
            if not self.tree.winfo_exists():
                self._dead = True
                return
            width = max(1, self.tree.winfo_width())
            height = max(1, self.tree.winfo_height())
            display = self.tree.cget('displaycolumns')
            if display in ('#all', ('#all',), ''):
                display = list(self.tree.cget('columns'))
            else:
                display = list(display)
            children = list(self.tree.get_children(''))
            visible = []
            for iid in children:
                bbox = self.tree.bbox(iid)
                if bbox and bbox[1] + bbox[3] >= 0 and bbox[1] <= height:
                    visible.append(iid)
            sample = visible[0] if visible else (children[0] if children else None)
            used = 0
            if sample:
                for column in display[:-1]:
                    bbox = self.tree.bbox(sample, column)
                    if not bbox:
                        continue
                    x = bbox[0] + bbox[2] - 1
                    if 0 < x < width:
                        self._line(self.vlines, used, self.column_color).place(x=x, y=0, width=1, height=height)
                        used += 1
            for line in self.vlines[used:]:
                line.place_forget()
            used = 0
            if visible:
                first = self.tree.bbox(visible[0])
                if first and first[1] > 1:
                    self._line(self.hlines, used, self.header_color).place(x=0, y=first[1] - 1, width=width, height=1)
                    used += 1
            for iid in visible:
                bbox = self.tree.bbox(iid)
                if bbox:
                    y = bbox[1] + bbox[3] - 1
                    if 0 < y < height:
                        self._line(self.hlines, used, self.row_color).place(x=0, y=y, width=width, height=1)
                        used += 1
            for line in self.hlines[used:]:
                line.place_forget()
        except Exception:
            return


def _retire_overlay(tree: ttk.Treeview) -> None:
    old = getattr(tree, '_barkav_grid_overlay', None)
    if old is None or isinstance(old, TreeGridOverlay185):
        return
    try:
        old._dead = True
        for line in list(getattr(old, 'vlines', [])) + list(getattr(old, 'hlines', [])):
            line.destroy()
    except Exception:
        pass
    tree._barkav_grid_overlay = None


def attach_tree_grid_185(tree: ttk.Treeview, *, light: bool = False):
    # 18.7 card tables opt out before this older layer can create its overlay.
    # This is the earliest grid attachment point in the inherited stack.
    if getattr(tree, '_barkav_line_free_187', False):
        return None
    # A barkav_ui.table.DataTable already decided its own grid, its own
    # row colours and its own headings - see barkav_ui/table.py. This is
    # one of four generations of the same blanket pass (18.4/18.5/18.6),
    # each written before that kit existed, and each still walks every
    # Treeview in the window. The flag is the one thing they all check.
    if getattr(tree, '_barkav_kit_table_187', False):
        return getattr(tree, '_barkav_grid_overlay', None)
    _retire_overlay(tree)
    old = getattr(tree, '_barkav_grid_overlay', None)
    colors = (
        ('#F2F5F9', '#E4EAF1', '#D5DEE8') if light
        else ('#172337', '#26364D', '#31445F')
    )
    if isinstance(old, TreeGridOverlay185):
        old.column_color, old.row_color, old.header_color = colors
        old.schedule()
        return old
    overlay = TreeGridOverlay185(tree, column_color=colors[0], row_color=colors[1], header_color=colors[2])
    tree._barkav_grid_overlay = overlay
    return overlay


def attach_table_visuals_recursive_185(root: tk.Misc, *, light: bool = False) -> None:
    stack = [root]
    while stack:
        widget = stack.pop()
        try:
            stack.extend(widget.winfo_children())
        except Exception:
            pass
        if isinstance(widget, ttk.Treeview):
            attach_tree_grid_185(widget, light=light)
            enable_tree_checkboxes(widget)


def build_brand_widget_185(parent, icon_path: str | Path, *, bg: str, fg: str, muted: str, compact: bool = False):
    """Reference-style icon plus a deliberately larger BARKAV wordmark."""
    host = tk.Frame(parent, bg=bg, bd=0, highlightthickness=0)
    try:
        from PIL import Image, ImageTk
        image = Image.open(icon_path).convert('RGB')
        size = 38 if compact else 44
        image = image.resize((size, size), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image, master=parent)
        host._brand_photo = photo
        tk.Label(host, image=photo, bg=bg, bd=0).pack(side='left', padx=(0, 9))
    except Exception:
        pass
    words = tk.Frame(host, bg=bg)
    words.pack(side='left', anchor='w')
    tk.Label(words, text='BARKAV', bg=bg, fg=fg, font=('Segoe UI', 14 if compact else 17, 'bold')).pack(anchor='w')
    tk.Label(words, text='Engineering & Construction', bg=bg, fg=muted,
             font=('Segoe UI', 7 if compact else 8)).pack(anchor='w', pady=(0, 1))
    return host


def style_ttk_185(root: tk.Misc, *, light: bool, font_size: int = 11, row_height: int = 38) -> None:
    p = palette_185(light)
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except Exception:
        pass
    style.configure('.', font=('Segoe UI', font_size), background=p['bg'], foreground=p['text'])
    style.configure('TFrame', background=p['bg'])
    style.configure('Panel.TFrame', background=p['panel'])
    style.configure('TLabel', background=p['bg'], foreground=p['text'])
    style.configure('TButton', font=('Segoe UI', max(9, font_size - 1)), padding=(11, 7),
                    background=p['glass'], foreground=p['text'], bordercolor=p['line'], relief='flat')
    style.map('TButton', background=[('active', p['panel2']), ('pressed', p['blue'])])
    style.configure('TEntry', fieldbackground=p['surface'], foreground=p['text'], insertcolor=p['text'],
                    bordercolor=p['line'], lightcolor=p['line'], darkcolor=p['line'], padding=6)
    style.configure('TCombobox', fieldbackground=p['surface'], background=p['surface'], foreground=p['text'],
                    arrowcolor=p['text'], bordercolor=p['line'], padding=5)
    style.map('TCombobox', fieldbackground=[('readonly', p['surface'])], foreground=[('readonly', p['text'])])
    style.configure('Treeview', rowheight=max(34, row_height), background=p['surface'], fieldbackground=p['surface'],
                    foreground=p['text'], bordercolor=p['line'], relief='flat', font=('Segoe UI', font_size))
    style.configure('Treeview.Heading', background=p['panel2'], foreground=p['text'],
                    bordercolor=p['line'], relief='flat', padding=(7, 8),
                    font=('Segoe UI', max(9, font_size - 1), 'bold'))
    style.map('Treeview', background=[('selected', p['blue'])], foreground=[('selected', '#FFFFFF')])
    style.configure('TNotebook', background=p['bg'], borderwidth=0)
    style.configure('TNotebook.Tab', background=p['surface'], foreground=p['muted'],
                    padding=(17, 8), font=('Segoe UI', max(9, font_size - 1), 'bold'))
    style.map('TNotebook.Tab', background=[('selected', p['panel2']), ('active', p['glass'])],
              foreground=[('selected', p['blue']), ('active', p['text'])])
    style.configure('TPanedwindow', background=p['line'])
    style.configure('TScrollbar', background=p['panel2'], troughcolor=p['bg'], bordercolor=p['line'], arrowcolor=p['muted'])
