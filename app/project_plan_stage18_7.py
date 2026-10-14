"""پلان کلی پروژه and the four price tabs of مدیریت پروژه.

The plan sheet is the estimate workbook shown inside the product: the levels
the Excel file has, folded into one scrollable sheet.

  * a phase, holding cost types
  * a cost type - مصالح, پیمانکار or خدمات - holding sections
  * a section, holding the estimate rows
  * the rows, carrying the columns of the yellow master row of 'براورد کلی'

Both come from ``rich_phase_items`` and ``rich_price_items``; this module adds
no store of its own.  Every visual decision comes from ``barkav_ui``.
"""

from __future__ import annotations

from report_document_stage18_7 import selected_table_rows

import os
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from barkav_ui.table import DataTable
from barkav_ui.theme import font as kit_font, metrics as kit_metrics, palette as kit_palette
from barkav_ui.window import BarkavWindow
from numeric_entry_stage18_7 import format_numeric_entry, bind_editor_mousewheel
from project_table_actions187 import popup_menu, key_at
from ui_stage18_3 import en, fa, group_int_fa
from rate_policy_stage18_7 import updated_unit_price_187
from v18_store import load_ui
from plan_actual_prices187 import contract_prices187, wording187


PLAN_TAB = 'پلان کلی پروژه'

# The yellow master row of 'براورد کلی', column for column. That row is the
# workbook's own statement of what a line is, so it is what the sheet shows -
# every figure in its three states: اولیه, بروز, واقعی.
PLAN_COLUMNS = (
    ('no', 'ردیف'), ('code', 'کد قیمت'), ('title', 'عنوان'),
    ('phase', 'فاز اجرایی'), ('unit', 'واحد'),
    ('rate_base', 'قیمت واحد-اولیه'), ('rate_current', 'قیمت واحد-بروز'),
    ('rate_actual', 'قیمت واحد-واقعی'),
    ('qty_base', 'مقدار-اولیه'), ('qty_current', 'مقدار-بروز'),
    ('qty_actual', 'مقدار-واقعی'),
    ('total_base', 'مبلغ کل-اولیه'), ('total_current', 'مبلغ کل-بروز'),
    ('total_actual', 'مبلغ کل-واقعی'),
)
# A heading line: the fold mark, no price code, its label, then the middle
# left empty and the three totals.
BLANK_ROW = ('',) * (len(PLAN_COLUMNS) - 6)

# The outline, outermost first.  A phase holds cost types, a cost type holds
# sections, and a section holds the rows the workbook actually lists.
OPEN_MARK = '−'
SHUT_MARK = '+'


def rtl(text: str) -> str:
    """Force one string to lay out right to left.

    'فاز ۲۵ — UPVC' rendered as 'UPVC — فاز ۲۵': the Latin run took the line's
    direction with it. A right-to-left *mark* does not fix that - measured, it
    changes nothing on any side of the string - but an explicit embedding
    does, so the label is wrapped in one.
    """

    return '‫' + str(text) + '‬'


# Cost groups retain the workbook's letters, with land following services.
KIND_LETTERS = (('A', 'مصالح'), ('B', 'اجرت'), ('C', 'خدمات'), ('D', 'خرید زمین'))

EXPORT_HEADERS = ['ردیف', 'شماره فاز', 'عنوان فاز', 'نوع هزینه', 'بخش', 'عنوان',
                  'واحد', 'قیمت واحد-اولیه', 'قیمت واحد-بروز', 'قیمت واحد-واقعی',
                  'مقدار-اولیه', 'مقدار-بروز', 'مقدار-واقعی',
                  'مبلغ کل-اولیه', 'مبلغ کل-بروز', 'مبلغ کل-واقعی']

# Section 5's three cost types, as the workbook spells them.  'پیمانکار' is
# what the user calls اجرت: the work a contractor is engaged for.
COST_TYPES = {'مصالح': 'مصالح', 'پیمانکار': 'اجرت', 'خدمات': 'خدمات', 'خرید زمین': 'خرید زمین'}
KIND_LABELS = {stored: shown for shown, stored in COST_TYPES.items()}

ANY = 'همه'
PLAN_FILTERS = (ANY, 'شماره فاز', 'عنوان فاز', *COST_TYPES)

EXPORT_PROMPT = 'خروجی'
EXPORT_FORMATS = {'پی‌دی‌اف': 'pdf', 'اکسل': 'xlsx', 'پرینت': 'print'}

# One tab per price category, including the permanent land tab.
PRICE_TABS = (
    ('قیمت مصالح', 'MATERIAL'),
    ('قیمت پیمانکار', 'LABOR'),
    ('قیمت خدمات', 'SERVICE'),
    ('قیمت زمین', 'LAND'),
)

# The price sheets of the reference workbook, column for column. 'وضعیت' is
# not among them: the rebuilt file dropped it, so the column stood empty.
PRICE_COLUMNS = (
    # ردیف is the row's place in the list as shown - phase by phase, from 1
    # (operator request, 2026-09-27). The catalogue number it used to show
    # is still on screen, inside کد قیمت (A16 is catalogue number 16).
    ('row', 'ردیف'), ('price_code', 'کد قیمت'),
    ('description', 'عنوان'), ('unit', 'واحد'),
    # Every one of these is the price of a single unit - a metre, a day, a
    # bag - so each says so. 'واقعی' on its own read as a line's total.
    ('estimate_rate', 'قیمت واحد برآورد (تومان)'),
    ('forecast_rate', 'قیمت واحد بروز (تومان)'),
    ('actual_rate', 'قیمت واحد واقعی (تومان)'),
    ('qty_estimate', 'مقدار-اولیه'), ('qty_forecast', 'مقدار-بروز'),
    ('qty_actual', 'مقدار-واقعی'),
    ('total_estimate', 'مبلغ کل-اولیه'), ('total_forecast', 'مبلغ کل-بروز'),
    ('total_actual', 'مبلغ کل-واقعی'), ('source', 'فازهای مورد استفاده'),
)

PHASE_COUNT = 32


def _phase_order(item: dict[str, Any]) -> tuple:
    """Where a price sits when the list is read phase by phase.

    'فازهای مورد استفاده' holds one phase or several ('۰۲، ۱۶', or the
    editor's '16 — تاسیسات'); a price is filed under the first phase that
    uses it, then by its catalogue number. A price no phase uses yet goes
    last.
    """

    phases = sorted({int(n) for n in re.findall(r'\d+', str(en(str(item.get('source') or ''))))
                     if 0 < int(n) <= PHASE_COUNT})
    try:
        code = float(str(en(str(item.get('code') or ''))).strip() or 0)
    except ValueError:
        code = 0.0
    return (phases[0] if phases else PHASE_COUNT + 1, code)


def _money(value) -> str:
    try:
        return group_int_fa(int(round(float(str(en(str(value or '0'))).replace(',', '') or 0))))
    except (TypeError, ValueError):
        return fa(str(value or ''))


def _number(value) -> str:
    """A quantity or coefficient: no thousands grouping, no trailing zeros."""

    try:
        number = float(str(en(str(value or '0'))).replace(',', '') or 0)
    except (TypeError, ValueError):
        return fa(str(value or ''))
    return fa(f'{number:g}')


# The letter 'براورد کلی' gives each section, so one code reads the same in
# the plan, the price tabs and a phase window.
CATEGORY_LETTERS = {'MATERIAL': 'A', 'LABOR': 'B', 'SERVICE': 'C', 'LAND': 'D'}
COST_TYPE_LETTERS = {'مصالح': 'A', 'اجرت': 'B', 'خدمات': 'C', 'خرید زمین': 'D'}


def price_code(row: dict[str, Any]) -> str:
    """The catalogue code of the price a row is priced from.

    A rate belongs to the price, and one price serves every row that uses it -
    میلگرد is bought for several phases and costs the same in each. The code
    is what makes that visible: two rows carrying B34 are two rows that move
    together, and editing either rate edits one price.

    The quantity is not shared. It is the row's own, per phase, which is why
    the actual spend on میلگرد in اسکلت is not the actual spend on میلگرد
    anywhere else.
    """

    letter = (CATEGORY_LETTERS.get(str(row.get('category') or ''))
              or COST_TYPE_LETTERS.get(str(row.get('cost_type') or '').strip()))
    number = str(en(str(row.get('code') or ''))).strip()
    if not letter or not number:
        return ''
    try:
        return '%s%s' % (letter, int(float(number)))
    except (TypeError, ValueError):
        return '%s%s' % (letter, number)


