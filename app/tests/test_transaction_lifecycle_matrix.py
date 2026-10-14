"""Runtime lifecycle audit with a disposable project; never uses production data."""
import os
import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
_BOOT=tempfile.TemporaryDirectory(prefix='barkav-lifecycle-import-')
os.environ['STAGE4_DB_PATH']=str(Path(_BOOT.name)/'boot.sqlite3')
os.environ['STAGE4_SHEETS_ENABLED']='false'
os.environ['TELEGRAM_BOT_TOKEN']='lifecycle-test'
os.environ['GEMINI_API_KEY']='lifecycle-test'
os.environ.setdefault('ADMIN_USER_ID','1')
os.environ.setdefault('GROUP_CHAT_ID','-100777')
import dashboard_stage18_7 as m
from finance_db import FinanceDB
from approval_service import ApprovalCenterService
from budget_rich_v163 import RichBudgetService

@pytest.fixture
def runtime(tmp_path,monkeypatch):
    monkeypatch.setenv('STAGE4_DB_PATH',str(tmp_path/'project.sqlite3'))
    db=FinanceDB(tmp_path/'project.sqlite3')
    service=type(m.SERVICE)(db,tmp_path)
    approval=ApprovalCenterService(db,tmp_path)
    rich=RichBudgetService(db,tmp_path)
    # Some older regression modules reload dashboard modules during collection.
    # Patch saved function globals too, so they cannot retain a previous test DB.
    from types import ModuleType,FunctionType
    queue=[m.__dict__]+[module.__dict__ for name,module in list(sys.modules.items())
        if name.startswith('dashboard_stage') and module is not None]
    seen=set()
    while queue:
        namespace=queue.pop()
        if id(namespace) in seen:continue
        seen.add(id(namespace))
        for key,value in (('DB',db),('SERVICE',service),('APPROVAL',approval),('BASE_DIR',tmp_path)):
            if key in namespace:monkeypatch.setitem(namespace,key,value)
        for value in list(namespace.values()):
            if isinstance(value,ModuleType) and value.__name__.startswith('dashboard_stage'):
                queue.append(value.__dict__)
            elif isinstance(value,FunctionType) and value.__module__.startswith('dashboard_stage'):
                queue.append(value.__globals__)
                for cell in value.__closure__ or ():
                    if isinstance(cell.cell_contents,ModuleType) and cell.cell_contents.__name__.startswith('dashboard_stage'):
                        queue.append(cell.cell_contents.__dict__)
    return SimpleNamespace(db=db,service=service,approval=approval,rich=rich)

def register(runtime,payload,message_id=1):
    runtime.db.register_telegram_message(chat_id=-989,message_id=message_id,
        raw_text='متن مستقل تست',content_type='TEXT',message_date='2026-09-30T10:00:00')
    return runtime.db.create_or_replace_pending(telegram_chat_id=-989,
        telegram_message_id=message_id,detected_type=payload['detected_type'],
        payload=payload,confidence=1.0,status='PENDING_REVIEW')

def test_data_entry_delete_removes_an_approved_income_from_cash(runtime,monkeypatch):
    payload={'detected_type':'INCOME','v18_title':'ورودی','v18_subtype':'سایر',
        'event_date_shamsi':'1405/07/08','amount':1000,'description':'درآمد آزمون'}
    pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich)
    assert runtime.db.snapshot().cash_balance==1000
    center=SimpleNamespace(rich=runtime.rich,refresh=lambda:None,
        _push_history=lambda a:None,action=SimpleNamespace(set=lambda value:None),on_posted=None)
    monkeypatch.setattr(m.messagebox,'askyesno',lambda *a,**kw:True)
    m.DataEntryCenter187.batch_delete18(center,[runtime.db.get_pending_item(pid)])
    assert runtime.db.snapshot().cash_balance==0
    assert runtime.db.get_pending_item(pid)['status']=='REJECTED'

def test_atomic_scope_rolls_back_all_nested_services(runtime):
    with pytest.raises(ValueError):
        with runtime.db.atomic():
            runtime.db.set_setting('temporary-atomic','changed')
            other=FinanceDB.__new__(FinanceDB)
            other.db_path=runtime.db.db_path
            with other.read() as con:
                assert con.execute("SELECT value FROM settings WHERE key='temporary-atomic'").fetchone()[0]=='changed'
            raise ValueError('abort')
    assert runtime.db.get_setting('temporary-atomic') is None

from transaction_lifecycle import TransactionLifecycle, LifecycleDecision
from financial_calendar_stage18_7 import collect_financial_events_187, message_events_187
from cost_allocation_stage18_7 import actual_totals
from revenue_service import RevenueService
from loan_service import LoanService

