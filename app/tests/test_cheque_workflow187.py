"""Cheque acceptance through real Tk controls and disposable storage."""
import pytest
from pathlib import Path
from test_transaction_lifecycle_matrix import m, runtime, register
from test_stage18_7_record_fields import root


def cheque_payload():
    return dict(detected_type='EXPENSE', v18_title='هزینه ساخت', v18_subtype='چک',
                event_date_shamsi='1405/07/08', due_date_shamsi='1405/08/08',
                amount=1200000, final_amount=1200000, invoice_amount=1200000,
                cheque_amount=1200000, payment_state='PAID', total_debt=1200000,
                description='چک آزمایشی مصالح', receiver_name='گیرنده آزمایشی',
                issuer_name='صاحب حساب آزمایشی', issuer_bank='بانک آزمایشی',
                cheque_serial='123456789', cheque_type='PHYSICAL',
                cheque_status='ISSUED', cheque_registration_state='REGISTERED',
                cost_group='مصالح', payment_method='CHEQUE')


@pytest.mark.parametrize('form',['wizard','record'])
def test_issue_wizard_metadata_and_register(root, runtime, monkeypatch,form):
    errors=[]
    monkeypatch.setattr(m.messagebox, 'showerror', lambda *a, **k: errors.append(a))
    monkeypatch.setattr(m.messagebox, 'showwarning', lambda *a, **k: errors.append(a))
    monkeypatch.setattr(m, '_confirm_debt_warning_187', lambda *a: True)
    payload=cheque_payload()
    pid=register(runtime,payload)
    if form=='wizard':
        w=m.v182.TransactionWizard182(root,runtime.db.get_pending_item(pid),runtime.rich,lambda:None,lambda:None)
    else:
        w=m.v182.UnifiedPendingEditor182(root,runtime.db.get_pending_item(pid),runtime.rich,lambda:None)
    assert 'cheque_operation187' in w.vars
    if form=='wizard':w.next()
    assert {'cheque_serial','issuer_name','receiver_name','issuer_bank','due_date_shamsi'} <= set(w.vars)
    if form=='wizard':
        while w.winfo_exists() and not errors:
            w.next()
    else:
        m._editor_approve_187(w)
    assert not errors
    rows=runtime.db.list_cheques(open_only=False)
    assert len(rows)==1
    row=rows[0]
    for key in ('cheque_serial','issuer_name','issuer_bank','receiver_name','description','amount'):
        assert row[key]==payload[key]


def test_record_has_operation_and_resolution_fields(root,runtime):
    pid=register(runtime,cheque_payload())
    e=m.v182.UnifiedPendingEditor182(root,runtime.db.get_pending_item(pid),runtime.rich,lambda:None)
    assert 'cheque_operation187' in e.vars
    assert 'cheque_serial' in e.vars
    e.vars['cheque_operation187'].set(m.CHEQUE_OPERATION_RESOLVE_187)
    root.update()
    assert 'selected_cheque_id187' in e.widgets
    assert 'cheque_resolution_status187' in e.vars
    assert int(e.widgets['selected_cheque_id187']['height']) >= 5
    assert int(e.widgets['selected_cheque_id187'].master.master.grid_info()['columnspan']) == 4


