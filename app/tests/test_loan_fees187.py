"""Loan: the fees are the requested amount less what the bank paid in; the instalments are an annuity on the requested
amount and never add the fees again; a loan has no payment method; the record window's titles wrap."""
import tkinter as tk
from types import SimpleNamespace

from test_loan_record_approve187 import LOAN, RealDashboard, _approved_loan, _errors  # noqa: F401
from test_transaction_lifecycle_matrix import m, runtime, register  # noqa: F401
from test_stage18_7_record_fields import root  # noqa: F401


class Var:
    def __init__(self, value=''):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _form(**values):
    names = ('loan_total_amount', 'amount', 'interest_rate', 'installment_count', 'installment_amount', 'total_interest',
             'bank_fees', 'first_due_date_shamsi', 'loan_end_date', 'loan_start_date', 'loan_name')
    return SimpleNamespace(vars={name: Var(values.get(name, '')) for name in names}, payload={'v18_title': 'ورودی'}, _loading=False)


def _type(form, key, value):
    form.vars[key].set(value)
    m._sync_loan_fields_187(form, key)


# ---- fees ----------------------------------------------------------------------------------------------------------

def test_the_fees_are_the_requested_amount_less_the_deposit():
    form = _form()
    _type(form, 'loan_total_amount', '39,707,149')
    _type(form, 'amount', '39,500,000')
    assert m.parse_int(form.vars['bank_fees'].get()) == 207_149
    _type(form, 'amount', '39,000,000')
    assert m.parse_int(form.vars['bank_fees'].get()) == 707_149
    assert form.payload['bank_fees'] == 707_149


def test_there_are_no_fees_before_the_deposit_is_known_or_when_it_is_not_below_the_request():
    assert m._loan_fees_187(1000, 0) == 0
    assert m._loan_fees_187(0, 900) == 0
    assert m._loan_fees_187(1000, 1000) == 0
    assert m._loan_fees_187(1000, 1100) == 0
    assert m._loan_fees_187(1000, 900) == 100


def test_the_fees_box_is_read_only_and_the_computed_dates_are_date_fields():
    fields = {field.key: field for field in m._special_fields_187('ورودی', 'تسهیلات')}
    assert fields['bank_fees'].readonly
    for key in ('loan_end_date', 'last_paid_date_shamsi'):
        assert fields[key].kind == 'date' and fields[key].readonly


# ---- the instalment is an annuity on the requested amount -----------------------------------------------------------

def _annuity(principal, annual_percent, count):
    monthly = annual_percent / 100 / 12
    return principal * monthly * (1 + monthly) ** count / ((1 + monthly) ** count - 1)


def test_the_instalment_is_the_annuity_of_the_requested_amount():
    for principal, rate, count in ((39_707_149, 23.0, 12), (100_000_000, 24.0, 12), (66_635_054, 23.0, 24), (5_000_000, 18.5, 6)):
        assert abs(m.calculate_loan_installment_187(principal, rate, count) - _annuity(principal, rate, count)) <= 1
    assert m.calculate_loan_installment_187(100_000_000, 24.0, 12) == 9_455_960  # the textbook figure
    assert m.calculate_loan_installment_187(1200, 0, 12) == 100


def test_the_instalment_follows_the_requested_amount_not_the_deposit():
    form = _form()
    _type(form, 'installment_count', '12')
    _type(form, 'interest_rate', '23')
    _type(form, 'amount', '39,500,000')
    _type(form, 'loan_total_amount', '39,707,149')
    assert m.parse_int(form.vars['installment_amount'].get()) == m.calculate_loan_installment_187(39_707_149, 23.0, 12)
    _type(form, 'amount', '30,000,000')  # the deposit changes, the instalment does not
    assert m.parse_int(form.vars['installment_amount'].get()) == m.calculate_loan_installment_187(39_707_149, 23.0, 12)


# ---- the fees are not repaid a second time --------------------------------------------------------------------------

def test_a_loan_whose_fees_were_kept_back_repays_only_the_principal_and_the_interest(runtime):
    payload = dict(LOAN, amount=900, loan_total_amount=1000, installment_count=4, interest_rate=0)
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, runtime.db.get_pending_item(pid)['payload'], runtime.rich)
    with runtime.db.read() as con:
        loan = dict(con.execute('SELECT * FROM loans').fetchone())
        schedule = [row[0] for row in con.execute('SELECT amount FROM loan_installments ORDER BY installment_number')]
    assert loan['bank_fees'] == 100 and loan['net_received_amount'] == 900
    assert loan['total_repayment'] == 1000 and sum(schedule) == 1000 and len(set(schedule)) == 1


def test_fees_that_are_not_the_difference_are_still_added_by_the_service(runtime):
    loan = m.LoanService(runtime.db).create_loan(
        lender_name='بانک', principal_amount=1000, net_received_amount=1000, received_date_shamsi='1405/07/08',
        total_interest=0, bank_fees=50, installment_count=2, first_due_date_shamsi='1405/08/08')
    assert loan['total_repayment'] == 1050


def test_editing_a_loan_in_the_record_window_recomputes_the_fees_and_keeps_the_repayment(root, runtime, monkeypatch):
    pid, loan_id = _approved_loan(runtime)
    monkeypatch.setattr(m, 'show_toast', lambda *args, **kwargs: None)
    errors = _errors(monkeypatch)
    form = m.v182.UnifiedPendingEditor182(RealDashboard(root), runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    form.vars['amount'].set('900')
    form.approve()
    root.update()
    assert errors == []
    with runtime.db.read() as con:
        loan = dict(con.execute('SELECT * FROM loans WHERE loan_id=?', (loan_id,)).fetchone())
        schedule = [row[0] for row in con.execute('SELECT amount FROM loan_installments WHERE loan_id=? ORDER BY installment_number', (loan_id,))]
    assert loan['bank_fees'] == 100
    assert loan['total_repayment'] == sum(schedule) == loan['installment_amount'] * loan['installment_count']


# ---- no payment method on a loan ----------------------------------------------------------------------------------

def test_a_loan_has_no_payment_method_in_the_record_window_or_the_wizard():
    assert 'payment_method' not in [field.key for field in m._special_fields_187('ورودی', 'تسهیلات')]
    pages = m._facility_wizard_pages_187([])
    assert 'payment_method' not in [field.key for page in pages for field in page]
    assert 'payment_method' not in [field.key for page in m._wizard_steps_187('ورودی', 'تسهیلات') for field in page]


def test_the_record_window_of_a_loan_shows_no_payment_method(root, runtime):
    pid, _loan_id = _approved_loan(runtime)
    form = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    root.update()
    assert 'payment_method' not in form.widgets


# ---- titles wrap ----------------------------------------------------------------------------------------------------

def test_the_field_titles_of_the_loan_record_window_wrap_instead_of_being_cut(root, runtime):
    pid, _loan_id = _approved_loan(runtime)
    form = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    root.update()
    for key in ('remaining_installments', 'paid_installments_count', 'last_paid_date_shamsi'):
        label = form.widgets[key].master.grid_slaves(row=0, column=0)[0]
        assert isinstance(label, tk.Label) and int(label.cget('wraplength')) >= 110, key
