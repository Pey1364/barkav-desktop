from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
_BOOT=tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH']=str(Path(_BOOT.name)/'stage183_accept.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN','accept183-token')
os.environ.setdefault('GEMINI_API_KEY','accept183-gemini')
os.environ.setdefault('ADMIN_USER_ID','183')
os.environ.setdefault('GROUP_CHAT_ID','-100183')

import dashboard_stage18_3 as d183
import ui_stage18_3 as ui

DASH=(ROOT/'dashboard_stage18_3.py').read_text(encoding='utf-8')
CENTER=(ROOT/'project_center_stage18_3.py').read_text(encoding='utf-8')
RUNNER=(ROOT/'project_runner_stage18_3.py').read_text(encoding='utf-8')
UI=(ROOT/'ui_stage18_3.py').read_text(encoding='utf-8')


def test_01_project_center_stays_open_and_projects_are_tabs():
    block=CENTER[CENTER.index('def open_project'):CENTER.index('def new_project')]
    assert 'ttk.Notebook' in CENTER
    assert 'self.nb.add(tab' in CENTER
    assert 'self.destroy()' not in block
    assert 'project_runner_stage18_3.py' in block


def test_02_editor_invoice_final_discount_are_right_anchored():
    assert "for key,col in [('invoice_amount',3),('final_amount',2),('discount_amount',1)]" in DASH


def test_03_copy_paste_copies_source_payload_values_not_blank_row():
    block=DASH[DASH.index('def copy_rows'):DASH.index('def open_editor')]
    assert 'DB.get_pending_item' in block
    assert "deepcopy(dict(src.get('payload') or {}))" in block
    assert "src['raw_text']" in block


def test_04_data_entry_top_actions_centered_and_row_borders_enabled():
    assert "text')) in {'بازخوانی پیام‌ها','پردازش مجدد'}" in DASH
    assert "center.place(relx=.52,rely=.5,anchor='center')" in DASH
    assert 'TreeGridOverlay' in UI and 'attach_tree_grid' in UI


def test_05_reports_rtl_and_mouse_height_resize():
    assert 'self._install_rtl(self.report_main);self._install_rtl(self.report_nb)' in DASH
    assert 'def _install_report_resize_handles' in DASH
    assert "cursor='sb_v_double_arrow'" in DASH
    assert "bind('<B1-Motion>'" in DASH


def test_06_transaction_and_sales_subtabs_are_rtl():
    assert 'self._install_rtl(self.fin_nb)' in DASH
    assert 'self._install_rtl(self.sales_nb)' in DASH


def test_07_sales_support_contract_and_deed_uploads():
    assert "_upload_sale_doc('CONTRACT')" in DASH
    assert "_upload_sale_doc('DEED')" in DASH
    assert "entity_type='SALE'" in DASH
    assert 'اسناد فروش' in DASH


def test_08_project_details_tabs_rtl_and_rows_have_theme_grid():
    assert 'RtlNotebookStrip(self.nb' in DASH
    assert 'attach_tree_grid(self.floor_tree' in DASH or "attach_grids_recursive(self,light=_is_light())" in DASH


def test_09_team_designer_supervisor_filters_all_and_scrollable():
    assert "self._team_filters={}" in DASH
    assert "values=['همه']+self.ROLE_SPECS[role]" in DASH
    assert "('supervisor','ناظر'" in DASH and "('designer','طراح'" in DASH
    assert 'tk.Canvas' in DASH and 'ttk.Scrollbar' in DASH
    assert "wanted=='همه'" in DASH


def test_10_all_project_details_tabs_have_print_excel_pdf_output():
    assert "values=['انتخاب فرمت خروجی','پرینت','Excel','PDF']" in DASH
    assert 'def _active_export_data' in DASH
    assert "label=='مشخصات پایه'" in DASH and "label=='طبقات و واحدها'" in DASH


def test_11_output_is_single_dropdown_then_save_dialog_for_files():
    assert 'def install_smarttable_export_dropdown' in UI
    assert "values=('انتخاب فرمت خروجی','پرینت','Excel','PDF')" in UI
    assert 'table.export_excel()' in UI and 'table.export_pdf()' in UI and 'table.print_report()' in UI
    assert 'asksaveasfilename' in DASH


def test_12_transactions_sales_manager_visible_numbers_are_persianized():
    assert 'def _persianize_region' in DASH
    for method in ('refresh_financial','refresh_sales','refresh_manager'):
        start=DASH.index(f'def {method}')
        snippet=DASH[start:start+500]
        assert '_persianize_region' in snippet


