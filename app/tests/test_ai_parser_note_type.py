from __future__ import annotations

import asyncio
import unittest

from ai_parser import GeminiFinancialParser


class NoteTypeNormalizationTests(unittest.TestCase):
    """Gemini's structured JSON output reliably omits the optional note_type
    field even for real operator-labeled messages (confirmed against live
    pending_items). _normalize enforces the SYSTEM_PROMPT's own explicit-
    caption-label rule deterministically instead of only asking the model."""

    def _base(self, detected_type: str) -> dict:
        return {
            "detected_type": detected_type, "document_type": "TEXT",
            "transaction_type_fa": "گزارش وضعیت پروژه", "amount": 0,
            "description": "x", "payment_method": "UNKNOWN",
            "payment_state": "UNKNOWN", "is_cheque": False,
            "manager_fee_eligible": False, "confidence": 0.9,
        }

    def test_explicit_calendar_caption_forces_note_type_on_info(self):
        data = self._base("INFO")
        out = GeminiFinancialParser._normalize(
            data, text="یادداشت-تقویم کارگاهی:\nکار کرد ناصر از ۹ شهریور تا ۱۳ شهریور برای ابراهیم"
        )
        self.assertEqual(out["note_type"], "تقویم_کارگاهی")
        self.assertEqual(out["detected_type"], "INFO")

    def test_explicit_calendar_caption_resolves_unknown_to_info(self):
        data = self._base("UNKNOWN")
        out = GeminiFinancialParser._normalize(data, text="داکیومنت-تقویم: ۱۱ شهریور ۴۰۵")
        self.assertEqual(out["note_type"], "تقویم_کارگاهی")
        self.assertEqual(out["detected_type"], "INFO")

    def test_explicit_invoice_caption_forces_note_type_on_info(self):
        # «فاکتور» here is the note_type/title category, distinct from
        # document_type=INVOICE which classifies an attached image.
        data = self._base("EXPENSE")
        out = GeminiFinancialParser._normalize(data, text="فاکتور: خرید سیمان از فروشنده الف")
        self.assertEqual(out["note_type"], "فاکتور")
        self.assertEqual(out["detected_type"], "INFO")

    def test_calendar_caption_does_not_override_expense(self):
        data = self._base("EXPENSE")
        out = GeminiFinancialParser._normalize(
            data, text="تقویم پرداخت شد ۲۰۰۰۰۰ تومان بابت مصالح"
        )
        self.assertEqual(out["detected_type"], "EXPENSE")
        self.assertNotIn("note_type", out)

    def test_a_first_line_starting_with_a_title_files_a_note_under_it(self):
        data = self._base("INFO")
        out = GeminiFinancialParser._normalize(data, text="گزارش روزانه امروز کار خوب پیش رفت")
        self.assertEqual(out["note_type"], "گزارش_روزانه")

    def test_no_title_leaves_note_type_untouched(self):
        data = self._base("INFO")
        out = GeminiFinancialParser._normalize(data, text="امروز کار خوب پیش رفت")
        self.assertNotIn("note_type", out)


