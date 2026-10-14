"""COPY THIS FILE to start a new tab.

It is a complete, working example of the structure every BARKAV tab follows:
a sub-tab strip, a toolbar, a striped table, an action bar, and a wizard.
Everything visual is already correct and contract-compliant.

To build a new tab:
  1. Copy this file to ``<name>_stage18_7.py``.
  2. Rename ``TemplatePanel`` / ``TemplateWizard``.
  3. Replace SUB_TABS, COLUMNS and the labels with your own.
  4. Replace ``load_rows`` and ``TemplateWizard.finish`` with real service calls.

Do NOT add colours, font families or point sizes.  If you find yourself
wanting one, the component you need is missing from the kit - ask for it
rather than hard-coding it here.  ``tests/test_stage18_7_ui_contract.py``
fails the build on literal colours in this layer.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui_stage18_3 import fa

from .table import DataTable
from .tabs import sub_notebook
from .theme import font, metrics, palette
from .window import BarkavWizard


# --- what a new tab customises ---------------------------------------------

SUB_TABS = ('همه', 'فعال', 'خاتمه‌یافته')

COLUMNS = (
    ('row', 'ردیف'),
    ('name', 'نام'),
    ('contract', 'شماره قرارداد'),
    ('amount', 'مبلغ (تومان)'),
    ('status', 'وضعیت'),
)

class TemplatePanel(ttk.Frame):
    """One product tab: sub-tabs, each holding a toolbar + table + actions."""

    def __init__(self, parent: tk.Misc, *, db=None, base_dir=None, on_changed=None):
        super().__init__(parent, style='Panel.TFrame')
        self.db = db
        self.base_dir = base_dir
        self.on_changed = on_changed
        self.filter_text = tk.StringVar()
        self.export_choice = tk.StringVar(value='خروجی')
        self.tables: dict[str, DataTable] = {}
        self._build()

    def _build(self) -> None:
        m = metrics()
        notebook, self.strip = sub_notebook(self, level=2)
        self.notebook = notebook
        for label in SUB_TABS:
            page = ttk.Frame(notebook, style='Panel.TFrame', padding=m['outer_pad'])
            notebook.add(page, text=label)
            self.tables[label] = self._build_page(page, label)
        self.strip.rebuild()
        self.refresh()

    def _build_page(self, page: ttk.Frame, label: str) -> DataTable:
        table = DataTable(
            # No widths: DataTable measures each heading and its column's
            # contents, so headings stay tight against their own data.
            page, COLUMNS,
            on_open=lambda item, name=label: self.open_record(name, item),
            empty_text='رکوردی ثبت نشده است',
        )
        table.pack(fill='both', expand=True)

        # Section 4: filter and row actions right, output controls left.
        table.toolbar.add_search(self.filter_text)
        table.add_tool('ویرایش', lambda: self.open_record(label, None))
        table.add_export(self.export_choice, self.export,
                         label=None, side='left')

        # Section 6: declare in this order - destructive last, so it lands
        # furthest from the buttons the user reaches for first.
        table.add_action('افزودن', self.open_wizard, 'create')
        table.add_action('تأیید', self.approve_selected, 'neutral')
        table.add_action('کپی', self.copy_selected, 'caution')
        table.add_action('حذف', self.delete_selected, 'destructive')
        return table

    # --- data ---------------------------------------------------------------

    def load_rows(self, sub_tab: str) -> tuple[list[tuple], dict[int, str]]:
        """Return ``(rows, status_by_index)``.  Replace with real service calls.

        ``status`` values must be 'pending', 'approved' or 'rejected'; they
        tint the row instead of its stripe.
        """

        rows = [
            (fa(1), 'نمونه اول', fa('1001'), fa('120,000,000'), 'در انتظار'),
            (fa(2), 'نمونه دوم', fa('1002'), fa('85,000,000'), 'تأییدشده'),
            (fa(3), 'نمونه سوم', fa('1003'), fa('40,000,000'), 'ردشده'),
        ]
        return rows, {0: 'pending', 1: 'approved', 2: 'rejected'}

    def refresh(self) -> None:
        for label, table in self.tables.items():
            rows, status = self.load_rows(label)
            table.set_rows(rows, status=status)

    # --- actions ------------------------------------------------------------

    def open_wizard(self) -> None:
        TemplateWizard(self, 'ثبت مرحله‌ای رکورد', on_saved=self.refresh)

    def open_record(self, sub_tab: str, item: str | None) -> None:
        """Open the detail window for a row.  Use BarkavWindow, never Toplevel."""

    def approve_selected(self) -> None:
        pass

    def copy_selected(self) -> None:
        pass

    def delete_selected(self) -> None:
        pass

    def export(self) -> None:
        pass


class TemplateWizard(BarkavWizard):
    """A step-by-step record window.  Chrome and navigation come from the kit."""

    size_class = 'medium'
    step_titles = ('مشخصات پایه', 'جزئیات قرارداد', 'پرداخت‌ها', 'تأیید نهایی')

    #: (key, label) per step.
    FIELDS = {
        0: (('name', 'نام'), ('national_id', 'شناسه')),
        1: (('contract', 'شماره قرارداد'), ('date', 'تاریخ')),
        2: (('amount', 'مبلغ کل (تومان)'),),
        3: (),
    }

    def __init__(self, parent: tk.Misc, title: str, *, on_saved=None, **kwargs):
        self.on_saved = on_saved
        self.values: dict[str, tk.StringVar] = {}
        super().__init__(parent, title, **kwargs)

    def render_step(self, index: int, parent: tk.Frame) -> None:
        p = palette()
        m = metrics()
        tk.Label(
            parent, text=f'{fa(index + 1)}. {self.step_titles[index]}',
            bg=p['surface'], fg=p['text_primary'], font=font('title'), anchor='e',
        ).pack(fill='x', pady=(0, m['gap']))

        grid = tk.Frame(parent, bg=p['surface'])
        grid.pack(fill='x')
        grid.columnconfigure((0, 1), weight=1, uniform='field')
        for position, (key, label) in enumerate(self.FIELDS[index]):
            # Section 9: label above the field, right-aligned; column 1 is the
            # right-hand column so the first field lands right in RTL.
            row, column = divmod(position, 2)
            cell = tk.Frame(grid, bg=p['surface'])
            cell.grid(row=row, column=1 - column, sticky='ew', padx=m['gap'] // 2, pady=m['gap'] // 2)
            tk.Label(cell, text=label, bg=p['surface'], fg=p['text_secondary'],
                     font=font('small'), anchor='e').pack(fill='x')
            variable = self.values.setdefault(key, tk.StringVar())
            ttk.Entry(cell, textvariable=variable, justify='right').pack(fill='x')

    def validate_step(self, index: int) -> bool:
        for key, _label in self.FIELDS[index]:
            if not self.values.get(key, tk.StringVar()).get().strip():
                return False
        return True

    def finish(self) -> None:
        """Persist here, then let the panel refresh."""

        if self.on_saved is not None:
            self.on_saved()
        self.close()
