"""Actual Tk registration, record editing, deletion dialog and Restore menu."""
import os
import tkinter as tk
from tkinter import ttk
import pytest
from test_transaction_lifecycle_matrix import runtime,register,case_payload,CASES,views,m

pytestmark=pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS')!='1',reason='GUI opt-in')

def walk(widget):
    yield widget
    for child in widget.winfo_children():yield from walk(child)

def delete_answer(root,action='delete'):
    """Answer the question «حذف» asks in Data Entry: 'hide' or 'delete'."""
    attempts=[0]
    def answer():
        attempts[0]+=1
        dialogs=[w for w in walk(root) if getattr(w,'_ask_delete_accept187',None) is not None]
        if not dialogs:
            if attempts[0]<100:root.after(50,answer)
            return
        dialogs[-1]._ask_delete_action187.set(action)
        dialogs[-1]._ask_delete_accept187()
    root.after(50,answer)

def dialog_answer(root,*,purge=False,cancel=False):
    attempts=[0]
    def answer():
        attempts[0]+=1
        dialogs=[w for w in walk(root) if isinstance(w,tk.Toplevel) and w.title()=='تأیید حذف']
        if not dialogs:
            if attempts[0]<100:root.after(50,answer)
            return
        dialog=dialogs[-1]
        if cancel:dialog.close();return
        if purge:
            box=next(w for w in walk(dialog) if isinstance(w,ttk.Checkbutton))
            box.invoke()
        button=next(w for w in walk(dialog) if isinstance(w,ttk.Button) and w.cget('text')=='تأیید حذف')
        button.invoke()
    root.after(50,answer)

@pytest.fixture
def window(runtime,monkeypatch):
    failures=[]
    monkeypatch.setattr(m.v186.v185,'fetch_tgju_usd_toman',lambda **kw:(70000,'2026-09-30'))
    for name in ('showerror','showwarning'):
        monkeypatch.setattr(m.messagebox,name,lambda title,text,**kw:failures.append((title,text)))
    monkeypatch.setattr(m.messagebox,'showinfo',lambda *a,**kw:None)
    monkeypatch.setattr(m.messagebox,'askyesno',lambda *a,**kw:True)
    from barkav_ui import art
    art.clear_cache() # Cached PhotoImages belong to the previous fixture Tcl interpreter.
    print("GUI building",flush=True)
    root=m.Stage187Dashboard()
    root.title('BARKAV — آزمون خودکار، دادهٔ موقت')
    root.geometry('1500x950+0+0');root.update()
    # The first dashboard installs themed messagebox functions. Reapply the
    # test replies after installation; subsequent fixtures already had that skin.
    for name in ('showerror','showwarning'):
        monkeypatch.setattr(m.messagebox,name,lambda title,text,**kw:failures.append((title,text)))
    monkeypatch.setattr(m.messagebox,'showinfo',lambda *a,**kw:None)
    monkeypatch.setattr(m.messagebox,'askyesno',lambda *a,**kw:True)
    root._test_errors=failures
    yield root
    for widget in list(root.winfo_children()):
        if isinstance(widget,tk.Toplevel):widget.destroy()
    for job in root.tk.call('after','info'):
        try:root.after_cancel(job)
        except tk.TclError:pass
    try:root.destroy()
    except tk.TclError:
        # Legacy tooltips sometimes already remove a Tcl callback. Ensure
        # the interpreter's windows and journal hooks are still released.
        try:root.tk.call('destroy','.')
        except tk.TclError:pass
    if tk._default_root is root:tk._default_root=None
    import row_journal,file_journal
    row_journal.uninstall();file_journal.uninstall()


