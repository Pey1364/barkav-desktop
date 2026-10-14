from __future__ import annotations
import io, os, sys
from pathlib import Path
import pytest
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_BOOT=tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH']=str(Path(_BOOT.name)/'stage183.sqlite3')

os.environ.setdefault('TELEGRAM_BOT_TOKEN','reg183-token')
os.environ.setdefault('GEMINI_API_KEY','reg183-gemini')
os.environ.setdefault('ADMIN_USER_ID','183')
os.environ.setdefault('GROUP_CHAT_ID','-100183')
os.environ.setdefault('STAGE4_DB_PATH',str(Path('/tmp/barkav_test_183.sqlite3')))

from ui_stage18_3 import fa, group_int_fa, parse_int, fetch_tgju_usd_toman
import ui_stage18_3 as ui
import dashboard_stage18_3 as d183


def test_version_and_light_palette_are_183_and_not_pure_white():
    assert d183.VERSION=='18.3'
    assert d183._THEME_LIGHT_183['bg'] != '#FFFFFF'
    assert d183._THEME_LIGHT_183['bg'].startswith('#')
    assert d183._THEME_DARK_183['bg'] != d183.v182._THEME_DARK['bg']


def test_persian_live_number_helpers_keep_numeric_value():
    assert group_int_fa(12500000)=='۱۲,۵۰۰,۰۰۰'
    assert parse_int('۱۲,۵۰۰,۰۰۰')==12500000
    assert fa('1405/05/28 18:03')=='۱۴۰۵/۰۵/۲۸ ۱۸:۰۳'


def test_tgju_parser_returns_toman_and_is_tolerant(monkeypatch):
    html='<html><body><div>نرخ فعلی</div><span>1,234,560</span><div>واحد پولی : ریال</div></body></html>'.encode('utf-8')
    class R:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self):return html
    monkeypatch.setattr(ui.urllib.request,'urlopen',lambda *a,**k:R())
    rate,ts=fetch_tgju_usd_toman()
    assert rate==123456
    assert 'T' in ts


def test_shortcut_icon_is_new_multisize_ico():
    p=Path(d183.BASE_DIR)/'assets'/'BARKAV.ico'
    assert p.exists() and p.stat().st_size>10000
    from PIL import Image
    im=Image.open(p)
    assert im.format=='ICO'
    assert max(im.info.get('sizes') or {(0,0)})[0] >= 128


def test_new_launcher_and_persistent_project_center_sources_exist():
    base=Path(d183.BASE_DIR)
    assert (base/'launcher_stage18_3.py').exists()
    assert (base/'project_runner_stage18_3.py').exists()
    text=(base/'project_center_stage18_3.py').read_text(encoding='utf-8')
    assert 'ttk.Notebook' in text
    assert 'self.destroy()' not in text[text.find('def open_project'):text.find('def new_project')]


def test_sales_document_types_use_generic_attachment_service_without_schema_change():
    src=Path(d183.BASE_DIR,'dashboard_stage18_3.py').read_text(encoding='utf-8')
    assert "document_type='CONTRACT'" not in src or 'CONTRACT' in src
    assert "_upload_sale_doc('CONTRACT')" in src
    assert "_upload_sale_doc('DEED')" in src
    assert "entity_type='SALE'" in src


def test_settings_restart_is_automatic_not_manual_instruction():
    src=Path(d183.BASE_DIR,'dashboard_stage18_3.py').read_text(encoding='utf-8')
    assert '_restart_requested=True' in src
    assert 'خودکار بازآفرینی' in src
    runner=Path(d183.BASE_DIR,'project_runner_stage18_3.py').read_text(encoding='utf-8')
    assert "getattr(app,'_restart_requested',False)" in runner


def test_only_requested_business_schema_remains_inherited():
    # 18.3 intentionally adds no finance-db migration/schema file; business model stays 18.2.
    base=Path(d183.BASE_DIR)
    assert not (base/'finance_db_stage18_3.py').exists()
    assert d183.DB is d183.v182.DB
