from __future__ import annotations

from datetime import datetime
import os
import logging
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import uuid

from dashboard_stage17 import PhaseDetailDialog17
from sales_claims_stage18_7 import formatted_amount_input_187
from numeric_entry_stage18_7 import format_numeric_entry
from project_table_actions187 import ProjectTableActions, ensure_land_row_links, popup_menu
from ui_stage18_3 import en, fa, parse_int, install_smarttable_export_dropdown
from barkav_ui import BarkavDialog, BarkavWindow, confirm
from barkav_ui import art
from barkav_ui.table import ACTION_STYLES, CHECKBOX_CHECKED, CHECKBOX_UNCHECKED, apply_tree_rtl
from barkav_ui.tabs import LegacyTabStrip
from barkav_ui.theme import font as kit_font, metrics as kit_metrics
from cost_allocation_stage18_7 import apply_actuals, plan_row_labels
from project_plan_stage18_7 import (
    PLAN_COLUMNS,
    PLAN_TAB,
    PRICE_TABS,
    PricePanel187,
    ProjectPlanPanel187,
    project_actual_rows187,
    _money as _plan_money_187,
    _number as _plan_number_187,
    _quantities as _plan_quantities_187,
    _rates as _plan_rates_187,
    _totals as _plan_totals_187,
    price_code as _plan_price_code_187,
)
from ui_stage18_7 import palette_187


CATEGORY_LABELS_187 = {
    'MATERIAL': 'مصالح',
    'LABOR': 'دستمزد/اجرا',
    'SERVICE': 'اداری/خدمات',
    'LAND': 'خرید زمین',
    'INSTALLATION_GROUP': 'تأسیسات تجمیعی',
}
CATEGORY_CODES_187 = {value: key for key, value in CATEGORY_LABELS_187.items()}

# The phase summary is an aggregate, while the detail window is a filtered
# view of the exact same rows shown in پلان کلی.  Therefore unit rates belong
# in the drill-down, where each row carries its own price reference.
PHASE_SUMMARY_PLAN_LABELS_187 = {
    'no': 'ردیف', 'phase': 'فاز اجرایی', 'est': 'مبلغ کل-اولیه',
    'actual': 'مبلغ کل-واقعی', 'rem': 'مانده برآورد',
    'fc': 'مبلغ کل-بروز', 'var': 'انحراف',
}
# The summary contains phase-level aggregates, so only the headings that have
# an exact equivalent in پلان کلی remain visible.  ``remaining`` and
# ``variance`` are still present in the backing rows for calculations, but
# they do not masquerade as plan-sheet columns in this grid.
PHASE_SUMMARY_VISIBLE_COLUMNS_187 = ('no', 'phase', 'est', 'fc', 'actual')
PHASE_DETAIL_COLUMN_WIDTHS_187 = {
    'no': 70, 'code': 95, 'title': 235, 'phase': 160, 'unit': 80,
    'rate_base': 135, 'rate_current': 135, 'rate_actual': 135,
    'qty_base': 110, 'qty_current': 110, 'qty_actual': 110,
    'total_base': 145, 'total_current': 145, 'total_actual': 145,
}
PHASE_DETAIL_PLAN_COLUMNS_187 = tuple(
    (key, label, PHASE_DETAIL_COLUMN_WIDTHS_187.get(key, 120))
    for key, label in PLAN_COLUMNS
)


def phase_detail_plan_values_187(row: dict) -> list[str]:
    """Render one phase line exactly as its matching row in پلان کلی.

    Rates are read through the shared price reference helpers; quantities and
    totals are the same row-level calculations used by ProjectPlanPanel187.
    """
    rates = _plan_rates_187(row)
    quantities = _plan_quantities_187(row)
    totals = _plan_totals_187(row)
    return [
        fa(str(row.get('plan_ref') or '')),
        _plan_price_code_187(row),
        str(row.get('description') or ''),
        fa('%02d' % int(row.get('phase_no') or 0)),
        str(row.get('unit') or ''),
        *(_plan_money_187(value) for value in rates),
        *(_plan_number_187(value) for value in quantities),
        *(_plan_money_187(value) for value in totals),
    ]


def _move_phase_view_to_right_187(table) -> None:
    """Open an RTL phase table from its right-hand reading edge."""
    try:
        tree = table.tree
        tree.xview_moveto(1.0)
        tree.after_idle(lambda: tree.xview_moveto(1.0))
    except tk.TclError:
        pass


def _bind_phase_open_view_187(table) -> None:
    """Restore the right-hand viewport when the containing phase tab opens."""
    if getattr(table, '_phase_open_view_bound_187', False):
        return
    table._phase_open_view_bound_187 = True
    table.tree.bind('<Map>', lambda _event: _move_phase_view_to_right_187(table), add='+')


def _set_phase_table_rtl_187(table, visible_columns) -> None:
    """Apply one explicit RTL contract to either phase table."""
    tree = table.tree
    all_columns = {key for key, _label, _width in table.columns}
    shown = [key for key in visible_columns if key in all_columns]
    if '_check187' in all_columns:
        shown.insert(0, '_check187')
    try:
        tree.configure(displaycolumns=tuple(reversed(shown)))
        for key, label, _width in table.columns:
            tree.heading(key, text=label, anchor='e')
            tree.column(key, anchor='e')
        # The shell-wide RTL pass must not reverse these already RTL tables.
        tree._barkav_rtl_187 = True
    except tk.TclError:
        pass


def _span_phase_horizontal_scrollbar_187(table) -> None:
    """Make the phase table's horizontal bar span the table and scroll area."""
    try:
        table_frame = next(
            child for child in table.winfo_children()
            if isinstance(child, ttk.Frame)
            and any(isinstance(item, ttk.Scrollbar) for item in child.winfo_children())
        )
        horizontal = next(
            child for child in table_frame.winfo_children()
            if isinstance(child, ttk.Scrollbar) and child.cget('orient') == 'horizontal'
        )
        horizontal.grid(row=1, column=0, columnspan=2, sticky='ew')
        table_frame.columnconfigure(0, weight=1)
    except (StopIteration, tk.TclError):
        pass