NOTE_TYPES=list(m.v18.TITLE_TYPES['یادداشت'])
CASES=[('cash-paid','هزینه ساخت','نقدی',{'payment_state':'PAID','paid_amount':1000},-1000,1000),
 ('cash-unpaid','هزینه ساخت','نقدی',{'payment_state':'UNPAID','paid_amount':0},0,1000),
 ('cash-partial','هزینه ساخت','نقدی',{'payment_state':'PARTIAL','paid_amount':400},-400,1000),
 ('cheque','هزینه ساخت','چک',{'payment_method':'CHEQUE','is_cheque':True,'cheque_status':'ISSUED','due_date_shamsi':'1405/08/08'},0,1000),
 ('guarantee','هزینه ساخت','چک',{'payment_method':'CHEQUE','is_cheque':True,'is_guarantee':True,'cheque_status':'ISSUED','due_date_shamsi':'1405/08/08'},0,0),
 ('income','ورودی','سایر',{},1000,0),('partner','ورودی','شرکا/قرض',{'partner_name':'شریک آزمون','partner_kind':'قطعی'},1000,0),
 ('borrow','ورودی','شرکا/قرض',{'partner_name':'شریک آزمون','partner_kind':'قرض','partner_return_date':'1405/08/08'},1000,0),
 ('loan','ورودی','تسهیلات',{'loan_total_amount':1000,'loan_bank':'بانک آزمون','loan_start_date':'1405/07/08','installment_count':2,'interest_rate':0},1000,0),
 ('sale','ورودی','فروش',{},1000,0),('out','خروجی','سایر',{},-1000,0),
 ('installment','خروجی','اقساط',{'installments_paid_now':1},-1000,0)] + [
 ('note-'+str(i),'یادداشت',sub,{'calendar_date_shamsi':'1405/08/08','report_date_shamsi':'1405/07/08','report_rows':[{'description':'کار تست'}],
 'reminder_date_shamsi':'1405/08/08','invoice_note_date_shamsi':'1405/07/08','note_subject':'فنی'},0,0)
 for i,sub in enumerate(NOTE_TYPES)]
CASES += [('manager-salary', 'حقوق مدیر پروژه', 'نقدی', {}, -1000, 0)]
CASES += [
 ('land-fixed','خرید زمین','خرید زمین',
  {'land_payment_mode187':'همه موارد','payment_state':'PAID','total_debt':1000,
   'land_cash_amount':400,'land_cheque_amount':300,'land_barter_amount':300,
   'land_barter_description':'ملک نمونه','due_date_shamsi':'1405/08/08'},-400,1000),
 ('land-mixed','خرید زمین','نقدی، چک، معاوضه',
  {'payment_state':'PAID','total_debt':1000,'land_cash_amount':400,'land_cheque_amount':300,
   'land_barter_amount':300,'land_barter_description':'ملک نمونه','due_date_shamsi':'1405/08/08'},-400,1000),
 ('land-cash','خرید زمین','نقدی',{'payment_state':'PAID','total_debt':1000,'land_cash_amount':1000},-1000,1000),
 ('land-cheque','خرید زمین','چک',{'payment_state':'PAID','total_debt':1000,'land_cheque_amount':1000,
  'due_date_shamsi':'1405/08/08'},0,1000),
 ('land-barter','خرید زمین','معاوضه',{'payment_state':'PAID','total_debt':1000,
  'land_barter_amount':1000,'land_barter_description':'ملک نمونه'},0,1000),
]

def case_payload(runtime,case):
    name,title,sub,extra,cash,cost=case
    payload={'detected_type':m.v18._backend_type(title,sub),'v18_title':title,'v18_subtype':sub,
        'event_date_shamsi':'1405/07/08','amount':1000,'final_amount':1000,
        'description':'شرح مستقل '+name,'plan_ref':'AUDIT-LINE','cost_group':'مصالح','payment_method':'BANK_TRANSFER',**extra}
    if sub=='فروش':
        obj=RevenueService(runtime.db).create_sale_bundle(project_name='آزمون',block_name='A',unit_number='1',buyer_name='خریدار',
            contract_date_shamsi='1405/07/08',contract_amount=2000,installments=[{'amount':2000,'due_date_shamsi':'1405/08/08'}])
        payload['sale_id']=obj['sale_id']
    if sub=='اقساط':
        obj=LoanService(runtime.db).create_loan(lender_name='بانک',principal_amount=2000,net_received_amount=0,
            received_date_shamsi='1405/07/08',installment_count=2,installment_amount=1000,first_due_date_shamsi='1405/08/08',register_cash=False)
        payload['loan_id']=obj['loan_id']
    return payload

