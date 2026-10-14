"""«بروزرسانی قیمت‌ها» sub-tab inside مدیریت پروژه.

Built strictly on the shared kit (``barkav_ui``), the same one
``barkav_ui/template_tab.py`` demonstrates -- never hand-styled. It covers: the
main catalog table (11 columns, checkbox rows, a real دسته‌بندی -> فاز cascading
filter whose second box offers only phases the chosen category has rows in),
افزودن/ویرایش/کپی/حذف on one row at a time, خروجی in three formats, و ویزارد
«شروع براورد» (تاریخ براورد با تقویم شمسی -> دامنه اجرا -> قوانین و جزئیات ->
پارامترها -> اجرا و خلاصه + لیست بررسی مجدد).

Two structural notes, both deliberate:
  * «قوانین بروزرسانی» و «جزئیات بروزرسانی» are reachable **both** from the
    wizard's own third step (where they belong in the run order: classify,
    then run) and from the action row. The wizard step is what the operator's
    spec asks for; the action-row buttons stay because both screens are also
    used on their own, with no run in progress -- opening a five-step wizard
    and stepping past two screens just to read جزئیات would be worse, and
    they are the same windows either way, not a second copy.
  * The date field uses ``sales_claims_stage18_7.ShamsiDatePicker187``, the
    picker the rest of the active layer already opens, rather than a second
    calendar of its own.

«جزئیات بروزرسانی» (the 20+ column per-row detail screen) is built as a
tab-local list + edit-dialog (`DetailsWindow187`/`DetailItemDialog187`) --
the same list+dialog shape every other editor in this codebase already uses
(`PriceEditor187`, `CalcRuleDialog187`), not a true inline-editable
spreadsheet cell-by-cell. `DataTable` genuinely cannot do inline per-cell
dropdowns/colour today; rather than block this tab on a new shared-kit
widget, a real one-off list+dialog ships now, and whether that capability is
worth generalizing into `barkav_ui` later is its own separate decision.

Deliberately NOT in this increment (flagged, not silently skipped):
  * The «قوانین بروزرسانی» editor picks روش محاسبه from a dropdown but still
    takes the numeric ضرایب as a JSON object; a dedicated weight-sliders form
    is a follow-up, not a blocker (the JSON is validated on save).
  * Live multi-engine AI web research for حداقل‌حقوق -- USD and مس both have
    verified deterministic sources wired ("دریافت خودکار از TGJU" in the run
    wizard's پارامترها step; مس is TGJU's London/USD-per-tonne copper series,
    a deliberate operator-confirmed departure from the Toman/kg domestic
    market the workbook originally described -- see price_index_fetch.py).
    حداقل‌حقوق is a once-a-year policy figure and stays manual.
    ``PriceUpdateService`` already has everywhere further automation plugs
    in (``save_parameter``).

"اعمال تغییرات به فایل مرجع" (bidirectional Excel round trip) is wired: the
export always writes a NEW timestamped xlsx (``PriceUpdateService.
export_reference_workbook``), never overwrites anything, and re-importing an
edited copy of it (or an app-created row's own unedited export) updates rows
in place by code/description rather than duplicating them.
"""

from __future__ import annotations

from report_document_stage18_7 import selected_table_rows

from datetime import datetime
import json
import logging
from pathlib import Path
from queue import Empty, Queue
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import jdatetime

from ui_stage18_3 import en, fa, parse_int, persianize_var
from barkav_ui.table import ACTION_STYLES, DataTable
from barkav_ui.theme import font, metrics, palette
from barkav_ui.window import BarkavDialog, BarkavWindow, BarkavWizard
from export_utils import export_pdf, export_xlsx, print_file
import price_ai_research as ai_research
import price_calc_engine as calc
import price_index_fetch as fetch_index

log = logging.getLogger(__name__)
from price_update_service import PriceUpdateService, _norm, normalize_phase_codes
from project_management_rules187 import MANAGEMENT_RULES
# The RTL Shamsi calendar this app already ships, rather than a second one:
# `sales_claims_stage18_7.ShamsiDatePicker187` is the active-layer picker every
# contract/payment date field opens (dashboard_stage18_7.WizardDateField187
# routes to the very same class), and it already draws from the shared kit
# palette. Import order is safe: reports_stage18_7 imports sales_claims before
# it imports this module, and sales_claims imports neither.
from sales_claims_stage18_7 import ShamsiDatePicker187

CATALOG_LABELS = {'MATERIAL': 'مصالح', 'CONTRACTOR': 'پیمانکار', 'SERVICE': 'خدمات', 'LAND': 'خرید زمین'}
CATALOG_VALUES = {label: value for value, label in CATALOG_LABELS.items()}

# The 32 phase names, exactly as the reference workbook's sheet tabs name
# them ("07-خاکی و تخریب" etc.) -- shown in filters/dropdowns as "07 - خاکی و تخریب".
PHASE_NAMES = {
    '01': 'خرید زمین', '02': 'مطالعات اولیه', '03': 'طراحی', '04': 'نظام مهندسی',
    '05': 'جواز', '06': 'تجهیز کارگاه', '07': 'خاکی و تخریب', '08': 'اسکلت',
    '09': 'چاه', '10': 'کف سازی', '11': 'شاسی آسانسور', '12': 'وال پست',
    '13': 'میلگرد بستر', '14': 'وال مش', '15': 'تیغه چینی', '16': 'تاسیسات',
    '17': 'عایق و بام', '18': 'چهارچوب و فریم', '19': 'شاسی نما', '20': 'آسانسور',
    '21': 'درب ضدسرقت', '22': 'کاشی و سنگ', '23': 'سقف کاذب', '24': 'گچکاری',
    '25': 'UPVC', '26': 'نرده و هندریل', '27': 'درب پارکینگ', '28': 'نقاشی',
    '29': 'درب اتاق', '30': 'انشعابات', '31': 'پایان کار', '32': 'سند و فروش',
}

ALL_LABEL = 'همه'

EXPORT_PLACEHOLDER = 'خروجی'
#: The same three outputs every other active screen offers, each opened first
#: in the shared RTL preview (``show_export_preview_187``) and only saved from
#: there. The main table's Excel is the round-trippable reference workbook
#: (``PriceUpdateService.export_reference_workbook``), so it can be edited and
#: re-imported.
EXPORT_FORMATS = {
    'PDF': ('.pdf', ('PDF', '*.pdf')),
    'Excel': ('.xlsx', ('Excel', '*.xlsx')),
    'پرینت': ('.pdf', ('PDF', '*.pdf')),
}

# جزئیات بروزرسانی -- روش‌های استخراج پیشنهادی/اجرایی، طبق دیکته‌ی عملیاتی
# اپراتور. METHOD_OTHER is always last -- an escape hatch for a method not
# yet in this list.
METHOD_OPTIONS = (
    calc.METHOD_WEB, calc.METHOD_PHASE_AVERAGE, calc.METHOD_PEER_AVERAGE,
    calc.METHOD_WEIGHTED_INDEX, calc.METHOD_SERVICE_TARIFF, calc.METHOD_OTHER,
)

# ضرایب ترکیبی وزنی -- هر ۷ زیرستون جدا (اپراتور صریحاً تأیید کرد: هر ۷ تا،
# نه فقط ۵ تا، حتی با اینکه فایل اکسل فعلی فقط ۴ ستون وزن واقعی دارد).
WEIGHT_KEYS = (
    ('dollar', 'دلار'), ('copper', 'مس'), ('inflation', 'تورم'),
    ('wage', 'حداقل حقوق'), ('adjustment', 'تعدیل'), ('steel', 'فولاد'), ('other', 'سایر'),
)

COLUMNS = (
    ('row', 'ردیف'),
    ('estimate_date', 'تاریخ براورد'),
    ('category', 'دسته‌بندی'),
    ('description', 'شرح'),
    ('unit', 'واحد'),
    ('estimate_rate', 'قیمت براورد اولیه'),
    ('previous_rate', 'قیمت براورد دوره قبل'),
    ('forecast_rate', 'قیمت براورد بروز'),
    ('pct_previous', 'درصد افزایش نسبت به دوره قبل'),
    ('pct_initial', 'درصد افزایش نسبت به قیمت اولیه'),
    ('phase', 'فاز ساخت'),
)


def _pct(new: float, base: float) -> str:
    if not base:
        return '-'
    return f"{fa(f'{(new / base - 1) * 100:.1f}')}٪"


def _phase_label(codes: str) -> str:
    first = (codes or '').split(',')[0].strip()
    if not first:
        return '-'
    return f"{fa(first)} - {PHASE_NAMES.get(first, '')}".rstrip(' -')


def _format_param_value(value: float) -> str:
    """Whole numbers show clean; anything with a fractional part keeps 2
    decimals -- ``:,.0f`` would otherwise round مس's 13269.60 to 13,270 on
    every redisplay, and re-saving that rounded text loses the cents for good."""

    if float(value).is_integer():
        return f'{value:,.0f}'
    return f'{value:,.2f}'


def _parse_param_float(raw: str) -> float:
    """Decimal-safe number parsing for the پارامترها step -- ``parse_int``
    strips "." entirely and would silently turn 13269.6 into 132696."""

    cleaned = re.sub(r'[^0-9.\-]', '', raw.replace(',', ''))
    try:
        return float(cleaned) if cleaned not in ('', '-', '.') else 0.0
    except ValueError:
        return 0.0


def _staleness_note(parameter: dict | None) -> tuple[str, bool]:
    """برای پارامترهایی بدون منبع خودکار: هشدار اگر بیش از یک سال بازبینی نشده باشند.

    این عدد سالی یک‌بار با مصوبه تغییر می‌کند، پس «بیش از یک سال» دقیقاً معنی
    «باید امسال را چک کنی» می‌دهد -- نه یک آستانه‌ی دلبخواه.
    """

    if not parameter or not parameter.get('updated_at'):
        return 'هنوز منبع خودکار تأییدشده ندارد -- ثبت نشده، دستی وارد کنید', True
    try:
        updated = datetime.fromisoformat(parameter['updated_at'])
    except ValueError:
        return 'هنوز منبع خودکار تأییدشده ندارد -- دستی وارد کنید', False
    days = (datetime.now() - updated).days
    if days > 365:
        return f'⚠ بیش از یک سال از آخرین بروزرسانی گذشته ({fa(days // 30)} ماه) -- بررسی کنید', True
    return f'آخرین بروزرسانی: {fa(days)} روز پیش (منبع خودکار ندارد)', False


def _app_settings() -> dict:
    """تنظیمات برنامه (قیمت دلار روز/مبنا) -- the fallback source for the dollar parameter."""

    try:
        from v18_store import load_ui
        return load_ui() or {}
    except Exception:
        log.exception('Reading the app settings for price-update defaults failed')
        return {}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _hint(parent: tk.Misc, text: str) -> None:
    """A secondary hint, one right-aligned line per sentence.

    Tk wraps a right-to-left run from the wrong end: an auto-wrapped Persian
    hint came out with its second line starting mid-word and glued onto the
    first. Breaking at sentence ends ourselves keeps every line whole.
    """

    p = palette()
    m = metrics()
    holder = tk.Frame(parent, bg=p['bg'])
    holder.pack(fill='x', pady=(0, m['gap']))
    for sentence in re.split(r'(?<=[.؛])\s+', text.strip()):
        if sentence:
            # Tk lays out a line's leading/trailing neutral characters (a «, a
            # final '.') on the wrong side, so hints never start with a quote
            # mark and lose their full stop.
            tk.Label(holder, text=sentence.rstrip('.'), bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                     anchor='e', justify='right').pack(fill='x')


def _parameter_source_note(parameter: dict | None) -> str:
    source = (parameter or {}).get('source') or ''
    return {
        'reference_workbook': 'منبع: شیت «پارامترها»ی فایل مرجع',
        'wizard': 'منبع: ویرایش در همین صفحه',
        'tgju': 'منبع: TGJU',
    }.get(source, '')


def _today_shamsi() -> str:
    d = jdatetime.date.today()
    return f'{d.year:04d}/{d.month:02d}/{d.day:02d}'


