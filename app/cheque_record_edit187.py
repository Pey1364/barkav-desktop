"""Transactional cheque record editing; opening/cancelling never posts money."""
from copy import deepcopy
from datetime import datetime
import json


def pending_ids(db, cheque_id):
    with db.read() as con:
        rows = con.execute("""SELECT p.pending_id FROM pending_items p
            JOIN telegram_messages m ON p.telegram_chat_id=m.chat_id
              AND p.telegram_message_id=m.message_id
            WHERE m.linked_entity_type='CHEQUE' AND m.linked_entity_id=?
            ORDER BY p.updated_at DESC""", (cheque_id,)).fetchall()
        postings = con.execute('SELECT pending_id FROM financial_postings WHERE cheque_id=?',
                               (cheque_id,)).fetchall()
        # the record that issued the cheque even when it was approved by the older bundle route, which
        # links its message to a document, not to the cheque
        issued = [row['pending_id'] for row in con.execute(
            """SELECT l.pending_id,l.effects_json FROM transaction_lifecycle l
               JOIN pending_items p ON p.pending_id=l.pending_id WHERE l.state='ACTIVE' AND l.effects_json LIKE ?
               ORDER BY p.created_at""", (f'%{cheque_id}%',))
            if any(effect.get('table') == 'cheques' and effect.get('before') is None and effect.get('key') == [cheque_id]
                   for effect in json.loads(row['effects_json'] or '[]'))] if _has_table(con, 'transaction_lifecycle') else []
        documented = [row['pending_id'] for row in con.execute(
            """SELECT d.pending_id FROM financial_documents d JOIN financial_document_links l ON l.document_id=d.document_id
               WHERE d.status='ACTIVE' AND UPPER(l.entity_type)='CHEQUE' AND l.entity_id=? AND d.pending_id IS NOT NULL""",
            (cheque_id,))] if _has_table(con, 'financial_documents') else []
    return list(dict.fromkeys(str(pid) for pid in (*[row['pending_id'] for row in postings], *issued, *documented,
                                                  *[row['pending_id'] for row in rows])))


