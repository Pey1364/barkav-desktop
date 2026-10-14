"""Contractor contracts: the wizard, the record window and the detail window.

Implements docs «مشخصات-تب-قراردادهای-پیمانکاران»: a five-window wizard, a
record window that mirrors the sales record's preview/details split, and a
double-click detail window with its payment receipts and exports.

Every visual decision comes from ``barkav_ui``; this module contributes no
colours, fonts or sizes of its own.
"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from barkav_ui.table import DataTable
from barkav_ui.theme import font as kit_font, metrics as kit_metrics, palette as kit_palette
from barkav_ui.window import BarkavWindow, BarkavWizard
from contractor_store_stage18_7 import (
    COST_GROUPS,
    OTHER_TITLE,
    ROWS_PER_PAGE,
    SUPPLY_FIELDS,
    SUPPLY_ROLES,
    balance,
    paid_total,
    reference_row,
    reference_titles,
    upsert_contract,
)
from project_plan_stage18_7 import COST_TYPES
from budget_rich_v163 import norm
from sales_claims_stage18_7 import (
    ShamsiDatePicker187,
    show_export_preview_187,
)
from ui_stage18_3 import en, fa, group_int_fa


DOCUMENT_FIELDS = (
    ('contract_file', 'بارگذاری فایل قرارداد نمونه'),
    ('summary_file', 'بارگذاری فایل قرارداد'),
    ('identity_file', 'بارگذاری مدارک هویتی'),
)

CONTRACTOR_FIELDS = (
    ('family_name', 'نام و نام خانوادگی'),
    ('nationality', 'ملیت'),
    ('national_id', 'کد ملی'),
    ('has_licence', 'مدرک شغلی'),
    ('phone', 'شماره تماس'),
    ('address', 'آدرس'),
)

TERM_FIELDS = (
    ('duration_months', 'مدت زمان (ماه)'),
    ('total_amount', 'مبلغ کل قرارداد (تومان)'),
)

ROW_COLUMNS = (
    ('no', 'ردیف'),
    ('description', 'شرح ردیف'),
    ('unit', 'واحد'),
    # A unit price, said so: what one metre or one day of this work costs.
    # The totals below are the same figure times the volume beside it.
    ('unit_price', 'مبلغ واحد قرارداد'),
    ('estimate_price', 'مبلغ واحد برآورد'),
    ('quantity', 'حجم قرارداد'),
    ('estimate_quantity', 'حجم برآورد'),
    ('line_total', 'مبلغ کل قرارداد'),
    ('estimate_total', 'مبلغ کل برآورد'),
)

# A column is as wide as its own heading needs, and no narrower than a grouped
# amount. Every cell used to be twelve characters, so the long headings were
# cut and the short ones sat in empty space.
#
# شرح ردیف is the exception: its heading is two words and its content is a
# trade - 'اجرت میلگردبندی سقف' - so it is sized for what goes in it.
ROW_WIDTHS = {key: max(11, len(label) + 2) for key, label in ROW_COLUMNS}
ROW_WIDTHS['description'] = 26
ROW_WIDTHS['no'] = 5

# The row cells that hold money, and so separate their thousands as they
# are typed. حجم is a quantity - 1914 square metres is not 1,914 tomans.
MONEY_ROW_KEYS = ('unit_price', 'estimate_price', 'line_total', 'estimate_total')
NUMERIC_ROW_KEYS = (*MONEY_ROW_KEYS, 'quantity', 'estimate_quantity')

PAYMENT_COLUMNS = (
    ('no', 'ردیف'),
    ('date', 'تاریخ'),
    ('amount', 'مبلغ واریزی (تومان)'),
    ('receiver', 'گیرنده'),
    ('issuer', 'صاحب حساب'),
)

# A6 (105x148mm), scaled down to a legible on-screen thumbnail rather than
# print-resolution pixels - this sits beside a table row, not on a page.
RECEIPT_THUMB_SIZE = (142, 200)

# The entered count includes both fixed end stages.  For example, four stages
# means: پیش پرداخت، مرحله اول، مرحله دوم، تحویل کار.
PAYMENT_STAGE_MIN_187 = 2
PAYMENT_STAGE_MAX_187 = 20
_PAYMENT_STAGE_ORDINALS_187 = (
    'اول', 'دوم', 'سوم', 'چهارم', 'پنجم', 'ششم', 'هفتم', 'هشتم', 'نهم',
    'دهم', 'یازدهم', 'دوازدهم', 'سیزدهم', 'چهاردهم', 'پانزدهم', 'شانزدهم',
    'هفدهم', 'هجدهم',
)


def payment_stage_labels_187(stage_count: Any) -> tuple[str, ...]:
    """Return fixed and variable contractor-payment labels in reading order."""

    try:
        count = int(en(str(stage_count or PAYMENT_STAGE_MIN_187)))
    except (TypeError, ValueError):
        count = PAYMENT_STAGE_MIN_187
    count = max(PAYMENT_STAGE_MIN_187, min(PAYMENT_STAGE_MAX_187, count))
    labels = ['پیش پرداخت']
    for index in range(count - 2):
        labels.append(f'مرحله {_PAYMENT_STAGE_ORDINALS_187[index]}')
    labels.append('تحویل کار')
    return tuple(labels)


def normalise_payment_schedule_187(stage_count: Any,
                                   schedule: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Resize a payment plan without losing typed fixed-stage values."""

    by_label = {
        str(item.get('label') or '').strip(): dict(item)
        for item in (schedule or [])
        if isinstance(item, dict)
    }
    rows: list[dict[str, Any]] = []
    for sequence_no, label in enumerate(payment_stage_labels_187(stage_count), 1):
        existing = by_label.get(label, {})
        rows.append({
            'sequence_no': sequence_no,
            'label': label,
            'due_date_shamsi': str(existing.get('due_date_shamsi') or ''),
            'amount': str(existing.get('amount') or ''),
        })
    return rows


def _amount(value: Any) -> str:
    try:
        raw = (en(str(value or '0')).replace(',', '').replace('٬', '')
               .replace('\u2009', '').replace(' ', '').strip())
        return group_int_fa(int(raw or 0))
    except (TypeError, ValueError):
        return fa(str(value or ''))


def _row_display_value_187(key: str, value: Any) -> str:
    if key in MONEY_ROW_KEYS:
        return _amount(value)
    if key in ('quantity', 'estimate_quantity'):
        return _format_persian_number_187(value)
    return str(value or '')


def _format_persian_number_187(value: Any) -> str:
    """Persian digits and three-digit grouping, preserving a partial decimal."""

    raw = (en(str(value or '')).replace(',', '').replace('٬', '').replace('٫', '.')
           .replace('\u2009', '').strip())
    if not raw:
        return ''
    sign = ''
    if raw[:1] in ('-', '+'):
        sign, raw = raw[0], raw[1:]
    if raw.count('.') > 1 or any(ch not in '0123456789.' for ch in raw):
        return fa(f'{sign}{raw}')
    whole, dot, fraction = raw.partition('.')
    if not whole and not dot:
        return fa(sign)
    try:
        grouped = f'{int(whole or 0):,}'
    except ValueError:
        return fa(f'{sign}{raw}')
    result = f'{sign}{grouped}{dot}{fraction}'
    return fa(result)


def group_number_while_typing_187(variable) -> None:
    """Format an editable numeric variable without losing typed digits."""

    state = {'busy': False}

    def reformat(*_args) -> None:
        if state['busy']:
            return
        formatted = _format_persian_number_187(variable.get())
        if formatted != variable.get():
            state['busy'] = True
            try:
                variable.set(formatted)
            finally:
                state['busy'] = False

    variable.trace_add('write', reformat)
    reformat()


def keep_numeric_cursor_at_end_187(entry) -> None:
    """After each edit/paste, leave the insertion point after the full number."""

    def move_to_end(_event=None) -> None:
        try:
            entry.after_idle(lambda: entry.icursor('end') if entry.winfo_exists() else None)
        except tk.TclError:
            pass

    entry.bind('<KeyRelease>', move_to_end, add='+')
    entry.bind('<<Paste>>', move_to_end, add='+')


def editable_text_box_187(parent, variable: tk.StringVar, *, height: int = 4) -> tk.Text:
    """A right-aligned, multiline editor kept in sync with its saved value."""

    p = kit_palette()
    editor = tk.Text(parent, height=height, wrap='word', undo=True, justify='right',
                     bg=p['input'], fg=p['text_primary'],
                     insertbackground=p['text_primary'], relief='solid', bd=1,
                     highlightthickness=1, highlightbackground=p['border'])
    editor.insert('1.0', variable.get())
    editor.edit_modified(False)
    state = {'busy': False}

    def from_editor(_event=None) -> None:
        if state['busy'] or not editor.edit_modified():
            return
        state['busy'] = True
        try:
            variable.set(editor.get('1.0', 'end-1c'))
            editor.edit_modified(False)
        finally:
            state['busy'] = False

    def from_variable(*_args) -> None:
        if state['busy'] or not editor.winfo_exists():
            return
        current = editor.get('1.0', 'end-1c')
        if current == variable.get():
            return
        state['busy'] = True
        try:
            editor.delete('1.0', 'end')
            editor.insert('1.0', variable.get())
            editor.edit_modified(False)
        finally:
            state['busy'] = False

    editor.bind('<<Modified>>', from_editor, add='+')
    variable.trace_add('write', from_variable)
    return editor


def schedule_amount_total_187(rows) -> int:
    total = 0
    for row in rows:
        value = row.get('amount')
        if hasattr(value, 'get'):
            value = value.get()
        total += int(_row_number(value))
    return total


def refresh_schedule_summary_187(label, total_variable, rows) -> None:
    """Show whether scheduled payments exactly cover the contract total."""

    if not label.winfo_exists():
        return
    scheduled = schedule_amount_total_187(rows)
    total = int(_row_number(total_variable.get()))
    label.configure(text=(
        f'جمع مراحل پرداخت: {_amount(scheduled)} تومان  |  '
        f'مبلغ قرارداد: {_amount(total)} تومان'
        + ('  ✓ برابر' if scheduled == total else '  ⚠ برابر نیست')
    ))


def _receipt_image_path(pending_id: str) -> str:
    """The receipt image attached to a deposit's own transaction.

    A deposit only knows the pending_id of the transaction that posted it
    (attach_payment_to_contract stamps it there). That transaction's receipt
    image lives in receipt_analyses regardless of the transaction's current
    status - get_pending_item's own row never carries it (that column only
    exists on the JOIN behind list_pending_reviews, which excludes anything
    already APPROVED, i.e. every transaction that could ever fund a deposit).
    Imported lazily - dashboard_stage18 is the legacy stack this module
    deliberately stays clear of at module scope.
    """

    pid = str(pending_id or '').strip()
    if not pid:
        return ''
    try:
        from dashboard_stage18 import DB
        analysis = DB.get_receipt_analysis(pid) or {}
        path = str(analysis.get('image_path') or '')
        return path if path and Path(path).exists() else ''
    except Exception:
        return ''


def _receipt_thumbnail(parent, pending_id: str):
    """An A7-proportioned preview of a deposit's receipt, or a placeholder."""

    p = kit_palette()
    box = tk.Frame(parent, bg=p['surface_alt'], width=RECEIPT_THUMB_SIZE[0],
                   height=RECEIPT_THUMB_SIZE[1], highlightbackground=p['border_subtle'],
                   highlightthickness=1)
    box.pack_propagate(False)
    path = _receipt_image_path(pending_id)
    image = None
    if path:
        try:
            from dashboard_stage18 import Image, ImageOps, ImageTk
            if Image is not None and ImageTk is not None:
                source = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
                source.thumbnail(RECEIPT_THUMB_SIZE)
                image = ImageTk.PhotoImage(source)
        except Exception:
            image = None
    label = tk.Label(box, bg=p['surface_alt'])
    if image is not None:
        label.configure(image=image)
        label.image = image  # keep a reference; Tk drops the pixels otherwise
    else:
        label.configure(text='رسیدی ثبت نشده', fg=p['text_secondary'], font=kit_font('small'),
                        wraplength=RECEIPT_THUMB_SIZE[0] - 10, justify='center')
    label.place(relx=0.5, rely=0.5, anchor='center')
    return box


