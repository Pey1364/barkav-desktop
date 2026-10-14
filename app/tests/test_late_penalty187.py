"""A late instalment: the bank adds the loan's interest rate plus 6 points a year on the unpaid instalment, for each day
after its due date (365-day year, rounded to the unit). Such a payment is posted only after the person confirms it; a row
takes its late payment only when it is paid in full; the row, the loan's total repayment and the transaction change together."""
from datetime import date, timedelta

import pytest

from loan_service import gregorian_to_shamsi, late_penalty_amount, late_penalty_rate
from test_transaction_lifecycle_matrix import m, register, runtime  # noqa: F401
from test_stage18_7_record_fields import root  # noqa: F401
from test_loan_record_approve187 import RealDashboard, _errors  # noqa: F401

RATE = 23.0  # the loans of the two receipts: 23 + 6 = 29


def _penalty(base, days, rate=RATE):
    return late_penalty_amount(base, days, late_penalty_rate(rate))


def _loan(runtime, count=6, principal=60_000_000, rate=RATE):
    # six instalments of 10,000,000 and no interest in the schedule; the first is due on 1405/02/01
    return m.LoanService(runtime.db).create_loan(
        lender_name='بانک آزمون', principal_amount=principal, net_received_amount=principal,
        received_date_shamsi='1405/01/01', installment_count=count, first_due_date_shamsi='1405/02/01',
        interest_rate=rate, description='وام دیرکرد آزمون', register_cash=False)


def _rows(runtime, loan_id):
    with runtime.db.read() as con:
        return [dict(r) for r in con.execute(
            'SELECT * FROM loan_installments WHERE loan_id=? ORDER BY installment_number', (loan_id,))]


def _shamsi_after(row, days):
    """The Shamsi date `days` after the row's due date (negative: before it)."""
    return gregorian_to_shamsi(date.fromisoformat(str(row['due_date'])[:10]) + timedelta(days=days))


def _payload(loan, row, days, *, amount=None, count=1):
    base = int(row['amount'])
    if amount is None:
        amount = base + _penalty(base, days, loan['interest_rate'])
    return dict(detected_type='OUTFLOW', v18_title='خروجی', v18_subtype='اقساط',
                event_date_shamsi=_shamsi_after(row, days), amount=amount, description='قسط دیرکرد',
                loan_id=loan['loan_id'], installment_count=6, paid_installments_before=0,
                installments_paid_now=count)


def test_the_late_rate_is_the_loan_rate_plus_six_points_over_a_365_day_year():
    assert late_penalty_rate(23) == 29
    assert late_penalty_rate(0) == 6
    assert late_penalty_rate(None) == 6
    assert late_penalty_amount(10_000_000, 365, 29) == 2_900_000
    assert late_penalty_amount(10_000_000, 26, 29) == 206_575
    assert late_penalty_amount(10_000_000, 26, 6) == 42_740
    assert late_penalty_amount(10_000_000, 0, 29) == 0
    assert late_penalty_amount(0, 26, 29) == 0


def test_each_loan_is_late_at_its_own_rate(runtime):
    loan = _loan(runtime, rate=18)
    row = _rows(runtime, loan['loan_id'])[0]
    base = int(row['amount'])
    plan = m.LoanService(runtime.db).plan_installment_payment(
        loan['loan_id'], amount=base + late_penalty_amount(base, 26, 24), count=1,
        paid_date_shamsi=_shamsi_after(row, 26))
    item = plan['items'][0]
    assert item['penalty_rate'] == 24
    assert item['penalty'] == late_penalty_amount(base, 26, 24) and item['posted_penalty'] == item['penalty']
    assert plan['leftover'] == 0 and plan['mismatch'] is None


