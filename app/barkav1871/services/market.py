from __future__ import annotations

import json, shutil, uuid
from datetime import datetime
from pathlib import Path
from typing import Any


def _now(): return datetime.now().isoformat(timespec='seconds')
def _id(prefix): return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"
def _int(v):
    try:return int(float(str(v or 0).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')).replace(',','').replace('،','')))
    except Exception:return 0

class MarketService:
    """Canonical contractor/supplier master and commercial document layer.

    Tables are additive and deliberately separate from the accounting source tables.
    Payments may reference an existing accounting entity later; this service never
    silently posts money to the project ledger.
    """
    def __init__(self, db, base_dir):
        self.db=db;self.base_dir=Path(base_dir);self.files_dir=self.base_dir/'data'/'market_files';self.files_dir.mkdir(parents=True,exist_ok=True);self._migrate()

    def _migrate(self):
        with self.db.tx() as con:
            con.executescript('''
            CREATE TABLE IF NOT EXISTS market_entities(
              entity_id TEXT PRIMARY KEY,entity_type TEXT NOT NULL,first_name TEXT,last_name TEXT,company_name TEXT,
              national_id TEXT,foreign_id TEXT,category TEXT,phone TEXT,city TEXT,address TEXT,notes TEXT,
              active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_market_entities_type ON market_entities(entity_type,active);
            CREATE TABLE IF NOT EXISTS contractor_contracts(
              contract_id TEXT PRIMARY KEY,contractor_id TEXT NOT NULL REFERENCES market_entities(entity_id),contract_date_shamsi TEXT,
              subject TEXT,phase_no INTEGER,duration_days INTEGER NOT NULL DEFAULT 0,contract_amount INTEGER NOT NULL DEFAULT 0,
              start_date_shamsi TEXT,end_date_shamsi TEXT,status TEXT NOT NULL DEFAULT 'ACTIVE',notes TEXT,
              created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS market_files(
              file_id TEXT PRIMARY KEY,entity_id TEXT,contract_id TEXT,statement_id TEXT,invoice_id TEXT,file_kind TEXT,title TEXT,
              local_path TEXT,original_name TEXT,notes TEXT,created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS contractor_statements(
              statement_id TEXT PRIMARY KEY,contract_id TEXT NOT NULL REFERENCES contractor_contracts(contract_id),statement_no TEXT,
              statement_date_shamsi TEXT,gross_amount INTEGER NOT NULL DEFAULT 0,deductions INTEGER NOT NULL DEFAULT 0,
              net_amount INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'DRAFT',notes TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS contractor_statement_items(
              item_id TEXT PRIMARY KEY,statement_id TEXT NOT NULL REFERENCES contractor_statements(statement_id),description TEXT,
              unit TEXT,contract_rate INTEGER NOT NULL DEFAULT 0,quantity REAL NOT NULL DEFAULT 0,total INTEGER NOT NULL DEFAULT 0,
              source TEXT,sort_order INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS supplier_invoices(
              invoice_id TEXT PRIMARY KEY,supplier_id TEXT NOT NULL REFERENCES market_entities(entity_id),invoice_no TEXT,invoice_date_shamsi TEXT,
              invoice_amount INTEGER NOT NULL DEFAULT 0,final_amount INTEGER NOT NULL DEFAULT 0,discount_amount INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL DEFAULT 'OPEN',notes TEXT,linked_expense_id TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS supplier_invoice_items(
              item_id TEXT PRIMARY KEY,invoice_id TEXT NOT NULL REFERENCES supplier_invoices(invoice_id),description TEXT,unit TEXT,
              quantity REAL NOT NULL DEFAULT 0,unit_rate INTEGER NOT NULL DEFAULT 0,total INTEGER NOT NULL DEFAULT 0,
              price_id TEXT,sort_order INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS market_payments(
              market_payment_id TEXT PRIMARY KEY,entity_id TEXT NOT NULL REFERENCES market_entities(entity_id),contract_id TEXT,statement_id TEXT,
              invoice_id TEXT,payment_date_shamsi TEXT,amount INTEGER NOT NULL DEFAULT 0,method TEXT,from_account TEXT,to_account TEXT,
              receiver_account_owner TEXT,tracking_no TEXT,document_path TEXT,linked_payment_id TEXT,linked_transaction_id TEXT,
              notes TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS market_ratings(
              entity_id TEXT PRIMARY KEY REFERENCES market_entities(entity_id),quality REAL NOT NULL DEFAULT 0,price REAL NOT NULL DEFAULT 0,
              punctuality REAL NOT NULL DEFAULT 0,speed REAL NOT NULL DEFAULT 0,cooperation REAL NOT NULL DEFAULT 0,
              document_quality REAL NOT NULL DEFAULT 0,financial_history REAL NOT NULL DEFAULT 0,notes TEXT,updated_at TEXT NOT NULL
            );
            ''')

    def list_entities(self, entity_type:str|None=None):
        q="SELECT * FROM market_entities WHERE active=1";args=[]
        if entity_type:q+=' AND entity_type=?';args.append(entity_type.upper())
        q+=' ORDER BY COALESCE(company_name,last_name,first_name),first_name'
        with self.db.read() as con:rows=[dict(r) for r in con.execute(q,args).fetchall()]
        for r in rows:
            r.update(self.entity_financial_summary(r['entity_id']))
            r['rating_total']=self.rating_total(r['entity_id'])
        return rows

    def get_entity(self,eid):
        with self.db.read() as con:r=con.execute('SELECT * FROM market_entities WHERE entity_id=?',(eid,)).fetchone()
        return dict(r) if r else None

    def save_entity(self,data:dict[str,Any],eid:str|None=None):
        eid=eid or _id('MKT');now=_now();typ=str(data.get('entity_type') or 'SUPPLIER').upper()
        vals=(eid,typ,str(data.get('first_name') or ''),str(data.get('last_name') or ''),str(data.get('company_name') or ''),str(data.get('national_id') or ''),str(data.get('foreign_id') or ''),str(data.get('category') or ''),str(data.get('phone') or ''),str(data.get('city') or ''),str(data.get('address') or ''),str(data.get('notes') or ''),now,now)
        with self.db.tx() as con:
            con.execute('''INSERT INTO market_entities(entity_id,entity_type,first_name,last_name,company_name,national_id,foreign_id,category,phone,city,address,notes,active,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?,?) ON CONFLICT(entity_id) DO UPDATE SET entity_type=excluded.entity_type,first_name=excluded.first_name,last_name=excluded.last_name,company_name=excluded.company_name,national_id=excluded.national_id,foreign_id=excluded.foreign_id,category=excluded.category,phone=excluded.phone,city=excluded.city,address=excluded.address,notes=excluded.notes,active=1,updated_at=excluded.updated_at''',vals)
        return eid

    def delete_entity(self,eid):
        with self.db.tx() as con:con.execute('UPDATE market_entities SET active=0,updated_at=? WHERE entity_id=?',(_now(),eid))

    def list_contracts(self,contractor_id:str|None=None):
        q='SELECT c.*,e.first_name,e.last_name,e.company_name,e.phone FROM contractor_contracts c JOIN market_entities e ON e.entity_id=c.contractor_id WHERE c.status<>\'DELETED\'';args=[]
        if contractor_id:q+=' AND c.contractor_id=?';args.append(contractor_id)
        q+=' ORDER BY c.contract_date_shamsi DESC,c.created_at DESC'
        with self.db.read() as con:rows=[dict(r) for r in con.execute(q,args).fetchall()]
        for r in rows:
            sm=self.contract_financial_summary(r['contract_id']);r.update(sm)
        return rows

    def save_contract(self,data,cid=None):
        cid=cid or _id('CTR');now=_now()
        with self.db.tx() as con:
            con.execute('''INSERT INTO contractor_contracts(contract_id,contractor_id,contract_date_shamsi,subject,phase_no,duration_days,contract_amount,start_date_shamsi,end_date_shamsi,status,notes,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,'ACTIVE',?,?,?) ON CONFLICT(contract_id) DO UPDATE SET contractor_id=excluded.contractor_id,contract_date_shamsi=excluded.contract_date_shamsi,subject=excluded.subject,phase_no=excluded.phase_no,duration_days=excluded.duration_days,contract_amount=excluded.contract_amount,start_date_shamsi=excluded.start_date_shamsi,end_date_shamsi=excluded.end_date_shamsi,notes=excluded.notes,updated_at=excluded.updated_at''',
            (cid,data.get('contractor_id'),data.get('contract_date_shamsi') or '',data.get('subject') or '',int(data.get('phase_no') or 0),int(data.get('duration_days') or 0),_int(data.get('contract_amount')),data.get('start_date_shamsi') or '',data.get('end_date_shamsi') or '',data.get('notes') or '',now,now))
        return cid

    def add_file(self,source,*,entity_id='',contract_id='',statement_id='',invoice_id='',file_kind='OTHER',title='',notes=''):
        src=Path(source);fid=_id('FILE');dst=self.files_dir/f'{fid}_{src.name}';shutil.copy2(src,dst)
        with self.db.tx() as con:con.execute('INSERT INTO market_files(file_id,entity_id,contract_id,statement_id,invoice_id,file_kind,title,local_path,original_name,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(fid,entity_id,contract_id,statement_id,invoice_id,file_kind,title or src.name,str(dst),src.name,notes,_now()))
        return fid

    def list_files(self,*,entity_id='',contract_id='',statement_id='',invoice_id=''):
        clauses=[];args=[]
        for k,v in [('entity_id',entity_id),('contract_id',contract_id),('statement_id',statement_id),('invoice_id',invoice_id)]:
            if v:clauses.append(k+'=?');args.append(v)
        q='SELECT * FROM market_files'+((' WHERE '+' AND '.join(clauses)) if clauses else '')+' ORDER BY created_at DESC'
        with self.db.read() as con:return [dict(r) for r in con.execute(q,args).fetchall()]

    def save_statement(self,data,sid=None):
        sid=sid or _id('STMT');now=_now();gross=_int(data.get('gross_amount'));ded=_int(data.get('deductions'));net=_int(data.get('net_amount')) or max(gross-ded,0)
        with self.db.tx() as con:
            con.execute('''INSERT INTO contractor_statements(statement_id,contract_id,statement_no,statement_date_shamsi,gross_amount,deductions,net_amount,status,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,'ACTIVE',?,?,?)
            ON CONFLICT(statement_id) DO UPDATE SET statement_no=excluded.statement_no,statement_date_shamsi=excluded.statement_date_shamsi,gross_amount=excluded.gross_amount,deductions=excluded.deductions,net_amount=excluded.net_amount,notes=excluded.notes,updated_at=excluded.updated_at''',(sid,data.get('contract_id'),data.get('statement_no') or '',data.get('statement_date_shamsi') or '',gross,ded,net,data.get('notes') or '',now,now))
        return sid

    def list_statements(self,contract_id):
        with self.db.read() as con:rows=[dict(r) for r in con.execute("SELECT * FROM contractor_statements WHERE contract_id=? AND status<>'DELETED' ORDER BY statement_date_shamsi,created_at",(contract_id,)).fetchall()]
        for r in rows:
            paid=self._sum_payments(statement_id=r['statement_id']);r['paid_amount']=paid;r['balance']=int(r['net_amount'])-paid
        return rows

    def save_statement_item(self,data,item_id=None):
        item_id=item_id or _id('STI');now=_now();qty=float(data.get('quantity') or 0);rate=_int(data.get('contract_rate'));total=_int(data.get('total')) or int(round(qty*rate))
        with self.db.tx() as con:
            con.execute('''INSERT INTO contractor_statement_items(item_id,statement_id,description,unit,contract_rate,quantity,total,source,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(item_id) DO UPDATE SET description=excluded.description,unit=excluded.unit,contract_rate=excluded.contract_rate,quantity=excluded.quantity,total=excluded.total,source=excluded.source,updated_at=excluded.updated_at''',(item_id,data.get('statement_id'),data.get('description') or '',data.get('unit') or '',rate,qty,total,data.get('source') or 'MANUAL',int(data.get('sort_order') or 0),now,now))
        return item_id

    def list_statement_items(self,sid):
        with self.db.read() as con:return [dict(r) for r in con.execute('SELECT * FROM contractor_statement_items WHERE statement_id=? ORDER BY sort_order,created_at',(sid,)).fetchall()]

    def save_invoice(self,data,iid=None):
        iid=iid or _id('INV');now=_now();inv=_int(data.get('invoice_amount'));final=_int(data.get('final_amount')) or inv;disc=_int(data.get('discount_amount')) or max(inv-final,0)
        with self.db.tx() as con:
            con.execute('''INSERT INTO supplier_invoices(invoice_id,supplier_id,invoice_no,invoice_date_shamsi,invoice_amount,final_amount,discount_amount,status,notes,linked_expense_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?)
            ON CONFLICT(invoice_id) DO UPDATE SET invoice_no=excluded.invoice_no,invoice_date_shamsi=excluded.invoice_date_shamsi,invoice_amount=excluded.invoice_amount,final_amount=excluded.final_amount,discount_amount=excluded.discount_amount,notes=excluded.notes,updated_at=excluded.updated_at''',(iid,data.get('supplier_id'),data.get('invoice_no') or '',data.get('invoice_date_shamsi') or '',inv,final,disc,data.get('notes') or '',data.get('linked_expense_id') or '',now,now))
        return iid

    def list_invoices(self,supplier_id):
        with self.db.read() as con:rows=[dict(r) for r in con.execute("SELECT * FROM supplier_invoices WHERE supplier_id=? AND status<>'DELETED' ORDER BY invoice_date_shamsi DESC,created_at DESC",(supplier_id,)).fetchall()]
        for r in rows:
            paid=self._sum_payments(invoice_id=r['invoice_id']);r['paid_amount']=paid;r['balance']=int(r['final_amount'])-paid
        return rows

    def save_invoice_item(self,data,item_id=None):
        item_id=item_id or _id('INI');now=_now();qty=float(data.get('quantity') or 0);rate=_int(data.get('unit_rate'));total=_int(data.get('total')) or int(round(qty*rate))
        with self.db.tx() as con:
            con.execute('''INSERT INTO supplier_invoice_items(item_id,invoice_id,description,unit,quantity,unit_rate,total,price_id,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(item_id) DO UPDATE SET description=excluded.description,unit=excluded.unit,quantity=excluded.quantity,unit_rate=excluded.unit_rate,total=excluded.total,price_id=excluded.price_id,updated_at=excluded.updated_at''',(item_id,data.get('invoice_id'),data.get('description') or '',data.get('unit') or '',qty,rate,total,data.get('price_id') or '',int(data.get('sort_order') or 0),now,now))
        return item_id

    def list_invoice_items(self,iid):
        with self.db.read() as con:return [dict(r) for r in con.execute('SELECT * FROM supplier_invoice_items WHERE invoice_id=? ORDER BY sort_order,created_at',(iid,)).fetchall()]

    def save_payment(self,data,pid=None):
        pid=pid or _id('MPY');now=_now()
        with self.db.tx() as con:
            con.execute('''INSERT INTO market_payments(market_payment_id,entity_id,contract_id,statement_id,invoice_id,payment_date_shamsi,amount,method,from_account,to_account,receiver_account_owner,tracking_no,document_path,linked_payment_id,linked_transaction_id,notes,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(market_payment_id) DO UPDATE SET payment_date_shamsi=excluded.payment_date_shamsi,amount=excluded.amount,method=excluded.method,from_account=excluded.from_account,to_account=excluded.to_account,receiver_account_owner=excluded.receiver_account_owner,tracking_no=excluded.tracking_no,notes=excluded.notes,updated_at=excluded.updated_at''',
            (pid,data.get('entity_id'),data.get('contract_id') or '',data.get('statement_id') or '',data.get('invoice_id') or '',data.get('payment_date_shamsi') or '',_int(data.get('amount')),data.get('method') or '',data.get('from_account') or 'تنخواه',data.get('to_account') or '',data.get('receiver_account_owner') or '',data.get('tracking_no') or '',data.get('document_path') or '',data.get('linked_payment_id') or '',data.get('linked_transaction_id') or '',data.get('notes') or '',now,now))
        return pid

    def list_payments(self,entity_id):
        with self.db.read() as con:return [dict(r) for r in con.execute('SELECT * FROM market_payments WHERE entity_id=? ORDER BY payment_date_shamsi DESC,created_at DESC',(entity_id,)).fetchall()]

    def _sum_payments(self,**kw):
        clauses=[];args=[]
        for k,v in kw.items():
            if v:clauses.append(k+'=?');args.append(v)
        if not clauses:return 0
        with self.db.read() as con:r=con.execute('SELECT COALESCE(SUM(amount),0) FROM market_payments WHERE '+' AND '.join(clauses),args).fetchone()
        return int(r[0] or 0)

    def contract_financial_summary(self,cid):
        sts=[]
        with self.db.read() as con:
            sts=[dict(r) for r in con.execute("SELECT * FROM contractor_statements WHERE contract_id=? AND status<>'DELETED'",(cid,)).fetchall()]
        accrued=sum(int(x.get('net_amount') or 0) for x in sts);paid=self._sum_payments(contract_id=cid);return {'statement_total':accrued,'paid_total':paid,'balance':accrued-paid}

    def entity_financial_summary(self,eid):
        e=self.get_entity(eid) if False else None
        with self.db.read() as con:
            row=con.execute('SELECT entity_type FROM market_entities WHERE entity_id=?',(eid,)).fetchone();typ=row[0] if row else ''
            if typ=='CONTRACTOR':
                total=con.execute("SELECT COALESCE(SUM(net_amount),0) FROM contractor_statements s JOIN contractor_contracts c ON c.contract_id=s.contract_id WHERE c.contractor_id=? AND s.status<>'DELETED'",(eid,)).fetchone()[0]
            else:
                total=con.execute("SELECT COALESCE(SUM(final_amount),0) FROM supplier_invoices WHERE supplier_id=? AND status<>'DELETED'",(eid,)).fetchone()[0]
        paid=self._sum_payments(entity_id=eid);return {'document_total':int(total or 0),'paid_total':paid,'balance':int(total or 0)-paid}

    def save_rating(self,eid,data):
        vals=[float(data.get(k) or 0) for k in ('quality','price','punctuality','speed','cooperation','document_quality','financial_history')]
        with self.db.tx() as con:con.execute('''INSERT INTO market_ratings(entity_id,quality,price,punctuality,speed,cooperation,document_quality,financial_history,notes,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(entity_id) DO UPDATE SET quality=excluded.quality,price=excluded.price,punctuality=excluded.punctuality,speed=excluded.speed,cooperation=excluded.cooperation,document_quality=excluded.document_quality,financial_history=excluded.financial_history,notes=excluded.notes,updated_at=excluded.updated_at''',(eid,*vals,data.get('notes') or '',_now()))
    def get_rating(self,eid):
        with self.db.read() as con:r=con.execute('SELECT * FROM market_ratings WHERE entity_id=?',(eid,)).fetchone()
        return dict(r) if r else {'entity_id':eid}
    def rating_total(self,eid):
        r=self.get_rating(eid);vals=[float(r.get(k) or 0) for k in ('quality','price','punctuality','speed','cooperation','document_quality','financial_history')];return round(sum(vals)/len(vals),1) if any(vals) else 0.0
