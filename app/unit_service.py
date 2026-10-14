from __future__ import annotations

import re
from typing import Any

from finance_db import FinanceDB, _now


class UnitService:
    """Unit master with stable internal keys and editable user-facing IDs.

    `unit_id` remains the immutable database key used by sales and other links.
    Stage 11 adds editable display IDs for the unit, parking and storage so an
    existing/pre-sold unit can be placed in the desired numbering scheme
    without breaking foreign-key relationships.
    """

    def __init__(self, db: FinanceDB):
        self.db = db
        self._migrate()

    def _migrate(self):
        with self.db.tx() as con:
            cols={r[1] for r in con.execute('PRAGMA table_info(units)').fetchall()}
            additions={
                'parking_id': 'TEXT',
                'storage_id': 'TEXT',
                'notes': "TEXT NOT NULL DEFAULT ''",
                'display_unit_id': 'TEXT',
                'parking_display_id': 'TEXT',
                'storage_display_id': 'TEXT',
            }
            for c,ddl in additions.items():
                if c not in cols:
                    con.execute(f'ALTER TABLE units ADD COLUMN {c} {ddl}')
            # Backfill editable display IDs without touching stable unit_id.
            rows=con.execute("SELECT unit_id,unit_number,parking,storage,display_unit_id,parking_display_id,storage_display_id FROM units ORDER BY created_at,unit_id").fetchall()
            used_u={str(r['display_unit_id']) for r in rows if r['display_unit_id']}
            used_p={str(r['parking_display_id']) for r in rows if r['parking_display_id']}
            used_s={str(r['storage_display_id']) for r in rows if r['storage_display_id']}
            for r in rows:
                uid=r['display_unit_id'] or self._preferred_code('U', r['unit_number'], used_u)
                pid=r['parking_display_id'] or (self._preferred_code('P', r['parking'] or r['unit_number'], used_p) if str(r['parking'] or '').strip() else '')
                sid=r['storage_display_id'] or (self._preferred_code('S', r['storage'] or r['unit_number'], used_s) if str(r['storage'] or '').strip() else '')
                if uid: used_u.add(uid)
                if pid: used_p.add(pid)
                if sid: used_s.add(sid)
                con.execute("UPDATE units SET display_unit_id=?,parking_display_id=?,storage_display_id=? WHERE unit_id=?",(uid or None,pid or None,sid or None,r['unit_id']))

    @staticmethod
    def _preferred_code(prefix: str, raw: Any, used: set[str]) -> str:
        text=str(raw or '').strip()
        m=re.fullmatch(r'\d+', text)
        if m:
            candidate=f'{prefix}-{int(text):03d}'
            if candidate not in used:
                return candidate
        mx=0
        pat=re.compile(rf'^{re.escape(prefix)}-(\d+)$',re.I)
        for v in used:
            mm=pat.match(str(v or '').strip())
            if mm: mx=max(mx,int(mm.group(1)))
        candidate=f'{prefix}-{mx+1:03d}'
        while candidate in used:
            mx += 1; candidate=f'{prefix}-{mx+1:03d}'
        return candidate

    def _next_code(self, prefix: str, values: list[str]) -> str:
        return self._preferred_code(prefix, '', {str(v) for v in values if v})

    def _next_unit_id(self, con) -> str:
        vals=[r[0] for r in con.execute("SELECT unit_id FROM units WHERE unit_id LIKE 'U-%'").fetchall()]
        return self._next_code('U', vals)

    def _next_aux(self, con, col: str, prefix: str) -> str:
        vals=[r[0] for r in con.execute(f'SELECT {col} FROM units WHERE {col} IS NOT NULL').fetchall()]
        return self._next_code(prefix, vals)

    def _display_values(self, con, col: str) -> set[str]:
        return {str(r[0]) for r in con.execute(f"SELECT {col} FROM units WHERE {col} IS NOT NULL AND TRIM({col})!=''").fetchall()}

    def _validate_display_id(self, con, col: str, value: str, current_unit_id: str|None=None) -> str:
        value=str(value or '').strip().upper()
        if not value:
            return ''
        sql=f"SELECT unit_id FROM units WHERE UPPER({col})=UPPER(?)"
        args=[value]
        if current_unit_id:
            sql += ' AND unit_id!=?'; args.append(current_unit_id)
        if con.execute(sql,args).fetchone():
            labels={'display_unit_id':'ID واحد','parking_display_id':'ID پارکینگ','storage_display_id':'ID انباری'}
            raise ValueError(f"{labels.get(col,col)} «{value}» قبلاً استفاده شده است.")
        return value

    def list_units(self, include_cancelled: bool=False) -> list[dict[str,Any]]:
        where='' if include_cancelled else "WHERE u.status!='CANCELLED'"
        with self.db.read() as con:
            rows=con.execute(f'''SELECT u.*,s.sale_id,s.buyer_name,s.contract_amount,s.status sale_status
                FROM units u LEFT JOIN sales s ON s.unit_id=u.unit_id AND s.status!='CANCELLED'
                {where} ORDER BY CASE WHEN CAST(u.floor AS INTEGER) IS NULL THEN 999 ELSE CAST(u.floor AS INTEGER) END,
                u.floor, CAST(u.unit_number AS INTEGER), u.unit_number''').fetchall()
        return [dict(r) for r in rows]

    def add_unit(self, *, floor:str, unit_number:str, area:float=0, parking:str='', storage:str='',
                 project_name:str='', block_name:str='', notes:str='', display_unit_id:str='',
                 parking_display_id:str='', storage_display_id:str='') -> dict[str,Any]:
        now=_now(); unit_number=str(unit_number).strip()
        if not unit_number: raise ValueError('شماره واحد الزامی است.')
        with self.db.tx() as con:
            dup=con.execute("SELECT unit_id FROM units WHERE unit_number=? AND COALESCE(block_name,'')=? AND status!='CANCELLED'",(unit_number,block_name.strip())).fetchone()
            if dup: raise ValueError('این شماره واحد قبلاً تعریف شده است.')
            uid=self._next_unit_id(con)
            pid=self._next_aux(con,'parking_id','P') if parking.strip() else None
            sid=self._next_aux(con,'storage_id','S') if storage.strip() else None
            du=display_unit_id.strip().upper() if display_unit_id else self._preferred_code('U',unit_number,self._display_values(con,'display_unit_id'))
            dp=parking_display_id.strip().upper() if parking_display_id else (self._preferred_code('P',parking or unit_number,self._display_values(con,'parking_display_id')) if parking.strip() else '')
            ds=storage_display_id.strip().upper() if storage_display_id else (self._preferred_code('S',storage or unit_number,self._display_values(con,'storage_display_id')) if storage.strip() else '')
            du=self._validate_display_id(con,'display_unit_id',du)
            dp=self._validate_display_id(con,'parking_display_id',dp) if dp else ''
            ds=self._validate_display_id(con,'storage_display_id',ds) if ds else ''
            con.execute('''INSERT INTO units(unit_id,project_name,block_name,unit_number,floor,area,parking,storage,status,created_at,updated_at,parking_id,storage_id,notes,display_unit_id,parking_display_id,storage_display_id)
                           VALUES(?,?,?,?,?,?,?,?, 'AVAILABLE', ?,?,?,?,?,?,?,?)''',
                        (uid,project_name.strip(),block_name.strip(),unit_number,floor.strip(),float(area or 0),parking.strip(),storage.strip(),now,now,pid,sid,notes.strip(),du or None,dp or None,ds or None))
            self.db._enqueue_sync(con,'unit',uid,'CREATE')
        return self.get_unit(uid)

    def get_unit(self, unit_id:str)->dict[str,Any]:
        with self.db.read() as con:r=con.execute('SELECT * FROM units WHERE unit_id=?',(unit_id,)).fetchone()
        if not r: raise KeyError(unit_id)
        return dict(r)

    def update_unit(self, unit_id:str, **changes)->dict[str,Any]:
        allowed={'floor','unit_number','area','parking','storage','project_name','block_name','notes','status','display_unit_id','parking_display_id','storage_display_id'}
        fields=[]; vals=[]
        with self.db.tx() as con:
            current=con.execute('SELECT * FROM units WHERE unit_id=?',(unit_id,)).fetchone()
            if not current: raise KeyError(unit_id)
            for k,v in changes.items():
                if k not in allowed: continue
                if k=='area': v=float(str(v or 0).replace(',',''))
                if k in ('display_unit_id','parking_display_id','storage_display_id'):
                    v=self._validate_display_id(con,k,str(v or ''),unit_id) or None
                fields.append(f'{k}=?'); vals.append(v)
            if fields:
                fields.append('updated_at=?'); vals.append(_now()); vals.append(unit_id)
                con.execute(f"UPDATE units SET {','.join(fields)} WHERE unit_id=?",vals)
                self.db._enqueue_sync(con,'unit',unit_id,'UPDATE')
        return self.get_unit(unit_id)

    def cancel_unit(self, unit_id:str):
        with self.db.tx() as con:
            sold=con.execute("SELECT 1 FROM sales WHERE unit_id=? AND status!='CANCELLED'",(unit_id,)).fetchone()
            if sold: raise ValueError('واحد دارای قرارداد فروش است و قابل حذف نیست.')
            con.execute("UPDATE units SET status='CANCELLED',updated_at=? WHERE unit_id=?",(_now(),unit_id))
            self.db._enqueue_sync(con,'unit',unit_id,'UPDATE')

    def bulk_create(self, *, floor:str, count:int, start_number:int, default_area:float=0,
                    project_name:str='', block_name:str='') -> list[dict[str,Any]]:
        out=[]
        for i in range(int(count)):
            n=start_number+i
            out.append(self.add_unit(floor=floor,unit_number=str(n),area=default_area,
                parking=str(n),storage=str(n),project_name=project_name,block_name=block_name))
        return out

    def summary(self)->dict[str,Any]:
        with self.db.read() as con:
            r=con.execute("SELECT COUNT(*) c,COALESCE(SUM(area),0) area,SUM(CASE WHEN status='SOLD' THEN 1 ELSE 0 END) sold,COALESCE(SUM(CASE WHEN status='SOLD' THEN area ELSE 0 END),0) sold_area FROM units WHERE status!='CANCELLED'").fetchone()
        return {'count':int(r['c'] or 0),'area':float(r['area'] or 0),'sold':int(r['sold'] or 0),'sold_area':float(r['sold_area'] or 0)}
