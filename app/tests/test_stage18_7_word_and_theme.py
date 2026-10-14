from __future__ import annotations

import os
import hashlib
import inspect
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'stage187.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'reg187-token')
os.environ.setdefault('GEMINI_API_KEY', 'reg187-gemini')
os.environ.setdefault('ADMIN_USER_ID', '187')
os.environ.setdefault('GROUP_CHAT_ID', '-100187')

import dashboard_stage18_7 as d187
from barkav_themes.tokens import THEME_1, THEME_2, THEMES
from financial_calendar_stage18_7 import collect_financial_events_187
import ui_stage18_7 as ui187

def test_settings_rates_are_grouped_solar_hijri_and_close_after_save():
    assert d187._rate_timestamp_label_187('2026-09-13T03:30:45') == '۱۴۰۵/۰۶/۲۲ ۰۳:۳۰:۴۵'
    save_source = inspect.getsource(d187.SettingsTab187.save)
    assert 'numeric_keys' in save_source
    assert 'group_int_fa(parsed, blank_zero=True)' in save_source
    assert 'data[key] = parsed' in save_source
    settings_source = inspect.getsource(d187.SettingsTab187._build)
    assert "ttk.Entry(box, textvariable=value, justify='right')" in settings_source
    callback_source = inspect.getsource(d187.Stage187Dashboard._settings_saved)
    assert 'window.destroy()' in callback_source
    assert 'self.settings_window187 = None' in callback_source


def test_thirty_day_liquidity_keeps_cash_separate_from_net_commitment_balance():
    breakdown = d187.thirty_day_liquidity_breakdown_187(
        claims=1_000, commitments=200, cheques=300, installments=100, cash=500,
    )

    assert breakdown['balance'] == 400
    assert breakdown['cash'] == 500
    assert breakdown['liquidity_needed'] == 900

    shortage = d187.thirty_day_liquidity_breakdown_187(
        claims=100, commitments=500, cheques=200, installments=100, cash=300,
    )
    assert shortage['balance'] == -700
    assert shortage['liquidity_needed'] == -400



def test_187_is_an_isolated_overlay_and_keeps_186_intact():
    assert d187.VERSION == '18.7'
    assert d187.Stage187Dashboard.__mro__[1].__name__ == 'Stage186Dashboard'
    assert (ROOT / 'dashboard_stage18_6.py').is_file()
    assert (ROOT / 'BARKAV_18.6.bat').is_file()
    assert not (ROOT / 'finance_db_stage18_7.py').exists()
    # VERSION.txt tracks the real product version and moves on; d187.VERSION
    # above is a separate, unrelated stage-tag constant on this overlay
    # module and correctly stays '18.7' - same distinction this exact
    # assertion was updated for once before (see docs/HANDOFF.md entry 8,
    # 18.7 -> 19.0), moving again now (19.0.0 -> 19.1.1).
    assert (ROOT / 'VERSION.txt').read_text(encoding='utf-8').strip() == '19.1.1'
    assert not (ROOT / 'secrets.local.json').exists()
    from release_builder_v187 import include_file
    assert include_file(ROOT, ROOT / 'runtime' / 'sample.log') is False


def test_two_theme_contract_and_legacy_theme_one_snapshot():
    # Three display modes now: theme 1 is the frozen 18.6 look, theme 2 the
    # default, theme 3 the vivid mode reachable from the footer control.
    assert set(THEMES) == {1, 2, 3}
    assert THEME_1.dark['bg'] == '#091423'
    assert THEME_1.light['panel'] == '#FFFFFF'
    assert THEME_2.dark['bg'] == '#0E141B'
    assert THEME_2.dark['cyan'] == '#4FD1E0'
    assert THEME_2.light['line'] == '#D9DFE6'


