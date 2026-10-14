import unittest

from revenue_input import parse_received_payment_form, parse_sale_form


class Stage7InputTests(unittest.TestCase):
    def test_parse_sale_form_persian(self):
        data = parse_sale_form("""
پروژه: بارکاو
بلوک: A
واحد: 12
طبقه: 3
متراژ: 120
خریدار: علی رضایی
تاریخ قرارداد: ۱۴۰۵/۰۵/۲۰
مبلغ قرارداد: 10 میلیارد
اقساط:
۱۴۰۵/۰۵/۲۰ = 3 میلیارد
1405/06/20 = 3 میلیارد
1405/07/20 = 4 میلیارد
""")
        self.assertEqual(data["unit_number"], "12")
        self.assertEqual(data["contract_date_shamsi"], "1405/05/20")
        self.assertEqual(data["contract_amount"], 10_000_000_000)
        self.assertEqual(sum(x["amount"] for x in data["installments"]), 10_000_000_000)

    def test_parse_received_payment_form(self):
        data = parse_received_payment_form("""
Sale ID: SALE-ABC123
مبلغ: 1.5 میلیارد
تاریخ وصول: ۱۴۰۵/۰۵/۲۱
پرداخت‌کننده: علی رضایی
شرح: قسط اول
""")
        self.assertEqual(data["sale_id"], "SALE-ABC123")
        self.assertEqual(data["amount"], 1_500_000_000)
        self.assertEqual(data["received_date_shamsi"], "1405/05/21")
        self.assertEqual(data["payer_name"], "علی رضایی")


if __name__ == '__main__':
    unittest.main()
