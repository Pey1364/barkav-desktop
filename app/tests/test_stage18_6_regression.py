from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'stage186.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'reg186-token')
os.environ.setdefault('GEMINI_API_KEY', 'reg186-gemini')
os.environ.setdefault('ADMIN_USER_ID', '186')
os.environ.setdefault('GROUP_CHAT_ID', '-100186')

import dashboard_stage18_6 as d186
import ui_stage18_6 as ui186


DASH = (ROOT / 'dashboard_stage18_6.py').read_text(encoding='utf-8')
UI = (ROOT / 'ui_stage18_6.py').read_text(encoding='utf-8')
CENTER = (ROOT / 'project_center_stage18_6.py').read_text(encoding='utf-8')


def test_186_is_isolated_overlay_on_185():
    assert d186.VERSION == '18.6'
    assert d186.Stage186Dashboard.__mro__[1].__name__ == 'Stage185Dashboard'
    assert (ROOT / 'dashboard_stage18_5.py').exists()
    assert not (ROOT / 'finance_db_stage18_6.py').exists()


def test_reference_palettes_are_compact_navy_and_neutral_light():
    """The 18.6 reference palette is asserted from source, not from the dicts.

    ``activate_theme_bridge_187`` deliberately re-points the inherited 18.6
    palette dicts at the selected 18.7 theme at runtime - that is how the
    inherited widgets get themed at all. The dicts are therefore process-wide
    mutable, and reading them here would only report whichever theme happened
    to be loaded first. The frozen 18.6 values live in the source file.
    """
    source = (ROOT / 'ui_stage18_6.py').read_text(encoding='utf-8')
    dark = source[source.index('DARK_186 = {'):source.index('LIGHT_186 = {')]
    light = source[source.index('LIGHT_186 = {'):source.index('ROOF_LEVEL_186')]
    assert "'bg': '#091423'" in dark
    assert "'blue': '#2F78EE'" in dark
    assert "'bg': '#F5F7FA'" in light
    assert "'panel': '#FFFFFF'" in light


def test_floor_structure_always_adds_one_roof_storage_row():
    rows = ui186.normalize_floor_structure_186(6, 2, 1, [])
    assert [row['floor_level'] for row in rows[:-1]] == [-1, 0, 1, 2, 3, 4]
    assert rows[-1]['floor'] == 'بام'
    assert rows[-1]['is_roof'] is True
    assert rows[-1]['unit_count'] == 0
    assert rows[-1]['is_parking'] is False


def test_roof_storage_values_survive_floor_regeneration():
    existing = [{
        'floor': 'بام', 'is_roof': True, 'storage_count': 2,
        'storage_areas': [6.5, 8],
    }]
    rows = ui186.normalize_floor_structure_186(2, 0, 0, existing)
    assert rows[-1]['storage_count'] == 2
    assert rows[-1]['storage_areas'] == [6.5, 8]


def test_currency_conversion_keeps_toman_as_source_of_truth():
    assert ui186.convert_toman_186(123_456, 'تومان', 70_000) == 123_456
    assert ui186.convert_toman_186(123_456, 'ریال', 70_000) == 1_234_560
    assert ui186.convert_toman_186(140_000, 'دلار', 70_000) == 2
    assert ui186.format_currency_186(140_000, 'دلار', 70_000) == '۲.۰۰'


def test_currency_unit_is_only_added_to_money_headings():
    assert ui186.currency_heading_186('مبلغ (تومان)', 'ریال') == 'مبلغ (ریال)'
    assert ui186.currency_heading_186('شرح', 'دلار') == 'شرح'
    assert ui186.currency_heading_186('مانده', 'دلار') == 'مانده (دلار)'


def test_money_cell_parser_rejects_dates_and_text():
    assert ui186.parse_display_amount_186('۱,۲۳۴ تومان') == 1234
    assert ui186.parse_display_amount_186('۱۴۰۵/۰۵/۲۹') is None
    assert ui186.parse_display_amount_186('واریز بانکی') is None


def test_floor_cards_are_two_columns_and_labels_are_right_of_inputs():
    assert "uniform='floor_half'" in DASH
    assert "column=1 - (index % 2)" in DASH
    assert "text='نام طبقه'" in DASH
    assert "text='تعداد انباری'" in DASH


