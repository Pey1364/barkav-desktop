"""«افزودن» on the loan tab opens the wizard with its first page filled, not empty until one goes next and back."""
from test_transaction_lifecycle_matrix import m, runtime  # noqa: F401
from test_stage18_7_record_fields import root  # noqa: F401
from test_land_wizard_settlement187 import wizard_for

BANK_FIELDS = ['loan_bank', 'branch_name', 'borrower_name', 'guarantor_1', 'guarantor_2']
# the payload `_open_loan_wizard_187` makes for a new loan
NEW_LOAN = dict(v18_title='ورودی', v18_subtype='تسهیلات', detected_type='INCOME', event_date_shamsi='1405/07/14',
                loan_start_date='1405/07/14', amount=0, source='MANUAL_LOAN_GUI_187')


def _keys(page):
    return [field.key for field in page]


def _visible(form, keys):
    return [key for key in keys
            if form.widgets.get(key) is not None and form.widgets[key].winfo_viewable()]


def test_a_new_loan_wizard_opens_on_the_bank_and_borrower_fields(root, runtime):
    form = wizard_for(root, runtime, dict(NEW_LOAN))
    root.update()
    assert form.page_index == 0
    assert all(key in _keys(form.pages[0]) for key in BANK_FIELDS)
    assert _visible(form, BANK_FIELDS) == BANK_FIELDS


def test_going_next_and_back_does_not_change_the_first_page(root, runtime):
    form = wizard_for(root, runtime, dict(NEW_LOAN))
    root.update()
    on_open = [_keys(page) for page in form.pages], _visible(form, BANK_FIELDS)
    form.next()
    root.update()
    form.prev()
    root.update()
    assert ([_keys(page) for page in form.pages], _visible(form, BANK_FIELDS)) == on_open
    assert len(form.pages) == 3