def test_dark_accents_sit_above_the_mid_point_and_light_ones_below():
    """An accent has to contrast with its own ground to read as lit.

    The first theme-2 pass put dark-mode accents at 40-56% lightness, below
    the mid point, and the screens looked switched off. This pins the rule
    rather than the particular colours: on dark grounds accents are lighter
    than mid, on light grounds darker, and none of them are washed out.
    """
    import colorsys

    def lightness_and_saturation(value):
        r, g, b = (int(value.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4))
        _hue, light, sat = colorsys.rgb_to_hls(r, g, b)
        return light * 100, sat * 100

    accents = ('blue', 'cyan', 'green', 'yellow', 'orange', 'red', 'violet')
    for spec in (THEME_2, THEMES[3]):
        for key in accents:
            light, sat = lightness_and_saturation(spec.dark[key])
            assert light > 50, f'{spec.theme_id} dark {key} is too dark: {light:.0f}%'
            assert sat > 45, f'{spec.theme_id} dark {key} is washed out: {sat:.0f}%'
            light, sat = lightness_and_saturation(spec.light[key])
            assert light < 55, f'{spec.theme_id} light {key} is too pale: {light:.0f}%'
            assert sat > 45, f'{spec.theme_id} light {key} is washed out: {sat:.0f}%'


def test_theme_palettes_expose_central_semantic_tokens_for_dashboard_styles():
    expected = {
        'surface_alt', 'border', 'border_subtle', 'text_primary',
        'text_secondary', 'text_muted', 'accent', 'info', 'success',
        'warning', 'danger', 'on_accent', 'on_warning',
    }
    for spec in (THEME_1, THEME_2):
        for mode in ('dark', 'light'):
            palette = spec.palette(mode)
            assert expected <= set(palette)
            assert palette['text_primary'] != palette['bg']
            assert palette['border_subtle'] != palette['bg']
            assert {'on_accent', 'text_primary'} <= set(ui187.palette_187(mode == 'light'))


def test_ui_contract_tokens_exist_and_hold_their_invariants():
    """Guards docs/theme_18_7/BARKAV_UI_CONTRACT.md sections 2, 3, 5, 10 and 12."""
    required = {
        'nav_indicator', 'tab_indicator', 'grid_h', 'grid_v', 'focus_ring',
        'row_pending', 'row_approved', 'row_rejected',
        'dialog_header', 'dialog_footer', 'toast_bg',
        'disabled_bg', 'disabled_fg',
    }
    for spec in (THEME_1, THEME_2):
        for mode in ('dark', 'light'):
            palette = spec.palette(mode)
            assert required <= set(palette)
            # Section 5: the vertical column rule is always softer than the
            # horizontal row rule, never the same weight and never stronger.
            assert palette['grid_v'] != palette['grid_h']
            assert palette['grid_v'] == palette['line_soft']
            assert palette['grid_h'] == palette['line']
            # Section 5: a status tint is a low-alpha wash over the stripe
            # colour, so it must differ from both the stripe and the raw hue.
            for tint, hue in (
                ('row_pending', 'yellow'),
                ('row_approved', 'green'),
                ('row_rejected', 'red'),
            ):
                assert palette[tint] not in (palette['row_even'], palette[hue])
            # Sections 2 and 3: one accent drives every active-tab indicator.
            assert palette['nav_indicator'] == palette['accent']
            assert palette['tab_indicator'] == palette['accent']
            # Section 12: a toast floats over arbitrary content, so it must be
            # readable against the page even in the flat light modes.
            assert palette['toast_bg'] not in (palette['bg'], palette['panel'])


def test_shared_table_rows_keep_alternating_stripes_and_semantic_statuses():
    from barkav_themes.engine import stripe_tree

    class TreeProbe:
        def __init__(self):
            self.tags = {}

        def tag_configure(self, name, **values):
            self.tags[name] = values

    tree = TreeProbe()
    stripe_tree(tree)
    assert tree.tags['even']['background'] != tree.tags['odd']['background']
    assert tree.tags['approved']['background'] != tree.tags['even']['background']
    source = (ROOT / 'dashboard_stage18_7.py').read_text(encoding='utf-8')
    assert "tree.tag_configure('odd', background=stripe_odd" in source
def test_phase_strip_has_true_rounded_controls_and_a_status_legend():
    source = (ROOT / 'dashboard_stage18_7.py').read_text(encoding='utf-8')
    assert 'class RoundedPhaseButton187(tk.Canvas)' in source
    assert "_DRAW_TAG = '_phase_button_plate187'" in source
    assert 'self._replace_phase_buttons_with_rounded_187()' in source
    assert 'راهنما: سبز = فعال/تکمیل' in source
    assert 'def refresh_phase_strip(self):' in source


