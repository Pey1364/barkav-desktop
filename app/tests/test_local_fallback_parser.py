import unittest

from local_fallback_parser import analyze_locally


class LocalFallbackParserTests(unittest.TestCase):
    def test_construction_expense_paid(self):
        p = analyze_locally('#تست 100 میلیون بابت خرید بتن پرداخت کردم')
        self.assertEqual(p['detected_type'], 'EXPENSE')
        self.assertEqual(p['amount'], 100_000_000)
        self.assertEqual(p['final_amount'], 100_000_000)
        self.assertEqual(p['payment_state'], 'PAID')
        self.assertTrue(p['manager_fee_eligible'])

    def test_explicit_income(self):
        p = analyze_locally('#ورودی 2 میلیارد آورده شریک')
        self.assertEqual(p['detected_type'], 'INCOME')
        self.assertEqual(p['amount'], 2_000_000_000)
        self.assertFalse(p['manager_fee_eligible'])

    def test_manager_salary_is_nonconstruction_outflow(self):
        p = analyze_locally('50 میلیون برداشت حقوق پیمان')
        self.assertEqual(p['detected_type'], 'OUTFLOW')
        self.assertEqual(p['amount'], 50_000_000)

    def test_cheque_description_keeps_only_purchase_purpose(self):
        p = analyze_locally("#تست 50 میلیون بابت خرید سیمان با چک، سررسید 1405/05/22")
        self.assertEqual(p["description"], "سیمان")
        self.assertEqual(p["due_date_shamsi"], "1405/05/22")

    def test_unknown_text_stays_review(self):
        p = analyze_locally('این پیام فقط یک یادداشت است')
        self.assertEqual(p['detected_type'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
