"""Exercise actual Tk buttons, selected rows and the deletion mode dialog."""
import os
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import pytest
from test_transaction_lifecycle_matrix import runtime,register,case_payload,CASES,m
from test_transaction_lifecycle_ui import window,walk
from test_table_action_repair import incomes,choice_reply
from table_actions import DeleteChoice
import transaction_lifecycle_ui as actions

pytestmark=pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS')!='1',reason='GUI opt-in')


def select_all(window,table):
    table.tree.selection_set(table.tree.get_children())
    window.update()
    return table.selected_rows()


def test_real_bulk_button_uses_one_confirmation(runtime,window,monkeypatch):
    ids=incomes(runtime,3);window.refresh_all();window.update()
    table=window.in_table
    assert len(select_all(window,table))==3
    prompts,errors=choice_reply(monkeypatch)
    table.b_bulk_delete.invoke();window.update()
    assert prompts==[3] and not errors
    assert all(runtime.db.get_pending_item(pid)['status']=='REJECTED' for pid in ids)
    assert runtime.db.snapshot().cash_balance==0
    from transaction_lifecycle import TransactionLifecycle
    TransactionLifecycle(runtime.db).change_many(ids,restore=True)
    window.refresh_all();window.update();select_all(window,table)
    menus=[]
    class Menu:
        def __init__(self,*args,**kwargs):self.commands=[];menus.append(self)
        def add_command(self,**kwargs):self.commands.append(kwargs)
        def add_separator(self):pass
        def add_cascade(self,**kwargs):pass
        def tk_popup(self,*args):pass
        def grab_release(self):pass
    monkeypatch.setattr(m.tk,'Menu',Menu)
    iid=table.tree.selection()[0]
    y=table.tree.bbox(iid)[1]+2
    window._financial_context_menu_187(table,SimpleNamespace(y=y,x_root=0,y_root=0))
    assert len(table.selected_rows())==3
    next(item['command'] for item in menus[0].commands if item['label'].startswith('🗑'))()
    assert prompts==[3,3] and runtime.db.snapshot().cash_balance==0 and not errors


def test_delete_from_actual_rejected_table(runtime,window,monkeypatch):
    from transaction_lifecycle import TransactionLifecycle
    ids=incomes(runtime,2)
    for pid in ids:TransactionLifecycle(runtime.db).reject(pid)
    center=window.approval_center;center.filter.set('ردشده');center.refresh();window.update()
    rows=select_all(window,center.table)
    assert len(rows)==2
    import data_entry_extras_ui as extras
    prompts=[]
    monkeypatch.setattr(extras,'ask_delete',lambda parent,rows,**kw:prompts.append(len(rows)) or extras.DeleteDecision('delete'))
    errors=[]
    monkeypatch.setattr(m.messagebox,'showerror',lambda title,text,**kw:errors.append(text))
    center.table.on_delete(rows);window.update()
    assert prompts==[2] and not errors
    assert center.rows==[]
    assert all(TransactionLifecycle(runtime.db).get(pid)['state']=='PURGED' for pid in ids)


@pytest.mark.parametrize('single',[False,True])
def test_dialog_exposes_both_modes_and_returns_chosen_scope(runtime,window,single):
    captured=[]
    def answer():
        dialogs=[item for item in walk(window) if isinstance(item,tk.Toplevel) and item.title()=='تأیید حذف']
        if not dialogs:window.after(30,answer);return
        dialog=dialogs[-1]
        radios=[item for item in walk(dialog) if isinstance(item,ttk.Radiobutton)]
        captured.extend(item.cget('text') for item in radios)
        if single:radios[0].invoke()
        next(item for item in walk(dialog) if isinstance(item,ttk.Button) and item.cget('text')=='تأیید حذف').invoke()
    window.after(30,answer)
    result=actions.confirm_delete(window,3,messagebox=m.messagebox)
    assert len(captured)==2
    assert captured[0].startswith('حذف تکی') and captured[1].startswith('حذف گروهی')
    assert result.grouped is not single


@pytest.mark.parametrize('legacy',[False,True])
def test_generic_table_toolbar_and_context_have_same_group_scope(runtime,window,monkeypatch,legacy):
    import dashboard_stage12 as d12
    dialog=tk.Toplevel(window)
    table=(d12.SmartTable if legacy else m.SmartTable)(dialog,[('id','شناسه',80)])
    table.pack();deleted=[]
    def handler(row):
        if window._confirm_row_action('حذف','یک ردیف حذف شود؟'):deleted.append(row['id'])
    table.set_delete_handler(handler)
    table.set_rows([{'id':1},{'id':2},{'id':3}],lambda row:[row['id']])
    select_all(window,table)
    prompts,errors=choice_reply(monkeypatch)
    extra_prompts=[]
    monkeypatch.setattr(m.messagebox,'askyesno',lambda *args,**kwargs:extra_prompts.append(args) or True)
    table.b_bulk_delete.invoke()
    assert deleted==[1,2,3] and prompts==[3] and not errors
    assert not getattr(window,'_bulk_delete_confirmed',False)
    deleted.clear();table._delete_selected()
    assert deleted==[1,2,3] and prompts==[3,3]
    assert extra_prompts==[]
    dialog.destroy()


def test_financial_group_copy_and_data_entry_paste_keep_receipts_pending(runtime,window,tmp_path):
    ids=incomes(runtime,2)
    for pid in ids:
        receipt=tmp_path/(pid+'.png');receipt.write_bytes(b'fixture')
        runtime.db.attach_file_to_pending(pending_id=pid,local_path=str(receipt),mime_type='image/png')
        runtime.db.relink_pending_attachments(pid,entity_type='TRANSACTION',entity_id=runtime.db.get_financial_posting(pid)['transaction_id'])
    window.refresh_all();window.update();select_all(window,window.in_table)
    cloned=window._copy_transaction_187(window.in_table)
    assert len(cloned)==2 and len(set(cloned))==2
    assert runtime.db.snapshot().cash_balance==2000
    for pid in cloned:
        assert runtime.db.get_pending_item(pid)['status']=='PENDING_REVIEW'
        assert len(runtime.db.list_pending_attachments(pid))==1
        assert runtime.db.get_financial_posting(pid) is None
    center=window.approval_center
    center.copy_rows([runtime.db.get_pending_item(pid) for pid in ids])
    pasted=center.paste_rows([runtime.db.get_pending_item(cloned[0])])
    assert len(pasted)==2 and len(set(pasted))==2
    assert runtime.db.snapshot().cash_balance==2000
    assert all(len(runtime.db.list_pending_attachments(pid))==1 for pid in pasted)
    assert not window._test_errors