def views(runtime):
    # Services used by the actual dashboard, ledger, plan, sales, loans and calendar.
    from dataclasses import asdict
    from datetime import date
    from financial_calendar_stage18_7 import collect_financial_events_187
    return {'snapshot':asdict(runtime.db.snapshot()),'flow':runtime.service.financial_flow_totals(),
        'manager':asdict(runtime.service.manager_summary_shamsi('1405/07/01','1405/09/01')),
        'cheques':runtime.service.cheque_total_summary(),'actuals':actual_totals(runtime.db),
        'transactions':sorted((r['transaction_id'],r['amount']) for r in runtime.service.list_transactions()),
        'expenses':sorted((r['expense_id'],r['final_amount']) for r in runtime.service.list_construction_expenses()),
        'documents':sorted((r['document_id'],r['description']) for r in runtime.rich.list_documents()),
        'cheque_rows':sorted(r['cheque_id'] for r in runtime.db.list_cheques(limit=500)),
        'records':sorted(str(r.get('pending_id') or r.get('transaction_id') or '') for r in runtime.service.list_registered_records()),
        'events':[asdict(e) for e in collect_financial_events_187(runtime.service,370)],
        'messages':[asdict(e) for e in message_events_187(runtime.service,30,document_service=runtime.rich)],
        'loans':[(r['loan_id'],r['paid_total'],r['remaining_debt']) for r in LoanService(runtime.db).list_loans()],
        'sales':[(r['sale_id'],asdict(RevenueService(runtime.db).sale_summary(r['sale_id']))) for r in RevenueService(runtime.db).list_sales(active_only=True)]}

@pytest.mark.parametrize('case',CASES,ids=[c[0] for c in CASES])
def test_each_type_affects_views_rejects_restores_and_purges(runtime,case):
    payload=case_payload(runtime,case); baseline=views(runtime)
    pid=register(runtime,payload);m.v18.submit_v18(pid,payload,runtime.rich)
    approved=views(runtime)
    assert approved['snapshot']['cash_balance']-baseline['snapshot']['cash_balance']==case[4]
    assert approved['snapshot']['construction_cost']-baseline['snapshot']['construction_cost']==(0 if case[1]=='خرید زمین' else case[5]*11//10)
    assert pid in approved['records'], 'Approved noncash records must exist in Transactions'
    if case[0] in ('loan','sale','installment'):
        assert len(approved['records'])==len(baseline['records'])+1
    if case[0]=='loan':assert len(approved['loans'])==len(baseline['loans'])+1
    if case[0]=='sale':assert approved['sales']!=baseline['sales']
    if case[0]=='installment':assert approved['loans']!=baseline['loans']
    if case[1]=='خرید زمین':
        # An explicitly linked land expense now keeps its plan reference.
        # It contributes to the land plan's actuals and reverses with its
        # source, without adding construction manager fees.
        assert approved['actuals']['AUDIT-LINE'] == (1000, 'EXPENSES')
        assert runtime.db.manager_fee_accrued() == 0
        assert len(approved['records'])==len(baseline['records'])+1
    elif case[5]:assert approved['actuals']['AUDIT-LINE'][0]==1000
    if case[0] in ('cheque','guarantee'):
        assert approved['cheques']['amount']-baseline['cheques']['amount']==1000
        assert approved['events']!=baseline['events']
        assert len(approved['cheque_rows'])==len(baseline['cheque_rows'])+1
    if case[1]=='یادداشت':assert len(approved['documents'])==len(baseline['documents'])+1
    lifecycle=TransactionLifecycle(runtime.db);lifecycle.reject(pid)
    assert runtime.db.get_pending_item(pid)['status']=='REJECTED'
    assert views(runtime)==baseline
    lifecycle.restore(pid)
    assert views(runtime)==approved
    lifecycle.restore(pid)
    assert views(runtime)==approved
    lifecycle.reject(pid,permanent=True)
    assert views(runtime)==baseline
    assert pid not in {r['pending_id'] for r in runtime.db.list_pending_reviews(statuses=('REJECTED',))}
    with pytest.raises(ValueError):lifecycle.restore(pid)


@pytest.mark.parametrize('case',CASES,ids=[c[0] for c in CASES])
def test_edit_same_source_then_reject_clears_latest_effects(runtime,case):
    payload=case_payload(runtime,case);baseline=views(runtime)
    pid=register(runtime,payload);m.v18.submit_v18(pid,payload,runtime.rich)
    # Existing numeric dependencies are retained. Change amount for types that
    # accept arbitrary amounts; installment payment remains one complete installment.
    changed={**payload,'description':'شرح اصلاح‌شده مستقل'}
    if case[1]!='یادداشت' and case[2]!='اقساط':
        changed.update(amount=600,final_amount=600)
        if case[1]=='خرید زمین':
            changed['total_debt']=600
            for key in ('land_cash_amount','land_cheque_amount','land_barter_amount'):
                changed[key]=int(payload.get(key,0)*0.6)
        if case[0]=='cash-partial':changed['paid_amount']=200
        elif case[0]=='cash-paid':changed['paid_amount']=600
    m.v18.submit_v18(pid,changed,runtime.rich)
    assert runtime.db.get_pending_item(pid)['status']=='APPROVED'
    assert len([r for r in runtime.service.list_registered_records() if r.get('pending_id')==pid])==1
    edited=views(runtime)
    TransactionLifecycle(runtime.db).reject(pid)
    assert views(runtime)==baseline
    TransactionLifecycle(runtime.db).restore(pid)
    assert views(runtime)==edited


def test_approval_failure_rolls_back_cash_and_source(runtime):
    pid=register(runtime,{'detected_type':'INCOME','amount':1000})
    before=runtime.db.snapshot()
    def fail():
        runtime.db.post_transaction(event_date='2026-09-30',direction='IN',amount=999,category='TEST')
        runtime.db.update_pending(pid,status='APPROVED')
        from loan_service import LoanService
        LoanService(runtime.db) # DDL must not implicitly commit partial approval.
        raise ValueError('injected failure')
    with pytest.raises(ValueError):TransactionLifecycle(runtime.db).run(pid,fail)
    assert runtime.db.snapshot()==before
    assert runtime.db.get_pending_item(pid)['status']=='PENDING_REVIEW'


def test_changed_dependency_refuses_without_partial_changes(runtime):
    payload=case_payload(runtime,CASES[0]);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich)
    posting=runtime.db.get_financial_posting(pid)
    with runtime.db.tx() as con:con.execute('UPDATE transactions SET amount=1200 WHERE transaction_id=?',(posting['transaction_id'],))
    before=views(runtime)
    with pytest.raises(LifecycleDecision):TransactionLifecycle(runtime.db).reject(pid)
    assert views(runtime)==before
    assert runtime.db.get_pending_item(pid)['status']=='APPROVED'