def _export_through_preview_187(parent, choice, headers, rows, title, summary_lines=()):
    """Excel/PDF/پرینت of ``rows`` through the shared RTL preview, saved only on confirm.

    The same preview every other active export surface opens
    (``show_export_preview_187``); these management tabs used to write their
    file straight away, or - once the old report export band was removed -
    had no output at all.
    """

    from export_utils import export_pdf, export_xlsx, print_file
    from sales_claims_stage18_7 import show_export_preview_187

    if choice not in {'Excel', 'PDF', 'پرینت'}:
        return None
    rows = [dict(row) if isinstance(row, dict) else list(row) for row in rows]
    if not rows:
        messagebox.showinfo('خروجی', 'ردیفی برای خروجی وجود ندارد.', parent=parent)
        return None

    def save(selected, orientation=None, addressee='سایر', include_documents=True):
        suffix = '.xlsx' if selected == 'Excel' else '.pdf'
        path = filedialog.asksaveasfilename(
            parent=parent, title=f'خروجی {title}', defaultextension=suffix,
            initialfile=f'{title}{suffix}',
            filetypes=[('Excel', '*.xlsx')] if suffix == '.xlsx' else [('PDF', '*.pdf')])
        if not path:
            return False
        try:
            summary = [*summary_lines, f'جهت ارائه به: {addressee}']
            output_rows = [list(row) for row in rows]
            if not include_documents:
                document_columns = [index for index, header in enumerate(headers)
                                    if header in {'نمایش سند', 'فیش واریزی', 'رسید', 'سند'}]
                for row in output_rows:
                    for index in document_columns:
                        if index < len(row):
                            row[index] = '-'
            if selected == 'Excel':
                export_xlsx(path, headers, output_rows, title=title, summary_lines=summary)
            else:
                export_pdf(path, headers, output_rows, title=title, summary_lines=summary,
                           orientation=orientation)
                if selected == 'پرینت':
                    print_file(path)
        except Exception as exc:
            messagebox.showerror('خروجی', f'خروجی انجام نشد:\n{exc}', parent=parent)
            return False
        messagebox.showinfo('خروجی', f'فایل ساخته شد:\n{path}', parent=parent)
        return True

    return show_export_preview_187(parent, export_format=choice, headers=headers, rows=rows,
                                   title=f'پیش‌نمایش {title}', table_caption=title,
                                   row_label='ردیف', on_confirm=save,
                                   specs=[('خلاصه', 'اطلاعات', line) for line in summary_lines or ()],
                                   include_addressee=True)


def _smarttable_export_rows_187(table):
    """A SmartTable's shown rows (the checked ones, when any), without its ✓ column."""

    headers, rows = table.current_report_rows(selected_only=bool(table.selected_rows()))
    if headers and headers[0] == 'انتخاب':
        headers, rows = headers[1:], [row[1:] for row in rows]
    return headers, rows


def _route_smarttable_export_to_preview_187(table, title: str) -> None:
    combo = getattr(table, '_barkav_export_combo', None)
    var = getattr(table, '_barkav_export_var', None)
    if combo is None or var is None:
        return
    combo.unbind('<<ComboboxSelected>>')

    def chosen(_event=None):
        choice = var.get()
        var.set('خروجی')
        headers, rows = _smarttable_export_rows_187(table)
        summary = []
        try:
            summary = [str(table.total.get())]
        except (AttributeError, tk.TclError):
            pass
        _export_through_preview_187(table, choice, headers, rows, title, summary)

    combo.bind('<<ComboboxSelected>>', chosen, add='+')


def _tree_export_control_187(host, tree, headers, title, *, before=None) -> ttk.Combobox:
    """Add the single «خروجی» control for a plain report Treeview."""

    p = palette_187()
    bar = tk.Frame(host, bg=p['panel'])
    if before is not None:
        bar.pack(fill='x', before=before)
    else:
        bar.pack(fill='x')
    var = tk.StringVar(master=host, value='خروجی')
    combo = ttk.Combobox(bar, textvariable=var, values=('خروجی', 'PDF', 'Excel', 'پرینت'),
                         state='readonly', justify='right', width=19)
    combo.pack(side='left', padx=4, pady=3)

    def chosen(_event=None):
        choice = var.get()
        var.set('خروجی')
        from report_document_stage18_7 import selected_tree_items
        rows = [list(tree.item(item, 'values')) for item in selected_tree_items(tree)]
        _export_through_preview_187(host, choice, headers, rows, title)

    combo.bind('<<ComboboxSelected>>', chosen, add='+')
    return combo


def install_report_exports_187(app) -> None:
    """Export (through the preview) on «خلاصه روندهای گزارش» and «شاخص‌های مالی».

    Both lost their only output when the report export band was removed
    (see _lift_estimate_bar_187); they get one of their own, on their own
    header, like every other management tab.
    """

    tree = getattr(app, 'report_summary_tree', None)
    if tree is not None and not getattr(app, '_summary_export_187', None):
        app._summary_export_187 = _tree_export_control_187(
            tree.master, tree, ['شاخص', 'مقدار', 'جزئیات'], 'خلاصه روندهای گزارش', before=tree)
    index_table = getattr(app, 'index_table', None)
    if index_table is not None and not getattr(app, '_indices_export_187', None):
        app._indices_export_187 = _tree_export_control_187(
            index_table.master, index_table,
            ['شاخص', 'برآورد اولیه', 'انجام‌شده + بروز تا پایان', 'بروز صفر تا ۱۰۰'],
            'شاخص‌های مالی', before=index_table)


def _standardise_smarttable_toolbar_187(table, actions, title: str = 'گزارش') -> None:
    """Give a legacy SmartTable the project-management toolbar contract."""
    try:
        toolbar = table.winfo_children()[0]
    except (IndexError, tk.TclError):
        return
    for child in tuple(toolbar.winfo_children()):
        child.pack_forget()
    for label, command in actions:
        ttk.Button(toolbar, text=label, command=command,
                   style='TableToolbar.TButton').pack(side='right', padx=2)
    # Pack the label first from the right, so the entry appears to its left:
    # «جستجو: [کادر]», the reading order used in the plan and price tabs.
    ttk.Label(toolbar, text='جستجو:').pack(side='right')
    ttk.Entry(toolbar, textvariable=table.quick, width=22, justify='right',
              style='Compact.TEntry').pack(side='right', padx=(2, 16))
    try:
        table.quick.trace_add('write', lambda *_args: table.apply_filter())
    except tk.TclError:
        pass
    install_smarttable_export_dropdown(table)
    _route_smarttable_export_to_preview_187(table, title)


def _configure_phase_summary_table_187(app) -> None:
    """Match the فازها summary's RTL layout to the plan/price tabs."""
    table = app.phase_table
    table.columns = [
        (key, PHASE_SUMMARY_PLAN_LABELS_187.get(key, label), width)
        for key, label, width in table.columns
    ]
    _set_phase_table_rtl_187(table, PHASE_SUMMARY_VISIBLE_COLUMNS_187)
    _span_phase_horizontal_scrollbar_187(table)
    _bind_phase_open_view_187(table)
    _move_phase_view_to_right_187(table)
    for child in table.winfo_children()[0].winfo_children():
        if isinstance(child, ttk.Label) and str(child.cget('text')).startswith('کنترل فازها'):
            child.configure(text='فازها — خلاصه برآورد اولیه، واقعی و بروز')
            break

    def open_selected_phase():
        row = _selected_one(table)
        if row is None:
            messagebox.showinfo('فازها', 'ابتدا یک فاز را انتخاب کنید.', parent=app)
            return
        app.open_phase_by_no(int(row['phase_no']))

    _standardise_smarttable_toolbar_187(table, (
        ('افزودن', open_selected_phase),
        ('ویرایش', open_selected_phase),
        ('حذف', open_selected_phase),
        ('کپی', table.copy_selected),
    ), title='فازها')