def test_a_late_instalment_takes_its_late_payment_only_when_it_is_paid_in_full(runtime):
    loan = _loan(runtime)
    row = _rows(runtime, loan['loan_id'])[0]
    base = int(row['amount'])
    penalty = _penalty(base, 26)
    service = m.LoanService(runtime.db)
    plan = service.plan_installment_payment(loan['loan_id'], amount=base + penalty, count=1,
                                            paid_date_shamsi=_shamsi_after(row, 26))
    item = plan['items'][0]
    assert plan['leftover'] == 0 and plan['mismatch'] is None
    assert (item['days_late'], item['penalty'], item['pay'], item['posted_penalty']) == (26, penalty, base + penalty, penalty)
    plan = service.plan_installment_payment(loan['loan_id'], amount=base, count=1,
                                            paid_date_shamsi=_shamsi_after(row, 26))
    assert plan['items'][0]['pay'] == base and plan['items'][0]['posted_penalty'] == 0
    plan = service.plan_installment_payment(loan['loan_id'], amount=base + 1, count=1,
                                            paid_date_shamsi=_shamsi_after(row, 26))
    assert plan['mismatch'] is not None  # above the instalment, below the instalment with its late payment


def test_posting_a_late_payment_updates_the_row_the_loan_and_the_transaction_together(runtime):
    loan = _loan(runtime)
    row = _rows(runtime, loan['loan_id'])[0]
    base = int(row['amount'])
    penalty = _penalty(base, 26)
    before = m.LoanService(runtime.db).get_loan(loan['loan_id'])['total_repayment']
    posted = m.LoanService(runtime.db).pay_installments_with_penalties(
        [{'loan_installment_id': row['loan_installment_id'], 'amount': base + penalty, 'penalty': penalty}],
        paid_date_shamsi=_shamsi_after(row, 26))
    assert posted[0]['status'] == 'PAID'
    after = _rows(runtime, loan['loan_id'])[0]
    assert (after['amount'], after['paid_amount'], after['status']) == (base + penalty, base + penalty, 'PAID')
    assert m.LoanService(runtime.db).get_loan(loan['loan_id'])['total_repayment'] == before + penalty
    with runtime.db.read() as con:
        amount, note = con.execute('SELECT amount, description FROM transactions WHERE transaction_id=?',
                                   (posted[0]['transaction_id'],)).fetchone()
    assert amount == base + penalty and str(penalty) in note


def test_approval_refuses_a_late_payment_until_the_person_has_confirmed_it(runtime):
    loan = _loan(runtime)
    row = _rows(runtime, loan['loan_id'])[0]
    payload = _payload(loan, row, 26)
    pid = register(runtime, payload, message_id=11)
    with pytest.raises(ValueError, match='دیرکرد این قسط'):
        m._approve_v18_187(pid, payload, runtime.rich)
    assert _rows(runtime, loan['loan_id'])[0]['status'] != 'PAID'  # nothing was posted
    payload['late_penalty_accepted187'] = True
    assert 'دیرکرد' in m._approve_v18_187(pid, payload, runtime.rich)
    assert _rows(runtime, loan['loan_id'])[0]['status'] == 'PAID'


def test_the_confirmation_names_the_late_payment_and_marks_the_payment_only_when_accepted(runtime, monkeypatch):
    loan = _loan(runtime)
    payload = _payload(loan, _rows(runtime, loan['loan_id'])[0], 26)
    asked = []
    monkeypatch.setattr(m, '_ask_late_penalty_187', lambda form, text: asked.append(text) or False)
    assert m._confirm_late_penalty_187(None, payload) is False
    assert 'late_penalty_accepted187' not in payload
    assert 'دلیل افزایش قسط دیرکرد هست' in asked[0]
    assert 'با نرخ ۲۹٪' in asked[0]  # the loan's own rate plus six points
    monkeypatch.setattr(m, '_ask_late_penalty_187', lambda form, text: True)
    assert m._confirm_late_penalty_187(None, payload) is True
    assert payload['late_penalty_accepted187'] is True