def shamsi_date_row(parent: tk.Misc, variable: tk.StringVar) -> tuple[tk.Frame, ttk.Entry, ttk.Button]:
    """A Shamsi date field: still typeable, plus the shared RTL calendar.

    The picker is :class:`ShamsiDatePicker187`, the one every other date field
    in the active layer opens -- not a second calendar built for this tab. The
    entry stays editable on purpose: the operator's spec calls this date
    «قابل ویرایش دستی», and a picker-only field would take that away.
    """

    p = palette()
    m = metrics()
    holder = tk.Frame(parent, bg=p['bg'])
    entry = ttk.Entry(holder, textvariable=variable, justify='right')
    button = ttk.Button(holder, text='تقویم', style='TableToolbar.TButton',
                        command=lambda: ShamsiDatePicker187(holder, variable))
    # RTL: the field itself starts at the right edge, the picker sits to its left.
    entry.pack(side='right', fill='x', expand=True)
    button.pack(side='left', padx=(m['gap'] // 2, 0))
    return holder, entry, button


def _ask_export_path(parent: tk.Misc, choice: str, default_name: str) -> str:
    extension, file_filter = EXPORT_FORMATS[choice]
    return filedialog.asksaveasfilename(
        parent=parent, title=f'خروجی {choice}', defaultextension=extension,
        initialfile=f'{default_name}{extension}', filetypes=[file_filter])


def add_export_control(table: DataTable, variable: tk.StringVar, command) -> ttk.Combobox:
    """«خروجی: خروجی» on the table toolbar's left, as on every other screen."""

    return table.toolbar.add_filter(None, variable, (EXPORT_PLACEHOLDER, *EXPORT_FORMATS),
                                    side='left', command=command)


def preview_export(parent: tk.Misc, variable: tk.StringVar, headers: list[str],
                   rows: list, title: str, *, summary_lines: list[str] | None = None,
                   excel_writer=None) -> None:
    """Open the shared RTL export preview for ``rows``; save only from its confirm.

    ``excel_writer(path)`` replaces the plain Excel table (the main catalog's
    Excel is the re-importable reference workbook instead).
    """

    choice = variable.get()
    variable.set(EXPORT_PLACEHOLDER)
    if choice not in EXPORT_FORMATS:
        return
    rows = [list(row) for row in rows]
    if not rows:
        messagebox.showinfo('خروجی', 'با این فیلترها ردیفی برای خروجی وجود ندارد.', parent=parent)
        return
    # A column that is '-' on every exported row (the ۷ وزن columns for مصالح,
    # say) only squeezes the columns that say something.
    keep = [index for index in range(len(headers))
            if any(str(row[index]).strip() not in ('', '-') for row in rows if index < len(row))]
    headers = [headers[index] for index in keep]
    rows = [[row[index] if index < len(row) else '' for index in keep] for row in rows]
    from sales_claims_stage18_7 import show_export_preview_187

    def save(selected: str, orientation: str | None = None,
             addressee: str = 'سایر', include_documents: bool = True) -> bool:
        destination = _ask_export_path(parent, selected if selected in EXPORT_FORMATS else 'PDF', title)
        if not destination:
            return False
        try:
            summary = [*(summary_lines or []), f'جهت ارائه به: {addressee}']
            if selected == 'Excel':
                if excel_writer is not None:
                    excel_writer(destination)
                else:
                    export_xlsx(destination, headers, rows, title=title,
                                summary_lines=summary)
            else:
                export_pdf(destination, headers, rows, title=title,
                           summary_lines=summary, orientation=orientation or 'افقی')
                if selected == 'پرینت':
                    print_file(destination)
        except Exception as exc:
            messagebox.showerror('خروجی', f'خروجی‌گیری ناموفق بود:\n{exc}', parent=parent)
            return False
        messagebox.showinfo('خروجی', f'فایل آماده شد:\n{destination}', parent=parent)
        return True

    show_export_preview_187(parent, export_format=choice, headers=headers, rows=rows,
                            title=f'پیش‌نمایش {title}', table_caption=title, row_label='ردیف',
                            on_confirm=save, include_addressee=True)


def phase_option_labels(service: PriceUpdateService, catalog_type: str | None) -> tuple[str, ...]:
    """«همه» + only the فازها ``catalog_type`` has rows in (the cascade's second box)."""

    return (ALL_LABEL, *[phase_label(code) for code in service.available_phase_codes(catalog_type)])


def phase_label(code: str | None) -> str:
    """«۰۸ - اسکلت» -- Persian digits, like every number on these screens."""

    if not code:
        return ALL_LABEL
    return fa(f'{code} - {PHASE_NAMES.get(code, "")}'.rstrip(' -'))


def phase_code_of(label: str) -> str | None:
    if label in ('', ALL_LABEL):
        return None
    return en(label.split(' - ', 1)[0]).strip() or None


def rtl_dropdown(combo: ttk.Combobox) -> ttk.Combobox:
    """Right-align a combobox's drop-down list, not just its entry.

    ``justify='right'`` only reaches the entry; the list Tk pops down is a
    separate listbox that stays left-aligned, which made a long Persian list
    of اقلام hard to scan.
    """

    try:
        popdown = combo.tk.eval(f'ttk::combobox::PopdownWindow {combo}')
        combo.tk.call(f'{popdown}.f.l', 'configure', '-justify', 'right')
    except tk.TclError:
        pass
    return combo


def item_option_map(service: PriceUpdateService, catalog_type: str | None,
                    phase_code: str | None) -> dict[str, str]:
    """{«08-تیرچه»: price_id} for the «قلم» boxes -- the item's فاز, then its name.

    Empty until a دسته‌بندی is chosen: a list of every item across all three
    catalogs is not something anyone scrolls. The فاز shown is the item's
    first one (the one «یکنواختی فاز» keys it by); two items that still read
    the same are told apart by their row number.
    """

    if catalog_type is None:
        return {}
    items = service.list_catalog_items(catalog_type=catalog_type, phase_code=phase_code)
    labels = []
    for item in items:
        first = (item['phase_codes'] or '').split(',')[0].strip()
        labels.append(fa(f"{first}-{item['description']}" if first else item['description']))
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    options: dict[str, str] = {}
    for label, item in zip(labels, items):
        if counts[label] > 1:
            label = fa(f"{label} (ردیف {item['code'] or item['price_id'][-4:]})")
        options[label] = item['price_id']
    return options


class _ScopeFilter:
    """«نمایش بر اساس: [دسته‌بندی] [فاز] [قلم]» -- the main table's cascade, for a window.

    Starts at whatever scope the caller passes (the run wizard hands over its
    «دامنه اجرا»; the main table's own buttons pass nothing, i.e. «همه»).
    """

    def __init__(self, owner, table: DataTable, service: PriceUpdateService, *,
                 category: str | None, phase: str | None, on_change, item: str | None = None) -> None:
        self.service = service
        self.on_change = on_change
        self.category_var = tk.StringVar(master=owner, value=CATALOG_LABELS.get(category or '', ALL_LABEL))
        self.phase_var = tk.StringVar(master=owner, value=phase_label(phase))
        self.item_var = tk.StringVar(master=owner, value=ALL_LABEL)
        self._item_ids: dict[str, str] = {}
        table.toolbar.add_filter('نمایش بر اساس', self.category_var, (ALL_LABEL, *CATALOG_LABELS.values()),
                                 command=self._category_changed)
        options = phase_option_labels(service, self.category)
        if self.phase_var.get() not in options:
            options = (*options, self.phase_var.get())
        self.phase_combo = table.toolbar.add_filter(None, self.phase_var, options,
                                                    command=self._phase_changed)
        self.item_combo = table.toolbar.add_filter(None, self.item_var, (ALL_LABEL,), width=26,
                                                   command=on_change)
        rtl_dropdown(self.phase_combo)
        rtl_dropdown(self.item_combo)
        self._reload_items()
        if item:
            label = next((key for key, value in self._item_ids.items() if value == item), None)
            if label:
                self.item_var.set(label)

    @property
    def item(self) -> str | None:
        return self._item_ids.get(self.item_var.get())

    def _reload_items(self) -> None:
        self._item_ids = item_option_map(self.service, self.category, self.phase)
        options = (ALL_LABEL, *self._item_ids)
        self.item_combo.configure(values=options, state='readonly' if self._item_ids else 'disabled')
        if self.item_var.get() not in options:
            self.item_var.set(ALL_LABEL)

    def _phase_changed(self) -> None:
        self._reload_items()
        self.on_change()

    @property
    def category(self) -> str | None:
        return CATALOG_VALUES.get(self.category_var.get())

    @property
    def phase(self) -> str | None:
        return phase_code_of(self.phase_var.get())

    def note(self) -> str:
        return (f'دسته‌بندی: {self.category_var.get()} — فاز: {self.phase_var.get()}'
                f' — قلم: {self.item_var.get()}')

    def _category_changed(self) -> None:
        options = phase_option_labels(self.service, self.category)
        self.phase_combo.configure(values=options)
        if self.phase_var.get() not in options:
            self.phase_var.set(ALL_LABEL)
        self._reload_items()
        self.on_change()


class PriceUpdatePanel187(ttk.Frame):
    """The single-page panel: toolbar (filters+export) + table + actions."""

    def __init__(self, parent: tk.Misc, *, service: PriceUpdateService,
                 rich_db=None, on_changed=None):
        super().__init__(parent, style='Panel.TFrame')
        self.service = service
        self.rich_db = rich_db
        self.on_changed = on_changed
        self.category_var = tk.StringVar(value=ALL_LABEL)
        self.phase_var = tk.StringVar(value=ALL_LABEL)
        self.output_format_var = tk.StringVar(value=EXPORT_PLACEHOLDER)
        self._latest_snapshot_estimate_date = ''
        self._build()

    # ------------------------------------------------------------------ ui

    def _build(self) -> None:
        m = metrics()
        self.table = DataTable(self, COLUMNS, on_open=self._open_selected_row,
                                empty_text='قلمی ثبت نشده است', checkable=True)
        self.table.pack(fill='both', expand=True, padx=m['outer_pad'], pady=m['outer_pad'])
        self.table.register_row_style('needs_review', background='row_pending')
        # ttk.Treeview defaults to reserving room for ~10 rows regardless of
        # actual content, which measured out taller than this tab's actual
        # available height and silently squeezed the action row (with every
        # button on it, including شروع براورد) to 0px -- confirmed via a
        # geometry diagnostic against the real dashboard, not a guess. The
        # table keeps its own scrollbar for more rows; this only bounds how
        # much height it claims by default so the action row always fits.
        self.table.tree.configure(height=8)

        # Row actions sit on the toolbar above the table, at its right edge
        # (the kit's section 4: "filters and row actions right"), ahead of the
        # «نمایش بر اساس» filter -- the same place the operator reaches for
        # them on the other management tabs. Packed right-to-left in call
        # order, so افزودن is the right-most and حذف the furthest in; each
        # keeps its create/neutral/caution/destructive colour from the kit.
        for text, command, kind in (
            ('افزودن', self.add_item, 'create'),
            ('ویرایش', self.edit_selected, 'neutral'),
            ('کپی', self.copy_selected, 'caution'),
            ('حذف', self.delete_selected, 'destructive'),
        ):
            button = self.table.add_tool(text, command)
            button.configure(style=ACTION_STYLES[kind])
        self.category_combo = self.table.toolbar.add_filter(
            'نمایش بر اساس', self.category_var, (ALL_LABEL, *CATALOG_LABELS.values()),
            command=self._category_changed)
        self.phase_combo = self.table.toolbar.add_filter(
            None, self.phase_var, self._phase_options(), command=self.refresh)
        add_export_control(self.table, self.output_format_var, self._export)

        # Keep the row CRUD actions above; move this tab's longer commands
        # below the table so they stay visible without duplicating handlers.
        self.table.add_bottom_action('شروع براورد', self.open_run_wizard, 'create')
        self.table.add_bottom_action('سابقه بروزرسانی', self.open_history, 'neutral')
        self.table.add_bottom_action('در دست بررسی', self.open_needs_review, 'neutral')
        self.table.add_bottom_action('جزئیات بروزرسانی', self.open_details, 'neutral')
        self.table.add_bottom_action('قوانین بروزرسانی', self.open_rules, 'neutral')
        self.table.add_bottom_action('اعمال تغییرات به فایل مرجع', self.export_to_reference_file, 'neutral')
        self._seed_from_project_price_list_if_empty()
        self._seed_from_reference_workbook_if_unclassified()
        self.refresh()

    def _seed_from_reference_workbook_if_unclassified(self) -> None:
        """Fill روش/ضرایب/قوانین/پارامترها from the project's reference workbook.

        A catalog seeded from the project's price list has prices but no روش
        محاسبه, no ضرایب and no قوانین -- «جزئیات بروزرسانی» and «قوانین
        بروزرسانی» opened empty and «شروع براورد» had nothing to run. The
        reference workbook the estimate was imported from carries all of it,
        so it is read once, while nothing is classified yet; after that the
        operator's own edits are never overwritten from here. Parameters are
        only filled where still empty (0).
        """

        workbook = self.service.latest_reference_workbook()
        try:
            if workbook is not None and not self.service.has_classified_rows():
                self.service.import_reference_workbook(workbook, import_parameters=False)
            elif workbook is not None and not self.service.list_calc_rules():
                self.service.import_reference_rules(workbook)
            self.service.ensure_parameter_defaults(workbook=workbook, settings=_app_settings())
        except Exception:
            log.exception('Seeding بروزرسانی قیمت‌ها from the reference workbook failed')

    def sync_from_reference_workbook(self, path) -> None:
        """A new reference workbook was loaded: take its rows, روش‌ها, rules and parameters."""

        try:
            self.service.import_reference_workbook(path)
            if self.rich_db is not None:
                with self.rich_db.tx() as con:
                    self.service.recompute_installation_groups(con, _now_iso())
        except Exception:
            log.exception('Syncing بروزرسانی قیمت‌ها with %s failed', path)
        self._category_changed()

    def _seed_from_project_price_list_if_empty(self) -> None:
        """First-ever open for a project: pull its existing rich_price_items in.

        price_catalog_items starts completely empty, and nothing short of a
        manual «افزودن» or an external Excel import ever put anything in it
        -- so on a real project whose price list was already entered through
        the budget/estimate tabs (hundreds of rows), «شروع براورد» had
        nothing to run against and the tab looked broken. Fires at most once
        per project -- only when the catalog is completely empty -- and
        never runs again afterward, so it can never silently overwrite
        anything the operator later adds, edits, or deletes by hand.
        """
        if self.service.list_catalog_items(active_only=False):
            return
        try:
            self.service.import_from_rich_price_items()
        except Exception:
            log.exception('Auto-seeding price_catalog_items from rich_price_items failed')

    def _phase_options(self) -> tuple[str, ...]:
        """Only the فازها the chosen دسته‌بندی actually has rows in.

        Listing all 32 phase names regardless of category is what made the
        second box decorative: most combinations selected nothing, and an
        empty table looks the same whether the filter found no rows or the
        data is missing. Asking the service keeps the two boxes one cascade.
        """

        return phase_option_labels(self.service, self._selected_category())

    def _category_changed(self) -> None:
        """Rebuild the فاز box for the new دسته‌بندی, then refresh.

        A phase still offered under the new category keeps its selection --
        resetting a filter the user did not touch would be its own surprise --
        but one the new category has no rows for falls back to «همه» rather
        than leaving a stale label above an empty table.
        """

        options = self._phase_options()
        self.phase_combo.configure(values=options)
        if self.phase_var.get() not in options:
            self.phase_var.set(ALL_LABEL)
        self.refresh()

    # --------------------------------------------------------------- data

    def _selected_category(self) -> str | None:
        label = self.category_var.get()
        return CATALOG_VALUES.get(label)

    def _selected_phase(self) -> str | None:
        return phase_code_of(self.phase_var.get())

    def refresh(self) -> None:
        rows = self.service.list_catalog_items(
            catalog_type=self._selected_category(), phase_code=self._selected_phase())
        self._rows_by_key = {r['price_id']: r for r in rows}
        display = []
        status = {}
        keys = []
        for index, r in enumerate(rows):
            display.append(_fa_row((
                fa(index + 1),
                self._latest_snapshot_estimate_date or '-',
                CATALOG_LABELS.get(r['catalog_type'], r['catalog_type']),
                r['description'],
                r['unit'] or '-',
                fa(f"{r['estimate_rate']:,}"),
                fa(f"{r['previous_rate']:,}"),
                fa(f"{r['forecast_rate']:,}"),
                _pct(r['forecast_rate'], r['previous_rate']),
                _pct(r['forecast_rate'], r['estimate_rate']),
                _phase_label(r['phase_codes']),
            )))
            if r['needs_review']:
                status[index] = 'needs_review'
            keys.append(r['price_id'])
        self.table.set_rows(display, status=status, keys=keys)

    def _selected_item(self) -> dict | None:
        key = self.table.selected_key()
        return self._rows_by_key.get(key) if key else None

    # ------------------------------------------------------------ actions

    def _open_selected_row(self, _iid: str) -> None:
        self.edit_selected()

    def add_item(self) -> None:
        PriceItemDialog187(self, self.service, None, on_saved=self._after_change)

    def edit_selected(self) -> None:
        item = self._selected_item()
        if not item:
            messagebox.showinfo('ویرایش', 'یک ردیف را انتخاب کنید.')
            return
        PriceItemDialog187(self, self.service, item, on_saved=self._after_change)

    def copy_selected(self) -> None:
        items=[self._rows_by_key[key] for key in self.table.selected_keys() if key in self._rows_by_key]
        if not items:
            messagebox.showinfo('کپی', 'یک ردیف را انتخاب کنید.')
            return
        with self.service.db.atomic():
            for item in items:self.service.copy_catalog_item(item['price_id'])
        self._after_change()

    def delete_selected(self) -> None:
        items=[self._rows_by_key[key] for key in self.table.selected_keys() if key in self._rows_by_key]
        if not items:
            messagebox.showinfo('حذف', 'یک ردیف را انتخاب کنید.')
            return
        from table_actions import select_delete_rows
        items=select_delete_rows(self,items,messagebox=messagebox)
        if not items:return
        with self.service.db.atomic():
            for item in items:self.service.soft_delete_catalog_item(item['price_id'])
        self._after_change()

    def _after_change(self) -> None:
        # A new/edited/deleted row can add or retire a فاز, so the cascade's
        # second box is rebuilt here too -- otherwise it keeps offering a phase
        # nothing is in any more, or misses one just created.
        self._category_changed()
        if self.on_changed:
            self.on_changed()

    def open_run_wizard(self) -> None:
        PriceUpdateRunWizard187(self, self.service, self.rich_db, on_done=self._after_run)

    def _after_run(self, result) -> None:
        self._latest_snapshot_estimate_date = result.estimate_date_shamsi
        self.refresh()
        if self.on_changed:
            self.on_changed()
        if result.review_count:
            self.open_needs_review()

    def open_rules(self) -> None:
        CalcRulesWindow187(self, self.service, on_applied=self._after_change)

    def open_details(self) -> None:
        DetailsWindow187(self, self.service, on_changed=self._after_change)

    def open_needs_review(self) -> None:
        NeedsReviewWindow187(self, self.service)

    def open_history(self) -> None:
        SnapshotHistoryWindow187(self, self.service)

    def export_to_reference_file(self) -> None:
        """«اعمال تغییرات به فایل مرجع» -- writes a NEW xlsx, never overwrites anything."""

        try:
            out_path = self.service.export_reference_workbook()
        except Exception as exc:
            messagebox.showerror('اعمال تغییرات به فایل مرجع', f'خروجی‌گیری ناموفق بود:\n{exc}')
            return
        messagebox.showinfo(
            'اعمال تغییرات به فایل مرجع',
            f'یک فایل اکسل جدید ساخته شد (فایل مرجع قبلی دست‌نخورده ماند):\n{out_path}',
        )

    def _scope_note(self) -> str:
        category = self.category_var.get()
        phase = self.phase_var.get()
        return f'دسته‌بندی: {category} — فاز ساخت: {phase}'

    def _export(self) -> None:
        """«خروجی» -- Excel / PDF / پرینت of exactly what the table shows, via the shared preview.

        Excel is written by :meth:`PriceUpdateService.export_reference_workbook`
        rather than as the visible cells, so an exported xlsx is the real
        currently visible catalog rows so the saved PDF, Excel sheet and print
        all contain the same rows shown in the preview.
        """

        preview_export(
            self, self.output_format_var, [label for _key, label in COLUMNS], selected_table_rows(self.table),
            'بروزرسانی قیمت‌ها', summary_lines=[self._scope_note()])


class PriceItemDialog187(BarkavDialog):
    """افزودن/ویرایش یک قلم -- فیلدهای پایه؛ روش محاسبه در نسخه بعدی گسترش می‌یابد."""

    size_class = 'small'

    def __init__(self, parent: tk.Misc, service: PriceUpdateService, row: dict | None, *, on_saved):
        self.service = service
        self.row = row
        self.on_saved = on_saved
        super().__init__(parent, 'ویرایش قلم' if row else 'افزودن قلم')
        self._render()

    def _render(self) -> None:
        p = palette()
        m = metrics()
        grid = tk.Frame(self.body, bg=p['bg'])
        grid.pack(fill='both', expand=True)
        grid.columnconfigure((0, 1), weight=1, uniform='field')

        row = self.row or {}
        self.vars = {
            'description': tk.StringVar(value=row.get('description', '')),
            'catalog_type': tk.StringVar(value=CATALOG_LABELS.get(row.get('catalog_type', 'MATERIAL'))),
            'unit': tk.StringVar(value=row.get('unit', '')),
            'estimate_rate': tk.StringVar(value=fa(f"{row.get('estimate_rate', 0):,}")),
            'phase_codes': tk.StringVar(value=row.get('phase_codes', '')),
            'brand': tk.StringVar(value=row.get('brand', '')),
        }
        fields = (
            ('description', 'شرح', 'entry'),
            ('catalog_type', 'دسته‌بندی', 'combo'),
            ('unit', 'واحد', 'entry'),
            ('estimate_rate', 'قیمت براورد اولیه', 'entry'),
            ('phase_codes', 'کد فاز (مثال: 08 یا 07,09)', 'entry'),
            ('brand', 'برند', 'entry'),
        )
        for index, (key, label, kind) in enumerate(fields):
            cell = tk.Frame(grid, bg=p['bg'])
            cell.grid(row=index // 2, column=1 - (index % 2), sticky='ew', padx=m['gap'] // 2, pady=m['gap'] // 2)
            tk.Label(cell, text=label, bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                     anchor='e').pack(fill='x')
            if kind == 'combo':
                ttk.Combobox(cell, textvariable=self.vars[key], values=tuple(CATALOG_LABELS.values()),
                             state='readonly', justify='right').pack(fill='x')
            else:
                ttk.Entry(cell, textvariable=self.vars[key], justify='right').pack(fill='x')

        self.add_action('ذخیره', self._save, style='Success.TButton')
        self.add_action('انصراف', self.close)

    def _save(self) -> None:
        description = self.vars['description'].get().strip()
        if not description:
            messagebox.showwarning('ذخیره', 'شرح نمی‌تواند خالی باشد.', parent=self)
            return
        fields = dict(
            description=description,
            catalog_type=CATALOG_VALUES.get(self.vars['catalog_type'].get(), 'MATERIAL'),
            unit=self.vars['unit'].get().strip(),
            estimate_rate=parse_int(en(self.vars['estimate_rate'].get())),
            phase_codes=self.vars['phase_codes'].get().strip(),
            brand=self.vars['brand'].get().strip(),
        )
        price_id = self.row['price_id'] if self.row else None
        self.service.upsert_catalog_item(price_id, **fields)
        self.on_saved()
        self.close()


# Step indices for ``PriceUpdateRunWizard187.show_step()`` -- named rather
# than hardcoded at each call site, so a test or a future caller jumping
# straight to «پارامترها» does not silently point at the wrong screen if a
# step is ever inserted/reordered (``step_titles`` on the class is the single
# source of truth these mirror).
DATE_STEP_187 = 0
SCOPE_STEP_187 = 1
RULES_STEP_187 = 2
PARAMETERS_STEP_187 = 3
AI_STEP_187 = 4
SUMMARY_STEP_187 = 5

#: Where secrets.local.json lives -- the same keys the receipt reader uses.
AI_BASE_DIR = Path(__file__).resolve().parent

#: The macro parameters step ۵ can research, in the order they are asked.
AI_PARAMETER_LABELS = {'usd': 'نرخ دلار آزاد', 'copper': 'قیمت مس',
                       'wage_annual_growth': 'رشد سالانه حداقل حقوق'}

#: A researched value further than this from the entered one is flagged.
AI_DIFFERENCE_WARNING = 0.10

AI_MODEL_COLUMNS = (('row', 'ردیف'), ('label', 'مدل'), ('provider', 'سرویس'),
                    ('role', 'کاربرد'), ('cost', 'هزینه'), ('status', 'وضعیت'))
AI_RESULT_COLUMNS = (('parameter', 'پارامتر'), ('entered', 'مقدار واردشده (بروز)'),
                     ('found', 'مقدار هوش مصنوعی'), ('difference', 'اختلاف'),
                     ('check', 'صحت‌سنجی'), ('source', 'منبع'))


def _shamsi_months_between(start: str, end: str) -> int | None:
    """Whole months from one «۱۴۰۵/۰۲/۱۰» date to another, or None if either is unreadable."""

    try:
        first = jdatetime.date(*(int(x) for x in en(start).strip().split('/')))
        last = jdatetime.date(*(int(x) for x in en(end).strip().split('/')))
    except (TypeError, ValueError):
        return None
    months = (last.year - first.year) * 12 + (last.month - first.month)
    if last.day < first.day:
        months -= 1
    return months


class PriceUpdateRunWizard187(BarkavWizard):
    """«شروع براورد»: تاریخ براورد ← دامنه اجرا ← قوانین و جزئیات ← پارامترها ← اجرا و خلاصه.

    «دامنه اجرا» تعیین می‌کند کدام دسته‌بندی/فاز پردازش شود (پیش‌فرض: همه)، و
    «قوانین و جزئیات» همان دو صفحه‌ی «قوانین بروزرسانی» و «جزئیات بروزرسانی» را
    به‌عنوان بخشی از خود فرآیند اجرا در دسترس می‌گذارد -- چون ترتیب درست کار این
    است: اول قانون‌ها اعمال شوند، بعد اجرا؛ قلمی که روش محاسبه ندارد در اجرا
    دست‌نخورده می‌ماند.
    """

    size_class = 'large'
    step_titles = ('تاریخ براورد', 'دامنه اجرا', 'قوانین و جزئیات', 'پارامترها', 'مدل هوش مصنوعی',
                   'اجرا و خلاصه')

    #: هر پارامتر کلان سه مقدار دارد (مشخصات اپراتور): اولیه (مبنای برآورد، که
    #: نسبت رشد از آن گرفته می‌شود)، قبلی (ماه گذشته، فقط برای مقایسه) و بروز
    #: (مقدار این ماه، که در محاسبه اعمال می‌شود).
    PARAMETER_SUB_FIELDS = (
        ('base', 'اولیه'),
        ('previous', 'قبلی'),
        ('current', 'بروز'),
    )

    #: (key, label, auto_fetch) -- auto_fetch is a zero-arg callable returning
    #: (value, timestamp), or None when no verified live source exists yet.
    # A lambda, not the bound function itself: this module's test suite (and
    # the existing fetch_tgju_usd_toman tests elsewhere in the app) override
    # fetch functions by patching the *module attribute*
    # (``price_index_fetch.fetch_usd_toman = ...``); binding the function
    # object directly into this tuple at import time would freeze the
    # original and silently ignore that override.
    PARAMETER_FIELDS = (
        ('usd', 'نرخ دلار آزاد (تومان)', lambda: fetch_index.fetch_usd_toman()),
        # USD/tonne, London copper (TGJU base_global_copper) -- NOT
        # Toman/kg domestic بورس کالا; see price_index_fetch.py's module
        # docstring for why. Valid because only the current/base RATIO is
        # ever consumed, and both readings always come from this same series.
        # The reference workbook states مس in تومان/کیلوگرم (بورس کالا), so a
        # value fetched from TGJU in دلار/تن is converted with this screen's
        # own دلار بروز before it lands beside a تومان/کیلوگرم اولیه -- only
        # the current/base ratio is ever used, and it is only meaningful when
        # both sides are in the same unit (see _copper_in_stored_unit).
        ('copper', 'قیمت مس کاتد (تومان/کیلوگرم؛ یا دلار/تن اگر مبنا دلاری است)',
         lambda: fetch_index.fetch_copper_usd_per_ton()),
        # No automated source: mcls.gov.ir (وزارت کار، رشد حداقل حقوق) is
        # simply unreachable from this network (a real connection timeout,
        # not a page-structure problem -- confirmed 2026-09-23), and the rate
        # only changes once a year by decree anyway, so a manual field with a
        # staleness warning is the deliberate fallback, not a stopgap.
        ('wage_annual_growth', 'نرخ افزایش سالانه حداقل حقوق (کسر یا درصد؛ مثال: 0.6 یا 60)', None),
        # پارامترها!B11 of the workbook: رشد حداقل حقوق compounds over it.
        ('months_elapsed', 'ماه‌های سپری‌شده از مبنای برآورد', None),
    )

    def __init__(self, parent: tk.Misc, service: PriceUpdateService, rich_db, *, on_done):
        self.service = service
        self.rich_db = rich_db
        self.on_done = on_done
        self.date_var = tk.StringVar(value=_today_shamsi())
        persianize_var(self.date_var)
        self.category_var = tk.StringVar(value=ALL_LABEL)
        self.phase_var = tk.StringVar(value=ALL_LABEL)
        self.phase_combo: ttk.Combobox | None = None
        #: «قلم» -- one item of the chosen دسته‌بندی/فاز, or «همه».
        self.item_var = tk.StringVar(value=ALL_LABEL)
        self.item_combo: ttk.Combobox | None = None
        self._item_ids: dict[str, str] = {}
        #: ``{parameter key: {'base'|'previous'|'current': StringVar}}``
        self.param_vars: dict[str, dict[str, tk.StringVar]] = {}
        self._result = None
        settings = _app_settings()
        mode = str(settings.get('price_ai_mode') or ai_research.DEFAULT_PRICE_AI_MODE).upper()
        self.ai_mode_var = tk.StringVar(value=ai_research.PRICE_AI_MODES.get(
            mode, ai_research.PRICE_AI_MODES[ai_research.DEFAULT_PRICE_AI_MODE]))
        self._ai_chosen: list[str] = [str(x) for x in (settings.get('price_ai_models') or [])]
        self._ai_catalog: list = []
        self._ai_status: dict[str, str] = {}
        self._ai_results: dict[str, object] = {}
        self._ai_errors: dict[str, str] = {}
        self._ai_applied: list[str] = []
        self._ai_busy = False
        self._ai_syncing = False
        # Every parameter still at 0 is filled before the screen opens -- from
        # the reference workbook's «پارامترها», then the app's own تنظیمات --
        # so the operator reviews numbers instead of typing them from scratch.
        try:
            service.ensure_parameter_defaults(workbook=service.latest_reference_workbook(),
                                              settings=_app_settings())
        except Exception:
            log.exception('Filling price-update parameter defaults failed')
        super().__init__(parent, 'شروع براورد')

    # ------------------------------------------------------------ RTL chrome

    def _build_progress(self) -> None:
        """The kit's progress strip, laid out right-to-left for this Persian wizard.

        Same pieces and tokens as ``BarkavWizard._build_progress`` -- the
        count, the bar and the step host -- but the count and bar start at the
        right edge, and the current step's name reads beside them, so the
        header begins where every other line on the screen does.
        """

        p = palette()
        m = metrics()
        self.progress_bar = tk.Frame(
            self.body, bg=p['panel'], highlightbackground=p['border_subtle'], highlightthickness=1)
        self.progress_bar.pack(fill='x', pady=(0, m['gap']))
        gauge = tk.Frame(self.progress_bar, bg=p['panel'])
        gauge.pack(side='right', padx=m['outer_pad'], pady=m['gap'])
        self._progress_label = tk.Label(
            gauge, bg=p['panel'], fg=p['text_secondary'], font=font('small'), anchor='e')
        self._progress_label.pack(anchor='e')
        self._progress_track = tk.Frame(gauge, bg=p['surface_alt'], height=6, width=220)
        self._progress_track.pack(anchor='e', pady=(3, 0))
        self._progress_track.pack_propagate(False)
        self._progress_fill = tk.Frame(self._progress_track, bg=p['accent'])
        # The bar fills from the right, like the text it sits under.
        self._progress_fill.place(relx=1.0, y=0, anchor='ne', relheight=1, relwidth=0)
        self._step_title_label = tk.Label(
            self.progress_bar, bg=p['panel'], fg=p['text_primary'], font=font('title'), anchor='e')
        self._step_title_label.pack(side='right', padx=(0, m['gap']))

        self.step_host = tk.Frame(self.body, bg=p['bg'])
        self.step_host.pack(fill='both', expand=True)

    def _sync_navigation(self) -> None:
        super()._sync_navigation()
        if 0 <= self._step < len(self.step_titles):
            self._step_title_label.configure(text=self.step_titles[self._step])

    # ------------------------------------------------------------ scope

    def selected_category(self) -> str | None:
        return CATALOG_VALUES.get(self.category_var.get())

    def selected_phase(self) -> str | None:
        return phase_code_of(self.phase_var.get())

    def phase_options(self) -> tuple[str, ...]:
        return phase_option_labels(self.service, self.selected_category())

    def _scope_category_changed(self) -> None:
        options = self.phase_options()
        if self.phase_combo is not None:
            self.phase_combo.configure(values=options)
        if self.phase_var.get() not in options:
            self.phase_var.set(ALL_LABEL)
        self._scope_items_changed()

    def selected_item(self) -> str | None:
        """The one قلم to update, or ``None`` for every item of the scope."""

        return self._item_ids.get(self.item_var.get())

    def item_options(self) -> tuple[str, ...]:
        """«همه» + every item of the chosen دسته‌بندی (and فاز), as «08-تیرچه»."""

        self._item_ids = item_option_map(self.service, self.selected_category(), self.selected_phase())
        return (ALL_LABEL, *self._item_ids)

    def _scope_items_changed(self) -> None:
        options = self.item_options()
        if self.item_combo is not None and self.item_combo.winfo_exists():
            self.item_combo.configure(values=options,
                                      state='readonly' if len(options) > 1 else 'disabled')
        if self.item_var.get() not in options:
            self.item_var.set(ALL_LABEL)

    def scope_items(self) -> list[dict]:
        """The items this run will write: the chosen قلم, or the whole دسته‌بندی/فاز."""

        item_id = self.selected_item()
        if item_id:
            item = self.service.get_catalog_item(item_id)
            return [item] if item and item['active'] else []
        return self.service.list_catalog_items(catalog_type=self.selected_category(),
                                               phase_code=self.selected_phase())

    # ------------------------------------------------------------ steps

    def render_step(self, index: int, parent: tk.Frame) -> None:
        p = palette()
        m = metrics()
        if index == 0:
            tk.Label(parent, text='تاریخ براورد (شمسی، قابل ویرایش دستی یا از تقویم)', bg=p['bg'],
                     fg=p['text_primary'], font=font('title'), anchor='e').pack(fill='x', pady=(0, m['gap']))
            holder, self.date_entry, self.date_button = shamsi_date_row(parent, self.date_var)
            holder.pack(fill='x')
            return
        if index == 1:
            self._render_scope_step(parent, p, m)
            return
        if index == 2:
            self._render_rules_step(parent, p, m)
            return
        if index == 3:
            self._render_parameters_step(parent, p, m)
            return
        if index == AI_STEP_187:
            self._render_ai_step(parent, p, m)
            return
        tk.Label(parent, text='خلاصه اجرا', bg=p['bg'], fg=p['text_primary'], font=font('title'),
                 anchor='e').pack(fill='x', pady=(0, m['gap']))
        # validate_step(AI_STEP_187) has already run by the time the last step renders
        # (it is what let the wizard advance), so the real summary is ready here.
        text = self._summary_text if self._result is not None else 'در حال محاسبه...'
        tk.Label(parent, text=text, bg=p['bg'], fg=p['text_secondary'],
                 anchor='e', justify='right').pack(fill='x')

    def _render_scope_step(self, parent: tk.Frame, p: dict, m: dict) -> None:
        """دامنه اجرا -- کدام دسته‌بندی و کدام فاز در این اجرا پردازش شود."""

        tk.Label(parent, text='دامنه اجرا', bg=p['bg'], fg=p['text_primary'], font=font('title'),
                 anchor='e').pack(fill='x', pady=(0, m['gap']))
        _hint(parent, 'در حالت پیش‌فرض همه اقلام بازمحاسبه می‌شوند. '
                      'با انتخاب دسته‌بندی، فاز یا یک قلم، فقط همان بازمحاسبه و ثبت می‌شود و بقیه ثابت است')
        grid = tk.Frame(parent, bg=p['bg'])
        grid.pack(fill='x')
        grid.columnconfigure((0, 1, 2), weight=1, uniform='scope')

        category_cell = tk.Frame(grid, bg=p['bg'])
        category_cell.grid(row=0, column=2, sticky='ew', padx=m['gap'] // 2)
        tk.Label(category_cell, text='دسته‌بندی', bg=p['bg'], fg=p['text_secondary'],
                 font=font('small'), anchor='e').pack(fill='x')
        category_combo = ttk.Combobox(
            category_cell, textvariable=self.category_var,
            values=(ALL_LABEL, *CATALOG_LABELS.values()), state='readonly', justify='right')
        category_combo.pack(fill='x')
        category_combo.bind('<<ComboboxSelected>>', lambda _e: self._scope_category_changed(), add='+')
        self.category_combo = category_combo

        phase_cell = tk.Frame(grid, bg=p['bg'])
        phase_cell.grid(row=0, column=1, sticky='ew', padx=m['gap'] // 2)
        tk.Label(phase_cell, text='فاز ساخت', bg=p['bg'], fg=p['text_secondary'],
                 font=font('small'), anchor='e').pack(fill='x')
        self.phase_combo = ttk.Combobox(
            phase_cell, textvariable=self.phase_var, values=self.phase_options(),
            state='readonly', justify='right')
        self.phase_combo.pack(fill='x')
        self.phase_combo.bind('<<ComboboxSelected>>', lambda _e: self._scope_items_changed(), add='+')

        item_cell = tk.Frame(grid, bg=p['bg'])
        item_cell.grid(row=0, column=0, sticky='ew', padx=m['gap'] // 2)
        tk.Label(item_cell, text='قلم (مصالح / پیمانکار / خدمات)', bg=p['bg'], fg=p['text_secondary'],
                 font=font('small'), anchor='e').pack(fill='x')
        self.item_combo = ttk.Combobox(item_cell, textvariable=self.item_var, state='readonly',
                                       justify='right', height=20)
        self.item_combo.pack(fill='x')
        rtl_dropdown(self.item_combo)
        rtl_dropdown(self.phase_combo)
        self._scope_items_changed()

        self.scope_count_label = tk.Label(parent, bg=p['bg'], fg=p['text_secondary'],
                                           font=font('small'), anchor='e')
        self.scope_count_label.pack(fill='x', pady=(m['gap'], 0))
        self._refresh_scope_count()
        # Traces live on the StringVar, not on the widget, so they survive this
        # step being re-rendered (going back and forward re-runs render_step and
        # would otherwise stack a duplicate trace per visit).
        if not getattr(self, '_scope_traced', False):
            self._scope_traced = True
            for variable in (self.category_var, self.phase_var, self.item_var):
                variable.trace_add('write', lambda *_a: self._refresh_scope_count())

    def _refresh_scope_count(self) -> None:
        """تعداد اقلام دامنه‌ی فعلی -- قبل از اجرا، نه بعد از آن.

        بدون این عدد، انتخاب دسته‌بندی/فازی که هیچ قلمی ندارد تا مرحله‌ی خلاصه
        معلوم نمی‌شود و کاربر یک اجرای خالی را به‌حساب اجرای موفق می‌گذارد.
        """

        label = getattr(self, 'scope_count_label', None)
        if label is None or not label.winfo_exists():
            return
        label.configure(text=f'اقلام در این دامنه: {fa(len(self.scope_items()))}')

    def _render_rules_step(self, parent: tk.Frame, p: dict, m: dict) -> None:
        """قوانین و جزئیات -- همان دو صفحه، این بار داخل خود فرآیند اجرا."""

        tk.Label(parent, text='قوانین و جزئیات بروزرسانی', bg=p['bg'], fg=p['text_primary'],
                 font=font('title'), anchor='e').pack(fill='x', pady=(0, m['gap']))
        _hint(parent, 'قلمی که روش محاسبه ندارد در اجرا دست‌نخورده می‌ماند. پیش از ادامه، قوانین را '
                      'اعمال کنید یا روش هر قلم را در «جزئیات بروزرسانی» تنظیم کنید. این مرحله '
                      'اختیاری است و می‌توانید بدون تغییر رد شوید.')

        self.unclassified_label = tk.Label(parent, bg=p['bg'], fg=p['text_secondary'],
                                           font=font('small'), anchor='e', justify='right')
        self.unclassified_label.pack(fill='x', pady=(0, m['gap']))
        self._refresh_unclassified_note()

        buttons = tk.Frame(parent, bg=p['bg'])
        buttons.pack(fill='x')
        ttk.Button(buttons, text='قوانین بروزرسانی', style='Primary.TButton',
                   command=self._open_rules).pack(side='right', padx=(0, m['gap'] // 2))
        ttk.Button(buttons, text='جزئیات بروزرسانی', style='Primary.TButton',
                   command=self._open_details).pack(side='right', padx=(0, m['gap'] // 2))

    def _refresh_unclassified_note(self) -> None:
        label = getattr(self, 'unclassified_label', None)
        if label is None or not label.winfo_exists():
            return
        p = palette()
        items = self.scope_items()
        unclassified = sum(1 for item in items if not item['calc_method'])
        if unclassified:
            label.configure(
                text=f'⚠ {fa(unclassified)} قلم از {fa(len(items))} قلم این دامنه هنوز روش محاسبه '
                     'ندارد و در اجرا بازمحاسبه نمی‌شود.',
                fg=p['danger'])
        else:
            label.configure(text=f'همه‌ی {fa(len(items))} قلم این دامنه روش محاسبه دارند.',
                             fg=p['text_secondary'])

    def _open_rules(self) -> None:
        # Opened from the run, the window starts at the run's own «دامنه اجرا».
        CalcRulesWindow187(self, self.service, on_applied=self._refresh_unclassified_note,
                           category=self.selected_category(), phase=self.selected_phase(),
                           item=self.selected_item())

    def _open_details(self) -> None:
        DetailsWindow187(self, self.service, on_changed=self._refresh_unclassified_note,
                         category=self.selected_category(), phase=self.selected_phase(),
                         item=self.selected_item())

    def _render_parameters_step(self, parent: tk.Frame, p: dict, m: dict) -> None:
        """هر پارامتر با سه فیلد: اولیه / قبلی / بروز.

        اولیه مبناییست که نسبت رشد از آن گرفته می‌شود، قبلی فقط برای مقایسه ثبت
        می‌شود و بروز مقداریست که در محاسبه‌ی این ماه اعمال می‌گردد. سه فیلد جدا
        لازم است چون با یک فیلد، ثبت مقدار این ماه مبنای برآورد را هم جابه‌جا
        می‌کرد و نسبت رشد هر ماه از صفر شروع می‌شد.
        """

        tk.Label(parent, text='پارامترهای کلان — اولیه / قبلی / بروز', bg=p['bg'],
                 fg=p['text_primary'], font=font('title'), anchor='e').pack(fill='x', pady=(0, m['gap']))
        _hint(parent, 'مقدار «اولیه» مبنای نسبت رشد است، «بروز» مقدار این ماه که اعمال می‌شود و «قبلی» فقط برای مقایسه')
        # The ratios the stored values give, each its own label: one mixed
        # Persian/number line with separators gets reordered by the bidi
        # algorithm into an unreadable jumble.
        growth = self.service.growth_context()
        ratios = tk.Frame(parent, bg=p['bg'])
        ratios.pack(fill='x', pady=(0, m['gap']))
        for caption, key in (('رشد دلار', 'usd'), ('رشد مس', 'copper'), ('رشد حداقل حقوق (مرکب)', 'wage')):
            tk.Label(ratios, text=f"{caption}: {fa(f'{growth[key]:.3f}')}", bg=p['bg'],
                     fg=p['text_primary'], font=font('small')).pack(side='right', padx=(m['gap'], 0))
        for key, label, auto_fetch in self.PARAMETER_FIELDS:
            stored = self.service.get_parameter(key)
            row = tk.Frame(parent, bg=p['bg'])
            row.pack(fill='x', pady=m['gap'] // 2)
            tk.Label(row, text=label, bg=p['bg'], fg=p['text_primary'], font=font('small'),
                     anchor='e').pack(fill='x')
            fields = tk.Frame(row, bg=p['bg'])
            fields.pack(fill='x')
            fields.columnconfigure((0, 1, 2), weight=1, uniform='param')
            variables = self.param_vars.setdefault(key, {})
            for offset, (field, field_label) in enumerate(self.PARAMETER_SUB_FIELDS):
                cell = tk.Frame(fields, bg=p['bg'])
                # RTL: اولیه right-most, then قبلی, then بروز.
                cell.grid(row=0, column=2 - offset, sticky='ew', padx=m['gap'] // 2)
                tk.Label(cell, text=field_label, bg=p['bg'], fg=p['text_secondary'],
                         font=font('small'), anchor='e').pack(fill='x')
                variable = variables.get(field)
                if variable is None:
                    stored_value = stored[f'{field}_value'] if stored else 0
                    variable = tk.StringVar(
                        value=fa(_format_param_value(stored_value)) if stored else '')
                    variables[field] = variable
                ttk.Entry(cell, textvariable=variable, justify='right').pack(fill='x')
            tools = tk.Frame(row, bg=p['bg'])
            tools.pack(fill='x', pady=(m['gap'] // 2, 0))
            source = _parameter_source_note(stored)
            if source:
                tk.Label(tools, text=source, bg=p['bg'], fg=p['text_secondary'],
                         font=font('small')).pack(side='right')
            if auto_fetch is not None:
                ttk.Button(tools, text='دریافت خودکار «بروز» از TGJU',
                           command=lambda k=key, v=variables['current'], f=auto_fetch:
                               self._auto_fetch(k, v, f),
                           style='TableToolbar.TButton').pack(side='right', padx=(0, m['gap']))
            elif key == 'wage_annual_growth':
                note, is_stale = _staleness_note(stored)
                tk.Label(tools, text=note, bg=p['bg'],
                         fg=(p['danger'] if is_stale else p['text_secondary']),
                         font=font('small')).pack(side='right', padx=(0, m['gap']))
            elif key == 'months_elapsed':
                suggestion = self.suggested_months_elapsed()
                if suggestion is not None:
                    months, since = suggestion
                    tk.Label(tools, text=f'پیشنهاد: {fa(months)} ماه', bg=p['bg'],
                             fg=p['text_primary'], font=font('small')).pack(side='right')
                    tk.Label(tools, text=f'(آخرین اجرا {fa(since)})', bg=p['bg'],
                             fg=p['text_secondary'], font=font('small')).pack(
                                 side='right', padx=(m['gap'] // 2, 0))
                    ttk.Button(tools, text='اعمال پیشنهاد', style='TableToolbar.TButton',
                               command=lambda v=variables['current'], n=months: v.set(fa(n))).pack(
                                   side='right', padx=(m['gap'], 0))

    def suggested_months_elapsed(self) -> tuple[int, str] | None:
        """«ماه‌های سپری‌شده» carried forward from the last run, or None.

        رشد حقوق روی همین عدد مرکب می‌شود و دستی ماندنش یعنی هر ماه که فراموش
        شود رشد حقوق ثابت می‌ماند. پیشنهاد = ماه‌های ثبت‌شده در آخرین اجرا +
        فاصله‌ی تاریخ آن اجرا تا تاریخ براورد همین اجرا. فقط وقتی نشان داده
        می‌شود که تاریخ جلو رفته و پیشنهاد از مقدار فعلی بیشتر باشد.
        """

        for snapshot in self.service.list_snapshots():
            date = str(snapshot.get('estimate_date_shamsi') or '').strip()
            if not date:
                continue
            try:
                params = json.loads(snapshot.get('parameters_json') or '{}')
            except (TypeError, ValueError):
                return None
            gap = _shamsi_months_between(date, self.date_var.get())
            if not gap or gap < 0 or 'months_elapsed' not in params:
                return None
            months = int(round(float(params['months_elapsed']))) + gap
            current = self.service.get_parameter('months_elapsed')
            # Time only moves forward: a figure the operator already raised
            # past this one is not second-guessed.
            if current and int(round(float(current['current_value'] or 0))) >= months:
                return None
            return months, date
        return None


    def _auto_fetch(self, key: str, variable: tk.StringVar, fetcher) -> None:
        try:
            value, _timestamp = fetcher()
        except Exception as exc:
            messagebox.showwarning('دریافت خودکار', f'دریافت خودکار ناموفق بود:\n{exc}', parent=self)
            return
        if key == 'copper':
            value = self._copper_in_stored_unit(value)
            if value is None:
                return
        variable.set(fa(_format_param_value(value)))

    def _copper_in_stored_unit(self, usd_per_ton: float) -> float | None:
        """TGJU's دلار/تن, in whatever unit this project's مس اولیه is kept.

        A مبنا of 100,000 or more can only be تومان/کیلوگرم (London copper has
        never been near 100,000 دلار/تن), so the fetched figure is converted
        with the دلار بروز on this same screen: تن -> کیلوگرم is ÷1000. A
        dollar-per-tonne مبنا takes the figure as fetched.
        """

        variables = self.param_vars.get('copper', {})
        base = _parse_param_float(en(variables['base'].get())) if 'base' in variables else 0.0
        if base < 100_000:
            return usd_per_ton
        usd_vars = self.param_vars.get('usd', {})
        usd = _parse_param_float(en(usd_vars['current'].get())) if 'current' in usd_vars else 0.0
        if usd <= 0:
            messagebox.showwarning(
                'دریافت خودکار',
                'مبنای مس به تومان/کیلوگرم است؛ برای تبدیل قیمت دلاری TGJU، اول «بروز» دلار را وارد کنید.',
                parent=self)
            return None
        return usd_per_ton * usd / 1000.0

    def _save_parameters(self) -> None:
        for key, _label, _fetch in self.PARAMETER_FIELDS:
            variables = self.param_vars.get(key)
            if not variables:
                continue
            raw = {field: en(variables[field].get()).strip()
                   for field, _label in self.PARAMETER_SUB_FIELDS if field in variables}
            if not any(raw.values()):
                continue
            # All three are passed explicitly, even the untouched ones: with
            # only current_value, save_parameter() deliberately shifts the old
            # بروز into قبلی, which would overwrite whatever the operator just
            # typed into the قبلی field on this very screen.
            stored = self.service.get_parameter(key) or {}
            # parse_int() strips "." entirely (132696 instead of 13269.6) --
            # fine for whole-toman دلار, silently corrupts مس's decimal price
            # by ~10x. Every macro parameter here is stored as REAL.
            values = {
                field: (_parse_param_float(raw[field]) if raw.get(field)
                        else float(stored.get(f'{field}_value') or 0))
                for field, _label in self.PARAMETER_SUB_FIELDS
            }
            self.service.save_parameter(
                key, base_value=values['base'], previous_value=values['previous'],
                current_value=values['current'], source='wizard')

    # ------------------------------------------------------------ AI models

    def ai_mode(self) -> str:
        labels = {label: key for key, label in ai_research.PRICE_AI_MODES.items()}
        return labels.get(self.ai_mode_var.get(), ai_research.DEFAULT_PRICE_AI_MODE)

    def ai_selected(self) -> list[str]:
        """The engine ids this run uses: the mode's pick, or the operator's ticks."""

        return ai_research.resolve_selection(self.ai_mode(), self._ai_catalog, self._ai_chosen)

    def _render_ai_step(self, parent: tk.Frame, p: dict, m: dict) -> None:
        """مدل هوش مصنوعی -- کدام مدل‌ها پارامترهای کلان را استعلام و صحت‌سنجی کنند."""

        tk.Label(parent, text='انتخاب مدل هوش مصنوعی', bg=p['bg'], fg=p['text_primary'],
                 font=font('title'), anchor='e').pack(fill='x', pady=(0, m['gap']))
        # «جمینای», not the Latin name: a Latin word inside a Persian line
        # makes Tk reorder the whole line.
        _hint(parent, 'فقط جمینای به وب دسترسی زنده دارد و عدد را پیدا می‌کند. '
                      'بقیه مدل‌ها فقط درستی همان عدد را می‌سنجند و هر مخالفتی علامت بررسی می‌گیرد')

        top = tk.Frame(parent, bg=p['bg'])
        top.pack(fill='x', pady=(0, m['gap']))
        tk.Label(top, text='نحوه انتخاب مدل', bg=p['bg'], fg=p['text_secondary'],
                 font=font('small')).pack(side='right')
        self.ai_mode_combo = ttk.Combobox(top, textvariable=self.ai_mode_var, state='readonly',
                                          justify='right', width=52,
                                          values=tuple(ai_research.PRICE_AI_MODES.values()))
        self.ai_mode_combo.pack(side='right', padx=(m['gap'] // 2, 0))
        rtl_dropdown(self.ai_mode_combo)
        self.ai_mode_combo.bind('<<ComboboxSelected>>', lambda _e: self._ai_mode_changed(), add='+')
        self.ai_count_label = tk.Label(top, bg=p['bg'], fg=p['text_secondary'], font=font('small'))
        self.ai_count_label.pack(side='left')

        self._ai_catalog = ai_research.model_catalog(AI_BASE_DIR)
        self.ai_table = DataTable(parent, AI_MODEL_COLUMNS, checkable=True,
                                  empty_text='مدلی تعریف نشده است')
        self.ai_table.pack(fill='both', expand=True)
        self.ai_table.add_tool('بررسی اتصال', self._check_ai_status)
        self.ai_table.tree.configure(height=6)
        self.ai_table.tree.bind('<<TreeviewSelect>>', lambda _e: self._ai_ticks_changed(), add='+')

        self.ai_results_table = DataTable(parent, AI_RESULT_COLUMNS,
                                          empty_text='هنوز استعلامی انجام نشده است')
        self.ai_results_table.pack(fill='both', expand=True, pady=(m['gap'], 0))
        self.ai_results_table.tree.configure(height=3)
        # On the toolbar, not under the table: a step this tall has no room left below it.
        self.ai_research_button = self.ai_results_table.add_tool(
            'استعلام پارامترها با هوش مصنوعی', self._start_ai_research)
        self.ai_research_button.configure(style=ACTION_STYLES['create'])
        self.ai_results_table.add_tool('اعمال مقدار ردیف انتخاب‌شده', self._apply_ai_result).configure(
            style=ACTION_STYLES['neutral'])
        self.ai_note_label = tk.Label(parent, bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                                      anchor='e', text='نتیجه‌ی استعلام فقط پیشنهاد است و با دکمه‌ی اعمال ثبت می‌شود')
        self.ai_note_label.pack(fill='x', pady=(m['gap'] // 2, 0))
        self._refresh_ai_models()
        self._refresh_ai_results()

    def _ai_status_text(self, info) -> tuple[str, str]:
        if not info.active:
            return 'غیرفعال (کلید ندارد)', 'rejected'
        state = self._ai_status.get(info.engine_id)
        if state == 'ok':
            return 'فعال — اتصال برقرار', 'approved'
        if state == 'error':
            return 'فعال — خطای اتصال', 'pending'
        if state == 'checking':
            return 'در حال بررسی...', 'pending'
        return 'فعال', 'approved'

    def _refresh_ai_models(self) -> None:
        table = getattr(self, 'ai_table', None)
        if table is None or not table.winfo_exists():
            return
        rows, status, keys = [], {}, []
        for index, info in enumerate(self._ai_catalog):
            text, tint = self._ai_status_text(info)
            # The model name stays Latin: «gemini-۳٫۱» reads as neither.
            rows.append((fa(index + 1), info.label, info.provider, ai_research.ROLE_LABELS[info.role],
                         'رایگان' if info.free else 'پولی', text))
            status[index] = tint
            keys.append(info.engine_id)
        self._ai_syncing = True
        try:
            table.set_rows(rows, status=status, keys=keys)
            self._show_ai_ticks()
        finally:
            self._ai_syncing = False
        self._refresh_ai_count()

    def _show_ai_ticks(self) -> None:
        """Tick exactly the engines this run will use."""

        chosen = set(self.ai_selected())
        tree = self.ai_table.tree
        order = [key for _row, _state, key in self.ai_table._sorted()]
        iids = tree.get_children()
        tree.selection_set([iid for iid, key in zip(iids, order) if key in chosen])
        self.ai_table._mark_selection()

    def _refresh_ai_count(self) -> None:
        label = getattr(self, 'ai_count_label', None)
        if label is None or not label.winfo_exists():
            return
        selected = self.ai_selected()
        search = sum(1 for m in self._ai_catalog
                     if m.engine_id in selected and m.role == ai_research.ROLE_SEARCH)
        label.configure(text=f'انتخاب‌شده: {fa(len(selected))} مدل ({fa(search)} جستجو)')

    def _ai_mode_changed(self) -> None:
        if self.ai_mode() == 'SELECTED' and not self._ai_chosen:
            # Start the manual pick from what the automatic mode would use.
            self._ai_chosen = ai_research.resolve_selection('AUTO', self._ai_catalog, [])
        self._refresh_ai_models()

    def _ai_ticks_changed(self) -> None:
        """A tick the operator makes switches to «فقط مدل‌های انتخاب‌شده».

        Inactive engines cannot be ticked -- they have no key to call with.
        """

        if self._ai_syncing:
            return
        active = {m.engine_id for m in self._ai_catalog if m.active}
        ticked = [key for key in self.ai_table.selected_keys() if key in active]
        if ticked == self.ai_selected():
            return
        self._ai_chosen = ticked
        self.ai_mode_var.set(ai_research.PRICE_AI_MODES['SELECTED'])
        self.after_idle(self._refresh_ai_models)

    def _check_ai_status(self) -> None:
        """Each engine's key authenticated with a models-list call (no tokens spent)."""

        for info in self._ai_catalog:
            if info.active:
                self._ai_status[info.engine_id] = 'checking'
        self._refresh_ai_models()
        results: Queue = Queue()

        def job():
            try:
                results.put(ai_research.check_status(AI_BASE_DIR))
            except Exception as exc:
                log.exception('Checking AI engine status failed')
                results.put(exc)

        threading.Thread(target=job, name='barkav-price-ai-status', daemon=True).start()
        self._poll(results, self._status_checked)

    def _status_checked(self, outcome) -> None:
        if isinstance(outcome, Exception):
            self._ai_status = {}
            messagebox.showwarning('بررسی اتصال', f'بررسی اتصال انجام نشد:\n{outcome}', parent=self)
        else:
            self._ai_status = {key: value for key, value in outcome.items() if value != 'no_key'}
        self._refresh_ai_models()

    def _poll(self, results: Queue, done) -> None:
        try:
            outcome = results.get_nowait()
        except Empty:
            if self.winfo_exists():
                self.after(250, lambda: self._poll(results, done))
            return
        if self.winfo_exists():
            done(outcome)

    def _start_ai_research(self) -> None:
        selected = self.ai_selected()
        grounded, checkers = ai_research.build_clients(AI_BASE_DIR, selected)
        if grounded is None:
            messagebox.showwarning(
                'هوش مصنوعی', 'برای استعلام دست‌کم یک مدل Gemini فعال باید انتخاب شود.', parent=self)
            return
        self._ai_busy = True
        self.ai_research_button.configure(state='disabled')
        self.ai_note_label.configure(text='در حال استعلام از هوش مصنوعی...')
        results: Queue = Queue()

        def job():
            found, errors = {}, {}
            for key, (prompt, context) in ai_research.RESEARCH_PROMPTS.items():
                try:
                    found[key] = ai_research.fetch_and_verify(
                        prompt, context, gemini_client=grounded, sanity_clients=checkers)
                except Exception as exc:
                    errors[key] = str(exc)
            results.put((found, errors))

        threading.Thread(target=job, name='barkav-price-ai-research', daemon=True).start()
        self._poll(results, self._research_done)

    def _research_done(self, outcome) -> None:
        self._ai_busy = False
        found, errors = outcome
        if 'copper' in found:
            # LME دلار/تن, in the project's own copper unit (same as TGJU's).
            converted = self._copper_in_stored_unit(found['copper'].value)
            if converted is None:
                errors['copper'] = 'تبدیل واحد مس بدون «بروز» دلار ممکن نیست'
                del found['copper']
            else:
                found['copper'].value = converted
        self._ai_results, self._ai_errors = found, errors
        if self.ai_research_button.winfo_exists():
            self.ai_research_button.configure(state='normal')
            self._refresh_ai_results()

    @staticmethod
    def _as_fraction(key: str, value: float) -> float:
        return value / 100.0 if key == 'wage_annual_growth' and value > 1 else value

    def _refresh_ai_results(self) -> None:
        table = getattr(self, 'ai_results_table', None)
        if table is None or not table.winfo_exists():
            return
        rows, status, keys = [], {}, []
        for key, label in AI_PARAMETER_LABELS.items():
            stored = self.service.get_parameter(key)
            entered = float(stored['current_value'] or 0) if stored else 0.0
            result = self._ai_results.get(key)
            if result is None and key not in self._ai_errors:
                continue
            if result is None:
                rows.append((label, fa(_format_param_value(entered)), '—', '—', 'خطا',
                             self._ai_errors[key][:80]))
                status[len(rows) - 1] = 'rejected'
                keys.append(None)
                continue
            base = self._as_fraction(key, entered)
            value = self._as_fraction(key, result.value)
            gap = (value - base) / base if base else 0.0
            checks = [c for c in result.sanity_checks if c.plausible is not None]
            check_text = (result.review_reason or
                          (f'تأیید {fa(len(checks))} مدل' if checks else 'بدون صحت‌سنجی'))
            source = result.source_urls[0] if result.source_urls else 'بدون منبع'
            rows.append((label, fa(_format_param_value(entered)), fa(_format_param_value(result.value)),
                         (fa(f'{gap * 100:+.1f}') + '٪') if base else '—', check_text, source))
            if result.needs_review:
                status[len(rows) - 1] = 'rejected'
            elif base and abs(gap) > AI_DIFFERENCE_WARNING:
                status[len(rows) - 1] = 'pending'
            keys.append(key)
        table.set_rows(rows, status=status, keys=keys)
        if self._ai_results or self._ai_errors:
            self.ai_note_label.configure(
                text=f'اختلاف بیش از {fa(int(AI_DIFFERENCE_WARNING * 100))}٪ زرد و عدم توافق مدل‌ها قرمز است')

    def _apply_ai_result(self) -> None:
        key = self.ai_results_table.selected_key()
        result = self._ai_results.get(key) if key else None
        if result is None:
            messagebox.showinfo('اعمال', 'یک ردیف با مقدار هوش مصنوعی انتخاب کنید.', parent=self)
            return
        stored = self.service.get_parameter(key) or {}
        value = result.value
        if key == 'wage_annual_growth' and 0 < float(stored.get('current_value') or 0) <= 1:
            value = self._as_fraction(key, value)   # kept the way the operator enters it
        if result.needs_review and not messagebox.askyesno(
                'اعمال', f'{result.review_reason}\nبا این حال اعمال شود؟', parent=self):
            return
        self.service.save_parameter(
            key, base_value=float(stored.get('base_value') or 0),
            previous_value=float(stored.get('previous_value') or 0),
            current_value=value, source='ai')
        variables = self.param_vars.get(key, {})
        if 'current' in variables:
            variables['current'].set(fa(_format_param_value(value)))
        if key not in self._ai_applied:
            self._ai_applied.append(key)
        self._refresh_ai_results()

    def _remember_ai_choice(self) -> None:
        """The next «شروع براورد» opens on the same mode and ticks."""

        try:
            from v18_store import load_ui, save_ui
            data = load_ui()
            data['price_ai_mode'] = self.ai_mode()
            data['price_ai_models'] = list(self._ai_chosen)
            save_ui(data)
        except Exception:
            log.exception('Saving the price-update AI choice failed')

    def validate_step(self, index: int) -> bool:
        if index == 0:
            if not self.date_var.get().strip():
                messagebox.showwarning('تاریخ براورد', 'تاریخ براورد را وارد کنید.', parent=self)
                return False
            return True
        if index == 1:
            if not self.scope_items():
                messagebox.showwarning(
                    'دامنه اجرا',
                    'در این دسته‌بندی/فاز قلمی ثبت نشده است؛ دامنه را تغییر دهید.', parent=self)
                return False
            self._refresh_unclassified_note()
            return True
        if index == PARAMETERS_STEP_187:
            self._save_parameters()
            return True
        if index == AI_STEP_187:
            if self._ai_busy:
                messagebox.showinfo('هوش مصنوعی', 'استعلام هنوز در حال اجراست؛ کمی صبر کنید.',
                                    parent=self)
                return False
            self._remember_ai_choice()
            self._result = self.service.run_update(
                trigger='manual', estimate_date_shamsi=en(self.date_var.get().strip()),
                catalog_type=self.selected_category(), phase_code=self.selected_phase(),
                price_id=self.selected_item())
            if self.rich_db is not None:
                self.service.sync_forecast_to_rich(self.rich_db)
            self._summary_text = (
                f"دامنه: دسته‌بندی {self.category_var.get()} — فاز {self.phase_var.get()}"
                f" — قلم {self.item_var.get()}\n"
                f"تعداد کل اقلام: {fa(self._result.item_count)}\n"
                f"بازمحاسبه‌شده: {fa(self._result.recalculated_count)}\n"
                f"نیازمند بررسی مجدد: {fa(self._result.review_count)}\n"
                f"هوش مصنوعی: {self.ai_mode_var.get()}"
                + (f" — اعمال‌شده: {'، '.join(AI_PARAMETER_LABELS[k] for k in self._ai_applied)}"
                   if self._ai_applied else '')
            )
        return True

    def finish(self) -> None:
        if self._result is not None:
            self.on_done(self._result)
        self.close()


RULE_COLUMNS = (
    ('row', 'ردیف'), ('updated_at', 'آخرین ویرایش'), ('catalog_type', 'دسته‌بندی'),
    ('description', 'موضوع'), ('method', 'روش محاسبه'),
    ('affected_phase_codes', 'فاز'), ('params', 'قانون / پارامترها'),
)

#: A rule imported from the workbook's general sections governs all three
#: catalogs and is stored as ``ALL``.
RULE_CATALOG_LABELS = {**CATALOG_LABELS, 'ALL': 'همه دسته‌ها'}

#: Key prefix of the synthesized «قانون اختصاصی» row an item gets in the rules
#: window -- its own روش and ضرایب, edited in place.
ITEM_RULE_PREFIX = 'ITEM:'

#: Words too common in item names to tie a rule to an item by.
_NAME_STOPWORDS = {
    'بیشتر', 'کمتر', 'برای', 'سانتی', 'متری', 'عدد', 'نوع', 'های', 'مصالح', 'پیمانکار',
    'اجرای', 'اجرا', 'لوازم', 'سایر', 'تهیه', 'نصب', 'کار', 'قیمت', 'ضریب', 'میانگین',
}


def _shamsi(value) -> str:
    """An ISO timestamp as a Persian-digit Shamsi date («۱۴۰۵/۰۷/۰۴»)."""

    try:
        moment = datetime.fromisoformat(str(value))
        day = jdatetime.date.fromgregorian(date=moment.date())
        return fa(f'{day.year:04d}/{day.month:02d}/{day.day:02d}')
    except (TypeError, ValueError):
        return fa(str(value or '')[:10])


def _fa_row(row) -> tuple:
    """Every cell of a displayed row with Persian digits (names, notes, dates, numbers)."""

    return tuple(fa(cell) for cell in row)


def _name_tokens(text: str) -> set[str]:
    words = re.findall(r'[؀-ۿA-Za-z]+', _norm(text))
    return {word for word in words if len(word) >= 3 and word not in _NAME_STOPWORDS}


def _phases_text(codes) -> str:
    """«۰۸ - اسکلت، ۲۲ - کاشی و سنگ» for a list/comma string of phase codes."""

    if isinstance(codes, str):
        codes = [c.strip() for c in codes.split(',') if c.strip()]
    labels = [phase_label(code) for code in codes]
    return '، '.join(labels) if labels else 'همه فازها'


class _RuleItemIndex:
    """Which catalog items a rule is about -- by its موضوع naming them.

    The workbook's rules are prose keyed by a موضوع («بتن», «لوله سیمانی»,
    «سرامیک فاز ۲۲»), not by row. Matching the موضوع against item names is
    what lets the rules window show a rule's فاز, and narrow to the rules of
    one قلم.
    """

    def __init__(self, service: PriceUpdateService) -> None:
        self.items = service.list_catalog_items()
        self._tokens = {item['price_id']: _name_tokens(item['description']) for item in self.items}

    def items_named_by(self, rule: dict) -> list[dict]:
        topic = _name_tokens(rule['description'])
        if not topic:
            return []
        catalog = rule['catalog_type']
        out = []
        for item in self.items:
            if catalog not in ('ALL', item['catalog_type']):
                continue
            tokens = self._tokens[item['price_id']]
            if tokens and (tokens <= topic or topic <= tokens):
                out.append(item)
        return out

    def rule_phases(self, rule: dict) -> list[str]:
        explicit = [c.strip() for c in str(rule['affected_phase_codes'] or '').split(',') if c.strip()]
        if explicit:
            return explicit
        codes: list[str] = []
        for item in self.items_named_by(rule):
            first = (item['phase_codes'] or '').split(',')[0].strip()
            if first and first not in codes:
                codes.append(first)
        return sorted(codes)

    def rule_is_about(self, rule: dict, item: dict) -> bool:
        """The rule's موضوع names the item, or its text names what the item is."""

        if any(named['price_id'] == item['price_id'] for named in self.items_named_by(rule)):
            return True
        tokens = self._tokens.get(item['price_id']) or _name_tokens(item['description'])
        params = _row_params({'calc_params_json': rule.get('params_json')})
        text = _name_tokens(f"{rule['description']} {params.get('rule_text', '')}")
        return bool(tokens & text)


def _rule_order(rule: dict) -> int:
    try:
        params = json.loads(rule.get('params_json') or '{}')
        return int(params.get('order', 0)) if isinstance(params, dict) else 0
    except (TypeError, ValueError):
        return 0


def _rule_is_reference(rule: dict) -> bool:
    try:
        params = json.loads(rule.get('params_json') or '{}')
    except (TypeError, ValueError):
        return False
    return isinstance(params, dict) and bool(params.get('reference'))


def _rule_method(rule: dict) -> str:
    """روش محاسبه‌ی اعلام‌شده در ``params_json`` یک قانون (یا «—» اگر نداشته باشد)."""

    try:
        params = json.loads(rule.get('params_json') or '{}')
    except (TypeError, ValueError):
        return '—'
    if not isinstance(params, dict):
        return '—'
    return str(params.get('method') or '').strip() or '—'


#: Readable names for the option keys the editor writes.
OPTION_LABELS = {
    'web_prices': 'قیمت‌های وب', 'researched_price': 'قیمت تحقیق‌شده', 'carry_rate': 'حمل',
    'tax_rate': 'مالیات', 'regional_factor': 'ضریب منطقه‌ای', 'connection_factor': 'ضریب اتصال',
    'fallback': 'فال‌بک', 'peer_refs': 'ردیف‌های مرجع', 'index': 'شاخص', 'reference_ratio': 'ضریب ثابت',
    'annual_rate': 'نرخ سالانه', 'index_mode': 'حالت شاخص', 'adjustment_index': 'شاخص تعدیل',
    'inflation_rate': 'تورم', **{f'weight_{key}': f'وزن {label}' for key, label in WEIGHT_KEYS},
}
_HIDDEN_OPTION_KEYS = {'method', 'reference', 'section', 'order', 'rule_text'}


def _rule_params_summary(rule: dict) -> str:
    """خلاصه‌ی خوانا از پارامترهای قانون، به‌جای نمایش خام JSON در جدول."""

    try:
        params = json.loads(rule.get('params_json') or '{}')
    except (TypeError, ValueError):
        return '—'
    if not isinstance(params, dict):
        return '—'
    parts = []
    for key, value in params.items():
        if key in _HIDDEN_OPTION_KEYS:
            continue
        if isinstance(value, (int, float)):
            value = _format_param_value(value)
        elif isinstance(value, list):
            value = '، '.join(str(v) for v in value)
        parts.append(f'{OPTION_LABELS.get(key, key)}={value}')
    # Tk puts a line's final «.» at its far (left) end in a right-to-left run.
    text = str(params.get('rule_text') or '').strip().rstrip('.')
    if parts:
        text = f"{text}  [{'، '.join(parts)}]" if text else '، '.join(parts)
    return text or '—'


class CalcRulesWindow187(BarkavWindow):
    """«قوانین بروزرسانی» -- لیست + فیلتر + خروجی + «اعمال قوانین» + «مشاهده قوانین کلی».

    یک قانون، محاسبه نمی‌کند؛ *دسته‌بندی* می‌کند: می‌گوید اقلام کدام دسته‌بندی و
    کدام فازها با چه روش و چه ضرایبی محاسبه شوند. «اعمال قوانین» همان چیزیست که
    این تصمیم را روی اقلام می‌نویسد.

    با انتخاب یک «قلم»، فقط قوانین همان قلم دیده می‌شود: ردیف «قانون اختصاصی»
    خودِ آن قلم (روش و ضرایبی که در اجرا واقعاً به کار می‌رود) و قوانینی که
    موضوع یا متنشان به آن قلم مربوط است. دوبار کلیک روی هر ردیف، ویرایشگر
    گزینه‌ای را باز می‌کند.
    """

    size_class = 'large'

    def __init__(self, parent: tk.Misc, service: PriceUpdateService, *, on_applied=None,
                 category: str | None = None, phase: str | None = None, item: str | None = None):
        self.service = service
        self.on_applied = on_applied
        self._initial_scope = (category, phase, item)
        super().__init__(parent, 'قوانین بروزرسانی')
        self.output_format_var = tk.StringVar(master=self, value=EXPORT_PLACEHOLDER)
        self._build()

    def _build(self) -> None:
        self.table = DataTable(self.body, RULE_COLUMNS, on_open=self._edit_selected,
                                empty_text='قانونی ثبت نشده است', checkable=True)
        self.table.pack(fill='both', expand=True)
        category, phase, item = self._initial_scope
        self.scope = _ScopeFilter(self, self.table, self.service, category=category, phase=phase,
                                  item=item, on_change=self._refresh)
        add_export_control(self.table, self.output_format_var, self._export)
        self.table.add_action('اعمال قوانین', self._apply_rules, 'create')
        self.table.add_action('افزودن', self._add, 'create')
        self.table.add_action('ویرایش', self._edit_selected, 'neutral')
        self.table.add_action('مشاهده قوانین کلی', self._open_general, 'neutral')
        self.table.add_action('حذف', self._delete_selected, 'destructive')
        self.add_action('بستن', self.close)
        self._refresh()

    # ----------------------------------------------------------------- data

    def _filtered_rules(self) -> list[dict]:
        self._index = _RuleItemIndex(self.service)
        category = self.scope.category
        rules = self.service.list_calc_rules(catalog_type=category)
        if category:
            # «مصالح» means the مصالح rules: the general («همه دسته‌ها») ones
            # stay under «همه» and «مشاهده قوانین کلی».
            rules = [r for r in rules if r['catalog_type'] == category]
        item = self.service.get_catalog_item(self.scope.item) if self.scope.item else None
        if item:
            # Only the rules of this item in its own فاز: a rule about the same
            # material elsewhere (میلگرد بستر، فاز ۱۳) or with no فاز of its own
            # is not this row's rule.
            item_phases = {c.strip() for c in str(item['phase_codes'] or '').split(',') if c.strip()}
            if self.scope.phase:
                item_phases &= {self.scope.phase}
            related = [r for r in rules if self._index.rule_is_about(r, item)
                       and item_phases & set(self._index.rule_phases(r))]
            return sorted(related, key=lambda r: (
                not any(n['price_id'] == item['price_id'] for n in self._index.items_named_by(r)),
                _rule_is_reference(r), _rule_order(r)))
        phase = self.scope.phase
        if phase:
            rules = [r for r in rules if not self._index.rule_phases(r) or phase in self._index.rule_phases(r)]
        # Rules made here first (newest first, as stored); the workbook's own
        # rules after them, in the order the «قوانین محاسبه بروز» sheet reads.
        return sorted(rules, key=lambda r: (_rule_is_reference(r), _rule_order(r)))

    def _item_rule_row(self, item: dict) -> tuple:
        return _fa_row((
            '', _shamsi(item['updated_at']), CATALOG_LABELS.get(item['catalog_type'], ''),
            f"قانون اختصاصی: {item['description']}", item['calc_method'] or '—',
            _phases_text(item['phase_codes']), _basis_text(item),
        ))

    def _display_rows(self, rules: list[dict]) -> list[tuple[str, ...]]:
        return [
            _fa_row((index + 1, _shamsi(rule['updated_at']),
                     RULE_CATALOG_LABELS.get(rule['catalog_type'], rule['catalog_type']),
                     rule['description'], _rule_method(rule),
                     _phases_text(self._index.rule_phases(rule)), _rule_params_summary(rule)))
            for index, rule in enumerate(rules)
        ]

    def _refresh(self) -> None:
        rules = self._filtered_rules()
        self._by_key = {r['rule_id']: r for r in rules}
        rows = self._display_rows(rules)
        keys = [r['rule_id'] for r in rules]
        item = self.service.get_catalog_item(self.scope.item) if self.scope.item else None
        if item:
            rows = [self._item_rule_row(item), *rows]
            keys = [ITEM_RULE_PREFIX + item['price_id'], *keys]
            rows = [(fa(index + 1), *row[1:]) for index, row in enumerate(rows)]
        self.table.set_rows(rows, keys=keys)

    def _selected(self) -> dict | None:
        key = self.table.selected_key()
        return self._by_key.get(key) if key else None

    def _checked_rule_ids(self) -> list[str]:
        """هر ردیف تیک‌خورده (چندانتخابی)، نه فقط ردیف فعال."""

        return [key for key in self.table.selected_keys() if not str(key).startswith(ITEM_RULE_PREFIX)]

    # -------------------------------------------------------------- actions

    def _add(self) -> None:
        RuleOptionsDialog187(self, self.service, rule=None, on_saved=self._after_edit,
                             default_catalog=self.scope.category)

    def _edit_selected(self, *_a) -> None:
        key = self.table.selected_key()
        if not key:
            messagebox.showinfo('ویرایش', 'یک ردیف را انتخاب کنید.', parent=self)
            return
        if str(key).startswith(ITEM_RULE_PREFIX):
            item = self.service.get_catalog_item(str(key)[len(ITEM_RULE_PREFIX):])
            if item:
                RuleOptionsDialog187(self, self.service, item=item, on_saved=self._after_edit)
            return
        row = self._by_key.get(key)
        if row:
            RuleOptionsDialog187(self, self.service, rule=row, on_saved=self._after_edit)

    def _after_edit(self) -> None:
        self._refresh()
        if self.on_applied:
            self.on_applied()

    def _open_general(self) -> None:
        GeneralRulesWindow187(self, self.service, category=self.scope.category, on_changed=self._after_edit)

    def _delete_selected(self) -> None:
        keys=self.table.selected_keys()
        if any(str(key).startswith(ITEM_RULE_PREFIX) for key in keys):
            messagebox.showinfo('حذف', 'قانون اختصاصی یک قلم حذف‌شدنی نیست؛ روش آن را ویرایش کنید.',
                                parent=self)
            return
        rows=[self._by_key[key] for key in keys if key in self._by_key]
        from table_actions import select_delete_rows
        rows=select_delete_rows(self,rows,messagebox=messagebox)
        if not rows:return
        with self.service.db.atomic():
            for row in rows:self.service.delete_calc_rule(row['rule_id'])
        self._refresh()

    def _apply_rules(self) -> None:
        """«اعمال قوانین» -- نوشتن روش و ضرایب قوانین انتخاب‌شده روی اقلام.

        با هیچ ردیف تیک‌خورده، همه‌ی قوانینِ همین فیلتر اعمال می‌شوند (نه همه‌ی
        قوانین موجود): چیزی که کاربر می‌بیند همان چیزیست که اعمال می‌شود.
        """

        rule_ids = self._checked_rule_ids() or list(self._by_key)
        # A workbook rule that is still text only carries no روش to write.
        rule_ids = [rule_id for rule_id in rule_ids
                    if not _rule_is_reference(self._by_key.get(rule_id) or {})]
        if not rule_ids:
            messagebox.showinfo(
                'اعمال قوانین',
                'قانونی برای اعمال وجود ندارد. قوانین فایل مرجع متنی‌اند (روش و ضرایب آن‌ها هنگام '
                'بارگذاری فایل روی تک‌تک اقلام نوشته شده است)؛ برای اعمال، در ویرایش قانون یک '
                'روش محاسبه انتخاب کنید.', parent=self)
            return
        if not messagebox.askyesno(
                'اعمال قوانین',
                f'{fa(len(rule_ids))} قانون روی اقلام متناظرشان اعمال شود؟\n'
                'روش محاسبه و ضرایب اقلام بازنویسی می‌شود (قیمت‌ها تغییر نمی‌کند؛ '
                'قیمت‌ها در «شروع براورد» محاسبه می‌شوند).', parent=self):
            return
        try:
            result = self.service.apply_calc_rules(rule_ids)
        except Exception as exc:
            messagebox.showerror('اعمال قوانین', f'اعمال قوانین ناموفق بود:\n{exc}', parent=self)
            return
        lines = [f"قوانین اعمال‌شده: {fa(result['rules'])}",
                 f"اقلام بروزشده: {fa(result['items'])}"]
        if result['rules_without_method']:
            lines.append(
                f"⚠ {fa(result['rules_without_method'])} قانون روش محاسبه ندارد؛ "
                'اقلام آن‌ها در اجرا بازمحاسبه نمی‌شوند. روش را در ویرایش قانون تعیین کنید.')
        messagebox.showinfo('اعمال قوانین', '\n'.join(lines), parent=self)
        self._after_edit()

    def _export(self) -> None:
        preview_export(self, self.output_format_var, [label for _key, label in RULE_COLUMNS],
                       selected_table_rows(self.table), 'قوانین بروزرسانی', summary_lines=[self.scope.note()])


# ---------------------------------------------------------------- option editor

_NUMBER_CHOICES = {
    'carry_rate': ('0', '0.035', '0.1', '0.15', '0.3', '0.4'),
    'tax_rate': ('0', '0.1'),
    'regional_factor': ('1', '1.17', '1.2'),
    'connection_factor': ('1',),
    'weight': tuple(f'{step / 20:.2f}' for step in range(21)),
}
_FALLBACK_CHOICES = {
    '': 'میانگین مثبت وب‌دارهای فاز ← میانگین پیمانکار فاز ← ضریب دستمزد',
    'wage': 'مستقیم ضریب رشد دستمزد روزمزد',
}
_INDEX_MODE_CHOICES = {
    '': 'بیشینهٔ (قیمت تحقیق‌شده، ردیف مرجع، کف حداقل حقوق) — مثل فایل مرجع',
    'live': 'محاسبه زنده با وزن‌ها (و کف حداقل حقوق)',
}
_OTHER_INDEX_CHOICES = {
    'usd': 'ضریب رشد دلار', 'copper': 'ضریب رشد مس', 'wage': 'ضریب رشد حداقل حقوق',
    '': 'ضریب ثابت (فیلد «ضریب ثابت»)',
}
#: Which option sections each روش uses.
_METHOD_SECTIONS = {
    calc.METHOD_WEB: ('web', 'factors', 'fallback'),
    calc.METHOD_PHASE_AVERAGE: ('fallback',),
    calc.METHOD_PEER_AVERAGE: ('peers', 'fallback'),
    calc.METHOD_WEIGHTED_INDEX: ('weights', 'researched', 'peers'),
    calc.METHOD_SERVICE_TARIFF: ('researched', 'tariff', 'factors', 'fallback'),
    calc.METHOD_OTHER: ('other', 'fallback'),
}
TEXT_ONLY_LABEL = 'فقط متن (بدون اعمال روی اقلام)'


def _peer_ref_labels(service: PriceUpdateService) -> dict[str, str]:
    """{«مصالح: ۰۸-بتن»: 'MATERIAL:code'} for every item a row can copy its ratio from."""

    out: dict[str, str] = {}
    for catalog, label in CATALOG_LABELS.items():
        for item_label, price_id in item_option_map(service, catalog, None).items():
            item = service.get_catalog_item(price_id)
            if item and item['code']:
                out[f'{label}: {item_label}'] = f"{catalog}:{item['code']}"
    return out


class RuleOptionsDialog187(BarkavDialog):
    """ویرایش گزینه‌ای یک قانون یا «قانون اختصاصی» یک قلم -- همه‌ی قابلیت‌های اجرا با کادر کشویی.

    برای یک قلم، روش و ضرایب همان قلم نوشته می‌شود (همان چیزی که «شروع براورد»
    واقعاً به کار می‌برد). برای یک قانون، گزینه‌ها در خود قانون ذخیره می‌شوند و
    «اعمال قوانین» آن‌ها را روی اقلام دسته‌بندی/فازهای قانون می‌نویسد؛ قانون
    متنیِ فایل مرجع با انتخاب یک روش، قابل اعمال می‌شود.
    """

    size_class = 'large'

    def __init__(self, parent: tk.Misc, service: PriceUpdateService, *, item: dict | None = None,
                 rule: dict | None = None, on_saved, default_catalog: str | None = None):
        self.service = service
        self.item = item
        self.rule = rule
        self.on_saved = on_saved
        self.default_catalog = default_catalog
        source = item['calc_params_json'] if item else (rule or {}).get('params_json')
        self.params = _row_params({'calc_params_json': source})
        if item:
            title = f"قانون اختصاصی: {fa(item['description'])}"
        else:
            title = 'ویرایش قانون' if rule else 'افزودن قانون'
        super().__init__(parent, title, scrollable=True)
        self._render()

    # ------------------------------------------------------------ widgets

    def _combo(self, parent, label: str, variable: tk.StringVar, values, *, editable=False, width=None):
        p = palette()
        cell = tk.Frame(parent, bg=p['bg'])
        tk.Label(cell, text=label, bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                 anchor='e').pack(fill='x')
        combo = ttk.Combobox(cell, textvariable=variable, values=tuple(values), justify='right',
                             state='normal' if editable else 'readonly')
        if width:
            combo.configure(width=width)
        combo.pack(fill='x')
        rtl_dropdown(combo)
        return cell, combo

    def _section(self, key: str, title: str) -> tk.Frame:
        p = palette()
        m = metrics()
        frame = tk.Frame(self.body, bg=p['bg'], highlightbackground=p['border_subtle'], highlightthickness=1)
        tk.Label(frame, text=title, bg=p['bg'], fg=p['text_primary'], font=font('small'),
                 anchor='e').pack(fill='x', padx=m['gap'], pady=(m['gap'] // 2, 0))
        self.sections[key] = frame
        return frame

    def _number_var(self, key: str, default: str = '') -> tk.StringVar:
        value = self.params.get(key)
        text = _format_param_value(value) if isinstance(value, (int, float)) else (default if value is None else str(value))
        variable = tk.StringVar(master=self, value=fa(text.replace(',', '')))
        self.vars[key] = variable
        return variable

    def _choice_var(self, key: str, choices: dict[str, str]) -> tk.StringVar:
        variable = tk.StringVar(master=self, value=choices.get(str(self.params.get(key) or ''),
                                                               next(iter(choices.values()))))
        self.choice_vars[key] = (variable, choices)
        return variable

    # ------------------------------------------------------------- layout

    def _render(self) -> None:
        p = palette()
        m = metrics()
        self.vars: dict[str, tk.StringVar] = {}
        self.choice_vars: dict[str, tuple[tk.StringVar, dict[str, str]]] = {}
        self.sections: dict[str, tk.Frame] = {}

        head = tk.Frame(self.body, bg=p['bg'])
        head.pack(fill='x', pady=(0, m['gap']))
        if self.item:
            tk.Label(head, text=fa(f"{CATALOG_LABELS.get(self.item['catalog_type'], '')} — "
                                   f"{self.item['description']} — فاز: {_phases_text(self.item['phase_codes'])}"),
                     bg=p['bg'], fg=p['text_primary'], font=font('title'), anchor='e').pack(fill='x')
            method = self.item['calc_method'] or METHOD_OPTIONS[0]
            methods = METHOD_OPTIONS
        else:
            rule = self.rule or {}
            self.topic_var = tk.StringVar(master=self, value=rule.get('description', ''))
            catalog = rule.get('catalog_type') or self.default_catalog or 'MATERIAL'
            self.catalog_var = tk.StringVar(master=self, value=RULE_CATALOG_LABELS.get(catalog, 'مصالح'))
            self.phases_var = tk.StringVar(master=self, value=fa(rule.get('affected_phase_codes', '')))
            method = _rule_method(rule) if rule and _rule_method(rule) != '—' else (
                TEXT_ONLY_LABEL if rule and _rule_is_reference(rule) else METHOD_OPTIONS[0])
            methods = (*METHOD_OPTIONS, TEXT_ONLY_LABEL)
            grid = tk.Frame(head, bg=p['bg'])
            grid.pack(fill='x')
            grid.columnconfigure((0, 1, 2), weight=1, uniform='head')
            cell, _ = self._combo(grid, 'دسته‌بندی', self.catalog_var, tuple(RULE_CATALOG_LABELS.values()))
            cell.grid(row=0, column=2, sticky='ew', padx=m['gap'] // 2)
            cell = tk.Frame(grid, bg=p['bg'])
            tk.Label(cell, text='موضوع', bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                     anchor='e').pack(fill='x')
            ttk.Entry(cell, textvariable=self.topic_var, justify='right').pack(fill='x')
            cell.grid(row=0, column=1, sticky='ew', padx=m['gap'] // 2)
            cell, self.phase_pick = self._combo(
                grid, 'فازهای تحت تاثیر (خالی = همه؛ برای چند فاز: ۰۸,۲۲)', self.phases_var,
                phase_option_labels(self.service, None)[1:], editable=True)
            self.phase_pick.bind('<<ComboboxSelected>>', lambda _e: self.phases_var.set(
                fa(phase_code_of(self.phases_var.get()) or '')), add='+')
            cell.grid(row=0, column=0, sticky='ew', padx=m['gap'] // 2)
            tk.Label(head, text='متن قانون (پرامپت)', bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                     anchor='e').pack(fill='x', pady=(m['gap'], 0))
            self.rule_text = tk.Text(head, height=4, wrap='word')
            self.rule_text.tag_configure('rtl', justify='right')
            self.rule_text.pack(fill='x')
            self.rule_text.insert('1.0', fa(self.params.get('rule_text', '')), 'rtl')

        self.method_var = tk.StringVar(master=self, value=method if method in methods else methods[0])
        method_row = tk.Frame(self.body, bg=p['bg'])
        method_row.pack(fill='x', pady=(0, m['gap']))
        cell, method_combo = self._combo(method_row, 'روش محاسبه', self.method_var, methods)
        cell.pack(side='right', fill='x', expand=True)
        method_combo.bind('<<ComboboxSelected>>', lambda _e: self._sync_sections(), add='+')

        # وب -- قیمت‌ها و سایت‌ها
        web = self._section('web', 'قیمت وب (میانگین قیمت‌ها × ضرایب؛ اگر «قیمت تحقیق‌شده» پر باشد همان مبناست)')
        prices = [p_ for p_ in self.params.get('web_prices', []) if isinstance(p_, (int, float))] + [None] * 3
        sites = (list(self.params.get('web_sites', [])) + ['', '', ''])[:3]
        self.web_price_vars = [tk.StringVar(master=self, value=fa(_format_param_value(v)) if v else '') for v in prices[:3]]
        self.web_site_vars = [tk.StringVar(master=self, value=s) for s in sites]
        grid = tk.Frame(web, bg=p['bg'])
        grid.pack(fill='x', padx=m['gap'])
        grid.columnconfigure((0, 1, 2), weight=1, uniform='web')
        for index in range(3):
            for row, (label, variable) in enumerate(((f'قیمت وب {fa(index + 1)}', self.web_price_vars[index]),
                                                     (f'سایت {fa(index + 1)}', self.web_site_vars[index]))):
                cell = tk.Frame(grid, bg=p['bg'])
                tk.Label(cell, text=label, bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                         anchor='e').pack(fill='x')
                ttk.Entry(cell, textvariable=variable, justify='right').pack(fill='x')
                cell.grid(row=row, column=2 - index, sticky='ew', padx=m['gap'] // 2, pady=2)
        cells = tk.Frame(web, bg=p['bg'])
        cells.pack(fill='x', padx=m['gap'], pady=(0, m['gap'] // 2))
        cell, _ = self._combo(cells, 'قیمت تحقیق‌شده (تومان)', self._number_var('researched_price'), (), editable=True)
        cell.pack(side='right', fill='x', expand=True)

        # ضرایب مشترک
        factors = self._section('factors', 'ضرایب حمل، مالیات، منطقه و اتصال')
        grid = tk.Frame(factors, bg=p['bg'])
        grid.pack(fill='x', padx=m['gap'], pady=(0, m['gap'] // 2))
        grid.columnconfigure((0, 1, 2, 3), weight=1, uniform='fac')
        for column, (key, label, default) in enumerate((
                ('carry_rate', 'ضریب حمل (کسر)', '0'), ('tax_rate', 'مالیات (کسر)', '0'),
                ('regional_factor', 'ضریب منطقه‌ای', '1'), ('connection_factor', 'ضریب اتصال', '1'))):
            cell, _ = self._combo(grid, label, self._number_var(key, default),
                                  tuple(fa(v) for v in _NUMBER_CHOICES[key]), editable=True)
            cell.grid(row=0, column=3 - column, sticky='ew', padx=m['gap'] // 2)

        # قیمت تحقیق‌شده (پیمانکار) -- a separate variable would split one key; share it.
        researched = self._section('researched', 'قیمت تحقیق‌شده / استعلام (ضریب = قیمت ÷ اولیه)')
        cell, _ = self._combo(researched, 'قیمت تحقیق‌شده (تومان)', self.vars['researched_price'], (), editable=True)
        cell.pack(fill='x', padx=m['gap'], pady=(0, m['gap'] // 2))

        # میانگین ردیف‌ها
        peers = self._section('peers', 'ردیف‌های مرجع (ضریب = میانگین مثبت ضریب این ردیف‌ها)')
        self.peer_labels = _peer_ref_labels(self.service)
        ref_to_label = {ref: label for label, ref in self.peer_labels.items()}
        self.peer_list = tk.Listbox(peers, height=4, justify='right', exportselection=False)
        for ref in self.params.get('peer_refs', []) or []:
            self.peer_list.insert('end', ref_to_label.get(ref, ref))
        tools = tk.Frame(peers, bg=p['bg'])
        tools.pack(fill='x', padx=m['gap'])
        self.peer_pick = tk.StringVar(master=self)
        cell, _ = self._combo(tools, 'افزودن ردیف مرجع', self.peer_pick, tuple(self.peer_labels))
        cell.pack(side='right', fill='x', expand=True)
        ttk.Button(tools, text='افزودن', style='TableToolbar.TButton',
                   command=self._add_peer).pack(side='right', padx=m['gap'] // 2, anchor='s')
        ttk.Button(tools, text='حذف ردیف انتخاب‌شده', style='TableToolbar.TButton',
                   command=lambda: [self.peer_list.delete(i) for i in reversed(self.peer_list.curselection())]
                   ).pack(side='right', anchor='s')
        self.peer_list.pack(fill='x', padx=m['gap'], pady=(2, m['gap'] // 2))

        # شاخص ترکیبی وزنی
        weights = self._section('weights', 'شاخص ترکیبی وزنی (۷ زیرستون) — ضریب نهایی هرگز زیر کف حداقل حقوق نیست')
        cell, _ = self._combo(weights, 'حالت شاخص', self._choice_var('index_mode', _INDEX_MODE_CHOICES),
                              tuple(_INDEX_MODE_CHOICES.values()))
        cell.pack(fill='x', padx=m['gap'])
        grid = tk.Frame(weights, bg=p['bg'])
        grid.pack(fill='x', padx=m['gap'])
        grid.columnconfigure(tuple(range(4)), weight=1, uniform='w')
        weight_fields = [(f'weight_{key}', f'وزن {label}') for key, label in WEIGHT_KEYS]
        weight_fields += [('adjustment_index', 'شاخص تعدیل (ضریب)'), ('inflation_rate', 'تورم (ضریب)')]
        for index, (key, label) in enumerate(weight_fields):
            values = tuple(fa(v) for v in _NUMBER_CHOICES['weight']) if key.startswith('weight_') else ('1',)
            cell, _ = self._combo(grid, label, self._number_var(key, '0' if key.startswith('weight_') else '1'),
                                  values, editable=True)
            cell.grid(row=index // 4, column=3 - index % 4, sticky='ew', padx=m['gap'] // 2, pady=2)

        # تعرفه خدمات
        tariff = self._section('tariff', 'تعرفه خدمات (ضریب ثابت پژوهش‌شده، یا نرخ سالانه برای ماه‌های سپری‌شده)')
        grid = tk.Frame(tariff, bg=p['bg'])
        grid.pack(fill='x', padx=m['gap'], pady=(0, m['gap'] // 2))
        grid.columnconfigure((0, 1), weight=1, uniform='t')
        cell, _ = self._combo(grid, 'ضریب ثابت (مثلاً ۱٫۱۶)', self._number_var('reference_ratio'), (), editable=True)
        cell.grid(row=0, column=1, sticky='ew', padx=m['gap'] // 2)
        cell, _ = self._combo(grid, 'نرخ سالانه (کسر)', self._number_var('annual_rate'), (), editable=True)
        cell.grid(row=0, column=0, sticky='ew', padx=m['gap'] // 2)

        # سایر
        other = self._section('other', 'سایر — ضریب یکی از شاخص‌های کلان، یا یک ضریب ثابت')
        grid = tk.Frame(other, bg=p['bg'])
        grid.pack(fill='x', padx=m['gap'], pady=(0, m['gap'] // 2))
        grid.columnconfigure((0, 1), weight=1, uniform='o')
        cell, _ = self._combo(grid, 'شاخص', self._choice_var('index', _OTHER_INDEX_CHOICES),
                              tuple(_OTHER_INDEX_CHOICES.values()))
        cell.grid(row=0, column=1, sticky='ew', padx=m['gap'] // 2)
        cell, _ = self._combo(grid, 'ضریب ثابت', self.vars['reference_ratio'], (), editable=True)
        cell.grid(row=0, column=0, sticky='ew', padx=m['gap'] // 2)

        # فال‌بک
        fallback = self._section('fallback', 'اگر ضریب خودِ ردیف کاهشی/خنثی شد (هرگز ضریب ≤ ۱ اعمال نمی‌شود)')
        cell, _ = self._combo(fallback, 'جایگزین', self._choice_var('fallback', _FALLBACK_CHOICES),
                              tuple(_FALLBACK_CHOICES.values()))
        cell.pack(fill='x', padx=m['gap'], pady=(0, m['gap'] // 2))

        self._sync_sections()
        self.add_action('ذخیره', self._save, style='Success.TButton')
        self.add_action('انصراف', self.close)

    def _add_peer(self) -> None:
        label = self.peer_pick.get()
        if label and label not in self.peer_list.get(0, 'end'):
            self.peer_list.insert('end', label)

    def _sync_sections(self) -> None:
        m = metrics()
        wanted = _METHOD_SECTIONS.get(self.method_var.get(), ())
        for key, frame in self.sections.items():
            frame.pack_forget()
        for key in ('web', 'researched', 'factors', 'peers', 'weights', 'tariff', 'other', 'fallback'):
            if key in wanted:
                self.sections[key].pack(fill='x', pady=(0, m['gap']))

    # --------------------------------------------------------------- save

    def _collect(self) -> dict:
        """The option keys the chosen روش uses, from the boxes; empty boxes are left out."""

        wanted = _METHOD_SECTIONS.get(self.method_var.get(), ())
        keys: dict[str, object] = {}

        def number(key: str) -> None:
            raw = en(self.vars[key].get()).strip()
            keys[key] = _parse_param_float(raw) if raw else None

        if 'web' in wanted:
            prices = [_parse_param_float(en(v.get())) for v in self.web_price_vars if en(v.get()).strip()]
            keys['web_prices'] = [p_ for p_ in prices if p_] or None
            sites = [v.get().strip() for v in self.web_site_vars]
            keys['web_sites'] = sites if any(sites) else None
        if 'web' in wanted or 'researched' in wanted:
            number('researched_price')
        if 'factors' in wanted:
            for key in ('carry_rate', 'tax_rate', 'regional_factor', 'connection_factor'):
                number(key)
        if 'peers' in wanted:
            refs = [self.peer_labels.get(label, label) for label in self.peer_list.get(0, 'end')]
            keys['peer_refs'] = refs or None
        if 'weights' in wanted:
            for key, _label in WEIGHT_KEYS:
                number(f'weight_{key}')
            number('adjustment_index')
            number('inflation_rate')
            variable, choices = self.choice_vars['index_mode']
            keys['index_mode'] = next((k for k, v in choices.items() if v == variable.get()), '') or None
        if 'tariff' in wanted:
            number('reference_ratio')
            number('annual_rate')
        if 'other' in wanted:
            number('reference_ratio')
            variable, choices = self.choice_vars['index']
            keys['index'] = next((k for k, v in choices.items() if v == variable.get()), '') or None
        if 'fallback' in wanted:
            variable, choices = self.choice_vars['fallback']
            keys['fallback'] = next((k for k, v in choices.items() if v == variable.get()), '') or None
        return keys

    def _save(self) -> None:
        method = self.method_var.get()
        collected = self._collect()
        if self.item:
            params = dict(self.params)
            for key, value in collected.items():
                if value is None:
                    params.pop(key, None)
                else:
                    params[key] = value
            self.service.upsert_catalog_item(
                self.item['price_id'], calc_method=method, suggested_method=method,
                calc_params_json=json.dumps(params, ensure_ascii=False))
        else:
            topic = self.topic_var.get().strip()
            if not topic:
                messagebox.showwarning('ذخیره', 'موضوع قانون نمی‌تواند خالی باشد.', parent=self)
                return
            params = {key: value for key, value in self.params.items() if key in {'section', 'order'}}
            text = self.rule_text.get('1.0', 'end').strip()
            if text:
                params['rule_text'] = text
            if method == TEXT_ONLY_LABEL:
                params['reference'] = True
            else:
                params['method'] = method
                params.update({key: value for key, value in collected.items() if value is not None})
            catalog = next((k for k, v in RULE_CATALOG_LABELS.items() if v == self.catalog_var.get()), 'MATERIAL')
            phases = normalize_phase_codes(en(self.phases_var.get()))
            self.service.upsert_calc_rule(
                self.rule['rule_id'] if self.rule else None, catalog_type=catalog, description=topic,
                affected_phase_codes=phases, params_json=json.dumps(params, ensure_ascii=False))
        self.on_saved()
        self.close()


# ---------------------------------------------------------------- general rules

def _engine_rules(ctx: dict[str, float]) -> list[tuple[str, str, str]]:
    """(دسته‌بندی, موضوع, قانون) -- the rules every run applies, with today's numbers."""

    wage = fa(f"{ctx['wage']:.4f}")
    usd = fa(f"{ctx['usd']:.4f}")
    return [
        ('ALL', 'مقدار بروز = مقدار اولیه', 'در بروزرسانی فقط قیمت واحد تغییر می‌کند؛ مقدار هر ردیف ثابت می‌ماند'),
        ('ALL', 'رشد حداقل حقوق (مرکب)',
         f'ضریب = (۱ + نرخ سالانه) به توان (ماه‌های سپری‌شده ÷ ۱۲) — اکنون {wage}؛ خطی حساب نمی‌شود'),
        ('ALL', 'ممنوعیت ضریب کاهشی',
         'ضریب ≤ ۱ هرگز اعمال نمی‌شود؛ میانگین مثبت فاز، سپس میانگین پیمانکار فاز، سپس ضریب دستمزد جایگزین می‌شود و ردیف برای بازبینی علامت می‌خورد'),
        ('ALL', 'فقط ضرایب مثبت در میانگین', 'در میانگین فاز و میانگین ردیف‌ها فقط ضرایب بزرگ‌تر از ۱ شمرده می‌شوند'),
        ('ALL', 'سقف رشد دلار = پرچم بازبینی',
         f'ضریب بالاتر از رشد دلار (اکنون {usd}) عیناً اعمال می‌شود و فقط برای بازبینی علامت می‌خورد؛ بریده نمی‌شود'),
        ('CONTRACTOR', 'کف حداقل حقوق پیمانکار',
         f'ضریب هر ردیف پیمانکار = بیشینهٔ(ضریب محاسباتی، رشد حداقل حقوق {wage})؛ هر بار کف جایگزین شود، ردیف علامت بازبینی می‌خورد'),
    ]


class ParameterDialog187(BarkavDialog):
    """افزودن / ویرایش یک پارامتر کلان -- اولیه / قبلی / بروز.

    در حالت افزودن، نوع پارامتر از کادر کشویی انتخاب می‌شود: «شاخص تعدیل» و
    «تورم» را موتور محاسبه برای ردیف‌های شاخص ترکیبی وزنی (حالت زنده) می‌خواند؛
    «پارامتر دلخواه» فقط ثبت و نمایش می‌شود.
    """

    size_class = 'small'
    CUSTOM = 'پارامتر دلخواه (با نام زیر)'

    def __init__(self, parent: tk.Misc, service: PriceUpdateService, key: str | None, *, on_saved):
        self.service = service
        self.key = key
        self.on_saved = on_saved
        stored = service.get_parameter(key) if key else {}
        super().__init__(parent, f"پارامتر: {stored.get('label', key)}" if key else 'افزودن پارامتر')
        p = palette()
        m = metrics()
        self.kind_var = tk.StringVar(master=self, value=self.CUSTOM)
        self.label_var = tk.StringVar(master=self, value=stored.get('label', ''))
        if not key:
            free = [label for k, label in service.OPTIONAL_PARAMETERS.items() if service.get_parameter(k) is None]
            cell = tk.Frame(self.body, bg=p['bg'])
            cell.pack(fill='x', pady=m['gap'] // 2)
            tk.Label(cell, text='نوع پارامتر', bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                     anchor='e').pack(fill='x')
            rtl_dropdown(ttk.Combobox(cell, textvariable=self.kind_var, values=(*free, self.CUSTOM),
                                      state='readonly', justify='right')).pack(fill='x')
            cell = tk.Frame(self.body, bg=p['bg'])
            cell.pack(fill='x', pady=m['gap'] // 2)
            tk.Label(cell, text='نام (برای پارامتر دلخواه)', bg=p['bg'], fg=p['text_secondary'],
                     font=font('small'), anchor='e').pack(fill='x')
            ttk.Entry(cell, textvariable=self.label_var, justify='right').pack(fill='x')
        self.vars = {}
        for field, label in (('base', 'اولیه'), ('previous', 'قبلی'), ('current', 'بروز')):
            cell = tk.Frame(self.body, bg=p['bg'])
            cell.pack(fill='x', pady=m['gap'] // 2)
            tk.Label(cell, text=label, bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                     anchor='e').pack(fill='x')
            variable = tk.StringVar(master=self, value=fa(_format_param_value(stored.get(f'{field}_value') or 0)))
            ttk.Entry(cell, textvariable=variable, justify='right').pack(fill='x')
            self.vars[field] = variable
        self.add_action('ذخیره', self._save, style='Success.TButton')
        self.add_action('انصراف', self.close)

    def _save(self) -> None:
        values = {field: _parse_param_float(en(variable.get())) for field, variable in self.vars.items()}
        if self.key:
            self.service.save_parameter(self.key, base_value=values['base'], previous_value=values['previous'],
                                        current_value=values['current'], source='wizard')
        else:
            known = {label: k for k, label in self.service.OPTIONAL_PARAMETERS.items()}
            kind = self.kind_var.get()
            label = kind if kind in known else self.label_var.get().strip()
            if not label:
                messagebox.showwarning('ذخیره', 'نام پارامتر را وارد کنید.', parent=self)
                return
            self.service.add_parameter(label, key=known.get(kind), base_value=values['base'],
                                       previous_value=values['previous'], current_value=values['current'])
        self.on_saved()
        self.close()


PARAMETER_UNITS = {
    'usd': 'تومان', 'copper': 'تومان/کیلوگرم', 'wage_annual_growth': 'کسر سالانه', 'months_elapsed': 'ماه',
    'adjustment_index': 'ضریب', 'inflation_rate': 'ضریب',
}


def _codes_text(codes, full: set[str] | None = None, full_label: str = 'همه فازها') -> str:
    """«۰۲، ۰۶، ۰۸» -- the phase numbers a parameter or rule reaches.

    Reaching every phase in ``full`` reads as «همه فازها» rather than a line of
    thirty-two numbers nobody checks one by one.
    """

    codes = {c for c in codes if c}
    if full and codes >= full:
        return full_label
    missing = (full or set()) - codes
    if full and len(codes) > 10 and len(missing) <= 4:
        return f"{full_label} به‌جز {fa('، '.join(sorted(missing)))}"
    return fa('، '.join(sorted(codes))) if codes else '—'


def _parameter_phases(items: list[dict], key: str) -> set[str]:
    """The فازها whose prices move when parameter ``key`` changes."""

    def weight(params, *names):
        return sum(_as_number(params.get(name)) for name in names)

    out: set[str] = set()
    for item in items:
        if not item['calc_method']:
            continue
        params = _row_params(item)
        method = item['calc_method']
        live = params.get('index_mode') == 'live' or 'wage_weight' in params
        uses = False
        if key == 'usd':
            uses = (method == calc.METHOD_OTHER and params.get('index') == 'usd') or (
                method == calc.METHOD_WEIGHTED_INDEX and live
                and weight(params, 'weight_dollar', 'weight_steel', 'dollar_or_metal_weight') > 0)
        elif key == 'copper':
            uses = params.get('index') == 'copper' or weight(params, 'weight_copper') > 0
        elif key in ('wage_annual_growth', 'months_elapsed'):
            # رشد حداقل حقوق: every contractor row's floor, rows indexed on it,
            # and every fallback that ends at the day-wage ratio.
            uses = (item['catalog_type'] == 'CONTRACTOR' or params.get('index') == 'wage'
                    or params.get('fallback') == 'wage'
                    or (key == 'months_elapsed' and 'annual_rate' in params))
        elif key == 'adjustment_index':
            uses = method == calc.METHOD_WEIGHTED_INDEX and live and weight(params, 'weight_adjustment', 'adjustment_weight') > 0
        elif key == 'inflation_rate':
            uses = method == calc.METHOD_WEIGHTED_INDEX and live and weight(
                params, 'weight_inflation', 'weight_other', 'inflation_weight') > 0
        if uses:
            out.update(c.strip() for c in str(item['phase_codes'] or '').split(',') if c.strip())
    return out


def _as_number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class GeneralRulesWindow187(BarkavWindow):
    """«مشاهده قوانین کلی» -- آنچه با تغییرش همه‌ی اقلام (یا یک دسته‌بندی کامل) بروز می‌شود.

    بالا: پارامترهای کلان (دلار، مس، حداقل حقوق، ماه‌های سپری‌شده، و هر
    پارامتر افزوده) با اولیه/قبلی/بروز، ضریب رشد و شماره‌ی فازهایی که اثر
    می‌گیرند. پایین: قوانین ثابت موتور محاسبه (با اعداد امروز) و قوانین
    ثبت‌شده‌ی دسته‌بندی انتخابی، هر کدام با شماره‌ی فاز کنار نام قلم و
    دامنه‌ی اثر. «افزودن / ویرایش / حذف» بالای صفحه روی جدولی عمل می‌کند که
    ردیفش انتخاب شده است.
    """

    size_class = 'large'

    PARAM_COLUMNS = (('name', 'پارامتر'), ('unit', 'واحد'), ('base', 'اولیه'), ('previous', 'قبلی'),
                     ('current', 'بروز'), ('growth', 'ضریب رشد'), ('scope', 'دامنه اثر (فازها)'))
    GENERAL_COLUMNS = (('row', 'ردیف'), ('catalog', 'دسته‌بندی'), ('topic', 'موضوع'),
                       ('scope', 'دامنه اثر (فازها)'), ('rule', 'قانون'), ('kind', 'نوع'))

    def __init__(self, parent: tk.Misc, service: PriceUpdateService, *, category: str | None = None,
                 on_changed=None):
        self.service = service
        self.on_changed = on_changed
        super().__init__(parent, 'قوانین کلی بروزرسانی')
        self.category_var = tk.StringVar(master=self, value=CATALOG_LABELS.get(category or '', ALL_LABEL))
        self.output_format_var = tk.StringVar(master=self, value=EXPORT_PLACEHOLDER)
        self._active = 'params'
        self._build()

    def _build(self) -> None:
        p = palette()
        m = metrics()
        # One set of row actions for the whole page, right-aligned like every
        # table toolbar; it acts on the table whose row was selected last.
        actions = tk.Frame(self.body, bg=p['bg'])
        actions.pack(fill='x', pady=(0, m['gap']))
        for text, command, kind in (('افزودن', self._add, 'create'), ('ویرایش', self._edit, 'neutral'),
                                    ('حذف', self._delete, 'destructive')):
            ttk.Button(actions, text=text, command=command, style=ACTION_STYLES[kind]).pack(
                side='right', padx=m['gap'] // 2)
        self.target_label = tk.Label(actions, bg=p['bg'], fg=p['text_secondary'], font=font('small'))
        self.target_label.pack(side='right', padx=m['gap'])

        tk.Label(self.body, text='پارامترهای کلان — تغییر هر کدام، اقلام فازهای «دامنه اثر» را در اجرای بعد بروز می‌کند',
                 bg=p['bg'], fg=p['text_primary'], font=font('small'), anchor='e').pack(fill='x')
        self.params_table = DataTable(self.body, self.PARAM_COLUMNS, on_open=lambda _k: self._edit(),
                                      empty_text='پارامتری نیست')
        self.params_table.toolbar.pack_forget()
        self.params_table.pack(fill='x')
        self.params_table.tree.configure(height=6)

        tk.Label(self.body, text='قوانین کلی', bg=p['bg'], fg=p['text_primary'], font=font('small'),
                 anchor='e').pack(fill='x', pady=(m['gap'], 0))
        self.rules_table = DataTable(self.body, self.GENERAL_COLUMNS, on_open=lambda _k: self._edit(),
                                     empty_text='قانون کلی‌ای نیست')
        self.rules_table.pack(fill='both', expand=True)
        self.rules_table.toolbar.add_filter('نمایش بر اساس', self.category_var,
                                            (ALL_LABEL, *CATALOG_LABELS.values()), command=self._refresh)
        add_export_control(self.rules_table, self.output_format_var, lambda: preview_export(
            self, self.output_format_var, [label for _k, label in self.GENERAL_COLUMNS],
            self.rules_table.sorted_rows(), 'قوانین کلی بروزرسانی'))
        self.params_table.tree.bind('<<TreeviewSelect>>', lambda _e: self._activate('params'), add='+')
        self.rules_table.tree.bind('<<TreeviewSelect>>', lambda _e: self._activate('rules'), add='+')
        self.add_action('بستن', self.close)
        self._refresh()
        self._activate('params')

    def _activate(self, which: str) -> None:
        self._active = which
        self.target_label.configure(
            text='عمل روی: پارامترهای کلان' if which == 'params' else 'عمل روی: قوانین کلی')

    # --------------------------------------------------------------- data

    def _all_phases(self, catalog: str) -> set[str]:
        return set(self.service.available_phase_codes(None if catalog == 'ALL' else catalog))

    def _refresh(self) -> None:
        ctx = self.service.growth_context()
        items = self.service.list_catalog_items()
        growth = {'usd': ctx['usd'], 'copper': ctx['copper'], 'wage_annual_growth': ctx['wage']}
        rows, keys = [], []
        for parameter in self.service.list_parameters():
            key = parameter['key']
            rate = growth.get(key)
            rows.append(_fa_row((
                parameter['label'] or key, PARAMETER_UNITS.get(key, '—'),
                _format_param_value(parameter['base_value']), _format_param_value(parameter['previous_value']),
                _format_param_value(parameter['current_value']),
                f'{rate:.4f}' if rate is not None else '-',
                _codes_text(_parameter_phases(items, key), self._all_phases('ALL')))))
            keys.append(key)
        self.params_table.set_rows(rows, keys=keys)

        category = CATALOG_VALUES.get(self.category_var.get())
        index = _RuleItemIndex(self.service)
        entries = []
        for catalog, topic, text in _engine_rules(ctx):
            if category and catalog not in ('ALL', category):
                continue
            entries.append((None, catalog, topic, self._all_phases(catalog), text, 'قانون موتور محاسبه (ثابت)'))
        stored_rules = self.service.list_calc_rules(catalog_type=category)
        stored_topics = {rule['description'] for rule in stored_rules}
        for topic, text in MANAGEMENT_RULES:
            if topic not in stored_topics:
                entries.append((None, 'ALL', topic, self._all_phases('ALL'), text,
                                'قانون مدیریت پروژه (مرجع متنی)'))
        for rule in stored_rules:
            phases = index.rule_phases(rule)
            topic = rule['description']
            if phases and not str(rule['affected_phase_codes'] or '').strip():
                # The rule is about an item: its phase number goes beside the name.
                topic = f"{'،'.join(phases)}-{topic}"
            entries.append((rule, rule['catalog_type'], topic,
                            set(phases) or self._all_phases(rule['catalog_type']),
                            _rule_params_summary(rule), 'قانون ثبت‌شده (قابل ویرایش)'))
        entries.sort(key=lambda e: (e[1] != 'ALL', e[0] is not None, _rule_is_reference(e[0] or {}),
                                    _rule_order(e[0] or {})))
        self._rules_by_key = {}
        rows, keys = [], []
        for number, (rule, catalog, topic, phases, text, kind) in enumerate(entries, start=1):
            key = (rule['rule_id'] if rule else
                   f"{'MANAGEMENT' if kind == 'قانون مدیریت پروژه (مرجع متنی)' else 'ENGINE'}:{number}")
            self._rules_by_key[key] = rule
            full = self._all_phases(catalog)
            label = 'همه فازها' if catalog == 'ALL' else f"همه فازهای {CATALOG_LABELS.get(catalog, '')}"
            rows.append(_fa_row((number, RULE_CATALOG_LABELS.get(catalog, catalog), topic,
                                 _codes_text(phases, full, label), text, kind)))
            keys.append(key)
        self.rules_table.set_rows(rows, keys=keys)

    # ------------------------------------------------------------ actions

    def _add(self) -> None:
        if self._active == 'params':
            ParameterDialog187(self, self.service, None, on_saved=self._after_change)
        else:
            RuleOptionsDialog187(self, self.service, rule=None, on_saved=self._after_change,
                                 default_catalog=CATALOG_VALUES.get(self.category_var.get()) or 'ALL')

    def _edit(self) -> None:
        if self._active == 'params':
            key = self.params_table.selected_key()
            if not key:
                messagebox.showinfo('ویرایش', 'یک پارامتر را انتخاب کنید.', parent=self)
                return
            ParameterDialog187(self, self.service, key, on_saved=self._after_change)
            return
        key = self.rules_table.selected_key()
        if not key:
            messagebox.showinfo('ویرایش', 'یک قانون را انتخاب کنید.', parent=self)
            return
        rule = self._rules_by_key.get(key)
        if rule is None:
            text = ('برای ویرایش قوانین مدیریت پروژه، فایل مرجع اکسل را ویرایش و دوباره وارد کنید.'
                    if str(key).startswith('MANAGEMENT:') else
                    'قوانین موتور محاسبه ثابت‌اند؛ اعدادشان از پارامترهای کلان می‌آید.')
            messagebox.showinfo('ویرایش', text,
                                parent=self)
            return
        RuleOptionsDialog187(self, self.service, rule=rule, on_saved=self._after_change)

    def _delete(self) -> None:
        if self._active == 'params':
            key = self.params_table.selected_key()
            if not key:
                messagebox.showinfo('حذف', 'یک پارامتر را انتخاب کنید.', parent=self)
                return
            parameter = self.service.get_parameter(key) or {}
            if not messagebox.askyesno('حذف', f"پارامتر «{parameter.get('label', key)}» حذف شود؟", parent=self):
                return
            try:
                self.service.delete_parameter(key)
            except ValueError as exc:
                messagebox.showinfo('حذف', str(exc), parent=self)
                return
            self._after_change()
            return
        key = self.rules_table.selected_key()
        rule = self._rules_by_key.get(key) if key else None
        if rule is None:
            messagebox.showinfo('حذف', 'یک قانون ثبت‌شده را انتخاب کنید؛ قوانین موتور محاسبه حذف‌شدنی نیستند.',
                                parent=self)
            return
        if messagebox.askyesno('حذف', f"«{rule['description']}» حذف شود؟", parent=self):
            self.service.delete_calc_rule(rule['rule_id'])
            self._after_change()

    def _after_change(self) -> None:
        self._refresh()
        if self.on_changed:
            self.on_changed()


class CalcRuleDialog187(BarkavDialog):
    size_class = 'small'

    def __init__(self, parent: tk.Misc, service: PriceUpdateService, row: dict | None, *, on_saved):
        self.service = service
        self.row = row
        self.on_saved = on_saved
        super().__init__(parent, 'ویرایش قانون' if row else 'افزودن قانون')
        self._render()

    def _render(self) -> None:
        p = palette()
        m = metrics()
        row = self.row or {}
        self.catalog_var = tk.StringVar(value=CATALOG_LABELS.get(row.get('catalog_type', 'MATERIAL')))
        self.description_var = tk.StringVar(value=row.get('description', ''))
        self.phases_var = tk.StringVar(value=row.get('affected_phase_codes', ''))
        # روش محاسبه داخل params_json ذخیره می‌شود (کلید ``method``) تا اسکیمای
        # جدول قوانین دست‌نخورده بماند؛ اینجا به‌جای تایپ دستی JSON، از یک لیست
        # انتخاب می‌شود -- چون «اعمال قوانین» بدون این کلید هیچ اثری ندارد و
        # نوشتنش با دست بی‌سر‌و‌صدا فراموش یا غلط تایپ می‌شد.
        self.method_var = tk.StringVar(value=_rule_method(row) if row else METHOD_OPTIONS[0])
        if self.method_var.get() not in METHOD_OPTIONS:
            self.method_var.set(METHOD_OPTIONS[0])
        self.params_var = tk.StringVar(value=self._params_without_method(row))
        self.rule_text_widget = None
        if row and _rule_is_reference(row):
            self._render_reference_rule(row, p, m)
            return

        for label, variable, values in (
            ('دسته‌بندی', self.catalog_var, tuple(CATALOG_LABELS.values())),
            ('روش محاسبه (روی اقلام این قانون نوشته می‌شود)', self.method_var, METHOD_OPTIONS),
            ('شرح قانون', self.description_var, None),
            ('فازهای تحت تاثیر (خالی = همه؛ مثال: 08 یا 07,09)', self.phases_var, None),
            ('پارامترهای JSON (وزن‌ها و ضرایب)', self.params_var, None),
        ):
            cell = tk.Frame(self.body, bg=p['bg'])
            cell.pack(fill='x', pady=m['gap'] // 2)
            tk.Label(cell, text=label, bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                     anchor='e').pack(fill='x')
            if values is not None:
                ttk.Combobox(cell, textvariable=variable, values=values,
                             state='readonly', justify='right').pack(fill='x')
            else:
                ttk.Entry(cell, textvariable=variable, justify='right').pack(fill='x')

        self.add_action('ذخیره', self._save, style='Success.TButton')
        self.add_action('انصراف', self.close)

    def _render_reference_rule(self, row: dict, p: dict, m: dict) -> None:
        """A rule from «قوانین محاسبه بروز»: its موضوع and its written قانون, both editable."""

        tk.Label(self.body, text=f"دسته‌بندی: {RULE_CATALOG_LABELS.get(row['catalog_type'], row['catalog_type'])}",
                 bg=p['bg'], fg=p['text_secondary'], font=font('small'), anchor='e').pack(fill='x')
        for label, variable in (('موضوع', self.description_var),
                                ('فازهای تحت تاثیر (خالی = همه)', self.phases_var)):
            cell = tk.Frame(self.body, bg=p['bg'])
            cell.pack(fill='x', pady=m['gap'] // 2)
            tk.Label(cell, text=label, bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                     anchor='e').pack(fill='x')
            ttk.Entry(cell, textvariable=variable, justify='right').pack(fill='x')
        tk.Label(self.body, text='قانون (پرامپت)', bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                 anchor='e').pack(fill='x', pady=(m['gap'] // 2, 0))
        self.rule_text_widget = tk.Text(self.body, height=8, wrap='word')
        self.rule_text_widget.tag_configure('rtl', justify='right')
        self.rule_text_widget.pack(fill='both', expand=True)
        params = json.loads(row.get('params_json') or '{}')
        self.rule_text_widget.insert('1.0', str(params.get('rule_text') or ''), 'rtl')
        self.add_action('ذخیره', self._save, style='Success.TButton')
        self.add_action('انصراف', self.close)

    @staticmethod
    def _params_without_method(row: dict) -> str:
        """JSON قانون، بدون کلید ``method`` -- آن کلید ویجت خودش را دارد."""

        try:
            params = json.loads(row.get('params_json') or '{}')
        except (TypeError, ValueError):
            return '{}'
        if not isinstance(params, dict):
            return '{}'
        return json.dumps({k: v for k, v in params.items() if k != 'method'}, ensure_ascii=False)

    def _save(self) -> None:
        description = self.description_var.get().strip()
        if not description:
            messagebox.showwarning('ذخیره', 'شرح قانون نمی‌تواند خالی باشد.', parent=self)
            return
        if self.rule_text_widget is not None:
            params = json.loads(self.row.get('params_json') or '{}')
            params['rule_text'] = self.rule_text_widget.get('1.0', 'end').strip()
            self.service.upsert_calc_rule(
                self.row['rule_id'], catalog_type=self.row['catalog_type'], description=description,
                affected_phase_codes=self.phases_var.get().strip(),
                params_json=json.dumps(params, ensure_ascii=False))
            self.on_saved()
            self.close()
            return
        try:
            params = json.loads(self.params_var.get() or '{}')
        except ValueError:
            messagebox.showwarning('ذخیره', 'پارامترهای JSON نامعتبر است.', parent=self)
            return
        if not isinstance(params, dict):
            messagebox.showwarning('ذخیره', 'پارامترها باید یک شیء JSON باشد، مثل {"wage_weight": 0.4}.',
                                    parent=self)
            return
        params['method'] = self.method_var.get()
        rule_id = self.row['rule_id'] if self.row else None
        self.service.upsert_calc_rule(
            rule_id, catalog_type=CATALOG_VALUES.get(self.catalog_var.get(), 'MATERIAL'),
            description=description, affected_phase_codes=self.phases_var.get().strip(),
            params_json=json.dumps(params, ensure_ascii=False))
        self.on_saved()
        self.close()


class NeedsReviewWindow187(BarkavWindow):
    """«موارد در حال بررسی» -- هم پس از هر اجرا خودکار باز می‌شود، هم با دکمه‌ی مستقل."""

    size_class = 'medium'

    def __init__(self, parent: tk.Misc, service: PriceUpdateService):
        self.service = service
        super().__init__(parent, 'موارد در حال بررسی')
        self._build()

    def _build(self) -> None:
        columns = (
            ('row', 'ردیف'), ('category', 'دسته‌بندی'), ('description', 'شرح'),
            ('forecast_rate', 'قیمت بروز'), ('method', 'روش اعمال‌شده'), ('reason', 'دلیل بررسی'),
        )
        table = DataTable(self.body, columns, empty_text='ردیفی نیازمند بررسی نیست')
        table.pack(fill='both', expand=True)
        export_var = tk.StringVar(master=self, value=EXPORT_PLACEHOLDER)
        add_export_control(table, export_var, lambda: preview_export(
            self, export_var, [label for _key, label in columns], table.sorted_rows(), 'موارد در حال بررسی'))
        rows = self.service.needs_review_items()
        table.set_rows([
            _fa_row((i + 1, CATALOG_LABELS.get(r['catalog_type'], r['catalog_type']), r['description'],
                     f"{r['forecast_rate']:,}", r['executed_method'] or '-', r['review_reason'] or '-'))
            for i, r in enumerate(rows)
        ])
        self.add_action('بستن', self.close)


class SnapshotHistoryWindow187(BarkavWindow):
    """«سابقه بروزرسانی» -- هر اجرا یک ردیف، هرگز پاک/بازنویسی نمی‌شود."""

    size_class = 'medium'

    def __init__(self, parent: tk.Misc, service: PriceUpdateService):
        self.service = service
        super().__init__(parent, 'سابقه بروزرسانی')
        self._build()

    def _build(self) -> None:
        columns = (
            ('row', 'ردیف'), ('estimate_date', 'تاریخ براورد'), ('trigger', 'نوع اجرا'),
            ('items', 'تعداد اقلام'), ('review', 'نیازمند بررسی'), ('run_at', 'زمان اجرا'),
        )
        table = DataTable(self.body, columns, empty_text='هنوز بروزرسانی‌ای اجرا نشده است')
        table.pack(fill='both', expand=True)
        export_var = tk.StringVar(master=self, value=EXPORT_PLACEHOLDER)
        add_export_control(table, export_var, lambda: preview_export(
            self, export_var, [label for _key, label in columns], table.sorted_rows(), 'سابقه بروزرسانی'))
        snapshots = self.service.list_snapshots()
        rows = []
        for i, s in enumerate(snapshots):
            totals = json.loads(s['totals_json'] or '{}')
            rows.append(_fa_row((
                i + 1, s['estimate_date_shamsi'] or '-',
                'دستی' if s['trigger_kind'] == 'manual' else 'زمان‌بندی‌شده',
                totals.get('item_count', 0), totals.get('needs_review', 0),
                f"{_shamsi(s['run_at'])} {str(s['run_at'])[11:16]}",
            )))
        table.set_rows(rows)
        self.add_action('بستن', self.close)


class DetailsWindow187(BarkavWindow):
    """«جزئیات بروزرسانی» -- لیست همه‌ی اقلام با ستون‌های تشخیصی + دیالوگ ویرایش کامل.

    طراحی: فهرست + دیالوگ ویرایش (مثل PriceEditor187/CalcRuleDialog187)، نه
    اسپردشیت درون‌سطری -- چون DataTable فعلی از ویجت‌های تعبیه‌شده داخل هر
    سلول پشتیبانی نمی‌کند. رنگ‌بندی ضریب از همون سه تگ وضعیت موجود در کیت
    استفاده می‌کند (approved=سبز/مثبت, rejected=قرمز/کاهشی, pending=زرد/نیاز
    به بررسی یا اختلاف روش پیشنهادی-اجرایی) به‌جای اختراع رنگ جدید.
    """

    size_class = 'large'

    def __init__(self, parent: tk.Misc, service: PriceUpdateService, *, on_changed=None,
                 category: str | None = None, phase: str | None = None, item: str | None = None):
        self.service = service
        self.on_changed = on_changed
        self._initial_scope = (category, phase, item)
        super().__init__(parent, 'جزئیات بروزرسانی')
        self.output_format_var = tk.StringVar(master=self, value=EXPORT_PLACEHOLDER)
        self._build()

    def _build(self) -> None:
        columns = (
            ('row', 'ردیف'), ('updated_at', 'تاریخ ویرایش'), ('catalog_type', 'دسته‌بندی'),
            ('description', 'شرح'), ('unit_price', 'قیمت واحد'), ('previous_rate', 'قیمت براورد قبلی'),
            ('phase', 'شماره فاز'), ('brand', 'برند مصالح'), ('ratio', 'ضریب افزایش/کاهش'),
            ('suggested_method', 'روش استخراج پیشنهادی'), ('base_price', 'قیمت مبنا'),
            ('forecast_rate', 'قیمت بروز'), ('executed_method', 'روش استخراج اجرایی'),
            ('basis', 'مبنای محاسبه'),
            # «شامل همه‌ی ۷ زیرستون شاخص وزنی»: one column per weight, '-' where
            # the row's method does not use weights.
            *((f'weight_{key}', f'وزن {label}') for key, label in WEIGHT_KEYS),
        )
        self._columns = columns
        self.table = DataTable(self.body, columns, on_open=self._edit_selected,
                                empty_text='قلمی ثبت نشده است', checkable=True)
        self.table.pack(fill='both', expand=True)
        category, phase, item = self._initial_scope
        self.scope = _ScopeFilter(self, self.table, self.service, category=category, phase=phase,
                                  item=item, on_change=self._refresh)
        add_export_control(self.table, self.output_format_var, lambda: preview_export(
            self, self.output_format_var, [label for _key, label in self._columns],
            selected_table_rows(self.table), 'جزئیات بروزرسانی', summary_lines=[self.scope.note()]))
        self.table.add_action('ویرایش', self._edit_selected, 'neutral')
        self.table.add_action('قوانین این قلم', self._edit_rule_options, 'neutral')
        self.add_action('بستن', self.close)
        self._refresh()

    def _edit_rule_options(self) -> None:
        row = self._selected()
        if not row:
            messagebox.showinfo('قوانین این قلم', 'یک ردیف را انتخاب کنید.', parent=self)
            return
        RuleOptionsDialog187(self, self.service, item=row, on_saved=self._after_save)

    def _refresh(self) -> None:
        if self.scope.item:
            item = self.service.get_catalog_item(self.scope.item)
            rows = [item] if item and item['active'] else []
        else:
            rows = self.service.list_catalog_items(catalog_type=self.scope.category,
                                                   phase_code=self.scope.phase)
        self._by_key = {r['price_id']: r for r in rows}
        display = []
        status = {}
        for i, r in enumerate(rows):
            ratio = (r['forecast_rate'] / r['estimate_rate']) if r['estimate_rate'] else 1.0
            display.append(_fa_row((
                fa(i + 1), _shamsi(r['updated_at']), CATALOG_LABELS.get(r['catalog_type'], r['catalog_type']),
                r['description'], fa(f"{r['estimate_rate']:,}"), fa(f"{r['previous_rate']:,}"),
                _phase_label(r['phase_codes']), r['brand'] or '-',
                f"{fa(f'{ratio:.3f}')}", r['suggested_method'] or '-',
                fa(f"{_base_price(r):,}"), fa(f"{r['forecast_rate']:,}"), r['executed_method'] or '-',
                _basis_text(r), *_weight_cells(r),
            )))
            differs = bool(r['executed_method']) and r['executed_method'] != r['suggested_method']
            if r['needs_review'] or differs:
                status[i] = 'pending'
            elif ratio > 1.0001:
                status[i] = 'approved'
            elif ratio < 0.9999:
                status[i] = 'rejected'
        self.table.set_rows(display, status=status, keys=[r['price_id'] for r in rows])

    def _selected(self) -> dict | None:
        key = self.table.selected_key()
        return self._by_key.get(key) if key else None

    def _edit_selected(self, *_a) -> None:
        row = self._selected()
        if not row:
            messagebox.showinfo('ویرایش', 'یک ردیف را انتخاب کنید.', parent=self)
            return
        DetailItemDialog187(self, self.service, row, on_saved=self._after_save)

    def _after_save(self) -> None:
        self._refresh()
        if self.on_changed:
            self.on_changed()


def _row_params(row: dict) -> dict:
    try:
        params = json.loads(row.get('calc_params_json') or '{}')
    except (TypeError, ValueError):
        return {}
    return params if isinstance(params, dict) else {}


def _base_price(row: dict) -> int:
    """قیمت مبنا -- قیمت تحقیق‌شده، یا میانگین قیمت‌های وب، وگرنه خودِ برآورد اولیه."""

    params = _row_params(row)
    try:
        researched = float(params.get('researched_price') or 0)
    except (TypeError, ValueError):
        researched = 0.0
    if researched:
        return round(researched)
    prices = [p for p in params.get('web_prices', []) if isinstance(p, (int, float)) and p]
    if row.get('calc_method') == calc.METHOD_WEB and prices:
        return round(sum(prices) / len(prices))
    return int(row.get('estimate_rate') or 0)


def _basis_text(row: dict) -> str:
    """How this row's بروز is reached, in words: the workbook's own note, else its sources."""

    params = _row_params(row)
    for key in ('basis_note', 'tariff_basis', 'source'):
        text = str(params.get(key) or '').strip()
        if text:
            return text
    refs = params.get('peer_refs') or []
    if refs:
        return 'هم‌تراز با ردیف‌های ' + '، '.join(fa(str(r).split(':', 1)[-1]) for r in refs)
    return '-'


def _weight_cells(row: dict) -> list[str]:
    params = _row_params(row)
    cells = []
    for key, _label in WEIGHT_KEYS:
        try:
            value = float(params.get(f'weight_{key}') or 0)
        except (TypeError, ValueError):
            value = 0.0
        cells.append(fa(f'{value:.2f}') if value else '-')
    return cells


class DetailItemDialog187(BarkavDialog):
    """ویرایش کامل یک قلم: روش استخراج، سایت‌های وب، ضرایب ترکیبی وزنی، مالیات/حمل."""

    size_class = 'large'

    def __init__(self, parent: tk.Misc, service: PriceUpdateService, row: dict, *, on_saved):
        self.service = service
        self.row = row
        self.on_saved = on_saved
        try:
            self.params = json.loads(row.get('calc_params_json') or '{}')
        except (TypeError, ValueError):
            self.params = {}
        super().__init__(parent, f"جزئیات: {row['description']}", scrollable=True)
        self._render()

    def _render(self) -> None:
        p = palette()
        m = metrics()
        row = self.row

        info = tk.Frame(self.body, bg=p['bg'])
        info.pack(fill='x', pady=(0, m['gap']))
        tk.Label(info, text=f"{CATALOG_LABELS.get(row['catalog_type'], row['catalog_type'])} — {row['description']}",
                 bg=p['bg'], fg=p['text_primary'], font=font('title'), anchor='e').pack(fill='x')

        self.method_var = tk.StringVar(value=row.get('suggested_method') or METHOD_OPTIONS[0])
        self.phase_var = tk.StringVar(value=row.get('phase_codes', ''))
        self.brand_var = tk.StringVar(value=row.get('brand', ''))
        self.tax_var = tk.StringVar(value=fa(str(self.params.get('tax_rate', 0))))
        self.carry_var = tk.StringVar(value=fa(str(self.params.get('carry_rate', 0))))
        self.site_vars = [tk.StringVar(value=s) for s in (self.params.get('web_sites', ['', '', ''])
                                                            + ['', '', ''])[:3]]
        self.web_prices_var = tk.StringVar(
            value='، '.join(fa(_format_param_value(v)) for v in self.params.get('web_prices', [])
                           if isinstance(v, (int, float)) and v))
        self.weight_vars = {
            key: tk.StringVar(value=fa(str(self.params.get(f'weight_{key}', 0)))) for key, _label in WEIGHT_KEYS
        }
        self.prompt_var = tk.StringVar(value=row.get('ai_prompt', ''))
        self.regional_var = tk.StringVar(value=fa(str(self.params.get('regional_factor', 1))))
        self.connection_var = tk.StringVar(value=fa(str(self.params.get('connection_factor', 1))))
        self.researched_var = tk.StringVar(
            value=fa(f"{float(self.params['researched_price']):,.0f}") if self.params.get('researched_price') else '')

        tk.Label(self.body, text=f'مبنای محاسبه: {_basis_text(row)}', bg=p['bg'], fg=p['text_secondary'],
                 font=font('small'), anchor='e', justify='right', wraplength=760).pack(fill='x')

        basic = tk.Frame(self.body, bg=p['bg'])
        basic.pack(fill='x', pady=m['gap'] // 2)
        basic.columnconfigure((0, 1), weight=1, uniform='field')
        for index, (label, variable, kind, values) in enumerate((
            ('شماره فاز (مثال: 08 یا 07,09)', self.phase_var, 'combo', self._phase_choices()),
            ('برند مصالح', self.brand_var, 'entry', None),
            ('روش استخراج پیشنهادی', self.method_var, 'readonly_combo', METHOD_OPTIONS),
            ('مالیات (کسری اعشاری، مثال 0.10)', self.tax_var, 'entry', None),
            ('حمل و نقل (کسری اعشاری، مثال 0.30)', self.carry_var, 'entry', None),
            ('ضریب منطقه‌ای', self.regional_var, 'entry', None),
            ('ضریب اتصال', self.connection_var, 'entry', None),
            ('قیمت مبنای تحقیق‌شده (تومان؛ اگر پر باشد مبنای ضریب است)', self.researched_var, 'entry', None),
        )):
            cell = tk.Frame(basic, bg=p['bg'])
            cell.grid(row=index // 2, column=1 - (index % 2), sticky='ew', padx=m['gap'] // 2, pady=m['gap'] // 2)
            tk.Label(cell, text=label, bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                     anchor='e').pack(fill='x')
            if kind == 'entry':
                ttk.Entry(cell, textvariable=variable, justify='right').pack(fill='x')
            elif kind == 'combo':
                ttk.Combobox(cell, textvariable=variable, values=values, justify='right').pack(fill='x')
            else:
                combo = ttk.Combobox(cell, textvariable=variable, values=values, state='readonly', justify='right')
                combo.pack(fill='x')
                combo.bind('<<ComboboxSelected>>', lambda _e: self._sync_method_sections(), add='+')

        self.sites_section = tk.Frame(self.body, bg=p['bg'])
        self.sites_section.pack(fill='x', pady=m['gap'] // 2)
        tk.Label(self.sites_section, text='سایت‌های منتخب (فقط برای روش وب) + قیمت‌های استعلامی (جداکننده: «،»)',
                 bg=p['bg'], fg=p['text_secondary'], font=font('small'), anchor='e').pack(fill='x')
        self.site_entries = []
        for variable in self.site_vars:
            entry = ttk.Entry(self.sites_section, textvariable=variable, justify='right')
            entry.pack(fill='x', pady=2)
            self.site_entries.append(entry)
        self.web_prices_entry = ttk.Entry(self.sites_section, textvariable=self.web_prices_var, justify='right')
        self.web_prices_entry.pack(fill='x', pady=2)

        self.weights_section = tk.Frame(self.body, bg=p['bg'])
        self.weights_section.pack(fill='x', pady=m['gap'] // 2)
        tk.Label(self.weights_section, text='ضرایب ترکیبی وزنی (فقط برای شاخص ترکیبی/تعرفه وزنی)',
                 bg=p['bg'], fg=p['text_secondary'], font=font('small'), anchor='e').pack(fill='x')
        weights_grid = tk.Frame(self.weights_section, bg=p['bg'])
        weights_grid.pack(fill='x')
        weights_grid.columnconfigure(tuple(range(4)), weight=1, uniform='weight')
        self.weight_entries = []
        for index, (key, label) in enumerate(WEIGHT_KEYS):
            cell = tk.Frame(weights_grid, bg=p['bg'])
            cell.grid(row=index // 4, column=3 - (index % 4), sticky='ew', padx=3, pady=3)
            tk.Label(cell, text=label, bg=p['bg'], fg=p['text_secondary'], font=font('small'),
                     anchor='e').pack(fill='x')
            entry = ttk.Entry(cell, textvariable=self.weight_vars[key], justify='right', width=8)
            entry.pack(fill='x')
            self.weight_entries.append(entry)

        executed = tk.Frame(self.body, bg=p['bg'])
        executed.pack(fill='x', pady=m['gap'] // 2)
        differs = bool(row.get('executed_method')) and row['executed_method'] != row.get('suggested_method')
        tk.Label(executed, text=f"روش استخراج اجرایی (محاسبه‌شده): {row.get('executed_method') or '-'}",
                 bg=(p['row_pending'] if differs else p['bg']), fg=p['text_primary'], anchor='e',
                 font=font('small')).pack(fill='x')

        tk.Label(self.body, text='پرامپت هوش مصنوعی این ردیف', bg=p['bg'], fg=p['text_secondary'],
                 font=font('small'), anchor='e').pack(fill='x', pady=(m['gap'], 0))
        self.prompt_text = tk.Text(self.body, height=4, wrap='word')
        self.prompt_text.pack(fill='x')
        self.prompt_text.insert('1.0', self.prompt_var.get())

        self._sync_method_sections()
        self.add_action('ذخیره', self._save, style='Success.TButton')
        self.add_action('انصراف', self.close)

    def _phase_choices(self) -> tuple[str, ...]:
        return tuple(f'{code} - {name}' for code, name in PHASE_NAMES.items())

    def _sync_method_sections(self) -> None:
        method = self.method_var.get()
        site_state = 'normal' if method == calc.METHOD_WEB else 'disabled'
        for entry in self.site_entries + [self.web_prices_entry]:
            entry.configure(state=site_state)
        weight_state = 'normal' if method in (calc.METHOD_WEIGHTED_INDEX, calc.METHOD_SERVICE_TARIFF) else 'disabled'
        for entry in self.weight_entries:
            entry.configure(state=weight_state)

    def _save(self) -> None:
        def as_float(raw: str) -> float:
            try:
                return float(en(raw) or 0)
            except ValueError:
                return 0.0

        params = dict(self.params)
        params['tax_rate'] = as_float(self.tax_var.get())
        params['carry_rate'] = as_float(self.carry_var.get())
        params['regional_factor'] = as_float(self.regional_var.get()) or 1.0
        params['connection_factor'] = as_float(self.connection_var.get()) or 1.0
        researched = parse_int(en(self.researched_var.get()))
        if researched:
            params['researched_price'] = researched
        else:
            params.pop('researched_price', None)
        params['web_sites'] = [v.get().strip() for v in self.site_vars]
        # «،» separates prices, «,» may be a thousands separator inside one.
        params['web_prices'] = [value for value in (
            _parse_param_float(en(x.strip())) for x in re.split(r'[،;]', self.web_prices_var.get()) if x.strip())
            if value]
        weights_before = {key: float(self.params.get(f'weight_{key}') or 0) for key, _label in WEIGHT_KEYS}
        for key, _label in WEIGHT_KEYS:
            params[f'weight_{key}'] = as_float(self.weight_vars[key].get())
        if any(abs(params[f'weight_{key}'] - weights_before[key]) > 1e-9 for key, _label in WEIGHT_KEYS):
            # Weights the operator set by hand are meant to drive the ratio: the
            # live weighted index then joins the row's candidates (floored at
            # the wage growth as always).
            params['index_mode'] = 'live'

        phase_raw = self.phase_var.get()
        phase_codes = phase_raw.split(' - ', 1)[0].strip() if ' - ' in phase_raw else phase_raw.strip()

        self.service.upsert_catalog_item(
            self.row['price_id'],
            calc_method=self.method_var.get(),
            suggested_method=self.method_var.get(),
            calc_params_json=json.dumps(params, ensure_ascii=False),
            phase_codes=phase_codes,
            brand=self.brand_var.get().strip(),
            ai_prompt=self.prompt_text.get('1.0', 'end').strip(),
        )
        self.on_saved()
        self.close()


def install_price_update_187(app) -> None:
    """Register the tab beside PricePanel187/ProjectPlanPanel187 in مدیریت پروژه."""

    if getattr(app, '_price_update_installed_187', False):
        return
    app._price_update_installed_187 = True
    service = PriceUpdateService(app.rich.db, app.rich.base_dir)
    app.price_update_service187 = service
    panel = PriceUpdatePanel187(app.report_nb, service=service, rich_db=app.rich.db,
                                 on_changed=getattr(app, 'refresh_reports', None))
    app.report_nb.add(panel, text='بروزرسانی قیمت‌ها')
    app.price_update_panel187 = panel
