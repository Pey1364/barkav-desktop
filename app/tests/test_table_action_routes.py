"""Selected-row routing checks without touching the user's project files."""
from contextlib import nullcontext
from types import SimpleNamespace as NS
import pytest
from test_transaction_lifecycle_matrix import m,runtime
from table_actions import DeleteChoice, confirmed_delete, current_delete_choice
import transaction_lifecycle_ui as actions


@pytest.fixture
def choose(monkeypatch):
    calls=[]
    monkeypatch.setattr(actions,'confirm_delete',lambda parent,count,**kw:calls.append(count) or DeleteChoice())
    return calls


def tree_for(ids):
    return NS(selection=lambda:tuple(ids),index=lambda iid:ids.index(iid))


def test_inventory_and_manager_send_entire_selection_to_lifecycle():
    from inventory_stage18_7 import InventoryPanel187
    calls=[]; rows=[{'pending_id':'a'},{'pending_id':'b'}]
    table=NS(selected_rows=lambda:rows)
    app=NS(_delete_lifecycle_rows187=calls.append)
    InventoryPanel187.delete_rows(NS(table=table,app=app))
    m.Stage187Dashboard._manager_delete_selected_187(NS(manager_withdraw_table=table,_delete_lifecycle_rows187=calls.append))
    assert calls==[rows,rows]


def test_price_copy_delete_all_selected_and_refresh_once(choose):
    from price_update_stage18_7 import PriceUpdatePanel187
    copied=[];deleted=[];refresh=[]
    service=NS(db=NS(atomic=nullcontext),copy_catalog_item=copied.append,soft_delete_catalog_item=deleted.append)
    panel=NS(table=NS(selected_keys=lambda:['a','b']),_rows_by_key={'a':{'price_id':'A'},'b':{'price_id':'B'}},
        service=service,_after_change=lambda:refresh.append(True))
    PriceUpdatePanel187.copy_selected(panel);PriceUpdatePanel187.delete_selected(panel)
    assert copied==deleted==['A','B'] and choose==[2] and len(refresh)==2


def test_plan_group_delete_skips_headings_and_renumbers_each_phase_once(choose):
    from project_plan_stage18_7 import ProjectPlanPanel187
    deleted=[];phases=[];saved=[]
    rows={'a':{'phase_item_id':'a','phase_no':1},'b':{'phase_item_id':'b','phase_no':1}}
    panel=NS(table=NS(tree=tree_for(['heading','a','b']),selected_keys=lambda:[('phase',None),(None,'a'),(None,'b')]),
        rich=NS(db=NS(atomic=nullcontext),get_phase_item=rows.get,delete_phase_item=deleted.append,renumber_phase=phases.append),
        _saved=lambda:saved.append(True))
    ProjectPlanPanel187.delete_selected(panel)
    assert deleted==['a','b'] and phases==[1] and saved==[True] and choose==[2]


@pytest.mark.parametrize('tab',['STATEMENTS','ARCHIVE'])
def test_contractor_auxiliary_delete_uses_all_rows(choose,monkeypatch,tab):
    import contractors_stage18_7 as c
    label=getattr(c,tab);deleted=[];refresh=[]
    monkeypatch.setattr(c,'delete_statement' if tab=='STATEMENTS' else 'delete_profile',deleted.append)
    panel=NS(tables={label:NS(tree=tree_for(['a','b']),selected_keys=lambda:['A','B'])},_statement_ids=['A','B'],_profile_ids=['A','B'],_changed=lambda:refresh.append(True))
    c.ContractorsPanel187.delete_selected(panel,label)
    assert deleted==['A','B'] and choose==[2] and refresh==[True]


def test_contractor_finance_delete_uses_lifecycle_instead_of_removing_file_first():
    import contractors_stage18_7 as c
    calls=[];rows=[{'pending_id':'a'},{'pending_id':'b'}]
    dashboard=NS(_delete_lifecycle_rows187=calls.append)
    panel=NS(_finance_dashboard=lambda:(dashboard,object()),_selected_finance_sources=lambda:rows,_changed=lambda:None)
    c.ContractorsPanel187._delete_finance_payment(panel)
    assert calls==[rows]


def test_contractor_finance_missing_source_blocks_whole_selection(monkeypatch):
    import contractors_stage18_7 as c
    errors=[]
    monkeypatch.setattr(c,'get_contract',lambda cid:{'payments':[{'pending_id':'ok'},{'pending_id':''}]})
    monkeypatch.setattr(c.messagebox,'showerror',lambda *args,**kw:errors.append(args))
    panel=NS(tables={c.FINANCE:NS(tree=tree_for(['a','b']),selected_keys=lambda:['C:0','C:1'])},_finance_payments=[
        {'contract_id':'C','payment_index':0},{'contract_id':'C','payment_index':1}],
        db=NS(get_pending_item=lambda pid:{'pending_id':pid}))
    assert c.ContractorsPanel187._selected_finance_sources(panel)==[] and len(errors)==1


