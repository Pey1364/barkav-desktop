import unittest

from local_fallback_parser import analyze_locally
from edit_field_parser import parse_edit_fields
from financial_posting import build_posting_plan


class Stage61DueDateTests(unittest.TestCase):
    def test_fallback_extracts_explicit_cheque_due_date(self):
        p = analyze_locally('#تست 50 میلیون بابت خرید سیمان با چک، سررسید 1405/05/22')
        self.assertEqual(p['detected_type'], 'EXPENSE')
        self.assertEqual(p['payment_method'], 'CHEQUE')
        self.assertEqual(p['due_date_shamsi'], '1405/05/22')

    def test_fallback_normalizes_persian_digits(self):
        p = analyze_locally('#چک ۵۰ میلیون موعد چک ۱۴۰۵/۵/۲۲')
        self.assertEqual(p['due_date_shamsi'], '1405/05/22')

    def test_edit_accepts_cheque_due_date_alias(self):
        changes = parse_edit_fields('سررسید چک: 1405/05/22\nروش پرداخت: چک')
        self.assertEqual(changes['due_date_shamsi'], '1405/05/22')
        self.assertEqual(changes['payment_method'], 'CHEQUE')

    def test_posting_plan_accepts_extracted_due_date(self):
        p = analyze_locally('#تست 50 میلیون بابت خرید سیمان با چک، سررسید 1405/05/22')
        plan = build_posting_plan(payload=p, raw_text='#تست 50 میلیون بابت خرید سیمان با چک، سررسید 1405/05/22', telegram_message_date='1405/05/19 10:00')
        self.assertEqual(plan['due_date_shamsi'], '1405/05/22')
        self.assertTrue(plan['due_date'])
        self.assertTrue(plan['is_cheque'])


if __name__ == '__main__':
    unittest.main()
