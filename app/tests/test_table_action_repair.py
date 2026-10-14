"""Behavioral regression coverage for the active table action paths."""
from types import SimpleNamespace
import pytest
from test_transaction_lifecycle_matrix import runtime,register,case_payload,CASES,m
from transaction_lifecycle import TransactionLifecycle
import transaction_lifecycle_ui as actions
from table_actions import DeleteChoice,copy_payload,copy_pending_attachments


def center_for(runtime):
    history=[]
    center=SimpleNamespace(rich=runtime.rich,refresh=lambda:None,on_posted=None,
        _push_history=history.append,action=SimpleNamespace(set=lambda text:None))
    return center,history


def incomes(runtime,count=2):
    ids=[]
    for index in range(count):
        payload=case_payload(runtime,CASES[5])
        pid=register(runtime,payload,index+1)
        m.v18.submit_v18(pid,payload,runtime.rich)
        ids.append(pid)
    return ids


def choice_reply(monkeypatch,choice=DeleteChoice()):
    prompts=[]
    monkeypatch.setattr(actions,'confirm_delete',lambda parent,count,**kw:prompts.append(count) or choice)
    errors=[]
    monkeypatch.setattr(m.messagebox,'showerror',lambda title,text,**kw:errors.append(text))
    return prompts,errors


def test_group_delete_confirms_once_and_undo_restores_whole_group(runtime,monkeypatch):
    ids=incomes(runtime,3);center,history=center_for(runtime)
    prompts,errors=choice_reply(monkeypatch)
    m.DataEntryCenter187.batch_delete18(center,[runtime.db.get_pending_item(pid) for pid in ids])
    assert prompts==[3] and not errors
    assert runtime.db.snapshot().cash_balance==0
    assert all(runtime.db.get_pending_item(pid)['status']=='REJECTED' for pid in ids)
    assert len(history)==1
    history[0]['action'].undo()
    assert runtime.db.snapshot().cash_balance==3000


def test_single_mode_only_deletes_first_selected_row(runtime,monkeypatch):
    ids=incomes(runtime);center,_=center_for(runtime)
    prompts,errors=choice_reply(monkeypatch,DeleteChoice(grouped=False))
    m.DataEntryCenter187.batch_delete18(center,[runtime.db.get_pending_item(pid) for pid in ids])
    assert prompts==[2] and not errors
    assert runtime.db.get_pending_item(ids[0])['status']=='REJECTED'
    assert runtime.db.get_pending_item(ids[1])['status']=='APPROVED'
    assert runtime.db.snapshot().cash_balance==1000


def test_cancel_has_no_financial_or_history_effect(runtime,monkeypatch):
    ids=incomes(runtime);center,history=center_for(runtime)
    prompts,errors=choice_reply(monkeypatch,None)
    m.DataEntryCenter187.batch_delete18(center,[runtime.db.get_pending_item(pid) for pid in ids])
    assert prompts==[2] and not errors and history==[]
    assert runtime.db.snapshot().cash_balance==2000


def test_failed_group_delete_rolls_back_successful_rows(runtime,monkeypatch):
    ids=incomes(runtime)
    posting=runtime.db.get_financial_posting(ids[0])
    with runtime.db.tx() as con:con.execute('UPDATE transactions SET amount=1200 WHERE transaction_id=?',(posting['transaction_id'],))
    before=runtime.db.snapshot();center,history=center_for(runtime)
    prompts,errors=choice_reply(monkeypatch)
    m.DataEntryCenter187.batch_delete18(center,[runtime.db.get_pending_item(pid) for pid in ids])
    assert prompts==[2] and len(errors)==1 and history==[]
    assert runtime.db.snapshot()==before
    assert all(runtime.db.get_pending_item(pid)['status']=='APPROVED' for pid in ids)
    assert all(TransactionLifecycle(runtime.db).get(pid)['state']=='ACTIVE' for pid in ids)


def test_delete_from_rejected_only_purges_history_without_reversing_again(runtime,monkeypatch):
    pid=incomes(runtime,1)[0];life=TransactionLifecycle(runtime.db)
    life.reject(pid)
    posting=runtime.db.get_financial_posting(pid)
    with runtime.db.tx() as con:con.execute('UPDATE transactions SET amount=1200 WHERE transaction_id=?',(posting['transaction_id'],))
    before=runtime.db.snapshot();center,history=center_for(runtime)
    prompts,errors=choice_reply(monkeypatch,DeleteChoice(permanent=True))
    m.DataEntryCenter187.batch_delete18(center,[runtime.db.get_pending_item(pid)])
    assert prompts==[1] and not errors
    assert life.get(pid)['state']=='PURGED'
    assert runtime.db.snapshot()==before
    assert pid not in {r['pending_id'] for r in runtime.db.list_pending_reviews(statuses=('REJECTED',))}
    assert not history[0]['action'].undoable


def test_legacy_rejected_draft_can_be_deleted(runtime,monkeypatch):
    pid=register(runtime,case_payload(runtime,CASES[5]))
    runtime.db.update_pending(pid,status='REJECTED')
    center,_=center_for(runtime);prompts,errors=choice_reply(monkeypatch,DeleteChoice(permanent=True))
    m.DataEntryCenter187.batch_delete18(center,[runtime.db.get_pending_item(pid)])
    assert not errors and TransactionLifecycle(runtime.db).get(pid)['state']=='PURGED'


def test_copy_payload_keeps_parent_links_and_removes_old_posting_ids():
    original={'v18_title':'خروجی','v18_subtype':'اقساط','loan_id':'LOAN',
              'posting_id':'OLD','transaction_id':'OLD-TX','description':'about','nested':{'a':1}}
    copied=copy_payload(original)
    assert copied['loan_id']=='LOAN'
    assert 'posting_id' not in copied and 'transaction_id' not in copied
    copied['nested']['a']=2
    assert original['nested']['a']==1
    assert 'loan_id' not in copy_payload(dict(original,v18_title='ورودی',v18_subtype='تسهیلات'))


def test_copy_preserves_relinked_receipt_with_new_attachment_identity(runtime,tmp_path):
    source=incomes(runtime,1)[0]
    target=register(runtime,case_payload(runtime,CASES[5]),2)
    receipt=tmp_path/'receipt.png';receipt.write_bytes(b'fixture')
    original=runtime.db.attach_file_to_pending(pending_id=source,local_path=str(receipt),mime_type='image/png')
    runtime.db.relink_pending_attachments(source,entity_type='TRANSACTION',entity_id='SOURCE-TX')
    copy_pending_attachments(runtime.db,source,target)
    attached=runtime.db.list_pending_attachments(target)
    assert len(attached)==1 and attached[0]['attachment_id']!=original
    assert attached[0]['local_path']==str(receipt)
    assert attached[0]['entity_id']==target


@pytest.mark.parametrize('tab,method',[('قراردادها','copy_selected_contract'),('صورت وضعیت','copy_selected_statement'),
    ('آرشیو','copy_selected_profile')])
def test_contractor_copy_routes_to_correct_record(monkeypatch,tab,method):
    import contractors_stage18_7 as c
    labels={c.CONTRACTS:'copy_selected_contract',c.STATEMENTS:'copy_selected_statement',c.ARCHIVE:'copy_selected_profile',c.FINANCE:'_copy_finance_payment'}
    calls=[]
    owner=SimpleNamespace(**{name:(lambda value=name:calls.append(value)) for name in labels.values()})
    for label,expected in labels.items():
        calls.clear();c.ContractorsPanel187.copy_selected(owner,label)
        assert calls==[expected]