class ExplicitTitleTests(unittest.TestCase):
    """The operator titles every non-financial message; the title decides the category.

    The examples are the operator's own first lines from live messages.
    """

    def _out(self, detected, text, **extra):
        from ai_parser import apply_explicit_note_title
        return apply_explicit_note_title({"detected_type": detected, "confidence": 0.3, **extra}, text)

    def test_the_operators_real_titles(self):
        cases = {
            "گزارش روزانه ۵ مهر ۴۰۵:\n۱.شروع عملیات حفاری چاه جذبی": ("INFO", "گزارش_روزانه"),
            "گزارش روزانه از ۲۸ شهریور تا ۳ مهر\nکارگاه تعطیل": ("INFO", "گزارش_روزانه"),
            "تقویم کارگاهی:\n۵ مهر ۴۰۵ شروع چاه کنی": ("INFO", "تقویم_کارگاهی"),
            "داکیومنت-تقویم: ۱۴ شهریور ۴۰۵:\n۱.ادامه آرماتوربندی": ("INFO", "تقویم_کارگاهی"),
            "یادداشت- داکیومنت\nقبض های بتن ریزی": ("DOCUMENT", "داکیومنت"),
            "داکیومنت: قرارداد بتن فونداسیون": ("DOCUMENT", "داکیومنت"),
            "یادآوری: فردا تمدید بیمه": ("INFO", "یادآوری"),
            "یادداشت:\nعرض راه پله ۲.۴ باید باشد": ("INFO", "یادداشت"),
            "اطلاع رسانی\nتا الان ۲ میلیارد پرداخت شده": ("INFO", "اطلاع_رسانی"),
            "#یادآوری پرداخت قسط": ("INFO", "یادآوری"),
            "فاکتور:\nخرید سیمان ۵۰ کیسه": ("INFO", "فاکتور"),
        }
        for text, (detected, note) in cases.items():
            with self.subTest(text=text):
                out = self._out("UNKNOWN", text)
                self.assertEqual((out["detected_type"], out["note_type"]), (detected, note))
                self.assertEqual(out["transaction_title"], "یادداشت")
                self.assertGreaterEqual(out["confidence"], 0.9)

    def test_a_clear_title_overrides_a_financial_guess(self):
        out = self._out("EXPENSE", "گزارش روزانه ۱۹ شهریور ۴۰۵:\nبتن ریزی فونداسیون ۱۳۵ متر",
                        manager_fee_eligible=True, payment_state="PAID")
        self.assertEqual(out["detected_type"], "INFO")
        self.assertEqual(out["note_type"], "گزارش_روزانه")
        self.assertFalse(out["manager_fee_eligible"])

    def test_a_title_word_inside_a_money_message_does_not(self):
        for text in ("تقویم پرداخت شد ۲۰۰۰۰۰ تومان بابت مصالح", "هزینه ساخت\nیادداشت",
                     "قبض ماسه داکیومنت"):
            with self.subTest(text=text):
                out = self._out("EXPENSE", text)
                self.assertEqual(out["detected_type"], "EXPENSE")
                self.assertNotIn("note_type", out)

    def test_money_messages_without_a_title_are_left_alone(self):
        for text in ("هزینه ساخت\nکنتور موقت\nفاز تجهیز کارگاه\nخدمات", "خرید سیمان ۲ میلیون"):
            with self.subTest(text=text):
                self.assertNotIn("note_type", self._out("EXPENSE", text))

    def test_the_local_fallback_files_by_title_too(self):
        from local_fallback_parser import analyze_locally
        out = analyze_locally("گزارش روزانه ۴ مهر ۴۰۵:\n۱.کارگاه تعطیل")
        self.assertEqual((out["detected_type"], out["note_type"]), ("INFO", "گزارش_روزانه"))

    def test_the_data_entry_tab_shows_the_category(self):
        import dashboard_stage18_7  # noqa: F401  (adds the seven subtypes)
        import dashboard_stage18 as v18
        self.assertEqual(v18._title_type_from_payload(self._out("UNKNOWN", "تقویم کارگاهی:\n۵ مهر")),
                         ("یادداشت", "تقویم کارگاهی"))
        # A category the model chose (no title) also reaches the tab.
        self.assertEqual(v18._title_type_from_payload({"detected_type": "INFO", "note_type": "یادآوری"}),
                         ("یادداشت", "یادآوری"))
        self.assertEqual(v18._title_type_from_payload({"detected_type": "INFO", "note_type": "فاکتور"}),
                         ("یادداشت", "فاکتور"))

    def test_the_schema_has_no_empty_enum_value(self):
        # Gemini rejected every request over one: «enum[0]: cannot be empty».
        from ai_parser import ANALYSIS_SCHEMA

        def enums(node):
            if isinstance(node, dict):
                if "enum" in node:
                    yield node["enum"]
                for value in node.values():
                    yield from enums(value)

        for values in enums(ANALYSIS_SCHEMA):
            self.assertNotIn("", values)


class SubCategoryRoutingTests(unittest.TestCase):
    """sub_category is required in ANALYSIS_SCHEMA so Gemini must always
    return a value (unlike the four legacy fields it replaces, which stayed
    unset on ~100% of live pending_items - 0 of 90+ EXPENSE/INCOME/OUTFLOW
    rows and 1 of 47 INFO rows had their sub-field filled). _normalize routes
    that value into whichever legacy field the rest of the app already
    reads (e.g. dashboard_stage18_7._outflow_type_187 keys off outflow_type)."""

    def _base(self, detected_type: str, sub_category: str) -> dict:
        return {
            "detected_type": detected_type, "document_type": "TEXT",
            "transaction_type_fa": "x", "amount": 0, "description": "x",
            "payment_method": "UNKNOWN", "payment_state": "UNKNOWN",
            "is_cheque": False, "manager_fee_eligible": False, "confidence": 0.9,
            "sub_category": sub_category,
        }

    def test_expense_routes_to_expense_cost_type(self):
        out = GeminiFinancialParser._normalize(self._base("EXPENSE", "مصالح"), text="خرید سیمان")
        self.assertEqual(out["expense_cost_type"], "مصالح")
        self.assertNotIn("income_source_type", out)
        self.assertNotIn("outflow_type", out)
        self.assertNotIn("note_type", out)

    def test_income_routes_to_income_source_type(self):
        out = GeminiFinancialParser._normalize(self._base("INCOME", "فروش"), text="فروش واحد")
        self.assertEqual(out["income_source_type"], "فروش")

    def test_outflow_routes_to_outflow_type(self):
        out = GeminiFinancialParser._normalize(self._base("OUTFLOW", "اقساط"), text="قسط وام")
        self.assertEqual(out["outflow_type"], "اقساط")

    def test_info_routes_to_note_type(self):
        out = GeminiFinancialParser._normalize(self._base("INFO", "گزارش_روزانه"), text="امروز کار خوب پیش رفت")
        self.assertEqual(out["note_type"], "گزارش_روزانه")

    def test_info_routes_invoice_sub_category_to_note_type(self):
        out = GeminiFinancialParser._normalize(self._base("INFO", "فاکتور"), text="فاکتور خرید مصالح")
        self.assertEqual(out["note_type"], "فاکتور")

    def test_wrong_namespace_value_is_dropped_not_misassigned(self):
        # A value that only makes sense for OUTFLOW showing up on an EXPENSE
        # (a plausible model mistake) must not leak into expense_cost_type.
        out = GeminiFinancialParser._normalize(self._base("EXPENSE", "اقساط"), text="x")
        self.assertNotIn("expense_cost_type", out)

    def test_cheque_and_unknown_ignore_sub_category(self):
        out = GeminiFinancialParser._normalize(self._base("CHEQUE", "هیچکدام"), text="x")
        self.assertNotIn("expense_cost_type", out)
        self.assertNotIn("income_source_type", out)
        self.assertNotIn("outflow_type", out)
        self.assertNotIn("note_type", out)


