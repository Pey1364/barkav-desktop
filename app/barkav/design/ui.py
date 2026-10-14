"""Consolidated BARKAV UI helpers extracted from the active 18.7 runtime."""
from __future__ import annotations

# ---- Extracted from ui_stage10.py ----

import calendar
import re
import tkinter as tk
from datetime import date
from tkinter import ttk
from typing import Callable, Optional

from revenue_service import gregorian_to_shamsi, normalize_shamsi

_DIGIT_MAP = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def clean_int_text(value: str) -> str:
    s = str(value or '').translate(_DIGIT_MAP).replace(',', '').replace('،', '').strip()
    s = re.sub(r'[^0-9\-]', '', s)
    return s


def parse_int(value: str, default: int = 0) -> int:
    s = clean_int_text(value)
    if s in ('', '-'): return default
    return int(s)


_FA_OUT = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')

def group_int(value: str | int | float, blank_zero: bool = False) -> str:
    try:
        raw=str(value).translate(_DIGIT_MAP).replace(',', '').replace('،', '')
        n = int(float(raw or 0))
        if blank_zero and n == 0: return ''
        return f'{n:,}'.translate(_FA_OUT)
    except Exception:
        return str(value or '')


def bind_grouped_number(entry: ttk.Entry, var: tk.StringVar, *, allow_negative: bool = False) -> None:
    """Format integer input with thousands separators while the user types."""
    busy = {'value': False}

    def normalize(_event=None):
        if busy['value']:
            return
        raw = clean_int_text(var.get())
        if not allow_negative:
            raw = raw.lstrip('-')
        if raw in ('', '-'):
            if var.get() != raw:
                busy['value'] = True
                try:
                    var.set(raw)
                finally:
                    busy['value'] = False
            return
        try:
            current = str(var.get() or '')
            try:
                caret = int(entry.index(tk.INSERT))
            except Exception:
                caret = len(current)
            right_digits = sum(ch.isdigit() for ch in current[caret:])
            formatted = f'{int(raw):,}'
            if current == formatted:
                return
            busy['value'] = True
            try:
                var.set(formatted)
                new_pos = len(formatted)
                if right_digits:
                    digits_seen = 0
                    for idx in range(len(formatted) - 1, -1, -1):
                        if formatted[idx].isdigit():
                            digits_seen += 1
                            if digits_seen >= right_digits:
                                new_pos = idx
                                break
                try:
                    entry.icursor(new_pos)
                except Exception:
                    pass
            finally:
                busy['value'] = False
        except Exception:
            pass

    try:
        var.trace_add('write', lambda *_: normalize())
    except Exception:
        entry.bind('<KeyRelease>', normalize, add='+')
    entry.bind('<FocusOut>', normalize, add='+')
    entry.bind('<Return>', normalize, add='+')


def clean_decimal_text(value: str) -> str:
    """Normalize a user-entered decimal while treating commas as grouping."""
    s = str(value or '').translate(_DIGIT_MAP).replace('٬', '').replace(',', '').replace('،', '').replace('٫', '.').strip()
    s = re.sub(r'[^0-9.\-]', '', s)
    sign = '-' if s.startswith('-') else ''
    s = s.replace('-', '')
    if '.' in s:
        head, tail = s.split('.', 1)
        tail = tail.replace('.', '')
        return sign + head + '.' + tail
    return sign + s


def parse_decimal(value: str, default: float = 0.0) -> float:
    s = clean_decimal_text(value)
    if s in ('', '-', '.', '-.'):
        return default
    try:
        return float(s)
    except Exception:
        return default


def bind_grouped_decimal(entry: ttk.Entry, var: tk.StringVar, *, allow_negative: bool = False) -> None:
    """Live thousands grouping for decimal inputs (e.g. 1458.5 -> 1,458.5)."""
    busy = {'value': False}

    def normalize(_event=None):
        if busy['value']:
            return
        raw = clean_decimal_text(var.get())
        if not allow_negative:
            raw = raw.lstrip('-')
        if raw in ('', '-', '.', '-.'):
            return
        current = str(var.get() or '')
        negative = raw.startswith('-')
        unsigned = raw[1:] if negative else raw
        if '.' in unsigned:
            whole, frac = unsigned.split('.', 1)
            dot = True
        else:
            whole, frac, dot = unsigned, '', False
        if not whole:
            whole = '0'
        try:
            grouped = f'{int(whole):,}'
        except Exception:
            return
        formatted = ('-' if negative else '') + grouped + ('.' + frac if dot else '')
        if current == formatted:
            return
        try:
            caret = int(entry.index(tk.INSERT))
        except Exception:
            caret = len(current)
        right_chars = len(current) - caret
        busy['value'] = True
        try:
            var.set(formatted)
            try: entry.icursor(max(0, len(formatted) - right_chars))
            except Exception: pass
        finally:
            busy['value'] = False

    try:
        var.trace_add('write', lambda *_: normalize())
    except Exception:
        entry.bind('<KeyRelease>', normalize, add='+')
    entry.bind('<FocusOut>', normalize, add='+')
    entry.bind('<Return>', normalize, add='+')


def _jalali_today() -> tuple[int, int, int]:
    sh = gregorian_to_shamsi(date.today())
    y, m, d = [int(x) for x in sh.split('/')]
    return y, m, d


def _jalali_month_days(year: int, month: int) -> int:
    if month <= 6: return 31
    if month <= 11: return 30
    # Esfand 30 is valid only in a Jalali leap year. Round-trip through
    # Gregorian conversion because the shared parser deliberately accepts a
    # broad financial date range.
    try:
        from revenue_service import shamsi_to_gregorian
        candidate=f'{year:04d}/12/30'
        return 30 if gregorian_to_shamsi(shamsi_to_gregorian(candidate)) == candidate else 29
    except Exception:
        return 29


