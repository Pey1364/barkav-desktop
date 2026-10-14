import unittest
from loan_input import parse_loan_form, validate_loan_form


class LoanInputTests(unittest.TestCase):
    def test_parse_full_form_and_infer_interest(self):
        d=parse_loan_form('''بانک / وام‌دهنده: بانک ملت
نوع وام: وام بانکی
اصل وام: 1 میلیارد
مبلغ واقعی واریزی: 980 میلیون
تاریخ دریافت: 1405/05/20
نرخ سود: 18%
تعداد اقساط: 12
مبلغ هر قسط: 100 میلیون
تاریخ اولین قسط: 1405/06/20
ضامنین: علی، رضا
کارمزد: 20 میلیون''')
        self.assertEqual(d['lender_name'],'بانک ملت')
        self.assertEqual(d['principal_amount'],1_000_000_000)
        self.assertEqual(d['net_received_amount'],980_000_000)
        self.assertEqual(d['total_interest'],180_000_000)
        self.assertEqual(d['received_date_shamsi'],'1405/05/20')
        self.assertEqual(d['first_due_date_shamsi'],'1405/06/20')
        self.assertEqual(validate_loan_form(d),[])

    def test_count_requires_first_due(self):
        d=parse_loan_form('''بانک: بانک ملی
اصل وام: 500 میلیون
تاریخ دریافت: 1405/05/20
تعداد اقساط: 10''')
        self.assertIn('تاریخ اولین قسط',validate_loan_form(d))

if __name__=='__main__':
    unittest.main()
