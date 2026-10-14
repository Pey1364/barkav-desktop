"""Standalone dashboard read-model runtime."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from attachment_service import AttachmentService
from budget_service import BudgetService, norm_fa
from cheque_status187 import open_sql as _cheque_open_sql
from dashboard_service import DashboardService
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
        if transaction_id and con.execute("SELECT 1 FROM sqlite_master WHERE name='transaction_lifecycle'").fetchone():
            owner=con.execute("""SELECT l.pending_id FROM transaction_lifecycle l,
                json_each(l.effects_json) effect WHERE l.state='ACTIVE'
                AND json_extract(effect.value,'$.table')='transactions'
                AND json_extract(effect.value,'$.after.transaction_id')=? LIMIT 1""",(transaction_id,)).fetchone()
            if owner:return owner['pending_id'],None
        if expense_id:
            r=con.execute("SELECT pending_id,posting_id FROM financial_postings WHERE expense_id=? AND COALESCE(status,'ACTIVE')='ACTIVE'",(expense_id,)).fetchone()
            if r:return r['pending_id'],r['posting_id']
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='transaction_lifecycle'").fetchone():
                owner=con.execute("""SELECT l.pending_id FROM transaction_lifecycle l,
                    json_each(l.effects_json) effect WHERE l.state='ACTIVE'
                    AND json_extract(effect.value,'$.table')='expenses'
                    AND json_extract(effect.value,'$.after.expense_id')=? LIMIT 1""",(expense_id,)).fetchone()
                if owner:return owner['pending_id'],None
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

    def list_registered_records(self, *, limit: int = 3000) -> list[dict[str, Any]]:
        """All approved source records for display; financial totals still use the ledger."""
        rows = self.list_transactions(limit=limit)
        covered = {str(row.get('pending_id') or '') for row in rows}
        with self.db.read() as con:
            records = con.execute("""SELECT p.*,m.raw_text,m.linked_entity_type,m.linked_entity_id
                FROM pending_items p LEFT JOIN telegram_messages m
                ON m.chat_id=p.telegram_chat_id AND m.message_id=p.telegram_message_id
                WHERE p.status='APPROVED' AND COALESCE(m.state,'')!='DELETED'
                AND NOT EXISTS (SELECT 1 FROM financial_postings f
                    WHERE f.pending_id=p.pending_id AND f.status='DELETED')
                ORDER BY p.created_at DESC LIMIT ?""", (int(limit),)).fetchall()
            documents_exist = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='financial_documents'"
            ).fetchone() is not None
            for record in records:
                item = dict(record)
                pid = str(item['pending_id'])
                if pid in covered:
                    continue
                payload = json.loads(item.get('payload_json') or '{}')
                entity_type = str(item.get('linked_entity_type') or '').upper()
                entity_id = str(item.get('linked_entity_id') or '')
                document_id = None
                if documents_exist:
                    document = con.execute(
                        "SELECT document_id,status FROM financial_documents WHERE pending_id=? ORDER BY (status='ACTIVE') DESC,created_at DESC,rowid DESC LIMIT 1",
                        (pid,),
                    ).fetchone()
                    if document is not None:
                        if document['status'] != 'ACTIVE':
                            continue
                        document_id = document['document_id']
                posting = con.execute(
                    "SELECT * FROM financial_postings WHERE pending_id=? AND COALESCE(status,'ACTIVE')='ACTIVE'", (pid,),
                ).fetchone()
                linked = dict(posting) if posting else {}
                expense_id = linked.get('expense_id') or (entity_id if entity_type == 'EXPENSE' else None)
                cheque_id = linked.get('cheque_id') or (entity_id if entity_type == 'CHEQUE' else None)
                if cheque_id:
                    cheque = con.execute('SELECT status FROM cheques WHERE cheque_id=?', (cheque_id,)).fetchone()
                    if cheque is not None and cheque['status'] == 'CANCELLED':
                        continue
                detected = str(payload.get('detected_type') or item.get('detected_type') or '').upper()
                rows.append({
                    **item, 'payload': payload, 'transaction_id': None,
                    'expense_id': expense_id, 'cheque_id': cheque_id,
                    'document_id': document_id, 'posting_id': linked.get('posting_id'),
                    'direction': 'IN' if detected == 'INCOME' else ('OUT' if detected in {'EXPENSE','OUTFLOW'} else ''),
                    'amount': int(payload.get('amount') or payload.get('final_amount') or 0),
                    'shamsi_date': payload.get('event_date_shamsi') or '',
                    'description': payload.get('description') or item.get('raw_text') or '',
                    'payer_name': payload.get('payer_name') or '',
                    'receiver_name': payload.get('receiver_name') or '',
                    'receipt_count': self.attachments.count_for_entities(
                        [('PENDING', pid)] + ([('EXPENSE', expense_id)] if expense_id else [])),
                    '_registered_review187': True, '_sum_amount': 0,
                })
        rows.sort(key=lambda row: (str(row.get('shamsi_date') or ''), str(row.get('created_at') or '')), reverse=True)
        return rows[:int(limit)]

    def delete_registered_note(self, pending_id: str) -> None:
        item=self.db.get_pending_item(pending_id)
        if not item:raise KeyError(pending_id)
        if self.db.get_financial_posting(pending_id):
            raise ValueError('ثبت مالی باید از مسیر Posting حذف شود.')
        if str(item['payload'].get('detected_type') or item.get('detected_type')).upper()!='INFO':
            raise ValueError('این مسیر فقط برای یادداشت غیرمالی است.')
        from transaction_lifecycle import TransactionLifecycle
        TransactionLifecycle(self.db).reject(pending_id)

    def _delete_registered_note_legacy(self, pending_id: str) -> None:
        """Audit-safe deletion for approved informational records without a posting."""
        with self.db.tx() as con:
            row = con.execute('SELECT * FROM pending_items WHERE pending_id=?', (pending_id,)).fetchone()
            if row is None:
                raise KeyError(pending_id)
            if con.execute('SELECT 1 FROM financial_postings WHERE pending_id=?', (pending_id,)).fetchone():
                raise ValueError('ثبت مالی باید از مسیر Posting حذف شود.')
            payload = json.loads(row['payload_json'] or '{}')
            if str(payload.get('detected_type') or row['detected_type']).upper() != 'INFO':
                raise ValueError('این مسیر فقط برای یادداشت غیرمالی است.')
            before = dict(row)
            now = _now()
            con.execute("UPDATE pending_items SET status='REJECTED',updated_at=? WHERE pending_id=?", (now,pending_id))
            con.execute("UPDATE telegram_messages SET state='DELETED',updated_at=? WHERE chat_id=? AND message_id=?",
                        (now,row['telegram_chat_id'],row['telegram_message_id']))
            after = dict(con.execute('SELECT * FROM pending_items WHERE pending_id=?', (pending_id,)).fetchone())
            self.db._audit(con,'pending',pending_id,'DELETE','GUI',before=before,after=after,actor_id='GUI')
            self.db._enqueue_sync(con,'pending',pending_id,'DELETE',after)

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
        fields=[]; vals=[]
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
        with self.db.tx() as con:
            current=con.execute('SELECT * FROM transactions WHERE transaction_id=?',(transaction_id,)).fetchone()
            if not current: raise KeyError(transaction_id)
            before=dict(current)
            self._assert_transaction_is_standalone(before, con=con, operation='ویرایش')
            fields += ['updated_at=?','sync_status=?']; vals += [_now(),'PENDING',transaction_id]
            con.execute(f"UPDATE transactions SET {','.join(fields)} WHERE transaction_id=?",vals)
            after=dict(con.execute('SELECT * FROM transactions WHERE transaction_id=?',(transaction_id,)).fetchone())
            con.execute('INSERT INTO audit_log(entity_type,entity_id,action,source,before_json,after_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?)',('TRANSACTION',transaction_id,'UPDATE','GUI',json.dumps(before,ensure_ascii=False),json.dumps(after,ensure_ascii=False),'GUI',_now()))
            con.execute('INSERT INTO sync_queue(entity_type,entity_id,operation,payload_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',('TRANSACTION',transaction_id,'UPDATE',None,'PENDING',_now(),_now()))

    def delete_manual_transaction(self, transaction_id:str, reason:str='حذف از GUI')->None:
        with self.db.tx() as con:
            r=con.execute('SELECT * FROM transactions WHERE transaction_id=?',(transaction_id,)).fetchone()
            if not r:raise KeyError(transaction_id)
            self._assert_transaction_is_standalone(dict(r), con=con, operation='حذف')
            con.execute("UPDATE transactions SET status='VOIDED',deleted_at=?,updated_at=?,sync_status='PENDING' WHERE transaction_id=?",(_now(),_now(),transaction_id))
            con.execute('INSERT INTO audit_log(entity_type,entity_id,action,source,before_json,after_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?)',('TRANSACTION',transaction_id,'DELETE','GUI',json.dumps(dict(r),ensure_ascii=False),json.dumps({'reason':reason},ensure_ascii=False),'GUI',_now()))
            con.execute('INSERT INTO sync_queue(entity_type,entity_id,operation,payload_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',('TRANSACTION',transaction_id,'DELETE',None,'PENDING',_now(),_now()))

    def _assert_transaction_is_standalone(self, transaction:dict[str,Any], *, con=None, operation:str)->None:
        """Keep linked finance records on their own audited edit/delete path."""
        direct_links = {
            key: str(transaction.get(key) or '').strip()
            for key in ('expense_id', 'sale_id', 'loan_id')
            if str(transaction.get(key) or '').strip()
        }
        transaction_id = str(transaction.get('transaction_id') or '').strip()
        if con is None:
            with self.db.read() as reader:
                return self._assert_transaction_is_standalone(
                    transaction, con=reader, operation=operation,
                )
        linked = []
        if direct_links:
            linked.extend(f"{key[:-3].upper()}:{value}"
                          for key, value in direct_links.items())
        if transaction_id:
            checks = (
                ('چک', 'SELECT cheque_id FROM cheques WHERE cash_transaction_id=? LIMIT 1'),
                ('پرداخت', 'SELECT payment_id FROM payments WHERE transaction_id=? LIMIT 1'),
                ('وام', 'SELECT loan_id FROM loans WHERE receive_transaction_id=? LIMIT 1'),
                ('Posting', "SELECT pending_id FROM financial_postings WHERE transaction_id=? AND COALESCE(status,'ACTIVE')='ACTIVE' LIMIT 1"),
            )
            for label, sql in checks:
                row = con.execute(sql, (transaction_id,)).fetchone()
                if row:
                    linked.append(f'{label}:{row[0]}')
        if linked:
            raise ValueError(
                f"تراکنش به رکوردهای مرتبط وصل است ({'، '.join(linked)}); "
                f"{operation} مستقیم مجاز نیست و باید از مسیر همان رکورد یا Posting انجام شود."
            )

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


from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from finance_db import FinanceDB
from revenue_service import gregorian_to_shamsi, shamsi_to_gregorian


@dataclass(frozen=True)
class ManagerSummary:
    signed_days: int
    signed_average: int
    toman_month: int
    manager_fee: int
    withdrawals_signed: int
    balance: int


class DashboardServiceStage12(DashboardServiceStage9):
    """Stage 12 dashboard/read-model helpers.

    All values are derived from SQLite; no aggregate is persisted here.
    The 30-day window is inclusive of today and day +30.
    """

    def __init__(self, db: FinanceDB, base_dir: str | Path):
        super().__init__(db, base_dir)

    def financial_flow_totals(self) -> dict[str, int]:
        """Dashboard flow totals.

        ``total_out`` intentionally mirrors the «خروجی‌ها» sub-tab exactly:
        posted OUT transactions that are not construction-expense settlements
        (``expense_id IS NULL``). Construction payments remain visible in the
        construction-cost KPI and in the all-transactions ledger.
        """
        with self.db.read() as con:
            row=con.execute("""SELECT
                COALESCE(SUM(CASE WHEN direction='IN' THEN amount ELSE 0 END),0) total_in,
                COALESCE(SUM(CASE WHEN direction='OUT' AND expense_id IS NULL THEN amount ELSE 0 END),0) total_out
                FROM transactions WHERE status='POSTED' AND deleted_at IS NULL""").fetchone()
        return {'total_in':int(row['total_in'] or 0),'total_out':int(row['total_out'] or 0)}

    def cheque_total_summary(self) -> dict[str, int]:
        """Historical cheque totals for the dashboard.

        Cancelled cheques are excluded; cashed/returned/open cheques are kept so
        the number represents the total cheque volume recorded by the project.
        """
        with self.db.read() as con:
            row=con.execute("""SELECT COUNT(*) AS count, COALESCE(SUM(amount),0) AS amount
                FROM cheques WHERE status!='CANCELLED'""").fetchone()
        return {'count':int(row['count'] or 0),'amount':int(row['amount'] or 0)}

    def manager_summary_shamsi(self, start_shamsi: str, end_shamsi: str) -> ManagerSummary:
        # Use the exposure engine even when there has never been a withdrawal.
        # The fee accrual itself creates positive manager exposure.
        start=shamsi_to_gregorian(start_shamsi)
        end=shamsi_to_gregorian(end_shamsi)
        exp=self.db.manager_exposure(start,end)
        fee=self.db.manager_fee_accrued()
        withdrawals=self.db.manager_withdrawals()
        active=int(exp.creditor_days)+int(exp.debtor_days)
        signed_days=int(exp.creditor_days)-int(exp.debtor_days)
        signed_average=round(int(exp.net_toman_days)/active) if active else 0
        toman_month=round(int(exp.net_toman_days)/30)
        return ManagerSummary(
            signed_days=signed_days,
            signed_average=signed_average,
            toman_month=toman_month,
            manager_fee=int(fee),
            withdrawals_signed=-int(withdrawals),
            balance=int(fee)-int(withdrawals),
        )

    @staticmethod
    def _window(days: int=30) -> tuple[date,date]:
        today=date.today(); return today,today+timedelta(days=max(0,int(days)))

    def upcoming_cheques(self, days: int=30) -> list[dict[str,Any]]:
        start,end=self._window(days)
        with self.db.read() as con:
            rows=con.execute(f"""SELECT c.*,e.description expense_description
                FROM cheques c LEFT JOIN expenses e ON e.expense_id=c.expense_id
                WHERE {_cheque_open_sql('c')}
                  AND c.due_date>=? AND c.due_date<=?
                ORDER BY c.due_date,c.amount DESC""",(start.isoformat(),end.isoformat())).fetchall()
        out=[]
        for r in rows:
            d=dict(r); due=date.fromisoformat(d['due_date']); d['days_to_due']=(due-start).days
            d['_sum_amount']=int(d.get('amount') or 0); out.append(d)
        return out

    def cheque_30d_summary(self, days: int=30) -> dict[str,Any]:
        rows=self.upcoming_cheques(days); amount=sum(int(r.get('amount') or 0) for r in rows); cash=self.db.cash_balance()
        return {'rows':rows,'count':len(rows),'amount':amount,'cash':cash,'surplus':cash-amount}

    def upcoming_buyer_installments(self, days: int=30) -> list[dict[str,Any]]:
        self.revenue.refresh_installment_statuses()
        start,end=self._window(days)
        with self.db.read() as con:
            rows=con.execute("""SELECT i.*,s.buyer_name,s.buyer_phone,s.sale_id,u.unit_number,u.display_unit_id
                FROM installments i JOIN sales s ON s.sale_id=i.sale_id JOIN units u ON u.unit_id=s.unit_id
                WHERE s.status!='CANCELLED' AND i.status!='CANCELLED' AND i.paid_amount<i.amount
                  AND i.due_date>=? AND i.due_date<=?
                ORDER BY i.due_date,s.buyer_name""",(start.isoformat(),end.isoformat())).fetchall()
        out=[]
        for r in rows:
            d=dict(r); d['outstanding']=max(0,int(d.get('amount') or 0)-int(d.get('paid_amount') or 0)); d['days_to_due']=(date.fromisoformat(d['due_date'])-start).days; d['_sum_amount']=d['outstanding']; out.append(d)
        return out

    def overdue_buyer_installments(self) -> list[dict[str,Any]]:
        self.revenue.refresh_installment_statuses()
        today=date.today()
        with self.db.read() as con:
            rows=con.execute("""SELECT i.*,s.buyer_name,s.buyer_phone,s.sale_id,u.unit_number,u.display_unit_id
                FROM installments i JOIN sales s ON s.sale_id=i.sale_id JOIN units u ON u.unit_id=s.unit_id
                WHERE s.status!='CANCELLED' AND i.status!='CANCELLED' AND i.paid_amount<i.amount AND i.due_date<?
                ORDER BY i.due_date,s.buyer_name""",(today.isoformat(),)).fetchall()
        out=[]
        for r in rows:
            d=dict(r); d['outstanding']=max(0,int(d.get('amount') or 0)-int(d.get('paid_amount') or 0)); d['days_overdue']=(today-date.fromisoformat(d['due_date'])).days; d['_sum_amount']=d['outstanding']; out.append(d)
        return out

    def sales_30d_summary(self, days: int=30) -> dict[str,Any]:
        base=self.revenue.buyer_dashboard(); upcoming=self.upcoming_buyer_installments(days); overdue=self.overdue_buyer_installments()
        return {
            'contract_sales':int(base['contract_sales']),
            'cash_received':int(base['cash_received']),
            'receivable':int(base['receivable']),
            'upcoming_amount':sum(int(r['outstanding']) for r in upcoming),
            'overdue_amount':sum(int(r['outstanding']) for r in overdue),
            'upcoming_rows':upcoming,
            'overdue_rows':overdue,
        }

    def upcoming_loan_installments(self, days: int=30) -> list[dict[str,Any]]:
        # Refresh statuses through list_loans before querying.
        self.loans.list_loans()
        start,end=self._window(days)
        with self.db.read() as con:
            rows=con.execute("""SELECT li.*,l.lender_name,l.contract_number,l.loan_type,l.description AS loan_title
                FROM loan_installments li JOIN loans l ON l.loan_id=li.loan_id
                WHERE l.status='ACTIVE' AND li.status!='CANCELLED' AND li.paid_amount<li.amount
                  AND li.due_date>=? AND li.due_date<=?
                ORDER BY li.due_date,l.lender_name,li.installment_number""",(start.isoformat(),end.isoformat())).fetchall()
        out=[]
        for r in rows:
            d=dict(r); d['outstanding']=max(0,int(d.get('amount') or 0)-int(d.get('paid_amount') or 0)); d['days_to_due']=(date.fromisoformat(d['due_date'])-start).days; d['_sum_amount']=d['outstanding']; out.append(d)
        return out

    def loans_30d_summary(self, days: int=30) -> dict[str,Any]:
        totals=self.loans.loan_totals(); rows=self.upcoming_loan_installments(days)
        return {**totals,'upcoming_amount':sum(int(r['outstanding']) for r in rows),'upcoming_rows':rows}

    def liquidity_30d_summary(self, days: int=30) -> dict[str,int]:
        cash=self.db.cash_balance(); ch=self.cheque_30d_summary(days); sales=self.sales_30d_summary(days); loans=self.loans_30d_summary(days)
        obligations=int(ch['amount'])+int(loans['upcoming_amount'])
        expected=int(sales['upcoming_amount'])
        return {
            'cash':int(cash),
            'cheques':int(ch['amount']),
            'loan_installments':int(loans['upcoming_amount']),
            'obligations':obligations,
            'expected_inflows':expected,
            'conservative_balance':int(cash)-obligations,
            'projected_balance':int(cash)+expected-obligations,
        }