def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def install_checkbox_column_187(table) -> None:
    if getattr(table, '_checkbox_column_187', False):
        return
    old_columns = list(table.columns)
    old_keys = [item[0] for item in old_columns]
    check_key = '_check187'
    table.columns = [(check_key, 'انتخاب', 55)] + old_columns
    table.tree.configure(columns=(check_key, *old_keys))
    table.tree.heading(check_key, text='✓', anchor='center')
    table.tree.column(check_key, width=55, minwidth=45, stretch=False, anchor='center')
    for key, label, width in old_columns:
        table.tree.heading(key, text=label, anchor='e')
        table.tree.column(key, width=width, anchor='e')
    table.tree.configure(displaycolumns=tuple(reversed((check_key, *old_keys))))
    original_set_rows = table.set_rows

    def set_rows_with_check(rows, renderer):
        return original_set_rows(rows, lambda row: [CHECKBOX_UNCHECKED, *renderer(row)])

    table.set_rows = set_rows_with_check

    def sync_checks(_event=None):
        selected = set(table.tree.selection())
        for item in table.tree.get_children(''):
            values = list(table.tree.item(item, 'values') or ())
            if values:
                values[0] = CHECKBOX_CHECKED if item in selected else CHECKBOX_UNCHECKED
                table.tree.item(item, values=values)

    table.tree.bind('<<TreeviewSelect>>', sync_checks, add='+')
    # The column only echoes the selection; the kit's right-hand check
    # column (barkav_ui.row_overlay) shows the same state and replaces it.
    table.tree._barkav_selection_mirror_columns = {check_key}
    table._checkbox_column_187 = True


class PhaseDetailDialog187(PhaseDetailDialog17):
    """A phase drill-down rendered column-for-column as پلان کلی."""

    def __init__(self, parent, rich, phase_no: int, phase_name: str, on_refresh):
        self.dashboard = parent
        super().__init__(parent, rich, phase_no, phase_name, on_refresh)
        self.title(f'ریز فاز {phase_no:02d} — {phase_name} — BARKAV 18.7')
        self.resizable(True, True)
        self.minsize(900, 580)
        self._restyle_phase_detail_187()
        self._install_phase_navigation_187()
        self.refresh()

    def _configure_plan_columns_187(self) -> None:
        """Turn the inherited SmartTable into the same visible sheet columns."""
        table = self.table
        table.columns = list(PHASE_DETAIL_PLAN_COLUMNS_187)
        keys = tuple(key for key, _label, _width in table.columns)
        try:
            table.tree.configure(columns=keys)
            for key, label, width in table.columns:
                table.tree.heading(key, text=label, anchor='e')
                table.tree.column(key, width=width, minwidth=60, anchor='e', stretch=True)
        except tk.TclError:
            pass
        _set_phase_table_rtl_187(table, keys)

    def refresh(self):
        """Use the exact rate, quantity and total helpers of پلان کلی."""
        table = getattr(self, 'table', None)
        if table is None:
            return
        self._configure_plan_columns_187()
        projected = {row['phase_item_id']: row for row in project_actual_rows187(self.rich.all_phase_items())}
        table.set_rows([projected.get(row['phase_item_id'], row) for row in self.rows()], phase_detail_plan_values_187)
        _move_phase_view_to_right_187(table)

    def _restyle_phase_detail_187(self):
        """Keep the shared toolbar, RTL order and phase-opening viewport."""
        table = getattr(self, 'table', None)
        if table is None:
            return
        self._configure_plan_columns_187()

        toolbar = next((child for child in table.winfo_children()
                        if isinstance(child, ttk.Frame)), None)
        if toolbar is not None:
            _standardise_smarttable_toolbar_187(table, (
                ('افزودن', self.add_item),
                ('ویرایش', lambda: self.edit_item(self.one())),
                ('حذف', lambda: self.delete_item(self.one())),
                ('کپی', table.copy_selected),
            ), title=f'ریز فاز {self.phase_no:02d}')
            table.tree.unbind('<Button-3>')
            table.tree.bind('<Button-3>', self._phase_context_menu_187, add='+')

        # The inherited bottom action row duplicated the toolbar. Remove only
        # that row; the table summary and its context menu remain available.
        for child in tuple(self.winfo_children()):
            if child is table or not isinstance(child, tk.Frame):
                continue
            texts = ' '.join(
                str(grandchild.cget('text'))
                for grandchild in child.winfo_children()
                if isinstance(grandchild, (tk.Label, ttk.Label))
            )
            if 'قیمت‌های واحد' in texts:
                child.destroy()
                break

        # SmartTable's vertical bar stays at the right. Its horizontal view
        # opens at the right edge and returns there each time this dialog maps.
        try:
            tree = table.tree
            table_frame = next(
                child for child in table.winfo_children()
                if isinstance(child, ttk.Frame) and child is not toolbar
            )
            vertical = next(
                child for child in table_frame.winfo_children()
                if isinstance(child, ttk.Scrollbar) and child.cget('orient') == 'vertical'
            )
            horizontal = next(
                child for child in table_frame.winfo_children()
                if isinstance(child, ttk.Scrollbar) and child.cget('orient') == 'horizontal'
            )
            tree.grid(row=0, column=0, sticky='nsew')
            vertical.grid(row=0, column=1, sticky='ns')
            horizontal.grid(row=1, column=0, columnspan=2, sticky='ew')
            table_frame.columnconfigure(0, weight=1)
        except (StopIteration, tk.TclError):
            pass
        _bind_phase_open_view_187(table)
        _move_phase_view_to_right_187(table)

    def _install_phase_navigation_187(self) -> None:
        """Put previous/next phase controls in the detail window header."""
        if getattr(self, '_phase_navigation_installed_187', False):
            return
        header = next(
            (child for child in self.winfo_children()
             if isinstance(child, tk.Frame) and child is not self.table),
            None,
        )
        if header is None:
            return
        ttk.Button(
            header, text='فاز بعدی', style='TableToolbar.TButton',
            command=lambda: self._navigate_phase_187(1),
            state='disabled' if int(self.phase_no) >= 32 else 'normal',
        ).pack(side='left', padx=(2, 6))
        ttk.Button(
            header, text='فاز قبلی', style='TableToolbar.TButton',
            command=lambda: self._navigate_phase_187(-1),
            state='disabled' if int(self.phase_no) <= 1 else 'normal',
        ).pack(side='left', padx=2)
        self._phase_navigation_installed_187 = True

    def _navigate_phase_187(self, offset: int) -> None:
        target = int(self.phase_no) + int(offset)
        if not 1 <= target <= 32:
            return
        available = {
            int(row['phase_no'])
            for row in self.dashboard._phase_summary_live()
            if row.get('phase_no') is not None
        }
        if target not in available:
            messagebox.showinfo('فازها', 'برای این فاز هنوز ردیفی ثبت نشده است.', parent=self)
            return
        self.destroy()
        self.dashboard.open_phase_by_no(target)

    def _row_saved_187(self, created=None, after=None):
        if created:
            try:
                self.rich.place_phase_item(created, after, renumber_price=True)
            except Exception as exc:
                messagebox.showerror('افزودن ردیف', str(exc), parent=self)
        _refresh_plan_187(self.dashboard)
        self.refresh()

    def add_item(self):
        from project_plan_stage18_7 import PlanRowWindow187
        anchor = self.one() or {}
        PlanRowWindow187(self, rich=self.rich, row={
            'phase_no': self.phase_no, 'phase_name': self.phase_name,
            'cost_type': anchor.get('cost_type') or 'خدمات',
            'section': anchor.get('section') or '', 'anchor_cost_type': anchor.get('cost_type'),
            'factor': 1,
        }, on_saved=lambda created: self._row_saved_187(created, anchor.get('phase_item_id')))

    def edit_item(self, row):
        if row:
            from project_plan_stage18_7 import PlanRowWindow187
            PlanRowWindow187(self, rich=self.rich, row=row, on_saved=self._row_saved_187)

    def _phase_context_menu_187(self, event):
        actions = self.dashboard.project_table_actions187
        actions.context_selection(self.table, event)

        def paste():
            row = self.one() or {}
            actions.paste_plan(phase_no=self.phase_no, phase_name=self.phase_name, after=row.get('phase_item_id'))
            self.refresh()

        def navigate():
            row = self.one()
            self.destroy()
            if row:
                actions.phase_to_plan(self.phase_no)
                self.dashboard.project_plan187._reveal(row['phase_item_id'])
            else:
                actions.phase_to_plan(self.phase_no)
            self.dashboard.lift()

        return popup_menu(self, event, [
            ('افزودن', self.add_item),
            ('کپی', lambda: actions._copy('plan', self.table.selected_rows())),
            ('پیست', paste), ('حذف', lambda: self.delete_item(self.one())),
            ('ویرایش', lambda: self.edit_item(self.one())), ('رفتن به پلان کلی', navigate),
        ])

