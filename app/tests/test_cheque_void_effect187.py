"""«باطل‌شده» takes the cheque's money effect away; the other statuses keep it."""
import pytest
from test_cheque_workflow187 import cheque_payload
from test_transaction_lifecycle_matrix import m, runtime, register


def _issue(runtime):
    payload = cheque_payload()
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, payload, runtime.rich)
    return runtime.db.list_cheques(open_only=False)[0]['cheque_id']


def _resolve(runtime, cheque_id, status, message_id, *, edit=False):
    payload = cheque_payload()
    payload.update(cheque_operation187=m.CHEQUE_OPERATION_RESOLVE_187, selected_cheque_id187=cheque_id,
                   cheque_resolution_status187=status, cheque_return_account_holder187='حساب معرفی‌شده',
                   cheque_void_reason187='دلیل ابطال',
                   cheque_return_disposition187=m.CHEQUE_RETURN_DISPOSITION_CHOICES_187[3])
    if edit:
        payload['_resolution_edit_cheque_id187'] = cheque_id
    pid = register(runtime, payload, message_id)
    m._approve_cheque_resolution_187(pid, payload)


def _money(runtime):
    with runtime.db.read() as con:
        return {
            'payments': sorted(r[0] for r in con.execute('SELECT status FROM payments')),
            'expenses': sorted(r[0] for r in con.execute('SELECT status FROM expenses')),
            'cheques': con.execute('SELECT COUNT(*) FROM cheques').fetchone()[0],
            'transactions': con.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],
            'cost': runtime.db.snapshot().construction_cost,
            'cash': runtime.db.snapshot().cash_balance,
        }


def test_voiding_cancels_the_cheque_payment_but_keeps_the_cost_and_the_single_row(runtime):
    cheque_id = _issue(runtime)
    issued = _money(runtime)
    assert issued['payments'] == ['PENDING']

    _resolve(runtime, cheque_id, 'باطل‌شده', 2)

    voided = _money(runtime)
    assert voided['payments'] == ['CANCELLED']
    assert voided['cheques'] == 1 and voided['transactions'] == issued['transactions']
    assert voided['cost'] == issued['cost'] and voided['cash'] == issued['cash']
    assert voided['expenses'] == issued['expenses']


def test_changing_a_voided_cheque_to_another_status_gives_its_payment_back(runtime):
    cheque_id = _issue(runtime)
    issued = _money(runtime)
    _resolve(runtime, cheque_id, 'باطل‌شده', 2)
    assert _money(runtime)['payments'] == ['CANCELLED']

    _resolve(runtime, cheque_id, 'پاس‌شده', 3, edit=True)

    assert _money(runtime) == issued


@pytest.mark.parametrize('status', ['پاس‌شده', 'برگشتی', 'عودتی به شرط تسویه'])
def test_the_other_statuses_keep_the_money_effect_of_issue(runtime, status):
    cheque_id = _issue(runtime)
    issued = _money(runtime)

    _resolve(runtime, cheque_id, status, 2)

    assert _money(runtime) == issued
