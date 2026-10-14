from __future__ import annotations

import asyncio
import json
import logging
import math
import mimetypes
import os
import subprocess
import sys
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path
import re
import sqlite3
import threading
import time
from queue import Empty, Queue
from urllib import request as urlrequest
from datetime import date, datetime, timedelta
import tkinter as tk
from tkinter import Toplevel
from tkinter import filedialog, font as tkfont, messagebox, ttk

import dashboard_stage14
import dashboard_stage18_6 as v186
import dashboard_stage18 as v18
import dashboard_stage18_1 as v181
import dashboard_stage18_2 as v182
from dashboard_stage18 import (
    gregorian_to_shamsi, normalize_shamsi, shamsi_to_gregorian,
)
from dashboard_stage12 import money
import ui_stage18_6 as legacy_ui
from barkav_themes.engine import stripe_tree
from barkav_themes.tokens import get_theme, mix
from barkav_ui import art
from barkav_ui.tabs import LegacyTabStrip, TabStrip, notebook_depth
from barkav_ui.table import apply_tree_rtl as apply_tree_rtl_kit
from barkav_ui.theme import font as kit_font
from barkav_ui.line_icons import icon as line_icon_187, tile as line_tile_187
from barkav_ui.overflow import watch as watch_overflow_187
from barkav_ui.badges import feature_tile as feature_tile_187, glass_tile as glass_tile_187, \
    progress_ring as progress_ring_187
from barkav_ui.bidi import fa_grouped_number, rtl as rtl_187
from barkav_ui.phase_groups import PhaseGroups, PhaseLegend
from barkav_ui.rail import NavRail
from barkav_ui.skin import BUTTON_HEIGHT as BUTTON_HEIGHT_187, match_checkbutton_background
from barkav_ui.row_overlay import CHECK_COLUMN as CHECK_COLUMN_187, decorate as decorate_rows_187
from barkav_ui.tree_filter import filter_rows as filter_tree_rows_187, restore_all as restore_tree_rows_187
from barkav_ui.window_tabs import WindowTabs
from barkav_ui.window import (
    BarkavDialog, BarkavWindow, CommandPalette, PopupMenu, apply_dark_caption,
    bind_main_window_focus_on_destroy, center_toplevel_on_screen, fade_in,
    hide_for_fade, keep_above_parent, normalize_window_rtl,
    show_inline_error, show_toast, attach_tooltip,
)
from barkav.features.dashboard import SmartTable, add_tooltip
from contractors_stage18_7 import ContractorsPanel187
from contractor_store_stage18_7 import load_contracts, paid_total
from telegram_history_import import import_telegram_export
from instance_guard_v185 import ProjectInstanceGuard, bring_process_window_to_front
from phase_intelligence_v175 import PHASE_HINTS
from project_registry import ProjectEntry, ProjectRegistry
from data_entry_rules187 import (
    LAND_TITLE, LAND_MIXED, LAND_PARTS, LAND_MODE_KEY, LAND_MODES, SORT_SETTING,
    land_payment_mode, land_payment_subtype, normalize_land_record, normalize_land_parts,
    row_order as data_entry_row_order, insert_after as insert_data_entry_rows,
    previous_debt,
)
from transaction_titles187 import TRANSACTION_TITLES, transaction_title, MANAGER_TITLE, normalize_manager_salary
from budget_rich_v163 import norm
from cost_allocation_stage18_7 import cost_type_of as cost_type_of_187, phase_of as phase_of_187
from construction_cost_rules187 import manager_fee as construction_manager_fee
from runtime_base import frozen, load_local_secrets
from financial_calendar_stage18_7 import (
    FinancialCalendarDialog187,
    FinancialMessagesDialog187,
    StartupMessagesPopup187,
    is_startup_alert_due_187,
    unread_message_events_187,
    upcoming_events_187,
)
from project_plan_stage18_7 import _totals as plan_totals_187
from reports_stage18_7 import PhaseDetailDialog187, install_report_controls_187
from ui_stage18_3 import (
    bind_grouped_number_fa, en, fa, group_int_fa, group_decimal_fa,
    parse_int, parse_decimal, _clean_int, _clean_decimal,
)
from numeric_entry_stage18_7 import format_numeric_entry
from ui_stage18_7 import (
    DEFAULT_THEME_ID_187,
    activate_theme_bridge_187,
    palette_187,
    BACKGROUND_COLORS_187,
    available_font_families_187,
    available_font_weights_187,
    font_catalog_families_187,
    font_display_name_187,
    font_status_label_187,
    resolve_font_family_187,
    resolve_font_weight_187,
    style_ttk_187,
    theme_id_187,
    theme_metrics_187,
    theme_selection_187,
)
from v18_store import load_ui, save_profile, save_ui
from sales_claims_stage18_7 import (
    SalesClaimsPanel187,
    ShamsiDatePicker187,
    is_temporary_sales_finance_pending_187,
    show_export_preview_187,
)
from inventory_stage18_7 import InventoryPanel187
from rate_policy_stage18_7 import DEFAULT_RATE_BASIS_187, RATE_BASIS_CHOICES_187
from loan_service import LoanService, _add_months
import liquidity_service
import data_entry_read_service
import rtl_text187
from data_entry_extras_ui import (
    HIDDEN_FILTER as HIDDEN_FILTER_187, HIDDEN_LABEL as HIDDEN_LABEL_187,
    hidden_rows as hidden_rows_187, show_rows_again as show_rows_again_187,
)
from finance_db import _id as _finance_id_187, _now as _finance_now_187
from data_entry_mapping_187 import map_data_entry_values_187


VERSION = '18.7'
DISPLAY_VERSION_187 = '19.1.1'

# The sales workspace is presented as درآمد; the internal keys and the
# inherited tab text it is built from stay unchanged.
SALES_TAB_187 = 'درآمد'
# 'گزارش‌گیری' undersold the tab: it holds the estimate plan, the price
# catalogue and the phase control, which is project management.
REPORTS_TAB_187 = 'مدیریت پروژه'
BASE_DIR = v186.BASE_DIR
DB = v186.DB
SERVICE = v186.SERVICE

TGJU_GOLD_URL_187 = 'https://www.tgju.org/profile/geram18'

def contractor_commitments_30d_187(
    contracts, start: date, end: date, issued_by_contract=None,
) -> tuple[int, list[dict]]:
    """Moved to liquidity_service.contractor_commitments_30d.

    Resolves ``shamsi_to_gregorian`` from this module at call time, as the
    original body did, so existing callers and tests see the same converter.
    """
    return liquidity_service.contractor_commitments_30d(
        contracts, start, end, issued_by_contract, to_gregorian=shamsi_to_gregorian,
    )


thirty_day_liquidity_breakdown_187 = liquidity_service.thirty_day_liquidity_breakdown


MANAGER_RECEIPT_COLUMNS_187 = (
    ('row', 'ردیف', 78), ('date', 'تاریخ شمسی', 125),
    ('amount', 'مبلغ (تومان)', 175), ('desc', 'توضیحات', 420),
)


def manager_account_summary_187(*, construction_cost: int, land_purchase_cost: int,
                                manager_receipts: int, transaction_cash: int,
                                actual_cash: int, manager_percent: float,
                                expected_petty_cash: int | None = None) -> dict[str, int]:
    """Return the manager-account figures shown by the 18.7.1 workspace.

    construction_cost is the raw total of all phases before management fees;
    land_purchase_cost is its phase-01 portion. Manager receipts never reduce
    this fee basis. The manager_percent argument remains for caller compatibility.

    The manual actual-cash figure is deliberately supplied by the UI. It is
    not persisted here, so calculating the screen never changes project data.
    A positive account difference is owed to petty cash; a negative value
    is a claim against petty cash.
    """
    construction_cost = int(construction_cost or 0)
    land_purchase_cost = int(land_purchase_cost or 0)
    manager_receipts = int(manager_receipts or 0)
    transaction_cash = int(transaction_cash or 0)
    actual_cash = int(actual_cash or 0)
    eligible_costs = max(0, construction_cost - land_purchase_cost)
    manager_fee = construction_manager_fee(eligible_costs)
    before_difference = manager_fee - manager_receipts
    expected_cash = transaction_cash if expected_petty_cash is None else int(expected_petty_cash)
    account_difference = expected_cash - actual_cash
    return {
        'construction_cost': eligible_costs + manager_fee,
        'transaction_cash': transaction_cash,
        'actual_cash': actual_cash,
        'account_difference': account_difference,
        'eligible_costs': eligible_costs,
        'manager_fee': manager_fee,
        'manager_receipts': manager_receipts,
        'before_difference': before_difference,
        'with_difference': before_difference - account_difference,
    }


def _manager_formula_text_187(values, percent, reconciliation) -> str:
    """Format the manager basis and the requested petty-cash formula in RTL."""
    basis = fa(f"{int(values['eligible_costs']):,}")
    percent_display = int(percent) if float(percent).is_integer() else percent
    return (
        'کل هزینه‌های مشمول حقوق مدیر = '
        f"هزینه فازهای ۰۲ تا ۳۲: {basis} تومان | "
        f"حقوق مدیر: {fa(percent_display)}٪ × {basis} = "
        f"{fa(f'{int(values['manager_fee']):,}')} تومان\n"
        'اختلاف حساب = کل ورودی − خروجی غیرساخت − هزینه ساخت − هزینه فاز خرید زمین − موجودی تنخواه\n'
        f"{fa(format(int(reconciliation['total_in']), ','))} − "
        f"{fa(format(int(reconciliation['total_out']), ','))} − "
        f"{fa(format(int(reconciliation['construction_cost']), ','))} − "
        f"{fa(format(int(reconciliation['land_purchase_cost']), ','))} − "
        f"{fa(format(int(reconciliation['actual_cash']), ','))} = "
        f"{fa(format(int(reconciliation['account_difference']), ','))} تومان\n"
        'مثبت: بدهکار به تنخواه | منفی: طلبکار از تنخواه'
    )


def fetch_tgju_gold_toman(timeout: float = 8.0) -> tuple[int, str]:
    """Fetch the current 18-karat gold price from the same TGJU source as USD.

    TGJU profile values are published in rial; the settings UI stores display
    prices in toman, matching ``fetch_tgju_usd_toman``.
    """
    req = urlrequest.Request(
        TGJU_GOLD_URL_187,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 BARKAV/18.7',
            'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.6',
        },
    )
    with urlrequest.urlopen(req, timeout=timeout) as response:
        html = response.read().decode('utf-8', 'ignore')
    patterns = (
        r'نرخ\s*فعلی\s*</[^>]+>\s*<[^>]+>\s*([0-9۰-۹٠-٩,٬]+)',
        r'نرخ\s*فعلی\s*[:：]*\s*</?[^>]*>\s*([0-9۰-۹٠-٩,٬]{5,})',
        r'نرخ\s*فعلی\s*[:：]+\s*([0-9۰-۹٠-٩,٬]{5,})',
    )
    raw = ''
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            raw = match.group(1)
            break
    if not raw:
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text)
        match = re.search(r'نرخ\s*فعلی\s*[:：]*\s*([0-9۰-۹٠-٩,٬]{5,})', text)
        if match:
            raw = match.group(1)
    rial = parse_int(raw)
    if rial <= 0:
        raise ValueError('نرخ فعلی طلا در صفحه TGJU پیدا نشد.')
    return round(rial / 10), datetime.now().isoformat(timespec='seconds')


class _LineFreeGrid187:
    """Truthy no-op sentinel preventing inherited code from restoring grid rules."""

    _dead = True
    vlines: tuple = ()
    hlines: tuple = ()
    column_color = ''
    row_color = ''
    header_color = ''

    @staticmethod
    def schedule():
        return None


class _HorizontalTreeSeparator187:
    """A one-pixel row divider without restoring the old ruled table grid."""

    _barkav_horizontal_only187 = True

    def __init__(self, tree: ttk.Treeview, color: str):
        self.tree = tree
        self.color = color
        self.vlines: tuple = ()
        self.hlines: list[tk.Frame] = []
        self._dead = False
        self._pending = False
        for event in ('<Configure>', '<MouseWheel>', '<ButtonRelease-1>', '<KeyRelease>',
                      '<<TreeviewSelect>>'):
            tree.bind(event, lambda _event: self.schedule(), add='+')
        self.schedule()

    def _line(self, index: int) -> tk.Frame:
        while len(self.hlines) <= index:
            self.hlines.append(tk.Frame(self.tree, bd=0, highlightthickness=0))
        line = self.hlines[index]
        line.configure(bg=self.color)
        return line

    def schedule(self):
        if self._dead or self._pending:
            return
        self._pending = True
        try:
            self.tree.after_idle(self.update)
        except tk.TclError:
            self._dead = True

    def update(self):
        self._pending = False
        if self._dead:
            return
        try:
            if not self.tree.winfo_exists():
                self._dead = True
                return
            width = max(1, self.tree.winfo_width())
            height = max(1, self.tree.winfo_height())
            used = 0
            for item in self.tree.get_children(''):
                bbox = self.tree.bbox(item)
                if not bbox:
                    continue
                _x, y, _row_width, row_height = bbox
                line_y = y + row_height - 1
                if 0 < line_y < height:
                    self._line(used).place(x=0, y=line_y, width=width, height=1)
                    used += 1
            for line in self.hlines[used:]:
                line.place_forget()
        except tk.TclError:
            self._dead = True

    def destroy(self):
        self._dead = True
        for line in self.hlines:
            try:
                line.destroy()
            except tk.TclError:
                pass


class _DetachedGridTree187:
    """Terminate already-queued legacy grid callbacks without touching Tk."""

    @staticmethod
    def winfo_exists():
        return False


def _suppress_inherited_grid_187(tree, *, light=False):
    """Make every legacy grid attachment a no-op in the active 18.7 process."""
    del light
    tree._barkav_line_free_187 = True
    horizontal = getattr(tree, '_barkav_horizontal_separator_overlay187', None)
    if horizontal is not None and not getattr(horizontal, '_dead', True):
        # Keep the explicitly requested horizontal dividers while the legacy
        # attachment points remain unable to recreate a full cell grid.
        horizontal.schedule()
        return horizontal
    overlay = getattr(tree, '_barkav_grid_overlay', None)
    if overlay is not None:
        overlay._dead = True
        for line in (*getattr(overlay, 'vlines', ()), *getattr(overlay, 'hlines', ())):
            try:
                line.destroy()
            except tk.TclError:
                pass
        if hasattr(overlay, 'tree'):
            overlay.tree = _DetachedGridTree187()
    tree._barkav_grid_overlay = _LineFreeGrid187()
    return tree._barkav_grid_overlay


# The inherited dashboards imported their attachment functions by value, so
# setting a flag later is too late for lazily refreshed tabs. Redirect those
# three active call sites for this 18.7 process; historical source stays intact.
v186.attach_tree_grid_186 = _suppress_inherited_grid_187
v186.v185.attach_tree_grid_185 = _suppress_inherited_grid_187
v186.v184.attach_tree_grid_184 = _suppress_inherited_grid_187


def _without_check_glyph_187(value):
    """A table cell as a file or preview shows it: without the ☐/☑ the
    screen draws in front of a row number (operator report, 2026-09-27:
    the export preview's ردیف read '☐ ۱')."""

    if isinstance(value, str) and value[:1] in ('☐', '☑'):
        return value[1:].lstrip()
    return value


def _install_clean_report_rows_187() -> None:
    import dashboard_stage12 as v12

    original = v12.SmartTable.current_report_rows
    if getattr(original, '_barkav_clean187', False):
        return

    def current_report_rows(self, selected_only=False):
        headers, rows = original(self, selected_only)
        return headers, [[_without_check_glyph_187(value) for value in row] for row in rows]

    current_report_rows._barkav_clean187 = True
    # Every SmartTable in the active app is stage 12's; Excel, PDF, print,
    # copy and the export previews all read their rows through this one.
    v12.SmartTable.current_report_rows = current_report_rows


_install_clean_report_rows_187()


activate_theme_bridge_187()
# Stage186 imported these callables by value. Redirect only inside this 18.7
# process so every inherited surface resolves the selected Theme 1/2 tokens.
v186.palette_186 = palette_187
v186.style_ttk_186 = style_ttk_187
v186.DARK_186.update(palette_187(False))
v186.LIGHT_186.update(palette_187(True))


def _colour_luma_187(widget, colour) -> float:
    """Relative luminance 0..1 of any Tk colour spec, system names included."""
    try:
        r, g, b = (value / 65535 for value in widget.winfo_rgb(str(colour)))
    except tk.TclError:
        return 0.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def dashboard_font_187(widget, size: int, role: str = 'body') -> tuple[str, int, str]:
    """Use the single persisted font choice with Dashboard semantic weights."""
    ui = load_ui()
    family = resolve_font_family_187(widget, ui.get('font_family'))
    selected = resolve_font_weight_187(widget, family, ui.get('font_weight'))
    weight = 400 if role == 'body' else 700 if role in {'title', 'kpi'} else selected
    return family, max(7, int(size)), 'bold' if weight >= 700 else 'normal'


def safe_project_id_187(value: str | None = None) -> str:
    raw = value if value is not None else os.getenv('PEYMAAN_ACTIVE_PROJECT_ID', '')
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', str(raw or '').strip())[:80] or 'default'


def bot_runtime_paths_187(base_dir: str | Path, project_id: str | None = None) -> dict[str, Path]:
    runtime = Path(base_dir) / 'runtime'
    suffix = safe_project_id_187(project_id)
    return {
        'ready': runtime / f'telegram_bot_ready_{suffix}.flag',
        'inbound': runtime / f'telegram_inbound_last_{suffix}.json',
        'status': runtime / f'telegram_bot_status_{suffix}.json',
    }


def is_tab_close_hit_187(event_x: int, bbox: tuple[int, int, int, int] | list[int]) -> bool:
    """Only the explicit right-side × zone closes a project tab."""
    x, _y, width, _height = [int(value) for value in bbox]
    close_width = min(24, max(16, width // 7))
    return x + width - close_width <= int(event_x) <= x + width


def apply_tree_rtl_187(tree: ttk.Treeview) -> None:
    if getattr(tree, '_barkav_rtl_187', False):
        return
    every = tuple(tree.cget('columns') or ())
    # The kit's tick column (barkav_ui.row_overlay) is always the right-most
    # one; it takes no part in reversing the rest, or it would land on the left.
    tail = (CHECK_COLUMN_187,) if CHECK_COLUMN_187 in every else ()
    columns = tuple(c for c in every if c != CHECK_COLUMN_187)
    if not columns:
        return
    try:
        requested_display = getattr(tree, '_barkav_displaycolumns187', None)
        if requested_display:
            # Financial tables intentionally omit internal ID columns from
            # the visible presentation.  Keep that curated RTL order when
            # the inherited generic RTL pass runs later in the refresh.
            tree.configure(displaycolumns=tuple(requested_display))
            shown = tuple(requested_display)
        else:
            shown = tuple(c for c in (tree.cget('displaycolumns') or ()) if c != CHECK_COLUMN_187)
        if shown in (('#all',), columns):
            tree.configure(displaycolumns=tuple(reversed(columns)) + tail)
        elif not requested_display and shown != tuple(reversed(columns)):
            tree.configure(displaycolumns=tuple(reversed(shown)) + tail)
    except Exception:
        tree.configure(displaycolumns=tuple(reversed(columns)) + tail)
    for column in every:
        try:
            tree.heading(column, anchor='e')
            tree.column(column, anchor='e')
        except Exception:
            pass
    tree._barkav_rtl_187 = True

def _chart_label_187(label: str) -> str:
    """Keep forecast storage intact while using the approved Persian label."""
    return 'بروز' if str(label) == 'پیش‌بینی' else str(label)


def _enable_caption_controls_187(window: tk.Misc) -> bool:
    """Ensure a native Windows caption exposes minimize, maximize and close.

    Tk can recreate the outer HWND while mapping a Toplevel.  Explicitly
    restoring these standard style bits here prevents a dialog from retaining
    the close-only tool-window caption left by an earlier native style.
    """
    if os.name != 'nt':
        return False
    try:
        import ctypes

        window.update_idletasks()
        user32 = ctypes.windll.user32
        # Tk exposes a ``TkChild`` HWND for a widget; its direct parent is
        # the ``TkTopLevel`` that carries this dialog's native caption.
        # Walking farther up can reach a host application's frame when Tk is
        # embedded, which is never a safe target for a BARKAV dialog change.
        native_id = window.winfo_id()
        # Resolve the actual top-level HWND even when Tk returns the child
        # handle used by the Toplevel's client area.
        hwnd = user32.GetAncestor(native_id, 2) or user32.GetParent(native_id) or native_id
        if not hwnd:
            return False
        style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
        # WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | WS_MAXIMIZEBOX |
        # WS_MINIMIZEBOX.  Removing WS_POPUP is required if a prior
        # tool-window mapping left that borderless style behind.
        caption_controls = 0x00C00000 | 0x00080000 | 0x00040000 | 0x00010000 | 0x00020000
        # `SetWindowLongW` takes a signed 32-bit LONG.  Python 3.14 ctypes
        # no longer silently narrows a large Python int, so passing a bitwise
        # style value directly raises `OverflowError` on 64-bit Windows
        # before the wizard is even shown.  Convert explicitly to the native
        # signed width while keeping the same Win32 style bits.
        new_style = ctypes.c_long((int(style) | caption_controls) & ~0x80000000).value
        # ``transient(parent)`` marks Tk dialogs as tool windows.  Windows then
        # hides minimize/maximize even when the corresponding style bits exist.
        # Remove that extended style for wizard dialogs so the native caption
        # really exposes all three standard controls.
        ex_style = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
        new_ex_style = ctypes.c_long((int(ex_style) & ~0x00000080) | 0x00040000).value
        if int(style) == new_style and int(ex_style) == new_ex_style:
            return True
        user32.SetWindowLongW(hwnd, -16, new_style)
        user32.SetWindowLongW(hwnd, -20, new_ex_style)
        # SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER |
        # SWP_NOACTIVATE makes Windows redraw the caption immediately.
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0037)
        return True
    except (AttributeError, OSError, OverflowError, tk.TclError):
        return False


def _canvas_card_187(canvas, fill: str) -> None:
    """Paint a chart canvas as a rounded card, like the KPI cards beside it.

    A Canvas fills its whole rectangle itself, so it cannot sit on a
    rounded_backdrop label the way a frame's children do. It draws the card
    as its first item instead: ``fill`` inside, the parent's own colour in
    the corners. Cached per size and colours - redraw runs on every resize
    and data refresh.
    """
    from barkav_ui.skin import rounded_plate_image

    p = palette_187()
    try:
        page = str(canvas.master.cget('bg'))
    except (tk.TclError, AttributeError):
        page = p['bg']
    canvas.configure(bg=page, highlightthickness=0)
    width, height = canvas.winfo_width(), canvas.winfo_height()
    if width < 40 or height < 24:
        return
    radius = min(max(8, int(theme_metrics_187().get('radius', 6))), height // 2)
    key = (width, height, fill, page, radius, p['border_subtle'])
    if getattr(canvas, '_barkav_card_key187', None) != key:
        canvas._barkav_card_image187 = rounded_plate_image(
            width, height, fill=fill, page=page, radius=radius,
            border=p['border_subtle'], master=canvas)
        canvas._barkav_card_key187 = key
    canvas.create_image(0, 0, image=canvas._barkav_card_image187, anchor='nw')


def _chart_width_187(canvas, fallback: int) -> int:
    """The chart's real width once it is laid out. A floor wider than the
    card (400 for the phase chart) drew the right-aligned title past the
    card's right edge, where it was cut off (operator report, 2026-09-27);
    the fallback is only for a canvas not yet on screen."""
    width = canvas.winfo_width()
    return width if width > 60 else fallback


_PHASE_PREFIX_187 = re.compile(r'^\s*(\d{1,2})(?!\d)')


def unplanned_phase_costs_187(db, names: dict[int, str]) -> dict[int, int]:
    """Approved costs filed under a phase but on no plan line, by phase.

    The plan's واقعی carries only the costs matched to one of its lines. An
    expense whose «فاز اصلی» was chosen - stored as construction_stage,
    'NN — name' from the entry form or a bare name from older entries - but
    that matched no line was counted nowhere, so the 32-phase row stood
    still while costs were being recorded (operator report, 2026-09-27).
    Read-only; drafts and cancelled costs are left out.
    """
    from budget_rich_v163 import norm

    by_name: dict[str, int] = {}
    for number, name in (names or {}).items():
        key = norm(name)
        if key:
            by_name.setdefault(key, int(number))
    try:
        with db.read() as con:
            rows = con.execute(
                """SELECT construction_stage AS stage, SUM(final_amount) AS total FROM expenses
                   WHERE deleted_at IS NULL AND status IN ('APPROVED', 'PARTIALLY_PAID', 'PAID')
                     AND COALESCE(plan_ref, '') = ''
                     AND TRIM(COALESCE(construction_stage, '')) <> ''
                   GROUP BY construction_stage""").fetchall()
    except (sqlite3.Error, AttributeError):
        return {}
    totals: dict[int, int] = {}
    for stage, total in ((row[0], row[1]) for row in rows):
        text = norm(stage)
        match = _PHASE_PREFIX_187.match(text)
        number = int(match.group(1)) if match else None
        if number is None or not 1 <= number <= 32:
            # A bare name: the phase whose name it is, once the dash and
            # anything before it are set aside.
            number = by_name.get(text) or by_name.get(text.split('—')[-1].strip())
        if number and 1 <= number <= 32:
            totals[number] = totals.get(number, 0) + max(0, int(total or 0))
    return totals


def apply_donut_theme_187(canvas, *, detail: bool = False, compact: bool = False) -> None:
    def redraw(self):
        p = palette_187()
        self.delete('all')
        _canvas_card_187(self, p['panel'])
        width = _chart_width_187(self, 360)
        # D5: the chart row is sized to the room left on screen.
        height = max(140, self.winfo_height())
        self.create_text(width - 12, 14, text=self.title, anchor='ne',
                         fill=p['text_primary'], font=dashboard_font_187(self, 9, 'title'))
        if detail:
            # The detail window reserves its entire upper surface for the
            # chart.  Keep a small gutter for the title and canvas edges, so
            # the ring reads as the primary object rather than a thumbnail.
            radius = min((height - 38) * (.38 if compact else .5),
                         width * (.25 if compact else .18))
            center_x = max(radius + 20, width * (.31 if compact else .18))
            center_y = min(height - radius - 8, max(radius + 30, height * .52))
        else:
            center_x, center_y = min(105, width * .25), height * .53
            radius = min(68, height * .32)
        inner = radius * .58
        colors = {
            'blue': p['blue'], 'green': p['green'], 'orange': p['orange'],
            'red': p['red'], 'cyan': p['cyan'], 'violet': p['violet'],
            'muted': p['muted'],
        }
        start = 90.0
        total = self.total or 1.0
        for label, value, color_name in self.items:
            extent = -360.0 * max(0, float(value)) / total
            self.create_arc(
                center_x - radius, center_y - radius, center_x + radius, center_y + radius,
                start=start, extent=extent, fill=colors.get(color_name, color_name),
                outline=p['surface_alt'],
            )
            start += extent
        self.create_oval(
            center_x - inner, center_y - inner, center_x + inner, center_y + inner,
            fill=p['panel'], outline=p['panel'],
        )
        number = self.total
        if abs(number) >= 1_000_000_000:
            short = fa(f'{number / 1_000_000_000:.1f}B')
        elif abs(number) >= 1_000_000:
            short = fa(f'{number / 1_000_000:.1f}M')
        else:
            short = fa(f'{number:,.0f}')
        self.create_text(center_x, center_y - 5, text=short, fill=p['text_primary'],
                         font=dashboard_font_187(self, 12, 'kpi'))
        self.create_text(center_x, center_y + 17, text='تومان', fill=p['text_secondary'],
                         font=dashboard_font_187(self, 7, 'body'))
        y = 45 if detail or height >= 150 else 38
        x = (max(center_x + radius + 20, width * .56) if compact else
             max(center_x + radius + 38, width * .52)) if detail else max(200, width * .52)
        # Six rows at 25px need 170px; a shorter chart (D5 sizes the row to
        # the screen) tightens the spacing instead of cutting the last rows.
        shown = self.items[:6]
        step = max(13, min(25, (height - y - 6) // max(1, len(shown))))
        for label, value, color_name in shown:
            color = colors.get(color_name, color_name)
            self.create_rectangle(x, y - 5, x + 9, y + 4, fill=color, outline='')
            percent = float(value) / total * 100 if total else 0
            self.create_text(x + 15, y, text=f'{label}  {fa(f"{percent:.0f}")}٪',
                             anchor='w', fill=p['text_secondary'], font=dashboard_font_187(self, 7, 'body'))
            y += step

    canvas.redraw = redraw.__get__(canvas, type(canvas))
    canvas.redraw()


def apply_progress_theme_187(canvas) -> None:
    def redraw(self):
        from barkav_ui.skin import rounded_plate_image

        p = palette_187()
        self.delete('all')
        _canvas_card_187(self, p['surface'])
        width = max(self.winfo_width(), 100)
        height = max(self.winfo_height(), 40)
        margin = 6
        # Pill track and pill fill, the same stadium shape as the buttons.
        track_w, track_h = int(width - 2 * margin), int(height - 2 * margin)
        radius = max(2, track_h // 2)
        images = []
        if track_w > 8 and track_h > 4:
            images.append(rounded_plate_image(track_w, track_h, fill=p['surface_alt'],
                                              page=p['surface'], radius=radius,
                                              border=p['border_subtle'], master=self))
            self.create_image(margin, margin, image=images[-1], anchor='nw')
            filled = int(track_w * self.percent / 100)
            if filled > 0:
                # Below one pill-height of progress a started bar shows as a
                # dot rather than nothing at all.
                images.append(rounded_plate_image(max(filled, track_h), track_h, fill=p['info'],
                                                  page=p['surface_alt'], radius=radius,
                                                  master=self))
                self.create_image(margin, margin, image=images[-1], anchor='nw')
        self._barkav_progress_images187 = images
        foreground = p['on_accent'] if self.percent >= 48 else p['text_primary']
        self.create_text(
            width / 2, height / 2,
            text=f"پیشرفت کلی پروژه  {fa(f'{self.percent:.1f}')}٪",
            fill=foreground, font=dashboard_font_187(self, 10, 'title'),
        )

    canvas.redraw = redraw.__get__(canvas, type(canvas))
    canvas.redraw()


class RoundedPhaseButton187(tk.Canvas):
    """Compact Canvas control that preserves the inherited phase-button API."""

    _DRAW_TAG = '_phase_button_plate187'

    def __init__(self, parent, *, number: int, command, edit_command, page: str,
                 fill: str, foreground: str, border: str):
        self.number = number
        self._command = command
        self._edit_command = edit_command
        self._page = page
        self._fill = fill
        self._foreground = foreground
        self._active_fill = fill
        self._active_foreground = foreground
        self._border = border
        self._cursor = 'hand2'
        self._font = ('Segoe UI', 6, 'bold')
        self._text = fa(f'{number:02d}')
        self._hovered = False
        super().__init__(parent, height=26, bg=page, bd=0, highlightthickness=0,
                         cursor=self._cursor, takefocus=1)
        self.bind('<Configure>', self._redraw, add='+')
        self.bind('<Enter>', lambda _event: self._set_hover(True), add='+')
        self.bind('<Leave>', lambda _event: self._set_hover(False), add='+')
        self.bind('<ButtonRelease-1>', self._invoke, add='+')
        self.bind('<Double-Button-1>', self._edit, add='+')
        self._redraw()

    def configure(self, cnf=None, **kwargs):
        options = dict(cnf or {})
        options.update(kwargs)
        if not options:
            return super().configure()
        self._fill = options.pop('bg', options.pop('background', self._fill))
        self._foreground = options.pop('fg', options.pop('foreground', self._foreground))
        self._active_fill = options.pop('activebackground', self._active_fill)
        self._active_foreground = options.pop('activeforeground', self._active_foreground)
        self._border = options.pop('highlightbackground', self._border)
        options.pop('highlightthickness', None)
        options.pop('relief', None)
        options.pop('bd', None)
        options.pop('borderwidth', None)
        options.pop('padx', None)
        options.pop('pady', None)
        self._text = options.pop('text', self._text)
        self._font = options.pop('font', self._font)
        self._cursor = options.pop('cursor', self._cursor)
        if 'command' in options:
            self._command = options.pop('command')
        super().configure(bg=self._page, cursor=self._cursor, **options)
        self._redraw()

    config = configure

    def cget(self, key):
        values = {
            'bg': self._fill, 'background': self._fill,
            'fg': self._foreground, 'foreground': self._foreground,
            'activebackground': self._active_fill,
            'activeforeground': self._active_foreground,
            'text': self._text, 'font': self._font, 'cursor': self._cursor,
        }
        return values[key] if key in values else super().cget(key)

    def _set_hover(self, value):
        self._hovered = value
        self._redraw()

    def _invoke(self, _event):
        if callable(self._command):
            self._command()
        return 'break'

    def _edit(self, _event):
        if callable(self._edit_command):
            self._edit_command()
        return 'break'

    def _redraw(self, _event=None):
        try:
            width = max(1, self.winfo_width())
            height = max(1, self.winfo_height())
            radius = min(6, width // 2, height // 2)
            fill = self._active_fill if self._hovered else self._fill
            foreground = self._active_foreground if self._hovered else self._foreground
            self.delete(self._DRAW_TAG)
            items = (
                self.create_rectangle(radius, 0, width - radius, height, fill=fill,
                                      outline='', tags=self._DRAW_TAG),
                self.create_rectangle(0, radius, width, height - radius, fill=fill,
                                      outline='', tags=self._DRAW_TAG),
                self.create_arc(0, 0, radius * 2, radius * 2, start=90, extent=90,
                                fill=fill, outline='', tags=self._DRAW_TAG),
                self.create_arc(width - radius * 2, 0, width, radius * 2, start=0, extent=90,
                                fill=fill, outline='', tags=self._DRAW_TAG),
                self.create_arc(0, height - radius * 2, radius * 2, height, start=180, extent=90,
                                fill=fill, outline='', tags=self._DRAW_TAG),
                self.create_arc(width - radius * 2, height - radius * 2, width, height,
                                start=270, extent=90, fill=fill, outline='', tags=self._DRAW_TAG),
                self.create_text(width / 2, height / 2, text=self._text, fill=foreground,
                                 font=self._font, tags=self._DRAW_TAG),
            )
            if self._border and radius:
                items += (
                    self.create_rectangle(radius, 0, width - radius, height - 1,
                                          outline=self._border, tags=self._DRAW_TAG),
                    self.create_rectangle(0, radius, width - 1, height - radius,
                                          outline=self._border, tags=self._DRAW_TAG),
                )
            for item in items:
                self.tag_raise(item)
        except tk.TclError:
            return


def apply_line_theme_187(canvas) -> None:
    """Restyle the inherited chart without changing its series or calculations."""
    def redraw(self):
        p = palette_187()
        self.delete('all')
        _canvas_card_187(self, p['card'])
        width, height = _chart_width_187(self, 300), max(self.winfo_height(), 160)
        # Reserve a narrow left rail for the series key.  The donut chart
        # already presents its key vertically, and matching it here leaves
        # the colour meaning readable without competing with the title.
        x0, y0, x1, y1 = 92, 42, width - 18, height - 28
        self.create_text(x1, 17, text=_chart_label_187(self.title), anchor='ne', fill=p['text_primary'],
                         font=dashboard_font_187(self, 10, 'title'))
        self.create_line(x0, y1, x1, y1, fill=p['border_subtle'], dash=(2, 4))
        self.create_line(x0, y0, x0, y1, fill=p['border_subtle'])
        values = [value for _label, series, _color in self.series for value in series]
        maximum = max(max(values, default=0), 1)
        colors = {name: p[name] for name in ('blue', 'green', 'orange', 'red', 'cyan')}
        for label, series, color_name in self.series:
            if not series:
                continue
            if _chart_label_187(label) == 'برآورد':
                color_name = 'orange'
            points = []
            for index, value in enumerate(series):
                x = x0 + (x1 - x0) * (index / max(1, len(series) - 1))
                y = y1 - (y1 - y0) * (value / maximum)
                points.extend((x, y))
            if len(points) >= 4:
                self.create_line(*points, fill=colors.get(color_name, color_name), width=2, smooth=True)
        legend_x, legend_y = 10, y0 + 5
        for label, _series, color_name in self.series:
            if _chart_label_187(label) == 'برآورد':
                color_name = 'orange'
            color = colors.get(color_name, color_name)
            self.create_rectangle(legend_x, legend_y - 5, legend_x + 9, legend_y + 4, fill=color, outline='')
            self.create_text(legend_x + 14, legend_y, text=_chart_label_187(label), anchor='w',
                             fill=p['text_secondary'], font=dashboard_font_187(self, 7, 'body'))
            legend_y += 22

    canvas.redraw = redraw.__get__(canvas, type(canvas))
    canvas.redraw()


def apply_bar_theme_187(canvas) -> None:
    """Restyle the inherited phase chart while preserving every source row."""
    def redraw(self):
        p = palette_187()
        self.delete('all')
        _canvas_card_187(self, p['card'])
        width, height = _chart_width_187(self, 400), max(self.winfo_height(), 160)
        self.create_text(width - 12, 17, text=self.title, anchor='ne', fill=p['text_primary'],
                         font=dashboard_font_187(self, 10, 'title'))
        if not self.rows:
            return
        maximum = max([value for _label, estimate, actual, forecast in self.rows
                       for value in (estimate, actual, forecast)] + [1])
        # Match the donut's vertical colour key and keep a clear rail for it
        # so the legend never overlays a bar or its value label.
        x0, y0, x1, y1 = 92, 46, width - 14, height - 26
        self.create_line(x0, y1, x1, y1, fill=p['border_subtle'], dash=(2, 4))
        group_width = (x1 - x0) / max(1, len(self.rows))
        # برآورد is orange in both the line and phase-comparison charts.
        colors = (p['orange'], p['success'], p['info'])
        for index, (label, estimate, actual, forecast) in enumerate(self.rows):
            base = x0 + index * group_width
            bar_width = max(2, (group_width - 6) / 3)
            for offset, value in enumerate((estimate, actual, forecast)):
                bar_height = (y1 - y0) * (value / maximum)
                self.create_rectangle(base + 3 + offset * bar_width, y1 - bar_height,
                                      base + 2 + (offset + 1) * bar_width, y1,
                                      fill=colors[offset], outline='')
            if len(self.rows) <= 16 or index % 2 == 0:
                # The one leftover 6pt spot in these three chart themes - every
                # other title/legend/caption here already sits at 7pt or up.
                self.create_text(base + group_width / 2, y1 + 10, text=fa(label),
                                 fill=p['text_muted'], font=dashboard_font_187(self, 7, 'body'))
        legend_x, legend_y = 10, y0 + 5
        for label, color in zip(('برآورد', 'واقعی', 'بروز'), colors):
            self.create_rectangle(legend_x, legend_y - 5, legend_x + 9, legend_y + 4, fill=color, outline='')
            self.create_text(legend_x + 14, legend_y, text=label, anchor='w',
                             fill=p['text_secondary'], font=dashboard_font_187(self, 7, 'body'))
            legend_y += 22

    canvas.redraw = redraw.__get__(canvas, type(canvas))
    canvas.redraw()


# Persian numerals for the three selectable themes, and the way back.
THEME_CHOICE_LABELS_187 = {1: '۱', 2: '۲', 3: '۳'}
THEME_CHOICE_VALUES_187 = {label: value
                           for value, label in THEME_CHOICE_LABELS_187.items()}

# Engine ids are the exact ids consumed by ReceiptVisionProviderChain.
from ai_section_models187 import MODEL_LABELS as AI_ENGINE_LABELS_187, AIModelPicker187, SECTION_LABELS, section_choice, update_choice
AI_ENGINE_VALUES_187 = {label: value for value, label in AI_ENGINE_LABELS_187.items()}


def _rate_timestamp_label_187(value: object) -> str:
    """Format a stored Gregorian rate timestamp as a Persian Solar Hijri label."""
    raw = str(value or '').strip().replace('Z', '')
    try:
        stamp = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return fa(raw.replace('T', ' '))
    return f'{fa(gregorian_to_shamsi(stamp.date()))} {fa(stamp.strftime("%H:%M:%S"))}'


class SettingsTab187(v186.SettingsTab186):
    def _build(self):
        p = palette_187()
        self.configure(bg=p['bg'])
        self.data = load_ui()
        self.vars = {}
        self.controls187 = {}
        self._font_families = self._installed_fonts()
        self._font_values = tuple(font_status_label_187(self, name) for name in self._font_families)
        card = tk.Frame(self, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
        card.pack(fill='x', padx=12, pady=12)
        tk.Label(card, text='تنظیمات ظاهر و کاربری ۱۸.۷', bg=p['panel2'], fg=p['text'],
                 anchor='e', font=dashboard_font_187(self, 11, 'title'), padx=12, pady=9).pack(fill='x')
        body = tk.Frame(card, bg=p['panel'])
        body.pack(fill='x', padx=10, pady=10)
        body.grid_columnconfigure((0, 1), weight=1, uniform='settings')

        language = {'fa': 'فارسی (RTL)', 'en': 'English'}
        fields = (
            ('language', 'زبان رابط', tuple(language.values()), language.get(str(self.data.get('language') or 'fa'), 'فارسی (RTL)')),
            ('appearance', 'حالت نمایش', ('تیره', 'روشن'), 'روشن' if str(self.data.get('appearance') or 'dark').lower() == 'light' else 'تیره'),
            # All three display modes are selectable here; offering only
            # two silently reset anyone already on the third.
            ('theme_id', 'تم رابط', ('۱', '۲', '۳'), THEME_CHOICE_LABELS_187.get(theme_id_187(), '۲')),
            ('font_family', 'نوع فونت', tuple(self._font_values), self._safe_font_value()),
            ('font_weight', 'وزن فونت', tuple(str(x) for x in self._font_weights()), str(self.data.get('font_weight') or 400)),
            ('font_size', 'اندازه فونت', tuple(str(x) for x in range(9, 19)), str(self.data.get('font_size') or 11)),
            ('background_color', 'رنگ پس‌زمینه', ('پیش‌فرض',) + tuple(BACKGROUND_COLORS_187), str(self.data.get('background_color') or 'پیش‌فرض')),
            ('currency_unit', 'واحد پول', ('تومان', 'ریال', 'دلار'), str(self.data.get('currency_unit') or 'تومان')),
            ('updated_rate_basis_187', 'محاسبه قیمت بروز بر اساس', RATE_BASIS_CHOICES_187, str(self.data.get('updated_rate_basis_187') or DEFAULT_RATE_BASIS_187)),
            ('row_height', 'ارتفاع ردیف', tuple(str(x) for x in range(28, 47, 2)), str(self.data.get('row_height') or 40)),
            ('button_display', 'نمایش دکمه‌ها', tuple(BUTTON_DISPLAY_CHOICES_187),
             next((label for label, value in BUTTON_DISPLAY_CHOICES_187.items()
                   if value == str(self.data.get('button_display') or 'text')), 'متن')),
        )
        for index, (key, label, values, current) in enumerate(fields):
            box = tk.Frame(body, bg=p['panel'])
            box.grid(row=index // 2, column=index % 2, sticky='ew', padx=7, pady=7)
            tk.Label(box, text=label, bg=p['panel'], fg=p['text'], anchor='e',
                     font=dashboard_font_187(self, 10, 'control')).pack(fill='x')
            value = tk.StringVar(value=current if current in values else values[0])
            self.vars[key] = value
            control = ttk.Combobox(box, textvariable=value, values=values, state='readonly',
                                   justify='right')
            control.pack(fill='x', pady=(4, 0))
            self.controls187[key] = control

        price_card = tk.Frame(self, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
        price_card.pack(fill='x', padx=12, pady=12)
        tk.Label(price_card, text='بروزرسانی قیمت', bg=p['panel2'], fg=p['text'],
                 anchor='e', font=dashboard_font_187(self, 11, 'title'), padx=12, pady=9).pack(fill='x')
        price_body = tk.Frame(price_card, bg=p['panel'])
        price_body.pack(fill='x', padx=10, pady=10)
        rate = tk.Frame(price_body, bg=p['panel'])
        rate_row = (len(fields) + 1) // 2
        rate.grid(row=rate_row, column=0, columnspan=2, sticky='ew', padx=7, pady=7)
        rate.grid_columnconfigure((0, 1), weight=1, uniform='rates')
        self.rate_status187 = tk.StringVar(value='نرخ‌ها قابل دریافت و ویرایش دستی هستند.')
        latest_stamp = (
            self.data.get('usd_rate_current_updated_at')
            or self.data.get('gold_rate_current_updated_at')
        )
        if latest_stamp:
            self.rate_status187.set(
                f'آخرین به‌روزرسانی: {_rate_timestamp_label_187(latest_stamp)}'
            )
        self.rate_update_buttons187 = []
        rate_fields = (
            ('usd_rate_current', 'قیمت روز دلار آمریکا (تومان)', True),
            ('usd_rate_baseline', 'قیمت دلار زمان برآورد اولیه (تومان)', False),
            ('gold_rate_current', 'قیمت روز طلا ۱۸ عیار (تومان/گرم)', True),
            ('gold_rate_baseline', 'قیمت طلا زمان برآورد اولیه (تومان/گرم)', False),
        )
        for index, (key, label, live) in enumerate(rate_fields):
            box = tk.Frame(rate, bg=p['panel'])
            box.grid(row=index // 2, column=1 - (index % 2), sticky='ew', padx=4, pady=3)
            tk.Label(box, text=label, bg=p['panel'], fg=p['text'], anchor='e').pack(fill='x')
            value = tk.StringVar(value=group_int_fa(self.data.get(key, 0), blank_zero=True))
            self.vars[key] = value
            entry = ttk.Entry(box, textvariable=value, justify='right')
            entry.pack(fill='x', pady=4)
            bind_grouped_number_fa(entry, value)
            if live:
                button = ttk.Button(
                    box, text='بروزرسانی از TGJU', command=self.refresh_rates_187,
                    style='Toolbar.TButton',
                )
                button.pack(anchor='e', pady=(0, 1))
                self.rate_update_buttons187.append(button)
        tk.Label(
            rate, textvariable=self.rate_status187, bg=p['panel'], fg=p['muted'],
            anchor='e', justify='right',
        ).grid(row=2, column=0, columnspan=2, sticky='ew', padx=4, pady=(4, 0))

        ai_card = tk.Frame(self, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
        ai_card.pack(fill='x', padx=12, pady=12)
        tk.Label(ai_card, text='AI Machine (هوش مصنوعی)', bg=p['panel2'], fg=p['text'],
                 anchor='e', font=dashboard_font_187(self, 11, 'title'), padx=12, pady=9).pack(fill='x')
        ai_body = tk.Frame(ai_card, bg=p['panel'])
        ai_body.pack(fill='x', padx=10, pady=10)
        ai_body.grid_columnconfigure((0, 1), weight=1, uniform='ai-settings')
        engine_box = tk.Frame(ai_body, bg=p['panel'])
        engine_box.grid(row=0, column=1, sticky='ew', padx=7, pady=7)
        tk.Label(engine_box, text='انتخاب مدل هوش مصنوعی', bg=p['panel'], fg=p['text'],
                 anchor='e', font=dashboard_font_187(self, 10, 'control')).pack(fill='x')
        engine_value = AI_ENGINE_LABELS_187.get(str(self.data.get('ai_engine_mode') or 'AUTO').upper(), AI_ENGINE_LABELS_187['AUTO'])
        self.vars['ai_engine_mode'] = tk.StringVar(value=engine_value)
        section_box = tk.Frame(engine_box, bg=p['panel']); section_box.pack(fill='x')
        ttk.Label(section_box, text='بخش', anchor='e').pack(side='right', padx=5)
        self.ai_section187 = tk.StringVar(value='همه')
        section_control = ttk.Combobox(section_box, textvariable=self.ai_section187,
            values=tuple(SECTION_LABELS.values()), state='readonly', justify='right', width=18)
        section_control.pack(side='right', fill='x', expand=True)
        self.ai_section_drafts187 = {key: section_choice(key, self.data) for key in SECTION_LABELS if key != 'all'}
        self.ai_changed_sections187 = set()
        self.ai_models187 = AIModelPicker187(engine_box, section='all', base_dir=BASE_DIR,
            choice=section_choice('data_entry', self.data), persist=False,
            on_change=self._ai_models_changed187)
        self.ai_models187.pack(fill='x', pady=(4, 0))
        section_control.bind('<<ComboboxSelected>>', self._ai_section_changed187)
        self.controls187['ai_engine_mode'] = self.ai_models187
        confidence_box = tk.Frame(ai_body, bg=p['panel'])
        confidence_box.grid(row=0, column=0, sticky='ew', padx=7, pady=7)
        tk.Label(confidence_box, text='آستانهٔ اطمینان برای رفتن به موتور بعدی', bg=p['panel'], fg=p['text'],
                 anchor='e', font=dashboard_font_187(self, 10, 'control')).pack(fill='x')
        confidence_value = str(self.data.get('ai_confidence_threshold') or '0.85')
        if confidence_value not in {'0.5', '0.65', '0.72', '0.8', '0.85', '0.9', '0.95'}:
            confidence_value = '0.85'
        self.vars['ai_confidence_threshold'] = tk.StringVar(value=confidence_value)
        confidence_control = ttk.Combobox(
            confidence_box, textvariable=self.vars['ai_confidence_threshold'],
            values=('0.5', '0.65', '0.72', '0.8', '0.85', '0.9', '0.95'),
            state='readonly', justify='right')
        confidence_control.pack(fill='x', pady=(4, 0))
        self.controls187['ai_confidence_threshold'] = confidence_control
        tk.Label(ai_body, text='در حالت «همه»، زنجیرهٔ مجاز طبق ترتیب گزارش اجرا می‌شود و بهترین نتیجه نگه داشته می‌شود.',
                 bg=p['panel'], fg=p['muted'], anchor='e', justify='right').grid(
                     row=1, column=0, columnspan=2, sticky='ew', padx=7, pady=(2, 0))
        # «شروع براورد» step ۵ opens on this mode; the wizard can still change it per run.
        import price_ai_research
        price_ai_box = tk.Frame(ai_body, bg=p['panel'])
        price_ai_box.grid(row=2, column=1, sticky='ew', padx=7, pady=7)
        tk.Label(price_ai_box, text='نحوه انتخاب مدل در بروزرسانی قیمت', bg=p['panel'], fg=p['text'],
                 anchor='e', font=dashboard_font_187(self, 10, 'control')).pack(fill='x')
        price_modes = price_ai_research.PRICE_AI_MODES
        self._price_ai_values187 = {label: key for key, label in price_modes.items()}
        price_mode = str(self.data.get('price_ai_mode') or price_ai_research.DEFAULT_PRICE_AI_MODE).upper()
        self.vars['price_ai_mode'] = tk.StringVar(
            value=price_modes.get(price_mode, price_modes[price_ai_research.DEFAULT_PRICE_AI_MODE]))
        price_ai_control = ttk.Combobox(price_ai_box, textvariable=self.vars['price_ai_mode'],
                                        values=tuple(price_modes.values()), state='readonly', justify='right')
        price_ai_control.pack(fill='x', pady=(4, 0))
        self.controls187['price_ai_mode'] = price_ai_control

        # The confirm action lives in the window footer (section 10), so it
        # cannot be pushed off the bottom by a taller form.
        self.save_row187 = rate_row + 3
        tk.Label(
            body,
            text='فارسی به‌صورت پیش‌فرض RTL است؛ تغییرات ظاهری پس از بازآفرینی برنامه اعمال می‌شوند.',
            bg=p['panel'], fg=p['muted'], anchor='e', justify='right',
        ).grid(row=rate_row + 2, column=0, columnspan=2, sticky='ew', padx=7, pady=(0, 5))

    def _ai_section_changed187(self, _event=None):
        key = next(key for key,value in SECTION_LABELS.items() if value == self.ai_section187.get())
        self.ai_models187.section = key
        self.ai_models187.set_choice(self.ai_section_drafts187['data_entry' if key == 'all' else key])

    def _ai_models_changed187(self, choice):
        key = self.ai_models187.section
        for target in self.ai_section_drafts187 if key == 'all' else (key,):
            self.ai_section_drafts187[target] = dict(choice)
            self.ai_changed_sections187.add(target)
        self.vars['ai_engine_mode'].set(AI_ENGINE_LABELS_187.get(choice['mode'],
            AI_ENGINE_LABELS_187.get((choice['models'] or ['AUTO'])[0])))

    def _installed_fonts(self):
        return font_catalog_families_187(self)

    def refresh_rates_187(self, silent: bool = False):
        """Refresh USD and 18-karat gold from TGJU without touching project data."""
        if getattr(self, '_rate_job_running187', False):
            return
        self._rate_job_running187 = True
        self.rate_status187.set('در حال دریافت نرخ دلار و طلا...')
        for button in getattr(self, 'rate_update_buttons187', []):
            button.configure(state='disabled')

        results_queue = Queue()

        def job():
            results = {}
            errors = []
            for key, fetcher in (
                ('usd_rate_current', lambda: v186.v185.fetch_tgju_usd_toman(timeout=6.0)),
                ('gold_rate_current', lambda: fetch_tgju_gold_toman(timeout=6.0)),
            ):
                try:
                    results[key] = fetcher()
                except Exception as exc:
                    errors.append((key, exc))
            results_queue.put((results, errors))

        def done(results, errors):
            self._rate_job_running187 = False
            for button in getattr(self, 'rate_update_buttons187', []):
                try:
                    button.configure(state='normal')
                except tk.TclError:
                    pass
            saved = load_ui()
            updated = []
            for key, (rate, timestamp) in results.items():
                if int(rate or 0) <= 0:
                    continue
                self.vars[key].set(group_int_fa(rate))
                saved[key] = int(rate)
                saved[f'{key}_updated_at'] = timestamp
                updated.append('دلار' if key.startswith('usd_') else 'طلا')
            if updated:
                save_ui(saved)
                stamp = next(iter(results.values()))[1]
                self.rate_status187.set(
                    f"به‌روزرسانی شد: {' و '.join(dict.fromkeys(updated))} — "
                    f'{_rate_timestamp_label_187(stamp)}'
                )
            else:
                self.rate_status187.set('دریافت آنلاین انجام نشد؛ نرخ ذخیره‌شده حفظ شد.')
                if errors and not silent:
                    messagebox.showwarning(
                        'نرخ‌ها', 'ارتباط با TGJU برقرار نشد؛ نرخ‌های ذخیره‌شده حفظ شدند.', parent=self,
                    )

        def poll():
            try:
                results, errors = results_queue.get_nowait()
            except Empty:
                try:
                    if self.winfo_exists():
                        self.after(40, poll)
                except tk.TclError:
                    pass
                return
            done(results, errors)

        threading.Thread(target=job, daemon=True).start()
        self.after(40, poll)

    def _font_weights(self):
        return available_font_weights_187(self, resolve_font_family_187(self, self.data.get('font_family')))

    def _safe_font_value(self):
        current = str(self.data.get('font_family') or '').strip()
        if current in self._font_families:
            return font_status_label_187(self, current)
        return font_status_label_187(self, resolve_font_family_187(self, current))

    def save(self):
        old = load_ui()
        data = dict(old)
        language = {'فارسی (RTL)': 'fa', 'English': 'en'}
        data.update({key: value.get() for key, value in self.vars.items()})
        numeric_keys = (
            'usd_rate_current', 'usd_rate_baseline',
            'gold_rate_current', 'gold_rate_baseline',
        )
        for key in numeric_keys:
            parsed = parse_int(self.vars[key].get())
            data[key] = parsed
            self.vars[key].set(group_int_fa(parsed, blank_zero=True))
        selected_display = self.vars['font_family'].get()
        data['font_family'] = next(
            (name for name in self._font_families if font_status_label_187(self, name) == selected_display),
            self._font_families[0],
        )
        data['font_weight'] = resolve_font_weight_187(self, data['font_family'], data.get('font_weight'))
        data['language'] = language.get(self.vars['language'].get(), 'fa')
        data['appearance'] = 'light' if self.vars['appearance'].get() == 'روشن' else 'dark'
        data['theme_id'] = THEME_CHOICE_VALUES_187.get(
            self.vars['theme_id'].get(), DEFAULT_THEME_ID_187)
        # Merge into the latest settings so a calendar/search choice made while
        # Settings was open cannot be overwritten by an unrelated appearance save.
        data['ai_engine_mode'] = old.get('ai_engine_mode', 'AUTO')
        if hasattr(self, 'ai_changed_sections187'):
            for section in self.ai_changed_sections187:
                data = update_choice(data, section, self.ai_section_drafts187[section])
        else:
            data['ai_engine_mode'] = AI_ENGINE_VALUES_187.get(self.vars['ai_engine_mode'].get(), 'ALL')
        data['ai_confidence_threshold'] = max(0.0, min(1.0, float(self.vars['ai_confidence_threshold'].get())))
        if 'price_ai_mode' in self.vars:
            data['price_ai_mode'] = self._price_ai_values187.get(self.vars['price_ai_mode'].get(), 'AUTO')
        data['font_size'] = max(9, min(18, int(data.get('font_size') or 11)))
        data['row_height'] = max(28, min(46, int(data.get('row_height') or 40)))
        data['button_display'] = BUTTON_DISPLAY_CHOICES_187.get(
            str(data.get('button_display') or ''), 'text')
        data['usd_rate_current'] = parse_int(data.get('usd_rate_current'))
        data['usd_rate_baseline'] = parse_int(data.get('usd_rate_baseline'))
        if data.get('currency_unit') == 'دلار' and data['usd_rate_current'] <= 0:
            return messagebox.showwarning('واحد دلار', 'قیمت روز دلار آمریکا را وارد کن.', parent=self)
        save_ui(data)
        self.on_apply and self.on_apply(old, data)


def _migrated_attachment_index_187() -> dict[str, str]:
    """Index current release archives by basename for transferred databases."""
    roots = [Path(__file__).resolve().parent.parent / 'data']
    db_path = str(getattr(DB, 'db_path', '') or '')
    if db_path:
        roots.extend((Path(db_path).parent, Path(db_path).parent / 'receipt_archive'))
    index: dict[str, str] = {}
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for candidate in root.rglob('*'):
                if candidate.is_file():
                    index.setdefault(candidate.name.casefold(), str(candidate))
        except OSError:
            continue
    return index


def _repair_pending_attachment_paths_187(pending_id: str) -> int:
    """Repair stale absolute paths without changing attachment contents."""
    pending_id = str(pending_id or '').strip()
    if not pending_id:
        return 0
    try:
        attachments = list(DB.list_pending_attachments(pending_id) or [])
    except Exception:
        attachments = []
    index = _migrated_attachment_index_187()
    updates: list[tuple[str, str]] = []
    for item in attachments:
        raw = str(item.get('local_path') or '').strip()
        if not raw or Path(raw).is_file():
            continue
        replacement = index.get(Path(raw).name.casefold(), '')
        if replacement and replacement != raw:
            updates.append((replacement, str(item.get('attachment_id') or '')))
    analysis_replacement = ''
    try:
        analysis = DB.get_receipt_analysis(pending_id) or {}
        raw_analysis_path = str(analysis.get('image_path') or '').strip()
        if raw_analysis_path and not Path(raw_analysis_path).is_file():
            analysis_replacement = index.get(Path(raw_analysis_path).name.casefold(), '')
    except Exception:
        analysis = {}
    if not updates and not analysis_replacement:
        return 0
    try:
        with DB.tx() as con:
            for replacement, attachment_id in updates:
                if attachment_id:
                    con.execute(
                        'UPDATE attachments SET local_path=? WHERE attachment_id=?',
                        (replacement, attachment_id),
                    )
            if analysis_replacement:
                con.execute(
                    'UPDATE receipt_analyses SET image_path=?, updated_at=? WHERE pending_id=?',
                    (analysis_replacement, datetime.now().isoformat(timespec='seconds'), pending_id),
                )
    except Exception:
        logging.getLogger(__name__).exception(
            'Could not repair migrated attachment path for %s', pending_id,
        )
        return 0
    return len(updates) + bool(analysis_replacement)

# Settings: choose words or icon-only table actions.
BUTTON_DISPLAY_CHOICES_187 = {'متن': 'text', 'فقط آیکون': 'icon'}

# Reading a receipt is two jobs: local work (image preparation and Tesseract)
# and the AI call. On a typical receipt the AI call is the longer of the two,
# so more calls are kept in flight than before while the local work runs wider
# still so an AI slot never waits for its next receipt to be prepared.
REPROCESS_LOCAL_WORKERS_187 = max(4, min(8, (os.cpu_count() or 4) + 2))
REPROCESS_API_SLOTS_187 = 4
# After a rate-limit answer no new AI call starts for this long, so a plan
# with a low per-minute quota slows down instead of failing receipt after receipt.
REPROCESS_RATE_LIMIT_PAUSE_187 = 8.0
# A stalled network or OCR call must free its slot instead of freezing the
# whole batch; the receipt simply stays in review with the error listed.
REPROCESS_ITEM_TIMEOUT_187 = 300
_RATE_LIMIT_TOKENS_187 = ('429', 'rate limit', 'resource exhausted', 'quota')


class ReprocessApiGate187:
    """Cap concurrent AI calls, back off after a rate limit, and time the calls."""

    def __init__(self, parser, slots: int, *, pause: float = REPROCESS_RATE_LIMIT_PAUSE_187):
        self._parser = parser
        self._slots = asyncio.Semaphore(max(1, int(slots)))
        self._pause = float(pause)
        self._resume_at = 0.0
        self.calls = 0
        self.rate_limited = 0
        self.api_seconds = 0.0
        self.wait_seconds = 0.0

    async def analyze(self, **kwargs):
        loop = asyncio.get_running_loop()
        queued = loop.time()
        while True:
            delay = self._resume_at - loop.time()
            if delay <= 0:
                break
            await asyncio.sleep(delay)
        async with self._slots:
            started = loop.time()
            self.wait_seconds += started - queued
            try:
                return await self._parser.analyze(**kwargs)
            except Exception as exc:
                if any(token in str(exc).lower() for token in _RATE_LIMIT_TOKENS_187):
                    self.rate_limited += 1
                    self._resume_at = loop.time() + self._pause
                raise
            finally:
                self.calls += 1
                self.api_seconds += loop.time() - started

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return getattr(self._parser, name)


def format_duration_187(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    minutes, rest = divmod(seconds, 60)
    if minutes and rest:
        return f'{fa(minutes)} دقیقه و {fa(rest)} ثانیه'
    if minutes:
        return f'{fa(minutes)} دقیقه'
    return f'{fa(rest)} ثانیه'


def reprocess_status_text_187(kind: str, done: int, total: int, elapsed: float,
                              verb: str = 'پردازش') -> str:
    """«پردازش رسید ۸ از ۱۸… · حدود ۲ دقیقه مانده» once there is a pace to go by."""
    text = f'{verb} {kind} {fa(done)} از {fa(total)}…'
    if done >= 2 and total > done and elapsed > 0:
        text += f' · حدود {format_duration_187(elapsed / done * (total - done))} مانده'
    return text


def reprocess_error_text_187(pending_id, exc) -> str:
    if isinstance(exc, asyncio.TimeoutError):
        return (f'{pending_id}: پردازش بیش از {fa(REPROCESS_ITEM_TIMEOUT_187)} ثانیه '
                'طول کشید و متوقف شد؛ رسید در وضعیت بررسی ماند.')
    return f'{pending_id}: {exc or exc.__class__.__name__}'


def latest_reprocess_progress_187(events, current: int) -> int:
    """Newest finished count; keep the last one shown when nothing new arrived."""
    while True:
        try:
            current = events.get_nowait()
        except Empty:
            return current


class DataEntryCenter187(v186.DataEntryCenter186):
    """Keep earlier receipts visible and isolate Telegram status per project."""

    _STATUS_FILTERS_187 = (
        ('همه', 'همه'),
        ('در انتظار بررسی', 'Pending'),
        ('تأیید شده', 'تأییدشده'),
        # rows cleared from the table with «حذف» that the database still holds (data_entry_extras_ui)
        ('پنهان شده', 'پنهان‌شده'),
        ('رد شده', 'ردشده'),
    )
    def _build(self):
        self._data_entry_sort187 = DB.get_setting(SORT_SETTING) or 'row'
        self._data_entry_periodic_after187 = None
        self._service_status_after187 = None
        self._data_entry_poll_active187 = False
        self._last_data_entry_pending_marker187 = None
        self._skip_contractors_refresh187 = False
        self._data_entry_import_active187 = False
        super()._build()
        self._build_data_entry_toolbar_187()
        self._remove_bottom_actions_187()
        self._build_service_statuses_187()
        self._install_data_entry_context_actions_187()
        self._configure_data_entry_columns_187()
        self.table._sync_checks = self._sync_data_entry_checks_187
        self.table.on_open = self._open_row_187
        from record_receipt187 import DataEntryReceipt187
        self._receipt_preview187 = DataEntryReceipt187(self, DB, v182.APPROVAL)
        # The Word correction asks for previous receipts to be present in the
        # current view. All statuses already exist; 18.7 opens on that full list.
        self.filter.set('همه')
        self.status_filter187.set('همه')
        self.bind('<Map>', self._queue_data_entry_activity_sync_187, add='+')
        self.bind('<Unmap>', self._queue_data_entry_activity_sync_187, add='+')
        notebook_info = self._data_entry_notebook_187()
        if notebook_info is not None:
            notebook, _page = notebook_info
            notebook.bind('<<NotebookTabChanged>>', self._queue_data_entry_activity_sync_187, add='+')
        self.after_idle(self._sync_data_entry_activity_187)

    def _open_row_187(self, row):
        """Double-click on a row. A record that has been through review (approved, being edited, rejected) and every
        cheque resolution open the record window, exactly as «ویرایش» does; a row nobody has reviewed yet opens the
        wizard, the step-by-step first review."""
        row = row or getattr(self, 'current', None)
        payload = dict((row or {}).get('payload') or {})
        reviewed = str((row or {}).get('status') or '').upper() in {'APPROVED', 'EDIT_PENDING', 'REJECTED'}
        resolution = str(payload.get('cheque_operation187') or '') == CHEQUE_OPERATION_RESOLVE_187
        if (row and (reviewed or resolution) and not row.get('_lifecycle_decision_only187')
                and not is_temporary_sales_finance_pending_187(payload)):
            return self.open_editor(row)
        return self.open_wizard(row)

    def open_editor(self, row=None, *, navigation_rows=None):
        """Open with an immutable snapshot of the visible row order."""
        row = row or getattr(self, 'current', None)
        if not row:
            return
        if row.get('_lifecycle_decision_only187'):
            messagebox.showinfo('تعیین تکلیف',row['_lifecycle_decision187'],parent=self)
            return
        pending_id = str(row.get('pending_id') or '')
        if not pending_id:
            return
        snapshot = [dict(item) for item in (navigation_rows if navigation_rows is not None else (getattr(self, 'rows', None) or []))]
        index = next(
            (i for i, item in enumerate(snapshot)
             if str(item.get('pending_id') or '') == pending_id),
            -1,
        )
        if index < 0:
            snapshot.append(dict(row))
            index = len(snapshot) - 1
        before = self._pending_snapshot(pending_id)
        before_by_id = {pending_id: before}
        editor_ref = {}

        def record_open(pid):
            key = str(pid or '')
            if key and key not in before_by_id:
                before_by_id[key] = self._pending_snapshot(key)

        def done():
            editor = editor_ref.get('editor')
            active_id = str(getattr(editor, 'pid', pending_id) or pending_id)
            self._record_pending_edit(before_by_id.get(active_id))
            before_by_id[active_id] = self._pending_snapshot(active_id)
            self.refresh()
            if callable(self.on_posted):
                self.on_posted()

        editor_ref['editor'] = v182.UnifiedPendingEditor182(
            self, row, self.rich, done,
            navigation_rows=snapshot,
            navigation_index=index,
            on_record_open=record_open,
        )
        return editor_ref['editor']

    def batch_delete18(self, rows):
        from transaction_lifecycle_ui import delete_rows
        return delete_rows(self, rows, DB, messagebox, kind='delete')

    def show_hidden_187(self):
        """Switch the table to the «پنهان‌شده» category."""
        self.filter.set(HIDDEN_FILTER_187)
        self.status_filter187.set(HIDDEN_LABEL_187)
        self.refresh()

    def show_selected_again_187(self):
        rows = [row for row in self.table.selected_rows() if row.get('_hidden187')]
        if rows:
            show_rows_again_187(self, [row['pending_id'] for row in rows])

    def manual_transaction(self):
        selected = self.table.selected_rows()
        target = selected[-1].get('pending_id') if selected else None
        mid = int(datetime.now().timestamp() * 1_000_000)
        payload = dict(detected_type='EXPENSE', v18_title='هزینه ساخت', v18_subtype='نقدی',
                       event_date_shamsi=gregorian_to_shamsi(datetime.now().date()), amount=0,
                       payment_state='UNPAID', source='MANUAL_GUI_18_7')
        try:
            with DB.atomic():
                DB.register_telegram_message(chat_id=-180, message_id=mid, raw_text='',
                    content_type='manual_gui', message_date=datetime.now().isoformat(timespec='seconds'),
                    state='RECEIVED')
                pid = DB.create_or_replace_pending(telegram_chat_id=-180, telegram_message_id=mid,
                    detected_type='EXPENSE', payload=payload, confidence=1.0, status='PENDING_REVIEW')
                insert_data_entry_rows(DB, [pid], target)
        except Exception as exc:
            return messagebox.showerror('ثبت دستی انجام نشد', str(exc), parent=self)
        self._push_history({'kind': 'add', 'pending_ids': [str(pid)]})
        self.filter.set('Pending' if self.filter.get() == 'Pending' else 'همه')
        self._data_entry_sort187 = 'row'
        DB.set_setting(SORT_SETTING, 'row')
        self.refresh()
        self._select_pending_ids([pid])
        self.open_wizard(DB.get_pending_item(pid))
        return pid

    def batch_reject18(self, rows):
        from transaction_lifecycle_ui import delete_rows
        return delete_rows(self, rows, DB, messagebox)

    def restore_rejected_rows_187(self, rows):
        from transaction_lifecycle_ui import restore_rows
        return restore_rows(self, rows, DB, messagebox)

    def _progress_dialog_187(self, title, message, *, total=0):
        """Show a themed, RTL progress window without the shell fade flash."""
        p = palette_187()
        dialog = BarkavWindow(self, title, size_class='tiny', show_footer=False, show_immediately=False)
        content = dialog.body
        dialog._barkav_skip_fade187 = True
        # Built hidden and shown once, fully styled and centred: a window that
        # maps first and is restyled/moved afterwards flashes dark on open.
        dialog.withdraw()
        dialog.title(title)
        dialog.configure(bg=p['bg'])
        dialog.transient(self)
        dialog.resizable(False, False)
        label = tk.StringVar(value=message)
        tk.Label(
            content, textvariable=label, bg=p['bg'], fg=p['text_primary'],
            anchor='e', justify='right', wraplength=480,
            padx=22, pady=16,
        ).pack(fill='x')
        if total:
            progress = ttk.Progressbar(
                content, mode='determinate', maximum=max(1, int(total)), length=420,
            )
            progress['value'] = 0
        else:
            progress = ttk.Progressbar(content, mode='indeterminate', length=420)
            progress.start(12)
        progress.pack(fill='x', padx=22, pady=(0, 18))
        dialog.protocol('WM_DELETE_WINDOW', lambda: None)
        dialog.bind('<Escape>', lambda _event: 'break')
        # Room for a longer status line (count + time left) in later stages.
        dialog.update_idletasks()
        self._present_dialog_187(
            dialog, max(520, dialog.winfo_reqwidth()), dialog.winfo_reqheight() + 24)
        return dialog, label, progress

    def _present_dialog_187(self, dialog, width=None, height=None):
        """Show a dialog that was built hidden: styled, centred, then modal."""
        normalise = getattr(self.winfo_toplevel(), '_normalise_window_187', None)
        if callable(normalise):
            try:
                normalise(dialog)
            except (tk.TclError, AttributeError, KeyError):
                pass
        self._center_reprocess_dialog_187(dialog, width, height)
        dialog.deiconify()
        dialog.update_idletasks()

        def take_focus():
            try:
                dialog.grab_set()
                dialog.focus_force()
            except tk.TclError:
                if dialog.winfo_exists():
                    dialog.after(15, take_focus)

        take_focus()

    @staticmethod
    def _progress_phase_187(label, progress, message, total=None):
        """Reuse an open progress window for the next stage of the same job."""
        label.set(message)
        try:
            progress.stop()
            if total:
                progress.configure(mode='determinate', maximum=max(1, int(total)))
                progress['value'] = 0
            else:
                progress.configure(mode='indeterminate')
                progress.start(12)
            progress.update_idletasks()
        except tk.TclError:
            pass

    @staticmethod
    def _close_progress_dialog_187(dialog, progress):
        try:
            progress.stop()
            dialog.grab_release()
            dialog.destroy()
        except tk.TclError:
            pass

    @staticmethod
    def _unhide_imported_reviews_187(pending_ids) -> int:
        """Show imported rows again that an earlier delete had hidden.

        Deleting from Data Entry rejects the row and adds it to the hidden
        list; a repeated import of the same backup then reopens the row for
        review but the table would still skip it. Only rows that are waiting
        for review now are brought back; approved and rejected ones stay put.
        """
        ids = [str(pending_id) for pending_id in pending_ids or () if pending_id]
        if not ids:
            return 0
        restored = 0
        now = datetime.now().isoformat(timespec='seconds')
        with DB.tx() as con:
            for start in range(0, len(ids), 400):
                chunk = ids[start:start + 400]
                marks = ','.join('?' for _ in chunk)
                cursor = con.execute(
                    f"""UPDATE rich_ui_hidden_reviews SET hidden=0, updated_at=?
                        WHERE hidden=1 AND pending_id IN ({marks})
                          AND pending_id IN (
                              SELECT pending_id FROM pending_items
                              WHERE status IN ('PENDING_REVIEW','NEEDS_REVIEW'))""",
                    (now, *chunk),
                )
                restored += max(0, cursor.rowcount)
        return restored

    def import_chat_backup(self):
        """Import a Telegram backup off the UI thread, then refresh Pending."""
        selected = filedialog.askopenfilename(
            parent=self, title='انتخاب بکاپ Telegram Desktop',
            filetypes=[('Telegram backup', '*.json *.zip'), ('JSON', '*.json'), ('ZIP', '*.zip')],
        )
        if not selected:
            return None
        self._data_entry_import_active187 = True
        started_at = time.monotonic()
        dialog, label, progress = self._progress_dialog_187(
            'بارگذاری بکاپ چت', 'در حال خواندن فایل بکاپ…',
        )
        outcomes = Queue()
        counts = Queue()
        restored = {'count': 0, 'error': None}
        seen = {'total': None}

        def worker():
            try:
                source = Path(selected)
                receipts = getattr(v182.APPROVAL, 'receipts', None)

                def report(done, total):
                    counts.put((done, total))

                if source.suffix.lower() == '.zip':
                    with tempfile.TemporaryDirectory(prefix='barkav_chat_') as temp_dir:
                        json_path = self._safe_zip_json(source, Path(temp_dir))
                        result = import_telegram_export(
                            DB, json_path, receipt_service=receipts, progress=report)
                else:
                    result = import_telegram_export(
                        DB, source, receipt_service=receipts, progress=report)
            except Exception as exc:
                outcomes.put((None, exc))
                return
            try:
                restored['count'] = self._unhide_imported_reviews_187(result.pending_ids)
            except Exception as exc:
                logging.getLogger(__name__).exception('Could not restore hidden imported reviews')
                restored['error'] = exc
            outcomes.put((result, None))

        threading.Thread(target=worker, daemon=True).start()

        def show_counts():
            latest = None
            while True:
                try:
                    latest = counts.get_nowait()
                except Empty:
                    break
            if latest is None:
                return
            done, total = latest
            if seen['total'] != total:
                seen['total'] = total
                self._progress_phase_187(label, progress, '', total)
            progress['value'] = done
            label.set(reprocess_status_text_187(
                'پیام', done, total, time.monotonic() - started_at, verb='افزودن'))

        def poll():
            show_counts()
            try:
                result, error = outcomes.get_nowait()
            except Empty:
                if dialog.winfo_exists():
                    self.after(80, poll)
                return
            self._data_entry_import_active187 = False
            if error is not None:
                self._close_progress_dialog_187(dialog, progress)
                messagebox.showerror('بارگذاری بکاپ چت', str(error), parent=self)
                return
            took = format_duration_187(time.monotonic() - started_at)
            # The window stays up while the table repaints, so there is no
            # stretch where the app looks idle between the import and the summary.
            self._progress_phase_187(label, progress, 'در حال نمایش نتیجه در جدول…')
            refresh_error = None
            try:
                self.refresh()
            except Exception as exc:
                refresh_error = exc
            self._close_progress_dialog_187(dialog, progress)
            summary = (
                f'چت‌ها: {fa(result.chats)}\n'
                f'پیام‌های بررسی‌شده: {fa(result.scanned)}\n'
                f'کاندیدهای مالی: {fa(result.candidates)}\n'
                f'پیش‌نویس‌های افزوده‌شده: {fa(result.created)}\n'
                f'تکراری: {fa(result.duplicates)}\n'
                + (f'بازگردانده‌شده از موارد حذف‌شده: {fa(restored["count"])}\n' if restored['count'] else '')
                + f'نادیده‌گرفته‌شده: {fa(result.skipped)}\n'
                f'رسانهٔ پیدا‌نشده: {fa(result.media_missing)}\n'
                f'زمان بارگذاری: {took}\n\n'
                'پیش‌نویس‌ها در «ثبت دیتا» برای بررسی می‌آیند؛ ثبت مالی فقط پس از تأیید انجام می‌شود.'
                + (f'\n\nبه‌روزرسانی جدول با خطا روبه‌رو شد: {refresh_error}' if refresh_error else '')
                + (f'\n\nبازگردانی موارد مخفی‌شده با خطا روبه‌رو شد: {restored["error"]}' if restored['error'] else '')
            )
            ids = list(result.media_pending_ids or [])
            if not ids:
                messagebox.showinfo('بارگذاری بکاپ چت', summary, parent=self)
            elif messagebox.askyesno(
                'بارگذاری بکاپ چت',
                summary + f'\n\n{fa(len(ids))} تصویر آمادهٔ تحلیل است. تحلیل شروع شود؟',
                parent=self,
            ):
                self._run_ai_ids(ids)

        self.after(80, poll)
        return dialog

    def _data_entry_notebook_187(self):
        child = self
        parent = getattr(child, 'master', None)
        while parent is not None:
            if isinstance(parent, ttk.Notebook):
                return parent, child
            child = parent
            parent = getattr(child, 'master', None)
        return None

    def _is_data_entry_tab_active_187(self):
        try:
            # Tk unmaps the inactive ttk.Notebook pages.  This is the reliable
            # visibility signal here; comparing Tcl widget paths can differ
            # across the themed tab wrappers used by the 19.1.1 launcher and
            # incorrectly prevent the first table load when the tab is opened.
            return bool(self.winfo_exists() and self.winfo_ismapped())
        except tk.TclError:
            return False

    def _queue_data_entry_activity_sync_187(self, _event=None):
        try:
            self.after_idle(self._sync_data_entry_activity_187)
        except tk.TclError:
            pass

    def _cancel_data_entry_timer_187(self, attribute):
        timer = getattr(self, attribute, None)
        if timer:
            try:
                self.after_cancel(timer)
            except tk.TclError:
                pass
            setattr(self, attribute, None)

    def _sync_data_entry_activity_187(self):
        if self._is_data_entry_tab_active_187():
            if not self._data_entry_poll_active187:
                self._data_entry_poll_active187 = True
                self._periodic()
                self._service_status_181()
            return
        self._data_entry_poll_active187 = False
        self._cancel_data_entry_timer_187('_data_entry_periodic_after187')
        self._cancel_data_entry_timer_187('_service_status_after187')

    def _pending_review_marker_187(self):
        """Read a cheap signature so a full table redraw happens only on change."""
        with DB.read() as con:
            row = con.execute(
                """SELECT COUNT(*), COALESCE(MAX(updated_at), ''), COALESCE(MAX(rowid), 0)
                   FROM pending_items
                   WHERE status IN ('PENDING_REVIEW', 'NEEDS_REVIEW', 'EDIT_PENDING')"""
            ).fetchone()
        return int(row[0] or 0), str(row[1] or ''), int(row[2] or 0)

    def _periodic(self):
        """Poll for new Pending rows only while this notebook page is selected."""
        self._cancel_data_entry_timer_187('_data_entry_periodic_after187')
        if not self._is_data_entry_tab_active_187():
            self._data_entry_poll_active187 = False
            return
        if getattr(self, '_data_entry_import_active187', False):
            self._data_entry_periodic_after187 = self.after(4000, self._periodic)
            return
        try:
            marker = self._pending_review_marker_187()
            if marker != self._last_data_entry_pending_marker187:
                self._skip_contractors_refresh187 = True
                try:
                    self.refresh()
                finally:
                    self._skip_contractors_refresh187 = False
            self._update_bot()
        except Exception:
            logging.getLogger(__name__).exception('Could not check for new Data Entry pending rows')
        if self._is_data_entry_tab_active_187():
            self._data_entry_periodic_after187 = self.after(4000, self._periodic)
        else:
            self._data_entry_poll_active187 = False

    def _build_data_entry_toolbar_187(self):
        """Use one compact, RTL Income-style toolbar for Data Entry actions."""
        children = self.winfo_children()
        if not children:
            return
        toolbar = children[0]
        p = palette_187()
        try:
            for child in toolbar.winfo_children():
                child.destroy()
            toolbar.configure(bg=p['bg'], highlightthickness=0, bd=0)
        except tk.TclError:
            return
        # In an RTL toolbar, the first right-packed group stays at the right
        # edge.  This deliberately gives the required action order:
        # افزودن، ویرایش، کپی، حذف، نمایش براساس، بکاپ؛ خروجی در انتهای چپ.
        actions = ttk.Frame(toolbar, style='Card.TFrame', padding=3)
        actions.pack(side='right', padx=(5, 3), pady=3)
        self.data_entry_add_button187 = ttk.Button(
            actions, text='افزودن', command=self.manual_transaction,
            style='Toolbar.TButton')
        self.data_entry_edit_button187 = ttk.Button(
            actions, text='ویرایش', command=self._edit_selected_187,
            style='Toolbar.TButton')
        self.data_entry_copy_button187 = ttk.Button(
            actions, text='کپی',
            command=lambda: self.copy_rows(self.table.selected_rows()),
            style='Toolbar.TButton')
        self.data_entry_delete_button187 = ttk.Button(
            actions, text='حذف',
            command=lambda: self.batch_delete18(self.table.selected_rows()),
            style='Toolbar.TButton')
        for button in (
            self.data_entry_add_button187, self.data_entry_edit_button187,
            self.data_entry_copy_button187, self.data_entry_delete_button187,
        ):
            button.pack(side='right', padx=2)

        status = ttk.Frame(toolbar, style='Card.TFrame', padding=3)
        status.pack(side='right', padx=3, pady=3)
        ttk.Label(status, text='نمایش براساس', style='Caption.TLabel').pack(
            side='right', padx=(3, 5))
        self.status_filter187 = tk.StringVar(value='همه')
        self.status_filter_combo187 = ttk.Combobox(
            status, textvariable=self.status_filter187, state='readonly',
            values=tuple(label for label, _key in self._STATUS_FILTERS_187),
            # Narrowed from 16 to make room for the count summary between
            # فراخوانی بکاپ and خروجی, per the operator's own ask.
            width=12, justify='right')
        self.status_filter_combo187.pack(side='right', padx=2)
        self.status_filter_combo187.bind(
            '<<ComboboxSelected>>', self._select_status_filter_187, add='+')
        self.status_buttons = {}

        # Operator round 2026-09-27: the counters take the backup button's
        # place beside the filter; «کل» keeps its caption, the other three
        # are numbers in their state's colour with the name on hover, so
        # every count shows in full.
        counts = ttk.Frame(toolbar, style='Card.TFrame', padding=3)
        counts.pack(side='right', padx=3, pady=3)
        self.data_entry_count_labels187 = {}
        p187 = palette_187()
        # Colour by meaning, text only - same convention every other table
        # in the app uses for these three states (yellow/green/red); کل
        # stays the plain text colour, not a fourth accent colour. No
        # coloured badge plate behind it.
        colours = {
            'total': p187['text'], 'review': p187['yellow'],
            'approved': p187['green'], 'hidden': p187['cream'], 'rejected': p187['red'],
        }
        for key, caption in (
            ('total', 'کل'), ('review', 'در دست بررسی'),
            ('approved', 'تاییدی'), ('hidden', 'پنهان شده'), ('rejected', 'رد شده'),
        ):
            item = ttk.Frame(counts, style='Card.TFrame')
            item.pack(side='right', padx=(10, 0))
            if key == 'total':
                # The colon as its own widget: a trailing ':' after RTL text
                # is bidi-neutral and lands on the wrong side.
                ttk.Label(item, text=caption, style='Caption.TLabel',
                          foreground=colours[key]).pack(side='right')
                ttk.Label(item, text=':', style='Caption.TLabel',
                          foreground=colours[key]).pack(side='right')
            else:
                dot = tk.Canvas(item, width=9, height=9, highlightthickness=0, bd=0,
                                bg=p187['panel'])
                dot.create_oval(1, 1, 8, 8, fill=colours[key], outline='')
                dot.pack(side='right', padx=(0, 3))
                attach_tooltip(item, caption, delay_ms=200, side='below')
                attach_tooltip(dot, caption, delay_ms=200, side='below')
            value = ttk.Label(
                item, text='۰', style='Caption.TLabel', foreground=colours[key],
                font=dashboard_font_187(self, 9, 'bold'),
            )
            value.pack(side='right', padx=(3, 0))
            if key != 'total':
                attach_tooltip(value, caption, delay_ms=200, side='below')
            self.data_entry_count_labels187[key] = value
        self._refresh_data_entry_counts_187()

        output = ttk.Frame(toolbar, style='Card.TFrame', padding=3)
        output.pack(side='left', padx=(3, 5), pady=3)
        self.output_var = tk.StringVar(value='خروجی')
        self.output_combo = ttk.Combobox(
            output, textvariable=self.output_var, state='readonly',
            values=('خروجی', 'PDF', 'Excel', 'پرینت'),
            width=16, justify='right', style='Output.TCombobox')
        self.output_combo.pack(side='right', padx=2)
        self.output_combo.bind('<<ComboboxSelected>>', self._output_selected, add='+')

        # «بارگذاری بکاپ» (was «فراخوانی بکاپ») with an upload icon, at the
        # left beside the export - a file you bring in, not a row action.
        backup = ttk.Frame(toolbar, style='Card.TFrame', padding=3)
        backup.pack(side='left', padx=3, pady=3)
        self.chat_backup_button = ttk.Button(
            backup, text='بارگذاری بکاپ', command=self.import_chat_backup,
            style='Toolbar.TButton', cursor='hand2')
        image = line_icon_187('upload', size=15, colour=p['text_primary'], background=None,
                              weight=1.15, master=self)
        if image is not None:
            self.chat_backup_button.configure(image=image, compound='right')
            self.chat_backup_button._barkav_icon_image187 = image
            self.chat_backup_button._barkav_action_icon187 = True
        self.chat_backup_button.pack(side='right', padx=2)
        self.ai_models187 = AIModelPicker187(backup, section='data_entry', base_dir=BASE_DIR, width=25,
                                         default_caption='مدل هوش مصنوعی')
        self.ai_models187.pack(side='right', padx=5)
        attach_tooltip(self.chat_backup_button,
                       'بارگذاری فایل بکاپ چت تلگرام و افزودن پیام‌های آن به ثبت دیتا',
                       delay_ms=300, side='below')

        toolbar.bind('<Configure>', lambda _event: self.after_idle(
            self._round_data_entry_toolbar_187), add='+')
        self.after_idle(self._round_data_entry_toolbar_187)

    def _output_selected(self, _event=None):
        """Preview the current Data Entry rows through the common report flow."""
        variable = getattr(self, 'output_var', None)
        if variable is None:
            return None
        selected = str(variable.get() or '')
        self.output_var.set('خروجی')
        if selected not in {'PDF', 'Excel', 'پرینت'}:
            return None
        table = getattr(self, 'table', None)
        if table is None:
            return None
        from report_document_stage18_7 import selected_tree_items, resolve_report_document_paths
        headers = [column[1] for column in getattr(table, 'COLUMNS', ())]
        rows = []
        db = self.rich.db
        mapping = getattr(table, 'iid_to_row', {})
        for iid in selected_tree_items(table.tree):
            values = dict(zip(headers, table.tree.item(iid, 'values')))
            values['__document_paths_187'] = resolve_report_document_paths(db, mapping.get(iid, {}))
            rows.append(values)
        from reports_stage18_7 import _export_through_preview_187
        return _export_through_preview_187(self, selected, headers, rows, 'ثبت دیتا')

    def _refresh_data_entry_counts_187(self):
        """Show shared data-entry counters, independent of the table filter."""
        labels = getattr(self, 'data_entry_count_labels187', None)
        if not labels:
            return
        try:
            hidden_ids = self.rich.hidden_review_ids()
            values = data_entry_read_service.pending_counts(self.rich.db, hidden_ids)
            values['hidden'] = data_entry_read_service.hidden_count(self.rich.db, hidden_ids)
        except Exception:
            values = {'total': 0, 'review': 0, 'approved': 0, 'hidden': 0, 'rejected': 0}
        for key, label in labels.items():
            try:
                label.configure(text=fa(values[key]))
            except tk.TclError:
                continue

    def _edit_selected_187(self):
        rows = self.table.selected_rows()
        if not rows:
            return messagebox.showwarning('ویرایش', 'یک سطر را انتخاب کن.', parent=self)
        return self.open_editor(rows[-1])

    def _select_status_filter_187(self, _event=None):
        selected = self.status_filter187.get()
        key = dict(self._STATUS_FILTERS_187).get(selected, 'همه')
        self.filter.set(key)
        self.refresh()

    def _set_data_entry_sort_187(self, mode):
        self._data_entry_sort187 = mode
        DB.set_setting(SORT_SETTING, mode)
        self.refresh()

    def _sync_data_entry_checks_187(self):
        tree = self.table.tree
        selected = set(tree.selection())
        positions = getattr(self, '_data_entry_row_positions187', {})
        for index, iid in enumerate(tree.get_children(), 1):
            row = self.table.iid_to_row.get(iid) or {}
            number = positions.get(str(row.get('pending_id')), index)
            values = list(tree.item(iid, 'values'))
            values[0] = f"{'☑' if iid in selected else '☐'} {fa(number)}"
            tree.item(iid, values=values)
        tree.heading('row', text='☑ ردیف' if selected and len(selected) == len(tree.get_children()) else '☐ ردیف')

    def _remove_bottom_actions_187(self):
        """Keep the table action strip in the toolbar; context actions remain."""
        pane = getattr(self, '_data_pane', None)
        if pane is None:
            return
        stack = list(pane.winfo_children())
        while stack:
            child = stack.pop()
            try:
                stack.extend(child.winfo_children())
            except tk.TclError:
                pass
            if isinstance(child, tk.Button):
                try:
                    text = str(child.cget('text'))
                except tk.TclError:
                    text = ''
                if text in {'حذف', 'کپی', 'پیست', 'اضافه کردن'}:
                    child.destroy()

    def _install_data_entry_context_actions_187(self):
        """Mirror the active actions in the native table context menu."""
        menu = getattr(self.table, 'menu', None)
        if menu is None:
            return
        sorting = tk.Menu(menu, tearoff=False)
        sorting.add_command(label='بر اساس ردیف', command=lambda: self._set_data_entry_sort_187('row'))
        sorting.add_command(label='بر اساس تاریخ', command=lambda: self._set_data_entry_sort_187('date'))
        menu.add_cascade(label='سورتینگ', menu=sorting)
        try:
            menu.insert_command(0, label='✏️ ویرایش', command=self._edit_selected_187)
        except tk.TclError:
            return
        try:
            # The inherited menu already owns this entry, but rebuilding the
            # 18.7 toolbar used to leave its callback unavailable in the
            # active table. Rebind it explicitly and force it enabled.
            menu.entryconfigure(
                '♻ پردازش مجدد AI', state='normal',
                command=self._reprocess_selected_with_choice_187,
            )
        except tk.TclError:
            menu.add_command(
                label='♻ پردازش مجدد AI',
                command=self._reprocess_selected_with_choice_187,
            )
        try:
            menu.entryconfigure(
                '➕ اضافه کردن', label='📥 کپی زیرسطر',
                command=lambda: self.paste_rows(self.table.selected_rows()),
            )
        except tk.TclError:
            menu.add_command(
                label='📥 کپی زیرسطر',
                command=lambda: self.paste_rows(self.table.selected_rows()),
            )
        try:
            menu.entryconfigure('🔄 بروزرسانی', command=self.refresh)
        except tk.TclError:
            menu.add_command(label='🔄 بروزرسانی', command=self.refresh)
        align_menu = getattr(self.winfo_toplevel(), '_right_align_financial_menu_187', None)
        if callable(align_menu):
            align_menu(menu)

    def _reprocess_selected_rows_187(self):
        rows = self.table.selected_rows()
        if not rows and getattr(self, 'current', None):
            rows = [self.current]
        return rows

    def _reprocess_selected_187(self):
        """Run AI again for the selected unread/reviewable receipts."""
        return self.reprocess_rows(self._reprocess_selected_rows_187())

    def _reprocess_selected_with_choice_187(self):
        """Context-menu entry point: let the operator pick quick (no
        preview, straight to the image pipeline - matches the older,
        pre-preview behaviour) vs. the text-preview/engine-pick flow,
        instead of always forcing the preview dialog open.
        """
        candidates = self._reprocess_candidates_187(self._reprocess_selected_rows_187())
        if not candidates:
            return None
        return self._show_reprocess_mode_choice_187(candidates)

    def _reprocess_candidates_187(self, rows):
        """Re-read only items that are still waiting for AI review.

        The table can retain a row object while the Telegram worker or another
        approval action changes its database status.  Refresh each selected row
        from SQLite before dispatching the worker so an already-posted/edit
        pending item cannot enter the AI pipeline and produce a misleading
        "no longer waiting" error.
        """
        preview = getattr(self, '_receipt_preview187', None)
        if preview is not None:
            preview.save_caption()
        candidates = []
        for row in rows or ([getattr(self, 'current', None)] if getattr(self, 'current', None) else []):
            if not row:
                continue
            pending_id = str(row.get('pending_id') or '')
            fresh = DB.get_pending_item(pending_id) if pending_id else None
            fresh = dict(fresh or row)
            if fresh.get('status') in {'PENDING_REVIEW', 'NEEDS_REVIEW'}:
                candidates.append(fresh)
        if not candidates:
            messagebox.showinfo(
                'پردازش مجدد',
                'فقط رسیدهای خوانده‌نشده یا نیازمند بررسی قابل پردازش هستند.',
                parent=self,
            )
            return None
        for row in candidates:
            _repair_pending_attachment_paths_187(row.get('pending_id'))
        return candidates

    def _center_reprocess_dialog_187(self, dialog, width=None, height=None):
        """Open a secondary progress/reprocess window at screen centre."""
        try:
            dialog.update_idletasks()
            if width is None:
                width = dialog.winfo_reqwidth()
            if height is None:
                height = dialog.winfo_reqheight()
            center_toplevel_on_screen(dialog, width=width, height=height)
        except tk.TclError:
            pass

    def _show_reprocess_mode_choice_187(self, candidates):
        """A quick چند-گزینه‌ای picker: launch straight away with the
        original image pipeline, or open the text-preview/engine-pick
        dialog first.
        """
        p = palette_187()
        dialog = BarkavWindow(self, 'پردازش مجدد', size_class='tiny', show_footer=False)
        content = dialog.body
        dialog.title('پردازش مجدد')
        dialog.configure(bg=p['bg'])
        dialog.transient(self)
        dialog.resizable(False, False)
        tk.Label(
            content,
            text=f'پردازش مجدد {fa(len(candidates))} رکورد — کدام روش؟',
            bg=p['bg'], fg=p['text_primary'], anchor='e', justify='right',
            font=dashboard_font_187(self, 10, 'body'),
        ).pack(fill='x', padx=18, pady=(18, 4))
        tk.Label(
            content,
            text='پردازش سریع بدون پیش‌نمایش، همان تصویر/متن قبلی را دوباره می‌فرستد.\n'
                 'پردازش با پیش‌نمایش اجازه می‌دهد متن را ویرایش و موتور را انتخاب کنی.',
            bg=p['bg'], fg=p['text_secondary'], anchor='e', justify='right',
            wraplength=420,
        ).pack(fill='x', padx=18, pady=(0, 14))
        actions = ttk.Frame(content)
        actions.pack(fill='x', padx=18, pady=(0, 18))

        def run_quick():
            dialog.destroy()
            return self._start_image_reprocess_187(candidates)

        def run_preview():
            dialog.destroy()
            return self._show_reprocess_preview_187(candidates)

        ttk.Button(actions, text='پردازش سریع', command=run_quick,
                   style='Toolbar.TButton').pack(side='right', padx=4)
        ttk.Button(actions, text='پردازش با پیش‌نمایش متن', command=run_preview,
                   style='Success.TButton').pack(side='right', padx=4)
        ttk.Button(actions, text='انصراف', command=dialog.destroy).pack(side='left', padx=4)
        dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
        self._center_reprocess_dialog_187(dialog)
        dialog.grab_set()
        dialog.focus_force()
        return dialog

    def reprocess_rows(self, rows):
        """Kept for non-interactive callers (chat-backup import bridge,
        tests) that expect the full preview/engine-pick flow directly with
        no intermediate quick/detailed choice.
        """
        candidates = self._reprocess_candidates_187(rows)
        if not candidates:
            return None
        return self._show_reprocess_preview_187(candidates)

    def _reprocess_preview_text_187(self, row):
        payload = dict(row.get('payload') or {})
        analysis = DB.get_receipt_analysis(str(row.get('pending_id') or '')) or {}
        source = DB.get_telegram_message(
            int(row.get('telegram_chat_id') or 0), int(row.get('telegram_message_id') or 0)) or {}
        parts = (
            ('متن پیام و کپشن', payload.get('receipt_caption') if 'receipt_caption' in payload else source.get('raw_text')),
            ('متن فاکتور / سند', payload.get('related_document_captions')),
            ('متن OCR سند', analysis.get('ocr_text')),
            ('متن قابل مشاهده', payload.get('raw_visible_text')),
        )
        lines = []
        seen = set()
        for label, value in parts:
            values = value if isinstance(value, list) else [value]
            for item in values:
                text = str(item or '').strip()
                if text and text not in seen:
                    seen.add(text)
                    lines.append(f'[{label}]\n{text}')
        return '\n\n'.join(lines)

    def _reprocess_available_engines_187(self):
        """(value, label) pairs for engines this project actually has a
        constructed, ready-to-use provider for - not the full aspirational
        AI_ENGINE_LABELS_187 roster, since a project may not have every key
        configured. The first entry is always the whole configured chain.
        """
        pairs = [('', 'خودکار (زنجیره‌ی کامل)')]
        chain = getattr(getattr(v182.APPROVAL, 'receipts', None), 'parser', None)
        for name, _provider in getattr(chain, '_all_providers187', None) or getattr(chain, 'providers', None) or ():
            pairs.append((name, AI_ENGINE_LABELS_187.get(name, name)))
        return pairs

    def _show_reprocess_preview_187(self, candidates):
        existing = getattr(self, '_reprocess_preview187', None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return
        candidates = list(candidates or [])
        if len(candidates) >= 15:
            status, label, progress = self._progress_dialog_187(
                'آماده‌سازی پیش‌نمایش',
                f'در حال آماده‌سازی متن {fa(len(candidates))} پیام…',
                total=len(candidates),
            )
            self._reprocess_preview187 = status
            events = Queue()

            def worker():
                try:
                    texts = []
                    for index, row in enumerate(candidates, 1):
                        texts.append(self._reprocess_preview_text_187(row))
                        events.put(('progress', index, None))
                    events.put(('done', len(candidates), texts))
                except Exception as exc:
                    events.put(('error', 0, exc))

            threading.Thread(target=worker, daemon=True).start()

            def poll_preview():
                finished = False
                while True:
                    try:
                        kind, count, payload = events.get_nowait()
                    except Empty:
                        break
                    if kind == 'progress':
                        progress['value'] = count
                        label.set(f'آماده‌سازی متن پیام {fa(count)} از {fa(len(candidates))}…')
                    elif kind == 'done':
                        texts = payload
                        self._close_progress_dialog_187(status, progress)
                        self._reprocess_preview187 = None
                        self._build_reprocess_preview_187(candidates, texts)
                        finished = True
                    elif kind == 'error':
                        self._close_progress_dialog_187(status, progress)
                        self._reprocess_preview187 = None
                        messagebox.showerror('پیش‌نمایش پیام‌ها', str(payload), parent=self)
                        finished = True
                if not finished and status.winfo_exists():
                    self.after(35, poll_preview)

            self.after(35, poll_preview)
            return status
        texts = [self._reprocess_preview_text_187(row) for row in candidates]
        return self._build_reprocess_preview_187(candidates, texts)

    def _build_reprocess_preview_187(self, candidates, texts):
        p = palette_187()
        dialog = BarkavWindow(self, 'پیش\u200cنمایش متن برای پردازش مجدد', size_class='large', show_footer=False, show_immediately=False)
        content = dialog.body
        dialog._barkav_skip_fade187 = True
        dialog.withdraw()
        self._reprocess_preview187 = dialog
        dialog.title('پیش‌نمایش متن برای پردازش مجدد')
        dialog.configure(bg=p['bg'])
        dialog.transient(self)
        dialog.minsize(760, 460)
        current = {'index': 0}
        selector = ttk.Combobox(
            content, state='readonly', justify='right', width=48,
            values=tuple(f"{index + 1} — {row.get('pending_id', '')}" for index, row in enumerate(candidates)),
        )
        selector.pack(fill='x', padx=14, pady=(14, 5))
        selector.current(0)

        engine_row = ttk.Frame(content)
        engine_row.pack(fill='x', padx=14, pady=(0, 5))
        ttk.Label(engine_row, text='موتور پردازش', style='Caption.TLabel').pack(side='right', padx=(6, 0))
        engine_pairs = self._reprocess_available_engines_187()
        engine_by_label = {label: value for value, label in engine_pairs}
        engine_selector = ttk.Combobox(
            engine_row, state='readonly', justify='right', width=32,
            values=tuple(label for _value, label in engine_pairs),
        )
        engine_selector.pack(side='right', padx=(0, 6))
        engine_selector.current(0)

        tk.Label(content, text='این متن قابل ویرایش است. حالت پیش‌فرض فقط همین متن را به موتور انتخاب‌شده می‌فرستد؛ تصویر دست‌نخورده می‌ماند.',
                 bg=p['bg'], fg=p['text_secondary'], anchor='e', justify='right', wraplength=1000).pack(fill='x', padx=14, pady=5)

        # Pack the action row from the bottom *before* the expanding text
        # editor, so it always keeps its own space and can never be
        # squeezed to zero height by a tall/wrapped description above it -
        # the same overflow bug class this project's own tab action-rows
        # have hit before (a later-packed, non-expanding sibling loses out
        # to an earlier expand=True one when total content exceeds the
        # window's height).
        actions = ttk.Frame(content)
        actions.pack(side='bottom', fill='x', padx=14, pady=(4, 14))

        holder = tk.Frame(content, bg=p['bg'])
        holder.pack(fill='both', expand=True, padx=14, pady=6)
        editor = tk.Text(holder, wrap='word', undo=True, bg=p['panel'], fg=p['text_primary'],
                         insertbackground=p['text_primary'], relief='flat', padx=10, pady=8)
        scrollbar = ttk.Scrollbar(holder, orient='vertical', command=editor.yview)
        editor.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        editor.pack(side='left', fill='both', expand=True)
        editor.insert('1.0', texts[0] or '')

        def save_current():
            texts[current['index']] = editor.get('1.0', 'end-1c').strip()

        def change_row(_event=None):
            save_current()
            current['index'] = max(0, int(selector.current()))
            editor.delete('1.0', 'end')
            editor.insert('1.0', texts[current['index']])

        selector.bind('<<ComboboxSelected>>', change_row)

        def close_preview():
            try:
                dialog.grab_release()
                dialog.destroy()
            except tk.TclError:
                pass
            self._reprocess_preview187 = None

        def process_text():
            save_current()
            if any(not text.strip() for text in texts):
                return messagebox.showwarning('پردازش مجدد', 'متن پیش‌نمایش هر رکورد باید خالی نباشد.', parent=dialog)
            engine = engine_by_label.get(engine_selector.get()) or None
            close_preview()
            return self._start_text_reprocess_187(candidates, texts, engine)

        def process_images():
            save_current()
            close_preview()
            return self._start_image_reprocess_187(candidates)

        ttk.Button(actions, text='پردازش متن (پیش‌فرض)', command=process_text,
                   style='Success.TButton').pack(side='right', padx=4)
        ttk.Button(actions, text='پردازش همراه تصویر', command=process_images,
                   style='Toolbar.TButton').pack(side='right', padx=4)
        ttk.Button(actions, text='انصراف', command=close_preview).pack(side='left', padx=4)
        dialog.protocol('WM_DELETE_WINDOW', close_preview)
        self._present_dialog_187(dialog, 1040, 600)
        return dialog

    def _start_image_reprocess_187(self, candidates):
        candidates = list(candidates or [])
        status, label, progress = self._progress_dialog_187(
            'پردازش رسیدها',
            f'در حال پردازش {fa(len(candidates))} رسید…',
            total=len(candidates),
        )
        results = Queue(maxsize=1)
        progress_events = Queue()
        started_at = time.monotonic()

        def worker():
            completed, finished, errors = 0, 0, []
            receipts = getattr(v182.APPROVAL, 'receipts', None)
            original_parser = getattr(receipts, 'parser', None)
            # Several Tesseract processes at once each try to use every core;
            # one thread per process keeps the batch from fighting itself.
            omp_before = os.environ.get('OMP_THREAD_LIMIT')
            os.environ['OMP_THREAD_LIMIT'] = '1'

            async def run_batch():
                nonlocal completed, finished
                gate = None
                if original_parser is not None:
                    gate = ReprocessApiGate187(original_parser, REPROCESS_API_SLOTS_187)
                    receipts.parser = gate
                semaphore = asyncio.Semaphore(REPROCESS_LOCAL_WORKERS_187)

                async def run(row):
                    nonlocal completed, finished
                    pending_id = str(row.get('pending_id') or '')
                    before = dict(row.get('payload') or {})
                    manual = set(before.get('v18_manual_fields') or [])
                    try:
                        async with semaphore:
                            await asyncio.wait_for(
                                v182.APPROVAL.analyze_pending_with_ai(pending_id),
                                REPROCESS_ITEM_TIMEOUT_187,
                            )
                        fresh = DB.get_pending_item(pending_id) or {}
                        after = dict(fresh.get('payload') or {})
                        suggestions = {}
                        for key in manual:
                            if key in before and after.get(key) != before[key]:
                                suggestions[key] = after.get(key)
                                after[key] = before[key]
                        after['v18_manual_fields'] = sorted(manual)
                        if suggestions:
                            after['v18_reprocess_suggestions'] = suggestions
                        DB.update_pending(
                            pending_id, payload=after,
                            detected_type=str(after.get('detected_type') or 'UNKNOWN').upper(),
                            confidence=float(after.get('confidence') or 0),
                            status=('NEEDS_REVIEW' if str(after.get('detected_type') or '').upper() == 'UNKNOWN'
                                    else 'PENDING_REVIEW'),
                        )
                        completed += 1
                    except Exception as exc:
                        errors.append(reprocess_error_text_187(pending_id, exc))
                    finally:
                        finished += 1
                        progress_events.put(finished)

                await asyncio.gather(*(run(row) for row in candidates))
                if gate is not None:
                    logging.getLogger(__name__).info(
                        'Receipt batch: %d receipts in %.0fs, %d AI calls (%.1fs in the AI, '
                        '%.1fs waiting for a slot), %d rate-limit pauses',
                        len(candidates), time.monotonic() - started_at, gate.calls,
                        gate.api_seconds, gate.wait_seconds, gate.rate_limited)

            try:
                asyncio.run(run_batch())
            except Exception as exc:
                errors.append(str(exc))
            finally:
                if receipts is not None:
                    receipts.parser = original_parser
                if omp_before is None:
                    os.environ.pop('OMP_THREAD_LIMIT', None)
                else:
                    os.environ['OMP_THREAD_LIMIT'] = omp_before
                results.put((completed, errors))

        threading.Thread(target=worker, daemon=True).start()

        shown = {'finished': 0}

        def poll():
            shown['finished'] = latest_reprocess_progress_187(progress_events, shown['finished'])
            finished = shown['finished']
            progress['value'] = finished
            label.set(reprocess_status_text_187(
                'رسید', finished, len(candidates), time.monotonic() - started_at))
            try:
                done, errors = results.get_nowait()
            except Empty:
                if status.winfo_exists():
                    self.after(60, poll)
                return
            took = f'\n\nزمان کل: {format_duration_187(time.monotonic() - started_at)}'
            progress['value'] = len(candidates)
            self._progress_phase_187(label, progress, 'در حال به‌روزرسانی جدول…')
            note = self._refresh_after_reprocess_187()
            self._close_progress_dialog_187(status, progress)
            if errors and done:
                messagebox.showwarning(
                    'پردازش رسیدها',
                    f'{fa(done)} رسید پردازش شد؛ خطاها:\n' + '\n'.join(errors[:6]) + took + note,
                    parent=self,
                )
            elif errors:
                messagebox.showerror('پردازش رسیدها', '\n'.join(errors[:6]) + took + note, parent=self)
            else:
                messagebox.showinfo(
                    'پردازش رسیدها', f'{fa(done)} رسید با موفقیت پردازش شد.' + took + note, parent=self,
                )

        self.after(60, poll)
        return status

    def _refresh_after_reprocess_187(self) -> str:
        """Repaint the table once a batch ends; report a repaint failure in the summary."""
        try:
            self.refresh()
        except Exception as exc:
            logging.getLogger(__name__).exception('Data Entry refresh after reprocessing failed')
            return f'\n\nبه‌روزرسانی جدول با خطا روبه‌رو شد: {exc}'
        return ''

    def _start_text_reprocess_187(self, candidates, texts, engine=None):
        results = Queue(maxsize=1)
        progress_events = Queue()
        started_at = time.monotonic()
        status, label, progress = self._progress_dialog_187(
            'پردازش متن', f'در حال پردازش متن {fa(len(candidates))} رکورد…',
            total=len(candidates),
        )

        def worker():
            completed, finished, errors = 0, 0, []
            # Picking a specific engine here swaps the shared APPROVAL.
            # receipts.parser singleton for the duration of this batch only,
            # then restores it - it is not persisted to ui.json, so it never
            # outlives this one reprocess call. A second reprocess started
            # from another window while this one is still running would see
            # the same swapped engine; narrow enough in practice (this is a
            # deliberate, multi-click action) not to warrant a lock.
            original_parser = v182.APPROVAL.receipts.parser
            if engine:
                from receipt_ai_provider import ReceiptVisionProviderChain
                chain = original_parser
                matches = [
                    pair for pair in (getattr(chain, '_all_providers187', None) or getattr(chain, 'providers', None) or ())
                    if pair[0] == engine
                ]
                if matches:
                    v182.APPROVAL.receipts.parser = ReceiptVisionProviderChain(
                        matches,
                        confidence_threshold=getattr(chain, 'confidence_threshold', 0.0),
                        stop_on_threshold=False,
                    )
            async def run_batch():
                nonlocal completed
                sem = asyncio.Semaphore(REPROCESS_API_SLOTS_187)
                async def run(row, text):
                    nonlocal completed, finished
                    pid = str(row.get('pending_id') or '')
                    before = dict(row.get('payload') or {})
                    manual = set(before.get('v18_manual_fields') or [])
                    try:
                        async with sem:
                            await asyncio.wait_for(
                                v182.APPROVAL.analyze_pending_text_only(pid, text),
                                REPROCESS_ITEM_TIMEOUT_187,
                            )
                        fresh = DB.get_pending_item(pid) or {}
                        after = dict(fresh.get('payload') or {})
                        suggestions = {}
                        for key in manual:
                            if key in before and after.get(key) != before.get(key):
                                suggestions[key] = after.get(key)
                                after[key] = before[key]
                        after['v18_manual_fields'] = sorted(manual)
                        if suggestions:
                            after['v18_reprocess_suggestions'] = suggestions
                        DB.update_pending(pid, payload=after,
                                          detected_type=str(after.get('detected_type') or 'UNKNOWN').upper(),
                                          confidence=float(after.get('confidence') or 0),
                                          status='NEEDS_REVIEW' if str(after.get('detected_type') or '').upper() == 'UNKNOWN' else 'PENDING_REVIEW')
                        completed += 1
                    except Exception as exc:
                        errors.append(reprocess_error_text_187(pid, exc))
                    finally:
                        finished += 1
                        progress_events.put(finished)
                await asyncio.gather(*(run(row, text) for row, text in zip(candidates, texts)))
            try:
                asyncio.run(run_batch())
            except Exception as exc:
                errors.append(str(exc))
            finally:
                v182.APPROVAL.receipts.parser = original_parser
            results.put((completed, errors))

        threading.Thread(target=worker, daemon=True).start()

        shown = {'finished': 0}

        def poll():
            shown['finished'] = latest_reprocess_progress_187(progress_events, shown['finished'])
            finished = shown['finished']
            progress['value'] = finished
            label.set(reprocess_status_text_187(
                'متن', finished, len(candidates), time.monotonic() - started_at))
            try:
                done, errors = results.get_nowait()
            except Exception:
                if status.winfo_exists():
                    self.after(60, poll)
                return
            took = f'\n\nزمان کل: {format_duration_187(time.monotonic() - started_at)}'
            progress['value'] = len(candidates)
            self._progress_phase_187(label, progress, 'در حال به‌روزرسانی جدول…')
            note = self._refresh_after_reprocess_187()
            self._close_progress_dialog_187(status, progress)
            if errors:
                messagebox.showwarning('پردازش مجدد', f'{fa(done)} رکورد پردازش شد؛ خطاها:\n' + '\n'.join(errors[:6]) + took + note, parent=self)
            else:
                messagebox.showinfo('پردازش مجدد', f'{fa(done)} رکورد با متن پیش‌نمایش پردازش شد.' + took + note, parent=self)
        self.after(60, poll)

    def copy_rows(self, rows):
        """Copy pending rows for both clipboard use and ``کپی زیرسطر``."""
        result = super().copy_rows(rows)
        if not rows:
            return result
        lines = []
        for row in rows:
            payload = dict(row.get('payload') or {})
            raw_date = str(payload.get('event_date_shamsi') or row.get('message_date') or '').split()[0]
            if raw_date.startswith(('19', '20')):
                try:
                    raw_date = gregorian_to_shamsi(date.fromisoformat(raw_date))
                except ValueError:
                    pass
            title = str(payload.get('v18_title') or payload.get('detected_type') or '-')
            subtype = str(payload.get('v18_subtype') or '-')
            description = str(payload.get('description') or row.get('raw_text') or '')
            lines.append('\t'.join((fa(raw_date), title, subtype, description, fa(f"{parse_int(payload.get('amount') or 0):,}"))))
        try:
            self.clipboard_clear()
            self.clipboard_append('\n'.join(lines))
        except tk.TclError:
            pass
        self.action.set(f'{fa(len(rows))} سطر کپی شد؛ با «کپی زیرسطر» کنار ردیف انتخابی درج می‌شود.')
        return result

    def _path(self, row):
        payload = row.get('payload') or {}
        if payload.get('receipt_image_deleted187'):
            return None
        path = payload.get('receipt_image_path')
        if path and Path(path).is_file():
            return str(path)
        return super()._path(row)

    def _show(self, row):
        controller = getattr(self, '_receipt_preview187', None)
        if controller:
            controller.save_caption()
        fresh = DB.get_pending_item(str(row.get('pending_id') or ''))
        if fresh:
            row = {**row, **fresh}
        super()._show(row)
        self.current = row
        payload = row.get('payload') or {}
        caption = payload.get('receipt_caption') if 'receipt_caption' in payload else v182._receipt_caption(row, payload)
        self.text.configure(state='normal', undo=True, exportselection=False)
        self.text.delete('1.0', 'end')
        self.text.tag_configure('rtl187', justify='right')
        self.text.insert('1.0', str(caption or ''), 'rtl187')
        self.text.tag_add('rtl187', '1.0', 'end')
        if controller:
            controller.set_row(row)

    def _receipt_image_history_state_187(self, pending_id):
        item = DB.get_pending_item(str(pending_id)) or {}
        payload = dict(item.get('payload') or {})
        return {
            'receipt_image_path': str(payload.get('receipt_image_path') or ''),
            'receipt_image_deleted187': bool(payload.get('receipt_image_deleted187')),
            'receipt_caption': str(payload.get('receipt_caption') or ''),
        }

    def _apply_receipt_image_history_187(self, pending_id, target):
        from receipt_evidence187 import remove_image, restore_archived_image, save_evidence

        target = dict(target or {})
        current = self._receipt_image_history_state_187(pending_id)
        current_path = str(current.get('receipt_image_path') or '')
        target_path = str(target.get('receipt_image_path') or '')
        target_caption = str(target.get('receipt_caption') or '')
        if current_path and not current.get('receipt_image_deleted187') and current_path != target_path:
            remove_image(DB, pending_id, current_path, target_caption)
            current = self._receipt_image_history_state_187(pending_id)
            current_path = str(current.get('receipt_image_path') or '')
        if target_path:
            if current_path == target_path and not current.get('receipt_image_deleted187'):
                save_evidence(DB, pending_id, {
                    'receipt_image_path': target_path,
                    'receipt_image_deleted187': False,
                    'receipt_caption': target_caption,
                })
            else:
                restore_archived_image(DB, pending_id, target_path, target_caption)
        else:
            if current_path and not current.get('receipt_image_deleted187'):
                remove_image(DB, pending_id, current_path, target_caption)
            save_evidence(DB, pending_id, {
                'receipt_image_path': '',
                'receipt_image_deleted187': bool(target.get('receipt_image_deleted187')),
                'receipt_caption': target_caption,
            })
        return self._receipt_image_history_state_187(pending_id)

    def undo_data_entry(self):
        stack = getattr(self, '_undo_stack', [])
        if not stack or stack[-1].get('kind') != 'receipt_image':
            return super().undo_data_entry()
        action = stack[-1]
        pending_id = str(action.get('pending_id') or '')
        current = self._receipt_image_history_state_187(pending_id)
        expected = action.get('undo_expected') or action.get('after') or {}
        if current != expected:
            return 'رسید پس از ثبت این عملیات تغییر کرده است؛ برای جلوگیری از بازنویسی، Undo انجام نشد.'
        try:
            restored = self._apply_receipt_image_history_187(pending_id, action.get('before'))
        except Exception as exc:
            return f'بازگردانی رسید انجام نشد: {exc}'
        self._undo_stack.pop()
        action['redo_expected'] = restored
        self._redo_stack.append(action)
        self.refresh()
        message = 'تغییر رسید بازگردانی شد.'
        self.action.set(message)
        return message

    def redo_data_entry(self):
        stack = getattr(self, '_redo_stack', [])
        if not stack or stack[-1].get('kind') != 'receipt_image':
            return super().redo_data_entry()
        action = stack[-1]
        pending_id = str(action.get('pending_id') or '')
        current = self._receipt_image_history_state_187(pending_id)
        expected = action.get('redo_expected') or {}
        if current != expected:
            return 'رسید پس از Undo تغییر کرده است؛ برای جلوگیری از بازنویسی، Redo انجام نشد.'
        try:
            redone = self._apply_receipt_image_history_187(pending_id, action.get('after'))
        except Exception as exc:
            return f'اجرای دوبارهٔ تغییر رسید انجام نشد: {exc}'
        self._redo_stack.pop()
        action['undo_expected'] = redone
        self._undo_stack.append(action)
        self.refresh()
        message = 'تغییر رسید دوباره اجرا شد.'
        self.action.set(message)
        return message

    def paste_rows(self, target_rows=None):
        from table_actions import copy_payload,copy_pending_attachments
        original_filter = self.filter.get()
        sources=list(getattr(self,'_copied_rows',[]) or [])
        if not sources:
            return messagebox.showinfo('کپی زیرسطر','ابتدا یک یا چند ردیف را کپی کنید.',parent=self)
        targets=list(target_rows or self.table.selected_rows() or [])
        target=targets[-1] if targets else None
        ids=[]
        try:
            with DB.atomic():
                mid=int(datetime.now().timestamp()*1_000_000)
                for index,source in enumerate(sources):
                    payload=copy_payload(source.get('payload'))
                    source_id=str(source.get('pending_id') or '')
                    payload.update(source='COPY_GUI_18_7',copied_from_pending_id=source_id)
                    DB.register_telegram_message(chat_id=-182,message_id=mid+index,
                        raw_text=v182._receipt_caption(source,payload),content_type='copy_gui',
                        message_date=datetime.now().isoformat(timespec='seconds'),state='RECEIVED')
                    pid=DB.create_or_replace_pending(telegram_chat_id=-182,telegram_message_id=mid+index,
                        detected_type=str(source.get('detected_type') or payload.get('detected_type') or 'UNKNOWN'),
                        payload=payload,confidence=float(source.get('confidence') or 1.0),status='PENDING_REVIEW')
                    copy_pending_attachments(DB,source_id,pid)
                    ids.append(str(pid))
                insert_data_entry_rows(DB, ids, target.get('pending_id') if target else None)
        except Exception as exc:
            return messagebox.showerror('کپی انجام نشد',str(exc),parent=self)
        self._set_hidden(ids,False)
        self._push_history({'kind':'paste','pending_ids':ids})
        self.filter.set(original_filter)
        self._data_entry_sort187 = 'row'
        DB.set_setting(SORT_SETTING, 'row')
        self.refresh();self._select_pending_ids(ids)
        self.action.set(f'{fa(len(ids))} ردیف با پیوست‌هایشان کپی شدند؛ برای ثبت مالی باید تأیید شوند.')
        return ids

    def _run_ai_ids(self, pending_ids) -> None:
        """Bridge inherited chat-backup imports to the active review pipeline."""
        rows = []
        for pending_id in pending_ids or ():
            try:
                row = DB.get_pending_item(str(pending_id))
            except sqlite3.Error:
                row = None
            if row:
                rows.append(dict(row))
        return self.reprocess_rows(rows)

    def _scroll_data_entry_right_187(self):
        """Open the RTL review table at its right-most horizontal position."""
        try:
            self.table.tree.xview_moveto(1.0)
        except tk.TclError:
            pass

    def _build_service_statuses_187(self):
        """Show concise Gemini and Telegram states without duplicate headings."""
        preview = getattr(self, 'preview', None)
        if preview is None:
            return
        host = preview.master
        p = palette_187()
        preview_title = next((
            child for child in host.winfo_children()
            if isinstance(child, (ttk.Label, tk.Label)) and
            str(child.cget('text') or '').strip() == 'پیش‌نمایش'
        ), None)
        self.service_status_host187 = tk.Frame(host, bg=p['panel'])
        self.service_status_host187.pack(
            fill='x', padx=7, pady=(7, 2), before=preview_title or preview)
        self.service_status_host187.grid_columnconfigure((0, 1), weight=1, uniform='service187')
        self.bot_label = self._service_status_value_187(self.service_status_host187, 1, self.bot)
        self.gemini_label = self._service_status_value_187(self.service_status_host187, 0, self.gemini)
        host.bind('<Configure>', lambda _event: self.after_idle(
            self._round_data_entry_preview_187), add='+')
        self.after_idle(self._round_data_entry_preview_187)

    def _service_status_value_187(self, parent, column, variable):
        p = palette_187()
        card = tk.Frame(parent, bg=p['surface'], highlightthickness=0)
        card.grid(row=0, column=column, sticky='ew', padx=2, pady=2)
        label = tk.Label(
            card, textvariable=variable, bg=p['surface'], fg=p['muted'], anchor='e',
            justify='right', wraplength=165, font=dashboard_font_187(self, 7, 'control'),
            padx=7, pady=3)
        label.pack(fill='x')
        return label

    def _configure_data_entry_columns_187(self):
        """Keep Data Entry focused on the ten fields requested for review."""
        columns = [
            ('row', 'ردیف', 60), ('date', 'تاریخ شمسی فارسی', 60),
            ('title', 'عنوان تراکنش', 60), ('type', 'نوع تراکنش', 60),
            ('desc', 'بابت', 60), ('amount', 'مبلغ', 60),
            ('payer', 'واریزکننده', 60), ('receiver', 'گیرنده', 60),
            ('phase', 'فاز اصلی', 60), ('subphase', 'فاز فرعی', 60),
        ]
        self.table.COLUMNS = columns
        tree = self.table.tree
        keys = tuple(key for key, _label, _width in columns)
        tree.configure(columns=keys, displaycolumns=tuple(reversed(keys)))
        tree._barkav_non_currency_columns_186 = {
            *getattr(tree, '_barkav_non_currency_columns_186', ()),
            'amount',
        }
        tree._barkav_currency_headings_186 = {
            **getattr(tree, '_barkav_currency_headings_186', {}),
            'amount': 'مبلغ',
        }
        for key, label, width in columns:
            tree.heading(key, text=label, command=self.table.toggle_all if key == 'row' else '')
            tree.column(key, width=width, minwidth=40, anchor='e', stretch=False)
        tree._barkav_data_entry_tree187 = True
        self._apply_data_entry_table_style_187()
        self._fit_data_entry_table_187()
        self._install_data_entry_row_separators_187()
        # Reattach after the column schema changes so horizontal-scroll
        # callbacks repaint the themed checks and status stripes again.
        decorate_rows_187(tree)

    @staticmethod
    def _data_entry_cell_text_187(value) -> str:
        """Keep one compact display line; the original pending payload is unchanged."""
        text = ' '.join(str(value or '—').split())
        row_number = re.fullmatch(r'([☐☑]\s*)([0-9۰-۹٠-٩,٬ ]+)', text)
        if row_number:
            prefix = row_number.group(1).rstrip()
            number = str(fa_grouped_number(fa(row_number.group(2))))
            return f'{prefix} {rtl_187(number)}'
        text = str(fa_grouped_number(fa(text)))
        return rtl_187(text or '—')

    def _apply_data_entry_table_style_187(self):
        """Use a smaller heading style only in this narrow review table."""
        tree = self.table.tree
        style = ttk.Style(tree)
        try:
            style.layout('DataEntry187.Treeview', style.layout('Barkav.Data.Treeview'))
            style.layout('DataEntry187.Treeview.Heading', style.layout('Barkav.Data.Treeview.Heading'))
        except tk.TclError:
            pass
        for option in ('background', 'fieldbackground', 'foreground', 'rowheight', 'font'):
            value = style.lookup('Barkav.Data.Treeview', option)
            if value:
                style.configure('DataEntry187.Treeview', **{option: value})
        heading_font = style.lookup('Barkav.Data.Treeview.Heading', 'font')
        heading_padding = style.lookup('Barkav.Data.Treeview.Heading', 'padding') or (4, 8)
        style.configure(
            'DataEntry187.Treeview.Heading',
            font=heading_font or dashboard_font_187(self, 10, 'control'),
            padding=heading_padding, anchor='e')
        tree.configure(style='DataEntry187.Treeview')

    def _fit_data_entry_table_187(self):
        """Use readable, bounded review columns without inflating every row."""
        tree = self.table.tree
        style = ttk.Style(tree)
        body_font = tkfont.Font(
            root=tree,
            font=style.lookup('DataEntry187.Treeview', 'font') or dashboard_font_187(self, 10),
        )
        heading_font = tkfont.Font(
            root=tree,
            font=style.lookup('DataEntry187.Treeview.Heading', 'font') or dashboard_font_187(self, 10, 'control'),
        )
        keys = tuple(tree.cget('columns'))
        caps = {
            'row': 64, 'date': 130, 'title': 165, 'type': 115, 'desc': 250,
            'amount': 140, 'payer': 150, 'receiver': 150,
            'phase': 160, 'subphase': 160,
        }
        widths = {
            key: min(
                caps.get(key, 180),
                max(40, heading_font.measure(str(tree.heading(key, 'text') or '')) + 22),
            )
            for key in keys
        }
        row_height = max(
            int(style.lookup('Barkav.Data.Treeview', 'rowheight') or 34),
            body_font.metrics('linespace') + 10,
        )
        # font.measure() on shaped Persian text costs ~1 ms per call and this
        # ran for every cell on every refresh; remember each text's width per
        # font, and stop measuring a column once it has reached its cap.
        font_key = str(body_font.actual())
        cache = getattr(self, '_data_entry_measure_cache187', None)
        if (cache is None or len(cache) > 20000
                or getattr(self, '_data_entry_measure_font187', None) != font_key):
            cache = self._data_entry_measure_cache187 = {}
            self._data_entry_measure_font187 = font_key
        for iid in tree.get_children(''):
            values = tuple(tree.item(iid, 'values') or ())
            for index, key in enumerate(keys):
                cap = caps.get(key, 180)
                if widths[key] >= cap:
                    continue
                value = self._data_entry_cell_text_187(
                    values[index] if index < len(values) else '')
                measured = cache.get(value)
                if measured is None:
                    measured = cache[value] = body_font.measure(value)
                widths[key] = min(cap, max(widths[key], measured + 22))
        # ``row`` is the last *visual* column because the display order is
        # reversed for RTL.  Let it absorb any spare viewport width so the
        # right edge of the table is occupied instead of showing an empty
        # strip after the final row number.
        for key, width in widths.items():
            tree.column(key, width=width, minwidth=width, stretch=(key == 'row'))
        style.configure('DataEntry187.Treeview', rowheight=row_height)
        return widths, row_height

    def _install_data_entry_row_separators_187(self):
        """Preserve one subtle horizontal boundary between visible table rows."""
        tree = self.table.tree
        # Half way from the rows' own colour to the subtle border: a quiet
        # line in either theme (operator round 2026-09-27: the full border
        # colour read as heavy dark bars between rows).
        p = palette_187()
        color = mix(p['row_even'], p['border_subtle'], 0.5)
        overlay = getattr(tree, '_barkav_horizontal_separator_overlay187', None)
        if overlay is None or getattr(overlay, '_dead', False):
            overlay = _HorizontalTreeSeparator187(tree, color)
            tree._barkav_horizontal_separator_overlay187 = overlay
        else:
            overlay.color = color
            overlay.schedule()
        return overlay

    def _append_data_entry_columns_187(self):
        tree = self.table.tree
        for iid in tree.get_children(''):
            row = self.table.iid_to_row.get(iid) or {}
            values = list(tree.item(iid, 'values') or ())
            tree.item(iid, values=map_data_entry_values_187(
                values, row, fa=fa, cell_text=self._data_entry_cell_text_187,
                source_layout='current' if len(values) == 10 else 'legacy'))

    def _round_data_entry_toolbar_187(self):
        from barkav_ui.skin import rounded_backdrop
        p = palette_187()
        rounded_backdrop(
            self.winfo_children()[0], fill=p['surface'], page=p['bg'],
            radius=max(6, theme_metrics_187().get('radius', 6)),
            border=p['border_subtle'], master=self,
        )

    def _round_data_entry_preview_187(self):
        preview = getattr(getattr(self, 'preview', None), 'master', None)
        if preview is None:
            return
        from barkav_ui.skin import rounded_backdrop
        p = palette_187()
        rounded_backdrop(
            preview, fill=p['panel'], page=p['bg'],
            radius=max(6, theme_metrics_187().get('radius', 6)),
            border=p['border_subtle'], master=self,
        )

    def _update_status_buttons(self, counts=None):
        """Keep the visible dropdown in sync with inherited filter operations."""
        visible = {key: label for label, key in self._STATUS_FILTERS_187}
        variable = getattr(self, 'status_filter187', None)
        if variable is not None:
            variable.set(visible.get(self.filter.get(), 'همه'))

    def _row_colors_185(self):
        """Use Claude/Bot3 semantic row colors for Data Entry.

        The inherited 18.3 table adds tx183_* tags for review rows. Those
        tags made the active Bot2 table use transaction-family colors instead
        of Claude's status palette. Normalize them back to the semantic
        pending/approved/rejected tags, while keeping alternating stripes for
        rows without a workflow status.
        """
        tree = self.table.tree
        light = str(load_ui().get('appearance') or 'dark').lower() == 'light'
        p = palette_187(light)
        tree.tag_configure('even', background=p['row_even'], foreground=p['text_primary'])
        tree.tag_configure('odd', background=p['row_odd'], foreground=p['text_primary'])
        for state in ('pending', 'approved', 'rejected'):
            tree.tag_configure(state, background=p[f'data_entry_{state}'],
                               foreground=p[f'data_entry_{state}_text'])
            # Operator feedback: the status tint read as brown on the dark
            # theme. Status rows keep their normal stripe colour; the status
            # itself is a tag with no background, which only the start-edge
            # stripe reads (barkav_ui.row_overlay.STATUS_STRIPES).
            tree.tag_configure(f'status_{state}', foreground=p['text_primary'])
        tree.tag_configure('status_hidden', foreground=p['text_primary'])
        status_by_value = {
            'APPROVED': 'approved',
            'REJECTED': 'rejected',
            'PENDING': 'pending',
            'PENDING_REVIEW': 'pending',
            'NEEDS_REVIEW': 'pending',
            'EDIT_PENDING': 'pending',
        }
        for index, item in enumerate(tree.get_children('')):
            tags = list(tree.item(item, 'tags') or ())
            row = getattr(self.table, 'iid_to_row', {}).get(item) or {}
            status_tag = ('hidden' if row.get('_hidden187')
                          else status_by_value.get(str(row.get('status') or '').upper()))
            custom = [
                tag for tag in tags
                if tag not in {'even', 'odd', 'pending', 'approved', 'rejected',
                               'status_pending', 'status_approved', 'status_rejected', 'status_hidden'}
                and not str(tag).startswith('tx183_')
            ]
            if status_tag:
                custom.append(f'status_{status_tag}')
            custom.append('even' if index % 2 == 0 else 'odd')
            tree.item(item, tags=tuple(custom))

    def refresh(self):
        """Carry a settled هزینه ساخت approval's payment onto قراردادها too.

        attach_payment_to_contract writes straight into the contracts store
        the moment such a transaction is approved; nothing then told the
        قراردادها table to reread that store, so a real payment sat showing
        as zero until something unrelated redrew it. Every approval path -
        the wizard, the full editor, the batch button - already ends by
        calling this refresh, so catching the contracts tab up here reaches
        all three, and rereading its store is cheap enough to do every time.
        """

        self._auto_phase_suggestions()
        hidden = self.rich.hidden_review_ids()
        allrows = [
            row for row in v182.APPROVAL.list_reviews(limit=3000, newest_first=True)
            if str(row.get('pending_id')) not in hidden
        ]
        showing_hidden = self.filter.get() == HIDDEN_FILTER_187
        if showing_hidden:
            # The cleared rows: every status, the ones deleted for good too. They are listed apart, so
            # neither the other categories nor the counters of the table change.
            allrows = []
            for row in hidden_rows_187(DB, self.rich):
                row['_hidden187'] = True
                allrows.append(row)
        # A row taken off the table with «حذف» gives its number up: the numbers of the rows that stay close the gap.
        # The hidden category itself keeps the full registration numbering.
        ordered_ids = [pid for pid in data_entry_row_order(DB) if showing_hidden or pid not in hidden]
        positions = {pid: index for index, pid in enumerate(ordered_ids, 1)}
        self._data_entry_row_positions187 = positions
        registration_key = lambda row: positions.get(str(row.get('pending_id')), len(positions) + 1)
        allrows.sort(key=(lambda row: (_record_date_order_187(row), registration_key(row)))
                     if self._data_entry_sort187 == 'date' else registration_key)
        counts = {
            'همه': len(allrows),
            'Pending': sum(row.get('status') in {'PENDING_REVIEW', 'NEEDS_REVIEW', 'EDIT_PENDING'} for row in allrows),
            'تأییدشده': sum(row.get('status') == 'APPROVED' for row in allrows),
            'ردشده': sum(row.get('status') == 'REJECTED' for row in allrows),
        }
        self._update_status_buttons(counts)
        selected_filter = self.filter.get()
        if selected_filter == HIDDEN_FILTER_187:
            selected_filter = 'همه'
        if selected_filter == 'تعیین تکلیف':
            # An already open view may still hold the removed queue filter.
            self.filter.set('همه')
            self.status_filter187.set('همه')
            selected_filter = 'همه'
        rows = allrows
        if selected_filter == 'Pending':
            rows = [row for row in rows if row.get('status') in {
                'PENDING_REVIEW', 'NEEDS_REVIEW', 'EDIT_PENDING',
            }]
        elif selected_filter == 'تأییدشده':
            rows = [row for row in rows if row.get('status') == 'APPROVED']
        elif selected_filter == 'ردشده':
            rows = [row for row in rows if row.get('status') == 'REJECTED']
        self.rows = rows

        def render(row, index):
            payload = row.get('payload') or {}
            title, subtype = v18._title_type_from_payload(payload)
            description = str(row.get('_lifecycle_decision187') or payload.get('description') or row.get('raw_text') or '')
            amount = payload.get('amount') or payload.get('paid_amount') or payload.get('final_amount') or 0
            due = payload.get('due_date_shamsi') if title == 'هزینه ساخت' and subtype == 'چک' else '—'
            return [
                f'☐ {fa(registration_key(row))}',
                str(row.get('message_date') or payload.get('event_date_shamsi') or '-').split()[0],
                title, subtype, description[:80], v18._group_money(amount),
                payload.get('receiver_name') or '—', payload.get('issuer_name') or '—',
                v18._display_payment(payload, title, subtype), due or '—',
                payload.get('main_phase') or '—', payload.get('sub_phase') or '—',
            ]

        self.table.set_rows(rows, render)
        # PendingTable18.set_rows underneath tags every row pending/approved/
        # rejected (tx183_<title> for a titled pending one) and repaints those
        # tags in its raw yellow, green and red: a slab over the whole row. A
        # status belongs only in the start-edge stripe (operator round
        # 2026-09-27, N1), which _row_colors_185 sets up. It has to run after
        # every rebuild, not once when the tab is built, or picking a status
        # filter floods the rows. The stage 18.5 refresh() that used to do this
        # is not in this chain: this one replaces it without calling super().
        self._row_colors_185()
        # Only tags changed. The row overlay (stripes, tick plates) repaints
        # when the tree scrolls or resizes, and a filter that leaves the row
        # count and the widths alone - approved to rejected, two rows each -
        # does neither: the last filter's stripe colours would stay up.
        overlay = getattr(self.table.tree, '_barkav_rows', None)
        if overlay is not None:
            overlay.schedule()
        self._append_data_entry_columns_187()
        self._sync_data_entry_checks_187()
        self._fit_data_entry_table_187()
        self._install_data_entry_row_separators_187()
        # set_rows() and the column fitter may replace scroll callbacks; the
        # decorator owns these callbacks so checks and stripes repaint on scroll.
        decorate_rows_187(self.table.tree)
        self.after_idle(self._scroll_data_entry_right_187)
        self._refresh_data_entry_counts_187()
        try:
            self._last_data_entry_pending_marker187 = self._pending_review_marker_187()
        except Exception:
            logging.getLogger(__name__).exception('Could not update Data Entry pending marker after refresh')
        contractors = (
            None if getattr(self, '_skip_contractors_refresh187', False) else
            getattr(self.winfo_toplevel(), 'contractors187', None)
        )
        if contractors is not None:
            try:
                contractors.refresh()
            except Exception:
                pass
        return None

    def open_wizard(self, row=None):
        """Keep sales receipt Add/Edit drafts reversible until their final approval."""
        row = row or getattr(self, 'current', None)
        if row and row.get('_lifecycle_decision_only187'):
            messagebox.showinfo('تعیین تکلیف',row['_lifecycle_decision187'],parent=self)
            return
        if not row or not is_temporary_sales_finance_pending_187(dict(row.get('payload') or {})):
            return super().open_wizard(row)
        pending_id = str(row.get('pending_id') or '')
        before = self._pending_snapshot(pending_id)

        def done():
            self._record_pending_edit(before)
            self._preview_signature_185 = None
            self.refresh()

        def abandon():
            item = DB.get_pending_item(pending_id) or {}
            if is_temporary_sales_finance_pending_187(dict(item.get('payload') or {})) and item.get('status') in {
                'PENDING_REVIEW', 'NEEDS_REVIEW', 'EDIT_PENDING',
            }:
                v186.APPROVAL.reject(pending_id, actor_id='GUI_187_SALES_FINANCE_CANCEL')
            self._preview_signature_185 = None
            self.refresh()

        def full():
            fresh = dict(DB.get_pending_item(pending_id) or row)
            SalesFinancePendingEditor187(self, fresh, self.rich, done, on_abandon=abandon)

        SalesFinancePendingWizard187(self, row, self.rich, done, full)

    def _service_status_181(self):
        """Refresh each service from its single, project-scoped status source."""
        self._cancel_data_entry_timer_187('_service_status_after187')
        if not self._is_data_entry_tab_active_187():
            return
        try:
            paths = bot_runtime_paths_187(BASE_DIR)
            inbound = None
            status = None
            try:
                if paths['inbound'].exists():
                    inbound = json.loads(paths['inbound'].read_text(encoding='utf-8'))
            except Exception:
                inbound = None
            try:
                if paths['status'].exists():
                    status = json.loads(paths['status'].read_text(encoding='utf-8'))
            except Exception:
                status = None
            p = palette_187()
            state = str((status or {}).get('state') or '').upper()
            ready = paths['ready'].exists()
            self._start_telegram_probe_187()
            health = getattr(self, '_telegram_health187', None)
            bot_running = ready and state not in {'ERROR', 'STOPPED'}
            if health == 'online' and bot_running:
                suffix = f"آخرین پیام #{fa(inbound.get('message_id'))}" if inbound and inbound.get('message_id') else 'آخرین پیام ثبت نشده'
                self.bot.set(f'تلگرام: آنلاین و آماده — {suffix}')
                self._set_service_status_187('bot', p['green'])
            elif health == 'failed' or state in {'ERROR', 'STOPPED'}:
                self.bot.set('تلگرام: قطع — اتصال برقرار نیست')
                self._set_service_status_187('bot', p['red'])
            else:
                self.bot.set(
                    'تلگرام: در حال بررسی اتصال'
                )
                self._set_service_status_187('bot', p['yellow'])
            self._refresh_gemini_status_187(p)
        except Exception:
            logging.getLogger(__name__).exception('Could not refresh Data Entry service status')
        if self._is_data_entry_tab_active_187():
            try:
                self._service_status_after187 = self.after(4000, self._service_status_181)
            except tk.TclError:
                self._service_status_after187 = None

    def _update_bot(self):
        """The 18.7 service probes own this badge; do not overwrite its text."""
        return None

    def _refresh_gemini_status_187(self, palette):
        """Probe Gemini periodically (throttled) without exposing its key or content."""
        parser = getattr(getattr(v186.APPROVAL, 'receipts', None), 'parser', None)
        providers = [str(item[0]) for item in getattr(parser, 'providers', [])]
        configured = any('GEMINI' in provider.upper() for provider in providers)
        legacy_dashboard = getattr(getattr(v186, 'v185', None), 'v18', None)
        configured_key = bool(str(
            getattr(getattr(legacy_dashboard, 'CONFIG', None), 'gemini_api_key', '') or '').strip())
        if not configured:
            # AI_PARSER's provider chain is a process-lifetime singleton built
            # from the AI Machine mode active at startup (dashboard_stage14.
            # AI_ENGINE_MODE_AT_STARTUP). If the operator has since switched
            # that setting to one that would include Gemini, say so plainly
            # instead of repeating the generic "not set up" message, which
            # reads as a config problem rather than a pending-restart one.
            current_mode = str(load_ui().get('ai_engine_mode') or 'AUTO').strip().upper()
            mode_now_allows_gemini = current_mode in ('AUTO', 'ALL', 'GEMINI')
            mode_changed_since_startup = current_mode != dashboard_stage14.AI_ENGINE_MODE_AT_STARTUP
            if configured_key and mode_changed_since_startup and mode_now_allows_gemini:
                self.gemini.set('جمینای: تنظیم AI Machine تغییر کرده — برای اعمال، برنامه را دوباره اجرا کنید')
                self._set_service_status_187('gemini', palette['yellow'])
            elif configured_key:
                self.gemini.set('جمینای: راه‌اندازی نشد — SDK یا مدل را بررسی کنید')
                self._set_service_status_187('gemini', palette['red'])
            else:
                self.gemini.set('جمینای: تنظیم نشده')
                self._set_service_status_187('gemini', palette['red'])
            return
        self._start_gemini_probe_187()
        health = getattr(self, '_gemini_health187', None)
        if health == 'online':
            self.gemini.set('جمینای: آنلاین و آماده')
            self._set_service_status_187('gemini', palette['green'])
        elif health == 'failed':
            # Only the exception's class name is shown (e.g. "PermissionDenied",
            # "TimeoutError") - enough to tell a bad key apart from a network
            # problem without ever printing the key or the SDK's full message.
            detail = getattr(self, '_gemini_health_detail187', None)
            suffix = f' ({detail})' if detail else ''
            self.gemini.set(f'جمینای: اتصال برقرار نشد{suffix} — شبکه یا کلید را بررسی کنید')
            self._set_service_status_187('gemini', palette['red'])
        else:
            self.gemini.set('جمینای: در حال بررسی اتصال')
            self._set_service_status_187('gemini', palette['yellow'])

    def _start_gemini_probe_187(self):
        """Verify access with a models-list call, outside the Tk event loop.

        Throttled and re-armed the same way as ``_start_telegram_probe_187``
        below, so a transient failure (or a key fixed after the first check)
        is reflected again within one cooldown window instead of the badge
        being stuck on the very first probe's result for the whole session.
        """
        if os.environ.get('BARKAV_RUN_UI_TESTS') == '1':
            return
        now = time.monotonic()
        if getattr(self, '_gemini_probe_running187', False):
            return
        if now - float(getattr(self, '_gemini_probe_started187', 0.0)) < 12.0:
            return
        legacy_dashboard = getattr(getattr(v186, 'v185', None), 'v18', None)
        api_key = str(getattr(getattr(legacy_dashboard, 'CONFIG', None), 'gemini_api_key', '') or '')
        self._gemini_probe_started187 = now
        self._gemini_probe_running187 = True

        def check():
            state = 'failed'
            detail = None
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                state = 'online' if next(iter(client.models.list(config={'page_size': 1})), None) else 'failed'
            except Exception as exc:
                state = 'failed'
                detail = exc.__class__.__name__
            if state == 'failed' and detail:
                logging.getLogger(__name__).warning('Gemini health probe failed: %s', detail)

            # Tk is refreshed on its own four-second cycle.  Do not call a
            # Tk method from this worker thread.
            self._gemini_health187 = state
            self._gemini_health_detail187 = detail
            self._gemini_probe_running187 = False

        threading.Thread(target=check, name='barkav-gemini-health', daemon=True).start()

    def _start_telegram_probe_187(self):
        """Check Telegram's own API periodically; a ready file alone is stale offline."""
        if os.environ.get('BARKAV_RUN_UI_TESTS') == '1':
            return
        now = time.monotonic()
        if getattr(self, '_telegram_probe_running187', False):
            return
        if now - float(getattr(self, '_telegram_probe_started187', 0.0)) < 12.0:
            return
        legacy_dashboard = getattr(getattr(v186, 'v185', None), 'v18', None)
        token = str(getattr(getattr(legacy_dashboard, 'CONFIG', None), 'telegram_bot_token', '') or '')
        self._telegram_probe_started187 = now
        self._telegram_probe_running187 = True

        def check():
            state = 'failed'
            try:
                request = urlrequest.Request(
                    f'https://api.telegram.org/bot{token}/getMe',
                    headers={'User-Agent': 'BARKAV-health'},
                )
                with urlrequest.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode('utf-8'))
                state = 'online' if bool(payload.get('ok')) else 'failed'
            except Exception:
                state = 'failed'
            self._telegram_health187 = state
            self._telegram_probe_running187 = False

        threading.Thread(target=check, name='barkav-telegram-health', daemon=True).start()

    def _set_service_status_187(self, service, color):
        body_label = getattr(self, f'{service}_label', None)
        if body_label is None:
            return
        try:
            body_label.configure(fg=color)
        except tk.TclError:
            pass


class SalesFinancePendingWizard187(v186.TransactionWizard186):
    """Never turn an edit preview into a duplicate buyer receipt."""
    def next(self):
        action = str((self.payload or {}).get('sales_pending_action') or '').upper()
        if action == 'EDIT' and self.page_index >= len(self.pages) - 1:
            return messagebox.showwarning(
                'ویرایش مالی',
                'ویرایش وصول تأییدشده باید از مسیر اصلاح حسابرسی انجام شود؛ ثبت جدید برای جلوگیری از واریزی تکراری متوقف شد.',
                parent=self,
            )
        return super().next()


class SalesFinancePendingEditor187(v186.UnifiedPendingEditor186):
    """Closing a temporary sales receipt draft is the same as rejecting it."""
    def __init__(self, parent, row, rich, on_done, *, on_abandon):
        self._on_abandon = on_abandon
        super().__init__(parent, row, rich, on_done)
        self.protocol('WM_DELETE_WINDOW', self._abandon)

    def _abandon(self):
        self.destroy()
        self._on_abandon()

    def approve(self):
        action = str((self.payload or {}).get('sales_pending_action') or '').upper()
        if action == 'EDIT':
            return messagebox.showwarning(
                'ویرایش مالی',
                'ویرایش وصول تأییدشده باید از مسیر اصلاح حسابرسی انجام شود؛ ثبت جدید برای جلوگیری از واریزی تکراری متوقف شد.',
                parent=self,
            )
        return super().approve()


class ProjectSettingsDialog187(v186.ProjectSettingsDialog186):
    """Keep project-profile controls compact and immediate in the active layer."""

    _REBUILD_FLOORS_LABEL = 'ایجاد/به‌روزرسانی ردیف‌های طبقات'
    _SAVE_BASE_SOURCE_LABEL = 'ذخیره مشخصات پایه'
    _SAVE_BASE_LABEL = 'ذخیره'
    _SAVE_TEAM_SOURCE_LABEL = 'ذخیره عوامل پروژه'
    _SAVE_TEAM_LABEL = 'ذخیره'

    def _build_team_tab(self, team, p):
        """Add employer identity to the existing project team profile."""
        super()._build_team_tab(team, p)
        old = self.profile.get('employer')
        old = old if isinstance(old, dict) else {}
        self.employer_vars187 = {
            key: tk.StringVar(value=fa(str(old.get(key) or '')))
            for key in ('name', 'phone', 'address')
        }
        shell = next((child for child in team.winfo_children()
                      if isinstance(child, tk.Frame) and child.winfo_class() == 'Frame'
                      and child.winfo_children() and isinstance(child.winfo_children()[0], tk.Canvas)), None)
        card = tk.Frame(team, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
        card.pack(fill='x', padx=8, pady=(8, 2), before=shell)
        tk.Label(card, text='کارفرما', bg=p['panel2'], fg=p['text'], anchor='e',
                 font=('Segoe UI', max(9, self.font_size - 1), 'bold'), padx=8, pady=5).pack(fill='x')
        body = tk.Frame(card, bg=p['surface'])
        body.pack(fill='x', padx=6, pady=4)
        for column, (key, label) in enumerate((('name', 'نام و نام خانوادگی / نام شرکت'),
                                                ('phone', 'شماره تماس'), ('address', 'آدرس'))):
            cell = tk.Frame(body, bg=p['surface'])
            cell.grid(row=0, column=column, sticky='ew', padx=3)
            body.grid_columnconfigure(column, weight=1, uniform='employer187')
            tk.Label(cell, text=label, bg=p['surface'], fg=p['muted'], anchor='e').pack(fill='x')
            ttk.Entry(cell, textvariable=self.employer_vars187[key], justify='right').pack(fill='x', pady=(2, 0))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title(f'مشخصات پروژه — BARKAV {DISPLAY_VERSION_187}')
        self.after_idle(self._compact_basic_actions_187)
        self.after_idle(self._compact_team_action_187)
        self.after_idle(self._compact_floor_actions_187)

    def _export_active(self, _event=None):
        selected = str(getattr(self, 'output_var', tk.StringVar()).get() or '')
        self.output_var.set('خروجی')
        if selected not in {'PDF', 'Excel', 'پرینت'}:
            return None
        title, headers, rows = self._active_export_data()
        from reports_stage18_7 import _export_through_preview_187
        return _export_through_preview_187(self, selected, headers, rows, str(title or 'مشخصات پروژه'))
    def save_team_185(self):
        result = super().save_team_185()
        variables = getattr(self, 'employer_vars187', {})
        self.profile['employer'] = {key: value.get().strip() for key, value in variables.items()}
        save_profile(self.profile)
        return result

    def _compact_basic_actions_187(self):
        """Remove the manual floor-rebuild action and replace save with a pill.

        Floor cards already rebuild when their three base-count fields change,
        so exposing a second manual action is redundant.  The replacement
        keeps the original save callback and is deliberately the same compact
        height as the tab strip.
        """
        basic = getattr(self, '_project_tabs', {}).get('مشخصات پایه')
        if basic is None:
            return
        save_button = None
        for widget in list(v186._walk(basic)):
            if not isinstance(widget, tk.Button):
                continue
            try:
                label = str(widget.cget('text') or '')
            except tk.TclError:
                continue
            if label == self._REBUILD_FLOORS_LABEL:
                widget.destroy()
            elif label == self._SAVE_BASE_SOURCE_LABEL:
                save_button = widget

        if save_button is None:
            return
        try:
            parent = save_button.master
            pack = dict(save_button.pack_info())
        except tk.TclError:
            return
        pack.pop('in', None)
        save_button.destroy()
        pill = ttk.Button(
            parent,
            text=self._SAVE_BASE_LABEL,
            command=self.save_basic_185,
            style='Primary.TButton',
            width=14,
        )
        # The rounded skin fixes this control at the shared 28px pill height;
        # its width is intentionally close to a primary tab rather than a
        # large full-row action.
        pill.pack(**pack)
        self.save_basic_button187 = pill

    def _compact_team_action_187(self):
        """Replace the team save rectangle with the shared primary pill."""
        team = getattr(self, '_project_tabs', {}).get('عوامل پروژه')
        if team is None:
            return
        for widget in list(v186._walk(team)):
            if not isinstance(widget, tk.Button):
                continue
            try:
                if str(widget.cget('text') or '') != self._SAVE_TEAM_SOURCE_LABEL:
                    continue
                parent = widget.master
                pack = dict(widget.pack_info())
            except tk.TclError:
                continue
            pack.pop('in', None)
            widget.destroy()
            pill = ttk.Button(
                parent,
                text=self._SAVE_TEAM_LABEL,
                command=self.save_team_185,
                style='Primary.TButton',
                width=10,
            )
            pill.pack(**pack)
            self.save_team_button187 = pill
            return

    def _compact_floor_actions_187(self):
        """Keep the floor actions compact, rounded, and in their final places."""
        floors = getattr(self, '_project_tabs', {}).get('طبقات و واحدها')
        if floors is None:
            return
        add_button = save_button = None
        for widget in list(v186._walk(floors)):
            if not isinstance(widget, tk.Button):
                continue
            try:
                label = str(widget.cget('text') or '')
            except tk.TclError:
                continue
            if label == 'افزودن طبقه':
                add_button = widget
            elif label == 'ذخیره و همگام‌سازی واحدها':
                save_button = widget

        if add_button is not None:
            try:
                parent = add_button.master
                pack = dict(add_button.pack_info())
                pack.pop('in', None)
                add_button.destroy()
                self.add_floor_button187 = ttk.Button(
                    parent, text='افزودن طبقه', command=self.add_floor_185,
                    style='Ghost.TButton', width=12,
                )
                self.add_floor_button187.pack(**pack)
            except tk.TclError:
                pass

        if save_button is None:
            return
        try:
            save_button.destroy()
        except tk.TclError:
            return
        action_bar = tk.Frame(floors, bg=palette_187()['panel'])
        action_bar.pack(side='bottom', fill='x', padx=8, pady=(0, 8))
        self.save_floors_button187 = ttk.Button(
            action_bar, text='ذخیره', command=self.save_floors_185,
            style='Primary.TButton', width=12,
        )
        self.save_floors_button187.pack(side='right', padx=4, pady=4)

    def _capture_floor_cards(self) -> list[dict]:
        """Assign new unit fields after the greatest existing numeric unit.

        ``ProjectSettingsDialog185`` creates added unit records with a local
        ``1..n`` fallback.  That duplicates numbers when a later floor (or a
        larger unit count) is rendered.  Only fields that did not previously
        exist receive a new value; all user-entered values remain untouched.
        """
        visible_lengths = [len(card.get('unit_vars') or []) for card in self.floor_cards]
        rows = super()._capture_floor_cards()
        used_numbers = []
        for row, visible_count in zip(rows, visible_lengths):
            for unit in (row.get('units') or [])[:visible_count]:
                value = en(unit.get('unit_number') or '').strip()
                if value.isdigit():
                    used_numbers.append(int(value))
        next_number = max(used_numbers, default=0) + 1
        for row, visible_count in zip(rows, visible_lengths):
            for unit in (row.get('units') or [])[visible_count:]:
                unit['unit_number'] = str(next_number)
                next_number += 1
        return rows

    def _render_floor_cards(self):
        """Make unit and storage detail cards react to their counts directly.

        The inherited implementation contains an explicit ``اعمال تعداد``
        action.  That makes the visible fields depend on an extra click and
        encourages users to leave an edited count unapplied.  Keep its proven
        data-capture/rendering logic, then remove that action and attach a
        short, debounced rebuild to the two count variables instead.
        """
        super()._render_floor_cards()
        self._install_floor_count_updates_187()
        self._replace_floor_card_actions_187()

    def _install_floor_count_updates_187(self):
        """Queue one redraw after count typing settles, not per keypress."""
        for card in self.floor_cards:
            for key in ('unit_count', 'storage_count'):
                variable = card.get(key)
                if variable is None or getattr(variable, '_barkav187_auto_count', False):
                    continue
                variable.trace_add(
                    'write',
                    lambda *_args: self._queue_floor_detail_redraw(),
                )
                variable._barkav187_auto_count = True

    def _replace_floor_card_actions_187(self):
        """Remove manual apply controls and use a themed pill for deletion."""
        card_index = 0
        for card_widget in list(self.floor_body.winfo_children()):
            if not isinstance(card_widget, tk.Frame):
                continue
            children = card_widget.winfo_children()
            if not children or not isinstance(children[0], tk.Frame):
                continue
            head = children[0]
            for widget in list(head.winfo_children()):
                if not isinstance(widget, tk.Button):
                    continue
                try:
                    label = str(widget.cget('text') or '')
                except tk.TclError:
                    continue
                if label == 'اعمال تعداد':
                    widget.destroy()
                    continue
                if label != 'حذف سطر':
                    continue
                try:
                    grid = dict(widget.grid_info())
                except tk.TclError:
                    continue
                grid.pop('in', None)
                widget.destroy()
                ttk.Button(
                    head,
                    text='حذف سطر',
                    command=lambda index=card_index: self.remove_floor_185(index),
                    style='Danger.TButton',
                    width=9,
                ).grid(**grid)
            card_index += 1

        for widget in v186._walk(self.floor_body):
            if not isinstance(widget, tk.Label):
                continue
            try:
                label = str(widget.cget('text') or '')
            except tk.TclError:
                continue
            if '«اعمال تعداد»' in label:
                widget.configure(
                    text='تعداد انباری بام را وارد کنید؛ کادرها خودکار نمایش داده می‌شوند.'
                )


class ChartDetailDialog187(BarkavWindow):
    size_class = 'large'

    def __init__(self, parent: 'Stage187Dashboard', kind: str):
        titles = {
            'donut': 'جزئیات ترکیب فازها',
            'line': 'جزئیات روند تجمعی',
            'bar': 'جزئیات مقایسه فازها',
        }
        super().__init__(parent, titles[kind], size_class=self.size_class, show_footer=False)
        self.parent_app = parent
        self.kind = kind
        p = palette_187()
        self.configure(bg=p['bg'])
        tk.Label(self.body, text=titles[kind], bg=p['surface'], fg=p['text'],
                 anchor='e', font=dashboard_font_187(self, 14, 'title'), padx=14, pady=10).pack(fill='x')
        if kind == 'donut':
            self._build_donut()
        elif kind == 'line':
            self._build_line()
        else:
            self._build_bar()

    def _table(self, columns, parent=None):
        tree = ttk.Treeview(parent or self.body,
                            columns=tuple(key for key, _label, _width in columns),
                            show='headings')
        for key, label, width in columns:
            tree.heading(key, text=label, anchor='e')
            tree.column(key, width=width, anchor='e')
        apply_tree_rtl_kit(tree)
        tree.pack(fill='both', expand=True, padx=10, pady=(4, 10))
        return tree

    _DONUT_MODES_187 = (
        ('همه', None, None),
        ('برآورد', 'estimate', 'orange'),
        ('بروز', 'forecast', 'blue'),
        ('واقعی', 'actual', 'green'),
    )
    _DONUT_PHASE_COLORS_187 = ('blue', 'green', 'orange', 'violet', 'cyan', 'red')

    def _build_donut(self):
        """Build the plan-backed phase composition view and its mode selector."""
        p = palette_187()
        controls = tk.Frame(self.body, bg=p['bg'])
        controls.pack(fill='x', padx=10, pady=(6, 0))
        tk.Label(
            controls, text='نمایش بر اساس', bg=p['bg'], fg=p['text_secondary'],
            font=dashboard_font_187(self, 9, 'control'), anchor='e',
        ).pack(side='right', padx=(0, 6))
        self.donut_mode187 = tk.StringVar(value='همه')
        mode_combo = ttk.Combobox(
            controls, textvariable=self.donut_mode187, state='readonly',
            values=tuple(label for label, _key, _color in self._DONUT_MODES_187),
            justify='right', width=15,
        )
        mode_combo.pack(side='right')
        mode_combo.bind('<<ComboboxSelected>>', lambda _event: self._refresh_donut_187(), add='+')

        self.donut_charts187 = tk.Frame(self.body, bg=p['bg'], height=330)
        self.donut_charts187.pack(fill='x', padx=10, pady=(4, 6))
        self.donut_charts187.pack_propagate(False)
        self.donut_table187 = tk.Frame(self.body, bg=p['bg'])
        self.donut_table187.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        self._refresh_donut_187()

    @classmethod
    def _donut_mode_spec_187(cls, label: str):
        return next(
            (item for item in cls._DONUT_MODES_187 if item[0] == label),
            cls._DONUT_MODES_187[0],
        )

    def _donut_values_187(self, phases, key: str):
        values = [(row, float(row.get(key) or 0)) for row in phases]
        total = sum(value for _row, value in values)
        rows = [
            (row, value, value / total * 100)
            for row, value in values
            if total > 0 and value / total * 100 > 1.0
        ]
        return values, total, rows

    def _add_donut_chart_187(self, parent, *, label: str, key: str,
                              compact: bool, column: int = 0, phases=None):
        phases = list(phases if phases is not None else self.parent_app._phase_summary_live())
        _values, _total, rows = self._donut_values_187(phases, key)
        chart = v186.v18.v175.DonutChart175(
            parent, f'ترکیب فازها — {label}', 320 if compact else 360,
        )
        if compact:
            chart.grid(row=0, column=column, sticky='nsew', padx=4)
        else:
            chart.pack(fill='both', expand=True)
        apply_donut_theme_187(chart, detail=True, compact=compact)
        chart.set_items([
            (str(row.get('phase') or ''), value,
             self._DONUT_PHASE_COLORS_187[index % len(self._DONUT_PHASE_COLORS_187)])
            for index, (row, value, _percent) in enumerate(rows)
        ])
        return chart

    def _refresh_donut_187(self):
        """Redraw exactly the plan totals chosen in the display selector."""
        selected, key, _color = self._donut_mode_spec_187(self.donut_mode187.get())
        phases = list(self.parent_app._phase_summary_live())
        for child in self.donut_charts187.winfo_children():
            child.destroy()
        for child in self.donut_table187.winfo_children():
            child.destroy()

        if key is None:
            self.donut_charts187.configure(height=330)
            for column in range(3):
                self.donut_charts187.grid_columnconfigure(column, weight=1, uniform='donuts187')
            for index, (label, mode_key, _mode_color) in enumerate(self._DONUT_MODES_187[1:]):
                # RTL: estimate stays at the right, then updated, then actual.
                self._add_donut_chart_187(
                    self.donut_charts187, label=label, key=mode_key,
                    compact=True, column=2 - index, phases=phases,
                )
            tree = self._table([
                ('no', 'شماره فاز', 90), ('phase', 'نام فاز', 250),
                ('estimate', 'برآورد (تومان)', 175),
                ('forecast', 'بروز (تومان)', 175),
                ('actual', 'واقعی (تومان)', 175),
            ], parent=self.donut_table187)
            for index, row in enumerate(phases):
                tree.insert('', 'end', iid=str(index), values=(
                    fa(f"{int(row.get('phase_no') or 0):02d}"), row.get('phase') or '-',
                    fa(f"{int(row.get('estimate') or 0):,}"),
                    fa(f"{int(row.get('forecast') or 0):,}"),
                    fa(f"{int(row.get('actual') or 0):,}"),
                ))
            return

        self.donut_charts187.configure(height=390)
        self.donut_charts187.grid_columnconfigure(0, weight=1)
        self._add_donut_chart_187(
            self.donut_charts187, label=selected, key=key,
            compact=False, phases=phases,
        )
        _values, total, rows = self._donut_values_187(phases, key)
        tree = self._table([
            ('no', 'شماره فاز', 90), ('phase', 'نام فاز', 350),
            ('amount', f'{selected} (تومان)', 190), ('percent', 'سهم', 100),
        ], parent=self.donut_table187)
        for index, row in enumerate(phases):
            value = float(row.get(key) or 0)
            percent = value / total * 100 if total else 0
            tree.insert('', 'end', iid=str(index), values=(
                fa(f"{int(row.get('phase_no') or 0):02d}"), row.get('phase') or '-',
                fa(f'{int(value):,}'), fa(f'{percent:.1f}') + '٪',
            ))

    def _build_line(self):
        series = list(getattr(self.parent_app.liquidity_chart, 'series', []) or [])
        chart = v186.v18.v175.MiniLineChart(self.body, 'روند تجمعی برآورد / واقعی / بروز', 390)
        chart.pack(fill='x', padx=10, pady=10)
        apply_line_theme_187(chart)
        chart.set_series(series)
        tree = self._table([
            ('point', 'نقطه/فاز', 100), ('estimate', 'برآورد', 190),
            ('actual', 'واقعی', 190), ('forecast', 'بروز', 190),
        ])
        by_label = {label: list(values) for label, values, _color in series}
        count = max((len(values) for values in by_label.values()), default=0)
        for index in range(count):
            def value(label):
                items = by_label.get(label, [])
                return items[index] if index < len(items) else 0
            tree.insert('', 'end', values=(
                fa(index + 1), fa(f"{int(value('برآورد')):,}"),
                fa(f"{int(value('واقعی')):,}"), fa(f"{int(value('پیش‌بینی')):,}"),
            ))

    def _build_bar(self):
        rows = list(getattr(self.parent_app.phase_chart, 'rows', []) or [])
        chart = v186.v18.v175.MiniBarChart(self.body, 'مقایسه کامل فازها', 390)
        chart.pack(fill='x', padx=10, pady=10)
        apply_bar_theme_187(chart)
        chart.set_rows(rows)
        tree = self._table([
            ('phase', 'فاز', 100), ('estimate', 'برآورد', 190),
            ('actual', 'واقعی', 190), ('forecast', 'بروز', 190),
        ])
        for label, estimate, actual, forecast in rows:
            tree.insert('', 'end', values=(
                fa(label), fa(f'{int(estimate):,}'), fa(f'{int(actual):,}'),
                fa(f'{int(forecast):,}'),
            ))


def calculate_loan_installment_187(principal: int | float, annual_rate: int | float,
                                   installment_count: int) -> int:
    """Return the rounded monthly annuity payment used by bank schedules."""
    principal = int(principal or 0)
    count = int(installment_count or 0)
    if principal <= 0 or count <= 0:
        return 0
    monthly = float(annual_rate or 0) / 100.0 / 12.0
    if monthly <= 0:
        return int(round(principal / count))
    factor = (1.0 + monthly) ** count
    return int(round(principal * monthly * factor / (factor - 1.0)))


def loan_total_interest_187(principal: int | float, installment_amount: int | float,
                            installment_count: int) -> int:
    """Return the interest implied by the entered installment amount and count."""
    return max(0, int(installment_amount or 0) * int(installment_count or 0)
               - int(principal or 0))


def _is_facility_payload_187(title: str, subtype: str) -> bool:
    return title == 'ورودی' and subtype == 'تسهیلات'


def _is_installment_payload_187(title: str, subtype: str) -> bool:
    """A payment of a loan instalment: the loan's schedule decides what it pays, not a payment method."""
    return title == 'خروجی' and subtype == 'اقساط'


#: The counts of an instalment payment that can be typed over; the paid-now count was typed already.
_INSTALLMENT_TYPED_KEYS_187 = ('paid_installments_before', 'remaining_installments')


# Non-financial records keep the existing internal title «یادداشت» so older
# approval and database code remains compatible.  The document tab is renamed
# in the active dashboard; these values are the user-facing record subtypes.
_DOCUMENT_SUBTYPE_ALIASES_187 = {
    'یاداوری': 'یادآوری',
    'یادآوری': 'یادآوری',
}
_DOCUMENT_SUBTYPE_CODES_187 = {
    'تقویم کارگاهی': 'WORKSHOP_CALENDAR',
    'گزارش روزانه': 'DAILY_REPORT',
    'داکیومنت': 'DOCUMENT',
    'یادآوری': 'REMINDER',
    'یادداشت': 'NOTE',
    'اطلاع‌رسانی': 'INFO',
    # Named apart from document_type=INVOICE (an attached image's own
    # classification, unrelated to this note-category code) so the two are
    # never confused despite both fields sharing the name "document_type".
    'فاکتور': 'INVOICE_NOTE',
}
_DOCUMENT_CODE_TO_SUBTYPE_187 = {
    code: subtype for subtype, code in _DOCUMENT_SUBTYPE_CODES_187.items()
}


def _canonical_document_subtype_187(value: str) -> str:
    value = str(value or '').strip()
    return _DOCUMENT_SUBTYPE_ALIASES_187.get(value, value)


def _is_nonfinancial_payload_187(title: str, subtype: str) -> bool:
    return title == 'یادداشت' and _canonical_document_subtype_187(subtype) in _DOCUMENT_SUBTYPE_CODES_187


def _note_without_payment_method_187(title: str, subtype: str) -> bool:
    """Records that are not paid by a method: every kind of note (document, notice, invoice note, report,
    reminder...), a loan (it is paid into the account) and an instalment of a loan (the loan's schedule posts it)."""
    return (title == 'یادداشت'
            or _is_facility_payload_187(title, subtype) or _is_installment_payload_187(title, subtype))


def _combo_keyboard_values_187(widget):
    try:
        values = widget.cget('values')
        if isinstance(values, str):
            values = widget.tk.splitlist(values)
        return tuple(str(value) for value in (values or ()))
    except (AttributeError, tk.TclError, TypeError):
        return ()


def _combo_keyboard_index_187(widget, values):
    try:
        index = int(widget.current())
    except (tk.TclError, TypeError, ValueError):
        index = -1
    if not 0 <= index < len(values):
        try:
            index = values.index(str(widget.get()))
        except (ValueError, tk.TclError):
            index = -1
    return index


def _combo_keyboard_move_187(event, direction):
    widget = event.widget
    try:
        if str(widget.cget('state')) != 'readonly':
            return None
    except (AttributeError, tk.TclError):
        return None
    values = _combo_keyboard_values_187(widget)
    if not values:
        return 'break'
    index = _combo_keyboard_index_187(widget, values)
    if index < 0:
        index = 0 if direction > 0 else len(values) - 1
    else:
        index = max(0, min(len(values) - 1, index + direction))
    try:
        widget.current(index)
    except tk.TclError:
        return 'break'
    return 'break'


def _combo_keyboard_select_187(event):
    widget = event.widget
    try:
        if str(widget.cget('state')) != 'readonly':
            return None
    except (AttributeError, tk.TclError):
        return None
    values = _combo_keyboard_values_187(widget)
    if _combo_keyboard_index_187(widget, values) < 0:
        return 'break'
    try:
        widget.event_generate('<<ComboboxSelected>>')
    except tk.TclError:
        pass
    return 'break'


def _focus_next_keyboard_187(event, direction):
    widget = event.widget
    try:
        target = widget.tk_focusNext() if direction > 0 else widget.tk_focusPrev()
        if target is not widget:
            target.focus_set()
    except (AttributeError, tk.TclError):
        pass
    return 'break'


def _install_form_keyboard_navigation_187(owner):
    """Enable predictable field traversal and keyboard selection app-wide."""
    try:
        root = owner._root()
        if getattr(root, '_barkav_form_keyboard187', False):
            return
        root.bind_class('TEntry', '<Tab>', lambda event: _focus_next_keyboard_187(event, 1))
        root.bind_class('TEntry', '<Shift-Tab>', lambda event: _focus_next_keyboard_187(event, -1))
        root.bind_class('TCombobox', '<Tab>', lambda event: _focus_next_keyboard_187(event, 1))
        root.bind_class('TCombobox', '<Shift-Tab>', lambda event: _focus_next_keyboard_187(event, -1))
        root.bind_class('TCombobox', '<Up>', lambda event: _combo_keyboard_move_187(event, -1))
        root.bind_class('TCombobox', '<Down>', lambda event: _combo_keyboard_move_187(event, 1))
        root.bind_class('TCombobox', '<Return>', _combo_keyboard_select_187)
        root.bind_class('TCombobox', '<KP_Enter>', _combo_keyboard_select_187)
        root._barkav_form_keyboard187 = True
    except (AttributeError, tk.TclError):
        return


def _note_phase_field_187():
    from ai_parser import CONSTRUCTION_PHASES
    return v18.FieldDef('construction_stage', 'فاز ساخت', 'combo',
                       tuple(f'{number:02d} — {name}' for number, name in enumerate(CONSTRUCTION_PHASES, 1)))


def _phase_name_187(value):
    text = str(value or '').strip()
    number, separator, name = text.partition('—')
    return name.strip() if separator and number.strip().isdigit() else text


def _phase_display_187(form, value):
    name = _phase_name_187(value)
    choices = _note_phase_choices_187(form) if form.title_var.get() == 'یادداشت' else form._phase_values()
    return next((choice for choice in choices
                 if _phase_name_187(choice) == name), name)


def _note_phase_choices_187(form):
    from ai_parser import CONSTRUCTION_PHASES
    numbers = {name: number for number, name in enumerate(CONSTRUCTION_PHASES, 1)}
    # An imported project can carry its own phase numbers. Keep all 32 choices
    # available even when a new project has no estimate rows yet.
    for choice in form._phase_values():
        number, separator, name = str(choice).partition('—')
        if separator and number.strip().isdigit():
            numbers[name.strip()] = int(number.strip())
    return tuple(f'{numbers[name]:02d} — {name}' for name in CONSTRUCTION_PHASES)


def _document_code_187(subtype: str) -> str:
    return _DOCUMENT_SUBTYPE_CODES_187.get(_canonical_document_subtype_187(subtype), 'DOCUMENT')


v18.TITLE_TYPES['یادداشت'] = [
    'تقویم کارگاهی', 'گزارش روزانه', 'داکیومنت', 'یادآوری', 'یادداشت',
    # Kept for records created by earlier 18.7 builds.
    'اطلاع‌رسانی',
    'فاکتور',
]


_ORIGINAL_SPECIAL_FIELDS_187 = v181.special_fields_181
_ORIGINAL_WIZARD_STEPS_182_187 = v182.wizard_steps_182
_ORIGINAL_LOAD_VALUES_187 = v18.DynamicFormMixin._load_values
_ORIGINAL_PAYLOAD_VALUES_187 = v18.DynamicFormMixin._payload_from_vars
_ORIGINAL_WIZARD_PAYLOAD_VALUES_187 = v182.TransactionWizard182._payload_from_vars
_ORIGINAL_EDITOR_BUILD_SPECIAL_187 = v182.UnifiedPendingEditor182._build_special
_ORIGINAL_EDITOR_TITLE_CHANGED_187 = v182.UnifiedPendingEditor182._title_changed
_ORIGINAL_EDITOR_BUILD_187 = v182.UnifiedPendingEditor182._build
_ORIGINAL_EDITOR_EVIDENCE_187 = v182.UnifiedPendingEditor182._load_evidence
_ORIGINAL_EDITOR_INIT_187 = v182.UnifiedPendingEditor182.__init__
_ORIGINAL_EDITOR_NAVIGATION_VALUES_187 = v182.UnifiedPendingEditor182._navigation_values_182
_ORIGINAL_EDITOR_RELOAD_187 = v182.UnifiedPendingEditor182._reload_record_182
_ORIGINAL_WIZARD_BUILD_SHELL_187 = v182.TransactionWizard182._build_shell
_ORIGINAL_WIZARD_INIT_187 = v182.TransactionWizard182.__init__
_ORIGINAL_WIZARD_AFTER_RENDER_187 = v182.TransactionWizard182._after_page_render
_ORIGINAL_WIZARD_CAPTURE_187 = v182.TransactionWizard182._capture
_ORIGINAL_WIZARD_NEXT_187 = v182.TransactionWizard182.next
_ORIGINAL_APPROVE_V18_187 = v18.approve_v18
_ORIGINAL_DYNAMIC_FIELD_187 = v18.DynamicFormMixin._field
_ORIGINAL_INIT_DYNAMIC_187 = v18.DynamicFormMixin._init_dynamic
_ORIGINAL_MARK_MANUAL_187 = v18.DynamicFormMixin._mark_manual
_ORIGINAL_REFRESH_SUBPHASE_187 = v18.DynamicFormMixin._refresh_subphase
_ORIGINAL_EDITOR_MARK_MANUAL_187 = v182.UnifiedPendingEditor182._mark_manual

# The partner selector is also used by the inherited loader to distinguish a
# real partner name from the free-text «سایر» option. Keep the new choice in
# that shared allowlist so saved records reopen with the original selection.
if 'شرکا' not in v182._PARTNER_NAMES:
    v182._PARTNER_NAMES = (*v182._PARTNER_NAMES, 'شرکا')


def _init_dynamic_187(self, payload):
    """Put AI's suggested numbers into the editable draft, once per load."""
    draft = dict(payload or {})
    if draft.get('v18_title') == LAND_TITLE or draft.get('transaction_title') == LAND_TITLE:
        draft = normalize_land_record(draft)
    suggestions = dict(draft.get('v18_reprocess_suggestions') or {})
    title, subtype = v18._title_type_from_payload(draft)
    numeric = {'amount', 'paid_amount', 'final_amount', 'invoice_amount'} | {
        field.key for field in _special_fields_187(title, subtype)
        if field.kind in {'money', 'int'}}
    accepted = set()
    for key, value in tuple(suggestions.items()):
        if key in numeric and value is not None and any(character.isdigit() for character in str(value)):
            draft[key] = parse_int(value)
            accepted.add(key)
            suggestions.pop(key)
    if 'amount' in accepted:
        draft['paid_amount'] = draft['amount']
        accepted.add('paid_amount')
    elif title == LAND_TITLE and land_payment_subtype(draft) == 'نقدی' and 'land_cash_amount' in accepted:
        draft['amount'] = draft['paid_amount'] = draft['land_cash_amount']
        accepted.update(('amount', 'paid_amount'))
    draft['v18_manual_fields'] = [key for key in draft.get('v18_manual_fields') or [] if key not in accepted]
    if 'total_debt' in accepted:
        draft.pop('_total_debt_manual187', None)
    if suggestions:
        draft['v18_reprocess_suggestions'] = suggestions
    else:
        draft.pop('v18_reprocess_suggestions', None)
    self._settled_debt_auto187 = False
    _ORIGINAL_INIT_DYNAMIC_187(self, draft)


def _base_special_fields_187(title: str, subtype: str):
    """Expose the complete facility vocabulary without changing the DB schema."""
    subtype = _canonical_document_subtype_187(subtype)
    if title == MANAGER_TITLE:
        return [field for field in _base_special_fields_187('هزینه ساخت', 'نقدی')
                if field.key not in {'construction_stage', 'activity_name', 'plan_ref', 'cost_group', 'contract_id', 'main_phase', 'sub_phase'}]
    if _is_facility_payload_187(title, subtype):
        F = v18.FieldDef
        return [
            F('loan_bank', 'نام بانک'),
            F('branch_name', 'نام شعبه'),
            F('borrower_name', 'نام وام‌گیرنده'),
            F('guarantor_1', 'نام ضامن اول'),
            F('guarantor_2', 'نام ضامن دوم'),
            F('loan_name', 'نام وام'),
            F('loan_title', 'عنوان وام'),
            F('contract_number', 'شماره تسهیلات'),
            F('loan_start_date', 'تاریخ اخذ وام', 'date'),
            F('loan_total_amount', 'مبلغ درخواست وام', 'money'),
            F('installment_count', 'تعداد اقساط', 'int'),
            F('interest_rate', 'درصد سود', 'float'),
            F('installment_amount', 'مبلغ هر قسط', 'money'),
            F('total_interest', 'کل سود وام', 'money', readonly=True),
            F('bank_fees', 'کارمزد وام', 'money', readonly=True),
            F('first_due_date_shamsi', 'تاریخ اولین قسط', 'date'),
            F('loan_end_date', 'تاریخ آخرین قسط', 'date', readonly=True),
            F('last_paid_date_shamsi', 'تاریخ آخرین قسط پرداختی', 'date', readonly=True),
            F('paid_installments_count', 'تعداد اقساط پرداختی', 'int', readonly=True),
            F('remaining_installments', 'تعداد اقساط باقیمانده', 'int', readonly=True),
        ]
    if title == 'یادداشت':
        F = v18.FieldDef
        if subtype == 'تقویم کارگاهی':
            return [F('calendar_date_shamsi', 'تاریخ', 'date'), F('description', 'شرح', 'text')]
        if subtype == 'گزارش روزانه':
            return [
                F('report_date_shamsi', 'تاریخ', 'date'),
                F('report_row_count', 'تعداد ردیف', 'int'),
                F('report_contractor_count', 'تعداد عوامل پیمانکار', 'int'),
                F('report_daily_wage_count', 'تعداد عوامل روزمزد', 'int'),
                F('report_machinery', 'ماشین‌آلات فعال'),
                F('report_weather', 'وضعیت آب‌وهوا'),
                F('report_rows', 'ردیف‌ها', 'report_rows'),
                F('report_images', 'بارگذاری تصاویر', 'images'),
            ]
        if subtype == 'داکیومنت':
            return [
                F('description', 'شرح سند', 'text'),
                F('document_file', 'بارگذاری فایل سند', 'file'),
            ]
        if subtype == 'یادآوری':
            return [
                F('reminder_date_shamsi', 'تاریخ یادآوری', 'date'),
                F('description', 'شرح یادآوری', 'text'),
            ]
        if subtype == 'یادداشت':
            return [
                F('note_subject', 'موضوع یادداشت', 'combo', ('فنی', 'توصیفی', 'سایر')),
                F('description', 'شرح یادداشت', 'text'),
            ]
        if subtype == 'فاکتور':
            return [
                F('invoice_note_date_shamsi', 'تاریخ فاکتور', 'date'),
                F('description', 'شرح فاکتور', 'text'),
            ]
    fields = list(_ORIGINAL_SPECIAL_FIELDS_187(title, subtype))
    if _is_installment_payload_187(title, subtype):
        fields = [v18.FieldDef(field.key, field.label, field.kind, field.values, False)
                  if field.key in _INSTALLMENT_TYPED_KEYS_187 else field for field in fields]
    if title == 'هزینه ساخت' and subtype == 'نقدی' and not any(
            field.key == 'issuer_name' for field in fields):
        fields.append(v18.FieldDef('issuer_name', 'صاحب حساب'))
    return fields


v18.TITLE_TYPES[MANAGER_TITLE] = ['نقدی']
_ORIGINAL_BACKEND_TYPE_187 = v18._backend_type
def _backend_type_187(title, subtype):
    return 'OUTFLOW' if title == MANAGER_TITLE else _ORIGINAL_BACKEND_TYPE_187(title, subtype)
v18._backend_type = _backend_type_187

v18.TITLE_TYPES[LAND_TITLE] = [LAND_TITLE]
CHEQUE_CLEARING_SUBTYPE_187 = 'پاس کردن چک'
CHEQUE_CLEARING_MODES_187 = ('حساب دسته چک', 'واریز به حساب معرفی شده')
CHEQUE_CLEARING_STATUS_CHOICES_187 = ('صادرشده', 'پاس‌شده')
CHEQUE_OPERATION_ISSUE_187 = 'صدور چک'
CHEQUE_OPERATION_RESOLVE_187 = 'تعیین تکلیف چک'
CHEQUE_OPERATION_CHOICES_187 = (CHEQUE_OPERATION_ISSUE_187, CHEQUE_OPERATION_RESOLVE_187)
#: A cheque whose category was left empty is a materials cheque; «پیمانکار» is chosen on purpose.
CHEQUE_DEFAULT_COST_GROUP_187 = 'مصالح'
CHEQUE_RESOLUTION_STATUS_CHOICES_187 = (
    'پاس‌شده', 'برگشتی', 'عودتی به شرط تسویه', 'باطل‌شده',
)
CHEQUE_RETURN_DISPOSITION_CHOICES_187 = (
    'دریافت چک', 'عودت سیستمی', 'دریافت و عودت سیستمی',
    'عدم دریافت و عدم عودت سیستمی',
)
v18.TITLE_TYPES['هزینه ساخت'] = [value for value in
    dict.fromkeys(v18.TITLE_TYPES.get('هزینه ساخت', ()))
    if value != CHEQUE_CLEARING_SUBTYPE_187]
v18.METHOD_TO_CODE['سایر'] = 'OTHER'
v18.CODE_TO_METHOD['OTHER'] = 'سایر'
if 'سایر' not in v18.PAYMENT_METHODS:
    v18.PAYMENT_METHODS.append('سایر')


def _special_fields_187(title: str, subtype: str):
    F = v18.FieldDef
    if title == 'هزینه ساخت' and subtype == CHEQUE_CLEARING_SUBTYPE_187:
        return [
            F('selected_cheque_id187', 'چک ثبت‌شده برای پاس‌شدن', 'cheque_picker'),
            F('cheque_clearing_mode187', 'نحوه پاس‌شدن چک', 'combo', CHEQUE_CLEARING_MODES_187),
            F('cheque_status', 'وضعیت نهایی چک', 'combo', CHEQUE_CLEARING_STATUS_CHOICES_187),
            F('cheque_transfer_account_holder187', 'نام صاحب حساب مقصد', 'short_text'),
            F('cheque_transfer_description187', 'بابت واریز', 'short_text'),
        ]
    if title == LAND_TITLE:
        fields = [F('payer_name', 'پرداخت‌کننده'), F('receiver_name', 'فروشنده زمین'),
                  F('description', 'بابت'),
                  F('payment_method', 'نحوه پرداخت نقدی', 'combo', ('واریز بانکی', 'نقدی/کارتخوان', 'سایر')),
                  F('land_cash_amount', 'مبلغ نقدی', 'money'),
                  F('land_cheque_amount', 'مبلغ چک', 'money'),
                  F('land_barter_amount', 'مبلغ معاوضه', 'money'),
                  F('land_barter_description', 'شرح مورد معاوضه'),
                  F('issuer_name', 'صاحب حساب چک'), F('issuer_bank', 'بانک چک'),
                  F('cheque_serial', 'شماره چک'),
                  F('cheque_type', 'نوع چک', 'combo', tuple(v18.CHEQUE_KIND)),
                  F('due_date_shamsi', 'سررسید چک', 'date'),
                  F('payment_state', 'وضعیت پرداخت', 'combo', tuple(v18.PAYMENT_STATE)),
                  F('total_debt', 'کل بدهی', 'money'),
                  F('remaining_debt', 'مانده بدهی', 'money', readonly=True)]
    else:
        fields = _base_special_fields_187(title, subtype)
    if title == 'هزینه ساخت' and subtype == 'چک':
        fields = list(fields)
        if not any(field.key == 'cheque_serial' for field in fields):
            fields.append(F('cheque_serial', 'شماره چک / صیادی'))
    result = []
    for field in fields:
        if title == 'ورودی' and subtype == 'شرکا/قرض' and field.key == 'partner_name':
            field = F(field.key, field.label, field.kind,
                      tuple(dict.fromkeys((*field.values, 'شرکا'))), field.readonly)
        if field.key == 'payment_method':
            field = F(field.key, field.label, 'combo',
                      tuple(dict.fromkeys((*field.values, 'سایر'))), field.readonly)
        result.append(field)
    if title == 'ورودی' and subtype == 'شرکا/قرض':
        result.append(F('partner_source', 'محل تأمین', 'combo', ('شخصی', 'پروژه قبلی')))
    if _note_without_payment_method_187(title, subtype):
        return [field for field in result if field.key != 'payment_method']
    if not any(field.key == 'payment_method' for field in result):
        result.append(F('payment_method', 'روش پرداخت', 'combo', tuple(v18.PAYMENT_METHODS)))
    return result


def _base_wizard_steps_187(title: str, subtype: str):
    subtype = _canonical_document_subtype_187(subtype)
    if title == 'هزینه ساخت' and subtype == CHEQUE_CLEARING_SUBTYPE_187:
        F = v18.FieldDef
        fields = {field.key: field for field in _special_fields_187(title, subtype)}
        return [[fields[key] for key in (
            'selected_cheque_id187', 'cheque_clearing_mode187', 'cheque_status',
            'cheque_transfer_account_holder187', 'cheque_transfer_description187',
        )], [F('cheque_clearing_review187', 'مرور و تأیید نهایی', 'cheque_review187')]]
    if title == MANAGER_TITLE:
        allowed = {field.key for field in _special_fields_187(title, subtype)}
        pages = [[field for field in page if field.key in allowed]
                 for page in _ORIGINAL_WIZARD_STEPS_182_187('هزینه ساخت', 'نقدی')]
        return [page for page in pages if page]
    if title == LAND_TITLE:
        if subtype == LAND_TITLE:
            subtype = LAND_MIXED
        fields = {field.key: field for field in _special_fields_187(title, subtype)}
        groups = [('payer_name', 'receiver_name', 'description', 'payment_method'),
                  ('land_cash_amount', 'land_cheque_amount', 'land_barter_amount', 'land_barter_description'),
                  ('issuer_name', 'issuer_bank', 'cheque_serial', 'cheque_type', 'due_date_shamsi'),
                  ('payment_state', 'total_debt', 'remaining_debt')]
        if subtype not in (LAND_MIXED, 'چک'):
            groups.pop(2)
        return [[fields[key] for key in group] for group in groups]
    if _is_facility_payload_187(title, subtype):
        fields = {field.key: field for field in _special_fields_187(title, subtype)}
        groups = [
            ['loan_start_date', 'loan_total_amount', 'amount', 'loan_name',
             'loan_title', 'contract_number', 'interest_rate', 'bank_fees'],
            ['installment_count', 'installment_amount', 'total_interest',
             'first_due_date_shamsi', 'loan_end_date', 'last_paid_date_shamsi',
             'paid_installments_count', 'remaining_installments'],
        ]
        amount_field = v18.FieldDef('amount', 'مبلغ واریزی وام', 'money')
        return [[amount_field if key == 'amount' else fields[key]
                 for key in group if key == 'amount' or key in fields] for group in groups]
    if _is_nonfinancial_payload_187(title, subtype):
        fields = {field.key: field for field in _special_fields_187(title, subtype)}
        groups = {
            'تقویم کارگاهی': [['calendar_date_shamsi', 'description']],
            # Window two owns the complete daily-report form.  The row count is
            # entered beside the date and immediately expands the two-column
            # row/description editor below it; splitting that editor into a
            # later page made the count appear to do nothing.
            'گزارش روزانه': [['report_date_shamsi', 'report_row_count', 'report_contractor_count',
                              'report_daily_wage_count', 'report_machinery', 'report_weather',
                              'report_rows', 'report_images']],
            'داکیومنت': [['description', 'document_file']],
            'یادآوری': [['reminder_date_shamsi', 'description']],
            'یادداشت': [['note_subject', 'description']],
            'اطلاع‌رسانی': [['description']],
            'فاکتور': [['invoice_note_date_shamsi', 'description']],
        }.get(subtype, [])
        return [[fields[key] for key in group if key in fields] for group in groups]
    return _ORIGINAL_WIZARD_STEPS_182_187(title, subtype)


def _facility_wizard_pages_187(first_page):
    """Three screens: bank/borrower, loan terms, then installment schedule."""
    F = v18.FieldDef
    by_key = {field.key: field for field in _special_fields_187('ورودی', 'تسهیلات')}
    bank_keys = ('loan_bank', 'branch_name', 'borrower_name', 'guarantor_1', 'guarantor_2')
    base = [field for field in (first_page or ()) if field.key not in bank_keys]
    first = base + [by_key[key] for key in bank_keys]
    terms = [
        by_key['loan_start_date'], F('loan_total_amount', 'مبلغ درخواست وام', 'money'),
        F('amount', 'مبلغ واریزی وام', 'money'), by_key['loan_name'],
        by_key['loan_title'], by_key['contract_number'], by_key['interest_rate'],
        by_key['bank_fees'],
    ]
    schedule = [by_key[key] for key in (
        'installment_count', 'installment_amount', 'total_interest',
        'first_due_date_shamsi', 'loan_end_date', 'last_paid_date_shamsi',
        'paid_installments_count', 'remaining_installments',
    )]
    return [first, terms, schedule]


def _wizard_steps_187(title: str, subtype: str):
    pages = [list(page) for page in _base_wizard_steps_187(title, subtype)]
    if title == 'هزینه ساخت' and subtype == CHEQUE_CLEARING_SUBTYPE_187:
        return pages
    if title == 'هزینه ساخت' and subtype == 'چک':
        fields = {field.key: field for field in _special_fields_187(title, subtype)}
        # The issuance path keeps the existing expense workflow. Its second
        # window now contains the former windows 2+3 and the due date; the
        # redundant final page is removed by _wizard_next_187.
        groups = (
            ('payer_name', 'receiver_name', 'description',
             'issuer_name', 'issuer_bank', 'cheque_serial', 'cheque_type', 'is_guarantee', 'due_date_shamsi'),
            ('cheque_registration_state', 'cheque_status'),
            ('invoice_amount', 'final_amount', 'discount_amount'),
            ('payment_state', 'total_debt', 'remaining_debt'),
            ('main_phase', 'sub_phase'),
        )
        return [[fields[key] for key in group if key in fields] for group in groups]
    if title == 'ورودی' and subtype == 'شرکا/قرض':
        source = next(field for field in _special_fields_187(title, subtype)
                      if field.key == 'partner_source')
        pages = [[field for field in page if field.key != 'partner_source'] for page in pages]
        partner_page = next((page for page in pages
                             if any(field.key == 'partner_name' for field in page)), None)
        if partner_page is None:
            pages.insert(0, [source])
        else:
            partner_page.append(source)
    if _note_without_payment_method_187(title, subtype):
        return pages
    if not any(field.key == 'payment_method' for page in pages for field in page):
        method = next(field for field in _special_fields_187(title, subtype) if field.key == 'payment_method')
        if pages:
            pages[0].append(method)
        else:
            pages = [[method]]
    return pages


def _loan_date_value_187(value) -> str:
    try:
        return normalize_shamsi(str(value or '').strip())
    except Exception:
        return ''


def _loan_fees_187(requested, deposit) -> int:
    """The fees of a loan are what the bank kept back: the requested amount less what it paid in."""
    requested, deposit = int(requested or 0), int(deposit or 0)
    return max(0, requested - deposit) if requested > 0 and deposit > 0 else 0


def _loan_fee_repaid_187(principal, net_received, bank_fees) -> int:
    """What the instalments add for the fees: nothing when they are the part of the requested amount the bank
    kept back (net received + fees = principal), they were paid when the money arrived."""
    principal, net_received, bank_fees = int(principal or 0), int(net_received or 0), int(bank_fees or 0)
    return 0 if bank_fees > 0 and net_received + bank_fees == principal else bank_fees


def _sync_loan_fields_187(form, changed: str = '') -> None:
    """Keep installment totals, dates and the default loan name in sync.

    `changed` is the field somebody just typed in.  The installment box is the one
    editable result: while it is being typed in (cleared first, then filled) it is
    neither refilled with the computed default nor reformatted from here.  Until somebody
    types an installment of their own it is the computed one and follows the amount, the rate
    and the count; an installment that differs from the computed one is the person's own and
    stays, and emptying the box gives the computed one back.
    """
    if getattr(form, '_loading', False):
        return
    vars_map = getattr(form, 'vars', {}) or {}
    payload = getattr(form, 'payload', {}) or {}
    def value(key, default=''):
        var = vars_map.get(key)
        if var is not None:
            try:
                return var.get()
            except Exception:
                pass
        return payload.get(key, default)

    principal = parse_int(value('loan_total_amount', payload.get('principal_amount') or 0))
    count = parse_int(value('installment_count', 0))
    try:
        rate = parse_decimal(str(value('interest_rate', 0)).replace('%', '').replace('٪', ''))
    except (TypeError, ValueError):
        rate = 0.0
    deposit = parse_int(value('amount', payload.get('amount') or payload.get('net_received_amount') or 0))
    bank_fees = _loan_fees_187(principal, deposit)
    installment = parse_int(value('installment_amount', payload.get('installment_amount') or 0))
    typing_installment = changed == 'installment_amount'
    default_installment = (calculate_loan_installment_187(principal, rate, count)
                           if principal > 0 and count > 0 else 0)
    own_installment = getattr(form, '_installment_own187', None)
    if typing_installment:
        own_installment = installment > 0
    elif own_installment is None:
        own_installment = installment > 0 and installment != default_installment
    form._installment_own187 = own_installment
    if not own_installment and not typing_installment:
        installment = default_installment
    total_interest = loan_total_interest_187(principal, installment, count)
    start = _loan_date_value_187(value('loan_start_date', payload.get('received_date_shamsi') or ''))
    first = _loan_date_value_187(value('first_due_date_shamsi', ''))
    if not first and start and count > 0:
        first = gregorian_to_shamsi(_add_months(date.fromisoformat(shamsi_to_gregorian(start)), 1))
    end = _loan_date_value_187(value('loan_end_date', ''))
    if first and count > 0:
        end = gregorian_to_shamsi(_add_months(date.fromisoformat(shamsi_to_gregorian(first)), count - 1))
    paid_count = parse_int(payload.get('paid_installments_count') or payload.get('paid_installments') or 0)
    remaining = max(0, count - paid_count)
    current_name = str(value('loan_name', payload.get('loan_name') or '') or '').strip()
    previous_default = str(getattr(form, '_loan_name_default_value187', '') or '')
    default_name = str(principal)[:4] if principal > 0 else ''
    if not current_name or (previous_default and current_name == previous_default):
        current_name = default_name
    form._loan_name_default_value187 = current_name if current_name == default_name else ''

    payload.update({
        'principal_amount': principal,
        'loan_total_amount': principal,
        'bank_fees': bank_fees,
        'loan_name': current_name,
        'installment_amount': installment,
        'total_interest': total_interest,
        'first_due_date_shamsi': first,
        'loan_end_date': end,
        'paid_installments_count': paid_count,
        'remaining_installments': remaining,
    })
    form._loading = True
    try:
        for key, val in (
            ('loan_name', current_name), ('installment_amount', installment), ('bank_fees', bank_fees),
            ('total_interest', total_interest), ('first_due_date_shamsi', first),
            ('loan_end_date', end), ('paid_installments_count', paid_count),
            ('remaining_installments', remaining),
        ):
            var = vars_map.get(key)
            if typing_installment and key == 'installment_amount':
                continue
            if var is not None:
                if key in {'installment_amount', 'total_interest', 'bank_fees',
                           'paid_installments_count', 'remaining_installments'}:
                    var.set(v18._group_money(val))
                else:
                    var.set(val)
    finally:
        form._loading = False


def _sync_installments_187(form, changed: str = '') -> None:
    """Keep the remaining count of an instalment payment: the total less the paid before and the paid now.

    `changed` names the remaining box when somebody types in it.  Until somebody types a count of their own the
    remaining count is the computed one and follows the other counts; a count that differs from the computed one
    is the person's own and stays.  Leaving the box empty gives the computed one back.  No count here changes the
    loan's schedule: approval posts the number paid now.
    """
    if getattr(form, '_loading', False):
        return
    vars_map = getattr(form, 'vars', {}) or {}
    remaining = vars_map.get('remaining_installments')
    if remaining is None:
        return
    payload = getattr(form, 'payload', {}) or {}

    def count(key):
        var = vars_map.get(key)
        return parse_int(var.get() if var is not None else payload.get(key) or 0)

    try:
        typed = str(remaining.get() or '').strip()
    except tk.TclError:
        return
    computed = max(count('installment_count') - count('paid_installments_before')
                   - max(0, count('installments_paid_now')), 0)
    if changed == 'remaining_installments':
        form._remaining_own187 = bool(typed)
        return
    own = getattr(form, '_remaining_own187', None)
    if own is None:
        # A record saved without the count shows a loaded 0; only a count that was stored and differs is the person's.
        stored = payload.get('remaining_installments')
        own = stored not in (None, '') and bool(typed) and parse_int(typed) != computed
    form._remaining_own187 = own
    if own:
        return
    form._loading = True
    try:
        remaining.set(v18._group_money(computed))
    finally:
        form._loading = False


def _installment_count_sync_187(form):
    _sync_installments_187(form)


def _refill_remaining_187(form):
    """Leaving the remaining box empty brings the computed count back, so an emptied box is never saved as 0."""
    try:
        variable = form.vars.get('remaining_installments')
        if variable is None or str(variable.get() or '').strip():
            return
    except tk.TclError:
        return
    form._remaining_own187 = False
    _sync_installments_187(form)


def _loan_picker_entries_187() -> list[dict[str, str]]:
    """The loans as the instalment picker shows them: id, the loan's name (made unique where two loans share one) and
    status. Cancelled loans stay here so that an older record still resolves to its loan's name."""
    loans = LoanService(DB).list_loans(include_cancelled=True)
    base = {}
    for loan in loans:
        lid = str(loan.get('loan_id') or '')
        base[lid] = str(loan.get('loan_name') or '').strip() or str(int(loan.get('principal_amount') or 0))[:4] or lid
    counts = {}
    for name in base.values():
        counts[name] = counts.get(name, 0) + 1
    entries = []
    for loan in loans:
        lid = str(loan.get('loan_id') or '')
        name = base[lid]
        lender = str(loan.get('lender_name') or '').strip()
        if counts[name] > 1 and lender:
            name = f'{name} ({lender})'
        entries.append({'loan_id': lid, 'label': name, 'status': str(loan.get('status') or '').upper()})
    labels = {}
    for entry in entries:
        labels[entry['label']] = labels.get(entry['label'], 0) + 1
    numbered = {}
    for entry in entries:
        if labels[entry['label']] > 1:
            numbered[entry['label']] = numbered.get(entry['label'], 0) + 1
            entry['label'] = f"{entry['label']} ({fa(numbered[entry['label']])})"
    return entries


def _loan_picker_labels_187() -> dict[str, str]:
    return {entry['loan_id']: entry['label'] for entry in _loan_picker_entries_187()}


def _loan_picker_values_187() -> tuple[str, ...]:
    """What the picker lists for a new instalment payment: the names of the loans that are not cancelled."""
    return tuple(entry['label'] for entry in _loan_picker_entries_187() if entry['status'] != 'CANCELLED')


def _loan_label_of_id_187(loan_id) -> str:
    lid = str(loan_id or '').strip()
    return _loan_picker_labels_187().get(lid, lid)


def _loan_id_of_text_187(text) -> str:
    """The loan id behind a picker text: the name the picker shows, or an id (also one an older picker stored with
    its details after a «|»)."""
    raw = str(text or '').strip()
    if not raw:
        return ''
    for entry in _loan_picker_entries_187():
        if entry['label'] == raw:
            return entry['loan_id']
    return raw.split('|', 1)[0].strip()


def _show_loan_name_187(form) -> None:
    variable = getattr(form, 'vars', {}).get('loan_id')
    if variable is None:
        return
    lid = _loan_id_of_text_187((getattr(form, 'payload', {}) or {}).get('loan_id'))
    form._loading = True
    try:
        variable.set(_loan_label_of_id_187(lid) if lid else '')
    finally:
        form._loading = False


def _with_loan_id_187(payload, title, subtype):
    """An instalment payment keeps its loan's id, whatever name the picker shows."""
    if _is_installment_payload_187(title, subtype) and 'loan_id' in payload:
        payload['loan_id'] = _loan_id_of_text_187(payload.get('loan_id'))
    return payload


def _loan_selected_187(self, value: str):
    """Choosing an instalment's loan: the picker shows its name, the record keeps its id, and the counts start again."""
    loan_id = _loan_id_of_text_187(value)
    if not loan_id:
        return
    try:
        loan = LoanService(DB).get_loan(loan_id) or {}
        paid = int(loan.get('paid_installments') or 0)
        if not paid:
            with DB.read() as con:
                paid = con.execute("SELECT COUNT(*) FROM loan_installments WHERE loan_id=? AND status='PAID'", (loan_id,)).fetchone()[0]
        count = int(loan.get('installment_count') or 0)
        name = _loan_label_of_id_187(loan_id)
        vals = {
            'loan_id': name,
            'loan_bank': loan.get('lender_name') or '',
            'loan_total_amount': loan.get('principal_amount') or 0,
            'installment_count': count,
            'paid_installments_before': paid,
            'installments_paid_now': 1,
            'remaining_installments': max(count - paid - 1, 0),
        }
        self.payload['selected_loan_name'] = name
        self.payload.update(dict(vals, loan_id=loan_id))
        self._loading = True
        for key, val in vals.items():
            if key in self.vars:
                self.vars[key].set(v18._group_money(val) if isinstance(val, (int, float)) else str(val))
    finally:
        self._loading = False
    self._remaining_own187 = False


def _document_paths_187(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    raw = str(value or '').strip()
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, list):
            return [str(item).strip() for item in decoded if str(item).strip()]
    except (TypeError, ValueError):
        pass
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _document_rows_187(value) -> list[dict[str, str]]:
    if isinstance(value, list):
        rows = value
    else:
        try:
            rows = json.loads(str(value or '[]'))
        except (TypeError, ValueError):
            rows = []
    if not isinstance(rows, list):
        return []
    output = []
    for index, item in enumerate(rows, 1):
        if isinstance(item, dict):
            text = str(item.get('description') or item.get('شرح') or '').strip()
            number = str(item.get('row') or item.get('ردیف') or index).strip()
            main_phase = str(item.get('main_phase') or item.get('فاز اصلی') or '').strip()
            sub_phase = str(item.get('sub_phase') or item.get('فاز فرعی') or '').strip()
        else:
            text, number, main_phase, sub_phase = str(item or '').strip(), str(index), '', ''
        row = {'row': number or str(index), 'description': text}
        if main_phase:
            row['main_phase'] = main_phase
        if sub_phase:
            row['sub_phase'] = sub_phase
        output.append(row)
    return output


def _document_attachment_paths_187(form) -> list[dict]:
    pid = str(getattr(form, 'pid', '') or '')
    if not pid:
        return []
    try:
        return list(DB.list_pending_attachments(pid) or [])
    except Exception:
        return []


def _set_document_paths_187(form, key: str, paths) -> None:
    paths = _document_paths_187(paths)
    form.payload[key] = paths if key == 'report_images' else (paths[0] if paths else '')
    var = getattr(form, 'vars', {}).get(key)
    if var is not None:
        var.set(json.dumps(paths, ensure_ascii=False) if key == 'report_images' else (paths[0] if paths else ''))
    pid = str(getattr(form, 'pid', '') or '')
    if not pid or not paths:
        return
    existing = {
        str(row.get('local_path') or '')
        for row in _document_attachment_paths_187(form)
    }
    document_type = 'DAILY_REPORT_IMAGE' if key == 'report_images' else 'DOCUMENT_FILE'
    for path in paths:
        if path in existing:
            continue
        try:
            mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
            DB.attach_file_to_pending(
                pending_id=pid, local_path=path, mime_type=mime,
                document_type=document_type,
            )
            existing.add(path)
        except Exception:
            # The form remains usable when an old/temporary pending row cannot
            # accept an attachment; the selected path is still retained.
            continue


def _choose_document_file_187(form, key: str, *, multiple: bool = False) -> None:
    if multiple:
        selected = filedialog.askopenfilenames(
            parent=form, title='انتخاب تصاویر گزارش روزانه',
            filetypes=[('تصویر', '*.png *.jpg *.jpeg *.webp *.bmp'), ('همه فایل‌ها', '*.*')],
        )
    else:
        selected = filedialog.askopenfilename(
            parent=form, title='انتخاب فایل سند',
            filetypes=[
                ('همهٔ فرمت‌ها', '*.*'), ('PDF', '*.pdf'), ('CAD', '*.dwg *.dxf'),
                ('اسناد و صفحه‌گسترده‌ها', '*.doc *.docx *.xls *.xlsx *.txt *.rtf *.odt *.ods'),
            ],
        )
    paths = list(selected) if isinstance(selected, (tuple, list)) else ([selected] if selected else [])
    if paths:
        _set_document_paths_187(form, key, paths)
        if key == 'report_images':
            _refresh_report_rows_187(form)


def _capture_report_rows_187(form) -> None:
    rows = []
    previous = _document_rows_187(getattr(form, 'payload', {}).get('daily_report_rows'))
    controls = getattr(form, '_report_row_controls_187', [])
    for index, var in enumerate(getattr(form, '_report_row_vars_187', []), 1):
        try:
            text = str(var.get() or '').strip()
        except tk.TclError:
            text = ''
        prior = previous[index - 1] if index - 1 < len(previous) else {}
        control = controls[index - 1] if index - 1 < len(controls) else {}
        rows.append({
            'row': str(index), 'description': text,
            'main_phase': str(control.get('main_phase').get() if control.get('main_phase') else prior.get('main_phase') or '').strip(),
            'sub_phase': str(control.get('sub_phase').get() if control.get('sub_phase') else prior.get('sub_phase') or '').strip(),
        })
    form.payload['daily_report_rows'] = rows
    form.payload['report_row_count'] = len(rows)
    variable = getattr(form, 'vars', {}).get('report_rows')
    if variable is not None:
        variable.set(json.dumps(rows, ensure_ascii=False))


def _bind_full_text_tooltip_187(widget, variable, form) -> None:
    """Show the current complete description in a scrollable hover window."""
    state = {'show': None, 'hide': None, 'window': None}

    def cancel(key):
        token = state.get(key)
        if token is not None:
            try:
                widget.after_cancel(token)
            except tk.TclError:
                pass
            state[key] = None

    def close():
        state['hide'] = None
        window = state.get('window')
        state['window'] = None
        if window is not None:
            try:
                if window.winfo_exists():
                    window.destroy()
            except tk.TclError:
                pass

    def hide_later(_event=None):
        cancel('hide')
        try:
            state['hide'] = widget.after(220, close)
        except tk.TclError:
            close()

    def show():
        state['show'] = None
        value = str(variable.get() or '')
        if not value.strip() or state.get('window') is not None:
            return
        colors = palette_187()
        tip = tk.Toplevel(widget)
        tip.wm_overrideredirect(True)
        try:
            tip.attributes('-topmost', True)
        except tk.TclError:
            pass
        tip.geometry(f'+{widget.winfo_rootx() + 12}+{widget.winfo_rooty() + widget.winfo_height() + 4}')
        shell = tk.Frame(tip, bg=colors['panel'], highlightbackground=colors['line'], highlightthickness=1)
        shell.pack(fill='both', expand=True)
        output = tk.Text(
            shell, width=64, height=min(12, max(3, value.count('\n') + 3)),
            wrap='word', bg=colors['panel'], fg=colors['text'],
            insertbackground=colors['text'], relief='flat', padx=10, pady=8,
            font=(form.font_family, max(8, form.font_size - 1)),
        )
        scroll = ttk.Scrollbar(shell, orient='vertical', command=output.yview)
        output.configure(yscrollcommand=scroll.set)
        output.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        output.insert('1.0', value)
        _right_align_form_187(tip)
        output.configure(state='disabled')
        for target in (widget, tip, shell, output, scroll):
            target.bind('<Enter>', lambda _event: (cancel('hide'), None), add='+')
            target.bind('<Leave>', hide_later, add='+')
        state['window'] = tip

    def show_later(_event=None):
        cancel('show')
        cancel('hide')
        if state.get('window') is None:
            try:
                state['show'] = widget.after(350, show)
            except tk.TclError:
                pass

    widget.bind('<Enter>', show_later, add='+')
    widget.bind('<Leave>', hide_later, add='+')


def _right_align_form_187(form) -> None:
    """Align labels, values and editable paragraphs after each form rebuild."""
    normalize_window_rtl(form)
    stack = [form]
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if not isinstance(widget, tk.Text):
            continue
        widget.tag_configure('rtl187', justify='right')
        widget.tag_add('rtl187', '1.0', 'end')
        if not getattr(widget, '_form_rtl_bound187', False):
            widget.bind('<<Modified>>', lambda _event, target=widget:
                        target.tag_add('rtl187', '1.0', 'end'), add='+')
            widget._form_rtl_bound187 = True


def _multiline_description_widget_187(parent, variable, form, *, height=4, on_edit=None, width=None):
    """Bind an editable multiline Text widget to the form StringVar."""
    colors = palette_187()
    widget = tk.Text(
        parent, height=height, wrap='word', bg=colors['surface'], fg=colors['text'],
        insertbackground=colors['text'], relief='flat', padx=8, pady=6,
        font=(form.font_family, form.font_size),
    )
    if width:
        widget.configure(width=width)
    widget.insert('1.0', str(variable.get() or ''))
    widget.edit_modified(False)
    syncing = {'variable': False, 'widget': False}

    def capture_text(_event=None):
        if not widget.edit_modified():
            return
        widget.edit_modified(False)
        if syncing['variable']:
            return
        value = widget.get('1.0', 'end-1c')
        if variable.get() != value:
            syncing['widget'] = True
            try:
                variable.set(value)
            finally:
                syncing['widget'] = False
        if callable(on_edit):
            on_edit()

    def render_variable(*_args):
        if syncing['widget']:
            return
        value = str(variable.get() or '')
        if widget.get('1.0', 'end-1c') == value:
            return
        syncing['variable'] = True
        try:
            widget.delete('1.0', 'end')
            widget.insert('1.0', value)
            widget.edit_modified(False)
        finally:
            syncing['variable'] = False

    widget.bind('<<Modified>>', capture_text, add='+')
    variable.trace_add('write', render_variable)
    _right_align_form_187(widget)
    rtl_text187.install(widget)
    _bind_full_text_tooltip_187(widget, variable, form)
    return widget


def _refresh_report_rows_187(form) -> None:
    host = getattr(form, '_report_rows_host_187', None)
    if host is None or not host.winfo_exists():
        return
    previous = _document_rows_187(getattr(form, 'payload', {}).get('daily_report_rows'))
    for index, var in enumerate(getattr(form, '_report_row_vars_187', [])):
        if index < len(previous):
            try:
                previous[index]['description'] = str(var.get() or '').strip()
            except tk.TclError:
                pass
    count_var = getattr(form, 'vars', {}).get('report_row_count')
    count_value = count_var.get() if count_var is not None else ''
    # The count control is initially blank until _load_values runs. Preserve
    # existing rows while constructing (or rebuilding) the record form.
    count = parse_int(
        count_value if str(count_value).strip()
        else getattr(form, 'payload', {}).get('report_row_count') or len(previous)
    )
    count = max(0, min(count, 100))
    for child in host.winfo_children():
        child.destroy()
    form._report_row_vars_187 = []
    form._report_row_controls_187 = []
    p = palette_187()
    tk.Label(host, text='ردیف', bg=p['panel'], fg=p['muted'],
             font=(form.font_family, max(8, form.font_size - 1), 'bold'),
             anchor='e').grid(row=0, column=1, sticky='ew', padx=4, pady=2)
    tk.Label(host, text='شرح', bg=p['panel'], fg=p['muted'],
             font=(form.font_family, max(8, form.font_size - 1), 'bold'),
             anchor='e').grid(row=0, column=0, sticky='ew', padx=4, pady=2)
    host.grid_columnconfigure(0, weight=1)
    for index in range(count):
        tk.Label(host, text=fa(index + 1), bg=p['panel'], fg=p['text'],
                 font=(form.font_family, form.font_size), anchor='e').grid(
                     row=index + 1, column=1, sticky='e', padx=4, pady=2)
        prior = previous[index] if index < len(previous) else {}
        value = prior.get('description', '')
        variable = tk.StringVar(value=value)
        variable.trace_add('write', lambda *_args, target=form: _capture_report_rows_187(target))
        form._report_row_vars_187.append(variable)
        row_card = tk.Frame(host, bg=p['panel'], highlightbackground=p['line'], highlightthickness=1)
        row_card.grid(row=index + 1, column=0, sticky='ew', padx=4, pady=2)
        row_card.grid_columnconfigure(0, weight=1)
        phases = {}
        for col, (key, label) in enumerate((('main_phase', 'فاز اصلی'), ('sub_phase', 'فاز فرعی'))):
            cell = tk.Frame(row_card, bg=p['panel'])
            cell.grid(row=0, column=1 - col, sticky='ew', padx=4, pady=2)
            row_card.grid_columnconfigure(col, weight=1)
            tk.Label(cell, text=label, bg=p['panel'], fg=p['muted'], anchor='e').pack(fill='x')
            phases[key] = tk.StringVar(value=prior.get(key, ''))
            if key == 'main_phase':
                try:
                    from ai_parser import CONSTRUCTION_PHASES
                    options = tuple(f'{phase_no:02d} — {name}' for phase_no, name in enumerate(CONSTRUCTION_PHASES, 1))
                except ImportError:
                    options = ()
                ttk.Combobox(cell, textvariable=phases[key], values=options,
                             state='readonly' if options else 'normal', justify='right').pack(fill='x')
            else:
                ttk.Entry(cell, textvariable=phases[key], justify='right').pack(fill='x')
            phases[key].trace_add('write', lambda *_args, target=form: _capture_report_rows_187(target))
        desc = tk.Frame(row_card, bg=p['panel'])
        desc.grid(row=1, column=0, columnspan=2, sticky='ew', padx=4, pady=2)
        tk.Label(desc, text='شرح فعالیت', bg=p['panel'], fg=p['muted'], anchor='e').pack(fill='x')
        _multiline_description_widget_187(
            desc, variable, form,
            height=8 if isinstance(form, v182.UnifiedPendingEditor182) else 3,
            on_edit=lambda target=form: target._mark_manual('report_rows'),
        ).pack(fill='x')
        form._report_row_controls_187.append(phases)
    _capture_report_rows_187(form)


class WizardDateField187(v182.DateField):
    """Wizard date field using the shared RTL month/year Shamsi picker."""

    def open_calendar(self):
        return ShamsiDatePicker187(self, self.variable)


def _apply_wizard_font_187(window) -> None:
    """Apply the persisted application font to every wizard child widget."""
    try:
        ui = load_ui()
        family = resolve_font_family_187(window, ui.get('font_family'))
        default_size = max(7, int(ui.get('font_size') or getattr(window, 'font_size', 10)))
    except (TypeError, ValueError, tk.TclError):
        family = str(getattr(window, 'font_family', 'Segoe UI') or 'Segoe UI')
        default_size = max(7, int(getattr(window, 'font_size', 10) or 10))
    window.font_family = family

    def visit(widget):
        try:
            if 'font' in widget.keys():
                current = widget.cget('font')
                size, weight = default_size, 'normal'
                try:
                    spec = tkfont.Font(root=window, font=current)
                    size = max(7, int(spec.actual('size') or default_size))
                    weight = str(spec.actual('weight') or 'normal')
                except (TypeError, tk.TclError):
                    pass
                widget.configure(font=(family, size, weight))
        except (AttributeError, tk.TclError):
            pass
        try:
            for child in widget.winfo_children():
                visit(child)
        except tk.TclError:
            pass

    visit(window)


def _bind_data_number_187(entry, variable, *, allow_negative=False, decimal=False):
    def formatter(value):
        raw = (_clean_decimal if decimal else _clean_int)(value)
        if not allow_negative:
            raw = raw.replace('-', '')
        if raw in ('', '-', '.', '-.'):
            return raw
        return group_decimal_fa(raw) if decimal else group_int_fa(raw)
    format_numeric_entry(entry, variable, formatter, caret_at_end=True)


def _bind_data_decimal_187(entry, variable, *, allow_negative=False):
    _bind_data_number_187(entry, variable, allow_negative=allow_negative, decimal=True)


def _mark_manual_187(self, key):
    # Display normalization is not a manual correction of an AI suggestion.
    if not getattr(self.widgets.get(key), '_numeric_formatting187', False):
        _ORIGINAL_MARK_MANUAL_187(self, key)


def _editor_mark_manual_187(self, key):
    if (not getattr(self, '_loading', False)
            and not getattr(self.widgets.get(key), '_numeric_formatting187', False)):
        _ORIGINAL_EDITOR_MARK_MANUAL_187(self, key)


def _is_cheque_clearing_187(title, subtype):
    return title == 'هزینه ساخت' and subtype == CHEQUE_CLEARING_SUBTYPE_187


def _is_cheque_resolution_187(title, subtype, payload=None):
    data = payload if isinstance(payload, dict) else {}
    return (title == 'هزینه ساخت' and subtype == 'چک'
            and str(data.get('cheque_operation187') or '') == CHEQUE_OPERATION_RESOLVE_187)


def _cheque_resolution_detail_fields_187():
    F = v18.FieldDef
    return [
        F('cheque_snapshot_issue187', 'تاریخ صدور', 'entry', readonly=True),
        F('cheque_snapshot_due187', 'تاریخ سررسید', 'entry', readonly=True),
        F('cheque_snapshot_amount187', 'مبلغ چک', 'money', readonly=True),
        F('cheque_snapshot_issuer187', 'صاحب حساب / صادرکننده', 'entry', readonly=True),
        F('cheque_snapshot_receiver187', 'گیرنده', 'entry', readonly=True),
        F('cheque_snapshot_bank187', 'بانک', 'entry', readonly=True),
        F('cheque_snapshot_serial187', 'شماره چک / صیادی', 'entry', readonly=True),
        F('cheque_snapshot_type187', 'نوع چک', 'entry', readonly=True),
        F('cheque_snapshot_description187', 'بابت', 'entry', readonly=True),
    ]


def _cheque_resolution_status_fields_187():
    F = v18.FieldDef
    return [
        F('cheque_resolution_registration187', 'وضعیت ثبت چک', 'combo', tuple(v18.REG_BY_FA)),
        F('cheque_resolution_status187', 'وضعیت چک', 'combo', CHEQUE_RESOLUTION_STATUS_CHOICES_187),
        F('cheque_resolution_return_disposition187', 'وضعیت عودت چک', 'combo', CHEQUE_RETURN_DISPOSITION_CHOICES_187),
        F('cheque_resolution_account_holder187', 'صاحب حساب معرفی‌شده'),
        F('cheque_resolution_void_reason187', 'دلیل ابطال چک'),
    ]


def _cheque_resolution_status_code_187(label):
    return {
        'صادرشده': 'ISSUED', 'پاس‌شده': 'CASHED', 'برگشتی': 'RETURNED',
        'عودتی به شرط تسویه': 'RETURNED_ON_SETTLEMENT', 'باطل‌شده': 'VOIDED',
        'ISSUED': 'ISSUED', 'CASHED': 'CASHED', 'RETURNED': 'RETURNED',
        'RETURNED_ON_SETTLEMENT': 'RETURNED_ON_SETTLEMENT', 'VOIDED': 'VOIDED',
        'CANCELLED': 'VOIDED',
    }.get(str(label or '').strip(), '')


def _cheque_status_label_187(row):
    mode = str(row.get('settlement_mode') or '').upper()
    status = str(row.get('status') or 'ISSUED').upper()
    if mode == 'RETURNED_ON_SETTLEMENT':
        return 'عودتی به شرط تسویه'
    if mode == 'VOIDED' or status == 'CANCELLED':
        return 'باطل‌شده'
    return {'PENDING_DUE': 'صادرشده', 'ISSUED': 'صادرشده', 'CASHED': 'پاس‌شده',
            'RETURNED': 'برگشتی'}.get(status, status)


def _registered_cheques_for_clearing_187(include_ids=()):
    """Return open cheques and, while editing, this record's settled cheque."""
    try:
        # Resolve all outstanding cheques, including guarantees. The general
        # table's 500-row cap must not hide eligible cheques from this picker.
        with DB.read() as con:
            reviewing = con.execute("""SELECT DISTINCT c.cheque_id FROM cheques c
                JOIN pending_items p ON p.status IN ('EDIT_PENDING','PENDING_REVIEW','NEEDS_REVIEW')
                LEFT JOIN telegram_messages m ON p.telegram_chat_id=m.chat_id AND p.telegram_message_id=m.message_id
                LEFT JOIN financial_postings f ON f.pending_id=p.pending_id
                WHERE (m.linked_entity_type='CHEQUE' AND m.linked_entity_id=c.cheque_id)
                   OR f.cheque_id=c.cheque_id""").fetchall()
            include_ids=tuple(dict.fromkeys((*include_ids,*(row['cheque_id'] for row in reviewing))))
            rows = [dict(row) for row in con.execute(
                "SELECT * FROM cheques WHERE status IN ('ISSUED','PENDING_DUE') "
                "AND COALESCE(settlement_mode,'') != 'RETURNED_ON_SETTLEMENT' "
                "ORDER BY due_date ASC, created_at ASC")]
    except Exception:
        logging.getLogger(__name__).exception('Could not load registered cheques for clearing')
        return []
    by_id = {str(row.get('cheque_id') or ''): dict(row) for row in rows}
    for cheque_id in include_ids or ():
        cheque_id = str(cheque_id or '').strip()
        if not cheque_id or cheque_id in by_id:
            continue
        try:
            row = DB.get_cheque(cheque_id)
        except Exception:
            row = None
        if row and str(row.get('status') or '').upper() in {'CASHED', 'RETURNED', 'CANCELLED'}:
            by_id[cheque_id] = dict(row)
    return [row for row in by_id.values()
            if ((str(row.get('status') or '').upper() in {'ISSUED', 'PENDING_DUE'}
                 and str(row.get('settlement_mode') or '').upper() != 'RETURNED_ON_SETTLEMENT')
                or str(row.get('cheque_id') or '') in set(map(str, include_ids or ())))]


def _prepare_clearing_edit_state_187(form):
    payload = getattr(form, 'payload', {}) or {}
    if payload.get('_editing_cheque_clearing187') and payload.get('_original_clearing_cheque_id187'):
        form._editing_cheque_clearing187 = True
        form._original_clearing_cheque_id187 = str(payload.get('_original_clearing_cheque_id187'))
        form._original_clearing_mode187 = str(payload.get('_original_clearing_mode187') or '')
        # Keep the values saved with an existing transfer while the form is
        # initialized. A newly selected cheque may still seed blank fields.
        form._clearing_transfer_account_manual187 = bool(
            str(payload.get('cheque_transfer_account_holder187') or '').strip())
        form._clearing_transfer_description_manual187 = bool(
            str(payload.get('cheque_transfer_description187') or '').strip())
        return
    try:
        pending = DB.get_pending_item(str(getattr(form, 'pid', '') or '')) or {}
    except Exception:
        pending = {}
    if str(pending.get('status') or '').upper() not in {'APPROVED', 'EDIT_PENDING'}:
        form._editing_cheque_clearing187 = False
        return
    selected_id = str(payload.get('selected_cheque_id187') or payload.get('cheque_id') or '').strip()
    if not selected_id:
        try:
            message = DB.get_telegram_message(
                int(pending.get('telegram_chat_id') or 0), int(pending.get('telegram_message_id') or 0),
            ) or {}
            linked_id = str(message.get('linked_entity_id') or '').strip()
            linked_type = str(message.get('linked_entity_type') or '').upper()
            if linked_type == 'CHEQUE':
                linked = DB.get_cheque(linked_id)
                selected_id = str((linked or {}).get('cheque_id') or '')
        except Exception:
            selected_id = ''
    if not selected_id:
        form._editing_cheque_clearing187 = False
        return
    form._editing_cheque_clearing187 = True
    payload['_editing_cheque_clearing187'] = True
    payload['_original_clearing_cheque_id187'] = selected_id
    payload['_original_clearing_mode187'] = str(
        payload.get('cheque_clearing_mode187') or CHEQUE_CLEARING_MODES_187[0]
    )
    form._original_clearing_cheque_id187 = selected_id
    form._original_clearing_mode187 = payload['_original_clearing_mode187']
    if payload['_original_clearing_mode187'] == CHEQUE_CLEARING_MODES_187[1]:
        try:
            message = DB.get_telegram_message(
                int(pending.get('telegram_chat_id') or 0), int(pending.get('telegram_message_id') or 0),
            ) or {}
            linked = DB.get_cheque(str(message.get('linked_entity_id') or ''))
            if linked and linked.get('cash_transaction_id'):
                with DB.read() as con:
                    tx = con.execute(
                        'SELECT receiver_name,description FROM transactions WHERE transaction_id=?',
                        (linked['cash_transaction_id'],),
                    ).fetchone()
                if tx:
                    payload.setdefault('cheque_transfer_account_holder187', tx['receiver_name'] or '')
                    payload.setdefault('cheque_transfer_description187', linked.get('description') or '')
        except Exception:
            logging.getLogger(__name__).exception('Could not restore transfer details for cheque edit %s', selected_id)


def _cheque_date_delta_187(target, raw):
    if not target or not raw:
        return None
    try:
        target_sh = normalize_shamsi(str(target))
        cheque_sh = normalize_shamsi(str(raw))
        target_date = date.fromisoformat(shamsi_to_gregorian(target_sh))
        cheque_date = date.fromisoformat(shamsi_to_gregorian(cheque_sh))
        return abs((target_date - cheque_date).days)
    except (TypeError, ValueError):
        return None


def _suggest_clearing_cheque_187(rows, amount, event_date):
    """Suggest a unique exact-amount cheque, preferring the nearest due date."""
    amount = parse_int(amount or 0)
    if amount <= 0:
        return ''
    dated = []
    for row in rows:
        if parse_int(row.get('amount') or 0) != amount:
            continue
        delta = _cheque_date_delta_187(event_date, row.get('due_date_shamsi') or row.get('due_date'))
        if delta is None:
            delta = _cheque_date_delta_187(event_date, row.get('issue_date_shamsi') or row.get('issue_date'))
        dated.append((delta if delta is not None else 10**9, str(row.get('cheque_id') or '')))
    if not dated:
        return ''
    dated.sort()
    if len(dated) > 1 and dated[0][0] == dated[1][0]:
        return ''
    return dated[0][1]


def _own_resolved_cheque_187(form):
    """The cheque a resolution record already resolves, while that record is approved or being edited.

    Such a cheque is no longer «تعیین‌تکلیف‌نشده», but the record that resolved it still lists it, selected;
    without it the picker of the record (window or wizard) would be empty or lose the choice."""
    payload = getattr(form, 'payload', None)
    if not isinstance(payload, dict):
        return ''
    own = str(payload.get('_resolution_edit_cheque_id187') or '')
    if own:
        return own
    selected = str(payload.get('selected_cheque_id187') or payload.get('cheque_id') or '').strip()
    pending_id = str(getattr(form, 'pid', '') or '')
    if not (selected and pending_id and str(payload.get('cheque_operation187') or '') == CHEQUE_OPERATION_RESOLVE_187):
        return ''
    if str((DB.get_pending_item(pending_id) or {}).get('status') or '') in ('APPROVED', 'EDIT_PENDING'):
        payload['_resolution_edit_cheque_id187'] = selected
        return selected
    return ''


def _populate_clearing_cheque_picker_187(form):
    tree = getattr(form, 'widgets', {}).get('selected_cheque_id187')
    variable = getattr(form, 'vars', {}).get('selected_cheque_id187')
    if tree is None or variable is None:
        return
    if _is_cheque_clearing_187(
            getattr(getattr(form, 'title_var', None), 'get', lambda: '')(),
            getattr(getattr(form, 'subtype_var', None), 'get', lambda: '')()):
        _prepare_clearing_edit_state_187(form)
    resolution_edit_id = _own_resolved_cheque_187(form)
    include_ids = (getattr(form, '_original_clearing_cheque_id187', ''), resolution_edit_id)
    rows = _registered_cheques_for_clearing_187(include_ids=include_ids)
    form._clearing_cheques_by_id187 = {str(row.get('cheque_id')): row for row in rows}
    for item in tree.get_children():
        tree.delete(item)
    for row in rows:
        status = _cheque_status_label_187(row)
        tree.insert('', 'end', iid=str(row['cheque_id']), values=(
            group_int_fa(parse_int(row.get('amount') or 0)),
            rtl_187(fa(row.get('due_date_shamsi') or row.get('due_date') or '-')),
            rtl_187(fa(row.get('receiver_name') or '-')),
            rtl_187(fa(row.get('description') or '-')), rtl_187(fa(status)),
        ))
    current = str(variable.get() or '').strip()
    manual = bool(getattr(form, '_clearing_cheque_manual187', False)
                  or (getattr(form, 'payload', {}) or {}).get('selected_cheque_manual187'))
    operation = getattr(form, 'vars', {}).get('cheque_operation187')
    resolving = str(operation.get() if operation is not None
                    else (getattr(form, 'payload', {}) or {}).get('cheque_operation187') or '') == CHEQUE_OPERATION_RESOLVE_187
    # a resolution that already names a cheque from the list keeps it; the amount/date suggestion is for new ones
    keep = resolving and current in form._clearing_cheques_by_id187
    if ((not manual and not getattr(form, '_editing_cheque_clearing187', False)
         and not resolution_edit_id and not keep)
            or current not in form._clearing_cheques_by_id187):
        current = _suggest_clearing_cheque_187(
            rows,
            getattr(form, 'vars', {}).get('amount').get()
            if getattr(form, 'vars', {}).get('amount') is not None else form.payload.get('amount'),
            getattr(form, 'vars', {}).get('event_date_shamsi').get()
            if getattr(form, 'vars', {}).get('event_date_shamsi') is not None else form.payload.get('event_date_shamsi'),
        )
    form._loading = True
    try:
        variable.set(current)
        state_var = getattr(form, 'vars', {}).get('cheque_status')
        if state_var is not None:
            raw_status = str((form.payload or {}).get('cheque_status') or '').upper()
            label = v18.CODE_TO_CHEQUE_STATUS.get(raw_status, raw_status)
            if label not in CHEQUE_CLEARING_STATUS_CHOICES_187:
                label = 'پاس‌شده'
            state_var.set(label)
        mode_var = getattr(form, 'vars', {}).get('cheque_clearing_mode187')
        if mode_var is not None and mode_var.get() not in CHEQUE_CLEARING_MODES_187:
            mode_var.set(str((form.payload or {}).get('cheque_clearing_mode187') or
                             CHEQUE_CLEARING_MODES_187[0]))
    finally:
        form._loading = False
    if current and current in form._clearing_cheques_by_id187:
        tree.selection_set(current)
        tree.focus(current)
        tree.see(current)
    else:
        tree.selection_remove(tree.selection())
    _sync_clearing_transfer_defaults_187(form, current)
    _sync_clearing_transfer_visibility_187(form)
    _bind_clearing_mode_187(form)
    traced = getattr(form, '_clearing_match_vars187', {})
    for key in ('amount', 'event_date_shamsi'):
        var = getattr(form, 'vars', {}).get(key)
        if var is not None and traced.get(key) is not var:
            var.trace_add('write', lambda *_args, target=form: _refresh_clearing_suggestion_187(target))
            traced[key] = var
    form._clearing_match_vars187 = traced


def _sync_cheque_operation_visibility_187(form):
    operation = getattr(form, 'vars', {}).get('cheque_operation187')
    picker = getattr(form, 'widgets', {}).get('selected_cheque_id187')
    if operation is None or picker is None:
        return
    try:
        box = picker.master.master
        if str(operation.get() or '') == CHEQUE_OPERATION_RESOLVE_187:
            box.grid()
            _populate_clearing_cheque_picker_187(form)
        else:
            box.grid_remove()
    except (AttributeError, tk.TclError):
        pass


CHEQUE_NUMBER_LABELS_187 = {'PHYSICAL': 'شماره چک', 'DIGITAL': 'شماره صیادی'}
CHEQUE_NUMBER_LABEL_DEFAULT_187 = 'شماره چک / صیادی'


def _install_cheque_number_label_187(form):
    """The number box is «شماره چک» for a physical cheque and «شماره صیادی» for a digital one."""
    widget = (getattr(form, 'widgets', {}) or {}).get('cheque_serial')
    kind = (getattr(form, 'vars', {}) or {}).get('cheque_type')
    if widget is None or kind is None or getattr(widget, '_number_label187', False):
        return
    widget._number_label187 = True
    known = {CHEQUE_NUMBER_LABEL_DEFAULT_187, *CHEQUE_NUMBER_LABELS_187.values()}

    def relabel(*_args):
        code = v18.CHEQUE_TYPE_BY_FA.get(str(kind.get() or '').strip(), str(kind.get() or '').upper())
        text = CHEQUE_NUMBER_LABELS_187.get(code, CHEQUE_NUMBER_LABEL_DEFAULT_187)
        try:
            for child in widget.master.winfo_children():
                if isinstance(child, tk.Label) and str(child.cget('text')) in known:
                    child.configure(text=text)
                    break
        except tk.TclError:
            pass

    kind.trace_add('write', relabel)
    relabel()


CHEQUE_ISSUED_LABEL_187 = 'صادرشده'


def _choose_cheque_incomplete_action_187(parent, missing):
    """«نادیده گرفتن» / «باز کردن رکورد تعیین تکلیف» / «انصراف». Only the last leaves the status as it was."""
    window = BarkavWindow(parent, 'تکمیل عملیات تعیین تکلیف', size_class='tiny', show_footer=False)
    decision = {'value': 'cancel'}
    tk.Label(window.body, text=('وضعیت چک تغییر می‌کند و در رکورد تعیین تکلیف هم ثبت می‌شود، اما این موارد هنوز ثبت نشده‌اند.\n'
                           + '\n'.join('• ' + item for item in missing)
                           + '\nبرای تکمیل عملیات به رکورد تعیین تکلیف مراجعه کنید.'),
             bg=palette_187()['panel'], fg=palette_187()['text_primary'], wraplength=470, justify='right',
             anchor='e', padx=18, pady=16).pack(fill='x')
    actions = tk.Frame(window.body, bg=palette_187()['panel'])
    actions.pack(fill='x', padx=16, pady=(0, 14))
    for value, text, side in (('open', 'باز کردن رکورد تعیین تکلیف', 'right'), ('ignore', 'نادیده گرفتن', 'right'),
                              ('cancel', 'انصراف', 'left')):
        tk.Button(actions, text=text, command=lambda v=value: (decision.update(value=v), window.destroy()),
                  relief='flat', padx=14, pady=7).pack(side=side, padx=4)
    window.grab_set()
    window.wait_window()
    return decision['value']


def _cheque_dialog_save_187(self):
    """Manual status change from the cheque tab: the resolution record follows it. Only a status
    that still lacks the details its record must hold raises the three-way question."""
    v = v18.v175
    try:
        issue = v.normalize_shamsi(self.vars['issue'].get())
        due = v.normalize_shamsi(self.vars['due'].get())
        if not issue or not due:
            raise ValueError('تاریخ صدور/سررسید نامعتبر است.')
        new_status = v.CHEQUE_STATUS_BY_FA.get(self.vars['lifecycle'].get(), 'ISSUED')
        registration = v.REG_BY_FA.get(self.vars['registration_state'].get(), 'UNREGISTERED')
        cheque_id = str(self.row['cheque_id'])
        current = DB.get_cheque(cheque_id) or self.row
        current_code = _cheque_resolution_status_code_187(_cheque_status_label_187(current)) or 'ISSUED'
        holder = self.vars['return_account_holder'].get().strip()
        reason = self.vars['void_reason'].get().strip()
        missing = []
        if new_status == 'RETURNED_ON_SETTLEMENT' and not holder:
            missing.append('نام صاحب حساب معرفی‌شده')
        if new_status == 'VOIDED' and not reason:
            missing.append('دلیل ابطال چک')
        action = 'ignore'
        if missing and new_status != current_code:
            action = _choose_cheque_incomplete_action_187(self, missing)
            if action == 'cancel':
                return
        old_status = str(self.row.get('status') or 'ISSUED').upper()
        if old_status not in {'CASHED', 'CANCELLED'}:
            DB.update_cheque_details(
                cheque_id, amount=parse_int(self.vars['amount'].get()), issue_date=v.shamsi_to_gregorian(issue),
                issue_date_shamsi=issue, due_date=v.shamsi_to_gregorian(due), due_date_shamsi=due,
                issuer_name=self.vars['issuer_name'].get().strip(),
                cheque_type=v.CHEQUE_TYPE_BY_FA.get(self.vars['cheque_type'].get(), 'PHYSICAL'),
                receiver_name=self.vars['receiver_name'].get().strip(),
                issuer_bank=self.vars['issuer_bank'].get().strip(), cheque_serial=self.vars['cheque_serial'].get().strip(),
                description=self.vars['description'].get().strip(), is_guarantee=self.guarantee.get(),
                source='GUI_17_5', actor_id='GUI')
        disposition = self.vars['return_disposition'].get()
        if disposition not in CHEQUE_RETURN_DISPOSITION_CHOICES_187:
            disposition = CHEQUE_RETURN_DISPOSITION_CHOICES_187[3]
        DB.update_cheque_workflow_state(
            cheque_id, lifecycle=new_status, registration_state=registration,
            return_disposition=disposition if new_status in {'RETURNED_ON_SETTLEMENT', 'VOIDED'} else None,
            return_account_holder=holder if new_status == 'RETURNED_ON_SETTLEMENT' else None,
            void_reason=reason if new_status == 'VOIDED' else None,
            source='GUI_17_5', actor_id='GUI', require_details=False)
        parent = self.master
        self.destroy()
        self.on_refresh()
        if action == 'open':
            linked = DB.get_cheque_registered_pending(cheque_id)
            if linked:
                linked['cheque_id'] = cheque_id
                parent.after(0, lambda target=parent, item=linked: v._open_cheque_source_wizard175(target, item))
    except Exception as exc:
        messagebox.showerror('چک', str(exc), parent=self)


v18.v175.ChequeEditDialog175.save = _cheque_dialog_save_187


def _install_disabled_issued_status_187(form):
    """«صادرشده» is listed in the resolution status box but greyed out: a cheque
    being resolved cannot be set back to issued, and picking it changes nothing."""
    widget = (getattr(form, 'widgets', {}) or {}).get('cheque_resolution_status187')
    variable = (getattr(form, 'vars', {}) or {}).get('cheque_resolution_status187')
    if widget is None or variable is None or getattr(widget, '_issued_disabled187', False):
        return
    widget._issued_disabled187 = True
    widget.configure(values=(CHEQUE_ISSUED_LABEL_187, *CHEQUE_RESOLUTION_STATUS_CHOICES_187))
    last = [str(variable.get() or '')]
    if last[0] == CHEQUE_ISSUED_LABEL_187:
        last[0] = ''

    def selected(_event=None):
        if variable.get() == CHEQUE_ISSUED_LABEL_187:
            variable.set(last[0])
        else:
            last[0] = str(variable.get() or '')

    def grey_out_issued():
        try:
            popdown = widget.tk.call('ttk::combobox::PopdownWindow', str(widget))
            widget.tk.call(f'{popdown}.f.l', 'itemconfigure', 0, '-foreground', palette_187()['text_muted'],
                           '-selectforeground', palette_187()['text_muted'])
        except (tk.TclError, KeyError):
            pass

    widget.bind('<<ComboboxSelected>>', selected, add='+')
    # Tk fills the list after -postcommand returns, so grey the entry once it exists.
    widget.configure(postcommand=lambda: widget.after(5, grey_out_issued))


def _sync_cheque_resolution_optional_fields_187(form):
    variables = getattr(form, 'vars', {}) or {}
    widgets = getattr(form, 'widgets', {}) or {}
    status_var = variables.get('cheque_resolution_status187')
    if status_var is None:
        return
    _install_disabled_issued_status_187(form)
    status = str(status_var.get() or '')
    show_return = status in {'عودتی به شرط تسویه', 'باطل‌شده'}
    show_account = status == 'عودتی به شرط تسویه'
    show_reason = status == 'باطل‌شده'
    for key, show in (
        ('cheque_resolution_return_disposition187', show_return),
        ('cheque_resolution_account_holder187', show_account),
        ('cheque_resolution_void_reason187', show_reason),
    ):
        widget = widgets.get(key)
        if widget is None:
            continue
        try:
            box = widget.master
            (box.grid if show else box.grid_remove)()
        except (AttributeError, tk.TclError):
            pass
    if getattr(form, '_cheque_resolution_status_trace187', None) is not status_var:
        form._cheque_resolution_status_trace187 = status_var
        status_var.trace_add('write', lambda *_args, target=form:
                             _sync_cheque_resolution_optional_fields_187(target))


def _refresh_clearing_suggestion_187(form):
    if getattr(form, '_loading', False) or getattr(form, '_clearing_cheque_manual187', False):
        return
    tree = getattr(form, 'widgets', {}).get('selected_cheque_id187')
    variable = getattr(form, 'vars', {}).get('selected_cheque_id187')
    if tree is None or variable is None:
        return
    rows = list(getattr(form, '_clearing_cheques_by_id187', {}).values())
    amount = form.vars.get('amount').get() if form.vars.get('amount') is not None else form.payload.get('amount')
    event_date = form.vars.get('event_date_shamsi').get() if form.vars.get('event_date_shamsi') is not None else form.payload.get('event_date_shamsi')
    selected = _suggest_clearing_cheque_187(rows, amount, event_date)
    form._loading = True
    try:
        variable.set(selected)
        if selected:
            tree.selection_set(selected)
            tree.focus(selected)
            tree.see(selected)
        else:
            tree.selection_remove(tree.selection())
    finally:
        form._loading = False
    _sync_clearing_transfer_defaults_187(form, selected)


def _clearing_cheque_selected_187(form):
    tree = getattr(form, 'widgets', {}).get('selected_cheque_id187')
    selected = tree.selection() if tree is not None else ()
    if not selected:
        return
    cheque_id = str(selected[0])
    variable = getattr(form, 'vars', {}).get('selected_cheque_id187')
    if variable is not None and str(variable.get() or '') == cheque_id:
        return
    if variable is not None:
        variable.set(cheque_id)
    form._clearing_cheque_manual187 = True
    try:
        form.payload['selected_cheque_manual187'] = True
    except (AttributeError, TypeError):
        pass
    status_var = getattr(form, 'vars', {}).get('cheque_status')
    if status_var is not None:
        form._loading = True
        try:
            status_var.set('پاس‌شده')
        finally:
            form._loading = False
    _sync_clearing_transfer_defaults_187(form, cheque_id)
    _sync_clearing_transfer_visibility_187(form)


def _sync_clearing_transfer_defaults_187(form, cheque_id=None):
    variable = getattr(form, 'vars', {}).get('selected_cheque_id187')
    cheque_id = str(cheque_id or (variable.get() if variable is not None else ''))
    row = getattr(form, '_clearing_cheques_by_id187', {}).get(cheque_id)
    if row is None and cheque_id:
        try:
            row = DB.get_cheque(cheque_id)
        except Exception:
            row = None
    if not row:
        return
    account_var = getattr(form, 'vars', {}).get('cheque_transfer_account_holder187')
    description_var = getattr(form, 'vars', {}).get('cheque_transfer_description187')
    if account_var is None and description_var is None:
        return
    old_loading = getattr(form, '_loading', False)
    form._loading = True
    try:
        if account_var is not None and not getattr(form, '_clearing_transfer_account_manual187', False):
            account_var.set(str(row.get('issuer_name') or row.get('receiver_name') or ''))
        if description_var is not None and not getattr(form, '_clearing_transfer_description_manual187', False):
            description_var.set(str(row.get('description') or ''))
    finally:
        form._loading = old_loading


def _sync_clearing_transfer_visibility_187(form):
    mode_var = getattr(form, 'vars', {}).get('cheque_clearing_mode187')
    transfer = bool(mode_var is not None and str(mode_var.get() or '').strip() == CHEQUE_CLEARING_MODES_187[1])
    for key in ('cheque_transfer_account_holder187', 'cheque_transfer_description187'):
        widget = getattr(form, 'widgets', {}).get(key)
        if widget is None:
            continue
        try:
            box = widget.master
            if transfer:
                box.grid()
            else:
                box.grid_remove()
        except (AttributeError, tk.TclError):
            pass


def _bind_clearing_mode_187(form):
    variable = getattr(form, 'vars', {}).get('cheque_clearing_mode187')
    if variable is None or getattr(form, '_clearing_mode_trace_var187', None) is variable:
        return
    form._clearing_mode_trace_var187 = variable
    variable.trace_add('write', lambda *_args, target=form: (
        _sync_clearing_transfer_defaults_187(target),
        _sync_clearing_transfer_visibility_187(target),
    ))


def _clearing_review_text_187(form):
    variables = getattr(form, 'vars', {}) or {}
    selected_id = str(variables.get('selected_cheque_id187').get()
                      if variables.get('selected_cheque_id187') is not None else
                      (getattr(form, 'payload', {}) or {}).get('selected_cheque_id187') or
                      (getattr(form, 'payload', {}) or {}).get('cheque_id') or '')
    cheque = getattr(form, '_clearing_cheques_by_id187', {}).get(selected_id)
    if cheque is None and selected_id:
        try:
            cheque = DB.get_cheque(selected_id)
        except Exception:
            cheque = None
    if not cheque:
        return 'چکی انتخاب نشده است.'
    mode = str(variables.get('cheque_clearing_mode187').get()
               if variables.get('cheque_clearing_mode187') is not None else
               (getattr(form, 'payload', {}) or {}).get('cheque_clearing_mode187') or '')
    lines = [
        f"چک: {selected_id} — {group_int_fa(parse_int(cheque.get('amount') or 0))} تومان",
        f"گیرندهٔ ثبت‌شده: {cheque.get('receiver_name') or '-'}",
        f"روش پاس‌شدن: {mode or '-'}",
    ]
    if mode == CHEQUE_CLEARING_MODES_187[1]:
        lines.extend((
            f"صاحب حساب مقصد: {variables.get('cheque_transfer_account_holder187').get() if variables.get('cheque_transfer_account_holder187') is not None else (getattr(form, 'payload', {}) or {}).get('cheque_transfer_account_holder187') or '-'}",
            f"بابت واریز: {variables.get('cheque_transfer_description187').get() if variables.get('cheque_transfer_description187') is not None else (getattr(form, 'payload', {}) or {}).get('cheque_transfer_description187') or '-'}",
        ))
    return '\n'.join(rtl_187(fa(line)) for line in lines)


def _dynamic_field_187(self, parent, fd, row: int, col: int, *, ai=True, width=24):
    """Render specialized fields with the shared form font and RTL grid."""
    if isinstance(self, v182.UnifiedPendingEditor182):
        general = getattr(self, '_general_fields187', {})
        if fd.key in general and parent is not getattr(self, 'cost_group_row', None):
            variable, widget = general[fd.key]
            self.vars[fd.key], self.widgets[fd.key] = variable, widget
            return widget
        if fd.key == 'description':
            # The record editor supplies one persistent multiline about field.
            return None
        if col < 0 and fd.key == 'is_guarantee':
            # The inherited cheque row has five fields but four columns. Its
            # fifth control can use the removed small description's column.
            col = 0
    title = str(getattr(getattr(self, 'title_var', None), 'get', lambda: '')() or
                getattr(self, 'payload', {}).get('v18_title') or '')
    if fd.key == 'construction_stage' and title == 'یادداشت':
        fd = v18.FieldDef(fd.key, fd.label, 'combo', _note_phase_choices_187(self), fd.readonly)
    if (fd.key == 'amount' and title == 'یادداشت' and not fd.readonly
            and not isinstance(self, v182.UnifiedPendingEditor182)):
        fd = v18.FieldDef(fd.key, fd.label, fd.kind, fd.values, readonly=True)
    if fd.kind == 'date':
        # The inherited renderer resolves DateField in dashboard_stage18's
        # module globals.  Swap only for this synchronous render so other
        # legacy screens keep their established field implementation.
        original_date_field = v18.DateField
        v18.DateField = WizardDateField187
        try:
            return _ORIGINAL_DYNAMIC_FIELD_187(self, parent, fd, row, col, ai=ai, width=width)
        finally:
            v18.DateField = original_date_field
    if fd.kind == 'cheque_picker':
        p = palette_187()
        box = tk.Frame(parent, bg=p['panel'])
        box.grid(row=row, column=col, sticky='nsew', padx=5, pady=4)
        box.grid_columnconfigure(0, weight=1)
        tk.Label(box, text=fd.label, bg=p['panel'], fg=p['text'], anchor='e',
                 font=(self.font_family, self.font_size, 'bold')).grid(
                     row=0, column=0, sticky='e')
        variable = tk.StringVar(value=str((getattr(self, 'payload', {}) or {}).get(fd.key) or ''))
        host = tk.Frame(box, bg=p['panel'])
        host.grid(row=1, column=0, sticky='nsew', pady=(3, 0))
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(0, weight=1)
        columns = ('amount', 'due', 'receiver', 'description', 'status')
        tree = ttk.Treeview(host, columns=columns, show='headings', height=5,
                            selectmode='browse')
        for key, label, size in (
            ('amount', 'مبلغ', 100), ('due', 'سررسید', 100),
            ('receiver', 'گیرنده', 120), ('description', 'بابت', 180),
            ('status', 'وضعیت', 100),
        ):
            tree.heading(key, text=label)
            tree.column(key, width=size, minwidth=55, anchor='center', stretch=True)
        proportions = {'amount': .16, 'due': .16, 'receiver': .20, 'description': .31, 'status': .17}
        resizing = {'pending': False}
        def fit_columns(_event=None):
            if resizing['pending']:
                return
            resizing['pending'] = True
            def apply():
                resizing['pending'] = False
                try:
                    available = max(275, tree.winfo_width() - 2)
                    for key, ratio in proportions.items():
                        tree.column(key, width=max(55, int(available * ratio)))
                except tk.TclError:
                    pass
            try:
                tree.after_idle(apply)
            except tk.TclError:
                resizing['pending'] = False
        tree.bind('<Configure>', fit_columns, add='+')
        tree.after_idle(fit_columns)
        try:
            apply_tree_rtl_kit(tree)
        except Exception:
            pass
        vscroll = ttk.Scrollbar(host, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=vscroll.set)
        tree.grid(row=0, column=0, sticky='nsew')
        vscroll.grid(row=0, column=1, sticky='ns')
        self.vars[fd.key] = variable
        self.widgets[fd.key] = tree
        tree.bind('<<TreeviewSelect>>', lambda _event, target=self: _clearing_cheque_selected_187(target), add='+')
        if ai:
            tk.Label(box, text='انتخاب هوشمند بر پایه مبلغ و تاریخ؛ برای تغییر، ردیف دیگری را انتخاب کنید.',
                     bg=p['panel'], fg=p['muted'], anchor='e',
                     font=(self.font_family, max(7, self.font_size - 2))).grid(
                         row=2, column=0, sticky='e', pady=(2, 0))
        return tree
    if fd.kind == 'cheque_review187':
        p = palette_187()
        box = tk.Frame(parent, bg=p['panel'], highlightbackground=p.get('border_subtle', p['line']),
                       highlightthickness=1)
        box.grid(row=row, column=col, sticky='nsew', padx=5, pady=4)
        box.grid_columnconfigure(0, weight=1)
        tk.Label(box, text=fd.label, bg=p['panel'], fg=p['text'], anchor='e',
                 font=(self.font_family, self.font_size, 'bold')).grid(
                     row=0, column=0, sticky='e', padx=9, pady=(7, 2))
        review = tk.StringVar(value=_clearing_review_text_187(self))
        tk.Label(box, textvariable=review, bg=p['panel'], fg=p['text'], anchor='e',
                 justify='right', wraplength=560,
                 font=(self.font_family, self.font_size)).grid(
                     row=1, column=0, sticky='ew', padx=9, pady=(2, 9))
        self._clearing_review_var187 = review
        self._clearing_review_form187 = self
        self.widgets[fd.key] = box
        return box
    if fd.kind == 'short_text':
        widget = _ORIGINAL_DYNAMIC_FIELD_187(self, parent, fd, row, col, ai=ai, width=width)
        variable = getattr(self, 'vars', {}).get(fd.key)
        if variable is not None:
            flag = ('_clearing_transfer_account_manual187'
                    if fd.key == 'cheque_transfer_account_holder187'
                    else '_clearing_transfer_description_manual187')
            variable.trace_add('write', lambda *_args, target=self, attr=flag: setattr(
                target, attr, True) if not getattr(target, '_loading', False) else None)
        return widget
    if fd.kind in {'money', 'int', 'float'}:
        # Intercept the inherited renderer's binders before it installs traces.
        # Only registration uses append-at-end; other editors retain their caret.
        old_number, old_decimal = v18.bind_grouped_number, v18.bind_grouped_decimal
        v18.bind_grouped_number, v18.bind_grouped_decimal = _bind_data_number_187, _bind_data_decimal_187
        try:
            return _ORIGINAL_DYNAMIC_FIELD_187(self, parent, fd, row, col, ai=ai, width=width)
        finally:
            v18.bind_grouped_number, v18.bind_grouped_decimal = old_number, old_decimal
    if fd.kind not in {'file', 'images', 'report_rows', 'text'} and fd.key != 'description':
        return _ORIGINAL_DYNAMIC_FIELD_187(self, parent, fd, row, col, ai=ai, width=width)
    p = palette_187()
    box = tk.Frame(parent, bg=p['panel'])
    box.grid(row=row, column=col, sticky='nsew', padx=5, pady=4)
    box.grid_columnconfigure(0, weight=1)
    tk.Label(box, text=fd.label, bg=p['panel'], fg=p['text'], anchor='e',
             font=(self.font_family, self.font_size, 'bold')).grid(row=0, column=0, sticky='e')
    if fd.kind == 'report_rows':
        variable = tk.StringVar(value=json.dumps(self.payload.get('daily_report_rows') or [], ensure_ascii=False))
        host = tk.Frame(box, bg=p['panel'])
        host.grid(row=1, column=0, sticky='nsew', pady=(3, 0))
        self._report_rows_host_187 = host
        self._report_row_vars_187 = []
        self.vars[fd.key] = variable
        self.widgets[fd.key] = host
        _refresh_report_rows_187(self)
    elif fd.kind == 'text' or fd.key == 'description':
        # «بابت» is typed from the right in a box of its own wherever it is asked, not in a left-to-right Entry
        variable = tk.StringVar(value=str(self.payload.get(fd.key) or ''))
        widget = _multiline_description_widget_187(
            box, variable, self, height=3 if fd.key == 'description' else 5,
            on_edit=lambda key=fd.key: self._mark_manual(key),
            width=24 if fd.key == 'description' else None,
        )
        widget.grid(row=1, column=0, sticky='ew', pady=(3, 0))
        self.vars[fd.key] = variable
        self.widgets[fd.key] = widget
    else:
        paths = _document_paths_187(self.payload.get(fd.key))
        variable = tk.StringVar(value=json.dumps(paths, ensure_ascii=False) if fd.kind == 'images' else (paths[0] if paths else ''))
        line = tk.Frame(box, bg=p['panel'])
        line.grid(row=1, column=0, sticky='ew', pady=(3, 0))
        line.grid_columnconfigure(1, weight=1)
        entry = ttk.Entry(line, textvariable=variable, justify='right', state='readonly')
        entry.grid(row=0, column=1, sticky='ew')
        button = ttk.Button(
            line, text='انتخاب تصاویر' if fd.kind == 'images' else 'انتخاب فایل',
            style='Toolbar.TButton',
            command=lambda target=self, key=fd.key, many=fd.kind == 'images':
                _choose_document_file_187(target, key, multiple=many),
        )
        button.grid(row=0, column=0, padx=(4, 0))
        self.vars[fd.key] = variable
        self.widgets[fd.key] = entry
    if not fd.readonly:
        if fd.kind not in {'text', 'report_rows'} and fd.key != 'description':
            try:
                variable.trace_add('write', lambda *_args, key=fd.key: self._mark_manual(key))
            except tk.TclError:
                pass
    if ai:
        tk.Label(box, text=f"AI: {v18._ai_value(self.ai_original, fd.key)}", bg=p['panel'], fg=p['muted'],
                 font=(self.font_family, max(7, self.font_size - 2)), anchor='e').grid(
                     row=2, column=0, sticky='e', pady=(2, 0))
    return self.widgets[fd.key]


def _form_title_187(form) -> str:
    title_var = getattr(form, 'title_var', None)
    title = title_var.get() if title_var is not None else ''
    return str(title or (getattr(form, 'payload', None) or {}).get('v18_title') or '')


def _dynamic_field_with_installments_187(self, parent, fd, row: int, col: int, *, ai=True, width=24):
    """Render the field; typing in an instalment count also re-computes the remaining count."""
    widget = _dynamic_field_187(self, parent, fd, row, col, ai=ai, width=width)
    if fd.key == 'loan_id' and _form_title_187(self) == 'خروجی':
        widget.configure(values=_loan_picker_values_187())
    variable = getattr(self, 'vars', {}).get(fd.key)
    if (fd.key in _INSTALLMENT_TYPED_KEYS_187 and variable is not None
            and _form_title_187(self) == 'خروجی' and not getattr(variable, '_installment_traced187', False)):
        variable._installment_traced187 = True
        variable.trace_add('write', lambda *_args, target=self, key=fd.key: _sync_installments_187(
            target, key if key == 'remaining_installments' else ''))
        if fd.key == 'remaining_installments':
            widget.bind('<FocusOut>', lambda _event, target=self: _refill_remaining_187(target), add='+')
    return widget


def _load_values_187(self, title: str, subtype: str):
    _ORIGINAL_LOAD_VALUES_187(self, title, subtype)
    if _is_installment_payload_187(title, subtype):
        # Loading a record shows its loan by name and starts its remaining count again from what was saved.
        _show_loan_name_187(self)
        self._remaining_own187 = None
        _sync_installments_187(self)
    if _is_cheque_resolution_187(title, subtype, getattr(self, 'payload', {})):
        self._loading = True
        try:
            for field in _cheque_resolution_detail_fields_187() + _cheque_resolution_status_fields_187():
                variable = self.vars.get(field.key)
                if variable is not None:
                    value = self.payload.get(field.key, '')
                    variable.set(group_int_fa(value) if field.kind == 'money' else str(value or ''))
        finally:
            self._loading = False
    stage_var = getattr(self, 'vars', {}).get('construction_stage')
    if stage_var is not None:
        try:
            stage_var.set(_phase_display_187(self, (getattr(self, 'payload', {}) or {}).get('construction_stage')))
        except tk.TclError:
            pass
    subtype = _canonical_document_subtype_187(subtype)
    if _is_cheque_clearing_187(title, subtype):
        _prepare_clearing_edit_state_187(self)
        self._clearing_cheque_manual187 = bool(
            (getattr(self, 'payload', {}) or {}).get('selected_cheque_manual187'))
        _populate_clearing_cheque_picker_187(self)
    if _is_nonfinancial_payload_187(title, subtype):
        payload = getattr(self, 'payload', {}) or {}
        attachments = _document_attachment_paths_187(self)
        image_paths = [str(row.get('local_path') or '') for row in attachments
                       if str(row.get('document_type') or '').upper() == 'DAILY_REPORT_IMAGE'
                       or str(row.get('mime_type') or '').lower().startswith('image/')]
        file_paths = [str(row.get('local_path') or '') for row in attachments
                      if str(row.get('document_type') or '').upper() != 'DAILY_REPORT_IMAGE'
                      and not str(row.get('mime_type') or '').lower().startswith('image/')]
        values = {
            'calendar_date_shamsi': payload.get('calendar_date_shamsi') or payload.get('event_date_shamsi') or '',
            'report_date_shamsi': payload.get('report_date_shamsi') or payload.get('event_date_shamsi') or '',
            'reminder_date_shamsi': payload.get('reminder_date_shamsi') or payload.get('event_date_shamsi') or '',
            'invoice_note_date_shamsi': payload.get('invoice_note_date_shamsi') or payload.get('event_date_shamsi') or '',
            'report_row_count': payload.get('report_row_count') or len(_document_rows_187(payload.get('daily_report_rows') or payload.get('report_rows'))),
            'report_rows': payload.get('daily_report_rows') or payload.get('report_rows') or [],
            'report_images': payload.get('report_images') or image_paths,
            'document_file': payload.get('document_file') or payload.get('document_file_path') or (file_paths[0] if file_paths else ''),
            'note_subject': payload.get('note_subject') or payload.get('subject') or '',
        }
        # Normalize legacy aliases before the custom row/image widgets render;
        # otherwise an editor loaded from ``report_rows`` would show blank rows.
        if subtype == 'گزارش روزانه':
            self.payload['daily_report_rows'] = _document_rows_187(values['report_rows'])
            self.payload['report_row_count'] = parse_int(values['report_row_count'])
            self.payload['report_images'] = _document_paths_187(values['report_images'])
        elif subtype == 'داکیومنت':
            self.payload['document_file'] = values['document_file'] or ''
            self.payload['document_file_path'] = self.payload['document_file']
        elif subtype == 'یادداشت':
            self.payload['note_subject'] = values['note_subject'] or ''
        self._loading = True
        try:
            for key, value in values.items():
                var = getattr(self, 'vars', {}).get(key)
                if var is None:
                    continue
                fd = next((field for field in _special_fields_187(title, subtype) if field.key == key), None)
                if key == 'report_rows':
                    value = json.dumps(_document_rows_187(value), ensure_ascii=False)
                elif key == 'report_images':
                    value = json.dumps(_document_paths_187(value), ensure_ascii=False)
                elif fd is not None and fd.kind in {'money', 'int'}:
                    value = v18._group_money(value or 0)
                var.set('' if value is None else str(value))
        finally:
            self._loading = False
        return
    if not _is_facility_payload_187(title, subtype):
        return
    payload = getattr(self, 'payload', {}) or {}
    # The existing loader handles the shared widgets; these aliases belong to
    # the expanded facility form and are intentionally kept in the payload.
    values = {
        'loan_name': payload.get('loan_name') or str(payload.get('loan_total_amount') or payload.get('principal_amount') or '')[:4],
        'loan_title': payload.get('loan_title') or payload.get('description') or '',
        'branch_name': payload.get('branch_name') or '',
        'contract_number': payload.get('contract_number') or '',
        'borrower_name': payload.get('borrower_name') or '',
        'guarantor_1': payload.get('guarantor_1') or '',
        'guarantor_2': payload.get('guarantor_2') or '',
        'bank_fees': payload.get('bank_fees') or 0,
        'first_due_date_shamsi': payload.get('first_due_date_shamsi') or payload.get('first_due_date') or '',
        'last_paid_date_shamsi': payload.get('last_paid_date_shamsi') or '',
        'paid_installments_count': payload.get('paid_installments_count') or payload.get('paid_installments') or 0,
    }
    try:
        principal = int(payload.get('loan_total_amount') or payload.get('principal_amount') or payload.get('amount') or 0)
        count = int(payload.get('installment_count') or 0)
        rate = float(payload.get('interest_rate') or 0)
        values['installment_amount'] = payload.get('installment_amount') or calculate_loan_installment_187(principal, rate, count)
        values['total_interest'] = payload.get('total_interest') or loan_total_interest_187(principal, values['installment_amount'], count)
        values['remaining_installments'] = max(0, count - int(values['paid_installments_count'] or 0))
        start = _loan_date_value_187(payload.get('loan_start_date') or payload.get('event_date_shamsi'))
        first = _loan_date_value_187(values['first_due_date_shamsi'])
        if not first and start and count > 0:
            first = gregorian_to_shamsi(_add_months(date.fromisoformat(shamsi_to_gregorian(start)), 1))
        values['first_due_date_shamsi'] = first
        end = _loan_date_value_187(payload.get('loan_end_date'))
        if first and count > 0:
            end = gregorian_to_shamsi(_add_months(date.fromisoformat(shamsi_to_gregorian(first)), count - 1))
        values['loan_end_date'] = end
    except Exception:
        values.setdefault('installment_amount', 0)
        values.setdefault('total_interest', 0)
    self._loading = True
    try:
        for key, value in values.items():
            var = getattr(self, 'vars', {}).get(key)
            if var is None:
                continue
            fd = next((f for f in _special_fields_187(title, subtype) if f.key == key), None)
            if fd is not None and fd.kind in {'money', 'int'}:
                var.set(v18._group_money(value or 0))
            else:
                var.set('' if value is None else str(value))
    finally:
        self._loading = False


def _payload_values_187(self, title: str, subtype: str):
    before = dict(getattr(self, 'payload', {}) or {})
    subtype = _canonical_document_subtype_187(subtype)
    payload = _ORIGINAL_PAYLOAD_VALUES_187(self, title, subtype)
    vars_map = getattr(self, 'vars', {}) or {}
    if 'event_date_shamsi' not in vars_map:
        payload['event_date_shamsi'] = before.get('event_date_shamsi') or ''
    if 'amount' not in vars_map:
        amount = parse_int(before.get('amount') or before.get('paid_amount') or 0)
        payload['amount'] = amount
        payload['paid_amount'] = amount
    if title == 'هزینه ساخت' and subtype == 'چک':
        operation_var = vars_map.get('cheque_operation187')
        operation = str(operation_var.get() if operation_var is not None
                         else before.get('cheque_operation187') or CHEQUE_OPERATION_ISSUE_187).strip()
        if operation == CHEQUE_OPERATION_RESOLVE_187:
            def read_value(key, fallback=''):
                variable = vars_map.get(key)
                return variable.get() if variable is not None else before.get(key, fallback)
            selected_id = str(read_value('selected_cheque_id187',
                                         before.get('selected_cheque_id187') or '') or '').strip()
            status = _cheque_resolution_status_code_187(read_value('cheque_resolution_status187', ''))
            registration_label = str(read_value('cheque_resolution_registration187', '') or '').strip()
            registration = v18.REG_BY_FA.get(registration_label, '')
            payload.update(
                cheque_operation187=operation,
                selected_cheque_id187=selected_id,
                cheque_id=selected_id,
                cheque_resolution_status187=str(read_value('cheque_resolution_status187', '') or ''),
                cheque_status=status or str(before.get('cheque_status') or ''),
                cheque_registration_state=registration or str(before.get('cheque_registration_state') or ''),
                cheque_return_disposition187=str(read_value('cheque_resolution_return_disposition187',
                    before.get('cheque_return_disposition187') or CHEQUE_RETURN_DISPOSITION_CHOICES_187[3]) or ''),
                cheque_return_account_holder187=str(read_value('cheque_resolution_account_holder187',
                    before.get('cheque_return_account_holder187') or '') or '').strip(),
                cheque_void_reason187=str(read_value('cheque_resolution_void_reason187',
                    before.get('cheque_void_reason187') or '') or '').strip(),
                payment_state='CHEQUE_RESOLUTION',
                detected_type='EXPENSE', is_cheque=False,
                v18_title=title, v18_subtype=subtype,
                transaction_title=title, transaction_subtype=subtype,
            )
            return payload
    if _is_cheque_clearing_187(title, subtype):
        selected_id = str(vars_map.get('selected_cheque_id187').get()
                          if vars_map.get('selected_cheque_id187') is not None
                          else before.get('selected_cheque_id187') or before.get('cheque_id') or '').strip()
        include_id = (before.get('_original_clearing_cheque_id187'),) if before.get('_editing_cheque_clearing187') else ()
        selected = next((row for row in _registered_cheques_for_clearing_187(include_ids=include_id)
                         if str(row.get('cheque_id')) == selected_id), None)
        if not selected:
            raise ValueError('یک چک ثبت‌شده و صادرشده را از فهرست انتخاب کن.')
        mode = str(vars_map.get('cheque_clearing_mode187').get()
                   if vars_map.get('cheque_clearing_mode187') is not None
                   else before.get('cheque_clearing_mode187') or CHEQUE_CLEARING_MODES_187[0]).strip()
        if mode not in CHEQUE_CLEARING_MODES_187:
            raise ValueError('نحوه پاس‌شدن چک را انتخاب کن.')
        transfer_account = str(vars_map.get('cheque_transfer_account_holder187').get()
                               if vars_map.get('cheque_transfer_account_holder187') is not None
                               else before.get('cheque_transfer_account_holder187') or '').strip()
        transfer_description = str(vars_map.get('cheque_transfer_description187').get()
                                   if vars_map.get('cheque_transfer_description187') is not None
                                   else before.get('cheque_transfer_description187') or '').strip()
        if mode == CHEQUE_CLEARING_MODES_187[1]:
            if not transfer_account and not getattr(self, '_clearing_transfer_account_manual187', False):
                transfer_account = str(selected.get('issuer_name') or selected.get('receiver_name') or '').strip()
            if not transfer_description and not getattr(self, '_clearing_transfer_description_manual187', False):
                transfer_description = str(selected.get('description') or '').strip()
            if not transfer_account:
                raise ValueError('نام صاحب حساب مقصد را وارد کن.')
            if not transfer_description:
                raise ValueError('بابت واریز را وارد کن.')
        status_label = str(vars_map.get('cheque_status').get()
                           if vars_map.get('cheque_status') is not None
                           else before.get('cheque_status') or 'پاس‌شده').strip()
        status_label = v18.CODE_TO_CHEQUE_STATUS.get(status_label.upper(), status_label)
        status = v18.CHEQUE_STATUS_TO_CODE.get(status_label, '')
        if status not in {'ISSUED', 'CASHED'}:
            raise ValueError('وضعیت چک باید صادرشده یا پاس‌شده باشد.')
        payload.update(
            selected_cheque_id187=selected_id,
            selected_cheque_manual187=bool(getattr(self, '_clearing_cheque_manual187', False)
                                           or before.get('selected_cheque_manual187')),
            _editing_cheque_clearing187=bool(getattr(self, '_editing_cheque_clearing187', False)
                                              or before.get('_editing_cheque_clearing187')),
            _original_clearing_cheque_id187=str(getattr(self, '_original_clearing_cheque_id187', '')
                                                  or before.get('_original_clearing_cheque_id187') or ''),
            _original_clearing_mode187=str(getattr(self, '_original_clearing_mode187', '')
                                            or before.get('_original_clearing_mode187') or ''),
            cheque_id=selected_id,
            cheque_clearing_mode187=mode,
            cheque_transfer_account_holder187=transfer_account,
            cheque_transfer_description187=transfer_description,
            cheque_status=status,
            payment_state='CHEQUE_CLEARING',
            detected_type='EXPENSE',
            is_cheque=False,
            payment_method='BANK_TRANSFER' if mode == CHEQUE_CLEARING_MODES_187[1] else 'UNKNOWN',
        )
        if parse_int(payload.get('amount') or 0) <= 0:
            payload['amount'] = parse_int(selected.get('amount') or 0)
        payload['paid_amount'] = 0
        payload['final_amount'] = 0
        payload['invoice_amount'] = 0
        payload['event_date_shamsi'] = str(payload.get('event_date_shamsi') or
                                           selected.get('due_date_shamsi') or
                                           selected.get('issue_date_shamsi') or '')
        if not str(payload.get('description') or '').strip():
            payload['description'] = str(selected.get('description') or '')
        for key in ('cost_group', 'contract_id', 'construction_stage', 'plan_ref', 'main_phase', 'sub_phase'):
            payload.pop(key, None)
        payload['v18_title'] = title
        payload['v18_subtype'] = subtype
        payload['transaction_title'] = title
        payload['transaction_subtype'] = subtype
        return payload
    if title == MANAGER_TITLE:
        return normalize_manager_salary(payload)
    if title == LAND_TITLE:
        payload[LAND_MODE_KEY] = (vars_map[LAND_MODE_KEY].get() if LAND_MODE_KEY in vars_map
                                  else land_payment_mode(before))
        subtype = land_payment_subtype(payload)
        active = set(LAND_PARTS) if subtype == LAND_MIXED else {
            {'نقدی': LAND_PARTS[0], 'چک': LAND_PARTS[1], 'معاوضه': LAND_PARTS[2]}.get(subtype)}
        for key in LAND_PARTS:
            payload[key] = parse_int(payload.get(key) or 0) if key in active else 0
        if subtype == 'نقدی':
            payload['land_cash_amount'] = parse_int(payload.get('amount') or 0)
            payload['land_barter_description'] = ''
        payload['amount'] = sum(payload[key] for key in LAND_PARTS)
        payload['paid_amount'] = payload['amount']
        payload.update(detected_type='EXPENSE', expense_category='LAND_PURCHASE',
                       construction_stage=LAND_TITLE, main_phase=LAND_TITLE,
                       manager_fee_eligible=False, cost_group='', contract_id='',
                       plan_ref=str(before.get('plan_ref') or ''),
                       is_cheque=False)
        payload = _carry_debt_187(getattr(self, 'pid', ''), payload)
        if payload.get('payment_state') == 'PAID':
            if parse_int(payload.get('total_debt') or 0) <= 0 and not payload.get('_total_debt_manual187'):
                payload['total_debt'] = payload['amount']
            payload['remaining_debt'] = 0
        payload['final_amount'] = parse_int(payload.get('total_debt') or payload['amount'])
        return normalize_land_record(payload)
    if _is_nonfinancial_payload_187(title, subtype):
        stage_var = vars_map.get('construction_stage')
        if stage_var is not None:
            payload['construction_stage'] = _phase_name_187(stage_var.get())
        payload['v18_title'] = 'یادداشت'
        payload['v18_subtype'] = subtype
        payload['transaction_title'] = 'یادداشت'
        payload['transaction_subtype'] = subtype
        payload['document_type'] = _document_code_187(subtype)
        payload['detected_type'] = 'DOCUMENT' if subtype == 'داکیومنت' else 'INFO'
        payload['amount'] = 0
        payload['paid_amount'] = 0
        # Specialized dates are Persian DateField values. Keep the common date
        # synchronized so calendar and legacy document listings agree.
        date_key = {
            'تقویم کارگاهی': 'calendar_date_shamsi',
            'گزارش روزانه': 'report_date_shamsi',
            'یادآوری': 'reminder_date_shamsi',
            'فاکتور': 'invoice_note_date_shamsi',
        }.get(subtype)
        if date_key:
            specialized = str(payload.get(date_key) or before.get(date_key) or '').strip()
            if specialized:
                payload[date_key] = normalize_shamsi(specialized)
                payload['event_date_shamsi'] = payload[date_key]
        if subtype == 'گزارش روزانه':
            requested_count = parse_int(payload.get('report_row_count') or before.get('report_row_count'))
            rows = _document_rows_187(payload.get('report_rows') or before.get('daily_report_rows'))
            payload['daily_report_rows'] = rows
            payload['report_row_count'] = len(rows) if rows else requested_count
            payload['report_images'] = _document_paths_187(payload.get('report_images') or before.get('report_images'))
        if subtype == 'داکیومنت':
            paths = _document_paths_187(payload.get('document_file') or before.get('document_file'))
            payload['document_file'] = paths[0] if paths else ''
            payload['document_file_path'] = payload['document_file']
        if subtype == 'یادداشت':
            payload['note_subject'] = str(payload.get('note_subject') or before.get('note_subject') or '').strip()
        if subtype == 'تقویم کارگاهی':
            payload['calendar_keyword'] = 'تقویم'
        return payload
    if not _is_facility_payload_187(title, subtype):
        return payload
    for key in (
        'loan_bank', 'branch_name', 'loan_name', 'loan_title', 'contract_number',
        'loan_start_date', 'loan_total_amount', 'installment_count',
        'interest_rate', 'installment_amount', 'total_interest', 'bank_fees',
        'borrower_name', 'guarantor_1', 'guarantor_2', 'guarantor_3',
        'first_due_date_shamsi', 'loan_end_date', 'last_paid_date_shamsi',
        'paid_installments_count', 'remaining_installments',
    ):
        if key not in vars_map and key in before:
            payload[key] = before[key]
    principal = parse_int(payload.get('loan_total_amount') or payload.get('principal_amount') or payload.get('amount') or 0)
    count = parse_int(payload.get('installment_count') or 0)
    try:
        rate = float(payload.get('interest_rate') or 0)
    except (TypeError, ValueError):
        rate = 0.0
    installment = parse_int(payload.get('installment_amount') or 0)
    if installment <= 0 and principal > 0 and count > 0:
        installment = calculate_loan_installment_187(principal, rate, count)
    start_date = _loan_date_value_187(payload.get('loan_start_date') or payload.get('event_date_shamsi'))
    payload['principal_amount'] = principal
    payload['loan_total_amount'] = principal
    payload['loan_start_date'] = start_date
    payload['event_date_shamsi'] = start_date or payload.get('event_date_shamsi') or ''
    payload['net_received_amount'] = parse_int(payload.get('amount') or 0)
    payload['bank_fees'] = _loan_fees_187(principal, payload['net_received_amount'])
    payload['lender_name'] = str(payload.get('loan_bank') or '').strip()
    payload['loan_title'] = str(payload.get('loan_title') or payload.get('description') or '').strip()
    payload['description'] = payload['loan_title'] or 'ورودی تسهیلات'
    payload['installment_amount'] = installment
    payload['total_interest'] = loan_total_interest_187(principal, installment, count)
    payload['paid_installments_count'] = parse_int(payload.get('paid_installments_count') or payload.get('paid_installments') or 0)
    payload['remaining_installments'] = max(0, count - payload['paid_installments_count'])
    payload['first_due_date_shamsi'] = _loan_date_value_187(payload.get('first_due_date_shamsi'))
    if not payload['first_due_date_shamsi']:
        start = _loan_date_value_187(payload.get('loan_start_date') or payload.get('event_date_shamsi'))
        if start and count > 0:
            payload['first_due_date_shamsi'] = gregorian_to_shamsi(
                _add_months(date.fromisoformat(shamsi_to_gregorian(start)), 1))
    if payload['first_due_date_shamsi'] and count > 0:
        payload['loan_end_date'] = gregorian_to_shamsi(
            _add_months(date.fromisoformat(shamsi_to_gregorian(payload['first_due_date_shamsi'])), count - 1))
    return payload


def _wizard_payload_values_187(self, title: str, subtype: str):
    payload = _ORIGINAL_WIZARD_PAYLOAD_VALUES_187(self, title, subtype)
    if (title in (LAND_TITLE, MANAGER_TITLE) or _is_facility_payload_187(title, subtype)
            or _is_nonfinancial_payload_187(title, subtype)
            or _is_cheque_clearing_187(title, subtype)
            or _is_cheque_resolution_187(title, subtype, getattr(self, 'payload', {}))):
        payload = _payload_values_187(self, title, subtype)
    _with_loan_id_187(payload, title, subtype)
    return _carry_debt_187(self.pid, payload)


def _carry_debt_187(pid, payload):
    payload = dict(payload)
    state = str(payload.get('payment_state') or '')
    state = v18.STATE_TO_CODE.get(state, state)
    if state != 'PARTIAL':
        payload.pop('_debt_source_pending_id187', None)
        return payload
    def debt_title(record):
        if record.get('v18_title') == LAND_TITLE or record.get('transaction_title') == LAND_TITLE:
            record = normalize_land_record(record)
        return v18._title_type_from_payload(record)
    match = previous_debt(DB, pid, payload, _record_date_order_187, debt_title)
    if match:
        _key, source, previous = match
        if not payload.get('_total_debt_manual187'):
            payload['total_debt'] = parse_int(previous['remaining_debt'])
        payload['_debt_source_pending_id187'] = source
    else:
        payload.pop('_debt_source_pending_id187', None)
    total = parse_int(payload.get('total_debt') or 0)
    payload['remaining_debt'] = max(0, total - parse_int(payload.get('amount') or 0))
    return payload


def _sync_financial_fields_187(form, edited_key=None):
    if getattr(form, '_loading', False) or getattr(form, '_debt_syncing187', False):
        return
    form._debt_syncing187 = True
    try:
        payload = dict(form.payload)
        payload.update(v18_title=form.title_var.get(), v18_subtype=form.subtype_var.get())
        if form.vars.get(LAND_MODE_KEY) is not None:
            payload[LAND_MODE_KEY] = form.vars[LAND_MODE_KEY].get()
        for key in ('payment_state', 'description', 'event_date_shamsi', 'amount', 'total_debt', *LAND_PARTS):
            var = form.vars.get(key)
            if var is not None:
                payload[key] = var.get()
        about = getattr(form, 'about_text187', None)
        if about is not None and about.winfo_exists():
            payload['description'] = about.get('1.0', 'end-1c').strip()
        if form.title_var.get() == LAND_TITLE:
            subtype = land_payment_subtype(payload)
            form.payload[LAND_MODE_KEY] = land_payment_mode(payload)
            active = set(LAND_PARTS) if subtype == LAND_MIXED else {
                {'نقدی': LAND_PARTS[0], 'چک': LAND_PARTS[1], 'معاوضه': LAND_PARTS[2]}.get(subtype)}
            if subtype == 'نقدی':
                payload['land_cash_amount'] = parse_int(payload.get('amount') or 0)
            elif not any(key in form.payload for key in LAND_PARTS):
                # AI may extract a transaction amount without a split. Keep it
                # in the selected component instead of replacing it with zero.
                first = next((key for key in LAND_PARTS if key in active), LAND_PARTS[0])
                payload[first] = parse_int(payload.get('amount') or 0)
            for key in LAND_PARTS:
                if key not in active:
                    payload[key] = 0
            payload['amount'] = sum(parse_int(payload.get(key) or 0) for key in LAND_PARTS if key in active)
        payload = _carry_debt_187(form.pid, payload)
        state = v18.STATE_TO_CODE.get(str(payload.get('payment_state')), payload.get('payment_state'))
        debt_value = (payload.get('total_debt') if 'total_debt' in payload
                      else payload.get('invoice_amount') or payload.get('final_amount') or 0)
        total = parse_int(debt_value)
        paid = parse_int(payload.get('amount') or 0)
        if (state == 'PAID' and not payload.get('_total_debt_manual187')
                and (total <= 0 or getattr(form, '_settled_debt_auto187', False))):
            # Fill an absent debt, while retaining a real invoice/AI price.
            # A mismatch with that price is a warning at explicit approval.
            total = paid
            form._settled_debt_auto187 = True
        elif state != 'PAID':
            form._settled_debt_auto187 = False
        # Tk contains grouped strings; the display formatter accepts numeric
        # values. Passing "4,000" straight back to it used to display zero.
        payload['total_debt'] = total
        payload['remaining_debt'] = 0 if state == 'PAID' else max(0, total - paid) if state == 'PARTIAL' else total
        form._loading = True
        try:
            for key in ('total_debt', 'remaining_debt'):
                form.payload[key] = parse_int(payload.get(key) or 0)
                var = form.vars.get(key)
                if var is not None and key != edited_key and parse_int(var.get()) != form.payload[key]:
                    var.set(v18._group_money(payload.get(key) or 0))
            if form.title_var.get() == LAND_TITLE:
                form.payload['amount'] = paid
                form.payload['paid_amount'] = paid
                if (form.vars.get('amount') is not None and edited_key != 'amount'
                        and parse_int(form.vars['amount'].get()) != paid):
                    form.vars['amount'].set(v18._group_money(paid))
                for key in LAND_PARTS:
                    form.payload[key] = parse_int(payload.get(key) or 0)
                    var = form.vars.get(key)
                    if var is not None and key != edited_key and parse_int(var.get()) != form.payload[key]:
                        var.set(v18._group_money(form.payload[key]))
                    widget = form.widgets.get(key)
                    if widget is not None:
                        widget.configure(state='normal' if key in active and subtype != 'نقدی' else 'disabled')
                barter = form.widgets.get('land_barter_description')
                if barter is not None:
                    barter.configure(state='normal' if subtype in (LAND_MIXED, 'معاوضه') else 'disabled')
                for key in ('issuer_name', 'issuer_bank', 'cheque_serial', 'cheque_type', 'due_date_shamsi'):
                    widget = form.widgets.get(key)
                    if widget is not None:
                        widget.master.grid() if subtype in (LAND_MIXED, 'چک') else widget.master.grid_remove()
                method = form.widgets.get('payment_method')
                if method is not None:
                    method.master.grid() if subtype in (LAND_MIXED, 'نقدی') else method.master.grid_remove()
            debt = form.widgets.get('total_debt')
            if debt is not None:
                debt.configure(state='normal')
            if payload.get('_debt_source_pending_id187'):
                form.payload['_debt_source_pending_id187'] = payload['_debt_source_pending_id187']
            else:
                form.payload.pop('_debt_source_pending_id187', None)
        finally:
            form._loading = False
    finally:
        form._debt_syncing187 = False


def _install_financial_sync_187(form):
    for key in ('payment_state', 'description', 'event_date_shamsi', 'amount', 'total_debt', LAND_MODE_KEY, *LAND_PARTS):
        var = form.vars.get(key)
        if var is not None and not getattr(var, '_debt_bound187', False):
            var._debt_bound187 = True
            var.trace_add('write', lambda *_args, target=form, source=key: _financial_change_187(target, source))
    about = getattr(form, 'about_text187', None)
    if about is not None and about.winfo_exists() and not getattr(about, '_debt_bound187', False):
        about._debt_bound187 = True
        about.bind('<<Modified>>', lambda _event: _sync_financial_fields_187(form), add='+')
    _sync_financial_fields_187(form)


def _financial_change_187(form, edited_key=None):
    widget = form.widgets.get(edited_key)
    if (getattr(form, '_loading', False) or getattr(form, '_debt_syncing187', False)
            or getattr(widget, '_numeric_formatting187', False)):
        return
    if edited_key == 'total_debt':
        form.payload['_total_debt_manual187'] = True
        form._settled_debt_auto187 = False
    _sync_financial_fields_187(form, edited_key)
    if not getattr(form, '_loading', False):
        _sync_transaction_fields_187(form)


def _load_entry_values_187(self, title, subtype):
    _load_values_187(self, title, subtype)
    _install_financial_sync_187(self)


def _sync_document_event_date_187(form, key: str) -> None:
    value = str(getattr(form, 'vars', {}).get(key).get() if getattr(form, 'vars', {}).get(key) else '').strip()
    if not value:
        return
    try:
        value = normalize_shamsi(value)
    except Exception:
        return
    form.payload[key] = value
    form.payload['event_date_shamsi'] = value


_PERSIAN_COUNT_WORDS_187 = {
    0: 'صفر', 1: 'یک', 2: 'دو', 3: 'سه', 4: 'چهار', 5: 'پنج',
    6: 'شش', 7: 'هفت', 8: 'هشت', 9: 'نه', 10: 'ده',
}


def _daily_report_summary_187(count: int) -> str:
    count = max(0, int(count or 0))
    display = _PERSIAN_COUNT_WORDS_187.get(count, fa(count))
    return f'تعداد {display} ردیف گزارش روزانه ثبت شد'


def _wizard_skip_to_confirmation_187(self):
    """Skip optional intermediate pages and show the final confirmation page."""
    try:
        self._capture()
    except Exception:
        pass
    if getattr(self, 'pages', None):
        self.page_index = len(self.pages) - 1
        self._show_page()


def _replace_wizard_button_with_pill_187(window, button, text, command, style):
    """Replace legacy tall tk buttons with the shared short ttk pill."""
    try:
        pack = dict(button.pack_info())
        parent = button.master
        button.destroy()
        pill = ttk.Button(parent, text=text, command=command, style=style)
        pill.pack(**pack)
        return pill
    except (AttributeError, tk.TclError):
        return button


def _wizard_build_shell_187(self):
    """Keep inherited behavior but use compact shared pill actions."""
    # Caption helpers flush Tk's idle work. Withdraw before they can map the
    # unfinished wizard at the default position and size.
    hide_for_fade(self)
    _ORIGINAL_WIZARD_BUILD_SHELL_187(self)
    try:
        self.resizable(True, True)
        keep_above_parent(self, self.master)
        apply_dark_caption(self)
        _enable_caption_controls_187(self)
        self.after_idle(lambda target=self: _enable_caption_controls_187(target))
    except (AttributeError, tk.TclError):
        pass
    self.next_b = _replace_wizard_button_with_pill_187(
        self, getattr(self, 'next_b', None), 'بعدی', self.next, 'Primary.TButton')
    self.prev_b = _replace_wizard_button_with_pill_187(
        self, getattr(self, 'prev_b', None), 'قبلی', self.prev, 'Toolbar.TButton')
    for widget in tuple(self.winfo_children()):
        for child in tuple(widget.winfo_children()):
            try:
                if str(child.cget('text') or '') == 'رد کردن مرحله':
                    _replace_wizard_button_with_pill_187(
                        self, child, 'رد کردن تمام مراحل',
                        lambda target=self: _wizard_skip_to_confirmation_187(target),
                        'Toolbar.TButton')
                elif str(child.cget('text') or '') == 'فرم کامل':
                    _replace_wizard_button_with_pill_187(
                        self, child, 'فرم کامل', self._open_full, 'Toolbar.TButton')
            except (AttributeError, tk.TclError):
                continue
    _apply_wizard_font_187(self)


def _wizard_init_187(self, parent, row, rich, on_done, on_full):
    if (row.get('payload') or {}).get('v18_subtype') == CHEQUE_CLEARING_SUBTYPE_187:
        row = dict(row, payload=dict(row['payload'], v18_subtype='چک',
                   cheque_operation187=CHEQUE_OPERATION_RESOLVE_187))
    _ORIGINAL_WIZARD_INIT_187(self, parent, row, rich, on_done, on_full)
    _install_form_keyboard_navigation_187(self)
    original = row.get('payload') or {}
    if 'description' in original:
        self.payload['description'] = original['description']
    self.protocol('WM_DELETE_WINDOW', self._cancel_187)
    _apply_wizard_font_187(self)
    # Use the inherited 18.2 wizard's final size explicitly: Tk can report a
    # 1px actual/WM size for a window that has never been mapped.
    self.update_idletasks()
    center_toplevel_on_screen(self, width=780, height=560)
    fade_in(self)
    try:
        self.after_idle(lambda target=self: _apply_wizard_font_187(target))
    except tk.TclError:
        pass


def _wizard_cancel_187(self):
    """Closing the wizard discards its in-memory draft, without opening a record."""
    self.grab_release()
    self.destroy()


def _wizard_open_full_187(self):
    if getattr(self, '_closing_to_full', False):
        return
    try:
        self._capture()
    except Exception as exc:
        return messagebox.showerror('فرم کامل', str(exc), parent=self)
    drafts = getattr(self.master, '_wizard_full_drafts187', None)
    if drafts is None:
        drafts = self.master._wizard_full_drafts187 = {}
    drafts[str(self.pid)] = {**self.row, 'payload': deepcopy(self.payload)}
    self._closing_to_full = True
    self.grab_release()
    self.destroy()
    self.on_full()


_ORIGINAL_WIZARD_TITLE_CHANGED_187 = v182.TransactionWizard182._title_changed
_ORIGINAL_WIZARD_SHOW_PAGE_187 = v182.TransactionWizard182._show_page


def _sync_transaction_fields_187(form):
    """Apply transaction-kind visibility and editability to the current form."""
    construction = form.title_var.get() == 'هزینه ساخت'
    row = getattr(form, 'cost_group_row', None)
    if row is not None:
        row.grid() if construction else row.grid_remove()
    else:
        category = form.widgets.get('cost_group')
        if category is not None:
            category.master.grid() if construction else category.master.grid_remove()
        contract = form.widgets.get('contract_id')
        if contract is not None and not construction:
            contract.master.grid_remove()
    amount = form.widgets.get('amount')
    if amount is not None:
        computed = form.title_var.get() == 'یادداشت' or (
            form.title_var.get() == LAND_TITLE and land_payment_subtype(form.payload) != 'نقدی')
        amount.configure(state='disabled' if computed else 'normal')
    subtype = form.widgets.get('v18_subtype')
    if subtype is not None:
        subtype.configure(state='disabled' if form.title_var.get() == LAND_TITLE else 'readonly')
        if form.title_var.get() == LAND_TITLE:
            form.subtype_var.set(LAND_TITLE)
            form.payload.update(v18_subtype=LAND_TITLE, construction_stage=LAND_TITLE)


def _upload_receipt_from_form_187(form):
    """Route the wizard/editor's first-card action through the shared receipt UI."""
    pending_id = str(getattr(form, 'pid', '') or '')
    if not pending_id:
        return messagebox.showinfo('بارگذاری رسید/فاکتور', 'ابتدا یک تراکنش را انتخاب کنید.', parent=form)
    controller = getattr(form, '_receipt_controller187', None)
    owner = getattr(form, 'master', None)
    while controller is None and owner is not None:
        controller = getattr(owner, '_receipt_preview187', None)
        owner = getattr(owner, 'master', None)
    controller_pid = str(getattr(getattr(controller, 'form', None), 'pid', '') or '')
    if controller is not None and controller_pid == pending_id:
        controller.upload()
    else:
        path = filedialog.askopenfilename(
            parent=form, title='بارگذاری رسید یا فایل',
            filetypes=[
                ('همهٔ فرمت‌ها', '*.*'),
                ('تصاویر', '*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp'),
                ('PDF', '*.pdf'), ('CAD', '*.dwg *.dxf'),
                ('اسناد و صفحه‌گسترده‌ها', '*.doc *.docx *.xls *.xlsx *.txt *.rtf *.odt *.ods'),
            ],
        )
        if not path:
            return
        try:
            from receipt_evidence187 import is_image_file, upload_file, upload_image
            caption = str(getattr(form, 'payload', {}).get('receipt_caption') or '')
            if is_image_file(path):
                upload_image(DB, pending_id, path, caption)
            else:
                attachment = upload_file(DB, pending_id, path)
                try:
                    form.msg.set(f"فایل «{attachment['file_name']}» به رکورد پیوست شد.")
                except (AttributeError, tk.TclError):
                    pass
        except Exception as exc:
            return messagebox.showerror('بارگذاری رسید/فاکتور', str(exc), parent=form)

    fresh = DB.get_pending_item(pending_id)
    if fresh:
        saved = dict(fresh.get('payload') or {})
        payload = getattr(form, 'payload', None)
        if isinstance(payload, dict):
            for key in ('receipt_image_path', 'receipt_image_deleted187', 'receipt_caption'):
                payload[key] = saved.get(key, '' if key != 'receipt_image_deleted187' else False)
        row = getattr(form, 'row', None)
        if isinstance(row, dict):
            current = dict(row.get('payload') or {})
            for key in ('receipt_image_path', 'receipt_image_deleted187', 'receipt_caption'):
                current[key] = saved.get(key, '' if key != 'receipt_image_deleted187' else False)
            row['payload'] = current
            row['receipt_image_path'] = saved.get('receipt_image_path') or ''
        if controller is None:
            refresh = getattr(getattr(form, 'master', None), 'refresh', None)
            if callable(refresh):
                refresh()
    return


def _install_wizard_receipt_upload_187(form):
    page_index = getattr(form, 'page_index', None)
    resolution_receipt_page = (
        page_index == 2 and _is_cheque_resolution_187(
            getattr(getattr(form, 'title_var', None), 'get', lambda: '')(),
            getattr(getattr(form, 'subtype_var', None), 'get', lambda: '')(),
            getattr(form, 'payload', {}),
        )
    )
    if page_index != 0 and not resolution_receipt_page:
        return
    try:
        if page_index == 0:
            title_widget = getattr(form, 'widgets', {}).get('v18_title')
            if title_widget is None:
                return
            content = title_widget.master.master
        else:
            shell = form.host.winfo_children()[0]
            canvas = next(widget for widget in shell.winfo_children() if isinstance(widget, tk.Canvas))
            body = canvas.winfo_children()[0]
            content = body.winfo_children()[0]
        rows = [int(widget.grid_info().get('row') or 0) for widget in content.grid_slaves()]
        button = ttk.Button(
            content, text='بارگذاری رسید/فایل', style='Toolbar.TButton',
            command=lambda target=form: _upload_receipt_from_form_187(target),
        )
        button.grid(row=max(rows, default=-1) + 1, column=0, columnspan=2,
                    sticky='e', padx=7, pady=(7, 2))
        form._receipt_upload_button187 = button
    except (AttributeError, tk.TclError):
        return


_widget_host = v182._widget_host


def _wizard_show_page_187(self, load=False):
    if self.page_index == 0:
        # Initial open and title/subtype rebuilds use the inherited page list;
        # next() alone used to add this field too late for window one.
        first = [field for field in self.pages[0] if field.key not in {
            'construction_stage', LAND_MODE_KEY, 'cheque_operation187', 'selected_cheque_id187',
        }]
        if _is_cheque_clearing_187(self.title_var.get(), self.subtype_var.get()):
            first = [field for field in first if field.key not in {
                'cost_group', 'contract_id', 'payment_method',
            }]
        if self.title_var.get() == 'یادداشت':
            first.append(_note_phase_field_187())
        elif self.title_var.get() == LAND_TITLE:
            self.payload = normalize_land_record(self.payload)
            first.extend([v18.FieldDef('construction_stage', 'فاز ساخت', 'combo', (LAND_TITLE,), readonly=True),
                          v18.FieldDef(LAND_MODE_KEY, 'روش پرداخت', 'combo', LAND_MODES)])
            self.pages = [first] + _wizard_steps_187(LAND_TITLE, land_payment_subtype(self.payload)) + [[]]
        elif _is_facility_payload_187(self.title_var.get(), self.subtype_var.get()):
            self.pages = _facility_wizard_pages_187(first)
            first = self.pages[0]  # with the bank and borrower fields; pages[0] is set from `first` below
        if self.title_var.get() == 'هزینه ساخت' and self.subtype_var.get() == 'چک':
            if not str(self.payload.get('cost_group') or '').strip():
                self.payload['cost_group'] = CHEQUE_DEFAULT_COST_GROUP_187
            first.extend([
                v18.FieldDef('cheque_operation187', 'عملیات', 'combo', CHEQUE_OPERATION_CHOICES_187),
                v18.FieldDef('selected_cheque_id187', 'انتخاب چک', 'cheque_picker'),
            ])
        self.pages[0] = first
    result = _ORIGINAL_WIZARD_SHOW_PAGE_187(self, load=load)
    if (self.page_index == 0 and
            _is_facility_payload_187(self.title_var.get(), self.subtype_var.get())):
        for key in ('event_date_shamsi', 'amount', 'v18_title', 'v18_subtype'):
            host = _widget_host(self.widgets.get(key))
            try:
                if host is not None:
                    host.grid_remove()
            except (AttributeError, tk.TclError):
                pass
        for index, key in enumerate(('loan_bank', 'branch_name', 'borrower_name',
                                     'guarantor_1', 'guarantor_2')):
            host = _widget_host(self.widgets.get(key))
            try:
                if host is not None:
                    host.grid_configure(row=index // 2, column=1 - index % 2, sticky='nsew')
            except (AttributeError, tk.TclError):
                pass
    elif (_is_facility_payload_187(self.title_var.get(), self.subtype_var.get())
          and self.page_index > 0):
        for index, field in enumerate(self.pages[self.page_index]):
            host = _widget_host(self.widgets.get(field.key))
            try:
                if host is not None:
                    host.grid_configure(row=index // 2, column=1 - index % 2, sticky='nsew')
            except (AttributeError, tk.TclError):
                pass
    if self.page_index == 0 and self.title_var.get() == 'هزینه ساخت' and self.subtype_var.get() == 'چک':
        operation = self.vars.get('cheque_operation187')
        picker = self.widgets.get('selected_cheque_id187')
        if operation is not None:
            self._loading = True
            try:
                operation.set(str(self.payload.get('cheque_operation187') or CHEQUE_OPERATION_ISSUE_187))
            finally:
                self._loading = False
            operation_widget = self.widgets.get('cheque_operation187')
            category_widget = self.widgets.get('cost_group')
            contract_widget = self.widgets.get('contract_id')
            if category_widget is not None:
                category_widget.master.grid_configure(row=2, column=1, sticky='nsew')
            if operation_widget is not None:
                operation_widget.master.grid_configure(row=2, column=0, sticky='nsew')
            if contract_widget is not None:
                contract_widget.master.grid_configure(row=3, column=1, sticky='nsew')
            if picker is not None:
                picker_box = picker.master.master
                picker_box.grid_configure(row=4, column=0, columnspan=2, sticky='nsew')
                if operation.get() == CHEQUE_OPERATION_RESOLVE_187:
                    picker_box.grid()
                else:
                    picker_box.grid_remove()
                _populate_clearing_cheque_picker_187(self)
        if operation is not None and getattr(self, '_cheque_operation_trace187', None) is not operation:
            self._cheque_operation_trace187 = operation
            operation.trace_add('write', lambda *_args, target=self: _sync_cheque_operation_visibility_187(target))
        _sync_cheque_operation_visibility_187(self)
        category = self.vars.get('cost_group')
        if category is not None:
            # «انتخاب قرارداد» follows the category here too, as for a cash cost.
            if getattr(self, '_cheque_category_trace187', None) is not category:
                self._cheque_category_trace187 = category
                category.trace_add('write', lambda *_args, target=self: _sync_contract_selector_visibility_187(target))
            _sync_contract_selector_visibility_187(self)
    if self.page_index == 2 and _is_cheque_resolution_187(
            self.title_var.get(), self.subtype_var.get(), getattr(self, 'payload', {})):
        _sync_cheque_resolution_optional_fields_187(self)
    if (self.page_index > 0
            and _is_cheque_clearing_187(self.title_var.get(), self.subtype_var.get())):
        picker = self.widgets.get('selected_cheque_id187')
        mode = self.widgets.get('cheque_clearing_mode187')
        status = self.widgets.get('cheque_status')
        account = self.widgets.get('cheque_transfer_account_holder187')
        description = self.widgets.get('cheque_transfer_description187')
        review = self.widgets.get('cheque_clearing_review187')
        if picker is not None:
            picker.master.master.grid_configure(row=0, column=0, columnspan=2, sticky='nsew')
        if mode is not None:
            mode.master.grid_configure(row=1, column=1, sticky='nsew')
        if status is not None:
            status.master.grid_configure(row=1, column=0, sticky='nsew')
        if account is not None:
            account.master.grid_configure(row=2, column=1, sticky='nsew')
        if description is not None:
            description.master.grid_configure(row=2, column=0, sticky='nsew')
        if review is not None:
            review.grid_configure(row=0, column=0, columnspan=2, sticky='nsew')
        self.next_b.configure(text='تأیید و ثبت' if self.page_index == len(self.pages) - 1 else 'بعدی')
        _bind_clearing_mode_187(self)
        _sync_clearing_transfer_visibility_187(self)
        review_var = getattr(self, '_clearing_review_var187', None)
        if review_var is not None:
            review_var.set(_clearing_review_text_187(self))
    _install_cheque_number_label_187(self)
    _install_wizard_receipt_upload_187(self)
    stage_var = self.vars.get('construction_stage')
    if self.page_index == 0 and self.title_var.get() == 'یادداشت' and stage_var is not None:
        self._loading = True
        try:
            stage_var.set(_phase_display_187(self, self.payload.get('construction_stage')))
        finally:
            self._loading = False
    if self.page_index == 0 and self.title_var.get() == LAND_TITLE:
        self._loading = True
        try:
            self.vars['construction_stage'].set(LAND_TITLE)
            self.vars[LAND_MODE_KEY].set(land_payment_mode(self.payload))
        finally:
            self._loading = False
    _sync_transaction_fields_187(self)
    _install_financial_sync_187(self)
    _right_align_form_187(self)
    return result


def _wizard_title_changed_187(self, title):
    # Preserve entered values before the page's controls are rebuilt.
    previous_title = self.payload.get('v18_title')
    self._capture()
    if (title == LAND_TITLE) != (previous_title == LAND_TITLE):
        self.payload['plan_ref'] = ''
    if title == LAND_TITLE and previous_title != LAND_TITLE:
        self.payload[LAND_MODE_KEY] = 'همه موارد'
    _ORIGINAL_WIZARD_TITLE_CHANGED_187(self, title)
    self.payload['v18_title'] = title
    self.payload['v18_subtype'] = self.subtype_var.get()
    self.page_index = 0
    self._rebuild_pages()


def _wizard_sub_changed_187(self, subtype):
    # The inherited 18.2 callback only changed a variable, leaving the old
    # first page visible until Next/Back. Rebuild immediately after capturing.
    self._capture()
    self.subtype_var.set(subtype)
    self.payload['v18_subtype'] = subtype
    self.page_index = 0
    self._rebuild_pages()


def _wizard_capture_187(self):
    """Capture page one during a transient specialized-page rebuild."""
    if getattr(self, 'page_index', 0) != 0:
        return _ORIGINAL_WIZARD_CAPTURE_187(self)
    vars_map = getattr(self, 'vars', {}) or {}
    payload = getattr(self, 'payload', {}) or {}

    def read(key: str, fallback=''):
        variable = vars_map.get(key)
        if variable is None:
            return fallback
        try:
            return variable.get()
        except (AttributeError, tk.TclError):
            return fallback

    title_var = getattr(self, 'title_var', None)
    subtype_var = getattr(self, 'subtype_var', None)
    current_title = str(title_var.get() if title_var is not None else '').strip()
    current_subtype = str(subtype_var.get() if subtype_var is not None else '').strip()
    title = str(read('v18_title', current_title or payload.get('v18_title') or '') or '').strip()
    subtype = str(read('v18_subtype', current_subtype or payload.get('v18_subtype') or '') or '').strip()
    event_date = str(read('event_date_shamsi', payload.get('event_date_shamsi') or '') or '').strip()
    amount = read('amount', payload.get('amount') or 0)
    self.title_var.set(title)
    self.subtype_var.set(subtype)
    payload['event_date_shamsi'] = event_date
    payload['amount'] = parse_int(amount)
    payload['paid_amount'] = payload['amount']
    payload['v18_title'] = title
    payload['v18_subtype'] = subtype
    if title == LAND_TITLE:
        payload[LAND_MODE_KEY] = read(LAND_MODE_KEY, land_payment_mode(payload))
        payload.update(normalize_land_record(payload))
    if 'construction_stage' in vars_map:
        payload['construction_stage'] = LAND_TITLE if title == LAND_TITLE else _phase_name_187(read(
            'construction_stage', payload.get('construction_stage') or '',
        ))
    if 'cost_group' in vars_map:
        payload['cost_group'] = str(read('cost_group', payload.get('cost_group') or '') or '').strip()
    if 'contract_id' in vars_map:
        payload['contract_id'] = str(read('contract_id', payload.get('contract_id') or '') or '').split('|', 1)[0].strip()
    if title == 'هزینه ساخت' and subtype == 'چک':
        operation = str(read('cheque_operation187', payload.get('cheque_operation187') or CHEQUE_OPERATION_ISSUE_187) or '').strip()
        payload['cheque_operation187'] = operation
        selected_id = str(read('selected_cheque_id187', payload.get('selected_cheque_id187') or '') or '').strip()
        if selected_id:
            payload['selected_cheque_id187'] = selected_id
            payload['selected_cheque_manual187'] = bool(
                getattr(self, '_clearing_cheque_manual187', False)
                or payload.get('selected_cheque_manual187'))
    if _is_facility_payload_187(title, subtype):
        for key in ('loan_bank', 'branch_name', 'borrower_name', 'guarantor_1', 'guarantor_2'):
            payload[key] = str(read(key, payload.get(key) or '') or '').strip()


def _wizard_prev_187(self):
    """Navigate back from every specialized page, including document page two."""
    try:
        self._capture()
    except Exception:
        # A partially completed attachment or optional field must not trap the
        # user on page two; values that can be captured remain in the payload.
        pass
    if not getattr(self, 'pages', None):
        return
    if self.page_index > 0:
        self.page_index = max(0, self.page_index - 1)
        self._show_page()


def _sync_contract_selector_visibility_187(form) -> None:
    """Show the construction contract selector only for contractor costs."""
    group_var = getattr(form, 'vars', {}).get('cost_group')
    selector = getattr(form, 'widgets', {}).get('contract_id')
    if group_var is None or selector is None:
        return
    try:
        is_contractor = str(group_var.get() or '').strip() == 'پیمانکار'
        box = selector.master
        if is_contractor:
            box.grid()
        else:
            box.grid_remove()
            contract_var = form.vars.get('contract_id')
            if contract_var is not None:
                contract_var.set('')
        # the category also decides which plan lines the sub-phase box offers
        refresh_subphase = getattr(form, '_refresh_subphase', None)
        if callable(refresh_subphase):
            refresh_subphase()
    except tk.TclError:
        pass


def _sync_partner_source_visibility_187(form) -> None:
    """Show partner funding source only for the dedicated «شرکا» choice."""
    variables = getattr(form, 'vars', {}) or {}
    widgets = getattr(form, 'widgets', {}) or {}
    name_var = variables.get('partner_name')
    source_var = variables.get('partner_source')
    source_widget = widgets.get('partner_source')
    if source_widget is None:
        return
    try:
        selected = str(name_var.get() if name_var is not None
                       else (getattr(form, 'payload', {}) or {}).get('partner_name') or '').strip()
        visible = selected == 'شرکا'
        host = source_widget.master
        if visible:
            host.grid()
            source_widget.configure(state='readonly')
        else:
            host.grid_remove()
            source_widget.configure(state='disabled')
            if source_var is not None and str(source_var.get() or ''):
                was_loading = getattr(form, '_loading', False)
                form._loading = True
                try:
                    source_var.set('')
                    form.payload['partner_source'] = ''
                finally:
                    form._loading = was_loading
    except (AttributeError, tk.TclError):
        pass


def _wizard_after_render_187(self):
    _ORIGINAL_WIZARD_AFTER_RENDER_187(self)
    _install_financial_sync_187(self)
    title, subtype = self.title_var.get(), _canonical_document_subtype_187(self.subtype_var.get())
    if title == 'ورودی' and subtype == 'شرکا/قرض':
        partner_name = self.vars.get('partner_name')
        if partner_name is not None:
            partner_name.trace_add(
                'write', lambda *_args, target=self: _sync_partner_source_visibility_187(target))
        _sync_partner_source_visibility_187(self)
    if title == 'هزینه ساخت' and self.vars.get('cost_group') is not None:
        self.vars['cost_group'].trace_add(
            'write', lambda *_args, target=self: _sync_contract_selector_visibility_187(target))
        _sync_contract_selector_visibility_187(self)
    if _is_nonfinancial_payload_187(title, subtype):
        date_key = {
            'تقویم کارگاهی': 'calendar_date_shamsi',
            'گزارش روزانه': 'report_date_shamsi',
            'یادآوری': 'reminder_date_shamsi',
            'فاکتور': 'invoice_note_date_shamsi',
        }.get(subtype)
        if date_key and self.vars.get(date_key) is not None:
            self.vars[date_key].trace_add('write', lambda *_args, target=self, key=date_key: _sync_document_event_date_187(target, key))
            _sync_document_event_date_187(self, date_key)
        if subtype == 'گزارش روزانه' and self.vars.get('report_row_count') is not None:
            self.vars['report_row_count'].trace_add('write', lambda *_args, target=self: _refresh_report_rows_187(target))
            _refresh_report_rows_187(self)
        return
    if _is_facility_payload_187(title, subtype):
        for key in ('loan_total_amount', 'amount', 'interest_rate', 'installment_count',
                    'installment_amount', 'loan_start_date', 'first_due_date_shamsi'):
            var = self.vars.get(key)
            if var is not None:
                var.trace_add('write', lambda *_args, target=self, name=key: _sync_loan_fields_187(target, name))
        _sync_loan_fields_187(self)


def _seed_cheque_resolution_payload187(form):
    selected_id = str((getattr(form, 'payload', {}) or {}).get('selected_cheque_id187') or '').strip()
    if not selected_id:
        raise ValueError('از فهرست، چکِ تعیین‌تکلیف‌نشده را انتخاب کن.')
    row = DB.get_cheque(selected_id)
    if not row:
        raise ValueError('چک انتخاب‌شده دیگر در برنامه موجود نیست.')
    status = str(row.get('status') or '').upper()
    mode = str(row.get('settlement_mode') or '').upper()
    edit_id = str((getattr(form, 'payload', {}) or {}).get('_resolution_edit_cheque_id187') or '')
    unresolved = status in {'ISSUED', 'PENDING_DUE'} and mode != 'RETURNED_ON_SETTLEMENT'
    if not unresolved and edit_id != selected_id and selected_id not in {
            row['cheque_id'] for row in _registered_cheques_for_clearing_187()}:
        raise ValueError('چک انتخاب‌شده قبلاً تعیین تکلیف شده است؛ فهرست را دوباره بررسی کن.')
    payload = form.payload
    # A record that already resolved this very cheque keeps what it said. While it is under review the cheque
    # row may be released (blank), and opening the record must not wipe its own answers with that.
    own = (str(payload.get('cheque_id') or '') == selected_id
           and bool(str(payload.get('cheque_resolution_status187') or '').strip()))

    def kept(key, fresh, *aliases):
        if not own:
            return fresh
        return next((text for text in (str(payload.get(name) or '').strip() for name in (key, *aliases)) if text), fresh)

    payload.update(
        cheque_operation187=CHEQUE_OPERATION_RESOLVE_187,
        selected_cheque_id187=selected_id,
        cheque_id=selected_id,
        cheque_snapshot_issue187=str(row.get('issue_date_shamsi') or row.get('issue_date') or ''),
        cheque_snapshot_due187=str(row.get('due_date_shamsi') or row.get('due_date') or ''),
        cheque_snapshot_amount187=parse_int(row.get('amount') or 0),
        cheque_snapshot_issuer187=str(row.get('issuer_name') or ''),
        cheque_snapshot_receiver187=str(row.get('receiver_name') or ''),
        cheque_snapshot_bank187=str(row.get('issuer_bank') or ''),
        cheque_snapshot_serial187=str(row.get('cheque_serial') or ''),
        cheque_snapshot_type187=v18.CHEQUE_TYPE_FA.get(str(row.get('cheque_type') or 'PHYSICAL').upper(), 'فیزیکی'),
        cheque_snapshot_description187=str(row.get('description') or ''),
        amount=parse_int(row.get('amount') or 0),
        paid_amount=parse_int(row.get('amount') or 0),
        cheque_resolution_registration187=kept('cheque_resolution_registration187', v18.REG_FA.get(
            str(row.get('registration_state') or 'UNREGISTERED').upper(), 'ثبت‌نشده')),
        cheque_resolution_return_disposition187=kept('cheque_resolution_return_disposition187', str(
            row.get('return_disposition') or CHEQUE_RETURN_DISPOSITION_CHOICES_187[3]), 'cheque_return_disposition187'),
        cheque_resolution_account_holder187=kept('cheque_resolution_account_holder187',
                                                 str(row.get('return_account_holder') or ''),
                                                 'cheque_return_account_holder187'),
        cheque_void_reason187=kept('cheque_void_reason187', str(row.get('void_reason') or '')),
        v18_title='هزینه ساخت', v18_subtype='چک',
        transaction_title='هزینه ساخت', transaction_subtype='چک',
        detected_type='EXPENSE', payment_state='CHEQUE_RESOLUTION', is_cheque=False,
    )
    return dict(row)


def _cheque_issue_pages_187(title, subtype):
    """Windows 2 to 4 of a cheque issue: every cheque detail together, the two
    statuses, then the confirmation page (empty here; its summary is drawn on show)."""
    F = v18.FieldDef
    steps = _wizard_steps_187(title, subtype)
    details = [F('event_date_shamsi', 'تاریخ صدور', 'date'), F('amount', 'مبلغ', 'money')]
    for index, group in enumerate(steps):
        if index != 1:  # window 3 is the status pair
            details.extend(group)
    return [details, list(steps[1]), []]


def _pending_attachment_names_187(pid):
    """The file names attached to a pending record, each file once however many times it was attached."""
    try:
        with DB.read() as con:
            return [os.path.basename(str(row['local_path'] or ''))
                    for row in con.execute(
                        "SELECT local_path FROM attachments WHERE entity_type='PENDING' AND entity_id=? "
                        "GROUP BY local_path ORDER BY MIN(created_at)", (pid,)).fetchall()]
    except Exception:
        return []


def _cheque_summary_lines_187(form):
    """The confirmation page of a cheque issue or resolution, one fact per line,
    in words and Persian digits (the inherited review prints stored codes)."""
    payload = dict(form.payload or {})
    pid = str(getattr(form, 'pid', '') or '')

    def text(key, default='-'):
        value = str(payload.get(key) or '').strip()
        return value or default

    def day(key):
        return fa(text(key))

    if _is_cheque_resolution_187(form.title_var.get(), form.subtype_var.get(), payload):
        lines = [
            f"عملیات: {CHEQUE_OPERATION_RESOLVE_187}",
            f"چک انتخاب‌شده: {text('selected_cheque_id187')}",
            f"تاریخ صدور: {day('cheque_snapshot_issue187')}    تاریخ سررسید: {day('cheque_snapshot_due187')}",
            f"مبلغ: {group_int_fa(parse_int(payload.get('cheque_snapshot_amount187') or 0))}",
            f"صاحب حساب / صادرکننده: {text('cheque_snapshot_issuer187')}    گیرنده: {text('cheque_snapshot_receiver187')}",
            f"بانک: {text('cheque_snapshot_bank187')}    شماره چک / صیادی: {fa(text('cheque_snapshot_serial187'))}",
            f"نوع چک: {text('cheque_snapshot_type187')}    بابت: {text('cheque_snapshot_description187')}",
            f"وضعیت ثبت چک: {text('cheque_resolution_registration187')}",
            f"وضعیت چک: {text('cheque_resolution_status187')}",
        ]
        if str(payload.get('cheque_return_disposition187') or ''):
            lines.append(f"وضعیت عودت: {text('cheque_return_disposition187')}")
        if str(payload.get('cheque_return_account_holder187') or ''):
            lines.append(f"صاحب حساب معرفی‌شده: {text('cheque_return_account_holder187')}")
        if str(payload.get('cheque_void_reason187') or ''):
            lines.append(f"دلیل ابطال: {text('cheque_void_reason187')}")
    else:
        kind = str(payload.get('cheque_type') or 'PHYSICAL')
        registration = str(payload.get('cheque_registration_state') or '')
        status = str(payload.get('cheque_status') or 'ISSUED')
        lines = [
            f"عملیات: {CHEQUE_OPERATION_ISSUE_187}",
            f"تاریخ صدور: {day('event_date_shamsi')}    تاریخ سررسید: {day('due_date_shamsi')}",
            f"مبلغ: {group_int_fa(parse_int(payload.get('amount') or 0))}",
            f"صاحب حساب: {text('issuer_name')}    گیرنده: {text('receiver_name')}",
            f"بانک: {text('issuer_bank')}    شماره چک / صیادی: {fa(text('cheque_serial'))}",
            f"نوع چک: {v18.CHEQUE_TYPE_FA.get(kind.upper(), kind)}    "
            f"بابت ضمانت: {'بله' if payload.get('is_guarantee') in (True, 1, 'بله', '1') else 'خیر'}",
            f"بابت: {text('description')}",
            f"دسته‌بندی: {text('cost_group')}"
            + (f"    قرارداد: {text('contract_id')}" if str(payload.get('contract_id') or '') else ''),
            f"فاز: {text('main_phase')} / {text('sub_phase')}",
            f"مبلغ فاکتور: {group_int_fa(parse_int(payload.get('invoice_amount') or 0))}    "
            f"مبلغ نهایی: {group_int_fa(parse_int(payload.get('final_amount') or 0))}",
            f"وضعیت ثبت چک: {v18.REG_FA.get(registration.upper(), registration or '-')}",
            f"وضعیت چک: {v18.CODE_TO_CHEQUE_STATUS.get(status.upper(), status)}",
        ]
    names = _pending_attachment_names_187(pid)
    lines.append(f"اسناد پیوست: {fa(len(names))} فایل" + (' — ' + '، '.join(names) if names else ''))
    return lines


_ORIGINAL_WIZARD_RENDER_REVIEW_187 = v182.TransactionWizard182._render_review


def _wizard_render_review_187(self, body):
    """Confirmation window of a cheque: the readable summary instead of stored codes."""
    if self.title_var.get() == 'هزینه ساخت' and self.subtype_var.get() == 'چک':
        palette = palette_187()
        tk.Label(body, text='مرور نهایی', bg=palette['panel'], fg=palette['text_primary'],
                 font=(self.font_family, self.font_size + 3, 'bold')).pack(anchor='e', pady=(8, 12))
        tk.Label(body, text=chr(10).join(_cheque_summary_lines_187(self)), bg=palette['panel'],
                 fg=palette['text_primary'], anchor='ne', justify='right', wraplength=690, padx=18, pady=16,
                 font=(self.font_family, self.font_size)).pack(fill='both', expand=True)
        return
    return _ORIGINAL_WIZARD_RENDER_REVIEW_187(self, body)


def _wizard_next_187(self):
    """Keep the conditional construction category on wizard window one."""
    if self.page_index == 0:
        try:
            self._capture()
            self._validate_current()
        except Exception as exc:
            return messagebox.showwarning('ثبت مرحله‌ای', str(exc), parent=self)
        title, subtype = self.title_var.get(), self.subtype_var.get()
        if not title or not subtype:
            return messagebox.showwarning('نوع تراکنش', 'عنوان تراکنش و نوع تراکنش را انتخاب کن.', parent=self)
        first = [v18.FieldDef('event_date_shamsi', 'تاریخ', 'date')]
        first.append(v18.FieldDef('amount', 'مبلغ', 'money', readonly=title == 'یادداشت'))
        first.extend([
            v18.FieldDef('v18_title', 'عنوان تراکنش', 'titlecombo'),
            v18.FieldDef('v18_subtype', 'نوع تراکنش', 'subcombo'),
        ])
        if title == 'هزینه ساخت' and not _is_cheque_clearing_187(title, subtype):
            first.extend([
                v18.FieldDef('cost_group', 'دسته‌بندی', 'combo', tuple(v18.COST_GROUPS)),
            ])
            first.append(v18.FieldDef('contract_id', 'انتخاب قرارداد', 'contract'))
        elif title == 'یادداشت':
            first.append(_note_phase_field_187())
        elif title == LAND_TITLE:
            first.extend([v18.FieldDef('construction_stage', 'فاز ساخت', 'combo', (LAND_TITLE,), readonly=True),
                          v18.FieldDef(LAND_MODE_KEY, 'روش پرداخت', 'combo', LAND_MODES)])
        effective = land_payment_subtype(self.payload) if title == LAND_TITLE else subtype
        if title == 'هزینه ساخت' and subtype == 'چک':
            first.extend([
                v18.FieldDef('cheque_operation187', 'عملیات', 'combo', CHEQUE_OPERATION_CHOICES_187),
                v18.FieldDef('selected_cheque_id187', 'انتخاب چک', 'cheque_picker'),
            ])
            operation = str(self.payload.get('cheque_operation187') or CHEQUE_OPERATION_ISSUE_187)
            if operation == CHEQUE_OPERATION_RESOLVE_187:
                try:
                    cheque = _seed_cheque_resolution_payload187(self)
                except Exception as exc:
                    return messagebox.showwarning('تعیین تکلیف چک', str(exc), parent=self)
                self.payload.setdefault(
                    'cheque_resolution_registration187',
                    v18.REG_FA.get(str(cheque.get('registration_state') or 'UNREGISTERED').upper(), 'ثبت‌نشده'))
                current_status = _cheque_status_label_187(cheque)
                self.payload.setdefault(
                    'cheque_resolution_status187',
                    current_status if current_status in CHEQUE_RESOLUTION_STATUS_CHOICES_187 else '',
                )
                self.payload.setdefault('cheque_resolution_return_disposition187',
                                        CHEQUE_RETURN_DISPOSITION_CHOICES_187[3])
                self.payload.setdefault('cheque_resolution_account_holder187',
                                        str(cheque.get('return_account_holder') or ''))
                self.pages = [first, _cheque_resolution_detail_fields_187(),
                              _cheque_resolution_status_fields_187(), []]
            else:
                self.pages = [first] + _cheque_issue_pages_187(title, effective)
        elif _is_facility_payload_187(title, effective):
            self.pages = _facility_wizard_pages_187(first)
        else:
            self.pages = [first] + _wizard_steps_187(title, effective)
            if not _is_cheque_clearing_187(title, effective):
                self.pages.append([])
        self.page_index = 1 if len(self.pages) > 1 else 0
        return self._show_page()
    title, subtype = self.title_var.get(), self.subtype_var.get()
    resolution = _is_cheque_resolution_187(title, subtype, self.payload)
    if resolution and self.page_index == 2:
        try:
            self._capture()
            code = _cheque_resolution_status_code_187(self.payload.get('cheque_resolution_status187'))
            if code not in {'CASHED', 'RETURNED', 'RETURNED_ON_SETTLEMENT', 'VOIDED'}:
                raise ValueError('وضعیت چک را انتخاب کن.')
            if code in {'RETURNED_ON_SETTLEMENT', 'VOIDED'} and not str(
                    self.payload.get('cheque_return_disposition187') or '').strip():
                raise ValueError('وضعیت عودت چک را انتخاب کن.')
            if code == 'RETURNED_ON_SETTLEMENT' and not str(
                    self.payload.get('cheque_return_account_holder187') or '').strip():
                raise ValueError('نام صاحب حساب معرفی‌شده را وارد کن.')
            if code == 'VOIDED' and not str(self.payload.get('cheque_void_reason187') or '').strip():
                raise ValueError('دلیل ابطال چک را وارد کن.')
        except Exception as exc:
            return messagebox.showwarning('تعیین تکلیف چک', str(exc), parent=self)
    if self.page_index >= len(self.pages) - 1:
        if getattr(self, '_approved_in_wizard_187', False):
            return
        try:
            self._capture()
            self._validate_current()
            payload = dict(self.payload)
            payload['v18_manual_fields'] = sorted(self.manual_fields)
            if not _confirm_debt_warning_187(self, payload):
                return
            if not _confirm_late_penalty_187(self, payload):
                return
            if _is_cheque_clearing_187(title, _canonical_document_subtype_187(subtype)):
                _submit_cheque_clearing_187(self.pid, payload, self.rich)
            elif _is_cheque_resolution_187(title, subtype, payload):
                # Resolution edits an existing posted cheque. Bypass submit_v18's
                # normal revision path so it cannot rewrite the expense posting.
                _approve_cheque_resolution_187(self.pid, payload)
            else:
                v18.submit_v18(self.pid, payload, self.rich)
        except Exception as exc:
            messagebox.showerror('تأیید انجام نشد', str(exc), parent=self)
            return
        # Confirming returns to Data Entry but never opens the record window: the record opens only from the
        # wizard's «فرم کامل» button.
        self._approved_in_wizard_187 = True
        self.next_b.configure(text='ثبت شد', state='disabled')
        parent = self.master
        self.grab_release()
        self.destroy()
        try:
            owner = parent
            while owner is not None:
                notebook = getattr(owner, 'notebook', None)
                tab = getattr(owner, 'approval_tab', None)
                if notebook is not None and tab is not None:
                    notebook.select(tab)
                    break
                owner = getattr(owner, 'master', None)
            self.on_done()
        except Exception as exc:
            messagebox.showwarning(
                'ثبت انجام شد',
                f'ثبت انجام شد؛ تازه‌سازی فهرست با خطا روبه‌رو شد: {exc}',
                parent=parent,
            )
        return
    return _ORIGINAL_WIZARD_NEXT_187(self)


def _nonfinancial_description_187(payload: dict, subtype: str, raw: str = '') -> str:
    subtype = _canonical_document_subtype_187(subtype)
    if subtype == 'گزارش روزانه':
        rows = _document_rows_187(payload.get('daily_report_rows') or payload.get('report_rows'))
        count = len(rows) or parse_int(payload.get('report_row_count'))
        return _daily_report_summary_187(count)
    if subtype == 'یادداشت':
        subject = str(payload.get('note_subject') or '').strip()
        description = str(payload.get('description') or raw or '').strip()
        return f'{subject} — {description}'.strip(' —') if subject else description
    return str(payload.get('description') or raw or subtype).strip()


def _approve_nonfinancial_187(pid: str, payload: dict, rich) -> str:
    title, subtype = v18._title_type_from_payload(payload)
    subtype = _canonical_document_subtype_187(subtype)
    if not _is_nonfinancial_payload_187(title, subtype):
        return ''
    pending = DB.get_pending_item(str(pid)) or {}
    edit_document_id = str(payload.get('_document_edit_id_187') or '').strip()
    if str(pending.get('status') or '').upper() == 'APPROVED' and not edit_document_id:
        return 'این رکورد قبلاً ثبت شده است.'
    holder = type('_DocumentPayloadHolder187', (), {
        'payload': dict(payload), 'vars': {}, '_loading': False,
        'manual_fields': set(),
    })()
    normalized = _payload_values_187(holder, title, subtype)
    raw = v18._raw_text(str(pid), pending)
    description = _nonfinancial_description_187(normalized, subtype, raw)
    event_date = str(normalized.get('event_date_shamsi') or '').strip()
    document_payload = {
        **normalized,
        'document_type': _document_code_187(subtype),
        'event_date_shamsi': event_date,
        'description': description,
        'amount': 0,
    }
    links = []
    link_pending_id = str(normalized.get('link_pending_id') or '').strip()
    if link_pending_id:
        posting = DB.get_financial_posting(link_pending_id)
        if posting and posting.get('primary_entity_type') and posting.get('primary_entity_id'):
            links.append((posting['primary_entity_type'], posting['primary_entity_id']))
    if edit_document_id:
        now = _finance_now_187()
        with DB.tx() as con:
            current = con.execute(
                "SELECT document_id FROM financial_documents WHERE document_id=? AND status='ACTIVE' LIMIT 1",
                (edit_document_id,),
            ).fetchone()
            if not current:
                raise ValueError('سند غیرمالی انتخاب‌شده پیدا نشد.')
            con.execute(
                '''UPDATE financial_documents
                   SET document_type=?, event_date_shamsi=?, description=?, amount=0,
                       raw_text=?, updated_at=?
                   WHERE document_id=?''',
                (
                    _document_code_187(subtype), event_date, description, raw,
                    now, edit_document_id,
                ),
            )
            con.execute(
                'DELETE FROM financial_document_links WHERE document_id=?',
                (edit_document_id,),
            )
            for entity_type, entity_id in links:
                con.execute(
                    '''INSERT OR IGNORE INTO financial_document_links
                       (document_id, entity_type, entity_id, created_at)
                       VALUES(?,?,?,?)''',
                    (edit_document_id, str(entity_type).upper(), str(entity_id), now),
                )
        DB.relink_pending_attachments(str(pid), entity_type='DOCUMENT', entity_id=edit_document_id)
        v18.v175._mark_nonfinancial_approved(str(pid), 'DOCUMENT', edit_document_id)
        return f'{subtype} اصلاح شد؛ اثر مالی ندارد.'
    document_id = rich.add_financial_document(str(pid), document_payload, raw, links)
    DB.relink_pending_attachments(str(pid), entity_type='DOCUMENT', entity_id=document_id)
    v18.v175._mark_nonfinancial_approved(str(pid), 'DOCUMENT', document_id)
    return f'{subtype} ثبت شد؛ اثر مالی ندارد.'


def _manual_resolution_record_187(cheque_id, status, *, registration, disposition, holder, void_reason,
                                  require_details=True):
    """A status change made by hand on a cheque that has no resolution record gets one: a record in Data
    Entry, approved on the spot, like the one the wizard makes. Returns its id."""
    from types import SimpleNamespace
    form = SimpleNamespace(payload={'selected_cheque_id187': str(cheque_id), '_resolution_edit_cheque_id187': str(cheque_id)})
    _seed_cheque_resolution_payload187(form)
    label = {code: text for text, code in {
        'صادرشده': 'ISSUED', 'پاس‌شده': 'CASHED', 'برگشتی': 'RETURNED',
        'عودتی به شرط تسویه': 'RETURNED_ON_SETTLEMENT', 'باطل‌شده': 'VOIDED'}.items()}[status]
    payload = dict(form.payload)
    payload.update(
        cheque_resolution_status187=label, cheque_status=status,
        cheque_resolution_registration187=v18.REG_FA.get(str(registration or '').upper(), registration or ''),
        cheque_registration_state=str(registration or '').upper() or 'UNREGISTERED',
        cheque_resolution_return_disposition187=disposition, cheque_return_disposition187=disposition,
        cheque_resolution_account_holder187=holder, cheque_return_account_holder187=holder,
        cheque_void_reason187=void_reason,
        event_date_shamsi=gregorian_to_shamsi(datetime.now().date()),
        description=f'تغییر دستی وضعیت چک از تب چک‌ها به «{label}»', source='MANUAL_CHEQUE_TAB_18_7')
    mid = int(datetime.now().timestamp() * 1_000_000)
    with DB.atomic():
        DB.register_telegram_message(chat_id=-180, message_id=mid, raw_text='', content_type='manual_gui',
                                     message_date=datetime.now().isoformat(timespec='seconds'), state='RECEIVED')
        pid = DB.create_or_replace_pending(telegram_chat_id=-180, telegram_message_id=mid, detected_type='EXPENSE',
                                           payload=payload, confidence=1.0, status='PENDING_REVIEW')
        _approve_cheque_resolution_187(pid, payload, require_details=require_details)
    return pid


def _approve_cheque_resolution_187(pid: str, payload: dict, *, require_details: bool = True) -> str:
    payload = dict(payload or {})
    cheque_id = str(payload.get('selected_cheque_id187') or payload.get('cheque_id') or '').strip()
    if not cheque_id:
        raise ValueError('چکی برای تعیین تکلیف انتخاب نشده است.')
    cheque = DB.get_cheque(cheque_id)
    if not cheque:
        raise ValueError('چک انتخاب‌شده پیدا نشد.')
    target = _cheque_resolution_status_code_187(
        payload.get('cheque_resolution_status187') or payload.get('cheque_status'))
    if target not in {'CASHED', 'RETURNED', 'RETURNED_ON_SETTLEMENT', 'VOIDED'}:
        raise ValueError('وضعیت چک را از گزینه‌های مجاز انتخاب کن.')
    original_id = str(payload.get('_resolution_edit_cheque_id187') or '').strip()
    current = str(cheque.get('status') or '').upper()
    current_mode = str(cheque.get('settlement_mode') or '').upper()
    unresolved = current in {'ISSUED', 'PENDING_DUE'} and current_mode != 'RETURNED_ON_SETTLEMENT'
    if not unresolved and original_id != cheque_id and cheque_id not in {
            row['cheque_id'] for row in _registered_cheques_for_clearing_187()}:
        raise ValueError('چک انتخاب‌شده قبلاً تعیین تکلیف شده است.')
    disposition = str(payload.get('cheque_return_disposition187') or
                      cheque.get('return_disposition') or CHEQUE_RETURN_DISPOSITION_CHOICES_187[3]).strip()
    account_holder = str(payload.get('cheque_return_account_holder187') or
                         cheque.get('return_account_holder') or '').strip()
    void_reason = str(payload.get('cheque_void_reason187') or cheque.get('void_reason') or '').strip()
    if target in {'RETURNED_ON_SETTLEMENT', 'VOIDED'} and disposition not in CHEQUE_RETURN_DISPOSITION_CHOICES_187:
        raise ValueError('وضعیت عودت چک را انتخاب کن.')
    if require_details and target == 'RETURNED_ON_SETTLEMENT' and not account_holder:
        raise ValueError('نام صاحب حساب معرفی‌شده را وارد کن.')
    if require_details and target == 'VOIDED' and not void_reason:
        raise ValueError('دلیل ابطال چک را وارد کن.')
    registration = str(payload.get('cheque_registration_state') or
                       cheque.get('registration_state') or 'UNREGISTERED').upper()
    # What rejecting this record puts back: the cheque as it was before its first
    # resolution, and the receipts this record moved onto the cheque.
    previous = dict((DB.get_pending_item(str(pid)) or {}).get('payload') or {})
    before_state = (payload.get('_resolution_before187') or previous.get('_resolution_before187')
                    or (DB.cheque_state(cheque_id) if unresolved else dict(
                        status='ISSUED', settlement_mode='NORMAL', registration_state=cheque.get('registration_state'),
                        return_disposition=cheque.get('return_disposition'), return_account_holder=cheque.get('return_account_holder'),
                        void_reason=cheque.get('void_reason'), cashed_date=None, cashed_date_shamsi=None)))
    with DB.read() as con:
        moved = [row['attachment_id'] for row in con.execute(
            "SELECT attachment_id FROM attachments WHERE entity_type='PENDING' AND entity_id=?", (str(pid),))]
    attachments = list(dict.fromkeys([*(payload.get('_resolution_attachments187')
                                        or previous.get('_resolution_attachments187') or []), *moved]))
    DB.update_cheque_workflow_state(
        cheque_id, lifecycle=target, registration_state=registration,
        return_disposition=(disposition if target in {'RETURNED_ON_SETTLEMENT', 'VOIDED'} else None),
        return_account_holder=(account_holder if target == 'RETURNED_ON_SETTLEMENT' else None),
        void_reason=(void_reason if target == 'VOIDED' else None),
        source='GUI_CHEQUE_RESOLUTION_18_7', actor_id='GUI', require_details=require_details,
    )
    payload.update(
        _resolution_before187=before_state, _resolution_attachments187=attachments,
        cheque_operation187=CHEQUE_OPERATION_RESOLVE_187,
        selected_cheque_id187=cheque_id, cheque_id=cheque_id,
        cheque_status=target, cheque_registration_state=registration,
        cheque_return_disposition187=disposition,
        cheque_return_account_holder187=account_holder,
        cheque_void_reason187=void_reason,
        payment_state='CHEQUE_RESOLUTION', detected_type='EXPENSE', is_cheque=False,
    )
    DB.update_pending(str(pid), payload=payload)
    DB.relink_pending_attachments(str(pid), entity_type='CHEQUE', entity_id=cheque_id)
    v18.v175._mark_nonfinancial_approved(str(pid), 'CHEQUE', cheque_id)
    label = _cheque_status_label_187(DB.get_cheque(cheque_id) or {})
    return f'وضعیت چک به «{label}» به‌روزرسانی شد؛ ردیف مالی تازه‌ای ساخته نشد.'


def _installment_plan_187(payload: dict) -> dict:
    """Which instalments the payment would pay, read from the loan's schedule; nothing is written here."""
    lid = _loan_id_of_text_187(payload.get('loan_id'))
    if not lid:
        raise ValueError('نام وام را انتخاب کن.')
    return LoanService(DB).plan_installment_payment(
        lid, amount=parse_int(payload.get('amount') or 0),
        count=max(1, parse_int(payload.get('installments_paid_now') or 1)),
        paid_date_shamsi=str(payload.get('event_date_shamsi') or ''))


def _instalment_plan_problem_187(payload: dict, plan: dict) -> str:
    """Why the payment cannot be posted as it is; '' when it can."""
    amount = v18._group_money(parse_int(payload.get('amount') or 0))
    if plan.get('mismatch'):
        row = plan['mismatch']
        return (f"مبلغ این پرداخت ({amount}) نه برابر قسط {fa(row['installment_number'])} "
                f"({v18._group_money(row['base'])}) است، نه برابر آن با دیرکرد ({v18._group_money(row['due_total'])}). "
                'مبلغ را با رسید بانک بررسی کن.')
    if plan.get('leftover', 0) > 0:
        return _instalment_balance_message_187(payload, plan)
    return ''


def _instalment_balance_message_187(payload: dict, plan: dict) -> str:
    """The payment is more than the instalments still due take, late payments included: say how much, and what to check."""
    items = plan.get('items') or []
    amount = v18._group_money(parse_int(payload.get('amount') or 0))
    if len(items) == 1:
        owed = f"از مانده قسط {fa(items[0]['installment_number'])} ({v18._group_money(items[0]['due_total'])})"
    else:
        owed = f"از مانده قسط‌های این پرداخت ({v18._group_money(sum(item['due_total'] for item in items))})"
    head = f'مبلغ این پرداخت ({amount}) {owed} بیشتر است.'
    if any(item['penalty'] for item in items):
        rate = fa(round(next(item['penalty_rate'] for item in items if item['penalty'])))
        return head + f' دیرکرد با نرخ {rate}٪ سالانه حساب شده است؛ مبلغ را با رسید بانک بررسی کن.'
    lid = _loan_id_of_text_187(payload.get('loan_id'))
    installments = LoanService(DB).list_installments(lid) if lid else []
    if any(int(row.get('paid_amount') or 0) > 0 for row in installments):
        return head + ' این وام قسط پرداخت‌شده دارد و جدول اقساط آن قابل تغییر نیست.'
    return (head + ' اگر مبلغ قسط بانک بیشتر از جدول است، در پرونده همین وام «مبلغ هر قسط» را برابر مبلغ بانک '
            'بگذار و ثبت کن؛ چون هنوز قسطی پرداخت نشده، جدول اقساط دوباره ساخته می‌شود.')


def _approve_installment_187(pid: str, payload: dict, rich) -> str:
    """Post an instalment payment from the loan's schedule in one transaction. A row paid after its due date takes its
    late payment too, but only once the person has confirmed it (see _confirm_late_penalty_187)."""
    plan = _installment_plan_187(payload)
    problem = _instalment_plan_problem_187(payload, plan)
    if problem:
        raise ValueError(problem)
    rows = [item for item in plan['items'] if item['pay'] > 0]
    if not rows:
        raise ValueError('مبلغ پرداخت باید بیشتر از صفر باشد.')
    late = sum(item['posted_penalty'] for item in rows)
    if late and not payload.get('late_penalty_accepted187'):
        raise ValueError('دیرکرد این قسط هنوز تأیید نشده است.')
    lid = _loan_id_of_text_187(payload.get('loan_id'))
    posted = LoanService(DB).pay_installments_with_penalties(
        [{'loan_installment_id': item['loan_installment_id'], 'amount': item['pay'],
          'penalty': item['posted_penalty']} for item in rows],
        paid_date_shamsi=str(payload.get('event_date_shamsi') or ''),
        source='GUI_18', description=f'پرداخت قسط وام {lid}' + (f' با دیرکرد {late}' if late else ''))
    v18.v175._mark_nonfinancial_approved(pid, 'LOAN_INSTALLMENT', posted[-1]['installment_id'])
    message = f'{fa(len(posted))} قسط به پرونده تسهیلات ثبت شد.'
    if late:
        message += f' دیرکرد {v18._group_money(late)} به مبلغ قسط اضافه شد.'
    return message


def _ask_late_penalty_187(form, text: str) -> bool:
    """The themed question under which the late payment of an instalment is explained; «تایید» posts it."""
    from barkav_ui.messages import MessageDialog
    dialog = MessageDialog(form, 'قسط با دیرکرد', text, kind='warning', buttons=(
        ('انصراف', False, 'Toolbar.TButton'),
        ('تایید', True, 'Primary.TButton')))
    dialog.wait_window()
    return dialog.result is True


def _confirm_late_penalty_187(form, payload: dict) -> bool:
    """Ask before posting an instalment paid late with its late payment. Nothing is written here: False keeps the record
    open, and a payment that cannot be posted as it is raises with the reason."""
    title, subtype = v18._title_type_from_payload(payload)
    if not _is_installment_payload_187(title, subtype):
        return True
    plan = _installment_plan_187(payload)
    problem = _instalment_plan_problem_187(payload, plan)
    if problem:
        raise ValueError(problem)
    late = [item for item in plan['items'] if item['pay'] > 0 and item['posted_penalty'] > 0]
    if not late:
        payload.pop('late_penalty_accepted187', None)
        return True
    base = sum(item['base'] for item in late)
    lines = [f"قسط {fa(item['installment_number'])} سررسید {fa(item['due_date_shamsi'])} بوده و "
             f"{fa(item['days_late'])} روز دیرتر پرداخت می‌شود. دیرکرد با نرخ {fa(round(item['penalty_rate']))}٪ سالانه "
             f"{v18._group_money(item['penalty'])} است و قسط با دیرکرد {v18._group_money(item['due_total'])} "
             'پرداخت و در جدول اقساط ثبت می‌شود.' for item in late]
    text = '\n'.join([
        f"مبلغ این پرداخت ({v18._group_money(parse_int(payload.get('amount') or 0))}) از مانده "
        f"{'قسط‌ها' if len(late) > 1 else 'قسط'} ({v18._group_money(base)}) بیشتر است.",
        'دلیل افزایش قسط دیرکرد هست.',
        *lines,
    ])
    if not _ask_late_penalty_187(form, text):
        return False
    payload['late_penalty_accepted187'] = True
    return True


def _approve_v18_187(pid: str, payload: dict, rich) -> str:
    """Approve a facility with the complete wizard payload and loan schedule."""
    title, subtype = v18._title_type_from_payload(payload)
    subtype = _canonical_document_subtype_187(subtype)
    if _is_cheque_resolution_187(title, subtype, payload):
        return _approve_cheque_resolution_187(pid, payload)
    if _is_nonfinancial_payload_187(title, subtype):
        return _approve_nonfinancial_187(pid, payload, rich)
    if not _is_facility_payload_187(title, subtype):
        if _is_installment_payload_187(title, subtype):
            return _approve_installment_187(pid, payload, rich)
        return _ORIGINAL_APPROVE_V18_187(pid, payload, rich)
    pending = DB.get_pending_item(str(pid)) or {}
    if str(pending.get('status') or '').upper() == 'APPROVED':
        return 'این رکورد قبلاً ثبت شده است.'
    payload = _payload_values_187(type('_PayloadHolder187', (), {
        'payload': dict(payload), 'vars': {}, '_loading': False,
        'manual_fields': set(),
    })(), title, subtype)
    amount = parse_int(payload.get('amount') or payload.get('net_received_amount') or 0)
    principal = parse_int(payload.get('principal_amount') or payload.get('loan_total_amount') or amount)
    received_date = _loan_date_value_187(payload.get('loan_start_date') or payload.get('event_date_shamsi'))
    count = parse_int(payload.get('installment_count') or 0)
    if amount <= 0 or principal <= 0:
        raise ValueError('اصل و مبلغ دریافتی وام باید بیشتر از صفر باشد.')
    if not received_date:
        raise ValueError('تاریخ دریافت وام نامعتبر است.')
    first_due = _loan_date_value_187(payload.get('first_due_date_shamsi'))
    if not first_due and count > 0:
        first_due = gregorian_to_shamsi(
            _add_months(date.fromisoformat(shamsi_to_gregorian(received_date)), 1))
    installment = parse_int(payload.get('installment_amount') or 0)
    if installment <= 0 and principal > 0 and count > 0:
        installment = calculate_loan_installment_187(
            principal, payload.get('interest_rate') or 0, count,
        )
    total_interest = loan_total_interest_187(principal, installment, count)
    if first_due and count > 0:
        payload['loan_end_date'] = gregorian_to_shamsi(
            _add_months(date.fromisoformat(shamsi_to_gregorian(first_due)), count - 1))
    payload.update({
        'amount': amount, 'principal_amount': principal,
        'loan_total_amount': principal, 'net_received_amount': amount,
        'installment_amount': installment, 'total_interest': total_interest,
        'first_due_date_shamsi': first_due,
    })
    guarantors = ' | '.join(
        str(payload.get(key) or '').strip()
        for key in ('guarantor_1', 'guarantor_2')
        if str(payload.get(key) or '').strip()
    )
    obj = LoanService(DB).create_loan(
        lender_name=str(payload.get('loan_bank') or payload.get('lender_name') or 'بانک').strip(),
        principal_amount=principal,
        net_received_amount=amount,
        received_date_shamsi=received_date,
        interest_rate=float(payload.get('interest_rate') or 0),
        total_interest=total_interest,
        bank_fees=_loan_fees_187(principal, amount),
        installment_count=count,
        installment_amount=installment,
        first_due_date_shamsi=first_due,
        guarantors=guarantors,
        contract_number=str(payload.get('contract_number') or '').strip(),
        borrower_name=str(payload.get('borrower_name') or '').strip(),
        branch_name=str(payload.get('branch_name') or '').strip(),
        loan_name=str(payload.get('loan_name') or str(principal)[:4]).strip(),
        description=str(payload.get('loan_title') or payload.get('description') or 'ورودی تسهیلات').strip(),
        source='GUI_187',
        telegram_chat_id=pending.get('telegram_chat_id'),
        telegram_message_id=pending.get('telegram_message_id'),
    )
    loan_id = str(obj.get('loan_id') or '')
    v18.v175._mark_nonfinancial_approved(pid, 'LOAN', loan_id)
    DB.relink_pending_attachments(pid, entity_type='LOAN', entity_id=loan_id)
    return 'وام جدید و ردیف ورودی تسهیلات ثبت شد.'


v18.approve_v18 = _approve_v18_187


def _submit_cheque_clearing_187(pid, payload, rich):
    pending = DB.get_pending_item(str(pid)) or {}
    if str(pending.get('status') or '').upper() != 'APPROVED':
        return v18.submit_v18(pid, payload, rich)
    payload = dict(payload)
    payload['_editing_cheque_clearing187'] = True
    payload['_original_clearing_cheque_id187'] = str(
        payload.get('_original_clearing_cheque_id187') or
        payload.get('selected_cheque_id187') or payload.get('cheque_id') or ''
    )
    payload['_original_clearing_mode187'] = str(
        payload.get('_original_clearing_mode187') or
        payload.get('cheque_clearing_mode187') or CHEQUE_CLEARING_MODES_187[0]
    )
    DB.update_pending(str(pid), payload=payload, status='NEEDS_REVIEW')
    try:
        return v18.approve_v18(pid, payload, rich)
    except Exception:
        DB.update_pending(str(pid), payload=dict(pending.get('payload') or {}), status='APPROVED')
        raise


def _editor_prepare_fields_187(self):
    """Keep one functional category and contract selector across form rebuilds."""
    for key, (variable, widget) in getattr(self, '_general_fields187', {}).items():
        self.vars[key], self.widgets[key] = variable, widget
    note = self.title_var.get() == 'یادداشت'
    land = self.title_var.get() == LAND_TITLE
    clearing = _is_cheque_clearing_187(self.title_var.get(), self.subtype_var.get())
    for key in ('cost_group', 'contract_id'):
        widget = self.widgets.get(key)
        if widget is not None:
            if clearing:
                widget.master.grid_remove()
            else:
                widget.master.grid()
    stage = self.widgets.get('construction_stage')
    if (note or land) and stage is None:
        stage = self._field(self.main.body, _note_phase_field_187(), 2, 1, width=28)
        self._general_fields187['construction_stage'] = (self.vars['construction_stage'], stage)
    if stage is not None:
        stage.master.grid() if note or land else stage.master.grid_remove()
        stage.configure(values=(LAND_TITLE,) if land else _note_phase_choices_187(self),
                        state='disabled' if land else 'readonly')
        self._loading = True
        try:
            self.vars['construction_stage'].set(LAND_TITLE if land else _phase_display_187(self, self.payload.get('construction_stage')))
        finally:
            self._loading = False
    mode = self.widgets.get(LAND_MODE_KEY)
    if land and mode is None:
        mode = self._field(self.main.body, v18.FieldDef(LAND_MODE_KEY, 'روش پرداخت', 'combo', LAND_MODES), 2, 0, width=28)
        self._general_fields187[LAND_MODE_KEY] = (self.vars[LAND_MODE_KEY], mode)
    if mode is not None:
        mode.master.grid() if land else mode.master.grid_remove()
        self._loading = True
        try:
            self.vars[LAND_MODE_KEY].set(land_payment_mode(self.payload))
        finally:
            self._loading = False
    active = self.widgets.get('cost_group')
    if active is not None and active is not getattr(self, '_category_widget_187', None):
        self.vars['cost_group'].trace_add('write', lambda *_: self._contract_field_sync())
        self._category_widget_187 = active
        self._contract_field_sync()
    # The persistent, multiline about field below replaces this small entry.
    description = self.widgets.pop('description', None)
    self.vars.pop('description', None)
    if description is not None:
        description.master.destroy()
    _sync_transaction_fields_187(self)
    _ensure_payment_method_187(self)
    _install_financial_sync_187(self)
    # Preserve the existing construction party alignment and full-width report.
    for key, column in (('payer_name', 3), ('receiver_name', 2)):
        widget = self.widgets.get(key)
        if widget is not None:
            widget.configure(justify='right')
            if self.title_var.get() == 'هزینه ساخت':
                widget.master.grid_configure(column=column, sticky='nsew')
    if self.title_var.get() == 'یادداشت' and self.subtype_var.get() == 'گزارش روزانه':
        for row_index, key in ((2, 'report_rows'), (3, 'report_images')):
            widget = self.widgets.get(key)
            if widget is not None:
                widget.master.grid_configure(row=row_index, column=0, columnspan=4)
    _right_align_form_187(self)
    if clearing:
        for key in ('cost_group', 'contract_id'):
            widget = self.widgets.get(key)
            if widget is not None:
                widget.master.grid_remove()


def _ensure_payment_method_187(form):
    if _is_cheque_clearing_187(form.title_var.get(), form.subtype_var.get()):
        widget = form.widgets.pop('payment_method', None)
        form.vars.pop('payment_method', None)
        if widget is not None:
            widget.master.destroy()
        return
    if _note_without_payment_method_187(form.title_var.get(), form.subtype_var.get()):
        widget = form.widgets.pop('payment_method', None)
        form.vars.pop('payment_method', None)
        if widget is not None:
            widget.master.destroy()
        return
    if 'payment_method' in form.widgets:
        return
    cards = form.special_host.winfo_children()
    if not cards:
        return
    body = cards[0].body
    row = max((int(widget.grid_info()['row']) for widget in body.grid_slaves()), default=-1) + 1
    field = next(field for field in _special_fields_187(form.title_var.get(), form.subtype_var.get())
                 if field.key == 'payment_method')
    form._field(body, field, row, 3, width=20)
    form._loading = True
    try:
        form.vars['payment_method'].set(v18.CODE_TO_METHOD.get(
            str(form.payload.get('payment_method') or '').upper(), 'سایر'))
    finally:
        form._loading = False


def _editor_build_187(self):
    self.transient('')
    self.overrideredirect(False)
    self.resizable(True, True)
    self._general_fields187 = {}
    _install_form_keyboard_navigation_187(self)
    _ORIGINAL_EDITOR_BUILD_187(self)
    try:
        card_header = self.main.winfo_children()[0]
        self.receipt_upload_button187 = ttk.Button(
            card_header, text='بارگذاری رسید/فایل', style='Toolbar.TButton',
            command=lambda target=self: _upload_receipt_from_form_187(target),
        )
        self.receipt_upload_button187.pack(side='left', padx=8, pady=3)
    except (IndexError, AttributeError, tk.TclError):
        pass
    if self.vars.get('cost_group') is not None:
        self.vars['cost_group'].trace_add(
            'write', lambda *_args, target=self: _sync_contract_selector_visibility_187(target))
        _sync_contract_selector_visibility_187(self)
    body = self.main.body
    box = tk.Frame(body, bg=v18.DARK['panel'])
    box.grid(row=4, column=0, columnspan=2, sticky='nsew', padx=5, pady=8)
    box.grid_columnconfigure(0, weight=1)
    tk.Label(box, text='بابت', bg=v18.DARK['panel'], fg=v18.DARK['text'],
             font=(self.font_family, self.font_size, 'bold')).grid(row=0, column=0, sticky='e')
    self.about_text187 = tk.Text(
        box, height=5, wrap='word', undo=True, relief='flat', padx=10, pady=8,
        bg=v18.DARK['surface'], fg=v18.DARK['text'], insertbackground=v18.DARK['text'],
        font=(self.font_family, self.font_size + 1))
    self.about_text187.grid(row=1, column=0, sticky='ew', pady=(3, 0))
    self.about_text187.insert('1.0', str(self.payload.get('description') or ''))
    _editor_editable_text_187(self, self.about_text187, 'description')
    for frame in self.winfo_children():
        for button in frame.winfo_children():
            if isinstance(button, ttk.Button):
                if button is getattr(self, '_confirm_button_182', None):
                    button.configure(text='تأیید و ثبت تغییرات', style='Success.TButton')
                elif button.cget('text') == 'رد':
                    button.configure(style='Danger.TButton')
                continue
            if not isinstance(button, tk.Button):
                continue
            label = button.cget('text')
            if label == 'ذخیره اصلاحات':
                button.destroy()
            elif label in ('تأیید و ثبت', 'رد'):
                frame.configure(bg=v18.DARK['panel'])
                _replace_wizard_button_with_pill_187(
                    self, button, 'تأیید و ثبت تغییرات' if label == 'تأیید و ثبت' else 'رد',
                    self.approve if label == 'تأیید و ثبت' else self.reject,
                    'Success.TButton' if label == 'تأیید و ثبت' else 'Danger.TButton')
    _right_align_form_187(self)
    _install_financial_sync_187(self)


def _editor_editable_text_187(self, widget, key):
    widget.configure(state='normal', undo=True, exportselection=False)
    widget.tag_configure('rtl187', justify='right')
    widget.tag_add('rtl187', '1.0', 'end')
    widget.edit_modified(False)

    def changed(_event=None):
        if widget.edit_modified():
            widget.tag_add('rtl187', '1.0', 'end')
            self._mark_manual(key)
            if not getattr(self, '_approved_editor_182', False):
                self._confirm_button_182.configure(text='تأیید و ثبت تغییرات')
            widget.edit_modified(False)

    widget.bind('<<Modified>>', changed, add='+')

    def clipboard_action(action):
        try:
            if action == 'select':
                widget.tag_add('sel', '1.0', 'end-1c')
            elif action in ('copy', 'cut'):
                text = widget.get('sel.first', 'sel.last')
                widget.clipboard_clear()
                widget.clipboard_append(text)
                if action == 'cut':
                    widget.delete('sel.first', 'sel.last')
            elif action == 'paste':
                text = widget.clipboard_get()
                if widget.tag_ranges('sel'):
                    widget.delete('sel.first', 'sel.last')
                widget.insert('insert', text, 'rtl187')
        except tk.TclError:
            pass
        return 'break'

    def shortcut(event):
        # Windows keycodes stay the same when the keyboard layout is Persian.
        action = {65: 'select', 67: 'copy', 86: 'paste', 88: 'cut'}.get(event.keycode)
        if action:
            return clipboard_action(action)

    def menu(_event):
        PopupMenu(widget, [(None, [
            {'label': label, 'command': lambda value=action: clipboard_action(value)}
            for label, action in (('کپی', 'copy'), ('برش', 'cut'),
                                  ('چسباندن', 'paste'), ('انتخاب همه', 'select'))
        ])], compact=True)
        return 'break'

    widget._clipboard_action187 = clipboard_action
    widget.bind('<Control-KeyPress>', shortcut)
    widget.bind('<Control-Insert>', lambda _event: clipboard_action('copy'))
    widget.bind('<Shift-Insert>', lambda _event: clipboard_action('paste'))
    widget.bind('<Button-3>', menu)
    # «بابت» and the receipt text are typed from the right: see rtl_text187
    rtl_text187.install(widget)


def _editor_evidence_187(self):
    # Resolve this record's own image even when imported attachments omit MIME.
    paths = [self.payload.get('receipt_image_path'), self.row.get('receipt_image_path'),
             self.payload.get('image_path')]
    try:
        paths.append((DB.get_receipt_analysis(self.pid) or {}).get('image_path'))
        paths.extend(item.get('local_path') for item in DB.list_pending_attachments(self.pid) or [])
    except Exception:
        logging.getLogger(__name__).exception('Could not resolve record evidence for %s', self.pid)
    roots = (Path(str(DB.db_path)).parent, Path(v18.BASE_DIR), Path(__file__).resolve().parent)
    for raw in paths:
        if not raw:
            continue
        path = Path(str(raw))
        candidates = [path] if path.is_absolute() else [root / path for root in roots]
        for candidate in candidates:
            if not candidate.is_file() or v18.Image is None:
                continue
            try:
                with v18.Image.open(candidate) as image:
                    image.verify()
            except (OSError, ValueError):
                continue
            self.row['receipt_image_path'] = str(candidate)
            break
        else:
            continue
        break
    self._image = None
    self._tkimg = None
    self.canvas.delete('all')
    if self.payload.get('receipt_image_deleted187'):
        self.row['receipt_image_path'] = ''
        self.canvas.create_text(220, 180, text='رسید تصویری ندارد', fill=palette_187()['muted'],
                                font=(self.font_family, self.font_size))
    else:
        _ORIGINAL_EDITOR_EVIDENCE_187(self)
    # Preserve an intentionally cleared caption instead of falling back to raw text.
    caption = self.payload.get('receipt_caption') if 'receipt_caption' in self.payload else v182._receipt_caption(self.row, self.payload)
    self.caption.configure(state='normal')
    self.caption.delete('1.0', 'end')
    self.caption.insert('1.0', str(caption or ''))
    _editor_editable_text_187(self, self.caption, 'receipt_caption')
    if self._image is not None:
        self._fit_image()
    from record_receipt187 import RecordReceipt187
    controller = getattr(self, '_receipt_controller187', None)
    if controller is None or controller.canvas is not self.canvas:
        self._receipt_controller187 = RecordReceipt187(self, DB, v182.APPROVAL)
    else:
        controller.bind_text()
    self._receipt_controller187.refresh_gallery()


def _with_cheque_default_category_187(row):
    """A cheque record with no category yet opens on «مصالح»."""
    payload = dict((row or {}).get('payload') or {})
    title, subtype = v18._title_type_from_payload(payload)
    if title == 'هزینه ساخت' and subtype == 'چک' and not str(payload.get('cost_group') or '').strip():
        payload['cost_group'] = CHEQUE_DEFAULT_COST_GROUP_187
        return {**row, 'payload': payload}
    return row


def _editor_init_187(self, parent, row, rich, on_done, **navigation):
    from barkav_ui.widget_lifetime import install_callback_cleanup
    install_callback_cleanup(parent)
    row = getattr(parent, '_wizard_full_drafts187', {}).pop(str(row.get('pending_id')), row)
    row = _with_cheque_default_category_187(row)
    self._record_drafts187 = {}
    original = dict(row.get('payload') or {})
    if navigation.get('navigation_rows'):
        rows = sorted(navigation['navigation_rows'], key=_record_date_order_187)
        navigation['navigation_rows'] = rows
        navigation['navigation_index'] = next(
            (index for index, item in enumerate(rows)
             if str(item.get('pending_id')) == str(row.get('pending_id'))), 0)
    _ORIGINAL_EDITOR_INIT_187(self, parent, row, rich, on_done, **navigation)
    _editor_restore_description_187(self, original)
    _editor_caption_187(self)


def _record_date_order_187(row):
    """Previous is the neighbouring older record, regardless of table sorting."""
    payload = dict(row.get('payload') or {})
    for raw in (payload.get('event_date_shamsi'), row.get('message_date')):
        value = str(raw or '').translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩',
                                                      '01234567890123456789'))
        value = value.strip().split('T')[0].split(' ')[0].replace('/', '-')
        if not value:
            continue
        try:
            if int(value.split('-')[0]) < 1700:
                value = shamsi_to_gregorian(normalize_shamsi(value))
            return date.fromisoformat(value).toordinal()
        except (ValueError, TypeError):
            continue
    return date.max.toordinal()


def _editor_caption_187(self):
    # Keep Tk's window state consistent with the native caption styles too;
    # otherwise Windows can recreate a close-only tool frame after mapping.
    if self.transient():
        self.transient('')
    if self.overrideredirect():
        self.overrideredirect(False)
    self.resizable(True, True)
    _enable_caption_controls_187(self)
    if not getattr(self, '_caption_focus_bound187', False):
        self._caption_focus_bound187 = True
        def schedule(event):
            if event.widget is not self or getattr(self, '_caption_style_job187', None):
                return
            def apply():
                try:
                    _enable_caption_controls_187(self)
                finally:
                    self._caption_style_job187 = None
            self._caption_style_job187 = self.after_idle(apply)
        for sequence in ('<FocusIn>', '<Map>', '<Configure>'):
            self.bind(sequence, schedule, add='+')


def _editor_restore_description_187(self, original):
    # The inherited cheque editor seeds description from the receipt caption.
    # An explicitly saved about value must survive reopening, including blank.
    if 'description' in original:
        self.payload['description'] = original['description']
        self.about_text187.delete('1.0', 'end')
        self.about_text187.insert('1.0', str(original['description'] or ''), 'rtl187')
        self.about_text187.edit_modified(False)
    if 'receipt_caption' in original:
        self.payload['receipt_caption'] = original['receipt_caption']
        self.caption.delete('1.0', 'end')
        self.caption.insert('1.0', str(original['receipt_caption'] or ''), 'rtl187')
        self.caption.edit_modified(False)
    self._navigation_baseline_182 = self._navigation_values_182()


def _editor_navigation_values_187(self):
    values = _ORIGINAL_EDITOR_NAVIGATION_VALUES_187(self)
    for key, name in (('description', 'about_text187'), ('receipt_caption', 'caption')):
        widget = getattr(self, name, None)
        if widget is not None:
            values[key] = widget.get('1.0', 'end-1c')
    return values


def _editor_reload_187(self, row, index):
    row = _with_cheque_default_category_187(row)
    original = dict(row.get('payload') or {})
    _ORIGINAL_EDITOR_RELOAD_187(self, row, index)
    _editor_restore_description_187(self, original)
    _editor_caption_187(self)


def _editor_payload_values_187(self, title, subtype):
    payload = _payload_values_187(self, title, subtype)
    if hasattr(self, 'about_text187'):
        payload['description'] = self.about_text187.get('1.0', 'end-1c').strip()
    if hasattr(self, 'caption'):
        payload['receipt_caption'] = self.caption.get('1.0', 'end-1c').strip()
    if self.payload.get('_cheque_record_id187'):
        for key in ('cheque_return_disposition187','cheque_return_account_holder187','cheque_void_reason187'):
            if key in self.vars:payload[key]=self.vars[key].get()
    _with_loan_id_187(payload, title, subtype)
    return _carry_debt_187(self.pid, payload)


def _editor_navigate_187(self, direction):
    rows = getattr(self, '_navigation_rows_182', [])
    index = self._navigation_index_182 + int(direction)
    if not 0 <= index < len(rows):
        return
    # Moving between records keeps drafts in memory. Only the approval button
    # writes data or changes the original record's status.
    self._record_drafts187[self.pid] = self.payload_from_form()
    target = dict(rows[index])
    pid = str(target.get('pending_id') or '')
    target = dict(DB.get_pending_item(pid) or target)
    if pid in self._record_drafts187:
        target['payload'] = deepcopy(self._record_drafts187[pid])
    target['raw_text'] = v18._raw_text(pid, target)
    self._reload_record_182(target, index)


def _manual_status_action_187(form, cheque_id, payload):
    """A status changed by hand in the cheque's window needs details its resolution record must hold
    (the account holder of a settlement, the reason of a void). When they are missing the user is told, and
    chooses: ignore (the status changes, the details stay to be completed), open the resolution record, or
    cancel (nothing changes). None means cancel."""
    status = _cheque_resolution_status_code_187(payload.get('cheque_status'))
    if payload.get('cheque_status') == 'RETURNED_SETTLED':
        status = 'RETURNED_ON_SETTLEMENT'
    cheque = DB.get_cheque(str(cheque_id)) or {}
    current = _cheque_resolution_status_code_187(_cheque_status_label_187(cheque)) or 'ISSUED'
    if status == 'ISSUED' and current != 'ISSUED':
        # the resolution records of the cheque are taken back with it
        if not messagebox.askyesno(
                'برگشت به «صادرشده»',
                'وضعیت چک به «صادرشده» برمی‌گردد و رکورد تعیین تکلیف آن به ردشده‌ها می‌رود. ادامه می‌دهید؟', parent=form):
            return None
        return 'apply'
    missing = []
    if status == 'RETURNED_ON_SETTLEMENT' and not str(payload.get('cheque_return_account_holder187') or '').strip():
        missing.append('نام صاحب حساب معرفی‌شده')
    if status == 'VOIDED' and not str(payload.get('cheque_void_reason187') or '').strip():
        missing.append('دلیل ابطال چک')
    if not missing or status == current:
        return 'apply'
    choice = _choose_cheque_incomplete_action_187(form, missing)
    return None if choice == 'cancel' else choice


def _open_resolution_record_187(form, pid):
    owner = form.master
    while owner is not None and getattr(owner, 'approval_center', None) is None:
        owner = getattr(owner, 'master', None)
    item = DB.get_pending_item(str(pid))
    if owner is not None and item:
        owner.approval_center.open_editor(item, navigation_rows=[item])


def _loan_saver_owner_187(form):
    """The dashboard that saves a loan (its loan tab). The record window is a window of its own, so
    its own toplevel is not it: look up the chain of parents the way _open_resolution_record_187 does."""
    widget = form
    while widget is not None:
        if callable(getattr(widget, '_save_loan_edit_187', None)):
            return widget
        widget = getattr(widget, 'master', None)
    return None


def _editor_approve_187(self):
    if getattr(self, '_approved_editor_182', False):
        return
    try:
        payload = self.payload_from_form()
        payload['v18_manual_fields'] = sorted(self.manual_fields)
        if not _confirm_debt_warning_187(self, payload):
            return
        if not _confirm_late_penalty_187(self, payload):
            return
        if getattr(self, '_cheque_record_session187', None) is not None:
            import sys
            session = self._cheque_record_session187
            action = _manual_status_action_187(self, session.cheque_id, payload)
            if action is None:
                return
            result = session.approve(payload, sys.modules[__name__], require_details=(action == 'apply'))
            if action == 'open' and getattr(session, 'resolution_pid', None):
                self.after(0, lambda pid=session.resolution_pid: _open_resolution_record_187(self, pid))
        elif _is_cheque_clearing_187(self.title_var.get(), self.subtype_var.get()):
            result = _submit_cheque_clearing_187(self.pid, payload, self.rich)
        elif _is_cheque_resolution_187(self.title_var.get(), self.subtype_var.get(), payload):
            result = _approve_cheque_resolution_187(self.pid, payload)
        elif _is_facility_payload_187(self.title_var.get(), self.subtype_var.get()):
            from transaction_lifecycle import TransactionLifecycle
            lifecycle = TransactionLifecycle(DB).get(str(self.pid))
            loan_id = ''
            if lifecycle and lifecycle.get('state') == 'ACTIVE':
                for effect in json.loads(lifecycle.get('effects_json') or '[]'):
                    if effect.get('table') == 'loans' and effect.get('after'):
                        loan_id = str(effect['after'].get('loan_id') or '')
                        if loan_id:
                            break
            if loan_id:
                owner = _loan_saver_owner_187(self)
                if owner is None:
                    raise ValueError('فرم اصلی تسهیلات برای همگام‌سازی رکورد پیدا نشد.')
                result = owner._save_loan_edit_187({'loan_id': loan_id}, payload)
            else:
                result = v18.submit_v18(self.pid, payload, self.rich)
        else:
            result = v18.submit_v18(self.pid, payload, self.rich)
    except Exception as exc:
        return messagebox.showerror('تأیید انجام نشد', str(exc), parent=self)
    self.payload = payload
    self._record_drafts187.pop(self.pid, None)
    self._approved_editor_182 = True
    self._navigation_baseline_182 = self._navigation_values_182()
    self.msg.set(f'ثبت شد — {result}')
    self._confirm_button_182.configure(text='ثبت شد', state='disabled')
    try:
        self.on_done()
    except Exception as exc:
        self.msg.set(f'ثبت شد؛ تازه‌سازی فهرست با خطا روبه‌رو شد: {exc}')


CHEQUE_INFO_KEYS_187 = ('issuer_name', 'receiver_name', 'issuer_bank', 'cheque_serial', 'cheque_type',
                        'due_date_shamsi', 'is_guarantee')
CHEQUE_ISSUE_KEYS_187 = ('payer_name', 'payment_method', 'invoice_amount', 'final_amount', 'discount_amount',
                         'payment_state', 'total_debt', 'remaining_debt', 'main_phase', 'sub_phase')
CHEQUE_STATUS_KEYS_187 = ('cheque_registration_state', 'cheque_status')


def _cheque_record_mode_187(form):
    """'resolution' for a resolution record, 'cheque' for the record opened from the cheque tab (both
    records open for editing), 'issue' for an issue record. The window of each shows all three boxes of
    the cheque, and lets its own record change only its own box (the cheque tab's row both)."""
    operation = str(form.payload.get('cheque_operation187') or CHEQUE_OPERATION_ISSUE_187)
    if operation == CHEQUE_OPERATION_RESOLVE_187:
        return 'resolution'
    return 'cheque' if form.payload.get('_cheque_record_id187') else 'issue'


def _cheque_box_187(form, title):
    """One of the three boxes of a cheque record: «اطلاعات چک», «صدور چک», «تعیین تکلیف چک»."""
    card = v18.GlassSection(form.special_host, title)
    card.pack(fill='x', pady=(0, 8))
    card.body.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform='cheque187')
    return card.body


def _issue_summary_187(cheque_id):
    """What the issue record of a cheque says, for the box a resolution record shows of it: [(label, value)]."""
    from cheque_record_edit187 import pending_ids
    from transaction_lifecycle import is_resolution_payload
    for pid in pending_ids(DB, str(cheque_id or '')) if cheque_id else []:
        payload = (DB.get_pending_item(pid) or {}).get('payload') or {}
        if is_resolution_payload(payload):
            continue
        money = lambda key: group_int_fa(parse_int(payload.get(key) or 0))
        return [
            ('تاریخ صدور', fa(str(payload.get('event_date_shamsi') or '-'))),
            ('دسته‌بندی', str(payload.get('cost_group') or '-')),
            ('فاز اصلی', str(payload.get('main_phase') or '-')), ('فاز فرعی', str(payload.get('sub_phase') or '-')),
            ('مبلغ فاکتور', money('invoice_amount')), ('مبلغ نهایی', money('final_amount')),
            ('تخفیف', money('discount_amount')),
            ('وضعیت پرداخت', v18.CODE_TO_STATE.get(str(payload.get('payment_state') or '').upper(),
                                                  str(payload.get('payment_state') or '-'))),
        ]
    return []


def _fill_issue_summary_187(form, host):
    for widget in host.winfo_children():
        widget.destroy()
    palette = palette_187()
    items = _issue_summary_187((form.payload or {}).get('selected_cheque_id187'))
    if not items:
        tk.Label(host, text='رکورد صدور این چک پیدا نشد.', bg=palette['panel'], fg=palette['muted'],
                 anchor='e').grid(row=0, column=0, columnspan=4, sticky='e', padx=6, pady=6)
        return
    for index, (label, value) in enumerate(items):
        cell = tk.Frame(host, bg=palette['panel'])
        cell.grid(row=index // 4, column=3 - index % 4, sticky='nsew', padx=5, pady=4)
        cell.grid_columnconfigure(0, weight=1)
        tk.Label(cell, text=label, bg=palette['panel'], fg=palette['text'], anchor='e',
                 font=(form.font_family, form.font_size, 'bold')).grid(row=0, column=0, sticky='e')
        tk.Label(cell, text=value or '-', bg=palette['panel'], fg=palette['muted'], anchor='e',
                 font=(form.font_family, form.font_size)).grid(row=1, column=0, sticky='e')


def _sync_cheque_status_extras_187(form):
    """The return details of the status box: shown for «عودتی به شرط تسویه» and «باطل‌شده», as in the wizard."""
    variables, widgets = form.vars, form.widgets
    status = variables.get('cheque_status')
    if status is None:
        return
    label = str(status.get() or '')
    show_return = label in {'عودتی به شرط تسویه', 'باطل‌شده'}
    for key, show in (('cheque_return_disposition187', show_return),
                      ('cheque_return_account_holder187', label == 'عودتی به شرط تسویه'),
                      ('cheque_void_reason187', label == 'باطل‌شده')):
        widget = widgets.get(key)
        if widget is None:
            continue
        try:
            (widget.master.grid if show else widget.master.grid_remove)()
        except (AttributeError, tk.TclError):
            pass
    if getattr(form, '_cheque_status_extras_trace187', None) is not status:
        form._cheque_status_extras_trace187 = status
        status.trace_add('write', lambda *_args, target=form: _sync_cheque_status_extras_187(target))


def _cheque_box_hint_187(form, box, row, text):
    palette = palette_187()
    tk.Label(box, text=text, bg=palette['panel'], fg=palette['muted'], anchor='e', justify='right', wraplength=620,
             font=(form.font_family, max(8, form.font_size - 1))).grid(row=row, column=0, columnspan=4, sticky='e',
                                                                        padx=6, pady=(2, 4))


def _lock_cheque_fields_187(form, keys):
    """A record changes its own part of the cheque only: the other part is shown, not editable."""
    for key in keys:
        widget = form.widgets.get(key)
        if widget is None:
            continue
        for target in (widget, *widget.winfo_children()):
            try:
                target.configure(state='disabled')
            except (tk.TclError, AttributeError):
                pass


def _editor_build_cheque_187(self):
    """The record window of a cheque, in the wizard's own terms: «اطلاعات چک» (what the cheque is),
    «صدور چک» (what its issue booked) and «تعیین تکلیف چک» (what became of it), one box each."""
    if getattr(self, '_special_initialized', False):
        self.payload = self._payload_from_vars('هزینه ساخت', 'چک')
    for widget in self.special_host.winfo_children():
        widget.destroy()
    keep = {'event_date_shamsi', 'amount', 'v18_title', 'v18_subtype', 'cost_group', 'contract_id'}
    self.vars = {key: value for key, value in self.vars.items() if key in keep}
    self.widgets = {key: value for key, value in self.widgets.items() if key in keep}
    operation = str(self.payload.get('cheque_operation187') or CHEQUE_OPERATION_ISSUE_187)
    if operation == CHEQUE_OPERATION_RESOLVE_187:
        _own_resolved_cheque_187(self)
    mode = _cheque_record_mode_187(self)
    approved = str((DB.get_pending_item(self.pid) or {}).get('status')) in ('APPROVED', 'EDIT_PENDING')
    fields = {field.key: field for field in _special_fields_187('هزینه ساخت', 'چک')}
    # The operation is no choice of this window (it is the record's own), but the form still carries it.
    self.vars['cheque_operation187'] = tk.StringVar(value=operation)
    info = _cheque_box_187(self, 'اطلاعات چک')
    issue = _cheque_box_187(self, 'صدور چک')
    resolution = (_cheque_box_187(self, 'تعیین تکلیف چک')
                  if mode in ('resolution', 'cheque') or (mode == 'issue' and approved) else None)
    if mode == 'resolution':
        for index, field in enumerate(_cheque_resolution_detail_fields_187()):
            self._field(info, field, index // 4, 3 - index % 4)
        summary = tk.Frame(issue, bg=palette_187()['panel'])
        summary.grid(row=0, column=0, columnspan=4, sticky='nsew')
        for column in range(4):
            summary.grid_columnconfigure(column, weight=1, uniform='cheque187')
        self._issue_summary_host187 = summary
        _fill_issue_summary_187(self, summary)
        _cheque_box_hint_187(self, issue, 1, 'مشخصات صدور را رکورد صدور یا ردیف چک در تب چک‌ها تغییر می‌دهد، نه رکورد تعیین تکلیف.')
        self._field(resolution, v18.FieldDef('selected_cheque_id187', 'انتخاب چک', 'cheque_picker'), 0, 0)
        self.widgets['selected_cheque_id187'].master.master.grid_configure(columnspan=4, sticky='nsew')
        _populate_clearing_cheque_picker_187(self)
        try:
            _seed_cheque_resolution_payload187(self)
        except ValueError:
            pass  # The operator may select a cheque next.
        status_fields = _cheque_resolution_status_fields_187()
        for index, field in enumerate(status_fields):
            self._field(resolution, field, 1 + index // 2, 2 if index % 2 == 0 else 0)
        self._loading = True
        try:
            for field in (*_cheque_resolution_detail_fields_187(), *status_fields):
                value = self.payload.get(field.key, '')
                self.vars[field.key].set(group_int_fa(value) if field.kind == 'money' else str(value or ''))
        finally:
            self._loading = False
        _sync_cheque_resolution_optional_fields_187(self)

        def selected(_event=None):
            if getattr(self, '_loading', False):
                return
            try:
                _seed_cheque_resolution_payload187(self)
            except ValueError:
                return
            for field in _cheque_resolution_detail_fields_187():
                value = self.payload.get(field.key, '')
                self.vars[field.key].set(group_int_fa(value) if field.kind == 'money' else str(value or ''))
            _fill_issue_summary_187(self, self._issue_summary_host187)
            _right_align_form_187(self)

        self.widgets['selected_cheque_id187'].bind('<<TreeviewSelect>>', selected, add='+')
        _right_align_form_187(self)
    else:
        for index, key in enumerate(CHEQUE_INFO_KEYS_187):
            if key in fields:
                self._field(info, fields[key], index // 4, 3 - index % 4)
        issue_keys = list(CHEQUE_ISSUE_KEYS_187)
        status_keys = [key for key in CHEQUE_STATUS_KEYS_187 if key in fields]
        # before the cheque is approved its two statuses are part of the issue; after, they are its resolution
        if resolution is None:
            issue_keys += status_keys
        for index, key in enumerate(key for key in issue_keys if key in fields):
            self._field(issue, fields[key], index // 4, 3 - index % 4)
        if resolution is not None:
            for index, key in enumerate(status_keys):
                self._field(resolution, fields[key], 0, 3 - index)
        self._load_values('هزینه ساخت', 'چک')
        if resolution is not None:
            extra = [
                v18.FieldDef('cheque_return_disposition187', 'وضعیت عودت چک', 'combo', CHEQUE_RETURN_DISPOSITION_CHOICES_187),
                v18.FieldDef('cheque_return_account_holder187', 'نام صاحب حساب معرفی‌شده'),
                v18.FieldDef('cheque_void_reason187', 'دلیل ابطال چک'),
            ]
            for index, field in enumerate(extra):
                self._field(resolution, field, 1, 3 - index)
                default = CHEQUE_RETURN_DISPOSITION_CHOICES_187[3] if index == 0 else ''
                self.vars[field.key].set(str(self.payload.get(field.key) or default))
            _sync_cheque_status_extras_187(self)
            if mode == 'issue':
                # the issue record shows what became of the cheque, it does not change it
                _lock_cheque_fields_187(self, (*status_keys, *(field.key for field in extra)))
                _cheque_box_hint_187(self, resolution, 2,
                                     'این بخش را رکورد تعیین تکلیف یا ردیف چک در تب چک‌ها تغییر می‌دهد، نه رکورد صدور.')
    category = self.vars.get('cost_group')
    if category is not None and not str(category.get() or '').strip():
        self._loading = True
        try:
            category.set(CHEQUE_DEFAULT_COST_GROUP_187)
        finally:
            self._loading = False
    if self.payload.get('_cheque_record_id187'):
        _editor_prepare_fields_187(self)
    _install_cheque_number_label_187(self)
    self._special_initialized = True

    def change_operation(*_args):
        if not getattr(self, '_loading', False):
            self.after_idle(lambda: _editor_build_cheque_187(self))
    self.vars['cheque_operation187'].trace_add('write', change_operation)


def _wrap_field_titles_187(body, form, keys, columns=4):
    """A title longer than its column wraps onto a second line instead of being cut at the edge."""
    boxes = [form.widgets[key].master for key in keys if key in form.widgets]

    def fit(_event=None):
        try:
            width = max(110, int(body.winfo_width() / columns) - 24)
            for box in boxes:
                for label in box.grid_slaves(row=0, column=0):
                    if isinstance(label, tk.Label):
                        label.configure(wraplength=width, justify='right')
        except tk.TclError:
            pass

    body.bind('<Configure>', fit, add='+')
    fit()


def _facility_grid_cells_187(rows, available, columns=4):
    """(key, grid row, column) of every field of `rows` that exists.

    Columns are filled from the right, like the other right-to-left forms; a row with more
    fields than the grid has columns goes on in the next grid row (it used to reach column -1).
    """
    grid_row = 0
    for keys in rows:
        present = [key for key in keys if key in available]
        for position, key in enumerate(present):
            yield key, grid_row + position // columns, columns - 1 - position % columns
        grid_row += max(1, -(-len(present) // columns))


def _layout_installment_record_187(form):
    """The loan picker's values are long, so the loan name takes two of the record's four columns."""
    loan = form.widgets.get('loan_id')
    if loan is not None:
        loan.master.grid_configure(column=1, columnspan=2)


def _editor_build_special_187(self, title, sub):
    self._rendered_title187 = title
    for key in ('cost_group', 'contract_id'):
        widget = self.widgets.get(key)
        if widget is not None and widget.master.master is getattr(self, 'cost_group_row', None):
            self._general_fields187[key] = (self.vars[key], widget)
    sub = _canonical_document_subtype_187(sub)
    event_date_widget = self.widgets.get('event_date_shamsi')
    if event_date_widget is not None:
        try:
            (event_date_widget.master.grid_remove if _is_facility_payload_187(title, sub)
             else event_date_widget.master.grid)()
        except (AttributeError, tk.TclError):
            pass
    if title == 'هزینه ساخت' and sub == 'چک':
        return _editor_build_cheque_187(self)
    if not _is_facility_payload_187(title, sub):
        result = _ORIGINAL_EDITOR_BUILD_SPECIAL_187(self, title, sub)
        if _is_cheque_clearing_187(title, sub):
            picker = self.widgets.get('selected_cheque_id187')
            mode = self.widgets.get('cheque_clearing_mode187')
            status = self.widgets.get('cheque_status')
            account = self.widgets.get('cheque_transfer_account_holder187')
            description = self.widgets.get('cheque_transfer_description187')
            if picker is not None:
                picker.master.master.grid_configure(row=0, column=0, columnspan=4, sticky='nsew')
            if mode is not None:
                mode.master.grid_configure(row=1, column=2, columnspan=2, sticky='nsew')
                mode.configure(state='readonly')
            if status is not None:
                status.master.grid_configure(row=1, column=0, columnspan=2, sticky='nsew')
                status.configure(state='readonly')
            if account is not None:
                account.master.grid_configure(row=2, column=2, columnspan=2, sticky='nsew')
            if description is not None:
                description.master.grid_configure(row=2, column=0, columnspan=2, sticky='nsew')
            _bind_clearing_mode_187(self)
            _sync_clearing_transfer_visibility_187(self)
        if title == 'هزینه ساخت' and sub == 'نقدی' and 'issuer_name' not in self.vars:
            card = self.special_host.winfo_children()[0]
            self._field(card.body, v18.FieldDef('issuer_name', 'صاحب حساب'), 0, 0, width=20)
            self.vars['issuer_name'].set(str(self.payload.get('issuer_name') or ''))
        if _is_nonfinancial_payload_187(title, sub):
            date_key = {
                'تقویم کارگاهی': 'calendar_date_shamsi',
                'گزارش روزانه': 'report_date_shamsi',
                'یادآوری': 'reminder_date_shamsi',
                'فاکتور': 'invoice_note_date_shamsi',
            }.get(sub)
            if date_key and self.vars.get(date_key) is not None:
                self.vars[date_key].trace_add('write', lambda *_args, target=self, key=date_key: _sync_document_event_date_187(target, key))
            if sub == 'گزارش روزانه' and self.vars.get('report_row_count') is not None:
                self.vars['report_row_count'].trace_add('write', lambda *_args, target=self: _refresh_report_rows_187(target))
                _refresh_report_rows_187(self)
        if title == 'ورودی' and sub == 'شرکا/قرض':
            card = self.special_host.winfo_children()[0]
            source = next(field for field in _special_fields_187(title, sub)
                          if field.key == 'partner_source')
            self._field(card.body, source, 1, 0, width=20)
            self._loading = True
            try:
                self.vars['partner_source'].set(str(self.payload.get('partner_source') or ''))
            finally:
                self._loading = False
            partner_name = self.vars.get('partner_name')
            if partner_name is not None:
                partner_name.trace_add(
                    'write', lambda *_args, target=self: _sync_partner_source_visibility_187(target))
            _sync_partner_source_visibility_187(self)
        if _is_installment_payload_187(title, sub):
            _layout_installment_record_187(self)
        _editor_prepare_fields_187(self)
        return result
    try:
        if getattr(self, '_special_initialized', False) and self.vars and 'event_date_shamsi' in self.vars:
            self.payload = self._payload_from_vars(self.title_var.get(), self.subtype_var.get())
    except Exception:
        pass
    for widget in self.special_host.winfo_children():
        widget.destroy()
    keep = {'event_date_shamsi', 'amount', 'v18_title', 'v18_subtype'}
    self.vars = {key: value for key, value in self.vars.items() if key in keep}
    self.widgets = {key: value for key, value in self.widgets.items() if key in keep}
    card = v18.GlassSection(self.special_host, f'{title} — {sub}')
    card.pack(fill='both', expand=True)
    body = card.body
    body.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform='facility187')
    by = {field.key: field for field in _special_fields_187(title, sub)}
    rows = [
        ['loan_bank', 'branch_name', 'borrower_name', 'guarantor_1', 'guarantor_2'],
        ['loan_start_date', 'loan_total_amount', 'loan_name', 'loan_title',
         'contract_number', 'interest_rate', 'bank_fees'],
        ['installment_count', 'installment_amount', 'total_interest',
         'first_due_date_shamsi', 'loan_end_date', 'last_paid_date_shamsi',
         'paid_installments_count', 'remaining_installments'],
    ]
    placed = list(_facility_grid_cells_187(rows, by))
    for key, grid_row, column in placed:
        self._field(body, by[key], grid_row, column, width=20)
    _wrap_field_titles_187(body, self, [key for key, _row, _column in placed])
    self._load_values(title, sub)
    self._special_initialized = True
    for key in ('loan_total_amount', 'amount', 'interest_rate', 'installment_count',
                'installment_amount', 'loan_start_date', 'first_due_date_shamsi'):
        var = self.vars.get(key)
        if var is not None:
            var.trace_add('write', lambda *_args, target=self, name=key: _sync_loan_fields_187(target, name))
    _sync_loan_fields_187(self)
    _editor_prepare_fields_187(self)


def _editor_title_changed_187(self):
    previous_title = getattr(self, '_rendered_title187', None)
    if (self.title_var.get() == LAND_TITLE) != (previous_title == LAND_TITLE):
        self.payload['plan_ref'] = ''
    if self.title_var.get() == LAND_TITLE and previous_title != LAND_TITLE:
        self.subtype_var.set(LAND_TITLE)
        self.payload[LAND_MODE_KEY] = 'همه موارد'
    return _ORIGINAL_EDITOR_TITLE_CHANGED_187(self)


v181.special_fields_181 = _special_fields_187
v18._special_fields = _special_fields_187
v182.wizard_steps_182 = _wizard_steps_187
v18._wizard_steps = _wizard_steps_187
SUBPHASE_MIN_WIDTH_187 = 40
SUBPHASE_MAX_WIDTH_187 = 72


def _widen_subphase_cell_187(box):
    """In the record's four-column grid the box spreads over the free columns beside it."""
    info = box.grid_info()
    if not info or int(info.get('columnspan') or 1) > 1:
        return
    column, row = int(info['column']), int(info['row'])
    taken = {int(slave.grid_info()['column']) for slave in box.master.grid_slaves(row=row) if slave is not box}
    free = 0
    while free < column and not taken & {column - free - 1}:
        free += 1
    if free:
        box.grid_configure(column=column - free, columnspan=free + 1)


def _refresh_subphase_187(self):
    """A construction cost lists only the plan lines of the category (مصالح، پیمانکار، خدمات) it was given,
    in a box wide enough to read them."""
    _ORIGINAL_REFRESH_SUBPHASE_187(self)
    widget = getattr(self, 'widgets', {}).get('sub_phase')
    category_var = getattr(self, 'vars', {}).get('cost_group')
    if widget is None:
        return
    try:
        if category_var is not None:
            cost_type = cost_type_of_187(category_var.get())
            if cost_type:
                phase = phase_of_187(self.vars['main_phase'].get()) if 'main_phase' in self.vars else None
                rows = self.rich.subphase_candidates(phase, '')
                widget.set_all([row['description'] for row in rows
                                if norm(row.get('cost_type')) == norm(cost_type)])
        longest = max((len(str(value)) for value in getattr(widget, '_all', ()) or ()), default=0)
        widget.configure(width=min(SUBPHASE_MAX_WIDTH_187, max(SUBPHASE_MIN_WIDTH_187, longest + 4)))
        _widen_subphase_cell_187(widget.master)
    except (AttributeError, KeyError, tk.TclError, ValueError):
        pass


v18.DynamicFormMixin._refresh_subphase = _refresh_subphase_187
v18.DynamicFormMixin._load_values = _load_entry_values_187
v18.DynamicFormMixin._init_dynamic = _init_dynamic_187
v18.DynamicFormMixin._payload_from_vars = _payload_values_187
v18.DynamicFormMixin._field = _dynamic_field_with_installments_187
v18.UnifiedPendingEditor18._installment_count_sync = _installment_count_sync_187
v182.TransactionWizard182._installment_count_sync_182 = _installment_count_sync_187
v18.DynamicFormMixin._loan_selected = _loan_selected_187
v182.TransactionWizard182._loan_selected = _loan_selected_187
v18.DynamicFormMixin._mark_manual = _mark_manual_187
v182.TransactionWizard182._payload_from_vars = _wizard_payload_values_187
v182.TransactionWizard182._build_shell = _wizard_build_shell_187
v182.TransactionWizard182._show_page = _wizard_show_page_187
v182.TransactionWizard182._render_review = _wizard_render_review_187
v182.TransactionWizard182._title_changed = _wizard_title_changed_187
v182.TransactionWizard182.__init__ = _wizard_init_187
v182.TransactionWizard182._sub_changed = _wizard_sub_changed_187
v182.TransactionWizard182._cancel_187 = _wizard_cancel_187
v182.TransactionWizard182._open_full = _wizard_open_full_187
v182.TransactionWizard182._after_page_render = _wizard_after_render_187
v182.TransactionWizard182._capture = _wizard_capture_187
v182.TransactionWizard182.next = _wizard_next_187
v182.TransactionWizard182.prev = _wizard_prev_187
v182.UnifiedPendingEditor182._build_special = _editor_build_special_187
v182.UnifiedPendingEditor182._title_changed = _editor_title_changed_187
v182.UnifiedPendingEditor182._build = _editor_build_187
v182.UnifiedPendingEditor182._load_evidence = _editor_evidence_187
v182.UnifiedPendingEditor182._payload_from_vars = _editor_payload_values_187
v182.UnifiedPendingEditor182.__init__ = _editor_init_187
v182.UnifiedPendingEditor182._navigation_values_182 = _editor_navigation_values_187
v182.UnifiedPendingEditor182._reload_record_182 = _editor_reload_187
v182.UnifiedPendingEditor182._navigate_record_182 = _editor_navigate_187
v182.UnifiedPendingEditor182.approve = _editor_approve_187
v182.UnifiedPendingEditor182._mark_manual = _editor_mark_manual_187


class LoanEditWizard187(v182.TransactionWizard182):
    """Wizard-shaped editor that updates an existing loan instead of posting a copy."""
    def __init__(self, parent, row, rich, on_save):
        self._loan_row_187 = dict(row or {})
        self._loan_save_187 = on_save
        super().__init__(parent, dict(row or {}), rich, lambda: None, lambda: None)
        self.title('ویرایش تسهیلات — BARKAV 19.1.1')
        self.after_idle(lambda: _place_window_right_187(self, parent))

    def next(self):
        if self.page_index < len(self.pages) - 1:
            return super().next()
        try:
            self._capture()
            self._validate_current()
            payload = _payload_values_187(self, self.title_var.get(), self.subtype_var.get())
            self._loan_save_187(self._loan_row_187, payload)
            self.destroy()
        except Exception as exc:
            messagebox.showerror('ویرایش تسهیلات', str(exc), parent=self)


class LoanDetailsWindow187(BarkavWindow):
    """Read-only loan terms, installment schedule and the linked output payments."""
    def __init__(self, parent, loan_id):
        super().__init__(parent, 'جزئیات تسهیلات', size_class='large', show_footer=False)
        self.loan_id = str(loan_id or '').split('|', 1)[0].strip()
        self.loan = LoanService(DB).get_loan(self.loan_id) or {}
        self.installments = LoanService(DB).list_installments(self.loan_id)
        with DB.read() as con:
            self.payments = [dict(row) for row in con.execute(
                "SELECT * FROM transactions WHERE loan_id=? AND direction='OUT' "
                "AND COALESCE(UPPER(status),'POSTED') NOT IN ('VOIDED','CANCELLED','DELETED') "
                "ORDER BY COALESCE(shamsi_date,event_date),created_at,transaction_id",
                (self.loan_id,),
            ).fetchall()]
        self._build()

    @staticmethod
    def _money(value):
        return fa_grouped_number(parse_int(value or 0))

    def _build(self):
        palette = palette_187()
        info = tk.LabelFrame(self.body, text='مشخصات تسهیلات', bg=palette['panel'], fg=palette['text_primary'],
                             padx=10, pady=7, font=('Segoe UI', 10, 'bold'), labelanchor='ne')
        info.pack(fill='x', padx=10, pady=(10, 6))
        info.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform='loan_detail187')
        principal = parse_int(self.loan.get('principal_amount') or 0)
        count = parse_int(self.loan.get('installment_count') or 0)
        paid = sum(1 for item in self.installments if parse_int(item.get('paid_amount') or 0) > 0)
        first_due = str(self.loan.get('first_due_date_shamsi') or '')
        last_due = ''
        if first_due and count:
            try:
                last_due = gregorian_to_shamsi(
                    _add_months(date.fromisoformat(shamsi_to_gregorian(first_due)), count - 1))
            except Exception:
                last_due = ''
        last_paid = max((str(item.get('paid_date_shamsi') or '') for item in self.installments
                         if item.get('paid_date_shamsi')), default='')
        guarantors = [part.strip() for part in str(self.loan.get('guarantors') or '').split('|')]
        values = [
            ('نام وام‌گیرنده', self.loan.get('borrower_name') or '-'),
            ('بانک', self.loan.get('lender_name') or '-'),
            ('شعبه', self.loan.get('branch_name') or '-'),
            ('نام ضامن اول', guarantors[0] if guarantors and guarantors[0] else '-'),
            ('نام ضامن دوم', guarantors[1] if len(guarantors) > 1 and guarantors[1] else '-'),
            ('نام وام', self.loan.get('loan_name') or str(principal)[:4]),
            ('عنوان وام', self.loan.get('description') or '-'),
            ('شماره تسهیلات', self.loan.get('contract_number') or '-'),
            ('تاریخ اخذ وام', self.loan.get('received_date_shamsi') or '-'),
            ('مبلغ درخواست', self._money(principal)),
            ('مبلغ واریزی', self._money(self.loan.get('net_received_amount'))),
            ('سود و کارمزد', self._money(parse_int(self.loan.get('total_interest') or 0)
                                         + parse_int(self.loan.get('bank_fees') or 0))),
            ('درصد سود', f"{self.loan.get('interest_rate') or 0}%"),
            ('مبلغ هر قسط', self._money(self.loan.get('installment_amount'))),
            ('تعداد اقساط', fa(count)),
            ('اقساط پرداختی / باقی‌مانده', f'{fa(paid)} / {fa(max(0, count-paid))}'),
            ('اولین / آخرین سررسید', f'{first_due or "-"} / {last_due or "-"}'),
            ('آخرین قسط پرداختی', last_paid or '-'),
        ]
        for index, (label, value) in enumerate(values):
            cell = tk.Frame(info, bg=palette['panel'])
            cell.grid(row=index // 4, column=3 - index % 4, sticky='ew', padx=6, pady=5)
            tk.Label(cell, text=label, bg=palette['panel'], fg=palette['muted'], anchor='e',
                     font=('Segoe UI', 9, 'bold')).pack(fill='x', anchor='e')
            tk.Label(cell, text=str(value), bg=palette['panel'], fg=palette['text_primary'], anchor='e',
                     justify='right', wraplength=250, font=('Segoe UI', 9)).pack(fill='x', anchor='e')

        toolbar = tk.Frame(self.body, bg=palette['surface'])
        toolbar.pack(fill='x', padx=10, pady=(0, 6))
        self.export_choice = tk.StringVar(value='خروجی')
        ttk.Combobox(toolbar, textvariable=self.export_choice,
                     values=('خروجی', 'PDF', 'Excel', 'پرینت'), state='readonly',
                     justify='right', width=16).pack(side='right', padx=4, pady=5)
        ttk.Button(toolbar, text='پیش‌نمایش خروجی', command=self._preview).pack(side='right', padx=4, pady=5)
        # the totals line is packed first so a window too short for both tables never loses it
        paid_sum = sum(parse_int(item.get('paid_amount') or 0) for item in self.installments)
        tk.Label(self.body, text=f"جمع مبلغ اقساط: {self._money(sum(parse_int(item.get('amount') or 0) for item in self.installments))}"
                 f"    |    جمع پرداخت اقساط: {self._money(paid_sum)}"
                 f"    |    تعداد اقساط: {fa(count)}    |    پرداخت‌شده: {fa(paid)}",
                 bg=palette['surface'], fg=palette['text_primary'], anchor='e', font=('Segoe UI', 10, 'bold')).pack(
                     side='bottom', fill='x', padx=14, pady=(0, 10))
        self.tabset = ttk.Notebook(self.body)
        self.tabset.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        installment_tab = ttk.Frame(self.tabset, padding=6)
        payment_tab = ttk.Frame(self.tabset, padding=6)
        self.tabset.add(installment_tab, text='اقساط')
        self.tabset.add(payment_tab, text='واریزی‌ها در خروجی')
        self.installment_tree = self._table(installment_tab, (
            ('number', 'ردیف قسط', 95), ('due', 'تاریخ سررسید', 125),
            ('amount', 'مبلغ قسط', 150), ('paid', 'پرداخت‌شده', 150),
            ('remaining', 'مانده قسط', 150), ('paid_date', 'تاریخ پرداخت', 125),
            ('status', 'وضعیت', 140), ('transaction', 'شناسه تراکنش خروجی', 190),
        ))
        self.payment_tree = self._table(payment_tab, (
            ('date', 'تاریخ', 125), ('amount', 'مبلغ واریزی', 165),
            ('receiver', 'گیرنده', 180), ('description', 'شرح', 330),
            ('status', 'وضعیت', 115), ('transaction', 'شناسه تراکنش', 200),
        ))
        self._installment_rows = []
        for index, item in enumerate(self.installments, 1):
            amount = parse_int(item.get('amount') or 0)
            paid_amount = parse_int(item.get('paid_amount') or 0)
            status_map = {'PAID': 'پرداخت‌شده', 'PARTIALLY_PAID': 'پرداخت بخشی',
                          'OVERDUE': 'معوق', 'DUE': 'سررسید امروز', 'UPCOMING': 'در انتظار',
                          'CANCELLED': 'لغوشده'}
            values = (fa(index), fa(str(item.get('due_date_shamsi') or '')),
                      self._money(amount), self._money(paid_amount), self._money(max(0, amount-paid_amount)),
                      fa(str(item.get('paid_date_shamsi') or '')),
                      status_map.get(str(item.get('status') or '').upper(), str(item.get('status') or '-')),
                      str(item.get('transaction_id') or '-'))
            self._installment_rows.append(values)
            self.installment_tree.insert('', 'end', values=values)
        self._payment_rows = []
        for item in self.payments:
            values = (fa(str(item.get('shamsi_date') or item.get('event_date') or '')),
                      self._money(item.get('amount')), item.get('receiver_name') or '-',
                      item.get('description') or '-', item.get('status') or '-', item.get('transaction_id') or '-')
            self._payment_rows.append(values)
            self.payment_tree.insert('', 'end', values=values)

    @staticmethod
    def _table(parent, columns):
        shell = ttk.Frame(parent)
        shell.pack(fill='both', expand=True)
        keys = tuple(key for key, _label, _width in columns)
        tree = ttk.Treeview(shell, columns=keys, show='headings')
        vertical = ttk.Scrollbar(shell, orient='vertical', command=tree.yview)
        horizontal = ttk.Scrollbar(shell, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        for key, label, width in columns:
            tree.heading(key, text=label, anchor='e')
            tree.column(key, width=width, minwidth=75, anchor='e', stretch=True)
        tree.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=1)
        return tree

    def _preview(self):
        selected = str(self.export_choice.get() or '')
        if selected not in {'PDF', 'Excel', 'پرینت'}:
            return messagebox.showinfo('خروجی تسهیلات', 'قالب خروجی را انتخاب کن.', parent=self)
        if self.tabset.select() == str(self.tabset.tabs()[0]):
            headers = ['ردیف قسط', 'تاریخ سررسید', 'مبلغ قسط', 'پرداخت‌شده',
                       'مانده قسط', 'تاریخ پرداخت', 'وضعیت', 'شناسه تراکنش خروجی']
            rows = self._installment_rows
            caption = 'برنامه اقساط تسهیلات'
        else:
            headers = ['تاریخ', 'مبلغ واریزی', 'گیرنده', 'شرح', 'وضعیت', 'شناسه تراکنش']
            rows = self._payment_rows
            caption = 'واریزی‌های تسهیلات در خروجی'
        total = sum(parse_int(item.get('amount') or 0) for item in
                    (self.installments if caption == 'برنامه اقساط تسهیلات' else self.payments))
        return show_export_preview_187(
            self, export_format=selected, headers=headers, rows=rows,
            title=f'پیش‌نمایش {caption}', table_caption=caption, row_label='ردیف',
            include_addressee=True,
            on_confirm=lambda choice, orientation, addressee, include_documents:
                self._save_export(choice, orientation, addressee, headers, rows, total),
            specs=[('تسهیلات', 'مبلغ مرتبط', self._money(total))],
        )

    def _save_export(self, selected, orientation, addressee, headers, rows, total):
        if selected not in {'Excel', 'PDF', 'پرینت'}:
            return False
        from export_utils import export_pdf, export_xlsx, print_file
        suffix = '.xlsx' if selected == 'Excel' else '.pdf'
        path = filedialog.asksaveasfilename(
            parent=self, title='خروجی تسهیلات', defaultextension=suffix,
            filetypes=[('Excel', '*.xlsx')] if suffix == '.xlsx' else [('PDF', '*.pdf')],
        )
        if not path:
            return False
        summary = [f'جهت ارائه به: {addressee}', f'جمع: {self._money(total)}']
        if selected == 'Excel':
            export_xlsx(Path(path), headers, rows, title='گزارش تسهیلات', summary_lines=summary)
        else:
            export_pdf(Path(path), headers, rows, title='گزارش تسهیلات',
                       summary_lines=summary, orientation=orientation)
            if selected == 'پرینت':
                print_file(Path(path))
        messagebox.showinfo('خروجی تسهیلات', f'فایل ساخته شد:\n{path}', parent=self)
        return True


def _place_window_right_187(window, parent, width=820, height=650):
    try:
        window.update_idletasks()
        current_w = max(width, int(window.winfo_width() or width))
        current_h = max(height, int(window.winfo_height() or height))
        screen_w = int(window.winfo_screenwidth())
        screen_h = int(window.winfo_screenheight())
        x = max(0, screen_w - current_w - 18)
        y = max(0, (screen_h - current_h) // 2)
        window.geometry(f'{current_w}x{current_h}+{x}+{y}')
    except tk.TclError:
        pass


class Stage187Dashboard(v186.Stage186Dashboard):
    # Contractors sits directly after sales in the right-hand nav rail.
    _VISIBLE_NAV = (
        'داشبورد', 'ثبت دیتا', 'تراکنش‌ها', SALES_TAB_187,
        'پیمانکاران', REPORTS_TAB_187, 'حساب مدیر',
    )

    def __init__(self):
        activate_theme_bridge_187()
        v186.DARK_186.update(palette_187(False))
        v186.LIGHT_186.update(palette_187(True))
        self._startup_reminder_shown_187 = False
        self._project_calendar_window187 = None
        # project_runner_stage18_7.run_project sets these before importing
        # this module (apply_project_environment) - this process is one
        # project's dashboard, spawned fresh per open project, so there is
        # no constructor argument to carry them in through.
        self._barkav_project_id187 = os.environ.get('PEYMAAN_ACTIVE_PROJECT_ID')
        self._barkav_project_name187 = os.environ.get('PEYMAAN_ACTIVE_PROJECT_NAME') or 'پروژه'
        super().__init__()
        self.title(f'BARKAV — Engineering & Construction — Version {DISPLAY_VERSION_187}')
        self.after_idle(self._finalize_187)
        self.after(1300, self._show_startup_reminders_187)
        self.after(2600, self._red_line_check_187)

    def _red_line_check_187(self):
        """RED LINE (record_ownership187): the running app tells when a financial row has no record behind it."""
        from finance_db import FinanceDB
        if not FinanceDB.enforce_record_context:
            return
        try:
            from record_ownership187 import orphan_rows
            orphans = orphan_rows(DB)
        except Exception:
            logging.getLogger(__name__).exception('Red-line audit could not run')
            return
        if not orphans:
            return
        logging.getLogger(__name__).warning('Financial rows without a Data Entry record: %s',
                                            ', '.join(f"{row['table']}:{row['key']}" for row in orphans))
        messagebox.showwarning(
            'خط قرمز ثبت دیتا',
            f'{fa(len(orphans))} ردیف مالی پیدا شد که هیچ رکورد ثبت دیتایی پشت آن نیست. '
            'این ردیف‌ها نباید وجود داشته باشند؛ فهرست آن‌ها را با ابزار tools/audit_ledger_ownership.py ببین.',
            parent=self)

    def _cheque_display_status(self, row):
        """The group a cheque row falls into when the cheque tab is filtered by status.

        «عودتی به شرط تسویه» is stored as status RETURNED + RETURNED_ON_SETTLEMENT, which the inherited filter
        would file under «برگشتی». Nothing is owed through such a cheque, so the filter «پاس‌شده» lists it too
        (its own filter still lists it alone, and the status column keeps saying what it is)."""
        mode = str(row.get('settlement_mode') or '').upper()
        if mode == 'REPLACED_BY_TRANSFER':
            return 'عودتی'
        label = 'عودتی به شرط تسویه' if mode == 'RETURNED_ON_SETTLEMENT' else super()._cheque_display_status(row)
        chosen = getattr(self, 'ch_filter', None)
        if label == 'عودتی به شرط تسویه' and chosen is not None and chosen.get() == 'پاس‌شده':
            return 'پاس‌شده'
        return label

    def _approval_periodic(self):
        """Replace Stage 14's unconditional 4 s full redraw of ثبت دیتا.

        The inherited loop called ``approval_center.refresh()`` every four
        seconds whether or not anything changed or the tab was even open; that
        rebuild (rows, widths, separators, contractors) blocks the Tk loop for
        seconds and was the main source of idle CPU and tab-switch freezes.
        Now only the cheap pending-review marker is read and a redraw happens
        only when it actually changed.
        """
        try:
            center = getattr(self, 'approval_center', None)
            marker_of = getattr(center, '_pending_review_marker_187', None)
            if marker_of is not None and not getattr(center, '_data_entry_poll_active187', False):
                # While ثبت دیتا is visible its own _periodic already polls.
                if marker_of() != getattr(center, '_last_data_entry_pending_marker187', None):
                    center.refresh()
        except Exception:
            logging.getLogger(__name__).exception('Could not check Data Entry pending marker')
        finally:
            self.after(4000, self._approval_periodic)

    def _overview_page_187(self):
        page = getattr(self, '_overview_page187', None)
        if page is not None:
            return page
        try:
            for tab in self.notebook.tabs():
                if str(self.notebook.tab(tab, 'text')).strip() == 'داشبورد':
                    page = self.notebook.nametowidget(tab)
                    page.bind('<Map>', self._overview_mapped_187, add='+')
                    self._overview_page187 = page
                    return page
        except (tk.TclError, KeyError, AttributeError):
            pass
        return None

    def _overview_mapped_187(self, _event=None):
        if getattr(self, '_overview_dirty187', False):
            self._overview_dirty187 = False
            self.after_idle(self.refresh_overview)

    def _periodic(self):
        """Stage 12's 15 s overview refresh, only while داشبورد is on screen.

        refresh_overview() recomputes every card and chart (~1.5 s of blocked
        UI); running it behind ثبت دیتا or any other tab froze navigation for
        nothing. When hidden it is deferred until the page is shown again.
        """
        try:
            page = self._overview_page_187()
            if page is None or page.winfo_ismapped():
                self.refresh_overview()
            else:
                self._overview_dirty187 = True
        except Exception:
            logging.getLogger(__name__).exception('Could not refresh overview')
        finally:
            self.after(15000, self._periodic)

    def _style(self):
        super()._style()
        ui = load_ui()
        style_ttk_187(
            self,
            light=str(ui.get('appearance') or 'dark').lower() == 'light',
            font_size=int(ui.get('font_size') or 10),
            row_height=int(ui.get('row_height') or theme_metrics_187()['row_height']),
        )

    def _build(self):
        """Rearrange the inherited widgets into the 18.7 shell without duplicating them."""
        super()._build()
        self._build_contractors_187()
        self._install_shell_187()

    def _build_overview(self):
        """Build the inherited dashboard with the active 18.7 styling."""
        super()._build_overview()
        self._install_dashboard_card_interactions_187()
        self._ensure_physical_progress_card_187()
        self._replace_phase_buttons_with_rounded_187()

    def _install_phase_legend_187(self, phase_card):
        """Explain phase status colours instead of leaving a green state unexplained."""
        existing = getattr(self, 'phase_legend187', None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    return existing
            except tk.TclError:
                pass
        try:
            header = next(child for child in phase_card.winfo_children()
                          if isinstance(child, tk.Frame))
        except (StopIteration, tk.TclError):
            return None
        p = palette_187()
        legend = tk.Label(
            header,
            text='راهنما: سبز = فعال/تکمیل • زرد = متوقف • خاکستری = شروع‌نشده',
            bg=p['surface_alt'], fg=p['text_muted'], anchor='w',
            font=dashboard_font_187(self, 7, 'body'),
        )
        legend._phase_legend187 = True
        legend.pack(side='left', padx=(8, 4))
        self.phase_legend187 = legend
        return legend

    def _replace_phase_buttons_with_rounded_187(self):
        """Swap only the 32 legacy phase buttons for true rounded Canvas controls."""
        strip = getattr(self, 'phase_strip', None)
        buttons = getattr(self, 'phase_buttons', None)
        if strip is None or not buttons:
            return
        p = palette_187()
        for number, legacy_button in tuple(buttons.items()):
            if isinstance(legacy_button, RoundedPhaseButton187):
                legacy_button._page = p['card']
                legacy_button._border = p['border_subtle']
                legacy_button.configure(cursor='hand2')
                continue
            try:
                grid = legacy_button.grid_info()
                fill = legacy_button.cget('bg')
                foreground = legacy_button.cget('fg')
            except tk.TclError:
                continue
            button = RoundedPhaseButton187(
                strip,
                number=int(number),
                command=lambda n=number: self.open_phase_by_no(n),
                edit_command=lambda n=number: self.edit_phase_progress(n),
                page=p['card'], fill=fill, foreground=foreground,
                border=p['border_subtle'],
            )
            button.grid(
                row=int(grid.get('row', 0)), column=int(grid.get('column', int(number) - 1)),
                rowspan=int(grid.get('rowspan', 1)), columnspan=int(grid.get('columnspan', 1)),
                sticky=grid.get('sticky', 'nsew'), padx=grid.get('padx', 1), pady=grid.get('pady', 0),
            )
            legacy_button.destroy()
            buttons[number] = button

    def refresh_phase_strip(self):
        """Repaint the ۳۲-phase strip with the theme's own tokens.

        The inherited version (dashboard_stage16_3) hardcoded four dark-only
        hex pairs, so a light-theme user saw the same four colours the dark
        theme uses - never matching the rest of a light screen. It also mixed
        numeral systems: Persian digits at build time, plain Latin ones the
        moment this method first repainted them. barkav_themes/tokens.py
        already carries phase_not_started/active/paused/completed for
        exactly this state, in both theme modes; this just reads them
        instead of relying on inherited literals never wired to figure them.
        Buttons stay RoundedPhaseButton187 instances throughout - that widget
        keeps the plain-Button configure()/cget() API, so this can set
        bg/fg/text on it exactly as it would on the inherited tk.Button.
        """

        p = palette_187()
        prog = self.rich.get_phase_progress()
        colors = {
            'NOT_STARTED': (p['phase_not_started'], p['muted']),
            'ACTIVE': (p['phase_active'], p['text_primary']),
            'PAUSED': (p['phase_paused'], p['text_primary']),
            'COMPLETED': (p['phase_completed'], p['text_primary']),
        }
        for number, button in getattr(self, 'phase_buttons', {}).items():
            info = prog.get(number, {})
            status = info.get('status', 'NOT_STARTED')
            percent = float(info.get('physical_progress') or 0)
            bg, fg = colors.get(status, colors['NOT_STARTED'])
            tail = fa(f'{percent:.0f}%') if percent else ''
            button.configure(bg=bg, fg=fg, text=f"{fa(f'{number:02d}')}\n{tail}")
        self.overall_progress.set(self.rich.overall_physical_progress())
        self._replace_phase_buttons_with_rounded_187()

    _DASHBOARD_CARD_GROUPS_187 = {
        'total_in': 'تراکنش‌ها',
        'ch_all_total': 'چک‌ها',
        'loan_principal': 'تسهیلات',
        'sales_contract': 'فروش و مطالبات',
        'liq_obligation': '۳۰ روز آینده',
    }

    def _issued_cheques_by_contract_187(self, cheque_rows):
        """Map upcoming issued cheques to their approval payload's contract."""
        return liquidity_service.issued_cheques_by_contract(
            getattr(SERVICE, 'db', DB), cheque_rows)

    def _thirty_day_summary_187(self):
        """The five cash commitments requested for the ۳۰ روز آینده dialog."""
        return liquidity_service.thirty_day_summary(
            SERVICE, load_contracts(), db=getattr(SERVICE, 'db', DB),
            to_gregorian=shamsi_to_gregorian,
        )

    def _install_dashboard_card_interactions_187(self):
        """Keep navigation and detail links on each card header only."""
        for key, group in self._DASHBOARD_CARD_GROUPS_187.items():
            metric = getattr(self, 'cards', {}).get(key)
            if metric is None:
                continue
            try:
                # The inherited version bound the first metric row. The user
                # requested that card links live in the card header instead.
                metric.unbind('<Double-1>')
                section = metric.master.master
                header = section.winfo_children()[0]
            except (AttributeError, IndexError, tk.TclError):
                continue

            def open_summary(_event, value=group):
                self._open_dashboard_summary(value)
                return 'break'

            for widget in v186._walk(header):
                try:
                    widget.configure(cursor='hand2')
                    widget.bind('<Double-1>', open_summary, add='+')
                except (AttributeError, tk.TclError):
                    pass

    def _ensure_physical_progress_card_187(self):
        """Keep the 32-phase physical-progress card in the overview layout."""
        phase_strip = getattr(self, 'phase_strip', None)
        overall_progress = getattr(self, 'overall_progress', None)
        if phase_strip is None or overall_progress is None:
            return
        try:
            phase_card = phase_strip.master.master
            self.phase_card187 = phase_card
        except (AttributeError, tk.TclError):
            return
        try:
            header = next(
                child for child in phase_card.winfo_children()
                if isinstance(child, tk.Frame)
            )
            for child in header.winfo_children():
                if isinstance(child, tk.Label):
                    text = str(child.cget('text') or '')
                    if text and text not in {'▥', '◈'}:
                        child.configure(text='پیشرفت فیزیکی پروژه — ۳۲ فاز')
                        break
            self._install_phase_legend_187(phase_card)
            for button in getattr(self, 'phase_buttons', {}).values():
                button.configure(cursor='hand2')
        except (StopIteration, tk.TclError):
            pass
        try:
            # Explicitly re-manage this card. ``pack_configure`` alone does
            # not restore a card that an inherited layout pass has unmanaged.
            charts = getattr(self, 'cost_donut', None)
            if charts is not None:
                phase_card.pack(before=charts.master, fill='x', padx=5, pady=(4, 6))
            else:
                phase_card.pack(fill='x', padx=5, pady=(4, 6))
            phase_card.lift()
        except tk.TclError:
            return
    # ------------------------------------------------------------------
    # Transactions tab (18.7.1 UI contract)
    # ------------------------------------------------------------------
    # The inherited financial screen is deliberately left intact in the
    # older stages.  These helpers retarget only the live 18.7 instance so
    # that the transaction list can use the same controls as the income
    # workspace without changing the SQLite model or any accounting path.
    _TRANSACTION_COLUMNS_187 = (
        ('row', 'ردیف', 58),
        ('date', 'تاریخ شمسی فارسی', 122),
        ('title', 'عنوان تراکنش', 166),
        ('type', 'نوع تراکنش', 112),
        ('desc', 'بابت', 250),
        ('amount', 'مبلغ', 124),
        ('payer', 'واریزکننده', 132),
        ('receiver', 'گیرنده', 132),
        ('phase', 'فاز اصلی', 122),
        ('subphase', 'فاز فرعی', 122),
    )
    _LAND_TRANSACTION_COLUMNS_187 = (
        ('row', 'ردیف', 58),
        ('date', 'تاریخ', 122),
        ('desc', 'بابت', 250),
        ('amount', 'مبلغ', 124),
        ('payer', 'واریزکننده', 132),
        ('receiver', 'گیرنده', 132),
        ('phase', 'فاز اصلی', 122),
        ('subphase', 'فاز فرعی', 122),
    )
    _LOAN_TABLE_COLUMNS_187 = (
        ('date', 'تاریخ دریافت', 112),
        ('lender', 'نام بانک', 132),
        ('borrower', 'نام وام گیرنده', 150),
        ('principal', 'اصل وام (تومان)', 136),
        ('received', 'واریز خالص (تومان)', 145),
        ('interest', 'سود و کارمزد', 132),
        ('paid', 'اقساط پرداختی', 132),
        ('remain', 'مانده بدهی', 132),
        ('installment_amount', 'مبلغ قسط', 122),
        ('last_payment', 'تاریخ آخرین پرداختی', 148),
        ('next', 'قسط بعدی', 160),
        ('status', 'وضعیت', 94),
        ('loan_id', 'Loan ID', 145),
    )
    # The first selector chooses the column; the second selector is populated
    # from the values actually present in that column.  This keeps the common
    # financial toolbar useful without reviving the removed free-text filter.
    _TRANSACTION_FILTER_FIELDS_187 = (
        'همه', 'تاریخ', 'عنوان تراکنش', 'گیرنده', 'بابت', 'فاز اصلی',
    )
    _LAND_FILTER_FIELDS_187 = ('همه', 'تاریخ', 'واریز کننده', 'بابت')
    _EXPENSE_FILTER_FIELDS_187 = (
        'همه', 'تاریخ', 'دسته‌بندی', 'گیرنده', 'شرح', 'فاز ساخت',
    )
    _INCOME_FILTER_FIELDS_187 = (
        'همه', 'تاریخ', 'واریز کننده', 'شرح', 'نوع ورودی',
    )
    _OUTFLOW_FILTER_FIELDS_187 = (
        'همه', 'تاریخ', 'نوع خروجی', 'دریافت کننده', 'شرح',
    )
    _CHEQUE_FILTER_FIELDS_187 = (
        'همه', 'تاریخ سررسید', 'گیرنده', 'بابت', 'صاحب حساب', 'بانک',
        'ثبت', 'شماره صیادی',
    )
    _LOAN_FILTER_FIELDS_187 = (
        'همه', 'تاریخ', 'بانک', 'نام وام', 'گیرنده وام', 'وضعیت',
    )
    _DOCUMENT_FILTER_FIELDS_187 = (
        'همه', 'تاریخ', 'نوع سند', 'شرح', 'فاز ساخت',
    )
    _FINANCIAL_HIDDEN_ID_KEYS_187 = frozenset({
        'id', 'transaction_id', 'pending_id', 'expense_id', 'loan_id',
        'cheque_id', 'document_id', 'sale_id', 'unit_id', 'link_pending_id',
    })
    _FINANCIAL_TABLE_NAMES_187 = (
        'all_tx_table', 'land_table', 'exp_table', 'in_table', 'out_table',
        'loan_table', 'cheque_table', 'document_table',
    )

    def _build_financial(self):
        """Build inherited financial pages, then install the 18.7 controls."""
        super()._build_financial()
        _install_form_keyboard_navigation_187(self)
        self._build_land_transactions_187()
        self._install_financial_transaction_ui_187()
        for tab_id in getattr(self.fin_nb, 'tabs', lambda: ())():
            try:
                if self.fin_nb.tab(tab_id, 'text') in {'داکیومنت‌ها', 'سند غیر مالی'}:
                    self.fin_nb.tab(tab_id, text='سند غیر مالی')
            except tk.TclError:
                continue

    def _build_land_transactions_187(self):
        """Use the same table, toolbar and lifecycle routes as all transactions."""
        tab = ttk.Frame(self.fin_nb, padding=6)
        tabs = list(self.fin_nb.tabs())
        all_tab = next((item for item in tabs if self.fin_nb.tab(item, 'text') in
                        {'کلیه تراکنش‌ها', 'همه تراکنش‌ها'}), None)
        position = tabs.index(all_tab)+1 if all_tab else 0
        self.fin_nb.insert(position, tab, text=LAND_TITLE)
        self.land_table = SmartTable(tab, list(self._LAND_TRANSACTION_COLUMNS_187), title=LAND_TITLE)
        self.land_table.pack(fill='both', expand=True)
        self.land_table.row_values = lambda row: self._transaction_values_187(row, self.land_table)
        self.land_table._barkav_source_rows187 = []
        strip = getattr(self.fin_nb, '_barkav_rtl_strip', None)
        if strip is not None:
            refresh = getattr(strip, 'rebuild', None) or getattr(strip, 'sync', None)
            if refresh is not None:
                refresh()

    def _order_financial_tabs_184(self):
        super()._order_financial_tabs_184()
        tabs = list(self.fin_nb.tabs())
        land = next((item for item in tabs if self.fin_nb.tab(item, 'text') == LAND_TITLE), None)
        all_tab = next((item for item in tabs if self.fin_nb.tab(item, 'text') in
                        {'کلیه تراکنش‌ها', 'همه تراکنش‌ها'}), None)
        if land is not None and all_tab is not None:
            self.fin_nb.insert(tabs.index(all_tab)+1, land)
            strip = getattr(self.fin_nb, '_barkav_rtl_strip', None)
            refresh = getattr(strip, 'rebuild', None) or getattr(strip, 'sync', None)
            if refresh is not None:
                refresh()

    @staticmethod
    def _document_image_paths_187(attachments) -> list[str]:
        image_suffixes = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tif', '.tiff'}
        paths: list[str] = []
        for attachment in attachments or ():
            path = str((attachment or {}).get('local_path') or '').strip()
            mime = str((attachment or {}).get('mime_type') or '').lower()
            if path and (mime.startswith('image/') or Path(path).suffix.lower() in image_suffixes):
                paths.append(path)
        return paths

    def _document_attachments_187(self, row) -> list[dict]:
        row = dict(row or {})
        document_id = str(row.get('document_id') or '').strip()
        pending_id = str(row.get('pending_id') or '').strip()
        try:
            attached = DB.list_entity_attachments('DOCUMENT', document_id) if document_id else []
            if not attached and pending_id:
                attached = DB.list_pending_attachments(pending_id)
            return list(attached or [])
        except Exception:
            return []

    def _document_image_indicator_187(self, row) -> str:
        count = len(self._document_image_paths_187(self._document_attachments_187(row)))
        return f'🖼 {fa(count)}' if count else '—'

    def _install_document_preview_187(self, table) -> None:
        """Place the non-financial table on the RTL side and preview its images."""
        if table is None or getattr(table, '_barkav_document_preview187', None) is not None:
            return
        parent = table.master
        p = palette_187()
        preview = tk.Frame(parent, bg=p['panel'], width=340,
                           highlightbackground=p['border_subtle'], highlightthickness=1)
        preview.pack_propagate(False)
        tk.Label(preview, text='پیش‌نمایش سند', bg=p['panel'], fg=p['text'],
                 anchor='e', font=kit_font('body', bold=True), padx=10, pady=8).pack(fill='x')
        image_host = tk.Frame(preview, bg=p['panel2'])
        image_host.pack(fill='both', expand=True, padx=8, pady=(0, 6))
        image = tk.Label(image_host, text='یک سند را انتخاب کنید.', bg=p['panel2'], fg=p['muted'],
                         anchor='center', justify='center', wraplength=300)
        image.pack(fill='both', expand=True)
        tk.Label(preview, text='شرح تراکنش', bg=p['panel'], fg=p['text'],
                 anchor='e', font=kit_font('body', bold=True), padx=9, pady=3).pack(fill='x')
        description_host = tk.Frame(preview, bg=p['input'])
        description_host.pack(fill='x', padx=8, pady=(0, 6))
        description = tk.Text(
            description_host, height=4, wrap='word', undo=False,
            bg=p['input'], fg=p['text'], insertbackground=p['text'],
            relief='flat', highlightthickness=1,
            highlightbackground=p['border_subtle'], padx=7, pady=5,
        )
        description_scroll = ttk.Scrollbar(description_host, orient='vertical', command=description.yview)
        description.configure(yscrollcommand=description_scroll.set)
        description_scroll.pack(side='right', fill='y')
        description.pack(side='left', fill='both', expand=True)
        description.configure(state='disabled')
        caption = tk.StringVar(value='')
        tk.Label(preview, textvariable=caption, bg=p['panel'], fg=p['muted'],
                 anchor='e', justify='right', wraplength=320, padx=9, pady=6).pack(fill='x')
        try:
            table.pack_forget()
            preview.pack(side='left', fill='both', padx=(0, 6), pady=0)
            table.pack(side='right', fill='both', expand=True)
        except tk.TclError:
            try:
                preview.destroy()
            except tk.TclError:
                pass
            return
        table._barkav_document_preview187 = preview
        table._barkav_document_preview_image187 = image
        table._barkav_document_preview_caption187 = caption
        table._barkav_document_preview_description187 = description
        table.tree.bind('<<TreeviewSelect>>',
                        lambda _event, target=table: self._show_document_preview_187(target), add='+')

    def _show_document_preview_187(self, table) -> None:
        label = getattr(table, '_barkav_document_preview_image187', None)
        caption = getattr(table, '_barkav_document_preview_caption187', None)
        description_box = getattr(table, '_barkav_document_preview_description187', None)
        if label is None or caption is None:
            return
        selected = tuple(table.tree.selection() or ())
        row = getattr(table, '_iid_to_row', {}).get(selected[0]) if selected else None
        if not row:
            label.configure(image='', text='یک سند را انتخاب کنید.')
            label._barkav_document_photo187 = None
            caption.set('')
            if description_box is not None:
                description_box.configure(state='normal'); description_box.delete('1.0', 'end'); description_box.configure(state='disabled')
            return
        paths = self._document_image_paths_187(self._document_attachments_187(row))
        description = str(row.get('description') or 'سند بدون شرح')
        payload = self._transaction_payload_187(row)
        transaction_description = str(
            payload.get('description') or row.get('raw_text') or description or '—'
        ).strip()
        if description_box is not None:
            description_box.configure(state='normal')
            description_box.delete('1.0', 'end')
            description_box.insert('1.0', transaction_description or '—')
            description_box.configure(state='disabled')
        if not paths:
            label.configure(image='', text='برای این سند تصویر قابل نمایش ثبت نشده است.')
            label._barkav_document_photo187 = None
            caption.set(description)
            return
        path = Path(paths[0])
        if not path.is_file():
            label.configure(image='', text='فایل تصویر این سند در مسیر ثبت‌شده پیدا نشد.')
            label._barkav_document_photo187 = None
            caption.set(description)
            return
        try:
            from PIL import Image, ImageOps, ImageTk
            with Image.open(path) as source:
                rendered = ImageOps.exif_transpose(source).convert('RGB')
                rendered.thumbnail((320, 460), Image.LANCZOS)
                photo = ImageTk.PhotoImage(rendered, master=label)
            label.configure(image=photo, text='')
            label._barkav_document_photo187 = photo
            caption.set(f'{description} — {fa(len(paths))} تصویر')
        except Exception:
            label.configure(image='', text='پیش‌نمایش تصویر این سند امکان‌پذیر نیست.')
            label._barkav_document_photo187 = None
            caption.set(description)
    def _refresh_after_document_change_187(self):
        """Refresh after the modal closes, with one idle retry for Tk repaint races."""
        def refresh_once():
            try:
                self.refresh_financial()
            except Exception:
                # A partially initialized legacy tab must not hide a committed
                # document.  The idle retry runs after the remaining tabs settle.
                try:
                    self.after(120, self.refresh_financial)
                except (AttributeError, tk.TclError):
                    pass
        try:
            self.after_idle(refresh_once)
        except (AttributeError, tk.TclError):
            refresh_once()

    def _document_payload_from_row_187(self, row, payload=None):
        """Fill a document wizard from the posted row and its original Pending payload."""
        row = dict(row or {})
        result = dict(payload or {})
        code = str(row.get('document_type') or result.get('document_type') or '').strip().upper()
        subtype = _canonical_document_subtype_187(
            result.get('v18_subtype') or result.get('transaction_subtype')
            or _DOCUMENT_CODE_TO_SUBTYPE_187.get(code, 'داکیومنت')
        )
        result['v18_title'] = result.get('v18_title') or 'یادداشت'
        result['v18_subtype'] = result.get('v18_subtype') or subtype
        result['transaction_title'] = result.get('transaction_title') or 'یادداشت'
        result['transaction_subtype'] = result.get('transaction_subtype') or subtype
        result['document_type'] = result.get('document_type') or _document_code_187(subtype)
        result['detected_type'] = result.get('detected_type') or ('DOCUMENT' if subtype == 'داکیومنت' else 'INFO')
        result['event_date_shamsi'] = result.get('event_date_shamsi') or (
            row.get('event_date_shamsi') or row.get('date') or row.get('shamsi_date') or ''
        )
        result['description'] = result.get('description') or row.get('description') or ''
        result['amount'] = 0
        result['paid_amount'] = 0
        return result

    def _open_document_pending_wizard_187(self, pending_id, row, *, edit_document_id=''):
        """Open the shared wizard for a new, copied, or edited non-financial row."""
        pending_id = str(pending_id or '').strip()
        row = dict(row or {})
        payload = self._document_payload_from_row_187(row, row.get('payload'))
        if edit_document_id:
            payload['_document_edit_id_187'] = str(edit_document_id)
        row['pending_id'] = pending_id
        row['payload'] = payload

        def done():
            self._refresh_after_document_change_187()

        def full():
            fresh = dict(DB.get_pending_item(pending_id) or row)
            fresh_payload = self._document_payload_from_row_187(fresh, fresh.get('payload'))
            if edit_document_id:
                fresh_payload['_document_edit_id_187'] = str(edit_document_id)
            fresh['payload'] = fresh_payload
            fresh['raw_text'] = v18._raw_text(pending_id, fresh)
            editor = v182.UnifiedPendingEditor182(self, fresh, self.rich, done)
            self.after_idle(lambda: _place_window_right_187(editor, self))

        wizard = v182.TransactionWizard182(self, row, self.rich, done, full)
        if edit_document_id:
            wizard._document_edit_id_187 = str(edit_document_id)
        self.after_idle(lambda: _place_window_right_187(wizard, self))
        return wizard

    def _open_document_wizard_187(self):
        """Create a reviewable non-financial pending row, then open the wizard."""
        mid = int(datetime.now().timestamp() * 1_000_000)
        today = gregorian_to_shamsi(datetime.now().date())
        payload = {
            'v18_title': 'یادداشت', 'v18_subtype': 'داکیومنت',
            'transaction_title': 'یادداشت', 'transaction_subtype': 'داکیومنت',
            'detected_type': 'DOCUMENT', 'event_date_shamsi': today,
            'amount': 0, 'paid_amount': 0, 'source': 'MANUAL_DOCUMENT_GUI_187',
        }
        DB.register_telegram_message(
            chat_id=-187, message_id=mid, raw_text='', content_type='manual_document_gui',
            message_date=datetime.now().isoformat(timespec='seconds'), state='RECEIVED',
        )
        pending_id = DB.create_or_replace_pending(
            telegram_chat_id=-187, telegram_message_id=mid,
            detected_type='DOCUMENT', payload=payload, confidence=1.0,
            status='PENDING_REVIEW',
        )
        row = DB.get_pending_item(pending_id) or {
            'pending_id': pending_id, 'payload': payload,
            'telegram_chat_id': -187, 'telegram_message_id': mid,
        }
        return self._open_document_pending_wizard_187(pending_id, row)

    def _open_document_edit_wizard_187(self, row):
        """Open edit through the wizard and preload the selected document's record."""
        row = dict(row or {})
        pending_id = self._pending_from_posted_row(row)
        if not pending_id:
            return messagebox.showinfo(
                'ویرایش سند غیرمالی',
                'این سند به رکورد Pending اصلی متصل نیست و قابل ویرایش ایمن نیست.',
                parent=self,
            )
        pending = DB.get_pending_item(pending_id)
        if not pending:
            return messagebox.showwarning('ویرایش سند غیرمالی', 'رکورد مبدا پیدا نشد.', parent=self)
        document_id = str(row.get('document_id') or '').strip()
        if not document_id:
            try:
                with DB.read() as con:
                    found = con.execute(
                        'SELECT document_id FROM financial_documents WHERE pending_id=? AND status=\'ACTIVE\' '
                        'ORDER BY created_at DESC LIMIT 1', (pending_id,)
                    ).fetchone()
                document_id = str(found['document_id']) if found and found['document_id'] else ''
            except Exception:
                document_id = ''
        if not document_id:
            return messagebox.showwarning('ویرایش سند غیرمالی', 'شناسه سند پیدا نشد.', parent=self)
        edit_row = dict(pending)
        edit_row['payload'] = self._document_payload_from_row_187(edit_row, pending.get('payload'))
        edit_row['raw_text'] = v18._raw_text(pending_id, edit_row)
        return self._open_document_pending_wizard_187(
            pending_id, edit_row, edit_document_id=document_id,
        )

    def _loan_payload_from_row_187(self, row):
        row = dict(row or {})
        loan_id = str(row.get('loan_id') or '').split('|', 1)[0].strip()
        loan = LoanService(DB).get_loan(loan_id) if loan_id else None
        source = dict(loan or row)
        guarantors = [part.strip() for part in str(source.get('guarantors') or '').split('|')]
        paid_count = 0
        last_paid_date = ''
        if loan_id:
            with DB.read() as con:
                schedule_state = con.execute(
                    "SELECT COUNT(*) AS paid_count,MAX(paid_date_shamsi) AS last_paid_date "
                    "FROM loan_installments WHERE loan_id=? AND paid_amount>0",
                    (loan_id,),
                ).fetchone()
            if schedule_state:
                paid_count = int(schedule_state['paid_count'] or 0)
                last_paid_date = str(schedule_state['last_paid_date'] or '')
        principal = parse_int(source.get('principal_amount') or 0)
        count = parse_int(source.get('installment_count') or 0)
        first_due = str(source.get('first_due_date_shamsi') or '')
        end_due = ''
        if first_due and count:
            try:
                end_due = gregorian_to_shamsi(
                    _add_months(date.fromisoformat(shamsi_to_gregorian(first_due)), count - 1))
            except Exception:
                end_due = ''
        payload = {
            'v18_title': 'ورودی', 'v18_subtype': 'تسهیلات', 'detected_type': 'INCOME',
            'event_date_shamsi': source.get('received_date_shamsi') or row.get('shamsi_date') or '',
            'amount': source.get('net_received_amount') or row.get('amount') or 0,
            'loan_total_amount': principal,
            'principal_amount': principal,
            'loan_bank': source.get('lender_name') or '',
            'loan_name': source.get('loan_name') or str(principal)[:4],
            'loan_title': source.get('description') or '',
            'description': source.get('description') or '',
            'branch_name': source.get('branch_name') or '',
            'contract_number': source.get('contract_number') or '',
            'installment_count': count,
            'interest_rate': source.get('interest_rate') or 0,
            'installment_amount': source.get('installment_amount') or 0,
            'total_interest': source.get('total_interest') or 0,
            'bank_fees': source.get('bank_fees') or 0,
            'borrower_name': source.get('borrower_name') or '',
            'guarantor_1': guarantors[0] if len(guarantors) > 0 else '',
            'guarantor_2': guarantors[1] if len(guarantors) > 1 else '',
            'first_due_date_shamsi': first_due,
            'loan_end_date': end_due,
            'last_paid_date_shamsi': last_paid_date,
            'paid_installments_count': paid_count,
            'remaining_installments': max(0, count - paid_count),
        }
        return payload

    def _open_loan_wizard_187(self):
        mid = int(datetime.now().timestamp() * 1_000_000)
        today = gregorian_to_shamsi(datetime.now().date())
        payload = {
            'v18_title': 'ورودی', 'v18_subtype': 'تسهیلات', 'detected_type': 'INCOME',
            'event_date_shamsi': today, 'loan_start_date': today,
            'amount': 0, 'source': 'MANUAL_LOAN_GUI_187',
        }
        DB.register_telegram_message(
            chat_id=-187, message_id=mid, raw_text='', content_type='manual_loan_gui',
            message_date=datetime.now().isoformat(timespec='seconds'), state='RECEIVED',
        )
        pending_id = DB.create_or_replace_pending(
            telegram_chat_id=-187, telegram_message_id=mid,
            detected_type='INCOME', payload=payload, confidence=1.0,
            status='PENDING_REVIEW',
        )
        row = DB.get_pending_item(pending_id) or {
            'pending_id': pending_id, 'payload': payload,
            'telegram_chat_id': -187, 'telegram_message_id': mid,
        }
        def done():
            self.refresh_all()
        def full():
            fresh = DB.get_pending_item(pending_id) or row
            editor = v182.UnifiedPendingEditor182(self, dict(fresh), self.rich, done)
            self.after_idle(lambda: _place_window_right_187(editor, self))
        wizard = v182.TransactionWizard182(self, row, self.rich, done, full)
        self.after_idle(lambda: _place_window_right_187(wizard, self))
        return wizard

    def add_loan(self):
        """Open the three-step facility wizard on the right side of the window."""
        return self._open_loan_wizard_187()

    def edit_loan_row(self, row=None):
        row = row or self._one(getattr(self, 'loan_table', None))
        if not row:
            return None
        payload = self._loan_payload_from_row_187(row)
        payload['pending_id'] = f"EDIT-{row.get('loan_id') or int(datetime.now().timestamp())}"
        edit_row = dict(row)
        edit_row['pending_id'] = payload['pending_id']
        edit_row['payload'] = payload
        wizard = LoanEditWizard187(self, edit_row, self.rich, self._save_loan_edit_187)
        return wizard

    def _open_loan_details_187(self, row=None):
        row = row or self._one(getattr(self, 'loan_table', None))
        if not row or not row.get('loan_id'):
            return None
        window = LoanDetailsWindow187(self, row.get('loan_id'))
        self.after_idle(lambda: _place_window_right_187(window, self, 1220, 760))
        return window

    def _open_loan_input_row_187(self, row=None):
        row = row or self._one(getattr(self, 'loan_table', None))
        if not row:
            return None
        transaction_id = str(row.get('receive_transaction_id') or '')
        if not transaction_id:
            with DB.read() as con:
                found = con.execute(
                    'SELECT transaction_id FROM transactions WHERE loan_id=? AND direction=\'IN\' '
                    'ORDER BY created_at LIMIT 1', (str(row.get('loan_id') or ''),),
                ).fetchone()
            transaction_id = str(found['transaction_id'] or '') if found else ''
        table = getattr(self, 'in_table', None)
        if not transaction_id or table is None:
            return messagebox.showinfo('ردیف ورودی', 'ردیف ورودی متناظر پیدا نشد.', parent=self)
        for tab_id in self.notebook.tabs():
            if str(self.notebook.tab(tab_id, 'text')).strip() == 'تراکنش‌ها':
                self.notebook.select(tab_id)
                break
        for tab_id in self.fin_nb.tabs():
            if str(self.fin_nb.tab(tab_id, 'text')).strip() == 'ورودی':
                self.fin_nb.select(tab_id)
                break
        if not any(str(item.get('transaction_id') or '') == transaction_id
                   for item in getattr(table, 'filtered_rows', ()) or ()):
            self._set_transaction_filter_187(table, 'همه', 'همه')
        for iid, candidate in (getattr(table, '_iid_to_row', {}) or {}).items():
            if str(candidate.get('transaction_id') or '') == transaction_id:
                table.tree.selection_set(iid)
                table.tree.focus(iid)
                table.tree.see(iid)
                return candidate
        return messagebox.showinfo('ردیف ورودی', 'تراکنش متناظر ثبت شده اما در فهرست ورودی پیدا نشد.', parent=self)

    def _open_transaction_data_entry_187(self, row=None):
        row = row or self._one(getattr(self, 'in_table', None))
        if not row:
            return None
        try:
            from transaction_lifecycle import TransactionLifecycle
            pending_id = TransactionLifecycle(DB).pending_for_row(row)
        except Exception as exc:
            return messagebox.showinfo('رکورد ثبت دیتا', str(exc), parent=self)
        center = getattr(self, 'approval_center', None)
        item = DB.get_pending_item(str(pending_id))
        if center is None or not item:
            return messagebox.showinfo('رکورد ثبت دیتا', 'رکورد ثبت دیتای متناظر پیدا نشد.', parent=self)
        self.notebook.select(self.approval_tab)
        center.refresh()
        center.open_editor(item)
        return item

    def _delete_loan_lifecycle_187(self, row=None):
        row = row or self._one(getattr(self, 'loan_table', None))
        if not row:
            return None
        loan_id = str(row.get('loan_id') or '').split('|', 1)[0].strip()
        try:
            from transaction_lifecycle import TransactionLifecycle
            lifecycle = TransactionLifecycle(DB)
            pending_id = lifecycle.pending_for_row({'loan_id': loan_id})
        except Exception as exc:
            return messagebox.showwarning('حذف تسهیلات', str(exc), parent=self)
        if not messagebox.askyesno(
                'حذف تسهیلات',
                'تسهیلات، تراکنش ورودی و برنامه اقساط متناظر حذف شوند و رکورد ثبت دیتا به «ردشده‌ها» برود؟',
                parent=self):
            return None
        try:
            # Due/upcoming status is recalculated as the calendar advances. Rebase
            # only that derived status when every financial installment value is
            # otherwise unchanged; a payment or amount change still blocks deletion.
            with DB.tx() as con:
                record = con.execute(
                    "SELECT effects_json FROM transaction_lifecycle "
                    "WHERE pending_id=? AND state='ACTIVE'", (pending_id,),
                ).fetchone()
                if record:
                    effects = json.loads(record['effects_json'] or '[]')
                    changed = False
                    for effect in effects:
                        if effect.get('table') != 'loan_installments' or not effect.get('after'):
                            continue
                        current = con.execute(
                            'SELECT * FROM loan_installments WHERE loan_installment_id=?',
                            (str((effect.get('key') or [''])[0]),),
                        ).fetchone()
                        expected = effect['after']
                        if not current or parse_int(current['paid_amount'] or 0) > 0:
                            continue
                        current = dict(current)
                        stable = all(
                            current.get(key) == value
                            for key, value in expected.items()
                            if key not in {'status', 'updated_at', 'sync_status'}
                        )
                        if stable and current.get('status') != expected.get('status'):
                            effect['after'] = current
                            changed = True
                    if changed:
                        con.execute(
                            'UPDATE transaction_lifecycle SET effects_json=?,updated_at=? WHERE pending_id=?',
                            (json.dumps(effects, ensure_ascii=False), _finance_now_187(), pending_id),
                        )
            lifecycle.reject(pending_id)
            self.refresh_all()
            show_toast(self, 'تسهیلات و آثار ورودی آن رد شد؛ رکورد ثبت دیتا در «ردشده‌ها» قرار گرفت.')
        except Exception as exc:
            messagebox.showerror('حذف تسهیلات', str(exc), parent=self)
            return None
        return pending_id

    def cancel_loan(self):
        return self._delete_loan_lifecycle_187()

    def _save_loan_edit_187(self, row, payload):
        loan_id = str(row.get('loan_id') or '').split('|', 1)[0].strip()
        if not loan_id:
            raise ValueError('شناسه وام پیدا نشد.')
        payload = _payload_values_187(type('_LoanPayloadHolder187', (), {
            'payload': dict(payload), 'vars': {}, '_loading': False,
            'manual_fields': set(),
        })(), 'ورودی', 'تسهیلات')
        received = _loan_date_value_187(payload.get('loan_start_date') or payload.get('event_date_shamsi'))
        if not received:
            raise ValueError('تاریخ دریافت وام نامعتبر است.')
        principal = parse_int(payload.get('principal_amount') or payload.get('loan_total_amount'))
        amount = parse_int(payload.get('amount') or payload.get('net_received_amount'))
        count = parse_int(payload.get('installment_count') or 0)
        installment = parse_int(payload.get('installment_amount') or 0)
        if installment <= 0 and principal > 0 and count > 0:
            installment = calculate_loan_installment_187(principal, payload.get('interest_rate') or 0, count)
        total_interest = loan_total_interest_187(principal, installment, count)
        bank_fees = _loan_fees_187(principal, amount)
        fee_repaid = _loan_fee_repaid_187(principal, amount, bank_fees)
        loan_name = str(payload.get('loan_name') or str(principal)[:4]).strip()
        loan_title = str(payload.get('loan_title') or payload.get('description') or 'ورودی تسهیلات').strip()
        first_due = _loan_date_value_187(payload.get('first_due_date_shamsi'))
        if count and not first_due:
            first_due = gregorian_to_shamsi(
                _add_months(date.fromisoformat(shamsi_to_gregorian(received)), 1))
        with DB.read() as con:
            before_row = con.execute('SELECT * FROM loans WHERE loan_id=?', (loan_id,)).fetchone()
            if not before_row:
                raise ValueError('پرونده وام پیدا نشد.')
            before = dict(before_row)
            paid_count = int(con.execute(
                "SELECT COUNT(*) FROM loan_installments WHERE loan_id=? AND paid_amount>0",
                (loan_id,),
            ).fetchone()[0])
            tx_row = con.execute(
                'SELECT * FROM transactions WHERE transaction_id=?',
                (before.get('receive_transaction_id'),),
            ).fetchone() if before.get('receive_transaction_id') else None
            tx_row = dict(tx_row) if tx_row else None
        lifecycle_pid = ''
        try:
            from transaction_lifecycle import TransactionLifecycle
            lifecycle_pid = TransactionLifecycle(DB).pending_for_row({'loan_id': loan_id})
        except (ValueError, KeyError):
            lifecycle_pid = ''
        schedule_changed = any((
            principal != int(before.get('principal_amount') or 0),
            count != int(before.get('installment_count') or 0),
            first_due != str(before.get('first_due_date_shamsi') or ''),
            installment != int(before.get('installment_amount') or 0),
            total_interest != int(before.get('total_interest') or 0),
            bank_fees != int(before.get('bank_fees') or 0),
        ))
        if paid_count and schedule_changed:
            raise ValueError('وامی که قسط پرداخت‌شده دارد، برنامه اقساط آن قابل تغییر نیست.')
        end_date = ''
        if first_due and count:
            end_date = gregorian_to_shamsi(
                _add_months(date.fromisoformat(shamsi_to_gregorian(first_due)), count - 1))
        guarantors = ' | '.join(
            str(payload.get(key) or '').strip()
            for key in ('guarantor_1', 'guarantor_2')
            if str(payload.get(key) or '').strip()
        )
        now = _finance_now_187()
        received_gregorian = shamsi_to_gregorian(received)
        with DB.tx() as con:
            current = dict(con.execute('SELECT * FROM loans WHERE loan_id=?', (loan_id,)).fetchone())
            con.execute('''UPDATE loans SET lender_name=?,principal_amount=?,received_date=?,description=?,updated_at=?,
                           net_received_amount=?,received_date_shamsi=?,interest_rate=?,total_interest=?,bank_fees=?,
                           total_repayment=?,installment_count=?,installment_amount=?,first_due_date=?,first_due_date_shamsi=?,
                           guarantors=?,contract_number=?,borrower_name=?,branch_name=?,loan_name=? WHERE loan_id=?''', (
                str(payload.get('loan_bank') or '').strip(), principal, received_gregorian,
                loan_title, now,
                amount, received, float(payload.get('interest_rate') or 0), total_interest,
                bank_fees, total_interest + fee_repaid + principal,
                count, installment,
                shamsi_to_gregorian(first_due) if first_due else None, first_due,
                guarantors, str(payload.get('contract_number') or '').strip(),
                str(payload.get('borrower_name') or '').strip(),
                str(payload.get('branch_name') or '').strip(), loan_name, loan_id,
            ))
            if tx_row and before.get('receive_transaction_id'):
                con.execute('''UPDATE transactions SET event_date=?,shamsi_date=?,amount=?,payer_name=?,description=?,updated_at=?,sync_status='PENDING'
                               WHERE transaction_id=?''', (
                    received_gregorian, received, amount,
                    str(payload.get('loan_bank') or '').strip(),
                    loan_title, now,
                    before.get('receive_transaction_id'),
                ))
            if not paid_count:
                old_installments = [str(item['loan_installment_id']) for item in con.execute(
                    'SELECT loan_installment_id FROM loan_installments WHERE loan_id=?', (loan_id,)
                ).fetchall()]
                for installment_id in old_installments:
                    con.execute("UPDATE reminders SET status='CANCELLED',updated_at=? WHERE entity_type='LOAN_INSTALLMENT' AND entity_id=? AND status='SCHEDULED'", (now, installment_id))
                con.execute('DELETE FROM loan_installments WHERE loan_id=?', (loan_id,))
                if count and first_due:
                    total_repayment = principal + total_interest + fee_repaid
                    base_principal = principal // count
                    base_interest = (total_interest + fee_repaid) // count
                    for index in range(count):
                        due = _add_months(date.fromisoformat(shamsi_to_gregorian(first_due)), index)
                        principal_part = base_principal if index < count - 1 else principal - base_principal * (count - 1)
                        interest_part = base_interest if index < count - 1 else (total_interest + fee_repaid) - base_interest * (count - 1)
                        due_amount = installment if index < count - 1 else max(0, total_repayment - installment * (count - 1))
                        con.execute('''INSERT INTO loan_installments(
                            loan_installment_id,loan_id,installment_number,due_date,due_date_shamsi,amount,
                            principal_component,interest_component,created_at,updated_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?)''', (
                            _finance_id_187('LINS'), loan_id, index + 1, due.isoformat(),
                            gregorian_to_shamsi(due), due_amount, principal_part, interest_part, now, now,
                        ))
            after = dict(con.execute('SELECT * FROM loans WHERE loan_id=?', (loan_id,)).fetchone())
            DB._audit(con, 'loan', loan_id, 'UPDATE', 'GUI_187', before=before, after=after, actor_id='GUI')
            DB._enqueue_sync(con, 'loan', loan_id, 'UPDATE', after)
            if lifecycle_pid:
                record = con.execute(
                    "SELECT effects_json FROM transaction_lifecycle WHERE pending_id=? AND state='ACTIVE'",
                    (lifecycle_pid,),
                ).fetchone()
                if record:
                    effects = json.loads(record['effects_json'] or '[]')
                    txid = str(before.get('receive_transaction_id') or '')
                    old_by_key = {
                        (effect.get('table'), tuple(effect.get('key') or ())): effect
                        for effect in effects
                    }
                    def is_loan_effect(effect):
                        table, key = effect.get('table'), tuple(effect.get('key') or ())
                        after_row = effect.get('after') or {}
                        return (
                            table == 'loans' and key == (loan_id,)
                            or table == 'transactions' and txid and key == (txid,)
                            or table == 'loan_installments' and str(after_row.get('loan_id') or '') == loan_id
                        )
                    refreshed = [effect for effect in effects if not is_loan_effect(effect)]
                    current_rows = [('loans', 'loan_id', after)]
                    if txid:
                        transaction = con.execute(
                            'SELECT * FROM transactions WHERE transaction_id=?', (txid,),
                        ).fetchone()
                        if transaction:
                            current_rows.append(('transactions', 'transaction_id', dict(transaction)))
                    current_rows.extend(
                        ('loan_installments', 'loan_installment_id', dict(item))
                        for item in con.execute(
                            'SELECT * FROM loan_installments WHERE loan_id=? ORDER BY installment_number',
                            (loan_id,),
                        ).fetchall()
                    )
                    for table_name, key_name, current_row in current_rows:
                        key = (table_name, (str(current_row[key_name]),))
                        previous = old_by_key.get(key)
                        refreshed.append({
                            'table': table_name, 'pk': [key_name], 'key': [current_row[key_name]],
                            'before': previous.get('before') if previous else None,
                            'after': current_row,
                        })
                    table_order = ('transactions', 'expenses', 'payments', 'cheques', 'loans',
                                   'loan_installments', 'received_payments', 'payment_allocations',
                                   'sales', 'installments', 'units', 'receivables', 'reminders',
                                   'financial_postings', 'financial_documents',
                                   'financial_document_links', 'expense_payment_links', 'attachments')
                    rank = {name: index for index, name in enumerate(table_order)}
                    refreshed.sort(key=lambda effect: (rank.get(effect.get('table'), len(rank)),
                                                       str((effect.get('key') or [''])[0])))
                    encoded_payload = json.dumps(payload, ensure_ascii=False)
                    con.execute(
                        'UPDATE transaction_lifecycle SET effects_json=?,payload_json=?,updated_at=? WHERE pending_id=?',
                        (json.dumps(refreshed, ensure_ascii=False), encoded_payload, now, lifecycle_pid),
                    )
                    con.execute(
                        'UPDATE pending_items SET payload_json=?,updated_at=? WHERE pending_id=?',
                        (encoded_payload, now, lifecycle_pid),
                    )
            if before.get('receive_transaction_id'):
                tx_after = con.execute('SELECT * FROM transactions WHERE transaction_id=?', (before.get('receive_transaction_id'),)).fetchone()
                if tx_after:
                    DB._enqueue_sync(con, 'transaction', before.get('receive_transaction_id'), 'UPDATE', dict(tx_after))
        if (not lifecycle_pid and tx_row and tx_row.get('telegram_chat_id') is not None
                and tx_row.get('telegram_message_id') is not None):
            pending = DB.get_pending_by_message(tx_row['telegram_chat_id'], tx_row['telegram_message_id'])
            if pending:
                DB.update_pending(str(pending['pending_id']), payload=payload, detected_type='INCOME')
        self.refresh_all()
        show_toast(self, 'اطلاعات وام و ردیف ورودی اصلاح شد.')
        return 'اطلاعات وام، قسط‌ها، ردیف ورودی و رکورد ثبت دیتا همگام شد.'

    def _copy_transaction_187(self, table):
        rows=list(table.selected_rows() or [])
        if not rows:return None
        if len(rows)==1:return self._copy_transaction_row_187(table,rows[0])
        try:
            with DB.atomic():
                ids=[self._copy_transaction_row_187(table,row,notify=False) for row in rows]
        except Exception as exc:
            return messagebox.showerror('کپی انجام نشد',str(exc),parent=self)
        center=getattr(self,'approval_center',None)
        if center is not None:center.refresh()
        show_toast(self,f'{fa(len(ids))} ردیف با پیوست‌هایشان در ثبت دیتا کپی شدند؛ هنوز اثر مالی ندارند.')
        return ids

    def _copy_transaction_row_187(self, table, row, *, notify=True):
        from table_actions import copy_payload,copy_pending_attachments
        if not row:
            return None
        payload = deepcopy(self._transaction_payload_187(row))
        if table is getattr(self, 'document_table', None):
            payload = self._document_payload_from_row_187(row, payload)
        if not payload and row.get('loan_id'):
            payload = self._loan_payload_from_row_187(row)
        if not payload:
            direction = str(row.get('direction') or '').upper()
            payload = {
                'v18_title': 'ورودی' if direction == 'IN' else 'خروجی',
                'v18_subtype': 'سایر', 'detected_type': 'INCOME' if direction == 'IN' else 'OUTFLOW',
                'event_date_shamsi': row.get('shamsi_date') or row.get('event_date_shamsi') or '',
                'amount': row.get('amount') or 0,
                'payer_name': row.get('payer_name') or '',
                'receiver_name': row.get('receiver_name') or '',
                'description': row.get('description') or '',
            }
        payload=copy_payload(payload)
        payload['source'] = 'COPY_GUI_18_7'
        payload['copied_from_transaction_id'] = str(row.get('transaction_id') or row.get('loan_id') or '')
        mid = int(datetime.now().timestamp() * 1_000_000)
        DB.register_telegram_message(
            chat_id=-187, message_id=mid, raw_text=str(payload.get('description') or ''),
            content_type='copy_gui', message_date=datetime.now().isoformat(timespec='seconds'), state='RECEIVED',
        )
        pending_id = DB.create_or_replace_pending(
            telegram_chat_id=-187, telegram_message_id=mid,
            detected_type=str(payload.get('detected_type') or 'UNKNOWN'), payload=payload,
            confidence=1.0, status='PENDING_REVIEW',
        )
        from transaction_lifecycle import TransactionLifecycle
        try:source_id=TransactionLifecycle(DB).pending_for_row(row)
        except (ValueError,KeyError):source_id=''
        copy_pending_attachments(DB,source_id,pending_id)
        center = getattr(self, 'approval_center', None)
        if center is not None and notify:
            try:
                center.refresh()
            except Exception:
                pass
        if notify and table is getattr(self, 'document_table', None):
            return self._open_document_pending_wizard_187(pending_id, {
                **row,
                'pending_id': pending_id,
                'payload': payload,
            })
        if notify:show_toast(self, 'کپی به‌صورت سطر Pending زیر بررسی ثبت شد؛ پس از تأیید اثر مالی ایجاد می‌شود.')
        return pending_id

    def _save_loan_edit_187_from_editor(self, row, payload):
        return self._save_loan_edit_187(row, payload)

    def _build_cheques(self):
        """Install the same financial toolbar when the later cheque tab is built."""
        super()._build_cheques()
        self._install_financial_transaction_ui_187()

    def edit_cheque_row(self, row):
        return self._open_cheque_status_editor_187(row)

    def _open_cheque_status_editor_187(self, row):
        import sys
        from cheque_record_edit187 import open_cheque_record
        return open_cheque_record(self, row, sys.modules[__name__])

    def edit_cheque(self):
        row = self._one(self.cheque_table)
        if row:
            return self.edit_cheque_row(row)

    def _transaction_payload_187(self, row):
        """Return the original Data Entry payload for a posted transaction.

        Approved postings retain their pending id.  Reading that payload here
        means titles, subtypes and phase fields entered during Data Entry stay
        visible in the ledger while manual/legacy rows continue to use safe
        transaction fallbacks.  The small cache avoids repeated reads while
        a table is being refreshed or filtered.
        """
        row = row or {}
        pending_id = str(row.get('pending_id') or '').strip()
        cache = getattr(self, '_transaction_payload_cache187', None)
        if cache is None:
            cache = self._transaction_payload_cache187 = {}
        cache_key = pending_id or (
            f"message:{row.get('telegram_chat_id')}:{row.get('telegram_message_id')}"
            if row.get('telegram_chat_id') is not None and row.get('telegram_message_id') is not None
            else f"loan:{row.get('loan_id')}" if row.get('loan_id') else ''
        )
        if cache_key and cache_key in cache:
            return cache[cache_key]
        if not pending_id and row.get('telegram_chat_id') is not None and row.get('telegram_message_id') is not None:
            try:
                item = DB.get_pending_by_message(
                    int(row.get('telegram_chat_id')), int(row.get('telegram_message_id')),
                )
                payload = dict((item or {}).get('payload') or {})
                if payload:
                    if cache_key:
                        cache[cache_key] = payload
                    return payload
            except Exception:
                pass
        if not pending_id and row.get('loan_id'):
            try:
                loan_id = str(row.get('loan_id') or '').split('|', 1)[0].strip()
                loan = LoanService(DB).get_loan(loan_id) or {}
                payload = {
                    'v18_title': 'ورودی', 'v18_subtype': 'تسهیلات',
                    'detected_type': 'INCOME',
                    'event_date_shamsi': loan.get('received_date_shamsi') or row.get('shamsi_date') or '',
                    'amount': loan.get('net_received_amount') or row.get('amount') or 0,
                    'loan_total_amount': loan.get('principal_amount') or 0,
                    'principal_amount': loan.get('principal_amount') or 0,
                    'loan_bank': loan.get('lender_name') or '',
                    'loan_name': loan.get('description') or '',
                    'contract_number': loan.get('contract_number') or '',
                    'interest_rate': loan.get('interest_rate') or 0,
                    'installment_count': loan.get('installment_count') or 0,
                    'installment_amount': loan.get('installment_amount') or 0,
                    'total_interest': loan.get('total_interest') or 0,
                    'bank_fees': loan.get('bank_fees') or 0,
                    'first_due_date_shamsi': loan.get('first_due_date_shamsi') or '',
                    'loan_end_date': loan.get('loan_end_date') or '',
                    'guarantors': loan.get('guarantors') or '',
                }
                if cache_key:
                    cache[cache_key] = payload
                return payload
            except Exception:
                pass
        if not pending_id:
            return {}
        if cache_key in cache:
            return cache[cache_key]
        payload = {}
        try:
            item = DB.get_pending_item(pending_id)
            payload = dict((item or {}).get('payload') or {})
        except Exception:
            # A transaction can be imported from an older database without a
            # pending item.  Its ledger values remain fully usable.
            payload = {}
        cache[cache_key or pending_id] = payload
        return payload

    @staticmethod
    def _first_value_187(*values):
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return '-'

    @staticmethod
    def _rtl_display_text_187(value):
        """Localize digits and isolate embedded Latin runs in table cells."""
        text = fa(value if value is not None else '')
        check = re.match(r'^([☐☑])\s*(.*)$', text)
        if check:
            number = str(fa_grouped_number(check.group(2)))
            return f'{check.group(1)} {rtl_187(number)}'
        return rtl_187(str(fa_grouped_number(text)))

    @staticmethod
    def _normalise_transaction_text_187(value):
        return str(value or '').strip().replace('ي', 'ی').replace('ك', 'ک')

    @classmethod
    def _is_hidden_financial_id_key_187(cls, key):
        key_text = cls._normalise_transaction_text_187(key).lower()
        return (
            key_text in cls._FINANCIAL_HIDDEN_ID_KEYS_187
            or key_text.endswith('_id')
        )

    def _financial_column_label_187(self, table, key, label):
        if table not in (
            getattr(self, 'in_table', None), getattr(self, 'out_table', None),
        ):
            return label
        if key == 'cat':
            return 'نوع ورودی' if table is getattr(self, 'in_table', None) else 'نوع خروجی'
        return label

    def _transaction_filter_fields_for_table_187(self, table):
        if table is getattr(self, 'land_table', None):
            return self._LAND_FILTER_FIELDS_187
        if table is getattr(self, 'all_tx_table', None):
            return self._TRANSACTION_FILTER_FIELDS_187
        if table is getattr(self, 'exp_table', None):
            return self._EXPENSE_FILTER_FIELDS_187
        if table is getattr(self, 'document_table', None):
            return self._DOCUMENT_FILTER_FIELDS_187
        if table is getattr(self, 'in_table', None):
            return self._INCOME_FILTER_FIELDS_187
        if table is getattr(self, 'out_table', None):
            return self._OUTFLOW_FILTER_FIELDS_187
        if table is getattr(self, 'loan_table', None):
            return self._LOAN_FILTER_FIELDS_187
        if table is getattr(self, 'cheque_table', None):
            return self._CHEQUE_FILTER_FIELDS_187
        return self._TRANSACTION_FILTER_FIELDS_187

    def _income_type_187(self, row, payload):
        """Resolve the four Data Entry income categories without changing data."""
        payload = payload or {}
        candidates = (
            payload.get('v18_subtype'), payload.get('income_type'),
            payload.get('transaction_type_fa'), payload.get('transaction_subtype'),
            row.get('v18_subtype'), row.get('income_type'),
            row.get('transaction_type_fa'), row.get('transaction_subtype'),
            row.get('category'),
        )
        text = self._normalise_transaction_text_187(' '.join(
            str(value or '') for value in candidates
        ))
        category_code = str(row.get('category') or '').strip().upper()
        if (
            'تسهیلات' in text or payload.get('loan_name')
            or payload.get('selected_loan_name') or payload.get('loan_id')
            or category_code in {'LOAN_RECEIPT', 'LOAN'}
            or category_code.startswith('LOAN_')
        ):
            return 'تسهیلات'
        if (
            'فروش' in text or payload.get('sale_id') or payload.get('unit_id')
            or row.get('sale_id') or row.get('unit_id')
            or 'SALE' in category_code
        ):
            return 'فروش'
        if (
            'شرکا' in text or 'شریک' in text or 'قرض' in text
            or payload.get('partner_name') or payload.get('partner_kind')
            or 'PARTNER' in category_code or 'INJECTION' in category_code
        ):
            return 'شرکا/قرض'
        return 'سایر'

    def _income_description_187(self, row, payload, income_type):
        payload = payload or {}
        if income_type == 'تسهیلات':
            return self._first_value_187(
                payload.get('loan_name'), payload.get('selected_loan_name'),
                payload.get('loan_title'), row.get('loan_name'),
                row.get('description'),
            )
        if income_type == 'فروش':
            return self._first_value_187(
                payload.get('sale_id'), row.get('sale_id'),
                row.get('description'),
            )
        if income_type == 'شرکا/قرض':
            payer = self._first_value_187(
                payload.get('partner_name'), payload.get('payer_name'),
                row.get('payer_name'), row.get('receiver_name'),
            )
            kind = self._first_value_187(
                payload.get('partner_kind'), payload.get('deposit_type'),
                payload.get('loan_kind'), payload.get('نوع واریز'),
            )
            if payer != '-' and kind != '-':
                return f'{payer} — {kind}'
            # Older rows already store the normalized partner wording.
            return self._first_value_187(
                payload.get('description'), row.get('description'),
            )
        return self._first_value_187(
            payload.get('description'), payload.get('reason'),
            payload.get('babat'), row.get('description'),
        )

    def _outflow_type_187(self, row, payload):
        """Resolve the two Data Entry output categories used by خروجی‌ها."""
        payload = payload or {}
        category_code = str(row.get('category') or '').strip().upper()
        candidates = (
            payload.get('v18_subtype'), payload.get('outflow_type'),
            payload.get('transaction_type_fa'), payload.get('transaction_subtype'),
            row.get('v18_subtype'), row.get('outflow_type'),
            row.get('transaction_type_fa'), row.get('transaction_subtype'),
            row.get('category'),
        )
        text = self._normalise_transaction_text_187(' '.join(
            str(value or '') for value in candidates
        ))
        if (
            'اقساط' in text or payload.get('installment_number')
            or payload.get('installment_no') or payload.get('loan_id')
            or category_code == 'LOAN_INSTALLMENT'
            or category_code.startswith('LOAN_INSTALLMENT_')
        ):
            return 'اقساط'
        return 'سایر'

    def _outflow_db_context_187(self, row):
        """Read posted loan context without changing the financial source."""
        row = row or {}
        transaction_id = str(row.get('transaction_id') or '').strip()
        loan_id = str(row.get('loan_id') or '').split('|', 1)[0].strip()
        cache_key = transaction_id or (f'loan:{loan_id}' if loan_id else '')
        if not cache_key:
            return {}
        cache = getattr(self, '_outflow_db_context_cache187', None)
        if cache is None:
            cache = self._outflow_db_context_cache187 = {}
        if cache_key in cache:
            return cache[cache_key]
        context = {}
        try:
            with DB.read() as con:
                if transaction_id:
                    item = con.execute(
                        '''SELECT li.installment_number,
                                  l.description AS loan_name,
                                  l.lender_name AS loan_lender
                           FROM loan_installments li
                           JOIN loans l ON l.loan_id=li.loan_id
                           WHERE li.transaction_id=?
                           ORDER BY li.installment_number LIMIT 1''',
                        (transaction_id,),
                    ).fetchone()
                    if item:
                        context = dict(item)
                if not context and loan_id:
                    item = con.execute(
                        '''SELECT description AS loan_name,
                                  lender_name AS loan_lender
                           FROM loans WHERE loan_id=? LIMIT 1''',
                        (loan_id,),
                    ).fetchone()
                    if item:
                        context = dict(item)
        except Exception:
            # Imported/manual rows may not have a matching loan record.  The
            # wizard and ledger fields remain valid fallbacks in that case.
            context = {}
        cache[cache_key] = context
        return context

    def _outflow_description_187(self, row, payload, output_type):
        payload = payload or {}
        if output_type == 'اقساط':
            number = self._first_value_187(
                payload.get('installment_number'), payload.get('installment_no'),
                payload.get('loan_installment_number'),
                payload.get('sequence_no'), row.get('installment_number'),
                row.get('installment_no'), row.get('loan_installment_number'),
                row.get('sequence_no'),
            )
            loan_name = self._first_value_187(
                payload.get('selected_loan_name'), payload.get('loan_name'),
                payload.get('loan_bank'), row.get('loan_name'),
                row.get('loan_lender'),
            )
            context = {}
            if number == '-' or loan_name == '-':
                context = self._outflow_db_context_187(row)
            if number == '-':
                number = self._first_value_187(context.get('installment_number'))
            if number == '-':
                paid_before = self._first_value_187(
                    payload.get('paid_installments_before'),
                    row.get('paid_installments_before'),
                )
                if paid_before != '-':
                    try:
                        number = str(parse_int(paid_before) + 1)
                    except (TypeError, ValueError):
                        number = '-'
            if number != '-':
                number = fa(number)
            if loan_name == '-':
                loan_name = self._first_value_187(
                    context.get('loan_name'), context.get('loan_lender'),
                    payload.get('loan_id'), row.get('loan_id'),
                )
            if number != '-' and loan_name != '-':
                return f'قسط {number} — {loan_name}'
            if loan_name != '-':
                return f'قسط — {loan_name}'
            return self._first_value_187(
                payload.get('description'), row.get('description'),
            )
        return self._first_value_187(
            payload.get('description'), payload.get('reason'),
            payload.get('babat'), row.get('description'),
        )

    def _prepare_transaction_rows_187(self, rows):
        """Decorate ledger rows with the fields captured by ثبت دیتا."""
        expense_rows = {}
        try:
            expense_rows = {
                str(item.get('expense_id')): item
                for item in SERVICE.list_construction_expenses()
                if item.get('expense_id')
            }
        except Exception:
            expense_rows = {}
        for index, row in enumerate(rows or [], 1):
            payload = self._transaction_payload_187(row)
            expense = expense_rows.get(str(row.get('expense_id') or ''), {})
            direction = str(row.get('direction') or '').upper()
            detected = str(payload.get('detected_type') or '').upper()
            fallback_type = (
                'هزینه' if row.get('expense_id') else
                ('ورودی' if direction == 'IN' else 'خروجی')
            )
            row['_ui_row_number187'] = index
            row['_ui_title187'] = transaction_title(row, payload)
            if direction == 'IN':
                income_type = self._income_type_187(row, payload)
                row['_ui_income_type187'] = income_type
                row['_ui_type187'] = income_type
                row['_ui_desc187'] = self._income_description_187(
                    row, payload, income_type,
                )
            elif direction == 'OUT' and not row.get('expense_id'):
                output_type = self._outflow_type_187(row, payload)
                row['_ui_outflow_type187'] = output_type
                row['_ui_type187'] = output_type
                row['_ui_desc187'] = self._outflow_description_187(
                    row, payload, output_type,
                )
            else:
                row['_ui_type187'] = self._first_value_187(
                    payload.get('v18_subtype'), payload.get('transaction_type_fa'),
                    {'EXPENSE': 'هزینه', 'INCOME': 'ورودی',
                     'OUTFLOW': 'خروجی', 'CHEQUE': 'چک'}.get(detected),
                    fallback_type,
                )
                row['_ui_desc187'] = self._first_value_187(
                    payload.get('description'), row.get('description'),
                )
            row['_ui_phase187'] = self._first_value_187(
                payload.get('construction_stage'), payload.get('main_phase'),
                payload.get('phase_name'),
                expense.get('phase_name'), expense.get('construction_stage'),
            )
            row['_ui_subphase187'] = self._first_value_187(
                payload.get('activity_name'), payload.get('subphase'),
                payload.get('sub_phase'), payload.get('expense_category'),
                expense.get('activity_name_display'),
                expense.get('activity_name'),
            )
            row['_ui_date187'] = self._first_value_187(
                row.get('shamsi_date'), payload.get('event_date_shamsi'),
            )
            payer = self._first_value_187(
                row.get('payer_name'), payload.get('payer_name'),
            )
            partner_name = str(payload.get('partner_name') or '').strip()
            partner_source = str(payload.get('partner_source') or '').strip()
            if direction == 'IN' and partner_name == 'شرکا':
                payer = f'شرکا — {partner_source}' if partner_source else 'شرکا'
            row['_ui_payer187'] = payer
            row['_ui_receiver187'] = self._first_value_187(
                row.get('receiver_name'), payload.get('receiver_name'),
            )
        return rows or []

    def _transaction_values_187(self, row, table=None):
        target = table if table is not None else self.all_tx_table
        uid = str(getattr(target, '_row_uid', lambda value: '')(row))
        checked = uid in getattr(target, '_barkav_checked_uids187', set())
        mark = '☑' if checked else '☐'
        values_by_key = {
            'row': f"{mark} {fa_grouped_number(row.get('_ui_row_number187') or 0)}",
            'date': row.get('_ui_date187') or '-',
            'title': row.get('_ui_title187') or '-',
            'type': row.get('_ui_type187') or '-',
            'desc': row.get('_ui_desc187') or '-',
            'amount': money(row.get('amount')),
            'payer': row.get('_ui_payer187') or '-',
            'receiver': row.get('_ui_receiver187') or '-',
            'phase': row.get('_ui_phase187') or '-',
            'subphase': row.get('_ui_subphase187') or '-',
        }
        columns = (
            self._LAND_TRANSACTION_COLUMNS_187
            if target is getattr(self, 'land_table', None)
            else self._TRANSACTION_COLUMNS_187
        )
        if not any(key == 'receipt' for key, _label, _width in columns):
            columns = (*columns, ('receipt','رسید',100))
        values_by_key['receipt'] = self._receipt_indicator_187(row)
        return [self._rtl_display_text_187(values_by_key[key]) for key, _label, _width in columns]

    def _apply_all_transaction_columns_187(self, table=None):
        """Re-assert the transaction headings after inherited table upgrades."""
        table = table if table is not None else getattr(self, 'all_tx_table', None)
        tree = getattr(table, 'tree', None)
        if table is None or tree is None:
            return
        definitions = (
            self._LAND_TRANSACTION_COLUMNS_187
            if table is getattr(self, 'land_table', None)
            else self._TRANSACTION_COLUMNS_187
        )
        if not any(key == 'receipt' for key, _label, _width in definitions):
            definitions = (*definitions, ('receipt', 'رسید', 100))
        columns = tuple(c[0] for c in definitions)
        try:
            table.columns = list(definitions)
            tree.configure(columns=columns, displaycolumns=tuple(reversed(columns)))
            for key, label, width in definitions:
                tree.heading(key, text=label, anchor='e' if key != 'row' else 'center')
                tree.column(key, width=width, minwidth=42,
                            anchor='e' if key != 'row' else 'center', stretch=True)
        except tk.TclError:
            return

    def _apply_financial_table_columns_187(self, table):
        """Give every financial SmartTable the same RTL row/check column.

        The inherited tables retain their logical business columns and
        renderers.  Only the active 18.7 presentation layer adds the row
        marker and reverses the display order, so exports and accounting data
        remain unchanged.
        """
        if table is None or not hasattr(table, 'tree'):
            return
        if table in (getattr(self, 'all_tx_table', None), getattr(self, 'land_table', None)):
            self._apply_all_transaction_columns_187(table)
            return
        tree = table.tree
        current_columns = tuple(getattr(table, 'columns', ()) or ())
        # A later 18.7 report extension may add business columns (for example
        # construction-cost grouping).  Keep those columns while ensuring the
        # row marker remains the first logical column.
        current_business = tuple(item for item in current_columns
                                 if item[0] != 'row')
        if table is getattr(self, 'out_table', None) and not any(
            item[0] == 'payer' for item in current_business
        ):
            output_business = []
            inserted = False
            for item in current_business:
                if not inserted and item[0] == 'receiver':
                    output_business.append(('payer', 'واریزکننده', 132))
                    inserted = True
                output_business.append(item)
            if not inserted:
                output_business.append(('payer', 'واریزکننده', 132))
            current_business = tuple(output_business)
        if table is getattr(self, 'document_table', None):
            # A non-financial record has no monetary reference or link column.
            # Its attachment state is represented by an image indicator instead.
            # Keep the established ``'links', 'image'`` contract visible while
            # inserting the new phase column alongside it.
            current_business = tuple(
                item for item in current_business
                if item[0] not in {'amount', 'reference_amount', 'source_amount', 'links', 'phase', 'image'}
                and self._normalise_transaction_text_187(item[1]) not in {'مبلغ مرجع', 'اتصال به'}
            )
            current_business = (*current_business, ('phase', 'فاز ساخت', 170), ('image', 'تصویر سند', 112))
        elif table is getattr(self, 'loan_table', None):
            current_business = self._LOAN_TABLE_COLUMNS_187
        elif table is getattr(self, 'exp_table', None):
            has_plan_row = any(
                key in {'plan_ref', 'plan_row', 'plan_line', 'plan_id'}
                or self._normalise_transaction_text_187(label) == 'ردیف پلان'
                for key, label, _width in current_business
            )
            expense_columns = []
            for key, label, width in current_business:
                normalized_label = self._normalise_transaction_text_187(label)
                if has_plan_row and (
                    key in {'phase', 'construction_stage'}
                    or normalized_label == 'مرحله ساخت'
                ):
                    continue
                if key in {'plan_ref', 'plan_row', 'plan_line', 'plan_id'} or normalized_label == 'ردیف پلان':
                    expense_columns.append((key, 'فاز ساخت', 170))
                elif key in {'phase', 'construction_stage'} or normalized_label == 'مرحله ساخت':
                    expense_columns.append((key, 'فاز ساخت', width))
                else:
                    expense_columns.append((key, label, width))
            current_business = tuple(expense_columns)
        elif table is getattr(self, 'cheque_table', None):
            # Treeview display is reversed for RTL; placing guarantee last in
            # the logical schema keeps it at the far left of the visible grid.
            guarantee = [item for item in current_business if item[0] == 'guarantee']
            current_business = tuple(item for item in current_business if item[0] != 'guarantee')
            cheque_columns = [item for item in current_business if item[0] not in {'status', 'return_state'}]
            registration_index = next((index for index, item in enumerate(cheque_columns)
                                       if item[0] == 'reg'), len(cheque_columns) - 1)
            cheque_columns[registration_index + 1:registration_index + 1] = [
                ('status', 'وضعیت چک', 150), ('return_state', 'وضعیت عودت چک', 200),
            ]
            current_business = (*cheque_columns, *guarantee)
        if not any(item[0] == 'receipt' for item in current_business):
            index=next((i for i,item in enumerate(current_business) if item[0]=='guarantee'),len(current_business))
            current_business = (*current_business[:index], ('receipt','رسید',100), *current_business[index:])
        base_columns = getattr(table, '_barkav_base_columns187', None)
        if current_business and current_business != tuple(base_columns or ()):
            base_columns = current_business
            table._barkav_base_columns187 = base_columns
        elif base_columns is None:
            base_columns = current_business
            table._barkav_base_columns187 = base_columns
        if not base_columns:
            return
        columns = (
            ('row', 'ردیف', 58),
            *(
                (key, self._financial_column_label_187(table, key, label), width)
                for key, label, width in base_columns
            ),
        )
        keys = tuple(item[0] for item in columns)
        visible_keys = tuple(
            key for key in keys
            if not self._is_hidden_financial_id_key_187(key)
        )
        hidden_keys = tuple(key for key in keys if key not in visible_keys)
        try:
            table.columns = list(columns)
            tree._barkav_displaycolumns187 = tuple(reversed(visible_keys))
            if table in (
                getattr(self, 'in_table', None),
                getattr(self, 'out_table', None),
            ):
                # The inherited currency pass treats any heading containing
                # «ورودی»/«خروجی» as a money heading.  Keep these type labels
                # semantic; only amount columns may receive a currency unit.
                non_currency = set(
                    getattr(tree, '_barkav_non_currency_columns_186', ())
                )
                non_currency.add('cat')
                tree._barkav_non_currency_columns_186 = non_currency
            tree.configure(columns=keys, displaycolumns=tree._barkav_displaycolumns187)
            for key, label, width in columns:
                tree.heading(key, text=label,
                             anchor='e' if key != 'row' else 'center')
                tree.column(key, width=width,
                            minwidth=0 if key in hidden_keys else (42 if key == 'row' else max(42, int(width))),
                            anchor='e' if key != 'row' else 'center',
                            stretch=(key != 'row' and key not in hidden_keys))
            table._barkav_hidden_id_columns187 = hidden_keys
            table._barkav_financial_columns187 = True
            # Column rebuilds reset Treeview headings and can replace its
            # scrollbar callbacks. Reattach the row/checkbox painter last.
            decorate_rows_187(tree)
        except tk.TclError:
            return

    def _prepare_financial_rows_187(self, table, rows):
        """Attach a stable visible row number without changing persisted data."""
        for index, row in enumerate(rows or (), 1):
            if isinstance(row, dict):
                row['_ui_row_number187'] = index
        if table is not None:
            table._barkav_source_rows187 = list(rows or ())

    def _receipt_indicator_187(self, row):
        from receipt_gallery187 import receipt_paths
        count = len(receipt_paths(DB, str(row.get('pending_id') or ''), row))
        return f'📎 {fa_grouped_number(count)}' if count else '—'

    def _loan_borrower_name_187(self, row):
        row = row or {}
        cached = row.get('_ui_loan_borrower187')
        if cached is not None:
            return cached
        payload = self._transaction_payload_187(row)
        borrower = self._first_value_187(
            row.get('borrower_name'), row.get('loan_borrower'),
            row.get('receiver_name'), payload.get('borrower_name'),
            payload.get('loan_borrower'), payload.get('receiver_name'),
        )
        if borrower == '-' and row.get('receive_transaction_id'):
            try:
                with DB.read() as con:
                    result = con.execute(
                        'SELECT receiver_name FROM transactions WHERE transaction_id=?',
                        (str(row.get('receive_transaction_id')),),
                    ).fetchone()
                borrower = self._first_value_187(
                    result['receiver_name'] if result else None,
                )
            except (sqlite3.Error, KeyError, TypeError):
                borrower = '-'
        row['_ui_loan_borrower187'] = borrower
        return borrower

    def _loan_last_payment_date_187(self, row):
        row = row or {}
        cached = row.get('_ui_last_payment_date187')
        if cached is not None:
            return cached
        last_paid = self._first_value_187(
            row.get('last_payment_date_shamsi'), row.get('last_paid_date_shamsi'),
        )
        loan_id = str(row.get('loan_id') or '').strip()
        if last_paid == '-' and loan_id:
            try:
                with DB.read() as con:
                    result = con.execute(
                        '''SELECT MAX(paid_date_shamsi) AS paid_date
                           FROM loan_installments
                           WHERE loan_id=? AND paid_amount>0''',
                        (loan_id,),
                    ).fetchone()
                last_paid = self._first_value_187(
                    result['paid_date'] if result else None,
                )
            except (sqlite3.Error, KeyError, TypeError):
                last_paid = '-'
        row['_ui_last_payment_date187'] = last_paid
        return last_paid

    def _wrap_financial_row_values_187(self, table):
        """Prepend a visual check marker while preserving each table renderer."""
        if table is None or table in (getattr(self, 'all_tx_table', None), getattr(self, 'land_table', None)):
            return
        if table is getattr(self, 'exp_table', None):
            source_columns = tuple(
                item for item in getattr(table, 'columns', ())
                if item[0] != 'row'
            )

            def expense_values(row, target=table, columns=source_columns):
                payload = self._transaction_payload_187(row)
                phase = self._first_value_187(
                    row.get('phase_name'), row.get('construction_stage'),
                    payload.get('construction_stage'), row.get('phase'),
                )
                values_by_key = {
                    'date': self._first_value_187(row.get('shamsi_date'), row.get('date')),
                    'final': money(row.get('final_amount')),
                    'paid': money(row.get('paid_amount')),
                    'phase': phase,
                    'construction_stage': phase,
                    'plan_ref': phase,
                    # reports_stage18_7 installs these two columns using
                    # private presentation keys.  Keep them linked to the
                    # same expense fields as the public table columns.
                    '_plan_ref187': phase,
                    'plan_row': phase,
                    'plan_line': phase,
                    'plan_id': phase,
                    'activity': self._first_value_187(
                        row.get('activity_name_display'), row.get('activity_name'),
                    ),
                    'cost_group': self._first_value_187(
                        payload.get('cost_group'), payload.get('expense_category'),
                        row.get('cost_group'), row.get('category'),
                    ),
                    '_cost_group187': self._first_value_187(
                        payload.get('cost_group'), payload.get('expense_category'),
                        row.get('cost_group'), row.get('expense_category'),
                        row.get('category'),
                    ),
                    'category': self._first_value_187(
                        payload.get('cost_group'), payload.get('expense_category'),
                        row.get('cost_group'), row.get('category'),
                    ),
                    'payer': self._first_value_187(
                        row.get('payer_name_display'), row.get('payer_name'),
                    ),
                    'receiver': self._first_value_187(
                        row.get('receiver_name_display'), row.get('receiver_name'),
                    ),
                    'desc': self._first_value_187(row.get('description')),
                    'receipt': self._receipt_indicator_187(row),
                    'status': {
                        'POSTED': 'ثبت‌شده', 'ACTIVE': 'فعال',
                        'CANCELLED': 'لغوشده', 'VOIDED': 'باطل‌شده',
                        'DRAFT': 'پیش‌نویس', 'PENDING': 'در انتظار',
                    }.get(str(row.get('status') or '').upper(), row.get('status') or '-'),
                    'expense_id': row.get('expense_id') or '',
                    'id': row.get('expense_id') or '',
                }
                rendered = [values_by_key.get(key, self._first_value_187(row.get(key)))
                            for key, _label, _width in columns]
                uid = str(target._row_uid(row))
                checked = uid in getattr(target, '_barkav_checked_uids187', set())
                marker = '☑' if checked else '☐'
                number = fa_grouped_number(row.get('_ui_row_number187') or 0)
                return [self._rtl_display_text_187(value) for value in (f'{marker} {number}', *rendered)]

            expense_values._barkav_financial_wrapper187 = True
            expense_values._barkav_base_renderer187 = getattr(table, 'row_values', None)
            table.row_values = expense_values
            return
        if table is getattr(self, 'loan_table', None):
            def loan_values(row, target=table):
                paid_date = self._loan_last_payment_date_187(row)
                next_date = self._first_value_187(row.get('next_due_shamsi'))
                next_amount = row.get('next_due_amount')
                next_value = next_date if next_amount in (None, '') else (
                    f'{next_date} | {money(next_amount)}'
                )
                status = {
                    'ACTIVE': 'فعال', 'CANCELLED': 'لغوشده',
                    'CLOSED': 'تسویه‌شده', 'PAID': 'تسویه‌شده',
                }.get(str(row.get('status') or '').upper(), row.get('status') or '-')
                values_by_key = {
                    'row': '',
                    'date': self._first_value_187(row.get('received_date_shamsi')),
                    'lender': self._first_value_187(row.get('lender_name')),
                    'borrower': self._loan_borrower_name_187(row),
                    'principal': money(row.get('principal_amount')),
                    'received': money(row.get('net_received_amount')),
                    'interest': money(
                        int(row.get('total_interest') or 0) + int(row.get('bank_fees') or 0)
                    ),
                    'paid': money(row.get('paid_total')),
                    'remain': money(row.get('remaining_debt')),
                    'installment_amount': money(row.get('installment_amount')),
                    'last_payment': paid_date,
                    'next': next_value,
                    'status': status,
                    'loan_id': row.get('loan_id') or '',
                    'id': row.get('loan_id') or '',
                }
                uid = str(target._row_uid(row))
                checked = uid in getattr(target, '_barkav_checked_uids187', set())
                values_by_key['row'] = f"{'☑' if checked else '☐'} {fa_grouped_number(row.get('_ui_row_number187') or 0)}"
                values_by_key['receipt'] = self._receipt_indicator_187(row)
                return [self._rtl_display_text_187(values_by_key.get(key, '-'))
                        for key, _label, _width in target.columns]

            loan_values._barkav_financial_wrapper187 = True
            loan_values._barkav_base_renderer187 = getattr(table, 'row_values', None)
            table.row_values = loan_values
            return
        if table is getattr(self, 'document_table', None):
            source_columns = tuple(
                item for item in getattr(table, 'columns', ())
                if item[0] != 'row'
            )
            document_labels = {
                'WORKSHOP_CALENDAR': 'تقویم کارگاهی', 'DAILY_REPORT': 'گزارش روزانه',
                'DOCUMENT': 'داکیومنت', 'REMINDER': 'یادآوری', 'NOTE': 'یادداشت',
                'INFO': 'اطلاع‌رسانی', 'INVOICE_NOTE': 'فاکتور',
            }

            def document_values(row, target=table, columns=source_columns):
                values_by_key = {
                    'date': self._first_value_187(row.get('event_date_shamsi'), row.get('date')),
                    'type': document_labels.get(str(row.get('document_type') or '').upper(), row.get('document_type') or '-'),
                    'desc': row.get('description') or '-',
                    'phase': self._first_value_187(
                        self._transaction_payload_187(row).get('construction_stage'),
                        row.get('construction_stage'), row.get('phase_name'),
                    ),
                    'amount': money(row.get('amount')),
                    'image': self._document_image_indicator_187(row),
                    'document_id': row.get('document_id') or '',
                    'id': row.get('document_id') or '',
                }
                rendered = [
                    values_by_key.get(key, self._first_value_187(row.get(key)))
                    for key, _label, _width in columns
                ]
                uid = str(target._row_uid(row))
                checked = uid in getattr(target, '_barkav_checked_uids187', set())
                marker = '☑' if checked else '☐'
                number = fa_grouped_number(row.get('_ui_row_number187') or 0)
                return [self._rtl_display_text_187(value) for value in (f'{marker} {number}', *rendered)]

            document_values._barkav_financial_wrapper187 = True
            document_values._barkav_base_renderer187 = getattr(table, 'row_values', None)
            table.row_values = document_values
            return
        if table is getattr(self, 'out_table', None):
            # The output table adds the payer column in the active layer and
            # replaces raw wizard values with the two requested output types.
            source_columns = tuple(
                item for item in getattr(table, 'columns', ())
                if item[0] != 'row'
            )

            def output_values(row, target=table, columns=source_columns):
                values_by_key = {
                    'date': self._first_value_187(
                        row.get('_ui_date187'), row.get('shamsi_date'),
                    ),
                    'amount': money(row.get('amount')),
                    'cat': row.get('_ui_outflow_type187') or 'سایر',
                    'category': row.get('_ui_outflow_type187') or 'سایر',
                    'type': row.get('_ui_outflow_type187') or 'سایر',
                    'payer': self._first_value_187(
                        row.get('_ui_payer187'), row.get('payer_name'),
                    ),
                    'payer_name': self._first_value_187(
                        row.get('_ui_payer187'), row.get('payer_name'),
                    ),
                    'receiver': self._first_value_187(
                        row.get('_ui_receiver187'), row.get('receiver_name'),
                    ),
                    'receiver_name': self._first_value_187(
                        row.get('_ui_receiver187'), row.get('receiver_name'),
                    ),
                    'desc': row.get('_ui_desc187') or '-',
                    'description': row.get('_ui_desc187') or '-',
                    'receipt': self._receipt_indicator_187(row),
                    'transaction_id': row.get('transaction_id') or '',
                    'id': row.get('transaction_id') or '',
                }
                rendered = [
                    values_by_key.get(key, self._first_value_187(row.get(key)))
                    for key, _label, _width in columns
                ]
                uid = str(target._row_uid(row))
                checked = uid in getattr(target, '_barkav_checked_uids187', set())
                marker = '☑' if checked else '☐'
                number = fa_grouped_number(row.get('_ui_row_number187') or 0)
                return [self._rtl_display_text_187(value) for value in (f'{marker} {number}', *rendered)]

            output_values._barkav_financial_wrapper187 = True
            output_values._barkav_base_renderer187 = getattr(
                table, 'row_values', None,
            )
            table.row_values = output_values
            return
        if table is getattr(self, 'in_table', None):
            # The inherited income renderer exposes the raw category and
            # description.  Replace only those two presentation values with
            # the wizard-derived labels while retaining the original column
            # count (including the hidden internal id).
            source_columns = tuple(
                item for item in getattr(table, 'columns', ())
                if item[0] != 'row'
            )

            def income_values(row, target=table, columns=source_columns):
                values_by_key = {
                    'date': self._first_value_187(
                        row.get('_ui_date187'), row.get('shamsi_date'),
                    ),
                    'amount': money(row.get('amount')),
                    'cat': row.get('_ui_income_type187') or 'سایر',
                    'category': row.get('_ui_income_type187') or 'سایر',
                    'type': row.get('_ui_income_type187') or 'سایر',
                    'payer': self._first_value_187(
                        row.get('_ui_payer187'), row.get('payer_name'),
                    ),
                    'payer_name': self._first_value_187(
                        row.get('_ui_payer187'), row.get('payer_name'),
                    ),
                    'desc': row.get('_ui_desc187') or '-',
                    'description': row.get('_ui_desc187') or '-',
                    'receipt': self._receipt_indicator_187(row),
                    'transaction_id': row.get('transaction_id') or '',
                    'id': row.get('transaction_id') or '',
                }
                rendered = [
                    values_by_key.get(key, self._first_value_187(row.get(key)))
                    for key, _label, _width in columns
                ]
                uid = str(target._row_uid(row))
                checked = uid in getattr(target, '_barkav_checked_uids187', set())
                marker = '☑' if checked else '☐'
                number = fa_grouped_number(row.get('_ui_row_number187') or 0)
                return [self._rtl_display_text_187(value) for value in (f'{marker} {number}', *rendered)]

            income_values._barkav_financial_wrapper187 = True
            income_values._barkav_base_renderer187 = getattr(
                table, 'row_values', None,
            )
            table.row_values = income_values
            return
        renderer = getattr(table, 'row_values', None)
        if getattr(renderer, '_barkav_financial_wrapper187', False):
            # A compatible extension (currently the construction-cost
            # category renderer) may already return the complete row,
            # including the marker.  Reusing it avoids a second marker and
            # therefore keeps every value aligned with its heading.
            table._barkav_original_row_values187 = getattr(
                renderer, '_barkav_base_renderer187', renderer,
            )
            return
        if renderer is None:
            return
        table._barkav_original_row_values187 = renderer

        if table is getattr(self, 'cheque_table', None):
            def cheque_values(row, target=table, base_renderer=renderer):
                logical_columns = tuple(
                    str(item[0]) for item in (getattr(target, 'columns', ()) or ())
                )
                business_keys = tuple(key for key in logical_columns if key != 'row')
                rendered = v18.v175._cheque_row_values175(row, target.columns)
                values_by_key = dict(zip(business_keys, rendered))
                values_by_key['receipt'] = self._receipt_indicator_187(row)
                uid = str(target._row_uid(row))
                checked = uid in getattr(target, '_barkav_checked_uids187', set())
                row_value = f"{'☑' if checked else '☐'} {fa_grouped_number(row.get('_ui_row_number187') or 0)}"
                try:
                    tree_columns = tuple(str(key) for key in target.tree.cget('columns'))
                except tk.TclError:
                    tree_columns = logical_columns
                result = []
                if 'row' not in tree_columns:
                    result.append(row_value)
                for key in tree_columns:
                    if key == CHECK_COLUMN_187:
                        continue
                    if key == 'row':
                        result.append(row_value)
                    else:
                        result.append(values_by_key.get(key, '-'))
                return [self._rtl_display_text_187(value) for value in result]

            cheque_values._barkav_financial_wrapper187 = True
            cheque_values._barkav_base_renderer187 = renderer
            table.row_values = cheque_values
            return

        def values(row, target=table, base_renderer=renderer):
            try:
                rendered = list(base_renderer(row) or ())
            except Exception:
                rendered = []
            uid = str(target._row_uid(row))
            checked = uid in getattr(target, '_barkav_checked_uids187', set())
            marker = '☑' if checked else '☐'
            number = fa_grouped_number(row.get('_ui_row_number187') or 0)
            business = [key for key, _label, _width in target.columns if key != 'row']
            if 'receipt' in business:
                index = business.index('receipt')
                if len(rendered) < len(business):rendered.insert(index,self._receipt_indicator_187(row))
                else:rendered[index]=self._receipt_indicator_187(row)
            return [self._rtl_display_text_187(value) for value in (f'{marker} {number}', *rendered)]

        values._barkav_financial_wrapper187 = True
        values._barkav_base_renderer187 = renderer
        table.row_values = values

    def _install_financial_table_contract_187(self, table):
        """Install columns, row numbering and renderer wrapping after a refresh."""
        if table is None or not hasattr(table, 'tree'):
            return
        self._apply_financial_table_columns_187(table)
        rows = list(getattr(table, '_barkav_source_rows187',
                            getattr(table, 'all_rows', ())) or ())
        self._prepare_financial_rows_187(table, rows)
        self._wrap_financial_row_values_187(table)

    def edit_transaction_row(self, row):
        if row.get('_registered_review187'):
            pending = DB.get_pending_item(str(row.get('pending_id') or ''))
            if pending:
                return self.approval_center.open_editor(pending)
            return None
        return super().edit_transaction_row(row)

    def edit_transaction(self, table):
        row = self._one(table)
        if row and row.get('_registered_review187'):
            return self.edit_transaction_row(row)
        return super().edit_transaction(table)

    def delete_transaction(self, table):
        row = self._one(table)
        if row and row.get('_registered_review187'):
            return self._delete_tx_row(row)
        return super().delete_transaction(table)

    def _delete_tx_row(self, row):
        if not row or not row.get('_registered_review187') or row.get('posting_id'):
            return super()._delete_tx_row(row)
        if row.get('cheque_id'):
            return self._cancel_cheque_row(row)
        if not self._confirm_row_action('حذف', 'رکورد انتخاب‌شده حذف شود؟ سابقه حذف نگه داشته می‌شود.'):
            return
        try:
            if row.get('document_id'):
                self.rich.delete_document(row['document_id'])
            else:
                SERVICE.delete_registered_note(row['pending_id'])
            self.refresh_all()
        except Exception as exc:
            messagebox.showerror('خطا', str(exc), parent=self)

    def _refresh_all_transactions_view_187(self):
        table = getattr(self, 'all_tx_table', None)
        if table is None:
            return
        rows = SERVICE.list_registered_records()
        self._prepare_transaction_rows_187(rows)
        table._barkav_source_rows187 = rows
        table.set_rows(rows, self._transaction_values_187)
        self._refresh_transaction_filter_choices_187(table)
        self._apply_transaction_view_filter_187(table)
        land_table = getattr(self, 'land_table', None)
        if land_table is not None:
            land_rows = [row for row in rows if row.get('_ui_title187') == LAND_TITLE]
            land_table._barkav_source_rows187 = land_rows
            self._install_financial_table_contract_187(land_table)
            land_table.set_rows(land_rows, lambda row: self._transaction_values_187(row, land_table))
            self._refresh_transaction_filter_choices_187(land_table)
            self._apply_transaction_view_filter_187(land_table)

    def refresh_financial(self):
        """Keep inherited totals/data loading and retarget only all-transactions."""
        # Payloads can be edited from the double-click editor.  Never retain a
        # pre-edit copy when the ledger is refreshed.
        self._transaction_payload_cache187 = {}
        self._outflow_db_context_cache187 = {}
        super().refresh_financial()
        for name in self._FINANCIAL_TABLE_NAMES_187[1:]:
            table = getattr(self, name, None)
            if table is not None and hasattr(table, 'all_rows'):
                source_rows = list(table.all_rows or [])
                if table is getattr(self, 'land_table', None):
                    continue  # Refreshed from the complete registered-record view below.
                if table is getattr(self, 'exp_table', None):
                    source_rows = [row for row in source_rows if transaction_title(row,
                                   self._transaction_payload_187(row)) != LAND_TITLE]
                    table.set_rows(source_rows, getattr(table, 'row_values', None))
                if table is getattr(self, 'document_table', None) and not source_rows:
                    try:
                        source_rows = list(self.rich.list_documents() or [])
                        table.all_rows = source_rows
                        table.set_rows(source_rows, getattr(table, 'row_values', None))
                    except Exception:
                        logging.getLogger(__name__).exception('Non-financial document table refresh failed')
                if table in (
                    getattr(self, 'in_table', None),
                    getattr(self, 'out_table', None),
                ):
                    self._prepare_transaction_rows_187(source_rows)
                table._barkav_source_rows187 = source_rows
                self._install_financial_table_contract_187(table)
        self._refresh_all_transactions_view_187()
        for name in self._FINANCIAL_TABLE_NAMES_187[1:]:
            table = getattr(self, name, None)
            if table is not None:
                self._refresh_transaction_filter_choices_187(table)
                self._apply_transaction_view_filter_187(table)
        try:
            # Stage 18.4/18.6 schedule a currency-heading pass with
            # after_idle.  Queue this contract after it so the requested
            # headings remain stable without changing that inherited helper.
            self.after_idle(self._apply_all_transaction_columns_187)
        except tk.TclError:
            pass

    def refresh_cheques(self):
        """Refresh cheques and reapply the shared 18.7 financial table contract."""
        super().refresh_cheques()
        table = getattr(self, 'cheque_table', None)
        if table is None:
            return
        table._barkav_source_rows187 = list(getattr(table, 'all_rows', ()) or ())
        self._install_financial_table_contract_187(table)
        self._refresh_transaction_filter_choices_187(table)
        self._apply_transaction_view_filter_187(table)
        # Stage17 refreshers replace the renderer while rebuilding rows. Run
        # the refreshed financial contract again so the row marker and
        # key-based cheque values are repainted against the reordered columns.
        table.apply_filter()
        decorate_rows_187(table.tree)

    def _delete_transaction_selection_187(self, table):
        """Use the table's audited bulk path whenever more than one row is selected."""
        rows = list(getattr(table, 'selected_rows', lambda: [])() or [])
        bulk = getattr(table, '_delete_selected_many', None)
        handler = getattr(table, 'delete_handler', None)
        if len(rows) > 1 and callable(bulk) and callable(handler):
            return bulk()
        return self._transaction_action_187(table, 'delete')

    def _transaction_action_187(self, table, action):
        """Dispatch the common toolbar actions to existing safe handlers."""
        if action == 'copy':
            return self._copy_transaction_187(table)
        if action == 'add':
            if table is getattr(self, 'document_table', None):
                return self._open_document_wizard_187()
            if table is getattr(self, 'loan_table', None):
                return self.add_loan()
            center = getattr(self, 'approval_center', None)
            if center is not None and hasattr(center, 'manual_transaction'):
                return center.manual_transaction()
            return None
        if action == 'edit':
            if table is getattr(self, 'exp_table', None):
                return self.edit_expense()
            if table is getattr(self, 'loan_table', None):
                row = self._one(table)
                return self.edit_loan_row(row) if row else None
            if table is getattr(self, 'cheque_table', None):
                return self.edit_cheque()
            if table is getattr(self, 'document_table', None):
                row = self._one(table)
                return self._open_document_edit_wizard_187(row) if row else None
            return self.edit_transaction(table)
        if action == 'delete':
            if table is getattr(self, 'exp_table', None):
                return self.delete_expense()
            if table is getattr(self, 'loan_table', None):
                return self.cancel_loan()
            if table is getattr(self, 'cheque_table', None):
                row = self._one(table)
                return self._cancel_cheque_row(row) if row else None
            if table is getattr(self, 'document_table', None):
                row = self._one(table)
                if row and getattr(table, 'delete_handler', None):
                    return table.delete_handler(row)
                return None
            return self.delete_transaction(table)
        return None

    def _transaction_filter_text_187(self, row, field):
        """Return the visible value used by one financial-toolbar filter."""
        row = row or {}
        payload = self._transaction_payload_187(row)
        if field == 'عنوان تراکنش':
            return transaction_title(row, payload)
        if field == 'نوع سند':
            code = str(row.get('document_type') or '').strip().upper()
            return _DOCUMENT_CODE_TO_SUBTYPE_187.get(
                code,
                self._first_value_187(
                    payload.get('v18_subtype'), row.get('v18_subtype'),
                    row.get('transaction_subtype'), row.get('document_type'),
                ),
            )
        if field == 'نوع خروجی':
            return self._first_value_187(
                row.get('_ui_outflow_type187'), row.get('_ui_type187'),
            )
        if field == 'نوع ورودی':
            return self._first_value_187(
                row.get('_ui_income_type187'), row.get('_ui_type187'),
            )
        if field in {'واریز کننده', 'واریزکننده'}:
            return self._first_value_187(
                row.get('_ui_payer187'), row.get('payer_name'),
                row.get('payer_name_display'), payload.get('payer_name'),
            )
        if field in {'گیرنده', 'دریافت کننده', 'گیرنده وام'}:
            return self._first_value_187(
                row.get('_ui_receiver187'), row.get('receiver_name'),
                row.get('receiver_name_display'), row.get('borrower_name'),
                payload.get('borrower_name'), payload.get('loan_borrower'),
                row.get('receiver'),
            )
        if field in {'فاز اصلی', 'فاز ساخت'}:
            return self._first_value_187(
                row.get('_ui_phase187'), row.get('phase_name'),
                row.get('construction_stage'), payload.get('construction_stage'),
                row.get('main_phase'), row.get('phase'),
            )
        if field in {'تاریخ', 'تاریخ سررسید'}:
            return self._first_value_187(
                row.get('due_date_shamsi') if field == 'تاریخ سررسید' else None,
                row.get('_ui_date187'), row.get('shamsi_date'),
                row.get('event_date_shamsi'), row.get('received_date_shamsi'),
                row.get('date'), row.get('due_date_shamsi'),
            )
        if field in {'بابت', 'شرح'}:
            return self._first_value_187(
                row.get('_ui_desc187'), row.get('description'), row.get('expense_description'),
                payload.get('description'), payload.get('reason'), payload.get('babat'),
            )
        if field == 'دسته‌بندی':
            return self._first_value_187(
                payload.get('cost_group'), payload.get('expense_category'),
                row.get('cost_group'), row.get('expense_category'), row.get('category'),
            )
        if field == 'بانک':
            return self._first_value_187(
                row.get('issuer_bank'), row.get('lender_name'), payload.get('loan_bank'),
            )
        if field == 'نام وام':
            return self._first_value_187(
                row.get('description'), row.get('loan_name'), payload.get('loan_name'),
                payload.get('selected_loan_name'),
            )
        if field == 'صاحب حساب':
            return self._first_value_187(row.get('issuer_name'), payload.get('issuer_name'))
        if field == 'ثبت':
            state = str(row.get('registration_state') or '').upper()
            return {
                'REGISTERED': 'ثبت‌شده', 'UNREGISTERED': 'ثبت‌نشده',
                'UNKNOWN': 'نامشخص',
            }.get(state, self._first_value_187(row.get('registration_state')))
        if field == 'شماره صیادی':
            return self._first_value_187(row.get('cheque_serial'), row.get('serial'))
        if field == 'وضعیت':
            state = str(row.get('status') or '').upper()
            return {
                'ACTIVE': 'فعال', 'CANCELLED': 'لغوشده', 'CLOSED': 'تسویه‌شده',
                'PAID': 'تسویه‌شده', 'ISSUED': 'صادرشده', 'DUE': 'سررسیدشده',
                'CASHED': 'وصول‌شده', 'POSTED': 'ثبت‌شده',
            }.get(state, self._first_value_187(row.get('status')))
        if field == 'نوع تراکنش':
            direction = str(row.get('direction') or '').upper()
            fallback = (
                'هزینه' if row.get('expense_id') else
                ('ورودی' if direction == 'IN' else 'خروجی')
            )
            return self._first_value_187(
                row.get('_ui_type187'), row.get('transaction_type_fa'),
                row.get('v18_subtype'), row.get('transaction_subtype'),
                fallback,
            )
        return '-'

    def _transaction_filter_values_187(self, table, field):
        fields = self._transaction_filter_fields_for_table_187(table)
        if field not in fields or field == 'همه':
            return ('همه',)
        if field == 'عنوان تراکنش':
            return ('همه', *TRANSACTION_TITLES)
        if field == 'نوع ورودی':
            return ('همه', 'تسهیلات', 'فروش', 'شرکا/قرض', 'سایر')
        if field == 'نوع خروجی':
            return ('همه', 'اقساط', 'سایر')
        source = list(getattr(table, '_barkav_source_rows187', getattr(table, 'all_rows', [])) or [])
        values = {
            self._transaction_filter_text_187(row, field)
            for row in source
        }
        values.discard('-')
        special = ('جدیدترین', 'قدیمی‌ترین') if field in {'تاریخ', 'تاریخ سررسید'} else ()
        return ('همه', *special, *sorted(values))

    def _refresh_transaction_filter_choices_187(self, table, reset_value=False):
        field_var = getattr(table, '_barkav_filter_field_var187', None)
        value_var = getattr(table, '_barkav_filter_value_var187', None)
        value_combo = getattr(table, '_barkav_filter_value_combo187', None)
        if field_var is None or value_var is None or value_combo is None:
            return
        field = str(field_var.get() or 'همه')
        fields = self._transaction_filter_fields_for_table_187(table)
        if field not in fields:
            field = 'همه'
            field_var.set(field)
        values = self._transaction_filter_values_187(table, field)
        try:
            value_combo.configure(values=values)
        except tk.TclError:
            return
        if reset_value or str(value_var.get() or 'همه') not in values:
            value_var.set('همه')

    def _on_transaction_filter_field_changed_187(self, table):
        self._refresh_transaction_filter_choices_187(table, reset_value=True)
        self._apply_transaction_view_filter_187(table)

    def _apply_transaction_view_filter_187(self, table):
        field_var = getattr(table, '_barkav_filter_field_var187', None)
        value_var = getattr(table, '_barkav_filter_value_var187', None)
        field = str(field_var.get() if field_var is not None else 'همه') or 'همه'
        selected = str(value_var.get() if value_var is not None else 'همه') or 'همه'
        source = list(getattr(table, '_barkav_source_rows187', getattr(table, 'all_rows', [])) or [])
        if field in {'تاریخ', 'تاریخ سررسید'} and selected in {'جدیدترین', 'قدیمی‌ترین'}:
            table._barkav_sort_field187 = field
            table._barkav_sort_descending187 = selected == 'جدیدترین'
            rows = source
        elif field == 'همه' or selected == 'همه':
            rows = source
        else:
            rows = [
                row for row in source
                if self._transaction_filter_text_187(row, field) == selected
            ]
        rows = self._sort_financial_rows_187(table, rows)
        values = (
            self._transaction_values_187
            if table is getattr(self, 'all_tx_table', None)
            else getattr(table, 'row_values', None) or
            getattr(table, '_barkav_original_row_values187', None)
        )
        if values is not None:
            table.set_rows(rows, values)

    @staticmethod
    def _financial_date_sort_key_187(value):
        parts = tuple(int(part) for part in re.findall(r'\d+', en(str(value or ''))))
        return (0, *parts) if parts else (1, str(value or '').casefold())

    def _sort_financial_rows_187(self, table, rows):
        field = getattr(table, '_barkav_sort_field187', '')
        descending = bool(getattr(table, '_barkav_sort_descending187', False))
        if not field:
            return list(rows)
        if field == 'ردیف':
            return sorted(
                rows,
                key=lambda row: int(row.get('_ui_row_number187') or 0),
                reverse=descending,
            )
        if field in {'تاریخ', 'تاریخ سررسید'}:
            dated = []
            undated = []
            for row in rows:
                value = self._transaction_filter_text_187(row, field)
                (undated if self._financial_date_sort_key_187(value)[0] else dated).append(row)
            return sorted(
                dated,
                key=lambda row: self._financial_date_sort_key_187(
                    self._transaction_filter_text_187(row, field)
                ),
                reverse=descending,
            ) + undated
        def sort_key(row):
            value = self._transaction_filter_text_187(row, field)
            number = re.sub(r'[,،\s]', '', en(value))
            try:
                return (0, float(number))
            except (TypeError, ValueError):
                return (1, str(value or '').casefold())
        return sorted(rows, key=sort_key, reverse=descending)

    def _set_financial_sort_187(self, table, field, descending=False):
        table._barkav_sort_field187 = field
        table._barkav_sort_descending187 = bool(descending)
        self._apply_transaction_view_filter_187(table)

    def _transaction_pending_ids_187(self, db, row) -> list[str]:
        """Find the original Pending row for every financial-table shape."""
        row = dict(row or {})
        pending_ids = []
        direct = str(row.get('pending_id') or '').strip()
        if direct:
            pending_ids.append(direct)
        lookup = {
            key: str(row.get(key) or '').strip()
            for key in ('transaction_id', 'expense_id', 'payment_id', 'cheque_id')
            if str(row.get(key) or '').strip()
        }
        if not lookup:
            return pending_ids
        where = ' OR '.join(f'{key}=?' for key in lookup)
        try:
            with db.read() as con:
                linked = con.execute(
                    f'SELECT pending_id FROM financial_postings WHERE {where}',
                    tuple(lookup.values()),
                ).fetchall()
        except sqlite3.Error:
            return pending_ids
        for item in linked:
            pending_id = str(item['pending_id'] or '').strip()
            if pending_id and pending_id not in pending_ids:
                pending_ids.append(pending_id)
        return pending_ids

    def _transaction_document_paths_187(self, table, row) -> list[str]:
        """Resolve attachment paths for every visible financial sub-tab row."""
        from receipt_gallery187 import receipt_paths
        row = dict(row or {}) if isinstance(row, dict) else {}
        return receipt_paths(getattr(self,'db',None) or DB, str(row.get('pending_id') or ''), row)
    def _transaction_export_payload_187(self, table):
        """Return visible logical columns/rows, excluding hidden internal IDs."""
        tree = getattr(table, 'tree', None)
        if tree is not None:
            try:
                logical_columns = tuple(tree.cget('columns') or ())
                raw_displayed = tree.cget('displaycolumns')
                displayed = logical_columns if raw_displayed in ('#all', ('#all',)) else tuple(raw_displayed or ())
                displayed_set = set(displayed)
                hidden_keys = set(getattr(table, '_barkav_hidden_id_columns187', ()))
                visible_keys = [
                    key for key in logical_columns
                    if key in displayed_set
                    and key not in hidden_keys
                    and str(key).lower() != 'id'
                    and not str(key).lower().endswith('_id')
                ]
                headers = [str(tree.heading(key, 'text') or key) for key in visible_keys]
                index_by_key = {key: index for index, key in enumerate(logical_columns)}
                rows = []
                source_rows = getattr(table, '_iid_to_row', {}) or {}
                from report_document_stage18_7 import selected_tree_items
                for iid in selected_tree_items(tree):
                    raw_values = list(tree.item(iid, 'values') or ())
                    # Shared previews and file writers address dictionary rows by
                    # their displayed Persian header.  Keeping logical tree keys
                    # here made every value resolve to the fallback "-".
                    values = {
                        header: raw_values[index_by_key[key]] if index_by_key[key] < len(raw_values) else ''
                        for key, header in zip(visible_keys, headers)
                    }
                    paths = self._transaction_document_paths_187(
                        table, source_rows.get(str(iid), {})
                    )
                    if paths:
                        values['__document_paths_187'] = paths
                    rows.append(values)
                return headers, rows
            except (AttributeError, KeyError, tk.TclError):
                pass
        try:
            headers, rows = table.current_report_rows(selected_only=bool(table.selected_rows()))
        except (AttributeError, TypeError):
            headers = [label for _key, label, _width in getattr(table, 'columns', ())]
            rows = []
            renderer = getattr(table, 'row_values', None)
            for row in getattr(table, 'filtered_rows', getattr(table, 'all_rows', ())) or ():
                rows.append(renderer(row) if renderer else list(row.values()))
        return list(headers or ()), [list(row or ()) for row in rows or ()]

    def _save_transaction_export_187(self, table, selected, orientation=None,
                                     addressee='سایر', include_documents=True):
        """Save the same visible payload that the shared preview displays."""
        if selected not in {'Excel', 'PDF', 'پرینت'}:
            return False
        headers, rows = self._transaction_export_payload_187(table)
        export_rows = [list(row.get(header, '') for header in headers) if isinstance(row, dict) else list(row or ()) for row in rows]
        document_columns = [index for index, header in enumerate(headers)
                            if header in {'نمایش سند', 'فیش واریزی', 'رسید', 'سند'}]
        if not include_documents:
            for row in export_rows:
                for index in document_columns:
                    if index < len(row):
                        row[index] = '-'
        from export_utils import export_pdf, export_xlsx, print_file
        suffix = '.xlsx' if selected == 'Excel' else '.pdf'
        try:
            path = filedialog.asksaveasfilename(
                parent=self,
                title=f'خروجی {selected} تراکنش‌ها',
                defaultextension=suffix,
                filetypes=[('Excel', '*.xlsx')] if suffix == '.xlsx' else [('PDF', '*.pdf')],
            )
            if not path:
                return False
            destination = Path(path)
            if selected == 'Excel':
                export_xlsx(destination, headers, export_rows, title='گزارش تراکنش‌ها',
                            summary_lines=[f'جهت ارائه به: {addressee}'])
            else:
                summary = [f'جهت ارائه به: {addressee}']
                total_var = getattr(table, 'total', None)
                if total_var is not None:
                    try:
                        summary = [str(total_var.get())]
                    except (AttributeError, tk.TclError):
                        summary = []
                export_pdf(
                    destination, headers, export_rows, title='گزارش تراکنش‌ها',
                    summary_lines=summary, orientation=orientation,
                )
                if selected == 'پرینت':
                    print_file(destination)
            messagebox.showinfo('خروجی', f'فایل ساخته شد:\n{destination}', parent=self)
            return True
        except Exception as exc:
            messagebox.showerror('خروجی', f'خروجی {selected} انجام نشد:\n{exc}', parent=self)
            return False
    def _preview_transaction_export_187(self, table, selected):
        headers, rows = self._transaction_export_payload_187(table)
        return show_export_preview_187(
            self,
            export_format=selected,
            headers=headers,
            rows=rows,
            title='پیش‌نمایش خروجی تراکنش‌ها',
            table_caption='تراکنش‌ها',
            row_label='ردیف',
            include_addressee=True,
            on_confirm=lambda choice, orientation, addressee, include_documents: self._save_transaction_export_187(
                table, choice, orientation, addressee, include_documents,
            ),
        )

    def _export_transaction_187(self, table, format_var):
        selected = str(format_var.get() or 'خروجی')
        try:
            if selected in {'Excel', 'PDF', 'پرینت'}:
                preview = getattr(self, '_preview_transaction_export_187', None)
                if callable(preview):
                    preview(table, selected)
                else:
                    # Compatibility for lightweight callers that invoke the
                    # inherited dispatch method without a Stage187 instance.
                    if selected == 'Excel':
                        table.export_excel()
                    elif selected == 'PDF':
                        table.export_pdf()
                    else:
                        table.print_report()
        except Exception as exc:
            messagebox.showerror('خروجی', f'پیش‌نمایش {selected} انجام نشد:\n{exc}', parent=self)
        finally:
            try:
                format_var.set('خروجی')
            except (AttributeError, tk.TclError):
                pass
    def _financial_context_menu_187(self, table, event):
        iid = table.tree.identify_row(event.y)
        if iid:
            if iid not in table.tree.selection(): table.tree.selection_set(iid)
            table.tree.focus(iid)
        menu = tk.Menu(table, tearoff=0)
        menu.add_command(label='➕ افزودن', command=lambda: self._transaction_action_187(table, 'add'))
        menu.add_command(label='✏️ ویرایش', command=lambda: self._transaction_action_187(table, 'edit'))
        if table is getattr(self, 'loan_table', None):
            menu.add_command(label='↪ ردیف متناظر در ورودی',
                             command=lambda: self._open_loan_input_row_187())
        elif table is getattr(self, 'in_table', None):
            menu.add_command(label='↪ رفتن به رکورد ثبت دیتا',
                             command=lambda: self._open_transaction_data_entry_187())
        delete_label = '🗑 حذف انتخاب‌ها' if len(table.selected_rows()) > 1 else '🗑 حذف'
        menu.add_command(label=delete_label, command=lambda: self._delete_transaction_selection_187(table))
        from transaction_lifecycle_ui import add_menu_extras
        add_menu_extras(menu, table)
        menu.add_command(label='📋 کپی', command=lambda: self._transaction_action_187(table, 'copy'))
        menu.add_command(label='🔄 بروزرسانی', command=self._table_refresh_187)
        menu.add_separator()
        filter_menu = tk.Menu(menu, tearoff=0)
        filter_menu.add_command(
            label='همه',
            command=lambda: self._set_transaction_filter_187(table, 'همه', 'همه'),
        )
        for field in self._transaction_filter_fields_for_table_187(table)[1:]:
            values_menu = tk.Menu(filter_menu, tearoff=0)
            for value in self._transaction_filter_values_187(table, field)[1:]:
                values_menu.add_command(
                    label=value,
                    command=lambda target_field=field, target_value=value:
                    self._set_transaction_filter_187(table, target_field, target_value),
                )
            filter_menu.add_cascade(label=field, menu=values_menu)
        menu.add_cascade(label='نمایش براساس', menu=filter_menu)
        sorting_menu = tk.Menu(menu, tearoff=0)
        sorting_menu.add_command(
            label='بر اساس ردیف',
            command=lambda: self._set_financial_sort_187(table, 'ردیف'),
        )
        sorting_menu.add_command(
            label='تاریخ؛ جدیدترین به قدیمی‌ترین',
            command=lambda: self._set_financial_sort_187(
                table, 'تاریخ سررسید' if table is getattr(self, 'cheque_table', None) else 'تاریخ', True,
            ),
        )
        sorting_menu.add_command(
            label='تاریخ؛ قدیمی‌ترین به جدیدترین',
            command=lambda: self._set_financial_sort_187(
                table, 'تاریخ سررسید' if table is getattr(self, 'cheque_table', None) else 'تاریخ', False,
            ),
        )
        menu.add_cascade(label='سورتینگ', menu=sorting_menu)
        output_menu = tk.Menu(menu, tearoff=0)
        for output in ('PDF', 'Excel', 'پرینت'):
            output_menu.add_command(
                label=output,
                command=lambda value=output: self._export_transaction_context_187(table, value),
            )
        menu.add_cascade(label='خروجی', menu=output_menu)
        self._right_align_financial_menu_187(menu)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return 'break'

    def _right_align_financial_menu_187(self, menu, _seen=None):
        """Right-align native menu labels while retaining Tk's native actions."""
        if _seen is None:
            _seen = set()
        try:
            identity = str(menu)
            if identity in _seen:
                return
            _seen.add(identity)
            end = menu.index('end')
            if end is None:
                return
            font_name = menu.cget('font') or 'TkMenuFont'
            font = tkfont.nametofont(font_name, root=menu)
            entries = []
            for index in range(int(end) + 1):
                if menu.type(index) == 'separator':
                    continue
                label = str(menu.entrycget(index, 'label') or '')
                entries.append((index, label))
            if entries:
                target_width = max(font.measure(label) for _index, label in entries)
                space_width = max(1, font.measure(' '))
                for index, label in entries:
                    missing = max(0, target_width - font.measure(label))
                    pad = ' ' * (int((missing + space_width - 1) // space_width))
                    menu.entryconfigure(index, label=rtl_187(pad + label))
                    try:
                        child_name = str(menu.entrycget(index, 'menu') or '')
                        if child_name:
                            child = menu.nametowidget(child_name)
                            self._right_align_financial_menu_187(child, _seen)
                    except (tk.TclError, KeyError, AttributeError):
                        continue
        except (tk.TclError, AttributeError, TypeError, ValueError):
            # Test doubles and older Tk builds may not expose native entry
            # metadata; their menu actions remain intact in that case.
            return

    def _set_transaction_filter_187(self, table, field, value):
        field_var = getattr(table, '_barkav_filter_field_var187', None)
        value_var = getattr(table, '_barkav_filter_value_var187', None)
        if field_var is not None:
            field_var.set(field)
        self._refresh_transaction_filter_choices_187(table)
        if value_var is not None:
            value_var.set(value)
        self._apply_transaction_view_filter_187(table)

    def _export_transaction_context_187(self, table, value):
        try:
            if value in {'Excel', 'PDF', 'پرینت'}:
                preview = getattr(self, '_preview_transaction_export_187', None)
                if callable(preview):
                    preview(table, value)
                else:
                    # Compatibility for lightweight callers that invoke the
                    # inherited context dispatch without a Stage187 instance.
                    if value == 'Excel':
                        table.export_excel()
                    elif value == 'PDF':
                        table.export_pdf()
                    else:
                        table.print_report()
        except Exception as exc:
            messagebox.showerror('خروجی', f'پیش‌نمایش {value} انجام نشد:\n{exc}', parent=self)

    def _open_transaction_record_on_double_click_187(self, table, event):
        """Open ورودی/خروجی with the same record editor as the toolbar."""
        iid = table.tree.identify_row(event.y)
        if iid:
            table.tree.selection_set(iid)
            table.tree.focus(iid)
            if table is getattr(self, 'loan_table', None):
                return self._open_loan_details_187(table.selected_rows()[0])
            shown = tuple(table.tree.cget('displaycolumns'))
            column = table.tree.identify_column(event.x)
            index = int(column[1:])-1 if column.startswith('#') else -1
            if 0 <= index < len(shown) and shown[index] == 'receipt':
                from receipt_gallery187 import show_receipts
                row = table.selected_rows()[0]
                return show_receipts(self, self._transaction_document_paths_187(table,row))
            self._transaction_action_187(table, 'edit')
        return 'break'

    def _toggle_transaction_checkbox_187(self, table, event):
        displaycolumns = tuple(table.tree.cget('displaycolumns') or ())
        try:
            row_display_index = displaycolumns.index('row') + 1
        except ValueError:
            return None
        if table.tree.identify_column(event.x) != f"#{row_display_index}":
            return None
        iid = table.tree.identify_row(event.y)
        if not iid:
            return 'break'
        row = getattr(table, '_iid_to_row', {}).get(iid)
        if row is None:
            return 'break'
        uid = table._row_uid(row)
        checked = getattr(table, '_barkav_checked_uids187', set())
        if uid in checked:
            checked.remove(uid)
        else:
            checked.add(uid)
        values = list(table.tree.item(iid, 'values'))
        try:
            # Treeview item values are indexed by the underlying ``columns``;
            # displaycolumns only changes their visual order.
            row_column = tuple(table.tree.cget('columns')).index('row')
            values[row_column] = self._rtl_display_text_187(
                f"{'☑' if uid in checked else '☐'} {fa_grouped_number(row.get('_ui_row_number187') or 0)}"
            )
            table.tree.item(iid, values=values)
        except (ValueError, tk.TclError):
            pass
        return 'break'

    def _install_financial_transaction_ui_187(self):
        self._financial_transaction_ui187 = True
        tables = (
            getattr(self, 'all_tx_table', None), getattr(self, 'exp_table', None),
            getattr(self, 'land_table', None),
            getattr(self, 'in_table', None), getattr(self, 'out_table', None),
            getattr(self, 'loan_table', None), getattr(self, 'cheque_table', None),
            getattr(self, 'document_table', None),
        )
        for table in tables:
            if not isinstance(table, tk.Misc) or not hasattr(table, 'tree'):
                continue
            if hasattr(table, '_barkav_transaction_toolbar187'):
                continue
            parent = table.master
            # Remove the inherited page-level action row.  Its handlers are
            # still used below; only the duplicate visual row is hidden.
            for child in list(parent.winfo_children()):
                if child is table:
                    break
                texts = []
                for nested in self._walk_187(child):
                    try:
                        texts.append(str(nested.cget('text') or ''))
                    except (tk.TclError, AttributeError):
                        pass
                if any(token in texts for token in (
                    '✏️ ویرایش', '✏️ ویرایش چک', '🗑 حذف', '📎 رسید',
                    '➕ ثبت وام', '📅 اقساط / پرداخت', '🚫 لغو وام',
                    'مدیریت چک‌ها', 'ویرایش مشخصات/وضعیت',
                )):
                    try:
                        child.pack_forget()
                    except tk.TclError:
                        pass
            # The SmartTable toolbar has compact utilities, but the financial
            # screen owns one canonical action row.  Keep its quick variable
            # alive and expose it in the new row instead.
            legacy_bar = next(iter(table.winfo_children()), None)
            if isinstance(legacy_bar, tk.Misc):
                try:
                    legacy_bar.pack_forget()
                except tk.TclError:
                    pass
                table._barkav_legacy_bar187 = legacy_bar
            toolbar = ttk.Frame(parent, padding=(0, 3))
            toolbar.pack(fill='x', before=table)
            table._barkav_transaction_toolbar187 = toolbar
            table._barkav_checked_uids187 = set()
            table._barkav_original_row_values187 = getattr(table, 'row_values', None)
            table._barkav_source_rows187 = list(getattr(table, 'all_rows', []) or [])
            table._barkav_filter_field_var187 = tk.StringVar(value='همه')
            table._barkav_filter_value_var187 = tk.StringVar(value='همه')
            self._apply_financial_table_columns_187(table)
            if table is getattr(self, 'document_table', None):
                self._install_document_preview_187(table)
            table.tree.bind('<Button-1>', lambda event, target=table: self._toggle_transaction_checkbox_187(target, event), add='+')
            if table is not None:
                table.tree.unbind('<Double-1>')
                table.tree.bind(
                    '<Double-1>',
                    lambda event, target=table: self._open_transaction_record_on_double_click_187(target, event),
                )

            def action(name, target=table):
                return lambda: self._transaction_action_187(target, name)
            # One order in every tab (2026-09-27): افزودن, ویرایش, کپی, حذف.
            ttk.Button(toolbar, text='افزودن', command=action('add'), style='Toolbar.TButton').pack(side='right', padx=2)
            ttk.Button(toolbar, text='ویرایش', command=action('edit'), style='Toolbar.TButton').pack(side='right', padx=2)
            ttk.Button(toolbar, text='کپی', command=action('copy'), style='Toolbar.TButton').pack(side='right', padx=2)
            ttk.Button(
                toolbar, text='حذف',
                command=lambda target=table: self._delete_transaction_selection_187(target),
                style='Toolbar.TButton',
            ).pack(side='right', padx=2)
            ttk.Label(toolbar, text='نمایش براساس', anchor='e').pack(side='right', padx=(8, 2))
            field_combo = ttk.Combobox(
                toolbar, textvariable=table._barkav_filter_field_var187,
                values=self._transaction_filter_fields_for_table_187(table), state='readonly',
                width=15, justify='right',
            )
            field_combo.pack(side='right', padx=2)
            value_combo = ttk.Combobox(
                toolbar, textvariable=table._barkav_filter_value_var187,
                values=('همه',), state='readonly', width=15, justify='right',
            )
            value_combo.pack(side='right', padx=2)
            table._barkav_filter_field_combo187 = field_combo
            table._barkav_filter_value_combo187 = value_combo
            field_combo.bind('<<ComboboxSelected>>', lambda _event, target=table: self._on_transaction_filter_field_changed_187(target), add='+')
            value_combo.bind('<<ComboboxSelected>>', lambda _event, target=table: self._apply_transaction_view_filter_187(target), add='+')
            self._refresh_transaction_filter_choices_187(table)
            output_var = tk.StringVar(value='خروجی')
            table._barkav_output_var187 = output_var
            output_combo = ttk.Combobox(toolbar, textvariable=output_var,
                                        values=('خروجی', 'PDF', 'Excel', 'پرینت'),
                                        state='readonly', width=15, justify='right',
                                        style='Output.TCombobox')
            output_combo.pack(side='left', padx=2)
            output_combo.bind(
                '<<ComboboxSelected>>',
                lambda _event, target=table, var=output_var:
                self._export_transaction_187(target, var),
                add='+',
            )
            table._barkav_output_combo187 = output_combo
            table.tree.unbind('<Button-3>')
            table.tree.bind('<Button-3>', lambda event, target=table: self._financial_context_menu_187(target, event))

        all_table = getattr(self, 'all_tx_table', None)
        if all_table is not None:
            self._prepare_transaction_rows_187(list(getattr(all_table, 'all_rows', []) or []))
            all_table._barkav_source_rows187 = list(getattr(all_table, 'all_rows', []) or [])
        income_table = getattr(self, 'in_table', None)
        if income_table is not None:
            income_rows = list(getattr(income_table, 'all_rows', []) or [])
            self._prepare_transaction_rows_187(income_rows)
            income_table._barkav_source_rows187 = income_rows
            self._refresh_transaction_filter_choices_187(income_table)
            self._apply_transaction_view_filter_187(income_table)
        output_table = getattr(self, 'out_table', None)
        if output_table is not None:
            output_rows = list(getattr(output_table, 'all_rows', []) or [])
            self._prepare_transaction_rows_187(output_rows)
            output_table._barkav_source_rows187 = output_rows
            self._refresh_transaction_filter_choices_187(output_table)
            self._apply_transaction_view_filter_187(output_table)

    def _build_contractors_187(self):
        """Insert the contractors tab immediately after sales.

        Structure only for now - the panel is built from the shared template,
        so its layout and styling are already final and only its data layer
        remains to be written.
        """
        tab = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.contractors_tab187 = tab
        position = len(self.notebook.tabs())
        for index, tab_id in enumerate(self.notebook.tabs()):
            if self.notebook.tab(tab_id, 'text') == SALES_TAB_187:
                position = index + 1
                break
        self.notebook.insert(position, tab, text='پیمانکاران')
        self.contractors187 = ContractorsPanel187(
            tab, db=DB, base_dir=BASE_DIR, on_changed=self.refresh_all,
            # The contract titles come from the project's reference price
            # catalogue, which is what the specification calls the reference file.
            rich=getattr(self, 'rich', None),
        )
        self.contractors187.pack(fill='both', expand=True)

    def edit_project_settings(self):
        ProjectSettingsDialog187(self, self.refresh_all)

    DISPLAY_MODES_187 = (('dark', 'تاریک'), ('light', 'روشن'), ('vivid', 'رنگی'))

    def _theme_choice_label_187(self) -> str:
        return f'انتخاب تم: تم {fa(theme_id_187())}'

    def _display_mode_label_187(self) -> str:
        settings = load_ui()
        if str(settings.get('appearance') or 'dark').lower() == 'light':
            mode = 'روشن'
        elif int(settings.get('theme_id') or DEFAULT_THEME_ID_187) == 3:
            mode = 'رنگی'
        else:
            mode = 'تاریک'
        return f'حالت نمایش: {mode}'

    def _set_display_mode_187(self, mode: str):
        """Apply one of the three display modes from the footer.

        Dark and light are appearances of the same theme; vivid is a separate
        theme, so this sets whichever of the two the mode implies and leaves
        the other alone.
        """
        old = load_ui()
        new = dict(old)
        if mode == 'vivid':
            new['appearance'] = 'dark'
            new['theme_id'] = 3
        else:
            new['appearance'] = mode
            if int(new.get('theme_id') or DEFAULT_THEME_ID_187) == 3:
                new['theme_id'] = DEFAULT_THEME_ID_187
        if new == old:
            return
        # _settings_saved only reacts to a change; it re-reads the store rather
        # than writing it, so the choice has to be persisted first.
        save_ui(new)
        self._settings_saved(old, new)

    def _fix_clock_185(self):
        """The clock is a themed pill now, so the inherited tk styling cannot apply.

        ``Stage186Dashboard._fix_clock_185`` sets ``bg``, ``fg`` and
        ``highlightthickness`` on the label. Those are classic tk options and a
        ``ttk.Label`` rejects them, so the 18.7 clock is left to its style and
        only its alignment is set here.
        """
        label = getattr(self, 'datetime_label_186', None)
        if label is None:
            return super()._fix_clock_185()
        # The 18.7 clock carries no box, so the inherited glass fill and
        # highlight are dropped and only the shared colours are taken.
        p = palette_187()
        try:
            label.configure(
                anchor='center', justify='center',
                bg=p['surface_alt'], fg=p['text'], highlightthickness=0, bd=0,
            )
        except tk.TclError:
            pass

    def _build_shell_search_187(self, top, p):
        """A search field in the shell, in the place Excel puts its own.

        It filters the table on whichever tab is showing, so one field serves
        every screen instead of each tab growing its own. It sits in the
        bar's top row beside the mark, with Ctrl+K named for everything else.
        """
        self.shell_search187 = tk.StringVar()
        host = tk.Frame(top, bg=p['surface'])
        self.shell_search_host187 = host
        entry = ttk.Entry(host, textvariable=self.shell_search187,
                          justify='right', width=30)
        icon = line_icon_187('search', size=16, colour=p['text_secondary'], background=None, master=self)
        glass = tk.Label(host, image=icon, text='' if icon is not None else '⌕',
                         bg=p['surface'], bd=0, cursor='hand2')
        if icon is not None: glass.image = icon
        glass.pack(side='right', padx=(6, 0))
        glass.bind('<Button-1>', lambda _e: self._open_advanced_search187(), add='+')
        attach_tooltip(glass, 'جستجوی پیشرفته', side='below')
        self.shell_search_glass187 = glass
        entry.pack(side='right')
        self.shell_search_entry187 = entry
        self._pack_shell_search_187()
        self._install_search_placeholder_187(entry)
        attach_tooltip(entry, 'جست‌وجو در جدول تب فعال — Ctrl+K برای رفتن به هر جای برنامه',
                       side='below')
        self.shell_search187.trace_add('write', lambda *_: self._apply_shell_search_187())

    def _open_advanced_search187(self):
        from advanced_search_dialog187 import AdvancedSearchDialog187
        window = getattr(self, '_advanced_search187', None)
        if window is not None and window.winfo_exists():
            window.lift(); return
        query = '' if getattr(self, '_search_placeholder_active187', False) else self.shell_search187.get()
        self._advanced_search187 = AdvancedSearchDialog187(self, service=SERVICE,
            rich=getattr(self, 'rich', None), initial_query=query)

    def _pack_shell_search_187(self):
        host = getattr(self, 'shell_search_host187', None)
        if host is not None:
            # Beside the mark, at the left end of the bar's top row.
            host.pack(side='left', padx=(4, 8))

    def _install_search_placeholder_187(self, entry):
        """Show a faint prompt while the field is empty.

        ttk.Entry has no placeholder of its own, so the prompt is real text
        that is cleared on focus and restored when the field is left empty.
        A flag keeps the filter from treating the prompt as a query.
        """
        # A right-to-left mark alone only fixes a line that starts with a
        # digit (barkav_ui/bidi.py); it does not reorder a Latin run sitting
        # *inside* an RTL line, and Tk has no real bidi layout of its own to
        # do that for it - "Ctrl+K" kept unsettling the line, reported live
        # as still looking scrambled after the first fix (operator round
        # 2026-09-28). The shortcut is still in the tooltip below; the
        # inline prompt is Persian-only now, so there is no mixed-script
        # run left for Tk to get wrong. Plain «جستجو», no ellipsis
        # (operator round 2026-09-28, second pass).
        prompt = rtl_187('جستجو')
        self._search_placeholder_active187 = True

        def show():
            if not self.shell_search187.get():
                self._search_placeholder_active187 = True
                self.shell_search187.set(prompt)
                entry.configure(foreground=palette_187()['empty'])

        def hide(_event=None):
            if self._search_placeholder_active187:
                self._search_placeholder_active187 = False
                self.shell_search187.set('')
                entry.configure(foreground=palette_187()['text_primary'])

        def restore(_event=None):
            if not self.shell_search187.get():
                show()

        entry.bind('<FocusIn>', hide, add='+')
        entry.bind('<FocusOut>', restore, add='+')
        show()

    def _apply_shell_search_187(self):
        """Hide rows that do not contain the query, restore them when it clears."""
        if getattr(self, '_search_placeholder_active187', False):
            term = ''
        else:
            term = en(str(self.shell_search187.get() or '')).strip().lower()
        if not term:
            # Cleared on whichever tab: every table the query narrowed gets its
            # rows back, not only the one showing, or a tab opened later would
            # still be short under an empty field.
            restore_tree_rows_187()
            return
        try:
            current = self.notebook.nametowidget(self.notebook.select())
        except (tk.TclError, KeyError):
            return
        tree = self._find_tree_187(current)
        if tree is None:
            return
        # No stripe_tree() after this, as there used to be: the rows keep their
        # even/odd tags now, and stripe_tree() would repaint those in the theme
        # engine's palette instead of the one the table itself (Data Entry) uses.
        try:
            filter_tree_rows_187(tree, term, en)
        except tk.TclError:
            return

    def _shell_button_187(self, parent, text, command, fs, side='right'):
        # Icon only, no border, painted the bar's own colour. _bar_icon_187
        # swaps in a tile image whose rounded plate is part of the picture,
        # so the hover keeps its corners. The label survives as the tooltip.
        p = palette_187()
        button = tk.Button(
            parent, text=text, command=command,
            bg=p['surface'], fg=p['text'], activebackground=p['surface'],
            activeforeground=p['accent'], relief='flat', bd=0,
            highlightthickness=0, cursor='hand2', padx=2, pady=0,
        )
        button.pack(side=side, padx=2)
        return button

    def _set_theme_mode_187(self, mode: str):
        ui = load_ui()
        mode = 'light' if str(mode).lower() == 'light' else 'dark'
        if str(ui.get('appearance') or 'dark').lower() == mode:
            return
        ui['appearance'] = mode
        save_ui(ui)
        self._restart_requested = True
        self.after(80, self.destroy)

    def _tick_clock(self):
        try:
            now = datetime.now()
            self.datetime_top.set(
                # Decision 1.6: hours and minutes only - over the date, as
                # before D4 (operator round 2026-09-27).
                f"{fa(now.strftime('%H:%M'))}\n"
                f"{fa(v186.v18.gregorian_to_shamsi(now.date()))}"
            )
        finally:
            self.after(1000, self._tick_clock)

    def _show_footer_mode_menu_187(self, _event=None):
        button = getattr(self, 'footer_mode_button187', None)
        if button is not None:
            PopupMenu(button, self._theme_menu_sections_187()[:1], side='above', min_width=170)
        return 'break'

    def _show_footer_theme_menu_187(self, _event=None):
        button = getattr(self, 'footer_theme_button187', None)
        if button is not None:
            PopupMenu(button, self._theme_menu_sections_187()[1:], side='above', min_width=150)
        return 'break'

    def _set_theme_id_187(self, theme_id: int):
        ui = load_ui()
        try:
            selected = get_theme(theme_id).theme_id
        except (TypeError, ValueError):
            selected = 1
        if int(ui.get('theme_id') or 1) == selected:
            return
        ui['theme_id'] = selected
        save_ui(ui)
        self._restart_requested = True
        self.after(80, self.destroy)

    def _toggle_language_187(self):
        """Toggle the compact footer language control without opening Settings."""
        old = load_ui()
        current = str(old.get('language') or 'fa').lower()
        new = dict(old)
        new['language'] = 'fa' if current == 'en' else 'en'
        save_ui(new)
        self._settings_saved(old, new)

    def _apply_widget_font_187(self, widget, family: str, weight: int = 400, size: int | None = None):
        try:
            current = str(widget.cget('font') or '')
            if 'MDL2' in current or 'Symbol' in current:
                return
            actual = tkfont.Font(root=widget, font=current).actual() if current else {}
            actual_size = int(actual.get('size') or 10)
            target_size = int(size or actual_size)
            if target_size == 0:
                return
            widget.configure(font=(family, target_size, 'bold' if int(weight) >= 700 else 'normal', actual.get('slant', 'roman')))
        except (tk.TclError, ValueError, TypeError):
            return

    def _walk_187(self, root=None):
        """Every widget under root, root included."""
        stack = [root if root is not None else self]
        while stack:
            widget = stack.pop()
            yield widget
            try:
                stack.extend(widget.winfo_children())
            except tk.TclError:
                pass

    BANK_HISTORY_TAB_187 = 'تاریخچه تطبیق بانک'

    def _open_bank_history_187(self):
        for tab_id in self.notebook.tabs():
            if self.notebook.tab(tab_id, 'text') in (self.BANK_HISTORY_TAB_187, 'تطبیق بانکی'):
                self.notebook.select(tab_id)
                return

    def _tidy_manager_page_187(self):
        """حساب مدیر laid out like the other pages.

        Operator round 2026-09-27. Stage 18.2 put a «دسترسی‌های مدیریتی»
        band above the page whose one button, «تطبیق بانک», looked like a
        selected tab and opened a tab title no stage ever used ('تطبیق
        بانکی'), so it did nothing. The shortcut becomes an ordinary button
        on the date row that opens «تاریخچه تطبیق بانک», and the band goes.
        The six figures under the table are allotted before it, so a short
        window squeezes the table rather than dropping them.
        """
        old = getattr(self, 'manager_bank_button', None)
        tab_id = getattr(self, 'manager_tab_id', None)
        if old is None or tab_id is None or getattr(old, '_barkav_tidied187', False):
            return
        try:
            page = self.nametowidget(tab_id)
            controls = next((child for child in page.winfo_children()
                             if isinstance(child, (ttk.Frame, tk.Frame)) and any(
                                 'text' in w.keys() and str(w.cget('text')) == 'محاسبه'
                                 for w in child.winfo_children())), None)
            if controls is None:
                return
            button = ttk.Button(controls, text='تطبیق بانک', style='Toolbar.TButton',
                                command=self._open_bank_history_187)
            button._barkav_tidied187 = True
            self.manager_bank_button = button
            button.pack(side='left', padx=(0, 8))
            legend = next((w for w in controls.pack_slaves()
                           if w is not button and w.pack_info().get('side') == 'left'), None)
            if legend is not None:
                button.pack_configure(before=legend)
            if old.master is not page and old.master.winfo_manager():
                old.master.pack_forget()
            metrics = next(iter(getattr(self, 'manager_metrics', {}).values()), None)
            table = getattr(self, 'manager_withdraw_table', None)
            box = table
            while box is not None and box.master is not page:
                box = box.master
            if metrics is not None and box is not None and metrics.master.master is page:
                metrics.master.pack_configure(side='bottom', before=box)
        except (tk.TclError, AttributeError, KeyError):
            return

    def _tidy_bank_history_187(self):
        """تاریخچه تطبیق بانک: one bar of actions, as every other table.

        A band above the table held «✏️ ویرایش تطبیق» and «🗑 حذف تطبیق»,
        a second row of buttons over the table's own. Editing joins the
        table's bar as «ویرایش», running the same handler; the band's delete
        was the table's «حذف» again - same selection, same question, same
        soft delete - so it goes with the band.
        """
        table = getattr(self, 'rec_table', None)
        if table is None or getattr(table, '_barkav_bank_tidied187', False):
            return
        try:
            slaves = table.master.pack_slaves()
            index = slaves.index(table) if table in slaves else 0
            above = slaves[index - 1] if index else None
            words = {self._without_button_glyph_187(str(w.cget('text')))
                     for w in (above.winfo_children() if above is not None else ())
                     if isinstance(w, (ttk.Button, tk.Button))}
            if words != {'ویرایش تطبیق', 'حذف تطبیق'}:
                return
            bar = table.winfo_children()[0]
            ttk.Button(bar, text='ویرایش', command=self.edit_reconciliation,
                       style='Primary.TButton').pack(side='right', padx=2)
            above.pack_forget()
            table._barkav_bank_tidied187 = True
        except (tk.TclError, IndexError, AttributeError):
            return

    def _theme_manager_metrics_187(self, p):
        """The six figures under حساب مدیر on the page's own surface.

        Stage 10 drew them white with fixed text colours, so on the dark
        theme they were six white boxes. The sign colours come from the
        palette too, and follow each new value.
        """
        for metric in getattr(self, 'manager_metrics', {}).values():
            try:
                metric.configure(bg=p['card'], highlightbackground=p['border'])
                labels = [w for w in metric.winfo_children() if isinstance(w, tk.Label)]
                for label in labels:
                    label.configure(bg=p['card'])
                if labels:
                    labels[0].configure(fg=p['text_secondary'])
            except tk.TclError:
                continue
            if not hasattr(metric, '_barkav_set187'):
                metric._barkav_set187 = metric.set

                def signed(value, formatter=None, metric=metric):
                    metric._barkav_set187(value, formatter)
                    self._sign_colour_187(metric)
                metric.set = signed
            self._sign_colour_187(metric)

    @staticmethod
    def _sign_colour_187(metric):
        try:
            number = float(metric.value)
        except (TypeError, ValueError, AttributeError):
            number = 0
        colours = palette_187()
        try:
            metric.value_label.configure(fg=colours['success'] if number >= 0 else colours['danger'])
        except (tk.TclError, AttributeError):
            pass

    _TAB_BUTTON_ROLES_187 = frozenset((
        'Tab.TButton', 'TabActive.TButton', 'Subtab.TButton', 'SubtabActive.TButton',
        'TabSelected.TButton', 'TabUnselected.TButton',
        'WindowTabSelected.TButton', 'WindowTabUnselected.TButton'))

    def _style_fonts_187(self, family, size):
        """Tab titles at the app's size, every button a point below them.

        Operator round 2026-09-27: the buttons of each tab should read
        smaller than the tab names; both were drawn at one size.
        """
        from barkav_ui.skin import BUTTON_ROLES
        style = ttk.Style(self)
        tab_font = (family, size)
        button_font = (family, max(8, size - 1))
        for name in BUTTON_ROLES:
            try:
                if name in self._TAB_BUTTON_ROLES_187:
                    style.configure(name, font=tab_font)
                else:
                    # An inherited layer gave every button an 11-character
                    # minimum width, so «کپی» was as wide as «بارگذاری بکاپ»;
                    # 6 keeps short words tappable without the padding.
                    style.configure(name, font=button_font, width=-6)
            except tk.TclError:
                continue
        for name in ('Export.TMenubutton', 'TMenubutton'):
            try:
                style.configure(name, font=button_font)
            except tk.TclError:
                pass

    def unify_appearance_187(self, root=None):
        """Force one font, one table look and one strip look across the app.

        The inherited layers set fonts and table colours widget by widget, so
        a screen's appearance depended on which stage built it.  Rather than
        hunt those down one at a time, this sweeps the live widget tree and
        re-applies the theme to everything it finds.  It is idempotent, and
        re-running it is what makes a settings change propagate everywhere
        instead of only to the screens that happen to listen.
        """
        p = palette_187()
        family = resolve_font_family_187(self, load_ui().get('font_family'))
        weight = resolve_font_weight_187(self, family, load_ui().get('font_weight'))
        size = max(9, min(14, int(load_ui().get('font_size') or 10)))
        row_height = max(28, min(46, int(load_ui().get('row_height') or theme_metrics_187()['row_height'])))

        dark = _colour_luma_187(self, p['bg']) < 0.5
        toolbars = set()
        if not getattr(self, '_barkav_messages187', False):
            # Themed message boxes and hand-built dialogs (operator round
            # 2026-09-27: the reprocess windows and the final message looked
            # like bare Windows boxes).
            self._barkav_messages187 = True
            from barkav_ui import messages as kit_messages
            kit_messages.install()
            kit_messages.watch_raw_dialogs(self)
        self._style_fonts_187(family, size)
        self._tidy_manager_page_187()
        self._tidy_bank_history_187()
        self._theme_manager_metrics_187(p)
        import dashboard_stage12 as v12
        widgets = list(self._walk_187(root))
        for widget in widgets:
            if isinstance(widget, v12.SmartTable):
                self._canonical_smart_bar_187(widget)
            self._unify_widget_appearance_187(widget, p, family, weight, row_height, dark)
        toolbars = {
            widget.master for widget in widgets
            if isinstance(widget, (ttk.Button, tk.Button))
        }
        # N4: a row of three or more buttons gets a "بیشتر" menu for the
        # ones the packer drops when the row is too narrow.
        for frame in toolbars:
            try:
                count = sum(1 for w in frame.pack_slaves() if isinstance(w, (ttk.Button, tk.Button)))
            except (tk.TclError, AttributeError):
                continue
            if count >= 3:
                watch_overflow_187(frame)

    def _unify_widget_appearance_187(self, widget, palette, family, weight, row_height, dark=None):
        """Apply the shared appearance contract to one widget."""
        if isinstance(widget, ttk.Treeview):
            stripe_tree(widget, theme_selection_187())
            self._unify_table_187(widget, palette, row_height)
            return
        if isinstance(widget, ttk.Notebook):
            strip = self._normalise_notebook_187(widget)
            if strip is not None and hasattr(strip, 'rebuild'):
                try:
                    strip.rebuild()
                except tk.TclError:
                    pass
            return
        if isinstance(widget, ttk.Combobox):
            self._export_menu_187(widget, palette)
        elif isinstance(widget, ttk.Label):
            self._total_bar_187(widget, palette)
        elif isinstance(widget, ttk.Checkbutton):
            match_checkbutton_background(widget)
        if isinstance(widget, (ttk.Button, tk.Button)):
            self._canonical_action_word_187(widget)
            self._color_action_button_187(widget, palette)
            self._action_icon_187(widget, palette)
            self._icon_only_action_187(widget, palette)
            if isinstance(widget, tk.Button):
                self._normalise_classic_button_187(widget)
        if dark is None:
            dark = _colour_luma_187(self, palette['bg']) < 0.5
        if dark:
            self._theme_highlight_187(widget, palette)
        try:
            if 'font' not in widget.keys():
                return
        except (tk.TclError, AttributeError):
            return
        # Titles keep their relative weight; only family and size are
        # normalised, so the ladder in the contract still reads.
        if getattr(widget, '_barkav_keep_font187', False):
            return
        self._apply_widget_font_187(widget, family, weight)

    # افزودن / ویرایش / کپی / حذف take the same four roles the price-update
    # tab's action row declares through barkav_ui.table.ACTION_STYLES
    # (create / neutral / caution / destructive), wherever an inherited
    # screen or dialog built them - most as plain gray Toolbar pills.
    _ACTION_WORDS_187 = (
        ('حذف', 'Danger'), ('🗑', 'Danger'),
        ('کپی', 'Warning'),
        ('ویرایش', 'Primary'), ('✏', 'Primary'),
        ('افزودن', 'Success'), ('اضافه', 'Success'),
    )
    _NEUTRAL_BUTTON_STYLES_187 = frozenset(
        ('', 'TButton', 'Toolbar.TButton', 'TableToolbar.TButton', 'Ghost.TButton'))
    _ACTION_COLOURS_187 = {
        'Success': ('success', 'on_accent'), 'Primary': ('info', 'on_accent'),
        'Warning': ('warning', 'on_warning'), 'Danger': ('danger', 'on_accent'),
    }

    # ---- one toolbar shape for the stage-12 tables ------------------------
    # Symbols a few older bars put in front of a button's words; the shared
    # toolbar names its actions in words alone.
    _BUTTON_GLYPHS_187 = ('➕', '✏️', '✏', '🗑', '📎', '📅', '🚫', '✅', '❌', '♻', '🔄',
                          '📤', '📥', '💾', '\ufe0f')
    # The stage-12 bar's row-height pair, its select-all and its filter's
    # clear button: the shared toolbar has none of them.
    _LEGACY_BAR_HIDDEN_187 = ('↕−', '↕+', '☑ همه', '✖')
    _ACTION_RANK_187 = {'Success': 0, 'Primary': 1, None: 2, 'Warning': 3, 'Danger': 4}

    @classmethod
    def _without_button_glyph_187(cls, text: str) -> str:
        bare = str(text or '').strip()
        while bare and any(bare.startswith(glyph) for glyph in cls._BUTTON_GLYPHS_187):
            glyph = next(glyph for glyph in cls._BUTTON_GLYPHS_187 if bare.startswith(glyph))
            bare = bare[len(glyph):].strip()
        # A glyph alone stays: it is the whole label.
        return bare if re.search(r'[؀-ۿA-Za-z]', bare) else str(text or '').strip()

    def _canonical_smart_bar_187(self, table):
        """A stage-12 SmartTable's own bar in the shared toolbar's shape.

        Operator round 2026-09-27: حساب مدیر and مدیریت پروژه › فازها still
        showed the older bar, the row-height ↕−/↕+ that earlier versions
        dropped among it. Here the actions stand on the right in the order
        every tab uses - create, edit, the rest, copy, delete - with
        «خروجی ▾» at the left end and the search centred; ↕−/↕+, ☑ همه
        and the filter's ✖ go, and 📋 / 🗑 انتخاب‌ها read «کپی» / «حذف».
        Every handler is the one the button already had. Re-run on every
        appearance pass, so buttons a screen adds later join the order.
        """
        if hasattr(table, '_barkav_transaction_toolbar187'):
            return
        try:
            bar = table.winfo_children()[0]
            if not bar.winfo_manager():
                return
        except (IndexError, tk.TclError, AttributeError):
            return
        # One export path: stage 18.3's dropdown (which also retires the
        # 📊/📄/🖨 icons), shown as the one «خروجی ▾».
        try:
            from ui_stage18_3 import install_smarttable_export_dropdown
            combo = install_smarttable_export_dropdown(table)
        except Exception:
            combo = None
        if combo is not None:
            self._export_menu_187(combo, palette_187())
        export = getattr(combo, '_barkav_export_menu187', None) if combo is not None else None
        table._barkav_canonical187 = True
        # Hidden while the table had no delete handler; a handler set since
        # brings it back.
        bulk = getattr(table, 'b_bulk_delete', None)
        try:
            if bulk is not None and not bulk.winfo_manager() and str(bulk.cget('state')) != 'disabled':
                bulk.pack(side='right', padx=2)
        except tk.TclError:
            pass
        title = search_label = entry = None
        actions = []
        for child in list(bar.pack_slaves()):
            try:
                text = str(child.cget('text') or '').strip() if 'text' in child.keys() else ''
            except tk.TclError:
                continue
            if getattr(child, '_barkav_icon_only187', False):
                # Drawn as an icon; it is still the action it was named.
                text = self._CANONICAL_ACTION_WORDS_187.get(
                    self._action_role_187(child._barkav_original_label187), text)
                if child is not export:
                    actions.append((child, text))
                continue
            if isinstance(child, (ttk.Entry, tk.Entry)) and not isinstance(child, ttk.Combobox):
                entry = child
            elif isinstance(child, (ttk.Label, tk.Label)):
                if text.rstrip(':').strip() in ('فیلتر', 'جستجو'):
                    search_label = child
                elif title is None and text:
                    title = child
            elif isinstance(child, (ttk.Button, tk.Button)):
                try:
                    if child is export:
                        continue
                    if text in self._LEGACY_BAR_HIDDEN_187 or text.startswith('خروجی'):
                        # Another «خروجی» beside the one export is a stray.
                        child.pack_forget()
                        continue
                    if text == '📋':
                        text = 'کپی'
                        child.configure(text=text, width=0)
                        if isinstance(child, ttk.Button):
                            child.configure(style='Warning.TButton')
                    elif text.startswith('🗑') and 'انتخاب' in text:
                        if str(child.cget('state')) == 'disabled':
                            child.pack_forget()
                            continue
                        text = 'حذف'
                        child.configure(text=text, width=0)
                        if isinstance(child, ttk.Button):
                            child.configure(style='Danger.TButton')
                    else:
                        bare = self._without_button_glyph_187(text)
                        if bare != text:
                            text = bare
                            child.configure(text=text)
                except tk.TclError:
                    continue
                actions.append((child, text))
        # The same word twice - a screen's own «کپی» beside the bar's 📋 - is
        # one button; both ran the same handler.
        seen, kept = set(), []
        for child, text in actions:
            if text in seen:
                child.pack_forget()
                continue
            seen.add(text)
            kept.append((child, text))
        ordered = [child for child, _text in sorted(
            kept, key=lambda item: self._ACTION_RANK_187.get(self._action_role_187(item[1]), 2))]
        # As the price tabs' toolbars: «خروجی ▾» at the left end, packed
        # first so a crowded row drops its last buttons into «بیشتر ⋯» and
        # never the export; the search centred in what the edges leave; the
        # title and the actions from the right edge. The box and its caption
        # each take half the spare room and lean towards each other, which
        # centres the pair without re-parenting either.
        wanted = [w for w in (export, entry, search_label, title) if w is not None] + ordered
        try:
            if [w for w in bar.pack_slaves() if w in wanted] == wanted:
                return
            for widget in wanted:
                widget.pack_forget()
            if export is not None:
                export.pack(side='left', padx=2)
            if entry is not None:
                entry.pack(side='left', expand=True, anchor='e', padx=(8, 2))
                if search_label is not None:
                    search_label.configure(text='جستجو:')
                    search_label.pack(side='left', expand=True, anchor='w', padx=(0, 8))
            if title is not None:
                title.pack(side='right', padx=(0, 5))
            for child in ordered:
                child.pack(side='right', padx=2)
        except tk.TclError:
            pass

    # ---- one export control ----------------------------------------------
    EXPORT_PROMPT_187 = 'خروجی'

    _EXPORT_FORMATS_187 = {'Excel': 'sheet', 'PDF': 'page', 'پرینت': 'print', 'چاپ': 'print',
                           'JSON': 'page', 'CSV': 'sheet', 'Word': 'page',
                           'اکسل': 'sheet', 'پی‌دی‌اف': 'page', 'پی دی اف': 'page'}

    def _export_menu_187(self, combo, p):
        """Replace any export-format dropdown (and a redundant «خروجی» title
        or button beside it) with one «خروجی ▾» button whose themed menu
        lists the formats.

        The dropdown stays - hidden - and remains the source of truth: each
        menu entry sets it and fires <<ComboboxSelected>>, so every screen's
        own export handler runs exactly as before and resets it as before.
        """
        if getattr(combo, '_barkav_export_menu187', None) is not None:
            return
        try:
            values = [str(v) for v in combo.cget('values')]
            manager = combo.winfo_manager()
        except tk.TclError:
            return
        if not values or manager not in ('pack', 'grid'):
            return
        try:
            current = str(combo.get() or '').strip()
        except tk.TclError:
            current = ''
        if 'خروجی' in values[0] or 'فرمت' in values[0]:
            # The prompt is the first entry of the list.
            formats = [v for v in values[1:] if v.strip()]
        elif ('خروجی' in current or 'فرمت' in current) and current not in values:
            # The prompt only lives in the variable; the list is all formats.
            formats = [v for v in values if v.strip()]
        else:
            return
        if not any(v.strip() in self._EXPORT_FORMATS_187 for v in formats):
            return
        try:
            info = combo.pack_info() if manager == 'pack' else combo.grid_info()
        except tk.TclError:
            return
        parent = combo.master
        smarttable = self._smarttable_for_export_combo_187(combo)
        # A screen that already has its own «خروجی» button (the financial
        # toolbars) keeps it - in its place and style - as the menu button,
        # rather than hiding it behind a second one.
        button = None
        for sibling in parent.winfo_children():
            try:
                if (isinstance(sibling, ttk.Button) and sibling.winfo_manager()
                        and str(sibling.cget('text') or '').strip() == 'خروجی'):
                    button = sibling
                    break
            except tk.TclError:
                continue
        reused = button is not None
        if reused:
            button.configure(text='خروجی ▾', cursor='hand2')
        else:
            button = ttk.Button(parent, text='خروجی ▾', style='Toolbar.TButton', cursor='hand2')
        image = line_icon_187('export', size=15, colour=p['text_primary'], background=None,
                              weight=1.15, master=self)
        if image is not None:
            button.configure(image=image, compound='right')
            button._barkav_icon_image187 = image

        menu_formats = list(formats)
        if smarttable is not None:
            preferred = ('PDF', 'Excel', 'پرینت')
            menu_formats = [value for value in preferred if value in menu_formats]

        def open_menu(_button=button, _combo=combo, _formats=tuple(menu_formats)):
            items = [{'label': value, 'icon': self._EXPORT_FORMATS_187.get(value.strip(), 'page'),
                      'command': lambda v=value, c=_combo: self._run_export_choice_187(c, v)}
                     for value in _formats]
            PopupMenu(_button, [(None, items)], side='below', min_width=170)

        button.configure(command=open_menu)
        try:
            if manager == 'pack':
                if not reused:
                    button.pack(before=combo, **{k: v for k, v in info.items() if k != 'in'})
                combo.pack_forget()
            else:
                if not reused:
                    button.grid(**{k: v for k, v in info.items() if k != 'in'})
                combo.grid_remove()
        except tk.TclError:
            if not reused:
                button.destroy()
            return
        combo._barkav_export_menu187 = button
        button._barkav_action_icon187 = True
        if manager == 'pack':
            try:
                # Allotted first (operator round 2026-09-27: a crowded row had
                # folded the export into «بیشتر ⋯»); it stays the row's
                # left-most control.
                first = parent.pack_slaves()[0]
                if first is not button:
                    button.pack_configure(before=first)
            except (tk.TclError, IndexError):
                pass
        for sibling in parent.winfo_children():
            if sibling in (button, combo):
                continue
            if not isinstance(sibling, (ttk.Label, tk.Label, ttk.Button, tk.Button)):
                continue
            try:
                if str(sibling.cget('text') or '').strip().rstrip(':').strip() != 'خروجی':
                    continue
                if sibling.winfo_manager() == 'pack':
                    sibling.pack_forget()
                elif sibling.winfo_manager() == 'grid':
                    sibling.grid_remove()
            except tk.TclError:
                continue

    def _install_late_widget_hooks_187(self):
        """Screens build some toolbars and tables only when first shown, after
        the appearance pass ran; the export control and the total bar are
        applied to those too, the first time each widget appears."""
        if getattr(self, '_late_hooks187', False):
            return
        self._late_hooks187 = True
        self.bind_class('TCombobox', '<Map>', self._on_late_combo_187, add='+')
        self.bind_class('TLabel', '<Map>', self._on_late_label_187, add='+')

    def _on_late_combo_187(self, event):
        widget = event.widget
        if isinstance(widget, str):
            return
        try:
            widget.configure(justify='right')
        except tk.TclError:
            pass
        if getattr(widget, '_barkav_export_menu187', None) is not None:
            return
        self.after_idle(lambda w=widget: self._late_apply_187(w, self._export_menu_187))

    def _on_late_label_187(self, event):
        widget = event.widget
        if isinstance(widget, str) or getattr(widget, '_barkav_total_bar187', False):
            return
        if not isinstance(getattr(widget.master, 'total', None), tk.StringVar):
            return
        self.after_idle(lambda w=widget: self._late_apply_187(w, self._total_bar_187))

    def _late_apply_187(self, widget, apply):
        try:
            if widget.winfo_exists():
                apply(widget, palette_187())
        except tk.TclError:
            pass

    @staticmethod
    def _smarttable_for_export_combo_187(combo):
        parent = getattr(combo, 'master', None)
        for _ in range(4):
            if parent is None:
                return None
            if callable(getattr(parent, 'current_report_rows', None)):
                return parent
            parent = getattr(parent, 'master', None)
        return None

    def _run_export_choice_187(self, combo, value):
        table = self._smarttable_for_export_combo_187(combo)
        if table is not None:
            from reports_stage18_7 import _export_through_preview_187, _smarttable_export_rows_187
            headers, rows = _smarttable_export_rows_187(table)
            title = str(getattr(table, 'title', '') or '').strip() or 'گزارش'
            return _export_through_preview_187(table, value, headers, rows, title)
        try:
            combo.set(value)
            combo.event_generate('<<ComboboxSelected>>')
        except tk.TclError:
            pass

    # ---- the table total, readable right to left --------------------------
    # "۱۸ مورد | جمع مبلغ فیلترشده (تومان): ۱٬۱۳۰٬۳۶۴٬۰۰۰" opens with a number;
    # Tk on Windows lays a line out left-to-right, so that leading count ends
    # up beside the amount. The bar shows the same figures as separate
    # label/number chips instead, each one direction only. The StringVar
    # itself is untouched - screens and tests read it.
    _TOTAL_PATTERN_187 = re.compile(
        r'^\s*(?P<count>[0-9۰-۹٬,]+)\s*مورد\s*\|\s*(?P<label>[^:|]+?)\s*:\s*(?P<amount>[^|]+?)\s*'
        r'(?:\|\s*انتخاب\s*:\s*(?P<scount>[0-9۰-۹٬,]+)\s*مورد\s*/\s*(?P<samount>.+?))?\s*$'
    )

    def _total_bar_187(self, label, p):
        if getattr(label, '_barkav_total_bar187', False):
            return
        table = label.master
        var = getattr(table, 'total', None)
        if not isinstance(var, tk.StringVar):
            return
        try:
            if str(label.cget('textvariable')) != str(var) or label.winfo_manager() != 'pack':
                return
            info = label.pack_info()
        except tk.TclError:
            return
        label._barkav_total_bar187 = True
        bar = tk.Frame(table, bg=p['panel'], bd=0, highlightthickness=0)
        chips = {}
        for key in ('count', 'sum', 'selected'):
            chip = tk.Frame(bar, bg=p['surface_alt'], highlightthickness=1,
                            highlightbackground=p['border_subtle'])
            name = tk.Label(chip, bg=p['surface_alt'], fg=p['text_secondary'],
                            font=kit_font('small', widget=self))
            value = tk.Label(chip, bg=p['surface_alt'], fg=p['text_primary'],
                             font=kit_font('body', widget=self, bold=True))
            name.pack(side='right', padx=(10, 4), pady=4)
            value.pack(side='right', padx=(0, 10), pady=4)
            chips[key] = (chip, name, value)
        try:
            bar.pack(after=label, **{k: v for k, v in info.items() if k not in ('in', 'after', 'before')})
            label.pack_forget()
        except tk.TclError:
            bar.destroy()
            return

        def refresh(*_args):
            try:
                text = str(var.get() or '')
            except tk.TclError:
                return
            match = self._TOTAL_PATTERN_187.match(text)
            if match:
                parts = [('count', 'تعداد', match['count']),
                         ('sum', match['label'].strip(), match['amount'].strip())]
                if match['scount']:
                    # The label carries the count, so the value is a bare
                    # number and never opens a mixed-direction run.
                    parts.append(('selected', f"انتخاب‌شده ({match['scount']} ردیف)",
                                  match['samount'].strip()))
            else:
                parts = [('sum', '', text.strip())]
            shown = set()
            try:
                for key, name_text, value_text in parts:
                    chip, name, value = chips[key]
                    name.configure(text=name_text)
                    value.configure(text=value_text)
                    shown.add(key)
                for key in ('count', 'sum', 'selected'):
                    chip = chips[key][0]
                    chip.pack_forget()
                for key in ('count', 'sum', 'selected'):
                    if key in shown:
                        chips[key][0].pack(side='right', padx=(0, 6), pady=4)
            except tk.TclError:
                return

        var.trace_add('write', refresh)
        refresh()

    # N4: the four core actions carry the same line icon wherever they are.
    _ACTION_ICONS_187 = (('حذف', 'trash'), ('کپی', 'copy'), ('ویرایش', 'edit'), ('افزودن', 'plus'))

    _CANONICAL_ACTION_WORDS_187 = {'Success': 'افزودن', 'Primary': 'ویرایش',
                                   'Warning': 'کپی', 'Danger': 'حذف'}
    _ROLE_ICONS_187 = {'Success': 'plus', 'Primary': 'edit', 'Warning': 'copy', 'Danger': 'trash'}

    def _in_action_row_187(self, button) -> bool:
        """A table's row of actions in the main window - not a dialog's
        footer, not a lone button."""
        try:
            if button.winfo_toplevel() is not self:
                return False
            siblings = [w for w in button.master.winfo_children()
                        if isinstance(w, (ttk.Button, tk.Button))]
        except (tk.TclError, AttributeError):
            return False
        roles = 0
        for sibling in siblings:
            try:
                text = getattr(sibling, '_barkav_original_label187', None) or sibling.cget('text')
            except tk.TclError:
                continue
            if self._action_role_187(text):
                roles += 1
        return roles >= 2

    def _canonical_action_word_187(self, button):
        """One name per action in every table: افزودن, ویرایش, کپی, حذف.

        Operator round 2026-09-27: «قرارداد جدید +», «ویرایش قرارداد»,
        «کپی قرارداد», «حذف ردیف», «+ پیمانکار», «افزودن ریز», «اضافه» ...
        each read differently. The button keeps its handler; its old
        wording becomes the hover hint.
        """
        if getattr(button, '_barkav_original_label187', None) is not None:
            return
        try:
            text = str(button.cget('text') or '').strip()
        except tk.TclError:
            return
        if not text or len(text) > 24:
            return
        role = self._action_role_187(text)
        word = self._CANONICAL_ACTION_WORDS_187.get(role)
        if word is None or text == word or not self._in_action_row_187(button):
            return
        try:
            button.configure(text=word)
        except tk.TclError:
            return
        button._barkav_original_label187 = text
        attach_tooltip(button, text, delay_ms=300, side='below')

    def _icon_only_action_187(self, button, p):
        """Settings › نمایش دکمه‌ها › فقط آیکون: a table action is its
        glossy role-coloured tile alone, the word shown on hover."""
        if str(load_ui().get('button_display') or 'text') != 'icon':
            return
        if getattr(button, '_barkav_icon_only187', False) or not isinstance(button, ttk.Button):
            return
        try:
            text = str(button.cget('text') or '').strip()
        except tk.TclError:
            return
        role = self._action_role_187(text)
        if text not in self._CANONICAL_ACTION_WORDS_187.values() or not self._in_action_row_187(button):
            return
        try:
            parent_bg = str(button.master.cget('bg'))
        except (tk.TclError, AttributeError):
            parent_bg = p['panel']
        fill_key, text_key = self._ACTION_COLOURS_187[role]
        image = glass_tile_187(self._ROLE_ICONS_187[role], size=20, colour=p[fill_key],
                               ink=p[text_key], background=parent_bg, shadow=p['shadow'], master=self)
        if image is None:
            return
        style = ttk.Style(self)
        name = 'IconAction.TButton'
        try:
            style.layout(name, [('Button.padding', {'sticky': 'nsew', 'children': [
                ('Button.label', {'sticky': 'nsew'})]})])
            style.configure(name, background=parent_bg, padding=1, borderwidth=0, relief='flat')
            style.map(name, background=[('active', parent_bg), ('pressed', parent_bg)])
            button.configure(text='', image=image, compound='image', style=name, cursor='hand2')
        except tk.TclError:
            return
        button._barkav_icon_only187 = True
        button._barkav_icon_image187 = image
        if getattr(button, '_barkav_original_label187', None) is None:
            button._barkav_original_label187 = text
            attach_tooltip(button, text, delay_ms=300, side='below')

    def _action_icon_187(self, button, p):
        if getattr(button, '_barkav_action_icon187', False):
            return
        try:
            if str(button.cget('image') or ''):
                return
            text = str(button.cget('text') or '').strip()
            if isinstance(button, tk.Button) and (
                    int(button.cget('width') or 0) or int(button.cget('height') or 0)):
                # A classic button with an image measures width/height in
                # pixels, not characters; leave sized ones alone.
                return
        except (tk.TclError, ValueError):
            return
        if not text or text.startswith('+') or len(text) > 24:
            return
        name = next((icon for word, icon in self._ACTION_ICONS_187 if word in text), None)
        role = self._action_role_187(text)
        if name is None or role is None:
            return
        colour = p[self._ACTION_COLOURS_187[role][1]]
        image = line_icon_187(name, size=15, colour=colour, background=None, weight=1.15, master=self)
        if image is None:
            return
        try:
            button.configure(image=image, compound='right')
        except tk.TclError:
            return
        button._barkav_action_icon187 = True
        button._barkav_icon_image187 = image

    def _normalise_classic_button_187(self, button):
        """N7: a classic text button gets the same height as the ttk pills."""
        try:
            text = str(button.cget('text') or '').strip()
            if len(text) < 3 or text.replace(' ', '').isdigit():
                return
            if int(button.cget('height') or 0):
                return
            if str(button.cget('image') or '') and not getattr(button, '_barkav_action_icon187', False):
                return
            spec = button.cget('font')
            if 'MDL2' in str(spec) or 'Symbol' in str(spec):
                return
            cache = self.__dict__.setdefault('_linespace187', {})
            linespace = cache.get(str(spec))
            if linespace is None:
                linespace = tkfont.Font(root=self, font=spec).metrics('linespace')
                cache[str(spec)] = linespace
            edge = int(float(button.cget('bd') or 0)) + int(float(button.cget('highlightthickness') or 0))
            button.configure(pady=max(1, (BUTTON_HEIGHT_187 - linespace - 2 * edge) // 2))
        except (tk.TclError, ValueError):
            return

    # N6: one footer order in every window - the contract's own rule
    # (docs/theme_18_7/BARKAV_UI_CONTRACT.md: actions left-aligned, the
    # primary leftmost, cancel beside it) plus a destructive action kept
    # apart on the far right whenever the footer also has a primary one.
    _FOOTER_PRIMARY_187 = ('ذخیره', 'اعمال', 'ثبت', 'تایید', 'تأیید', 'اجرا', 'بعدی', 'ادامه', 'ایجاد')
    _FOOTER_CANCEL_187 = ('انصراف', 'بستن', 'لغو', 'قبلی', 'بازگشت', 'خیر')

    @classmethod
    def _footer_role_187(cls, text) -> str | None:
        text = str(text or '')
        if any(word in text for word in cls._FOOTER_PRIMARY_187):
            return 'primary'
        if 'حذف' in text:
            return 'danger'
        if any(word in text for word in cls._FOOTER_CANCEL_187):
            return 'cancel'
        return None

    def _order_dialog_footer_187(self, window):
        if window is self:
            return
        try:
            window.update_idletasks()
            window_height = window.winfo_height()
            window_top = window.winfo_rooty()
        except tk.TclError:
            return
        if window_height < 120:
            return
        for frame in self._walk_187(window):
            if not isinstance(frame, (tk.Frame, ttk.Frame)):
                continue
            if getattr(frame, '_barkav_footer_ordered187', False):
                continue
            try:
                slaves = frame.pack_slaves()
                if len(slaves) < 2 or len(frame.winfo_children()) != len(slaves):
                    continue
                if not all(isinstance(w, (tk.Button, ttk.Button)) for w in slaves):
                    continue
                if getattr(frame.winfo_toplevel(), '_footer_actions', None) is not None \
                        and frame is getattr(frame.winfo_toplevel(), 'footer', None):
                    continue   # a kit window lays out its own footer
                infos = [w.pack_info() for w in slaves]
                if len({str(info.get('side')) for info in infos}) != 1:
                    continue
                bottom = frame.winfo_rooty() + frame.winfo_height() - window_top
                roles = [self._footer_role_187(w.cget('text')) for w in slaves]
            except tk.TclError:
                continue
            if bottom < window_height * 0.6 or None in roles:
                continue
            frame._barkav_footer_ordered187 = True
            visual = list(zip(slaves, roles, infos))
            if str(infos[0].get('side')) == 'right':
                visual.reverse()   # packing order -> left-to-right order
            has_primary = 'primary' in roles
            lead = [v for v in visual if v[1] == 'primary' or (v[1] == 'danger' and not has_primary)]
            cancels = [v for v in visual if v[1] == 'cancel']
            apart = [v for v in visual if v[1] == 'danger' and has_primary]
            if [v[0] for v in visual] == [v[0] for v in lead + cancels] \
                    and str(infos[0].get('side')) == 'left':
                continue
            for widget in slaves:
                widget.pack_forget()
            for widget, _role, info in lead + cancels:
                widget.pack(side='left', **{k: v for k, v in info.items() if k not in ('in', 'side')})
            for widget, _role, info in reversed(apart):
                widget.pack(side='right', **{k: v for k, v in info.items() if k not in ('in', 'side')})

    # ---- N5: readable forms --------------------------------------------
    def _install_inline_errors_187(self):
        """A dialog's own error or warning shows inside that dialog.

        ``messagebox.showerror``/``showwarning`` called with a dialog as
        parent become a strip at the bottom of that dialog instead of a
        second, modal window. Calls with no dialog parent, very long texts,
        and anything already replaced by someone else (a test stub) keep
        the native box.
        """
        if getattr(messagebox, '_barkav_inline187', False):
            return
        originals = {}
        for name in ('showerror', 'showwarning'):
            function = getattr(messagebox, name)
            if getattr(function, '__module__', '') != 'tkinter.messagebox':
                return
            originals[name] = function
        app = self

        def make(name):
            original = originals[name]

            def inline(title=None, message=None, **options):
                window = app._inline_error_target_187(options.get('parent'))
                text = str(message or title or '').strip()
                if window is None or not text or len(text) > 420:
                    return original(title, message, **options)
                try:
                    show_inline_error(
                        window, text, kind='error' if name == 'showerror' else 'warning',
                        on_lost=lambda: show_toast(app, text, kind='error', duration_ms=6000),
                    )
                    window.bell()
                except tk.TclError:
                    return original(title, message, **options)
                return 'ok'

            inline._barkav_inline187 = True
            return inline

        for name in originals:
            setattr(messagebox, name, make(name))
        messagebox._barkav_inline187 = True

    def _inline_error_target_187(self, parent):
        if parent is None:
            return None
        try:
            window = parent.winfo_toplevel()
            if window is self or not window.winfo_ismapped():
                return None
        except (tk.TclError, AttributeError):
            return None
        if isinstance(window, BarkavWindow) or getattr(window, '_barkav_normalised187', False):
            return window
        return None

    @staticmethod
    def _form_kind_187(widget) -> str | None:
        if isinstance(widget, (tk.Label, ttk.Label)):
            try:
                if str(widget.cget('image') or ''):
                    return None
                return 'label' if str(widget.cget('text') or '').strip() else None
            except tk.TclError:
                return None
        inputs = (tk.Entry, ttk.Entry, ttk.Combobox, tk.Spinbox, ttk.Spinbox)
        if isinstance(widget, inputs):
            return 'input'
        if isinstance(widget, (tk.Frame, ttk.Frame)):
            try:
                if any(isinstance(child, inputs) for child in widget.winfo_children()):
                    return 'input'
            except tk.TclError:
                return None
        return None

    def _stack_form_labels_187(self, window):
        """Put each label above its field in simple one-column forms.

        Only a grid made purely of (label, field) pairs, one pair per row,
        at least three rows, qualifies. If the taller form no longer fits
        the window (or the screen), the original grid is put back.
        """
        if window is self:
            return
        for frame in list(self._walk_187(window)):
            if not isinstance(frame, (tk.Frame, ttk.Frame)) or getattr(frame, '_barkav_stacked187', False):
                continue
            try:
                slaves = frame.grid_slaves()
                if len(slaves) < 6 or len(slaves) != len(frame.winfo_children()):
                    continue
                rows = {}
                for widget in slaves:
                    info = widget.grid_info()
                    if int(info.get('rowspan', 1)) != 1:
                        rows = None
                        break
                    rows.setdefault(int(info['row']), []).append((int(info['column']), widget, info))
            except (tk.TclError, ValueError, KeyError):
                continue
            if not rows or len(rows) < 3:
                continue
            layout, pairs, tail = None, [], []
            for row in sorted(rows):
                cells = sorted(rows[row], key=lambda cell: cell[0])
                if len(cells) == 1 and pairs and isinstance(
                        cells[0][1], (tk.Button, ttk.Button, tk.Checkbutton, ttk.Checkbutton)):
                    tail.append(cells[0])   # e.g. the form's own Save button
                    continue
                if len(cells) != 2 or tail or any(int(cell[2].get('columnspan', 1)) != 1 for cell in cells):
                    layout = None
                    break
                kinds = [self._form_kind_187(cell[1]) for cell in cells]
                if sorted(kinds, key=str) != ['input', 'label']:
                    layout = None
                    break
                label = cells[kinds.index('label')]
                field = cells[kinds.index('input')]
                shape = (label[0], field[0])
                if layout is None:
                    layout = shape
                elif layout != shape:
                    layout = None
                    break
                pairs.append((label, field))
            if layout is None:
                continue
            frame._barkav_stacked187 = True
            columns = {}
            for column in {0, *layout}:
                try:
                    config = frame.grid_columnconfigure(column)
                    columns[column] = {'weight': config.get('weight', 0), 'minsize': config.get('minsize', 0)}
                except tk.TclError:
                    pass
            labels_before = {}
            for (_lc, label, _li), _field in pairs:
                try:
                    labels_before[str(label)] = str(label.cget('text') or '')
                except tk.TclError:
                    pass
            try:
                before_height = window.winfo_height()
                for index, ((_lc, label, _li), (_fc, field, _fi)) in enumerate(pairs):
                    text = str(label.cget('text') or '')
                    if text.rstrip().endswith(':'):
                        # "نام:" beside a field reads as "name: [ ]"; above it
                        # the colon only adds noise.
                        label.configure(text=text.rstrip()[:-1].rstrip())
                    label.grid_configure(row=2 * index, column=0, sticky='e',
                                         pady=(10 if index else 2, 2))
                    field.grid_configure(row=2 * index + 1, column=0, sticky='ew', pady=(0, 0))
                for offset, (_tc, widget, _ti) in enumerate(tail):
                    widget.grid_configure(row=2 * len(pairs) + offset, column=0, columnspan=1)
                frame.grid_columnconfigure(0, weight=1)
                for column in set(layout) - {0}:
                    frame.grid_columnconfigure(column, weight=0, minsize=0)
                window.update_idletasks()
                needed = window.winfo_reqheight()
                limit = window.winfo_screenheight() - 80
                if needed > limit:
                    raise ValueError('taller than the screen')
                if needed > before_height > 1:
                    window.geometry(f'{window.winfo_width()}x{needed}')
            except (tk.TclError, ValueError):
                for (_lc, label, label_info), (_fc, field, field_info) in pairs:
                    label_text = labels_before.get(str(label))
                    if label_text is not None:
                        try:
                            label.configure(text=label_text)
                        except tk.TclError:
                            pass
                    for widget, info in ((label, label_info), (field, field_info)):
                        try:
                            widget.grid_configure(**{k: v for k, v in info.items() if k != 'in'})
                        except tk.TclError:
                            pass
                for column, config in columns.items():
                    try:
                        frame.grid_columnconfigure(column, **config)
                    except tk.TclError:
                        pass
                for _tc, widget, info in tail:
                    try:
                        widget.grid_configure(**{k: v for k, v in info.items() if k != 'in'})
                    except tk.TclError:
                        pass

    def _focus_ring_fields_187(self, window):
        """Classic text fields in a dialog get the theme's focus ring."""
        p = palette_187()
        for widget in self._walk_187(window):
            if not isinstance(widget, (tk.Entry, tk.Spinbox, tk.Text)):
                continue
            try:
                if int(widget.cget('highlightthickness') or 0) <= 0:
                    widget.configure(highlightthickness=1, highlightbackground=p['border_subtle'])
                widget.configure(highlightcolor=p['focus_ring'])
            except (tk.TclError, ValueError, KeyError):
                continue

    @classmethod
    def _action_role_187(cls, text) -> str | None:
        text = str(text or '')
        for word, role in cls._ACTION_WORDS_187:
            if word in text:
                return role
        # "+ پیمانکار", "ثبت قرارداد +": an add action spelled with a plus
        # sign rather than the word - but never a bare symbol button such as
        # the "↕+" row-height control, which has no letters at all.
        if '+' in text and re.search(r'[؀-ۿA-Za-z]', text):
            return 'Success'
        return None

    def _color_action_button_187(self, button, p):
        try:
            text = button.cget('text')
            if not text and 'textvariable' in button.keys() and button.cget('textvariable'):
                text = button.getvar(str(button.cget('textvariable')))
        except tk.TclError:
            return
        role = self._action_role_187(text)
        if role is None:
            return
        try:
            if isinstance(button, ttk.Button):
                if str(button.cget('style') or '') in self._NEUTRAL_BUTTON_STYLES_187:
                    button.configure(style=f'{role}.TButton')
                return
            fill_key, text_key = self._ACTION_COLOURS_187[role]
            fill = p[fill_key]
            button.configure(bg=fill, fg=p[text_key], activebackground=mix(fill, p['text_primary'], 0.12),
                             activeforeground=p[text_key], relief='flat', bd=0)
        except (tk.TclError, KeyError):
            return

    @staticmethod
    def _theme_highlight_187(widget, p):
        """Retheme Tk's own light-grey default focus border (the X11 default,
        SystemButtonFace on Windows) that classic widgets draw whenever a
        stage left highlightthickness at its default - the pale square
        outline round inherited buttons and text boxes on a dark screen."""
        try:
            if int(widget.cget('highlightthickness') or 0) <= 0:
                return
            current = str(widget.cget('highlightbackground'))
        except (tk.TclError, ValueError):
            return
        if _colour_luma_187(widget, current) < 0.55:
            return
        try:
            if widget.winfo_class() == 'Button':
                # Invisible at rest, the theme's focus ring under the keyboard.
                try:
                    rest = str(widget.master.cget('bg'))
                except (tk.TclError, AttributeError):
                    rest = p['bg']
            else:
                rest = p['border_subtle']
            widget.configure(highlightbackground=rest, highlightcolor=p['focus_ring'])
        except tk.TclError:
            return

    @staticmethod
    def _strip_candidates_187(owner):
        """Yield tab-strip-like objects stored on a live screen or dialog."""
        try:
            values = tuple(vars(owner).values())
        except (TypeError, AttributeError):
            return
        for value in values:
            candidates = value if isinstance(value, (list, tuple, set)) else (value,)
            for candidate in candidates:
                if hasattr(candidate, 'notebook') and hasattr(candidate, 'rebuild'):
                    yield candidate

    def _existing_notebook_strip_187(self, notebook):
        """Find both current kit strips and inherited strips not tagged on the notebook."""
        direct = getattr(notebook, '_barkav_rtl_strip', None)
        if direct is not None:
            return direct
        owners = [self]
        current = getattr(notebook, 'master', None)
        while current is not None:
            owners.append(current)
            if isinstance(current, (tk.Tk, Toplevel)):
                break
            current = getattr(current, 'master', None)
        seen = set()
        for owner in owners:
            for candidate in self._strip_candidates_187(owner):
                marker = id(candidate)
                if marker in seen:
                    continue
                seen.add(marker)
                if getattr(candidate, 'notebook', None) is notebook:
                    return candidate
        return None

    def _normalise_notebook_187(self, notebook):
        """Give every secondary notebook the same strip used by Income.

        A few inherited screens kept their old rectangular ``RtlNotebookStrip``
        in an owner attribute such as ``_rtl`` instead of tagging the notebook.
        Those bars escaped the earlier appearance sweep.  Hide that legacy bar
        and attach the shared kit strip once; current kit strips are simply
        adopted and rebuilt.
        """
        if notebook is getattr(self, 'notebook', None) or len(notebook.tabs()) < 2:
            return None
        strip = self._existing_notebook_strip_187(notebook)
        if isinstance(strip, TabStrip):
            notebook._barkav_rtl_strip = strip
            return strip
        if strip is not None:
            bar = getattr(strip, 'bar', None)
            if isinstance(bar, tk.Misc):
                try:
                    bar.pack_forget()
                except tk.TclError:
                    try:
                        bar.grid_remove()
                    except tk.TclError:
                        pass
        try:
            replacement = LegacyTabStrip(notebook, level=notebook_depth(notebook))
        except tk.TclError:
            return strip
        notebook._barkav_rtl_strip = replacement
        return replacement

    def _normalise_window_187(self, window):
        """Apply the shared visual contract after a dialog has built its body."""
        try:
            if not window.winfo_exists():
                return
        except tk.TclError:
            return
        p = palette_187()
        try:
            window.configure(bg=p['bg'])
            title = str(window.title() or '')
            title = re.sub(r'BARKAV\s+18\.(?:6|7)(?!\.)',
                           f'BARKAV {DISPLAY_VERSION_187}', title)
            if title:
                window.title(title)
        except (tk.TclError, KeyError):
            pass
        apply_dark_caption(window)
        self.unify_appearance_187(window)
        self._upgrade_tables_184(window)
        self._normalise_dialog_rtl_187(window)
        self._order_dialog_footer_187(window)
        self._stack_form_labels_187(window)
        self._focus_ring_fields_187(window)
        window._barkav_normalised187 = True

    def _normalise_dialog_rtl_187(self, window):
        """Keep double-click dialogs on the same font and RTL text rhythm."""
        family = resolve_font_family_187(self, load_ui().get('font_family'))
        weight = resolve_font_weight_187(self, family, load_ui().get('font_weight'))
        size = max(9, min(14, int(load_ui().get('font_size') or 10)))
        normalize_window_rtl(window)
        for widget in self._walk_187(window):
            try:
                if 'font' in widget.keys():
                    self._apply_widget_font_187(widget, family, weight, size)
            except (tk.TclError, AttributeError):
                continue

    def _on_toplevel_map_187(self, event):
        window = getattr(event, 'widget', None)
        if not isinstance(window, Toplevel):
            return
        if getattr(window, '_barkav_normalise_job187', None):
            return
        try:
            bind_main_window_focus_on_destroy(window, getattr(self, '_main_window', self))
            center_toplevel_on_screen(window)
            window._barkav_normalise_job187 = window.after_idle(
                lambda target=window: self._normalise_toplevel_once_187(target)
            )
        except tk.TclError:
            return

    def _normalise_toplevel_once_187(self, window):
        try:
            self._normalise_window_187(window)
        finally:
            try:
                window._barkav_normalise_job187 = None
            except tk.TclError:
                pass

    @staticmethod
    def _fade_in_window_187(window):
        """Compatibility shim: reveal immediately, without alpha animation."""
        try:
            if window.state() == 'withdrawn':
                window.deiconify()
        except (AttributeError, tk.TclError):
            pass

    def _on_notebook_tab_changed_187(self, event):
        """Style a newly opened screen in short idle slices after it paints."""
        notebook = getattr(event, 'widget', None)
        if not isinstance(notebook, ttk.Notebook):
            return
        try:
            page = notebook.nametowidget(notebook.select())
        except (tk.TclError, KeyError):
            return
        try:
            if (notebook.winfo_toplevel() is self
                    and getattr(self, '_barkav_main_appearance_ready187', False)):
                page._barkav_appearance_ready187 = True
                return
        except tk.TclError:
            return
        if (getattr(page, '_barkav_appearance_ready187', False)
                or getattr(page, '_barkav_appearance_job187', None)):
            return

        widgets = iter(self._walk_187(page))
        style_params = None

        def apply_once(target=page, owner=notebook):
            nonlocal style_params
            try:
                if (owner.winfo_toplevel() is self
                        and getattr(self, '_barkav_main_appearance_ready187', False)):
                    target._barkav_appearance_job187 = None
                    target._barkav_appearance_ready187 = True
                    return
                if style_params is None:
                    p = palette_187()
                    ui = load_ui()
                    family = resolve_font_family_187(self, ui.get('font_family'))
                    weight = resolve_font_weight_187(self, family, ui.get('font_weight'))
                    row_height = max(28, min(46, int(ui.get('row_height') or theme_metrics_187()['row_height'])))
                    dark = _colour_luma_187(self, p['bg']) < 0.5
                    style_params = (p, family, weight, row_height, dark)
                p, family, weight, row_height, dark = style_params
                for _ in range(24):
                    try:
                        widget = next(widgets)
                    except StopIteration:
                        target._barkav_appearance_job187 = None
                        target._barkav_appearance_ready187 = True
                        return
                    self._unify_widget_appearance_187(
                        widget, p, family, weight, row_height, dark,
                    )
                target._barkav_appearance_job187 = self.after_idle(apply_once)
            except (tk.TclError, KeyError):
                try:
                    target._barkav_appearance_job187 = None
                except tk.TclError:
                    pass
                return

        # Large screens can contain hundreds of widgets. Work in small idle
        # batches so an initial styling pass does not monopolize tab changes.
        page._barkav_appearance_job187 = self.after(140, apply_once)

    def _install_window_normaliser_187(self):
        """Make dialogs opened after startup inherit the same live contract."""
        if getattr(self, '_barkav_window_normaliser187', False):
            return
        self._barkav_window_normaliser187 = True
        self.bind_all('<Map>', self._on_toplevel_map_187, add='+')
        self.bind_all('<<NotebookTabChanged>>', self._on_notebook_tab_changed_187, add='+')

    def _table_refresh_187(self):
        """Refresh through the established dashboard pipeline, never raw SQL."""
        self.refresh_all()

    def _tree_refresh_context_187(self, tree, event):
        """Refresh-only context menu for legacy trees that had none."""
        iid = tree.identify_row(event.y)
        if iid:
            if iid not in tree.selection(): tree.selection_set(iid)
            tree.focus(iid)
        menu = tk.Menu(tree, tearoff=0)
        menu.add_command(label='🔄 بروزرسانی', command=self._table_refresh_187)
        self._right_align_financial_menu_187(menu)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return 'break'

    def _install_table_refresh_187(self, tree):
        """Give every shared table one safe refresh route."""
        self._install_menu_refresh_bridge_187()
        try:
            tree._barkav_refresh_187 = self._table_refresh_187
        except (AttributeError, tk.TclError):
            pass
        current = tree
        while current is not None:
            if getattr(current, 'tree', None) is tree:
                current._barkav_refresh_187 = self._table_refresh_187
                break
            current = getattr(current, 'master', None)
        try:
            if not str(tree.bind('<Button-3>') or '').strip():
                tree.bind('<Button-3>', lambda event, target=tree:
                          self._tree_refresh_context_187(target, event))
        except tk.TclError:
            return

    def _install_menu_refresh_bridge_187(self):
        """Add the shared refresh command to context menus opened over tables."""
        menu_class = tk.Menu
        if getattr(menu_class, '_barkav_refresh_bridge_187', False):
            return
        original_popup = menu_class.tk_popup

        def popup_with_table_refresh(menu, x, y, *args, **kwargs):
            try:
                target = menu.winfo_toplevel().winfo_containing(int(x), int(y))
                while target is not None:
                    refresh = getattr(target, '_barkav_refresh_187', None)
                    if callable(refresh):
                        labels = []
                        last_kind = None
                        end = menu.index('end')
                        if end is not None:
                            for index in range(int(end) + 1):
                                try:
                                    labels.append(str(menu.entrycget(index, 'label') or ''))
                                    last_kind = menu.type(index)
                                except tk.TclError:
                                    continue
                        if not any('بروزرسانی' in label for label in labels):
                            if last_kind not in (None, 'separator'):
                                menu.add_separator()
                            menu.add_command(label='🔄 بروزرسانی', command=refresh)
                        break
                    target = getattr(target, 'master', None)
            except (tk.TclError, TypeError, ValueError):
                pass
            return original_popup(menu, x, y, *args, **kwargs)

        menu_class.tk_popup = popup_with_table_refresh
        menu_class._barkav_refresh_bridge_187 = True

    def _unify_table_187(self, tree, palette, row_height):
        """One style, one stripe pair and one grid for every table."""
        try:
            tree._barkav_line_free_187 = True
            if getattr(tree, '_barkav_data_entry_tree187', False):
                tree.configure(style='DataEntry187.Treeview')
                style = ttk.Style(tree)
                style.configure(
                    'DataEntry187.Treeview.Heading',
                    font=style.lookup('Barkav.Data.Treeview.Heading', 'font') or dashboard_font_187(self, 10, 'control'),
                    padding=style.lookup('Barkav.Data.Treeview.Heading', 'padding') or (4, 8), anchor='e')
            else:
                tree.configure(style='Barkav.Data.Treeview')
            stripe_tree(tree, theme_selection_187())
            is_data_entry = getattr(tree, '_barkav_data_entry_tree187', False)
            # همه جدول‌ها دو سطح تم‌محور دارند تا ردیف‌های عادی یک‌درمیان
            # از هم تفکیک شوند؛ tagهای وضعیت فقط روی ردیف مربوط اعمال می‌شوند.
            stripe_even = palette['row_even'] if is_data_entry else palette['row_card_even']
            stripe_odd = palette['row_odd'] if is_data_entry else palette['row_card_odd']
            tree.tag_configure('even', background=stripe_even, foreground=palette['text_primary'])
            tree.tag_configure('odd', background=stripe_odd, foreground=palette['text_primary'])
            status_palette = (
                {
                    state: (palette[f'data_entry_{state}'], palette[f'data_entry_{state}_text'])
                    for state in ('pending', 'approved', 'rejected')
                }
                if is_data_entry
                else {
                    state: (palette[f'row_{state}'], palette['text_primary'])
                    for state in ('pending', 'approved', 'rejected')
                }
            )
            for state in ('pending', 'approved', 'rejected'):
                background, foreground = status_palette[state]
                tree.tag_configure(state, background=background, foreground=foreground)
            # Raw inherited Treeviews often inserted rows without stripe tags.
            # Styling the tags alone therefore left those tables visually flat.
            # Preserve semantic/custom tags and add exactly one alternating tag
            # unless a status tint already owns the row background.
            status_tags = {'pending', 'approved', 'rejected'}
            for index, item in enumerate(tree.get_children('')):
                tags = list(tree.item(item, 'tags') or ())
                tags = [tag for tag in tags if tag not in {'even', 'odd'}]
                if not status_tags.intersection(tags):
                    tags.append('even' if index % 2 == 0 else 'odd')
                tree.item(item, tags=tuple(tags))
            overlay = getattr(tree, '_barkav_grid_overlay', None)
            if overlay is not None:
                # The card-row contract has no horizontal or vertical rules.
                overlay._dead = True
                for line in (*getattr(overlay, 'vlines', ()), *getattr(overlay, 'hlines', ())):
                    line.destroy()
                # TreeGridOverlay.update() from the inherited layer may already
                # be queued and does not consult _dead before rebuilding lines.
                # Detaching its tree makes that final queued callback exit.
                overlay.tree = _DetachedGridTree187()
            # Stage 18.4 tries to reinstall its grid after every refresh.  A
            # truthy no-op object keeps that inherited call idempotent while
            # preserving the 18.7 contract's line-free Income table surface.
            tree._barkav_grid_overlay = _LineFreeGrid187()
            self._ensure_tree_scrollbars_187(tree)
            self._install_table_refresh_187(tree)
            self._round_table_frame_187(tree, palette)
            # After the scrollbars above own their commands, so the overlay's
            # scroll relay wraps the final ones.
            row_overlay = decorate_rows_187(tree)
            for child in tree.master.winfo_children():
                if not isinstance(child, ttk.Scrollbar):
                    continue
                try:
                    horizontal = str(child.cget('orient')) == 'horizontal'
                except tk.TclError:
                    horizontal = False
                if not horizontal or getattr(child, '_barkav_row_overlay_scroll187', False):
                    continue
                child._barkav_row_overlay_scroll187 = True
                child.bind('<B1-Motion>', lambda _event, overlay=row_overlay: overlay.schedule(), add='+')
                child.bind('<ButtonRelease-1>', lambda _event, overlay=row_overlay: overlay.schedule(), add='+')
        except (tk.TclError, KeyError, AttributeError):
            return

    @staticmethod
    def _ensure_tree_scrollbars_187(tree):
        """Add only the missing axes to inherited pack-managed Treeviews."""
        try:
            if tree.winfo_manager() != 'pack':
                return
            parent = tree.master
            xcommand = str(tree.cget('xscrollcommand') or '')
            ycommand = str(tree.cget('yscrollcommand') or '')
            if not xcommand:
                xbar = ttk.Scrollbar(parent, orient='horizontal', command=tree.xview)
                xbar.pack(side='bottom', fill='x', before=tree)
                tree.configure(xscrollcommand=xbar.set)
                tree._barkav_xscroll187 = xbar
            if not ycommand:
                ybar = ttk.Scrollbar(parent, orient='vertical', command=tree.yview)
                ybar.pack(side='right', fill='y', before=tree)
                tree.configure(yscrollcommand=ybar.set)
                tree._barkav_yscroll187 = ybar
        except (tk.TclError, AttributeError):
            return

    def _round_shell_bars_187(self):
        """Decision 1.2: the top and footer bars are rounded.

        Both are classic tk frames, so the corner comes from a rounded plate
        painted behind their content - the same trick the table frames use.
        """
        from barkav_ui.skin import rounded_backdrop
        p = palette_187()
        radius = max(6, theme_metrics_187().get('radius', 6))
        for bar in getattr(self, '_shell_bars187', []):
            if not bar.winfo_exists():
                continue
            if not getattr(bar, '_barkav_bound187', False):
                bar._barkav_bound187 = True
                bar.bind('<Configure>',
                         lambda _e: self.after_idle(self._round_shell_bars_187), add='+')
            fill = p['surface'] if bar is self._shell_bars187[0] else p['surface_alt']
            try:
                bar.configure(highlightthickness=0, bd=0)
            except tk.TclError:
                pass
            if bar is self._shell_bars187[0]:
                self._install_brand_logo_187(background=fill)
                self._decorate_top_187()
            plate = rounded_backdrop(bar, fill=fill, page=p['bg'], radius=radius,
                                     border=p['border_subtle'], master=self)
            if plate is None:
                continue
            # Children were painted the old bar colour; match them to the plate
            # or they show as squares sitting on top of the rounded shape. The
            # rule between the top bar's two rows keeps its own colour.
            for child in bar.winfo_children():
                if child is plate or getattr(child, '_barkav_keep_bg187', False):
                    continue
                try:
                    child.configure(bg=fill)
                except tk.TclError:
                    continue


    def _round_table_frame_187(self, tree, palette):
        """Round the box a table sits in.

        The containers are classic ``tk.Frame``s, which cannot be rounded, so
        a rounded plate is painted behind and the table is inset a few pixels
        to let its corners show.  Only containers that hold nothing but the
        table and its scrollbars are touched, so no real layout is disturbed.
        """
        container = tree.master
        radius = max(4, theme_metrics_187().get('radius', 6))
        if isinstance(container, ttk.Frame):
            # SmartTable and friends are ttk frames, so they can simply take
            # the rounded Card style the skin already installed.
            try:
                container.configure(style='Card.TFrame', padding=3)
            except tk.TclError:
                pass
            return
        if not isinstance(container, tk.Frame):
            return
        siblings = [w for w in container.winfo_children()
                    if w is not getattr(container, '_barkav_backdrop', None)]
        if any(not isinstance(w, (ttk.Treeview, ttk.Scrollbar, tk.Scrollbar, tk.Label))
               for w in siblings):
            return
        if tree.winfo_manager() == 'pack':
            info = tree.pack_info()
            if int(info.get('padx') or 0) == 0:
                tree.pack_configure(padx=3, pady=3)
        from barkav_ui.skin import rounded_backdrop
        rounded_backdrop(container, fill=palette['panel'], page=palette['bg'],
                         radius=radius, border=palette['border_subtle'], master=self)

    def _apply_settings_live_187(self, old, new):
        family = resolve_font_family_187(self, new.get('font_family'))
        weight = resolve_font_weight_187(self, family, new.get('font_weight'))
        size = max(9, min(18, int(new.get('font_size') or 11)))
        row_height = max(28, min(46, int(new.get('row_height') or 40)))
        style_ttk_187(
            self,
            light=str(new.get('appearance') or 'dark').lower() == 'light',
            font_size=size,
            row_height=row_height,
        )
        for root in (self, getattr(self, 'settings_window187', None)):
            if root is None or not root.winfo_exists():
                continue
            for widget in v186._walk(root):
                self._apply_widget_font_187(widget, family, weight, size)
        self._apply_financial_report_theme_187()
        if getattr(self, 'footer_language_button187', None) is not None:
            self.footer_language_button187.configure(
                text='ENG' if str(new.get('language') or 'fa').lower() == 'en' else 'فا'
            )
        self._refresh_footer_theme_button_187()
        # A settings change must reach every screen, not only the ones
        # that happen to listen for it.
        art.clear_cache()
        self.unify_appearance_187()

    def _refresh_footer_theme_button_187(self):
        mode_button = getattr(self, 'footer_mode_button187', None)
        theme_button = getattr(self, 'footer_theme_button187', None)
        if mode_button is None and theme_button is None:
            return
        p = palette_187()
        mode = str(load_ui().get('appearance') or 'dark').lower()
        if mode_button is not None:
            mode_button.configure(text=self._display_mode_label_187())
        theme_button = getattr(self, 'footer_theme_button187', None)
        if theme_button is not None and theme_button.winfo_exists():
            # footer_theme_button187 is a ttk.Menubutton (Footer.TMenubutton) -
            # its colours come from that named style, already refreshed by the
            # style_ttk_187() call earlier in this same settings-apply path,
            # not from a direct bg/fg configure, which ttk widgets reject.
            theme_button.configure(text=self._theme_choice_label_187())

    def _close_file_menu_187(self, _event=None):
        popup = getattr(self, 'file_menu187', None)
        try:
            if popup is not None and popup.winfo_exists():
                popup.close()
        except tk.TclError:
            pass
        self.file_menu187 = None

    # D1 (operator-approved, with a better File menu): the product's own
    # drop-down - rounded, themed, a line icon per row, in two groups - like
    # the theme and export menus, instead of a hand-built grey panel.
    _FILE_MENU_ICONS_187 = {
        'ذخیره': 'save', 'ذخیره با نام': 'file', 'بروزرسانی': 'refresh',
        'تنظیمات': 'settings', 'ذخیره بسته توسعه': 'export', 'سیستم': 'system',
    }
    _FILE_MENU_HINTS_187 = {'ذخیره': 'بکاپ دستی', 'ذخیره با نام': 'فایل جدا'}

    def _show_file_menu_187(self, _event=None):
        current = getattr(self, 'file_menu187', None)
        if current is not None and current.winfo_exists():
            self._close_file_menu_187()
            return 'break'
        entries = (
            ('ذخیره', self.manual_save),
            ('ذخیره با نام', self.save_as),
            ('بروزرسانی', self.refresh_all),
            ('تنظیمات', self.open_settings_187),
            ('ذخیره بسته توسعه', self.export_development_package),
            ('سیستم', lambda: self._select_tab_text('سیستم')),
        )
        items = [
            {'label': label, 'command': command, 'icon': self._FILE_MENU_ICONS_187.get(label),
             'hint': self._FILE_MENU_HINTS_187.get(label, '')}
            for label, command in entries
        ]
        # On شروع the project's own entries (ذخیره) do not apply; there the
        # menu also carries the display mode and theme (operator round
        # 2026-09-27: they live only in «فایل» there, not in the footer).
        sections = [('برنامه', items[2:])]
        if getattr(self, '_window_view187', 'project') != 'start':
            sections.insert(0, ('پروژه', items[:2]))
        sections += self._theme_menu_sections_187()
        # The button sits at the bar's right end now (2026-09-27), so the
        # menu lines up with its right edge.
        self.file_menu187 = PopupMenu(
            self.file_button187, sections,
            side='below', align='right', min_width=240,
        )
        return 'break'

    # ------------------------------------------------------------------
    # Window tabs (استارت / پروژه) - one window instead of a second
    # top-level one. Ported from origin/master (docs/HANDOFF.md entry 10):
    # closing/reopening a project used to mean a whole separate OS window
    # (project_runner_stage18_7 spawns Stage187Dashboard in its own
    # process) with its own Hub window left open behind it. This keeps
    # that same subprocess model (opening a *different* project still
    # launches a new process - true in-place project switching would mean
    # turning this whole Tk-rooted dashboard chain into an embeddable
    # Frame, a much larger change) but gives the *current* window a
    # second, in-place view: a copy of the Hub's own "recent projects"
    # panel, toggled by a small tab row under the quick-command icons
    # rather than ever needing a second window for it.
    #
    # Adapted from master: the active project is selected through
    # PEYMAAN_ACTIVE_PROJECT_ID/_NAME; dashboards remain isolated per-project
    # processes. Start-view create/edit actions reuse ProjectRegistry and the
    # existing ProjectWizard without changing the financial data model.
    # ------------------------------------------------------------------

    def _build_window_tabs_187(self, row, p):
        # D1 (operator-approved): browser-style tabs - the selected one in the
        # same soft accent fill as the rail's selected item, the project's
        # with a cross that closes it. They read from the right end, شروع
        # first (operator round 2026-09-27; استارت reads «شروع»).
        # Operator round 2026-09-30: AutoCAD's file tabs - flat, side by side
        # with no gap, filling the bar's bottom row so they touch the rule
        # above and the bar's edge below. An unselected tab keeps a plate of
        # its own one step above the bar instead of the bar's black.
        self.tab_area187 = tk.Frame(row, bg=p['surface'], highlightthickness=0)
        # The first tab's right edge lines up with the file menu's above it.
        self.tab_area187.pack(side='right', fill='both', expand=True, padx=(0, 4))
        self.window_tabs187 = WindowTabs(self.tab_area187, background=p['surface'],
                                         height=self._SHELL_TABS_ROW_187, strip=True)
        self.window_tabs187.pack(side='right', fill='y')
        project_label = getattr(self, '_barkav_project_name187', None) or 'پروژه'
        self.window_tabs187.add('start', 'شروع', self._show_start_view_187)
        self.window_tabs187.add('project', project_label, self._show_project_view_187,
                                closable=True, on_close=self._close_project_tab_187)
        self._window_view187 = 'project'
        self._sync_window_tabs_187()
        # Switching views this early crashes: _install_shell_187 (still
        # running, right here) packs footer187 with before=self.notebook
        # *after* this method returns, which requires the notebook to
        # still be packed at that point. Deferring with after_idle runs
        # this once the whole synchronous _build() has finished instead.
        if os.environ.get('BARKAV_LAND_ON_START187') == '1':
            self.after_idle(self._show_start_view_187)

    def _sync_window_tabs_187(self):
        tabs = getattr(self, 'window_tabs187', None)
        if tabs is not None:
            tabs.select(self._window_view187)

    def _close_project_tab_187(self):
        """The project tab's cross closes this project's window, as the
        title bar's does - after asking, since it sits among other tabs."""
        name = getattr(self, '_barkav_project_name187', None) or 'این پروژه'
        if not messagebox.askyesno('بستن پروژه', f'پروژه «{name}» بسته شود؟', parent=self):
            return
        self.after(60, self.destroy)

    def _show_project_view_187(self):
        if self._window_view187 == 'project':
            return
        start_view = getattr(self, 'start_view187', None)
        if start_view is not None:
            start_view.pack_forget()
        self.notebook.pack(fill='both', expand=True, padx=8, pady=(5, 7))
        # _window_view187 must flip to 'project' *before* _rebuild_navbar()
        # runs: _rebuild_navbar's own early-return guard checks this same
        # attribute and still read 'start' here (set at the end of
        # _show_start_view_187, not yet updated) if left until after the
        # call - it would return immediately without ever re-packing the
        # navbar, leaving it silently unmapped. Confirmed live on master:
        # toggling استارت -> پروژه repeatedly left navbar.winfo_ismapped()
        # at 0 every single time until this reorder.
        self._window_view187 = 'project'
        # Re-pack + rebuild rather than a hardcoded .pack(...) here: 187
        # re-styles this into a right-side vertical rail (theme != 1) or
        # leaves it as the inherited horizontal strip (theme 1) - only
        # _rebuild_navbar itself knows which one currently applies.
        self._rebuild_navbar()
        self._set_shell_tools_visible_187(True)
        self._sync_window_tabs_187()

    def _show_start_view_187(self):
        if self._window_view187 == 'start':
            self._refresh_start_view_187()
            return
        self._remember_navbar_pack_187()
        self.navbar.pack_forget()
        self.notebook.pack_forget()
        crumb = getattr(self, 'crumb_bar187', None)
        if crumb is not None:
            crumb.pack_forget()
        if getattr(self, 'start_view187', None) is None:
            self._build_start_view_187()
        self.start_view187.pack(fill='both', expand=True, padx=8, pady=(5, 7))
        # Theme and display mode live in «فایل» on شروع (operator round
        # 2026-09-27), not in the footer.
        for name in ('footer_mode_button187', 'footer_theme_button187'):
            widget = getattr(self, name, None)
            try:
                if widget is not None and widget.winfo_manager():
                    widget.pack_forget()
            except tk.TclError:
                pass
        self._set_shell_tools_visible_187(False)
        self._refresh_start_view_187()
        self._window_view187 = 'start'
        self._sync_window_tabs_187()

    def _set_shell_tools_visible_187(self, visible: bool) -> None:
        """Show/hide the file/save/undo/redo/messages group and the search
        field.

        All three act on whichever project data the notebook tab is
        currently showing, so on استارت - a view of *other* projects, not
        this project's own data - they don't make sense to leave up. Each
        Stage187Dashboard is its own OS process per open project
        (project_runner_stage18_7.py's subprocess-per-project model), so
        toggling these instance attributes here is already correct per
        window; there is no shared/global state across two open projects
        for this to leak through.
        """
        # Operator round 2026-09-27: the bar keeps one layout on شروع and in
        # the project - the file menu at the right end of the top row, the
        # search at its left end, the tabs in the row below.
        # Operator round 2026-09-28: save/undo/redo used to live *inside*
        # «فایل»'s own pill, so hiding them on شروع shrank that pill and
        # dragged the tabs sideways with it - "the boxes change between
        # شروع and the project", reported live. They sit in a frame of
        # their own beside the file menu, so showing or hiding them never
        # moves the file menu or the tabs.
        tools = getattr(self, 'shell_tools_host187', None)
        host = getattr(self, 'quick_commands_host187', None)
        try:
            if host is not None and not host.winfo_manager():
                options = {'before': tools} if tools is not None and tools.winfo_manager() else {}
                host.pack(side='right', padx=(4, 10), **options)
        except tk.TclError:
            pass
        search = getattr(self, 'shell_search_host187', None)
        if search is not None and not search.winfo_manager():
            self._pack_shell_search_187()
        try:
            if tools is not None:
                if visible and not tools.winfo_manager():
                    options = {'after': host} if host is not None and host.winfo_manager() else {}
                    tools.pack(side='right', padx=(2, 4), **options)
                elif not visible and tools.winfo_manager():
                    tools.pack_forget()
        except tk.TclError:
            pass
        # The messages bell belongs to an open project: off on شروع, back at
        # the footer's left end in the project (operator round 2026-09-27).
        bell = getattr(self, 'bell_host187', None)
        try:
            if bell is not None and not visible:
                bell.pack_forget()
            elif bell is not None and not bell.winfo_manager():
                left = [w for w in bell.master.pack_slaves() if w.pack_info().get('side') == 'left']
                options = {'before': left[0]} if left else {}
                bell.pack(side='left', padx=(8, 2), **options)
        except tk.TclError:
            pass

    def _start_registry_187(self) -> ProjectRegistry:
        return ProjectRegistry(BASE_DIR)

    _START_PHASE_COUNT187 = 32

    def _start_phase_status_colors_187(self, p: dict[str, str]) -> dict[str, str]:
        # The brighter phase_summary_* tokens, not the plain phase_* ones
        # the real in-project strip uses - this glance-strip renders much
        # smaller and needed to stay legible against the card behind it.
        return {
            'NOT_STARTED': p['phase_summary_not_started'], 'ACTIVE': p['phase_summary_active'],
            'PAUSED': p['phase_summary_paused'], 'COMPLETED': p['phase_summary_completed'],
        }

    def _start_read_phase_progress_187(self, db_path: str) -> tuple[dict[int, dict], float]:
        """Read-only (mode=ro) against a project's own database - safe even
        while that same project is open elsewhere and writing to it; never
        writes, never calls migrate/seed (unlike BudgetService, which isn't
        built for this). A missing table or file just means "no data yet".
        """
        path = Path(db_path)
        try:
            stamp = tuple(
                (candidate.stat().st_mtime_ns, candidate.stat().st_size)
                if candidate.exists() else None
                for candidate in (path, Path(f'{path}-wal'))
            )
        except OSError:
            stamp = None
        cache = getattr(self, '_start_progress_cache187', None)
        if cache is None:
            cache = self._start_progress_cache187 = {}
        cache_key = str(path.resolve())
        cached = cache.get(cache_key)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        try:
            if not path.is_file():
                return {}, 0.0
            uri = f'file:{path.resolve().as_posix()}?mode=ro'
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    'SELECT phase_no, status, physical_progress FROM phase_progress_v163'
                ).fetchall()
            finally:
                conn.close()
            progress = {int(row['phase_no']): dict(row) for row in rows}
        except Exception:
            return {}, 0.0
        total = sum(
            float((progress.get(n) or {}).get('physical_progress') or 0)
            for n in range(1, self._START_PHASE_COUNT187 + 1)
        )
        result = (progress, total / self._START_PHASE_COUNT187)
        cache[cache_key] = (stamp, result)
        if len(cache) > 16:
            cache.pop(next(iter(cache)))
        return result

    def _start_phase_name_187(self, db_path: str, phase_no: int) -> str:
        """The project's own name for this phase (rich_phase_items, read-only);
        falls back to the official name from the 32-phase taxonomy when that
        project hasn't recorded an item for it yet."""
        try:
            path = Path(db_path)
            if path.is_file():
                uri = f'file:{path.resolve().as_posix()}?mode=ro'
                conn = sqlite3.connect(uri, uri=True, timeout=1.0)
                try:
                    row = conn.execute(
                        "SELECT phase_name FROM rich_phase_items WHERE phase_no=? "
                        "AND phase_name IS NOT NULL AND phase_name != '' LIMIT 1",
                        (phase_no,),
                    ).fetchone()
                finally:
                    conn.close()
                if row and row[0]:
                    return str(row[0])
        except Exception:
            pass
        hints = PHASE_HINTS.get(phase_no)
        return hints[0] if hints else f'فاز {phase_no}'

    def _paint_resizable_backdrop_187(self, container, *, fill, page, radius, border):
        """rounded_backdrop(), kept in sync with the container's real size.

        The backdrop is a fixed-size PhotoImage painted once from whatever
        width/height the container happens to have at that moment.
        Re-painting on the container's own <Configure> keeps the two in
        step; the size check skips redundant repaints when a <Configure>
        fires without an actual size change.
        """
        from barkav_ui.skin import rounded_backdrop

        rounded_backdrop(container, fill=fill, page=page, radius=radius, border=border, master=self)
        container._barkav_backdrop_size187 = (container.winfo_width(), container.winfo_height())

        if getattr(container, '_barkav_backdrop_bound187', False):
            return

        def _on_configure(event, container=container):
            size = (event.width, event.height)
            if size == getattr(container, '_barkav_backdrop_size187', None):
                return
            container._barkav_backdrop_size187 = size
            rounded_backdrop(container, fill=fill, page=page, radius=radius,
                             border=border, master=self)

        container._barkav_backdrop_bound187 = True
        container.bind('<Configure>', _on_configure, add='+')

    _START_CARD_LIMIT187 = 60
    _START_CARD_GAP187 = 8

    def _build_start_view_187(self):
        """استارت (operator-approved S1-S4): a welcome with the way back into
        the last project and the three things this page is for as cards.
        Beneath them (operator round 2026-09-27) two framed halves: the
        recent projects, searchable and pinnable, on the right, and the
        BARKAV mark with the building sketch - the earlier watermark - on
        the left.
        """
        p = palette_187()
        view = tk.Frame(self, bg=p['bg'])
        self.start_view187 = view
        radius = max(8, int(theme_metrics_187().get('radius', 6)))
        column = tk.Frame(view, bg=p['bg'])
        column.pack(fill='both', expand=True, padx=28, pady=(16, 10))

        # S1: welcome, and the last project one click away.
        hero = tk.Frame(column, bg=p['card'])
        hero.pack(fill='x')
        words = tk.Frame(hero, bg=p['card'])
        words.pack(side='right', fill='x', expand=True, padx=18, pady=14)
        tk.Label(words, text='خوش آمدید', bg=p['card'], fg=p['text_primary'],
                 font=kit_font('title', widget=self), anchor='e').pack(fill='x')
        self.start_last187 = tk.Label(words, text='', bg=p['card'], fg=p['text_secondary'],
                                      font=kit_font('body', widget=self), anchor='e')
        self.start_last187.pack(fill='x', pady=(3, 0))
        self.start_continue187 = ttk.Button(hero, text='ادامه', style='Primary.TButton',
                                            command=self._start_continue_187, cursor='hand2')
        self.start_continue187.pack(side='left', padx=18)
        self._paint_resizable_backdrop_187(hero, fill=p['card'], page=p['bg'], radius=radius,
                                           border=p['border_subtle'])

        # S1: the three actions, as cards instead of three bare links - each
        # with its own colour, the first one in the accent.
        actions = tk.Frame(column, bg=p['bg'])
        actions.pack(fill='x', pady=(12, 0))
        for index in range(3):
            actions.grid_columnconfigure(index, weight=1, uniform='start_actions187')
        for index, (icon, hue, title, hint, command) in enumerate((
            ('new_project', p['accent'], 'پروژه جدید', 'از صفر، با ویزارد پروژه',
             self._start_new_project_187),
            ('open_project', p.get('orange') or p['accent'], 'باز کردن پروژه',
             'یک فایل پروژه (.brk) را انتخاب کن', self._start_open_shortcut_187),
            ('edit_project', p.get('violet') or p['accent'], 'ویرایش پروژه',
             'نام و تنظیمات یک پروژه را تغییر بده', self._start_edit_project_187),
        )):
            card = self._start_action_card_187(actions, icon, hue, title, hint, command, p, radius)
            # The first action reads first: the right-most column.
            card.grid(row=0, column=2 - index, sticky='nsew', padx=(0 if index == 2 else 6, 0 if index == 0 else 6))

        # Two framed halves under the actions, the split in line with the
        # gaps between the action cards.
        lower = tk.Frame(column, bg=p['bg'])
        lower.pack(fill='both', expand=True, pady=(12, 0))
        lower.grid_rowconfigure(0, weight=1)
        for index in range(2):
            lower.grid_columnconfigure(index, weight=1, uniform='start_lower187')
        recent = tk.Frame(lower, bg=p['card'])
        recent.grid(row=0, column=1, sticky='nsew', padx=(6, 0))
        mark = tk.Frame(lower, bg=p['card'])
        mark.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        self.start_recent_panel187 = recent
        self.start_mark_panel187 = mark

        # S3: the list's heading, and opposite it on the panel's left the
        # search over the projects.
        head = tk.Frame(recent, bg=p['card'])
        head.pack(fill='x', padx=16, pady=(12, 10))
        tk.Label(head, text='پروژه‌های اخیر', bg=p['card'], fg=p['text_primary'],
                 font=kit_font('title', widget=self), anchor='e').pack(side='right')
        search = tk.Frame(head, bg=p['card'])
        search.pack(side='left')
        self.start_query187 = tk.StringVar()
        entry = ttk.Entry(search, textvariable=self.start_query187, justify='right', width=26)
        glass_image = line_icon_187('search', size=16, colour=p['text_secondary'], background=None, master=self)
        if glass_image is not None:
            glass = tk.Label(search, image=glass_image, bg=p['card'], bd=0)
            glass.image = glass_image
            glass.pack(side='right', padx=(6, 0))
        entry.pack(side='right')
        self.start_search187 = entry
        self._install_start_placeholder_187(entry)
        self.start_query187.trace_add('write', lambda *_: self._refresh_start_view_187())

        # S2: the project cards, one to a row - as many as the panel holds
        # (_fit_start_cards_187). The host asks for no size of its own, so
        # the cards never push the page taller than the window.
        self.start_recent_host187 = tk.Frame(recent, bg=p['card'])
        self.start_recent_host187.pack(fill='both', expand=True, padx=14, pady=(0, 14))
        self.start_recent_host187.pack_propagate(False)
        # Operator round 2026-09-27: every project in a list that scrolls,
        # each card whole inside the frame, rather than as many as fit.
        self._build_start_scroll_list_187(self.start_recent_host187, p)
        self._paint_resizable_backdrop_187(recent, fill=p['card'], page=p['bg'], radius=radius,
                                           border=p['border_subtle'])

        # The earlier watermark - the mark with its tagline over the building
        # sketch - now in a frame of its own.
        self.start_mark187 = tk.Canvas(mark, bg=p['card'], bd=0, highlightthickness=0,
                                       width=1, height=1)
        self.start_mark187.pack(fill='both', expand=True, padx=16, pady=16)
        self.start_mark187.bind('<Configure>', self._schedule_start_mark_187, add='+')
        self._paint_resizable_backdrop_187(mark, fill=p['card'], page=p['bg'], radius=radius,
                                           border=p['border_subtle'])

    def _schedule_start_mark_187(self, _event=None):
        # A window drag sends a run of sizes; paint once it settles.
        pending = getattr(self, '_start_mark_job187', None)
        if pending is not None:
            try:
                self.after_cancel(pending)
            except tk.TclError:
                pass
        self._start_mark_job187 = self.after(90, self._paint_start_mark_187)

    def _paint_start_mark_187(self):
        """The BARKAV mark and its tagline above the building sketch, both
        faint in the accent, centred as one group in the left frame."""
        self._start_mark_job187 = None
        canvas = getattr(self, 'start_mark187', None)
        try:
            if canvas is None or not canvas.winfo_exists():
                return
            width, height = canvas.winfo_width(), canvas.winfo_height()
        except tk.TclError:
            return
        if width < 80 or height < 80:
            return
        p = palette_187()
        colour = mix(p['card'], p['accent'], 0.22)
        # Operator round 2026-09-27: the mark larger and a step stronger
        # than the sketch, so «Engineering & Construction» reads, with clear
        # room between it and the building.
        mark_colour = mix(p['card'], p['accent'], 0.5)
        # Sizes move in steps so resizing does not fill the image cache.
        step = 16
        logo_height = max(64, min(160, int(height * 0.34) // step * step))
        gap = 40
        sketch_width = max(step, (width - 16) // step * step)
        sketch_height = max(step, (height - logo_height - gap - 8) // step * step)
        try:
            logo = art.logo(height=logo_height, background=p['card'], colour=mark_colour,
                            drop_tagline=False, wordmark_scale=1.15, align_wordmark=True,
                            master=self)
            sketch = art.construction_watermark(max_width=sketch_width, max_height=sketch_height,
                                                background=p['card'], colour=colour, master=self)
        except (OSError, ValueError, tk.TclError):
            return
        canvas.delete('all')
        pictures = [image for image in (logo, sketch) if image is not None]
        canvas._barkav_images187 = pictures
        if not pictures:
            return
        total = sum(image.height() for image in pictures) + gap * (len(pictures) - 1)
        y = max(0, (height - total) // 2)
        for image in pictures:
            canvas.create_image(width // 2, y, image=image, anchor='n')
            y += image.height() + gap

    def _install_start_placeholder_187(self, entry):
        # Plain «جستجو», no ellipsis (operator round 2026-09-28, second pass).
        prompt = rtl_187('جستجو')
        self._start_placeholder_on187 = False

        def show(_event=None):
            if not self.start_query187.get():
                self._start_placeholder_on187 = True
                self.start_query187.set(prompt)
                entry.configure(foreground=palette_187()['empty'])

        def hide(_event=None):
            if self._start_placeholder_on187:
                self._start_placeholder_on187 = False
                self.start_query187.set('')
                entry.configure(foreground=palette_187()['text_primary'])

        entry.bind('<FocusIn>', hide, add='+')
        entry.bind('<FocusOut>', show, add='+')
        show()

    def _start_query_187(self) -> str:
        if getattr(self, '_start_placeholder_on187', False):
            return ''
        variable = getattr(self, 'start_query187', None)
        return en(str(variable.get() if variable is not None else '')).strip().lower()

    def _start_clickable_187(self, card, widgets, command, p, radius, *, border=None,
                             fill=None, page=None):
        """A whole card is one button: a click anywhere on it runs
        ``command``, and pointing at it lights its outline."""
        from barkav_ui.skin import rounded_backdrop

        border = border or p['border_subtle']
        fill, page = fill or p['card'], page or p['bg']
        card._barkav_hot187 = False

        # Pointing at a card lifts its outline to a lighter neutral, 2px -
        # not the cyan a selected or current item wears (operator round
        # 2026-09-27).
        hover_border = mix(p['border_subtle'], p['text_primary'], 0.45)

        def paint(hot: bool) -> None:
            if hot == card._barkav_hot187:
                return
            card._barkav_hot187 = hot
            try:
                rounded_backdrop(card, fill=fill, page=page, radius=radius,
                                 border=(border if border == p['accent'] else hover_border) if hot else border,
                                 border_width=2 if hot else 1, master=self)
            except tk.TclError:
                pass

        def settle(_event=None):
            # Moving between the card's own pieces sends Leave/Enter pairs;
            # the card is hot while the pointer is anywhere inside it.
            def check():
                try:
                    under = self.winfo_containing(*self.winfo_pointerxy())
                except (tk.TclError, KeyError):
                    under = None
                inside = False
                while under is not None:
                    if under is card:
                        inside = True
                        break
                    under = getattr(under, 'master', None)
                paint(inside)
            try:
                self.after(25, check)
            except tk.TclError:
                pass

        for widget in widgets:
            widget.bind('<Button-1>', lambda _e: command(), add='+')
            widget.bind('<Enter>', settle, add='+')
            widget.bind('<Leave>', settle, add='+')

    def _build_start_scroll_list_187(self, host, p):
        canvas = tk.Canvas(host, bg=p['card'], bd=0, highlightthickness=0)
        bar = ttk.Scrollbar(host, orient='vertical', command=canvas.yview)
        inner = tk.Frame(canvas, bg=p['card'])
        window = canvas.create_window(0, 0, window=inner, anchor='nw')
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side='right', fill='both', expand=True)

        def resized(_event=None):
            try:
                canvas.configure(scrollregion=(0, 0, canvas.winfo_width(), inner.winfo_reqheight()))
                # The bar only when the list is longer than the frame (on
                # the left: the list reads from the right).
                if inner.winfo_reqheight() > canvas.winfo_height() + 1:
                    if not bar.winfo_manager():
                        bar.pack(side='left', fill='y', padx=(0, 4), before=canvas)
                else:
                    bar.pack_forget()
                    canvas.yview_moveto(0)
            except tk.TclError:
                pass

        canvas.bind('<Configure>', lambda e: (canvas.itemconfigure(window, width=e.width), resized()),
                    add='+')
        inner.bind('<Configure>', resized, add='+')

        def wheel(event):
            # <Enter>/<Leave> on `host` used to arm and disarm this, but
            # every card inside `inner` is itself a widget: the pointer
            # crosses into one on the very first pixel over the list, Tk
            # fires <Leave> on `host` for that crossing, and the wheel goes
            # dead again - reported live (operator round 2026-09-28). A
            # bind_all kept armed for the list's whole lifetime, gated by
            # checking the pointer's widget on each event instead, has no
            # such crossing to trip over.
            try:
                if not bar.winfo_manager():
                    return None
                under = self.winfo_containing(*self.winfo_pointerxy())
                while under is not None and under is not host:
                    under = getattr(under, 'master', None)
                if under is not host:
                    return None
                step = -1 if (getattr(event, 'delta', 0) > 0 or getattr(event, 'num', 0) == 4) else 1
                canvas.yview_scroll(step, 'units')
            except tk.TclError:
                return None
            return 'break'

        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.bind_all(sequence, wheel, add='+')
        self.start_recent_list187 = inner
        self.start_recent_canvas187 = canvas

    def _start_hidden_187(self) -> list[str]:
        return [str(item) for item in (load_ui().get('start_hidden187') or [])]

    def _start_hide_project_187(self, project_id: str) -> None:
        """The × on a recent project: off the list (a search still finds
        it); the project and its file are untouched."""
        ui = load_ui()
        hidden = [str(item) for item in (ui.get('start_hidden187') or [])]
        if project_id not in hidden:
            hidden.append(project_id)
        ui['start_hidden187'] = hidden
        save_ui(ui)
        self._refresh_start_view_187()

    def _start_action_card_187(self, parent, icon, hue, title, hint, command, p, radius):
        # Operator round 2026-09-27: a shaded two-tone tile instead of a
        # plain line icon, and a lower card.
        card = tk.Frame(parent, bg=p['card'], cursor='hand2')
        tile = feature_tile_187(icon, size=38, colour=hue, ink=p['on_accent'],
                                background=p['card'], master=self)
        badge = tk.Label(card, image=tile, bg=p['card'], cursor='hand2', bd=0)
        badge.image = tile
        badge.pack(side='right', padx=(10, 12), pady=10)
        words = tk.Frame(card, bg=p['card'], cursor='hand2')
        # A left inset so the heading/hint labels stop short of the card's
        # true left edge instead of painting over its border there (same
        # fix as the recent-project rows, operator round 2026-09-28).
        words.pack(side='right', fill='x', expand=True, pady=8, padx=(10, 8))
        heading = tk.Label(words, text=title, bg=p['card'], fg=p['text_primary'], cursor='hand2',
                           font=kit_font('body', widget=self, bold=True), anchor='e')
        heading.pack(fill='x')
        sub = tk.Label(words, text=hint, bg=p['card'], fg=p['text_secondary'], cursor='hand2',
                       font=kit_font('small', widget=self), anchor='e')
        sub.pack(fill='x', pady=(1, 0))
        self._paint_resizable_backdrop_187(card, fill=p['card'], page=p['bg'], radius=radius,
                                           border=p['border_subtle'])
        self._start_clickable_187(card, (card, badge, words, heading, sub), command, p, radius)
        return card

    def _start_opened_187(self, project: ProjectEntry) -> float:
        try:
            return Path(project.db_path).stat().st_mtime
        except OSError:
            return 0.0

    def _start_pins_187(self) -> list[str]:
        return [str(item) for item in (load_ui().get('start_pins187') or [])]

    def _start_toggle_pin_187(self, project_id: str) -> None:
        """S3: a pinned project stays at the top of the list."""
        ui = load_ui()
        pins = [str(item) for item in (ui.get('start_pins187') or [])]
        if project_id in pins:
            pins.remove(project_id)
        else:
            pins.insert(0, project_id)
        ui['start_pins187'] = pins
        save_ui(ui)
        self._refresh_start_view_187()

    def _start_continue_187(self) -> None:
        project = getattr(self, '_start_latest187', None)
        if project is not None:
            self._start_open_project_187(project)

    def _refresh_start_view_187(self, *, force=False):
        host = getattr(self, 'start_recent_list187', None) or getattr(self, 'start_recent_host187', None)
        if host is None:
            return
        p = palette_187()
        radius = max(8, int(theme_metrics_187().get('radius', 6)))
        try:
            projects = list(self._start_registry_187().list())
        except Exception:
            projects = []

        # S1: the welcome line names the last project opened.
        recent = sorted(projects, key=self._start_opened_187, reverse=True)
        latest = recent[0] if recent else None
        self._start_latest187 = latest
        if latest is not None:
            opened = self._start_opened_187(latest)
            when = fa(gregorian_to_shamsi(datetime.fromtimestamp(opened).date())) if opened else '—'
            self.start_last187.configure(text=f'آخرین بار «{latest.name}» را در {when} باز کردی.')
            self.start_continue187.configure(text=f'ادامه {latest.name}')
            if not self.start_continue187.winfo_manager():
                self.start_continue187.pack(side='left', padx=18)
        else:
            self.start_last187.configure(text='هنوز پروژه‌ای باز نشده است؛ از «پروژه جدید» شروع کن.')
            self.start_continue187.pack_forget()

        self._start_cards187 = []
        self._start_more187 = None
        if not projects:
            tk.Label(host, text='هنوز پروژه‌ای ثبت نشده است.', bg=p['card'], fg=p['text_secondary'],
                     font=kit_font('body', widget=self)).pack(pady=20)
            return
        # S3: pinned projects first, then the most recently opened.
        pins = self._start_pins_187()
        ordered = sorted(projects, key=lambda item: (item.project_id not in pins,
                                                     -self._start_opened_187(item)))
        query = self._start_query_187()
        hidden = set(self._start_hidden_187())
        matches = [item for item in ordered
                   if (query or item.project_id not in hidden)
                   and (not query or query in en(str(item.name)).lower() or query in str(item.project_id).lower())]
        if not matches:
            tk.Label(host, text='پروژه‌ای با این نام پیدا نشد.', bg=p['card'], fg=p['text_secondary'],
                     font=kit_font('body', widget=self)).pack(pady=20)
            return
        self._start_match_count187 = len(matches)
        # The note sits at the foot of the frame, shown only when some
        # matches do not fit.
        self._start_more187 = tk.Label(host, text='', bg=p['card'], fg=p['text_secondary'],
                                       font=kit_font('small', widget=self), anchor='e')
        self._start_more187 = None
        for index, project in enumerate(matches[:self._START_CARD_LIMIT187]):
            card = self._start_project_card_187(host, project, project.project_id in pins, p, radius)
            card.pack(side='top', fill='x', padx=(2, 2), pady=(self._START_CARD_GAP187 if index else 2, 0))
            self._start_cards187.append(card)

    def _fit_start_cards_187(self, _event=None):
        """As many project cards as the frame holds, in order; the rest are
        named in the note at its foot. Reads the cards' own heights, so it
        follows the font size and the window."""
        host = getattr(self, 'start_recent_host187', None)
        cards = [card for card in getattr(self, '_start_cards187', None) or [] if card.winfo_exists()]
        note = getattr(self, '_start_more187', None)
        if host is None or not cards or getattr(self, '_start_fitting187', False):
            return
        self._start_fitting187 = True
        try:
            host.update_idletasks()
            height = host.winfo_height()
            if height <= 1:
                return
            total = max(len(cards), int(getattr(self, '_start_match_count187', len(cards))))
            gap = self._START_CARD_GAP187
            note_height = note.winfo_reqheight() + 6 if note is not None else 0
            used = shown = 0
            for index, card in enumerate(cards):
                need = card.winfo_reqheight() + (gap if index else 0)
                reserve = note_height if total > index + 1 else 0
                if shown and used + need + reserve > height:
                    break
                used += need
                shown += 1
            for index, card in enumerate(cards):
                if index >= shown:
                    card.pack_forget()
                elif not card.winfo_manager():
                    card.pack(side='top', fill='x', pady=(gap if index else 0, 0))
            hidden = total - shown
            if note is not None:
                if hidden > 0:
                    note.configure(text=f'و {fa(hidden)} پروژهٔ دیگر - برای دیدنشان نام را جستجو کن.')
                    if not note.winfo_manager():
                        note.pack(side='bottom', fill='x')
                else:
                    note.pack_forget()
        except tk.TclError:
            pass
        finally:
            self._start_fitting187 = False

    def _start_project_card_187(self, parent, project: ProjectEntry, pinned: bool, p, radius):
        """S2: one project - its overall progress as a ring, name, when it
        was last opened, the phase it is in, and its 32 phases in brief."""
        is_current = project.project_id == getattr(self, '_barkav_project_id187', None)
        progress, average = self._start_read_phase_progress_187(project.db_path)
        overall = max(0.0, min(1.0, float(average or 0) / 100))
        count = self._START_PHASE_COUNT187
        active = sorted(n for n in range(1, count + 1)
                        if str((progress.get(n) or {}).get('status') or '') == 'ACTIVE')
        phase_text = self._start_phase_name_187(project.db_path, active[0]) if active else '—'
        opened = self._start_opened_187(project)
        when = fa(gregorian_to_shamsi(datetime.fromtimestamp(opened).date())) if opened else '—'
        # Inside the framed list the cards sit a step darker than the frame
        # (operator round 2026-09-27), wells rather than cards on cards.
        fill, page = p['bg'], p['card']
        track = mix(fill, p['text_primary'], 0.1)

        card = tk.Frame(parent, bg=fill, cursor='hand2')
        # Compact enough for several to a frame.
        ring = tk.Canvas(card, width=52, height=52, bg=fill, bd=0, highlightthickness=0, cursor='hand2')
        ring.pack(side='right', padx=(10, 12), pady=10)
        image = progress_ring_187(overall, size=48, width=5, colour=p['accent'], track=track,
                                  background=fill, master=self)
        ring.image = image
        ring.create_image(26, 26, image=image)
        ring.create_text(26, 26, text=f'{fa(round(overall * 100))}٪', fill=p['text_primary'],
                         font=kit_font('small', widget=self, bold=True))
        body = tk.Frame(card, bg=fill, cursor='hand2')
        # A left inset, or the pin/× icons sit flush on the card's true left
        # edge and paint straight over the 1px border there - the frame
        # read as open on that side, reported live (operator round
        # 2026-09-28).
        body.pack(side='right', fill='both', expand=True, pady=10, padx=(10, 12))
        row = tk.Frame(body, bg=fill, cursor='hand2')
        row.pack(fill='x')
        name = tk.Label(row, text=fa(project.name), bg=fill, cursor='hand2',
                        fg=p['accent'] if is_current else p['text_primary'],
                        font=kit_font('body', widget=self, bold=True), anchor='e')
        name.pack(side='right')
        pieces = [card, ring, body, row, name]
        if is_current:
            here = tk.Label(row, text='· همین پنجره', bg=fill, fg=p['text_secondary'],
                            font=kit_font('small', widget=self), cursor='hand2')
            here.pack(side='right', padx=(6, 0))
            pieces.append(here)
        pin_image = line_icon_187('pin', size=16, colour=p['accent'] if pinned else p['text_secondary'],
                                  background=None, master=self)
        pin = tk.Label(row, image=pin_image, bg=fill, cursor='hand2', bd=0)
        pin.image = pin_image
        pin.pack(side='left')
        pin.bind('<Button-1>', lambda _e, pid=project.project_id: (self._start_toggle_pin_187(pid), 'break')[1])
        attach_tooltip(pin, 'برداشتن سنجاق' if pinned else 'سنجاق کن تا همیشه بالا بماند', side='below')
        if not is_current:
            close_image = line_icon_187('close', size=14, colour=p['text_secondary'], background=None,
                                        master=self)
            close = tk.Label(row, image=close_image, bg=fill, cursor='hand2', bd=0)
            close.image = close_image
            close.pack(side='left', padx=(0, 8))
            close.bind('<Button-1>',
                       lambda _e, pid=project.project_id: (self._start_hide_project_187(pid), 'break')[1])
            attach_tooltip(close, 'برداشتن از فهرست اخیر (پروژه پاک نمی‌شود)', side='below')
        meta = tk.Label(body, text=f'آخرین باز شدن {when} · مرحله: {fa(phase_text)}', bg=fill,
                        fg=p['text_secondary'], font=kit_font('small', widget=self), anchor='e', cursor='hand2')
        meta.pack(fill='x', pady=(2, 6))
        strip = tk.Canvas(body, height=8, bg=fill, bd=0, highlightthickness=0, cursor='hand2')
        strip.pack(fill='x')
        colours = self._start_phase_status_colors_187(p)

        def draw_strip(_event=None, canvas=strip, progress=progress):
            try:
                canvas.delete('all')
                width = canvas.winfo_width()
            except tk.TclError:
                return
            if width < 64:
                return
            gap = 2
            cell = (width - gap * (count - 1)) / count
            for number in range(1, count + 1):
                status = str((progress.get(number) or {}).get('status') or 'NOT_STARTED')
                colour = track if status == 'NOT_STARTED' else colours.get(status, track)
                x1 = width - (number - 1) * (cell + gap)
                canvas.create_rectangle(x1 - cell, 0, x1, 8, fill=colour, outline='')

        strip.bind('<Configure>', draw_strip, add='+')
        pieces.extend((meta, strip))
        border = p['accent'] if is_current else p['border_subtle']
        self._paint_resizable_backdrop_187(card, fill=fill, page=page, radius=radius, border=border)
        self._start_clickable_187(card, pieces, lambda item=project: self._start_open_project_187(item),
                                  p, radius, border=border, fill=fill, page=page)
        return card

    def _start_open_project_187(self, project: ProjectEntry) -> None:
        if project.project_id == getattr(self, '_barkav_project_id187', None):
            self._show_project_view_187()
            return
        # Reuses this codebase's own ProjectInstanceGuard/
        # bring_process_window_to_front (barkav_bare_launcher_187.
        # ProjectHub187._launch_project's pattern) instead of master's
        # plain Popen, so opening an already-running project from here
        # focuses its real window rather than starting a duplicate.
        guard = ProjectInstanceGuard(BASE_DIR / 'runtime', project.project_id)
        if not guard.acquire():
            owner_pid = guard.owner_pid()
            if owner_pid:
                bring_process_window_to_front(owner_pid)
            return
        guard.release()
        args = ([sys.executable, '--run-project', project.project_id] if frozen()
                else [sys.executable, str(BASE_DIR / 'project_runner_stage18_7.py'), project.project_id])
        subprocess.Popen(args, cwd=str(BASE_DIR))

    def _start_project_secrets_187(self) -> dict:
        # Same local-only lookup as the launcher. Secret values are never
        # logged or copied into project data here.
        return load_local_secrets(BASE_DIR)

    def _start_project_wizard_done_187(self, project: ProjectEntry) -> None:
        self._refresh_start_view_187(force=True)
        if project.project_id == getattr(self, '_barkav_project_id187', None):
            messagebox.showinfo(
                'پروژه ویرایش شد',
                'تغییرات ذخیره شد. برای اعمال اطلاعات تازهٔ گروه تلگرام، این پروژه را ببند و دوباره باز کن.',
                parent=self,
            )

    def _start_new_project_187(self) -> None:
        from project_center_stage15 import ProjectWizard

        ProjectWizard(
            self, self._start_registry_187(), self._start_project_secrets_187(),
            on_done=self._start_project_wizard_done_187, palette=palette_187(),
        )

    def _start_edit_project_187(self) -> None:
        from project_center_stage15 import ProjectWizard

        projects = self._start_registry_187().list()
        if not projects:
            messagebox.showinfo('ویرایش پروژه', 'هنوز پروژه‌ای ساخته نشده.', parent=self)
            return
        p = palette_187()
        dialog = BarkavWindow(self, 'انتخاب پروژه برای ویرایش', size_class='tiny', show_footer=False)
        content = dialog.body
        dialog.title('انتخاب پروژه برای ویرایش')
        dialog.configure(bg=p['bg'])
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.geometry('440x190')
        tk.Label(
            content, text='پروژهٔ مورد نظر برای ویرایش را انتخاب کن:',
            bg=p['bg'], fg=p['text'], anchor='e',
            font=kit_font('body', widget=self),
        ).pack(fill='x', padx=18, pady=(20, 8))
        names = [f'{project.name} ({project.project_id})' for project in projects]
        choice = tk.StringVar(value=names[0])
        combo = ttk.Combobox(
            content, textvariable=choice, values=names, state='readonly', justify='right',
        )
        combo.pack(fill='x', padx=18, pady=8)

        def proceed() -> None:
            selected = projects[names.index(choice.get())]
            dialog.destroy()
            ProjectWizard(
                self, self._start_registry_187(), self._start_project_secrets_187(),
                on_done=self._start_project_wizard_done_187,
                palette=p, existing=selected,
            )

        buttons = tk.Frame(content, bg=p['bg'])
        buttons.pack(fill='x', padx=18, pady=(12, 18))
        ttk.Button(buttons, text='ادامه', command=proceed).pack(side='left')
        ttk.Button(buttons, text='انصراف', command=dialog.destroy).pack(side='right')
        dialog.bind('<Escape>', lambda _event: dialog.destroy())
        combo.focus_set()

    def _start_open_shortcut_187(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title='بازکردن پروژه',
            filetypes=[('BARKAV Project', '*.brk')],
        )
        if not path:
            return
        # Same argv[1]-is-the-path convention launcher_stage18_7.main()
        # already uses for a double-clicked .brk file - no special flag.
        args = ([sys.executable, path] if frozen() else
                [sys.executable, str(BASE_DIR / 'launcher_stage18_7.py'), path])
        subprocess.Popen(args, cwd=str(BASE_DIR))

    # The top bar is a tenth taller than the 67px it had (operator round
    # 2026-09-30). The mark, at the size it always had, spans the bar's full
    # height at the left; beside it are two rows divided by a 1px rule, tools
    # and search above, window tabs below. The tab row rests on the bar's own
    # 1px bottom edge, so: inset + tools row + rule + tabs row + edge = 74.
    _SHELL_BAR_HEIGHT_187 = 74
    _SHELL_INSET_187 = 2
    _SHELL_TOOLS_ROW_187 = 36
    _SHELL_TABS_ROW_187 = 34
    # How far the tab row keeps from the bar's right end: the tabs run down to
    # the bar's edge, and its rounded corner has to stay clear of them.
    _SHELL_CORNER_CLEAR_187 = 8
    # The command icons: a 22px glyph (the earlier bar drew 18px) on a 30px tile.
    _SHELL_ICON_187 = 22
    _SHELL_TILE_187 = 30

    def _build_shell_rows_187(self, top, p):
        """The top bar's two rows and the rule between them, right of the mark.

        Packed from the bottom up so the tab row rests on the bar's own bottom
        edge and the rule on the tab row's top: nothing shows between the tabs
        and either line (operator round 2026-09-30). The rows are plain
        frames, so each keeps clear of the bar's rounded corners; the rule
        keeps its own colour when _round_shell_bars_187 repaints the bar's
        other children.
        """
        inset = self._SHELL_INSET_187
        row2 = tk.Frame(top, bg=p['surface'], height=self._SHELL_TABS_ROW_187,
                        bd=0, highlightthickness=0)
        row2.pack(side='bottom', fill='x', padx=(0, self._SHELL_CORNER_CLEAR_187), pady=(0, 1))
        row2.pack_propagate(False)
        rule = tk.Frame(top, bg=p['border'], height=1, bd=0, highlightthickness=0)
        rule.pack(side='bottom', fill='x', padx=(0, 1))
        rule._barkav_keep_bg187 = True
        row1 = tk.Frame(top, bg=p['surface'], height=self._SHELL_TOOLS_ROW_187,
                        bd=0, highlightthickness=0)
        row1.pack(side='top', fill='x', padx=(0, inset), pady=(inset, 0))
        row1.pack_propagate(False)
        self.shell_tools_row187, self.shell_rule187, self.shell_tabs_row187 = row1, rule, row2
        return row1, row2

    def _install_shell_187(self):
        p = palette_187()
        fs = max(9, min(12, int(load_ui().get('font_size') or 10)))
        clock = getattr(self, 'datetime_label_186', None)
        if clock is None:
            return
        tools = clock.master
        top = tools.master
        top.configure(bg=p['surface'], highlightbackground=p['border_subtle'], highlightthickness=1)
        tools.configure(bg=p['surface'])

        for button in getattr(self, 'command_buttons', []):
            button.destroy()
        old_theme = getattr(self, 'quick_theme_button', None)
        if old_theme is not None:
            old_theme.destroy()
        clock.destroy()
        # The inherited tools frame is empty now; left packed, its padding
        # held the window tabs off the bar's right end.
        tools.pack_forget()

        # Operator round 2026-09-30: the mark at the left spans the bar's full
        # height, beside two rows under one frame. The top row holds the
        # search next to the mark, and at the right the file menu - a bare
        # three-bar mark, no word - then save, undo, redo, refresh. A rule
        # divides it from the bottom row, which holds the window tabs, شروع
        # first from the right, in AutoCAD's file-tab style. The messages
        # bell went to the footer.
        row1, row2 = self._build_shell_rows_187(top, p)
        brand = getattr(self, '_brand_host_186', None)
        if brand is not None:
            # The mark's holder stays where the inherited bar packed it, first
            # in the packing order, and takes the bar's height. Its options
            # are set outright: a re-pack keeps the old ones, and the 4px pady
            # the inherited bar gave it is not wanted here.
            brand.pack_configure(side='left', fill='y', padx=(14, 6), pady=2)
        self.quick_commands_host187 = tk.Frame(row1, bg=p['surface'])
        self.quick_commands_host187.pack(side='right', padx=(4, 10))
        group = self.quick_commands_host187
        self.file_button187 = tk.Button(
            group, text='', command=self._show_file_menu_187,
            bg=p['surface'], fg=p['text'], activebackground=p['surface'],
            activeforeground=p['text'], relief='flat', bd=0, highlightthickness=0,
            cursor='hand2', padx=0, pady=0,
        )
        self.file_menu187 = None
        self.file_button187.pack(side='right')
        attach_tooltip(self.file_button187, 'فایل: ذخیره، تنظیمات و ابزار برنامه', side='below')
        # Save/undo/redo/refresh sit in a frame of their own beside the file
        # menu, so hiding them on شروع moves nothing else in the bar - reported
        # live as "the boxes change between شروع and the project" (operator
        # round 2026-09-28).
        self.shell_tools_host187 = tk.Frame(row1, bg=p['surface'])
        self.command_buttons = []
        for text, command, tip in (
            ('Save', self.manual_save, 'بکاپ دستی'),
            ('Undo', self.undo, 'بازگشت آخرین عملیات'),
            ('Redo', self.redo, 'اجرای دوباره'),
            ('Refresh', self._table_refresh_187, 'بروزرسانی داده‌ها'),
        ):
            button = self._shell_button_187(self.shell_tools_host187, text, command, fs, side='right')
            attach_tooltip(button, tip, side='below')
            self.command_buttons.append(button)

        # A tenth taller than the 67px bar it replaces (operator round 2026-09-30).
        top.configure(height=self._SHELL_BAR_HEIGHT_187, highlightthickness=0, bd=0)
        try:
            top.pack_configure(padx=8, pady=(6, 0))
        except tk.TclError:
            pass
        self._build_window_tabs_187(row2, p)
        self._build_shell_search_187(row1, p)
        self._set_shell_tools_visible_187(True)
        self._shell_bars187 = [top]
        top_height = int(top.cget('height') or 56)
        top_color = p['surface_alt']
        # Room for the clock's two lines (operator round 2026-09-27).
        footer_height = 40
        self.footer187 = tk.Frame(
            self, bg=top_color, height=footer_height,
            highlightbackground=p['border_subtle'], highlightthickness=1,
        )
        self.footer187.pack(side='bottom', fill='x', padx=8, pady=(0, 6),
                            before=self.notebook)
        self._shell_bars187.append(self.footer187)
        self.footer187.pack_propagate(False)

        # D4: a thin status line - when the project was last written, and
        # whether Telegram is connected - with the clock at the far end.
        self.footer_status_host187 = tk.Frame(self.footer187, bg=top_color)
        self.footer_status_host187.pack(side='right', padx=(10, 6))
        self.footer_saved187 = tk.Label(
            self.footer_status_host187, text='', bg=top_color, fg=p['green'],
            font=kit_font('small', widget=self), bd=0,
        )
        self.footer_saved187.pack(side='right')
        self.footer_telegram187 = tk.Label(
            self.footer_status_host187, text='', bg=top_color, fg=p['text_secondary'],
            font=kit_font('small', widget=self), bd=0,
        )
        self.footer_telegram187.pack(side='right', padx=(16, 0))
        self.after(1200, self._refresh_footer_status_187)

        # The language control was removed from the footer; language is set
        # from Settings, which is where every other appearance choice lives.
        self.footer_language_button187 = None

        current_mode = str(load_ui().get('appearance') or 'dark').lower()
        self.footer_mode_button187 = ttk.Menubutton(
            self.footer187, text=self._display_mode_label_187(),
            direction='above', style='Footer.TMenubutton', cursor='hand2',
        )
        self.footer_theme_menu187 = tk.Menu(
            self.footer_mode_button187, tearoff=False,
            bg=p['surface'], fg=p['text'], activebackground=p['blue'],
            activeforeground=p['on_accent'], font=dashboard_font_187(self, max(9, fs), 'control'),
        )
        for label, mode in (('تاریک', 'dark'), ('روشن', 'light'), ('رنگی', 'vivid')):
            self.footer_theme_menu187.add_command(
                label=label, command=lambda m=mode: self._set_display_mode_187(m))
        self.footer_mode_button187.bind('<Button-1>', self._show_footer_mode_menu_187)
        self.footer_mode_button187.pack(side='right', padx=3, pady=1)

        self.footer_theme_button187 = ttk.Menubutton(
            self.footer187, text=self._theme_choice_label_187(), direction='above',
            style='Footer.TMenubutton', cursor='hand2',
        )
        self.footer_themes_menu187 = tk.Menu(
            self.footer_theme_button187, tearoff=False,
            bg=p['surface'], fg=p['text'], activebackground=p['blue'],
            activeforeground=p['on_accent'], font=dashboard_font_187(self, max(9, fs), 'control'),
        )
        for theme_id in (1, 2, 3):
            self.footer_themes_menu187.add_command(
                label=f'تم {fa(theme_id)}', command=lambda value=theme_id: self._set_theme_id_187(value),
            )
        self.footer_theme_button187.bind('<Button-1>', self._show_footer_theme_menu_187)
        self.footer_theme_button187.pack(side='right', padx=3, pady=1)
        self.quick_theme_button = self.footer_mode_button187

        # Operator round 2026-09-27: the messages bell at the footer's left
        # end, its count on its corner, and the clock beside it with the
        # time over the date again; a double click opens the calendar.
        self.bell_host187 = tk.Frame(self.footer187, bg=top_color)
        self.bell_host187.pack(side='left', padx=(8, 2))
        self.messages_button187 = tk.Button(
            self.bell_host187, text='', command=lambda: FinancialMessagesDialog187(self, SERVICE),
            bg=top_color, activebackground=top_color, relief='flat', bd=0,
            highlightthickness=0, cursor='hand2', padx=0, pady=0,
        )
        # Room above and beside the tile for the count.
        self.messages_button187.pack(padx=(6, 0), pady=(4, 0))
        self.messages_text187 = tk.StringVar(value='')
        attach_tooltip(self.messages_button187, 'پیام‌ها و یادآوری‌ها', side='above')
        self.footer_clock_host187 = tk.Frame(self.footer187, bg=top_color)
        self.footer_clock_host187.pack(side='left', padx=(8, 6))
        self.datetime_label_186 = tk.Label(
            self.footer_clock_host187, textvariable=self.datetime_top,
            bg=top_color, fg=p['text_secondary'], bd=0, highlightthickness=0,
            font=kit_font('small', widget=self), anchor='center', justify='center',
        )
        self.datetime_label_186.pack(fill='both', expand=True)
        self.footer_clock_host187.bind('<Double-1>', self._open_project_calendar_187, add='+')
        self.datetime_label_186.bind('<Double-1>', self._open_project_calendar_187, add='+')

        system_tab = getattr(self, 'system_tab186', None)
        if system_tab is not None:
            for widget in v186._walk(system_tab):
                if isinstance(widget, (tk.Button, ttk.Button)):
                    try:
                        if widget.cget('text') == 'بسته توسعه':
                            widget.configure(text='ذخیره بسته توسعه')
                    except tk.TclError:
                        pass
        self._refresh_message_count_187()

    def _refresh_footer_status_187(self):
        """D4's status line: when this project's data was last written, and
        Telegram's state as the data-entry probe last read it. Nothing here
        touches the network or the database; it reads a file time and a
        label the probe already keeps."""
        saved = getattr(self, 'footer_saved187', None)
        try:
            if saved is None or not saved.winfo_exists():
                return
        except tk.TclError:
            return
        p = palette_187()
        text = ''
        try:
            base = Path(DB.db_path)
            # WAL mode: a write lands in the -wal file until a checkpoint.
            written = max(path.stat().st_mtime for path in (base, Path(f'{base}-wal'))
                          if path.exists())
            ago = max(0, int(time.time() - written))
            if ago < 60:
                when = 'لحظاتی پیش'
            elif ago < 3600:
                when = f'{fa(ago // 60)} دقیقه پیش'
            elif ago < 86400:
                when = f'{fa(ago // 3600)} ساعت پیش'
            else:
                when = fa(gregorian_to_shamsi(datetime.fromtimestamp(written).date()))
            text = f'● ذخیره شد، {when}'
        except (OSError, ValueError, AttributeError):
            text = ''
        saved.configure(text=text, fg=p['green'])
        label = getattr(self, 'footer_telegram187', None)
        state = getattr(getattr(self, 'approval_center', None), 'bot', None)
        if label is not None:
            try:
                reading = str(state.get()) if isinstance(state, tk.StringVar) else ''
            except tk.TclError:
                reading = ''
            if 'آنلاین' in reading:
                label.configure(text='تلگرام: متصل', fg=p['text_secondary'])
            elif 'قطع' in reading:
                label.configure(text='تلگرام: قطع', fg=p['red'])
            elif reading:
                label.configure(text='تلگرام: در حال بررسی', fg=p['text_secondary'])
            else:
                label.configure(text='')
        try:
            self.after(20000, self._refresh_footer_status_187)
        except tk.TclError:
            pass

    def _open_project_calendar_187(self, _event=None):
        """Open the shared project calendar and bring it to the foreground."""
        window = getattr(self, '_project_calendar_window187', None)
        if window is not None:
            try:
                if window.winfo_exists():
                    window.deiconify()
                    window.lift()
                    window.focus_force()
                    return window
            except tk.TclError:
                pass
        self._project_calendar_window187 = None
        try:
            window = FinancialCalendarDialog187(self, SERVICE)
            self._project_calendar_window187 = window
            window.bind('<Destroy>', self._clear_project_calendar_window_187, add='+')
            return window
        except Exception:
            logging.getLogger(__name__).exception('Project calendar failed to open')
            try:
                messagebox.showerror(
                    'تقویم پروژه',
                    'تقویم پروژه باز نشد. جزئیات خطا در لاگ ثبت شد.',
                    parent=self,
                )
            except tk.TclError:
                pass
            return None

    def _clear_project_calendar_window_187(self, event):
        """Drop the shared calendar reference after its top-level is destroyed."""
        if event.widget is getattr(self, '_project_calendar_window187', None):
            self._project_calendar_window187 = None

    def _build_approval_center(self):
        tab = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.approval_tab = tab
        self.notebook.insert(1, tab, text='ثبت دیتا')
        def refresh_after_posted_187():
            # Approval commits first, then refreshes every financial view in
            # the same event loop turn so a restart is never needed.
            self.refresh_all()
            try:
                self.after_idle(self.refresh_financial)
            except tk.TclError:
                self.refresh_financial()

        self.approval_center = DataEntryCenter187(
            tab, self.rich, on_posted=refresh_after_posted_187,
        )
        self.approval_center.pack(fill='both', expand=True)
        # The record action above Pending is deliberately redirected to the
        # dedicated sales record, never to the data-entry/manual transaction UI.
        self.approval_center.open_selected_record_187 = self.open_selected_record_187
        if self._bot_process:
            self.approval_center.set_bot_process(self._bot_process, self._bot_log)
        self.after_idle(self._rebuild_navbar)

    def _build_sales(self):
        """Use one versioned sales workspace over the existing ledger."""
        root = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.notebook.add(root, text=SALES_TAB_187)
        self.sales_root = root
        self.sales_claims187 = SalesClaimsPanel187(
            root, db=DB, base_dir=BASE_DIR, on_changed=self.refresh_all,
        )
        self.sales_claims187.pack(fill='both', expand=True)
        self.sales_nb = self.sales_claims187.nb
        self.sales_table = self.sales_claims187.contract_tree

    def open_selected_record_187(self, sale_id: str = '', draft=None, document_path: str = ''):
        """Dashboard-level bridge used by the Pending record action and the sales wizard."""
        panel = getattr(self, 'sales_claims187', None)
        if panel is None:
            return None
        return panel.open_sales_record(sale_id=sale_id, draft=draft, document_path=document_path)

    def open_sales_wizard_187(self):
        """Record creation always starts in the dedicated sales-contract wizard."""
        panel = getattr(self, 'sales_claims187', None)
        if panel is None:
            return None
        return panel.open_wizard()

    def refresh_sales(self):
        panel = getattr(self, 'sales_claims187', None)
        if panel is not None:
            panel.refresh()

    def _build_settings(self):
        self.settings_window187 = None
        self.settings_tab187 = None
        self.settings_tab186 = None
        self.settings_tab185 = None

    def open_settings_187(self):
        window = getattr(self, 'settings_window187', None)
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            window.focus_force()
            return window
        # Section 10: the shell supplies the themed title bar, all three window
        # controls, the centring, the size class and the scrolling.
        # Sized to hold the whole form, so no scrolling is needed.
        window = BarkavWindow(
            self, 'تنظیمات', subtitle=f'BARKAV {DISPLAY_VERSION_187}',
            size_class='small', scrollable=True, show_footer=True,
        )
        self.settings_window187 = window
        tab = SettingsTab187(window.body, self._settings_saved)
        self.settings_tab187 = tab
        self.settings_tab186 = tab
        self.settings_tab185 = tab
        tab.pack(fill='x', expand=True)
        window.after_idle(lambda: tab.refresh_rates_187(silent=True))
        window.add_action('ذخیره تنظیمات', tab.save, style='Success.TButton')
        window.add_action('انصراف', window.close)
        window.protocol('WM_DELETE_WINDOW', lambda: (window.destroy(), setattr(self, 'settings_window187', None)))
        window.after_idle(window.focus_force)
        return window

    def _build_reports(self):
        super()._build_reports()
        self._barkav_service_187 = SERVICE
        self._barkav_base_187 = BASE_DIR
        self._barkav_apply_phase04_187 = v186.v18.apply_phase04_rules_v18
        install_report_controls_187(self)
        inventory_tab = ttk.Frame(self.report_nb, padding=5)
        self.report_nb.add(inventory_tab, text='مدیریت انبار')
        self.inventory_panel187 = InventoryPanel187(inventory_tab, self)
        self.inventory_panel187.pack(fill='both', expand=True)

    def open_phase_by_no(self, number: int):
        row = next(
            (item for item in self._phase_summary_live() if item['phase_no'] == int(number)),
            None,
        )
        if row:
            PhaseDetailDialog187(
                self, self.rich, int(number), row['phase'], self.refresh_all
            )

    def _settings_saved(self, old, new):
        changed = {key for key in (
            'appearance', 'font_family', 'font_weight', 'font_size', 'row_height', 'theme_id',
            'language', 'background_color', 'updated_rate_basis_187', 'button_display',
            'ai_engine_mode', 'ai_confidence_threshold',
        ) if old.get(key) != new.get(key)}
        ai_restart = bool(changed & {'ai_engine_mode', 'ai_confidence_threshold'})
        live = changed & {'font_family', 'font_weight', 'font_size', 'row_height', 'language',
                          'button_display'}
        visual = bool(changed & {'appearance', 'theme_id', 'background_color'})
        self.ui = load_ui()
        if live:
            self._apply_settings_live_187(old, new)
        if visual or ai_restart:
            window = getattr(self, 'settings_window187', None)
            if window is not None and window.winfo_exists():
                window.destroy()
                self.settings_window187 = None
            notice = ('تنظیمات ذخیره شد؛ برنامه و سرویس‌های پروژه برای اعمال آن بازآفرینی می‌شوند.'
                      if ai_restart else 'تنظیمات پوسته ذخیره شد؛ رابط کاربری بازآفرینی می‌شود.')
            messagebox.showinfo('تنظیمات', notice, parent=self)
            self._restart_requested = True
            self.after(100, self.destroy)
        else:
            window = getattr(self, 'settings_window187', None)
            if window is not None and window.winfo_exists():
                window.destroy()
            self.settings_window187 = None
            if not live:
                self.refresh_all()
            show_toast(self, 'تنظیمات ذخیره و اعمال شد.')

    # Section 11 rail (operator-approved R1, R3-R7): grouped items with
    # headings, a rounded active pill, hover, monochrome line icons,
    # Ctrl+1..9 shortcuts with hover hints, a collapsible icons-only mode
    # that is remembered, and the project/theme/settings block at the foot.
    # One list, no روزانه/پروژه headings (operator round 2026-09-27).
    NAV_GROUPS_187 = (
        ('', ('داشبورد', 'ثبت دیتا', 'تراکنش‌ها', 'حساب مدیر',
              SALES_TAB_187, 'پیمانکاران', REPORTS_TAB_187)),
    )
    NAV_ICONS_187 = {
        'داشبورد': 'dashboard', 'ثبت دیتا': 'data', 'تراکنش‌ها': 'transactions',
        'حساب مدیر': 'account', SALES_TAB_187: 'income', 'پیمانکاران': 'contractors',
        REPORTS_TAB_187: 'project',
    }

    def _remember_navbar_pack_187(self):
        navbar = getattr(self, 'navbar', None)
        if navbar is None:
            return
        try:
            if navbar.winfo_manager() == 'pack':
                self._navbar_pack_options187 = dict(navbar.pack_info())
        except tk.TclError:
            return

    def _restore_navbar_pack_187(self) -> bool:
        navbar = getattr(self, 'navbar', None)
        if navbar is None:
            return False
        try:
            if navbar.winfo_manager() == 'pack':
                return True
            if theme_id_187() != 1:
                navbar.pack(side='right', fill='y', padx=(0, 8), pady=(6, 7),
                            before=self.notebook)
                return navbar.winfo_manager() == 'pack'
            options = getattr(self, '_navbar_pack_options187', None)
            if not options:
                return False
            navbar.pack(**options)
            return navbar.winfo_manager() == 'pack'
        except tk.TclError:
            return False

    def _rebuild_navbar(self):
        if not getattr(self, 'navbar', None):
            return
        if getattr(self, '_window_view187', 'project') == 'start':
            # Keep callbacks from hidden inherited tabs from bringing the
            # project navigation back over the Start view.
            return

        p = palette_187()
        current_theme = theme_id_187()
        tabs = {self.notebook.tab(tab_id, 'text'): tab_id for tab_id in self.notebook.tabs()}
        if current_theme != 1:
            if 'حساب مدیر' not in tabs and 'حساب مدیر پروژه' in tabs:
                self.notebook.tab(tabs['حساب مدیر پروژه'], text='حساب مدیر')
                tabs['حساب مدیر'] = tabs['حساب مدیر پروژه']
            if REPORTS_TAB_187 not in tabs and 'گزارش‌گیری' in tabs:
                self.notebook.tab(tabs['گزارش‌گیری'], text=REPORTS_TAB_187)
                tabs[REPORTS_TAB_187] = tabs['گزارش‌گیری']

        target_state = tuple(
            (label, tabs[label]) for label in self._VISIBLE_NAV if label in tabs
        )
        color_state = tuple(
            p.get(key) for key in (
                'nav', 'nav_active', 'nav_indicator', 'accent', 'text_secondary',
            )
        )
        font_state = tuple(load_ui().get(key) for key in ('font_family', 'font_size', 'font_weight'))
        signature = (
            current_theme, color_state, font_state,
            tuple((label, str(target)) for label, target in target_state),
        )
        nav_buttons = getattr(self, 'nav_buttons', {})
        if (
            signature == getattr(self, '_nav_build_signature187', None)
            and len(nav_buttons) == len(target_state)
        ):
            if self._restore_navbar_pack_187():
                self._sync_nav()
                return

        # The rebuilt controls use fresh theme colours; force one selected
        # state paint after construction.
        self._active_nav_target187 = None
        if current_theme == 1:
            self._nav_rail187 = None
            self._nav_tiles187 = {}
            self._nav_tile_images187 = {}
            self._nav_images187 = {}
            result = super()._rebuild_navbar()
            self._nav_build_signature187 = signature
            self._remember_navbar_pack_187()
            return result

        for child in self.navbar.winfo_children():
            child.destroy()
        self.nav_buttons = {}
        ui = load_ui()
        if 'nav_collapsed' in ui:
            collapsed = bool(ui.get('nav_collapsed'))
        else:
            # Until the operator chooses, a narrow screen starts with the
            # icons-only rail so toolbars keep the width they had before.
            collapsed = self.winfo_screenwidth() < 1440
        # The inherited shell packs the navbar as a horizontal strip across the
        # top. The reference design uses a right-side rail for other themes.
        self.navbar.pack_forget()
        self.navbar.configure(
            width=NavRail.COLLAPSED_WIDTH if collapsed else NavRail.EXPANDED_WIDTH, bg=p['nav'])
        self.navbar.pack(side='right', fill='y', padx=(0, 8), pady=(6, 7),
                         before=self.notebook)
        self.navbar.pack_propagate(False)
        tabs = {self.notebook.tab(tab_id, 'text'): tab_id for tab_id in self.notebook.tabs()}
        if 'حساب مدیر' not in tabs and 'حساب مدیر پروژه' in tabs:
            self.notebook.tab(tabs['حساب مدیر پروژه'], text='حساب مدیر')
            tabs['حساب مدیر'] = tabs['حساب مدیر پروژه']
        if REPORTS_TAB_187 not in tabs and 'گزارش‌گیری' in tabs:
            self.notebook.tab(tabs['گزارش‌گیری'], text=REPORTS_TAB_187)
            tabs[REPORTS_TAB_187] = tabs['گزارش‌گیری']

        visible = [label for label in self._VISIBLE_NAV if tabs.get(label)]
        grouped = [(heading, [label for label in labels if label in visible])
                   for heading, labels in self.NAV_GROUPS_187]
        leftovers = [label for label in visible
                     if not any(label in labels for _heading, labels in grouped)]
        if leftovers and grouped:
            grouped[-1][1].extend(leftovers)
        groups, shortcuts = [], {}
        for heading, labels in grouped:
            entries = []
            for label in labels:
                target = tabs[label]
                number = len(shortcuts) + 1
                if number <= 9:
                    shortcuts[number] = target
                entries.append((
                    target, label, self.NAV_ICONS_187.get(label, 'page'),
                    lambda tab_id=target: self.notebook.select(tab_id),
                    f'Ctrl+{number}' if number <= 9 else '',
                ))
            if entries:
                groups.append((heading, entries))
        footer = (
            ('project', self._rail_project_label_187(), 'folder', self._show_start_view_187,
             'استارت و انتخاب پروژه'),
            ('theme', 'تم و حالت نمایش', 'theme', self._post_rail_theme_menu_187, '',
             {'chevron': True, 'on_hover': self._rail_theme_hover_187}),
            ('settings', 'تنظیمات', 'settings', self.open_settings_187, ''),
            ('collapse', 'جمع کردن نوار', 'collapse', self._toggle_nav_rail_187, ''),
        )
        self._nav_rail187 = NavRail(
            self.navbar, groups=groups, footer=footer, collapsed=collapsed,
            on_collapse=self._remember_nav_collapsed_187, widget_for_font=self,
        )
        for key, item in self._nav_rail187.items.items():
            self.nav_buttons[key] = item.canvas
        self._nav_shortcuts187 = shortcuts
        self._bind_shell_keys_187()
        self._move_theme_controls_to_rail_187()
        self.after_idle(self._move_theme_controls_to_rail_187)
        self._place_breadcrumb_187()
        self._sync_nav()

    def _sync_nav(self):
        """Paint the active rail item."""
        rail = getattr(self, '_nav_rail187', None)
        if rail is None or not rail.alive():
            return super()._sync_nav()
        try:
            selected = str(self.notebook.select())
        except tk.TclError:
            return
        rail.set_active(selected)

    def _rail_project_label_187(self) -> str:
        return str(getattr(self, '_barkav_project_name187', None) or 'پروژه')

    def _toggle_nav_rail_187(self):
        rail = getattr(self, '_nav_rail187', None)
        if rail is not None and rail.alive():
            rail.toggle()

    def _remember_nav_collapsed_187(self, collapsed: bool):
        try:
            ui = load_ui()
            ui['nav_collapsed'] = bool(collapsed)
            save_ui(ui)
            self.ui = ui
        except Exception:
            pass

    def _move_theme_controls_to_rail_187(self):
        """The display-mode and theme pickers live at the foot of the rail
        now (R7); the footer copies stay built for the code that updates
        their text, but are no longer shown."""
        if getattr(self, '_nav_rail187', None) is None:
            return
        for name in ('footer_mode_button187', 'footer_theme_button187'):
            widget = getattr(self, name, None)
            try:
                if widget is not None and widget.winfo_manager():
                    widget.pack_forget()
            except tk.TclError:
                pass

    def _display_mode_187(self) -> str:
        settings = load_ui()
        if str(settings.get('appearance') or 'dark').lower() == 'light':
            return 'light'
        if int(settings.get('theme_id') or DEFAULT_THEME_ID_187) == 3:
            return 'vivid'
        return 'dark'

    def _theme_menu_sections_187(self):
        mode = self._display_mode_187()
        current = theme_id_187()
        return [
            ('حالت نمایش', [
                {'label': label, 'icon': icon, 'checked': mode == key,
                 'command': lambda m=key: self._set_display_mode_187(m)}
                for label, key, icon in (('تاریک', 'dark', 'theme'), ('روشن', 'light', 'theme'),
                                         ('رنگی', 'vivid', 'theme'))
            ]),
            ('تم', [
                {'label': f'تم {fa(value)}', 'checked': current == value,
                 'command': lambda v=value: self._set_theme_id_187(v)}
                for value in (1, 2, 3)
            ]),
        ]

    def _post_rail_theme_menu_187(self):
        """The theme flyout beside the rail: compact rows (operator round
        2026-09-27), and gone again once the pointer leaves it."""
        self._cancel_rail_theme_job_187()
        rail = getattr(self, '_nav_rail187', None)
        item = rail.footer_items.get('theme') if rail is not None else None
        if item is None:
            return
        PopupMenu(item.canvas, self._theme_menu_sections_187(), side='left', min_width=170,
                  compact=True, hover_close=True)

    def _cancel_rail_theme_job_187(self):
        job, self._rail_theme_job187 = getattr(self, '_rail_theme_job187', None), None
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass

    def _rail_theme_hover_187(self, item, inside: bool):
        """Pointing at «تم و حالت نمایش» opens its flyout after a moment;
        leaving it closes the flyout unless the pointer went into it."""
        self._cancel_rail_theme_job_187()
        current = PopupMenu._current
        showing = current is not None and getattr(current, '_anchor', None) is item.canvas
        try:
            if inside and not showing:
                self._rail_theme_job187 = self.after(220, self._post_rail_theme_menu_187)
            elif not inside and showing:
                self._rail_theme_job187 = self.after(320, current.close_if_away)
        except tk.TclError:
            pass

    # ---- N8: the dashboard's five cards lead with one number ------------
    # Each summary card's first figure becomes its headline: a small label
    # over a large number. Where the card itself holds a meaningful pair of
    # figures, a thin bar under the headline shows that ratio - computed
    # from the card's own values, never from invented history.
    _KPI_HEROES_187 = ('total_in', 'ch_all_total', 'loan_principal', 'sales_contract', 'liq_obligation')
    # A part key that starts with «~» is what is left of the whole once that card is taken off it.
    _KPI_RATIOS_187 = {
        'total_in': ('total_out', 'total_in', 'خروجی نسبت به ورودی'),
        'ch_all_total': ('~ch_open_total', 'ch_all_total', 'چک‌های پاس‌شده نسبت به کل چک‌ها'),
        'loan_principal': ('loan_paid', 'loan_principal', 'اقساط پرداخت‌شده'),
        'sales_contract': ('sales_received', 'sales_contract', 'وصول‌شده از فروش'),
    }

    def _install_kpi_cards_187(self):
        cards = getattr(self, 'cards', None)
        if not cards:
            return
        p = palette_187()
        family = kit_font('body', widget=self)[0]
        base = max(9, min(12, int(load_ui().get('font_size') or 10)))
        # Every metric row stacks its number under its own title now. Title
        # and value used to share one row - title on the right with
        # fill+expand, value on the left in whatever was left - and a
        # longer caption's own requested width could leave no room for the
        # value beside it at all: the number read as lost under the text,
        # reported live on cards beyond the five KPI heroes below (operator
        # round 2026-09-28).
        for metric in cards.values():
            if getattr(metric, '_kpi187', False) or getattr(metric, '_stacked187', False):
                continue
            try:
                metric.title_label.pack_forget()
                metric.value_label.pack_forget()
                metric.title_label.pack(side='top', fill='x', anchor='e', padx=8, pady=(4, 0))
                metric.value_label.configure(anchor='e')
                metric.value_label.pack(side='top', fill='x', anchor='e', padx=8, pady=(0, 4))
            except (tk.TclError, AttributeError):
                continue
            metric._stacked187 = True
        for key in self._KPI_HEROES_187:
            metric = cards.get(key)
            if metric is None or getattr(metric, '_kpi187', False):
                continue
            try:
                background = str(metric.cget('bg'))
                metric.title_label.pack_forget()
                metric.value_label.pack_forget()
                metric.title_label.pack(side='top', anchor='e', padx=8, pady=(4, 0))
                metric.value_label.configure(font=(family, base + 5, 'bold'), anchor='e',
                                             fg=p['text_primary'])
                metric.value_label._barkav_keep_font187 = True
                metric.value_label.pack(side='top', anchor='e', padx=8, pady=0)
            except (tk.TclError, AttributeError):
                continue
            metric._kpi187 = True
            ratio = self._KPI_RATIOS_187.get(key)
            if ratio is None:
                continue
            canvas = tk.Canvas(metric, height=14, bg=background, bd=0, highlightthickness=0)
            canvas.pack(side='top', fill='x', padx=10, pady=(1, 0))
            caption = tk.Label(metric, bg=background, fg=p['text_secondary'],
                               font=kit_font('small', widget=self), anchor='e')
            caption.pack(side='top', anchor='e', padx=8, pady=(0, 3))
            metric._kpi_bar187 = (canvas, caption, ratio)
            for source in ratio[:2]:
                other = cards.get(source.lstrip('~'))
                if other is not None:
                    other.var.trace_add('write', lambda *_a, m=metric: self._draw_kpi_bar_187(m))
            canvas.bind('<Configure>', lambda _e, m=metric: self._draw_kpi_bar_187(m), add='+')
            self._draw_kpi_bar_187(metric)

    def _draw_kpi_bar_187(self, metric):
        canvas, caption, (part_key, whole_key, text) = metric._kpi_bar187
        cards = self.cards
        rest = part_key.startswith('~')
        part_key = part_key.lstrip('~')
        part = v186.parse_display_amount_186(cards[part_key].var.get()) if part_key in cards else None
        whole = v186.parse_display_amount_186(cards[whole_key].var.get()) if whole_key in cards else None
        if rest and part is not None and whole is not None:
            part = max(0.0, whole - part)
        p = palette_187()
        try:
            canvas.delete('all')
            width = canvas.winfo_width()
            if not whole or part is None or whole <= 0 or width < 20:
                caption.configure(text='')
                return
            raw = float(part) / float(whole)
            share = max(0.0, min(1.0, raw))
            # Operator round 2026-09-27: taller, and filled as a row of small
            # blocks - one block per 5% - from the right, where the text
            # starts; a share under one block still lights the first.
            x0, x1, top, bottom = 4, width - 4, 2, 12
            count, gap = 20, 2
            size = (x1 - x0 - gap * (count - 1)) / count
            lit = min(count, max(1 if share > 0 else 0, round(share * count)))
            # `surface_alt` is the same tone as the alternating metric rows
            # themselves (both come from the theme's `panel2`), so an unlit
            # block painted in it vanished against its own row - reported
            # live as "the fill box isn't shown" on the two ratios that sit
            # on an alternating row and are mostly unlit (operator round
            # 2026-09-28). Blending the row's own colour with the text
            # colour keeps a visible track under any background.
            track = mix(str(canvas.cget('bg')), p['text_primary'], 0.14)
            for index in range(count):
                right = x1 - index * (size + gap)
                canvas.create_rectangle(right - size, top, right, bottom, width=0,
                                        fill=p['accent'] if index < lit else track)
            caption.configure(text=f'{fa(round(raw * 100))}٪ {text}')
        except (tk.TclError, ValueError, ZeroDivisionError):
            return

    # ---- N9: where am I ------------------------------------------------
    def _install_breadcrumb_187(self):
        """A slim bar above the page: the path through the tabs, and the
        page's own name in bold (operator-approved N9)."""
        if getattr(self, 'crumb_bar187', None) is not None:
            return
        p = palette_187()
        bar = tk.Frame(self, bg=p['bg'], height=28, bd=0, highlightthickness=0)
        bar.pack_propagate(False)
        self.crumb_path187 = tk.Label(bar, bg=p['bg'], fg=p['text_secondary'],
                                      font=kit_font('small', widget=self), anchor='e')
        self.crumb_title187 = tk.Label(bar, bg=p['bg'], fg=p['text_primary'],
                                       font=kit_font('body', widget=self, bold=True), anchor='e')
        self.crumb_path187.pack(side='right', padx=(0, 4))
        self.crumb_title187.pack(side='right')
        self.crumb_bar187 = bar
        self.bind_all('<<NotebookTabChanged>>', self._on_any_tab_changed_187, add='+')
        self._place_breadcrumb_187()
        self.after_idle(self._update_breadcrumb_187)

    def _place_breadcrumb_187(self):
        bar = getattr(self, 'crumb_bar187', None)
        if bar is None or getattr(self, '_window_view187', 'project') == 'start':
            return
        try:
            if not self.notebook.winfo_manager():
                return
            # Always directly before the notebook, after the rail, so it sits
            # over the page and never over the rail.
            bar.pack_forget()
            bar.pack(side='top', fill='x', padx=(14, 8), pady=(4, 0), before=self.notebook)
        except tk.TclError:
            pass

    def _on_any_tab_changed_187(self, event):
        try:
            if event.widget.winfo_toplevel() is not self:
                return
        except (tk.TclError, AttributeError):
            return
        job = getattr(self, '_crumb_job187', None)
        if job is None:
            try:
                self._crumb_job187 = self.after_idle(self._update_breadcrumb_187)
            except tk.TclError:
                self._crumb_job187 = None

    @staticmethod
    def _first_notebook_in_187(page):
        queue = [page]
        while queue:
            widget = queue.pop(0)
            try:
                children = widget.winfo_children()
            except tk.TclError:
                continue
            for child in children:
                try:
                    # Only what is actually in the layout; a page drawn a
                    # moment from now is not mapped yet, but it is managed.
                    if not child.winfo_manager():
                        continue
                except tk.TclError:
                    continue
                if isinstance(child, ttk.Notebook):
                    try:
                        if child.tabs():
                            return child
                    except tk.TclError:
                        pass
                    continue
                queue.append(child)
        return None

    def _breadcrumb_parts_187(self) -> list[str]:
        parts, notebook = [], self.notebook
        for _depth in range(6):
            if notebook is None:
                break
            try:
                current = notebook.select()
                if not current:
                    break
                parts.append(str(notebook.tab(current, 'text') or '').strip())
                page = notebook.nametowidget(current)
            except (tk.TclError, KeyError):
                break
            notebook = self._first_notebook_in_187(page)
        return [part for part in parts if part]

    def _update_breadcrumb_187(self):
        self._crumb_job187 = None
        bar = getattr(self, 'crumb_bar187', None)
        if bar is None:
            return
        parts = self._breadcrumb_parts_187()
        try:
            if not parts:
                self.crumb_path187.configure(text='')
                self.crumb_title187.configure(text='')
                return
            path = ' › '.join(parts[:-1])
            self.crumb_path187.configure(text=f'{path} ›' if path else '')
            self.crumb_title187.configure(text=parts[-1])
        except tk.TclError:
            pass

    # ---- N10: Ctrl+K ----------------------------------------------------
    def _reveal_tab_187(self, notebook, tab_id):
        """Select ``tab_id`` in ``notebook`` and every page above it."""
        if getattr(self, '_window_view187', 'project') == 'start':
            self._show_project_view_187()
        chain, child, parent = [], notebook, notebook.master
        while parent is not None:
            if isinstance(parent, ttk.Notebook):
                chain.append((parent, child))
            child, parent = parent, getattr(parent, 'master', None)
        for ancestor, inner in reversed(chain):
            for tid in ancestor.tabs():
                page = str(ancestor.nametowidget(tid))
                if str(inner) == page or str(inner).startswith(page + '.'):
                    try:
                        ancestor.select(tid)
                    except tk.TclError:
                        pass
                    break
        try:
            notebook.select(tab_id)
        except tk.TclError:
            pass

    def _palette_entries_187(self) -> list[tuple]:
        entries, seen = [], set()
        groups = {label: heading for heading, labels in self.NAV_GROUPS_187 for label in labels}

        def add(title, subtitle, group, icon, callback):
            key = (group, title, subtitle)
            if title and key not in seen:
                seen.add(key)
                entries.append((title, subtitle, group, icon, callback))

        main_tabs = list(self.notebook.tabs())
        for tab_id in main_tabs:
            text = str(self.notebook.tab(tab_id, 'text') or '').strip()
            add(text, groups.get(text, 'تب اصلی'), 'تب‌ها', self.NAV_ICONS_187.get(text, 'page'),
                lambda t=tab_id: self._reveal_tab_187(self.notebook, t))
        for tab_id in main_tabs:
            main_text = str(self.notebook.tab(tab_id, 'text') or '').strip()
            try:
                page = self.notebook.nametowidget(tab_id)
            except (tk.TclError, KeyError):
                continue
            for widget in self._walk_in_order_187(page):
                if not isinstance(widget, ttk.Notebook) or not self._reachable_187(widget):
                    continue
                for sub_id in widget.tabs():
                    text = str(widget.tab(sub_id, 'text') or '').strip()
                    add(text, main_text, 'زیرتب‌ها', self.NAV_ICONS_187.get(main_text, 'page'),
                        lambda nb=widget, t=sub_id: self._reveal_tab_187(nb, t))
        shell = (
            ('ذخیره پروژه', '', 'folder', self.manual_save),
            ('بروزرسانی همه داده‌ها', '', 'play', self.refresh_all),
            ('تنظیمات', '', 'settings', self.open_settings_187),
            ('استارت و انتخاب پروژه', '', 'folder', self._show_start_view_187),
            ('جمع یا باز کردن نوار کناری', '', 'collapse', self._toggle_nav_rail_187),
        )
        for title, subtitle, icon, callback in shell:
            add(title, subtitle, 'کارها', icon, callback)
        try:
            page = self.notebook.nametowidget(self.notebook.select())
        except (tk.TclError, KeyError):
            page = None
        if page is not None:
            for widget in self._walk_187(page):
                if not isinstance(widget, (ttk.Button, tk.Button)):
                    continue
                try:
                    text = str(widget.cget('text') or '').strip()
                    if not widget.winfo_ismapped() or str(widget.cget('state')) == 'disabled':
                        continue
                except tk.TclError:
                    continue
                if len(text) < 2 or text.replace(' ', '').isdigit() or len(entries) > 160:
                    continue
                icon = next((name for word, name in self._ACTION_ICONS_187 if word in text), 'play')
                add(text, 'در همین صفحه', 'کارهای این صفحه', icon, widget.invoke)
        return entries

    @staticmethod
    def _walk_in_order_187(root):
        """Every widget under root in creation order (breadth first)."""
        queue = [root]
        while queue:
            widget = queue.pop(0)
            yield widget
            try:
                queue.extend(widget.winfo_children())
            except tk.TclError:
                pass

    def _reachable_187(self, widget) -> bool:
        """True when nothing between ``widget`` and the main notebook was
        taken out of its layout - a legacy tab strip that a later stage
        replaced and forgot is not somewhere the palette should send you."""
        node = widget
        while node is not None and node is not self.notebook:
            try:
                if not node.winfo_manager():
                    return False
            except tk.TclError:
                return False
            node = getattr(node, 'master', None)
        return node is self.notebook

    def open_command_palette_187(self):
        existing = getattr(self, 'command_palette187', None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.lift()
                existing.entry.focus_force()
                return
        except tk.TclError:
            pass
        self.command_palette187 = CommandPalette(
            self, self._palette_entries_187(),
            placeholder='نام تب، زیرتب یا کاری را بنویسید؛ Enter برای رفتن، Esc برای بستن',
        )
        if not getattr(self, '_palette_click_bound187', False):
            self._palette_click_bound187 = True
            self.bind('<ButtonPress>', self._close_palette_on_click_187, add='+')

    def _close_palette_on_click_187(self, _event=None):
        palette_window = getattr(self, 'command_palette187', None)
        try:
            if palette_window is not None and palette_window.winfo_exists():
                palette_window.close()
        except tk.TclError:
            pass

    def _bind_shell_keys_187(self):
        """Ctrl+1..9 select rail items and Ctrl+K opens the command palette.

        One Control-KeyPress handler on the main window reads the keysym and,
        on Windows, the virtual-key code too - with a Persian keyboard layout
        the digits and K do not always arrive as Latin keysyms.
        """
        if getattr(self, '_shell_keys_bound187', False):
            return
        self._shell_keys_bound187 = True
        self.bind('<Control-KeyPress>', self._on_shell_key_187, add='+')

    def _on_shell_key_187(self, event):
        keysym = str(getattr(event, 'keysym', '') or '')
        try:
            keycode = int(getattr(event, 'keycode', 0) or 0)
        except (TypeError, ValueError):
            keycode = 0
        number = None
        if len(keysym) == 1 and keysym.isdigit():
            number = int(keysym)
        elif keysym.startswith('KP_') and keysym[3:].isdigit():
            number = int(keysym[3:])
        elif sys.platform == 'win32' and 49 <= keycode <= 57:
            number = keycode - 48
        if number:
            target = getattr(self, '_nav_shortcuts187', {}).get(number)
            if target is None or getattr(self, '_window_view187', 'project') == 'start':
                return None
            try:
                self.notebook.select(target)
            except tk.TclError:
                return None
            return 'break'
        if keysym.lower() == 'k' or (sys.platform == 'win32' and keycode == 75):
            opener = getattr(self, 'open_command_palette_187', None)
            if opener is not None:
                opener()
                return 'break'
        return None

    def _decorate_top_187(self):
        """D1: the bar's commands wear the rail's line icons on rounded tiles -
        muted at rest, the accent under the pointer - and فایل is a bare
        three-bar mark on a tile of its own, with no word.

        Repeated late as well as at build time: the inherited finalisers
        re-label these buttons after 18.7 first decorates them.
        """
        p = palette_187()
        for name, button in zip(('save', 'undo', 'redo', 'refresh'), getattr(self, 'command_buttons', [])):
            self._bar_icon_187(button, name, p)
        file_button = getattr(self, 'file_button187', None)
        if file_button is not None and file_button.winfo_exists():
            self._file_button_look_187(file_button, p)
        messages_button = getattr(self, 'messages_button187', None)
        if messages_button is not None and messages_button.winfo_exists():
            # At the footer's left end on a glassy tile (operator round
            # 2026-09-27), like the rail's items.
            ground = str(messages_button.master.cget('bg'))
            tile = glass_tile_187('bell', size=22, colour=p['accent'], ink=p['on_accent'],
                                  background=ground, shadow=p['shadow'], master=self)
            messages_button.configure(image=tile, text='', bg=ground, activebackground=ground,
                                      relief='flat', bd=0, highlightthickness=0, cursor='hand2',
                                      padx=0, pady=0)
            messages_button.image = tile

    def _file_button_look_187(self, button, p):
        """فایل as a bare three-bar mark (operator round 2026-09-30: no word,
        only a clear three-line sign). It sits on the one accent-tinted tile
        in the bar, so it reads as the menu the tools beside it hang off."""
        ground = p['surface']
        shape = dict(size=self._SHELL_ICON_187, box=self._SHELL_TILE_187, ground=ground,
                     radius=9, weight=1.25, master=self)
        rest = line_tile_187('hamburger', colour=p['text_primary'],
                             fill=mix(ground, p['accent'], 0.22), **shape)
        lit = line_tile_187('hamburger', colour=p['text_primary'],
                            fill=mix(ground, p['accent'], 0.38), **shape)
        if rest is None or lit is None:
            return
        # The plate is in the image, so the button's own colour never changes.
        button._barkav_bar_icons187 = (rest, lit, ground, ground)
        try:
            button.configure(
                image=rest, text='', compound='none',
                bg=ground, activebackground=ground, fg=p['text_primary'],
                activeforeground=p['text_primary'], relief='flat', bd=0,
                highlightthickness=0, cursor='hand2', padx=0, pady=0,
            )
        except tk.TclError:
            return
        self._bind_bar_hover_187(button)

    def _bar_icon_187(self, button, name, p):
        """One command as a line icon on a tile: a faint plate at rest, a
        stronger one and the accent under the pointer. Larger than the 18px
        bare icons the bar had before (operator round 2026-09-30)."""
        ground = p['surface']
        shape = dict(size=self._SHELL_ICON_187, box=self._SHELL_TILE_187, ground=ground,
                     radius=9, weight=1.1, master=self)
        rest = line_tile_187(name, colour=mix(p['text_secondary'], p['text_primary'], 0.45),
                             fill=mix(ground, p['text_primary'], 0.05), **shape)
        lit = line_tile_187(name, colour=p['accent'],
                            fill=mix(ground, p['text_primary'], 0.13), **shape)
        if rest is None or lit is None:
            return
        button._barkav_bar_icons187 = (rest, lit, ground, ground)
        try:
            button.configure(
                image=rest, text='', compound='none',
                bg=ground, activebackground=ground, fg=p['text_primary'],
                activeforeground=p['text_primary'], relief='flat', bd=0,
                highlightthickness=0, cursor='hand2', padx=0, pady=0,
            )
        except tk.TclError:
            return
        self._bind_bar_hover_187(button)

    def _bind_bar_hover_187(self, button) -> None:
        if not getattr(button, '_barkav_bar_hover187', False):
            button._barkav_bar_hover187 = True
            button.bind('<Enter>', lambda _e, b=button: self._bar_hover_187(b, True), add='+')
            button.bind('<Leave>', lambda _e, b=button: self._bar_hover_187(b, False), add='+')

    @staticmethod
    def _bar_hover_187(button, on: bool) -> None:
        rest, lit, ground, hover = getattr(button, '_barkav_bar_icons187', (None,) * 4)
        if rest is None:
            return
        try:
            button.configure(image=lit if on else rest, bg=hover if on else ground)
        except tk.TclError:
            pass

    def _decorate_top_187_legacy(self):
        icons = ('💾', '↶', '↷', '⟳', '⚙', '⧉', '◉')
        for icon, button in zip(icons, getattr(self, 'command_buttons', [])):
            try:
                button.configure(text=f'{icon}  {button.cget("text")}')
            except Exception:
                pass
        tools = getattr(self, 'datetime_label_186', None)
        if tools is None or getattr(self, 'messages_button187', None):
            return
        p = palette_187()
        self.messages_text187 = tk.StringVar(value='پیام‌ها')
        self.messages_button187 = tk.Button(
            tools.master, textvariable=self.messages_text187,
            command=self._open_messages_187,
            bg=p['glass'], fg=p['text'], activebackground=p['panel2'],
            relief='flat', highlightbackground=p['line'], highlightthickness=1,
            font=('Segoe MDL2 Assets', 12), padx=9, pady=5, cursor='hand2',
        )
        # Packed after the clock/theme controls: visually left of the clock in RTL header.
        self.messages_button187.pack(side='right', padx=3)
        self._refresh_message_count_187()

    def _install_chart_details_187(self):
        try:
            apply_donut_theme_187(self.cost_donut)
            apply_progress_theme_187(self.overall_progress)
            apply_line_theme_187(self.liquidity_chart)
            apply_bar_theme_187(self.phase_chart)
        except Exception:
            pass
        bindings = (
            (getattr(self, 'cost_donut', None), 'donut'),
            (getattr(self, 'liquidity_chart', None), 'line'),
            (getattr(self, 'phase_chart', None), 'bar'),
        )
        for widget, kind in bindings:
            if widget is not None:
                widget.configure(cursor='hand2')
                widget.bind('<Double-1>', lambda _event, value=kind: ChartDetailDialog187(self, value), add='+')

    def _install_dashboard_links_187(self):
        mapping = {
            'تراکنش‌ها': 'تراکنش‌ها', 'چک‌ها': 'چک‌ها',
            'تسهیلات': REPORTS_TAB_187, 'فروش و مطالبات': SALES_TAB_187,
            '۳۰ روز آینده': '__calendar__',
        }
        sections = {}
        key_group = {
            'total_in': 'تراکنش‌ها', 'ch_all_total': 'چک‌ها',
            'loan_principal': 'تسهیلات', 'sales_contract': 'فروش و مطالبات',
            'liq_obligation': '۳۰ روز آینده',
        }
        for key, title in key_group.items():
            metric = getattr(self, 'cards', {}).get(key)
            if metric is not None:
                try:
                    sections[title] = metric.master.master
                except Exception:
                    pass
        for title, section in sections.items():
            target = mapping[title]
            try:
                header = section.winfo_children()[0]
            except Exception:
                continue
            callback = (
                self._open_project_calendar_187
                if target == '__calendar__' else
                (lambda _event, value=target: self._select_tab_text(value))
            )
            header.configure(cursor='hand2')
            header.bind('<Button-1>', callback, add='+')
            for child in header.winfo_children():
                child.configure(cursor='hand2')
                child.bind('<Button-1>', callback, add='+')

    def _refresh_message_count_187(self):
        message_var = getattr(self, 'messages_text187', None)
        if message_var is None:
            return
        try:
            count = len(unread_message_events_187(upcoming_events_187(SERVICE, 30)))
        except Exception:
            count = 0
        message_var.set(fa(count) if count else '')
        host = getattr(self, 'bell_host187', None)
        if host is None or not host.winfo_exists():
            return
        badge = getattr(self, 'messages_badge187', None)
        if badge is None or not badge.winfo_exists():
            p = palette_187()
            fs = max(9, min(12, int(load_ui().get('font_size') or 10)))
            # A small count on the bell's upper corner, clear of the bell.
            badge = tk.Label(
                host, textvariable=message_var, bg=p['red'], fg=p['on_accent'],
                bd=0, padx=3, pady=0, anchor='center',
                font=kit_font('small', widget=self, bold=True),
            )
            badge.place(x=0, y=0, anchor='nw')
            self.messages_badge187 = badge
        if count:
            badge.configure(bg=palette_187()['red'], fg=palette_187()['on_accent'])
            badge.place(x=0, y=0, anchor='nw')
            badge.lift()
        else:
            badge.place_forget()

    def _show_startup_reminders_187(self):
        if self._startup_reminder_shown_187:
            return
        self._startup_reminder_shown_187 = True
        try:
            events = upcoming_events_187(SERVICE, 30)
            alerts = [event for event in events if is_startup_alert_due_187(event)]
            if alerts:
                StartupMessagesPopup187(self, alerts, on_hidden=self._refresh_message_count_187)
        except Exception:
            logging.getLogger(__name__).exception('Startup message popup could not be opened')

    def _open_messages_187(self):
        return FinancialMessagesDialog187(
            self, SERVICE, document_service=self.rich,
            on_open_calendar=self._open_project_calendar_187,
            on_messages_opened=self._refresh_message_count_187,
        )

    def _upgrade_tables_184(self, root=None):
        super()._upgrade_tables_184(root)
        target = root or self

        def apply():
            for widget in v186._walk(target):
                if isinstance(widget, ttk.Treeview):
                    apply_tree_rtl_187(widget)
                    # The inherited stage can add a ruled-grid overlay after
                    # it creates the Treeview.  Run the 18.7 contract last so
                    # those legacy vertical and horizontal rules stay gone.
                    self._unify_table_187(
                        widget, palette_187(),
                        max(28, int(theme_metrics_187()['row_height'])),
                    )
        try:
            target.after_idle(apply)
        except Exception:
            apply()

    def _apply_financial_report_theme_187(self):
        """Retarget inherited transaction and manager-report widgets to 18.7 styles only."""
        p = palette_187()
        size = max(9, min(18, int(load_ui().get('font_size') or 11)))
        family = resolve_font_family_187(self, load_ui().get('font_family'))
        weight = resolve_font_weight_187(self, family, load_ui().get('font_weight'))
        notebook = getattr(self, 'fin_nb', None)
        if isinstance(notebook, ttk.Notebook) and not hasattr(notebook, '_barkav_rtl_strip'):
            # A notebook driven by an RTL button strip keeps the style that
            # empties its Tab layout.  Re-styling it here put the real tab row
            # back and left the screen showing two rows of the same tabs.
            notebook.configure(style='Barkav.Data.TNotebook')

        table_names = (
            'all_tx_table', 'exp_table', 'cheque_table', 'in_table',
            'out_table', 'loan_table', 'document_table', 'manager_withdraw_table',
        )
        for name in table_names:
            table = getattr(self, name, None)
            tree = getattr(table, 'tree', None)
            if isinstance(tree, ttk.Treeview):
                tree.configure(style='Barkav.Data.Treeview')
                stripe_tree(tree, theme_selection_187())
            if isinstance(table, tk.Misc):
                for widget in v186._walk(table):
                    self._apply_widget_font_187(widget, family, weight, size)

        for metric in getattr(self, 'manager_metrics', {}).values():
            if isinstance(metric, tk.Misc):
                for widget in v186._walk(metric):
                    self._apply_widget_font_187(widget, family, weight, size)
        for widget in v186._walk(self):
            if isinstance(widget, ttk.Notebook) and widget is notebook:
                continue
            if getattr(widget, 'master', None) is notebook:
                self._apply_widget_font_187(widget, family, weight, size)
        try:
            self.configure(bg=p['bg'])
        except tk.TclError:
            pass

    def _restyle_dashboard_187(self):
        """Apply visible Dashboard-only hierarchy without touching presentation data."""
        p = palette_187()
        canvas = getattr(self, 'overview_canvas', None)
        if canvas is not None:
            canvas.configure(bg=p['bg'], highlightthickness=0)
            for child in canvas.winfo_children():
                child.configure(bg=p['bg'])
        sections = []
        for metric in getattr(self, 'cards', {}).values():
            try:
                section = metric.master.master
            except (AttributeError, tk.TclError):
                continue
            if section not in sections:
                sections.append(section)
        phase_strip = getattr(self, 'phase_strip', None)
        if phase_strip is not None:
            sections.append(phase_strip.master.master)

        for section in sections:
            try:
                section.configure(bg=p['card'], highlightbackground=p['border_subtle'], highlightthickness=1)
                # The five KPI cards are gridded; the 32-phase card is packed,
                # and grid options on it silently took it out of the page.
                if section.winfo_manager() == 'grid':
                    section.grid_configure(padx=8, pady=4)
            except tk.TclError:
                continue
            children = [child for child in section.winfo_children()
                        if child is not getattr(section, '_barkav_backdrop', None)]
            header = next((child for child in children if isinstance(child, tk.Frame)), None)
            if header is not None:
                # The inherited dashboard has tall headers and metric rows;
                # constrain the header to the compact dashboard rhythm while
                # preserving room for the reference artwork.
                # D5: 38px - the icon tile's height plus a little - so the
                # whole dashboard fits a 768-pixel screen without scrolling.
                header.configure(bg=p['surface_alt'], height=36)
                for label in header.winfo_children():
                    if isinstance(label, tk.Label):
                        if getattr(label, '_phase_legend187', False):
                            label.configure(bg=p['surface_alt'], fg=p['text_muted'],
                                            font=dashboard_font_187(self, 7, 'body'))
                            continue
                        glyph = str(label.cget('text') or '')
                        reference = getattr(label, '_dashboard_reference187', None) or {
                            '⇄': 'transactions', '▱': 'checks', '♜': 'loans',
                            '◉': 'sales', '▣': 'calendar',
                        }.get(glyph)
                        if glyph == '▥' or getattr(label, '_dashboard_phase_icon187', False):
                            # The 32-phase card takes the same kind of tile.
                            image = self._card_tile_187('project', 'yellow', p)
                            label._dashboard_phase_icon187 = True
                            label._barkav_tile187 = image
                            label.configure(bg=p['surface_alt'], image=image, text='',
                                            width=image.width(), height=image.height(),
                                            padx=0, pady=0)
                            label.pack_forget()
                            label.place(relx=0.0, rely=0.5, anchor='w', x=8, y=0)
                            label.lift()
                            continue
                        if reference:
                            # D2, reworked 2026-09-27: each card wears the
                            # rail's glassy raised tile, in a colour of its own.
                            image = self._card_tile_187(
                                self._CARD_ICONS_187.get(reference, 'dashboard'),
                                self._CARD_HUES_187.get(reference, 'accent'), p)
                            if not hasattr(self, '_dashboard_card_images187'):
                                self._dashboard_card_images187 = {}
                            self._dashboard_card_images187[reference] = image
                            label._dashboard_reference187 = reference
                            label.configure(bg=p['surface_alt'], fg=p['accent'], image=image,
                                            text='', width=image.width(), height=image.height(),
                                            padx=0, pady=0, anchor='center')
                            # Same spot in every card: the left end of the
                            # header, clear of its rounded corner.
                            label.pack_forget()
                            label.place(relx=0.0, rely=0.5, anchor='w', x=8, y=0)
                            # The rounded card's backdrop is a sibling of the
                            # header; keep the tile above it after a redraw.
                            label.lift()
                        elif not getattr(label, '_phase_legend187', False):
                            # «۳۰ روز آینده» starts with its number, which Tk
                            # on Windows then put on the left (2026-09-27).
                            label.configure(bg=p['surface_alt'], fg=p['text_primary'],
                                            text=rtl_187(label.cget('text')),
                                            font=dashboard_font_187(self, 10, 'title'))

        for index, metric in enumerate(getattr(self, 'cards', {}).values()):
            background = p['surface_alt'] if index % 2 == 0 else p['card']
            # Alternate fills alone keep the rows apart inside the rounded
            # card (2026-09-27); a border on every row cost 2px a row.
            metric.configure(bg=background, highlightthickness=0)
            metric.title_label.configure(bg=background, fg=p['text_secondary'],
                                         font=dashboard_font_187(self, 8, 'body'))
            metric.value_label.configure(bg=background, fg=p['text_primary'],
                                         font=dashboard_font_187(self, 11, 'kpi'))
            # Keep both text values readable but remove the inherited tall
            # row padding so the full overview fits without vertical scroll.
            metric.title_label.pack_configure(pady=1)
            metric.value_label.pack_configure(pady=1)
            metric.pack_configure(pady=1)

        if phase_strip is not None:
            phase_strip.configure(bg=p['card'])
        # Inherited from stage16_3/18_6 at a flat 6pt - unreadable at any
        # real window width, and the one property refresh_phase_strip's own
        # per-status repaint (below) never touches, so it only needs setting
        # once here rather than on every data refresh.
        phase_font = dashboard_font_187(self, 9, 'kpi')
        for button in getattr(self, 'phase_buttons', {}).values():
            button.configure(bg=p['glass'], fg=p['text_secondary'], activebackground=p['info'],
                             activeforeground=p['on_accent'], highlightbackground=p['border_subtle'],
                             highlightthickness=1, font=phase_font, pady=8)
        for chart in (getattr(self, 'cost_donut', None), getattr(self, 'liquidity_chart', None),
                      getattr(self, 'phase_chart', None)):
            if chart is not None:
                chart.grid_configure(padx=8, pady=4)

    _CARD_ICONS_187 = {
        'transactions': 'transactions', 'checks': 'cheque', 'loans': 'bank',
        'sales': 'coins', 'calendar': 'calendar',
    }
    # Palette roles; transactions and sales match their rail items' tiles.
    _CARD_HUES_187 = {
        'transactions': 'green', 'checks': 'violet', 'loans': 'blue',
        'sales': 'orange', 'calendar': 'accent',
    }

    def _card_tile_187(self, icon, role, p):
        return glass_tile_187(icon, size=30, colour=p.get(role) or p['accent'], ink=p['on_accent'],
                              background=p['surface_alt'], shadow=p['shadow'], master=self)

    def _install_phase_groups_187(self):
        """D3 (operator-approved, reworked 2026-09-27): the 32 phases in one
        row with their names under them and the overall ring, in place of 32
        numbered buttons and a bar; the colour key sits in the card heading.

        The buttons stay (hidden): other code still reads and repaints them."""
        strip = getattr(self, 'phase_strip', None)
        if strip is None or getattr(self, 'phase_groups187', None) is not None:
            return
        p = palette_187()
        for button in getattr(self, 'phase_buttons', {}).values():
            try:
                button.grid_remove()
            except tk.TclError:
                pass
        overall = getattr(self, 'overall_progress', None)
        try:
            if overall is not None and overall.winfo_manager():
                overall.pack_forget()
        except tk.TclError:
            pass
        colours = {
            'NOT_STARTED': p['phase_not_started'], 'ACTIVE': p['phase_active'],
            'PAUSED': p['phase_paused'], 'COMPLETED': p['phase_completed'],
            'track': mix(p['card'], p['text_primary'], 0.09),
            'text': p['text_primary'], 'muted': p['text_secondary'],
            'accent': p['accent'], 'ring': p['accent'],
            'card': p['surface_alt'], 'border': p['accent'],
        }
        self._phase_colours187 = colours
        groups = PhaseGroups(
            strip, background=p['card'], colours=colours,
            on_open=self.open_phase_by_no, on_edit=self.edit_phase_progress,
            on_overall=lambda: v18.v175.v16.ProjectFinancialOverview(self, self.rich),
        )
        groups.grid(row=1, column=0, columnspan=32, sticky='ew', pady=(2, 0))
        self.phase_groups187 = groups
        try:
            strip.master.master.pack_configure(pady=2)
        except (tk.TclError, AttributeError):
            pass
        self._refresh_phase_groups_187()
        canvas = getattr(self, 'overview_canvas', None)
        if canvas is not None:
            canvas.bind('<Configure>', lambda _e: self._schedule_overview_fit_187(), add='+')
        self._schedule_overview_fit_187()

    def _schedule_overview_fit_187(self):
        if getattr(self, '_overview_fit_job187', None) is None:
            try:
                self._overview_fit_job187 = self.after(60, self._fit_overview_187)
            except tk.TclError:
                self._overview_fit_job187 = None

    def _fit_overview_187(self):
        """D5 (operator-approved): the dashboard fits its window without
        scrolling. Everything above the charts keeps its size; the charts
        take the height that is left, between 128 and 240 pixels (128 since
        the 2026-09-27 round made the bar, the footer and the phase card
        taller)."""
        self._overview_fit_job187 = None
        canvas = getattr(self, 'overview_canvas', None)
        charts = [c for c in (getattr(self, 'cost_donut', None), getattr(self, 'liquidity_chart', None),
                              getattr(self, 'phase_chart', None)) if c is not None]
        if canvas is None or not charts:
            return
        try:
            visible = canvas.winfo_height()
            inner = charts[0].master.master
            content = inner.winfo_reqheight()
            current = int(float(charts[0].cget('height')))
        except (tk.TclError, AttributeError, ValueError):
            return
        if visible < 200:
            return
        # The rows above the charts give back what they do not need.
        try:
            charts[0].master.pack_configure(pady=(2, 0))
            button = getattr(self, 'project_settings_button187', None)
            if button is not None and button.winfo_manager() == 'pack':
                button.pack_configure(pady=2)
            inner.update_idletasks()
            content = inner.winfo_reqheight()
        except (tk.TclError, AttributeError):
            pass
        # Operator round 2026-09-27: squeezed to fit, the charts were cut
        # off and unreadable; they keep a readable height and the page
        # scrolls to them instead.
        target = max(240, min(300, current + (visible - content) - 2))
        if abs(target - current) < 3:
            return
        for chart in charts:
            try:
                chart.configure(height=target)
            except tk.TclError:
                continue

    def _refresh_phase_groups_187(self):
        """Fill the 32 cells from the recorded progress and, where none is
        recorded, from what each phase has cost against its budget - the
        plan's واقعی, which the posted costs feed (operator round
        2026-09-27: the row stood still while costs were being recorded)."""
        groups = getattr(self, 'phase_groups187', None)
        if groups is None:
            return
        try:
            progress = self.rich.get_phase_progress()
        except Exception:
            progress = {}
        names = {number: (PHASE_HINTS.get(number) or (f'فاز {number}',))[0] for number in range(1, 33)}
        spending = {}
        try:
            for row in self._phase_summary_live():
                number = int(row['phase_no'])
                if row.get('phase'):
                    names[number] = str(row['phase'])
                budget = int(row.get('forecast') or 0) or int(row.get('estimate') or 0)
                spending[number] = (int(row.get('actual') or 0), budget)
        except Exception:
            spending = {}
        for number, amount in unplanned_phase_costs_187(DB, names).items():
            spent, budget = spending.get(number, (0, 0))
            spending[number] = (spent + amount, budget)
        groups.set_data(progress, names, spending=spending)
        self._dress_phase_card_187()

    _PHASE_CARD_TITLE187 = 'پیشرفت پروژه — ۳۲ فاز'

    def _dress_phase_card_187(self):
        """The card's heading: its title, and the colour key at its left end
        in place of the one-line legend another layer may have packed there
        (operator round 2026-09-27). Re-run on every refresh, so it holds
        whichever order the finalisers run in."""
        strip = getattr(self, 'phase_strip', None)
        colours = getattr(self, '_phase_colours187', None)
        try:
            card = strip.master.master
            # DashboardCard186 packs its heading strip before its body, and
            # the rounded backdrop is placed rather than packed - so the
            # first *packed* Frame is always the heading, however many
            # other Frames a merged build's card ends up carrying. Picking
            # "the first Frame that isn't the backdrop" from the unordered
            # winfo_children() could - and, reported live on a build merged
            # with other branches, did - land on a different one instead,
            # leaving the legend built but parented somewhere lower than
            # the title (operator round 2026-09-28).
            packed_frames = [child for child in card.pack_slaves() if isinstance(child, tk.Frame)]
            if packed_frames:
                header = packed_frames[0]
            else:
                header = next(child for child in card.winfo_children()
                              if isinstance(child, tk.Frame)
                              and child is not getattr(card, '_barkav_backdrop', None))
        except (AttributeError, StopIteration, tk.TclError, IndexError):
            return
        titled = False
        title = None
        # Any «راهنما: ...» hint line another layer put in the card goes too
        # (operator round 2026-09-27); the colour key beside the title says it.
        for child in self._walk_187(card):
            if not isinstance(child, tk.Label) or child.master is header:
                continue
            try:
                if str(child.cget('text') or '').strip().startswith('راهنما'):
                    child.pack_forget()
                    child.place_forget()
                    child.grid_forget()
            except tk.TclError:
                pass
        for child in header.winfo_children():
            if not isinstance(child, tk.Label):
                continue
            try:
                hint = str(child.cget('text') or '').strip().startswith('راهنما')
            except tk.TclError:
                hint = False
            if getattr(child, '_phase_legend187', False) or hint:
                try:
                    child.pack_forget()
                    child.place_forget()
                except tk.TclError:
                    pass
                continue
            if titled or getattr(child, '_dashboard_phase_icon187', False) or child.cget('image'):
                continue
            try:
                child.configure(text=self._PHASE_CARD_TITLE187)
                titled = True
                title = child
            except tk.TclError:
                pass
        legend = getattr(self, 'phase_legend_canvas187', None)
        if colours is None:
            return
        try:
            if legend is None or not legend.winfo_exists():
                background = str(header.cget('bg'))
                legend = PhaseLegend(header, background=background, colours=colours)
                self.phase_legend_canvas187 = legend
            # Beside the title (operator round 2026-09-27), just to its left.
            def place(_event=None, legend=legend, title=title):
                try:
                    if title is not None and title.winfo_ismapped():
                        # The label may span the heading; its words sit at
                        # its right end.
                        words = tkfont.Font(root=title, font=title.cget('font')).measure(
                            str(title.cget('text')))
                        right = title.winfo_x() + title.winfo_width() - int(title.cget('padx') or 0)
                        legend.place(x=right - words - 16, rely=0.5, anchor='e', y=0)
                    else:
                        legend.place(relx=0.0, rely=0.5, anchor='w', x=52, y=0)
                    legend.lift()
                except tk.TclError:
                    pass

            place()
            if not getattr(header, '_barkav_legend_bound187', False):
                header._barkav_legend_bound187 = True
                header.bind('<Configure>', lambda _e: place(), add='+')
                if title is not None:
                    title.bind('<Configure>', lambda _e: place(), add='+')
        except tk.TclError:
            pass

    def _overview_project_frame_187(self):
        """Find the inherited project-summary surface without changing stage 18.6.

        ``Stage186Dashboard`` creates this frame as a local variable.  Its
        heading is stable UI text, so locating that one heading lets the 18.7
        overlay restyle the existing surface and retain all project metadata
        and commands.
        """
        for widget in self._walk_187(getattr(self, 'overview_canvas', self)):
            if not isinstance(widget, tk.Label):
                continue
            try:
                if str(widget.cget('text')) == 'نمای کلی پروژه':
                    return widget.master
            except tk.TclError:
                continue
        return None

    def _replace_project_settings_button_187(self, project):
        """Replace the inherited blue classic button with the rounded gray skin."""
        existing = getattr(self, 'project_settings_button187', None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    return existing
            except tk.TclError:
                pass
        for widget in project.winfo_children():
            if not isinstance(widget, tk.Button):
                continue
            try:
                if str(widget.cget('text')) != 'مشخصات پروژه':
                    continue
                pack = dict(widget.pack_info())
            except tk.TclError:
                continue
            # ``in`` is only meaningful to Tk's pack query and must not be
            # handed back when the replacement's parent is already project.
            pack.pop('in', None)
            widget.destroy()
            button = ttk.Button(
                project, text='مشخصات پروژه', command=self.edit_project_settings,
                style='ProjectSummary.TButton', width=16,
            )
            button.pack(**pack)
            self.project_settings_button187 = button
            return button
        return None

    @staticmethod
    def _paint_chart_rounding_187(chart, palette, radius):
        """Draw a rounded card inside a Canvas whose page-colour corners show.

        A native Canvas, like a Treeview, cannot have a non-rectangular window
        shape.  Painting the rounded surface *inside* it preserves every chart
        renderer while making the four outer corners transparent to the page.
        """
        try:
            chart.delete('_barkav_chart_card187')
            width, height = max(1, chart.winfo_width()), max(1, chart.winfo_height())
            r = min(max(4, int(radius)), width // 2, height // 2)
            if r < 2:
                return
            tag = '_barkav_chart_card187'
            parts = (
                chart.create_rectangle(r, 0, width - r, height, fill=palette['card'], outline='', tags=tag),
                chart.create_rectangle(0, r, width, height - r, fill=palette['card'], outline='', tags=tag),
                chart.create_arc(0, 0, 2 * r, 2 * r, start=90, extent=90, fill=palette['card'], outline='', tags=tag),
                chart.create_arc(width - 2 * r, 0, width, 2 * r, start=0, extent=90, fill=palette['card'], outline='', tags=tag),
                chart.create_arc(0, height - 2 * r, 2 * r, height, start=180, extent=90, fill=palette['card'], outline='', tags=tag),
                chart.create_arc(width - 2 * r, height - 2 * r, width, height, start=270, extent=90, fill=palette['card'], outline='', tags=tag),
                chart.create_rectangle(r, 0, width - r, height - 1, outline=palette['border_subtle'], tags=tag),
                chart.create_rectangle(0, r, width - 1, height - r, outline=palette['border_subtle'], tags=tag),
            )
            for item in parts:
                chart.tag_lower(item)
        except tk.TclError:
            return

    def _paint_resizable_backdrop_187(self, container, *, fill, page, radius, border, band=None):
        """rounded_backdrop(), kept in sync with the container's real size.

        The backdrop is a fixed-size PhotoImage painted once from whatever
        width/height the container happens to have at that moment. Stage
        18.6's own notebook rebinds ``<<NotebookTabChanged>>`` to
        re-maximize the window on every tab switch (dashboard_stage18_6.py),
        so a container built before the first maximize (or before any later
        resize) is left with a backdrop narrower than its own now-larger
        frame - the card visibly stops short of the content sitting at the
        frame's real edges. Re-painting on the container's own <Configure>
        keeps the two in step; the size check skips redundant repaints when
        a <Configure> fires without an actual size change.
        """
        from barkav_ui.skin import rounded_backdrop

        container._barkav_backdrop_spec187 = dict(fill=fill, page=page, radius=radius,
                                                  border=border, band=band)
        selected = getattr(container, '_barkav_selected_border187', None)
        rounded_backdrop(container, fill=fill, page=page, radius=radius, border=selected or border,
                         band=band, master=self, border_width=2 if selected else 1)
        container._barkav_backdrop_size187 = (container.winfo_width(), container.winfo_height())

        if getattr(container, '_barkav_backdrop_bound187', False):
            return

        def _on_configure(event, container=container):
            size = (event.width, event.height)
            if size == getattr(container, '_barkav_backdrop_size187', None):
                return
            container._barkav_backdrop_size187 = size
            selected = getattr(container, '_barkav_selected_border187', None)
            rounded_backdrop(container, fill=fill, page=page, radius=radius,
                             border=selected or border, band=band, master=self,
                             border_width=2 if selected else 1)

        container._barkav_backdrop_bound187 = True
        container.bind('<Configure>', _on_configure, add='+')

    def _make_card_selectable_187(self, section):
        """A click anywhere on a dashboard card outlines it in the
        selection colour, as a selected table row is (operator round
        2026-09-27); another click elsewhere moves the outline. Pointing at
        a card (without clicking) also lifts its outline, the same lighter
        neutral a Start card's hover uses - these five had no hover
        feedback at all, reported live (operator round 2026-09-28)."""
        from barkav_ui.skin import rounded_backdrop

        if getattr(section, '_barkav_selectable187', False):
            return
        section._barkav_selectable187 = True
        section._barkav_hot187 = False

        def repaint():
            spec = getattr(section, '_barkav_backdrop_spec187', None)
            if spec is None or getattr(section, '_barkav_selected_border187', None):
                return
            p = palette_187()
            base_border = spec.get('border') or p['border_subtle']
            hover_border = mix(p['border_subtle'], p['text_primary'], 0.45)
            hot = section._barkav_hot187
            try:
                rounded_backdrop(section, fill=spec.get('fill'), page=spec.get('page'),
                                 radius=spec.get('radius'), band=spec.get('band'), master=self,
                                 border=hover_border if hot else base_border,
                                 border_width=2 if hot else 1)
            except tk.TclError:
                pass

        def settle(_event=None):
            def check():
                try:
                    under = self.winfo_containing(*self.winfo_pointerxy())
                except (tk.TclError, KeyError):
                    under = None
                inside = False
                while under is not None:
                    if under is section:
                        inside = True
                        break
                    under = getattr(under, 'master', None)
                if inside != section._barkav_hot187:
                    section._barkav_hot187 = inside
                    repaint()
            try:
                self.after(25, check)
            except tk.TclError:
                pass

        def bind(widget):
            try:
                widget.bind('<Button-1>', lambda _e: self._select_card_187(section), add='+')
                widget.bind('<Enter>', settle, add='+')
                widget.bind('<Leave>', settle, add='+')
                for child in widget.winfo_children():
                    bind(child)
            except tk.TclError:
                pass

        bind(section)

    def _select_card_187(self, section):
        previous = getattr(self, '_selected_card187', None)
        self._selected_card187 = section
        p = palette_187()
        # The selected table row's own outline colour.
        colour = p['focus_ring']
        for card, border in ((previous, None), (section, colour)):
            if card is None:
                continue
            try:
                if not card.winfo_exists():
                    continue
            except tk.TclError:
                continue
            card._barkav_selected_border187 = border
            spec = getattr(card, '_barkav_backdrop_spec187', None)
            if spec is None:
                continue
            self._paint_resizable_backdrop_187(card, **spec)
            backdrop = getattr(card, '_barkav_backdrop', None)
            for child in card.winfo_children():
                if child is backdrop:
                    continue
                try:
                    if backdrop is not None and backdrop.winfo_exists():
                        child.tkraise(backdrop)
                except tk.TclError:
                    pass

    def _round_overview_containers_187(self):
        """Apply the shared rounded-card surface to all Dashboard containers."""
        from barkav_ui.skin import rounded_backdrop

        p = palette_187()
        radius = max(8, int(theme_metrics_187().get('radius', 6)))
        project = self._overview_project_frame_187()
        if project is not None:
            self._replace_project_settings_button_187(project)
            try:
                project.configure(bg=p['bg'], highlightthickness=0, bd=0)
            except tk.TclError:
                pass
            try:
                # Inherited stage 18.6 left a 6px bottom margin here plus a
                # further 2+2px above the metric-card row below - an 10px
                # page-coloured seam between two rounded cards that should
                # read as one continuous surface, not two floating boxes.
                project.pack_configure(pady=(2, 0))
            except tk.TclError:
                pass
            self._paint_resizable_backdrop_187(project, fill=p['card'], page=p['bg'],
                                               radius=radius, border=p['border_subtle'])

        sections = []
        for metric in getattr(self, 'cards', {}).values():
            try:
                section = metric.master.master
            except (AttributeError, tk.TclError):
                continue
            if section not in sections:
                sections.append(section)
        phase_strip = getattr(self, 'phase_strip', None)
        if phase_strip is not None:
            try:
                sections.append(phase_strip.master.master)
            except (AttributeError, tk.TclError):
                pass

        for section in sections:
            try:
                section.configure(bg=p['bg'], highlightthickness=0, bd=0)
                # The rounded backdrop is a sibling which can be inserted before
                # the header/body.  Never treat it as content and explicitly lift
                # the real header after rebuilding the surface; this keeps the
                # checks/transactions reference icons above the card layer.
                children = [
                    child for child in section.winfo_children()
                    if child is not getattr(section, '_barkav_backdrop', None)
                ]
                band = None
                if len(children) >= 2:
                    # Operator round 2026-09-27: the cards read as rounded.
                    # The heading's colour is drawn into the card as a band,
                    # so the heading frame stays clear of the corners, and
                    # the rows keep off the rounded foot.
                    children[0].pack_configure(padx=radius, pady=(1, 0))
                    children[1].pack_configure(padx=4, pady=(2, 4))
                    band = (1 + int(children[0].cget('height') or 38),
                            str(children[0].cget('bg') or p['surface_alt']))
            except tk.TclError:
                continue
            self._paint_resizable_backdrop_187(section, fill=p['card'], page=p['bg'],
                                               radius=radius, border=p['border_subtle'], band=band)
            for child in children:
                try:
                    backdrop = getattr(section, '_barkav_backdrop', None)
                    # Use an explicit sibling target: this remains reliable
                    # when place() reorders the backdrop during a redraw.
                    if backdrop is not None and backdrop.winfo_exists():
                        child.tkraise(backdrop)
                    else:
                        child.lift()
                    for grandchild in child.winfo_children():
                        if backdrop is not None and backdrop.winfo_exists():
                            grandchild.tkraise(backdrop)
                        else:
                            grandchild.lift()
                except tk.TclError:
                    continue

        for section in sections:
            self._make_card_selectable_187(section)

        for chart in (getattr(self, 'cost_donut', None), getattr(self, 'liquidity_chart', None),
                      getattr(self, 'phase_chart', None)):
            if not isinstance(chart, tk.Canvas):
                continue
            try:
                chart.configure(bg=p['bg'], highlightthickness=0, bd=0)
            except tk.TclError:
                continue
            if not getattr(chart, '_barkav_round_redraw187', False):
                original = chart.redraw

                def redraw_with_card(original=original, target=chart):
                    original()
                    self._paint_chart_rounding_187(target, palette_187(), radius)
                    self._smooth_chart_lines_187(target)

                chart.redraw = redraw_with_card
                chart._barkav_round_redraw187 = True
            chart.redraw()

    def _smooth_chart_lines_187(self, canvas):
        """Tk's canvas draws lines without anti-aliasing, so a chart's
        curves came out stair-stepped (operator round 2026-09-27). Every
        polyline of the chart is drawn again at four times the size into a
        transparent picture, scaled down, and put where the lines were;
        the chart's words stay on top."""
        try:
            from PIL import Image, ImageDraw, ImageTk
        except ImportError:
            return
        try:
            width, height = int(canvas.winfo_width()), int(canvas.winfo_height())
            lines = [item for item in canvas.find_all() if canvas.type(item) == 'line'
                     and len(canvas.coords(item)) >= 6]
        except tk.TclError:
            return
        if width < 20 or height < 20 or not lines:
            return
        scale = 4
        picture = Image.new('RGBA', (width * scale, height * scale), (0, 0, 0, 0))
        pen = ImageDraw.Draw(picture)
        for item in lines:
            try:
                coords = canvas.coords(item)
                colour = canvas.itemcget(item, 'fill')
                stroke = max(1.0, float(canvas.itemcget(item, 'width') or 1))
                red, green, blue = (value // 257 for value in canvas.winfo_rgb(colour))
            except (tk.TclError, ValueError):
                continue
            points = [(coords[i] * scale, coords[i + 1] * scale) for i in range(0, len(coords) - 1, 2)]
            size = int(round(max(2.0, stroke + 0.6) * scale))
            pen.line(points, fill=(red, green, blue, 255), width=size, joint='curve')
            radius = size / 2
            for x, y in (points[0], points[-1]):
                pen.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(red, green, blue, 255))
            canvas.delete(item)
        image = ImageTk.PhotoImage(picture.resize((width, height), Image.LANCZOS), master=self)
        canvas._barkav_smooth_lines187 = image
        layer = canvas.create_image(0, 0, image=image, anchor='nw')
        for item in canvas.find_all():
            if canvas.type(item) == 'text':
                canvas.tag_raise(item, layer)

    def _phase_summary_live(self):
        """Roll dashboard charts up from the exact rows shown in پلان پروژه.

        The plan treats a zero ``مبلغ کل-بروز`` as an explicit zero.  The
        inherited roll-up substituted the base estimate for missing/zero
        revision figures, so the dashboard could disagree with the plan's
        visible per-phase totals.  Reuse the plan's own total function for
        all three series, while retaining the existing dashboard field names
        for the inherited charts and phase table.
        """
        grouped: dict[int, dict[str, int | str]] = {}
        for item in self.rich.all_phase_items():
            try:
                phase_no = int(item.get('phase_no') or 0)
            except (TypeError, ValueError):
                continue
            if phase_no <= 0:
                continue
            summary = grouped.setdefault(
                phase_no,
                {
                    'phase': str(item.get('phase_name') or ''),
                    'estimate': 0,
                    'actual': 0,
                    'forecast': 0,
                },
            )
            if not summary['phase'] and item.get('phase_name'):
                summary['phase'] = str(item['phase_name'])
            estimate, current, actual = plan_totals_187(item)
            summary['estimate'] = int(summary['estimate']) + estimate
            summary['actual'] = int(summary['actual']) + actual
            # ``forecast`` is the legacy chart field for the plan's بروز
            # column, not a synthetic end-of-project forecast here.
            summary['forecast'] = int(summary['forecast']) + current

        rows = []
        for phase_no in sorted(grouped):
            summary = grouped[phase_no]
            estimate = int(summary['estimate'])
            actual = int(summary['actual'])
            current = int(summary['forecast'])
            rows.append({
                'phase_no': phase_no,
                'phase': str(summary['phase']),
                'phase_id': f'PH-{phase_no:02d}',
                'estimate': estimate,
                'actual': actual,
                'remaining_base': max(estimate - actual, 0),
                'forecast': current,
                'variance': current - estimate,
            })
        return rows

    def _open_dashboard_summary(self, group):
        if group != '۳۰ روز آینده':
            return super()._open_dashboard_summary(group)
        summary = self._thirty_day_summary_187()
        dialog = BarkavWindow(
            self, 'مشخصات اجمالی — ۳۰ روز آینده',
            subtitle='داشبورد', size_class='small', show_footer=False,
        )
        dialog.geometry('760x460')
        card = v18.GlassSection(dialog.body, '۳۰ روز آینده')
        card.pack(fill='both', expand=True, padx=10, pady=10)
        tree = ttk.Treeview(card.body, columns=('title', 'value'), show='headings')
        tree.heading('title', text='عنوان')
        tree.heading('value', text='مقدار')
        tree.column('title', anchor='e', width=350)
        tree.column('value', anchor='center', width=270)
        tree.pack(fill='both', expand=True)
        rows = (
            ('تعهدات ۳۰ روز', summary['commitments']),
            ('چک‌ها ۳۰ روز', summary['cheques']),
            ('اقساط ۳۰ روز', summary['installments']),
            ('مطالبات ۳۰ روز', summary['claims']),
            ('تراز مالی ۳۰ روز', summary['balance']),
            ('مانده نقدی', summary['cash']),
            ('نقدینگی مورد نیاز', summary['liquidity_needed']),
            # Reported beside the 30-day figures; not part of the balance.
            ('تعهدات معوق (خارج از محاسبه)', summary['overdue_commitments']),
        )
        tree.tag_configure('positive', foreground=palette_187().get('green'))
        tree.tag_configure('negative', foreground=palette_187().get('red'))
        for title, value in rows:
            tag = 'positive' if title == 'نقدینگی مورد نیاز' and value >= 0 else (
                'negative' if title == 'نقدینگی مورد نیاز' else '')
            tree.insert('', 'end', values=(title, fa(f'{int(value):,}')), tags=(tag,) if tag else ())
        return dialog

    def _build_manager(self):
        """Build the compact, ledger-backed 18.7.1 manager account workspace."""
        super()._build_manager()
        tab_id = getattr(self, 'manager_tab_id', None)
        if not tab_id:
            tab_id = next((item for item in self.notebook.tabs()
                           if self.notebook.tab(item, 'text') in ('حساب مدیر', 'حساب مدیر پروژه')),
                          self.notebook.tabs()[-1])
        self.manager_tab_id = tab_id
        self.notebook.tab(tab_id, text='حساب مدیر')
        tab = self.nametowidget(tab_id)
        for child in list(tab.winfo_children()):
            child.destroy()

        self.manager_fee_percent_var = tk.StringVar(value=fa('10'))
        self.manager_actual_cash_var = tk.StringVar()
        self._manager_actual_cash_initialized_187 = False
        self.manager_formula_var = tk.StringVar(
            value='کل هزینه‌های مشمول حقوق مدیر = هزینه فازهای ۰۲ تا ۳۲، بدون حقوق مدیر'
        )
        self.manager_status_var = tk.StringVar(value='برای محاسبه، موجودی واقعی را بررسی کنید؛ حقوق مدیر ۱۰٪ هزینه ساخت است.')
        self.manager_summary_vars = {
            key: tk.StringVar(value=fa('۰')) for key in (
                'construction_cost', 'transaction_cash', 'account_difference',
                'eligible_costs', 'manager_fee', 'manager_receipts',
                'before_difference', 'with_difference',
            )
        }
        self.manager_metrics = {}

        palette = palette_187()
        panel = palette['panel']
        surface = palette['surface']
        text_color = palette['text']
        muted = palette['muted']
        line = palette['line']

        controls = tk.Frame(tab, bg=surface, highlightbackground=line, highlightthickness=1)
        controls.pack(fill='x', padx=6, pady=(6, 4))
        # The former explanatory titles in this compact command row were
        # redundant.  The formula below names the result; this row is action
        # and value only, matching the user's annotated layout.
        percent_entry = ttk.Entry(controls, textvariable=self.manager_fee_percent_var,
                                  width=7, justify='center', style='Compact.TEntry', state='readonly')
        percent_entry.pack(side='right', pady=5, padx=(10, 2))
        tk.Label(controls, text='٪', bg=surface, fg=muted,
                 font=('Segoe UI', 9, 'bold')).pack(side='right', padx=(2, 7))
        calculate = ttk.Button(controls, text='محاسبه', command=self.refresh_manager,
                               style='Primary.TButton')
        calculate.pack(side='right', padx=4, pady=4)
        add_tooltip(calculate, 'مبالغ حساب مدیر را با درصد واردشده و موجودی واقعی محاسبه می‌کند؛ چیزی ذخیره نمی‌شود.')
        fee_box = tk.Frame(controls, bg=panel, highlightbackground=line, highlightthickness=1)
        fee_box.pack(side='right', padx=(8, 4), pady=4)
        tk.Label(fee_box, textvariable=self.manager_summary_vars['manager_fee'], bg=panel, fg=text_color,
                 font=('Segoe UI', 10, 'bold')).pack(side='right', padx=10, pady=5)
        tk.Label(controls, textvariable=self.manager_status_var, bg=surface, fg=muted,
                 font=('Segoe UI', 8)).pack(side='left', padx=10)
        percent_entry.bind('<Return>', lambda _event: self.refresh_manager(), add='+')

        cards = tk.Frame(tab, bg=surface)
        cards.pack(fill='x', padx=6, pady=(0, 4))
        for column in range(4):
            cards.grid_columnconfigure(column, weight=1, uniform='manager-summary')

        def card(column, title, variable, *, input_field=False, tip=None):
            frame = tk.Frame(cards, bg=panel, highlightbackground=line, highlightthickness=1)
            frame.grid(row=0, column=column, sticky='nsew', padx=2, pady=2)
            title_label = tk.Label(frame, text=title, bg=panel, fg=muted,
                                   font=('Segoe UI', 8, 'bold'), anchor='e')
            title_label.pack(fill='x', padx=9, pady=(7, 2))
            if input_field:
                entry = ttk.Entry(frame, textvariable=variable, justify='center',
                                  style='Compact.TEntry')
                entry.pack(fill='x', padx=9, pady=(1, 8))
                bind_grouped_number_fa(entry, variable, allow_negative=True)
                entry.bind('<Return>', lambda _event: self.refresh_manager(), add='+')
            else:
                value_label = tk.Label(frame, textvariable=variable, bg=panel, fg=text_color,
                                       font=('Segoe UI', 11, 'bold'), anchor='e')
                value_label.pack(fill='x', padx=9, pady=(1, 8))
            if tip:
                add_tooltip(frame, tip)
                add_tooltip(title_label, tip)
            return frame

        card(0, 'کل هزینه‌های مشمول حقوق مدیر (تومان)', self.manager_summary_vars['eligible_costs'])
        card(1, 'موجودی فعلی طبق تراکنش‌ها (تومان)', self.manager_summary_vars['transaction_cash'])
        card(2, 'موجودی واقعی ـ ورود دستی (تومان)', self.manager_actual_cash_var, input_field=True,
             tip='این عدد فقط برای محاسبهٔ همین نشست است و در داده‌های پروژه ذخیره نمی‌شود.')
        card(3, 'اختلاف حساب (تومان)', self.manager_summary_vars['account_difference'],
             tip='کل ورودی − خروجی غیرساخت − هزینه ساخت − هزینه فاز خرید زمین − موجودی تنخواه؛ مثبت یعنی بدهکار به تنخواه و منفی یعنی طلبکار از تنخواه.')

        formula = tk.Label(tab, textvariable=self.manager_formula_var, bg=surface, fg=palette['cyan'],
                           font=('Segoe UI', 8, 'bold'), anchor='e', justify='right', padx=10, pady=6)
        formula.bind('<Configure>', lambda event: formula.configure(wraplength=max(200, event.width - 24)))
        formula.pack(fill='x', padx=6, pady=(0, 3))

        toolbar = ttk.Frame(tab, padding=(2, 3))
        toolbar.pack(fill='x', padx=6, pady=(1, 3))
        ttk.Label(toolbar, text='دریافتی‌های مدیر', anchor='e', style='Section.TLabel').pack(
            side='right', padx=(4, 14))
        ttk.Button(toolbar, text='افزودن', command=self._manager_add_record_187,
                   style='Toolbar.TButton').pack(side='right', padx=2)
        ttk.Button(toolbar, text='ویرایش', command=self._manager_edit_selected_187,
                   style='Toolbar.TButton').pack(side='right', padx=2)
        ttk.Button(toolbar, text='حذف', command=self._manager_delete_selected_187,
                   style='Toolbar.TButton').pack(side='right', padx=2)
        ttk.Button(toolbar, text='کپی', command=self._manager_copy_selected_187,
                   style='Toolbar.TButton').pack(side='right', padx=2)

        self.manager_output_var = tk.StringVar(value='خروجی')
        output_combo = ttk.Combobox(toolbar, textvariable=self.manager_output_var,
                                    values=('خروجی', 'PDF', 'Excel', 'پرینت'),
                                    state='readonly', width=15, justify='right', style='Output.TCombobox')
        output_combo.pack(side='left', padx=(2, 6))
        output_combo.bind('<<ComboboxSelected>>', lambda _event: self._export_manager_receipts_187(), add='+')

        search_host = ttk.Frame(toolbar)
        search_host.pack(side='left', padx=(10, 2))
        ttk.Label(search_host, text='جستجو:').pack(side='right')
        self.manager_search_entry_187 = ttk.Entry(search_host, width=22, justify='right', style='Compact.TEntry')
        self.manager_search_entry_187.pack(side='right', padx=(2, 0))

        box = ttk.Frame(tab, style='Card.TFrame', padding=4)
        box.pack(fill='both', expand=True, padx=6, pady=(0, 4))
        self.manager_withdraw_table = SmartTable(box, list(MANAGER_RECEIPT_COLUMNS_187), title='')
        self.manager_withdraw_table.pack(fill='both', expand=True)
        legacy_toolbar = next(iter(self.manager_withdraw_table.winfo_children()), None)
        if isinstance(legacy_toolbar, tk.Misc):
            legacy_toolbar.pack_forget()
        self.manager_withdraw_table.set_edit_handler(self._open_manager_record_187)
        self.manager_withdraw_table.set_delete_handler(self._delete_manager_record_187)
        self.manager_withdraw_table._manager_checked_uids187 = set()
        self.manager_withdraw_table.tree.unbind('<Double-1>')
        self.manager_withdraw_table.tree.bind('<Double-1>', self._manager_double_click_187)
        self.manager_withdraw_table.tree.unbind('<Button-1>')
        self.manager_withdraw_table.tree.bind('<Button-1>', self._toggle_manager_checkbox_187, add='+')
        self.manager_withdraw_table.tree.unbind('<Button-3>')
        self.manager_withdraw_table.tree.bind('<Button-3>', self._manager_context_menu_187)
        self.manager_withdraw_table.tree.bind('<<TreeviewSelect>>', self._sync_manager_checkbox_marks_187, add='+')
        self.manager_search_entry_187.configure(textvariable=self.manager_withdraw_table.quick)
        self.manager_search_entry_187.bind('<KeyRelease>', lambda _event: self.manager_withdraw_table.apply_filter(), add='+')

        bottom = tk.Frame(tab, bg=surface)
        # Reserve this summary band before the expanding table, so the three
        # requested totals always remain visible at the bottom of the tab.
        bottom.pack(fill='x', padx=6, pady=(0, 6), before=box)
        for column in range(3):
            bottom.grid_columnconfigure(column, weight=1, uniform='manager-bottom')
        card_defs = (
            ('جمع کل دریافتی', 'manager_receipts', None),
            ('بستانکاری/بدهکاری مدیر بدون احتساب اختلاف حساب', 'before_difference',
             'مثبت = طلبکار (طلب مدیر از پروژه) | منفی = بدهکار (بدهی مدیر به پروژه).'),
            ('بستانکاری/بدهکاری مدیر با احتساب اختلاف حساب', 'with_difference',
             'مثبت = طلبکار (طلب مدیر از پروژه) | منفی = بدهکار (بدهی مدیر به پروژه).'),
        )
        for column, (title, key, tip) in enumerate(card_defs):
            frame = tk.Frame(bottom, bg=panel, highlightbackground=line, highlightthickness=1)
            frame.grid(row=0, column=column, sticky='nsew', padx=2, pady=2)
            label = tk.Label(frame, text=title, bg=panel, fg=muted, font=('Segoe UI', 8, 'bold'), anchor='e')
            label.pack(fill='x', padx=9, pady=(7, 2))
            tk.Label(frame, textvariable=self.manager_summary_vars[key], bg=panel, fg=text_color,
                     font=('Segoe UI', 11, 'bold'), anchor='e').pack(fill='x', padx=9, pady=(1, 8))
            if tip:
                add_tooltip(frame, tip)
                add_tooltip(label, tip)

    def _manager_percent_187(self) -> float:
        return 10.0

    def _manager_receipt_pending_187(self, row):
        """Resolve the posted receipt back to its original Pending record."""
        for pending_id in self._transaction_pending_ids_187(DB, row):
            pending = DB.get_pending_item(pending_id)
            if pending:
                return str(pending_id), dict(pending)
        return '', None

    def _select_data_entry_for_manager_187(self):
        center = getattr(self, 'approval_center', None)
        tab = getattr(self, 'approval_tab', None)
        if tab is not None:
            try:
                self.notebook.select(tab)
            except tk.TclError:
                pass
        return center

    def _manager_add_record_187(self):
        center = self._select_data_entry_for_manager_187()
        if center is not None and hasattr(center, 'manual_transaction'):
            return center.manual_transaction()
        return messagebox.showwarning('ثبت دیتا', 'پنجره ثبت تراکنش در دسترس نیست.', parent=self)

    def _open_manager_record_187(self, row=None):
        row = row or self._one(self.manager_withdraw_table)
        if not row:
            return None
        pending_id, pending = self._manager_receipt_pending_187(row)
        if not pending:
            return messagebox.showwarning(
                'ویرایش دریافتی مدیر',
                'این ردیف Pending اصلی ندارد؛ برای حفظ شناسه، فقط از تب تراکنش‌ها قابل ویرایش است.',
                parent=self,
            )
        center = self._select_data_entry_for_manager_187()
        if center is None or not hasattr(center, 'open_editor'):
            return messagebox.showwarning('ثبت دیتا', 'ویرایشگر ثبت دیتا در دسترس نیست.', parent=self)
        try:
            center.refresh()
        except (tk.TclError, sqlite3.Error):
            pass
        # The editor receives the original Pending row, so saving updates every
        # linked screen through that same pending/transaction identifier.
        return center.open_editor(pending)

    def _manager_edit_selected_187(self):
        return self._open_manager_record_187()

    def _delete_manager_record_187(self, row=None):
        row = row or self._one(self.manager_withdraw_table)
        if not row:
            return None
        if not messagebox.askyesno('حذف', 'ثبت انتخاب‌شده Soft Delete شود؟', parent=self):
            return None
        pending_id, _pending = self._manager_receipt_pending_187(row)
        try:
            if pending_id:
                SERVICE.delete_posting(pending_id)
            else:
                SERVICE.delete_manual_transaction(str(row.get('transaction_id') or ''))
            self.refresh_all()
        except (sqlite3.Error, TypeError, ValueError) as exc:
            messagebox.showerror('حذف', str(exc), parent=self)
        return None

    def _manager_delete_selected_187(self):
        return self._delete_lifecycle_rows187(list(self.manager_withdraw_table.selected_rows() or []))

    def _manager_copy_selected_187(self):
        return self._copy_transaction_187(self.manager_withdraw_table)

    def _export_manager_receipts_187(self):
        selected = str(getattr(self, 'manager_output_var', tk.StringVar()).get() or '')
        table = self.manager_withdraw_table
        if hasattr(self, 'manager_output_var'):
            self.manager_output_var.set('خروجی')
        if selected not in {'PDF', 'Excel', 'پرینت'}:
            return None
        from reports_stage18_7 import _export_through_preview_187, _smarttable_export_rows_187
        headers, rows = _smarttable_export_rows_187(table)
        return _export_through_preview_187(self, selected, headers, rows, 'رسیدهای حساب مدیر')

    def _manager_double_click_187(self, event):
        iid = self.manager_withdraw_table.tree.identify_row(event.y)
        if iid:
            self.manager_withdraw_table.tree.selection_set(iid)
            self.manager_withdraw_table.tree.focus(iid)
            self._open_manager_record_187()
        return 'break'

    def _sync_manager_checkbox_marks_187(self, _event=None):
        table = self.manager_withdraw_table
        checked = getattr(table, '_manager_checked_uids187', set())
        checked.clear()
        for iid in table.tree.selection():
            row = getattr(table, '_iid_to_row', {}).get(iid)
            if row:
                checked.add(table._row_uid(row))
        for iid in table.tree.get_children():
            row = getattr(table, '_iid_to_row', {}).get(iid)
            values = list(table.tree.item(iid, 'values') or ())
            if row and values:
                values[0] = f"{'☑' if table._row_uid(row) in checked else '☐'} {fa(row.get('_manager_row_no187') or 0)}"
                table.tree.item(iid, values=values)

    def _toggle_manager_checkbox_187(self, event):
        table = self.manager_withdraw_table
        if table.tree.identify_column(event.x) != '#1':
            return None
        iid = table.tree.identify_row(event.y)
        if not iid:
            return 'break'
        selected = set(table.tree.selection())
        if iid in selected:
            selected.remove(iid)
        else:
            selected.add(iid)
        table.tree.selection_set(tuple(selected))
        if selected:
            table.tree.focus(iid)
        self._sync_manager_checkbox_marks_187()
        return 'break'

    def _manager_context_menu_187(self, event):
        table = self.manager_withdraw_table
        iid = table.tree.identify_row(event.y)
        if iid:
            if iid not in table.tree.selection(): table.tree.selection_set(iid)
            table.tree.focus(iid)
        menu = tk.Menu(table, tearoff=0)
        menu.add_command(label='افزودن', command=self._manager_add_record_187)
        menu.add_command(label='ویرایش', command=self._manager_edit_selected_187)
        menu.add_command(label='حذف', command=self._manager_delete_selected_187)
        menu.add_command(label='کپی', command=self._manager_copy_selected_187)
        menu.add_command(label='بروزرسانی', command=self.refresh_all)
        self._right_align_financial_menu_187(menu)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def refresh_manager(self):
        """Refresh the ledger-backed manager table and session-only calculation."""
        try:
            snapshot = DB.snapshot()
            cash = int(snapshot.cash_balance)
            if not self._manager_actual_cash_initialized_187:
                self.manager_actual_cash_var.set(fa(f'{cash:,}'))
                self._manager_actual_cash_initialized_187 = True
            actual_cash = parse_int(self.manager_actual_cash_var.get() or cash)
            reconciliation = DB.petty_cash_reconciliation(actual_cash)
            percent = self._manager_percent_187()
            values = manager_account_summary_187(
                construction_cost=DB.construction_cost() + DB.land_purchase_cost(),
                land_purchase_cost=DB.land_purchase_cost(),
                manager_receipts=DB.manager_withdrawals(),
                transaction_cash=cash,
                actual_cash=actual_cash,
                manager_percent=percent,
                expected_petty_cash=reconciliation['expected_cash'],
            )
            for key, variable in self.manager_summary_vars.items():
                if key in values:
                    variable.set(fa(f"{int(values[key]):,}"))
            self.manager_formula_var.set(_manager_formula_text_187(values, percent, reconciliation))
            self.manager_status_var.set('محاسبه شد؛ این محاسبه هیچ داده یا تنظیمی را تغییر نمی‌دهد.')
            with DB.read() as connection:
                rows = [dict(row) for row in connection.execute(
                    """SELECT transaction_id, shamsi_date, amount, description FROM transactions
                       WHERE category='CONTRACTOR_FEE' AND direction='OUT'
                         AND status='POSTED' AND deleted_at IS NULL
                       ORDER BY event_date DESC, created_at DESC"""
                ).fetchall()]
            for number, row in enumerate(rows, 1):
                row['_sum_amount'] = int(row.get('amount') or 0)
                row['_manager_row_no187'] = number
            self.manager_withdraw_table.set_rows(
                rows,
                lambda row: [f"☐ {fa(row.get('_manager_row_no187') or 0)}",
                             row.get('shamsi_date') or '-', money(row.get('amount') or 0),
                             row.get('description') or '-'],
            )
        except (sqlite3.Error, TypeError, ValueError) as exc:
            self.manager_status_var.set(f'خطا در محاسبه حساب مدیر: {exc}')
    def refresh_overview(self):
        super().refresh_overview()
        self._thirty_day_summary187 = self._thirty_day_summary_187()
        summary = self._thirty_day_summary187
        try:
            card_values = {
                'liq_obligation': summary['commitments'] + summary['cheques'] + summary['installments'],
                'liq_inflow': summary['claims'],
                'liq_projected': summary['balance'],
                'sales_30': summary['claims'],
                'loan_30': summary['installments'],
            }
            for key, value in card_values.items():
                self.cards[key].var.set(fa(f"{int(value):,}"))
        except (KeyError, TypeError, ValueError):
            pass

        # A count is a count, not an amount; its display must not include فقره.
        try:
            self.cards['ch30_count'].var.set(fa(f"{int(SERVICE.cheque_30d_summary(30)['count']):,}"))
        except (KeyError, TypeError, ValueError):
            pass
        self._refresh_plan_charts_187()
        if getattr(self, 'messages_text187', None):
            self._refresh_message_count_187()

    def _refresh_plan_charts_187(self):
        """Build both phase charts from one fresh ``پلان کلی`` snapshot.

        The bar chart displays the source amount for each phase.  The line
        chart intentionally displays its running total, but each point is
        calculated only from those exact same source amounts rather than from
        a previously populated canvas series.
        """
        phases = list(self._phase_summary_live())
        estimate_total = actual_total = current_total = 0
        estimate_series = []
        actual_series = []
        current_series = []
        bar_rows = []
        for row in phases:
            estimate = int(row.get('estimate') or 0)
            actual = int(row.get('actual') or 0)
            current = int(row.get('forecast') or 0)
            estimate_total += estimate
            actual_total += actual
            current_total += current
            estimate_series.append(estimate_total)
            actual_series.append(actual_total)
            current_series.append(current_total)
            bar_rows.append((
                f"{int(row.get('phase_no') or 0):02d}", estimate, actual, current,
            ))
        if getattr(self, 'liquidity_chart', None) is not None:
            self.liquidity_chart.set_series([
                ('برآورد', estimate_series, 'orange'),
                ('واقعی', actual_series, 'green'),
                ('بروز', current_series, 'blue'),
            ])
        if getattr(self, 'phase_chart', None) is not None:
            self.phase_chart.set_rows(bar_rows)

    def refresh_phase_strip(self):
        """Repaint the ۳۲-phase strip with the theme's own tokens.

        The inherited version (dashboard_stage16_3) hardcoded four dark-only
        hex pairs, so a light-theme user saw the same four colours the dark
        theme uses - never matching the rest of a light screen. It also mixed
        numeral systems: Persian digits at build time, plain Latin ones the
        moment this method first repainted them. barkav_themes/tokens.py
        already carries phase_not_started/active/paused/completed for
        exactly this state, in both theme modes; this just reads them
        instead of relying on inherited literals never wired to figure them.
        """

        p = palette_187()
        prog = self.rich.get_phase_progress()
        colors = {
            'NOT_STARTED': (p['phase_not_started'], p['muted']),
            'ACTIVE': (p['phase_active'], p['text_primary']),
            'PAUSED': (p['phase_paused'], p['text_primary']),
            'COMPLETED': (p['phase_completed'], p['text_primary']),
        }
        for number, button in getattr(self, 'phase_buttons', {}).items():
            info = prog.get(number, {})
            status = info.get('status', 'NOT_STARTED')
            percent = float(info.get('physical_progress') or 0)
            bg, fg = colors.get(status, colors['NOT_STARTED'])
            tail = fa(f'{percent:.0f}%') if percent else ''
            button.configure(bg=bg, fg=fg, text=f"{fa(f'{number:02d}')}\n{tail}")
        self.overall_progress.set(self.rich.overall_physical_progress())
        self._refresh_phase_groups_187()

    def refresh_reports(self):
        super().refresh_reports()
        self._apply_financial_report_theme_187()
        inventory = getattr(self, 'inventory_panel187', None)
        if inventory is not None:
            inventory.refresh()
        self._install_brand_logo_187()
        self.after(260, self._round_shell_bars_187)
        self.unify_appearance_187()
        # The project-plan editor calls ``refresh_reports`` after its save.
        # Refresh the three dashboard charts in the same turn so their plan
        # backed totals never wait for an application restart.
        self.refresh_overview()
        try:
            version = SERVICE.budget.latest_version()
            if version:
                created = str(version.get('created_at') or '').replace('T', ' ')[:16]
                self.budget_version.set(
                    f"نسخه برآورد: {fa(version.get('version_no'))} — "
                    f"{version.get('title')} — {fa(created)}"
                )
        except Exception:
            pass

    def _install_brand_logo_187(self, background: str | None = None):
        """Swap the inherited brand strip for the supplied BARKAV mark.

        The artwork ships as dark ink on white with no alpha, so it is keyed
        and re-tinted to the theme rather than pasted as-is.
        """
        host = getattr(self, '_brand_host_186', None)
        if host is None or not host.winfo_exists():
            return
        p = palette_187()
        ground = background or p['surface']
        # The size it always had: the mark spans both of the bar's rows and
        # sits centred in its full height.
        image = art.logo(height=44, background=ground, drop_tagline=True,
                         wordmark_scale=1.3, align_wordmark=True,
                         colour=p['text_primary'], master=self)
        if image is None:
            return
        for child in host.winfo_children():
            child.destroy()
        self._brand_logo_image187 = image
        host.configure(bg=ground)
        # expand: the holder is as tall as the bar, and the mark is centred in it.
        tk.Label(host, image=image, bg=ground, bd=0).pack(padx=2, pady=0, expand=True)
        try:
            # At the bar's left end (operator round 2026-09-27); the window
            # tabs start from the right.
            host.pack_configure(side='left', padx=(14, 6))
        except tk.TclError:
            pass

    def _find_tree_187(self, widget):
        """First Treeview under a widget, breadth-first."""
        queue = [widget]
        while queue:
            current = queue.pop(0)
            if isinstance(current, ttk.Treeview):
                return current
            try:
                queue.extend(current.winfo_children())
            except tk.TclError:
                pass
        return None

    def _finalize_187(self):
        p = palette_187()
        self.configure(bg=p['bg'])
        self._install_inline_errors_187()
        self._install_breadcrumb_187()
        self._install_late_widget_hooks_187()
        # Restore the approved mark after inherited startup hooks.
        # Header setup must not depend on the reports refresh completing.
        self._install_brand_logo_187()
        # Theme the main window's native caption too, so it matches the
        # dialogs instead of staying the default light Windows bar.
        apply_dark_caption(self)
        self._decorate_top_187()
        self._restyle_dashboard_187()
        self._install_chart_details_187()
        self._round_overview_containers_187()
        self._ensure_physical_progress_card_187()
        self._install_kpi_cards_187()
        self._install_phase_groups_187()
        self._install_dashboard_links_187()
        self._install_window_normaliser_187()
        self._upgrade_tables_184(self)
        self.unify_appearance_187()
        self._apply_financial_report_theme_187()
        try:
            # The approved brand mark is the 18.4 artwork referenced by the
            # 18.6 correction document. Keep the versioned reference explicit.
            self.iconbitmap(default=str(BASE_DIR / 'assets' / 'BARKAV_18_4.ico'))
        except Exception:
            pass
        self._barkav_main_appearance_ready187 = True

    def export_development_package(self):
        destination = filedialog.asksaveasfilename(
            parent=self, defaultextension='.zip',
            initialfile='BARKAV_Development_Package_18.7.zip',
            filetypes=[('ZIP', '*.zip')],
        )
        if not destination:
            return
        try:
            from development_package_v187 import build_development_package
            result = build_development_package(BASE_DIR, Path(destination), VERSION)
            messagebox.showinfo(
                'ذخیره بسته توسعه',
                f"بسته توسعه {VERSION} ذخیره شد:\n{result['path']}\n\n"
                'دیتابیس زنده، لاگ و فایل محرمانه وارد بسته نشده‌اند.',
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror('ذخیره بسته توسعه', str(exc), parent=self)


# The actual Tk submission entry point, covering every title/subtype.
_ORIGINAL_LIFECYCLE_SUBMIT_187 = v18.submit_v18

def _confirm_debt_warning_187(form, payload):
    """Ask before posting, while no SQLite transaction is held open."""
    if payload.get('v18_title') != LAND_TITLE:
        return True
    from land_purchase187 import debt_warning, debt_signature
    warning = debt_warning(payload, parse_int)
    if not warning:
        payload.pop('land_debt_override187', None)
        return True
    warning += (f"\nکل بدهی: {v18._group_money(parse_int(payload.get('total_debt') or 0))}"
                f"\nمجموع پرداخت‌ها: {v18._group_money(sum(parse_int(payload.get(key) or 0) for key in LAND_PARTS))}")
    from barkav_ui.messages import MessageDialog
    dialog = MessageDialog(form, 'هشدار مبلغ بدهی', warning, kind='warning', buttons=(
        ('اصلاح تراکنش', False, 'Primary.TButton'),
        ('نادیده گرفتن و ثبت تراکنش', True, 'Toolbar.TButton')))
    dialog.wait_window()
    if dialog.result is True:
        payload['land_debt_override187'] = debt_signature(payload, parse_int)
        return True
    # Keep the draft open. A correction never changes the stored row's status.
    key = 'amount' if payload.get('payment_state') == 'PAID' else 'total_debt'
    if key == 'amount' and land_payment_subtype(payload) != 'نقدی':
        key = {'چک': LAND_PARTS[1], 'معاوضه': LAND_PARTS[2]}.get(land_payment_subtype(payload), LAND_PARTS[0])
    if isinstance(form, v182.TransactionWizard182):
        form.page_index = next((index for index, page in enumerate(form.pages)
                                if any(field.key == key for field in page)), 0)
        form._show_page()
    widget = form.widgets.get(key)
    if widget is not None:
        widget.focus_set()
    return False


def _single_cheque_payload_187(payload):
    """One cheque record is one cheque. A one-element list the receipt reader left on the payload only
    repeats the cheque's own fields (stale ones, once the record has been edited) and would send the
    approval down the older bundle route: no expense, and a second cheque row on every edit. The record's
    own fields win; the element only fills what the record leaves blank."""
    cheques = payload.get('cheques')
    if not isinstance(cheques, list) or len(cheques) > 1 or payload.get('is_guarantee'):
        return payload
    payload = dict(payload)
    payload.pop('cheques', None)
    for key, value in (cheques[0] if cheques and isinstance(cheques[0], dict) else {}).items():
        if payload.get(key) in (None, ''):
            payload[key] = value
    return payload


def _lifecycle_submit_187(pid, payload, rich):
    title, subtype = v18._title_type_from_payload(payload)
    if _is_cheque_resolution_187(title, subtype, payload):
        return _approve_cheque_resolution_187(pid, payload)
    if title == 'هزینه ساخت' and subtype == 'چک':
        payload = _single_cheque_payload_187(payload)
    if payload.get("v18_title") == MANAGER_TITLE or payload.get("transaction_title") == MANAGER_TITLE:
        payload = normalize_manager_salary(payload)
    if payload.get('v18_title') == LAND_TITLE or payload.get('transaction_title') == LAND_TITLE:
        payload = normalize_land_parts(payload, parse_int)
    payload = _carry_debt_187(pid, payload)
    title, subtype = v18._title_type_from_payload(payload)
    if title == 'هزینه ساخت' and subtype == 'چک' and not payload.get('is_guarantee'):
        # A construction invoice accrues its cost now; the cheque moves cash
        # only when cleared. Guarantee cheques keep their nonfinancial route.
        payload.update(detected_type='EXPENSE', is_cheque=True, payment_method='CHEQUE')
    elif title == 'یادداشت':
        payload.update(amount=0, paid_amount=0, final_amount=0)
        # All document edits now use the original source record lifecycle.
        payload.pop('_document_edit_id_187', None)
    from transaction_lifecycle import TransactionLifecycle
    import row_journal
    with row_journal.suspended():
        lifecycle = TransactionLifecycle(DB)
        if title == LAND_TITLE:
            from land_purchase187 import approve as approve_land
            return lifecycle.run(str(pid), lambda: approve_land(DB, str(pid), payload,
                parse_amount=parse_int, normalize_date=normalize_shamsi, to_gregorian=shamsi_to_gregorian),
                replace=True)
        prior = lifecycle.get(str(pid))
        replace_land = bool(prior and json.loads(prior['payload_json']).get('v18_title') == LAND_TITLE)
        def submit():
            if replace_land:
                # The original revision API requires an active posting. Its
                # expense/payment objects have just been reversed by the
                # lifecycle; revision rebuilds them inside this same SQL unit.
                post = DB.get_financial_posting(str(pid))
                if post:
                    with DB.tx() as con:
                        con.execute("UPDATE financial_postings SET status='ACTIVE',deleted_at=NULL WHERE pending_id=?", (str(pid),))
            posted = payload
            if DB._session_state().get('revive_cheques'):
                # The cheque is posted again on its old row; the status a resolution gave it is put
                # back by the lifecycle afterwards, so the posting itself starts from «صادرشده».
                posted = {**payload, 'cheque_status': 'ISSUED'}
            return _ORIGINAL_LIFECYCLE_SUBMIT_187(pid, posted, rich)
        return lifecycle.run(str(pid), submit, replace=replace_land)

v18.submit_v18 = _lifecycle_submit_187

from transaction_lifecycle_ui import install_runtime as _install_transaction_lifecycle_187
_install_transaction_lifecycle_187(Stage187Dashboard, DataEntryCenter187,
    v182.UnifiedPendingEditor182, sys.modules[__name__])

# «انتقال به دردست بررسی» goes on the menus the lifecycle installed just above.
from transaction_review_ui import install as _install_review_return_187
_install_review_return_187(Stage187Dashboard, DataEntryCenter187, sys.modules[__name__])

# «رفتن به رکورد متناظر» on the Transactions tables and «حذف‌شده‌ها» on Data Entry's menu.
from data_entry_extras_ui import install as _install_data_entry_extras_187
_install_data_entry_extras_187(Stage187Dashboard, DataEntryCenter187, sys.modules[__name__])

def run_dashboard_187() -> None:
    DB.__class__.enforce_record_context = True  # RED LINE: no financial row without a record (record_ownership187)
    app = Stage187Dashboard()
    app.mainloop()


if __name__ == '__main__':
    run_dashboard_187()