class JalaliCalendar(tk.Toplevel):
    WEEKDAYS = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج']
    MONTHS = ['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند']

    def __init__(self, parent: tk.Misc, initial: str = '', on_select: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self.title('انتخاب تاریخ شمسی')
        self.resizable(False, False)
        self.transient(parent)
        self.on_select = on_select
        parsed = normalize_shamsi(initial) if initial else None
        if parsed:
            self.year, self.month, self.day = [int(x) for x in parsed.split('/')]
        else:
            self.year, self.month, self.day = _jalali_today()
        self._build()
        self.grab_set()

    def _build(self):
        self.body = ttk.Frame(self, padding=8); self.body.pack(fill='both', expand=True)
        nav = ttk.Frame(self.body); nav.pack(fill='x')
        ttk.Button(nav, text='◀', width=3, command=lambda:self._move_month(1)).pack(side='left')
        ttk.Button(nav, text='امروز', command=self._today).pack(side='left', padx=3)
        ttk.Button(nav, text='▶', width=3, command=lambda:self._move_month(-1)).pack(side='right')
        self.title_var = tk.StringVar(); ttk.Label(nav, textvariable=self.title_var, font=('Tahoma',10,'bold')).pack(expand=True)
        self.grid = ttk.Frame(self.body); self.grid.pack(pady=(7,0))
        self._render()

    def _today(self):
        self.year, self.month, self.day = _jalali_today(); self._render()

    def _move_month(self, delta: int):
        m = self.month + delta; y = self.year
        while m > 12: m -= 12; y += 1
        while m < 1: m += 12; y -= 1
        self.year, self.month = y, m; self.day = 1; self._render()

    def _render(self):
        for w in self.grid.winfo_children(): w.destroy()
        self.title_var.set(f'{self.MONTHS[self.month-1]} {self.year}')
        for i, name in enumerate(self.WEEKDAYS):
            ttk.Label(self.grid, text=name, width=4, anchor='center').grid(row=0, column=i, padx=1, pady=1)
        # 1 Farvardin 1399 was Friday; use Gregorian conversion indirectly via Python weekday through revenue_service.
        from revenue_service import shamsi_to_gregorian
        import datetime as _dt
        g = _dt.date.fromisoformat(shamsi_to_gregorian(f'{self.year:04d}/{self.month:02d}/01'))
        # Python Monday=0. Persian week Saturday=0.
        start = (g.weekday() + 2) % 7
        days = _jalali_month_days(self.year, self.month)
        for d in range(1, days+1):
            idx = start + d - 1; row = 1 + idx//7; col = idx%7
            b = ttk.Button(self.grid, text=str(d), width=4, command=lambda dd=d:self._select(dd))
            b.grid(row=row, column=col, padx=1, pady=1)

    def _select(self, day: int):
        value = f'{self.year:04d}/{self.month:02d}/{day:02d}'
        if self.on_select: self.on_select(value)
        self.destroy()


class DateField(ttk.Frame):
    def __init__(self, parent, variable: tk.StringVar, width: int = 13, **kwargs):
        super().__init__(parent)
        self.variable = variable
        self.entry = ttk.Entry(self, textvariable=variable, width=width, justify='center', **kwargs)
        self.entry.pack(side='right', fill='x', expand=True)
        ttk.Button(self, text='📅', width=3, command=self.open_calendar).pack(side='left', padx=(2,0))
        self.entry.bind('<Double-1>', lambda e:self.open_calendar())

    def open_calendar(self):
        JalaliCalendar(self, self.variable.get(), self.variable.set)


class SignedMetric(tk.Frame):
    def __init__(self, parent, title: str, unit: str = ''):
        super().__init__(parent, bg='white', highlightthickness=1, highlightbackground='#D8E2EA')
        self.title = title; self.unit = unit; self.value = 0
        tk.Label(self, text=title, bg='white', fg='#637381', font=('Tahoma',8)).pack(pady=(7,1))
        self.var = tk.StringVar(value='-')
        self.value_label = tk.Label(self, textvariable=self.var, bg='white', fg='#1E2D3D', font=('Tahoma',10,'bold'))
        self.value_label.pack(pady=(1,7))

    def set(self, value: int | float, formatter: Optional[Callable[[int|float], str]] = None):
        self.value = value
        if formatter: text = formatter(value)
        else:
            try:
                n=float(value); text=f'{n:,.1f}' if not n.is_integer() else f'{int(n):,}'
            except Exception: text=str(value)
            if self.unit: text += f' {self.unit}'
        self.var.set(text)
        try: n=float(value)
        except Exception: n=0
        self.value_label.configure(fg='#2F7D63' if n >= 0 else '#B84B4B')

# ---- Extracted from ui_stage18_3.py ----

import re
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Any
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
EN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def fa(value: Any) -> str:
    return str(value if value is not None else '').translate(FA_DIGITS)


def en(value: Any) -> str:
    return str(value if value is not None else '').translate(EN_DIGITS)


def _clean_int(value: Any) -> str:
    s = en(value).replace(',', '').replace('٬', '').replace('،', '').strip()
    return re.sub(r'[^0-9\-]', '', s)


def parse_int(value: Any, default: int = 0) -> int:
    s = _clean_int(value)
    if s in ('', '-'): return default
    try: return int(s)
    except Exception: return default


def group_int_fa(value: Any, blank_zero: bool = False) -> str:
    try:
        raw = _clean_int(value)
        n = int(raw or 0)
        if blank_zero and n == 0: return ''
        return fa(f'{n:,}')
    except Exception:
        return fa(value)


def _clean_decimal(value: Any) -> str:
    s = en(value).replace(',', '').replace('٬', '').replace('،', '').replace('٫', '.').strip()
    s = re.sub(r'[^0-9.\-]', '', s)
    sign = '-' if s.startswith('-') else ''
    s = s.replace('-', '')
    if '.' in s:
        head, tail = s.split('.', 1)
        return sign + head + '.' + tail.replace('.', '')
    return sign + s


def parse_decimal(value: Any, default: float = 0.0) -> float:
    s = _clean_decimal(value)
    if s in ('', '-', '.', '-.'): return default
    try: return float(s)
    except Exception: return default


def group_decimal_fa(value: Any) -> str:
    raw = _clean_decimal(value)
    if raw in ('', '-', '.', '-.'):
        return fa(raw)
    neg = raw.startswith('-'); unsigned = raw[1:] if neg else raw
    if '.' in unsigned:
        whole, frac = unsigned.split('.', 1); dot = True
    else:
        whole, frac, dot = unsigned, '', False
    try: grouped = f'{int(whole or 0):,}'
    except Exception: return fa(value)
    out = ('-' if neg else '') + grouped + ('.' + frac if dot else '')
    return fa(out)


def _preserve_caret(entry: ttk.Entry, old: str, new: str) -> None:
    try: caret = int(entry.index(tk.INSERT))
    except Exception: caret = len(old)
    right_digits = sum(ch.isdigit() for ch in old[caret:])
    pos = len(new)
    if right_digits:
        seen = 0
        for idx in range(len(new)-1, -1, -1):
            if new[idx].isdigit():
                seen += 1
                if seen >= right_digits:
                    pos = idx
                    break
    try: entry.icursor(pos)
    except Exception: pass


def bind_grouped_number_fa(entry: ttk.Entry, var: tk.StringVar, *, allow_negative: bool = False) -> None:
    busy = {'v': False}
    def normalize(*_):
        if busy['v']: return
        raw = _clean_int(var.get())
        if not allow_negative: raw = raw.lstrip('-')
        if raw in ('', '-'):
            target = fa(raw)
        else:
            try: target = fa(f'{int(raw):,}')
            except Exception: return
        old = str(var.get() or '')
        if old == target: return
        busy['v'] = True
        try:
            var.set(target); _preserve_caret(entry, old, target)
        finally: busy['v'] = False
    try: var.trace_add('write', normalize)
    except Exception: entry.bind('<KeyRelease>', normalize, add='+')
    entry.bind('<FocusOut>', normalize, add='+'); entry.bind('<Return>', normalize, add='+')


def bind_grouped_decimal_fa(entry: ttk.Entry, var: tk.StringVar, *, allow_negative: bool = False) -> None:
    busy = {'v': False}
    def normalize(*_):
        if busy['v']: return
        raw = _clean_decimal(var.get())
        if not allow_negative: raw = raw.lstrip('-')
        if raw in ('', '-', '.', '-.'):
            target = fa(raw)
        else:
            target = group_decimal_fa(raw)
        old = str(var.get() or '')
        if old == target: return
        busy['v'] = True
        try:
            var.set(target); _preserve_caret(entry, old, target)
        finally: busy['v'] = False
    try: var.trace_add('write', normalize)
    except Exception: entry.bind('<KeyRelease>', normalize, add='+')
    entry.bind('<FocusOut>', normalize, add='+'); entry.bind('<Return>', normalize, add='+')


def widget_notebook_path(widget: tk.Misc) -> list[str]:
    """Return tab labels for notebook ancestors, inner to outer."""
    out=[]; w=widget
    while True:
        try: parent=w.master
        except Exception: break
        if parent is None: break
        if isinstance(parent, ttk.Notebook):
            try: out.append(str(parent.tab(w, 'text')))
            except Exception: pass
        w=parent
    return out


class RtlNotebookStrip:
    """Shared rounded RTL tab strip controlling an existing hidden Notebook.

    The strip is deliberately canvas-drawn: native Tk buttons cannot provide
    the same rounded geometry on every Windows theme.  All screens therefore
    get the same light-above-window tab surface, selected state and hover
    behaviour from this one component.
    """
    def __init__(self, notebook: ttk.Notebook, *, bg: str, line: str, text: str, muted: str,
                 active_bg: str, active_fg: str, font=('Segoe UI', 10, 'bold')):
        self.notebook=notebook; self.buttons={}; self.colors=(bg,line,text,muted,active_bg,active_fg); self.font=font
        self._hovered=''
        style=ttk.Style(notebook)
        style.configure('BarkavRtlHidden.TNotebook', background=bg, borderwidth=0, tabmargins=0)
        try: style.layout('BarkavRtlHidden.TNotebook.Tab', [])
        except Exception: pass
        notebook.configure(style='BarkavRtlHidden.TNotebook')
        self.bar=tk.Frame(notebook.master,bg=bg,highlightthickness=0,height=52)
        try: self.bar.pack(fill='x',pady=(0,4),before=notebook)
        except Exception: self.bar.pack(fill='x',pady=(0,4))
        self.bar.pack_propagate(False)
        # Invoke this base implementation explicitly.  Older feature modules
        # may still expose screen-specific subclasses; they must not fork the
        # product's shared tab geometry.
        RtlNotebookStrip.rebuild(self)
        notebook.bind('<<NotebookTabChanged>>',lambda _e:RtlNotebookStrip.sync(self),add='+')

    def rebuild(self):
        for w in self.bar.winfo_children(): w.destroy()
        self.buttons.clear()
        self.canvas=tk.Canvas(self.bar,bg=self.colors[0],highlightthickness=0,bd=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda _event:self._draw_tabs(),add='+')
        self._draw_tabs()

    @staticmethod
    def _rounded_box(canvas, x1, y1, x2, y2, radius, *, fill, outline, tag):
        """Draw one pill without platform-specific button chrome."""
        canvas.create_rectangle(x1+radius,y1,x2-radius,y2,fill=fill,outline='',tags=(tag,))
        canvas.create_rectangle(x1,y1+radius,x2,y2-radius,fill=fill,outline='',tags=(tag,))
        for start,box in ((180,(x1,y1,x1+2*radius,y1+2*radius)),
                          (90,(x2-2*radius,y1,x2,y1+2*radius)),
                          (270,(x1,y2-2*radius,x1+2*radius,y2)),
                          (0,(x2-2*radius,y2-2*radius,x2,y2))):
            canvas.create_arc(*box,start=start,extent=90,fill=fill,outline=outline,tags=(tag,))

    @staticmethod
    def _tab_surface(window_surface):
        """Make the inactive tab visibly one elevation above its window."""
        try:
            raw=window_surface.lstrip('#')
            rgb=[int(raw[index:index+2],16) for index in (0,2,4)]
            if sum(rgb)/3 < 150:
                # Dark themes need a meaningful, not merely theoretical,
                # elevation step for an inactive tab to read as a tile.
                rgb=[round(value+(255-value)*0.14) for value in rgb]
                return '#%02X%02X%02X' % tuple(rgb)
            return '#FFFFFF'
        except (TypeError, ValueError):
            return window_surface

    def _draw_tabs(self):
        if not hasattr(self,'canvas'): return
        canvas=self.canvas; canvas.delete('all')
        bg,line,text,muted,active_bg,active_fg=self.colors
        tab_bg=self._tab_surface(bg)
        try: selected=str(self.notebook.select())
        except Exception: selected=''
        x=max(canvas.winfo_width(),320)-8
        self.buttons={}
        # The first logical tab remains the right-most tab in RTL layouts.
        for index,tid in enumerate(self.notebook.tabs()):
            label=str(self.notebook.tab(tid,'text'))
            tab_width=max(112,min(200,38+len(label)*14))
            x1,x2=x-tab_width,x
            active=str(tid)==selected
            hovered=str(tid)==self._hovered and not active
            fill=active_bg if (active or hovered) else tab_bg
            foreground=active_fg if active else text
            tag=f'barkav_tab_{index}'
            self._rounded_box(canvas,x1,5,x2,47,15,fill=fill,outline=line,tag=tag)
            canvas.create_text((x1+x2)/2,26,text=label,fill=foreground,font=self.font,tags=(tag,))
            canvas.tag_bind(tag,'<Button-1>',lambda _event,target=tid:self.notebook.select(target))
            canvas.tag_bind(tag,'<Enter>',lambda _event,target=tid:self._set_hover(str(target)))
            canvas.tag_bind(tag,'<Leave>',lambda _event:self._set_hover(''))
            self.buttons[str(tid)]=tag
            x=x1-6

    def _set_hover(self, tab_id):
        if self._hovered!=tab_id:
            self._hovered=tab_id; self._draw_tabs()

    def sync(self):
        self._draw_tabs()


class TreeGridOverlay:
    """Visible cell grid for ttk.Treeview without replacing the Treeview data model.

    Vertical column separators are deliberately softer than horizontal row separators.
    """
    def __init__(self, tree: ttk.Treeview, *, column_color: str, row_color: str, header_color: str | None=None):
        self.tree=tree; self.column_color=column_color; self.row_color=row_color; self.header_color=header_color or row_color
        self.vlines=[]; self.hlines=[]; self._dead=False
        for ev in ('<Configure>','<MouseWheel>','<ButtonRelease-1>','<KeyRelease>','<<TreeviewSelect>>'):
            tree.bind(ev,lambda e:self.schedule(),add='+')
        self.schedule()

    def _line(self, pool, idx, color):
        while len(pool)<=idx:
            pool.append(tk.Frame(self.tree,bg=color,bd=0,highlightthickness=0))
        w=pool[idx]
        try: w.configure(bg=color)
        except Exception: pass
        return w

    def schedule(self):
        if self._dead: return
        try: self.tree.after_idle(self.update)
        except Exception: self._dead=True

    def update(self):
        try:
            if not self.tree.winfo_exists(): self._dead=True; return
            width=max(1,self.tree.winfo_width()); height=max(1,self.tree.winfo_height())
            display=self.tree.cget('displaycolumns')
            if display in ('#all', ('#all',), ''): display=list(self.tree.cget('columns'))
            else: display=list(display)
            kids=list(self.tree.get_children())
            visible=[]
            for iid in kids:
                try:
                    bb=self.tree.bbox(iid)
                    if bb and bb[1]+bb[3]>=0 and bb[1]<=height: visible.append(iid)
                except Exception: pass
            sample=visible[0] if visible else (kids[0] if kids else None)
            vused=0
            if sample:
                for col in display[:-1]:
                    try: bb=self.tree.bbox(sample,col)
                    except Exception: bb=''
                    if not bb: continue
                    x=bb[0]+bb[2]-1
                    if 0 < x < width:
                        ln=self._line(self.vlines,vused,self.column_color); ln.place(x=x,y=0,width=1,height=height); vused+=1
            for ln in self.vlines[vused:]: ln.place_forget()
            hused=0
            # Header/data boundary from first visible row's y position.
            if visible:
                try:
                    bb=self.tree.bbox(visible[0])
                    if bb and bb[1]>1:
                        ln=self._line(self.hlines,hused,self.header_color); ln.place(x=0,y=max(0,bb[1]-2),width=width,height=2); hused+=1
                except Exception: pass
            for iid in visible:
                try: bb=self.tree.bbox(iid)
                except Exception: bb=''
                if not bb: continue
                y=bb[1]+bb[3]-2
                if 0<y<height:
                    ln=self._line(self.hlines,hused,self.row_color); ln.place(x=0,y=y,width=width,height=2); hused+=1
            for ln in self.hlines[hused:]: ln.place_forget()
        except Exception:
            return
        try: self.tree.after(350,self.update)
        except Exception: self._dead=True


def attach_tree_grid(tree: ttk.Treeview, *, light: bool=False):
    if getattr(tree, '_barkav_line_free_187', False):
        old = getattr(tree, '_barkav_grid_overlay', None)
        if old is not None:
            old._dead = True
            for line in list(getattr(old, 'vlines', [])) + list(getattr(old, 'hlines', [])):
                line.destroy()
        tree._barkav_grid_overlay = None
        return None
    old=getattr(tree,'_barkav_grid_overlay',None)
    if old: return old
    ov=TreeGridOverlay(tree,
        column_color='#D7DEE6' if light else '#29415A',
        row_color='#B8C5D2' if light else '#47617A',
        header_color='#9FB1C2' if light else '#587895')
    tree._barkav_grid_overlay=ov
    return ov


def attach_grids_recursive(root: tk.Misc, *, light: bool=False):
    stack=[root]
    while stack:
        w=stack.pop()
        try: stack.extend(w.winfo_children())
        except Exception: pass
        if isinstance(w,ttk.Treeview): attach_tree_grid(w,light=light)


def install_smarttable_export_dropdown(table, *, values=('انتخاب فرمت خروجی','پرینت','Excel','PDF')):
    """Replace the three legacy output icon buttons in one SmartTable toolbar."""
    if getattr(table,'_barkav_export_combo',None): return table._barkav_export_combo
    try: bar=table.winfo_children()[0]
    except Exception: return None
    for w in list(bar.winfo_children()):
        try:
            if isinstance(w,ttk.Button) and str(w.cget('text')) in {'📊','📄','🖨'}: w.destroy()
        except Exception: pass
    var=tk.StringVar(master=table,value=values[0])
    combo=ttk.Combobox(bar,textvariable=var,state='readonly',values=list(values),width=19,justify='right')
    combo.pack(side='left',padx=3)
    def chosen(_=None):
        val=var.get()
        try:
            if val=='Excel': table.export_excel()
            elif val=='PDF': table.export_pdf()
            elif val=='پرینت': table.print_report()
        finally:
            try: var.set(values[0])
            except Exception: pass
    combo.bind('<<ComboboxSelected>>',chosen,add='+')
    table._barkav_export_combo=combo; table._barkav_export_var=var
    return combo


def themed_brand_image(source: str | Path, *, fg: str, bg: str, size=(250,58)):
    """Return PIL RGBA image recolored to theme; caller creates ImageTk.PhotoImage."""
    from PIL import Image
    im=Image.open(source).convert('RGBA')
    # Convert original white background to transparent and dark logo pixels to requested foreground.
    fr,fgc,fb = tuple(int(fg[i:i+2],16) for i in (1,3,5))
    px=im.load()
    for y in range(im.height):
        for x in range(im.width):
            r,g,b,a=px[x,y]
            lum=(r+g+b)//3
            if lum>242:
                px[x,y]=(0,0,0,0)
            else:
                # preserve antialiasing using darkness as alpha
                alpha=max(0,min(255,255-lum))
                px[x,y]=(fr,fgc,fb,alpha)
    im.thumbnail(size,Image.Resampling.LANCZOS)
    return im


TGJU_DOLLAR_URL='https://www.tgju.org/profile/price_dollar_rl'


def fetch_tgju_usd_toman(timeout: float=8.0) -> tuple[int,str]:
    """Fetch free USD rate from TGJU. TGJU page states the value in IRR; return toman."""
    req=urllib.request.Request(TGJU_DOLLAR_URL,headers={
        'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 BARKAV/18.3',
        'Accept-Language':'fa-IR,fa;q=0.9,en;q=0.6',
    })
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        html=resp.read().decode('utf-8','ignore')
    # Stable profile fragments seen on the official page. Try several forms so minor markup shifts don't break it.
    patterns=[
        r'نرخ\s*فعلی\s*</[^>]+>\s*<[^>]+>\s*([0-9۰-۹٠-٩,٬]+)',
        r'نرخ\s*فعلی\s*[:：]*\s*</?[^>]*>\s*([0-9۰-۹٠-٩,٬]{5,})',
        r'در\s*حال\s*حاضر\s*قیمت\s*هر\s*دلار\s*([0-9۰-۹٠-٩,٬]+)\s*ریال',
        r'نرخ\s*فعلی\s*[:：]+\s*([0-9۰-۹٠-٩,٬]{5,})',
    ]
    raw=''
    for pat in patterns:
        m=re.search(pat,html,re.I|re.S)
        if m: raw=m.group(1); break
    if not raw:
        # Extract text by stripping tags and use the same official wording.
        text=re.sub(r'<[^>]+>',' ',html); text=re.sub(r'\s+',' ',text)
        m=re.search(r'نرخ فعلی\s*[:：]*\s*([0-9۰-۹٠-٩,٬]{5,})',text)
        if not m: m=re.search(r'در حال حاضر قیمت هر دلار\s*([0-9۰-۹٠-٩,٬]+)\s*ریال',text)
        if m: raw=m.group(1)
    rial=parse_int(raw)
    if rial<=0: raise ValueError('نرخ فعلی دلار در صفحه TGJU پیدا نشد.')
    toman=round(rial/10)
    return toman, datetime.now().isoformat(timespec='seconds')

# ---- Extracted from ui_stage18_4.py ----

import tkinter as tk
from tkinter import ttk
from pathlib import Path



def attach_tree_grid_184(tree: ttk.Treeview, *, light: bool=False):
    """18.4 grid: horizontal row separators remain readable; verticals are intentionally very faint."""
    if getattr(tree, '_barkav_line_free_187', False):
        old = getattr(tree, '_barkav_grid_overlay', None)
        if old is not None:
            old._dead = True
            for line in list(getattr(old, 'vlines', [])) + list(getattr(old, 'hlines', [])):
                line.destroy()
        tree._barkav_grid_overlay = None
        return None
    old=getattr(tree,'_barkav_grid_overlay',None)
    column='#EEF1F4' if light else '#122436'
    row='#BAC6D2' if light else '#47617A'
    header='#9FAFBD' if light else '#587895'
    if old:
        try:
            old.column_color=column; old.row_color=row; old.header_color=header; old.schedule()
        except Exception: pass
        return old
    ov=TreeGridOverlay(tree,column_color=column,row_color=row,header_color=header)
    tree._barkav_grid_overlay=ov
    return ov


def enable_tree_checkboxes(tree: ttk.Treeview):
    """Give any Treeview a Data-Entry-like checkbox selection column without touching its values tuple.

    Uses ttk's #0 tree column, so existing code that indexes item(values) remains 100% compatible.
    """
    if getattr(tree,'_barkav_checkboxes_184',False): return tree
    # PendingTable already owns a dedicated checkbox/value column and click behavior.
    parent=getattr(tree,'master',None)
    if parent is not None and hasattr(parent,'toggle_all') and hasattr(parent,'_sync_checks'):
        return tree
    try:
        show=str(tree.cget('show') or '')
        tokens=set(show.split())
        tokens.update(('tree','headings'))
        tree.configure(show='tree headings')
        tree.heading('#0',text='☐',anchor='center')
        tree.column('#0',width=46,minwidth=42,stretch=False,anchor='center')
    except Exception:
        return tree

    def sync(*_):
        try:
            selected=set(tree.selection()); kids=tree.get_children('')
            for iid in kids: tree.item(iid,text='☑' if iid in selected else '☐')
            tree.heading('#0',text='☑' if kids and len(selected)==len(kids) else '☐')
        except Exception: pass

    def toggle_all():
        try:
            kids=tree.get_children(''); sel=tree.selection()
            if kids and len(sel)==len(kids): tree.selection_remove(sel)
            else: tree.selection_set(kids)
            sync()
        except Exception: pass

    def click(ev):
        try:
            if tree.identify_column(ev.x)!='#0':
                tree.after_idle(sync); return None
            iid=tree.identify_row(ev.y)
            if not iid: return 'break'
            sel=set(tree.selection())
            if iid in sel: tree.selection_remove(iid)
            else: tree.selection_add(iid)
            tree.focus(iid); sync(); return 'break'
        except Exception:
            return None

    try: tree.heading('#0',command=toggle_all)
    except Exception: pass
    tree.bind('<Button-1>',click,add='+')
    tree.bind('<<TreeviewSelect>>',lambda e:sync(),add='+')
    tree.bind('<Configure>',lambda e:tree.after_idle(sync),add='+')
    tree._barkav_checkboxes_184=True; tree._barkav_checkbox_sync=sync
    tree.after_idle(sync)
    return tree


def attach_table_visuals_recursive(root: tk.Misc, *, light: bool=False):
    stack=[root]
    while stack:
        w=stack.pop()
        try: stack.extend(w.winfo_children())
        except Exception: pass
        if isinstance(w,ttk.Treeview):
            attach_tree_grid_184(w,light=light)
            enable_tree_checkboxes(w)


def retarget_smarttable_instance_184(table, *, font_size: int=11, light: bool=False):
    """Keep legacy SmartTable behavior but make its font/numbers/check selection match 18.4."""
    if getattr(table,'_barkav_184_upgraded',False):
        try:
            attach_tree_grid_184(table.tree,light=light); enable_tree_checkboxes(table.tree)
        except Exception: pass
        return table
    tree=getattr(table,'tree',None)
    if not isinstance(tree,ttk.Treeview): return table
    try:
        st=ttk.Style(table)
        if getattr(table,'style_name',None): st.configure(table.style_name,font=('Segoe UI',font_size),rowheight=max(34,int(getattr(table,'row_height',34))))
        if getattr(table,'heading_style_name',None): st.configure(table.heading_style_name,font=('Segoe UI',max(9,font_size-1),'bold'))
    except Exception: pass

    # Wrap per-instance methods. This avoids changing any business/service code.
    orig_update=getattr(table,'_update_total',None)
    if callable(orig_update):
        def update_total_184(*a,**kw):
            res=orig_update(*a,**kw)
            try: table.total.set(fa(table.total.get()))
            except Exception: pass
            try:
                for iid in tree.get_children(''):
                    vals=list(tree.item(iid,'values') or ())
                    if vals: tree.item(iid,values=[fa(v) for v in vals])
            except Exception: pass
            try: tree.after_idle(tree._barkav_checkbox_sync)
            except Exception: pass
            return res
        table._update_total=update_total_184

    orig_apply=getattr(table,'apply_filter',None)
    if callable(orig_apply):
        def apply_filter_184(*a,**kw):
            res=orig_apply(*a,**kw)
            try:
                for iid in tree.get_children(''):
                    vals=list(tree.item(iid,'values') or ())
                    if vals: tree.item(iid,values=[fa(v) for v in vals])
            except Exception: pass
            try: table.total.set(fa(table.total.get()))
            except Exception: pass
            try: tree.after_idle(tree._barkav_checkbox_sync)
            except Exception: pass
            return res
        table.apply_filter=apply_filter_184

    orig_height=getattr(table,'change_row_height',None)
    if callable(orig_height):
        def change_row_height_184(delta):
            res=orig_height(delta)
            try:
                st=ttk.Style(table)
                if getattr(table,'style_name',None): st.configure(table.style_name,font=('Segoe UI',font_size))
                if getattr(table,'heading_style_name',None): st.configure(table.heading_style_name,font=('Segoe UI',max(9,font_size-1),'bold'))
            except Exception: pass
            return res
        table.change_row_height=change_row_height_184

    attach_tree_grid_184(tree,light=light); enable_tree_checkboxes(tree)
    table._barkav_184_upgraded=True
    try: table._update_total()
    except Exception: pass
    return table


def upgrade_smarttables_recursive_184(root: tk.Misc, *, font_size: int=11, light: bool=False):
    stack=[root]
    while stack:
        w=stack.pop()
        try: stack.extend(w.winfo_children())
        except Exception: pass
        if hasattr(w,'tree') and hasattr(w,'set_rows'):
            try: retarget_smarttable_instance_184(w,font_size=font_size,light=light)
            except Exception: pass


def build_brand_widget_184(parent, source: str|Path, *, bg: str, fg: str, compact: bool=False):
    """Theme-blended BARKAV brand with a larger readable Engineering & Construction line."""
    host=tk.Frame(parent,bg=bg,bd=0,highlightthickness=0)
    try:
        from PIL import Image, ImageTk
        im=Image.open(source).convert('RGBA')
        # Crop away the tiny source tagline; render it ourselves at a readable size.
        crop_h=max(1,int(im.height*0.82)); im=im.crop((0,0,im.width,crop_h))
        # Theme recolor, preserving antialiasing.
        fr,fgc,fb=tuple(int(fg[i:i+2],16) for i in (1,3,5)); px=im.load()
        for y in range(im.height):
            for x in range(im.width):
                r,g,b,a=px[x,y]; lum=(r+g+b)//3
                if lum>242: px[x,y]=(0,0,0,0)
                else: px[x,y]=(fr,fgc,fb,max(0,min(255,255-lum)))
        im.thumbnail((220 if compact else 245,43 if compact else 49),Image.Resampling.LANCZOS)
        photo=ImageTk.PhotoImage(im,master=parent);host._brand_photo=photo
        tk.Label(host,image=photo,bg=bg,bd=0).pack(anchor='w')
    except Exception:
        tk.Label(host,text='BARKAV',bg=bg,fg=fg,font=('Segoe UI',15,'bold')).pack(anchor='w')
    tk.Label(host,text='Engineering & Construction',bg=bg,fg=fg,
             font=('Segoe UI',9 if compact else 10,'bold')).pack(anchor='w',pady=(0,1))
    return host

# ---- Extracted from ui_stage18_5.py ----

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any



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
    if getattr(tree, '_barkav_line_free_187', False):
        old = getattr(tree, '_barkav_grid_overlay', None)
        if old is not None:
            old._dead = True
            for line in list(getattr(old, 'vlines', [])) + list(getattr(old, 'hlines', [])):
                line.destroy()
        tree._barkav_grid_overlay = None
        return None
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

# ---- Extracted from ui_stage18_6.py ----

import re
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any



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
    if getattr(tree, '_barkav_line_free_187', False):
        old = getattr(tree, '_barkav_grid_overlay', None)
        if old is not None:
            old._dead = True
            for line in list(getattr(old, 'vlines', [])) + list(getattr(old, 'hlines', [])):
                line.destroy()
        tree._barkav_grid_overlay = None
        return None
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

# ---- Extracted from ui_stage18_7.py ----

import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path
import sys

from barkav_themes.engine import ThemeSelection, apply_ttk_theme, legacy_palette
from barkav_themes.tokens import get_theme
from v18_store import load_ui


BACKGROUND_COLORS_187 = {
    'سرمه‌ای': {'dark': '#071525', 'light': '#EAF2FA'},
    'ذغالی': {'dark': '#1F2937', 'light': '#F1F3F5'},
    'سبزآبی': {'dark': '#0B3036', 'light': '#E8F5F2'},
    'بنفش خاکستری': {'dark': '#28243D', 'light': '#F1EEFA'},
}

FONT_CATALOG_187 = {
    'IRANSansX': 'ایران سنس X', 'IRANYekanX': 'ایران یکان X',
    'Yekan Bakh': 'یکان بخ', 'Vazirmatn': 'وزیرمتن', 'Dana': 'دانا',
    'Peyda': 'پیدا', 'Estedad': 'استعداد', 'Kalameh': 'کلمب',
}
FONT_ASSET_DIRS_187 = tuple(Path(__file__).resolve().parents[2] / name for name in ('assets/fonts', 'fonts', 'new theme/fonts'))
_FONT_ASSETS_REGISTERED_187 = False

def _register_font_assets_187() -> None:
    global _FONT_ASSETS_REGISTERED_187
    if _FONT_ASSETS_REGISTERED_187 or not sys.platform.startswith('win'):
        return
    _FONT_ASSETS_REGISTERED_187 = True
    try:
        import ctypes
        for directory in FONT_ASSET_DIRS_187:
            for path in directory.glob('*'):
                if path.suffix.lower() in {'.ttf', '.otf'}:
                    ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, 0)
    except (OSError, AttributeError):
        return

