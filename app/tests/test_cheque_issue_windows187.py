"""A cheque issue is four windows: basics, every cheque detail, the two statuses, confirmation."""
import tkinter as tk
from pathlib import Path
from test_cheque_workflow187 import cheque_payload
from test_transaction_lifecycle_matrix import m, runtime, register
from test_stage18_7_record_fields import root


def _labels(widget):
    texts = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Label):
            texts.append(str(child.cget('text')))
        texts.extend(_labels(child))
    return texts


def _wizard(root, runtime, **changes):
    payload = cheque_payload()
    payload.update(changes)
    pid = register(runtime, payload)
    return pid, payload, m.v182.TransactionWizard182(root, runtime.db.get_pending_item(pid), runtime.rich,
                                                     lambda: None, lambda: None)


def test_second_window_holds_every_cheque_detail_and_the_money_structure(root, runtime):
    pid, payload, wizard = _wizard(root, runtime)
    wizard.next()
    root.update()
    assert len(wizard.pages) == 4 and wizard.page_index == 1
    assert {'event_date_shamsi', 'amount', 'due_date_shamsi', 'issuer_name', 'receiver_name', 'issuer_bank',
            'cheque_serial', 'cheque_type', 'description', 'is_guarantee', 'invoice_amount', 'final_amount',
            'payment_state', 'total_debt', 'remaining_debt', 'main_phase', 'sub_phase'} <= set(wizard.vars)


def test_third_window_has_the_two_statuses_and_issued_is_the_default(root, runtime):
    pid, payload, wizard = _wizard(root, runtime, cheque_status='')
    wizard.next()
    wizard.next()
    root.update()
    assert wizard.page_index == 2
    assert set(wizard.vars) == {'cheque_registration_state', 'cheque_status'}
    assert wizard.vars['cheque_status'].get() == 'صادرشده'


def test_last_window_summarizes_the_cheque_lists_attachments_and_can_go_back(root, runtime):
    pid, payload, wizard = _wizard(root, runtime)
    proof = Path(runtime.db.db_path).parent / 'cheque-proof.txt'
    proof.write_text('evidence', encoding='utf-8')
    runtime.service.attachments.add_local(entity_type='PENDING', entity_id=pid, source_path=proof)
    for _ in range(3):
        wizard.next()
    root.update()
    assert wizard.page_index == 3 and wizard.next_b.cget('text') == 'تأیید و ثبت'
    text = chr(10).join(_labels(wizard.host)).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789'))
    for value in (payload['issuer_name'], payload['receiver_name'], payload['issuer_bank'], payload['cheque_serial'],
                  payload['due_date_shamsi'], payload['description'], 'cheque-proof.txt'):
        assert value in text
    assert 'صدور چک' in text
    wizard.prev()
    assert wizard.page_index == 2
    wizard.next()
    assert wizard.page_index == 3


def test_confirming_registers_exactly_the_cheque_that_was_summarized(root, runtime, monkeypatch):
    errors = []
    for name in ('showerror', 'showwarning'):
        monkeypatch.setattr(m.messagebox, name, lambda *a, **k: errors.append(a))
    monkeypatch.setattr(m, '_confirm_debt_warning_187', lambda *a: True)
    pid, payload, wizard = _wizard(root, runtime)
    for _ in range(4):
        if wizard.winfo_exists():
            wizard.next()
    assert not errors
    rows = runtime.db.list_cheques(open_only=False)
    assert len(rows) == 1
    for key in ('cheque_serial', 'issuer_name', 'issuer_bank', 'receiver_name', 'description', 'amount'):
        assert rows[0][key] == payload[key]
    assert rows[0]['status'] == 'ISSUED'
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'


def _number_label(form):
    box = form.widgets['cheque_serial'].master
    return next(str(child.cget('text')) for child in box.winfo_children() if isinstance(child, tk.Label))


def test_the_number_box_is_labelled_by_cheque_type_in_the_wizard_and_the_record(root, runtime):
    pid, payload, wizard = _wizard(root, runtime)
    wizard.next()
    root.update()
    wizard.vars['cheque_type'].set('دیجیتال')
    assert _number_label(wizard) == 'شماره صیادی'
    wizard.vars['cheque_type'].set('فیزیکی')
    assert _number_label(wizard) == 'شماره چک'
    wizard.destroy()
    editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    root.update()
    editor.vars['cheque_type'].set('دیجیتال')
    assert _number_label(editor) == 'شماره صیادی'
    editor.destroy()
