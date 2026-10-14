from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'stage185.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'reg185-token')
os.environ.setdefault('GEMINI_API_KEY', 'reg185-gemini')
os.environ.setdefault('ADMIN_USER_ID', '185')
os.environ.setdefault('GROUP_CHAT_ID', '-100185')

import dashboard_stage18_5 as d185
import ui_stage18_5 as ui185
from instance_guard_v185 import ProjectInstanceGuard, safe_project_key
from launcher_stage18_5 import preflight_report
from project_center_stage18_5 import validate_project_shortcut
from project_registry import ProjectEntry


DASH = (ROOT / 'dashboard_stage18_5.py').read_text(encoding='utf-8')
UI = (ROOT / 'ui_stage18_5.py').read_text(encoding='utf-8')
CENTER = (ROOT / 'project_center_stage18_5.py').read_text(encoding='utf-8')
ACTIVE_VERSION = (ROOT / 'VERSION.txt').read_text(encoding='utf-8').strip()


def _requires_active_185_release():
    if ACTIVE_VERSION != '18.5':
        pytest.skip('18.5 package-only assertion is superseded by the active release')


def _sqlite(path: Path):
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE marker(id INTEGER PRIMARY KEY)')


def test_185_is_an_overlay_without_finance_schema_module():
    assert d185.VERSION == '18.5'
    assert d185.Stage185Dashboard.__mro__[1].__name__ == 'Stage184Dashboard'
    assert not (ROOT / 'finance_db_stage18_5.py').exists()
    assert not (ROOT / 'financial_posting_stage18_5.py').exists()


def test_reference_palettes_are_deep_navy_and_neutral_light():
    assert ui185.DARK_185['bg'] == '#0A1322'
    assert ui185.DARK_185['blue'] == '#2E78F3'
    assert ui185.LIGHT_185['bg'] == '#F5F7FA'
    assert ui185.LIGHT_185['panel'] == '#FFFFFF'


def test_floor_example_is_bottom_up_and_parking_is_lowest():
    rows = ui185.normalize_floor_structure(6, 2, 1, [])
    assert [row['floor_level'] for row in rows] == [-1, 0, 1, 2, 3, 4]
    assert [row['floor'] for row in rows] == ['طبقه منفی ۱', 'همکف', 'طبقه اول', 'طبقه دوم', 'طبقه سوم', 'طبقه چهارم']
    assert [row['is_parking'] for row in rows] == [True, True, False, False, False, False]


def test_floor_normalization_preserves_units_storage_and_disables_upper_parking():
    existing = [{
        'floor_level': -1, 'floor': 'زیرزمین', 'unit_count': 2,
        'units': [{'unit_number': '1', 'usage': 'تجاری', 'area': 80}, {'unit_number': '2', 'usage': 'اداری', 'area': 90}],
        'storage_count': 1, 'storage_areas': [7], 'parking_supplied': 11,
    }]
    rows = ui185.normalize_floor_structure(3, 1, 1, existing)
    assert rows[0]['units'][0]['usage'] == 'تجاری'
    assert rows[0]['storage_areas'] == [7]
    assert rows[0]['parking_supplied'] == 11
    assert all(row['parking_supplied'] == 0 for row in rows[1:])


def test_base_area_save_uses_explicit_persian_decimal_parser():
    assert d185.parse_decimal('۱,۲۳۴') == 1234
    assert "gross_area=parse_decimal(self.vars['gross_area'].get())" in DASH
    assert "saleable_area=parse_decimal(self.vars['saleable_area'].get())" in DASH


def test_admin_followup_role_has_requested_fields():
    specs = d185.ProjectSettingsDialog185.ROLE_SPECS
    fields = dict(d185.ProjectSettingsDialog185.TEAM_FIELDS['admin_followup'])
    assert specs['admin_followup'] == ['مسئول پیگیری اداری']
    assert set(fields) == {'name', 'company', 'phone'}


def test_data_entry_uses_real_backup_import_and_skips_attachment_only_buttons():
    assert 'import_telegram_export' in DASH
    assert "text='فراخوانی بکاپ چت'" in DASH
    build = DASH[DASH.index('class DataEntryCenter185'):DASH.index('class SettingsTab185')]
    assert 'v183.DataEntryCenter183._build(self)' in build
    assert "text='📎 تاریخچه چت'" not in build
    assert "text='📂 تاریخچه‌های متصل'" not in build


def test_grid_overlay_is_event_driven_not_polling():
    section = UI[UI.index('class TreeGridOverlay185'):UI.index('def _retire_overlay')]
    assert "after_idle(self.update)" in section
    assert 'after(350' not in section