@pytest.mark.parametrize('status', m.CHEQUE_RESOLUTION_STATUS_CHOICES_187)
@pytest.mark.parametrize('form', ['wizard','record'])
def test_resolve_updates_existing_rows_and_preserves_cost(root,runtime,monkeypatch,status,form):
    errors=[]
    for name in ('showerror','showwarning'):
        monkeypatch.setattr(m.messagebox,name,lambda *a,**k:errors.append(a))
    monkeypatch.setattr(m,'_confirm_debt_warning_187',lambda *a:True)
    original=cheque_payload()
    source=register(runtime,original)
    m.v18.submit_v18(source,original,runtime.rich)
    cheque=runtime.db.list_cheques(open_only=False)[0]
    before=runtime.db.snapshot().construction_cost
    with runtime.db.connect() as con:
        tx_count=con.execute('SELECT count(*) FROM transactions').fetchone()[0]
    payload=cheque_payload()
    payload.update(cheque_operation187=m.CHEQUE_OPERATION_RESOLVE_187,
                   selected_cheque_id187=cheque['cheque_id'],selected_cheque_manual187=True)
    pid=register(runtime,payload,2)
    receipt=Path(runtime.db.db_path).parent/'cheque-proof.txt'
    receipt.write_text('synthetic cheque evidence',encoding='utf-8')
    runtime.service.attachments.add_local(entity_type='PENDING',entity_id=pid,source_path=receipt)
    row=runtime.db.get_pending_item(pid)
    if form=='wizard':
        w=m.v182.TransactionWizard182(root,row,runtime.rich,lambda:None,lambda:None)
        w.next()
        assert w.page_index==1
        assert str(w.widgets['cheque_snapshot_receiver187'].cget('state'))=='disabled'
        w.next()
    else:
        w=m.v182.UnifiedPendingEditor182(root,row,runtime.rich,lambda:None)
    box = w.widgets['cheque_resolution_status187']
    assert box['values'][0] == 'صادرشده'  # listed, but greyed out and not selectable
    w.vars['cheque_resolution_status187'].set('صادرشده')
    box.event_generate('<<ComboboxSelected>>')
    assert w.vars['cheque_resolution_status187'].get() != 'صادرشده'
    w.vars['cheque_resolution_status187'].set(status)
    w.vars['cheque_resolution_registration187'].set('ثبت‌شده')
    w.vars['cheque_resolution_account_holder187'].set('حساب معرفی‌شده آزمایشی')
    w.vars['cheque_resolution_void_reason187'].set('ابطال آزمایشی')
    if form=='wizard':
        w.next()
        w.next()
    else:
        m._editor_approve_187(w)
    assert not errors
    assert runtime.db.get_pending_item(pid)['status']=='APPROVED'
    assert len(runtime.db.list_cheques(open_only=False))==1
    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque['cheque_id']))==status
    assert runtime.db.snapshot().construction_cost==before
    with runtime.db.connect() as con:
        assert con.execute('SELECT count(*) FROM transactions').fetchone()[0]==tx_count
    assert runtime.db.get_pending_item(source)['payload']['cheque_status']==m._cheque_resolution_status_code_187(status)
    with runtime.db.connect() as con:
        assert con.execute("SELECT count(*) FROM attachments WHERE entity_type='CHEQUE' AND entity_id=?",(cheque['cheque_id'],)).fetchone()[0]==1


def test_live_cheque_table_columns_and_active_editor(runtime,monkeypatch):
    from barkav_ui import art
    art.clear_cache()
    monkeypatch.setattr(m.v186.v185,'fetch_tgju_usd_toman',lambda timeout=6:(70000,'2026-10-05'))
    monkeypatch.setattr(m.DataEntryCenter187,'_start_gemini_probe_187',lambda self:None)
    monkeypatch.setattr(m.DataEntryCenter187,'_start_telegram_probe_187',lambda self:None)
    monkeypatch.setattr(m.Stage187Dashboard,'_show_startup_reminders_187',lambda self:None)
    payload=cheque_payload(); pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich)
    app=m.Stage187Dashboard()
    try:
        app.update(); app.refresh_cheques(); app.update()
        table=app.cheque_table
        columns=[item[0] for item in table.columns]
        assert columns[columns.index('reg')+1:columns.index('reg')+3]==['status','return_state']
        row=table.all_rows[0]
        values=dict(zip(table.tree['columns'],table.row_values(row)))
        for key,field in [('issuer','issuer_name'),('receiver','receiver_name'),('bank','issuer_bank'),('serial','cheque_serial'),('desc','description')]:
            assert values[key]==payload[field]
        assert values['status']=='صادرشده'
        editor=app.edit_cheque_row(row)
        assert isinstance(editor,m.v182.UnifiedPendingEditor182)
        assert editor.payload['_cheque_record_id187']==row['cheque_id']
        editor.destroy()
    finally:
        app.destroy()


def _manual_dialog(root, runtime, status):
    payload = cheque_payload()
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, payload, runtime.rich)
    cheque_id = runtime.db.list_cheques(open_only=False)[0]['cheque_id']
    resolution = register(runtime, dict(payload, cheque_operation187=m.CHEQUE_OPERATION_RESOLVE_187,
                                        selected_cheque_id187=cheque_id, cheque_resolution_status187='برگشتی'), 2)
    m._approve_cheque_resolution_187(resolution, dict(payload, cheque_operation187=m.CHEQUE_OPERATION_RESOLVE_187,
                                                      selected_cheque_id187=cheque_id,
                                                      cheque_resolution_status187='برگشتی'))
    row = runtime.db.get_cheque(cheque_id)
    dialog = m.v18.v175.ChequeEditDialog175(root, row, lambda: None)
    dialog.vars['lifecycle'].set(status)
    return cheque_id, resolution, dialog