def test_contractor_receipt_reject_restore_and_resolve_contract(runtime):
    from contractor_store_stage18_7 import upsert_contract,get_contract,delete_contracts
    from contract_deletion import delete_contractors
    upsert_contract({'contract_id':'C1','title':'قرارداد آزمون','total_amount':2000,'payments':[]})
    payload={**case_payload(runtime,CASES[0]),'contract_id':'C1','cost_group':'پیمانکار'}
    pid=register(runtime,payload);m.v18.submit_v18(pid,payload,runtime.rich)
    assert sum(__import__('contractor_store_stage18_7').amount_of(p['amount']) for p in get_contract('C1')['payments'])==1000
    with pytest.raises(ValueError):delete_contracts(['C1'])
    lifecycle=TransactionLifecycle(runtime.db);lifecycle.reject(pid)
    assert not get_contract('C1')['payments']
    lifecycle.restore(pid)
    assert sum(__import__('contractor_store_stage18_7').amount_of(p['amount']) for p in get_contract('C1')['payments'])==1000
    assert delete_contractors(runtime.db,['C1'])==1
    assert get_contract('C1') is None
    assert runtime.db.get_pending_item(pid)['status']=='REJECTED'
    assert runtime.db.snapshot().cash_balance==0
    with pytest.raises(LifecycleDecision):lifecycle.restore(pid)


def test_sales_contract_resolves_two_receipts_in_reverse_order(runtime):
    from contract_deletion import delete_sale
    payload=case_payload(runtime,next(c for c in CASES if c[0]=='sale'))
    ids=[]
    for mid in (1,2):
        pid=register(runtime,{**payload,'amount':500},mid);m.v18.submit_v18(pid,{**payload,'amount':500},runtime.rich);ids.append(pid)
    assert runtime.db.snapshot().cash_balance==1000
    assert delete_sale(runtime.db,payload['sale_id'])==2
    assert runtime.db.snapshot().cash_balance==0
    assert not RevenueService(runtime.db).list_sales(active_only=True)
    assert all(runtime.db.get_pending_item(pid)['status']=='REJECTED' for pid in ids)
    with pytest.raises(LifecycleDecision):TransactionLifecycle(runtime.db).restore(ids[0])


def test_contract_with_unlinked_receipt_needs_decision(runtime):
    from contract_deletion import delete_contractors
    from contractor_store_stage18_7 import upsert_contract,get_contract
    record={'contract_id':'C1','title':'بدون مبدا','payments':[{'amount':1000}]}
    upsert_contract(record)
    with pytest.raises(LifecycleDecision):delete_contractors(runtime.db,['C1'])
    assert get_contract('C1')==record


