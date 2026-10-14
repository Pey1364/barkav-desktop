"""Persistent approval/rejection/restoration of one source record and its effects."""
from __future__ import annotations
import json
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from datetime import datetime
from finance_db import _now

TABLES=('transactions','expenses','payments','cheques','loans','loan_installments',
        'received_payments','payment_allocations','sales','installments','units',
        'receivables','reminders','financial_postings','financial_documents',
        'financial_document_links','expense_payment_links','attachments')
VOLATILE={'updated_at','sync_status'}
CANCEL={'transactions':{'status':'VOIDED','deleted_at':True},
        'expenses':{'status':'CANCELLED','deleted_at':True},
        'financial_postings':{'status':'DELETED','deleted_at':True},
        'financial_documents':{'status':'DELETED'},
        **{t:{'status':'CANCELLED'} for t in ('payments','cheques','loans','loan_installments',
            'received_payments','sales','installments','receivables','reminders')}}
ASSOCIATIONS={'payment_allocations','financial_document_links','expense_payment_links'}
ENTITY={table:table[:-1] for table in TABLES}
ENTITY.update({'received_payments':'received_payment','loan_installments':'loan_installment','financial_postings':'financial_posting','financial_documents':'financial_document','financial_document_links':'financial_document_link','expense_payment_links':'expense_payment_link','payment_allocations':'payment_allocation'})

RESOLVE_OPERATION='تعیین تکلیف چک'
# Written on a record that goes back to review, read by its next approval: the cheque rows its earlier
# approval made, with the state each had, so the cheque keeps its id (one cheque is one row for good).
CHEQUE_HINT='_cheque_hint187'
# A cheque as its issue made it: everything a resolution record changes is back at its starting value.
ISSUE_TIME_STATE={'status':'ISSUED','settlement_mode':'NORMAL','return_disposition':'عدم دریافت و عدم عودت سیستمی',
                  'return_account_holder':'','void_reason':'','cashed_date':None,'cashed_date_shamsi':None}

def is_new_resolution(payload):
    """A resolution made by the current flow: it posts nothing, whatever snapshot an older approval left."""
    return is_resolution_payload(payload) and str((payload or {}).get('payment_state') or '')=='CHEQUE_RESOLUTION'

def is_resolution_payload(payload):
    """A «تعیین تکلیف چک» record: it changes an existing cheque's status, it posts no money of its own."""
    payload=payload or {}
    return (str(payload.get('cheque_operation187') or '')==RESOLVE_OPERATION
            and str(payload.get('selected_cheque_id187') or '').strip()!='')

class LifecycleDecision(ValueError):
    """An ambiguous/shared record needs an accounting decision, with no mutation."""

def _json(value): return json.dumps(value,ensure_ascii=False)
def _stable(row): return None if row is None else {k:v for k,v in row.items() if k not in VOLATILE}