def test_manual_status_change_updates_the_resolution_record_without_a_question(root, runtime, monkeypatch):
    asked = []
    monkeypatch.setattr(m, '_choose_cheque_incomplete_action_187', lambda *a: asked.append(a) or 'cancel')
    cheque_id, resolution, dialog = _manual_dialog(root, runtime, 'پاس‌شده')
    dialog.save(); root.update()
    assert not asked
    assert m._cheque_status_label_187(runtime.db.get_cheque(cheque_id)) == 'پاس‌شده'
    assert runtime.db.get_pending_item(resolution)['payload']['cheque_status'] == 'CASHED'


@pytest.mark.parametrize('answer', ['cancel', 'ignore', 'open'])
def test_a_status_that_lacks_its_details_asks_and_only_cancel_keeps_the_old_one(root, runtime, monkeypatch, answer):
    opened = []
    monkeypatch.setattr(m, '_choose_cheque_incomplete_action_187', lambda parent, missing: answer)
    monkeypatch.setattr(m.v18.v175, '_open_cheque_source_wizard175', lambda parent, pending: opened.append(pending))
    cheque_id, resolution, dialog = _manual_dialog(root, runtime, 'عودتی به شرط تسویه')
    dialog.vars['return_account_holder'].set('')
    dialog.save(); root.update(); root.update()
    label = m._cheque_status_label_187(runtime.db.get_cheque(cheque_id))
    if answer == 'cancel':
        assert label == 'برگشتی' and not opened
        assert runtime.db.get_pending_item(resolution)['payload']['cheque_status'] == 'RETURNED'
    else:
        assert label == 'عودتی به شرط تسویه'
        assert runtime.db.get_pending_item(resolution)['payload']['cheque_status'] == 'RETURNED_ON_SETTLEMENT'
        assert bool(opened) == (answer == 'open')


def test_return_disposition_manual_sync(root,runtime):
    payload=cheque_payload();pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich)
    row=runtime.db.list_cheques(open_only=False)[0]
    runtime.db.update_cheque_workflow_state(row['cheque_id'],lifecycle='VOIDED',
        void_reason='ابطال آزمایشی',return_disposition=m.CHEQUE_RETURN_DISPOSITION_CHOICES_187[3])
    dlg=m.v18.v175.ChequeEditDialog175(root,runtime.db.get_cheque(row['cheque_id']),lambda:None)
    dlg.vars['return_disposition'].set('دریافت چک')
    dlg.save()
    assert runtime.db.get_pending_item(pid)['payload']['cheque_return_disposition187']=='دریافت چک'


def test_themed_checks_and_status_stripe_at_right_scroll_edge(root):
    from tkinter import ttk
    from barkav_ui.row_overlay import RowDecorator, CHECK_COLUMN
    tree=ttk.Treeview(root,columns=('row','description','amount'),show='headings',height=4)
    tree.pack(fill='both',expand=True)
    for key in tree['columns']:
        tree.column(key,width=600,stretch=False)
    iid=tree.insert('','end',values=('☑ ۱','آزمایش اسکرول',1200),tags=('status_approved',))
    decorator=RowDecorator(tree)
    decorator._ensure_check_column()
    tree.xview_moveto(1)
    root.update()
    decorator._paint()
    root.update()
    cell=tree.bbox(iid,CHECK_COLUMN)
    assert cell and cell[0] >= 0
    assert decorator._stripes and decorator._stripes[0].winfo_x() >= tree.winfo_width()-12
    assert decorator._ticks


def test_issued_is_listed_in_the_resolution_status_box_but_greyed_out(root, runtime):
    pid = register(runtime, cheque_payload())
    e = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    e.vars['cheque_operation187'].set(m.CHEQUE_OPERATION_RESOLVE_187)
    root.update()
    box = e.widgets['cheque_resolution_status187']
    box.tk.call('ttk::combobox::Post', str(box))
    root.update()
    root.after(50)
    root.update()
    popdown = box.tk.call('ttk::combobox::PopdownWindow', str(box))
    greyed = box.tk.call(f'{popdown}.f.l', 'itemcget', 0, '-foreground')
    normal = box.tk.call(f'{popdown}.f.l', 'itemcget', 1, '-foreground')
    assert str(greyed) and str(greyed) != str(normal)
