from __future__ import annotations

import inspect

from ai_parser import ANALYSIS_SCHEMA, SYSTEM_PROMPT, _SUB_CATEGORY_ROUTES
from config_loader import load_config
from project_registry import ProjectEntry, apply_project_environment
from receipt_intelligence import LocalOCREngine, ReceiptIntelligenceService


def test_handoff_ai_taxonomy_is_additive_and_caption_rule_is_present():
    properties = ANALYSIS_SCHEMA["properties"]
    assert properties["expense_cost_type"]["enum"] == ["مصالح", "پیمانکار", "خدمات", "سایر"]
    assert properties["income_source_type"]["enum"] == ["تسهیلات", "فروش", "شرکا_یا_قرض", "سایر"]
    assert properties["outflow_type"]["enum"] == ["اقساط", "سایر"]
    assert "تقویم_کارگاهی" in properties["note_type"]["enum"]
    assert "قوی‌ترین سیگنال" in SYSTEM_PROMPT
    # Superseded by a later, schema-level fix (this project's HANDOFF entry
    # 12): Gemini's schema-constrained decoding reliably omits optional enum
    # fields no matter how strongly SYSTEM_PROMPT's free text asks for them
    # - confirmed against live data (0 of 90+ EXPENSE/INCOME/OUTFLOW rows had
    # one set). So the guarantee this test checks is no longer "the prompt
    # mentions the field name" but "sub_category is schema-required, and
    # _SUB_CATEGORY_ROUTES deterministically routes it into the matching
    # legacy field's own enum" - see ai_parser.py's own comment above
    # sub_category in ANALYSIS_SCHEMA for the full reasoning.
    assert "sub_category" in ANALYSIS_SCHEMA["required"]
    assert _SUB_CATEGORY_ROUTES["EXPENSE"] == (
        "expense_cost_type", tuple(properties["expense_cost_type"]["enum"]))
    assert _SUB_CATEGORY_ROUTES["INCOME"] == (
        "income_source_type", tuple(properties["income_source_type"]["enum"]))
    assert _SUB_CATEGORY_ROUTES["OUTFLOW"] == (
        "outflow_type", tuple(properties["outflow_type"]["enum"]))


def test_handoff_group_ids_load_and_export(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("ADMIN_USER_ID", "7")
    monkeypatch.setenv("GROUP_CHAT_ID", "-1001")
    monkeypatch.setenv("GROUP_CHAT_IDS", "-1001,-1002")
    config = load_config(tmp_path)
    assert config.group_chat_id == -1001
    assert config.group_chat_ids == (-1001, -1002)

    entry = ProjectEntry(
        project_id="PRJ-001", name="Test", db_path=str(tmp_path / "db.sqlite3"),
        group_chat_id=-1001, group_chat_ids=[-1001, -1002],
    )
    apply_project_environment(entry)
    assert __import__("os").environ["GROUP_CHAT_IDS"] == "-1001,-1002"


def test_handoff_ocr_is_cached_and_moved_off_event_loop():
    ocr_source = inspect.getsource(LocalOCREngine)
    receipt_source = inspect.getsource(ReceiptIntelligenceService.analyze_archived)
    assert "_available_cache" in ocr_source
    assert "_effective_lang_cache" in ocr_source
    assert "await asyncio.to_thread(self.preprocess" in receipt_source
    assert "await asyncio.to_thread(self.ocr.extract" in receipt_source