def test_13_wizard_and_editor_numeric_input_uses_persian_live_formatting():
    assert 'class _PersianNumericFieldMixin' in DASH
    assert 'bind_grouped_number_fa' in DASH
    assert ui.group_int_fa(1250000)=='۱,۲۵۰,۰۰۰'
    assert ui.parse_int('۱,۲۵۰,۰۰۰')==1250000


def test_14_reporting_numbers_are_persianized():
    start=DASH.index('def refresh_reports')
    assert '_persianize_region' in DASH[start:start+500]


def test_15_all_tree_tables_receive_vertical_and_stronger_horizontal_grid_lines():
    assert 'class TreeGridOverlay' in UI
    assert 'self.vlines' in UI and 'self.hlines' in UI
    assert 'height=2' in UI  # stronger row separators
    assert 'width=1' in UI   # lighter column separators
    assert 'attach_grids_recursive' in DASH


def test_16_legacy_sections_retarget_to_segoe_ui():
    assert "font.configure(family='Segoe UI')" in DASH
    assert "st.configure('.',font=('Segoe UI'" in DASH


def test_17_settings_apply_live_or_auto_restart_without_manual_reopen():
    assert '_restart_requested=True' in DASH
    assert 'self.refresh_all()' in DASH
    assert "getattr(app,'_restart_requested',False)" in RUNNER


def test_18_light_theme_background_is_very_light_gray_not_white():
    assert d183._THEME_LIGHT_183['bg']=='#EEF1F4'
    assert d183._THEME_LIGHT_183['surface']!='#FFFFFF'


def test_19_data_entry_four_action_buttons_are_half_height_compact():
    block=DASH[DASH.index('def _compact_bottom_buttons'):DASH.index('def _center_reprocess_actions')]
    for name in ('حذف','کپی','پیست','اضافه کردن'):
        assert name in block
    assert 'pady=3' in block


def test_20_data_entry_transaction_colors_are_more_vivid():
    assert 'class PendingTable183' in DASH
    # Bright 18.3 accent palette is deliberately distinct from 18.2.
    for c in ('#45A5EB','#46C48E','#F0B44D','#F06B78','#24B7C6'):
        assert c in DASH


def test_21_project_details_usd_updates_from_tgju_and_stays_editable(monkeypatch):
    assert ui.TGJU_DOLLAR_URL=='https://www.tgju.org/profile/price_dollar_rl'
    html='<div>نرخ فعلی</div><span>1,250,000</span><div>واحد پولی : ریال</div>'.encode()
    class Resp:
        def __enter__(self): return self
        def __exit__(self,*a): return False
        def read(self): return html
    monkeypatch.setattr(ui.urllib.request,'urlopen',lambda *a,**k:Resp())
    rate,_=ui.fetch_tgju_usd_toman()
    assert rate==125000
    assert "e=ttk.Entry(box,textvariable=v,justify='right')" in DASH


def test_22_windows_shortcut_uses_new_user_requested_multisize_icon():
    ico=ROOT/'assets'/'BARKAV.ico'
    shortcut=ROOT/'CREATE_SHORTCUT.bat'
    assert ico.exists() and ico.stat().st_size>10000
    assert 'BARKAV.ico' in shortcut.read_text(encoding='utf-8',errors='ignore')
    from PIL import Image
    im=Image.open(ico)
    assert im.format=='ICO' and max(im.info['sizes'])[0]>=128


def test_23_header_uses_brand_top_left_and_datetime_next_to_system_commands():
    assert "brand_path=BASE_DIR/'assets'/'barkav_brand_header.png'" in DASH
    assert "pack(side='left'" in DASH
    assert "('سیستم'," in DASH
    # date/time is packed into the same right-side tools container immediately after command buttons.
    assert "tk.Label(tools,textvariable=self.datetime_top" in DASH


def test_24_graphics_are_materially_retargeted_to_reference_style_not_old_182_theme():
    assert d183._THEME_DARK_183['bg']=='#071523'
    assert d183._THEME_DARK_183['panel2']=='#162D46'
    assert d183._THEME_DARK_183 != d183.v182._THEME_DARK
    assert d183._THEME_LIGHT_183 != d183.v182._THEME_LIGHT
    assert "height=76" in DASH and "height=62" in DASH
    assert "highlightthickness=1" in DASH
    assert "st.configure('Treeview.Heading'" in DASH