def test_phase_detail_uses_the_exact_plan_columns_and_shared_toolbar_contract():
    from project_plan_stage18_7 import PLAN_COLUMNS
    from reports_stage18_7 import PHASE_DETAIL_PLAN_COLUMNS_187

    assert [(key, label) for key, label, _width in PHASE_DETAIL_PLAN_COLUMNS_187] == list(PLAN_COLUMNS)
    source = (ROOT / 'reports_stage18_7.py').read_text(encoding='utf-8')
    assert 'def _configure_plan_columns_187' in source
    assert 'def phase_detail_plan_values_187' in source
    assert 'def _standardise_smarttable_toolbar_187' in source
    assert 'PHASE_SUMMARY_PLAN_LABELS_187' in source
    assert 'PHASE_SUMMARY_VISIBLE_COLUMNS_187' in source
    assert "PHASE_SUMMARY_VISIBLE_COLUMNS_187 = ('no', 'phase', 'est', 'fc', 'actual')" in source
    assert 'def _set_phase_table_rtl_187' in source
    assert 'def _span_phase_horizontal_scrollbar_187' in source
    assert "horizontal.grid(row=1, column=0, columnspan=2, sticky='ew')" in source
    assert 'tree.xview_moveto(1.0)' in source
    assert "('افزودن', open_selected_phase)" in source
    assert "('ویرایش', open_selected_phase)" in source
    assert "('حذف', open_selected_phase)" in source
    assert "('افزودن ریز'" not in source
    assert "('ویرایش ریز'" not in source
    assert "('حذف ریز'" not in source
    assert "ttk.Label(toolbar, text='جستجو:').pack(side='right')" in source
    assert 'self._install_phase_navigation()' not in source
    assert 'self._install_phase_navigation_187()' in source
    assert 'def _navigate_phase_187' in source
    assert "text='فاز قبلی'" in source
    assert "text='فاز بعدی'" in source
    context = source[source.index('    def _phase_context_menu_187'):source.index('class PriceEditor187')]
    for label in ('افزودن', 'ویرایش', 'حذف', 'کپی'):
        assert label in context
    assert 'پیست در فیلتر' not in context
    assert "('افزودن', self.add_item)" in source
    assert "('ویرایش', lambda: self.edit_item(self.one()))" in source
    assert "('حذف', lambda: self.delete_item(self.one()))" in source
    assert "('کپی', table.copy_selected)" in source
    assert 'self.resizable(True, True)' in source


def test_phase_detail_rows_use_the_same_rates_quantities_and_totals_as_plan():
    from project_plan_stage18_7 import PLAN_COLUMNS, _money, _number, _quantities, _rates, _totals
    from reports_stage18_7 import phase_detail_plan_values_187

    row = {
        'plan_ref': '۱۲', 'category': 'MATERIAL', 'code': 7,
        'description': 'سیمان', 'phase_no': 3, 'unit': 'کیسه',
        'estimate_rate': 100, 'forecast_rate': 120, 'actual_rate': 110,
        'qty_estimate': 2, 'qty_forecast': 3, 'qty_actual': 1,
        'factor': 2, 'total_actual': 150,
    }
    values = phase_detail_plan_values_187(row)

    assert len(values) == len(PLAN_COLUMNS)
    assert values[2] == 'سیمان'
    assert values[3] == '۰۳'
    assert values[4] == 'کیسه'
    assert values[5:8] == [_money(value) for value in _rates(row)]
    assert values[8:11] == [_number(value) for value in _quantities(row)]
    assert values[11:14] == [_money(value) for value in _totals(row)]


def test_active_dashboard_uses_shared_font_resolver_and_semantic_chart_tokens():
    source = (ROOT / 'dashboard_stage18_7.py').read_text(encoding='utf-8')
    assert 'def dashboard_font_187' in source
    assert 'font=dashboard_font_187' in source
    assert "p['text_primary']" in source
    assert "p['border_subtle']" in source
    assert "p['on_accent']" in source


