"""Contractors workspace - structure only.

Built from ``barkav_ui/template_tab.py`` so it already matches every other
tab: sub-tab sizing, table striping and separators, RTL column order, action
colours and window chrome all come from the kit.

Only the data layer is still to be written.  Each sub-tab's ``load_rows``
returns an empty list today; wiring it to a real service is the remaining
work and requires no visual changes.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from barkav_ui.table import DataTable
from contractor_archive_stage18_7 import (
    ArchiveDetailWindow187, ArchiveRecordWindow187, ArchiveWizard187,
    archive_criteria_export_rows, archive_history_export_rows,
    archive_identity_segments, archive_score_line,
)
from contractor_contracts_stage18_7 import (
    ContractDetailWindow187,
    ContractRecordWindow187,
    ContractWizard187,
)
from contractor_statements_stage18_7 import (
    DEFAULT_STATEMENT_TYPE,
    STATEMENT_TYPES,
    StatementFinanceDetailWindow187,
    StatementRecordWindow187,
    StatementWizard187,
)
from contractor_store_stage18_7 import (
    balance,
    delete_contracts,
    delete_profile,
    delete_statement,
    get_contract,
    get_profile,
    get_statement,
    load_contracts,
    load_profiles,
    load_statements,
    paid_total,
    statement_amount,
    statements_for_contract,
    sync_archive_from_sources,
    upsert_contract,
)
from barkav_ui.tabs import sub_notebook
from barkav_ui.theme import font as kit_font, metrics as kit_metrics, palette as kit_palette
from barkav_ui.window import BarkavWizard
from datetime import date, datetime
import os
from pathlib import Path
from tkinter import filedialog, messagebox

from export_utils import style_xlsx_workbook
from sales_claims_stage18_7 import (
    export_archive_profile_pdf_187, export_contract_pdf_187, show_export_preview_187,
)
from ui_stage18_3 import en, fa, group_int_fa


def _money(value) -> str:
    try:
        return group_int_fa(int(str(en(str(value or '0'))).replace(',', '') or 0))
    except (TypeError, ValueError):
        return fa(str(value or ''))


def _as_int(value) -> int:
    try:
        return int(str(en(str(value or '0'))).replace(',', '') or 0)
    except (TypeError, ValueError):
        return 0


def _today_shamsi() -> str:
    # Imported lazily - revenue_service pulls in the sales/finance stack
    # this module otherwise stays clear of at module scope.
    from revenue_service import gregorian_to_shamsi
    return gregorian_to_shamsi(date.today())


CONTRACTS = 'قراردادها'
STATEMENTS = 'صورت وضعیت'
FINANCE = 'امور مالی'
ARCHIVE = 'آرشیو'

SUB_TABS = (CONTRACTS, STATEMENTS, FINANCE, ARCHIVE)

# Per-sub-tab column definitions.  Declared in logical order; DataTable
# mirrors them so the first column lands right in RTL.
COLUMNS = {
    CONTRACTS: (
        ('row', 'ردیف'), ('number', 'شماره قرارداد'),
        ('title', 'عنوان قرارداد'), ('name', 'نام پیمانکار'),
        ('phone', 'شماره تماس'), ('amount', 'مبلغ قرارداد (تومان)'),
        ('duration', 'مدت پرداخت'), ('paid', 'مبلغ پرداخت‌شده (تومان)'),
        ('balance', 'بدهکاری / بستانکاری (تومان)'),
    ),
    STATEMENTS: (
        ('row', 'ردیف'), ('name', 'پیمانکار'), ('title', 'عنوان قرارداد'),
        ('contract_date', 'تاریخ قرارداد'), ('number', 'شماره صورت‌وضعیت'),
        ('type', 'نوع صورت‌وضعیت'), ('amount', 'مبلغ صورت‌وضعیت (تومان)'),
        ('paid', 'مبلغ پرداختی (تومان)'), ('balance', 'بدهکار / بستانکار (تومان)'),
    ),
    # امور مالی is a transaction log - one row per واریز (deposit) actually
    # posted against a قرارداد, not a per-contract rollup. Rows are grouped
    # by قرارداد, oldest واریز first, so مبلغ تجمعی واریز can run as a
    # per-contract cumulative total the same way صورت‌وضعیت's own تجمیعی does.
    FINANCE: (
        ('row', 'ردیف'), ('date', 'تاریخ واریز'), ('title', 'عنوان قرارداد'),
        ('name', 'نام پیمانکار'), ('amount', 'مبلغ واریز (تومان)'),
        ('cumulative_paid', 'مبلغ تجمعی واریز (تومان)'),
        ('cumulative_statement', 'مبلغ صورت‌وضعیت تجمیعی (تومان)'),
        ('balance', 'بدهکار / بستانکار (تومان)'),
        ('contract_amount', 'مبلغ کل قرارداد (تومان)'),
        ('remaining', 'مبلغ باقیمانده قرارداد (تومان)'),
    ),
    # آرشیو is a registry of every طرف حساب (پیمانکار/تامین‌کننده/خدمات‌دهنده)
    # on file, not one قرارداد's own history - دسته‌بندی is what tells them
    # apart in one shared list.
    ARCHIVE: (
        ('row', 'ردیف'), ('name', 'نام'), ('category', 'دسته‌بندی'),
        ('activity', 'عنوان فعالیت'), ('phone', 'شماره تماس'), ('address', 'آدرس'),
        ('payment_type', 'نوع پرداخت'), ('score', 'امتیاز کلی (از ۱۰۰)'),
        ('rehire_chance', 'احتمال همکاری مجدد'),
    ),
}

EMPTY_TEXT = {
    CONTRACTS: 'قراردادی برای پیمانکاران ثبت نشده است',
    STATEMENTS: 'صورت وضعیتی ثبت نشده است',
    FINANCE: 'قراردادی برای گزارش مالی وجود ندارد',
    ARCHIVE: 'رده‌بندی پیمانکاری ثبت نشده است',
}

ANY = 'همه'

# 'نمایش بر اساس' is two stages: the first names a field, the second offers
# the values that field actually holds.  One long list of every contract
# would not tell the reader what they were choosing between.
STATEMENT_TYPE_FILTER_FIELD = 'نوع صورت‌وضعیت'
FILTER_FIELDS = (ANY, 'نام پیمانکار', STATEMENT_TYPE_FILTER_FIELD, 'نام قرارداد', 'شماره قرارداد')
FILTER_KEYS = {
    'نام پیمانکار': 'family_name',
    'نام قرارداد': 'title',
    'شماره قرارداد': 'contract_number',
}
STATEMENT_FILTER_FIELDS = (ANY, 'نام پیمانکار', STATEMENT_TYPE_FILTER_FIELD)

# امور مالی's نمایش براساس: تاریخ reads from the واریز itself, the other two
# from its قرارداد - handled specially in _finance_matches/_finance_filter_field_changed.
FINANCE_FILTER_FIELDS = (ANY, 'نام پیمانکار', 'عنوان قرارداد', 'تاریخ')
FINANCE_FILTER_KEYS = {'نام پیمانکار': 'family_name', 'عنوان قرارداد': 'title'}

# آرشیو's own نمایش براساس - همان profile fields, دسته‌بندی is what separates
# پیمانکار/تامین‌کننده/خدمات‌دهنده in one shared list.
ARCHIVE_FILTER_FIELDS = (ANY, 'دسته‌بندی', 'نام', 'نوع پرداخت')
ARCHIVE_FILTER_KEYS = {
    'دسته‌بندی': 'category', 'نام': 'family_name', 'نوع پرداخت': 'payment_type',
}

EXPORT_PROMPT = 'خروجی'
EXPORT_FORMATS = {'پی‌دی‌اف': 'pdf', 'اکسل': 'xlsx', 'پرینت': 'print'}


class ContractorsPanel187(ttk.Frame):
    """The contractors tab: four sub-tabs, each a toolbar + table + actions."""

    def __init__(self, parent: tk.Misc, *, db=None, base_dir=None, on_changed=None,
                 rich=None):
        super().__init__(parent, style='Panel.TFrame')
        self.rich = rich
        self._contract_ids: list = []
        self.db = db
        self.base_dir = base_dir
        self.on_changed = on_changed
        self.filters: dict[str, tk.StringVar] = {}
        self.tables: dict[str, DataTable] = {}
        self._build()

    def _build(self) -> None:
        m = kit_metrics()
        self.nb, self.strip = sub_notebook(self, level=2)
        for label in SUB_TABS:
            page = ttk.Frame(self.nb, style='Panel.TFrame', padding=m['outer_pad'])
            self.nb.add(page, text=label)
            self.tables[label] = self._build_page(page, label)
        self.strip.rebuild()
        self.refresh()

    def _build_page(self, page: ttk.Frame, label: str) -> DataTable:
        table = DataTable(
            page, COLUMNS[label],
            on_open=lambda item, name=label: self.open_record(name, item),
            empty_text=EMPTY_TEXT[label],
            checkable=label in (CONTRACTS, STATEMENTS, FINANCE, ARCHIVE),
        )
        table.pack(fill='both', expand=True)

        self.filters[label] = tk.StringVar()
        self.filters[label].trace_add('write', lambda *_a: self.refresh())
        if label == CONTRACTS:
            # Right to left: what you do with a contract, then what you are
            # looking at, then - away on the left - what you take out of it.
            table.add_tool('قرارداد جدید +', self.open_wizard)
            table.add_tool('ویرایش قرارداد', self.edit_selected)
            table.add_tool('کپی قرارداد', self.copy_selected_contract)
            table.add_tool('حذف ردیف', lambda: self.delete_selected(CONTRACTS))
            # The same four on the row itself, where the hand already is.
            table.tree.bind('<Button-3>', self._context_menu, add='+')

            self.filter_field = tk.StringVar(value=ANY)
            self.filter_value = tk.StringVar(value=ANY)
            table.toolbar.add_filter('نمایش براساس', self.filter_field,
                                     FILTER_FIELDS, command=self._filter_field_changed)
            self.filter_value_combo = table.toolbar.add_filter(
                None, self.filter_value, (ANY,), command=self.refresh)

            # One control, no caption: it becomes the shared «خروجی ▾». (It
            # was captioned «جستجو», so a stray «جستجو :» stood beside the
            # export where no search box is.)
            self.export_choice = tk.StringVar(value=EXPORT_PROMPT)
            table.add_export(self.export_choice, self._export_chosen,
                             label=None, side='left')
            return table
        if label == STATEMENTS:
            # Right to left: what you do with a صورت‌وضعیت, then what you are
            # looking at, then - away on the left - what you take out of it.
            # No free-text search box here - نمایش براساس already narrows
            # this table, and the app's own global جست‌وجو bar covers the rest.
            table.add_tool('صورت‌وضعیت جدید +', lambda: self.open_wizard(STATEMENTS))
            table.add_tool('ویرایش', lambda: self.edit_selected_row(STATEMENTS))
            table.add_tool('کپی', self.copy_selected_statement)
            table.add_tool('حذف ردیف', lambda: self.delete_selected(STATEMENTS))
            # The same four on the row itself, where the hand already is.
            table.tree.bind('<Button-3>', self._statement_context_menu, add='+')

            # Same two-stage shape as قراردادها's own نمایش براساس: the first
            # box names a field, the second box holds that field's actual
            # values - نوع صورت‌وضعیت reads from the صورت‌وضعیت itself, نام
            # پیمانکار from its قرارداد.
            self.statement_filter_field = tk.StringVar(value=ANY)
            self.statement_filter_value = tk.StringVar(value=ANY)
            table.toolbar.add_filter('نمایش براساس', self.statement_filter_field,
                                     STATEMENT_FILTER_FIELDS, command=self._statement_filter_field_changed)
            self.statement_filter_value_combo = table.toolbar.add_filter(
                None, self.statement_filter_value, (ANY,), command=self.refresh)

            self.statement_export_choice = tk.StringVar(value=EXPORT_PROMPT)
            table.add_export(self.statement_export_choice,
                             self._statement_export_chosen, label=None, side='left')
            return table
        if label == FINANCE:
            # Right to left: افزودن-ویرایش-حذف-کپی, each routed through the
            # shared ثبت دیتا wizard/pending system so a واریز recorded or
            # corrected here is the same money the rest of the app sees.
            table.add_tool('افزودن +', self._add_finance_payment)
            table.add_tool('ویرایش', self._edit_finance_payment)
            table.add_tool('کپی', self._copy_finance_payment)
            table.add_tool('حذف ردیف', self._delete_finance_payment)
            table.tree.bind('<Button-3>', self._finance_context_menu, add='+')
            # بدهکار شدن پیمانکار (balance() رفته زیر صفر) با متن قرمز مشخص
            # می‌شود - نه صرفاً یک ته‌رنگ مثل approved/pending/rejected.
            table.register_row_style('debt', background='row_rejected', foreground='danger')

            self.finance_filter_field = tk.StringVar(value=ANY)
            self.finance_filter_value = tk.StringVar(value=ANY)
            table.toolbar.add_filter('نمایش براساس', self.finance_filter_field,
                                     FINANCE_FILTER_FIELDS, command=self._finance_filter_field_changed)
            self.finance_filter_value_combo = table.toolbar.add_filter(
                None, self.finance_filter_value, (ANY,), command=self.refresh)

            self.finance_export_choice = tk.StringVar(value=EXPORT_PROMPT)
            table.add_export(self.finance_export_choice,
                             self._finance_export_chosen, label=None, side='left')
            return table
        # آرشیو: افزودن-ویرایش-حذف-کپی, then نمایش‌براساس, then خروجی - the
        # same shape as صورت‌وضعیت/امور مالی's own toolbars.
        table.add_tool('افزودن +', lambda: self.open_wizard(ARCHIVE))
        table.add_tool('ویرایش', lambda: self.edit_selected_row(ARCHIVE))
        table.add_tool('کپی', self.copy_selected_profile)
        table.add_tool('حذف ردیف', lambda: self.delete_selected(ARCHIVE))
        table.tree.bind('<Button-3>', self._archive_context_menu, add='+')

        self.archive_filter_field = tk.StringVar(value=ANY)
        self.archive_filter_value = tk.StringVar(value=ANY)
        table.toolbar.add_filter('نمایش براساس', self.archive_filter_field,
                                 ARCHIVE_FILTER_FIELDS, command=self._archive_filter_field_changed)
        self.archive_filter_value_combo = table.toolbar.add_filter(
            None, self.archive_filter_value, (ANY,), command=self.refresh)

        self.archive_export_choice = tk.StringVar(value=EXPORT_PROMPT)
        table.add_export(self.archive_export_choice,
                         self._archive_export_chosen, label=None, side='left')
        return table

    # --- data ---------------------------------------------------------------

    def _filter_key(self) -> str | None:
        """The contract field the first filter names, or None for 'همه'."""

        field = getattr(self, 'filter_field', None)
        return FILTER_KEYS.get(field.get()) if field is not None else None

    def _filter_field_changed(self) -> None:
        """Refill the second filter with the values that field actually holds.

        نوع صورت‌وضعیت is fixed (موقت/قطعی), not a قرارداد field to scan -
        every صورت‌وضعیت already only ever holds one of the two.
        """

        field = getattr(self, 'filter_field', None)
        if field is not None and field.get() == STATEMENT_TYPE_FILTER_FIELD:
            choices = (ANY, *STATEMENT_TYPES)
        else:
            key = self._filter_key()
            if key is None:
                choices = (ANY,)
            else:
                seen = {str(c.get(key) or '').strip() for c in load_contracts()}
                choices = (ANY, *sorted(v for v in seen if v))
        self.filter_value_combo.configure(values=choices)
        self.filter_value.set(ANY)
        self.refresh()

    def _matches(self, contract: dict) -> bool:
        field = getattr(self, 'filter_field', None)
        if field is not None and field.get() == STATEMENT_TYPE_FILTER_FIELD:
            wanted = self.filter_value.get()
            if wanted != ANY:
                types = getattr(self, '_contract_statement_types', {}).get(
                    contract.get('contract_id'), set())
                if wanted not in types:
                    return False
        else:
            key = self._filter_key()
            if key is not None:
                wanted = self.filter_value.get()
                if wanted != ANY and str(contract.get(key) or '').strip() != wanted:
                    return False
        text = (self.filters.get(CONTRACTS).get() if CONTRACTS in self.filters else '').strip()
        if not text:
            return True
        haystack = ' '.join(str(contract.get(k) or '') for k in
                            ('contract_number', 'title', 'family_name', 'phone'))
        return text in haystack or en(text) in en(haystack)

    def _text_matches(self, label: str, *fields: Any) -> bool:
        """Same free-text search box the other three sub-tabs share."""

        text = (self.filters.get(label).get() if label in self.filters else '').strip()
        if not text:
            return True
        haystack = ' '.join(str(field or '') for field in fields)
        return text in haystack or en(text) in en(haystack)

    def load_rows(self, sub_tab: str) -> tuple[list[tuple], dict[int, str]]:
        """Return ``(rows, status_by_index)`` for one sub-tab."""

        if sub_tab == STATEMENTS:
            return self._load_statement_rows()
        if sub_tab == FINANCE:
            return self._load_finance_rows()
        if sub_tab == ARCHIVE:
            return self._load_archive_rows()
        rows, status, self._contract_ids = [], {}, []
        # One load_statements() pass, not one per قرارداد - نوع صورت‌وضعیت
        # filtering needs to know which types each قرارداد's own
        # صورت‌وضعیت‌ها cover.
        self._contract_statement_types: dict[str, set] = {}
        for statement in load_statements():
            cid = statement.get('contract_id')
            self._contract_statement_types.setdefault(cid, set()).add(
                str(statement.get('statement_type') or DEFAULT_STATEMENT_TYPE))
        for contract in load_contracts():
            if not self._matches(contract):
                continue
            index = len(rows)
            owed = balance(contract)
            rows.append((
                fa(index + 1),
                fa(contract.get('contract_number') or '-'),
                contract.get('title') or '-',
                contract.get('family_name') or '-',
                fa(contract.get('phone') or '-'),
                _money(contract.get('total_amount')),
                fa(contract.get('duration_months') or '-'),
                _money(paid_total(contract)),
                _money(owed),
            ))
            self._contract_ids.append(contract.get('contract_id'))
        return rows, status

    # Alternate rows are striped by the shared table look like every other
    # tab (operator round 2026-09-27: the green 'approved' tint these tables
    # used for it read as a selected row).

    def _statement_filter_key(self) -> str | None:
        field = getattr(self, 'statement_filter_field', None)
        return FILTER_KEYS.get(field.get()) if field is not None else None

    def _statement_filter_field_changed(self) -> None:
        """Refill the second filter with the values that field actually holds.

        نوع صورت‌وضعیت is fixed (موقت/قطعی), read from the صورت‌وضعیت itself -
        نام پیمانکار reads from its قرارداد.
        """

        field = getattr(self, 'statement_filter_field', None)
        if field is not None and field.get() == STATEMENT_TYPE_FILTER_FIELD:
            choices = (ANY, *STATEMENT_TYPES)
        else:
            key = self._statement_filter_key()
            if key is None:
                choices = (ANY,)
            else:
                seen = {str(c.get(key) or '').strip() for c in load_contracts()}
                choices = (ANY, *sorted(v for v in seen if v))
        self.statement_filter_value_combo.configure(values=choices)
        self.statement_filter_value.set(ANY)
        self.refresh()

    def _statement_matches(self, contract: dict, statement: dict | None = None) -> bool:
        field = getattr(self, 'statement_filter_field', None)
        if field is not None and field.get() == STATEMENT_TYPE_FILTER_FIELD:
            wanted = self.statement_filter_value.get()
            if wanted == ANY:
                return True
            current = str((statement or {}).get('statement_type') or DEFAULT_STATEMENT_TYPE)
            return current == wanted
        key = self._statement_filter_key()
        if key is None:
            return True
        wanted = self.statement_filter_value.get()
        return wanted == ANY or str(contract.get(key) or '').strip() == wanted

    def _load_statement_rows(self) -> tuple[list[tuple], dict[int, str]]:
        rows, status, self._statement_ids = [], {}, []
        # One load_contracts() call, not one per صورت‌وضعیت - get_contract()
        # itself re-reads and re-parses the whole JSON file on every call, so
        # calling it inside this loop cost one full file read per row.
        contracts_by_id = {c.get('contract_id'): c for c in load_contracts()}
        for statement in load_statements():
            contract = contracts_by_id.get(statement.get('contract_id')) or {}
            if not self._statement_matches(contract, statement):
                continue
            index = len(rows)
            amount = statement_amount(statement)
            paid = paid_total(contract)
            owed = balance(contract)
            rows.append((
                fa(index + 1),
                contract.get('family_name') or '-',
                contract.get('title') or '-',
                fa(contract.get('contract_date') or '-'),
                fa(statement.get('statement_number') or '-'),
                str(statement.get('statement_type') or DEFAULT_STATEMENT_TYPE),
                _money(amount),
                _money(paid),
                _money(owed),
            ))
            self._statement_ids.append(statement.get('statement_id'))
        return rows, status

    def _finance_filter_key(self) -> str | None:
        field = getattr(self, 'finance_filter_field', None)
        return FINANCE_FILTER_KEYS.get(field.get()) if field is not None else None

    def _finance_filter_field_changed(self) -> None:
        """Refill the second filter with the values that field actually holds.

        تاریخ reads from the واریز itself - every other قرارداد field reads
        from the قرارداد, the same shape as _filter_field_changed's own.
        """

        field = self.finance_filter_field.get()
        if field == 'تاریخ':
            seen = {str(payment.get('date') or '').strip()
                    for contract in load_contracts()
                    for payment in (contract.get('payments') or [])}
        else:
            key = self._finance_filter_key()
            # Only قراردادهای that actually have a واریز show up in the جدول
            # itself - a قرارداد with none would still be an option here
            # (from load_contracts() alone) whose value narrows the table
            # to nothing.
            seen = ({str(c.get(key) or '').strip() for c in load_contracts()
                    if c.get('payments')} if key is not None else set())
        choices = (ANY, *sorted(v for v in seen if v))
        self.finance_filter_value_combo.configure(values=choices)
        self.finance_filter_value.set(ANY)
        self.refresh()

    def _finance_matches(self, contract: dict, payment: dict) -> bool:
        field = getattr(self, 'finance_filter_field', None)
        field = field.get() if field is not None else ANY
        if field == ANY:
            return True
        wanted = self.finance_filter_value.get()
        if wanted == ANY:
            return True
        if field == 'تاریخ':
            return str(payment.get('date') or '').strip() == wanted
        key = self._finance_filter_key()
        return key is None or str(contract.get(key) or '').strip() == wanted

    def _load_finance_rows(self) -> tuple[list[tuple], dict[int, str]]:
        rows, status, self._finance_payments = [], {}, []
        # One load_statements() call, not one per قرارداد -
        # cumulative_statement_amount() itself re-reads and re-parses the
        # whole صورت‌وضعیت JSON file on every call; with upto_statement_id
        # left at its default None it is exactly this same per-contract sum.
        statement_totals: dict[str, int] = {}
        for statement in load_statements():
            cid = statement.get('contract_id')
            statement_totals[cid] = statement_totals.get(cid, 0) + statement_amount(statement)
        for contract in load_contracts():
            contract_id = contract.get('contract_id')
            raw_payments = contract.get('payments') or []
            order = sorted(range(len(raw_payments)),
                            key=lambda i: str(raw_payments[i].get('date') or ''))
            statement_total = statement_totals.get(contract_id, 0)
            owed = statement_total - _as_int(paid_total(contract))
            remaining = balance(contract)
            running = 0
            for raw_index in order:
                payment = raw_payments[raw_index]
                if not self._finance_matches(contract, payment):
                    continue
                amount = _as_int(payment.get('amount'))
                running += amount
                index = len(rows)
                rows.append((
                    fa(index + 1),
                    fa(payment.get('date') or '-'),
                    contract.get('title') or '-',
                    contract.get('family_name') or '-',
                    _money(amount),
                    _money(running),
                    _money(statement_total),
                    _money(owed),
                    _money(contract.get('total_amount')),
                    _money(remaining),
                ))
                if owed < 0:
                    # پیمانکار بدهکار شده - از قرارداد بیشتر از صورت‌وضعیت
                    # ثبت‌شده پول گرفته؛ متن قرمز، جای ته‌رنگ صرفاً خوانایی.
                    status[index] = 'debt'
                self._finance_payments.append({
                    'contract_id': contract_id, 'payment_index': raw_index,
                    'pending_id': str(payment.get('pending_id') or ''),
                })
        return rows, status

    def _archive_filter_key(self) -> str | None:
        field = getattr(self, 'archive_filter_field', None)
        return ARCHIVE_FILTER_KEYS.get(field.get()) if field is not None else None

    def _archive_filter_field_changed(self) -> None:
        """Refill the second filter with the values that field actually holds."""

        key = self._archive_filter_key()
        if key is None:
            choices = (ANY,)
        else:
            seen = {str(p.get(key) or '').strip() for p in load_profiles()}
            choices = (ANY, *sorted(v for v in seen if v))
        self.archive_filter_value_combo.configure(values=choices)
        self.archive_filter_value.set(ANY)
        self.refresh()

    def _archive_matches(self, profile: dict) -> bool:
        key = self._archive_filter_key()
        if key is None:
            return True
        wanted = self.archive_filter_value.get()
        return wanted == ANY or str(profile.get(key) or '').strip() == wanted

    def _load_archive_rows(self) -> tuple[list[tuple], dict[int, str]]:
        # هر بار این تب رفرش می‌شود، اول با قراردادها/تراکنش‌های تأییدشده/
        # عوامل پروژه همگام می‌شود - یک نام تکراری هرگز ردیف دوم نمی‌سازد،
        # و امتیاز/ضریب دستی هیچ‌کس دست نمی‌خورد.
        try:
            sync_archive_from_sources()
        except Exception:
            pass
        rows, status, self._profile_ids = [], {}, []
        for profile in load_profiles():
            if not self._archive_matches(profile):
                continue
            index = len(rows)
            rows.append((
                fa(index + 1),
                profile.get('family_name') or '-',
                profile.get('category') or '-',
                profile.get('activity') or '-',
                fa(profile.get('phone') or '-'),
                profile.get('address') or '-',
                profile.get('payment_type') or '-',
                fa(str(profile.get('overall_score') or '-')),
                profile.get('rehire_chance') or '-',
            ))
            self._profile_ids.append(profile.get('profile_id'))
        return rows, status

    def _selected_index(self, sub_tab: str) -> int | None:
        table = self.tables.get(sub_tab)
        if table is None:
            return None
        try:
            return (self._row_keys(sub_tab) or []).index(table.selected_key())
        except (ValueError,tk.TclError):
            return None

    def _selected_contract(self) -> dict | None:
        table = self.tables.get(CONTRACTS)
        if table is None:
            return None
        try:
            key = table.selected_key()
            return get_contract(key) if key else None
        except (IndexError, tk.TclError, AttributeError):
            return None

    def refresh(self) -> None:
        for label, table in self.tables.items():
            rows, status = self.load_rows(label)
            table.set_rows(rows, status=status, keys=self._row_keys(label))

    def _row_keys(self, label: str) -> list | None:
        """A stable identity per row, so a periodic refresh (bot-status and
        pending-approval ticks both rebuild every tab's table every few
        seconds) can put the user's selection back where it was instead of
        silently dropping it."""

        if label == CONTRACTS:
            return list(self._contract_ids)
        if label == STATEMENTS:
            return list(self._statement_ids)
        if label == FINANCE:
            return [f"{p.get('contract_id')}:{p.get('payment_index')}"
                   for p in self._finance_payments]
        if label == ARCHIVE:
            return list(self._profile_ids)
        return None

    # --- actions ------------------------------------------------------------

    def open_wizard(self, sub_tab: str = CONTRACTS) -> None:
        if sub_tab == STATEMENTS:
            StatementWizard187(self, rich=self.rich, on_saved=self._statement_saved)
        elif sub_tab == ARCHIVE:
            ArchiveWizard187(self, rich=self.rich, on_saved=self._profile_saved)
        else:
            ContractWizard187(self, rich=self.rich, on_saved=self._contract_saved)

    def edit_selected(self) -> None:
        contract = self._selected_contract()
        if contract is None:
            messagebox.showinfo('قراردادها', 'ابتدا یک قرارداد را انتخاب کنید.',
                                parent=self)
            return
        ContractWizard187(self, rich=self.rich, contract=contract,
                          on_saved=self._contract_saved)

    def edit_selected_row(self, sub_tab: str) -> None:
        """ویرایش for صورت‌وضعیت, امور مالی and آرشیو - one selected row each."""

        if sub_tab == STATEMENTS:
            index = self._selected_index(STATEMENTS)
            ids = getattr(self, '_statement_ids', [])
            if index is None or index >= len(ids):
                messagebox.showinfo('صورت وضعیت', 'ابتدا یک ردیف را انتخاب کنید.', parent=self)
                return
            statement = get_statement(ids[index])
            if statement is not None:
                StatementWizard187(self, rich=self.rich, statement=statement,
                                   on_saved=self._statement_saved)
        elif sub_tab == ARCHIVE:
            index = self._selected_index(ARCHIVE)
            ids = getattr(self, '_profile_ids', [])
            if index is None or index >= len(ids):
                messagebox.showinfo('آرشیو', 'ابتدا یک ردیف را انتخاب کنید.', parent=self)
                return
            profile = get_profile(ids[index])
            if profile is not None:
                ArchiveWizard187(self, rich=self.rich, profile=profile,
                                 on_saved=self._profile_saved)

    def copy_selected_contract(self) -> None:
        contract = self._selected_contract()
        if contract is None:
            messagebox.showinfo('قراردادها', 'ابتدا یک قرارداد را انتخاب کنید.',
                                parent=self)
            return
        clone = dict(contract)
        # A copy is a new contract, so it must not inherit the original's id
        # or its payment history.
        clone.pop('contract_id', None)
        # A number identifies one paper contract, so the copy needs its own.
        clone.pop('contract_number', None)
        clone['payments'] = []
        clone['title'] = f"{clone.get('title') or ''} (رونوشت)".strip()
        ContractWizard187(self, rich=self.rich, contract=clone,
                          on_saved=self._contract_saved)

    def copy_selected_statement(self) -> None:
        index = self._selected_index(STATEMENTS)
        ids = getattr(self, '_statement_ids', [])
        if index is None or index >= len(ids):
            messagebox.showinfo('صورت وضعیت', 'ابتدا یک ردیف را انتخاب کنید.', parent=self)
            return
        statement = get_statement(ids[index])
        if statement is None:
            return
        clone = dict(statement)
        # A copy is a new صورت‌وضعیت, so it must not inherit the original's id
        # or its own paper number - everything else (قرارداد, ردیف‌ها, دوره,
        # پاداش/جریمه, نوع) carries over, per «کپی ... با اطلاعات ردیف بالا».
        clone.pop('statement_id', None)
        clone.pop('statement_number', None)
        StatementWizard187(self, rich=self.rich, statement=clone,
                           on_saved=self._statement_saved)

    def copy_selected_profile(self) -> None:
        index = self._selected_index(ARCHIVE)
        ids = getattr(self, '_profile_ids', [])
        if index is None or index >= len(ids):
            messagebox.showinfo('آرشیو', 'ابتدا یک ردیف را انتخاب کنید.', parent=self)
            return
        profile = get_profile(ids[index])
        if profile is None:
            return
        clone = dict(profile)
        # A copy is a new طرف حساب, so it must not inherit the original's id -
        # everything else (دسته‌بندی, فعالیت, امتیازها, ...) carries over.
        clone.pop('profile_id', None)
        ArchiveWizard187(self, rich=self.rich, profile=clone, on_saved=self._profile_saved)

    def _selected_finance_payment(self) -> tuple[dict, dict] | tuple[None, None]:
        """The (contract, payment) pair the selected امور مالی row names."""

        index = self._selected_index(FINANCE)
        entries = getattr(self, '_finance_payments', [])
        if index is None or index >= len(entries):
            return None, None
        entry = entries[index]
        contract = get_contract(entry['contract_id'])
        payments = contract.get('payments') or [] if contract is not None else []
        if contract is None or entry['payment_index'] >= len(payments):
            return None, None
        return contract, payments[entry['payment_index']]

    def _finance_dashboard(self):
        """The شared ثبت دیتا pending/wizard system, reached from the dashboard
        Toplevel this panel sits inside - امور مالی has no import of its own
        on the legacy dashboard/finance_db stack, the same way
        contractor_contracts_stage18_7's receipt lookups stay clear of it.
        """

        dashboard = self.winfo_toplevel()
        center = getattr(dashboard, 'approval_center', None)
        if self.db is None or center is None or not callable(getattr(center, 'open_wizard', None)):
            messagebox.showwarning('امور مالی', 'پنجره ثبت دیتا در دسترس نیست.', parent=self)
            return None
        return dashboard, center

    def _open_finance_pending(self, dashboard, center, pending_id: str, *,
                              cleanup_if_abandoned: bool = False) -> None:
        """Show پنجره ویزارد for one pending_id in ثبت دیتا, tab switched there.

        ``cleanup_if_abandoned`` is only for a pending item this panel just
        created (افزودن/کپی) - closing that wizard without approving or
        rejecting it would otherwise leave a placeholder (amount 0, or a
        copy nobody meant to keep) sitting در انتظار بررسی forever.
        ویرایش reopens an existing واریز's own pending item and must never
        pass this - closing without changes there should just leave that
        واریز exactly as it already was.
        """

        center.filter.set('همه')
        center.refresh()
        row = next((item for item in getattr(center, 'rows', [])
                   if str(item.get('pending_id')) == pending_id), None)
        if row is None:
            messagebox.showinfo('امور مالی', 'رکورد مربوطه در ثبت دیتا پیدا نشد.', parent=self)
            return
        notebook = getattr(dashboard, 'notebook', None)
        approval_tab = getattr(dashboard, 'approval_tab', None)
        if notebook is not None and approval_tab is not None:
            notebook.select(approval_tab)
        if cleanup_if_abandoned:
            before = set(center.winfo_children())
        center.open_wizard(row)
        if cleanup_if_abandoned:
            opened = [w for w in center.winfo_children()
                     if w not in before and isinstance(w, tk.Toplevel)]
            if opened:
                opened[-1].bind(
                    '<Destroy>',
                    lambda _e, pid=pending_id: self._discard_finance_pending_if_untouched(pid),
                    add='+')

    def _discard_finance_pending_if_untouched(self, pending_id: str) -> None:
        """The wizard closed - if that pending item is still exactly the
        placeholder افزودن/کپی created (never approved, never rejected),
        drop it instead of leaving it در انتظار بررسی forever."""

        if self.db is None:
            return
        try:
            item = self.db.get_pending_item(pending_id)
        except Exception:
            return
        if item is None or str(item.get('status') or '').upper() not in ('', 'PENDING_REVIEW'):
            return
        try:
            from dashboard_stage18 import APPROVAL
            APPROVAL.reject(pending_id, actor_id='GUI_187_FINANCE_ABANDONED')
        except Exception:
            return
        self._changed()

    def _add_finance_payment(self) -> None:
        reached = self._finance_dashboard()
        if reached is None:
            return
        dashboard, center = reached
        contract, _payment = self._selected_finance_payment()
        payload = {
            'detected_type': 'EXPENSE', 'v18_title': 'هزینه ساخت', 'v18_subtype': 'نقدی',
            'event_date_shamsi': _today_shamsi(), 'amount': 0, 'payment_state': 'UNPAID',
            'contract_id': contract.get('contract_id') if contract else '',
            'cost_group': 'پیمانکار', 'source': 'MANUAL_GUI_187_FINANCE',
        }
        now_id = int(datetime.now().timestamp() * 1_000_000)
        self.db.register_telegram_message(chat_id=-187, message_id=now_id, raw_text='',
                                          content_type='manual_gui',
                                          message_date=datetime.now().isoformat(timespec='seconds'),
                                          state='RECEIVED')
        pending_id = self.db.create_or_replace_pending(
            telegram_chat_id=-187, telegram_message_id=now_id, detected_type='EXPENSE',
            payload=payload, confidence=1.0, status='PENDING_REVIEW')
        self._open_finance_pending(dashboard, center, str(pending_id), cleanup_if_abandoned=True)

    def _edit_finance_payment(self) -> None:
        """ویرایش: reopen the واریز's own پنجره ویزارد in ثبت دیتا.

        Submitting it there runs the existing revise_v18 path (an already
        posted transaction is corrected in place), which is what actually
        moves it out of در انتظار بررسی and back to تأییدشده - this button
        only has to get the wizard open on the right pending item.
        """

        reached = self._finance_dashboard()
        if reached is None:
            return
        _contract, payment = self._selected_finance_payment()
        if payment is None:
            messagebox.showinfo('امور مالی', 'ابتدا یک ردیف را انتخاب کنید.', parent=self)
            return
        pending_id = str(payment.get('pending_id') or '')
        if not pending_id:
            messagebox.showinfo('امور مالی', 'این واریزی به رکورد ثبت‌دیتا متصل نیست.', parent=self)
            return
        self._open_finance_pending(*reached, pending_id)

    def _delete_finance_payment(self) -> None:
        reached = self._finance_dashboard()
        if reached is None: return
        rows = self._selected_finance_sources()
        if not rows: return
        dashboard, center = reached
        remove = getattr(dashboard, '_delete_lifecycle_rows187', None)
        if callable(remove): remove(rows)
        else: center.batch_delete18(rows)
        self._changed()

    def _selected_finance_sources(self) -> list[dict]:
        """Resolve the full selection before changing either ledger or receipt file."""
        table = self.tables.get(FINANCE)
        if table is None: return []
        entries = getattr(self, '_finance_payments', [])
        rows, seen = [], set()
        by_key={f"{entry.get('contract_id')}:{entry.get('payment_index')}":entry for entry in entries}
        for key in table.selected_keys():
            entry = by_key.get(key)
            if entry is None: continue
            contract = get_contract(entry['contract_id']) or {}
            payments = contract.get('payments') or []
            if not 0 <= entry['payment_index'] < len(payments): continue
            pid = str(payments[entry['payment_index']].get('pending_id') or '')
            row = self.db.get_pending_item(pid) if pid else None
            if row is None:
                messagebox.showerror('تعیین تکلیف', 'یکی از واریزی‌ها به رکورد ثبت دیتا متصل نیست؛ هیچ ردیفی تغییر نکرد.', parent=self)
                return []
            if pid not in seen: rows.append(row); seen.add(pid)
        if not rows: messagebox.showinfo('امور مالی', 'ابتدا یک ردیف را انتخاب کنید.', parent=self)
        return rows

    def _copy_finance_payment(self) -> None:
        reached = self._finance_dashboard()
        if reached is None:
            return
        dashboard, center = reached
        rows = self._selected_finance_sources()
        if not rows: return
        from table_actions import copy_payload, copy_pending_attachments
        now_id = int(datetime.now().timestamp() * 1_000_000)
        pending_ids = []
        try:
            with self.db.atomic():
                for index, row in enumerate(rows):
                    payload = copy_payload(row.get('payload'))
                    payload['source'] = 'MANUAL_GUI_187_FINANCE_COPY'
                    payload['payment_state'] = 'UNPAID'
                    payload['paid_amount'] = 0
                    self.db.register_telegram_message(chat_id=-187, message_id=now_id+index, raw_text='',
                                          content_type='manual_gui',
                                          message_date=datetime.now().isoformat(timespec='seconds'),
                                          state='RECEIVED')
                    pending_id = self.db.create_or_replace_pending(
                        telegram_chat_id=-187, telegram_message_id=now_id+index,
                        detected_type=str(payload.get('detected_type') or row.get('detected_type') or 'EXPENSE'),
                        payload=payload, confidence=1.0, status='PENDING_REVIEW')
                    copy_pending_attachments(self.db, row['pending_id'], pending_id)
                    pending_ids.append(str(pending_id))
        except Exception as exc:
            messagebox.showerror('کپی انجام نشد', str(exc), parent=self); return
        if len(pending_ids) == 1:
            self._open_finance_pending(dashboard, center, pending_ids[0], cleanup_if_abandoned=True)
        else:
            center.filter.set('همه'); center.refresh()
            if getattr(dashboard, 'notebook', None) is not None and getattr(dashboard, 'approval_tab', None) is not None:
                dashboard.notebook.select(dashboard.approval_tab)
            messagebox.showinfo('کپی', f'{fa(len(pending_ids))} ردیف با پیوست‌هایشان در ثبت دیتا کپی شدند.', parent=self)

    def _finance_export_chosen(self) -> None:
        """Run the export the dropdown names, then go back to naming itself."""

        fmt = EXPORT_FORMATS.get(self.finance_export_choice.get())
        self.finance_export_choice.set(EXPORT_PROMPT)
        if fmt is not None:
            self._preview_export(FINANCE, fmt)

    def _statement_export_chosen(self) -> None:
        """Run the export the dropdown names, then go back to naming itself."""

        fmt = EXPORT_FORMATS.get(self.statement_export_choice.get())
        self.statement_export_choice.set(EXPORT_PROMPT)
        if fmt is not None:
            self._preview_export(STATEMENTS, fmt)

    def _archive_export_chosen(self) -> None:
        """Run the export the dropdown names, then go back to naming itself."""

        fmt = EXPORT_FORMATS.get(self.archive_export_choice.get())
        self.archive_export_choice.set(EXPORT_PROMPT)
        if fmt is not None:
            self._preview_export(ARCHIVE, fmt)

    def _context_menu(self, event) -> None:
        """Right click: the same four actions, on the row under the pointer."""

        item = self.tables[CONTRACTS].tree.identify_row(event.y)
        if item and item not in self.tables[CONTRACTS].tree.selection():
            self.tables[CONTRACTS].tree.selection_set(item)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label='قرارداد جدید', command=self.open_wizard)
        menu.add_command(label='ویرایش قرارداد', command=self.edit_selected)
        menu.add_command(label='کپی قرارداد', command=self.copy_selected_contract)
        menu.add_separator()
        menu.add_command(label='حذف ردیف',
                         command=lambda: self.delete_selected(CONTRACTS))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _finance_context_menu(self, event):
        tree = self.tables[FINANCE].tree
        iid = tree.identify_row(event.y)
        if iid:
            if iid not in tree.selection(): tree.selection_set(iid)
            tree.focus(iid)
        menu = tk.Menu(self, tearoff=0)
        for label, command in (('افزودن', self._add_finance_payment),
                ('ویرایش', self._edit_finance_payment), ('کپی', self._copy_finance_payment),
                ('حذف', self._delete_finance_payment), ('بروزرسانی', self.refresh)):
            menu.add_command(label=label, command=command)
        try: menu.tk_popup(event.x_root, event.y_root)
        finally: menu.grab_release()
        return 'break'

    def _archive_context_menu(self, event) -> None:
        """Right click: همان four toolbar actions, on the row under the pointer."""

        item = self.tables[ARCHIVE].tree.identify_row(event.y)
        if item and item not in self.tables[ARCHIVE].tree.selection():
            self.tables[ARCHIVE].tree.selection_set(item)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label='افزودن', command=lambda: self.open_wizard(ARCHIVE))
        menu.add_command(label='ویرایش', command=lambda: self.edit_selected_row(ARCHIVE))
        menu.add_command(label='کپی', command=self.copy_selected_profile)
        menu.add_separator()
        menu.add_command(label='حذف ردیف', command=lambda: self.delete_selected(ARCHIVE))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _statement_context_menu(self, event) -> None:
        """Right click: همان four toolbar actions, on the row under the pointer."""

        item = self.tables[STATEMENTS].tree.identify_row(event.y)
        if item and item not in self.tables[STATEMENTS].tree.selection():
            self.tables[STATEMENTS].tree.selection_set(item)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label='صورت‌وضعیت جدید', command=lambda: self.open_wizard(STATEMENTS))
        menu.add_command(label='ویرایش', command=lambda: self.edit_selected_row(STATEMENTS))
        menu.add_command(label='کپی', command=self.copy_selected_statement)
        menu.add_separator()
        menu.add_command(label='حذف ردیف', command=lambda: self.delete_selected(STATEMENTS))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _changed(self) -> None:
        """The contracts have moved, so redraw this list and tell the app.

        The plan totals its اجرت lines from these contracts, so a payment
        recorded here has to reach the rest of the program - and the payments
        are recorded in the record window, not the wizard.
        """

        self._filter_field_changed()
        if self.on_changed is not None:
            self.on_changed()

    def _contract_saved(self, contract, open_record: bool = True) -> None:
        # The record window opens first, and the rest of the program catches
        # up afterwards. It used to be the other way round, and a full refresh
        # takes seconds - long enough for the main window to come back to the
        # front over a record window that had not been created yet, and long
        # enough for anything that failed in it to stop the window opening at
        # all.
        record = None
        if open_record:
            record = ContractRecordWindow187(self, contract=contract, rich=self.rich,
                                             on_saved=lambda _c: self._changed())
        try:
            self._changed()
        finally:
            try:
                if record is not None and record.winfo_exists():
                    record.lift()
                    record.focus_force()
            except tk.TclError:
                pass

    def _statement_saved(self, statement, open_record: bool = True) -> None:
        record = None
        if open_record:
            record = StatementRecordWindow187(self, statement=statement, rich=self.rich,
                                              on_saved=lambda _s: self._changed())
        try:
            self._changed()
        finally:
            try:
                if record is not None and record.winfo_exists():
                    record.lift()
                    record.focus_force()
            except tk.TclError:
                pass

    def _profile_saved(self, profile, open_record: bool = True) -> None:
        record = None
        if open_record:
            record = ArchiveRecordWindow187(self, profile=profile, rich=self.rich,
                                            on_saved=lambda _p: self._changed())
        try:
            self._changed()
        finally:
            try:
                if record is not None and record.winfo_exists():
                    record.lift()
                    record.focus_force()
            except tk.TclError:
                pass

    def open_record(self, sub_tab: str, item: str | None) -> None:
        if sub_tab == CONTRACTS:
            table = self.tables.get(CONTRACTS)
            contract_id = table.key_for_item(item) if table is not None and item else None
            # Keep direct callers that already pass a contract ID working.
            if contract_id is None and item is not None and str(item) in self._contract_ids:
                contract_id = str(item)
            contract = get_contract(str(contract_id)) if contract_id else None
            if contract is not None:
                ContractDetailWindow187(self, contract=contract,
                                        on_export=self._export_contract)
            return
        if sub_tab == STATEMENTS:
            index = self._selected_index(STATEMENTS)
            ids = getattr(self, '_statement_ids', [])
            if index is not None and index < len(ids):
                statement = get_statement(ids[index])
                if statement is not None:
                    contract = get_contract(statement.get('contract_id')) or {}
                    StatementFinanceDetailWindow187(self, contract=contract, statement=statement,
                                                    db=self.db)
            return
        if sub_tab == FINANCE:
            # نه پنجرهٔ رکورد قرارداد - همان پنجرهٔ جزئیات مالی صورت‌وضعیت,
            # روی آخرین صورت‌وضعیت این قرارداد (اگر هنوز هیچ صورت‌وضعیتی
            # ثبت نشده، بخش ردیف‌های آن خالی می‌ماند - نه خطا).
            contract, _payment = self._selected_finance_payment()
            if contract is not None:
                own_statements = statements_for_contract(contract.get('contract_id'))
                latest_statement = own_statements[-1] if own_statements else None
                StatementFinanceDetailWindow187(self, contract=contract, statement=latest_statement,
                                                db=self.db)
            return
        if sub_tab == ARCHIVE:
            index = self._selected_index(ARCHIVE)
            ids = getattr(self, '_profile_ids', [])
            if index is not None and index < len(ids):
                profile = get_profile(ids[index])
                if profile is not None:
                    ArchiveDetailWindow187(self, profile=profile, on_export=self._export_profile)

    def approve_selected(self, sub_tab: str) -> None:
        pass

    def copy_selected(self, sub_tab: str) -> None:
        if sub_tab == CONTRACTS:self.copy_selected_contract()
        elif sub_tab == STATEMENTS:self.copy_selected_statement()
        elif sub_tab == ARCHIVE:self.copy_selected_profile()
        elif sub_tab == FINANCE:self._copy_finance_payment()

    def delete_selected(self, sub_tab: str) -> None:
        from table_actions import select_delete_rows
        if sub_tab in (STATEMENTS,ARCHIVE):
            table=self.tables.get(sub_tab)
            if table is None:return
            ids=getattr(self,'_statement_ids' if sub_tab==STATEMENTS else '_profile_ids',[])
            selected=[key for key in table.selected_keys() if key in ids]
            selected=select_delete_rows(self,selected,messagebox=messagebox)
            if not selected:return
            for key in selected:
                (delete_statement if sub_tab==STATEMENTS else delete_profile)(key)
            self._changed()
            return
        if sub_tab != CONTRACTS:
            return
        table = self.tables.get(CONTRACTS)
        if table is None:
            return
        selected_ids = []
        ids = getattr(self, '_contract_ids', [])
        for key in table.selected_keys():
            if key in ids:
                contract_id = str(key)
                if contract_id not in selected_ids:
                    selected_ids.append(contract_id)
        if not selected_ids:
            return
        if len(selected_ids) == 1:
            contract = get_contract(selected_ids[0])
            if contract is None:
                return
            title = f"قرارداد «{contract.get('title')}» حذف شود؟"
        else:
            title = f"{fa(len(selected_ids))} قرارداد انتخاب‌شده حذف شوند؟"
        receipts = [p for cid in selected_ids for p in (get_contract(cid) or {}).get('payments') or []]
        if receipts:
            title += f"\n{fa(len(receipts))} رسید واریزی هم به ردشده‌ها منتقل می‌شوند و اثرشان برداشته می‌شود."
        selected_ids=select_delete_rows(self,selected_ids,messagebox=messagebox,detail=title)
        if selected_ids:
            from contract_deletion import delete_contractors_with_history
            from transaction_lifecycle import TransactionLifecycle
            history = getattr(self.winfo_toplevel(), '_window_history', None)
            scope = history.hub.current_scope() if history is not None else None
            if history is not None:
                # Finish earlier edits first. The delete below is recorded as
                # one business action spanning the contract file and receipts.
                history.flush()
            try:
                deleted, action = delete_contractors_with_history(self.db, selected_ids)
                if deleted:
                    if history is not None and action is not None:
                        history.hub.record(action, scope)
                    self._changed()
            except (ValueError, KeyError) as exc:
                TransactionLifecycle(self.db).flag_decision('CONTRACT:'+','.join(selected_ids),'DELETE',exc)
                messagebox.showerror('تعیین تکلیف',str(exc),parent=self)

    def restore_selected(self, sub_tab: str) -> None:
        pass

    def _export_contract(self, contract, fmt: str) -> None:
        headers = ['عنوان', 'پیمانکار', 'مبلغ کل', 'پرداخت‌شده', 'مانده']
        payload = [{
            'عنوان': contract.get('title') or '',
            'پیمانکار': contract.get('family_name') or '',
            'مبلغ کل': _money(contract.get('total_amount')),
            'پرداخت‌شده': _money(paid_total(contract)),
            'مانده': _money(balance(contract)),
        }]
        return self._write_export(headers, payload, fmt, 'قرارداد پیمانکار', preview=True)

    def _export_profile(self, profile, fmt: str, addressee='سایر') -> None:
        """معیارهای نظرسنجی هم برود توی خروجی، نه فقط پنج ستون خلاصه - همان
        هویت + امتیاز + معیارها (دو ستون) + تاریخ‌های همکاری که پنجرهٔ
        جزئیات خودش نشان می‌دهد، نه یک ردیف تخت جدا از آن‌ها."""

        suffixes = {'pdf': '.pdf', 'xlsx': '.xlsx', 'print': '.pdf'}
        suffix = suffixes.get(fmt, '.xlsx')
        path = filedialog.asksaveasfilename(
            parent=self, title='خروجی رده‌بندی طرف حساب', defaultextension=suffix,
            filetypes=[(suffix.lstrip('.').upper(), f'*{suffix}')])
        if not path:
            return
        destination = Path(path)
        try:
            if suffix == '.pdf':
                criteria_headers, criteria_rows = archive_criteria_export_rows(profile)
                history_headers, history_rows = archive_history_export_rows(profile)
                export_archive_profile_pdf_187(
                    destination, title=f"جزئیات رده‌بندی - {profile.get('family_name') or ''}",
                    identity_lines=[*archive_identity_segments(profile), f'جهت ارائه به: {addressee}'],
                    score_line=archive_score_line(profile),
                    criteria_headers=criteria_headers, criteria_rows=criteria_rows,
                    history_headers=history_headers, history_rows=history_rows,
                )
                if fmt == 'print' and hasattr(os, 'startfile'):
                    os.startfile(str(destination), 'print')
            else:
                self._export_profile_xlsx(profile, destination, addressee)
        except Exception as exc:
            messagebox.showerror('خروجی', str(exc), parent=self)
            return
        messagebox.showinfo('خروجی', 'خروجی آماده شد.', parent=self)

    def _export_profile_xlsx(self, profile, destination: Path, addressee='سایر') -> None:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment
        book = Workbook()
        right = Alignment(horizontal='right')

        summary = book.active
        summary.title = 'مشخصات'
        summary.sheet_view.rightToLeft = True
        for line in archive_identity_segments(profile) + [archive_score_line(profile), f'جهت ارائه به: {addressee}']:
            summary.append([line])
            summary[summary.max_row][0].alignment = right

        criteria_headers, criteria_rows = archive_criteria_export_rows(profile)
        criteria_sheet = book.create_sheet('معیارهای نظرسنجی')
        criteria_sheet.sheet_view.rightToLeft = True
        criteria_sheet.append(criteria_headers)
        for cell in criteria_sheet[1]:
            cell.alignment = right
        for row in criteria_rows:
            criteria_sheet.append(row)
            for cell in criteria_sheet[criteria_sheet.max_row]:
                cell.alignment = right

        history_headers, history_rows = archive_history_export_rows(profile)
        history_sheet = book.create_sheet('تاریخ‌های همکاری')
        history_sheet.sheet_view.rightToLeft = True
        history_sheet.append(history_headers)
        for cell in history_sheet[1]:
            cell.alignment = right
        for row in history_rows:
            history_sheet.append(row)
            for cell in history_sheet[history_sheet.max_row]:
                cell.alignment = right

        book.save(destination)

    def _export_chosen(self) -> None:
        """Run the export the dropdown names, then go back to naming itself."""

        fmt = EXPORT_FORMATS.get(self.export_choice.get())
        self.export_choice.set(EXPORT_PROMPT)
        if fmt is not None:
            self._preview_export(CONTRACTS, fmt)

    EXPORT_TITLES = {
        CONTRACTS: 'قراردادهای پیمانکاران', STATEMENTS: 'صورت‌وضعیت‌های پیمانکاران',
        FINANCE: 'گزارش مالی پیمانکاران', ARCHIVE: 'رده‌بندی پیمانکاران',
    }

    def _preview_export(self, sub_tab: str, fmt: str = 'xlsx'):
        """Show the common RTL preview before the existing save implementation."""
        headers = [label for _key, label in COLUMNS[sub_tab]]
        rows, _status = self.load_rows(sub_tab)
        table = getattr(self, 'tables', {}).get(sub_tab)
        if table is not None:
            from report_document_stage18_7 import selected_table_rows
            rows = selected_table_rows(table)
        payload = [dict(zip(headers, row)) for row in rows]
        if sub_tab == FINANCE and table is not None:
            from report_document_stage18_7 import selected_tree_items, resolve_report_document_paths
            sources = getattr(self, '_finance_payments', [])
            for record, iid in zip(payload, selected_tree_items(table.tree)):
                key = table._sorted()[table.tree.index(iid)][2]
                source = next((item for item in sources
                               if f"{item.get('contract_id')}:{item.get('payment_index')}" == key), {})
                record['__document_paths_187'] = resolve_report_document_paths(getattr(self, 'db', None), source)
        if not payload:
            messagebox.showinfo('خروجی', 'ردیفی برای خروجی وجود ندارد.', parent=self)
            return None
        title = self.EXPORT_TITLES.get(sub_tab, 'پیمانکاران')
        choices = {'xlsx': 'Excel', 'pdf': 'PDF', 'print': 'پرینت'}
        return show_export_preview_187(
            self,
            export_format=choices.get(fmt, 'PDF'),
            headers=headers,
            rows=payload,
            title=f'پیش‌نمایش {title}',
            table_caption=title,
            row_label='ردیف',
            include_addressee=True,
            on_confirm=lambda choice, orientation, addressee, include_documents: self._write_export(
                headers,
                payload,
                {'Excel': 'xlsx', 'PDF': 'pdf', 'پرینت': 'print'}.get(choice, 'pdf'),
                title,
                orientation=orientation,
                addressee=addressee,
                include_documents=include_documents,
            ),
        )

    def export(self, sub_tab: str, fmt: str = 'xlsx') -> None:
        headers = [label for _key, label in COLUMNS[sub_tab]]
        rows, _status = self.load_rows(sub_tab)
        payload = [dict(zip(headers, row)) for row in rows]
        if not payload:
            messagebox.showinfo('خروجی', 'ردیفی برای خروجی وجود ندارد.', parent=self)
            return
        self._write_export(headers, payload, fmt, self.EXPORT_TITLES.get(sub_tab, 'پیمانکاران'))

    def _write_export(self, headers, payload, fmt: str, title: str, *, preview=False,
                      orientation: str | None = None, addressee='سایر',
                      include_documents=True):
        if preview:
            choices = {'xlsx': 'Excel', 'pdf': 'PDF', 'print': 'پرینت'}
            return show_export_preview_187(
                self,
                export_format=choices.get(fmt, 'PDF'),
                headers=headers,
                rows=payload,
                title=f'پیش‌نمایش {title}',
                table_caption=title,
                row_label='ردیف',
                include_addressee=True,
                on_confirm=lambda choice, selected_orientation, selected_addressee, show_documents: self._write_export(
                    headers,
                    payload,
                    {'Excel': 'xlsx', 'PDF': 'pdf', 'پرینت': 'print'}.get(choice, 'pdf'),
                    title,
                    orientation=selected_orientation,
                    addressee=selected_addressee,
                    include_documents=show_documents,
                ),
            )
        suffixes = {'pdf': '.pdf', 'xlsx': '.xlsx', 'print': '.pdf'}
        suffix = suffixes.get(fmt, '.xlsx')
        path = filedialog.asksaveasfilename(
            parent=self, title=f'خروجی {title}', defaultextension=suffix,
            filetypes=[(suffix.lstrip('.').upper(), f'*{suffix}')])
        if not path:
            return
        destination = Path(path)
        try:
            export_rows = [[row.get(header, '') for header in headers] for row in payload]
            if not include_documents:
                document_columns = [index for index, header in enumerate(headers)
                                    if header in {'نمایش سند', 'فیش واریزی', 'رسید', 'سند'}]
                for row in export_rows:
                    for index in document_columns:
                        if index < len(row):
                            row[index] = '-'
            summary = [f'جهت ارائه به: {addressee}']
            if suffix == '.pdf':
                # export_pdf lays its own columns out left-to-right, so a
                # logical-order header list puts ردیف at the sheet's left
                # edge - backwards from the on-screen table, where the same
                # column sits at the right. Reversed here, the same way
                # export_receipts_pdf_187 already reverses its own tables.
                pdf_headers = list(reversed(headers))
                pdf_rows = [[row.get(header, '') for header in pdf_headers] for row in payload]
                if orientation in {'افقی', 'عمودی'}:
                    export_contract_pdf_187(
                        destination, pdf_headers, pdf_rows, title,
                        orientation=orientation,
                        summary_lines=summary,
                    )
                else:
                    export_contract_pdf_187(destination, pdf_headers, pdf_rows, title,
                                            summary_lines=summary)
                if fmt == 'print' and hasattr(os, 'startfile'):
                    os.startfile(str(destination), 'print')
            else:
                from export_utils import export_xlsx
                export_xlsx(destination, headers, export_rows, title=title,
                            summary_lines=summary)
        except Exception as exc:
            messagebox.showerror('خروجی', str(exc), parent=self)
            return
        messagebox.showinfo('خروجی', 'خروجی آماده شد.', parent=self)
        return True

class ContractorWizard187(BarkavWizard):
    """Step-by-step contractor record.  Chrome and navigation come from the kit."""

    size_class = 'medium'
    step_titles = ('مشخصات پیمانکار', 'مشخصات قرارداد', 'شرایط مالی', 'تأیید نهایی')

    FIELDS = {
        0: (('name', 'نام پیمانکار'), ('national_id', 'شناسه/کد ملی'),
            ('phone', 'تلفن'), ('specialty', 'تخصص')),
        1: (('subject', 'موضوع قرارداد'), ('number', 'شماره قرارداد'),
            ('date', 'تاریخ قرارداد'), ('duration', 'مدت (ماه)')),
        2: (('amount', 'مبلغ قرارداد (تومان)'), ('advance', 'پیش‌پرداخت (تومان)'),
            ('retention', 'حسن انجام کار (٪)'), ('installments', 'تعداد اقساط')),
        3: (),
    }

    def __init__(self, parent: tk.Misc, title: str, *, on_saved=None, **kwargs):
        self.on_saved = on_saved
        self.values: dict[str, tk.StringVar] = {}
        super().__init__(parent, title, **kwargs)

    def render_step(self, index: int, parent: tk.Frame) -> None:
        p = kit_palette()
        m = kit_metrics()
        tk.Label(
            parent, text=f'‏{fa(index + 1)}. {self.step_titles[index]}',
            bg=p['bg'], fg=p['text_primary'], font=kit_font('title'), anchor='e',
        ).pack(fill='x', pady=(0, m['gap']))

        if not self.FIELDS[index]:
            tk.Label(
                parent, text='برای ثبت نهایی، دکمه ذخیره را بزنید.',
                bg=p['bg'], fg=p['text_secondary'], font=kit_font('body'), anchor='e',
            ).pack(fill='x')
            return

        grid = tk.Frame(parent, bg=p['bg'])
        grid.pack(fill='x')
        grid.columnconfigure((0, 1), weight=1, uniform='field')
        for position, (key, label) in enumerate(self.FIELDS[index]):
            # Section 9: label above the field; column 1 is the right-hand
            # column so the first field lands right in RTL.
            row, column = divmod(position, 2)
            cell = tk.Frame(grid, bg=p['bg'])
            cell.grid(row=row, column=1 - column, sticky='ew',
                      padx=m['gap'] // 2, pady=m['gap'] // 2)
            tk.Label(cell, text=label, bg=p['bg'], fg=p['text_secondary'],
                     font=kit_font('small'), anchor='e').pack(fill='x')
            variable = self.values.setdefault(key, tk.StringVar())
            ttk.Entry(cell, textvariable=variable, justify='right').pack(fill='x')

    def finish(self) -> None:
        """Persist the contractor record here, then let the panel refresh."""

        if self.on_saved is not None:
            self.on_saved()
        self.close()