class PriceEditor187(BarkavDialog):
    size_class = 'small'

    def __init__(self, parent, rich, row: dict | None, on_done, *, seed: dict | None = None):
        self.rich = rich
        self.row = dict(row or {})
        # A new price starts from what the caller knows - its category, and
        # the number it should take in the list it is being added to.
        self.seed = dict(seed or {})
        self.on_done = on_done
        super().__init__(parent, 'ویرایش قیمت' if row else 'افزودن قیمت')
        p = palette_187()
        body = tk.Frame(self.body, bg=p['panel'],
                        highlightbackground=p['border_subtle'], highlightthickness=1)
        body.pack(fill='both', expand=True)
        # The three rates are named as the reference workbook names them, and
        # in its order: برآورد اولیه, then بروز, then واقعی. The old labels
        # ('واقعی مرجع', 'پیش‌بینی') named the same two columns the other way
        # round from the table beside them.
        labels = [
            ('category', 'گروه قیمت'), ('code', 'شماره ردیف'), ('description', 'شرح'),
            ('unit', 'واحد'), ('estimate_rate', 'قیمت واحد برآورد'),
            ('forecast_rate', 'قیمت واحد بروز'), ('actual_rate', 'قیمت واحد واقعی'),
            ('source', 'فاز اجرا'),
        ]
        self.vars = {}
        for index, (key, label) in enumerate(labels):
            tk.Label(body, text=label, bg=p['panel'], fg=p['text'], anchor='e',
                     font=kit_font('small', bold=True)).grid(row=index, column=1, sticky='e', padx=8, pady=7)
            source_row = self.row or self.seed
            value = CATEGORY_LABELS_187.get(source_row.get(key), source_row.get(key, ''))
            variable = tk.StringVar(value=str(value or ''))
            self.vars[key] = variable
            if key == 'category':
                widget = ttk.Combobox(
                    body, textvariable=variable,
                    values=('مصالح', 'دستمزد/اجرا', 'اداری/خدمات', 'خرید زمین'),
                    state='readonly', justify='right', width=38,
                )
                if not variable.get():
                    variable.set('مصالح')
            elif key == 'source':
                # A price may serve several phases, so the list is a shortcut
                # rather than the only thing accepted: it stays typeable.
                widget = ttk.Combobox(body, textvariable=variable, values=self._phase_choices(),
                                      justify='right', width=38)
            else:
                widget = ttk.Entry(body, textvariable=variable, justify='right', width=40)
                if key in self.AMOUNTS:
                    variable.set(formatted_amount_input_187(variable.get()))
                    self._group_digits(variable, widget)
            widget.grid(row=index, column=0, sticky='ew', padx=8, pady=7)
        body.grid_columnconfigure(0, weight=1)
        # Section 10: the primary action lives in the window footer.
        self.add_action('ذخیره', self.save, style='Primary.TButton')
        if self.row:
            self.add_action('حذف ردیف', self.delete, style='Danger.TButton')
        self.add_action('انصراف', self.close)

    AMOUNTS = ('estimate_rate', 'forecast_rate', 'actual_rate')

    def _phase_choices(self) -> tuple[str, ...]:
        try:
            return tuple(f"{int(r['phase_no']):02d} — {r['phase']}"
                         for r in self.rich.list_phase_summary())
        except Exception:
            return ()

    def _group_digits(self, variable: tk.StringVar, entry) -> None:
        """Keep digit grouping and caret position after native insertion."""
        format_numeric_entry(entry, variable, formatted_amount_input_187)

    def delete(self):
        """Retire this price. Rows that reference it keep their own rate."""

        if not self.row:
            return
        try:
            deleted = _soft_delete_price(self, self.row)
        except Exception as exc:
            messagebox.showerror('قیمت', str(exc), parent=self)
            return
        if not deleted:
            return
        self.destroy()
        self.on_done()

    def save(self):
        try:
            data = {key: value.get().strip() for key, value in self.vars.items()}
            category = CATEGORY_CODES_187.get(data['category'])
            if not category:
                raise ValueError('گروه قیمت را انتخاب کنید.')
            if not data['description']:
                raise ValueError('شرح قیمت الزامی است.')
            rates = {key: max(0, parse_int(data[key])) for key in (
                'estimate_rate', 'actual_rate', 'forecast_rate',
            )}
            now = _now()
            if self.row:
                price_id = str(self.row['price_id'])
                before = self.rich.get_price(price_id) or {}
                with self.rich.db.tx() as connection:
                    connection.execute(
                        """UPDATE rich_price_items SET category=?,code=?,description=?,unit=?,
                           estimate_rate=?,actual_rate=?,forecast_rate=?,source=?,updated_at=? WHERE price_id=?""",
                        (category, data['code'], data['description'], data['unit'],
                         rates['estimate_rate'], rates['actual_rate'], rates['forecast_rate'],
                         data['source'] or 'GUI_18_7', now, price_id),
                    )
                    connection.execute(
                        'UPDATE rich_phase_items SET local_estimate_rate=?,local_actual_rate=?,updated_at=? WHERE price_id=?',
                        (rates['estimate_rate'], rates['actual_rate'], now, price_id),
                    )
                try:
                    self.rich._log('PRICE', price_id, 'UPDATE_18_7', before, self.rich.get_price(price_id) or {})
                except Exception:
                    pass
            else:
                price_id = 'PPRICE_' + uuid.uuid4().hex[:18].upper()
                with self.rich.db.tx() as connection:
                    connection.execute(
                        """INSERT INTO rich_price_items(
                           price_id,code,description,category,unit,estimate_rate,actual_rate,
                           forecast_rate,status,source,visible,aggregate,group_key,active,created_at,updated_at
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
                        (price_id, data['code'], data['description'], category, data['unit'],
                         rates['estimate_rate'], rates['actual_rate'], rates['forecast_rate'],
                         'MANUAL', data['source'] or 'GUI_18_7', 1, 0, '', now, now),
                    )
                try:
                    self.rich._log('PRICE', price_id, 'CREATE_18_7', {}, self.rich.get_price(price_id) or {})
                except Exception:
                    pass
            self.destroy()
            self.on_done()
        except Exception as exc:
            messagebox.showerror('قیمت', str(exc), parent=self)


class PriceCatalogDialog187(BarkavWindow):
    size_class = 'large'

    def __init__(self, parent, rich, on_refresh):
        self.rich = rich
        self.on_refresh = on_refresh
        super().__init__(parent, 'مدیریت کامل قیمت‌ها', subtitle='BARKAV 18.7',
                         show_footer=False)
        p = palette_187()
        bar = tk.Frame(self.body, bg=p['surface'],
                       highlightbackground=p['border_subtle'], highlightthickness=1)
        bar.pack(fill='x')
        self.category = tk.StringVar(value='همه')
        ttk.Combobox(bar, textvariable=self.category,
                     values=('همه', 'مصالح', 'دستمزد/اجرا', 'اداری/خدمات', 'خرید زمین'),
                     state='readonly', justify='right', width=20).pack(side='right', padx=7, pady=7)
        self.category.trace_add('write', lambda *_: self.refresh())
        gap = kit_metrics()['gap']
        for label, command, style in (
            ('افزودن قیمت', self.add, 'Success.TButton'),
            ('ویرایش', self.edit, 'Primary.TButton'),
            ('حذف', self.delete, 'Danger.TButton'),
        ):
            ttk.Button(bar, text=label, command=command, style=style).pack(
                side='left', padx=gap // 2, pady=gap)
        self.tree = ttk.Treeview(
            self.body, columns=('category', 'code', 'description', 'unit', 'estimate', 'actual', 'forecast', 'source'),
            show='headings', selectmode='browse', style='Barkav.Data.Treeview',
        )
        specs = [
            ('category', 'گروه', 135), ('code', 'کد', 90), ('description', 'شرح', 280),
            ('unit', 'واحد', 80), ('estimate', 'برآورد', 125), ('actual', 'واقعی', 125),
            ('forecast', 'پیش‌بینی', 125), ('source', 'منبع', 130),
        ]
        for key, label, width in specs:
            self.tree.heading(key, text=label, anchor='e')
            self.tree.column(key, width=width, anchor='e')
        apply_tree_rtl(self.tree)
        self.tree.pack(fill='both', expand=True, pady=(kit_metrics()['gap'], 0))
        self.tree.bind('<Double-1>', lambda _event: self.edit(), add='+')
        self.rows = []
        self.refresh()

    def refresh(self):
        wanted = CATEGORY_CODES_187.get(self.category.get())
        rows = list(self.rich.list_prices(category=wanted, visible_only=True))
        if self.category.get() in CATEGORY_CODES_187:
            rows = [row for row in rows if row.get('category') == wanted]
        elif self.category.get() == 'همه':
            rows = [row for row in rows if row.get('category') in {'MATERIAL', 'LABOR', 'SERVICE', 'LAND'}]
        self.rows = rows
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, row in enumerate(rows):
            self.tree.insert('', 'end', iid=str(index), values=(
                CATEGORY_LABELS_187.get(row.get('category'), row.get('category')),
                row.get('code') or '-', row.get('description') or '-', row.get('unit') or '-',
                fa(f"{int(row.get('estimate_rate') or 0):,}"),
                fa(f"{int(row.get('actual_rate') or 0):,}"),
                fa(f"{int(row.get('forecast_rate') or 0):,}"), row.get('source') or '-',
            ))

    def one(self):
        selected = self.tree.selection()
        if not selected:
            return None
        return self.rows[int(selected[0])]

    def add(self):
        PriceEditor187(self, self.rich, None, self._done)

    def edit(self):
        row = self.one()
        if row:
            PriceEditor187(self, self.rich, row, self._done)

    def delete(self):
        row = self.one()
        if not row:
            return
        try:
            deleted = _soft_delete_price(self, row)
        except Exception as exc:
            messagebox.showerror('قیمت', str(exc), parent=self)
            return
        if not deleted:
            return
        self._done()

    def _done(self):
        self.refresh()
        self.on_refresh()


def _selected_one(table):
    rows = table.selected_rows()
    return rows[0] if rows else None


def _soft_delete_price(parent, row) -> bool:
    """Retire a price row after one themed confirmation.

    ``parent`` only needs a ``.rich`` attribute - the dashboard, a price
    editor dialog and the catalogue window all have one. Each caller decides
    its own refresh afterward from the returned bool, rather than this
    function guessing which screen called it.
    """

    if not row:
        return False
    if not confirm(parent, 'حذف قیمت', f"«{row.get('description') or ''}» حذف شود؟"):
        return False
    before = dict(row)
    with parent.rich.db.tx() as connection:
        connection.execute('UPDATE rich_price_items SET active=0,updated_at=? WHERE price_id=?',
                           (_now(), row['price_id']))
    try:
        parent.rich._log('PRICE', row['price_id'], 'DELETE_18_7', before, {'active': 0})
    except Exception:
        pass
    return True


def _price_context_menu(app, event):
    tree = app.price_table.tree
    item = tree.identify_row(event.y)
    if item:
        if item not in tree.selection():tree.selection_set(item)
        tree.focus(item)
    p = palette_187()
    menu = tk.Menu(tree, tearoff=0, bg=p['surface'], fg=p['text_primary'])
    icon_size = 16

    def item_icon(name):
        return art.action_icon(name, size=icon_size, colour=p['text_primary'],
                               background=p['surface'], master=tree)

    def delete_selected():
        from table_actions import select_delete_rows,confirmed_delete,DeleteChoice
        rows=select_delete_rows(app,list(app.price_table.selected_rows() or []),messagebox=messagebox)
        if not rows:return
        with app.rich.db.atomic(),confirmed_delete(DeleteChoice()):
            for row in rows:_soft_delete_price(app,row)
        app.refresh_reports()

    for label, name, command in (
        ('افزودن قیمت', 'add', lambda: PriceEditor187(app, app.rich, None, app.refresh_reports)),
        ('ویرایش قیمت', 'edit', lambda: PriceEditor187(
            app, app.rich, _selected_one(app.price_table), app.refresh_reports
        ) if _selected_one(app.price_table) else None),
        ('حذف قیمت', 'delete', delete_selected),
    ):
        icon = item_icon(name)
        if icon is not None:
            menu.add_command(label=label, command=command, image=icon, compound='left')
        else:
            # Windows-only glyph font not found (e.g. off Windows) - the item
            # still works, just without its icon.
            menu.add_command(label=label, command=command)
    menu.add_separator()
    menu.add_command(label='📋 کپی', command=app.price_table.copy_selected)
    menu.add_command(label='📌 پیست در فیلتر', command=app.price_table.paste_filter)
    menu.add_command(label='مدیریت کامل قیمت‌ها', command=lambda: PriceCatalogDialog187(app, app.rich, app.refresh_reports))
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def open_estimate_file_187(app):
    version = app.SERVICE.budget.latest_version() if hasattr(app, 'SERVICE') else None
    if version is None:
        try:
            version = app._barkav_service_187.budget.latest_version()
        except Exception:
            version = None
    path = Path(str((version or {}).get('source_file') or app._barkav_base_187 / 'phase_budget_current.xlsx'))
    if not path.is_file():
        messagebox.showwarning('فایل برآورد', 'فایل منبع آخرین برآورد پیدا نشد.', parent=app)
        return
    try:
        modified = path.stat().st_mtime_ns
        os.startfile(str(path))
        app._estimate_watch_187 = {'path': path, 'mtime': modified, 'active': False}
        app.after(1800, lambda: app._estimate_watch_187.update(active=True))
    except Exception as exc:
        messagebox.showerror('فایل برآورد', str(exc), parent=app)


def import_overall_estimate_187(app):
    """Load the management workbook through its consolidated sheet only."""
    path = filedialog.askopenfilename(
        parent=app, title='انتخاب فایل مرجع مدیریت پروژه',
        filetypes=[('Excel Workbook', '*.xlsx')])
    if not path:
        return
    try:
        result = app.rich.import_workbook(path, 'برآورد کلی مدیریت پروژه',
                                          preserve_manual=False)
        _sync_price_update_187(app, path)
        _refresh_plan_187(app)
    except Exception as exc:
        messagebox.showerror('مدیریت پروژه', str(exc), parent=app)
        return
    messagebox.showinfo(
        'مدیریت پروژه',
        f'{fa(result.phase_count)} فاز و {fa(result.phase_item_count)} ردیف از شیت «براورد کلی» بروزرسانی شد.',
        parent=app,
    )


def check_estimate_file_187(app, _event=None):
    watch = getattr(app, '_estimate_watch_187', None)
    if not watch or not watch.get('active'):
        return
    path = Path(watch['path'])
    try:
        modified = path.stat().st_mtime_ns
    except Exception:
        return
    if modified == watch.get('mtime'):
        return
    watch['active'] = False
    watch['mtime'] = modified
    if not messagebox.askyesno(
        'بروزرسانی برآورد',
        'فایل اکسل تغییر کرده است. تغییرات به‌عنوان نسخهٔ جدید برآورد وارد شوند؟',
        parent=app,
    ):
        return
    try:
        title = 'ویرایش فایل برآورد — ' + datetime.now().strftime('%Y-%m-%d %H:%M')
        app._barkav_service_187.budget.import_budget_xlsx(path, title)
        rich_result = app.rich.import_workbook(path, title, preserve_manual=True)
        app._barkav_apply_phase04_187(app.rich)
        _sync_price_update_187(app, path)
        destination = app._barkav_base_187 / 'phase_budget_current.xlsx'
        if path.resolve() != destination.resolve():
            shutil.copy2(path, destination)
        app.refresh_reports()
        messagebox.showinfo(
            'بروزرسانی برآورد',
            f'نسخهٔ جدید ثبت شد؛ {fa(rich_result.phase_count)} فاز بروزرسانی شد.',
            parent=app,
        )
    except Exception as exc:
        messagebox.showerror('بروزرسانی برآورد', str(exc), parent=app)


def install_cost_group_column_187(app) -> None:
    """Show where each construction cost was filed, in the هزینه ساخت table.

    The entry form asks which of the plan's three sections a cost belongs to,
    and the program then reads the wording to decide which line of that
    section. Both answers belong in the table the cost lands in - otherwise
    the only way to see how a payment was filed is to reopen it, and a wrong
    guess sits there unnoticed while it quietly moves a plan total.
    """

    table = getattr(app, 'exp_table', None)
    if table is None or getattr(table, '_cost_group_column_187', False):
        return
    group_key, ref_key = '_cost_group187', '_plan_ref187'
    old_columns = list(table.columns)
    old_keys = [item[0] for item in old_columns]
    added = [(group_key, 'دسته‌بندی', 95), (ref_key, 'ردیف پلان', 195)]
    has_financial_row = bool(old_columns and old_columns[0][0] == 'row')
    if has_financial_row:
        # Keep the shared financial row marker as the first logical column;
        # business-only cost metadata follows it and remains on the RTL right.
        table.columns = [old_columns[0], *added, *old_columns[1:]]
        keys = (old_columns[0][0], group_key, ref_key, *old_keys[1:])
    else:
        table.columns = added + old_columns
        keys = (group_key, ref_key, *old_keys)
    table.tree.configure(columns=keys)
    for column, label, width in added:
        table.tree.heading(column, text=label, anchor='e')
        table.tree.column(column, width=width, minwidth=80, stretch=False, anchor='e')
    for column, label, width in old_columns:
        table.tree.heading(column, text=label, anchor='e')
        table.tree.column(column, width=width, anchor='e')
    table.tree.configure(displaycolumns=tuple(reversed(keys)))

    original = table.set_rows

    def set_rows_with_placement(rows, renderer):
        # Looked up once per redraw rather than once per row: the map is a
        # thousand lines long and the table is often the same length.
        labels = {}
        try:
            labels = plan_row_labels(app.rich.db)
        except Exception:
            pass

        def placement(row):
            ref = str(row.get('plan_ref') or '')
            if not ref:
                return '—'
            title = labels.get(ref)
            return f'{title} — {fa(ref)}' if title else fa(ref)

        if has_financial_row and getattr(renderer, '_barkav_financial_wrapper187', False):
            # The active dashboard renderer already contains the row marker;
            # do not prepend metadata a second time during filter redraws.
            result = original(rows, renderer)
        else:
            def render_with_placement(row):
                rendered = list(renderer(row) or ())
                if has_financial_row:
                    uid = str(table._row_uid(row))
                    checked = uid in getattr(table, '_barkav_checked_uids187', set())
                    marker = CHECKBOX_CHECKED if checked else CHECKBOX_UNCHECKED
                    marker = f"{marker} {fa(row.get('_ui_row_number187') or 0)}"
                    return [marker, str(row.get('cost_group') or '—'),
                            placement(row), *rendered]
                return [str(row.get('cost_group') or '—'),
                        placement(row), *rendered]

            if has_financial_row:
                render_with_placement._barkav_financial_wrapper187 = True
                render_with_placement._barkav_base_renderer187 = renderer

            result = original(rows, render_with_placement)
        # These two are the first columns, which in an RTL row means the
        # right-hand edge - and this table is wider than its pane, so it opens
        # showing the middle of a row unless it is parked where reading starts.
        # Once only: after that the view is wherever the operator left it.
        if not getattr(table, '_parked_right_187', False):
            table._parked_right_187 = True
            table.tree.after_idle(lambda: table.tree.xview_moveto(1.0))
        return result

    table.set_rows = set_rows_with_placement
    table._cost_group_column_187 = True
    try:
        app.refresh_all()
    except Exception:
        pass


def install_read_session_187(app) -> None:
    """Let a whole-window refresh share one database handle.

    A refresh reads a few hundred times, and each read used to open its own
    connection - five milliseconds each on this database, most of the seconds
    a refresh took. The reads are unchanged; only the handle is shared.
    """

    if getattr(app, '_read_session_187', False):
        return
    app._read_session_187 = True

    def sharing(name):
        original = getattr(app, name, None)
        if original is None:
            return

        def refresh_in_one_session():
            with app.rich.db.session():
                return original()

        setattr(app, name, refresh_in_one_session)

    for name in ('refresh_all', 'refresh_reports'):
        sharing(name)


def install_actual_cost_sync_187(app) -> None:
    """Total what was actually spent onto the plan whenever the reports redraw.

    A payment is filed against a plan line the moment it is saved; the line
    only shows it once someone adds the payments up. Doing that here means
    every screen reading the plan - the sheet, the three price tabs, the phase
    table - reports the same actuals as the transactions tab, and none of them
    has to know where the money came from.

    The totals are recomputed from scratch, never accumulated, so re-running
    this is free and a corrected assignment moves the money rather than
    duplicating it.
    """

    if getattr(app, '_actual_cost_sync_187', False):
        return
    app._actual_cost_sync_187 = True
    original = app.refresh_reports

    def refresh_with_actuals():
        try:
            changed = apply_actuals(app.rich.db)
            plan = getattr(app, 'project_plan187', None)
            plan_rows = project_actual_rows187(app.rich.all_phase_items())
            # Statements can change performed quantities and unit prices
            # without changing any posted cost. Compare the shared projection
            # too, so such edits and deletions cannot leave stale tables.
            if changed or plan is None or plan._cache != plan_rows:
                if plan is not None:
                    plan._cache = plan_rows
                    plan.refresh()
                for panel in getattr(app, 'price_panels187', {}).values():
                    panel.refresh(plan_rows=plan_rows)
        except Exception:
            logging.getLogger(__name__).exception('Could not synchronize project-plan actual costs')
        return original()

    app.refresh_reports = refresh_with_actuals


def install_project_plan_187(app) -> None:
    """Give مدیریت پروژه its plan sheet and its three price tabs.

    The inherited 'قیمت' tab was one table with a category dropdown; the three
    categories are three tabs now, so what you are looking at is named rather
    than remembered. The plan sheet takes the place the 'مدیریت کامل قیمت‌ها'
    button used to hold, as the tab furthest right - where reading starts.
    """

    notebook = app.report_nb
    tabs = {notebook.tab(tab_id, 'text'): tab_id for tab_id in notebook.tabs()}
    old_price = tabs.get('قیمت') or tabs.get('قیمت‌ها')
    if old_price is not None:
        notebook.forget(old_price)

    ensure_land_row_links(app.rich)
    app.price_panels187 = {}
    # Each is inserted at the front, so they are walked backwards to come out
    # in declared order - مصالح, پیمانکار, خدمات - reading right to left.
    for title, category in reversed(PRICE_TABS):
        panel = PricePanel187(
            notebook, rich=app.rich, category=category, title=title,
            on_add=lambda pane, seed=None: PriceEditor187(
                app, app.rich, None, lambda p=pane: (p.renumber(), _refresh_plan_187(app)),
                seed=seed),
            on_edit=lambda pane, row: PriceEditor187(app, app.rich, row,
                                                     lambda: _refresh_plan_187(app)),
            on_delete=lambda pane, row: (_soft_delete_price(app, row),
                                         _refresh_plan_187(app)),
        )
        notebook.insert(0, panel, text=title)
        app.price_panels187[category] = panel

    app.project_plan187 = ProjectPlanPanel187(
        notebook, rich=app.rich, on_changed=lambda: _refresh_plan_187(app))
    # Inserted last at position 0, so it ends up the first tab - and in an RTL
    # strip the first tab is the right-most one.
    notebook.insert(0, app.project_plan187, text=PLAN_TAB)
    notebook.select(0)
    app.project_table_actions187 = ProjectTableActions(app, lambda: _refresh_plan_187(app))
    app.project_plan187.row_actions = app.project_table_actions187
    for panel in app.price_panels187.values():
        panel.row_actions = app.project_table_actions187


def _sync_price_update_187(app, path=None) -> None:
    """Hand a newly loaded reference workbook to «بروزرسانی قیمت‌ها» as well.

    The budget import fills the plan's own tables; the price-update tab keeps
    its own catalog, روش‌ها, قوانین and پارامترها, which would otherwise go on
    showing the previous file's. ``path`` defaults to the workbook the last
    import recorded.
    """

    panel = getattr(app, 'price_update_panel187', None)
    if panel is None:
        return
    if path is None:
        path = panel.service.latest_reference_workbook()
    if path is not None:
        panel.sync_from_reference_workbook(path)


def _refresh_plan_187(app) -> None:
    plan = getattr(app, 'project_plan187', None)
    if plan is not None:
        # The rows were read once and kept; a new reference file replaces all
        # of them, so what was kept has to go.
        plan._cache = None
        plan.refresh()
    plan_rows = plan._all_rows() if plan is not None else project_actual_rows187(app.rich.all_phase_items())
    for panel in getattr(app, 'price_panels187', {}).values():
        panel.refresh(plan_rows=plan_rows)
    try:
        app.refresh_reports()
    except Exception:
        logging.getLogger(__name__).exception('Could not refresh reports after project-plan changes')


def install_budget_import_refresh_187(app) -> None:
    """Redraw the plan and the price tabs when a new reference file lands.

    ``import_budget`` predates these screens and only refreshed the ones that
    existed then, so a freshly imported workbook sat in the database while the
    plan went on showing the old one.
    """

    original = app.import_budget

    def import_and_refresh(*args, **kwargs):
        result = original(*args, **kwargs)
        ensure_land_row_links(app.rich)
        _sync_price_update_187(app)
        _refresh_plan_187(app)
        return result

    app.import_budget = import_and_refresh


def install_report_controls_187(app) -> None:
    if getattr(app, '_report_controls_installed_187', False):
        return
    app._report_controls_installed_187 = True
    install_checkbox_column_187(app.price_table)
    install_checkbox_column_187(app.phase_table)
    p = palette_187()

    install_project_plan_187(app)
    # Keep price updates isolated in their own tables and tab, alongside the
    # rest of project management (the legacy rich_price_items schema remains intact).
    from price_update_stage18_7 import install_price_update_187
    install_price_update_187(app)
    install_budget_import_refresh_187(app)
    install_cost_group_column_187(app)
    install_actual_cost_sync_187(app)
    # Installed last: it wraps whatever the others have already wrapped.
    install_read_session_187(app)

    # The phase table's actions sit in its own bar above the table, like
    # every tab's (operator round 2026-09-27: here they were under it); the
    # dashboard puts that bar in the shared toolbar's order and look.
    phase_bar = next(iter(app.phase_table.winfo_children()), None)
    if not isinstance(phase_bar, (tk.Frame, ttk.Frame)):
        phase_bar = tk.Frame(app.phase_table.master, bg=p['panel'])
        phase_bar.pack(side='top', fill='x', padx=4, pady=4, before=app.phase_table)
    for text, command, kind in [
        ('افزودن', lambda: app.open_phase_by_no(int((_selected_one(app.phase_table) or {'phase_no': 1})['phase_no'])), 'create'),
        ('ویرایش', lambda: app.open_phase_by_no(int((_selected_one(app.phase_table) or {'phase_no': 1})['phase_no'])), 'neutral'),
        ('کپی', app.phase_table.copy_selected, 'caution'),
        ('حذف', lambda: app.open_phase_by_no(int((_selected_one(app.phase_table) or {'phase_no': 1})['phase_no'])), 'destructive'),
    ]:
        ttk.Button(phase_bar, text=text, command=command,
                   style=ACTION_STYLES[kind]).pack(side='right', padx=3)

    _configure_phase_summary_table_187(app)
    app.phase_table.tree.unbind('<Button-3>')
    app.phase_table.tree.bind('<Button-3>', app.project_table_actions187.phase_menu)
    install_report_exports_187(app)

    app.price_table.tree.unbind('<Button-3>')
    app.price_table.tree.bind('<Button-3>', lambda event: _price_context_menu(app, event))

    _lift_estimate_bar_187(app)
    app.bind('<FocusIn>', lambda event: check_estimate_file_187(app, event), add='+')


def _lift_estimate_bar_187(app, attempt: int = 0) -> None:
    """Put the estimate-file controls on the row of the main tabs.

    They were a band of their own inside 'گزارش فازها', below a second band
    that only held an export dropdown. Two full-width bars stacked above the
    content pushed the tables down for no reading gained: the export band goes
    entirely, and the estimate controls move up onto the tab row, where they
    are on the same line as the tabs they belong to.
    """

    page = app.report_main.master
    bar = getattr(app, 'report_export_bar', None)
    if bar is not None and bar.winfo_exists():
        bar.destroy()
    # An 18.3 finaliser refills this bar from an idle callback, and the two
    # can run in either order. Clearing the attribute is what makes the
    # removal stick whichever way round they land.
    app.report_export_bar = None

    strip = next((child for child in page.winfo_children()
                  if isinstance(child, LegacyTabStrip)), None)
    old = next((child for child in app.report_nb.master.winfo_children()
                if isinstance(child, tk.Frame) and not isinstance(child, LegacyTabStrip)
                and any('برآورد' in str(w.cget('text'))
                        for w in child.winfo_children() if 'text' in w.keys())), None)
    if strip is None or old is None:
        # The RTL strip is installed by an inherited idle callback, so on the
        # first pass there is nothing to attach to yet.
        if attempt < 6:
            app.after(120, lambda: _lift_estimate_bar_187(app, attempt + 1))
        return
    # Tk cannot re-parent a widget, so the controls are rebuilt on the strip.
    # The band they came from is hidden rather than destroyed: inherited
    # finalisers still walk this page and would trip over a missing child.
    old.pack_forget()
    m = kit_metrics()
    # Two icon buttons with a hover hint instead of two long labels
    # (operator request, 2026-09-27); the hint says what each one does.
    # Glossy tiles like the rail's (2026-09-27 follow-up): a paper clip to
    # attach the estimate workbook, a spreadsheet page to open it.
    from barkav_ui.badges import glass_tile
    from barkav_ui.window import attach_tooltip
    p = palette_187()
    try:
        strip_bg = str(strip.cget('bg'))
    except tk.TclError:
        strip_bg = p['panel']
    style = ttk.Style(app)
    style.layout('EstimateTile.TButton', [('Button.padding', {'sticky': 'nsew', 'children': [
        ('Button.label', {'sticky': 'nsew'})]})])
    style.configure('EstimateTile.TButton', background=strip_bg, padding=1, borderwidth=0, relief='flat')
    style.map('EstimateTile.TButton', background=[('active', strip_bg), ('pressed', strip_bg)])
    for text, hint, icon_name, hue, command in (
        ('بارگذاری براورد کلی',
         'بارگذاری برآورد کلی: فایل اکسل برآورد را پیوست می‌کند و جدول‌ها را به‌روز می‌کند.',
         'attach', 'blue', lambda: import_overall_estimate_187(app)),
        ('باز کردن فایل برآورد',
         'باز کردن فایل برآورد: فایل اکسل برآوردِ ثبت‌شده را برای دیدن یا ویرایش باز می‌کند.',
         'sheet_file', 'green', lambda: open_estimate_file_187(app)),
    ):
        image = glass_tile(icon_name, size=24, colour=p.get(hue) or p['accent'], ink=p['on_accent'],
                           background=strip_bg, shadow=p['shadow'], master=app)
        button = ttk.Button(strip, command=command, style='EstimateTile.TButton', cursor='hand2')
        if image is not None:
            button.configure(image=image, compound='image')
            button.image = image
        else:
            button.configure(text=text, style='Toolbar.TButton')
        button.pack(side='left', padx=m['gap'] // 2)
        attach_tooltip(button, hint, delay_ms=300, side='below')
    tk.Label(strip, textvariable=app.budget_version, bg=palette_187()['panel'],
             fg=palette_187()['text_secondary'], font=kit_font('small')).pack(
                 side='left', padx=m['gap'])
