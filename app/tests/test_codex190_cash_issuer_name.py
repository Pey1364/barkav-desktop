from financial_posting import build_posting_plan


def test_cash_expense_preserves_the_non_receiver_account_owner():
    plan = build_posting_plan(
        payload={
            'detected_type': 'EXPENSE', 'amount': 250000, 'final_amount': 250000,
            'invoice_amount': 250000, 'description': 'مصالح', 'payment_method': 'CASH',
            'payment_state': 'PAID', 'issuer_name': 'صاحب کارت ثالث',
        },
        raw_text='پرداخت نقدی',
        telegram_message_date='1405/06/01',
    )

    assert plan['issuer_name'] == 'صاحب کارت ثالث'
