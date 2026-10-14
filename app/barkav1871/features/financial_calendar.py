from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

try:
    import jdatetime
except ModuleNotFoundError:  # Reported by the canonical launcher before UI opens.
    jdatetime = None

from barkav1871.design.controls import en, fa
from barkav1871.design import ThemeManager


def _require_jdatetime() -> None:
    if jdatetime is None:
        raise RuntimeError("برای تقویم مالی، بستهٔ jdatetime را نصب کنید.")


@dataclass(frozen=True)
class FinancialEvent:
    due_date: str
    due_date_shamsi: str
    kind: str
    title: str
    amount: int
    direction: str
    details: str = ''


EVENT_LABELS = {
    'CHEQUE': 'چک',
    'RECEIVABLE': 'مطالبه/قسط خریدار',
    'LOAN': 'قسط تسهیلات',
}


def _shamsi_from_gregorian(value: str) -> str:
    try:
        converted = jdatetime.date.fromgregorian(date=date.fromisoformat(str(value)[:10]))
        return f'{converted.year:04d}/{converted.month:02d}/{converted.day:02d}'
    except Exception:
        return ''


def _normalize_shamsi(value: Any, fallback_gregorian: str = '') -> str:
    raw = en(str(value or '')).replace('-', '/').strip()
    parts = raw.split('/')
    if len(parts) == 3:
        try:
            return f'{int(parts[0]):04d}/{int(parts[1]):02d}/{int(parts[2]):02d}'
        except Exception:
            pass
    return _shamsi_from_gregorian(fallback_gregorian)


def collect_financial_events(service, days: int = 370) -> list[FinancialEvent]:
    """Build one read-only financial event stream from existing SQLite services."""
    events: list[FinancialEvent] = []
    for row in service.upcoming_cheques(days):
        due = str(row.get('due_date') or '')[:10]
        events.append(FinancialEvent(
            due, _normalize_shamsi(row.get('due_date_shamsi'), due), 'CHEQUE',
            str(row.get('description') or row.get('expense_description') or 'سررسید چک'),
            int(row.get('amount') or 0), 'OUT',
            str(row.get('receiver_name') or row.get('issuer_bank') or ''),
        ))
    buyer_rows = list(service.upcoming_buyer_installments(days))
    try:
        buyer_rows.extend(service.overdue_buyer_installments())
    except Exception:
        pass
    seen_buyer: set[str] = set()
    for row in buyer_rows:
        row_id = str(row.get('installment_id') or '')
        if row_id and row_id in seen_buyer:
            continue
        seen_buyer.add(row_id)
        due = str(row.get('due_date') or '')[:10]
        events.append(FinancialEvent(
            due, _normalize_shamsi(row.get('due_date_shamsi'), due), 'RECEIVABLE',
            f"وصول واحد {row.get('unit_number') or '-'}",
            int(row.get('outstanding') or 0), 'IN',
            str(row.get('buyer_name') or ''),
        ))
    for row in service.upcoming_loan_installments(days):
        due = str(row.get('due_date') or '')[:10]
        events.append(FinancialEvent(
            due, _normalize_shamsi(row.get('due_date_shamsi'), due), 'LOAN',
            str(row.get('loan_title') or 'قسط تسهیلات'),
            int(row.get('outstanding') or 0), 'OUT',
            str(row.get('lender_name') or ''),
        ))
    return sorted(events, key=lambda item: (item.due_date, item.kind, item.title))


def upcoming_events(service, days: int = 30) -> list[FinancialEvent]:
    today = date.today()
    output = []
    for event in collect_financial_events(service, max(31, days)):
        try:
            delta = (date.fromisoformat(event.due_date) - today).days
        except Exception:
            continue
        if 0 <= delta <= days:
            output.append(event)
    return output


def _format_amount(value: int) -> str:
    return fa(f'{int(value or 0):,}')