def _as_number(value, default: float = 0.0) -> float:
    """A typed figure as a number: Persian digits and separators are display."""

    try:
        return float(str(en(str(value or ''))).replace(',', '').strip() or default)
    except (TypeError, ValueError):
        return default


def _grouped(value) -> str:
    """An amount with its thousands separated, ready for an entry box."""

    try:
        return group_int_fa(int(round(float(str(en(str(value or '0'))).replace(',', '') or 0))))
    except (TypeError, ValueError):
        return str(value or '')


def _group_as_typed(variable: tk.StringVar, entry) -> None:
    """Format after native text insertion, without moving the user's caret."""
    format_numeric_entry(entry, variable, _grouped)


def _plain(value) -> str:
    """A figure as it should sit in an entry box: no grouping, no trailing zeros."""

    try:
        number = float(str(en(str(value or '0'))).replace(',', '') or 0)
    except (TypeError, ValueError):
        return str(value or '')
    return f'{number:g}'


def _rate_of(row: dict[str, Any]) -> int:
    return int(row['estimate_rate']) if row.get('estimate_rate') is not None else int(row.get('local_estimate_rate') or 0)


def _rates(row: dict[str, Any]) -> tuple[int, int, int]:
    """Read the linked catalogue's three prices, including explicit zeros.

    Only a missing updated value uses the dollar/gold policy. Quantities and
    posted actual totals remain properties of the individual plan row.
    """
    estimate = _rate_of(row)
    stored_forecast = int(row.get('forecast_rate') or 0)
    if row.get('forecast_rate') is not None:
        updated = stored_forecast  # A stored value, including zero, is authoritative.
    else:
        try:
            settings = load_ui()
        except (OSError, ValueError, TypeError):
            settings = {}
        updated = updated_unit_price_187(
            estimate,
            settings.get('usd_rate_current'), settings.get('gold_rate_current'),
            settings.get('usd_rate_baseline'), settings.get('gold_rate_baseline'),
            settings.get('updated_rate_basis_187', 'دلار و طلا'),
        )
    actual = (int(row['_display_actual_rate187']) if '_display_actual_rate187' in row else
              int(row['actual_rate']) if row.get('actual_rate') is not None else int(row.get('local_actual_rate') or 0))
    if row.get('_actual_projection187') == 'ENGINEERING_AREA':
        actual = round(float(row['_display_actual_rate187']))
    return estimate, updated, actual


