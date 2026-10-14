"""An instalment payment (خروجی / اقساط): no payment method, a wider loan picker that lists loan names, counts typed by
hand, and a loan kept by its id but shown by its name.

The remaining count is the total less the paid before and the paid now until somebody types a count of their own;
no count changes the loan's schedule, and approval posts the number paid now.
"""
import pytest

from test_transaction_lifecycle_matrix import m, register, runtime  # noqa: F401
from test_stage18_7_record_fields import root  # noqa: F401


def _loan(runtime, count=6, name=None, principal=60_000_000):
    values = dict(lender_name='بانک آزمون', principal_amount=principal, net_received_amount=principal,
                  received_date_shamsi='1405/01/01', installment_count=count, first_due_date_shamsi='1405/02/01',
                  description='وام آزمون اقساط', register_cash=False)
    if name:
        values['loan_name'] = name
    return m.LoanService(runtime.db).create_loan(**values)


def _instalment(loan, **values):
    payload = dict(detected_type='OUTFLOW', v18_title='خروجی', v18_subtype='اقساط',
                   event_date_shamsi='1405/02/01', amount=1_000_000, description='قسط آزمون',
                   loan_id=loan['loan_id'], loan_bank='بانک آزمون', loan_total_amount=60_000_000,
                   installment_count=6, paid_installments_before=2, installments_paid_now=1)
    payload.update(values)
    return payload


def _count(form, key):
    return m.parse_int(form.vars[key].get())


def _type(root, entry, digits):
    entry.focus_force()
    root.update()
    entry.selection_range(0, 'end')
    for digit in digits:
        entry.event_generate('<KeyPress>', keysym=digit)
        root.update()


def _erase(root, entry):
    entry.focus_force()
    root.update()
    entry.selection_range(0, 'end')
    entry.event_generate('<KeyPress>', keysym='BackSpace')
    root.update()


def _leave(root, entry):
    entry.event_generate('<FocusOut>')
    root.update()


def _page_of(wizard, key):
    return next(index for index, page in enumerate(wizard.pages) if any(field.key == key for field in page))


def test_an_instalment_payment_has_no_payment_method_in_wizard_or_record(root, runtime):
    row = runtime.db.get_pending_item(register(runtime, _instalment(_loan(runtime))))
    assert 'payment_method' not in [field.key for field in m._special_fields_187('خروجی', 'اقساط')]
    wizard = m.v182.TransactionWizard182(root, row, runtime.rich, lambda: None, lambda: None)
    root.update()
    assert 'payment_method' not in wizard.widgets
    assert 'payment_method' not in [field.key for page in wizard.pages for field in page]
    wizard.destroy()
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    root.update()
    assert 'payment_method' not in editor.widgets
    editor.destroy()


def test_the_loan_name_box_takes_two_columns_of_the_record_window(root, runtime):
    row = runtime.db.get_pending_item(register(runtime, _instalment(_loan(runtime))))
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    editor.geometry('1200x800+0+0')
    editor.update()
    loan_box = editor.widgets['loan_id'].master
    payer_box = editor.widgets['payer_name'].master
    assert loan_box.grid_info()['columnspan'] == 2
    assert loan_box.winfo_width() >= 1.5 * payer_box.winfo_width()
    editor.destroy()


def test_the_loan_picker_lists_loan_names_and_never_a_latin_id(root, runtime):
    first = _loan(runtime, name='6636')
    _loan(runtime, name='اعتبار ملی پیمان-2', principal=39_707_149)
    cancelled = _loan(runtime, name='قدیمی')
    m.LoanService(runtime.db).cancel_loan(cancelled['loan_id'])
    row = runtime.db.get_pending_item(register(runtime, _instalment(first), message_id=4))
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    root.update()
    values = tuple(editor.widgets['loan_id'].cget('values'))
    assert '6636' in values and 'اعتبار ملی پیمان-2' in values
    assert not any(str(value).startswith('LOAN-') or '|' in str(value) for value in values)
    assert 'قدیمی' not in values  # a cancelled loan is not offered for a new payment
    editor.destroy()


def test_a_record_shows_its_loan_by_name_and_keeps_its_id(root, runtime):
    loan = _loan(runtime, name='6636')
    row = runtime.db.get_pending_item(register(runtime, _instalment(loan), message_id=5))
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    root.update()
    assert editor.vars['loan_id'].get() == '6636'
    assert editor.payload_from_form()['loan_id'] == loan['loan_id']
    editor.destroy()
    # a record saved by the older picker, which stored the id followed by the details it showed
    legacy = _instalment(loan, loan_id=f"{loan['loan_id']} | وام | بانک آزمون | ۶۰٬۰۰۰٬۰۰۰")
    row = runtime.db.get_pending_item(register(runtime, legacy, message_id=6))
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    root.update()
    assert editor.vars['loan_id'].get() == '6636'
    assert editor.payload_from_form()['loan_id'] == loan['loan_id']
    editor.destroy()


def test_choosing_a_loan_in_the_record_shows_its_name_and_stores_its_id(root, runtime):
    loan = _loan(runtime, name='6636')
    payload = dict(detected_type='OUTFLOW', v18_title='خروجی', v18_subtype='اقساط',
                   event_date_shamsi='1405/05/28', amount=1_000_000, description='قسط آزمون')
    row = runtime.db.get_pending_item(register(runtime, payload, message_id=7))
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    root.update()
    editor._loan_selected('6636')
    root.update()
    assert editor.vars['loan_id'].get() == '6636'
    assert editor.payload_from_form()['loan_id'] == loan['loan_id']
    assert _count(editor, 'remaining_installments') == 5  # 6 - 0 - 1
    editor.destroy()