class FinancialMessagesDialog(tk.Toplevel):
    def __init__(self, parent, service, *, startup: bool = False):
        super().__init__(parent)
        self.events = upcoming_events(service, 30)
        self.title('پیام‌های مالی ۳۰ روز آینده')
        self.geometry('980x560')
        self.minsize(780, 460)
        self.transient(parent)
        p = ThemeManager().palette
        self.configure(bg=p['bg'])
        head = tk.Frame(self, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
        head.pack(fill='x', padx=10, pady=10)
        title = 'یادآوری شروع برنامه' if startup else 'پیام‌ها و سررسیدهای مالی'
        tk.Label(head, text=title, bg=p['surface'], fg=p['text'],
                 font=('Segoe UI', 14, 'bold')).pack(side='right', padx=12, pady=10)
        tk.Button(head, text='تقویم بزرگ', command=lambda: FinancialCalendarDialog(parent, service),
                  bg=p['blue'], fg='#FFFFFF', relief='flat', padx=15, pady=7).pack(side='left', padx=8)
        summary = self._summary_text()
        tk.Label(self, text=summary, bg=p['panel2'], fg=p['text'], anchor='e', justify='right',
                 font=('Segoe UI', 10, 'bold'), padx=12, pady=8).pack(fill='x', padx=10)
        tree = ttk.Treeview(
            self,
            columns=('date', 'kind', 'title', 'details', 'amount', 'direction'),
            show='headings',
        )
        headings = [
            ('date', 'سررسید', 120), ('kind', 'نوع', 145), ('title', 'عنوان', 250),
            ('details', 'طرف/جزئیات', 175), ('amount', 'مبلغ (تومان)', 145),
            ('direction', 'جریان', 80),
        ]
        for key, label, width in headings:
            tree.heading(key, text=label, anchor='e')
            tree.column(key, width=width, anchor='e')
        tree.configure(displaycolumns=tuple(reversed([x[0] for x in headings])))
        tree.pack(fill='both', expand=True, padx=10, pady=10)
        colors = ThemeManager().selection
        palette = ThemeManager().palette
        tree.tag_configure('CHEQUE', foreground=palette['red'])
        tree.tag_configure('RECEIVABLE', foreground=palette['green'])
        tree.tag_configure('LOAN', foreground=palette['orange'])
        _ = colors
        for index, event in enumerate(self.events):
            tree.insert('', 'end', iid=str(index), tags=(event.kind,), values=(
                fa(event.due_date_shamsi), EVENT_LABELS[event.kind], event.title,
                event.details or '-', _format_amount(event.amount),
                'ورودی' if event.direction == 'IN' else 'خروجی',
            ))
        if not self.events:
            tree.insert('', 'end', values=('-', '-', 'رویداد مالی در ۳۰ روز آینده ثبت نشده است.', '-', '-', '-'))

    def _summary_text(self) -> str:
        counts = {key: 0 for key in EVENT_LABELS}
        for event in self.events:
            counts[event.kind] += 1
        return (
            f"۳۰ روز آینده: {fa(len(self.events))} رویداد — "
            f"{fa(counts['CHEQUE'])} چک، {fa(counts['RECEIVABLE'])} مطالبه، "
            f"{fa(counts['LOAN'])} قسط تسهیلات"
        )


class FinancialCalendarDialog(tk.Toplevel):
    DAYS_FA = ('شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه')
    MONTHS_FA = (
        '', 'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
        'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند',
    )

    def __init__(self, parent, service):
        _require_jdatetime()
        super().__init__(parent)
        self.title('تقویم مالی پروژه — BARKAV 18.7.1')
        self.geometry('1180x790')
        self.minsize(940, 660)
        self.transient(parent)
        self.events = collect_financial_events(service, 370)
        self.by_day: dict[str, list[FinancialEvent]] = {}
        for event in self.events:
            self.by_day.setdefault(event.due_date_shamsi, []).append(event)
        today = jdatetime.date.today()
        self.year, self.month = today.year, today.month
        self.search = tk.StringVar()
        self.month_title = tk.StringVar()
        self.selected_title = tk.StringVar(value='برای نمایش جزئیات، یک روز را انتخاب کنید.')
        self._build()
        self.render_month()

    def _build(self):
        p = ThemeManager().palette
        self.configure(bg=p['bg'])
        nav = tk.Frame(self, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
        nav.pack(fill='x', padx=10, pady=(10, 6))
        tk.Button(nav, text='ماه بعد  ←', command=lambda: self.move_month(1),
                  bg=p['glass'], fg=p['text'], relief='flat', padx=12, pady=7).pack(side='left', padx=6, pady=6)
        tk.Button(nav, text='→  ماه قبل', command=lambda: self.move_month(-1),
                  bg=p['glass'], fg=p['text'], relief='flat', padx=12, pady=7).pack(side='left', padx=2, pady=6)
        tk.Label(nav, textvariable=self.month_title, bg=p['surface'], fg=p['text'],
                 font=('Segoe UI', 15, 'bold')).pack(side='right', padx=14)
        entry = ttk.Entry(nav, textvariable=self.search, justify='right', width=18)
        entry.pack(side='right', padx=5, pady=8)
        entry.bind('<Return>', lambda _event: self.search_date(), add='+')
        tk.Button(nav, text='جست‌وجوی ماه/روز', command=self.search_date,
                  bg=p['blue'], fg='#FFFFFF', relief='flat', padx=10, pady=6).pack(side='right', padx=4)
        tk.Button(nav, text='امروز', command=self.go_today,
                  bg=p['glass'], fg=p['text'], relief='flat', padx=10, pady=6).pack(side='right', padx=4)

        self.grid_host = tk.Frame(self, bg=p['bg'])
        self.grid_host.pack(fill='both', expand=True, padx=10, pady=4)
        for column in range(7):
            self.grid_host.grid_columnconfigure(column, weight=1, uniform='calendar')
        for row in range(7):
            self.grid_host.grid_rowconfigure(row, weight=1)

        details = tk.Frame(self, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
        details.pack(fill='x', padx=10, pady=(4, 10))
        tk.Label(details, textvariable=self.selected_title, bg=p['panel2'], fg=p['text'],
                 anchor='e', font=('Segoe UI', 10, 'bold'), padx=8, pady=6).pack(fill='x')
        self.details_tree = ttk.Treeview(
            details, columns=('kind', 'title', 'details', 'amount', 'direction'),
            show='headings', height=5,
        )
        for key, label, width in [
            ('kind', 'نوع', 145), ('title', 'عنوان', 300), ('details', 'جزئیات', 220),
            ('amount', 'مبلغ (تومان)', 160), ('direction', 'جریان', 85),
        ]:
            self.details_tree.heading(key, text=label, anchor='e')
            self.details_tree.column(key, width=width, anchor='e')
        self.details_tree.configure(displaycolumns=('direction', 'amount', 'details', 'title', 'kind'))
        self.details_tree.pack(fill='x', padx=6, pady=6)

    @staticmethod
    def _month_days(year: int, month: int) -> int:
        if month <= 6:
            return 31
        if month <= 11:
            return 30
        return 30 if jdatetime.date(year, 1, 1).isleap() else 29

    def render_month(self, selected_day: int | None = None):
        p = ThemeManager().palette
        for child in self.grid_host.winfo_children():
            child.destroy()
        self.month_title.set(f'{self.MONTHS_FA[self.month]} {fa(self.year)}')
        for index, label in enumerate(self.DAYS_FA):
            column = 6 - index
            tk.Label(self.grid_host, text=label, bg=p['panel2'], fg=p['text'],
                     font=('Segoe UI', 9, 'bold'), pady=6).grid(
                         row=0, column=column, sticky='nsew', padx=2, pady=2
                     )
        first_g = jdatetime.date(self.year, self.month, 1).togregorian()
        saturday_index = (first_g.weekday() + 2) % 7
        for day in range(1, self._month_days(self.year, self.month) + 1):
            slot = saturday_index + day - 1
            week, day_index = divmod(slot, 7)
            column = 6 - day_index
            sh = f'{self.year:04d}/{self.month:02d}/{day:02d}'
            events = self.by_day.get(sh, [])
            kinds = {event.kind for event in events}
            if 'CHEQUE' in kinds:
                accent = p['red']
            elif 'LOAN' in kinds:
                accent = p['orange']
            elif 'RECEIVABLE' in kinds:
                accent = p['green']
            else:
                accent = p['muted']
            today = jdatetime.date.today()
            active = selected_day == day or (today.year, today.month, today.day) == (self.year, self.month, day)
            text = fa(day)
            if events:
                text += f'\n{fa(len(events))} رویداد'
            button = tk.Button(
                self.grid_host, text=text, command=lambda value=day: self.select_day(value),
                bg=p['raised'] if active and 'raised' in p else (p['panel2'] if active else p['panel']),
                fg=accent if events else p['text'], activebackground=p['glass'],
                activeforeground=p['text'], relief='flat', bd=0,
                highlightbackground=accent if events else p['line'], highlightthickness=2 if events else 1,
                font=('Segoe UI', 10, 'bold'), justify='center', cursor='hand2',
            )
            button.grid(row=week + 1, column=column, sticky='nsew', padx=2, pady=2)

    def select_day(self, day: int):
        self.render_month(day)
        sh = f'{self.year:04d}/{self.month:02d}/{day:02d}'
        rows = self.by_day.get(sh, [])
        self.selected_title.set(f'{fa(sh)} — {fa(len(rows))} رویداد مالی')
        for item in self.details_tree.get_children():
            self.details_tree.delete(item)
        for index, event in enumerate(rows):
            self.details_tree.insert('', 'end', iid=str(index), values=(
                EVENT_LABELS[event.kind], event.title, event.details or '-',
                _format_amount(event.amount), 'ورودی' if event.direction == 'IN' else 'خروجی',
            ))

    def move_month(self, delta: int):
        value = self.year * 12 + self.month - 1 + int(delta)
        self.year, zero_month = divmod(value, 12)
        self.month = zero_month + 1
        self.render_month()

    def go_today(self):
        today = jdatetime.date.today()
        self.year, self.month = today.year, today.month
        self.render_month(today.day)
        self.select_day(today.day)

    def search_date(self):
        raw = en(self.search.get()).replace('-', '/').strip()
        parts = [part for part in raw.split('/') if part]
        try:
            if len(parts) not in (2, 3):
                raise ValueError
            year, month = int(parts[0]), int(parts[1])
            day = int(parts[2]) if len(parts) == 3 else None
            if not 1 <= month <= 12 or (day is not None and not 1 <= day <= self._month_days(year, month)):
                raise ValueError
        except Exception:
            messagebox.showwarning('جست‌وجوی تقویم', 'تاریخ را به شکل ۱۴۰۵/۰۵ یا ۱۴۰۵/۰۵/۲۰ وارد کنید.', parent=self)
            return
        self.year, self.month = year, month
        self.render_month(day)
        if day is not None:
            self.select_day(day)