def test_dashboard_visual_layer_owns_cards_tables_and_all_three_chart_styles():
    source = (ROOT / 'dashboard_stage18_7.py').read_text(encoding='utf-8')
    for name in ('apply_donut_theme_187', 'apply_line_theme_187', 'apply_bar_theme_187', '_restyle_dashboard_187'):
        assert f'def {name}' in source
    assert 'stripe_tree(widget, theme_selection_187())' in source
    assert 'metric.value_label.configure' in source
    assert 'self._restyle_dashboard_187()' in source


def test_approved_184_brand_mark_is_explicit_and_packaged():
    header = ROOT / 'assets' / 'barkav_brand_header.png'
    icon = ROOT / 'assets' / 'BARKAV_18_4.ico'
    assert hashlib.sha256(header.read_bytes()).hexdigest() == (
        '413368e2e0d2dc2f0791c3abc45e7249d3e872a7b74c43c61b0839995a1a93a9'
    )
    assert hashlib.sha256(icon.read_bytes()).hexdigest() == (
        'e3f0ac01606902d94ee279a318cd127024f3c31063f42a3963369753086a1f3a'
    )
    source = (ROOT / 'dashboard_stage18_7.py').read_text(encoding='utf-8')
    assert "BARKAV_18_4.ico" in source


def test_theme_selection_is_ui_only_and_falls_back_safely(monkeypatch):
    monkeypatch.setattr(ui187, 'load_ui', lambda: {'theme_id': 2, 'appearance': 'light'})
    assert ui187.theme_id_187() == 2
    assert ui187.palette_187()['bg'] == THEME_2.light['bg']
    # Theme 2 is the product default, so both an unset and an unusable stored
    # value resolve to it. Theme 1 stays selectable, just not automatic.
    monkeypatch.setattr(ui187, 'load_ui', lambda: {'theme_id': 'bad', 'appearance': 'dark'})
    assert ui187.theme_id_187() == ui187.DEFAULT_THEME_ID_187 == 2
    monkeypatch.setattr(ui187, 'load_ui', lambda: {'appearance': 'dark'})
    assert ui187.theme_id_187() == 2
    monkeypatch.setattr(ui187, 'load_ui', lambda: {'theme_id': 1, 'appearance': 'dark'})
    assert ui187.theme_id_187() == 1


def test_light_background_preference_is_a_ttk_token_override(monkeypatch):
    monkeypatch.setattr(ui187, 'load_ui', lambda: {
        'theme_id': 2, 'appearance': 'light', 'background_color': 'سبزآبی',
    })
    palette = ui187.palette_187()
    assert palette['bg'] == ui187.BACKGROUND_COLORS_187['سبزآبی']['light']
    engine = (ROOT / 'barkav_themes' / 'engine.py').read_text(encoding='utf-8')
    assert 'palette_override' in engine
    assert 'p.update(palette_override)' in engine
    style_source = inspect.getsource(ui187.style_ttk_187)
    assert 'palette_override=palette_187(light)' in style_source


def test_contract_selector_is_visible_only_for_contractor_costs():
    class FakeVar:
        def __init__(self, value):
            self.value = value
        def get(self):
            return self.value
        def set(self, value):
            self.value = value

    class FakeBox:
        def __init__(self):
            self.visible = True
        def grid(self):
            self.visible = True
        def grid_remove(self):
            self.visible = False

    class FakeSelector:
        def __init__(self, box):
            self.master = box

    box = FakeBox()
    form = type('Form', (), {
        'vars': {'cost_group': FakeVar('مصالح'), 'contract_id': FakeVar('C-1')},
        'widgets': {'contract_id': FakeSelector(box)},
    })()
    d187._sync_contract_selector_visibility_187(form)
    assert not box.visible
    assert form.vars['contract_id'].get() == ''
    form.vars['cost_group'].set('پیمانکار')
    d187._sync_contract_selector_visibility_187(form)
    assert box.visible


def test_chat_backup_uses_the_active_data_entry_reprocess_pipeline(monkeypatch):
    seen = []

    class FakeDB:
        @staticmethod
        def get_pending_item(pending_id):
            return {'pending_id': pending_id} if pending_id == 'ok' else None

    class FakeCenter:
        def reprocess_rows(self, rows):
            seen.extend(rows)
            return 'queued'

    monkeypatch.setattr(d187, 'DB', FakeDB())
    assert d187.DataEntryCenter187._run_ai_ids(FakeCenter(), ['ok', 'missing']) == 'queued'
    assert seen == [{'pending_id': 'ok'}]


