"""Contractor صورت‌وضعیت records: the wizard and the record window.

Same split as contractor_contracts_stage18_7 - a wizard for step-by-step
entry, a record window for reviewing/editing an existing one afterwards -
and the same cancel-on-close rule: closing before تأیید نهایی never applies
an edit to an existing صورت‌وضعیت, only a brand-new one is carried on that
way.

A صورت‌وضعیت belongs to one قرارداد and reports what that contract's own
rows covered in one period: مقدار کارکرد این دوره against each row's
مبلغ واحد قرارداد, plus پاداش, minus جریمه.
"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from barkav_ui.theme import font as kit_font, metrics as kit_metrics, palette as kit_palette
from barkav_ui.window import BarkavWindow, BarkavWizard
from contractor_store_stage18_7 import (
    amount_of,
    balance,
    cumulative_statement_amount,
    get_contract,
    load_contracts,
    paid_total,
    previous_statement_row_totals,
    statements_for_contract,
    upsert_statement,
)
from sales_claims_stage18_7 import (
    export_statement_finance_detail_pdf_187, group_amount_while_typing_187,
    show_export_preview_187,
)
from ui_stage10 import DateField
from ui_stage18_3 import en, fa, group_int_fa


def _amount(value: Any) -> str:
    try:
        return group_int_fa(int(str(en(str(value or '0'))).replace(',', '') or 0))
    except (TypeError, ValueError):
        return fa(str(value or ''))


def _row_number(value: Any) -> float:
    try:
        return float(str(en(str(value or '0'))).replace(',', '').replace('٬', '') or 0)
    except (TypeError, ValueError):
        return 0.0


def contract_choices() -> list[str]:
    """'contract_id | عنوان — پیمانکار' - one string per contract, parsed back on save."""

    return [f"{c.get('contract_id')} | {c.get('title') or '-'} — {c.get('family_name') or '-'}"
           for c in load_contracts()]


def contract_id_from_choice(text: str) -> str:
    return str(text or '').split('|', 1)[0].strip()


def _format_row_number(value: float) -> str:
    """Whole کارکرد quantities read as plain integers; a fraction keeps its
    decimal - group_amount_while_typing_187 handles the grouping either way."""

    return str(int(value)) if value == int(value) else str(value)


def blank_statement_row(*, on_total_change=None,
                        cumulative_base: tuple[float, int] | None = None) -> dict[str, tk.StringVar]:
    """مبلغ کارکرد دوره follows مبلغ واحد قرارداد × مقدار کارکرد این دوره.

    کارکرد کل / مبلغ کارکرد تجمیعی follow the same مقدار/مبلغ دوره, added onto
    ``cumulative_base`` - the matching row's own running total from the
    صورت‌وضعیت immediately before this one (zero for صورت‌وضعیت شماره ۱).
    """

    row = {
        'description': tk.StringVar(), 'unit_price': tk.StringVar(),
        'contract_quantity': tk.StringVar(), 'worked_quantity': tk.StringVar(),
        'line_total': tk.StringVar(), 'cumulative_quantity': tk.StringVar(),
        'cumulative_amount': tk.StringVar(),
    }
    # Grouping is attached once each row's own Entry exists instead - see
    # render_statement_row_grid. A write trace registered on a bare StringVar
    # fires ahead of the Entry's own; by the time this one's nested re-set
    # settles the digits, the Entry's sync trace has already read a value
    # from before that happened, and the cell shows what was set, not what
    # the variable actually holds once a widget is bound to it.

    base_quantity, base_amount = cumulative_base or (0.0, 0)
    state = {'busy': False}

    def recompute(*_args):
        if state['busy']:
            return
        price = _row_number(row['unit_price'].get())
        quantity = _row_number(row['worked_quantity'].get())
        state['busy'] = True
        try:
            has_total = price > 0 and quantity > 0
            total = int(round(price * quantity)) if has_total else int(_row_number(row['line_total'].get()))
            # Set both cumulative columns before مبلغ کارکرد دوره itself - its
            # own write is what notifies on_total_change, and a footer
            # listening for that must see the cumulative columns already
            # settled, not whatever they held before this keystroke.
            row['cumulative_quantity'].set(_format_row_number(base_quantity + quantity))
            row['cumulative_amount'].set(str(int(round(base_amount + total))))
            if has_total:
                row['line_total'].set(str(total))
        finally:
            state['busy'] = False

    # A brand-new row never writes مقدار کارکرد این دوره until the operator
    # types into it - without this, کارکرد کل/مبلغ کارکرد تجمیعی would sit
    # blank instead of reading whatever صورت‌وضعیت قبل already reached.
    if base_quantity or base_amount:
        row['cumulative_quantity'].set(_format_row_number(base_quantity))
        row['cumulative_amount'].set(str(int(round(base_amount))))
    row['worked_quantity'].trace_add('write', recompute)
    if on_total_change is not None:
        row['line_total'].trace_add('write', lambda *_a: on_total_change())
    return row


def rows_from_contract(contract: dict[str, Any], *, on_total_change=None,
                       statement_id: str | None = None) -> list[dict[str, tk.StringVar]]:
    """One صورت‌وضعیت row per priced contract row; مقدار کارکرد starts blank.

    ``statement_id`` names the صورت‌وضعیت these rows belong to (None for a
    brand-new one) so کارکرد کل/مبلغ کارکرد تجمیعی can start from whatever
    the previous صورت‌وضعیت on this same قرارداد already reached.
    """

    contract_id = contract.get('contract_id') or ''
    rows = []
    for source in contract.get('rows') or []:
        description = str(source.get('description') or '').strip()
        if not description:
            continue
        base = previous_statement_row_totals(contract_id, description, before_statement_id=statement_id)
        row = blank_statement_row(on_total_change=on_total_change, cumulative_base=base)
        row['description'].set(description)
        row['unit_price'].set(str(source.get('unit_price') or ''))
        row['contract_quantity'].set(str(source.get('quantity') or ''))
        rows.append(row)
    return rows


STATEMENT_ROW_COLUMNS = (
    ('no', 'ردیف'), ('description', 'شرح'), ('unit_price', 'مبلغ واحد قرارداد'),
    ('contract_quantity', 'حجم کل قرارداد'), ('worked_quantity', 'مقدار کارکرد این دوره'),
    ('line_total', 'مبلغ کارکرد دوره'),
    ('cumulative_quantity', 'کارکرد کل'), ('cumulative_amount', 'مبلغ کارکرد تجمیعی'),
)
STATEMENT_ROW_WIDTHS = {
    'no': 5, 'description': 26, 'unit_price': 14,
    'contract_quantity': 12, 'worked_quantity': 16, 'line_total': 14,
    'cumulative_quantity': 12, 'cumulative_amount': 16,
}
STATEMENT_READONLY_ROW_KEYS = ('description', 'unit_price', 'contract_quantity',
                              'cumulative_quantity', 'cumulative_amount')
STATEMENT_ROW_KEYS = ('description', 'unit_price', 'contract_quantity', 'worked_quantity',
                      'line_total', 'cumulative_quantity', 'cumulative_amount')


def render_statement_row_grid(parent, rows: list[dict[str, tk.StringVar]]) -> tk.Frame:
    """شرح, مبلغ واحد قرارداد and حجم کل قرارداد are read-only reference from
    the contract itself; only مقدار کارکرد این دوره is typed."""

    p = kit_palette()
    grid = tk.Frame(parent, bg=p['bg'])
    grid.pack(fill='x')
    for column, (key, label) in enumerate(STATEMENT_ROW_COLUMNS):
        position = len(STATEMENT_ROW_COLUMNS) - 1 - column
        tk.Label(grid, text=label, bg=p['bg'], fg=p['text_secondary'],
                 font=kit_font('small'), anchor='e').grid(
                     row=0, column=position, sticky='ew', padx=3, pady=(0, 4))
        grid.columnconfigure(position, weight=1, minsize=STATEMENT_ROW_WIDTHS[key] * 8)
    for index, row in enumerate(rows):
        for column, (key, _label) in enumerate(STATEMENT_ROW_COLUMNS):
            position = len(STATEMENT_ROW_COLUMNS) - 1 - column
            if key == 'no':
                tk.Label(grid, text=fa(index + 1), bg=p['bg'], fg=p['text_secondary'],
                         font=kit_font('small')).grid(row=index + 1, column=position,
                                                      sticky='ew', padx=3, pady=2)
                continue
            state = 'readonly' if key in STATEMENT_READONLY_ROW_KEYS else 'normal'
            ttk.Entry(grid, textvariable=row[key], justify='right',
                     width=STATEMENT_ROW_WIDTHS[key], state=state).grid(
                         row=index + 1, column=position, sticky='ew', padx=3, pady=2)
            # Attached now that this cell's own Entry exists - see
            # blank_statement_row for why the order matters. Whatever was
            # already set (a contract's own مبلغ واحد/حجم, populated before
            # this trace existed) is reformatted too - attaching a trace does
            # not retroactively apply it to the current value. _row_number
            # already strips both the grouping and the digits back out, so
            # حجم/مقدار read the same as before once typed into a calculation.
            if key in ('unit_price', 'contract_quantity', 'worked_quantity', 'line_total',
                      'cumulative_quantity', 'cumulative_amount'):
                group_amount_while_typing_187(row[key])
                row[key].set(row[key].get())
    return grid


STATEMENT_TYPES = ('موقت', 'قطعی')
DEFAULT_STATEMENT_TYPE = STATEMENT_TYPES[0]

# شماره صورت‌وضعیت, then نوع صورت‌وضعیت right after it, then the three real
# Shamsi dates - each rendered with the app's own calendar field, not a
# plain text box.
NUMBER_FIELD = ('statement_number', 'شماره صورت‌وضعیت')
DATE_FIELDS = (
    ('statement_date', 'تاریخ صورت‌وضعیت'), ('period_from', 'دوره از'), ('period_to', 'دوره تا'),
)


def _persian_digits_while_typing(variable: tk.StringVar) -> None:
    """Show whatever is typed in Persian digits - no grouping, since
    شماره صورت‌وضعیت is an identifier, not an amount."""

    state = {'busy': False}

    def reformat(*_args):
        if state['busy']:
            return
        converted = fa(variable.get())
        if converted != variable.get():
            state['busy'] = True
            try:
                variable.set(converted)
            finally:
                state['busy'] = False

    variable.trace_add('write', reformat)


def _render_statement_identity_fields(parent, get_var, *, bg: str) -> None:
    """شماره صورت‌وضعیت, نوع صورت‌وضعیت and the three period dates - identical
    in the wizard's اول window and the record's اول box, save for where each
    keeps its own StringVars and what background their row sits on."""

    p = kit_palette()
    m = kit_metrics()

    def field_row(key: str, label: str, default: str = ''):
        holder = tk.Frame(parent, bg=bg)
        holder.pack(fill='x', pady=(m['gap'] // 2, 0))
        tk.Label(holder, text=label, bg=bg, fg=p['text_secondary'],
                font=kit_font('small'), anchor='e', width=22).pack(side='right')
        return holder, get_var(key, default)

    holder, variable = field_row(*NUMBER_FIELD)
    # Attached after the Entry exists, not before: a write trace registered
    # on a bare StringVar fires ahead of the Entry's own - by the time this
    # one's nested re-set settles the digits, the Entry's sync trace reads a
    # value from before that happened, and the box shows what was typed, not
    # what the variable actually holds once the widget is bound to it.
    ttk.Entry(holder, textvariable=variable, justify='right').pack(
        side='right', fill='x', expand=True, padx=m['gap'] // 2)
    _persian_digits_while_typing(variable)

    holder, type_variable = field_row('statement_type', 'نوع صورت‌وضعیت', DEFAULT_STATEMENT_TYPE)
    ttk.Combobox(holder, textvariable=type_variable, values=STATEMENT_TYPES,
                state='readonly', justify='right').pack(
        side='right', fill='x', expand=True, padx=m['gap'] // 2)

    for key, label in DATE_FIELDS:
        holder, variable = field_row(key, label)
        DateField(holder, variable, width=13).pack(
            side='right', fill='x', expand=True, padx=m['gap'] // 2)
BONUS_FIELDS = (('bonus_amount', 'پاداش (تومان)'), ('penalty_amount', 'جریمه دیرکرد (تومان)'))


class StatementWizard187(BarkavWizard):
    """Four windows: مشخصات, ردیف‌ها, پاداش/جریمه, تأیید نهایی."""

    size_class = 'medium'
    step_titles = ('مشخصات صورت‌وضعیت', 'ردیف‌های قرارداد', 'پاداش و جریمه', 'تأیید نهایی')

    def __init__(self, parent, *, rich=None, on_saved=None, statement: dict[str, Any] | None = None):
        self.rich = rich
        self.on_saved = on_saved
        self.record = dict(statement or {})
        self.values: dict[str, tk.StringVar] = {}
        self.row_values: list[dict[str, tk.StringVar]] = []
        self._saved_once = False
        title = 'ویرایش صورت‌وضعیت' if statement else 'ثبت صورت‌وضعیت جدید'
        super().__init__(parent, title, subtitle='BARKAV 18.7')
        self._seed_from_record()

    def _var(self, key: str, default: str = '') -> tk.StringVar:
        if key not in self.values:
            self.values[key] = tk.StringVar(value=str(default))
        return self.values[key]

    def _seed_from_record(self) -> None:
        for key, value in self.record.items():
            if isinstance(value, (str, int, float)):
                self._var(key).set(str(value))
        contract_id = self.record.get('contract_id')
        if contract_id:
            for choice in contract_choices():
                if contract_id_from_choice(choice) == str(contract_id):
                    self._var('contract_id').set(choice)
                    break
        rows = [r for r in (self.record.get('rows') or []) if isinstance(r, dict)]
        if rows:
            self.row_values = []
            statement_id = self.record.get('statement_id')
            for source in rows:
                description = str(source.get('description') or '').strip()
                base = previous_statement_row_totals(str(contract_id or ''), description,
                                                     before_statement_id=statement_id)
                row = blank_statement_row(on_total_change=self._retotal, cumulative_base=base)
                for key in ('description', 'unit_price', 'contract_quantity',
                           'worked_quantity', 'line_total'):
                    row[key].set(str(source.get(key) or ''))
                self.row_values.append(row)
            self._retotal()

    def _contract(self) -> dict[str, Any] | None:
        cid = contract_id_from_choice(self._var('contract_id').get())
        return get_contract(cid) if cid else None

    def _contract_chosen(self, *_args) -> None:
        contract = self._contract()
        if contract is None:
            return
        self.row_values = rows_from_contract(contract, on_total_change=self._retotal,
                                             statement_id=self.record.get('statement_id'))
        self.show_step(self._step)
        self._retotal()

    def _retotal(self) -> None:
        total = sum(int(_row_number(row['line_total'].get())) for row in self.row_values)
        bonus = amount_of(self._var('bonus_amount').get())
        penalty = amount_of(self._var('penalty_amount').get())
        combined = total + bonus - penalty
        self._var('amount').set(str(max(combined, 0)) if (total or bonus or penalty) else '')
        self._show_total()
        self._show_row_totals()

    def _show_total(self) -> None:
        caption = getattr(self, '_amount_caption', None)
        if caption is None or not caption.winfo_exists():
            return
        amount = self._var('amount').get()
        caption.configure(
            text=f'مبلغ صورت‌وضعیت: {_amount(amount)} تومان' if amount
            else 'مبلغ صورت‌وضعیت از ردیف‌ها محاسبه می‌شود')

    def _show_row_totals(self) -> None:
        caption = getattr(self, '_row_totals_caption', None)
        if caption is None or not caption.winfo_exists():
            return
        period_total = int(sum(_row_number(row['line_total'].get()) for row in self.row_values))
        cumulative_total = int(sum(_row_number(row['cumulative_amount'].get()) for row in self.row_values))
        caption.configure(
            text=f'مبلغ کل صورت‌وضعیت دوره: {_amount(period_total)} تومان'
                 f'    |    مبلغ کل صورت‌وضعیت تجمیعی: {_amount(cumulative_total)} تومان')

    # --- rendering -----------------------------------------------------------

    def render_step(self, index: int, parent: tk.Frame) -> None:
        p = kit_palette()
        m = kit_metrics()
        tk.Label(parent, text=f'‏{fa(index + 1)}. {self.step_titles[index]}',
                bg=p['bg'], fg=p['text_primary'], font=kit_font('title'),
                anchor='e').pack(fill='x', pady=(0, m['gap']))
        if index == 0:
            self._render_details(parent)
        elif index == 1:
            self._render_rows(parent)
        elif index == 2:
            self._render_bonus(parent)
        else:
            self._render_confirm(parent)

    def _render_details(self, parent) -> None:
        p = kit_palette()
        m = kit_metrics()
        holder = tk.Frame(parent, bg=p['bg'])
        holder.pack(fill='x', pady=(0, m['gap']))
        tk.Label(holder, text='قرارداد', bg=p['bg'], fg=p['text_secondary'],
                font=kit_font('small'), anchor='e', width=22).pack(side='right')
        variable = self._var('contract_id')
        ttk.Combobox(holder, textvariable=variable, values=contract_choices(),
                    state='readonly', justify='right').pack(
            side='right', fill='x', expand=True, padx=m['gap'] // 2)
        variable.trace_add('write', self._contract_chosen)

        _render_statement_identity_fields(parent, self._var, bg=p['bg'])

    def _render_rows(self, parent) -> None:
        p = kit_palette()
        m = kit_metrics()
        if not self.row_values:
            tk.Label(parent, text='ابتدا یک قرارداد را از پنجرهٔ اول انتخاب کنید.',
                    bg=p['bg'], fg=p['text_secondary'], font=kit_font('body'),
                    anchor='e').pack(fill='x')
            return
        render_statement_row_grid(parent, self.row_values)
        self._row_totals_caption = tk.Label(parent, bg=p['bg'], fg=p['text_secondary'],
                                            font=kit_font('small'), anchor='e', justify='right')
        self._row_totals_caption.pack(fill='x', pady=(m['gap'], 0))
        self._show_row_totals()

    def _render_bonus(self, parent) -> None:
        p = kit_palette()
        m = kit_metrics()
        for key, label in BONUS_FIELDS:
            row = tk.Frame(parent, bg=p['bg'])
            row.pack(fill='x', pady=(0, m['gap']))
            tk.Label(row, text=label, bg=p['bg'], fg=p['text_secondary'],
                    font=kit_font('small'), anchor='e', width=22).pack(side='right')
            variable = self._var(key)
            ttk.Entry(row, textvariable=variable, justify='right').pack(
                side='right', fill='x', expand=True, padx=m['gap'] // 2)
            # Attached after the Entry exists - see blank_statement_row for
            # why the order matters.
            group_amount_while_typing_187(variable)
            variable.trace_add('write', lambda *_a: self._retotal())
        self._amount_caption = tk.Label(parent, bg=p['bg'], fg=p['text_secondary'],
                                        font=kit_font('small'), anchor='e')
        self._amount_caption.pack(fill='x', pady=(m['gap'], 0))
        self._retotal()

    def _render_confirm(self, parent) -> None:
        p = kit_palette()
        m = kit_metrics()
        contract = self._contract() or {}
        summary = (
            f"قرارداد: {contract.get('title') or '-'}\n"
            f"پیمانکار: {contract.get('family_name') or '-'}\n"
            f"شماره صورت‌وضعیت: {fa(self._var('statement_number').get() or '-')}\n"
            f"تاریخ: {fa(self._var('statement_date').get() or '-')}\n"
            f"مبلغ صورت‌وضعیت: {_amount(self._var('amount').get())} تومان"
        )
        tk.Label(parent, text=summary, bg=p['panel'], fg=p['text_primary'],
                font=kit_font('body'), anchor='e', justify='right',
                padx=m['outer_pad'], pady=m['outer_pad']).pack(fill='x')

    # --- persistence -----------------------------------------------------------

    def collect(self) -> dict[str, Any]:
        record = dict(self.record)
        record.update({key: variable.get() for key, variable in self.values.items()})
        record['contract_id'] = contract_id_from_choice(self._var('contract_id').get())
        record['rows'] = [
            {key: row[key].get() for key in STATEMENT_ROW_KEYS}
            for row in self.row_values
        ]
        return record

    def finish(self) -> None:
        """ذخیره on تأیید نهایی: the one place an edit is actually applied."""

        self._save(open_record=False)
        self.close()

    def close(self) -> None:
        """Closing before تأیید نهایی: a cancel for an edit, discarded
        outright for a new one - the operator's explicit ask, unlike
        ContractWizard187/ArchiveWizard187 which still carry a brand-new
        record on as a draft through the record window. A صورت‌وضعیت the
        wizard never reached تأیید نهایی on must never appear in the
        table at all.
        """

        if self._saved_once:
            super().close()
            return
        if self.record.get('statement_id') and self.on_saved is not None:
            self.on_saved(self.record, True)
        super().close()

    def _save(self, *, open_record: bool) -> None:
        if self._saved_once:
            return
        record = self.collect()
        if not record.get('contract_id'):
            # A صورت‌وضعیت with no قرارداد names nothing to report against -
            # not a legitimate half-filled record the way a contract's own
            # title-only draft is.
            return
        self._saved_once = True
        saved = upsert_statement(record)
        if self.on_saved is not None:
            self.on_saved(saved, open_record)


class StatementRecordWindow187(BarkavWindow):
    """Review/edit an existing صورت‌وضعیت: same sections, no wizard steps."""

    size_class = 'full'

    def __init__(self, parent, *, statement: dict[str, Any], rich=None, on_saved=None):
        self.statement = dict(statement)
        self.rich = rich
        self.on_saved = on_saved
        self.values: dict[str, tk.StringVar] = {}
        self.row_values: list[dict[str, tk.StringVar]] = []
        super().__init__(parent, 'پنجره رکورد صورت‌وضعیت', subtitle=str(statement.get('statement_number') or ''),
                         show_footer=True, scrollable=True)
        self._build()
        self.add_action('ذخیره', self.save, style='Primary.TButton')
        self.add_action('بستن', self.close)

    def _build(self) -> None:
        p = kit_palette()
        m = kit_metrics()
        contract = get_contract(self.statement.get('contract_id')) or {}
        tk.Label(self.body, text=f"قرارداد: {contract.get('title') or '-'}    پیمانکار: {contract.get('family_name') or '-'}",
                bg=p['bg'], fg=p['text_primary'], font=kit_font('title'), anchor='e').pack(fill='x', pady=(0, m['gap']))

        details = ttk.Frame(self.body, style='Card.TFrame')
        details.pack(fill='x', pady=(0, m['gap']))

        def get_var(key: str, default: str = '') -> tk.StringVar:
            return self.values.setdefault(
                key, tk.StringVar(value=str(self.statement.get(key) or default)))

        _render_statement_identity_fields(details, get_var, bg=p['card'])

        rows_heading = tk.Frame(self.body, bg=p['bg'])
        rows_heading.pack(fill='x', pady=(m['gap'], m['gap'] // 2))
        tk.Label(rows_heading, text='ردیف‌های قرارداد', bg=p['bg'], fg=p['text_primary'],
                font=kit_font('title'), anchor='e').pack(fill='x')
        rows_section = ttk.Frame(self.body, style='Card.TFrame')
        rows_section.pack(fill='x', pady=(0, m['gap']))
        contract_id = str(self.statement.get('contract_id') or '')
        statement_id = self.statement.get('statement_id')
        for source in self.statement.get('rows') or []:
            description = str(source.get('description') or '').strip()
            base = previous_statement_row_totals(contract_id, description,
                                                 before_statement_id=statement_id)
            # blank_statement_row is what actually wires مبلغ کارکرد دوره to
            # مبلغ واحد قرارداد × مقدار کارکرد این دوره - building rows as a
            # bare dict here (as this window used to) left that trace off
            # entirely, so typing into مقدار کارکرد never recomputed anything.
            row = blank_statement_row(on_total_change=self._retotal, cumulative_base=base)
            for key in STATEMENT_ROW_KEYS:
                row[key].set(str(source.get(key) or ''))
            self.row_values.append(row)
        # render_statement_row_grid attaches grouping itself, once each
        # cell's own Entry exists - see blank_statement_row for why that
        # order matters.
        render_statement_row_grid(rows_section, self.row_values)
        self._row_totals_caption = tk.Label(self.body, bg=p['bg'], fg=p['text_secondary'],
                                            font=kit_font('small'), anchor='e', justify='right')
        self._row_totals_caption.pack(fill='x', pady=(0, m['gap']))

        bonus = ttk.Frame(self.body, style='Card.TFrame')
        bonus.pack(fill='x', pady=(0, m['gap']))
        for key, label in BONUS_FIELDS:
            row = tk.Frame(bonus, bg=p['card'])
            row.pack(fill='x', pady=m['gap'] // 2)
            tk.Label(row, text=label, bg=p['card'], fg=p['text_secondary'],
                    font=kit_font('small'), anchor='e', width=22).pack(side='right')
            variable = self.values.setdefault(
                key, tk.StringVar(value=str(self.statement.get(key) or '')))
            ttk.Entry(row, textvariable=variable, justify='right').pack(
                side='right', fill='x', expand=True, padx=m['gap'] // 2)
            # Attached after the Entry exists - see blank_statement_row for
            # why the order matters.
            group_amount_while_typing_187(variable)
            variable.trace_add('write', lambda *_a: self._retotal())

        self._amount_caption = tk.Label(self.body, bg=p['bg'], fg=p['text_secondary'],
                                        font=kit_font('body'), anchor='e', justify='right')
        self._amount_caption.pack(fill='x')
        self._retotal()

    def _retotal(self) -> None:
        # blank_statement_row's on_total_change fires the moment a row's own
        # مبلغ کارکرد دوره is first seeded - before self._amount_caption
        # (created later in _build) exists yet.
        caption = getattr(self, '_amount_caption', None)
        if caption is None or not caption.winfo_exists():
            return
        total = sum(int(_row_number(row['line_total'].get())) for row in self.row_values)
        bonus = amount_of(self.values.get('bonus_amount', tk.StringVar()).get())
        penalty = amount_of(self.values.get('penalty_amount', tk.StringVar()).get())
        amount = max(total + bonus - penalty, 0)
        cumulative = cumulative_statement_amount(
            self.statement.get('contract_id'), self.statement.get('statement_id')) or amount
        caption.configure(
            text=f'مبلغ صورت‌وضعیت: {_amount(amount)} تومان    |    مبلغ صورت‌وضعیت تجمعی: {_amount(cumulative)} تومان')
        self._show_row_totals()

    def _show_row_totals(self) -> None:
        caption = getattr(self, '_row_totals_caption', None)
        if caption is None or not caption.winfo_exists():
            return
        period_total = int(sum(_row_number(row['line_total'].get()) for row in self.row_values))
        cumulative_total = int(sum(_row_number(row['cumulative_amount'].get()) for row in self.row_values))
        caption.configure(
            text=f'مبلغ کل صورت‌وضعیت دوره: {_amount(period_total)} تومان'
                 f'    |    مبلغ کل صورت‌وضعیت تجمیعی: {_amount(cumulative_total)} تومان')

    def save(self) -> None:
        record = dict(self.statement)
        record.update({key: variable.get() for key, variable in self.values.items()})
        record['rows'] = [{key: row[key].get() for key in STATEMENT_ROW_KEYS}
                         for row in self.row_values]
        self.statement = upsert_statement(record)
        if self.on_saved is not None:
            self.on_saved(self.statement)


DETAIL_EXPORT_PROMPT = 'خروجی'
DETAIL_EXPORT_FORMATS = {'پی‌دی‌اف': 'pdf', 'اکسل': 'xlsx', 'پرینت': 'print'}
DETAIL_MONEY_ROW_KEYS = {'unit_price', 'contract_quantity', 'worked_quantity', 'line_total',
                         'cumulative_quantity', 'cumulative_amount'}


def _find_payment_receipt_path(db, payment: dict[str, Any]) -> str:
    """فیش lookup for one واریز, from a bare pending_id.

    A fresh/در-انتظار-بررسی واریز still has its فیش attached under
    entity_type='PENDING' - list_pending_attachments finds it directly.
    Once ApprovalCenterService.approve() posts the pending item, it calls
    relink_pending_attachments() to move that same attachment row onto
    whatever the posting became (EXPENSE, else TRANSACTION, else CHEQUE -
    see approve()'s own priority in approval_service.py), and the
    attachments table keeps no memory of the original pending_id after
    that. FinanceDB.get_financial_posting(pending_id) is what still
    remembers the mapping (it reads the financial_postings row created by
    that same post), so it is used here to re-derive the entity the
    attachment now lives under, checked in that same expense/transaction/
    cheque priority. یک pending بدون posting (رد‌شده یا هنوز تأییدنشده)
    فقط 'بدون فیش' برمی‌گرداند, نه خطا.
    """

    pending_id = str(payment.get('pending_id') or '')
    if not pending_id or db is None:
        return ''
    try:
        attachments = db.list_pending_attachments(pending_id)
    except Exception:
        attachments = []
    for attachment in attachments:
        local_path = str(attachment.get('local_path') or '')
        if local_path and Path(local_path).exists():
            return local_path
    try:
        posting = db.get_financial_posting(pending_id)
    except Exception:
        posting = None
    if not posting:
        return ''
    for entity_type, entity_id in (
        ('EXPENSE', posting.get('expense_id')),
        ('TRANSACTION', posting.get('transaction_id')),
        ('CHEQUE', posting.get('cheque_id')),
    ):
        if not entity_id:
            continue
        try:
            posted_attachments = db.list_entity_attachments(entity_type, str(entity_id))
        except Exception:
            continue
        for attachment in posted_attachments:
            local_path = str(attachment.get('local_path') or '')
            if local_path and Path(local_path).exists():
                return local_path
    return ''


class StatementFinanceDetailWindow187(BarkavWindow):
    """دبل‌کلیک روی صورت‌وضعیت یا امور مالی - نه پنجرهٔ رکورد قابل‌ویرایش،
    بلکه خلاصهٔ مالیِ همان قرارداد: هویت + جمع‌بندی، ردیف‌های یک صورت‌وضعیت
    (خود آن صورت‌وضعیت اگر از صورت‌وضعیت باز شده، یا آخرین صورت‌وضعیتِ
    قرارداد اگر از امور مالی باز شده - یک قرارداد بدون هیچ صورت‌وضعیتی
    بخش ردیف‌ها را خالی می‌بیند، نه خطا)، و فهرست واریزی‌های قرارداد
    به‌همراه فیش هرکدام.
    """

    size_class = 'full'

    def __init__(self, parent, *, contract: dict[str, Any], statement: dict[str, Any] | None = None,
                 db=None):
        self.contract = dict(contract)
        self.statement = dict(statement) if statement else None
        self.db = db
        self._receipt_images: list[Any] = []
        super().__init__(parent, 'جزئیات مالی صورت‌وضعیت',
                         subtitle=str(contract.get('family_name') or ''), show_footer=True,
                         scrollable=True)
        self._build()
        self.add_action('بستن', self.close)

    # --- summary -------------------------------------------------------------

    def _summary_segments(self) -> list[str]:
        """چهار بخش «برچسب: عدد», جدا از هم - نه یک رشتهٔ ترکیبی.

        «بدهکار/بستانکار» با اسلش داخل خودش، کنار چند رقمِ دیگر در همان
        رشته, حتی با RLM جلوی رشته هم به‌هم می‌ریخت (Tk بدون الگوریتم
        bidi واقعی). هر بخش، ویجت Label جداگانهٔ خودش را می‌گیرد - مشکل
        واقعاً کنار گذاشته می‌شود, نه فقط پوشانده.
        """

        statement_type = self.statement.get('statement_type') if self.statement else None
        cumulative = cumulative_statement_amount(self.contract.get('contract_id'))
        return [
            f'نوع صورت‌وضعیت: {statement_type or DEFAULT_STATEMENT_TYPE}',
            f'مبلغ تجمیعی صورت‌وضعیت: {_amount(cumulative)} تومان',
            f'مبلغ دریافتی: {_amount(paid_total(self.contract))} تومان',
            f'بدهکار/بستانکار: {_amount(balance(self.contract))} تومان',
        ]

    def _summary_line(self) -> str:
        """خط جمع‌بندی به‌صورت یک رشته - برای خروجی PDF, که رشته را با
        _rtl() (بازچینی bidi واقعی) نمایش می‌دهد, نه Label خام Tk."""

        return '    '.join(self._summary_segments())

    def _statement_caption(self) -> str:
        rows = (self.statement or {}).get('rows') or []
        period_total = int(sum(_row_number(row.get('line_total')) for row in rows))
        cumulative_total = int(sum(_row_number(row.get('cumulative_amount')) for row in rows))
        return (f"مبلغ صورت‌وضعیت دوره: {_amount(period_total)} تومان    |    "
               f"مبلغ صورت‌وضعیت تجمیعی: {_amount(cumulative_total)} تومان")

    def _statement_row_cells(self, index: int, row: dict[str, Any]) -> list[str]:
        cells = []
        for key, _label in STATEMENT_ROW_COLUMNS:
            if key == 'no':
                cells.append(fa(index + 1))
            elif key in DETAIL_MONEY_ROW_KEYS:
                cells.append(_amount(row.get(key)))
            else:
                cells.append(str(row.get(key) or '-'))
        return cells

    def _ordered_payments(self) -> list[dict[str, Any]]:
        payments = list(self.contract.get('payments') or [])
        order = sorted(range(len(payments)), key=lambda i: str(payments[i].get('date') or ''))
        return [payments[i] for i in order]

    # --- build -----------------------------------------------------------------

    def _build(self) -> None:
        p = kit_palette()
        m = kit_metrics()

        top = tk.Frame(self.body, bg=p['bg'])
        top.pack(fill='x', pady=(0, m['gap']))
        self.export_choice = tk.StringVar(value=DETAIL_EXPORT_PROMPT)
        combo = ttk.Combobox(top, textvariable=self.export_choice,
                             values=(DETAIL_EXPORT_PROMPT, *DETAIL_EXPORT_FORMATS),
                             state='readonly', justify='right', width=18, style='Toolbar.TCombobox')
        combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>', lambda _e: self._export_chosen())

        identity = (
            f"پیمانکار: {self.contract.get('family_name') or '-'}    "
            f"عنوان قرارداد: {self.contract.get('title') or '-'}"
        )
        tk.Label(self.body, text=identity, bg=p['bg'], fg=p['text_primary'],
                font=kit_font('body'), anchor='e', justify='right').pack(
            fill='x', pady=(0, m['gap'] // 2))
        summary = tk.Frame(self.body, bg=p['panel'])
        summary.pack(fill='x', pady=(0, m['gap']))
        for segment in self._summary_segments():
            tk.Label(summary, text=segment, bg=p['panel'], fg=p['text_primary'],
                    font=kit_font('title'), anchor='e').pack(
                side='right', padx=(m['gap'], 0), pady=m['outer_pad'])

        rows_heading = tk.Frame(self.body, bg=p['bg'])
        rows_heading.pack(fill='x', pady=(0, m['gap'] // 2))
        tk.Label(rows_heading, text='ردیف‌های صورت‌وضعیت', bg=p['bg'], fg=p['text_primary'],
                font=kit_font('title'), anchor='e').pack(fill='x')
        rows_section = ttk.Frame(self.body, style='Card.TFrame')
        rows_section.pack(fill='x', pady=(0, m['gap'] // 2))
        self._render_statement_rows(rows_section)
        tk.Label(self.body, text=self._statement_caption(), bg=p['bg'], fg=p['text_secondary'],
                font=kit_font('small'), anchor='e').pack(fill='x', pady=(0, m['gap']))

        payments_heading = tk.Frame(self.body, bg=p['bg'])
        payments_heading.pack(fill='x', pady=(0, m['gap'] // 2))
        tk.Label(payments_heading, text='واریزی‌ها و فیش‌های آن', bg=p['bg'], fg=p['text_primary'],
                font=kit_font('title'), anchor='e').pack(fill='x')
        payments_section = ttk.Frame(self.body, style='Card.TFrame')
        payments_section.pack(fill='both', expand=True)
        self._render_payments(payments_section)

    def _render_statement_rows(self, parent) -> None:
        p = kit_palette()
        m = kit_metrics()
        rows = (self.statement or {}).get('rows') or []
        header = tk.Frame(parent, bg=p['heading'])
        header.pack(fill='x')
        for key, label in STATEMENT_ROW_COLUMNS:
            # Same font as the row cells below (kit_font('body')), not the
            # smaller heading size - tk.Label's own width=N is a character
            # count measured in THAT label's own font, so a smaller header
            # font renders the same width= narrower in pixels than the row
            # below it and the columns drift out of alignment.
            tk.Label(header, text=label, bg=p['heading'], fg=p['text_primary'], font=kit_font('body'),
                    anchor='e', width=STATEMENT_ROW_WIDTHS.get(key, 12)).pack(side='right')
        if not rows:
            tk.Label(parent, text='ردیفی ثبت نشده است.', bg=p['card'], fg=p['text_secondary'],
                    font=kit_font('body'), anchor='e').pack(fill='x', pady=m['gap'] // 2)
            return
        stripes = (p['row_even'], p['row_odd'])
        for index, row in enumerate(rows):
            stripe = stripes[index % 2]
            line = tk.Frame(parent, bg=stripe)
            line.pack(fill='x')
            for (key, _label), text in zip(STATEMENT_ROW_COLUMNS, self._statement_row_cells(index, row)):
                tk.Label(line, text=text, bg=stripe, fg=p['text_primary'], font=kit_font('body'),
                        anchor='e', width=STATEMENT_ROW_WIDTHS.get(key, 12)).pack(side='right')

    def _render_payments(self, parent) -> None:
        p = kit_palette()
        m = kit_metrics()
        header = tk.Frame(parent, bg=p['heading'])
        header.pack(fill='x')
        for text, width in (('ردیف', 6), ('تاریخ واریز', 16), ('مبلغ واریزی (تومان)', 18), ('گیرنده', 22), ('صاحب‌حساب', 22)):
            # Same font as the row cells below - see _render_statement_rows
            # for why the header can't use the smaller heading size here.
            tk.Label(header, text=text, bg=p['heading'], fg=p['text_primary'], font=kit_font('body'),
                    anchor='e', width=width).pack(side='right')
        tk.Label(header, text='فیش واریزی', bg=p['heading'], fg=p['text_primary'],
                font=kit_font('body'), anchor='e').pack(side='right', fill='x', expand=True)
        payments = self._ordered_payments()
        if not payments:
            tk.Label(parent, text='واریزی‌ای ثبت نشده است.', bg=p['card'], fg=p['text_secondary'],
                    font=kit_font('body'), anchor='e').pack(fill='x', pady=m['gap'] // 2)
            return
        stripes = (p['row_even'], p['row_odd'])
        for index, payment in enumerate(payments):
            stripe = stripes[index % 2]
            line = tk.Frame(parent, bg=stripe)
            line.pack(fill='x')
            for text, width in (
                (fa(index + 1), 6), (fa(payment.get('date') or '-'), 16),
                (_amount(payment.get('amount')), 18), (payment.get('receiver') or '-', 22),
                (payment.get('issuer') or '-', 22),
            ):
                tk.Label(line, text=text, bg=stripe, fg=p['text_primary'], font=kit_font('body'),
                        anchor='e', width=width).pack(side='right')
            self._render_receipt_cell(line, stripe, payment)

    def _render_receipt_cell(self, parent, bg: str, payment: dict[str, Any]) -> None:
        p = kit_palette()
        path = _find_payment_receipt_path(self.db, payment)
        if not path:
            tk.Label(parent, text='بدون فیش', bg=bg, fg=p['text_secondary'],
                    font=kit_font('small'), anchor='e').pack(side='right', fill='x', expand=True)
            return
        try:
            from PIL import Image, ImageTk
            image = Image.open(path)
            image.thumbnail((90, 128))
            photo = ImageTk.PhotoImage(image)
        except Exception:
            tk.Label(parent, text='فیش قابل‌نمایش نیست', bg=bg, fg=p['text_secondary'],
                    font=kit_font('small'), anchor='e').pack(side='right', fill='x', expand=True)
            return
        self._receipt_images.append(photo)
        tk.Label(parent, image=photo, bg=bg).pack(side='right', padx=4, pady=4)

    # --- export -----------------------------------------------------------------

    def _export_chosen(self) -> None:
        fmt = DETAIL_EXPORT_FORMATS.get(self.export_choice.get())
        self.export_choice.set(DETAIL_EXPORT_PROMPT)
        if fmt is not None:
            self._write_export(fmt, preview=True)

    def _preview_rows(self):
        headers = [label for _key, label in STATEMENT_ROW_COLUMNS]
        rows = [
            self._statement_row_cells(index, row)
            for index, row in enumerate((self.statement or {}).get('rows') or [])
        ]
        if rows:
            return headers, rows, 'ردیف‌های صورت‌وضعیت'
        payments = self._ordered_payments()
        if payments:
            payment_headers = ['ردیف', 'تاریخ واریز', 'مبلغ واریزی (تومان)', 'گیرنده', 'صاحب‌حساب']
            payment_rows = [
                [fa(index + 1), fa(payment.get('date') or '-'),
                 _amount(payment.get('amount')), payment.get('receiver') or '-',
                 payment.get('issuer') or '-']
                for index, payment in enumerate(payments)
            ]
            return payment_headers, payment_rows, 'واریزی‌ها'
        return ['بخش', 'شرح'], [['صورت‌وضعیت', 'ردیفی ثبت نشده است']], 'جزئیات'

    def _preview_specs(self):
        specs = [
            ('خلاصه', 'پیمانکار', self.contract.get('family_name') or '-'),
            ('خلاصه', 'قرارداد', self.contract.get('title') or '-'),
            ('خلاصه', 'وضعیت', self._summary_line()),
        ]
        for index, payment in enumerate(self._ordered_payments(), 1):
            specs.append((
                'واریزی‌ها',
                f'واریزی {fa(index)}',
                f"{fa(payment.get('date') or '-')} | "
                f"{_amount(payment.get('amount'))} تومان | "
                f"{payment.get('receiver') or '-'} | "
                f"{payment.get('issuer') or '-'}",
            ))
        return specs

    def _write_export(self, fmt: str, *, preview=False, orientation='افقی',
                      addressee='سایر', include_documents=True):
        if preview:
            headers, rows, caption = self._preview_rows()
            choices = {'xlsx': 'Excel', 'pdf': 'PDF', 'print': 'پرینت'}
            return show_export_preview_187(
                self,
                export_format=choices.get(fmt, 'PDF'),
                headers=headers,
                rows=rows,
                specs=self._preview_specs(),
                document_paths=[path for payment in self._ordered_payments()
                                if (path := _find_payment_receipt_path(self.db, payment))],
                title='پیش‌نمایش جزئیات مالی صورت‌وضعیت',
                table_caption=caption,
                row_label='ردیف',
                include_addressee=True,
                on_confirm=lambda choice, selected_orientation, selected_addressee, show_documents: self._write_export(
                    {'Excel': 'xlsx', 'PDF': 'pdf', 'پرینت': 'print'}.get(choice, 'pdf'),
                    orientation=selected_orientation,
                    addressee=selected_addressee,
                    include_documents=show_documents,
                ),
            )
        suffixes = {'pdf': '.pdf', 'xlsx': '.xlsx', 'print': '.pdf'}
        suffix = suffixes.get(fmt, '.pdf')
        path = filedialog.asksaveasfilename(
            parent=self, title='خروجی جزئیات مالی', defaultextension=suffix,
            filetypes=[(suffix.lstrip('.').upper(), f'*{suffix}')])
        if not path:
            return False
        destination = Path(path)
        try:
            if suffix == '.pdf':
                self._export_pdf(destination, orientation=orientation,
                                 addressee=addressee, include_documents=include_documents)
                if fmt == 'print' and hasattr(os, 'startfile'):
                    os.startfile(str(destination), 'print')
            else:
                self._export_xlsx(destination, addressee=addressee)
        except Exception as exc:
            messagebox.showerror('خروجی', str(exc), parent=self)
            return False
        messagebox.showinfo('خروجی', 'خروجی آماده شد.', parent=self)
        return True
    def _export_pdf(self, destination: Path, *, orientation='افقی',
                    addressee='سایر', include_documents=True) -> None:
        rows = (self.statement or {}).get('rows') or []
        payments = self._ordered_payments()
        export_statement_finance_detail_pdf_187(
            destination,
            title=f"جزئیات مالی صورت‌وضعیت - {self.contract.get('family_name') or ''}",
            identity_lines=[
                f"پیمانکار: {self.contract.get('family_name') or '-'}    "
                f"عنوان قرارداد: {self.contract.get('title') or '-'}",
                self._summary_line(),
                f'جهت ارائه به: {addressee}',
            ],
            statement_headers=[label for _key, label in STATEMENT_ROW_COLUMNS],
            statement_rows=[self._statement_row_cells(i, row) for i, row in enumerate(rows)],
            statement_caption=self._statement_caption(),
            payment_headers=['ردیف', 'تاریخ واریز', 'مبلغ واریزی (تومان)', 'گیرنده', 'صاحب‌حساب'],
            payment_rows=[
                [fa(i + 1), fa(payment.get('date') or '-'),
                 _amount(payment.get('amount')), payment.get('receiver') or '-',
                 payment.get('issuer') or '-']
                for i, payment in enumerate(payments)
            ],
            receipt_paths=([_find_payment_receipt_path(self.db, payment) for payment in payments]
                           if include_documents else []),
            orientation=orientation,
        )

    def _export_xlsx(self, destination: Path, *, addressee='سایر') -> None:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment
        book = Workbook()
        right = Alignment(horizontal='right')
        sheet = book.active
        sheet.title = 'صورت‌وضعیت'
        sheet.sheet_view.rightToLeft = True
        sheet.append([f'جهت ارائه به: {addressee}'])
        sheet.append([label for _key, label in STATEMENT_ROW_COLUMNS])
        for cell in sheet[1]:
            cell.alignment = right
        for index, row in enumerate((self.statement or {}).get('rows') or []):
            sheet.append(self._statement_row_cells(index, row))
            for cell in sheet[sheet.max_row]:
                cell.alignment = right

        payments_sheet = book.create_sheet('واریزی‌ها')
        payments_sheet.sheet_view.rightToLeft = True
        payments_sheet.append([f'جهت ارائه به: {addressee}'])
        payments_sheet.append(['ردیف', 'تاریخ واریز', 'مبلغ واریزی (تومان)', 'گیرنده', 'صاحب‌حساب'])
        for cell in payments_sheet[1]:
            cell.alignment = right
        for index, payment in enumerate(self._ordered_payments()):
            payments_sheet.append([fa(index + 1), fa(payment.get('date') or '-'),
                                   _amount(payment.get('amount')), payment.get('receiver') or '-',
                                   payment.get('issuer') or '-'])
            for cell in payments_sheet[payments_sheet.max_row]:
                cell.alignment = right
        book.save(destination)