def _quantities(row: dict[str, Any]) -> tuple[float, float, float]:
    def number(key: str) -> float:
        try:
            return float(row.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    estimate = number('qty_estimate')
    updated = number('qty_forecast') if row.get('qty_forecast') is not None else estimate
    actual = number('_display_actual_quantity187') if '_display_actual_quantity187' in row else number('qty_actual')
    return estimate, updated, actual


def _totals(row: dict[str, Any]) -> tuple[int, int, int]:
    """The three line totals: quantity times coefficient times rate.

    Except واقعی, which is not that product at all: it is the money actually
    paid against this line, from the transactions and the contracts. A line
    can be priced and metred and still have had nothing paid on it, and then
    its واقعی total is zero - multiplying the two out would report money that
    has not moved.

    The other two stay computed, which is what keeps a line and the phase
    total above it in step.
    """

    try:
        factor = float(row.get('factor') or 1)
    except (TypeError, ValueError):
        factor = 1.0
    rates = _rates(row)
    quantities = _quantities(row)
    computed = [int(round(q * factor * r)) for q, r in zip(quantities, rates)]
    computed[2] = int(row.get('total_actual') or 0)
    return tuple(computed)


def project_actual_rows187(plan_rows) -> list[dict[str, Any]]:
    """One read-only actual projection shared by the plan and price tables.

    Posted costs stay intact. Inferred quantities must not become stored
    measurements merely because a table refreshed or an editor was opened.
    """
    rows = [dict(row) for row in plan_rows]
    for row in rows:
        for key in ('_display_actual_rate187', '_display_actual_quantity187', '_actual_projection187'):
            row.pop(key, None)
    contracts = contract_prices187(rows)
    for row in rows:
        total = _totals(row)[2]
        if '_engineering_area187' in row:
            area = float(row['_engineering_area187'] or 0)
            row['_display_actual_rate187'] = total / area if area > 0 else 0
            row['_display_actual_quantity187'] = area if total and area > 0 else 0
            row['_actual_projection187'] = 'ENGINEERING_AREA'
            continue
        if wording187(row.get('unit')) == 'مقطوع':
            row['_display_actual_rate187'] = total
            row['_actual_projection187'] = 'LUMP_SUM'
            continue
        contract = contracts.get(str(row.get('plan_ref') or ''))
        if contract is not None and (contract['quantity'] > 0 or total <= 0):
            row['_display_actual_rate187'] = contract['rate']
            row['_display_actual_quantity187'] = contract['quantity']
            row['_actual_projection187'] = 'CONTRACT'
        elif total > 0 and (_quantities(row)[2] <= 0 or contract is not None):
            updated_rate = _rates(row)[1]
            if updated_rate > 0:
                row['_display_actual_rate187'] = updated_rate
                row['_display_actual_quantity187'] = total / updated_rate
                row['_actual_projection187'] = 'ESTIMATED'
    return rows


def preserve_computed_actuals187(row, data):
    """An unchanged computed display is not a new manually entered value."""
    if not row.get('_actual_projection187'):
        return
    if int(_as_number(data.get('actual_rate'))) == _rates(row)[2]:
        data['actual_rate'] = row.get('actual_rate') if row.get('actual_rate') is not None else row.get('local_actual_rate', 0)
    if _as_number(data.get('qty_actual')) == _as_number(_plain(_quantities(row)[2])):
        data['qty_actual'] = row.get('qty_actual') or 0


def price_plan_totals187(plan_rows) -> dict[str, dict[str, Any]]:
    """One catalogue item's quantities and costs across its active plan rows."""
    result = {}
    for row in plan_rows:
        price_id = str(row.get('price_id') or '')
        if not price_id:
            continue
        summary = result.setdefault(price_id, dict(quantities=[0.0, 0.0, 0.0], totals=[0, 0, 0],
            rows=[], estimated=False, actual_rate=None))
        summary['rows'].append(row)
        summary['estimated'] |= row.get('_actual_projection187') == 'ESTIMATED'
        for index, value in enumerate(_quantities(row)):
            summary['quantities'][index] += value
        for index, value in enumerate(_totals(row)):
            summary['totals'][index] += value
    for summary in result.values():
        rows = summary.pop('rows')
        if all(row.get('_actual_projection187') == 'LUMP_SUM' for row in rows):
            summary['actual_rate'] = summary['totals'][2]
        elif any(row.get('_actual_projection187') for row in rows):
            quantity = summary['quantities'][2]
            summary['actual_rate'] = int(round(
                sum(_rates(row)[2] * _quantities(row)[2] for row in rows) / quantity
                if quantity > 0 else sum(_rates(row)[2] for row in rows) / len(rows)))
    return result


class PlanRowWindow187(BarkavWindow):
    """Edit one estimate row.  Opened by double-clicking the sheet."""

    size_class = 'small'

    # The sheet's own columns, plus the three it groups by. مبلغ کل is not
    # among them: it is quantity times coefficient times rate, so it is
    # reported under the fields rather than typed into.
    FIELDS = (
        ('phase_no', 'فاز اجرایی'), ('phase_name', 'عنوان فاز'),
        ('section', 'بخش'), ('cost_type', 'نوع هزینه'),
        ('description', 'عنوان'), ('unit', 'واحد'),
        ('estimate_rate', 'قیمت واحد-اولیه'), ('qty_estimate', 'مقدار-اولیه'),
        ('forecast_rate', 'قیمت واحد-بروز'), ('qty_forecast', 'مقدار-بروز'),
        ('actual_rate', 'قیمت واحد-واقعی'), ('qty_actual', 'مقدار-واقعی'),
        ('factor', 'ضریب'), ('source', 'منبع / توضیح'),
    )
    RATES = ('estimate_rate', 'forecast_rate', 'actual_rate')
    QUANTITIES = ('qty_estimate', 'qty_forecast', 'qty_actual')
    NUMERIC = (*QUANTITIES, *RATES, 'factor', 'phase_no')

    def __init__(self, parent, *, rich, row: dict[str, Any] | None = None, on_saved=None):
        self.rich = rich
        self.row = dict(row or {})
        if self.row.get('phase_item_id') and self.row.get('price_id'):
            price = rich.get_price(self.row['price_id']) or {}
            for key in ('estimate_rate', 'forecast_rate', 'actual_rate', 'code', 'category'):
                if key in price:
                    self.row[key] = price[key]
        if self.row.get('phase_item_id'):
            projected = project_actual_rows187(rich.all_phase_items())
            self.row = next((row for row in projected if row['phase_item_id'] == self.row['phase_item_id']), self.row)
        self.on_saved = on_saved
        self.created: str | None = None
        self.values: dict[str, tk.StringVar] = {}
        super().__init__(parent, 'ویرایش ردیف برآورد' if self.row.get('phase_item_id') else 'ردیف جدید برآورد',
                         subtitle=str(self.row.get('phase_name') or ''), show_footer=True, scrollable=True)
        self._build()
        bind_editor_mousewheel(self)
        self.add_action('ذخیره', self.save, style='Primary.TButton')
        self.add_action('بستن', self.close)

    def _build(self) -> None:
        p = kit_palette()
        m = kit_metrics()
        grid = tk.Frame(self.body, bg=p['bg'])
        grid.pack(fill='both', expand=True)
        grid.columnconfigure((0, 1), weight=1, uniform='plan')
        for position, (key, label) in enumerate(self.FIELDS):
            row, column = divmod(position, 2)
            cell = tk.Frame(grid, bg=p['bg'])
            cell.grid(row=row, column=1 - column, sticky='ew',
                      padx=m['gap'] // 2, pady=m['gap'] // 2)
            tk.Label(cell, text=label, bg=p['bg'], fg=p['text_secondary'],
                     font=kit_font('small'), anchor='e').pack(fill='x')
            if key in self.RATES:
                start = _grouped(_rates(self.row)[self.RATES.index(key)])
            elif key in self.QUANTITIES:
                start = _plain(_quantities(self.row)[self.QUANTITIES.index(key)])
            else:
                start = str(self.row.get(key) or '')
            variable = tk.StringVar(value=start)
            self.values[key] = variable
            if key == 'cost_type':
                ttk.Combobox(cell, textvariable=variable, values=tuple(COST_TYPES.values()),
                             state='readonly', justify='right').pack(fill='x')
                if not variable.get():
                    variable.set(COST_TYPES['خدمات'])
            else:
                entry = ttk.Entry(cell, textvariable=variable, justify='right')
                entry.pack(fill='x')
            if key in self.RATES:
                _group_as_typed(variable, entry)
            if key in self.RATES or key in self.QUANTITIES or key == 'factor':
                variable.trace_add('write', lambda *_a: self._retotal())

        # The three totals, reported rather than typed.
        line = tk.Frame(self.body, bg=p['bg'])
        line.pack(fill='x', pady=(m['gap'], 0))
        self._total_labels = []
        for label in ('مبلغ کل-اولیه', 'مبلغ کل-بروز', 'مبلغ کل-واقعی'):
            cell = tk.Frame(line, bg=p['bg'])
            cell.pack(side='right', fill='x', expand=True, padx=m['gap'] // 2)
            tk.Label(cell, text=label, bg=p['bg'], fg=p['text_secondary'],
                     font=kit_font('small'), anchor='e').pack(fill='x')
            value = tk.Label(cell, bg=p['panel2'], fg=p['text_primary'],
                             font=kit_font('body'), anchor='e')
            value.pack(fill='x')
            self._total_labels.append(value)
        if not self.values['factor'].get():
            self.values['factor'].set('1')
        self._retotal()

    def _retotal(self) -> None:
        labels = getattr(self, '_total_labels', None)
        if not labels:
            return
        factor = _as_number(self.values['factor'].get(), 1.0)
        for index, label in enumerate(labels):
            if not label.winfo_exists():
                continue
            if index == 2:
                label.configure(text=_grouped(_totals(self.row)[2]))
                continue
            rate = _as_number(self.values[self.RATES[index]].get())
            quantity = _as_number(self.values[self.QUANTITIES[index]].get())
            label.configure(text=_grouped(int(round(quantity * factor * rate))))

    def _save_rates(self, price_id, data) -> None:
        """All three unit prices belong to the linked catalogue item."""

        if not price_id:
            return
        self.rich.save_price_rates(
            str(price_id), int(_as_number(data['estimate_rate'])),
            int(_as_number(data['actual_rate'])), int(_as_number(data['forecast_rate'])))

    def save(self) -> None:
        data = {key: variable.get().strip() for key, variable in self.values.items()}
        if not data.get('description'):
            messagebox.showwarning('ردیف برآورد', 'عنوان ردیف لازم است.', parent=self)
            return
        for key in self.NUMERIC:
            data[key] = str(_as_number(data.get(key), 1.0 if key == 'factor' else 0.0))
        preserve_computed_actuals187(self.row, data)
        try:
            if self.row.get('phase_item_id'):
                self.rich.save_phase_item(
                    self.row['phase_item_id'],
                    section=data['section'], description=data['description'],
                    cost_type=data['cost_type'], unit=data['unit'],
                    qty_estimate=data['qty_estimate'], qty_forecast=data['qty_forecast'],
                    qty_actual=data['qty_actual'], factor=data['factor'] or 1,
                    source=data['source'])
                self._save_rates(self.row.get('price_id'), data)
            else:
                if (self.row.get('anchor_cost_type') and data['cost_type'] != self.row['anchor_cost_type']
                        and data['section'] == str(self.row.get('section') or '')):
                    data['section'] = ''
                self.created = self.rich.add_phase_item(
                    int(float(data['phase_no'] or 1)), data['phase_name'], data)
                fresh = self.rich.get_phase_item(self.created) or {}
                self._save_rates(fresh.get('price_id'), data)
        except Exception as exc:
            messagebox.showerror('ردیف برآورد', str(exc), parent=self)
            return
        if self.on_saved is not None:
            # Always the id, even when editing, where it is None. A callback
            # that took an argument and a call that passed none is what stopped
            # saving from working at all.
            self.on_saved(self.created)
        self.close()


class PhasePlanWindow187(BarkavWindow):
    """A whole phase on one screen: its name, and every row under it.

    Reached by selecting a phase heading and pressing ویرایش. Opening rows one
    at a time is fine for fixing one figure and hopeless for working through a
    phase, which is what the estimate is actually revised in.
    """

    size_class = 'large'

    # The plan sheet's own columns, in its order. The three totals are not
    # among the editable ones: they are quantity times coefficient times rate,
    # and they follow what is typed rather than being typed themselves.
    FIELDS = (
        ('description', 'شرح', 28), ('unit', 'واحد', 9),
        ('estimate_rate', 'قیمت واحد-اولیه', 14),
        ('forecast_rate', 'قیمت واحد-بروز', 14),
        ('actual_rate', 'قیمت واحد-واقعی', 14),
        ('qty_estimate', 'مقدار-اولیه', 9),
        ('qty_forecast', 'مقدار-بروز', 9),
        ('qty_actual', 'مقدار-واقعی', 9),
        ('factor', 'ضریب', 6),
        ('total_actual', 'مبلغ کل-واقعی', 15),
    )
    RATES = ('estimate_rate', 'forecast_rate', 'actual_rate')
    QUANTITIES = ('qty_estimate', 'qty_forecast', 'qty_actual')
    # Only two of the three are reported; مبلغ کل-واقعی is entered, because a
    # payment is often known when the quantity behind it is not.
    TOTALS = ('مبلغ کل-اولیه', 'مبلغ کل-بروز')

    def __init__(self, parent, *, rich, phase_no: int, on_saved=None):
        self.rich = rich
        self.phase_no = int(phase_no)
        self.on_saved = on_saved
        self.rows: list[dict[str, Any]] = []
        self.values: dict[str, dict[str, tk.StringVar]] = {}
        self.totals: dict[str, list[tk.Label]] = {}
        self.name = tk.StringVar()
        super().__init__(parent, 'ویرایش فاز %s' % fa('%02d' % self.phase_no),
                         show_footer=True, scrollable=True)
        self._build()
        self.add_action('ذخیره', self.save, style='Primary.TButton')
        self.add_action('بستن', self.close)

    # --- structure ----------------------------------------------------------

    def _build(self) -> None:
        p = kit_palette()
        m = kit_metrics()
        head = tk.Frame(self.body, bg=p['bg'])
        head.pack(fill='x', pady=(0, m['gap']))
        tk.Label(head, text='عنوان فاز', bg=p['bg'], fg=p['text_secondary'],
                 font=kit_font('small'), anchor='e').pack(side='right', padx=(0, m['gap'] // 2))
        ttk.Entry(head, textvariable=self.name, justify='right', width=36).pack(side='right')
        ttk.Button(head, text='افزودن ردیف', style='Toolbar.TButton',
                   command=lambda: self.add_row(None)).pack(side='left')

        self.grid = tk.Frame(self.body, bg=p['bg'])
        self.grid.pack(fill='both', expand=True)
        self._fill()

    def _fill(self) -> None:
        """Draw the phase from the database. Called again after any change."""

        for child in self.grid.winfo_children():
            child.destroy()
        self.values.clear()
        self.totals.clear()
        p = kit_palette()

        projected = {row['phase_item_id']: row for row in project_actual_rows187(self.rich.all_phase_items())}
        self.rows = [projected.get(row['phase_item_id'], row) for row in self.rich.list_phase_items(self.phase_no)]
        if self.rows and not self.name.get():
            self.name.set(str(self.rows[0].get('phase_name') or ''))

        headings = ('ردیف', 'کد قیمت',
                    *(label for _k, label, _w in self.FIELDS), *self.TOTALS, '')
        for column, label in enumerate(headings):
            tk.Label(self.grid, text=label, bg=p['heading'], fg=p['text_primary'],
                     font=kit_font('small')).grid(
                         row=0, column=len(headings) - 1 - column, sticky='ew', padx=1, pady=1)

        for line, item in enumerate(self.rows, 1):
            self._row(line, item, len(headings))

        if not self.rows:
            tk.Label(self.grid, text='این فاز ردیفی ندارد.', bg=p['bg'], fg=p['empty'],
                     font=kit_font('small'), anchor='e').grid(row=1, column=0, sticky='ew')

    def _row(self, line: int, item: dict[str, Any], width: int) -> None:
        p = kit_palette()
        item_id = str(item.get('phase_item_id') or '')
        fields: dict[str, tk.StringVar] = {}
        rates = _rates(item)
        quantities = _quantities(item)
        stripe = p['row_even'] if line % 2 else p['row_odd']

        tk.Label(self.grid, text=fa(str(item.get('plan_ref') or line)), bg=stripe,
                 fg=p['text_primary'], font=kit_font('small')).grid(
                     row=line, column=width - 1, sticky='ew', padx=1, pady=1)
        # The catalogue code: two rows carrying the same one share a rate.
        tk.Label(self.grid, text=price_code(item), bg=stripe,
                 fg=p['text_secondary'], font=kit_font('small')).grid(
                     row=line, column=width - 2, sticky='ew', padx=1, pady=1)

        for position, (key, _label, size) in enumerate(self.FIELDS):
            if key in self.RATES:
                start = _grouped(rates[self.RATES.index(key)])
            elif key in self.QUANTITIES:
                start = _plain(quantities[self.QUANTITIES.index(key)])
            elif key == 'total_actual':
                start = _grouped(_totals(item)[2])
            else:
                start = _plain(item.get(key)) if key == 'factor' else str(item.get(key) or '')
            variable = tk.StringVar(value=start)
            fields[key] = variable
            if key in self.RATES or key in self.QUANTITIES or key == 'factor':
                variable.trace_add('write', lambda *_a, i=item_id: self._retotal(i))
            entry = ttk.Entry(self.grid, textvariable=variable, justify='right', width=size)
            entry.grid(row=line, column=width - 3 - position, sticky='ew', padx=1, pady=1)
            if key in self.RATES or key == 'total_actual':
                _group_as_typed(variable, entry)

        labels = []
        for offset in range(len(self.TOTALS)):
            label = tk.Label(self.grid, bg=stripe, fg=p['text_primary'],
                             font=kit_font('small'), anchor='e', width=15)
            label.grid(row=line, column=width - 3 - len(self.FIELDS) - offset,
                       sticky='ew', padx=1, pady=1)
            labels.append(label)

        actions = tk.Frame(self.grid, bg=stripe)
        actions.grid(row=line, column=0, sticky='ew', padx=1)
        ttk.Button(actions, text='+', width=2, style='Toolbar.TButton',
                   command=lambda i=item_id: self.add_row(i)).pack(side='left')
        ttk.Button(actions, text='×', width=2, style='Toolbar.TButton',
                   command=lambda i=item_id: self.delete_row(i)).pack(side='left')

        self.values[item_id] = fields
        self.totals[item_id] = labels
        self._retotal(item_id)

    # --- figures ------------------------------------------------------------

    def _retotal(self, item_id: str) -> None:
        """Recompute one row's three totals from what is currently typed."""

        fields = self.values.get(item_id)
        labels = self.totals.get(item_id)
        if not fields or not labels:
            return
        factor = _as_number(fields['factor'].get(), 1.0)
        for index, label in enumerate(labels):
            if not label.winfo_exists():
                continue
            rate = _as_number(fields[self.RATES[index]].get())
            quantity = _as_number(fields[self.QUANTITIES[index]].get())
            label.configure(text=_grouped(int(round(quantity * factor * rate))))

    # --- rows ---------------------------------------------------------------

    def add_row(self, after: str | None) -> None:
        """A new row under the given one, or at the end when there is none."""

        self._store()
        try:
            created = self.rich.add_phase_item(self.phase_no, self.name.get().strip(), {
                'description': 'ردیف جدید',
                'cost_type': next((r.get('cost_type') for r in self.rows if r['phase_item_id'] == after), 'خدمات'), 'unit': '',
                'qty_estimate': 0, 'estimate_rate': 0, 'factor': 1,
                'section': next((str(r.get('section') or '') for r in self.rows
                                 if str(r.get('phase_item_id')) == after), ''),
            })
            self.rich.place_phase_item(created, after, renumber_price=True)
        except Exception as exc:
            messagebox.showerror('افزودن ردیف', str(exc), parent=self)
            return
        self._fill()

    def delete_row(self, item_id: str) -> None:
        row = next((r for r in self.rows if str(r.get('phase_item_id')) == item_id), None)
        if row is None:
            return
        if not messagebox.askyesno(
                'حذف ردیف', f"«{row.get('description') or ''}» حذف شود؟", parent=self):
            return
        self._store()
        try:
            self.rich.delete_phase_item(item_id)
            self.rich.renumber_phase(self.phase_no)
        except Exception as exc:
            messagebox.showerror('حذف ردیف', str(exc), parent=self)
            return
        self._fill()

    # --- saving -------------------------------------------------------------

    def _store(self) -> None:
        """Write what is on screen back, so a structural change keeps it."""

        name = self.name.get().strip()
        price_changes = {}
        for item_id, fields in self.values.items():
            original = next((r for r in self.rows if str(r.get('phase_item_id')) == item_id), {})
            changes = {key: str(_as_number(fields[key].get()))
                       for key in (*self.QUANTITIES, 'factor')}
            rates_data = {key: int(_as_number(fields[key].get())) for key in self.RATES}
            actual_data = {**rates_data, **changes}
            preserve_computed_actuals187(original, actual_data)
            changes['qty_actual'] = actual_data['qty_actual']
            rates_data['actual_rate'] = actual_data['actual_rate']
            changes['total_actual'] = str(int(_as_number(fields['total_actual'].get())))
            changes['description'] = fields['description'].get().strip()
            changes['unit'] = fields['unit'].get().strip()
            if name:
                changes['phase_name'] = name
            # Quantities stay on this line; all three unit prices are shared
            # by the rows referencing its catalogue item.
            self.rich.save_phase_item(item_id, **changes)
            rates = tuple(int(_as_number(rates_data[key])) for key in self.RATES)
            price_id = original.get('price_id')
            stored = dict(original)
            stored.pop('_display_actual_rate187', None)
            if price_id and rates != _rates(stored):
                price_changes[str(price_id)] = rates
        # A price can be used more than once in this phase. An unchanged
        # duplicate must not overwrite the figure edited on another row.
        for price_id, (estimate, forecast, actual) in price_changes.items():
            self.rich.save_price_rates(price_id, estimate, actual, forecast)

    def save(self) -> None:
        try:
            self._store()
        except Exception as exc:
            messagebox.showerror('ویرایش فاز', str(exc), parent=self)
            return
        if self.on_saved is not None:
            self.on_saved()
        self.close()


class ProjectPlanPanel187(ttk.Frame):
    """The estimate sheet: phases, their sections, and the rows underneath."""

    def __init__(self, parent: tk.Misc, *, rich, on_changed=None):
        super().__init__(parent, style='Panel.TFrame')
        self.rich = rich
        self.on_changed = on_changed
        # Which headings are unfolded, what is on each visible line, and the
        # rows themselves - read once, because thirty-two queries per redraw
        # is too much for something a click repeats.
        self._open: set[tuple] = set()
        self._nodes: list[tuple] = []
        self._cache: list[dict[str, Any]] | None = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        self.table = DataTable(self, PLAN_COLUMNS, empty_text='برآوردی بارگذاری نشده است')
        self.table.pack(fill='both', expand=True)
        # The three heading levels take the surfaces the contract already gives
        # headings, stepping inwards, rather than colours of their own.
        self.table.register_row_style('phase', background='heading')
        self.table.register_row_style('kind', background='surface_alt')
        self.table.register_row_style('section', background='panel2',
                                      foreground='text_secondary')
        # Unfolding is bound to the ردیف column, where the +/− sits, so the
        # rest of the row is free to be selected like any other table's.
        # A double click opens whatever the line stands for.
        self.table.tree.bind('<Button-1>', self._clicked, add='+')
        self.table.tree.bind('<Double-1>', self._opened, add='+')
        self.table.tree.bind('<Button-3>', self._context_menu, add='+')
        self._build_outline_controls187()

        # Right to left: what you do with a row, then what you are looking at,
        # then - away on the left - what you take out of it.
        self.table.add_tool('افزودن', self.add_row)
        self.table.add_tool('ویرایش', self.edit_selected)
        self.table.add_tool('حذف', self.delete_selected)

        self.filter_field = tk.StringVar(value=ANY)
        self.filter_value = tk.StringVar(value=ANY)
        self.table.toolbar.add_filter('نمایش براساس', self.filter_field, PLAN_FILTERS,
                                      command=self._filter_field_changed)
        self.filter_value_combo = self.table.toolbar.add_filter(
            None, self.filter_value, (ANY,), command=self.refresh)

        self.export_choice = tk.StringVar(value=EXPORT_PROMPT)
        self.table.add_export(self.export_choice, self._export_chosen, side='left')

    def _build_outline_controls187(self) -> None:
        """Keep the fold buttons beside the sheet, outside horizontal scrolling."""
        self.outline_bar187 = ttk.Frame(self.table._table_host, width=76,
                                       style='Panel.TFrame')
        self.outline_bar187.grid(row=0, column=2, sticky='ns', pady=(2, 0))
        self.outline_bar187.grid_propagate(False)
        self._outline_buttons187 = {}
        self._outline_row_keys187 = {}
        self._outline_job187 = None
        tree = self.table.tree
        original = tree.tk.splitlist(str(tree.cget('yscrollcommand') or ''))

        def scrolled(*args):
            if original:
                tree.tk.call(*original, *args)
            self._schedule_outline187()

        tree.configure(yscrollcommand=scrolled)
        tree.bind('<Configure>', self._schedule_outline187, add='+')
        self.outline_bar187.bind('<Map>', self._schedule_outline187, add='+')

    def _schedule_outline187(self, _event=None) -> None:
        if self._outline_job187 is None:
            self._outline_job187 = self.after_idle(self._paint_outline187)

    def _paint_outline187(self) -> None:
        self._outline_job187 = None
        tree = self.table.tree
        # Only visit the viewport; an unfolded estimate can contain thousands
        # of rows. Treeview's row positions keep the gutter aligned on scroll.
        visible = {}
        step = max(1, int(kit_metrics().get('row_height', 34)) // 2)
        seen = set()
        for y in range(0, tree.winfo_height(), step):
            iid = tree.identify_row(y)
            if not iid or iid in seen:
                continue
            seen.add(iid)
            node = self._outline_row_keys187.get(iid)
            key = node[0] if node else None
            box = tree.bbox(iid)
            if key is not None and box:
                visible[key] = box
        for key in set(self._outline_buttons187) - set(visible):
            self._outline_buttons187.pop(key).destroy()
        for key, (_x, y, _width, height) in visible.items():
            button = self._outline_buttons187.get(key)
            if button is None:
                button = ttk.Button(self.outline_bar187, width=2,
                    style='Toolbar.TButton', command=lambda target=key: self._toggle_outline187(target))
                self._outline_buttons187[key] = button
            button.configure(text=self._mark(key))
            level = {'phase': 0, 'kind': 1, 'section': 2}[key[0]]
            button.place(x=40 - level * 16, y=y + 2, width=32,
                         height=max(16, height - 4))

    def _toggle_outline187(self, key: tuple) -> None:
        self._open.discard(key) if key in self._open else self._open.add(key)
        self.after_idle(self.refresh)

    # --- data ---------------------------------------------------------------

    def _all_rows(self) -> list[dict[str, Any]]:
        """Every estimate row, read once and kept until something changes."""

        if self._cache is None:
            # One read for the lot. Asking phase by phase opened thirty-two
            # connections, and the first statement on each costs milliseconds.
            try:
                self._cache = project_actual_rows187(self.rich.all_phase_items())
            except Exception:
                self._cache = []
        return self._cache

    def _filter_field_changed(self) -> None:
        field = self.filter_field.get()
        rows = self._all_rows()
        if field == 'شماره فاز':
            seen = {int(r.get('phase_no') or 0) for r in rows}
            choices = (ANY, *(fa('%02d' % no) for no in sorted(seen)))
        elif field == 'عنوان فاز':
            seen = {str(r.get('phase_name') or '').strip() for r in rows}
            choices = (ANY, *sorted(v for v in seen if v))
        else:
            # A cost type is already the whole answer; there is nothing left
            # to narrow it by.
            choices = (ANY,)
        self.filter_value_combo.configure(values=choices)
        self.filter_value.set(ANY)
        self.refresh()

    def _matches(self, row: dict[str, Any]) -> bool:
        field = self.filter_field.get()
        if field in COST_TYPES:
            return str(row.get('cost_type') or '').strip() == COST_TYPES[field]
        wanted = self.filter_value.get()
        if wanted == ANY:
            return True
        if field == 'شماره فاز':
            try:
                return int(row.get('phase_no') or 0) == int(en(wanted))
            except (TypeError, ValueError):
                return True
        if field == 'عنوان فاز':
            return str(row.get('phase_name') or '').strip() == wanted
        return True

    # --- the outline --------------------------------------------------------

    def _outline(self) -> dict:
        """Group the rows the way 'براورد کلی' lays them out.

        Returns ``{phase_no: (name, {cost_type: [rows in workbook order]})}``.
        A section is not a grouping key here: its heading appears where its
        first row does, which is how the workbook reads.
        """

        tree: dict[int, tuple[str, dict[str, list]]] = {}
        for item in sorted(self._all_rows(),
                           key=lambda r: (int(r.get('phase_no') or 0),
                                          int(r.get('sort_order') or 0))):
            if not self._matches(item):
                continue
            phase_no = int(item.get('phase_no') or 0)
            _name, kinds = tree.setdefault(
                phase_no, (str(item.get('phase_name') or ''), {}))
            kind = str(item.get('cost_type') or '').strip() or 'خدمات'
            kinds.setdefault(kind, []).append(item)
        return dict(sorted(tree.items()))

    def _mark(self, key: tuple) -> str:
        return OPEN_MARK if key in self._open else SHUT_MARK

    def _heading(self, mark: str, label: str, group) -> tuple:
        """A heading line: what it is, and what it comes to in all three states."""

        totals = [0, 0, 0]
        for item in group:
            for index, value in enumerate(_totals(item)):
                totals[index] += value
        # A right-to-left mark holds the line together: a heading ending in
        # Latin - 'فاز ۲۵ — UPVC' - otherwise renders with the Latin first.
        return (mark, '', rtl(label), *BLANK_ROW, *(_money(value) for value in totals))

    @staticmethod
    def _section_ref(row: dict[str, Any]) -> str:
        """The workbook's number for a row's parent: '25-4-1' hangs off '25-4'."""

        ref = str(row.get('plan_ref') or '')
        return ref.rsplit('-', 1)[0] if ref.count('-') > 1 else ''

    def refresh(self) -> None:
        """Emit only what is open: phases first, then whatever is unfolded."""

        rows, kinds, self._nodes = [], {}, []
        for phase_no, (phase_name, by_kind) in self._outline().items():
            phase_key = ('phase', phase_no)
            kinds[len(rows)] = 'phase'
            rows.append(self._heading(
                self._mark(phase_key),
                'فاز %s — %s' % (fa('%02d' % phase_no), phase_name),
                [r for group in by_kind.values() for r in group]))
            self._nodes.append((phase_key, None))
            if phase_key not in self._open:
                continue
            # A, B then C, as the workbook letters them.
            for letter, kind in KIND_LETTERS:
                group = by_kind.get(kind)
                if not group:
                    continue
                kind_key = ('kind', phase_no, kind)
                kinds[len(rows)] = 'kind'
                rows.append(self._heading(self._mark(kind_key),
                                          '%s. %s' % (letter, KIND_LABELS[kind]), group))
                self._nodes.append((kind_key, None))
                if kind_key in self._open:
                    self._emit_rows(rows, kinds, phase_no, kind, group)
        self.table.set_rows(rows, status=kinds, keys=self._nodes)
        self._outline_row_keys187 = dict(zip(self.table.tree.get_children(), self._nodes))
        self._schedule_outline187()

    def _emit_rows(self, rows, kinds, phase_no: int, kind: str, group) -> None:
        """One cost type's rows, a section heading opening each section.

        Rows with no section belong straight to the cost type - the workbook
        only breaks one out when it has its own sub-rows.
        """

        seen = None
        for item in group:
            section = str(item.get('section') or '').strip()
            key = ('section', phase_no, kind, section) if section else None
            if section != seen:
                seen = section
                if key is not None:
                    kinds[len(rows)] = 'section'
                    rows.append(self._heading(
                        '%s %s' % (self._mark(key), fa(self._section_ref(item))),
                        section,
                        [r for r in group
                         if str(r.get('section') or '').strip() == section]))
                    self._nodes.append((key, None))
            if key is not None and key not in self._open:
                continue
            rows.append((
                fa(str(item.get('plan_ref') or '')),
                price_code(item),
                str(item.get('description') or ''),
                fa('%02d' % int(item.get('phase_no') or 0)),
                str(item.get('unit') or ''),
                *(_money(value) for value in _rates(item)),
                *(_number(value) for value in _quantities(item)),
                *(_money(value) for value in _totals(item)),
            ))
            self._nodes.append((None, str(item.get('phase_item_id') or '')))

    def _node_at(self, event):
        """The (group key, row id) pair under the pointer, or (None, None)."""

        try:
            index = self.table.tree.index(self.table.tree.identify_row(event.y))
            return self.table._sorted()[index][2]
        except (IndexError, tk.TclError, ValueError):
            return (None, None)

    def _column_at(self, event) -> str:
        """Which declared column the pointer is over, by key."""

        try:
            shown = self.table.tree.cget('displaycolumns')
            if shown in ('#all', ('#all',), ''):
                shown = self.table.tree.cget('columns')
            return str(shown[int(self.table.tree.identify_column(event.x)[1:]) - 1])
        except (IndexError, ValueError, tk.TclError):
            return ''

    def _clicked(self, event) -> None:
        # Only the ردیف column folds. Anywhere else is an ordinary click, so a
        # heading can be selected and ticked like any other row.
        if self._column_at(event) != 'no':
            return
        key, _item_id = self._node_at(event)
        if key is None:
            return
        self._toggle_outline187(key)

    def _opened(self, event):
        """Every line opens something: a row, a phase name, a section name."""

        key, item_id = self._node_at(event)
        if key is None:
            if item_id:
                self.edit_selected()
            return None
        if key[0] == 'phase':
            self._rename_phase(key[1])
        elif key[0] == 'section':
            self._rename_section(key[1], key[2], key[3])
        else:
            # A cost type is one of three fixed categories, so there is no name
            # to edit; the double click folds it instead.
            self._open.discard(key) if key in self._open else self._open.add(key)
            self.after_idle(self.refresh)
        return 'break'

    def _rename_section(self, phase_no: int, kind: str, section: str) -> None:
        """Rename a section across the rows of its phase and cost type."""

        from tkinter import simpledialog

        name = simpledialog.askstring('نام بخش', 'نام بخش:', initialvalue=section,
                                      parent=self)
        if not name or name.strip() == section:
            return
        for item in self._all_rows():
            if (int(item.get('phase_no') or 0) != phase_no
                    or str(item.get('cost_type') or '').strip() != kind
                    or str(item.get('section') or '').strip() != section):
                continue
            try:
                self.rich.save_phase_item(item['phase_item_id'], section=name.strip())
            except Exception as exc:
                messagebox.showerror('نام بخش', str(exc), parent=self)
                return
        self._saved()

    def _rename_phase(self, phase_no: int) -> None:
        """Rename a phase everywhere it appears - it is one name, not many."""

        from tkinter import simpledialog

        current = next((str(r.get('phase_name') or '') for r in self._all_rows()
                        if int(r.get('phase_no') or 0) == phase_no), '')
        name = simpledialog.askstring(
            'عنوان فاز', 'عنوان فاز %s:' % fa('%02d' % phase_no),
            initialvalue=current, parent=self)
        if not name or name.strip() == current:
            return
        for item in self._all_rows():
            if int(item.get('phase_no') or 0) != phase_no:
                continue
            try:
                self.rich.save_phase_item(item['phase_item_id'],
                                          phase_name=name.strip())
            except Exception as exc:
                messagebox.showerror('عنوان فاز', str(exc), parent=self)
                return
        self._saved()


    def _selected_row(self) -> dict[str, Any] | None:
        selection = self.table.tree.selection()
        if not selection:
            return None
        try:
            _key, item_id = self.table.selected_key()
        except (IndexError, tk.TclError, ValueError):
            return None
        if not item_id:
            return None
        return self.rich.get_phase_item(item_id)

    # --- actions ------------------------------------------------------------

    def _context_menu(self, event):
        actions = getattr(self, 'row_actions', None)
        iid = self.table.tree.identify_row(event.y)
        if iid:
            if iid not in self.table.tree.selection():
                self.table.tree.selection_set(iid)
            self.table.tree.focus(iid)
        key = key_at(self.table, iid)
        target = self.rich.get_phase_item(key[1]) if key and key[1] else self._selected_row()
        return popup_menu(self, event, [
            ('افزودن', self.add_row),
            ('کپی', lambda: actions.copy_plan() if actions else None),
            ('پیست', lambda: actions.paste_plan() if actions else None),
            ('حذف', self.delete_selected), ('ویرایش', self.edit_selected),
            ('رفتن به تب قیمت', lambda: actions.plan_to_price(target) if actions else None),
        ])

    def add_row(self) -> None:
        """Add under the selected row, and renumber what follows.

        A row's number is its position, so a row put anywhere but the end
        moves the numbers below it.
        """

        seed = self._selected_row() or {}
        node = self._selected_node()
        if not seed and node is not None:
            phase_no = int(node[1])
            seed = {
                'phase_no': phase_no,
                'phase_name': next((r.get('phase_name') for r in self._all_rows()
                                    if int(r.get('phase_no') or 0) == phase_no), ''),
                'cost_type': node[2] if node[0] in ('kind', 'section') else 'خدمات',
                'section': node[3] if node[0] == 'section' else '',
            }
        after = str(seed.get('phase_item_id') or '') or None
        PlanRowWindow187(self, rich=self.rich, row={
            'phase_no': seed.get('phase_no') or 1,
            'phase_name': seed.get('phase_name') or '',
            'section': seed.get('section') or '',
            'cost_type': seed.get('cost_type') or 'خدمات',
            'anchor_cost_type': seed.get('cost_type'),
            'factor': 1,
        }, on_saved=lambda created, target=after: self._added(created, target))

    def _added(self, created: str | None, after: str | None) -> None:
        if created:
            try:
                self.rich.place_phase_item(created, after, renumber_price=True)
            except Exception as exc:
                messagebox.showerror(PLAN_TAB, str(exc), parent=self)
        self._saved(created)

    def _reveal(self, item_id: str) -> None:
        """Unfold down to a row and select it.

        The sheet opens folded, so a row added into a closed phase left no
        sign that anything had happened - which read as the save failing.
        """

        self._cache = None
        row = self.rich.get_phase_item(item_id)
        if not row:
            return
        phase_no = int(row.get('phase_no') or 0)
        kind = str(row.get('cost_type') or '').strip() or 'خدمات'
        section = str(row.get('section') or '').strip()
        self._open.add(('phase', phase_no))
        self._open.add(('kind', phase_no, kind))
        if section:
            self._open.add(('section', phase_no, kind, section))
        self.refresh()
        for index, (_values, _state, (_key, rid)) in enumerate(self.table._sorted()):
            if rid == item_id:
                children = self.table.tree.get_children()
                if index < len(children):
                    self.table.tree.selection_set(children[index])
                    self.table.tree.see(children[index])
                return

    def edit_selected(self) -> None:
        """A row opens its own window; a phase opens all of it at once."""

        key = self._selected_node()
        if key is not None and key[0] == 'phase':
            PhasePlanWindow187(self, rich=self.rich, phase_no=key[1],
                               on_saved=self._saved)
            return
        row = self._selected_row()
        if row is None:
            messagebox.showinfo(PLAN_TAB, 'ابتدا یک ردیف یا یک فاز را انتخاب کنید.',
                                parent=self)
            return
        PlanRowWindow187(self, rich=self.rich, row=row, on_saved=self._saved)

    def _selected_node(self):
        """The heading key of the selected line, or None if it is a row."""

        selection = self.table.tree.selection()
        if not selection:
            return None
        try:
            return self.table.selected_key()[0]
        except (IndexError, tk.TclError, ValueError):
            return None

    def delete_selected(self) -> None:
        actions = getattr(self, 'row_actions', None)
        rows = actions.plan_rows() if actions else []
        for _key,item_id in ([] if actions else self.table.selected_keys()):
            try:
                item=self.rich.get_phase_item(item_id) if item_id else None
            except (IndexError,tk.TclError,ValueError):item=None
            if item:rows.append(item)
        if not rows:
            messagebox.showinfo(PLAN_TAB, 'ابتدا یک ردیف را انتخاب کنید.', parent=self)
            return
        from table_actions import select_delete_rows
        rows=select_delete_rows(self,rows,messagebox=messagebox)
        if not rows:return
        try:
            with self.rich.db.atomic():
                for row in rows:self.rich.delete_phase_item(str(row.get('phase_item_id')))
                for phase in {int(row.get('phase_no') or 0) for row in rows}:self.rich.renumber_phase(phase)
        except Exception as exc:
            messagebox.showerror('حذف ردیف', str(exc), parent=self)
            return
        self._saved()

    def _saved(self, created: str | None = None) -> None:
        self._cache = None
        self.refresh()
        if created:
            self._reveal(created)
        if self.on_changed is not None:
            self.on_changed()

    def _export_chosen(self) -> None:
        fmt = EXPORT_FORMATS.get(self.export_choice.get())
        self.export_choice.set(EXPORT_PROMPT)
        if fmt is not None:
            self.export(fmt)

    def export(self, fmt: str = 'xlsx') -> None:
        # An exported sheet has no headings to fold, so what the outline holds
        # as levels - phase, cost type, section - it carries as columns.
        headers = EXPORT_HEADERS
        payload = []
        selected_nodes = self.table.selected_keys()
        selected_keys = {str(item_id) for _group, item_id in selected_nodes if item_id}
        selected_groups = [group for group, _item_id in selected_nodes if group]
        for item in sorted(self._all_rows(),
                           key=lambda r: (int(r.get('phase_no') or 0),
                                          int(r.get('sort_order') or 0))):
            if selected_nodes and str(item.get('phase_item_id') or '') not in selected_keys:
                phase = int(item.get('phase_no') or 0)
                kind = str(item.get('cost_type') or '').strip() or 'خدمات'
                section = str(item.get('section') or '').strip()
                groups = {('phase', phase), ('kind', phase, kind), ('section', phase, kind, section)}
                if not any(group in groups for group in selected_groups):
                    continue
            if not self._matches(item):
                continue
            payload.append(dict(zip(headers, (
                fa(len(payload) + 1), fa('%02d' % int(item.get('phase_no') or 0)),
                str(item.get('phase_name') or ''),
                KIND_LABELS.get(str(item.get('cost_type') or '').strip(),
                                str(item.get('cost_type') or '')),
                str(item.get('section') or ''), str(item.get('description') or ''),
                str(item.get('unit') or ''),
                *(_money(v) for v in _rates(item)),
                *(_number(v) for v in _quantities(item)),
                *(_money(v) for v in _totals(item)),
            ))))
        if not payload:
            messagebox.showinfo('خروجی', 'ردیفی برای خروجی وجود ندارد.', parent=self)
            return
        write_export_187(self, headers, payload, fmt, PLAN_TAB)


class PricePanel187(ttk.Frame):
    """One price category - مصالح, پیمانکار or خدمات - as its own tab."""

    def __init__(self, parent: tk.Misc, *, rich, category: str, title: str,
                 on_edit=None, on_add=None, on_delete=None):
        super().__init__(parent, style='Panel.TFrame')
        self.rich = rich
        self.category = category
        self.title = title
        self._on_edit, self._on_add, self._on_delete = on_edit, on_add, on_delete
        self._price_ids: list[str] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        self.actual_note187 = tk.Label(self, text=(
            '* تمام یا بخشی از مقدار واقعی برآوردی است: قیمت واحد بخش برآوردی برابر قیمت واحد بروز '
            'و مقدار آن برابر مبلغ کل واقعی ÷ قیمت واحد بروز است. '
            'برای موارد مقطوع، قیمت واقعی برابر جمع هزینهٔ واقعی ردیف‌های مرتبط در پلان است.'),
            bg=kit_palette()['bg'], fg=kit_palette()['text_secondary'],
            font=kit_font('small'), anchor='e', justify='right', wraplength=1100)
        self.actual_note187.pack(side='bottom', fill='x', padx=kit_metrics()['gap'], pady=kit_metrics()['gap']//2)
        self.bind('<Configure>', lambda event: self.actual_note187.configure(wraplength=max(100, event.width-24)), add='+')
        self.table = DataTable(self, PRICE_COLUMNS, on_open=lambda _item: self.edit_selected(),
                               empty_text='قیمتی در این گروه ثبت نشده است',
                               sortable=True, checkable=True)
        self.table.pack(fill='both', expand=True)
        # Right to left: what you do with a price, then - centred - what you
        # are looking for, then what you take out on the left.
        self.table.add_tool('افزودن', self.add_row)
        self.table.add_tool('ویرایش', self.edit_selected)
        self.table.add_tool('حذف', self.delete_selected)

        self.export_choice = tk.StringVar(value=EXPORT_PROMPT)
        self.table.add_export(self.export_choice, self._export_chosen,
                              label=None, side='left')
        self.filter_text = tk.StringVar()
        self.filter_text.trace_add('write', lambda *_a: self.refresh())
        self.table.toolbar.add_search(self.filter_text, 'جستجو', side='center')
        self.table.tree.bind('<Button-3>', self._context_menu, add='+')

    def rows(self) -> list[dict[str, Any]]:
        try:
            return list(self.rich.list_prices(category=self.category, visible_only=True))
        except Exception:
            return []

    def refresh(self, *, plan_rows=None) -> None:
        term = self.filter_text.get().strip()
        if plan_rows is None:
            plan_rows = project_actual_rows187(self.rich.all_phase_items())
        summaries = price_plan_totals187(plan_rows)
        rows, self._price_ids = [], []
        for item in sorted(self.rows(), key=_phase_order):
            haystack = ' '.join(str(item.get(k) or '') for k in ('code', 'description', 'source'))
            if term and term not in haystack and en(term) not in en(haystack):
                continue
            summary = summaries.get(str(item.get('price_id') or ''),
                                    dict(quantities=(0, 0, 0), totals=(0, 0, 0)))
            actual_rate = summary.get('actual_rate')
            if wording187(item.get('unit')) == 'مقطوع':
                actual_rate = summary['totals'][2]
            elif actual_rate is None:
                actual_rate = item.get('actual_rate')
            star = ' *' if summary.get('estimated') else ''
            rows.append((
                fa(str(len(rows) + 1)), price_code(item),
                str(item.get('description') or ''),
                str(item.get('unit') or '-'), _money(item.get('estimate_rate')),
                _money(item.get('forecast_rate')), _money(actual_rate) + star,
                _number(summary['quantities'][0]), _number(summary['quantities'][1]),
                _number(summary['quantities'][2]) + star,
                *(_money(value) for value in summary['totals']),
                fa(str(item.get('source') or '-')),
            ))
            self._price_ids.append(str(item.get('price_id') or ''))
        self.table.set_rows(rows, keys=self._price_ids)

    def selected(self) -> dict[str, Any] | None:
        # By key, not by position: the table sorts, and a position stops
        # meaning anything the moment it does.
        price_id = self.table.selected_key()
        if not price_id:
            return None
        try:
            return self.rich.get_price(price_id)
        except AttributeError:
            return None

    def _export_chosen(self) -> None:
        fmt = EXPORT_FORMATS.get(self.export_choice.get())
        self.export_choice.set(EXPORT_PROMPT)
        if fmt is None:
            return
        headers = [label for _key, label in PRICE_COLUMNS]
        payload = [dict(zip(headers, row)) for row in selected_table_rows(self.table)]
        if not payload:
            messagebox.showinfo('خروجی', 'قیمتی برای خروجی وجود ندارد.', parent=self)
            return
        write_export_187(self, headers, payload, fmt, self.title)

    def _context_menu(self, event):
        item = self.table.tree.identify_row(event.y)
        if item:
            if item not in self.table.tree.selection():
                self.table.tree.selection_set(item)
            self.table.tree.focus(item)
        actions = getattr(self, 'row_actions', None)
        key = key_at(self.table, item)
        target = self.rich.get_price(key) if key else self.selected()
        return popup_menu(self, event, [
            ('افزودن', self.add_row),
            ('کپی', lambda: actions.copy_prices(self) if actions else None),
            ('پیست', lambda: actions.paste_prices(self) if actions else None),
            ('حذف', self.delete_selected), ('ویرایش', self.edit_selected),
            ('رفتن به پلان کلی', lambda: actions.price_to_plan(target) if actions else None),
        ])

    def _codes(self) -> list[tuple[float, str]]:
        """(code, price_id) for this category, in the catalogue's own order."""

        out = []
        for item in self.rows():
            try:
                code = float(en(str(item.get('code') or '')).strip() or 0)
            except ValueError:
                code = 0.0
            out.append((code, str(item.get('price_id') or '')))
        return sorted(out)

    def renumber(self) -> None:
        """Make the row numbers 1..N again, in their current order.

        A number inserted between two others is a fraction until this runs;
        after it the column reads straight down again.
        """

        try:
            with self.rich.db.tx() as con:
                for position, (_code, price_id) in enumerate(self._codes(), 1):
                    con.execute('UPDATE rich_price_items SET code=? WHERE price_id=?',
                                (str(position), price_id))
        except Exception:
            return
        self.refresh()

    def add_row(self) -> None:
        """Add below the selected row, so the new number follows it."""

        if self._on_add is None:
            return
        selected = self.selected()
        seed = {'category': self.category}
        if selected:
            try:
                # Half a step below its neighbour; renumber turns it whole.
                seed['code'] = str(float(en(str(selected.get('code') or 0))) + 0.5)
            except ValueError:
                pass
        self._on_add(self, seed)

    def edit_selected(self) -> None:
        row = self.selected()
        if row is None:
            messagebox.showinfo(self.title, 'ابتدا یک ردیف را انتخاب کنید.', parent=self)
            return
        if self._on_edit is not None:
            self._on_edit(self, row)

    def delete_selected(self) -> None:
        # Every ticked row, not just the first: the ticks exist so several
        # prices can be dealt with at once.
        rows = []
        for price_id in self.table.selected_keys():
            try:
                row = self.rich.get_price(price_id)
            except AttributeError:
                row = None
            if row:
                rows.append(row)
        if not rows:
            messagebox.showinfo(self.title, 'ابتدا یک ردیف را انتخاب کنید.', parent=self)
            return
        from table_actions import select_delete_rows,confirmed_delete,DeleteChoice
        rows=select_delete_rows(self,rows,messagebox=messagebox)
        if not rows:return
        if self._on_delete is not None:
            with confirmed_delete(DeleteChoice()):
                for row in rows:self._on_delete(self, row)
        self.renumber()


def write_export_187(parent, headers, payload, fmt: str, title: str, *, preview=True,
                     orientation=None, addressee='سایر', include_documents=True):
    if preview:
        from sales_claims_stage18_7 import show_export_preview_187
        choices = {'xlsx': 'Excel', 'pdf': 'PDF', 'print': 'پرینت'}
        return show_export_preview_187(
            parent,
            export_format=choices.get(fmt, 'PDF'),
            headers=headers,
            rows=payload,
            title=f'پیش‌نمایش {title}',
            table_caption=title,
            row_label='ردیف',
            include_addressee=True,
            on_confirm=lambda choice, selected_orientation, selected_addressee, show_documents: write_export_187(
                parent,
                headers,
                payload,
                {'Excel': 'xlsx', 'PDF': 'pdf', 'پرینت': 'print'}.get(choice, 'pdf'),
                title,
                preview=False,
                orientation=selected_orientation,
                addressee=selected_addressee,
                include_documents=show_documents,
            ),
        )
    """Save a table as PDF, Excel or straight to the printer."""

    from sales_claims_stage18_7 import export_contract_pdf_187
    from export_utils import export_xlsx

    suffixes = {'pdf': '.pdf', 'xlsx': '.xlsx', 'print': '.pdf'}
    suffix = suffixes.get(fmt, '.xlsx')
    path = filedialog.asksaveasfilename(
        parent=parent, title=f'خروجی {title}', defaultextension=suffix,
        filetypes=[(suffix.lstrip('.').upper(), f'*{suffix}')])
    if not path:
        return
    destination = Path(path)
    try:
        export_rows = [
            [row.get(header, '') if isinstance(row, dict) else row[index]
             for index, header in enumerate(headers)]
            for row in payload
        ]
        if not include_documents:
            document_columns = [index for index, header in enumerate(headers)
                                if header in {'نمایش سند', 'فیش واریزی', 'رسید', 'سند'}]
            for row in export_rows:
                for index in document_columns:
                    if index < len(row):
                        row[index] = '-'
        summary = [f'جهت ارائه به: {addressee}']
        if suffix == '.pdf':
            if orientation in {'افقی', 'عمودی'}:
                export_contract_pdf_187(
                    destination, headers, export_rows, title,
                    orientation=orientation,
                    summary_lines=summary,
                )
            else:
                export_contract_pdf_187(destination, headers, export_rows, title,
                                        summary_lines=summary)
            if fmt == 'print' and hasattr(os, 'startfile'):
                os.startfile(str(destination), 'print')
        else:
            export_xlsx(destination, headers, export_rows, title=title,
                        summary_lines=summary)
    except Exception as exc:
        messagebox.showerror('خروجی', str(exc), parent=parent)
        return
    messagebox.showinfo('خروجی', 'خروجی آماده شد.', parent=parent)
