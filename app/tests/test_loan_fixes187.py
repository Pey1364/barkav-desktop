"""The loan wizard and the loan record window (commit cb5c813) build, and the installment box can be typed in."""
from types import SimpleNamespace

from test_transaction_lifecycle_matrix import m  # noqa: F401  (boots the app modules)


class Var:
    def __init__(self, value=''):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _loan_form(**values):
    names = ('loan_total_amount', 'interest_rate', 'installment_count', 'installment_amount', 'total_interest',
             'first_due_date_shamsi', 'loan_end_date', 'loan_start_date', 'loan_name')
    form = SimpleNamespace(vars={name: Var(values.get(name, '')) for name in names}, payload={}, _loading=False)
    return form


# ---- wizard: `F` was used in a branch where it had no value ----------------------------------------------------

def test_the_loan_wizard_pages_can_be_built_and_ask_the_paid_in_amount():
    pages = m._base_wizard_steps_187('ورودی', 'تسهیلات')
    amount = [field for page in pages for field in page if field.key == 'amount']
    assert len(amount) == 1 and amount[0].label == 'مبلغ واریزی وام' and amount[0].kind == 'money'


def test_the_wizard_page_code_has_the_widget_host_helper():
    assert callable(m._widget_host) and m._widget_host is m.v182._widget_host


# ---- record window: a row longer than four fields reached column -1 --------------------------------------------

ROWS = [
    ['loan_bank', 'branch_name', 'borrower_name', 'guarantor_1', 'guarantor_2'],
    ['loan_start_date', 'loan_total_amount', 'loan_name', 'loan_title', 'contract_number', 'interest_rate', 'bank_fees'],
    ['installment_count', 'installment_amount', 'total_interest', 'first_due_date_shamsi', 'loan_end_date',
     'last_paid_date_shamsi', 'paid_installments_count', 'remaining_installments'],
]


def test_loan_record_cells_stay_inside_a_four_column_grid_without_overlap():
    available = {key for row in ROWS for key in row}
    cells = list(m._facility_grid_cells_187(ROWS, available))
    assert [key for key, _row, _col in cells] == [key for row in ROWS for key in row]
    assert all(0 <= column <= 3 for _key, _row, column in cells)
    assert len({(row, column) for _key, row, column in cells}) == len(cells)
    assert max(row for _key, row, _col in cells) == 5  # 5 + 7 + 8 fields: 2 + 2 + 2 grid rows


def test_loan_record_cells_fill_from_the_right_and_skip_missing_fields():
    cells = list(m._facility_grid_cells_187([['a', 'b', 'c', 'd', 'e'], ['f']], {'a', 'c', 'd', 'e', 'f'}))
    assert cells == [('a', 0, 3), ('c', 0, 2), ('d', 0, 1), ('e', 0, 0), ('f', 1, 3)]


# ---- installment box: it was refilled with the computed default the moment it was cleared ----------------------

def test_the_installment_box_is_left_alone_while_it_is_typed_in():
    form = _loan_form(loan_total_amount='12,000,000', installment_count='12', interest_rate='0')
    m._sync_loan_fields_187(form, 'installment_amount')
    assert form.vars['installment_amount'].get() == ''


def test_the_installment_box_gets_the_computed_default_when_another_field_changes():
    form = _loan_form(loan_total_amount='12,000,000', installment_count='12', interest_rate='0')
    m._sync_loan_fields_187(form, 'loan_total_amount')
    assert m.parse_int(form.vars['installment_amount'].get()) == 1_000_000


def test_a_typed_installment_is_kept_and_totals_follow_it():
    form = _loan_form(loan_total_amount='12,000,000', installment_count='12', installment_amount='1,100,000')
    m._sync_loan_fields_187(form, 'installment_amount')
    assert form.vars['installment_amount'].get() == '1,100,000'
    assert m.parse_int(form.vars['total_interest'].get()) == 1_200_000


# ---- installment box: the computed value follows the inputs until a person types their own -------------------------

def _type(form, key, value):
    form.vars[key].set(value)
    m._sync_loan_fields_187(form, key)


def _installment(form):
    return m.parse_int(form.vars['installment_amount'].get())


def test_the_computed_installment_follows_the_amount_the_count_and_the_rate():
    form = _loan_form()
    _type(form, 'loan_total_amount', '12,000,000')
    _type(form, 'installment_count', '12')
    assert _installment(form) == 1_000_000
    _type(form, 'interest_rate', '24')
    assert _installment(form) == m.calculate_loan_installment_187(12_000_000, 24.0, 12) == 1_134_715
    _type(form, 'installment_count', '24')
    assert _installment(form) == m.calculate_loan_installment_187(12_000_000, 24.0, 24)


def test_an_installment_a_person_typed_is_not_replaced_when_the_rate_or_count_change():
    form = _loan_form()
    _type(form, 'loan_total_amount', '12,000,000')
    _type(form, 'installment_count', '12')
    _type(form, 'installment_amount', '1,300,000')
    _type(form, 'interest_rate', '24')
    _type(form, 'installment_count', '10')
    assert _installment(form) == 1_300_000


def test_emptying_the_installment_box_gives_the_computed_one_back_on_the_next_change():
    form = _loan_form()
    _type(form, 'loan_total_amount', '12,000,000')
    _type(form, 'installment_count', '12')
    _type(form, 'installment_amount', '1,300,000')
    _type(form, 'installment_amount', '')
    assert form.vars['installment_amount'].get() == ''  # not refilled under the typing hand
    _type(form, 'interest_rate', '24')
    assert _installment(form) == 1_134_715


def test_a_saved_installment_that_is_the_computed_one_keeps_following_but_a_different_one_stays():
    computed = m.calculate_loan_installment_187(12_000_000, 24.0, 12)
    follows = _loan_form(loan_total_amount='12,000,000', installment_count='12', interest_rate='24',
                         installment_amount=f'{computed:,}')
    m._sync_loan_fields_187(follows)  # opening the record
    _type(follows, 'installment_count', '24')
    assert _installment(follows) == m.calculate_loan_installment_187(12_000_000, 24.0, 24)

    own = _loan_form(loan_total_amount='12,000,000', installment_count='12', interest_rate='24',
                     installment_amount='1,500,000')
    m._sync_loan_fields_187(own)
    _type(own, 'installment_count', '24')
    assert _installment(own) == 1_500_000