class GeminiClientLifecycleTests(unittest.TestCase):
    """google-genai's async client binds its transport to whichever asyncio
    event loop is running when it is first used. GeminiFinancialParser is a
    long-lived module-level singleton (AI_PARSER/RECEIPT_PARSER/PARSER)
    reused across many separate asyncio.run() calls - every GUI reprocess
    click spawns its own thread and a brand-new event loop
    (dashboard_stage18_2.reprocess_rows). A client cached on self therefore
    raised "RuntimeError: Event loop is closed" on the second and every
    later reprocess call in the same running app - confirmed live by the
    operator (PEN-55036ECEA820), right after the reprocess fixes made calls
    reach Gemini far more often than before. analyze() must build a fresh
    client every call instead."""

    @staticmethod
    def _fake_genai(calls: list):
        class FakeAioModels:
            def __init__(self, owner_loop):
                self._owner_loop = owner_loop

            async def generate_content(self, **kwargs):
                if asyncio.get_running_loop() is not self._owner_loop:
                    raise RuntimeError("Event loop is closed")

                class Resp:
                    text = (
                        '{"detected_type":"INFO","document_type":"TEXT","transaction_type_fa":"x",'
                        '"amount":0,"description":"x","payment_method":"UNKNOWN","payment_state":"UNKNOWN",'
                        '"is_cheque":false,"manager_fee_eligible":false,"confidence":0.5,"sub_category":"هیچکدام"}'
                    )
                return Resp()

        class FakeAio:
            def __init__(self, owner_loop):
                self.models = FakeAioModels(owner_loop)
                self.closed = False

            async def aclose(self):
                self.closed = True

        class FakeClient:
            def __init__(self, api_key):
                self.aio = FakeAio(asyncio.get_running_loop())
                calls.append(self)

        class FakeGenaiModule:
            Client = FakeClient

        return FakeGenaiModule()

    def test_analyze_survives_two_separate_event_loops(self):
        # Bypass __init__ (which does a real `from google import genai`) and
        # inject a fake module instead - exercises exactly what analyze()
        # does with self._genai, same as the real constructor would set up.
        parser = GeminiFinancialParser.__new__(GeminiFinancialParser)
        calls: list = []
        parser._genai = self._fake_genai(calls)
        parser._types = type("FakeTypes", (), {
            "GenerateContentConfig": lambda **kwargs: None,
        })
        parser._api_key = "fake"
        parser.model = "fake-model"

        # Two SEPARATE asyncio.run() calls, exactly like two separate GUI
        # reprocess clicks each spawning their own thread + event loop. The
        # old code (a client cached in __init__) would raise on the second
        # call; this must succeed both times.
        out1 = asyncio.run(parser.analyze(text="پیام یک"))
        out2 = asyncio.run(parser.analyze(text="پیام دو"))

        self.assertEqual(out1["detected_type"], "INFO")
        self.assertEqual(out2["detected_type"], "INFO")
        self.assertEqual(len(calls), 2, "a fresh client must be built for every analyze() call")
        self.assertTrue(calls[0].aio.closed, "each call's client must be closed before its loop closes")
        self.assertTrue(calls[1].aio.closed)


class ConstructionPhaseTests(unittest.TestCase):
    def test_only_one_of_the_32_project_phases_is_kept(self):
        base = {
            'detected_type': 'EXPENSE', 'document_type': 'TEXT', 'amount': 100,
            'description': 'بتن', 'payment_method': 'CASH', 'payment_state': 'PAID',
            'is_cheque': False, 'manager_fee_eligible': True, 'confidence': 0.8,
        }
        valid = GeminiFinancialParser._normalize({**base, 'construction_stage': '08 - اسکلت'})
        invalid = GeminiFinancialParser._normalize({**base, 'construction_stage': 'مرحله دلخواه مدل'})
        self.assertEqual(valid['construction_stage'], 'اسکلت')
        self.assertEqual(invalid['construction_stage'], '')
        self.assertEqual(len(__import__('ai_parser').CONSTRUCTION_PHASES), 32)


if __name__ == "__main__":
    unittest.main()