def test_a_payment_on_time_asks_nothing(runtime, monkeypatch):
    loan = _loan(runtime)
    payload = _payload(loan, _rows(runtime, loan['loan_id'])[0], 0)
    monkeypatch.setattr(m, '_ask_late_penalty_187', lambda *_: pytest.fail('asked about a payment that is not late'))
    assert m._confirm_late_penalty_187(None, payload) is True


def test_an_amount_above_the_late_instalment_is_refused_before_anyone_is_asked(runtime, monkeypatch):
    loan = _loan(runtime)
    row = _rows(runtime, loan['loan_id'])[0]
    base = int(row['amount'])
    payload = _payload(loan, row, 26, amount=base + _penalty(base, 26) + 1)
    monkeypatch.setattr(m, '_ask_late_penalty_187', lambda *_: pytest.fail('asked before refusing'))
    with pytest.raises(ValueError, match='بیشتر است'):
        m._confirm_late_penalty_187(None, payload)


def test_an_amount_between_the_instalment_and_its_late_payment_is_refused_with_both_figures(runtime):
    loan = _loan(runtime)
    row = _rows(runtime, loan['loan_id'])[0]
    payload = _payload(loan, row, 26, amount=int(row['amount']) + 1)
    with pytest.raises(ValueError, match='نه برابر قسط'):
        m._confirm_late_penalty_187(None, payload)


def test_two_late_instalments_paid_together_each_take_their_late_payment_after_one_question(runtime, monkeypatch):
    loan = _loan(runtime)
    first, second = _rows(runtime, loan['loan_id'])[:2]
    base = int(first['amount'])
    second_days = 5
    first_days = (date.fromisoformat(str(second['due_date'])[:10]) + timedelta(days=second_days)
                  - date.fromisoformat(str(first['due_date'])[:10])).days
    amount = 2 * base + _penalty(base, first_days) + _penalty(base, second_days)
    payload = _payload(loan, second, second_days, amount=amount, count=2)
    pid = register(runtime, payload, message_id=12)
    asked = []
    monkeypatch.setattr(m, '_ask_late_penalty_187', lambda form, text: asked.append(text) or True)
    assert m._confirm_late_penalty_187(None, payload) is True
    assert len(asked) == 1 and 'قسط ۱' in asked[0] and 'قسط ۲' in asked[0]
    before = m.LoanService(runtime.db).get_loan(loan['loan_id'])['total_repayment']
    message = m._approve_v18_187(pid, payload, runtime.rich)
    assert '۲ قسط' in message
    assert [row['status'] for row in _rows(runtime, loan['loan_id'])[:2]] == ['PAID', 'PAID']
    assert m.LoanService(runtime.db).get_loan(loan['loan_id'])['total_repayment'] == (
        before + _penalty(base, first_days) + _penalty(base, second_days))


def test_the_record_window_asks_before_posting_a_late_payment_and_posts_it_once_confirmed(root, runtime, monkeypatch):
    monkeypatch.setattr(m, 'show_toast', lambda *args, **kwargs: None)
    errors = _errors(monkeypatch)
    loan = _loan(runtime)
    row = _rows(runtime, loan['loan_id'])[0]
    pid = register(runtime, _payload(loan, row, 26), message_id=13)
    asked = []
    monkeypatch.setattr(m, '_ask_late_penalty_187', lambda form, text: asked.append(text) or False)
    form = m.v182.UnifiedPendingEditor182(RealDashboard(root), runtime.db.get_pending_item(pid), runtime.rich,
                                          lambda: None)
    root.update()
    form.approve()
    root.update()
    assert len(asked) == 1 and 'دلیل افزایش قسط دیرکرد هست' in asked[0]
    assert _rows(runtime, loan['loan_id'])[0]['status'] != 'PAID'  # cancelled: nothing was posted
    assert errors == []
    monkeypatch.setattr(m, '_ask_late_penalty_187', lambda form, text: True)
    form.approve()
    root.update()
    assert errors == []
    assert _rows(runtime, loan['loan_id'])[0]['status'] == 'PAID'