def test_manager_account_summary_keeps_the_agreed_signs_and_basis():
    summary = d187.manager_account_summary_187(
        construction_cost=1_000_000,
        land_purchase_cost=200_000,
        manager_receipts=100_000,
        transaction_cash=500_000,
        actual_cash=530_000,
        manager_percent=10,
    )
    assert summary['eligible_costs'] == 800_000
    assert summary['manager_fee'] == 80_000
    assert summary['before_difference'] == -20_000
    assert summary['account_difference'] == -30_000
    assert summary['with_difference'] == 10_000

def test_manager_workspace_uses_the_compact_receipts_toolbar_and_pending_editor_route():
    assert d187.MANAGER_RECEIPT_COLUMNS_187 == (
        ('row', 'ردیف', 78), ('date', 'تاریخ شمسی', 125),
        ('amount', 'مبلغ (تومان)', 175), ('desc', 'توضیحات', 420),
    )
    source = (ROOT / 'dashboard_stage18_7.py').read_text(encoding='utf-8')
    assert 'کل هزینه‌های مشمول حقوق مدیر =' in source
    assert "card(0, 'کل هزینه‌های مشمول حقوق مدیر (تومان)', self.manager_summary_vars['eligible_costs'])" in source
    assert "bottom.pack(fill='x', padx=6, pady=(0, 6), before=box)" in source
    assert 'دریافتی‌های مدیر' in source
    assert "('افزودن', command=self._manager_add_record_187" not in source
    for method in (
        '_manager_add_record_187', '_manager_edit_selected_187',
        '_manager_delete_selected_187', '_manager_copy_selected_187',
        '_manager_context_menu_187', '_open_manager_record_187',
    ):
        assert f'def {method}' in source
    assert 'center.open_editor(pending)' in source
    assert "('row', 'ردیف', 78)" in source
    assert "('date', 'تاریخ شمسی', 125)" in source
    assert "('amount', 'مبلغ (تومان)', 175)" in source
    assert "('desc', 'توضیحات', 420)" in source
    assert "text='بروزرسانی'" not in source[source.index('    def _build_manager(self):'):source.index('    def refresh_overview(self):')]


def test_transactions_and_manager_report_use_the_active_font_theme_bridge():
    source = (ROOT / 'dashboard_stage18_7.py').read_text(encoding='utf-8')
    assert 'def _apply_financial_report_theme_187' in source
    assert "notebook.configure(style='Barkav.Data.TNotebook')" in source
    for name in (
        'all_tx_table', 'exp_table', 'cheque_table', 'in_table', 'out_table',
        'loan_table', 'document_table', 'manager_withdraw_table', 'manager_metrics',
    ):
        assert repr(name) in source
    assert "tree.configure(style='Barkav.Data.Treeview')" in source
    assert 'self._apply_financial_report_theme_187()' in inspect.getsource(d187.Stage187Dashboard._apply_settings_live_187)