class TransactionLifecycle:
    def __init__(self,db,*,source='GUI_LIFECYCLE',actor_id='GUI'):
        self.db=db
        self.source=source
        self.actor_id=actor_id
        self._schema()

    def _schema(self):
        with self.db.read() as con:
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='transaction_lifecycle'").fetchone():
                return
            if self.db._session_state().get('writer') is not None:
                raise RuntimeError('Initialize lifecycle before entering an approval transaction')
            folder=Path(self.db.db_path).parent/'.barkav-migration-backups'
            folder.mkdir(parents=True,exist_ok=True)
            backup=folder/(Path(self.db.db_path).name+'.'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.'+uuid.uuid4().hex[:8]+'.pre-lifecycle.sqlite3')
            with closing(sqlite3.connect(backup)) as destination:
                con.backup(destination)
                if destination.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise sqlite3.DatabaseError('lifecycle backup integrity check failed')
        with self.db.tx() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS transaction_lifecycle(
                pending_id TEXT PRIMARY KEY REFERENCES pending_items(pending_id),
                state TEXT NOT NULL CHECK(state IN ('ACTIVE','REJECTED','PURGED')),
                effects_json TEXT NOT NULL, rejected_json TEXT NOT NULL DEFAULT '[]',
                contract_json TEXT NOT NULL DEFAULT '[]', payload_json TEXT NOT NULL,
                message_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL)''')

    def get(self,pid,con=None):
        if con is None:
            with self.db.read() as reader: return self.get(pid,reader)
        row=con.execute('SELECT * FROM transaction_lifecycle WHERE pending_id=?',(pid,)).fetchone()
        return dict(row) if row else None

    def _snapshot(self,con):
        tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        out={}
        for table in TABLES:
            if table not in tables: continue
            columns=con.execute(f'PRAGMA table_info("{table}")').fetchall()
            pk=[name for _,name in sorted((r[5],r[1]) for r in columns if r[5])]
            if not pk: continue
            rows={tuple(row[k] for k in pk):dict(row) for row in con.execute(f'SELECT * FROM "{table}"')}
            out[table]=(pk,rows)
        return out

    def _diff(self,before,after):
        result=[]
        for table,(pk,rows) in after.items():
            prior=before.get(table,(pk,{}))[1]
            for key in prior.keys()|rows.keys():
                old,new=prior.get(key),rows.get(key)
                if _stable(old)!=_stable(new):
                    result.append({'table':table,'pk':pk,'key':list(key),'before':old,'after':new})
        return result

    def _load_contracts(self):
        path=Path(self.db.db_path).parent/'contractor_contracts_18_7.json'
        if not path.exists(): return path, {'contracts':[]}
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data,dict) or not isinstance(data.get('contracts'),list):
            raise LifecycleDecision('فایل قراردادهای پروژه قابل خواندن نیست؛ تعیین تکلیف لازم است.')
        return path,data

    def _contracts(self,pid):
        _,data=self._load_contracts()
        return [{'contract_id':c['contract_id'],'payment':p}
                for c in data['contracts'] for p in c.get('payments') or []
                if str(p.get('pending_id') or '')==str(pid)]

    def _set_contracts(self,pid,wanted):
        path,data=self._load_contracts();contracts=data['contracts']
        ids={str(c['contract_id']) for c in contracts}
        if any(str(item['contract_id']) not in ids for item in wanted):
            raise LifecycleDecision('قرارداد رسید حذف شده است؛ پیش از بازگردانی، قرارداد باید تعیین تکلیف شود.')
        changed=False
        for contract in contracts:
            previous=list(contract.get('payments') or [])
            payments=[p for p in previous if str(p.get('pending_id') or '')!=str(pid)]
            payments += [item['payment'] for item in wanted if str(item['contract_id'])==str(contract['contract_id'])]
            if payments!=previous:
                contract['payments']=payments;changed=True
        if changed:
            temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
            try:
                temporary.write_text(_json(data),encoding='utf-8')
                temporary.replace(path)
            finally:
                if temporary.exists(): temporary.unlink()

    def _message(self,pid,con):
        row=con.execute('''SELECT m.* FROM telegram_messages m JOIN pending_items p
            ON m.chat_id=p.telegram_chat_id AND m.message_id=p.telegram_message_id
            WHERE p.pending_id=?''',(pid,)).fetchone()
        return dict(row) if row else {}

    def _persist(self,pid,state,effects,payload,message,contracts,rejected=None,con=None):
        con.execute('''INSERT INTO transaction_lifecycle(pending_id,state,effects_json,
            rejected_json,contract_json,payload_json,message_json,updated_at)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(pending_id) DO UPDATE SET
            state=excluded.state,effects_json=excluded.effects_json,
            rejected_json=excluded.rejected_json,contract_json=excluded.contract_json,
            payload_json=excluded.payload_json,message_json=excluded.message_json,updated_at=excluded.updated_at''',
            (pid,state,_json(effects),_json(rejected or []),_json(contracts),_json(payload),_json(message),_now()))

    def _cheque_hint(self,effects):
        """The cheque rows these effects created, oldest first, each with the state it has now."""
        out=[]
        for row in effects or ():
            if row['table']!='cheques' or row.get('before') is not None or not row.get('after'): continue
            cid=str(row['key'][0])
            try: cheque=self.db.get_cheque(cid); state=self.db.cheque_state(cid)
            except KeyError: continue
            if cheque: out.append({'cheque_id':cid,'state':state,'created_at':str(cheque.get('created_at') or '')})
        return sorted(out,key=lambda token:(token['created_at'],token['cheque_id']))

    def _release_resolved_cheques(self,effects,con):
        """A cheque a resolution record has changed goes back to the state its issue gave it, so that
        the issue can be taken back or posted again without being refused for a change it is not
        responsible for. Returns {cheque id: the state it had}, to be put on again afterwards."""
        released={}
        for row in effects or ():
            if row['table']!='cheques' or row.get('before') is not None or not row.get('after'): continue
            cid=str(row['key'][0])
            try: current=self.db.cheque_state(cid)
            except KeyError: continue
            wanted={column:row['after'].get(column) for column in self.db.CHEQUE_STATE_COLUMNS}
            if current!=wanted:
                released[cid]=current
                self.db._restore_cheque_state(con,cid,wanted,source=self.source,actor_id=self.actor_id)
        return released

    def issue_time_cheques(self,effects,con):
        """What a record's snapshot says of a cheque is the cheque as the issue made it. What a
        resolution record made of it (the status, the return details) belongs to that record, which
        undoes it when it is taken back; the issue's own snapshot must not carry it."""
        ids={str(row['key'][0]) for row in effects if row['table']=='cheques' and row.get('after')}
        if not ids: return effects
        starts={}
        for row in con.execute("SELECT payload_json FROM pending_items WHERE status IN ('APPROVED','EDIT_PENDING') AND payload_json LIKE '%selected_cheque_id187%' ORDER BY created_at,rowid"):
            payload=json.loads(row['payload_json'] or '{}')
            cid=str(payload.get('selected_cheque_id187') or '')
            if is_resolution_payload(payload) and cid in ids and cid not in starts:
                # the state the cheque had when its first resolution found it is the state its issue gave it
                starts[cid]=payload.get('_resolution_before187') or ISSUE_TIME_STATE
        if not starts: return effects
        return [({**row,'after':{**row['after'],**{column:starts[str(row['key'][0])].get(column) for column in ISSUE_TIME_STATE}}}
                 if row['table']=='cheques' and row.get('after') and str(row['key'][0]) in starts else row)
                for row in effects]

    def run(self,pid,callback,*,replace=False):
        """Capture all effects of the actual runtime approval, including special types."""
        if self.db._session_state().get('lifecycle_capture'):
            return callback()
        prior_contracts=self._contracts(pid)
        try:
            with self.db.atomic() as con:
                item=self.db.get_pending_item(pid)
                if not item: raise KeyError(pid)
                record=self.get(pid,con)
                if record and record['state']!='ACTIVE':
                    raise ValueError('ردیف ردشده فقط با «بازگردانی» قابل احیاست؛ حذف کامل قابل بازگردانی نیست.')
                existing=json.loads(record['effects_json']) if record else (self._legacy(pid,con) if item['status']=='APPROVED' else [])
                hint=list((item['payload'] or {}).get(CHEQUE_HINT) or [])
                reversed_effects=None
                released={}
                if existing:
                    tokens=self._cheque_hint(existing)
                    released=self._release_resolved_cheques(existing,con)
                # Special approvals do not have a financial_postings row. Reverse
                # their old effects before replaying edited values to avoid duplicates.
                if existing and (replace or not self.db.get_financial_posting(pid)):
                    hint=tokens or hint
                    self._reverse(existing,con)
                    self._set_contracts(pid,[])
                    con.execute("UPDATE pending_items SET status='PENDING_REVIEW' WHERE pending_id=?",(pid,))
                    reversed_effects=existing
                    existing=None
                before=self._snapshot(con)
                state=self.db._session_state();state['lifecycle_capture']=True
                # The cheques this record made before are posted again on the same rows, as long as those are
                # rows taken back: a live cheque (a copy of the record carried the token) is never written over.
                def taken_back(token):
                    row=self.db.get_cheque(str(token['cheque_id']))
                    return row is None or (row['status']=='CANCELLED' and row.get('settlement_mode')!='VOIDED')
                state['revive_cheques']=[dict(token) for token in hint if taken_back(token)];state['revived_cheques']=[]
                try: result=callback()
                finally:
                    state['lifecycle_capture']=False
                    revived=state.pop('revived_cheques',[]);state.pop('revive_cheques',None)
                effects=self._diff(before,self._snapshot(con))
                if reversed_effects:
                    # A re-posted cheque is still a row this record created: rejecting the record takes it back.
                    first={(row['table'],tuple(row['key'])):row['before'] for row in reversed_effects}
                    effects=[{**row,'before':None} if row['table']=='cheques' and first.get((row['table'],tuple(row['key'])),1) is None
                             else row for row in effects]
                if existing:
                    merged={(r['table'],tuple(r['key'])):r for r in existing}
                    for row in effects:
                        key=(row['table'],tuple(row['key']))
                        if key in merged: row={**row,'before':merged[key]['before']}
                        merged[key]=row
                    effects=list(merged.values())
                effects=self.issue_time_cheques(effects,con)
                # The posting made each cheque as the issue has it; what a resolution record had made of
                # it is put back (the edit's own «وضعیت ثبت چک» stays).
                put_back={token['cheque_id']:token['state'] for token in revived}
                if reversed_effects is None:
                    # the cheques stayed as they were (an in-place revision); after a replay only the ones
                    # posted again have a state to get back, a cheque the new approval left out stays taken back
                    for cid,state_before in released.items():
                        put_back.setdefault(cid,state_before)
                for cid,state_before in put_back.items():
                    self.db._restore_cheque_state(con,cid,state_before,source=self.source,
                                                  actor_id=self.actor_id,keep_registration=True)
                if self.db.get_pending_item(pid)['status']!='APPROVED':
                    raise ValueError('تأیید کامل نشد؛ همه آثار ثبت برگشت داده شد.')
                payload=dict(self.db.get_pending_item(pid)['payload'] or {})
                if CHEQUE_HINT in payload:
                    payload.pop(CHEQUE_HINT)
                    self.db.update_pending(pid,payload=payload)
                self._persist(pid,'ACTIVE',effects,payload,
                    self._message(pid,con),self._contracts(pid),con=con)
            return result
        except Exception as exc:
            self._set_contracts(pid,prior_contracts)
            if isinstance(exc,LifecycleDecision):self.flag_decision(pid,'APPROVE',exc)
            raise

    def _fetch(self,row,con):
        if row.get('table') not in TABLES:
            raise LifecycleDecision('جدول اثر ثبت ناشناخته است؛ تعیین تکلیف لازم است.')
        expected=[name for _,name in sorted((r['pk'],r['name']) for r in con.execute(f'PRAGMA table_info("{row["table"]}")') if r['pk'])]
        if row.get('pk')!=expected or len(row.get('key',[]))!=len(expected):
            raise LifecycleDecision('شناسه اثر ثبت معتبر نیست؛ تعیین تکلیف لازم است.')
        where=' AND '.join(f'"{k}"=?' for k in row['pk'])
        result=con.execute(f'SELECT * FROM "{row["table"]}" WHERE {where}',row['key']).fetchone()
        return dict(result) if result else None

    def _fields(self,row,target):
        other=row['after' if target=='before' else 'before']
        desired=row[target]
        # «وضعیت ثبت چک» is information a resolution record may change (and the cheque tab); it moves no money,
        # so a change of it is no change an issue's snapshot has to answer for
        ignored=VOLATILE|({'registration_state'} if row['table']=='cheques' else set())
        if desired is None or other is None:
            return set(desired or other or {})-set(row['pk'])-ignored
        return {k for k in desired if k not in row['pk'] and k not in ignored and desired[k]!=other.get(k)}

    def _write(self,row,target,con):
        table=row['table'];current=self._fetch(row,con)
        wanted=row[target]
        if wanted is None and target=='before':
            if table in ASSOCIATIONS:
                con.execute(f'DELETE FROM "{table}" WHERE '+ ' AND '.join(f'"{k}"=?' for k in row['pk']),row['key'])
                self.db._audit(con,ENTITY[table],':'.join(map(str,row['key'])),'REJECT',self.source,before=current,after=None,actor_id=self.actor_id)
                self.db._enqueue_sync(con,ENTITY[table],':'.join(map(str,row['key'])),'DELETE',None)
                return
            if table not in CANCEL:
                raise LifecycleDecision(f'اثر ثبت در {table} مسیر لغو مشخص ندارد؛ تعیین تکلیف لازم است.')
            wanted={**(current or row['after']),**CANCEL[table]}
            if wanted.get('deleted_at') is True: wanted['deleted_at']=_now()
            fields=set(CANCEL[table])
        elif wanted is None:
            raise LifecycleDecision('حذف کامل یک موجودیت وابسته قابل بازگردانی خودکار نیست.')
        else: fields=self._fields(row,target)
        if current is None:
            if wanted is None: return
            columns=list(wanted)
            con.execute(f'INSERT INTO "{table}" ('+','.join(f'"{k}"' for k in columns)+') VALUES('+','.join('?' for _ in columns)+')',[wanted[k] for k in columns])
        elif fields:
            values={k:wanted[k] for k in fields}
            if 'updated_at' in current: values['updated_at']=_now()
            if 'sync_status' in current: values['sync_status']='PENDING'
            con.execute(f'UPDATE "{table}" SET '+','.join(f'"{k}"=?' for k in values)+' WHERE '+
                        ' AND '.join(f'"{k}"=?' for k in row['pk']),[*values.values(),*row['key']])
        after=self._fetch(row,con)
        identifier=':'.join(map(str,row['key']))
        self.db._audit(con,ENTITY[table],identifier,'RESTORE' if target=='after' else 'REJECT',
                       self.source,before=current,after=after,actor_id=self.actor_id)
        operation='DELETE' if after is None or str(after.get('status') or '') in ('CANCELLED','VOIDED','DELETED') else 'UPDATE'
        self.db._enqueue_sync(con,ENTITY[table],identifier,operation,after)

    def _check(self,row,expected,con,target):
        current=self._fetch(row,con)
        fields=self._fields(row,target)
        if expected is None:
            if current is not None: raise LifecycleDecision('شناسه وابسته دوباره استفاده شده است؛ تعیین تکلیف لازم است.')
        elif current is None or any(current.get(k)!=expected.get(k) for k in fields):
            raise LifecycleDecision(f'اثر ثبت در {row["table"]} بعداً تغییر کرده است؛ تعیین تکلیف لازم است.')

    def _reverse(self,effects,con):
        self._check_dependents(effects,con)
        for row in effects: self._check(row,row['after'],con,'before')
        for row in reversed(effects): self._write(row,'before',con)

    def _legacy(self,pid,con):
        """Only unambiguous posting-owned legacy rows are adopted automatically."""
        post=self.db.get_financial_posting(pid)
        if not post:
            return self._legacy_nonposting(pid,con)
        if post.get('status')=='DELETED':
            raise LifecycleDecision('این ثبت قدیمی سابقه کامل وابستگی‌ها ندارد؛ تعیین تکلیف لازم است.')
        effects=[]
        for table,key,value in (
            ('financial_postings','posting_id',post['posting_id']),
            ('expenses','expense_id',post.get('expense_id')),
            ('transactions','transaction_id',post.get('transaction_id')),
            ('payments','payment_id',post.get('payment_id')),
            ('cheques','cheque_id',post.get('cheque_id'))):
            if value:
                row=con.execute(f'SELECT * FROM "{table}" WHERE "{key}"=?',(value,)).fetchone()
                if row: effects.append({'table':table,'pk':[key],'key':[value],'before':None,'after':dict(row)})
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='financial_documents'").fetchone() and con.execute("SELECT 1 FROM financial_documents WHERE pending_id=? AND status='ACTIVE'",(pid,)).fetchone():
            effects.extend(self._legacy_nonposting(pid,con))
        return effects

    def drop_stale_snapshot(self,pid,record,con):
        """A resolution record posts nothing, but an older approval of the same record (the clearing
        flow made a cash row) may have left a snapshot on it. It is dropped once none of its rows is
        alive any more; if one is, the record cannot be taken back without a decision."""
        from record_ownership187 import LEDGER
        for effect in json.loads(record['effects_json']):
            table=effect.get('table')
            if table not in LEDGER or not effect.get('key'): continue
            column,live=LEDGER[table]
            if con.execute(f'SELECT 1 FROM {table} WHERE {column}=? AND {live}',(str(effect['key'][0]),)).fetchone()                     and effect.get('before') is None:
                raise LifecycleDecision('این رکورد تعیین تکلیف از تأیید قدیمی یک ردیف مالی زنده دارد؛ تعیین تکلیف لازم است.')
        con.execute('DELETE FROM transaction_lifecycle WHERE pending_id=?',(pid,))
        self.db._audit(con,'transaction_lifecycle',pid,'DELETE',self.source,before=dict(record),after=None,actor_id=self.actor_id)

    def _undo_resolution(self,pid,item):
        """Take a resolution record back: the cheque returns to the state it had before the
        record changed it, the receipts it brought go back onto the record, and the record
        stops being linked to the cheque. The cheque's money effect is whatever that state had."""
        payload=dict(item['payload'] or {})
        cheque_id=str(payload.get('selected_cheque_id187') or '')
        if self.db.get_cheque(cheque_id):
            before=payload.get('_resolution_before187') or dict(ISSUE_TIME_STATE,registration_state=None)
            self.db.restore_cheque_state(cheque_id,before,source=self.source,actor_id=self.actor_id)
            with self.db.tx() as con:
                for attachment_id in payload.get('_resolution_attachments187') or []:
                    con.execute("UPDATE attachments SET entity_type='PENDING',entity_id=? WHERE attachment_id=? "
                                "AND entity_type='CHEQUE' AND entity_id=?",(pid,attachment_id,cheque_id))
        kept={k:v for k,v in payload.items() if k not in ('_resolution_before187','_resolution_attachments187')}
        # restoring the cheque rewrote this record's status fields too; keep what the user had chosen
        self.db.update_pending(pid,payload=kept)
        self.db.update_telegram_message(chat_id=item['telegram_chat_id'],message_id=item['telegram_message_id'],
                                        state='PENDING_REVIEW',linked_entity_type=None,linked_entity_id=None)

    def _reject_one(self,pid,*,permanent=False):
        prior_contracts=self._contracts(pid)
        try:
            with self.db.atomic() as con:
                item=self.db.get_pending_item(pid)
                if not item: raise KeyError(pid)
                record=self.get(pid,con)
                if record and record['state']=='PURGED': return
                if record and record['state']=='ACTIVE' and item['status'] in ('APPROVED','EDIT_PENDING') and is_new_resolution(item['payload']):
                    self.drop_stale_snapshot(pid,record,con)
                    record=None
                effects=json.loads(record['effects_json']) if record else []
                # A posted record still in «در حال اصلاح» keeps the ledger of its last
                # approval (the edit is only staged), so it is adopted like an approved one.
                resolution=(not record and item['status'] in ('APPROVED','EDIT_PENDING')
                            and is_resolution_payload(item['payload']))
                if not record and not resolution and item['status'] in ('APPROVED','EDIT_PENDING'): effects=self._legacy(pid,con)
                if not record or record['state']=='ACTIVE':
                    message=self._message(pid,con)
                    # This transient review state stays inside the confirmed SQL
                    # transaction; cancellation or dependency failure rolls it back.
                    con.execute("UPDATE pending_items SET status='PENDING_REVIEW' WHERE pending_id=?",(pid,))
                    if resolution: self._undo_resolution(pid,item)
                    effects=self._include_late_reminders(effects,con)
                    if effects: self._reverse(effects,con)
                    self._set_contracts(pid,[])
                    rejected=[{**row,'rejected':self._fetch(row,con)} for row in effects]
                else:
                    message=json.loads(record['message_json'])
                    rejected=json.loads(record['rejected_json'])
                    # Purging an already rejected record changes only its
                    # visibility/audit state. Its financial effects were
                    # reversed earlier and must not be reversed or validated
                    # against newer independent transactions a second time.
                    if not permanent:
                        self._check_dependents(effects,con)
                        for effect in rejected:self._check(effect,effect['rejected'],con,'after')
                approved_payload=None
                if con.execute("SELECT 1 FROM sqlite_master WHERE name='posting_revisions'").fetchone():
                    if not record and item['status']=='EDIT_PENDING':
                        # Restoring must bring back what was approved, not the unapproved edit.
                        staged=con.execute("SELECT old_payload_json FROM posting_revisions WHERE pending_id=? AND status='PENDING' ORDER BY created_at DESC LIMIT 1",(pid,)).fetchone()
                        if staged: approved_payload=json.loads(staged['old_payload_json'])
                    con.execute("UPDATE posting_revisions SET status='REJECTED',updated_at=? WHERE pending_id=? AND status='PENDING'",(_now(),pid))
                state='PURGED' if permanent else 'REJECTED'
                payload=json.loads(record['payload_json']) if record else (approved_payload or item['payload'])
                contracts=json.loads(record['contract_json']) if record else prior_contracts
                self._persist(pid,state,effects,payload,message,contracts,rejected,con)
                con.execute("UPDATE pending_items SET status='REJECTED',updated_at=? WHERE pending_id=?",(_now(),pid))
                con.execute("UPDATE telegram_messages SET state='REJECTED',reaction_state='NONE',updated_at=? WHERE chat_id=? AND message_id=?",
                    (_now(),item['telegram_chat_id'],item['telegram_message_id']))
                if con.execute("SELECT 1 FROM sqlite_master WHERE name='rich_ui_hidden_reviews'").fetchone():
                    if permanent:
                        con.execute('INSERT INTO rich_ui_hidden_reviews(pending_id,hidden,updated_at) VALUES(?,1,?) ON CONFLICT(pending_id) DO UPDATE SET hidden=1,updated_at=excluded.updated_at',(pid,_now()))
                    else:
                        con.execute('UPDATE rich_ui_hidden_reviews SET hidden=0,updated_at=? WHERE pending_id=?',(_now(),pid))
                self.db.update_receipt_analysis_status(pid,'REJECTED')
                self.db.enqueue_integration_event('GUI_REJECTED',pending_id=pid,payload={'permanent':permanent,'actor_id':self.actor_id})
                self.clear_decision(pid)
                self.db._audit(con,'pending',pid,'DELETE',self.source,before=item,after={'status':state},actor_id=self.actor_id)
                self.db._enqueue_sync(con,'pending',pid,'DELETE',{'status':state})
        except Exception:
            self._set_contracts(pid,prior_contracts)
            raise

    def _restore_one(self,pid):
        prior_contracts=self._contracts(pid)
        try:
            with self.db.atomic() as con:
                record=self.get(pid,con)
                if not record or record['state']=='PURGED':
                    raise ValueError('حذف کامل قابل بازگردانی نیست؛ این ردیف سابقه بازگردانی ندارد.')
                if record['state']=='ACTIVE': return
                effects=json.loads(record['rejected_json'])
                for row in effects: self._check(row,row['rejected'],con,'after')
                self._check_parents(effects,con)
                contracts=json.loads(record['contract_json'])
                self._set_contracts(pid,contracts)
                for row in effects: self._write(row,'after',con)
                # Unapproved rejected drafts return to review, approved records to their old place.
                approved=bool(effects) or json.loads(record['message_json']).get('state')=='APPROVED'
                payload=json.loads(record['payload_json'])
                # A rejected resolution has no ledger rows to bring back. It returns to review so it
                # can be approved on its own, for this cheque or, if it was filed wrongly, another.
                resolution=is_resolution_payload(payload) and not effects
                if resolution: approved=False
                status='APPROVED' if approved else 'PENDING_REVIEW'
                self.db.update_pending(pid,payload=payload,status=status)
                item=self.db.get_pending_item(pid);msg=json.loads(record['message_json'])
                self.db.update_telegram_message(chat_id=item['telegram_chat_id'],message_id=item['telegram_message_id'],
                    state=status,linked_entity_type=None if resolution else msg.get('linked_entity_type'),
                    linked_entity_id=None if resolution else msg.get('linked_entity_id'))
                con.execute("UPDATE transaction_lifecycle SET state='ACTIVE',updated_at=? WHERE pending_id=?",(_now(),pid))
                if con.execute("SELECT 1 FROM sqlite_master WHERE name='rich_ui_hidden_reviews'").fetchone():
                    con.execute('UPDATE rich_ui_hidden_reviews SET hidden=0,updated_at=? WHERE pending_id=?',(_now(),pid))
                self.db.update_receipt_analysis_status(pid,'APPROVED' if approved else 'NEEDS_REVIEW')
                self.db.enqueue_integration_event('GUI_APPROVED' if approved else 'GUI_REOPENED',pending_id=pid,payload={'actor_id':self.actor_id,'restore':True})
                self.clear_decision(pid)
                self.db._audit(con,'pending',pid,'RESTORE',self.source,before={'status':'REJECTED'},after={'status':status},actor_id=self.actor_id)
                self.db._enqueue_sync(con,'pending',pid,'UPDATE',{'status':status})
        except Exception:
            self._set_contracts(pid,prior_contracts)
            raise

    def pending_for_row(self,row):
        if row.get('pending_id'): return str(row['pending_id'])
        checks={'transaction_id':'transactions','expense_id':'expenses','cheque_id':'cheques',
                'received_payment_id':'received_payments','document_id':'financial_documents',
                'loan_installment_id':'loan_installments','loan_id':'loans'}
        with self.db.read() as con:
            records=con.execute("SELECT pending_id,effects_json FROM transaction_lifecycle WHERE state='ACTIVE'").fetchall()
            for key,table in checks.items():
                value=row.get(key)
                if not value: continue
                for record in records:
                    for effect in json.loads(record['effects_json']):
                        if effect['table']==table and effect['after'] and str(effect['after'].get(key) or '')==str(value):
                            return record['pending_id']
                if key in ('transaction_id','expense_id','cheque_id'):
                    post=con.execute(f'SELECT pending_id FROM financial_postings WHERE {key}=?',(value,)).fetchone()
                    if post: return post['pending_id']
        raise LifecycleDecision('این ردیف منبع ثبت دیتای مشخص ندارد؛ تعیین تکلیف لازم است.')


    def _check_parents(self,effects,con):
        for row in effects:
            after=row['after'] or {}
            parents=[]
            if row['table']=='received_payments':parents.append(('sales','sale_id',after.get('sale_id')))
            if row['table']=='loan_installments' and row['before'] is not None:parents.append(('loans','loan_id',after.get('loan_id')))
            for table,key,value in parents:
                parent=con.execute(f'SELECT status FROM {table} WHERE {key}=?',(value,)).fetchone()
                if not parent or parent['status']=='CANCELLED':
                    raise LifecycleDecision('قرارداد یا وام مبدا حذف شده است؛ بازگردانی رسید نیازمند تعیین تکلیف است.')

    def change_many(self,ids,*,restore=False,permanent=False,purge_rejected=False):
        ids=list(dict.fromkeys(str(pid) for pid in ids))
        affected=set(ids)
        queue=list(ids)
        while queue:
            pid=queue.pop()
            record=self.get(pid)
            children=json.loads(record['message_json']).get('_lifecycle_child_ids') or [] if record else []
            if not restore: children=list(children)+self._cheque_dependents(pid)
            for child in children:
                if child not in affected:
                    affected.add(child);queue.append(child)
        # Cheque settlements can change contractor receipts too. Keep their
        # file snapshots until the entire SQL group has committed.
        previous={pid:self._contracts(pid) for pid in affected}
        try:
            with self.db.atomic():
                was_rejected={pid:(self.db.get_pending_item(pid) or {}).get('status')=='REJECTED' for pid in ids}
                # Later receipts can depend on earlier entries. Reject newest
                # first; restore oldest first, regardless of table sorting.
                with self.db.read() as con:
                    order={row['pending_id']:(row['created_at'],row['position']) for row in con.execute(
                        'SELECT pending_id,created_at,rowid AS position FROM pending_items WHERE pending_id IN ('+
                        ','.join('?' for _ in ids)+')',ids)} if ids else {}
                ids.sort(key=lambda pid:order.get(pid,('',0)),reverse=not restore)
                for pid in ids:
                    self.restore(pid) if restore else self.reject(pid,permanent=permanent or (purge_rejected and was_rejected[pid]))
        except Exception:
            for pid,wanted in previous.items():self._set_contracts(pid,wanted)
            raise

    def flag_decision(self,pid,operation,reason):
        entries=json.loads(self.db.get_setting('transaction_lifecycle_decisions') or '{}')
        entries[str(pid)]={'operation':operation,'reason':str(reason),'updated_at':_now()}
        self.db.set_setting('transaction_lifecycle_decisions',_json(entries))

    def decision_rows(self,sources):
        """Read-only queue entries; orphan entries never create pending records."""
        decisions=self.decisions();by_id={str(r.get('pending_id')):r for r in sources}
        rows=[]
        for key,entry in sorted(decisions.items(),key=lambda pair:pair[1].get('updated_at',''),reverse=True):
            row=dict(by_id.get(key) or {})
            if not row:
                row={'status':'DECISION_ONLY','_lifecycle_decision_only187':True,
                     'message_date':entry.get('updated_at'),'payload':{'description':entry['reason']}}
            row.update(_lifecycle_decision_key187=key,_lifecycle_decision187=key+': '+entry['reason'])
            rows.append(row)
        return rows

    def clear_decision(self,pid):
        entries=self.decisions()
        if str(pid) in entries:
            del entries[str(pid)]
            self.db.set_setting('transaction_lifecycle_decisions',_json(entries))

    def _include_late_reminders(self,effects,con):
        # Scheduler-created reminders belong to the uniquely owned new entity.
        known={tuple(e['key']) for e in effects if e['table']=='reminders'}
        result=list(effects)
        for e in effects:
            kind={'cheques':'CHEQUE','loan_installments':'LOAN_INSTALLMENT','installments':'INSTALLMENT'}.get(e['table'])
            if not kind or e['before'] is not None or not e['after']:continue
            for row in con.execute('SELECT * FROM reminders WHERE entity_type=? AND entity_id=? AND status!=?',(kind,str(e['key'][0]),'CANCELLED')).fetchall():
                if (row['reminder_id'],) in known:continue
                result.append({'table':'reminders','pk':['reminder_id'],'key':[row['reminder_id']],'before':None,'after':dict(row)})
                known.add((row['reminder_id'],))
        return result

    def decisions(self):
        return json.loads(self.db.get_setting('transaction_lifecycle_decisions') or '{}')


    def _check_dependents(self,effects,con):
        owned={(r['table'],tuple(r['key'])) for r in effects}
        for effect in effects:
            if effect['table']=='cheques':
                current=self._fetch(effect,con)
                if (current and current['status']=='CASHED'
                        and str(current.get('settlement_mode') or '').upper()!='CHECKBOOK'
                        and ('transactions',(current.get('cash_transaction_id'),)) not in owned):
                    raise LifecycleDecision('چک پاس‌شده رسید تسویه با مبدا مشخص ندارد؛ تعیین تکلیف لازم است.')
        tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for effect in effects:
            if effect['before'] is not None or not effect['after']:continue
            entity={'expenses':'EXPENSE','transactions':'TRANSACTION','cheques':'CHEQUE','loans':'LOAN'}.get(effect['table'])
            if not entity:continue
            if 'financial_document_links' in tables:
                for link in con.execute('SELECT document_id,entity_type,entity_id FROM financial_document_links WHERE UPPER(entity_type)=? AND entity_id=?',(entity,str(effect['key'][0]))):
                    if ('financial_document_links',tuple(link)) not in owned:
                        raise LifecycleDecision('این ثبت به سند دیگری متصل شده است؛ ارتباط سند باید تعیین تکلیف شود.')
            if 'expense_payment_links' in tables:
                fk={'expenses':'expense_id','transactions':'transaction_id','cheques':'cheque_id'}.get(effect['table'])
                if fk:
                    for link in con.execute(f'SELECT link_id FROM expense_payment_links WHERE {fk}=?',(effect['key'][0],)):
                        if ('expense_payment_links',(link[0],)) not in owned:
                            raise LifecycleDecision('این ثبت ارتباط پرداخت دیگری دارد؛ ارتباط رسید باید تعیین تکلیف شود.')
        relations={
            'expenses':(('payments','payment_id','expense_id',"status!='CANCELLED'"),),
            'loans':(('loan_installments','loan_installment_id','loan_id',"status!='CANCELLED'"),),
            'received_payments':(('payment_allocations','allocation_id','received_payment_id','1=1'),),
        }
        for row in effects:
            if row['before'] is not None:continue
            for table,pk,fk,where in relations.get(row['table'],()):
                for child in con.execute(f'SELECT {pk} FROM {table} WHERE {fk}=? AND {where}',row['key']):
                    if (table,(child[0],)) not in owned:
                        raise LifecycleDecision('این ثبت وابستگی مالی تازه یا رسید دیگری دارد؛ ابتدا تعیین تکلیف لازم است.')


    def _legacy_nonposting(self,pid,con):
        effects=[]
        def add(table,key,value):
            row=con.execute(f'SELECT * FROM {table} WHERE {key}=?',(value,)).fetchone()
            if row:effects.append({'table':table,'pk':[key],'key':[value],'before':None,'after':dict(row)})
        docs=con.execute("SELECT * FROM financial_documents WHERE pending_id=? AND status='ACTIVE'",(pid,)).fetchall()
        for doc in docs:
            add('financial_documents','document_id',doc['document_id'])
            for link in con.execute('SELECT * FROM financial_document_links WHERE document_id=?',(doc['document_id'],)):
                effect={'table':'financial_document_links','pk':['document_id','entity_type','entity_id'],
                    'key':[link['document_id'],link['entity_type'],link['entity_id']],'before':None,'after':dict(link)}
                effects.append(effect)
                if link['entity_type'].upper()=='CHEQUE' and doc['document_type'] in ('GUARANTEE_CHEQUE','GUARANTEE_CHEQUE_BUNDLE','CHEQUE_BUNDLE'):
                    add('cheques','cheque_id',link['entity_id'])
        if effects:return effects
        message=self._message(pid,con)
        if message.get('linked_entity_type')=='LOAN':
            lid=message['linked_entity_id']
            loan=con.execute("SELECT * FROM loans WHERE loan_id=? AND status!='CANCELLED'",(lid,)).fetchone()
            if loan:
                if con.execute('SELECT 1 FROM loan_installments WHERE loan_id=? AND paid_amount>0',(lid,)).fetchone():
                    raise LifecycleDecision('وام قدیمی قسط پرداخت‌شده دارد؛ رسیدهای اقساط باید تعیین تکلیف شوند.')
                add('loans','loan_id',lid)
                if loan['receive_transaction_id']:add('transactions','transaction_id',loan['receive_transaction_id'])
                for installment in con.execute("SELECT loan_installment_id FROM loan_installments WHERE loan_id=? AND status!='CANCELLED'",(lid,)):
                    add('loan_installments','loan_installment_id',installment[0])
                return effects
        item=self.db.get_pending_item(pid)
        if item.get('detected_type')=='INFO' or (item['payload'].get('v18_title')=='یادداشت' and item.get('detected_type')=='DOCUMENT'):
            return []
        raise LifecycleDecision('این ثبت قدیمی سابقه کافی برای برگشت وابستگی‌ها ندارد؛ تعیین تکلیف لازم است.')


    def _cheque_dependents(self,pid):
        record=self.get(pid)
        if record and record['state']!='ACTIVE':return []
        effects=json.loads(record['effects_json']) if record else []
        ids={r['after']['cheque_id'] for r in effects if r['table']=='cheques' and r['before'] is None and r['after']}
        post=self.db.get_financial_posting(pid)
        if post and post.get('cheque_id'):ids.add(post['cheque_id'])
        if not ids:return []
        with self.db.read() as con:
            sources=con.execute("""SELECT l.pending_id,l.effects_json FROM transaction_lifecycle l
                JOIN pending_items p ON p.pending_id=l.pending_id WHERE l.state='ACTIVE'
                AND l.pending_id!=? ORDER BY p.created_at DESC,p.rowid DESC""",(pid,)).fetchall()
            resolutions=con.execute("""SELECT pending_id,payload_json FROM pending_items
                WHERE status IN ('APPROVED','EDIT_PENDING') AND pending_id!=?
                AND payload_json LIKE '%selected_cheque_id187%' ORDER BY created_at DESC,rowid DESC""",(pid,)).fetchall()
        children=[source['pending_id'] for source in sources if any(
            e['table']=='cheques' and e['before'] is not None and e['after'] and e['after']['cheque_id'] in ids
            for e in json.loads(source['effects_json']))]
        for row in resolutions:
            payload=json.loads(row['payload_json'] or '{}')
            if is_resolution_payload(payload) and str(payload['selected_cheque_id187']) in ids and row['pending_id'] not in children:
                children.append(row['pending_id'])
        return children

    def reject(self,pid,*,permanent=False):
        record=self.get(pid)
        children=self._cheque_dependents(pid)
        if permanent and record and record['state']=='REJECTED':
            children=json.loads(record['message_json']).get('_lifecycle_child_ids') or []
        if not children:return self._reject_one(pid,permanent=permanent)
        ids=children+[pid];previous={key:self._contracts(key) for key in ids}
        try:
            with self.db.atomic() as con:
                for child in children:self.reject(child,permanent=permanent)
                self._reject_one(pid,permanent=permanent)
                record=self.get(pid,con);message=json.loads(record['message_json'])
                message['_lifecycle_child_ids']=children
                con.execute('UPDATE transaction_lifecycle SET message_json=? WHERE pending_id=?',(_json(message),pid))
        except Exception:
            for key,payments in previous.items():self._set_contracts(key,payments)
            raise

    def restore(self,pid):
        record=self.get(pid)
        if not record or record['state']!='REJECTED':return self._restore_one(pid)
        children=json.loads(record['message_json']).get('_lifecycle_child_ids') or []
        ids=[pid,*reversed(children)];previous={key:self._contracts(key) for key in ids}
        try:
            with self.db.atomic():
                self._restore_one(pid)
                for child in reversed(children):self.restore(child)
        except Exception:
            for key,payments in previous.items():self._set_contracts(key,payments)
            raise
