"""A cheque's record shows the receipts of both its records, the issue's and the resolution's."""
from pathlib import Path
import pytest
from test_cheque_identity187 import _bundle_issue
from test_cheque_resolution_lifecycle187 import _issue, _resolve
from test_cheque_workflow187 import cheque_payload
from test_transaction_lifecycle_matrix import m, runtime, register
from receipt_gallery187 import receipt_paths


def _file(runtime, name):
    path = Path(runtime.db.db_path).parent / name
    path.write_text(name, encoding='utf-8')
    return path


def _issue_with_receipt(runtime, bundle=False):
    payload = cheque_payload()
    if bundle:
        payload['cheques'] = [dict(amount=payload['amount'], due_date_shamsi=payload['due_date_shamsi'],
                                   cheque_serial=payload['cheque_serial'], issuer_bank=payload['issuer_bank'])]
    pid = register(runtime, payload)
    runtime.service.attachments.add_local(entity_type='PENDING', entity_id=pid, source_path=_file(runtime, 'issue-receipt.txt'))
    m.v18.submit_v18(pid, payload, runtime.rich)
    return pid, runtime.db.list_cheques(open_only=False)[0]['cheque_id']


def _name(path):
    name = Path(path).name
    return name.split('_', 1)[1] if name.startswith('ATT-') else name


def _names(paths):
    return sorted(_name(path) for path in paths)


@pytest.mark.parametrize('bundle', [False, True], ids=['posting', 'bundle'])
def test_every_window_of_a_resolved_cheque_lists_both_receipts(runtime, bundle):
    issue, cheque_id = _issue_with_receipt(runtime, bundle)
    resolution = _resolve(runtime, cheque_id, 'پاس‌شده', 2, attach='resolution-receipt.txt')
    both = ['issue-receipt.txt', 'resolution-receipt.txt']

    assert _names(receipt_paths(runtime.db, issue)) == both
    assert _names(receipt_paths(runtime.db, resolution)) == both
    assert _names(receipt_paths(runtime.db, '', {'cheque_id': cheque_id})) == both


@pytest.mark.parametrize('bundle', [False, True], ids=['posting', 'bundle'])
def test_a_record_lists_its_own_receipt_first_and_the_cheques_view_the_issue_first(runtime, bundle):
    issue, cheque_id = _issue_with_receipt(runtime, bundle)
    resolution = _resolve(runtime, cheque_id, 'عودتی به شرط تسویه', 2, attach='resolution-receipt.txt')
    for pending, row, expected in (
            (issue, None, ['issue-receipt.txt', 'resolution-receipt.txt']),
            (resolution, None, ['resolution-receipt.txt', 'issue-receipt.txt']),
            ('', {'cheque_id': cheque_id}, ['issue-receipt.txt', 'resolution-receipt.txt'])):
        names = [_name(path) for path in receipt_paths(runtime.db, pending, row)]
        assert names == expected


def test_a_receipt_just_added_to_the_resolution_is_the_first_of_the_resolution_record(runtime):
    issue, cheque_id = _issue_with_receipt(runtime, bundle=True)  # its receipt sits on a document
    resolution = _resolve(runtime, cheque_id, 'برگشتی', 2)
    runtime.service.attachments.add_local(entity_type='PENDING', entity_id=resolution,
                                          source_path=_file(runtime, 'resolution-receipt.txt'))
    assert [_name(path) for path in receipt_paths(runtime.db, issue)] == ['issue-receipt.txt', 'resolution-receipt.txt']
    assert [_name(path) for path in receipt_paths(runtime.db, resolution)] == ['resolution-receipt.txt', 'issue-receipt.txt']


def test_the_issue_receipts_come_first_when_the_issue_is_open(runtime):
    issue, cheque_id = _issue_with_receipt(runtime)
    _resolve(runtime, cheque_id, 'برگشتی', 2, attach='resolution-receipt.txt')
    names = [_name(path) for path in receipt_paths(runtime.db, issue)]
    assert names.index('issue-receipt.txt') < names.index('resolution-receipt.txt')


def test_an_unresolved_cheque_lists_only_its_own_receipt(runtime):
    issue, cheque_id = _issue_with_receipt(runtime)
    assert _names(receipt_paths(runtime.db, issue)) == ['issue-receipt.txt']


def test_a_record_of_another_cheque_does_not_borrow_these_receipts(runtime):
    issue, cheque_id = _issue_with_receipt(runtime)
    other = register(runtime, cheque_payload(), 7)
    assert _names(receipt_paths(runtime.db, other)) == []