def _has_table(con, name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


class ChequeRecordSession187:
    def __init__(self, db, cheque_id, pid):
        self.db, self.cheque_id, self.pid = db, cheque_id, pid
        self.before = deepcopy(db.get_pending_item(pid))
        # The issue and every resolution of this cheque are under review while its row is edited.
        self.records = {str(other): deepcopy(db.get_pending_item(other)) for other in pending_ids(db, cheque_id)}
        self.records.setdefault(str(pid), self.before)
        self.committed = False
        with db.read() as con:
            self.attachments = {row['attachment_id']: dict(row) for row in con.execute(
                "SELECT * FROM attachments WHERE (entity_type='PENDING' AND entity_id=?) "
                "OR (entity_type='CHEQUE' AND entity_id=?)", (pid, cheque_id))}

    def cancel(self):
        if self.committed:
            return
        db = self.db
        with db.atomic() as con:
            for row in con.execute("SELECT * FROM attachments WHERE "
                    "(entity_type='PENDING' AND entity_id=?) OR (entity_type='CHEQUE' AND entity_id=?)",
                    (self.pid, self.cheque_id)).fetchall():
                if row['attachment_id'] not in self.attachments:
                    con.execute("UPDATE attachments SET entity_type='RECEIPT_ARCHIVE',entity_id=? "
                                'WHERE attachment_id=?', (self.pid, row['attachment_id']))
            for aid, row in self.attachments.items():
                con.execute('UPDATE attachments SET entity_type=?,entity_id=? WHERE attachment_id=?',
                            (row['entity_type'], row['entity_id'], aid))
            for other, record in self.records.items():
                if record:
                    db.update_pending(other, payload=record['payload'], status=record['status'])

    def under_review(self):
        """Put every approved record of the cheque in review, so the cheque shows in the unresolved list."""
        for other, record in self.records.items():
            if record and record['status'] == 'APPROVED':
                self.db.update_pending(other, status='EDIT_PENDING')

    def resolution_ids(self):
        """The approved (or under review) resolution records of this cheque."""
        from transaction_lifecycle import is_resolution_payload
        return [pid for pid, record in self.records.items()
                if record and is_resolution_payload(record['payload']) and record['status'] in ('APPROVED', 'EDIT_PENDING')]

    def approve(self, payload, runtime, *, require_details=True):
        db = self.db
        cid = self.cheque_id
        self.resolution_pid = None
        with db.atomic() as con:
            before = db.get_cheque(cid)
            amount = runtime.parse_int(payload.get('amount') or 0)
            if amount <= 0:
                raise ValueError('مبلغ چک باید بیشتر از صفر باشد.')
            issue = str(payload.get('event_date_shamsi') or before['issue_date_shamsi'])
            due = str(payload.get('due_date_shamsi') or before['due_date_shamsi'])
            # The legacy details API blocks CASHED; this dedicated atomic edit
            # restores its lifecycle before committing, without undoing money.
            original_state = db.cheque_state(cid)
            con.execute("UPDATE cheques SET status='ISSUED' WHERE cheque_id=?", (cid,))
            db.update_cheque_details(cid, amount=amount,
                issue_date=runtime.shamsi_to_gregorian(issue), issue_date_shamsi=issue,
                due_date=runtime.shamsi_to_gregorian(due), due_date_shamsi=due,
                issuer_name=payload.get('issuer_name',''), issuer_bank=payload.get('issuer_bank',''),
                receiver_name=payload.get('receiver_name',''), description=payload.get('description',''),
                cheque_serial=payload.get('cheque_serial',''), cheque_type=payload.get('cheque_type','PHYSICAL'),
                is_guarantee=bool(payload.get('is_guarantee')), source='GUI_CHEQUE_RECORD', actor_id='GUI')
            # the status the cheque really had, so a change from or to «باطل‌شده» moves its payment
            db.restore_cheque_state(cid, original_state, source='GUI_CHEQUE_RECORD')
            status = runtime._cheque_resolution_status_code_187(payload.get('cheque_status'))
            if payload.get('cheque_status') == 'RETURNED_SETTLED':status='RETURNED_ON_SETTLEMENT'
            if status not in {'ISSUED','CASHED','RETURNED','RETURNED_ON_SETTLEMENT','VOIDED'}:
                raise ValueError('وضعیت چک معتبر نیست.')
            registration = payload.get('cheque_registration_state') or before['registration_state']
            disposition = payload.get('cheque_return_disposition187') or runtime.CHEQUE_RETURN_DISPOSITION_CHOICES_187[3]
            holder = payload.get('cheque_return_account_holder187') or ''
            reason = payload.get('cheque_void_reason187') or ''
            current_code = runtime._cheque_resolution_status_code_187(runtime._cheque_status_label_187(before)) or 'ISSUED'
            resolutions = self.resolution_ids()
            if status == 'ISSUED' and current_code != 'ISSUED' and resolutions:
                # «صادرشده» again: the resolution records are taken back, and each puts the cheque back as
                # it was before it
                from transaction_lifecycle import TransactionLifecycle
                for resolution in resolutions:
                    TransactionLifecycle(db).reject(resolution)
                db.update_cheque_workflow_state(cid, lifecycle='ISSUED', registration_state=registration,
                                                source='GUI_CHEQUE_RECORD')
            elif status not in ('ISSUED', current_code) and not resolutions:
                # a status change of a cheque no resolution record covers: the change gets its record
                self.resolution_pid = runtime._manual_resolution_record_187(
                    cid, status, registration=registration, disposition=disposition, holder=holder,
                    void_reason=reason, require_details=require_details)
            else:
                db.update_cheque_workflow_state(cid, lifecycle=status, registration_state=registration,
                    return_disposition=disposition, return_account_holder=holder, void_reason=reason,
                    source='GUI_CHEQUE_RECORD', require_details=require_details)
                self.resolution_pid = (resolutions or [None])[0]
            eid = before.get('expense_id')
            if eid:
                expense = con.execute('SELECT * FROM expenses WHERE expense_id=?', (eid,)).fetchone()
                if expense and expense['status'] != 'CANCELLED':
                    fields = {key: payload[key] for key in ('cost_group','contract_id','main_phase','sub_phase')
                              if key in expense.keys() and key in payload}
                    fields['description']=payload.get('description',expense['description'])
                    for key in ('final_amount','invoice_amount','discount_amount'):
                        fields[key]=runtime.parse_int(payload.get(key,expense[key]))
                    con.execute('UPDATE expenses SET '+','.join(key+'=?' for key in fields)+
                                ',updated_at=? WHERE expense_id=?',
                                (*fields.values(),datetime.now().isoformat(),eid))
                    db._audit(con,'expense',eid,'RECORD_EDIT','GUI_CHEQUE_RECORD',before=dict(expense),
                        after=dict(con.execute('SELECT * FROM expenses WHERE expense_id=?',(eid,)).fetchone()),actor_id='GUI')
            if amount != int(before['amount']):
                con.execute('UPDATE payments SET amount=? WHERE cheque_id=?', (amount,cid))
                if before.get('cash_transaction_id'):
                    con.execute('UPDATE transactions SET amount=? WHERE transaction_id=?',
                                (amount,before['cash_transaction_id']))
            clean = {key: value for key,value in payload.items() if key != '_cheque_record_id187'}
            clean['cheque_id'] = cid
            if self.before['payload'].get('cheque_operation187'):
                clean['cheque_operation187']=self.before['payload']['cheque_operation187']
            db.update_pending(self.pid, payload=clean, status='APPROVED')
            for other, record in self.records.items():
                if other != self.pid and record and db.get_pending_item(other)['status'] == 'EDIT_PENDING':
                    db.update_pending(other, status=record['status'])
            db.relink_pending_attachments(self.pid, entity_type='CHEQUE', entity_id=cid)
            for source_id in pending_ids(db,cid):
                source=db.get_pending_item(source_id)
                if source_id != self.pid:
                    data=dict(source['payload'])
                    # the status and the registration were put on the record with the cheque's state (a code)
                    for key in ('amount','issuer_name','issuer_bank','receiver_name','description','cheque_serial',
                                'cheque_type','is_guarantee','due_date_shamsi'):
                        if key in clean:data[key]=clean[key]
                    db.update_pending(source_id,payload=data)
                # Keep audit-safe delete/restore snapshots aligned with edits.
                entry=con.execute("SELECT effects_json FROM transaction_lifecycle WHERE pending_id=? AND state='ACTIVE'",
                                  (source_id,)).fetchone()
                if entry:
                    from transaction_lifecycle import TABLES, TransactionLifecycle
                    lifecycle=TransactionLifecycle(db)
                    effects=json.loads(entry['effects_json'])
                    for effect in effects:
                        if effect['after'] and effect['table'] in TABLES:
                            keys=effect['pk'];values=effect['key']
                            schema={column['name'] for column in con.execute('PRAGMA table_info('+effect['table']+')')}
                            if not set(keys)<=schema:raise ValueError('سابقهٔ ویرایش معتبر نیست.')
                            current=con.execute('SELECT * FROM '+effect['table']+' WHERE '+
                                ' AND '.join(key+'=?' for key in keys),values).fetchone()
                            if current:effect['after']=dict(current)
                    # the issue's snapshot is the cheque as the issue made it, not as a resolution left it
                    effects=lifecycle.issue_time_cheques(effects,con)
                    con.execute('UPDATE transaction_lifecycle SET effects_json=?,payload_json=? WHERE pending_id=?',
                        (json.dumps(effects),json.dumps(db.get_pending_item(source_id)['payload']),source_id))
            db._audit(con,'cheque',cid,'RECORD_EDIT','GUI_CHEQUE_RECORD',before=before,
                      after=db.get_cheque(cid),actor_id='GUI')
        self.committed = True
        return 'اطلاعات چک و اسناد آن به‌روزرسانی شد.'


def open_cheque_record(window, row, runtime):
    db = runtime.DB
    cid = str(row['cheque_id'])
    ids = pending_ids(db,cid)
    if not ids:
        return runtime.messagebox.showerror('ویرایش چک','رکورد ثبت دیتای این چک پیدا نشد.',parent=window)
    pid = ids[0]
    session = ChequeRecordSession187(db,cid,pid)
    cheque = db.get_cheque(cid)
    draft = deepcopy(session.before)
    draft['payload'].update(v18_title='هزینه ساخت',v18_subtype='چک',
        cheque_operation187=runtime.CHEQUE_OPERATION_ISSUE_187,_cheque_record_id187=cid,
        event_date_shamsi=cheque['issue_date_shamsi'],due_date_shamsi=cheque['due_date_shamsi'],
        amount=cheque['amount'],cheque_status=runtime._cheque_status_label_187(cheque),
        cheque_registration_state=cheque['registration_state'],
        cheque_return_disposition187=cheque.get('return_disposition') or '',
        cheque_return_account_holder187=cheque.get('return_account_holder') or '',
        cheque_void_reason187=cheque.get('void_reason') or '')
    for key in ('issuer_name','issuer_bank','receiver_name','description','cheque_serial','cheque_type','is_guarantee'):
        draft['payload'][key]=cheque.get(key)
    try:
        editor=window.approval_center.open_editor(draft,navigation_rows=[draft])
        editor._cheque_record_session187=session
        session.under_review()
        def closed(event):
            if event.widget is editor:
                session.cancel()
                window.after_idle(window.refresh_all)
        editor.bind('<Destroy>',closed,add='+')
        window.approval_center.refresh()
        return editor
    except Exception:
        session.cancel()
        raise
