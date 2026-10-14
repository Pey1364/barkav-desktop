"""One cheque, one row: issue and resolution are two linked Data Entry records."""
import json
from pathlib import Path
import pytest
from test_cheque_workflow187 import cheque_payload
from test_transaction_lifecycle_matrix import m, runtime, register


def _attach(runtime, pid, name):
    path = Path(runtime.db.db_path).parent / name
    path.write_text(name, encoding='utf-8')
    runtime.service.attachments.add_local(entity_type='PENDING', entity_id=pid, source_path=path)


def _attached(runtime, cheque_id):
    """Every document the cheque tab's receipt column / viewer offers for this cheque's row."""
    from receipt_gallery187 import receipt_paths
    return sorted(Path(path).name.split('_', 1)[-1] for path in receipt_paths(runtime.db, row=runtime.db.get_cheque(cheque_id)))


@pytest.mark.parametrize('status', ['پاس‌شده', 'برگشتی', 'عودتی به شرط تسویه', 'باطل‌شده'])
def test_issue_and_resolution_share_one_cheque_row_and_all_documents(runtime, status):
    payload = cheque_payload()
    issue = register(runtime, payload)
    _attach(runtime, issue, 'issue-proof.txt')
    m.v18.submit_v18(issue, payload, runtime.rich)
    rows = runtime.db.list_cheques(open_only=False)
    assert len(rows) == 1
    cheque_id = rows[0]['cheque_id']
    cost = runtime.db.snapshot().construction_cost

    resolution_payload = cheque_payload()
    resolution_payload.update(cheque_operation187=m.CHEQUE_OPERATION_RESOLVE_187, selected_cheque_id187=cheque_id,
                              cheque_resolution_status187=status, cheque_return_account_holder187='حساب معرفی‌شده',
                              cheque_void_reason187='دلیل ابطال',
                              cheque_return_disposition187=m.CHEQUE_RETURN_DISPOSITION_CHOICES_187[3])
    resolution = register(runtime, resolution_payload, 2)
    _attach(runtime, resolution, 'resolution-proof.txt')
    m._approve_cheque_resolution_187(resolution, resolution_payload)

    # still one row, the cost was recognized once, both records are approved and linked
    assert [row['cheque_id'] for row in runtime.db.list_cheques(open_only=False)] == [cheque_id]
    assert runtime.db.snapshot().construction_cost == cost
    assert runtime.db.get_pending_item(issue)['status'] == 'APPROVED'
    assert runtime.db.get_pending_item(resolution)['status'] == 'APPROVED'
    assert runtime.db.get_pending_item(resolution)['payload']['cheque_id'] == cheque_id
    assert runtime.db.get_pending_item(issue)['payload']['cheque_status'] == m._cheque_resolution_status_code_187(status)
    # the resolution updated the same row's status, and every document is reachable from the row
    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == status
    assert _attached(runtime, cheque_id) == ['issue-proof.txt', 'resolution-proof.txt']
    with runtime.db.read() as con:
        assert con.execute('SELECT COUNT(*) FROM expenses').fetchone()[0] == 1
        assert con.execute('SELECT COUNT(*) FROM payments').fetchone()[0] == 1


def test_a_settled_cheque_is_offered_for_resolution_only_while_its_record_is_under_review(runtime):
    payload = cheque_payload()
    issue = register(runtime, payload)
    m.v18.submit_v18(issue, payload, runtime.rich)
    cheque_id = runtime.db.list_cheques(open_only=False)[0]['cheque_id']
    runtime.db.update_cheque_workflow_state(cheque_id, lifecycle='CASHED')
    offered = lambda: {row['cheque_id'] for row in m._registered_cheques_for_clearing_187()}

    assert cheque_id not in offered()

    runtime.db.update_pending(issue, status='EDIT_PENDING')
    assert cheque_id in offered()

    runtime.db.update_pending(issue, status='APPROVED')
    assert cheque_id not in offered()