def test_paid_and_remaining_counts_are_typed_by_hand_in_the_record_window(root, runtime):
    row = runtime.db.get_pending_item(register(runtime, _instalment(_loan(runtime))))
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    root.update()
    for key in ('paid_installments_before', 'installments_paid_now', 'remaining_installments'):
        assert str(editor.widgets[key].cget('state')) == 'normal'
    assert _count(editor, 'remaining_installments') == 3  # 6 - 2 - 1
    _type(root, editor.widgets['remaining_installments'], '7')
    _type(root, editor.widgets['installments_paid_now'], '2')
    assert _count(editor, 'remaining_installments') == 7  # typed over: it stays
    _erase(root, editor.widgets['remaining_installments'])
    _leave(root, editor.widgets['remaining_installments'])
    assert _count(editor, 'remaining_installments') == 2  # emptied and left: 6 - 2 - 2
    _type(root, editor.widgets['installments_paid_now'], '3')
    assert _count(editor, 'remaining_installments') == 1  # 6 - 2 - 3
    _type(root, editor.widgets['paid_installments_before'], '1')
    assert _count(editor, 'remaining_installments') == 2  # 6 - 1 - 3
    editor.destroy()


def test_a_typed_remaining_count_is_kept_when_the_record_is_opened_again(root, runtime):
    loan = _loan(runtime)
    pid = register(runtime, _instalment(loan, remaining_installments=7))
    editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    root.update()
    assert _count(editor, 'remaining_installments') == 7
    _type(root, editor.widgets['installments_paid_now'], '2')
    assert _count(editor, 'remaining_installments') == 7
    editor.destroy()
    untyped = register(runtime, _instalment(loan), message_id=2)
    editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(untyped), runtime.rich, lambda: None)
    root.update()
    assert _count(editor, 'remaining_installments') == 3  # nothing was typed: the computed count
    editor.destroy()


def test_the_wizard_counts_start_again_when_a_loan_is_chosen(root, runtime):
    loan = _loan(runtime, name='6636')
    payload = dict(detected_type='OUTFLOW', v18_title='خروجی', v18_subtype='اقساط',
                   event_date_shamsi='1405/05/28', amount=1_000_000, description='قسط آزمون')
    row = runtime.db.get_pending_item(register(runtime, payload, message_id=3))
    wizard = m.v182.TransactionWizard182(root, row, runtime.rich, lambda: None, lambda: None)
    root.update()
    picker, counts = _page_of(wizard, 'loan_id'), _page_of(wizard, 'remaining_installments')

    def show(index):
        wizard._capture()
        wizard.page_index = index
        wizard._show_page()
        root.update()

    show(picker)
    selected = '6636'
    assert selected in tuple(wizard.widgets['loan_id'].cget('values'))
    wizard.vars['loan_id'].set(selected)
    wizard._loan_selected(selected)
    assert wizard.payload['loan_id'] == loan['loan_id']
    show(counts)
    assert _count(wizard, 'remaining_installments') == 5  # 6 - 0 - 1
    _type(root, wizard.widgets['remaining_installments'], '7')
    _type(root, wizard.widgets['installments_paid_now'], '2')
    assert _count(wizard, 'remaining_installments') == 7  # typed over, and kept when the page is shown again
    show(picker)
    wizard._loan_selected(selected)
    show(counts)
    assert _count(wizard, 'remaining_installments') == 5  # choosing the loan again starts its counts
    wizard.destroy()


def test_approval_posts_the_instalments_paid_now_whatever_remaining_was_typed(root, runtime):
    loan = _loan(runtime)
    with runtime.db.read() as con:
        first = dict(con.execute(
            'SELECT * FROM loan_installments WHERE loan_id=? ORDER BY installment_number LIMIT 1',
            (loan['loan_id'],)).fetchone())
    payload = _instalment(loan, amount=first['amount'], remaining_installments=7, installments_paid_now=1)
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, payload, runtime.rich)
    with runtime.db.read() as con:
        paid = con.execute('SELECT COUNT(*) FROM loan_installments WHERE loan_id=? AND paid_amount>0',
                           (loan['loan_id'],)).fetchone()[0]
    assert paid == 1


def test_an_instalment_above_the_one_due_names_the_figure_to_correct(root, runtime):
    loan = _loan(runtime)  # six instalments of 10,000,000 and no interest
    with runtime.db.read() as con:
        first = dict(con.execute(
            'SELECT * FROM loan_installments WHERE loan_id=? ORDER BY installment_number LIMIT 1',
            (loan['loan_id'],)).fetchone())
    payload = _instalment(loan, amount=first['amount'] + 1)
    pid = register(runtime, payload, message_id=8)
    with pytest.raises(ValueError, match='مبلغ هر قسط'):
        m._approve_v18_187(pid, payload, runtime.rich)


def test_the_correction_message_says_the_loan_has_paid_instalments_when_it_has(root, runtime):
    loan = _loan(runtime)
    with runtime.db.read() as con:
        first = dict(con.execute(
            'SELECT * FROM loan_installments WHERE loan_id=? ORDER BY installment_number LIMIT 1',
            (loan['loan_id'],)).fetchone())
    m.LoanService(runtime.db).pay_installment(first['loan_installment_id'], amount=first['amount'],
                                              paid_date_shamsi='1405/05/28', source='TEST')
    payload = _instalment(loan, amount=first['amount'] + 1)
    pid = register(runtime, payload, message_id=9)
    with pytest.raises(ValueError, match='جدول اقساط آن قابل تغییر نیست'):
        m._approve_v18_187(pid, payload, runtime.rich)