def test_sorted_contractor_edit_and_copy_resolve_stable_identity(monkeypatch):
    import contractors_stage18_7 as c
    calls=[]
    monkeypatch.setattr(c,'get_contract',lambda key:calls.append(key) or {'contract_id':key})
    table=NS(selected_key=lambda:'B',tree=tree_for(['display-row-zero']))
    panel=NS(tables={c.CONTRACTS:table},_contract_ids=['A','B'],_row_keys=lambda tab:['A','B'])
    assert c.ContractorsPanel187._selected_contract(panel)['contract_id']=='B'
    assert c.ContractorsPanel187._selected_index(panel,c.CONTRACTS)==1 and calls==['B']


def test_sorted_plan_edit_resolves_stable_identity():
    from project_plan_stage18_7 import ProjectPlanPanel187
    calls=[]
    table=NS(selected_key=lambda:(None,'B'),tree=tree_for(['display-row-zero']))
    panel=NS(table=table,_nodes=[(None,'A'),(None,'B')],rich=NS(get_phase_item=lambda key:calls.append(key) or {'phase_item_id':key}))
    assert ProjectPlanPanel187._selected_row(panel)['phase_item_id']=='B' and calls==['B']


def test_confirmed_delete_scope_resets_after_failure():
    assert current_delete_choice() is None
    with pytest.raises(ValueError):
        with confirmed_delete(DeleteChoice()):
            assert current_delete_choice()==DeleteChoice()
            raise ValueError('fixture')
    assert current_delete_choice() is None


def test_sales_finance_actions_use_original_receipts():
    import sales_claims_stage18_7 as s
    rows=[{"received_payment_id":"a"},{"received_payment_id":"b"}]; deleted=[]; edited=[]; scopes=[]
    root=NS(_delete_lifecycle_rows187=deleted.append,edit_transaction_row=edited.append)
    def selected(**kwargs):
        scopes.append(kwargs); return rows
    panel=NS(winfo_toplevel=lambda:root,_selected_finance_receipts_187=selected,_changed=lambda:None)
    s.SalesClaimsPanel187._finance_delete(panel);s.SalesClaimsPanel187._finance_edit(panel)
    assert deleted==[rows] and edited==[rows[0]] and scopes==[{"all_receipts":True},{}]


def test_sales_delete_collects_every_receipt_in_the_selected_stage(runtime):
    import sales_claims_stage18_7 as s
    from test_transaction_lifecycle_matrix import case_payload,CASES,register
    payload=case_payload(runtime,next(case for case in CASES if case[2]=='فروش'))
    ids=[]
    for mid in (1,2):
        pid=register(runtime,payload,mid);m.v18.submit_v18(pid,payload,runtime.rich)
        ids.append(pid)
    with runtime.db.read() as con:
        iid=con.execute('SELECT installment_id FROM installments WHERE sale_id=?',(payload['sale_id'],)).fetchone()[0]
    panel=NS(db=runtime.db,finance_tree=object(),_checked_or_selected_rows=lambda tree:[iid])
    rows=s.SalesClaimsPanel187._selected_finance_receipts_187(panel,all_receipts=True)
    assert len(rows)==2 and len({row['received_payment_id'] for row in rows})==2
    assert len(s.SalesClaimsPanel187._selected_finance_receipts_187(panel))==1
    from transaction_lifecycle import TransactionLifecycle
    before=runtime.db.snapshot()
    life=TransactionLifecycle(runtime.db)
    life.change_many(ids[::-1])
    assert runtime.db.snapshot().cash_balance==0
    from test_table_action_repair import center_for
    center,_=center_for(runtime)
    actions.restore_rows(center,[runtime.db.get_pending_item(pid) for pid in ids[::-1]],runtime.db,m.messagebox)
    assert runtime.db.snapshot()==before


def test_group_rollback_restores_unselected_cheque_child_file_snapshots():
    from transaction_lifecycle import TransactionLifecycle
    calls=[];contracts={'root':['root'],'child':['child'],'bad':['bad']}
    life=object.__new__(TransactionLifecycle)
    life.db=NS(atomic=nullcontext,get_pending_item=lambda pid:{'status':'APPROVED'},
        read=lambda:nullcontext(NS(execute=lambda *args:[])))
    life.get=lambda pid:None
    life._cheque_dependents=lambda pid:['child'] if pid=='root' else []
    life._contracts=lambda pid:list(contracts[pid])
    life._set_contracts=lambda pid,rows:contracts.update({pid:rows})
    def reject(pid,**kw):
        calls.append(pid)
        if pid=='bad':raise ValueError('fixture')
        contracts['root']=[];contracts['child']=[]
    life.reject=reject
    with pytest.raises(ValueError):life.change_many(['root','bad'])
    assert calls==['root','bad'] and contracts=={'root':['root'],'child':['child'],'bad':['bad']}
