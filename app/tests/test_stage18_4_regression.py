from __future__ import annotations
import os, sys, tempfile, json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
_BOOT=tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH']=str(Path(_BOOT.name)/'stage184.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN','reg184-token')
os.environ.setdefault('GEMINI_API_KEY','reg184-gemini')
os.environ.setdefault('ADMIN_USER_ID','184')
os.environ.setdefault('GROUP_CHAT_ID','-100184')

import dashboard_stage18_4 as d184
import ui_stage18_4 as ui184

DASH=(ROOT/'dashboard_stage18_4.py').read_text(encoding='utf-8')
CENTER=(ROOT/'project_center_stage18_4.py').read_text(encoding='utf-8')
SHORTCUT=(ROOT/'CREATE_SHORTCUT.bat').read_text(encoding='utf-8',errors='ignore')


def test_184_version_and_business_layer_stays_on_183_inheritance():
    assert d184.VERSION=='18.4'
    assert d184.Stage184Dashboard.__mro__[1].__name__=='Stage183Dashboard'
    assert not (ROOT/'finance_db_stage18_4.py').exists()
    assert not (ROOT/'financial_posting_stage18_4.py').exists()


def test_01_subtabs_retarget_font_numbers_using_instance_upgrade():
    assert 'retarget_smarttable_instance_184' in (ROOT/'ui_stage18_4.py').read_text(encoding='utf-8')
    assert "font=('Segoe UI',font_size)" in (ROOT/'ui_stage18_4.py').read_text(encoding='utf-8')
    assert 'table.total.set(fa(table.total.get()))' in (ROOT/'ui_stage18_4.py').read_text(encoding='utf-8')


def test_02_usd_removed_from_project_base_but_settings_has_tgju():
    assert 'class SettingsTab184' in DASH and 'بروزرسانی از TGJU' in DASH
    assert 'class ProjectSettingsDialog184' in DASH and '_remove_usd_from_project_base' in DASH
    assert "self.vars.pop('usd_rate_current',None)" in DASH


def test_03_project_units_are_rtl_display_order():
    assert "tree.configure(displaycolumns=('areas','count','floor'))" in DASH
    assert "tree.heading(c,anchor='e')" in DASH


def test_04_transaction_double_click_routes_to_new_unified_editor():
    for method in ('edit_transaction_row','edit_expense_row','edit_cheque_row','edit_loan_row'):
        assert f'def {method}' in DASH
    assert 'UnifiedPendingEditor184' in DASH
    assert "doc.set_edit_handler(self.edit_document_row_184)" in DASH


def test_05_quick_theme_button_next_to_datetime_and_settings_kept():
    assert 'def _install_quick_theme' in DASH and "text=symbol" in DASH
    assert "ui['appearance']='dark'" in DASH
    assert 'class SettingsTab184' in DASH


def test_06_all_tables_checkbox_column_and_ultra_faint_verticals():
    ui=(ROOT/'ui_stage18_4.py').read_text(encoding='utf-8')
    assert "tree.configure(show='tree headings')" in ui
    assert "tree.heading('#0',text='☐'" in ui
    assert "column='#EEF1F4' if light else '#122436'" in ui


def test_07_project_center_new_open_and_project_shortcut_files():
    assert "text='New'" in CENTER and "text='Open'" in CENTER
    assert "filetypes=[('BARKAV Project','*.barkav')" in CENTER
    assert "'format':'BARKAV_PROJECT_SHORTCUT'" in CENTER
    assert 'ProjectWizard' in CENTER


def test_08_project_tab_project_id_uses_persian_digits():
    assert "({fa(p.project_id)})" in CENTER


def test_09_open_project_counter_is_explicit_and_not_concatenated():
    assert "پروژه‌های باز: {opened}    •    کل پروژه‌ها: {total}" in CENTER


def test_10_project_tabs_have_clickable_close_x_logic():
    assert "  ×'" in CENTER
    assert "self.nb.bind('<Button-1>',self._tab_click" in CENTER
    assert 'def close_project' in CENTER and 'proc.terminate()' in CENTER


def test_11_logo_tagline_is_larger_and_project_center_uses_brand():
    ui=(ROOT/'ui_stage18_4.py').read_text(encoding='utf-8')
    assert "text='Engineering & Construction'" in ui
    assert "9 if compact else 10" in ui
    assert 'build_brand_widget_184(head' in CENTER
    assert '_replace_brand_184' in DASH


def test_12_save_as_is_explicitly_not_a_new_184_feature():
    # The user deferred the new Word/Excel-style Save As UI to future development.
    # 18.4 adds no new Save As control/implementation file.
    assert 'save_as_184' not in DASH


def test_13_shortcut_uses_unique_184_icon_to_avoid_windows_cache():
    ico = ROOT / 'assets' / 'BARKAV.ico'
    assert ico.is_file() and ico.stat().st_size > 10000
    assert 'set "TARGET=%APP%BARKAV_19.1.1.bat"' in SHORTCUT
    assert 'set "ICON=%APP%assets\\BARKAV.ico"' in SHORTCUT
    assert 'set "LINK=%ROOT%\\BARKAV.lnk"' in SHORTCUT
    assert '$s.TargetPath=' in SHORTCUT and '$s.WorkingDirectory=' in SHORTCUT
    assert 'ie4uinit.exe -show' in SHORTCUT


def test_14_transaction_tab_order_places_cheque_after_expense_and_document_last():
    assert "desired=['کلیه تراکنش‌ها','هزینه ساخت','چک‌ها','ورودی‌ها','خروجی‌ها','تسهیلات','داکیومنت‌ها']" in DASH


def test_15_data_entry_colors_are_more_vivid_and_use_184_grid():
    # Per-title colors were later replaced with one light yellow for every
    # pending row (see dashboard_stage18_6's _row_colors_185, the layer that
    # actually wins) - 184's own copy stays in sync with that same color.
    assert '#F5C842' in DASH
    assert 'attach_tree_grid_184(tree' in DASH


def test_16_chat_history_attachment_is_separate_document_type():
    assert "document_type='CHAT_HISTORY'" in DASH
    assert "فیلد «بابت»" in DASH or 'از «بابت»' in DASH
    assert "str(d.get('document_type') or '').upper()=='CHAT_HISTORY'" in DASH