def test_schema_backup_and_restart_preserve_restore(runtime):
    import sqlite3
    payload=case_payload(runtime,CASES[5]);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich);TransactionLifecycle(runtime.db).reject(pid)
    backups=list(Path(runtime.db.db_path).parent.glob('.barkav-migration-backups/*pre-lifecycle.sqlite3'))
    assert backups
    with sqlite3.connect(backups[0]) as con:
        assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not con.execute("SELECT 1 FROM sqlite_master WHERE name='transaction_lifecycle'").fetchone()
    TransactionLifecycle(FinanceDB(runtime.db.db_path)).restore(pid)
    assert runtime.db.snapshot().cash_balance==1000


@pytest.mark.parametrize('cheque_type',['PHYSICAL','DIGITAL'])
def test_fresh_cashed_cheque_rejects_all_owned_effects_and_restores(runtime,cheque_type):
    payload={**case_payload(runtime,CASES[3]),'cheque_type':cheque_type,'cheque_status':'CASHED'}
    baseline=views(runtime);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich)
    approved=views(runtime)
    assert approved['snapshot']['cash_balance']==-1000
    assert approved['snapshot']['construction_cost']==1100
    assert approved['snapshot']['open_cheque_commitments']==0
    lifecycle=TransactionLifecycle(runtime.db);lifecycle.reject(pid)
    assert views(runtime)==baseline
    lifecycle.restore(pid)
    assert views(runtime)==approved


def test_delete_cheque_resolves_owned_clearing_receipt_then_restores_both(runtime):
    payload=case_payload(runtime,CASES[3]);baseline=views(runtime)
    origin=register(runtime,payload);m.v18.submit_v18(origin,payload,runtime.rich)
    clearing={**payload,'v18_subtype':'نقدی','detected_type':'EXPENSE','payment_method':'BANK_TRANSFER','is_cheque':False,'payment_state':'CHEQUE_CLEARING'}
    receipt=register(runtime,clearing,2);m.v18.submit_v18(receipt,clearing,runtime.rich)
    approved=views(runtime)
    assert approved['snapshot']['construction_cost']==1100
    assert approved['snapshot']['cash_balance']==-1000
    lifecycle=TransactionLifecycle(runtime.db);lifecycle.reject(origin)
    assert views(runtime)==baseline
    assert runtime.db.get_pending_item(receipt)['status']=='REJECTED'
    lifecycle.restore(origin)
    assert views(runtime)==approved
    assert runtime.db.get_pending_item(receipt)['status']=='APPROVED'


def test_unowned_historical_clearing_requires_decision(runtime):
    payload=case_payload(runtime,CASES[3]);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich)
    cheque=runtime.db.get_financial_posting(pid)['cheque_id']
    runtime.db.cash_cheque(cheque,cashed_date='2026-09-30')
    baseline=views(runtime)
    with pytest.raises(LifecycleDecision):TransactionLifecycle(runtime.db).reject(pid)
    assert views(runtime)==baseline


def test_backup_connection_is_closed_immediately(runtime):
    TransactionLifecycle(runtime.db)
    backup=next(Path(runtime.db.db_path).parent.glob('.barkav-migration-backups/*pre-lifecycle.sqlite3'))
    renamed=backup.with_suffix('.renamed');backup.rename(renamed);renamed.rename(backup)


def seed_plan_line(runtime):
    with runtime.db.tx() as con:
        con.execute("INSERT INTO rich_price_items(price_id,description,category,unit,created_at,updated_at) VALUES('PRICE','قیمت آزمون','اجرت','متر','2026-09-30','2026-09-30')")
        con.execute("""INSERT INTO rich_phase_items(phase_item_id,phase_no,phase_name,section,
            description,cost_type,unit,qty_actual,local_actual_rate,plan_ref,price_id,created_at,updated_at)
            VALUES('LINE',2,'آزمون','LABOR','شرح قبلی','اجرت','متر',0,0,'LAB-LINE','PRICE','2026-09-30','2026-09-30')""")

def plan_line(runtime):
    with runtime.db.read() as con:return dict(con.execute("SELECT * FROM rich_phase_items WHERE phase_item_id='LINE'").fetchone())


def test_contract_delete_clears_derived_actual_rate_quantity_and_total(runtime):
    from contractor_store_stage18_7 import upsert_contract
    from cost_allocation_stage18_7 import apply_actuals
    from contract_deletion import delete_contractors
    seed_plan_line(runtime)
    contract={'contract_id':'C1','title':'پیمانکار آزمون','total_amount':1000,'payments':[],
        'rows':[{'plan_ref':'LAB-LINE','quantity':2,'unit_price':500,'description':'شرح قرارداد'}]}
    upsert_contract(contract);apply_actuals(runtime.db)
    assert plan_line(runtime)['local_actual_rate']==500
    assert plan_line(runtime)['qty_actual']==2
    assert plan_line(runtime)['total_actual']==1000
    delete_contractors(runtime.db,['C1'])
    assert plan_line(runtime)['local_actual_rate']==0
    assert plan_line(runtime)['qty_actual']==0
    assert plan_line(runtime)['total_actual']==0
    assert plan_line(runtime)['description']=='شرح قبلی'