def installed_font_families_187(root: tk.Misc) -> tuple[str, ...]:
    _register_font_assets_187()
    try:
        return tuple(sorted({str(name).strip() for name in tkfont.families(root) if str(name).strip()}))
    except tk.TclError:
        return ()

def available_font_families_187(root: tk.Misc) -> tuple[str, ...]:
    installed = set(installed_font_families_187(root))
    requested = tuple(name for name in FONT_CATALOG_187 if name in installed)
    fallback = tuple(name for name in ('Segoe UI', 'Tahoma', 'Arial') if name in installed)
    if requested or fallback:
        return requested + tuple(name for name in fallback if name not in requested)
    try:
        return (str(tkfont.nametofont('TkDefaultFont', root=root).actual().get('family') or 'TkDefaultFont'),)
    except (tk.TclError, TypeError):
        return ('TkDefaultFont',)

def font_catalog_families_187(root: tk.Misc) -> tuple[str, ...]:
    """Return the complete user-facing catalog, including missing families."""
    available = available_font_families_187(root)
    return tuple(FONT_CATALOG_187) + tuple(name for name in available if name not in FONT_CATALOG_187)

def font_status_label_187(root: tk.Misc, family: str) -> str:
    label = font_display_name_187(family)
    if family in set(installed_font_families_187(root)):
        return label
    fallback = available_font_families_187(root)[0]
    return f'{label} (مفقود؛ fallback: {font_display_name_187(fallback)})'

