from __future__ import annotations

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

        # ماه و سال هر دو مستقیم انتخاب می‌شوند - نه فقط با ◀/▶ ورق زدن، که برای
        # پرش چند سالی دور و دراز است.
        picker = ttk.Frame(nav); picker.pack(expand=True)
        self.month_var = tk.StringVar(value=self.MONTHS[self.month - 1])
        month_combo = ttk.Combobox(picker, textvariable=self.month_var, values=self.MONTHS,
                                   state='readonly', width=9, justify='center')
        month_combo.pack(side='right', padx=(3, 0))
        month_combo.bind('<<ComboboxSelected>>', lambda _e: self._month_picked())

        self.year_var = tk.StringVar(value=str(self.year).translate(_FA_OUT))
        year_entry = ttk.Entry(picker, textvariable=self.year_var, width=5, justify='center')
        year_entry.pack(side='right')
        year_entry.bind('<Return>', lambda _e: self._year_typed())
        year_entry.bind('<FocusOut>', lambda _e: self._year_typed())

        self.grid = ttk.Frame(self.body); self.grid.pack(pady=(7,0))
        self._render()

    def _today(self):
        self.year, self.month, self.day = _jalali_today(); self._render()

    def _move_month(self, delta: int):
        m = self.month + delta; y = self.year
        while m > 12: m -= 12; y += 1
        while m < 1: m += 12; y -= 1
        self.year, self.month = y, m; self.day = 1; self._render()

    def _month_picked(self):
        self.month = self.MONTHS.index(self.month_var.get()) + 1
        self.day = 1
        self._render()

    def _year_typed(self):
        try:
            year = int(clean_int_text(self.year_var.get()) or self.year)
        except ValueError:
            year = self.year
        self.year = year
        self.day = 1
        self._render()

    def _render(self):
        for w in self.grid.winfo_children(): w.destroy()
        self.month_var.set(self.MONTHS[self.month - 1])
        self.year_var.set(str(self.year).translate(_FA_OUT))
        # RTL: شنبه (the Persian week's own first day) sits at the right
        # edge, هفته advancing leftward - mirror(i) = 6-i puts weekday index 0
        # in grid column 6 and index 6 in column 0.
        for i, name in enumerate(self.WEEKDAYS):
            ttk.Label(self.grid, text=name, width=4, anchor='center').grid(row=0, column=6 - i, padx=1, pady=1)
        # 1 Farvardin 1399 was Friday; use Gregorian conversion indirectly via Python weekday through revenue_service.
        from revenue_service import shamsi_to_gregorian
        import datetime as _dt
        g = _dt.date.fromisoformat(shamsi_to_gregorian(f'{self.year:04d}/{self.month:02d}/01'))
        # Python Monday=0. Persian week Saturday=0.
        start = (g.weekday() + 2) % 7
        days = _jalali_month_days(self.year, self.month)
        for d in range(1, days+1):
            idx = start + d - 1; row = 1 + idx//7; col = 6 - (idx % 7)
            b = ttk.Button(self.grid, text=str(d).translate(_FA_OUT), width=4, command=lambda dd=d:self._select(dd))
            b.grid(row=row, column=col, padx=1, pady=1)

    def _select(self, day: int):
        # Persian digits, matching every other date/identifier field this
        # product shows - normalize_shamsi()/en() already assume a StringVar
        # bound to a date may hold either script when reading it back.
        value = f'{self.year:04d}/{self.month:02d}/{day:02d}'.translate(_FA_OUT)
        if self.on_select: self.on_select(value)
        self.destroy()


def _persian_digits_while_typing(variable: tk.StringVar) -> None:
    """Show whatever is typed in Persian digits - a date is an identifier,
    not an amount, so no thousands-grouping."""

    state = {'busy': False}

    def reformat(*_args):
        if state['busy']:
            return
        converted = variable.get().translate(_FA_OUT)
        if converted != variable.get():
            state['busy'] = True
            try:
                variable.set(converted)
            finally:
                state['busy'] = False

    variable.trace_add('write', reformat)


class DateField(ttk.Frame):
    def __init__(self, parent, variable: tk.StringVar, width: int = 13, **kwargs):
        super().__init__(parent)
        self.variable = variable
        self.entry = ttk.Entry(self, textvariable=variable, width=width, justify='center', **kwargs)
        self.entry.pack(side='right', fill='x', expand=True)
        ttk.Button(self, text='📅', width=3, command=self.open_calendar).pack(side='left', padx=(2,0))
        self.entry.bind('<Double-1>', lambda e:self.open_calendar())
        # Attached after the Entry exists - a trace on a bare StringVar fires
        # ahead of the Entry's own sync trace, so Entry.get() would show a
        # stale value.
        _persian_digits_while_typing(variable)
        variable.set(variable.get())

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