def test_contract_delete_preserves_manual_actual_values(runtime):
    from contractor_store_stage18_7 import upsert_contract
    from cost_allocation_stage18_7 import apply_actuals
    from contract_deletion import delete_contractors
    seed_plan_line(runtime)
    with runtime.db.tx() as con:con.execute("UPDATE rich_phase_items SET local_actual_rate=70,qty_actual=3 WHERE phase_item_id='LINE'")
    upsert_contract({'contract_id':'C1','title':'آزمون','total_amount':1000,'payments':[],
        'rows':[{'plan_ref':'LAB-LINE','quantity':2,'unit_price':500}]})
    apply_actuals(runtime.db);delete_contractors(runtime.db,['C1'])
    assert plan_line(runtime)['local_actual_rate']==70
    assert plan_line(runtime)['qty_actual']==3


def test_legacy_price_override_without_provenance_needs_decision(runtime):
    from contractor_store_stage18_7 import upsert_contract,get_contract
    from contract_deletion import delete_contractors
    seed_plan_line(runtime)
    upsert_contract({'contract_id':'C1','title':'قدیمی','payments':[],
        'rows':[{'plan_ref':'LAB-LINE','quantity':2,'unit_price':500}]})
    with runtime.db.tx() as con:con.execute("UPDATE rich_phase_items SET actual_source='CONTRACTS',local_actual_rate=500,qty_actual=2 WHERE phase_item_id='LINE'")
    with pytest.raises(LifecycleDecision):delete_contractors(runtime.db,['C1'])
    assert get_contract('C1')
    assert plan_line(runtime)['local_actual_rate']==500


def test_late_cheque_reminders_reject_restore_and_purge(runtime):
    payload=case_payload(runtime,CASES[3]);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich)
    cheque=runtime.db.get_financial_posting(pid)['cheque_id']
    with runtime.db.tx() as con:
        con.execute("INSERT INTO reminders(reminder_id,entity_type,entity_id,scheduled_at,status,created_at,updated_at) VALUES('R','CHEQUE',?,'2026-10-10','SCHEDULED','2026-09-30','2026-09-30')",(cheque,))
    lifecycle=TransactionLifecycle(runtime.db);lifecycle.reject(pid)
    with runtime.db.read() as con:assert con.execute("SELECT status FROM reminders WHERE reminder_id='R'").fetchone()[0]=='CANCELLED'
    lifecycle.restore(pid)
    with runtime.db.read() as con:assert con.execute("SELECT status FROM reminders WHERE reminder_id='R'").fetchone()[0]=='SCHEDULED'
    lifecycle.reject(pid,permanent=True)
    with runtime.db.read() as con:assert con.execute("SELECT status FROM reminders WHERE reminder_id='R'").fetchone()[0]=='CANCELLED'


def test_legacy_sale_receipt_edit_requires_decision_without_duplicate(runtime):
    payload=case_payload(runtime,next(c for c in CASES if c[0]=='sale'))
    pid=register(runtime,payload);m.v18.submit_v18(pid,payload,runtime.rich)
    with runtime.db.tx() as con:con.execute('DELETE FROM transaction_lifecycle WHERE pending_id=?',(pid,))
    before=views(runtime)
    with pytest.raises(LifecycleDecision):m.v18.submit_v18(pid,{**payload,'amount':500},runtime.rich)
    assert views(runtime)==before


def test_successful_reject_clears_resolved_decision(runtime):
    payload=case_payload(runtime,CASES[5]);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich)
    lifecycle=TransactionLifecycle(runtime.db);lifecycle.flag_decision(pid,'DELETE','بررسی انجام شد')
    lifecycle.reject(pid);assert pid not in lifecycle.decisions()


def test_original_document_wizard_edit_and_reject_clear_current_document(runtime):
    payload=case_payload(runtime,next(c for c in CASES if c[1]=='یادداشت'))
    baseline=views(runtime);pid=register(runtime,payload);m.v18.submit_v18(pid,payload,runtime.rich)
    document=runtime.rich.list_documents()[0]['document_id']
    changed={**payload,'description':'شرح اصلاح شده','_document_edit_id_187':document}
    runtime.db.update_pending(pid,payload=changed)
    m.v18.submit_v18(pid,changed,runtime.rich)
    assert len(runtime.rich.list_documents())==1
    assert 'شرح اصلاح شده' in runtime.rich.list_documents()[0]['description']
    TransactionLifecycle(runtime.db).reject(pid);assert views(runtime)==baseline


