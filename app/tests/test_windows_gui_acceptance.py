from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "windows_gui_acceptance",
    ROOT / "tools" / "windows_gui_acceptance.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _snapshot(scenario: str = "contracts"):
    return {
        "scenario": scenario,
        "title": "BARKAV — Engineering & Construction — Version 19.1.1",
        "tree": {"width": 1000, "height": 500, "style": "Barkav.Data.Treeview"},
        "xscroll": {"mapped": True, "manager": "grid", "width": 1000, "height": 14},
        "yscroll": {"mapped": True, "manager": "grid", "width": 14, "height": 500},
        "finance_toolbar_root_y": [100, 100, 100],
        "finance_button_texts": ["اضافه", "ویرایش", "حذف"],
        "finance_search_kind": "نام خریدار",
        "finance_search_value": "همه",
        "finance_row_count": 9,
    }


def test_rendered_contract_snapshot_accepts_clean_table_and_scrollbars():
    checks = MODULE.evaluate_snapshot(_snapshot())
    assert checks
    assert all(checks.values())


def test_rendered_finance_snapshot_requires_one_row_and_no_refresh_button():
    checks = MODULE.evaluate_snapshot(_snapshot("finance"))
    assert checks["finance_toolbar_one_row"]
    assert checks["finance_refresh_button_absent"]
    bad = _snapshot("finance")
    bad["finance_toolbar_root_y"] = [100, 130, 100]
    bad["finance_button_texts"].append("بروزرسانی")
    rejected = MODULE.evaluate_snapshot(bad)
    assert not rejected["finance_toolbar_one_row"]
    assert not rejected["finance_refresh_button_absent"]


def test_rendered_snapshot_rejects_nonstandard_table_background():
    bad = _snapshot()
    bad["tree"]["style"] = "Custom.Image.Treeview"
    checks = MODULE.evaluate_snapshot(bad)
    assert not checks["table_uses_standard_background"]


def test_shared_skin_gives_arrowless_scrollbars_a_real_track_image():
    source = (ROOT / "barkav_ui" / "skin.py").read_text(encoding="utf-8")
    assert "SCROLLBAR_THICKNESS = 14" in source
    assert "def _scrollbar_track(" in source
    assert "track_name, 'image', track" in source