def test_every_type_through_real_record_window_delete_dialog_and_restore_menu(runtime,window):
    center=window.approval_center
    for index,case in enumerate(CASES):
        print("GUI case",case[0],"register",flush=True)
        payload=case_payload(runtime,case)
        if case[0]=='cash-partial':payload['amount']=400
        before=views(runtime)
        pid=register(runtime,payload,1000+index)
        editor=m.v182.UnifiedPendingEditor182(center,runtime.db.get_pending_item(pid),runtime.rich,
            window.refresh_all,navigation_rows=[runtime.db.get_pending_item(pid)],navigation_index=0)
        print("GUI editor",case[0],flush=True)
        editor.update();editor.approve();window.update()
        assert not window._test_errors,(case[0],window._test_errors)
        assert editor.winfo_exists() and editor._approved_editor_182,case[0]
        assert runtime.db.snapshot().cash_balance-before['snapshot']['cash_balance']==case[4],case[0]
        editor.destroy();window.refresh_all();window.update()
        rows=[r for r in window.all_tx_table.all_rows if r.get('pending_id')==pid]
        assert len(rows)==1,case[0]
        approved=views(runtime)
        print("GUI delete",case[0],flush=True)
        dialog_answer(window)
        window._delete_tx_row(rows[0]);window.update()
        assert not window._test_errors,(case[0],window._test_errors)
        assert runtime.db.get_pending_item(pid)['status']=='REJECTED'
        assert views(runtime)==before,case[0]
        print('GUI restore',case[0],flush=True)
        center.filter.set('ردشده');center.refresh();window.update()
        iid=next(i for i,r in center.table.iid_to_row.items() if r['pending_id']==pid)
        center.table.tree.selection_set(iid)
        center.table.menu.tk.call(center.table.menu.cget('postcommand'))
        assert center.table.menu.entrycget('بازگردانی / Restore','state')=='normal'
        center.table.menu.invoke('بازگردانی / Restore');window.update()
        assert views(runtime)==approved,case[0]
        assert not window._test_errors,(case[0],window._test_errors)
        rows=[r for r in window.all_tx_table.all_rows if r.get('pending_id')==pid]
        print('GUI purge',case[0],flush=True)
        dialog_answer(window,purge=True)
        window._delete_tx_row(rows[0]);window.update()
        assert views(runtime)==before,case[0]
        assert pid not in {r['pending_id'] for r in runtime.db.list_pending_reviews(statuses=('REJECTED',))}


def test_cancel_delete_preserves_source_and_all_effects(runtime,window):
    payload=case_payload(runtime,CASES[5]);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich);window.refresh_all()
    before=views(runtime)
    row=next(r for r in window.all_tx_table.all_rows if r.get('pending_id')==pid)
    dialog_answer(window,cancel=True)
    window._delete_tx_row(row)
    assert views(runtime)==before
    assert runtime.db.get_pending_item(pid)['status']=='APPROVED'


def test_edit_opens_original_record_and_reject_removes_effects(runtime,window):
    payload=case_payload(runtime,CASES[0]);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich);window.refresh_all()
    expense=next(r for r in window.exp_table.all_rows if r.get('pending_id')==pid)
    window.edit_expense_row(expense);window.update()
    editor=next(w for w in walk(window) if isinstance(w,m.v182.UnifiedPendingEditor182))
    assert editor.pid==pid
    editor.reject();window.update()
    assert runtime.db.snapshot().cash_balance==0
    assert runtime.db.get_pending_item(pid)['status']=='REJECTED'
    assert not window._test_errors


def test_unlinked_manual_row_is_queued_without_changing_finance(runtime,window):
    from transaction_lifecycle import TransactionLifecycle
    tx=runtime.db.post_transaction(event_date='2026-09-30',direction='IN',amount=1000,category='TEST')
    dialog_answer(window);window._delete_tx_row({'transaction_id':tx})
    assert runtime.db.snapshot().cash_balance==1000
    assert tx in TransactionLifecycle(runtime.db).decisions()
    assert window._test_errors[-1][0]=='تعیین تکلیف'


def test_final_cheque_dashboard_cost_no_cash_and_context_delete(runtime,window):
    payload=case_payload(runtime,CASES[3]);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich);window.refresh_all()
    assert m.parse_int(window.cards['cost'].var.get())==1000
    assert m.parse_int(window.cards['cash'].var.get())==0
    assert len([r for r in window.exp_table.all_rows if r.get('pending_id')==pid])==1
    cheque=next(r for r in window.cheque_table.all_rows if r.get('cheque_id')==runtime.db.get_financial_posting(pid)['cheque_id'])
    dialog_answer(window);window._cancel_cheque_row(cheque)
    assert m.parse_int(window.cards['cost'].var.get())==0
    assert runtime.db.get_pending_item(pid)['status']=='REJECTED'
    assert not window._test_errors