def test_determination_queue_includes_unlinked_contract_sale_without_fake_pending(runtime):
    lifecycle=TransactionLifecycle(runtime.db)
    before=runtime.db.list_pending_reviews()
    for key in ('CONTRACT:C1','SALE:S1','TX-unlinked'):lifecycle.flag_decision(key,'DELETE','مبدا باید بررسی شود')
    rows=lifecycle.decision_rows([])
    assert len(rows)==3 and all(r.get('_lifecycle_decision_only187') and not r.get('pending_id') for r in rows)
    assert runtime.db.list_pending_reviews()==before


def test_actual_phase_expense_total_clears_after_reject(runtime):
    from cost_allocation_stage18_7 import apply_actuals
    seed_plan_line(runtime)
    with runtime.db.tx() as con:con.execute("UPDATE rich_phase_items SET cost_type='مصالح',plan_ref='AUDIT-LINE' WHERE phase_item_id='LINE'")
    payload=case_payload(runtime,CASES[0]);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich);apply_actuals(runtime.db)
    assert plan_line(runtime)['total_actual']==1000
    TransactionLifecycle(runtime.db).reject(pid);apply_actuals(runtime.db)
    assert plan_line(runtime)['total_actual']==0


def test_contract_removal_preserves_later_manual_field_edit(runtime):
    from contractor_store_stage18_7 import upsert_contract
    from cost_allocation_stage18_7 import apply_actuals
    from contract_deletion import delete_contractors
    seed_plan_line(runtime)
    upsert_contract({'contract_id':'C1','title':'آزمون','total_amount':1000,'payments':[],
        'rows':[{'plan_ref':'LAB-LINE','quantity':2,'unit_price':500}]})
    apply_actuals(runtime.db)
    with runtime.db.tx() as con:con.execute("UPDATE rich_phase_items SET local_actual_rate=900 WHERE phase_item_id='LINE'")
    delete_contractors(runtime.db,['C1'])
    assert plan_line(runtime)['local_actual_rate']==900
    assert plan_line(runtime)['qty_actual']==0


def test_all_runtime_titles_and_subtypes_have_lifecycle_cases():
    covered={(case[1],case[2]) for case in CASES}
    assert {(title,sub) for title,subs in m.v18.TITLE_TYPES.items() for sub in subs}<=covered


@pytest.mark.parametrize('group',['مصالح','پیمانکار','خدمات'])
@pytest.mark.parametrize('method',['BANK_TRANSFER','CASH_POS','OTHER'])
@pytest.mark.parametrize('state,paid,cash',[('PAID',1000,-1000),('PARTIAL',400,-400),('UNPAID',0,0)])
def test_cost_sections_and_methods_apply_then_reverse_every_view(runtime,group,method,state,paid,cash):
    payload={**case_payload(runtime,CASES[0]),'cost_group':group,'payment_method':method,'payment_state':state,'paid_amount':paid}
    baseline=views(runtime);pid=register(runtime,payload);m.v18.submit_v18(pid,payload,runtime.rich)
    assert runtime.db.snapshot().construction_cost==1100
    assert runtime.db.snapshot().cash_balance==cash
    approved=views(runtime);life=TransactionLifecycle(runtime.db)
    life.reject(pid);assert views(runtime)==baseline
    life.restore(pid);assert views(runtime)==approved


def test_contract_file_failure_rolls_back_database_and_source(runtime,monkeypatch):
    from contractor_store_stage18_7 import upsert_contract,get_contract
    upsert_contract({'contract_id':'C1','title':'آزمون','total_amount':2000,'payments':[]})
    payload={**case_payload(runtime,CASES[0]),'contract_id':'C1','cost_group':'پیمانکار'}
    pid=register(runtime,payload);m.v18.submit_v18(pid,payload,runtime.rich)
    baseline=views(runtime);contract=get_contract('C1');life=TransactionLifecycle(runtime.db)
    original=life._set_contracts
    def fail(key,wanted):
        if not wanted:raise OSError('injected file permission failure')
        return original(key,wanted)
    monkeypatch.setattr(life,'_set_contracts',fail)
    with pytest.raises(OSError):life.reject(pid)
    assert views(runtime)==baseline and get_contract('C1')==contract
    assert runtime.db.get_pending_item(pid)['status']=='APPROVED'