def missing_font_assets_187(root: tk.Misc) -> tuple[str, ...]:
    installed = set(installed_font_families_187(root))
    return tuple(name for name in FONT_CATALOG_187 if name not in installed)

def font_display_name_187(family: str) -> str:
    return FONT_CATALOG_187.get(family, family)

def resolve_font_family_187(root: tk.Misc, requested: str | None = None) -> str:
    available = available_font_families_187(root)
    return str(requested) if requested in available else available[0]

def available_font_weights_187(root: tk.Misc, family: str) -> tuple[int, ...]:
    return (400, 700)

def resolve_font_weight_187(root: tk.Misc, family: str, requested: int | str | None = None) -> int:
    available = available_font_weights_187(root, family)
    try:
        value = int(requested or 400)
    except (TypeError, ValueError):
        value = 400
    return min(available, key=lambda candidate: abs(candidate - value))


def theme_id_187() -> int:
    """Return a safe UI-only theme selection; project/financial data is untouched."""
    try:
        return get_theme(load_ui().get('theme_id', 1)).theme_id
    except Exception:
        return 1


def theme_selection_187(light: bool | None = None) -> ThemeSelection:
    ui = load_ui()
    if light is None:
        light = str(ui.get('appearance') or 'dark').lower() == 'light'
    return ThemeSelection(theme_id_187(), 'light' if light else 'dark').normalized()