def test_record_navigation_uses_transaction_table_when_data_entry_is_filtered(runtime,window):
    ids=[]
    for mid in (1,2):
        payload={**case_payload(runtime,CASES[5]),'description':'ردیف '+str(mid)}
        pid=register(runtime,payload,mid);m.v18.submit_v18(pid,payload,runtime.rich);ids.append(pid)
    window.refresh_all();window.approval_center.filter.set('Pending');window.approval_center.refresh()
    rows=window.all_tx_table.filtered_rows
    first=rows[0]['pending_id'];last=rows[1]['pending_id']
    window.edit_transaction_row(rows[0]);window.update()
    editor=next(w for w in walk(window) if isinstance(w,m.v182.UnifiedPendingEditor182))
    assert editor.pid==first
    editor._navigate_record_182(1);window.update()
    assert editor.pid==last
    editor._navigate_record_182(-1);window.update()
    assert editor.pid==first
    assert not window._test_errors


def test_transaction_tab_undo_redo_restores_source_and_effects(runtime,window):
    payload=case_payload(runtime,CASES[5]);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich);window.refresh_all()
    node=window.all_tx_table;chain=[]
    while node is not window:
        chain.append(node);node=node.master
    for node in reversed(chain):
        if isinstance(node.master,ttk.Notebook):node.master.select(node)
    window.update();window._window_history._mark_input()
    row=next(r for r in window.all_tx_table.all_rows if r.get('pending_id')==pid)
    dialog_answer(window);window._delete_tx_row(row)
    assert runtime.db.snapshot().cash_balance==0
    window.undo();window.update()
    assert runtime.db.get_pending_item(pid)['status']=='APPROVED'
    assert runtime.db.snapshot().cash_balance==1000
    window.redo();window.update()
    assert runtime.db.get_pending_item(pid)['status']=='REJECTED'
    assert runtime.db.snapshot().cash_balance==0
    assert not window._test_errors


def test_rejected_delete_is_permanent_and_removed_queue_filter_returns_to_all(runtime,window):
    from transaction_lifecycle import TransactionLifecycle
    payload=case_payload(runtime,CASES[5]);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich)
    life=TransactionLifecycle(runtime.db);life.reject(pid)
    center=window.approval_center;center.filter.set('ردشده');center.refresh()
    delete_answer(window);center.batch_delete18([runtime.db.get_pending_item(pid)])
    assert life.get(pid)['state']=='PURGED'
    life.flag_decision('CONTRACT:C1','DELETE','رسید بدون مبدا')
    # The category was explicitly removed in 864607d. An already open view
    # can still hold its old filter, and must return to ordinary source rows.
    assert 'تعیین تکلیف' not in dict(center._STATUS_FILTERS_187).values()
    center.filter.set('تعیین تکلیف');center.refresh()
    assert center.filter.get()=='همه' and center.status_filter187.get()=='همه'
    assert not any(row.get('_lifecycle_decision_only187') or
                   row.get('_lifecycle_decision_key187') for row in center.rows)
    assert 'CONTRACT:C1' in life.decisions() # Display removal keeps audit state.
    assert life.get(pid)['state']=='PURGED'
    assert not window._test_errors


def test_reject_of_an_approved_record_in_edit_asks_again_and_declining_changes_nothing(runtime,window,monkeypatch):
    payload=case_payload(runtime,CASES[0]);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich);window.refresh_all()
    expense=next(r for r in window.exp_table.all_rows if r.get('pending_id')==pid)
    window.edit_expense_row(expense);window.update()
    editor=next(w for w in walk(window) if isinstance(w,m.v182.UnifiedPendingEditor182))
    runtime.db.begin_posting_revision(pending_id=pid,new_payload=dict(payload,amount=2500),source='GUI_187_EDIT',actor_id='GUI')
    cash=runtime.db.snapshot().cash_balance
    asked=[]
    monkeypatch.setattr(m.messagebox,'askyesno',lambda title,text,**kw:asked.append(text) or False)
    editor.reject();window.update()
    assert len(asked)==1 and 'اثر مالی دارد' in asked[0]
    assert runtime.db.get_pending_item(pid)['status']=='EDIT_PENDING'
    assert runtime.db.snapshot().cash_balance==cash
    monkeypatch.setattr(m.messagebox,'askyesno',lambda title,text,**kw:asked.append(text) or True)
    editor.reject();window.update()
    assert len(asked)==2
    assert runtime.db.get_pending_item(pid)['status']=='REJECTED'
    assert runtime.db.snapshot().cash_balance==0
    assert not window._test_errors