def test_failure_after_file_write_compensates_sql_and_json(runtime,monkeypatch):
    from contractor_store_stage18_7 import upsert_contract,get_contract
    upsert_contract({'contract_id':'C1','title':'آزمون','total_amount':2000,'payments':[]})
    payload={**case_payload(runtime,CASES[0]),'contract_id':'C1','cost_group':'پیمانکار'}
    pid=register(runtime,payload);m.v18.submit_v18(pid,payload,runtime.rich)
    baseline=views(runtime);contract=get_contract('C1');audit=runtime.db._audit
    def fail(con,entity,*args,**kwargs):
        if entity=='pending':raise ValueError('injected audit failure after file write')
        return audit(con,entity,*args,**kwargs)
    monkeypatch.setattr(runtime.db,'_audit',fail)
    with pytest.raises(ValueError):TransactionLifecycle(runtime.db).reject(pid)
    assert views(runtime)==baseline and get_contract('C1')==contract
    assert runtime.db.get_pending_item(pid)['status']=='APPROVED'


def test_rejected_analysis_message_audit_and_sync_follow_direct_lifecycle(runtime):
    import json
    payload=case_payload(runtime,CASES[5]);pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich)
    with runtime.db.tx() as con:con.execute("INSERT INTO receipt_analyses(analysis_id,pending_id,status,created_at,updated_at) VALUES('A',?,'APPROVED','2026-09-30','2026-09-30')",(pid,))
    life=TransactionLifecycle(runtime.db);life.reject(pid)
    with runtime.db.read() as con:
        assert con.execute("SELECT status FROM receipt_analyses WHERE pending_id=?",(pid,)).fetchone()[0]=='REJECTED'
        assert con.execute("SELECT state FROM telegram_messages WHERE chat_id=-989 AND message_id=1").fetchone()[0]=='REJECTED'
        assert con.execute("SELECT COUNT(*) FROM audit_log WHERE entity_id=? AND action='DELETE'",(pid,)).fetchone()[0]>0
        assert con.execute("SELECT COUNT(*) FROM sync_queue WHERE entity_id=? AND operation='DELETE'",(pid,)).fetchone()[0]>0
        assert con.execute("SELECT COUNT(*) FROM integration_events WHERE pending_id=? AND event_type='GUI_REJECTED'",(pid,)).fetchone()[0]==1
    life.restore(pid)
    with runtime.db.read() as con:assert con.execute("SELECT status FROM receipt_analyses WHERE pending_id=?",(pid,)).fetchone()[0]=='APPROVED'


def test_explicit_delete_preserves_audit_actor_and_restore_undo_source(runtime):
    payload=case_payload(runtime,CASES[5]);pid=register(runtime,payload);m.v18.submit_v18(pid,payload,runtime.rich)
    runtime.db.delete_financial_posting(pending_id=pid,source='TELEGRAM',actor_id='operator-7')
    with runtime.db.read() as con:
        row=con.execute("SELECT source,actor_id FROM audit_log WHERE entity_id=? AND action='DELETE' ORDER BY audit_id DESC LIMIT 1",(pid,)).fetchone()
        assert tuple(row)==('TELEGRAM','operator-7')
    TransactionLifecycle(runtime.db,source='GUI_UNDO').restore(pid)
    with runtime.db.read() as con:
        row=con.execute("SELECT source,actor_id FROM audit_log WHERE entity_id=? AND action='RESTORE' ORDER BY audit_id DESC LIMIT 1",(pid,)).fetchone()
        assert tuple(row)==('GUI_UNDO','GUI')


def test_legacy_financial_source_also_rejects_its_own_document(runtime):
    payload=case_payload(runtime,CASES[5]);pid=register(runtime,payload);m.v18.submit_v18(pid,payload,runtime.rich)
    document=runtime.rich.add_financial_document(pid,{'document_type':'DOCUMENT','event_date_shamsi':'1405/07/08','description':'سند قدیمی'},'مدرک',[])
    with runtime.db.tx() as con:con.execute('DELETE FROM transaction_lifecycle WHERE pending_id=?',(pid,))
    life=TransactionLifecycle(runtime.db);life.reject(pid)
    assert not runtime.rich.list_documents()
    assert runtime.db.snapshot().cash_balance==0
    life.restore(pid);assert runtime.rich.list_documents()[0]['document_id']==document


def test_new_external_document_link_refuses_partial_delete(runtime):
    payload=case_payload(runtime,CASES[0]);pid=register(runtime,payload);m.v18.submit_v18(pid,payload,runtime.rich)
    expense=runtime.db.get_financial_posting(pid)['expense_id']
    runtime.rich.add_financial_document(None,{'document_type':'DOCUMENT','description':'سند مستقل'},'مدرک',[('EXPENSE',expense)])
    baseline=views(runtime)
    with pytest.raises(LifecycleDecision):TransactionLifecycle(runtime.db).reject(pid)
    assert views(runtime)==baseline
    assert runtime.db.get_pending_item(pid)['status']=='APPROVED'