class SearchableCombo187(ttk.Combobox):
    """A combobox whose list narrows as you type.

    The reference title list runs to hundreds of budget lines, so picking one
    from a plain dropdown is impractical; typing part of a title filters it.
    """

    def __init__(self, parent, *, values: list[str], textvariable, **kwargs):
        self._all_values = list(values)
        super().__init__(parent, values=self._all_values,
                         textvariable=textvariable, **kwargs)
        self.bind('<KeyRelease>', self._filter, add='+')

    def set_source(self, values: list[str]) -> None:
        self._all_values = list(values)
        self.configure(values=self._all_values)

    def _filter(self, event) -> None:
        if event.keysym in {'Up', 'Down', 'Return', 'Escape', 'Tab'}:
            return
        term = en(self.get()).strip().lower()
        if not term:
            self.configure(values=self._all_values)
            return
        matches = [v for v in self._all_values if term in en(v).lower()]
        self.configure(values=matches or self._all_values)
        self._show_matches()

    def _show_matches(self) -> None:
        """Drop the list open while typing.

        Narrowing a list nobody can see is not a search: without this the
        field looked like a plain text box until the arrow was clicked.
        """

        try:
            self.tk.call('ttk::combobox::Post', self)
            self.focus_set()
            self.icursor('end')
        except tk.TclError:
            pass


def _vertical_scroll_area(parent, *, bg: str) -> tk.Frame:
    """A plain vertical-scrolling frame, for content too small to worry about.

    Only اسناد/مشخصات/مفاد ever go through this - a handful of fields each -
    so the redraw a scrolling canvas puts on every ttk widget inside it on
    every notch stays small. ردیف‌های قرارداد, the one section large enough
    for that cost to matter, is never put in here - see render_row_grid_187.
    """

    holder = tk.Frame(parent, bg=bg)
    holder.pack(side='top', fill='both', expand=True)
    canvas = tk.Canvas(holder, bg=bg, highlightthickness=0)
    scrollbar = ttk.Scrollbar(holder, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side='left', fill='y')
    canvas.pack(side='right', fill='both', expand=True)

    inner = tk.Frame(canvas, bg=bg)
    item = canvas.create_window((0, 0), window=inner, anchor='ne')

    def fit(_event=None):
        canvas.configure(scrollregion=canvas.bbox('all'))

    def resize(event):
        canvas.coords(item, event.width, 0)
        canvas.itemconfigure(item, width=event.width)

    inner.bind('<Configure>', fit, add='+')
    canvas.bind('<Configure>', resize, add='+')
    canvas.bind('<MouseWheel>',
               lambda e: canvas.yview_scroll(int(-e.delta / 120), 'units'), add='+')
    return inner


def render_row_grid_187(parent, rows, *, start: int = 0, count: int | None = None,
                        on_reference=None, max_height: int | None = None) -> tk.Frame:
    """The contract's rows, editable, in both the wizard and the record window.

    One grid rather than two so a row reads the same wherever it is met, and
    so the record window can edit what the wizard entered - the شرح ردیف and
    the two unit prices are typed by hand, and the plan takes them from here.

    No rules between the cells: the boxes are their own boundary, and a grid
    drawn on top of them only made the table louder.

    ``max_height`` caps how tall the grid may grow before it scrolls
    vertically too - the record window shows every row at once, with no
    ``count`` to bound it, and a contract with many rows would otherwise push
    the sections below it off the window. Left unset, the grid is exactly as
    tall as its rows, which is what a wizard page already bounds through
    ``count``.
    """

    p = kit_palette()
    # Eight columns of contract detail are wider than the pane they sit in, and
    # in an RTL table the columns that fall off are the first ones - شرح ردیف
    # and the contract's own price. So the grid carries the table sideways
    # itself instead of overflowing its parent, which also stopped the form
    # above it re-laying out on every notch of the scroll wheel.
    holder = tk.Frame(parent, bg=p['bg'])
    holder.pack(fill='both', expand=True)
    canvas = tk.Canvas(holder, bg=p['bg'], highlightthickness=0)
    sideways = ttk.Scrollbar(holder, orient='horizontal', command=canvas.xview)
    vertical = None
    if max_height is not None:
        vertical = ttk.Scrollbar(holder, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=vertical.set)
        vertical.pack(side='left', fill='y')
    canvas.configure(xscrollcommand=sideways.set)
    sideways.pack(side='bottom', fill='x')
    canvas.pack(side='top', fill='both', expand=True)

    grid = tk.Frame(canvas, bg=p['bg'])
    window = canvas.create_window((0, 0), window=grid, anchor='ne')

    def fit(_event=None):
        canvas.update_idletasks()
        width = max(grid.winfo_reqwidth(), canvas.winfo_width())
        height = grid.winfo_reqheight()
        canvas.configure(scrollregion=(0, 0, width, height))
        canvas.configure(height=min(height, max_height) if max_height is not None else height)
        # anchor='ne' keeps the first column against the right edge, where an
        # RTL row starts; the item is placed there rather than at x=0.
        canvas.coords(window, width, 0)

    grid.bind('<Configure>', fit, add='+')
    canvas.bind('<Configure>', fit, add='+')
    canvas.bind('<Shift-MouseWheel>',
                lambda e: canvas.xview_scroll(int(-e.delta / 120), 'units'), add='+')
    if vertical is not None:
        canvas.bind('<MouseWheel>',
                    lambda e: canvas.yview_scroll(int(-e.delta / 120), 'units'), add='+')
    for column, (key, label) in enumerate(ROW_COLUMNS):
        position = len(ROW_COLUMNS) - 1 - column
        tk.Label(grid, text=label, bg=p['bg'], fg=p['text_secondary'],
                 font=kit_font('small'), anchor='e').grid(
                     row=0, column=position, sticky='ew', padx=3, pady=(0, 4))
        grid.columnconfigure(position, weight=1, minsize=ROW_WIDTHS[key] * 8)

    last = len(rows) if count is None else min(len(rows), start + count)
    for offset, index in enumerate(range(start, last)):
        row = rows[index]
        for column, (key, _label) in enumerate(ROW_COLUMNS):
            position = len(ROW_COLUMNS) - 1 - column
            if key == 'no':
                tk.Label(grid, text=fa(index + 1), bg=p['bg'], fg=p['text_secondary'],
                         font=kit_font('small')).grid(row=offset + 1, column=position,
                                                      sticky='ew', padx=3, pady=2)
                continue
            entry = ttk.Entry(grid, textvariable=row[key], justify='right',
                              width=ROW_WIDTHS[key])
            entry.grid(row=offset + 1, column=position, sticky='ew', padx=3, pady=2)
            if key in NUMERIC_ROW_KEYS:
                keep_numeric_cursor_at_end_187(entry)
            if key == 'description' and on_reference is not None:
                entry.bind('<FocusOut>', lambda _e, r=row: on_reference(r), add='+')
    grid.after_idle(fit)
    return grid


def _row_number(value: Any) -> float:
    try:
        raw = (en(str(value or '0')).replace(',', '').replace('٬', '').replace('٫', '.')
               .replace('\u2009', '').replace(' ', ''))
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def recompute_row_totals_187(row: dict[str, tk.StringVar]) -> None:
    for price_key, quantity_key, total_key in (
            ('unit_price', 'quantity', 'line_total'),
            ('estimate_price', 'estimate_quantity', 'estimate_total')):
        price = _row_number(row[price_key].get())
        quantity = _row_number(row[quantity_key].get())
        if price > 0 and quantity > 0:
            row[total_key].set(str(int(round(price * quantity))))


def _wire_row_total(row: dict[str, tk.StringVar]) -> None:
    """Keep each row total equal to its unit rate times its own quantity."""

    state = {'busy': False}

    def bind_formula(price_key: str, quantity_key: str, total_key: str) -> None:
        formula_active = {'value': False}

        def recompute(*_args) -> None:
            if state['busy']:
                return
            price = _row_number(row[price_key].get())
            quantity = _row_number(row[quantity_key].get())
            if price > 0 and quantity > 0:
                result = str(int(round(price * quantity)))
                state['busy'] = True
                try:
                    row[total_key].set(result)
                    formula_active['value'] = True
                finally:
                    state['busy'] = False
            elif formula_active['value']:
                state['busy'] = True
                try:
                    row[total_key].set('')
                    formula_active['value'] = False
                finally:
                    state['busy'] = False

        row[price_key].trace_add('write', recompute)
        row[quantity_key].trace_add('write', recompute)

    bind_formula('unit_price', 'quantity', 'line_total')
    bind_formula('estimate_price', 'estimate_quantity', 'estimate_total')


def blank_row_187(*, on_total_change=None) -> dict[str, tk.StringVar]:
    """One contract row's variables, with the money cells already grouped.

    ``plan_ref`` is carried but never shown: it is the plan line this row
    stands for, and it has to survive the operator renaming the row - which is
    the whole point of being able to rename it.

    ``on_total_change`` is called whenever this row's own مبلغ کل قرارداد
    changes - typed directly, or recomputed from its unit price - so the
    contract's own مبلغ کل قرارداد can be kept as the sum of its rows without
    each caller re-wiring every row itself.
    """

    row = {key: tk.StringVar() for key, _label in ROW_COLUMNS if key != 'no'}
    row['plan_ref'] = tk.StringVar()
    for key in NUMERIC_ROW_KEYS:
        group_number_while_typing_187(row[key])
    _wire_row_total(row)
    if on_total_change is not None:
        row['line_total'].trace_add('write', lambda *_a: on_total_change())
    return row


# --- pulling a contract's rows from the reference plan -----------------------
#
# Shared by the wizard and the record window, so choosing a فاز ساخت fills
# the row grid the same way wherever it is chosen.

def plan_phase_choices(rich) -> tuple[str, ...]:
    """The thirty-two build phases, numbered, as the plan holds them."""

    try:
        summary = rich.list_phase_summary() if rich is not None else []
    except Exception:
        summary = []
    return tuple(f"{fa(f'{int(row.get('phase_no') or 0):02d}')} — {row.get('phase') or ''}"
                 for row in summary)


def plan_phase_no(text: str) -> int | None:
    raw = str(text or '').split('—')[0].strip()
    try:
        return int(en(raw))
    except (TypeError, ValueError):
        return None


def phase_reference_titles_187(rich, phase_no: int | None,
                               cost_group: str = 'پیمانکار') -> list[str]:
    """Only offer catalogue contract titles represented by this phase."""

    if rich is None or phase_no is None:
        return [OTHER_TITLE]
    try:
        items = rich.list_phase_items(phase_no)
    except Exception:
        return [OTHER_TITLE]
    cost_type = COST_TYPES.get(cost_group, 'اجرت')
    planned = [item for item in items
               if str(item.get('cost_type') or '').strip() == cost_type]
    phase_names = {
        norm(value)
        for item in planned
        for value in (item.get('section'), item.get('description'))
        if str(value or '').strip()
    }
    return [OTHER_TITLE, *[
        title for title in reference_titles(rich, cost_group)
        if title != OTHER_TITLE and norm(title) in phase_names
    ]]


def plan_rows_for_title(rich, phase_no: int, title: str,
                        cost_group: str = 'پیمانکار') -> list[dict[str, Any]]:
    """The plan lines one trade covers, in one phase.

    The workbook groups a phase's lines under exactly what a contract is
    for: a named trade, and the blank lines kept beneath it for what the
    contract adds later. That group is the contract; the phase is not.
    Which of the phase's three cost_type groups - مصالح, اجرت or خدمات -
    follows the contract's own دسته‌بندی; a پیمانکار contract still reads
    only اجرت lines, as it always did.
    """

    title = norm(title)
    if not title or title == norm(OTHER_TITLE):
        return []
    try:
        items = rich.list_phase_items(phase_no)
    except Exception:
        return []
    cost_type = COST_TYPES.get(cost_group, 'اجرت')
    own_type = [r for r in items if str(r.get('cost_type') or '').strip() == cost_type]
    own = [r for r in own_type if norm(r.get('section')) == title]
    return own or [r for r in own_type if norm(r.get('description')) == title]


def contract_rows_total(row_values: list[dict[str, tk.StringVar]]) -> int:
    """The sum of every row's own مبلغ کل قرارداد - what this contract costs.

    Not the plan's estimate: a phase only names the work and its measured
    quantities, and putting its estimate here read as the agreed price
    before anyone had agreed to one.
    """

    return sum(int(_row_number(row['line_total'].get())) for row in row_values)


def apply_plan_rows(row_values: list[dict[str, tk.StringVar]],
                    planned: list[dict[str, Any]]) -> None:
    """Write what the plan says onto a contract's rows - quantities, estimates.

    Only the agreed price is left for the operator to type; everything else
    the reference catalogue already states.
    """

    for row, item in zip(row_values, planned):
        row['plan_ref'].set(str(item.get('plan_ref') or ''))
        row['description'].set(str(item.get('description') or ''))
        row['unit'].set(str(item.get('unit') or ''))
        rate = int(item.get('estimate_rate') or item.get('local_estimate_rate') or 0)
        quantity = float(item.get('qty_estimate') or 0)
        row['estimate_price'].set(str(rate))
        row['quantity'].set(f'{quantity:g}')
        row['estimate_quantity'].set(f'{quantity:g}')
        row['estimate_total'].set(str(int(round(quantity * rate))))
        recompute_row_totals_187(row)


