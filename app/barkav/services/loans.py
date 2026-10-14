from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Optional

from finance_db import FinanceDB, _id, _now
from revenue_service import gregorian_to_shamsi, normalize_shamsi, shamsi_to_gregorian


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return date(y, m, day)


class LoanService:
    def __init__(self, db: FinanceDB):
        self.db = db
        self._migrate()

    def _migrate(self) -> None:
        with self.db.tx() as con:
            cols = {r[1] for r in con.execute('PRAGMA table_info(loans)').fetchall()}
            additions = {
                'loan_type': "TEXT NOT NULL DEFAULT 'BANK'",
                'net_received_amount': 'INTEGER NOT NULL DEFAULT 0',
                'received_date_shamsi': 'TEXT',
                'interest_rate': 'REAL NOT NULL DEFAULT 0',
                'total_interest': 'INTEGER NOT NULL DEFAULT 0',
                'bank_fees': 'INTEGER NOT NULL DEFAULT 0',
                'total_repayment': 'INTEGER NOT NULL DEFAULT 0',
                'installment_count': 'INTEGER NOT NULL DEFAULT 0',
                'installment_amount': 'INTEGER NOT NULL DEFAULT 0',
                'first_due_date': 'TEXT',
                'first_due_date_shamsi': 'TEXT',
                'guarantors': "TEXT NOT NULL DEFAULT ''",
                'collateral': "TEXT NOT NULL DEFAULT ''",
                'contract_number': "TEXT NOT NULL DEFAULT ''",
                'receive_transaction_id': 'TEXT',
            }
            for col, ddl in additions.items():
                if col not in cols:
                    con.execute(f'ALTER TABLE loans ADD COLUMN {col} {ddl}')
            con.executescript('''
                CREATE TABLE IF NOT EXISTS loan_installments (
                    loan_installment_id TEXT PRIMARY KEY,
                    loan_id TEXT NOT NULL REFERENCES loans(loan_id),
                    installment_number INTEGER NOT NULL,
                    due_date TEXT NOT NULL,
                    due_date_shamsi TEXT,
                    amount INTEGER NOT NULL CHECK(amount >= 0),
                    principal_component INTEGER NOT NULL DEFAULT 0,
                    interest_component INTEGER NOT NULL DEFAULT 0,
                    paid_amount INTEGER NOT NULL DEFAULT 0,
                    paid_date TEXT,
                    paid_date_shamsi TEXT,
                    transaction_id TEXT REFERENCES transactions(transaction_id),
                    status TEXT NOT NULL DEFAULT 'UPCOMING' CHECK(status IN ('UPCOMING','DUE','PARTIALLY_PAID','PAID','OVERDUE','CANCELLED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(loan_id, installment_number)
                );
                CREATE INDEX IF NOT EXISTS idx_loan_installments_due ON loan_installments(due_date,status);
            ''')

    def _refresh_statuses(self) -> None:
        today = date.today().isoformat()
        with self.db.tx() as con:
            con.execute("UPDATE loan_installments SET status='PAID',updated_at=? WHERE paid_amount>=amount AND status!='CANCELLED'", (_now(),))
            con.execute("UPDATE loan_installments SET status='PARTIALLY_PAID',updated_at=? WHERE paid_amount>0 AND paid_amount<amount AND status!='CANCELLED'", (_now(),))
            con.execute("UPDATE loan_installments SET status='OVERDUE',updated_at=? WHERE paid_amount=0 AND due_date<? AND status NOT IN ('PAID','CANCELLED')", (_now(),today))
            con.execute("UPDATE loan_installments SET status='DUE',updated_at=? WHERE paid_amount=0 AND due_date=? AND status NOT IN ('PAID','CANCELLED')", (_now(),today))
            con.execute("UPDATE loan_installments SET status='UPCOMING',updated_at=? WHERE paid_amount=0 AND due_date>? AND status NOT IN ('PAID','CANCELLED')", (_now(),today))

    def create_loan(self, *, lender_name: str, principal_amount: int, net_received_amount: int,
                    received_date_shamsi: str, loan_type: str = 'BANK', interest_rate: float = 0,
                    total_interest: int = 0, bank_fees: int = 0, installment_count: int = 0,
                    installment_amount: int = 0, first_due_date_shamsi: str = '', guarantors: str = '',
                    collateral: str = '', contract_number: str = '', description: str = '',
                    source: str = 'GUI', register_cash: bool = True, telegram_chat_id: int | None = None, telegram_message_id: int | None = None) -> dict[str, Any]:
        principal_amount=int(principal_amount); net_received_amount=int(net_received_amount)
        if principal_amount <= 0: raise ValueError('اصل وام باید بیشتر از صفر باشد.')
        if net_received_amount < 0: raise ValueError('مبلغ واقعی دریافتی نامعتبر است.')
        rec_sh=normalize_shamsi(received_date_shamsi)
        if not rec_sh: raise ValueError('تاریخ دریافت شمسی نامعتبر است.')
        rec=shamsi_to_gregorian(rec_sh)
        first_sh=normalize_shamsi(first_due_date_shamsi) if first_due_date_shamsi else ''
        first=shamsi_to_gregorian(first_sh) if first_sh else None
        installment_count=max(0,int(installment_count)); installment_amount=max(0,int(installment_amount))
        total_interest=max(0,int(total_interest)); bank_fees=max(0,int(bank_fees))
        total_repayment=principal_amount+total_interest+bank_fees
        if installment_count and not installment_amount:
            installment_amount=(total_repayment + installment_count - 1)//installment_count
        lid=_id('LOAN'); tid=None; now=_now()
        with self.db.tx() as con:
            if register_cash and net_received_amount:
                tid=_id('TXN')
                con.execute('''INSERT INTO transactions(transaction_id,event_date,shamsi_date,direction,amount,category,payer_name,receiver_name,description,source_type,telegram_chat_id,telegram_message_id,loan_id,status,sync_status,created_at,updated_at)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                            (tid,rec,rec_sh,'IN',net_received_amount,'LOAN_RECEIPT',lender_name,'پروژه',description or f'دریافت وام از {lender_name}',source,telegram_chat_id,telegram_message_id,lid,'POSTED','PENDING',now,now))
            con.execute('''INSERT INTO loans(loan_id,lender_name,principal_amount,received_date,description,status,created_at,updated_at,
                           loan_type,net_received_amount,received_date_shamsi,interest_rate,total_interest,bank_fees,total_repayment,
                           installment_count,installment_amount,first_due_date,first_due_date_shamsi,guarantors,collateral,contract_number,receive_transaction_id)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (lid,lender_name.strip(),principal_amount,rec,description.strip(),'ACTIVE',now,now,loan_type,net_received_amount,rec_sh,float(interest_rate or 0),total_interest,bank_fees,total_repayment,installment_count,installment_amount,first,first_sh,guarantors.strip(),collateral.strip(),contract_number.strip(),tid))
            if installment_count and first:
                base_principal=principal_amount//installment_count
                base_interest=(total_interest+bank_fees)//installment_count
                for i in range(installment_count):
                    due=_add_months(date.fromisoformat(first),i)
                    principal_part=base_principal if i<installment_count-1 else principal_amount-base_principal*(installment_count-1)
                    interest_part=base_interest if i<installment_count-1 else (total_interest+bank_fees)-base_interest*(installment_count-1)
                    amt=installment_amount if i<installment_count-1 else max(0,total_repayment-installment_amount*(installment_count-1))
                    if amt<=0: amt=principal_part+interest_part
                    liid=_id('LINS')
                    con.execute('''INSERT INTO loan_installments(loan_installment_id,loan_id,installment_number,due_date,due_date_shamsi,amount,principal_component,interest_component,created_at,updated_at)
                                   VALUES(?,?,?,?,?,?,?,?,?,?)''',
                                (liid,lid,i+1,due.isoformat(),gregorian_to_shamsi(due),amt,principal_part,interest_part,now,now))
                    con.execute('INSERT INTO sync_queue(entity_type,entity_id,operation,payload_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                                ('loan_installment',liid,'CREATE',None,'PENDING',now,now))
            con.execute('INSERT INTO sync_queue(entity_type,entity_id,operation,payload_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                        ('loan',lid,'CREATE',None,'PENDING',now,now))
            if tid:
                con.execute('INSERT INTO sync_queue(entity_type,entity_id,operation,payload_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                            ('transaction',tid,'CREATE',None,'PENDING',now,now))
        return self.get_loan(lid) or {}

    def get_loan(self, loan_id: str) -> Optional[dict[str, Any]]:
        self._refresh_statuses()
        with self.db.read() as con:
            r=con.execute('SELECT * FROM loans WHERE loan_id=?',(loan_id,)).fetchone()
        return dict(r) if r else None

    def list_loans(self, include_cancelled: bool=False) -> list[dict[str, Any]]:
        self._refresh_statuses()
        where='' if include_cancelled else "WHERE l.status!='CANCELLED'"
        with self.db.read() as con:
            rows=con.execute(f'''SELECT l.*,
                COALESCE((SELECT SUM(li.paid_amount) FROM loan_installments li WHERE li.loan_id=l.loan_id AND li.status!='CANCELLED'),0) paid_total,
                COALESCE((SELECT SUM(li.interest_component * CASE WHEN li.amount=0 THEN 0 ELSE MIN(1.0,1.0*li.paid_amount/li.amount) END) FROM loan_installments li WHERE li.loan_id=l.loan_id AND li.status!='CANCELLED'),0) paid_interest_estimate,
                COALESCE((SELECT COUNT(*) FROM loan_installments li WHERE li.loan_id=l.loan_id AND li.status='PAID'),0) paid_installments,
                COALESCE((SELECT COUNT(*) FROM loan_installments li WHERE li.loan_id=l.loan_id AND li.status='OVERDUE'),0) overdue_installments,
                (SELECT due_date_shamsi FROM loan_installments li WHERE li.loan_id=l.loan_id AND li.status IN ('UPCOMING','DUE','PARTIALLY_PAID','OVERDUE') ORDER BY due_date LIMIT 1) next_due_shamsi,
                (SELECT MAX(0,amount-paid_amount) FROM loan_installments li WHERE li.loan_id=l.loan_id AND li.status IN ('UPCOMING','DUE','PARTIALLY_PAID','OVERDUE') ORDER BY due_date LIMIT 1) next_due_amount
                FROM loans l {where} ORDER BY COALESCE(l.received_date,'') DESC,l.loan_id DESC''').fetchall()
        out=[]
        for r in rows:
            d=dict(r); d['remaining_debt']=max(0,int(d.get('total_repayment') or d.get('principal_amount') or 0)-int(d.get('paid_total') or 0)); out.append(d)
        return out

    def list_installments(self, loan_id: str) -> list[dict[str, Any]]:
        self._refresh_statuses()
        with self.db.read() as con:
            rows=con.execute('SELECT * FROM loan_installments WHERE loan_id=? ORDER BY installment_number',(loan_id,)).fetchall()
        return [dict(r) for r in rows]

    def pay_installment(self, loan_installment_id: str, *, amount: int, paid_date_shamsi: str, source: str='GUI', description: str='', telegram_chat_id: int | None = None, telegram_message_id: int | None = None) -> dict[str, Any]:
        sh=normalize_shamsi(paid_date_shamsi)
        if not sh: raise ValueError('تاریخ پرداخت شمسی نامعتبر است.')
        gd=shamsi_to_gregorian(sh); amount=int(amount)
        if amount<=0: raise ValueError('مبلغ پرداخت باید بیشتر از صفر باشد.')
        now=_now(); tid=_id('TXN')
        with self.db.tx() as con:
            row=con.execute('''SELECT li.*,l.lender_name FROM loan_installments li JOIN loans l ON l.loan_id=li.loan_id WHERE li.loan_installment_id=?''',(loan_installment_id,)).fetchone()
            if not row: raise KeyError(loan_installment_id)
            remain=max(0,int(row['amount'])-int(row['paid_amount']))
            if amount>remain: raise ValueError('مبلغ پرداخت از مانده این قسط بیشتر است.')
            new_paid=int(row['paid_amount'])+amount
            status='PAID' if new_paid>=int(row['amount']) else 'PARTIALLY_PAID'
            con.execute('''INSERT INTO transactions(transaction_id,event_date,shamsi_date,direction,amount,category,payer_name,receiver_name,description,source_type,telegram_chat_id,telegram_message_id,loan_id,status,sync_status,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (tid,gd,sh,'OUT',amount,'LOAN_INSTALLMENT','پروژه',row['lender_name'],description or f"قسط {row['installment_number']} وام",source,telegram_chat_id,telegram_message_id,row['loan_id'],'POSTED','PENDING',now,now))
            con.execute('''UPDATE loan_installments SET paid_amount=?,paid_date=?,paid_date_shamsi=?,transaction_id=?,status=?,updated_at=? WHERE loan_installment_id=?''',
                        (new_paid,gd,sh,tid,status,now,loan_installment_id))
            if status == 'PAID':
                con.execute("UPDATE reminders SET status='CANCELLED',updated_at=? WHERE entity_type='LOAN_INSTALLMENT' AND entity_id=? AND status='SCHEDULED'", (now, loan_installment_id))
            con.execute('INSERT INTO sync_queue(entity_type,entity_id,operation,payload_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                        ('transaction',tid,'CREATE',None,'PENDING',now,now))
            con.execute('INSERT INTO sync_queue(entity_type,entity_id,operation,payload_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                        ('loan_installment',loan_installment_id,'UPDATE',None,'PENDING',now,now))
        return {'transaction_id':tid,'installment_id':loan_installment_id,'paid_amount':new_paid,'status':status}

    def cancel_loan(self, loan_id: str) -> None:
        with self.db.tx() as con:
            now = _now()
            con.execute("UPDATE loans SET status='CANCELLED',updated_at=? WHERE loan_id=?",(now,loan_id))
            rows = con.execute("SELECT loan_installment_id FROM loan_installments WHERE loan_id=? AND status!='PAID'", (loan_id,)).fetchall()
            con.execute("UPDATE loan_installments SET status='CANCELLED',updated_at=? WHERE loan_id=? AND status!='PAID'",(now,loan_id))
            for row in rows:
                con.execute("UPDATE reminders SET status='CANCELLED',updated_at=? WHERE entity_type='LOAN_INSTALLMENT' AND entity_id=? AND status='SCHEDULED'", (now, row['loan_installment_id']))

    def cancel_installment(self, loan_installment_id: str, *, source: str='GUI') -> None:
        """Soft-cancel an unpaid loan installment. Paid rows are protected."""
        with self.db.tx() as con:
            row=con.execute("SELECT * FROM loan_installments WHERE loan_installment_id=?",(loan_installment_id,)).fetchone()
            if not row: raise KeyError(loan_installment_id)
            if str(row['status']).upper()=='CANCELLED': return
            if int(row['paid_amount'] or 0)>0:
                raise ValueError('قسط وامی که پرداخت دارد قابل حذف نیست.')
            now=_now()
            con.execute("UPDATE loan_installments SET status='CANCELLED',updated_at=? WHERE loan_installment_id=?",(now,loan_installment_id))
            con.execute("UPDATE reminders SET status='CANCELLED',updated_at=? WHERE entity_type='LOAN_INSTALLMENT' AND entity_id=? AND status='SCHEDULED'",(now,loan_installment_id))
            self.db._enqueue_sync(con,'loan_installment',loan_installment_id,'UPDATE')

    def loan_totals(self) -> dict[str,int]:
        rows=self.list_loans()
        return {
            'principal':sum(int(r.get('principal_amount') or 0) for r in rows),
            'net_received':sum(int(r.get('net_received_amount') or 0) for r in rows),
            'interest':sum(int(r.get('total_interest') or 0)+int(r.get('bank_fees') or 0) for r in rows),
            'paid':sum(int(r.get('paid_total') or 0) for r in rows),
            'remaining':sum(int(r.get('remaining_debt') or 0) for r in rows),
        }

    def ensure_reminders(self) -> int:
        self._refresh_statuses(); created=0; now=_now()
        with self.db.tx() as con:
            rows=con.execute("SELECT * FROM loan_installments WHERE status IN ('UPCOMING','DUE','PARTIALLY_PAID','OVERDUE')").fetchall()
            for r in rows:
                due=date.fromisoformat(r['due_date'])
                dates=[due-timedelta(days=3),due]
                for offset in range(1,8): dates.append(due+timedelta(days=offset))
                for d in dates:
                    if d < date.today()-timedelta(days=7): continue
                    scheduled=f'{d.isoformat()}T09:00:00'
                    exists=con.execute("SELECT 1 FROM reminders WHERE entity_type='LOAN_INSTALLMENT' AND entity_id=? AND scheduled_at=?",(r['loan_installment_id'],scheduled)).fetchone()
                    if not exists:
                        con.execute('''INSERT INTO reminders(reminder_id,entity_type,entity_id,scheduled_at,channel_telegram,status,created_at,updated_at)
                                       VALUES(?,?,?,?,1,'SCHEDULED',?,?)''',(_id('REM'),'LOAN_INSTALLMENT',r['loan_installment_id'],scheduled,now,now)); created+=1
        return created

    def due_reminders(self, now_dt: Optional[datetime]=None) -> list[dict[str,Any]]:
        self._refresh_statuses(); now_dt=now_dt or datetime.now()
        with self.db.read() as con:
            rows=con.execute('''SELECT r.*,li.installment_number,li.due_date_shamsi,li.amount,li.paid_amount,l.lender_name,l.loan_id
                                FROM reminders r JOIN loan_installments li ON li.loan_installment_id=r.entity_id
                                JOIN loans l ON l.loan_id=li.loan_id
                                WHERE r.entity_type='LOAN_INSTALLMENT' AND r.status='SCHEDULED' AND r.scheduled_at<=?
                                AND li.status IN ('UPCOMING','DUE','PARTIALLY_PAID','OVERDUE') ORDER BY r.scheduled_at''',(now_dt.isoformat(timespec='seconds'),)).fetchall()
        return [dict(r) for r in rows]
