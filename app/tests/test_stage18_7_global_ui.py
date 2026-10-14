from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / 'dashboard_stage18_7.py').read_text(encoding='utf-8')
SMART_TABLE = (Path(__file__).resolve().parents[1] / 'barkav' / 'features' / 'dashboard.py').read_text(encoding='utf-8')
TOKENS = (Path(__file__).resolve().parents[1] / 'barkav_themes' / 'tokens.py').read_text(encoding='utf-8')
WINDOW = (Path(__file__).resolve().parents[1] / 'barkav_ui' / 'window.py').read_text(encoding='utf-8')


def test_global_ui_contract_shows_windows_without_fade_and_keeps_wizard_skip():
    assert "attributes('-alpha'" not in SOURCE
    assert "attributes('-alpha'" not in WINDOW
    assert 'window.deiconify()' in WINDOW
    assert 'self.after(140, apply_once)' in SOURCE
    assert "رد کردن تمام مراحل" in SOURCE
    assert "_wizard_skip_to_confirmation_187" in SOURCE
    assert "Primary.TButton" in SOURCE


def test_global_tables_keep_refresh_bulk_delete_and_green_stripes():
    assert "_install_table_refresh_187(tree)" in SOURCE
    assert "label='🔄 بروزرسانی'" in SOURCE
    assert "_delete_selected_many" in SMART_TABLE
    assert "حذف/ابطال انتخاب‌ها" in SMART_TABLE
    assert 'palette["green"]' in TOKENS