def test_shell_file_menu_footer_and_theme_controls_are_owned_by_187():
    shell = inspect.getsource(d187.Stage187Dashboard._install_shell_187)
    file_menu = inspect.getsource(d187.Stage187Dashboard._show_file_menu_187)
    theme = inspect.getsource(d187.Stage187Dashboard._set_theme_mode_187)
    assert "('ذخیره', self.manual_save)" in file_menu
    assert "('ذخیره با نام', self.save_as)" in file_menu
    assert "('ذخیره بسته توسعه', self.export_development_package)" in file_menu
    assert "('تنظیمات', self.open_settings_187)" in file_menu
    assert "('سیستم', lambda: self._select_tab_text('سیستم'))" in file_menu
    # Operator-approved D1 (2026-09-27): the File menu is the product's own
    # drop-down - the kit PopupMenu, a line icon per row, in two groups -
    # opening under a labelled «فایل» button, like the theme and export menus.
    assert 'PopupMenu(' in file_menu
    assert "sections = [('برنامه', items[2:])]" in file_menu
    assert "sections.insert(0, ('پروژه', items[:2]))" in file_menu
    assert 'self._theme_menu_sections_187()' in file_menu, 'theme and mode live in «فایل»'
    assert "align='right'" in file_menu, 'under the button at the right end'
    assert set(d187.Stage187Dashboard._FILE_MENU_ICONS_187) == {
        'ذخیره', 'ذخیره با نام', 'بروزرسانی', 'تنظیمات', 'ذخیره بسته توسعه', 'سیستم'}
    # Operator round 2026-09-30: the file menu is a bare three-bar mark on
    # a tile, with no word on the button (its tooltip still names it).
    assert "text='فایل'" not in shell and "text=''" in shell
    assert "'hamburger'" in inspect.getsource(d187.Stage187Dashboard._file_button_look_187)
    assert "('Save', self.manual_save, 'بکاپ دستی')" in shell
    assert "('Undo', self.undo, 'بازگشت آخرین عملیات')" in shell
    assert "('Redo', self.redo, 'اجرای دوباره')" in shell
    assert 'self.footer187' in shell
    assert 'self.footer_mode_button187' in shell and 'self.footer_theme_button187' in shell
    # The footer control is named after what it does and offers three modes.
    assert 'self._display_mode_label_187()' in shell
    modes = inspect.getsource(d187.Stage187Dashboard._set_display_mode_187)
    assert "new['theme_id'] = 3" in modes
    for label in ('تاریک', 'روشن', 'رنگی'):
        assert label in shell
    # The two-entry light/dark menu became the three-mode display control
    # asserted just below; its labels are built from DISPLAY_MODES_187.
    # The control names the theme it is currently on, so its text is built
    # rather than literal.
    assert 'self._theme_choice_label_187()' in shell
    assert 'self.footer_themes_menu187' in shell
    label = inspect.getsource(d187.Stage187Dashboard._theme_choice_label_187)
    assert 'انتخاب تم' in label and 'theme_id_187()' in label
    # The footer no longer carries a language toggle: language is chosen in
    # Settings alongside every other appearance option. The toggle itself is
    # kept and still asserted below, since Settings drives the same path.
    assert 'self.footer_language_button187 = None' in shell
    toggle_language = inspect.getsource(d187.Stage187Dashboard._toggle_language_187)
    assert "new['language'] = 'fa' if current == 'en' else 'en'" in toggle_language
    assert 'self._settings_saved(old, new)' in toggle_language
    # Operator round 2026-09-27: the messages bell at the footer's left end
    # beside a two-line clock; the footer keeps D4's status (last save,
    # Telegram). Operator round 2026-09-30: the file menu and save/undo/
    # redo/refresh at the right end of the bar's top row, the bar a tenth
    # taller than the 67px it had (tests/test_stage18_7_header_two_row.py
    # covers the rows themselves).
    assert "self.bell_host187 = tk.Frame(self.footer187" in shell
    assert 'self.footer_saved187' in shell and 'self.footer_telegram187' in shell
    assert "self.quick_commands_host187.pack(side='right'" in shell
    assert "height=footer_height" in shell and "bg=top_color" in shell
    assert 'footer_height = 40' in shell and 'top.configure(height=self._SHELL_BAR_HEIGHT_187' in shell
    assert d187.Stage187Dashboard._SHELL_BAR_HEIGHT_187 == 74
    assert shell.index('self.bell_host187.pack(') < shell.index('self.footer_clock_host187.pack(')
    clock = inspect.getsource(d187.Stage187Dashboard._tick_clock)
    assert "\\n" in clock, 'time over date'
    assert "ui['appearance'] = mode" in theme
    assert 'overrideredirect' not in shell
    settings = inspect.getsource(d187.SettingsTab187._build)
    assert "('language', 'زبان رابط'" in settings
    assert "('appearance', 'حالت نمایش'" in settings
    assert "('background_color', 'رنگ پس‌زمینه'" in settings
    assert "self._installed_fonts()" in settings
    assert 'font_catalog_families_187' in inspect.getsource(d187.SettingsTab187._installed_fonts)
    assert 'font_status_label_187' in inspect.getsource(d187.SettingsTab187._build)
    save_settings = inspect.getsource(d187.SettingsTab187.save)
    assert "'فارسی (RTL)': 'fa'" in save_settings and "'English': 'en'" in save_settings
    assert "data['appearance'] = 'light'" in save_settings
    # Settings offers all three display modes now, so the saved value comes
    # from a map rather than a two-way conditional that clamped to 1 or 2.
    assert "THEME_CHOICE_VALUES_187" in save_settings
    assert set(d187.THEME_CHOICE_LABELS_187) == {1, 2, 3}
    # Settings is built on the shared window shell, so it inherits the themed
    # title bar with minimize/maximize/close, the contract size class, parent
    # centring and scrolling instead of hand-rolling them.  The old assertions
    # here pinned the previous tk.Toplevel implementation and its manual
    # scrollbar and screen-corner placement; that is what this replaces.
    window = inspect.getsource(d187.Stage187Dashboard.open_settings_187)
    assert 'BarkavWindow(' in window
    # The confirm action sits in the window footer, so a taller form can
    # never push it out of reach the way an in-form button could.
    assert "window.add_action('ذخیره تنظیمات'" in window
    assert 'tk.Toplevel' not in window
    apply_live = inspect.getsource(d187.Stage187Dashboard._apply_settings_live_187)
    assert "style_ttk_187" in apply_live and "footer_language_button187" in apply_live
    assert "row_height" in apply_live and "_apply_widget_font_187" in apply_live
    assert 'font_size' in apply_live
    apply_widget = inspect.getsource(d187.Stage187Dashboard._apply_widget_font_187)
    assert "if not current" not in apply_widget
    assert 'target_size' in apply_widget


