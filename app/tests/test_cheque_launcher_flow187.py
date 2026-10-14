"""Regression for real first-window selection, not preselected payloads."""
from test_cheque_workflow187 import cheque_payload
from test_transaction_lifecycle_matrix import m, runtime, register
from test_stage18_7_record_fields import root


def test_select_cheque_rebuilds_first_window_and_back_keeps_fields(root, runtime):
    payload = cheque_payload()
    payload.update(v18_subtype='نقدی', cost_group='')
    pid = register(runtime, payload)
    wizard = m.v182.TransactionWizard182(root, runtime.db.get_pending_item(pid),
                                         runtime.rich, lambda: None, lambda: None)
    assert m.CHEQUE_CLEARING_SUBTYPE_187 not in wizard.widgets['v18_subtype']['values']
    wizard.vars['v18_subtype'].set('چک')
    wizard.widgets['v18_subtype'].event_generate('<<ComboboxSelected>>')
    root.update()
    assert wizard.page_index == 0
    assert 'cheque_operation187' in wizard.widgets
    # An empty category is «مصالح», with no contract choice, as for a cash cost.
    assert wizard.vars['cost_group'].get() == 'مصالح'
    assert not _contract_choice_shown(wizard)
    # Choosing «پیمانکار» shows «انتخاب قرارداد» straight away.
    wizard.vars['cost_group'].set('پیمانکار')
    wizard.widgets['cost_group'].event_generate('<<ComboboxSelected>>')
    root.update()
    assert _contract_choice_shown(wizard)
    wizard.next()
    wizard.prev()
    assert _contract_choice_shown(wizard)
    assert wizard.vars['cost_group'].get() == 'پیمانکار'
    assert wizard.vars['cheque_operation187'].get() == m.CHEQUE_OPERATION_ISSUE_187


def _contract_choice_shown(form):
    """The «انتخاب قرارداد» box is on screen (grid_remove leaves it managed but unmapped)."""
    form.update()
    widget = form.widgets.get('contract_id')
    return widget is not None and bool(widget.master.winfo_ismapped())


def test_blank_category_of_a_cheque_record_defaults_to_materials(root, runtime):
    payload = cheque_payload()
    payload['cost_group'] = ''
    pid = register(runtime, payload)
    editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid),
                                            runtime.rich, lambda: None)
    root.update()
    assert editor.vars['cost_group'].get() == 'مصالح'
    editor.destroy()


def test_picker_lists_issued_registered_unregistered_and_guarantee(root, runtime):
    ids = []
    for index, registered in enumerate(('REGISTERED', 'UNREGISTERED', 'REGISTERED'), 1):
        payload = cheque_payload()
        payload.update(cheque_registration_state=registered, is_guarantee=index == 3)
        pid = register(runtime, payload, index)
        m.v18.submit_v18(pid, payload, runtime.rich)
        ids.append(runtime.db.list_cheques(open_only=False)[-1]['cheque_id'])
    payload = cheque_payload()
    pid = register(runtime, payload, 4)
    wizard = m.v182.TransactionWizard182(root, runtime.db.get_pending_item(pid),
                                         runtime.rich, lambda: None, lambda: None)
    wizard.vars['cheque_operation187'].set(m.CHEQUE_OPERATION_RESOLVE_187)
    root.update()
    picker = wizard.widgets['selected_cheque_id187']
    assert len(picker.get_children()) == 3
    assert set(picker.get_children()) == {row['cheque_id'] for row in runtime.db.list_cheques(open_only=True)}
    assert int(picker.master.master.grid_info()['columnspan']) == 2
    assert int(picker['height']) >= 5


def test_legacy_ai_clearing_opens_new_operation(root, runtime):
    payload = cheque_payload()
    payload['v18_subtype'] = m.CHEQUE_CLEARING_SUBTYPE_187
    pid = register(runtime, payload)
    wizard = m.v182.TransactionWizard182(root, runtime.db.get_pending_item(pid),
                                         runtime.rich, lambda: None, lambda: None)
    assert wizard.subtype_var.get() == 'چک'
    assert wizard.vars['cheque_operation187'].get() == m.CHEQUE_OPERATION_RESOLVE_187


def test_guarantee_resolution_only_changes_metadata(runtime):
    payload = cheque_payload()
    payload['is_guarantee'] = True
    source = register(runtime, payload)
    m.v18.submit_v18(source, payload, runtime.rich)
    cheque = runtime.db.list_cheques(open_only=False)[0]
    cost = runtime.db.snapshot().construction_cost
    for index, status in enumerate(m.CHEQUE_RESOLUTION_STATUS_CHOICES_187, 2):
        payload = cheque_payload()
        payload.update(cheque_operation187=m.CHEQUE_OPERATION_RESOLVE_187,
                       selected_cheque_id187=cheque['cheque_id'],
                       _resolution_edit_cheque_id187=cheque['cheque_id'],
                       cheque_resolution_status187=status,
                       cheque_return_account_holder187='حساب آزمون',
                       cheque_void_reason187='دلیل آزمون')
        pid = register(runtime, payload, index)
        m._approve_cheque_resolution_187(pid, payload)
        assert m._cheque_status_label_187(runtime.db.get_cheque(cheque['cheque_id'])) == status
        assert runtime.db.snapshot().construction_cost == cost


def test_picker_shows_purpose_amount_due_date_and_receiver_in_persian_digits(root, runtime):
    payload = cheque_payload()
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, payload, runtime.rich)
    cheque_id = runtime.db.list_cheques(open_only=False)[0]['cheque_id']
    probe = register(runtime, cheque_payload(), 2)
    wizard = m.v182.TransactionWizard182(root, runtime.db.get_pending_item(probe), runtime.rich,
                                         lambda: None, lambda: None)
    wizard.vars['cheque_operation187'].set(m.CHEQUE_OPERATION_RESOLVE_187)
    root.update()
    picker = wizard.widgets['selected_cheque_id187']
    values = dict(zip(picker['columns'], picker.item(cheque_id, 'values')))
    assert values['amount'] == '۱,۲۰۰,۰۰۰'
    assert values['due'] == '۱۴۰۵/۰۸/۰۸'
    assert values['receiver'] == payload['receiver_name']
    assert values['description'] == payload['description']
    # the AI picked it from the amount and the document date, and the pick can be changed
    assert picker.selection() == (cheque_id,)