class ContractWizard187(BarkavWizard):
    """Documents, contractor, contract rows, terms, payments and confirmation.

    The row step grows: five rows fit one window and more rows add windows,
    so ``step_titles`` is rebuilt whenever the row count changes.
    """

    size_class = 'medium'

    BASE_TITLES = ('اسناد قرارداد', 'مشخصات پیمانکار', 'مفاد قرارداد', 'شرایط پرداخت')
    CONFIRM_TITLE = 'تأیید نهایی'

    def __init__(self, parent, *, rich=None, on_saved=None,
                 contract: dict[str, Any] | None = None):
        self.rich = rich
        self.on_saved = on_saved
        self.record = dict(contract or {})
        self.values: dict[str, tk.StringVar] = {}
        self.row_values: list[dict[str, tk.StringVar]] = []
        self.payment_values: list[dict[str, tk.StringVar]] = []
        self._row_pages = 1
        self._saved_once = False
        self.step_titles = self._compose_titles()
        title = 'ویرایش قرارداد پیمانکار' if contract else 'ثبت قرارداد پیمانکار'
        super().__init__(parent, title, subtitle='BARKAV 18.7')
        self._seed_from_record()
        self._seed_payment_schedule()

    # --- structure ----------------------------------------------------------

    def _compose_titles(self) -> tuple[str, ...]:
        pages = tuple(
            f'ردیف‌های قرارداد ({fa(index + 1)})' if self._row_pages > 1
            else 'ردیف‌های قرارداد'
            for index in range(self._row_pages)
        )
        return (*self.BASE_TITLES[:2], *pages, *self.BASE_TITLES[2:], self.CONFIRM_TITLE)

    def _terms_step_index(self) -> int:
        return 2 + self._row_pages

    def _payment_step_index(self) -> int:
        return 3 + self._row_pages

    def _build_navigation(self) -> None:
        """Keep the data-entry wizard's shortcuts on every contract step."""

        super()._build_navigation()
        self._skip_all_button = self.add_action(
            'رد کردن تمامی مراحل', self.skip_all_stages, style='Toolbar.TButton')
        self._full_form_button = self.add_action(
            'نمایش فرم کامل', self.open_full_form, style='Toolbar.TButton')
        self._close_button = self.add_action('بستن', self.close, style='Ghost.TButton')

    def _sync_navigation(self) -> None:
        super()._sync_navigation()
        self._next_button.configure(
            text='تأیید و ثبت' if self._step == self.step_count - 1 else 'بعدی  ←')

    def skip_all_stages(self) -> None:
        """Move directly to the final confirmation while keeping entered data."""

        self.show_step(self.step_count - 1)

    def open_full_form(self) -> None:
        """Hand the current in-memory draft to the full Record window.

        The wizard itself does not persist the draft on this route. If the
        Record window is then closed without saving, an edit remains exactly
        as it was and a new contract has not yet been created.
        """

        if getattr(self, '_handed_off_to_record', False):
            return
        self._handed_off_to_record = True
        draft = self.collect()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        if self.on_saved is not None:
            self.on_saved(draft, True)

    def _var(self, key: str, default: str = '') -> tk.StringVar:
        if key not in self.values:
            self.values[key] = tk.StringVar(value=str(default))
        return self.values[key]

    # --- the project plan behind the wizard ---------------------------------

    def _phase_choices(self) -> tuple[str, ...]:
        """The thirty-two build phases, numbered, as the plan holds them."""
        return plan_phase_choices(self.rich)

    def _phase_no(self) -> int | None:
        return plan_phase_no(self._var('build_phase').get())

    def _phase_chosen(self, *_args) -> None:
        """Take this contract's own trade in that phase: its rows, and their
        quantities - not its total. A phase's estimate is not what the
        contract was agreed at; see _retotal_contract for what is.
        """

        refresh = getattr(self, '_refresh_phase_titles', None)
        if refresh is not None:
            refresh()
        phase_no = self._phase_no()
        if phase_no is None:
            return
        self._pull_rows_from_plan(phase_no)

    def _retotal_contract(self) -> None:
        """مبلغ کل قرارداد follows the sum of every row's own total, unless typed.

        فاز ساخت used to fill this in from the phase's estimate - showing an
        estimate as if it were what the contract was actually agreed at. It
        is the rows' own totals now, empty until a price is entered anywhere;
        typing the amount directly still overrides it, the same rule هر ردیف
        already follows for a lump-sum row.
        """

        if getattr(self, '_total_busy', False):
            return
        total = contract_rows_total(self.row_values)
        self._total_busy = True
        try:
            self._var('total_amount').set(str(total) if total else '')
        finally:
            self._total_busy = False
        self._show_total()

    def _show_total(self) -> None:
        caption = getattr(self, '_total_caption', None)
        if caption is None or not caption.winfo_exists():
            return
        amount = self._var('total_amount').get()
        caption.configure(
            text=f'مبلغ کل قرارداد: {_amount(amount)} تومان' if amount
            else 'مبلغ کل قرارداد از مجموع ردیف‌ها محاسبه می‌شود')

    def _plan_rows_for(self, phase_no: int) -> list[dict[str, Any]]:
        """The plan lines this contract's own trade covers, in this phase."""

        return plan_rows_for_title(self.rich, phase_no, self._contract_title(),
                                   self._var('cost_group', 'پیمانکار').get())

    def _pull_rows_from_plan(self, phase_no: int) -> None:
        """Fill the row pages from the plan, unless the title is 'سایر'.

        A title chosen from the reference catalogue names work the plan
        already describes, so its rows, quantities and estimates are known -
        only the agreed price is not, and that is the one thing still typed.
        """

        if self._var('title', OTHER_TITLE).get().strip() == OTHER_TITLE:
            return
        planned = self._plan_rows_for(phase_no)
        if not planned:
            return
        self._var('row_count').set(str(len(planned)))
        self._resize_rows()
        apply_plan_rows(self.row_values, planned)
        self.show_step(self._step)
        self._retotal_contract()

    def _payment_stage_count(self) -> int:
        try:
            count = int(en(self._var('payment_stage_count', str(PAYMENT_STAGE_MIN_187)).get()))
        except (TypeError, ValueError):
            count = PAYMENT_STAGE_MIN_187
        return max(PAYMENT_STAGE_MIN_187, min(PAYMENT_STAGE_MAX_187, count))

    def _payment_schedule_data(self) -> list[dict[str, Any]]:
        return [
            {
                'sequence_no': index,
                'label': row['label'],
                'due_date_shamsi': row['due_date_shamsi'].get().strip(),
                'amount': row['amount'].get().strip(),
            }
            for index, row in enumerate(self.payment_values, 1)
        ]

    def _seed_payment_schedule(self) -> None:
        stored = [row for row in (self.record.get('payment_schedule') or [])
                  if isinstance(row, dict)]
        requested = self.record.get('payment_stage_count') or len(stored) or PAYMENT_STAGE_MIN_187
        rows = normalise_payment_schedule_187(requested, stored)
        self._var('payment_stage_count').set(str(len(rows)))
        self.payment_values = [
            {
                'label': row['label'],
                'due_date_shamsi': tk.StringVar(value=row['due_date_shamsi']),
                'amount': tk.StringVar(value=row['amount']),
            }
            for row in rows
        ]
        for row in self.payment_values:
            group_number_while_typing_187(row['amount'])

    def _resize_payment_schedule(self) -> None:
        rows = normalise_payment_schedule_187(
            self._payment_stage_count(), self._payment_schedule_data())
        self._var('payment_stage_count').set(str(len(rows)))
        self.payment_values = [
            {
                'label': row['label'],
                'due_date_shamsi': tk.StringVar(value=row['due_date_shamsi']),
                'amount': tk.StringVar(value=row['amount']),
            }
            for row in rows
        ]
        for row in self.payment_values:
            group_number_while_typing_187(row['amount'])
        if getattr(self, '_step', -1) == self._payment_step_index():
            self.show_step(self._step)

    def _seed_from_record(self) -> None:
        for key, value in self.record.items():
            if isinstance(value, (str, int, float)):
                self._var(key).set(str(value))
        # Editing or copying a contract must not start its rows from scratch:
        # they were already agreed, priced and metred. self.row_values begins
        # empty regardless of what was saved, and collect() only ever reads
        # self.row_values - so closing the wizard on an edit, without this,
        # silently replaced real rows with blank ones the moment ✕ was
        # pressed. Re-selecting فاز ساخت would refill them, but a value the
        # combo already shows correctly gives no reason to touch it again.
        stored_rows = [r for r in (self.record.get('rows') or []) if isinstance(r, dict)]
        if stored_rows:
            self.row_values = []
            for stored in stored_rows:
                row = blank_row_187(on_total_change=self._retotal_contract)
                for key, _label in ROW_COLUMNS:
                    if key != 'no':
                        row[key].set(str(stored.get(key) or ''))
                row['plan_ref'].set(str(stored.get('plan_ref') or ''))
                self.row_values.append(row)
                recompute_row_totals_187(row)
            self._var('row_count').set(str(len(self.row_values)))
            pages = max(1, -(-len(self.row_values) // ROWS_PER_PAGE))
            if pages != self._row_pages:
                self._row_pages = pages
                self.step_titles = self._compose_titles()
            # A row's own on_total_change fires while it is still being built,
            # before it is appended to self.row_values - so the very last row
            # restored is missing from its own recompute. One explicit call
            # once every row is in place is what makes the total correct
            # regardless of that ordering.
            self._retotal_contract()

    # --- shared field helpers ----------------------------------------------

    def _grid(self, parent) -> tk.Frame:
        p = kit_palette()
        grid = tk.Frame(parent, bg=p['bg'])
        grid.pack(fill='x')
        grid.columnconfigure((0, 1), weight=1, uniform='field')
        return grid

    def _cell(self, grid, position: int, label: str):
        """One labelled cell; column 1 is the right-hand one in RTL."""
        p = kit_palette()
        m = kit_metrics()
        row, column = divmod(position, 2)
        cell = tk.Frame(grid, bg=p['bg'])
        cell.grid(row=row, column=1 - column, sticky='ew',
                  padx=m['gap'] // 2, pady=m['gap'] // 2)
        tk.Label(cell, text=label, bg=p['bg'], fg=p['text_secondary'],
                 font=kit_font('small'), anchor='e').pack(fill='x')
        return cell

    def _file_row(self, parent, key: str, label: str) -> None:
        """A caption, the chosen file's name, and the button that picks it.

        There is no text box: a path is never typed here, only chosen, so a
        field to type into was an empty box on every one of these rows.
        """

        p = kit_palette()
        m = kit_metrics()
        holder = tk.Frame(parent, bg=p['bg'])
        holder.pack(fill='x', pady=m['gap'] // 2)
        variable = self._var(key)
        tk.Label(holder, text=label, bg=p['bg'], fg=p['text_secondary'],
                 font=kit_font('small'), anchor='e', width=24).pack(side='right')

        def choose():
            path = filedialog.askopenfilename(parent=self, title=label)
            if path:
                variable.set(path)

        # The button sits where the row starts, right after its caption: it is
        # the only thing on this row the user acts on.
        ttk.Button(holder, text='انتخاب فایل', command=choose,
                   style='Toolbar.TButton').pack(side='right', padx=m['gap'] // 2)
        chosen = tk.Label(holder, bg=p['bg'], fg=p['text_secondary'],
                          font=kit_font('small'), anchor='e')
        chosen.pack(side='right', fill='x', expand=True)

        def show(*_args):
            path = variable.get().strip()
            chosen.configure(text=Path(path).name if path else 'فایلی انتخاب نشده است',
                             fg=p['text_primary'] if path else p['empty'])

        variable.trace_add('write', show)
        show()

    # --- steps --------------------------------------------------------------

    def render_step(self, index: int, parent: tk.Frame) -> None:
        p = kit_palette()
        m = kit_metrics()
        tk.Label(parent, text=f'‏{fa(index + 1)}. {self.step_titles[index]}',
                 bg=p['bg'], fg=p['text_primary'], font=kit_font('title'),
                 anchor='e').pack(fill='x', pady=(0, m['gap']))

        if index == 0:
            self._render_documents(parent)
        elif index == 1:
            self._render_contractor(parent)
        elif 2 <= index < 2 + self._row_pages:
            self._render_rows(parent, index - 2)
        elif index == self._terms_step_index():
            self._render_terms(parent)
        elif index == self._payment_step_index():
            self._render_payment_terms(parent)
        else:
            self._render_confirm(parent)

    def _render_documents(self, parent) -> None:
        p = kit_palette()
        m = kit_metrics()
        for key, label in DOCUMENT_FIELDS:
            self._file_row(parent, key, label)

        # The contract's own number, as written on the paper contract.  It is
        # what 'نمایش بر اساس' filters on, so it is asked for before anything
        # that can be looked up.
        number = tk.Frame(parent, bg=p['bg'])
        number.pack(fill='x', pady=(m['gap'], 0))
        tk.Label(number, text='شماره قرارداد', bg=p['bg'], fg=p['text_secondary'],
                 font=kit_font('small'), anchor='e', width=22).pack(side='right')
        ttk.Entry(number, textvariable=self._var('contract_number'),
                  justify='right').pack(side='right', fill='x', expand=True,
                                        padx=m['gap'] // 2)

        # The date is followed immediately by the phase; titles are filtered
        # to work actually present in that phase.
        date_row = tk.Frame(parent, bg=p['bg'])
        date_row.pack(fill='x', pady=(m['gap'], 0))
        tk.Label(date_row, text='تاریخ قرارداد', bg=p['bg'], fg=p['text_secondary'],
                 font=kit_font('small'), anchor='e', width=22).pack(side='right')
        date_var = self._var('contract_date')
        ttk.Entry(date_row, textvariable=date_var, justify='right').pack(
            side='right', fill='x', expand=True, padx=m['gap'] // 2)
        ttk.Button(date_row, text='تقویم', style='Toolbar.TButton',
                   command=lambda: ShamsiDatePicker187(self, date_var, compact=True)).pack(
                       side='left', padx=(m['gap'] // 2, 0))

        phase_row = tk.Frame(parent, bg=p['bg'])
        phase_row.pack(fill='x', pady=(m['gap'], 0))
        tk.Label(phase_row, text='فاز ساخت', bg=p['bg'], fg=p['text_secondary'],
                 font=kit_font('small'), anchor='e', width=22).pack(side='right')
        phase_var = self._var('build_phase')
        phase_combo = ttk.Combobox(phase_row, textvariable=phase_var,
                                   values=self._phase_choices(), state='readonly',
                                   justify='right')
        phase_combo.pack(side='right', fill='x', expand=True,
                         padx=m['gap'] // 2)

        # دسته‌بندی decides which of the three reference tabs عنوان قرارداد
        # is read from - مصالح, پیمانکار or خدمات - the same three-way split
        # a هزینه ساخت transaction asks for. پیمانکار is the default: it is
        # the only kind a contract meant before this field existed.
        group_row = tk.Frame(parent, bg=p['bg'])
        group_row.pack(fill='x', pady=(m['gap'], 0))
        tk.Label(group_row, text='دسته‌بندی', bg=p['bg'], fg=p['text_secondary'],
                 font=kit_font('small'), anchor='e', width=22).pack(side='right')
        group_var = self._var('cost_group', 'پیمانکار')
        ttk.Combobox(group_row, textvariable=group_var, values=COST_GROUPS,
                     state='readonly', justify='right').pack(
            side='right', fill='x', expand=True, padx=m['gap'] // 2)

        holder = tk.Frame(parent, bg=p['bg'])
        holder.pack(fill='x', pady=(m['gap'], 0))
        tk.Label(holder, text='عنوان قرارداد', bg=p['bg'], fg=p['text_secondary'],
                 font=kit_font('small'), anchor='e', width=22).pack(side='right')
        variable = self._var('title', OTHER_TITLE)
        combo = SearchableCombo187(holder, values=phase_reference_titles_187(
                                       self.rich, self._phase_no(), group_var.get()),
                                   textvariable=variable, justify='right')
        combo.pack(side='right', fill='x', expand=True, padx=m['gap'] // 2)

        # 'سایر' means the reference file does not cover this work, so a free
        # text box appears for the title instead.
        custom = tk.Frame(parent, bg=p['bg'])
        custom_entry = ttk.Entry(custom, textvariable=self._var('custom_title'),
                                 justify='right')
        tk.Label(custom, text='عنوان دستی', bg=p['bg'], fg=p['text_secondary'],
                 font=kit_font('small'), anchor='e', width=22).pack(side='right')
        custom_entry.pack(side='right', fill='x', expand=True, padx=m['gap'] // 2)

        def sync(*_args):
            # variable/group_var live on self.values for the wizard's whole
            # life, so this trace outlives اسناد قرارداد's own render: paging
            # away destroys custom/combo, but nothing ever removes the trace,
            # and revisiting this step registers another one on top of it.
            # Guard on the widgets it closes over rather than the value, or a
            # stale trace throws TclError the moment either var changes again
            # from anywhere else in the wizard.
            if not custom.winfo_exists():
                return
            if variable.get().strip() == OTHER_TITLE:
                custom.pack(fill='x', pady=m['gap'] // 2)
            else:
                custom.pack_forget()

        def group_changed(*_args):
            refresh_titles()

        def refresh_titles(*_args):
            if not combo.winfo_exists():
                return
            titles = phase_reference_titles_187(
                self.rich, self._phase_no(), group_var.get())
            combo.set_source(titles)
            if variable.get().strip() not in titles:
                previous = variable.get().strip()
                if previous and previous != OTHER_TITLE and not self._var('custom_title').get().strip():
                    self._var('custom_title').set(previous)
                variable.set(OTHER_TITLE)

        def title_changed(*_args):
            if (combo.winfo_exists() and variable.get().strip() != OTHER_TITLE
                    and variable.get().strip() in combo._all_values):
                self._var('custom_title').set('')
                phase_no = self._phase_no()
                if phase_no is not None:
                    self._pull_rows_from_plan(phase_no)

        def finish_title_entry(_event=None):
            if not combo.winfo_exists():
                return
            typed = variable.get().strip()
            if typed and typed not in combo._all_values:
                self._var('custom_title').set(typed)
                variable.set(OTHER_TITLE)

        variable.trace_add('write', sync)
        group_var.trace_add('write', group_changed)
        phase_var.trace_add('write', refresh_titles)
        phase_var.trace_add('write', self._phase_chosen)
        variable.trace_add('write', title_changed)
        combo.bind('<FocusOut>', finish_title_entry, add='+')
        self._refresh_phase_titles = refresh_titles
        refresh_titles()
        sync()

    def _render_contractor(self, parent) -> None:
        grid = self._grid(parent)
        # Two columns, three rows, as the specification asks.
        nationality = self._var('nationality', 'ایرانی')
        licence = self._var('has_licence', 'ندارد')
        id_label_holder: dict[str, tk.Label] = {}

        for position, (key, label) in enumerate(CONTRACTOR_FIELDS):
            cell = self._cell(grid, position, label)
            if key == 'nationality':
                ttk.Combobox(cell, textvariable=nationality,
                             values=('ایرانی', 'اتباع'), state='readonly',
                             justify='right').pack(fill='x')
            elif key == 'has_licence':
                ttk.Combobox(cell, textvariable=licence, values=('ندارد', 'دارد'),
                             state='readonly', justify='right').pack(fill='x')
            elif key == 'national_id':
                id_label_holder['label'] = cell.winfo_children()[0]
                ttk.Entry(cell, textvariable=self._var(key),
                          justify='right').pack(fill='x')
            else:
                ttk.Entry(cell, textvariable=self._var(key),
                          justify='right').pack(fill='x')

        # The identity field is labelled by nationality, not by a fixed name.
        def sync_identity(*_args):
            label = id_label_holder.get('label')
            if label is not None and label.winfo_exists():
                label.configure(text='کد اتباع' if nationality.get() == 'اتباع'
                                else 'کد ملی')

        nationality.trace_add('write', sync_identity)
        sync_identity()

        # 'دارد' reveals the upload the licence needs.
        licence_row = tk.Frame(parent, bg=kit_palette()['bg'])

        def sync_licence(*_args):
            if licence.get() == 'دارد':
                if not licence_row.winfo_children():
                    self._file_row(licence_row, 'licence_file', 'بارگذاری مدرک شغلی')
                licence_row.pack(fill='x', pady=kit_metrics()['gap'] // 2)
            else:
                licence_row.pack_forget()

        licence.trace_add('write', sync_licence)
        sync_licence()

    def _render_terms(self, parent) -> None:
        p = kit_palette()
        grid = self._grid(parent)
        cell = self._cell(grid, 0, 'مدت زمان (ماه)')
        duration_entry = ttk.Entry(cell, textvariable=self._var('duration_months'),
                                   justify='right')
        duration_entry.pack(fill='x')
        keep_numeric_cursor_at_end_187(duration_entry)

        total_cell = self._cell(grid, 1, 'مبلغ کل قرارداد')
        self._total_caption = tk.Label(
            total_cell, bg=p['bg'], fg=p['text_secondary'], font=kit_font('small'), anchor='e')
        self._total_caption.pack(fill='x')
        self._show_total()

        supply = self._grid(parent)
        for position, (key, label) in enumerate(SUPPLY_FIELDS):
            cell = self._cell(supply, position, label)
            ttk.Combobox(cell, textvariable=self._var(key, SUPPLY_ROLES[0]),
                         values=SUPPLY_ROLES, state='readonly',
                         justify='right').pack(fill='x')

    def _render_payment_terms(self, parent) -> None:
        """Ask for total payment stages, then show their RTL Shamsi rows.

        The stage boxes scroll vertically: more than three stages pushed the
        navigation buttons off the window, and the count was not reachable by
        wheel because the boxes sat directly on the step host.
        """

        p = kit_palette()
        m = kit_metrics()
        scroll = _vertical_scroll_area(parent, bg=p['bg'])
        header = tk.Frame(scroll, bg=p['bg'])
        header.pack(fill='x', pady=(0, m['gap']))
        tk.Label(header, text='تعداد مراحل پرداخت', bg=p['bg'], fg=p['text_secondary'],
                 font=kit_font('small'), anchor='e').pack(side='right')
        ttk.Spinbox(header, from_=PAYMENT_STAGE_MIN_187, to=PAYMENT_STAGE_MAX_187,
                    textvariable=self._var('payment_stage_count'), width=6,
                    justify='right', command=self._resize_payment_schedule).pack(side='right', padx=m['gap'] // 2)
        ttk.Button(header, text='ایجاد مراحل', command=self._resize_payment_schedule,
                   style='Toolbar.TButton').pack(side='right')
        tk.Label(scroll, text='پیش پرداخت و تحویل کار ثابت‌اند؛ تعداد واردشده شامل همه مراحل است.',
                 bg=p['bg'], fg=p['text_secondary'], font=kit_font('small'),
                 anchor='e').pack(fill='x', pady=(0, m['gap']))

        for row in self.payment_values:
            box = ttk.LabelFrame(scroll, text=row['label'], labelanchor='ne', padding=m['gap'])
            box.pack(fill='x', pady=m['gap'] // 2)
            box.grid_columnconfigure((0, 1), weight=1, uniform='payment')
            date_box = ttk.Frame(box, style='Card.TFrame')
            date_box.grid(row=0, column=1, sticky='ew', padx=m['gap'] // 2, pady=m['gap'] // 2)
            ttk.Label(date_box, text='تاریخ شمسی', anchor='e').pack(fill='x')
            date_line = ttk.Frame(date_box, style='Card.TFrame')
            date_line.pack(fill='x')
            ttk.Entry(date_line, textvariable=row['due_date_shamsi'], justify='right').pack(
                side='right', fill='x', expand=True)
            ttk.Button(date_line, text='تقویم', style='Toolbar.TButton',
                       command=lambda value=row['due_date_shamsi']: ShamsiDatePicker187(self, value)).pack(
                           side='left', padx=(m['gap'] // 2, 0))
            amount_box = ttk.Frame(box, style='Card.TFrame')
            amount_box.grid(row=0, column=0, sticky='ew', padx=m['gap'] // 2, pady=m['gap'] // 2)
            ttk.Label(amount_box, text='مبلغ (تومان)', anchor='e').pack(fill='x')
            amount_entry = ttk.Entry(amount_box, textvariable=row['amount'], justify='right')
            amount_entry.pack(fill='x')
            keep_numeric_cursor_at_end_187(amount_entry)

        self._payment_summary_label = tk.Label(
            scroll, bg=p['bg'], fg=p['text_secondary'], font=kit_font('body'), anchor='e')
        self._payment_summary_label.pack(fill='x', pady=(m['gap'], 0))
        total_variable = self._var('total_amount')

        def refresh_summary(*_args):
            refresh_schedule_summary_187(self._payment_summary_label, total_variable,
                                         self.payment_values)

        for row in self.payment_values:
            row['amount'].trace_add('write', refresh_summary)
        total_variable.trace_add('write', refresh_summary)
        refresh_summary()

        for key, label in (('payment_terms', 'شرایط پرداخت'), ('notes', 'سایر')):
            tk.Label(scroll, text=label, bg=p['bg'], fg=p['text_secondary'],
                     font=kit_font('small'), anchor='e').pack(
                         fill='x', pady=(m['gap'], m['gap'] // 2))
            editor = editable_text_box_187(scroll, self._var(key), height=4)
            editor.pack(fill='x')

    def _render_rows(self, parent, page: int) -> None:
        p = kit_palette()
        m = kit_metrics()
        header = tk.Frame(parent, bg=p['bg'])
        header.pack(fill='x', pady=(0, m['gap']))
        tk.Label(header, text='تعداد ردیف', bg=p['bg'], fg=p['text_secondary'],
                 font=kit_font('small'), anchor='e').pack(side='right', padx=(0, 4))
        count = self._var('row_count', str(max(1, len(self.row_values) or 1)))
        spin = ttk.Spinbox(header, from_=1, to=60, textvariable=count, width=6,
                           justify='right', command=self._resize_rows)
        spin.pack(side='right')
        ttk.Button(header, text='اعمال', command=self._resize_rows,
                   style='Toolbar.TButton').pack(side='right', padx=m['gap'] // 2)

        render_row_grid_187(parent, self.row_values, start=page * ROWS_PER_PAGE,
                            count=ROWS_PER_PAGE,
                            on_reference=self._fill_from_reference)

    def _render_confirm(self, parent) -> None:
        p = kit_palette()
        m = kit_metrics()
        summary = (
            f"شماره: {fa(self._var('contract_number').get() or '-')}\n"
            f"دسته‌بندی: {self._var('cost_group', 'پیمانکار').get()}\n"
            f"عنوان: {self._contract_title()}\n"
            f"پیمانکار: {self._var('family_name').get()}\n"
            f"مدت: {fa(self._var('duration_months').get() or '-')} ماه\n"
            f"مبلغ کل: {_amount(self._var('total_amount').get())} تومان\n"
            f"تعداد مراحل پرداخت: {fa(len(self.payment_values))}\n"
            f"تعداد ردیف: {fa(len(self.row_values))}"
        )
        tk.Label(parent, text=summary, bg=p['panel'], fg=p['text_primary'],
                 font=kit_font('body'), anchor='e', justify='right',
                 padx=m['outer_pad'], pady=m['outer_pad']).pack(fill='x')

    # --- behaviour ----------------------------------------------------------

    def _contract_title(self) -> str:
        title = self._var('title', OTHER_TITLE).get().strip()
        if title == OTHER_TITLE:
            return self._var('custom_title').get().strip() or OTHER_TITLE
        return title

    def _resize_rows(self) -> None:
        previous_titles = self.step_titles
        previous_step = self._step
        was_confirm = previous_step == len(previous_titles) - 1
        was_terms = previous_step == self._terms_step_index()
        was_payment = previous_step == self._payment_step_index()
        was_rows = 2 <= previous_step < 2 + self._row_pages
        previous_row_page = max(0, previous_step - 2) if was_rows else 0
        try:
            wanted = max(1, min(60, int(en(self._var('row_count').get() or '1'))))
        except (TypeError, ValueError):
            return
        while len(self.row_values) < wanted:
            self.row_values.append(blank_row_187(on_total_change=self._retotal_contract))
        del self.row_values[wanted:]
        pages = max(1, -(-wanted // ROWS_PER_PAGE))
        if pages != self._row_pages:
            self._row_pages = pages
            self.step_titles = self._compose_titles()
        if was_confirm:
            target_step = len(self.step_titles) - 1
        elif was_payment:
            target_step = self._payment_step_index()
        elif was_terms:
            target_step = self._terms_step_index()
        elif was_rows:
            target_step = 2 + min(previous_row_page, self._row_pages - 1)
        else:
            target_step = min(previous_step, len(self.step_titles) - 1)
        self.show_step(target_step)
        # A shrink drops rows without any of them reporting a change, so the
        # total is not automatically corrected the way growing it is.
        self._retotal_contract()

    def _fill_from_reference(self, row: dict[str, tk.StringVar]) -> None:
        """Pull estimate figures for a row from the project's reference file."""
        reference = reference_row(self.rich, row['description'].get(),
                                  self._var('cost_group', 'پیمانکار').get())
        if not reference:
            return
        if not row['unit'].get():
            row['unit'].set(str(reference.get('unit') or ''))
        if not row['estimate_price'].get():
            row['estimate_price'].set(str(reference.get('estimate_rate') or ''))
        if not row['estimate_quantity'].get():
            row['estimate_quantity'].set(str(reference.get('quantity') or ''))
        if not row['estimate_total'].get():
            try:
                rate = float(en(str(reference.get('estimate_rate') or 0)) or 0)
                quantity = float(en(str(reference.get('quantity') or 0)) or 0)
                row['estimate_total'].set(str(int(rate * quantity)))
            except (TypeError, ValueError):
                pass

    def validate_step(self, index: int) -> bool:
        """No step blocks the next one.

        A contract is entered from paperwork that arrives in pieces, so a
        field that is not to hand yet must not stop the rest being recorded.
        Anything still empty can be filled in from the record window.
        """

        if index != self._payment_step_index():
            return True
        scheduled = schedule_amount_total_187(self.payment_values)
        total = int(_row_number(self._var('total_amount').get()))
        if scheduled != total:
            messagebox.showwarning(
                'شرایط پرداخت',
                f'جمع مراحل پرداخت ({_amount(scheduled)} تومان) باید با مبلغ کل قرارداد '
                f'({_amount(total)} تومان) برابر باشد.',
                parent=self)
            return False
        return True

    def collect(self) -> dict[str, Any]:
        record = dict(self.record)
        record.update({key: variable.get() for key, variable in self.values.items()})
        record['title'] = self._contract_title()
        record['rows'] = [
            {**{key: row[key].get() for key, _label in ROW_COLUMNS if key != 'no'},
             'plan_ref': row['plan_ref'].get()}
            for row in self.row_values
        ]
        record['payment_stage_count'] = str(len(self.payment_values))
        record['payment_schedule'] = self._payment_schedule_data()
        record.setdefault('status', 'فعال')
        record.setdefault('payments', [])
        return record

    def finish(self) -> None:
        """ذخیره on the last window: the operator's explicit تأیید نهایی.

        This is the one place an edit to an existing contract is ever
        applied - reaching and confirming this window is the confirmation
        the rest of the wizard defers to. The record window is how a
        contract closed part-way through is carried on; confirming here is
        the other outcome, and does not need one opened over it.
        """

        # A direct «تأیید و ثبت» or «رد کردن تمامی مراحل» route must still
        # honour the payment schedule rule even when the payment step was
        # skipped rather than traversed.
        for index in range(self.step_count):
            if not self.validate_step(index):
                self.show_step(index)
                return
        self._save(open_record=False)
        self.close()

    def close(self) -> None:
        """Stop the wizard: discard edits, or keep a new partial row without opening Record."""

        if self._saved_once:
            super().close()
            return
        if not self.record.get('contract_id'):
            self._save(open_record=False)
        super().close()

    def _save(self, *, open_record: bool) -> None:
        if self._saved_once:
            return
        self._saved_once = True
        saved = upsert_contract(self.collect())
        if self.on_saved is not None:
            self.on_saved(saved, open_record)


class ContractRecordWindow187(BarkavWindow):
    """Preview on the left, contract details on the right, both scrollable.

    Mirrors the sales record window the specification points at, so the two
    read as the same kind of screen.
    """

    size_class = 'full'

    def __init__(self, parent, *, contract: dict[str, Any], rich=None, on_saved=None):
        self.contract = dict(contract)
        self.rich = rich
        self.on_saved = on_saved
        self.values: dict[str, tk.StringVar] = {}
        self.row_values: list[dict[str, tk.StringVar]] = []
        self.payment_values: list[dict[str, tk.StringVar]] = []
        super().__init__(parent, 'پنجره رکورد قرارداد پیمانکار',
                         subtitle=str(contract.get('title') or ''), show_footer=True)
        self._build()
        self.add_action('ذخیره', self.save, style='Primary.TButton')
        self.add_action('بستن', self.close)

    def _build(self) -> None:
        p = kit_palette()
        m = kit_metrics()
        body = tk.PanedWindow(self.body, orient='horizontal', bg=p['border_subtle'],
                              sashwidth=6, relief='flat', bd=0)
        body.pack(fill='both', expand=True)

        preview = ttk.Frame(body, style='Card.TFrame', padding=m['gap'])
        details = ttk.Frame(body, style='Card.TFrame', padding=m['gap'])
        body.add(preview, minsize=280, stretch='always')
        body.add(details, minsize=420, stretch='always')

        self._build_preview(preview)
        self._build_details(details)

    def _build_preview(self, parent) -> None:
        p = kit_palette()
        m = kit_metrics()
        tools = tk.Frame(parent, bg=p['card'])
        tools.pack(fill='x')
        tk.Label(tools, text='پیش‌نمایش قرارداد', bg=p['card'], fg=p['text_primary'],
                 font=kit_font('title'), anchor='e').pack(side='right')
        ttk.Button(tools, text='+', width=3, style='Toolbar.TButton',
                   command=lambda: self._zoom(1)).pack(side='left', padx=2)
        ttk.Button(tools, text='−', width=3, style='Toolbar.TButton',
                   command=lambda: self._zoom(-1)).pack(side='left', padx=2)

        holder = tk.Frame(parent, bg=p['input'])
        holder.pack(fill='both', expand=True, pady=(m['gap'], 0))
        self.preview_canvas = tk.Canvas(holder, bg=p['input'], highlightthickness=0)
        vertical = ttk.Scrollbar(holder, orient='vertical',
                                 command=self.preview_canvas.yview)
        horizontal = ttk.Scrollbar(holder, orient='horizontal',
                                   command=self.preview_canvas.xview)
        self.preview_canvas.configure(yscrollcommand=vertical.set,
                                      xscrollcommand=horizontal.set)
        self._preview_bars = (vertical, horizontal)
        vertical.pack(side='left', fill='y')
        horizontal.pack(side='bottom', fill='x')
        self.preview_canvas.pack(side='right', fill='both', expand=True)
        self.preview_canvas.bind(
            '<MouseWheel>',
            lambda e: self.preview_canvas.yview_scroll(int(-e.delta / 120), 'units'),
            add='+')
        self._preview_zoom = 1.0
        self._preview_image = None
        self._render_preview()

    def _zoom(self, direction: int) -> None:
        self._preview_zoom = max(0.3, min(4.0, self._preview_zoom + 0.2 * direction))
        self._render_preview()

    def _render_preview(self) -> None:
        path = str(self.contract.get('contract_file') or '')
        self.preview_canvas.delete('all')
        p = kit_palette()
        if not path or not Path(path).is_file():
            self.preview_canvas.create_text(
                10, 10, anchor='nw', fill=p['empty'],
                text='فایلی برای پیش‌نمایش بارگذاری نشده است')
            self._fit_preview()
            return
        try:
            from PIL import Image, ImageTk
            image = Image.open(path)
            width = max(1, int(image.width * self._preview_zoom))
            height = max(1, int(image.height * self._preview_zoom))
            image = image.resize((width, height), Image.LANCZOS)
            self._preview_image = ImageTk.PhotoImage(image, master=self)
            self.preview_canvas.create_image(0, 0, anchor='nw', image=self._preview_image)
            self.preview_canvas.configure(scrollregion=(0, 0, width, height))
            self._fit_preview(scrollable=True)
        except Exception:
            self.preview_canvas.create_text(
                10, 10, anchor='nw', fill=p['empty'],
                text=f'{Path(path).name}\nاین قالب قابل پیش‌نمایش نیست')
            self._fit_preview()

    def _fit_preview(self, *, scrollable: bool = False) -> None:
        """Match the preview's scroll region to what is in it, and its
        scrollbars to whether there is anything to scroll.

        The scrollbars are the whole story here. A canvas that reports its
        position to a scrollbar does so on every redraw, and this one shares a
        paned window with the form - so each notch of the wheel over the form
        cost about 215 milliseconds. Detaching them brings that to 0.01, and
        nothing else tried came close: not a scroll region, not a fixed size,
        not changing how the panes stretch.

        An empty preview has nothing to scroll and so needs no bars. They come
        back with the image, where they are what the reader actually uses.
        """

        box = self.preview_canvas.bbox('all') or (0, 0, 0, 0)
        self.preview_canvas.configure(scrollregion=box)
        vertical, horizontal = getattr(self, '_preview_bars', (None, None))
        if vertical is None:
            return
        if scrollable:
            self.preview_canvas.configure(yscrollcommand=vertical.set,
                                          xscrollcommand=horizontal.set)
        else:
            # Detached, not hidden. Taking the bars out of the layout costs
            # as much as leaving them driven - it is the reporting that is
            # expensive, not the widgets - and an empty preview keeping its
            # frame is what the pane looked like before.
            self.preview_canvas.configure(yscrollcommand='', xscrollcommand='')
            vertical.set(0.0, 1.0)
            horizontal.set(0.0, 1.0)

    def _build_details(self, parent) -> None:
        """All five sections shown together, in reading order, in one scroll.

        Not tabs: the operator asked to see the whole contract at once rather
        than switch between four hidden panes - and one scrollbar for the
        whole window rather than a second, separate one just for
        ردیف‌های قرارداد. A canvas scrolling a frame full of ttk widgets
        does cost more the more rows a contract has, but a record window is
        one contract's own paperwork, not a table of many; splitting the
        scroll to chase that cost cut against what the operator actually
        asked for, so this reads top to bottom as a single page instead.

        The confirm step has no fields of its own - it only summarises what
        the others hold - so it is the one wizard window that does not
        appear here.
        """

        p = kit_palette()
        m = kit_metrics()
        tk.Label(parent, text='مشخصات قرارداد پیمانکار', bg=p['card'],
                 fg=p['text_primary'], font=kit_font('title'), anchor='e').pack(fill='x')

        scroll_area = _vertical_scroll_area(parent, bg=p['card'])
        sections = (
            ('‏۱. اسناد قرارداد', self._page_documents),
            ('‏۲. مشخصات پیمانکار', self._page_contractor),
            ('‏۳. ردیف‌های قرارداد', self._page_rows),
            ('‏۴. مفاد قرارداد', self._page_terms),
            ('‏۵. شرایط پرداخت', self._page_payment_terms),
        )
        for title, build in sections:
            heading = tk.Frame(scroll_area, bg=p['card'])
            heading.pack(fill='x', pady=(m['gap'], m['gap'] // 2))
            tk.Label(heading, text=title, bg=p['card'], fg=p['text_primary'],
                    font=kit_font('body', bold=True), anchor='e').pack(fill='x')
            section = ttk.Frame(scroll_area, style='Card.TFrame')
            section.pack(fill='x')
            build(section)

    def _page_documents(self, page) -> None:
        for key, label in DOCUMENT_FIELDS:
            self._file_line(page, key, label)

        m = kit_metrics()
        number_line = ttk.Frame(page, style='Card.TFrame')
        number_line.pack(fill='x', pady=m['gap'] // 2)
        ttk.Label(number_line, text='شماره قرارداد', anchor='e', width=24).pack(side='right')
        ttk.Entry(number_line, textvariable=self.values.setdefault(
            'contract_number', tk.StringVar(value=str(self.contract.get('contract_number') or ''))),
            justify='right').pack(side='right', fill='x', expand=True, padx=m['gap'] // 2)

        date_line = ttk.Frame(page, style='Card.TFrame')
        date_line.pack(fill='x', pady=m['gap'] // 2)
        ttk.Label(date_line, text='تاریخ قرارداد', anchor='e', width=24).pack(side='right')
        date_var = self.values.setdefault(
            'contract_date', tk.StringVar(value=str(self.contract.get('contract_date') or '')))
        ttk.Entry(date_line, textvariable=date_var, justify='right').pack(
            side='right', fill='x', expand=True, padx=m['gap'] // 2)
        ttk.Button(date_line, text='تقویم', style='Toolbar.TButton',
                   command=lambda: ShamsiDatePicker187(self, date_var, compact=True)).pack(side='left')

        phase_line = ttk.Frame(page, style='Card.TFrame')
        phase_line.pack(fill='x', pady=m['gap'] // 2)
        ttk.Label(phase_line, text='فاز ساخت', anchor='e', width=24).pack(side='right')
        phase_var = self.values.setdefault(
            'build_phase', tk.StringVar(value=str(self.contract.get('build_phase') or '')))
        phase_combo = ttk.Combobox(phase_line, textvariable=phase_var,
                                   values=plan_phase_choices(self.rich), state='readonly',
                                   justify='right')
        phase_combo.pack(side='right', fill='x', expand=True, padx=m['gap'] // 2)

        group_line = ttk.Frame(page, style='Card.TFrame')
        group_line.pack(fill='x', pady=m['gap'] // 2)
        ttk.Label(group_line, text='دسته‌بندی', anchor='e', width=24).pack(side='right')
        group_var = self.values.setdefault(
            'cost_group', tk.StringVar(value=str(self.contract.get('cost_group') or 'پیمانکار')))
        ttk.Combobox(group_line, textvariable=group_var, values=COST_GROUPS,
                     state='readonly', justify='right').pack(
                         side='right', fill='x', expand=True, padx=m['gap'] // 2)

        title_line = ttk.Frame(page, style='Card.TFrame')
        title_line.pack(fill='x', pady=m['gap'] // 2)
        ttk.Label(title_line, text='عنوان قرارداد', anchor='e', width=24).pack(side='right')
        stored_title = str(self.contract.get('title') or '')
        choices = phase_reference_titles_187(
            self.rich, plan_phase_no(phase_var.get()), group_var.get())
        choice_value = stored_title if stored_title in choices else OTHER_TITLE
        self._record_title_choice = tk.StringVar(value=choice_value)
        self._record_custom_title = tk.StringVar(
            value=str(self.contract.get('custom_title') or
                      (stored_title if stored_title and stored_title != OTHER_TITLE
                       and stored_title not in choices else '')))
        self.values.setdefault('custom_title', tk.StringVar(
            value=self._record_custom_title.get()))
        title_combo = SearchableCombo187(
            title_line, values=choices, textvariable=self._record_title_choice,
            justify='right')
        title_combo.pack(side='right', fill='x', expand=True, padx=m['gap'] // 2)
        custom_line = ttk.Frame(page, style='Card.TFrame')
        ttk.Label(custom_line, text='عنوان دستی', anchor='e', width=24).pack(side='right')
        ttk.Entry(custom_line, textvariable=self._record_custom_title,
                  justify='right').pack(side='right', fill='x', expand=True,
                                        padx=m['gap'] // 2)

        def sync_title(*_args):
            choice = self._record_title_choice.get().strip()
            if choice not in title_combo._all_values:
                return
            if choice != OTHER_TITLE and self._record_custom_title.get():
                self._record_custom_title.set('')
            actual = (self._record_custom_title.get().strip() or OTHER_TITLE
                      if choice == OTHER_TITLE else choice)
            self.values.setdefault('custom_title', tk.StringVar()).set(
                self._record_custom_title.get().strip())
            self.values.setdefault('title', tk.StringVar()).set(actual)
            if choice == OTHER_TITLE:
                custom_line.pack(fill='x', pady=m['gap'] // 2)
            else:
                custom_line.pack_forget()

        def refresh_titles(*_args):
            if not title_combo.winfo_exists():
                return
            titles = phase_reference_titles_187(
                self.rich, plan_phase_no(phase_var.get()), group_var.get())
            title_combo.set_source(titles)
            current = self.values.get('title')
            current_title = current.get().strip() if current is not None else stored_title
            if current_title and current_title not in titles:
                if current_title != OTHER_TITLE and not self._record_custom_title.get().strip():
                    self._record_custom_title.set(current_title)
                self._record_title_choice.set(OTHER_TITLE)
            sync_title()
            if self._record_title_choice.get().strip() in titles[1:]:
                self._repull_from_plan()

        def title_selected(_event=None):
            sync_title()
            if self._record_title_choice.get().strip() != OTHER_TITLE:
                self._repull_from_plan()

        def finish_title_entry(_event=None):
            typed = self._record_title_choice.get().strip()
            if typed and typed not in title_combo._all_values:
                self._record_custom_title.set(typed)
                self._record_title_choice.set(OTHER_TITLE)
            refresh_titles()

        self._record_title_choice.trace_add('write', sync_title)
        self._record_custom_title.trace_add('write', sync_title)
        phase_var.trace_add('write', refresh_titles)
        group_var.trace_add('write', refresh_titles)
        title_combo.bind('<<ComboboxSelected>>', title_selected, add='+')
        title_combo.bind('<FocusOut>', finish_title_entry, add='+')
        sync_title()

    def _page_contractor(self, page) -> None:
        self._fields(page, CONTRACTOR_FIELDS)

    def _record_payment_schedule_data(self) -> list[dict[str, Any]]:
        return [
            {
                'sequence_no': index,
                'label': row['label'],
                'due_date_shamsi': row['due_date_shamsi'].get().strip(),
                'amount': row['amount'].get().strip(),
            }
            for index, row in enumerate(self.payment_values, 1)
        ]

    def _seed_record_payment_schedule(self) -> None:
        stored = [row for row in (self.contract.get('payment_schedule') or [])
                  if isinstance(row, dict)]
        requested = self.contract.get('payment_stage_count') or len(stored) or PAYMENT_STAGE_MIN_187
        rows = normalise_payment_schedule_187(requested, stored)
        self.payment_stage_count_var = tk.StringVar(value=str(len(rows)))
        self.payment_values = [
            {
                'label': row['label'],
                'due_date_shamsi': tk.StringVar(value=row['due_date_shamsi']),
                'amount': tk.StringVar(value=row['amount']),
            }
            for row in rows
        ]
        for row in self.payment_values:
            group_number_while_typing_187(row['amount'])

    def _resize_record_payment_schedule(self) -> None:
        try:
            count = int(en(self.payment_stage_count_var.get()))
        except (TypeError, ValueError):
            count = PAYMENT_STAGE_MIN_187
        rows = normalise_payment_schedule_187(count, self._record_payment_schedule_data())
        self.payment_stage_count_var.set(str(len(rows)))
        self.payment_values = [
            {
                'label': row['label'],
                'due_date_shamsi': tk.StringVar(value=row['due_date_shamsi']),
                'amount': tk.StringVar(value=row['amount']),
            }
            for row in rows
        ]
        for row in self.payment_values:
            group_number_while_typing_187(row['amount'])
        host = getattr(self, '_payment_schedule_host', None)
        if host is not None and host.winfo_exists():
            self._render_record_payment_schedule(host)

    def _page_payment_terms(self, page) -> None:
        self._seed_record_payment_schedule()
        self._payment_schedule_host = ttk.Frame(page, style='Card.TFrame')
        self._payment_schedule_host.pack(fill='x')
        self._render_record_payment_schedule(self._payment_schedule_host)
        m = kit_metrics()
        for key, label in (('payment_terms', 'شرایط پرداخت'), ('notes', 'سایر')):
            ttk.Label(page, text=label, anchor='e').pack(
                fill='x', pady=(m['gap'], m['gap'] // 2))
            editor = editable_text_box_187(
                page, self.values.setdefault(
                    key, tk.StringVar(value=str(self.contract.get(key) or ''))), height=4)
            editor.pack(fill='x')

    def _render_record_payment_schedule(self, host) -> None:
        for child in host.winfo_children():
            child.destroy()
        m = kit_metrics()
        header = ttk.Frame(host, style='Card.TFrame')
        header.pack(fill='x', pady=(0, m['gap']))
        ttk.Label(header, text='تعداد مراحل پرداخت', anchor='e').pack(side='right')
        ttk.Spinbox(header, from_=PAYMENT_STAGE_MIN_187, to=PAYMENT_STAGE_MAX_187,
                    textvariable=self.payment_stage_count_var, width=6,
                    justify='right', command=self._resize_record_payment_schedule).pack(
                        side='right', padx=m['gap'] // 2)
        ttk.Button(header, text='ایجاد مراحل', command=self._resize_record_payment_schedule,
                   style='Toolbar.TButton').pack(side='right')
        ttk.Label(host, text='پیش پرداخت و تحویل کار ثابت‌اند؛ تعداد واردشده شامل همه مراحل است.',
                  anchor='e').pack(fill='x', pady=(0, m['gap']))
        for row in self.payment_values:
            box = ttk.LabelFrame(host, text=row['label'], labelanchor='ne', padding=m['gap'])
            box.pack(fill='x', pady=m['gap'] // 2)
            box.grid_columnconfigure((0, 1), weight=1, uniform='record-payment')
            date_box = ttk.Frame(box, style='Card.TFrame')
            date_box.grid(row=0, column=1, sticky='ew', padx=m['gap'] // 2, pady=m['gap'] // 2)
            ttk.Label(date_box, text='تاریخ شمسی', anchor='e').pack(fill='x')
            date_line = ttk.Frame(date_box, style='Card.TFrame')
            date_line.pack(fill='x')
            ttk.Entry(date_line, textvariable=row['due_date_shamsi'], justify='right').pack(
                side='right', fill='x', expand=True)
            ttk.Button(date_line, text='تقویم', style='Toolbar.TButton',
                       command=lambda value=row['due_date_shamsi']: ShamsiDatePicker187(self, value)).pack(
                           side='left', padx=(m['gap'] // 2, 0))
            amount_box = ttk.Frame(box, style='Card.TFrame')
            amount_box.grid(row=0, column=0, sticky='ew', padx=m['gap'] // 2, pady=m['gap'] // 2)
            ttk.Label(amount_box, text='مبلغ (تومان)', anchor='e').pack(fill='x')
            amount_entry = ttk.Entry(amount_box, textvariable=row['amount'], justify='right')
            amount_entry.pack(fill='x')
            keep_numeric_cursor_at_end_187(amount_entry)

        total_variable = self.values.setdefault(
            'total_amount', tk.StringVar(value=str(self.contract.get('total_amount') or '')))
        summary = ttk.Label(host, anchor='e')
        summary.pack(fill='x', pady=(m['gap'], 0))

        def refresh_summary(*_args):
            refresh_schedule_summary_187(summary, total_variable, self.payment_values)

        for row in self.payment_values:
            row['amount'].trace_add('write', refresh_summary)
        total_variable.trace_add('write', refresh_summary)
        refresh_summary()

    def _page_terms(self, page) -> None:
        self._fields(page, TERM_FIELDS)
        m = kit_metrics()
        self._fields(page, SUPPLY_FIELDS)
        ttk.Button(page, text='بازخوانی مقادیر از پلان', command=self._repull_from_plan,
                   style='Toolbar.TButton').pack(anchor='e', pady=(m['gap'], 0))

    def _page_rows(self, page) -> None:
        self._build_rows(page)

    def _repull_from_plan(self) -> None:
        """Re-read this contract's own rows from the reference plan.

        Editing a contract used to lose its rows on every save (see
        ContractWizard187._seed_from_record); this is how an already-broken
        contract's estimate values come back without retyping them, and how
        a contract is refreshed after the reference workbook changes.
        """

        title = self.values.get('title')
        title_text = (title.get().strip() if title is not None
                      else str(self.contract.get('title') or ''))
        phase = self.values.get('build_phase')
        phase_no = plan_phase_no(phase.get() if phase is not None else '')
        if phase_no is None:
            return
        group = self.values.get('cost_group')
        cost_group = (group.get().strip() if group is not None
                     else str(self.contract.get('cost_group') or '')) or 'پیمانکار'
        planned = plan_rows_for_title(self.rich, phase_no, title_text, cost_group)
        if not planned:
            messagebox.showwarning(
                'بروزرسانی از پلان',
                'ردیفی برای این عنوان و فاز در پلان کلی پروژه پیدا نشد.', parent=self)
            return
        while len(self.row_values) < len(planned):
            self.row_values.append(blank_row_187(on_total_change=self._retotal_contract))
        del self.row_values[len(planned):]
        apply_plan_rows(self.row_values, planned)
        host = getattr(self, '_rows_grid_host', None)
        if host is not None and host.winfo_exists():
            for child in host.winfo_children():
                child.destroy()
            render_row_grid_187(host, self.row_values)
        count_var = getattr(self, '_row_count_var', None)
        if count_var is not None:
            count_var.set(str(len(self.row_values)))
        # apply_plan_rows only ever fills برآورد and حجم, never مبلغ واحد
        # قرارداد itself, so nothing here would already have re-totalled.
        self._retotal_contract()

    def _retotal_contract(self) -> None:
        """مبلغ کل قرارداد follows the sum of every row's own total, unless typed.

        فاز ساخت used to be read alongside the plan's own estimate; the total
        is the rows' own now, empty until a price is entered anywhere, and
        typing the amount directly still overrides it - the same rule هر
        ردیف already follows for a lump-sum row.
        """

        if getattr(self, '_total_busy', False):
            return
        variable = self.values.setdefault(
            'total_amount', tk.StringVar(value=str(self.contract.get('total_amount') or '')))
        total = contract_rows_total(self.row_values)
        self._total_busy = True
        try:
            variable.set(str(total) if total else '')
        finally:
            self._total_busy = False

    def _group(self, parent, title: str, row: int) -> ttk.LabelFrame:
        group = ttk.LabelFrame(parent, text=title, labelanchor='ne',
                               padding=kit_metrics()['gap'])
        group.grid(row=row, column=0, sticky='ew', padx=4, pady=4)
        return group

    def _fields(self, group, fields) -> None:
        """Two columns, right-hand one first, as the wizard lays them out."""

        m = kit_metrics()
        grid = ttk.Frame(group, style='Card.TFrame')
        grid.pack(fill='x')
        grid.columnconfigure((0, 1), weight=1, uniform='record')
        for position, (key, label) in enumerate(fields):
            row, column = divmod(position, 2)
            cell = ttk.Frame(grid, style='Card.TFrame')
            cell.grid(row=row, column=1 - column, sticky='ew',
                      padx=m['gap'] // 2, pady=m['gap'] // 2)
            ttk.Label(cell, text=label, anchor='e', justify='right').pack(fill='x')
            variable = self.values.setdefault(
                key, tk.StringVar(value=str(self.contract.get(key) or '')))
            if key == 'total_amount':
                group_number_while_typing_187(variable)
                variable.set(variable.get())
            entry = ttk.Entry(cell, textvariable=variable, justify='right')
            entry.pack(fill='x')
            if key in ('total_amount', 'duration_months'):
                keep_numeric_cursor_at_end_187(entry)

    def _file_line(self, group, key: str, label: str) -> None:
        p = kit_palette()
        m = kit_metrics()
        holder = ttk.Frame(group, style='Card.TFrame')
        holder.pack(fill='x', pady=m['gap'] // 2)
        variable = self.values.setdefault(
            key, tk.StringVar(value=str(self.contract.get(key) or '')))
        ttk.Label(holder, text=label, anchor='e', width=24).pack(side='right')

        def choose():
            path = filedialog.askopenfilename(parent=self, title=label)
            if path:
                variable.set(path)
                self._render_preview()

        ttk.Button(holder, text='انتخاب فایل', command=choose,
                   style='Toolbar.TButton').pack(side='right', padx=m['gap'] // 2)
        chosen = tk.Label(holder, bg=p['card'], fg=p['text_secondary'],
                          font=kit_font('small'), anchor='e')
        chosen.pack(side='right', fill='x', expand=True)

        def show(*_args):
            path = variable.get().strip()
            chosen.configure(text=Path(path).name if path else 'فایلی انتخاب نشده است',
                             fg=p['text_primary'] if path else p['empty'])

        variable.trace_add('write', show)
        show()

    def _build_rows(self, group) -> None:
        """The contract's rows, editable here as they are in the wizard,
        with the same تعداد ردیف control the wizard's own row page has.

        The شرح ردیف and the two unit prices are typed by hand and the plan
        takes what they say, so a contract entered in a hurry has to be
        correctable afterwards - which a read-only table did not allow.
        """

        self.row_values = []
        for stored in self.contract.get('rows') or []:
            row = blank_row_187(on_total_change=self._retotal_contract)
            for key, _label in ROW_COLUMNS:
                if key != 'no':
                    row[key].set(str(stored.get(key) or ''))
            row['plan_ref'].set(str(stored.get('plan_ref') or ''))
            self.row_values.append(row)
            recompute_row_totals_187(row)
        if not self.row_values:
            self.row_values.append(blank_row_187(on_total_change=self._retotal_contract))

        p = kit_palette()
        m = kit_metrics()
        header = tk.Frame(group, bg=p['card'])
        header.pack(fill='x', pady=(0, m['gap'] // 2))
        tk.Label(header, text='تعداد ردیف', bg=p['card'], fg=p['text_secondary'],
                font=kit_font('small'), anchor='e').pack(side='right', padx=(0, 4))
        self._row_count_var = tk.StringVar(value=str(max(1, len(self.row_values))))
        ttk.Spinbox(header, from_=1, to=60, textvariable=self._row_count_var, width=6,
                   justify='right', command=self._resize_rows).pack(side='right')
        ttk.Button(header, text='اعمال', command=self._resize_rows,
                  style='Toolbar.TButton').pack(side='right', padx=m['gap'] // 2)

        self._rows_grid_host = tk.Frame(group, bg=p['card'])
        self._rows_grid_host.pack(fill='x')
        render_row_grid_187(self._rows_grid_host, self.row_values)
        # Mirrors ContractWizard187._seed_from_record: a row's own
        # on_total_change fires while it is still being built, before it is
        # appended to self.row_values, so the last row restored is missing
        # from its own recompute until this runs once, after all are in place.
        self._retotal_contract()

    def _resize_rows(self) -> None:
        try:
            wanted = max(1, min(60, int(en(self._row_count_var.get() or '1'))))
        except (TypeError, ValueError):
            return
        while len(self.row_values) < wanted:
            self.row_values.append(blank_row_187(on_total_change=self._retotal_contract))
        del self.row_values[wanted:]
        host = getattr(self, '_rows_grid_host', None)
        if host is not None and host.winfo_exists():
            for child in host.winfo_children():
                child.destroy()
            render_row_grid_187(host, self.row_values)
        # A shrink drops rows without any of them reporting a change, so the
        # total is not automatically corrected the way growing it is.
        self._retotal_contract()

    def save(self) -> None:
        scheduled = schedule_amount_total_187(self.payment_values)
        total = int(_row_number(self.values.get(
            'total_amount', tk.StringVar(value=str(self.contract.get('total_amount') or ''))).get()))
        if scheduled != total:
            messagebox.showwarning(
                'شرایط پرداخت',
                f'جمع مراحل پرداخت ({_amount(scheduled)} تومان) باید با مبلغ کل قرارداد '
                f'({_amount(total)} تومان) برابر باشد.',
                parent=self)
            return
        record = dict(self.contract)
        record.update({key: variable.get() for key, variable in self.values.items()})
        record['rows'] = [
            {**{key: row[key].get() for key, _label in ROW_COLUMNS if key != 'no'},
             'plan_ref': row['plan_ref'].get()}
            for row in getattr(self, 'row_values', [])
        ]
        record['payment_stage_count'] = str(len(self.payment_values))
        record['payment_schedule'] = self._record_payment_schedule_data()
        self.contract = upsert_contract(record)
        if self.on_saved is not None:
            self.on_saved(self.contract)
        messagebox.showinfo('رکورد قرارداد', 'اطلاعات قرارداد ذخیره شد.', parent=self)


EXPORT_PROMPT_187 = 'خروجی'
EXPORT_FORMATS_187 = {'پی‌دی‌اف': 'pdf', 'اکسل': 'xlsx', 'پرینت': 'print'}


def _export_contract_detail_pdf(path, contract: dict[str, Any], *, orientation: str | None = None,
                               addressee='سایر', include_documents=True) -> None:
    """Everything the detail window shows: summary, rows, deposits and their
    receipts - one PDF, not just the five-field contract summary the generic
    قراردادها list export writes for every sub-tab alike.
    """

    from reportlab import platypus
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from export_utils import _pdf_font, _rtl

    font = _pdf_font()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    page_size = landscape(A4) if orientation == 'افقی' else A4
    doc = platypus.SimpleDocTemplate(str(path), pagesize=page_size, rightMargin=18, leftMargin=18,
                                     topMargin=18, bottomMargin=18)
    body = ParagraphStyle('body', fontName=font, fontSize=9, leading=12, alignment=TA_RIGHT)
    heading = ParagraphStyle('heading', parent=body, fontSize=12, leading=16)
    title_style = ParagraphStyle('title', parent=body, fontSize=15, leading=20)

    def table(headers, rows, *, receipt_col: int | None = None):
        # Source headers/rows are in logical (RTL-reading) order; ReportLab
        # lays columns out left-to-right, so both are reversed once here to
        # read right to left - export_receipts_pdf_187's own convention.
        # receipt_col is a logical-order index, so it is mirrored the same
        # way to land on the matching *physical* column after that reversal.
        physical_headers = list(reversed(headers))
        physical_rows = [list(reversed(row)) for row in rows]
        physical_receipt_col = None if receipt_col is None else len(headers) - 1 - receipt_col

        page_width = A4[0] - doc.leftMargin - doc.rightMargin
        receipt_width = 40 * mm if physical_receipt_col is not None else 0
        other_width = (page_width - receipt_width) / max(1, len(headers) - (1 if physical_receipt_col is not None else 0))
        col_widths = [receipt_width if i == physical_receipt_col else other_width for i in range(len(headers))]

        def cell(col: int, value: Any):
            if col != physical_receipt_col:
                return platypus.Paragraph(_rtl(str(value if value not in (None, '') else '-')), body)
            candidate = Path(str(value or ''))
            if value and candidate.exists() and candidate.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
                try:
                    return platypus.Image(str(candidate), width=40 * mm, height=56 * mm, kind='proportional')
                except (OSError, ValueError):
                    pass
            return platypus.Paragraph(_rtl('رسیدی ثبت نشده'), body)

        data = [[_rtl(h) for h in physical_headers]]
        data.extend([[cell(i, v) for i, v in enumerate(row)] for row in physical_rows])
        grid = platypus.Table(data, colWidths=col_widths, repeatRows=1, hAlign='RIGHT')
        grid.setStyle(platypus.TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font), ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#153B5B')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#B8C2CC')),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        return grid

    story = [platypus.Paragraph(_rtl(f"جزئیات قرارداد پیمانکار — {contract.get('title') or '-'}"), title_style)]
    story.append(platypus.Spacer(1, 8))
    summary = (
        f"شماره قرارداد: {fa(contract.get('contract_number') or '-')}    "
        f"عنوان: {contract.get('title') or '-'}    پیمانکار: {contract.get('family_name') or '-'}"
    )
    money = (
        f"مبلغ کل: {_amount(contract.get('total_amount'))}    "
        f"پرداخت‌شده: {_amount(paid_total(contract))}    مانده: {_amount(balance(contract))}"
    )
    story.extend([platypus.Paragraph(_rtl(summary), body), platypus.Paragraph(_rtl(money), body),
                 platypus.Paragraph(_rtl(f'جهت ارائه به: {addressee}'), body),
                 platypus.Spacer(1, 12)])

    row_list = contract.get('rows') or []
    story.append(platypus.Paragraph(_rtl('ردیف‌های قرارداد'), heading))
    story.append(platypus.Spacer(1, 4))
    if row_list:
        story.append(table(
            [label for _key, label in ROW_COLUMNS if _key != 'no'],
            [[_row_display_value_187(key, row.get(key, ''))
              for key, _label in ROW_COLUMNS if key != 'no'] for row in row_list],
        ))
    else:
        story.append(platypus.Paragraph(_rtl('ردیفی ثبت نشده است'), body))
    story.append(platypus.Spacer(1, 14))

    payments = contract.get('payments') or []
    story.append(platypus.Paragraph(_rtl('واریزی‌ها'), heading))
    story.append(platypus.Spacer(1, 4))
    if payments:
        payment_headers = [label for _key, label in PAYMENT_COLUMNS if _key != 'no'] + ['رسید']
        payment_rows = [
            [item.get(key, '') for key, _label in PAYMENT_COLUMNS if key != 'no']
            + [_receipt_image_path(item.get('pending_id', '')) if include_documents else '-']
            for item in payments
        ]
        story.append(table(payment_headers, payment_rows,
                           receipt_col=len(payment_headers) - 1 if include_documents else None))
    else:
        story.append(platypus.Paragraph(_rtl('سند پرداختی ثبت نشده است'), body))

    doc.build(story)


class ContractDetailWindow187(BarkavWindow):
    """Double-click view: the contract, its rows, its receipts and exports."""

    size_class = 'large'

    def __init__(self, parent, *, contract: dict[str, Any], on_export=None):
        self.contract = dict(contract)
        self.on_export = on_export
        super().__init__(parent, 'جزئیات قرارداد پیمانکار',
                         subtitle=str(contract.get('title') or ''))
        self._build()
        self.add_action('بستن', self.close)

    def _build(self) -> None:
        p = kit_palette()
        m = kit_metrics()

        # Top-left, one control instead of three separate buttons - the same
        # شکل و منطق as قراردادها's own «خروجی» in the main tab.
        export_bar = tk.Frame(self.body, bg=p['bg'])
        export_bar.pack(fill='x')
        self.export_choice = tk.StringVar(value=EXPORT_PROMPT_187)
        export_combo = ttk.Combobox(export_bar, textvariable=self.export_choice,
                                    values=(EXPORT_PROMPT_187, *EXPORT_FORMATS_187), state='readonly',
                                    justify='right', width=20)
        export_combo.pack(side='left', padx=m['gap'], pady=(0, m['gap']))
        export_combo.bind('<<ComboboxSelected>>', lambda _e: self._export_chosen())

        head = ttk.Frame(self.body, style='Card.TFrame', padding=m['gap'])
        head.pack(fill='x')
        # Two explicit lines - identity, then money - rather than one long
        # line left to wrap on its own. A tk.Label with no wraplength never
        # wraps at all; it just keeps going past the window's right-to-left
        # edge until the rest is clipped. Once one was set, wrapping still
        # broke mid-word inside «پرداخت‌شده»: Tk's line breaker does not treat
        # the ZWNJ in «پرداخت‌شده» as non-breaking, so the tail end of the
        # word could resurface at the start of the box. Lines short enough to
        # never need that automatic break avoid it; wraplength stays only as
        # a safety net for an unusually long title/family name.
        summary = (
            f"شماره قرارداد: {fa(self.contract.get('contract_number') or '-')}    "
            f"عنوان: {self.contract.get('title') or '-'}    "
            f"پیمانکار: {self.contract.get('family_name') or '-'}\n"
            f"مبلغ کل: {_amount(self.contract.get('total_amount'))}    "
            f"پرداخت‌شده: {_amount(paid_total(self.contract))}    "
            f"مانده: {_amount(balance(self.contract))}"
        )
        tk.Label(head, text=summary, bg=p['card'], fg=p['text_primary'],
                 font=kit_font('body'), anchor='e', justify='right',
                 wraplength=1300).pack(fill='x')

        row_list = self.contract.get('rows') or []
        rows = DataTable(self.body, ROW_COLUMNS, empty_text='ردیفی ثبت نشده است')
        # Not expand=True: a fixed row count should end its own box right
        # after the last row, not stretch to whatever space is left over.
        rows.pack(fill='x', pady=(m['gap'], 0))
        rows.set_rows([
            (fa(index + 1), row.get('description', ''), row.get('unit', ''),
             _row_display_value_187('unit_price', row.get('unit_price')),
             _row_display_value_187('estimate_price', row.get('estimate_price')),
             _row_display_value_187('quantity', row.get('quantity')),
             _row_display_value_187('estimate_quantity', row.get('estimate_quantity')),
             _row_display_value_187('line_total', row.get('line_total')),
             _row_display_value_187('estimate_total', row.get('estimate_total')))
            for index, row in enumerate(row_list)
        ])
        rows.tree.configure(height=max(1, len(row_list)))

        self._build_payments(self.body)

    def _build_payments(self, parent) -> None:
        """واریزی‌ها as cards, not a plain table - a receipt image sits beside
        each one, and a Treeview cell has no room for that."""

        p = kit_palette()
        m = kit_metrics()
        payments = self.contract.get('payments') or []

        section = tk.Frame(parent, bg=p['bg'])
        section.pack(fill='both', expand=True, pady=(m['gap'], 0))

        if not payments:
            tk.Label(section, text='سند پرداختی ثبت نشده است', bg=p['bg'],
                     fg=p['text_secondary'], font=kit_font('body')).pack(fill='both', expand=True)
            return

        list_host = _vertical_scroll_area(section, bg=p['bg'])
        for index, item in enumerate(payments):
            card = tk.Frame(list_host, bg=p['card'], highlightbackground=p['border_subtle'],
                            highlightthickness=1)
            card.pack(fill='x', pady=(0, m['gap']))

            _receipt_thumbnail(card, item.get('pending_id', '')).pack(
                side='left', padx=m['gap'], pady=m['gap'])

            details = tk.Frame(card, bg=p['card'])
            details.pack(side='right', fill='both', expand=True, padx=m['gap'], pady=m['gap'])
            tk.Label(details, text=f"ردیف {fa(index + 1)}", bg=p['card'], fg=p['text_primary'],
                     font=kit_font('body'), anchor='e').pack(fill='x')
            fields = (
                ('صاحب حساب', item.get('issuer', '') or '-'),
                ('گیرنده', item.get('receiver', '') or '-'),
                ('مبلغ واریزی (تومان)', _amount(item.get('amount'))),
                ('تاریخ', fa(item.get('date', '') or '-')),
            )
            for label, value in fields:
                field = tk.Frame(details, bg=p['card'])
                field.pack(fill='x', pady=(m['gap'] // 2, 0))
                tk.Label(field, text=f'{label}:', bg=p['card'], fg=p['text_secondary'],
                         font=kit_font('small'), anchor='e').pack(side='right')
                tk.Label(field, text=value, bg=p['card'], fg=p['text_primary'],
                         font=kit_font('small'), anchor='e').pack(side='right', padx=(0, m['gap'] // 2))

    def _export_chosen(self) -> None:
        """Run the export the dropdown names, then go back to naming itself."""

        fmt = EXPORT_FORMATS_187.get(self.export_choice.get())
        self.export_choice.set(EXPORT_PROMPT_187)
        if fmt is not None:
            self._export(fmt)

    def _export(self, fmt: str) -> None:
        formats = {'pdf': 'PDF', 'xlsx': 'Excel', 'print': 'پرینت'}
        self._export_pdf(print_after=fmt == 'print', preview=True,
                         export_format=formats.get(fmt, 'PDF'))

    def _preview_rows(self):
        headers = ['بخش', 'شرح', 'جزئیات', 'مبلغ', 'تاریخ', 'نمایش سند']
        rows = []
        for index, row in enumerate(self.contract.get('rows') or [], 1):
            rows.append([
                'ردیف قرارداد',
                row.get('description') or '-',
                f"حجم: {_row_display_value_187('quantity', row.get('quantity'))} "
                f"{row.get('unit') or ''}".strip(),
                _amount(row.get('line_total')),
                '-',
                '-',
            ])
        for index, payment in enumerate(self.contract.get('payments') or [], 1):
            rows.append([
                'واریزی',
                payment.get('receiver') or '-',
                f"صاحب‌حساب: {payment.get('issuer') or '-'}",
                _amount(payment.get('amount')),
                fa(payment.get('date') or '-'),
                _receipt_image_path(payment.get('pending_id', '')),
            ])
        if not rows:
            rows.append(['قرارداد', self.contract.get('title') or '-', 'ردیفی ثبت نشده است', '-', '-', '-'])
        return headers, rows
    def _export_pdf(self, *, print_after: bool, orientation='افقی', preview=False,
                    export_format='PDF', addressee='سایر', include_documents=True) -> None:
        if preview:
            headers, rows = self._preview_rows()
            specs = [
                ('خلاصه', 'پیمانکار', self.contract.get('family_name') or '-'),
                ('خلاصه', 'قرارداد', self.contract.get('title') or '-'),
                ('خلاصه', 'وضعیت', (
                    f"مبلغ کل: {_amount(self.contract.get('total_amount'))} | "
                    f"پرداخت‌شده: {_amount(paid_total(self.contract))} | "
                    f"مانده: {_amount(balance(self.contract))}"
                )),
            ]
            return show_export_preview_187(
                self,
                export_format=export_format,
                headers=headers,
                rows=rows,
                specs=specs,
                title='پیش‌نمایش جزئیات قرارداد پیمانکار',
                table_caption='جزئیات قرارداد و واریزی‌ها',
                row_label='ردیف',
                include_addressee=True,
                on_confirm=lambda choice, selected_orientation, selected_addressee, show_documents:
                    self._save_detail_export(choice, selected_orientation,
                                             selected_addressee, show_documents),
            )
        path = filedialog.asksaveasfilename(
            parent=self, title='خروجی جزئیات قرارداد', defaultextension='.pdf',
            filetypes=[('PDF', '*.pdf')])
        if not path:
            return
        try:
            _export_contract_detail_pdf(path, self.contract, orientation=orientation,
                                        addressee=addressee, include_documents=include_documents)
            if print_after and hasattr(os, 'startfile'):
                os.startfile(str(path), 'print')
        except Exception as exc:
            messagebox.showerror('خروجی', str(exc), parent=self)
            return
        messagebox.showinfo('خروجی', 'خروجی آماده شد.', parent=self)
        return True

    def _save_detail_export(self, choice, orientation, addressee, include_documents):
        suffix = '.xlsx' if choice == 'Excel' else '.pdf'
        path = filedialog.asksaveasfilename(
            parent=self, title=f'خروجی {choice} جزئیات قرارداد پیمانکار',
            defaultextension=suffix,
            filetypes=[('Excel', '*.xlsx')] if suffix == '.xlsx' else [('PDF', '*.pdf')],
        )
        if not path:
            return False
        headers, rows = self._preview_rows()
        rows = [list(row) for row in rows]
        if not include_documents:
            for row in rows:
                row[-1] = '-'
        summary = [
            f"پیمانکار: {self.contract.get('family_name') or '-'}",
            f"قرارداد: {self.contract.get('title') or '-'}",
            f'جهت ارائه به: {addressee}',
        ]
        try:
            if choice == 'Excel':
                from export_utils import export_xlsx
                export_xlsx(path, headers, rows, title='جزئیات قرارداد پیمانکار',
                            summary_lines=summary)
            else:
                _export_contract_detail_pdf(
                    path, self.contract, orientation=orientation,
                    addressee=addressee, include_documents=include_documents,
                )
                if choice == 'پرینت' and hasattr(os, 'startfile'):
                    os.startfile(str(path), 'print')
        except Exception as exc:
            messagebox.showerror('خروجی', str(exc), parent=self)
            return False
        messagebox.showinfo('خروجی', 'خروجی آماده شد.', parent=self)
        return True