def test_font_resolver_catalog_availability_and_nearest_weight(monkeypatch):
    import ui_stage18_7 as ui187

    monkeypatch.setattr(ui187.tkfont, 'families', lambda _root: ('IRANSansX', 'Arial'))
    assert ui187.available_font_families_187(object()) == ('IRANSansX', 'Arial')
    assert ui187.resolve_font_family_187(object(), 'MissingFont') == 'IRANSansX'
    assert ui187.font_display_name_187('IRANSansX') == 'ایران سنس X'
    assert ui187.resolve_font_weight_187(object(), 'IRANSansX', 600) == 700
    assert 'IRANYekanX' in ui187.missing_font_assets_187(object())
    labels = tuple(ui187.font_status_label_187(object(), name) for name in ui187.FONT_CATALOG_187)
    assert labels == tuple(f'{ui187.font_display_name_187(name)} (مفقود؛ fallback: ایران سنس X)' if name != 'IRANSansX' else 'ایران سنس X' for name in ui187.FONT_CATALOG_187)


def test_project_tab_closes_only_in_explicit_cross_zone():
    bbox = (10, 0, 210, 32)
    assert d187.is_tab_close_hit_187(215, bbox)
    assert not d187.is_tab_close_hit_187(25, bbox)
    assert not d187.is_tab_close_hit_187(120, bbox)


def test_telegram_runtime_files_are_project_isolated():
    one = d187.bot_runtime_paths_187(ROOT, 'project-A')
    two = d187.bot_runtime_paths_187(ROOT, 'project-B')
    assert one['ready'] != two['ready']
    assert one['inbound'] != two['inbound']
    assert 'project-A' in one['status'].name
    assert all(path.parent.name == 'runtime' for path in one.values())


def test_telegram_stage_uses_one_scoped_ready_status():
    source = (ROOT / 'telegram_stage18_7.py').read_text(encoding='utf-8')
    assert "_write_status(status_file, 'READY')" in source
    assert 'legacy.post_init = post_init_with_status' in source
    assert 'legacy.post_shutdown = post_shutdown_with_status' in source


class _EventService:
    def upcoming_cheques(self, days):
        return [{'due_date': '2026-08-25', 'due_date_shamsi': '1405/06/03',
                 'amount': 100, 'description': 'چک پیمانکار'}]

    def upcoming_buyer_installments(self, days):
        return [{'installment_id': 'I1', 'due_date': '2026-08-26',
                 'due_date_shamsi': '1405/06/04', 'outstanding': 200,
                 'unit_number': '2', 'buyer_name': 'خریدار'}]

    def overdue_buyer_installments(self):
        return []

    def upcoming_loan_installments(self, days):
        return [{'due_date': '2026-08-27', 'due_date_shamsi': '1405/06/05',
                 'outstanding': 300, 'loan_title': 'وام بانکی', 'lender_name': 'بانک'}]