def test_preview_and_service_badges_are_stable():
    assert '_preview_signature_185' in DASH
    assert "label.configure(width=35" in DASH
    assert "label.configure(width=27" in DASH


def test_financial_indices_use_adjustable_horizontal_pane():
    assert "ttk.Panedwindow(root, orient='horizontal')" in DASH
    assert "pane.sashpos(0, int(width * 0.57))" in DASH
    assert "pane.add(results, weight=3)" in DASH
    assert "pane.add(params, weight=2)" in DASH


def test_financial_indices_reinsert_uses_end_when_original_index_is_gone():
    assert "remaining_tabs = self.report_main.tabs()" in DASH
    assert "insert_at = target_index if 0 <= target_index < len(remaining_tabs) else 'end'" in DASH
    assert "self.report_main.insert(insert_at, root, text='شاخص‌های مالی')" in DASH


def test_usd_refresh_is_background_persisted_and_startup_scheduled():
    assert "threading.Thread(target=job, daemon=True).start()" in DASH
    assert "ui['usd_rate_current'] = int(rate)" in DASH
    assert "self.after(650, self._startup_usd_refresh_185)" in DASH


def test_system_and_all_active_entrypoints_are_185():
    _requires_active_185_release()
    assert "نسخه برنامه: {fa(VERSION)}" in DASH
    for name in ('launcher_stage18_5.py', 'project_center_stage18_5.py', 'project_runner_stage18_5.py', 'BARKAV_18.5.bat'):
        assert (ROOT / name).exists()
    assert (ROOT / 'VERSION.txt').read_text(encoding='utf-8').strip() == '18.5'


def test_shortcut_validation_accepts_sqlite_and_rejects_isolation_collisions(tmp_path):
    database = tmp_path / 'finance.sqlite3'
    _sqlite(database)
    shortcut = tmp_path / 'demo.barkav'
    data = {'format': 'BARKAV_PROJECT_SHORTCUT', 'project_id': 'PRJ-200', 'name': 'دمو', 'db_path': str(database), 'group_chat_id': -100200}
    project, is_new = validate_project_shortcut(data, shortcut, [])
    assert is_new and project.db_path == str(database)
    other_db = tmp_path / 'other.sqlite3'
    _sqlite(other_db)
    registered = [ProjectEntry('PRJ-001', 'ثبت‌شده', str(other_db), -100200)]
    with pytest.raises(ValueError, match='Group ID'):
        validate_project_shortcut(data, shortcut, registered)
    registered = [ProjectEntry('PRJ-001', 'ثبت‌شده', str(database), -100999)]
    with pytest.raises(ValueError, match='دیتابیس'):
        validate_project_shortcut(data, shortcut, registered)


def test_shortcut_existing_identity_cannot_silently_switch_database(tmp_path):
    first = tmp_path / 'first.sqlite3'
    second = tmp_path / 'second.sqlite3'
    _sqlite(first)
    _sqlite(second)
    registered = [ProjectEntry('PRJ-001', 'پروژه', str(first), -1001)]
    data = {'format': 'BARKAV_PROJECT_SHORTCUT', 'project_id': 'PRJ-001', 'db_path': str(second), 'group_chat_id': -1001}
    with pytest.raises(ValueError, match='بازنویسی نشد'):
        validate_project_shortcut(data, tmp_path / 'x.barkav', registered)


def test_project_guard_rejects_second_runner(tmp_path):
    assert safe_project_key('PRJ/001') == 'PRJ_001'
    first = ProjectInstanceGuard(tmp_path, 'PRJ-001')
    second = ProjectInstanceGuard(tmp_path, 'PRJ-001')
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
    assert second.acquire() is True
    second.release()


def test_preflight_reports_missing_runtime_without_exposing_values(tmp_path):
    errors, _warnings = preflight_report(tmp_path)
    text = '\n'.join(errors)
    assert 'secrets.local.json' in text
    assert 'data' in text


def test_release_source_has_only_the_185_product_bat():
    _requires_active_185_release()
    product_bats = sorted(path.name for path in ROOT.glob('BARKAV_*.bat'))
    assert product_bats == ['BARKAV_18.5.bat']


def test_release_source_excludes_live_sensitive_files():
    assert not (ROOT / 'secrets.local.json').exists()
    assert not list((ROOT / 'data').glob('*.sqlite3'))
    assert (ROOT / 'LOCAL_DATA_SETUP.md').is_file()


def test_project_center_185_uses_theme_and_validated_import():
    assert 'palette_185' in CENTER
    assert 'validate_project_shortcut' in CENTER
    assert "project_runner_stage18_5.py" in CENTER
