"""Cheque issue wizard: window two has no payment method; the review counts each attached file once."""
from test_transaction_lifecycle_matrix import m, runtime, register  # noqa: F401


def test_window_two_of_the_cheque_issue_wizard_has_no_payment_method():
    pages = m._wizard_steps_187('هزینه ساخت', 'چک')
    keys = [field.key for page in pages for field in page]
    assert 'payment_method' not in keys
    assert 'due_date_shamsi' in keys and 'issuer_name' in keys


def test_attaching_the_same_file_to_a_pending_record_twice_keeps_one_row(runtime, tmp_path):
    from test_cheque_workflow187 import cheque_payload
    pid = register(runtime, cheque_payload())
    path = tmp_path / 'receipt.jpg'
    path.write_bytes(b'x')
    first = runtime.db.attach_file_to_pending(pending_id=pid, local_path=str(path), mime_type='image/jpeg')
    again = runtime.db.attach_file_to_pending(pending_id=pid, local_path=str(path), mime_type='image/jpeg')
    other = tmp_path / 'second.jpg'
    other.write_bytes(b'y')
    second = runtime.db.attach_file_to_pending(pending_id=pid, local_path=str(other), mime_type='image/jpeg')
    assert again == first and second != first
    assert len(runtime.db.list_pending_attachments(pid)) == 2


def test_the_wizard_review_lists_a_file_once_even_when_it_was_attached_several_times(runtime, tmp_path):
    from test_cheque_workflow187 import cheque_payload
    pid = register(runtime, cheque_payload())
    path = tmp_path / 'receipt.jpg'
    path.write_bytes(b'x')
    with runtime.db.tx() as con:  # rows as the repeated backup imports left them
        for number in range(8):
            con.execute("INSERT INTO attachments(attachment_id,entity_type,entity_id,document_type,local_path,mime_type,created_at) "
                        "VALUES(?,?,?,?,?,?,?)", (f'ATT-DUP{number}', 'PENDING', pid, 'RECEIPT', str(path), 'image/jpeg', f'2026-01-0{number + 1}'))
    assert m._pending_attachment_names_187(pid) == ['receipt.jpg']