def palette_187(light: bool | None = None) -> dict[str, str]:
    selected = theme_selection_187(light)
    palette = legacy_palette(selected)
    choice = str(load_ui().get('background_color') or 'پیش‌فرض').strip()
    if choice in BACKGROUND_COLORS_187:
        palette['bg'] = BACKGROUND_COLORS_187[choice]['light' if selected.mode == 'light' else 'dark']
    return palette


def theme_metrics_187() -> dict[str, int]:
    return dict(get_theme(theme_id_187()).metrics)


def style_ttk_187(
    root: tk.Misc,
    *,
    light: bool | None = None,
    font_size: int = 10,
    row_height: int | None = None,
) -> None:
    selection = theme_selection_187(light)
    metrics = get_theme(selection.theme_id).metrics
    apply_ttk_theme(
        root,
        selection,
        palette_override=palette_187(light),
        font_family=resolve_font_family_187(root, load_ui().get('font_family')),
        font_weight=resolve_font_weight_187(root, load_ui().get('font_family'), load_ui().get('font_weight')),
        font_size=font_size,
        row_height=row_height or metrics['row_height'],
    )
    # Existing 18.6 widgets use this Tcl flag to choose their light palette.
    try:
        root.tk.call('set', '::barkav_light_186', '1' if selection.mode == 'light' else '0')
        root.tk.call('set', '::barkav_light_187', '1' if selection.mode == 'light' else '0')
    except Exception:
        pass