def test_calendar_combines_cheque_receivable_and_loan_without_schema_change():
    events = collect_financial_events_187(_EventService(), 370)
    assert [event.kind for event in events] == ['CHEQUE', 'RECEIVABLE', 'LOAN']
    assert [event.direction for event in events] == ['OUT', 'IN', 'OUT']
    assert sum(event.amount for event in events) == 600


def test_reports_have_word_requested_controls_without_phase_schema_changes():
    source = (ROOT / 'reports_stage18_7.py').read_text(encoding='utf-8')
    assert 'PhaseDetailDialog187' in source
    assert '_configure_phase_summary_table_187(app)' in source
    assert 'install_checkbox_column_187' in source
    assert 'مدیریت کامل قیمت‌ها' in source
    assert 'باز کردن فایل برآورد' in source
    assert 'UPDATE rich_price_items SET active=0' in source
    assert 'CREATE TABLE' not in source


def test_approved_loan_and_installment_create_transaction_rows():
    payload = {
        'v18_title': 'ورودی', 'v18_subtype': 'تسهیلات',
        'amount': 1_000_000, 'loan_total_amount': 1_000_000,
        'loan_start_date': '1405/05/01', 'installment_count': 2,
        'loan_bank': 'بانک آزمایشی', 'loan_name': 'تسهیلات تست ۱۸.۷',
    }
    d187.v186.v18.approve_v18('PENDING_187_LOAN', payload, None)
    with d187.DB.read() as connection:
        loan = dict(connection.execute(
            "SELECT * FROM loans WHERE description='تسهیلات تست ۱۸.۷' ORDER BY created_at DESC LIMIT 1"
        ).fetchone())
        before = int(connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE category='LOAN_RECEIPT'"
        ).fetchone()[0])
    assert before == 1
    with d187.DB.read() as connection:
        installment = dict(connection.execute(
            'SELECT * FROM loan_installments WHERE loan_id=? ORDER BY installment_number LIMIT 1',
            (loan['loan_id'],),
        ).fetchone())
    d187.v186.v18.approve_v18('PENDING_187_INSTALLMENT', {
        'v18_title': 'خروجی', 'v18_subtype': 'اقساط',
        'loan_id': loan['loan_id'], 'installments_paid_now': 1,
        'amount': int(installment['amount']), 'event_date_shamsi': '1405/06/01',
    }, None)
    with d187.DB.read() as connection:
        out_count = int(connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE category='LOAN_INSTALLMENT'"
        ).fetchone()[0])
    assert out_count == 1


def test_bundled_persian_fonts_ship_with_licences_and_stay_persian_only(monkeypatch):
    import ui_stage18_7 as ui187

    fonts = Path(__file__).resolve().parents[1] / 'assets' / 'fonts'
    for family in ('Vazirmatn', 'Vazirmatn-UI', 'Sahel', 'Shabnam', 'Samim', 'Parastoo'):
        faces = sorted(path.name for path in fonts.glob(f'{family}*.ttf'))
        assert any('Bold' in name for name in faces) and len(faces) >= 2, (family, faces)
    assert len(list((fonts / 'licenses').glob('*.txt'))) == 5
    for family in ('Vazirmatn UI', 'Sahel', 'Shabnam', 'Samim', 'Parastoo'):
        assert family in ui187.FONT_CATALOG_187
    monkeypatch.setattr(ui187.tkfont, 'families', lambda _root: ('Vazirmatn', 'Sahel', 'Segoe UI'))
    monkeypatch.setattr(ui187, 'load_ui', lambda: {'language': 'fa'})
    assert ui187.resolve_font_family_187(object(), 'Sahel') == 'Sahel'
    monkeypatch.setattr(ui187, 'load_ui', lambda: {'language': 'en'})
    assert ui187.resolve_font_family_187(object(), 'Sahel') == 'Segoe UI', 'Persian faces only in the Persian UI'