def test_project_team_uses_four_vertical_role_columns_in_requested_order():
    assert "order = [('designer', 3), ('supervisor', 2), ('executor', 1), ('admin_followup', 0)]" in DASH
    assert "uniform='team_quarter'" in DASH
    assert set(d186.ProjectSettingsDialog186.ROLE_SPECS) == {
        'designer', 'supervisor', 'executor', 'admin_followup'
    }


def test_data_entry_has_framed_service_badges_and_lighter_categories():
    assert "highlightthickness=1" in DASH[DASH.index('class DataEntryCenter186'):DASH.index('class SettingsTab186')]
    # پنجینگ رنگش زرد روشن است، در هر دو تم و صرف‌نظر از عنوان تراکنش - رنگ‌های
    # قبلی (آبی/سبز/بنفش/خاکستری، هر تم مقادیر خودش) دقیقاً همان چیزی بود که
    # به عنوان «آبی» گزارش و خواسته شد به رنگ‌های روشن ساده تبدیل شود.
    assert '#F5C842' in DASH
    assert "attach_tree_grid_186(tree" in DASH
    # Read from source: the runtime dict is re-pointed by the 18.7 bridge.
    assert "'line': '#E1E7EE'" in (ROOT / 'ui_stage18_6.py').read_text(encoding='utf-8')


def test_report_calculate_button_is_full_width_below_parameters():
    assert "text='محاسبه شاخص‌ها با پارامترهای بالا'" in DASH
    assert 'self.calculate_indices_button186.pack(fill=\'x\'' in DASH
    assert "command=self.calculate_financial_indices" in DASH


def test_manager_metrics_are_forced_from_authoritative_snapshot():
    section = DASH[DASH.index('    def refresh_manager(self):'):DASH.index('    def _upgrade_tables_184', DASH.index('    def refresh_manager(self):'))]
    assert 'snapshot = DB.snapshot()' in section
    assert "'fee': int(snapshot.manager_fee_accrued)" in section
    assert "'balance': int(snapshot.manager_balance)" in section
    assert "manager_fee_bps" in section


def test_smarttable_total_is_filter_aware_and_currency_aware():
    assert 'جمع مبلغ فیلترشده' in UI
    assert "getattr(table, '_filtered_total_amount', 0)" in UI
    assert 'format_currency_186(selected_amount' in UI


def test_compact_shell_uses_184_brand_asset_and_reference_geometry():
    assert "BASE_DIR / 'assets' / 'barkav_brand_header.png'" in DASH
    assert "height=62" in DASH
    assert "height=46" in DASH
    assert "range(5)" in DASH
    assert "reference_five" in DASH


def test_active_entrypoints_are_186():
    """Historical layers stay available; the active route is 19.1.1."""
    for name in ('BARKAV_18.6.bat', 'launcher_stage18_6.py', 'project_center_stage18_6.py',
                 'project_runner_stage18_6.py', 'dashboard_stage18_6.py', 'ui_stage18_6.py',
                 'BARKAV_19.1.1.bat', 'launcher_stage18_7.py', 'dashboard_stage18_7.py'):
        assert (ROOT / name).is_file()
    assert (ROOT / 'VERSION.txt').read_text(encoding='utf-8').strip() == '19.1.1'
    bat = (ROOT / 'BARKAV_19.1.1.bat').read_text(encoding='utf-8')
    assert 'BARKAV_19.1.1.vbs' in bat
    vbs = (ROOT / 'BARKAV_19.1.1.vbs').read_text(encoding='utf-8')
    assert 'launcher_stage18_7.py' in vbs
    launcher = (ROOT / 'launcher_stage18_7.py').read_text(encoding='utf-8')
    assert 'from project_runner_stage18_7 import run_project' in launcher
    runner = (ROOT / 'project_runner_stage18_7.py').read_text(encoding='utf-8')
    assert 'Stage187Dashboard' in runner
    assert 'project_runner_stage18_6.py' in CENTER


def test_release_source_has_only_the_186_product_bat_and_no_live_data():
    assert sorted(path.name for path in ROOT.glob('BARKAV_*.bat')) == [
        'BARKAV_18.6.bat', 'BARKAV_18.7.1.bat', 'BARKAV_18.7.bat', 'BARKAV_19.1.1.bat']
    assert not (ROOT / 'secrets.local.json').exists()
    assert not list((ROOT / 'data').glob('*.sqlite3'))
    assert (ROOT / 'LOCAL_DATA_SETUP.md').is_file()
