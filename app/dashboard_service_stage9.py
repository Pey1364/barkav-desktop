from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from attachment_service import AttachmentService
from budget_service import BudgetService, norm_fa
from dashboard_service import DashboardService
from dashboard_read_model import DashboardServiceStage9 as SharedReadModel
from finance_db import FinanceDB, _now
from loan_service import LoanService
from project_service import ProjectService
from revenue_service import normalize_shamsi, shamsi_to_gregorian


class DashboardServiceStage9(DashboardService):
    def __init__(self, db: FinanceDB, base_dir: str | Path):
        super().__init__(db)
        self.base_dir=Path(base_dir)
        self.project=ProjectService(db,base_dir)
        self.attachments=AttachmentService(db,base_dir)
        self.loans=LoanService(db)
        self.budget=BudgetService(db,base_dir)

    def _posting_ids(self, con, *, transaction_id: str|None=None, expense_id: str|None=None) -> tuple[str|None,str|None]:
        if transaction_id:
            r=con.execute("SELECT pending_id,posting_id FROM financial_postings WHERE transaction_id=? AND COALESCE(status,'ACTIVE')='ACTIVE'",(transaction_id,)).fetchone()
            if r:return r['pending_id'],r['posting_id']
        if expense_id:
            r=con.execute("SELECT pending_id,posting_id FROM financial_postings WHERE expense_id=? AND COALESCE(status,'ACTIVE')='ACTIVE'",(expense_id,)).fetchone()
            if r:return r['pending_id'],r['posting_id']
        return None,None

    def list_transactions(self, *, direction: str|None=None, nonconstruction_only: bool=False, limit:int=3000)->list[dict[str,Any]]:
        where=["t.status='POSTED'","t.deleted_at IS NULL"]; args=[]
        if direction:
            where.append('t.direction=?'); args.append(direction.upper())
        if nonconstruction_only:
            where.append('t.expense_id IS NULL')
        sql=f'''SELECT t.*,l.lender_name loan_lender,s.buyer_name sale_buyer
                FROM transactions t LEFT JOIN loans l ON l.loan_id=t.loan_id LEFT JOIN sales s ON s.sale_id=t.sale_id
                WHERE {' AND '.join(where)} ORDER BY t.event_date DESC,t.created_at DESC LIMIT ?'''; args.append(int(limit))
        with self.db.read() as con:
            rows=con.execute(sql,args).fetchall(); out=[]
            for r in rows:
                d=dict(r); pending,posting=self._posting_ids(con,transaction_id=d['transaction_id'],expense_id=d.get('expense_id')); d['pending_id']=pending; d['posting_id']=posting
                ents=[('TRANSACTION',d['transaction_id'])]
                if d.get('expense_id'): ents.append(('EXPENSE',d['expense_id']))
                d['receipt_count']=self.attachments.count_for_entities(ents); out.append(d)
        return out

    def list_construction_expenses(self, limit:int=3000)->list[dict[str,Any]]:
        with self.db.read() as con:
            rows=con.execute('''SELECT e.*,
                COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.expense_id=e.expense_id AND p.status='COMPLETED'),0) paid_amount,
                (SELECT t.transaction_id FROM transactions t WHERE t.expense_id=e.expense_id AND t.status='POSTED' AND t.deleted_at IS NULL ORDER BY t.created_at LIMIT 1) transaction_id,
                (SELECT t.payer_name FROM transactions t WHERE t.expense_id=e.expense_id AND t.status='POSTED' AND t.deleted_at IS NULL ORDER BY t.created_at LIMIT 1) tx_payer,
                (SELECT t.receiver_name FROM transactions t WHERE t.expense_id=e.expense_id AND t.status='POSTED' AND t.deleted_at IS NULL ORDER BY t.created_at LIMIT 1) tx_receiver,
                a.name master_activity,p.name master_phase
                FROM expenses e LEFT JOIN construction_activities a ON a.activity_id=e.activity_id
                LEFT JOIN construction_phases p ON p.phase_id=a.phase_id
                WHERE e.deleted_at IS NULL AND e.status IN ('APPROVED','PARTIALLY_PAID','PAID')
                ORDER BY e.event_date DESC,e.created_at DESC LIMIT ?''',(int(limit),)).fetchall(); out=[]
            for r in rows:
                d=dict(r); pending,posting=self._posting_ids(con,expense_id=d['expense_id']); d['pending_id']=pending; d['posting_id']=posting
                d['payer_name_display']=d.get('payer_name') or d.get('tx_payer') or '-'; d['receiver_name_display']=d.get('vendor_name') or d.get('tx_receiver') or '-'
                d['phase_name']=d.get('master_phase') or d.get('construction_stage') or ''; d['activity_name_display']=d.get('master_activity') or d.get('activity_name') or d.get('category') or ''
                ents=[('EXPENSE',d['expense_id'])]
                if d.get('transaction_id'):ents.append(('TRANSACTION',d['transaction_id']))
                d['receipt_count']=self.attachments.count_for_entities(ents); out.append(d)
        return out

    def attach_receipt(self, entity_type:str, entity_id:str, path:str|Path)->dict[str,Any]:
        return self.attachments.add_local(entity_type=entity_type,entity_id=entity_id,source_path=path,document_type='RECEIPT')

    def receipt_list(self, entities:list[tuple[str,str]])->list[dict[str,Any]]:
        return self.attachments.list_for_entities(entities)

    def edit_manual_transaction(self, transaction_id:str, *, amount:int|None=None, shamsi_date:str|None=None, payer_name:str|None=None, receiver_name:str|None=None, description:str|None=None)->None:
        with self.db.read() as con:
            r=con.execute('SELECT * FROM transactions WHERE transaction_id=?',(transaction_id,)).fetchone()
        if not r: raise KeyError(transaction_id)
        before=dict(r); fields=[]; vals=[]
        if amount is not None:
            amount=int(amount)
            if amount<0:
                raise ValueError('مبلغ منفی مجاز نیست.')
            fields.append('amount=?'); vals.append(amount)
        if shamsi_date is not None:
            sh=normalize_shamsi(shamsi_date)
            if not sh:
                raise ValueError('تاریخ شمسی نامعتبر است.')
            fields += ['shamsi_date=?','event_date=?']; vals += [sh,shamsi_to_gregorian(sh)]
        for k,v in [('payer_name',payer_name),('receiver_name',receiver_name),('description',description)]:
            if v is not None: fields.append(f'{k}=?'); vals.append(str(v).strip())
        if not fields:return
        fields += ['updated_at=?','sync_status=?']; vals += [_now(),'PENDING',transaction_id]
        with self.db.tx() as con:
            con.execute(f"UPDATE transactions SET {','.join(fields)} WHERE transaction_id=?",vals)
            after=dict(con.execute('SELECT * FROM transactions WHERE transaction_id=?',(transaction_id,)).fetchone())
            con.execute('INSERT INTO audit_log(entity_type,entity_id,action,source,before_json,after_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?)',('TRANSACTION',transaction_id,'UPDATE','GUI',json.dumps(before,ensure_ascii=False),json.dumps(after,ensure_ascii=False),'GUI',_now()))
            con.execute('INSERT INTO sync_queue(entity_type,entity_id,operation,payload_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',('TRANSACTION',transaction_id,'UPDATE',None,'PENDING',_now(),_now()))

    def delete_manual_transaction(self, transaction_id:str, reason:str='حذف از GUI')->None:
        with self.db.tx() as con:
            r=con.execute('SELECT * FROM transactions WHERE transaction_id=?',(transaction_id,)).fetchone()
            if not r:raise KeyError(transaction_id)
            con.execute("UPDATE transactions SET status='VOIDED',deleted_at=?,updated_at=?,sync_status='PENDING' WHERE transaction_id=?",(_now(),_now(),transaction_id))
            con.execute('INSERT INTO audit_log(entity_type,entity_id,action,source,before_json,after_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?)',('TRANSACTION',transaction_id,'DELETE','GUI',json.dumps(dict(r),ensure_ascii=False),json.dumps({'reason':reason},ensure_ascii=False),'GUI',_now()))
            con.execute('INSERT INTO sync_queue(entity_type,entity_id,operation,payload_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',('TRANSACTION',transaction_id,'DELETE',None,'PENDING',_now(),_now()))

    def search(self, query:str='', scope:str='همه', *, date_from:str='', date_to:str='', amount_min:int|None=None, amount_max:int|None=None)->list[dict[str,Any]]:
        q=norm_fa(query); results=[]
        want=lambda name: scope in ('همه','') or scope==name
        if want('کلیه تراکنش‌ها') or want('ورودی‌ها') or want('خروجی‌ها') or scope=='همه':
            direction='IN' if scope=='ورودی‌ها' else ('OUT' if scope=='خروجی‌ها' else None)
            for r in self.list_transactions(direction=direction,nonconstruction_only=(scope=='خروجی‌ها')):
                if date_from and (r.get('shamsi_date') or '')<date_from:continue
                if date_to and (r.get('shamsi_date') or '')>date_to:continue
                amt=int(r.get('amount') or 0)
                if amount_min is not None and amt<amount_min:continue
                if amount_max is not None and amt>amount_max:continue
                hay=norm_fa(' '.join(str(r.get(k) or '') for k in ('category','payer_name','receiver_name','description','transaction_id','loan_lender','sale_buyer','shamsi_date')))
                if q and not all(tok in hay for tok in q.split()):continue
                results.append({'source':'تراکنش','id':r['transaction_id'],'date':r.get('shamsi_date') or '','amount':amt,'direction':r['direction'],'person':r.get('receiver_name') or r.get('payer_name') or '','description':r.get('description') or '','status':r.get('status') or '','receipt_count':r.get('receipt_count',0),'raw':r})
        if want('هزینه ساخت') or scope=='همه':
            for r in self.list_construction_expenses():
                if date_from and (r.get('shamsi_date') or '')<date_from:continue
                if date_to and (r.get('shamsi_date') or '')>date_to:continue
                amt=int(r.get('final_amount') or 0)
                if amount_min is not None and amt<amount_min:continue
                if amount_max is not None and amt>amount_max:continue
                hay=norm_fa(' '.join(str(r.get(k) or '') for k in ('phase_name','activity_name_display','payer_name_display','receiver_name_display','description','expense_id','shamsi_date')))
                if q and not all(tok in hay for tok in q.split()):continue
                results.append({'source':'هزینه ساخت','id':r['expense_id'],'date':r.get('shamsi_date') or '','amount':amt,'direction':'OUT','person':r.get('receiver_name_display') or '','description':f"{r.get('phase_name') or ''} / {r.get('activity_name_display') or ''} / {r.get('description') or ''}",'status':r.get('status') or '','receipt_count':r.get('receipt_count',0),'raw':r})
        if want('وام‌ها') or scope=='همه':
            for r in self.loans.list_loans():
                amt=int(r.get('principal_amount') or 0); hay=norm_fa(' '.join(str(r.get(k) or '') for k in ('lender_name','loan_type','contract_number','guarantors','collateral','description','loan_id')))
                if q and not all(tok in hay for tok in q.split()):continue
                results.append({'source':'وام','id':r['loan_id'],'date':r.get('received_date_shamsi') or '','amount':amt,'direction':'IN','person':r.get('lender_name') or '','description':r.get('description') or '','status':r.get('status') or '','receipt_count':0,'raw':r})
        if want('چک‌ها') or scope=='همه':
            for r in self.list_cheques(open_only=False):
                amt=int(r.get('amount') or 0); hay=norm_fa(' '.join(str(r.get(k) or '') for k in ('receiver_name','description','cheque_serial','issuer_bank','cheque_id','due_date_shamsi')))
                if q and not all(tok in hay for tok in q.split()):continue
                results.append({'source':'چک','id':r['cheque_id'],'date':r.get('due_date_shamsi') or '','amount':amt,'direction':'OUT','person':r.get('receiver_name') or '','description':r.get('description') or '','status':r.get('status') or '','receipt_count':0,'raw':r})
        if want('فروش و مطالبات') or scope=='همه':
            for r in self.list_sales_summary():
                amt=int(r.get('contract_amount') or 0); hay=norm_fa(' '.join(str(r.get(k) or '') for k in ('buyer_name','unit_number','project_name','contract_number','sale_id')))
                if q and not all(tok in hay for tok in q.split()):continue
                results.append({'source':'فروش','id':r['sale_id'],'date':r.get('contract_date_shamsi') or '','amount':amt,'direction':'IN','person':r.get('buyer_name') or '','description':f"واحد {r.get('unit_number') or ''}",'status':r.get('status') or '','receipt_count':0,'raw':r})
        return results

# The Tk runtime uses this legacy entry point; share audited mutations and
# the approved-record view with the standalone read model.
DashboardServiceStage9.list_registered_records = SharedReadModel.list_registered_records
DashboardServiceStage9.edit_manual_transaction = SharedReadModel.edit_manual_transaction
DashboardServiceStage9.delete_manual_transaction = SharedReadModel.delete_manual_transaction
DashboardServiceStage9._assert_transaction_is_standalone = SharedReadModel._assert_transaction_is_standalone
DashboardServiceStage9.delete_registered_note = SharedReadModel.delete_registered_note

DashboardServiceStage9._posting_ids = SharedReadModel._posting_ids