def activate_theme_bridge_187() -> None:
    """Point the inherited 18.6 presentation layer at the selected 18.7 tokens.

    This runs only in the separate 18.7 process.  It does not edit or persist
    anything in the 18.6 source tree.
    """
    palette_186 = palette_187
    style_ttk_186 = style_ttk_187
    current = palette_187()
    DARK_186.update(current)
    LIGHT_186.update(palette_187(True))
    # Charts are inherited from these stable layers and read their module-level
    # semantic palette while drawing.
    for module_name in ('dashboard_stage16_3', 'dashboard_stage17_5'):
        try:
            module = __import__(module_name)
            module.DARK.update(current)
        except Exception:
            pass


# Re-export the accepted 18.6 helpers.  Their palette lookup is redirected by
# activate_theme_bridge_187, while all business/data behavior remains inherited.
attach_tree_grid_187 = attach_tree_grid_186
bind_persian_digits = bind_persian_digits
build_brand_widget_187 = build_brand_widget_186
convert_tree_currency_187 = convert_tree_currency_186
currency_unit_187 = currency_unit_186
format_currency_187 = format_currency_186
normalize_floor_structure_187 = normalize_floor_structure_186
parse_display_amount_187 = parse_display_amount_186
retarget_smarttable_187 = retarget_smarttable_186
DashboardCard187 = DashboardCard186
CompactMetric187 = CompactMetric186
