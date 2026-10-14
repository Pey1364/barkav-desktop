from __future__ import annotations

from construction_cost_rules187 import is_land_phase, manager_fee, construction_with_manager

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from finance_db import FinanceDB, _id, _now
from loan_service import LoanService
from revenue_service import RevenueService
from xlsx_simple import parse_phase_budget


def norm_fa(value: str) -> str:
    s=str(value or '').strip().translate(str.maketrans('يىكۀةؤإأٱ٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹','ییکههوااا01234567890123456789'))
    s=s.replace('\u200c',' ').replace('\u200f',' ').replace('\u200e',' ')
    return re.sub(r'\s+',' ',s).strip().lower()


def stable_id(prefix: str, *parts: str) -> str:
    raw='|'.join(norm_fa(p) for p in parts).encode('utf-8')
    return f"{prefix}-{hashlib.sha1(raw).hexdigest()[:12].upper()}"


@dataclass(frozen=True)
class ForecastSummary:
    initial_budget: int
    current_budget: int
    actual_expenses: int
    cost_performance_factor: float
    inflation_factor: float
    forecast_base_cost: int
    forecast_land_cost: int
    forecast_construction_cost: int
    forecast_manager_fee: int
    forecast_total_cost: int
    construction_cost_per_gross_m2: int
    construction_cost_per_saleable_m2: int
    total_cost_per_gross_m2: int
    total_cost_per_saleable_m2: int
    projected_revenue: int
    projected_profit: int
    projected_profit_percent: float
    suggested_remaining_sale_price_per_m2: int
    funding_gap: int
    presale_area_needed_m2: float
    remaining_saleable_area_m2: float
    end_sale_price_per_m2: int
    budget_coverage_percent: float


class BudgetService:
    def __init__(self, db: FinanceDB, base_dir: str | Path):
        self.db=db; self.base_dir=Path(base_dir); self.revenue=RevenueService(db); self.loans=LoanService(db)
        self._migrate(); self._seed_master_if_empty()

    def _migrate(self) -> None:
        with self.db.tx() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS construction_phases (
                    phase_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS construction_activities (
                    activity_id TEXT PRIMARY KEY,
                    phase_id TEXT NOT NULL REFERENCES construction_phases(phase_id),
                    name TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(phase_id,name)
                );
                CREATE TABLE IF NOT EXISTS budget_versions (
                    version_id TEXT PRIMARY KEY,
                    version_no INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    source_file TEXT,
                    total_estimate INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS activity_estimates (
                    version_id TEXT NOT NULL REFERENCES budget_versions(version_id),
                    activity_id TEXT NOT NULL REFERENCES construction_activities(activity_id),
                    estimate_amount INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(version_id,activity_id)
                );
                CREATE TABLE IF NOT EXISTS report_settings (
                    setting_id TEXT PRIMARY KEY,
                    gross_area REAL NOT NULL DEFAULT 0,
                    saleable_area REAL NOT NULL DEFAULT 0,
                    unit_count INTEGER NOT NULL DEFAULT 0,
                    unit_areas_json TEXT NOT NULL DEFAULT '[]',
                    monthly_inflation REAL NOT NULL DEFAULT 0,
                    remaining_months INTEGER NOT NULL DEFAULT 0,
                    presale_price_per_m2 INTEGER NOT NULL DEFAULT 0,
                    end_sale_price_override INTEGER,
                    unbudgeted_misc INTEGER NOT NULL DEFAULT 0,
                    target_profit_percent REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
            ''')
            cols={r[1] for r in con.execute('PRAGMA table_info(expenses)').fetchall()}
            if 'activity_id' not in cols: con.execute('ALTER TABLE expenses ADD COLUMN activity_id TEXT')
            if 'activity_name' not in cols: con.execute('ALTER TABLE expenses ADD COLUMN activity_name TEXT')
            if 'payer_name' not in cols: con.execute('ALTER TABLE expenses ADD COLUMN payer_name TEXT')
            now=_now()
            con.execute("INSERT OR IGNORE INTO report_settings(setting_id,updated_at) VALUES('MAIN',?)",(now,))

    def _seed_master_if_empty(self) -> None:
        with self.db.read() as con:
            n=int(con.execute('SELECT COUNT(*) FROM construction_phases').fetchone()[0] or 0)
        if n: return

        # New projects prefer the current 32-phase Peymaan workbook.  The workbook
        # is the budget taxonomy/source; a later workbook can be imported from the
        # existing GUI button as a new immutable budget version.
        current=self.base_dir/'phase_budget_current.xlsx'
        if not current.exists(): current=Path(__file__).resolve().parent/'phase_budget_current.xlsx'
        if current.exists():
            try:
                data=parse_phase_budget(current)
                self._upsert_master(data)
                estimates=[]
                for p in data:
                    for a in p.get('activities',[]):
                        estimates.append((stable_id('ACT',p['phase'],a['name']),int(a.get('estimate') or 0)))
                self._create_budget_version('نسخه اولیه اکسل برآورد ۳۲ فاز', str(current), estimates)
                return
            except Exception:
                # Fall back to the legacy JSON/template so a malformed optional
                # workbook never prevents Peymaan from starting.
                pass

        path=self.base_dir/'phase_master.json'
        if not path.exists():
            path=Path(__file__).resolve().parent/'phase_master.json'
        if not path.exists(): return
        data=json.loads(path.read_text(encoding='utf-8'))
        self._upsert_master(data)
        estimates=[]
        for p in data:
            for a in p.get('activities',[]): estimates.append((stable_id('ACT',p['phase'],a['name']),int(a.get('estimate') or 0)))
        template=self.base_dir/'phase_budget_template.xlsx'
        if not template.exists(): template=Path(__file__).resolve().parent/'phase_budget_template.xlsx'
        self._create_budget_version('نسخه اولیه قالب', str(template), estimates)

    def _upsert_master(self, phases: list[dict[str,Any]]) -> None:
        now=_now()
        with self.db.tx() as con:
            for pi,p in enumerate(phases,1):
                pname=str(p['phase']).strip(); pid=stable_id('PHASE',pname)
                con.execute('''INSERT INTO construction_phases(phase_id,name,sort_order,created_at,updated_at) VALUES(?,?,?,?,?)
                               ON CONFLICT(phase_id) DO UPDATE SET name=excluded.name,sort_order=excluded.sort_order,active=1,updated_at=excluded.updated_at''',(pid,pname,pi,now,now))
                for ai,a in enumerate(p.get('activities',[]),1):
                    aname=str(a['name']).strip(); aid=stable_id('ACT',pname,aname)
                    con.execute('''INSERT INTO construction_activities(activity_id,phase_id,name,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?)
                                   ON CONFLICT(activity_id) DO UPDATE SET phase_id=excluded.phase_id,name=excluded.name,sort_order=excluded.sort_order,active=1,updated_at=excluded.updated_at''',(aid,pid,aname,ai,now,now))

    def _create_budget_version(self,title:str,source_file:str,estimates:list[tuple[str,int]]) -> dict[str,Any]:
        now=_now(); vid=_id('BUDGET')
        merged: dict[str,int] = {}
        for aid,val in estimates:
            merged[aid] = merged.get(aid,0) + max(0,int(val))
        with self.db.tx() as con:
            no=int(con.execute('SELECT COALESCE(MAX(version_no),0)+1 FROM budget_versions').fetchone()[0])
            total=sum(merged.values())
            con.execute('INSERT INTO budget_versions(version_id,version_no,title,source_file,total_estimate,created_at) VALUES(?,?,?,?,?,?)',(vid,no,title,source_file,total,now))
            con.executemany('INSERT INTO activity_estimates(version_id,activity_id,estimate_amount) VALUES(?,?,?)',[(vid,aid,val) for aid,val in merged.items()])
        return {'version_id':vid,'version_no':no,'title':title,'total_estimate':total}

    def import_budget_xlsx(self,path:str|Path,title:str='') -> dict[str,Any]:
        phases=parse_phase_budget(path); self._upsert_master(phases); estimates=[]
        for p in phases:
            for a in p['activities']:
                estimates.append((stable_id('ACT',p['phase'],a['name']),int(a.get('estimate') or 0)))
        return self._create_budget_version(title.strip() or f'برآورد {Path(path).stem}',str(Path(path).resolve()),estimates)

    def latest_version(self) -> Optional[dict[str,Any]]:
        with self.db.read() as con:
            r=con.execute('SELECT * FROM budget_versions ORDER BY version_no DESC LIMIT 1').fetchone()
        return dict(r) if r else None

    def first_version(self) -> Optional[dict[str,Any]]:
        with self.db.read() as con:
            r=con.execute('SELECT * FROM budget_versions ORDER BY version_no ASC LIMIT 1').fetchone()
        return dict(r) if r else None

    def list_versions(self)->list[dict[str,Any]]:
        with self.db.read() as con: rows=con.execute('SELECT * FROM budget_versions ORDER BY version_no DESC').fetchall()
        return [dict(r) for r in rows]

    def list_phases(self)->list[dict[str,Any]]:
        with self.db.read() as con: rows=con.execute('SELECT * FROM construction_phases WHERE active=1 ORDER BY sort_order,name').fetchall()
        return [dict(r) for r in rows]

    def list_activities(self,phase_id:str|None=None)->list[dict[str,Any]]:
        where='WHERE a.active=1'; args=[]
        if phase_id: where+=' AND a.phase_id=?'; args.append(phase_id)
        with self.db.read() as con:
            rows=con.execute(f'''SELECT a.*,p.name phase_name FROM construction_activities a JOIN construction_phases p ON p.phase_id=a.phase_id {where} ORDER BY p.sort_order,a.sort_order,a.name''',args).fetchall()
        return [dict(r) for r in rows]

    def classify_expense(self,expense_id:str,phase_id:str,activity_id:str,payer_name:str='',receiver_name:str='') -> None:
        with self.db.read() as con:
            p=con.execute('SELECT name FROM construction_phases WHERE phase_id=?',(phase_id,)).fetchone(); a=con.execute('SELECT name FROM construction_activities WHERE activity_id=? AND phase_id=?',(activity_id,phase_id)).fetchone()
        if not p or not a: raise ValueError('فاز یا فعالیت نامعتبر است.')
        with self.db.tx() as con:
            con.execute('UPDATE expenses SET construction_stage=?,activity_id=?,activity_name=?,payer_name=?,vendor_name=COALESCE(NULLIF(?,\'\'),vendor_name),updated_at=? WHERE expense_id=?',(p['name'],activity_id,a['name'],payer_name.strip(),receiver_name.strip(),_now(),expense_id))
            tx=con.execute("SELECT transaction_id FROM transactions WHERE expense_id=? AND status='POSTED' AND deleted_at IS NULL ORDER BY created_at LIMIT 1",(expense_id,)).fetchone()
            if tx:
                con.execute('UPDATE transactions SET payer_name=COALESCE(NULLIF(?,\'\'),payer_name),receiver_name=COALESCE(NULLIF(?,\'\'),receiver_name),updated_at=?,sync_status=\'PENDING\' WHERE transaction_id=?',(payer_name.strip(),receiver_name.strip(),_now(),tx['transaction_id']))

    def _latest_version_id(self) -> str:
        v=self.latest_version()
        if not v:
            raise ValueError('نسخه برآورد وجود ندارد.')
        return str(v['version_id'])

    def update_activity_estimate(self, activity_id: str, amount: int) -> dict[str,Any]:
        amount=max(0,int(amount or 0)); vid=self._latest_version_id()
        with self.db.tx() as con:
            a=con.execute('SELECT activity_id FROM construction_activities WHERE activity_id=? AND active=1',(activity_id,)).fetchone()
            if not a: raise ValueError('فعالیت پیدا نشد.')
            con.execute('''INSERT INTO activity_estimates(version_id,activity_id,estimate_amount) VALUES(?,?,?)
                           ON CONFLICT(version_id,activity_id) DO UPDATE SET estimate_amount=excluded.estimate_amount''',(vid,activity_id,amount))
            total=int(con.execute('SELECT COALESCE(SUM(estimate_amount),0) FROM activity_estimates WHERE version_id=?',(vid,)).fetchone()[0] or 0)
            con.execute('UPDATE budget_versions SET total_estimate=? WHERE version_id=?',(total,vid))
        return {'activity_id':activity_id,'estimate_amount':amount,'total_estimate':total}

    def add_phase_after(self, after_phase_id: str|None, name: str) -> dict[str,Any]:
        name=str(name or '').strip()
        if not name: raise ValueError('نام فاز الزامی است.')
        now=_now()
        with self.db.tx() as con:
            dup=con.execute('SELECT phase_id FROM construction_phases WHERE name=? AND active=1',(name,)).fetchone()
            if dup: raise ValueError('فازی با این نام وجود دارد.')
            if after_phase_id:
                r=con.execute('SELECT sort_order FROM construction_phases WHERE phase_id=?',(after_phase_id,)).fetchone()
                pos=int(r['sort_order'] if r else con.execute('SELECT COALESCE(MAX(sort_order),0) FROM construction_phases').fetchone()[0]) + 1
            else:
                pos=int(con.execute('SELECT COALESCE(MAX(sort_order),0)+1 FROM construction_phases').fetchone()[0])
            con.execute('UPDATE construction_phases SET sort_order=sort_order+1 WHERE sort_order>=?',(pos,))
            pid=_id('PHASE')
            con.execute('INSERT INTO construction_phases(phase_id,name,sort_order,active,created_at,updated_at) VALUES(?,?,?,1,?,?)',(pid,name,pos,now,now))
        return {'phase_id':pid,'name':name,'sort_order':pos}

    def rename_phase(self, phase_id: str, new_name: str) -> None:
        new_name=str(new_name or '').strip()
        if not new_name: raise ValueError('نام جدید فاز خالی است.')
        now=_now()
        with self.db.tx() as con:
            r=con.execute('SELECT name FROM construction_phases WHERE phase_id=? AND active=1',(phase_id,)).fetchone()
            if not r: raise ValueError('فاز پیدا نشد.')
            dup=con.execute('SELECT phase_id FROM construction_phases WHERE name=? AND active=1 AND phase_id!=?',(new_name,phase_id)).fetchone()
            if dup: raise ValueError('فازی با این نام وجود دارد.')
            aids=[x[0] for x in con.execute('SELECT activity_id FROM construction_activities WHERE phase_id=?',(phase_id,)).fetchall()]
            con.execute('UPDATE construction_phases SET name=?,updated_at=? WHERE phase_id=?',(new_name,now,phase_id))
            if aids:
                q=','.join('?' for _ in aids)
                con.execute(f'UPDATE expenses SET construction_stage=?,updated_at=? WHERE activity_id IN ({q})',(new_name,now,*aids))

    def delete_phase(self, phase_id: str) -> None:
        with self.db.tx() as con:
            used=int(con.execute('''SELECT COUNT(*) FROM expenses e JOIN construction_activities a ON a.activity_id=e.activity_id
                                    WHERE a.phase_id=? AND e.deleted_at IS NULL''',(phase_id,)).fetchone()[0] or 0)
            if used: raise ValueError(f'این فاز به {used} هزینه متصل است؛ قبل از حذف هزینه‌ها را به فاز دیگری منتقل کن.')
            con.execute('UPDATE construction_activities SET active=0,updated_at=? WHERE phase_id=?',(_now(),phase_id))
            con.execute('UPDATE construction_phases SET active=0,updated_at=? WHERE phase_id=?',(_now(),phase_id))

    def add_activity(self, phase_id: str, name: str, estimate: int=0) -> dict[str,Any]:
        name=str(name or '').strip()
        if not name: raise ValueError('نام فعالیت الزامی است.')
        now=_now()
        with self.db.tx() as con:
            p=con.execute('SELECT phase_id FROM construction_phases WHERE phase_id=? AND active=1',(phase_id,)).fetchone()
            if not p: raise ValueError('فاز پیدا نشد.')
            dup=con.execute('SELECT activity_id FROM construction_activities WHERE phase_id=? AND name=? AND active=1',(phase_id,name)).fetchone()
            if dup: raise ValueError('این فعالیت قبلاً وجود دارد.')
            order=int(con.execute('SELECT COALESCE(MAX(sort_order),0)+1 FROM construction_activities WHERE phase_id=?',(phase_id,)).fetchone()[0])
            aid=_id('ACT')
            con.execute('INSERT INTO construction_activities(activity_id,phase_id,name,sort_order,active,created_at,updated_at) VALUES(?,?,?,?,1,?,?)',(aid,phase_id,name,order,now,now))
        self.update_activity_estimate(aid,estimate)
        return {'activity_id':aid,'name':name,'estimate':int(estimate or 0)}

    def rename_activity(self, activity_id: str, new_name: str) -> None:
        new_name=str(new_name or '').strip()
        if not new_name: raise ValueError('نام فعالیت خالی است.')
        now=_now()
        with self.db.tx() as con:
            r=con.execute('SELECT phase_id FROM construction_activities WHERE activity_id=? AND active=1',(activity_id,)).fetchone()
            if not r: raise ValueError('فعالیت پیدا نشد.')
            dup=con.execute('SELECT activity_id FROM construction_activities WHERE phase_id=? AND name=? AND active=1 AND activity_id!=?',(r['phase_id'],new_name,activity_id)).fetchone()
            if dup: raise ValueError('فعالیتی با این نام در فاز وجود دارد.')
            con.execute('UPDATE construction_activities SET name=?,updated_at=? WHERE activity_id=?',(new_name,now,activity_id))
            con.execute('UPDATE expenses SET activity_name=?,updated_at=? WHERE activity_id=?',(new_name,now,activity_id))

    def delete_activity(self, activity_id: str) -> None:
        with self.db.tx() as con:
            used=int(con.execute('SELECT COUNT(*) FROM expenses WHERE activity_id=? AND deleted_at IS NULL',(activity_id,)).fetchone()[0] or 0)
            if used: raise ValueError(f'این فعالیت به {used} هزینه متصل است و قابل حذف نیست.')
            con.execute('UPDATE construction_activities SET active=0,updated_at=? WHERE activity_id=?',(_now(),activity_id))

    def get_settings(self)->dict[str,Any]:
        with self.db.read() as con: r=con.execute("SELECT * FROM report_settings WHERE setting_id='MAIN'").fetchone()
        d=dict(r) if r else {}
        try: d['unit_areas']=json.loads(d.get('unit_areas_json') or '[]')
        except Exception: d['unit_areas']=[]
        return d

    def save_settings(self,**kw)->dict[str,Any]:
        current=self.get_settings(); unit_areas=kw.get('unit_areas',current.get('unit_areas',[]))
        values={
            'gross_area':float(kw.get('gross_area',current.get('gross_area',0)) or 0),
            'saleable_area':float(kw.get('saleable_area',current.get('saleable_area',0)) or 0),
            'unit_count':int(kw.get('unit_count',current.get('unit_count',0)) or 0),
            'unit_areas_json':json.dumps([float(x) for x in unit_areas if float(x)>=0],ensure_ascii=False),
            'monthly_inflation':float(kw.get('monthly_inflation',current.get('monthly_inflation',0)) or 0),
            'remaining_months':int(kw.get('remaining_months',current.get('remaining_months',0)) or 0),
            'presale_price_per_m2':int(kw.get('presale_price_per_m2',current.get('presale_price_per_m2',0)) or 0),
            'end_sale_price_override':kw.get('end_sale_price_override',current.get('end_sale_price_override')),
            'unbudgeted_misc':int(kw.get('unbudgeted_misc',current.get('unbudgeted_misc',0)) or 0),
            'target_profit_percent':float(kw.get('target_profit_percent',current.get('target_profit_percent',0)) or 0),
        }
        if values['end_sale_price_override'] in ('',None): values['end_sale_price_override']=None
        else: values['end_sale_price_override']=int(values['end_sale_price_override'])
        with self.db.tx() as con:
            con.execute('''UPDATE report_settings SET gross_area=?,saleable_area=?,unit_count=?,unit_areas_json=?,monthly_inflation=?,remaining_months=?,presale_price_per_m2=?,end_sale_price_override=?,unbudgeted_misc=?,target_profit_percent=?,updated_at=? WHERE setting_id='MAIN' ''',
                        (*values.values(),_now()))
        return self.get_settings()

    def _estimate_map(self,version_id:str|None)->dict[str,int]:
        if not version_id: return {}
        with self.db.read() as con: rows=con.execute('SELECT activity_id,estimate_amount FROM activity_estimates WHERE version_id=?',(version_id,)).fetchall()
        return {r['activity_id']:int(r['estimate_amount'] or 0) for r in rows}

    def _actual_by_activity(self)->tuple[dict[str,int],int]:
        with self.db.read() as con:
            rows=con.execute("SELECT activity_id,SUM(final_amount) total FROM expenses WHERE status IN ('APPROVED','PARTIALLY_PAID','PAID') AND deleted_at IS NULL GROUP BY activity_id").fetchall()
            unclassified=int(con.execute("SELECT COALESCE(SUM(final_amount),0) FROM expenses WHERE status IN ('APPROVED','PARTIALLY_PAID','PAID') AND deleted_at IS NULL AND (activity_id IS NULL OR activity_id='')").fetchone()[0] or 0)
        return {str(r['activity_id']):int(r['total'] or 0) for r in rows if r['activity_id']},unclassified

    def report_rows(self)->list[dict[str,Any]]:
        latest=self.latest_version(); est=self._estimate_map(latest['version_id'] if latest else None); actual,unclassified=self._actual_by_activity(); settings=self.get_settings()
        perf, infl=self._factors(est,actual,settings)
        rows=[]
        with self.db.read() as con:
            acts=con.execute('''SELECT a.activity_id,a.name activity_name,p.phase_id,p.name phase_name,p.sort_order phase_order,a.sort_order activity_order FROM construction_activities a JOIN construction_phases p ON p.phase_id=a.phase_id WHERE a.active=1 ORDER BY p.sort_order,a.sort_order''').fetchall()
        for a in acts:
            e=int(est.get(a['activity_id'],0)); ac=int(actual.get(a['activity_id'],0)); remaining=max(0,e-ac); forecast=ac+round(remaining*perf*infl)
            rows.append({'phase_id':a['phase_id'],'phase':a['phase_name'],'activity_id':a['activity_id'],'activity':a['activity_name'],'estimate':e,'actual':ac,'remaining_budget':remaining,'forecast':forecast,'variance':forecast-e})
        if unclassified:
            rows.append({'phase_id':'UNCLASSIFIED','phase':'دسته‌بندی نشده','activity_id':'UNCLASSIFIED','activity':'هزینه‌های بدون فاز/فعالیت','estimate':0,'actual':unclassified,'remaining_budget':0,'forecast':unclassified,'variance':unclassified})
        return rows

    def phase_summary(self)->list[dict[str,Any]]:
        # Include every active phase, even if it has no activities yet.  Stage 12
        # grouped only report_rows(), so a newly-added empty phase vanished from
        # the GUI immediately after insertion.
        with self.db.read() as con:
            phases=[dict(r) for r in con.execute(
                "SELECT phase_id,name,sort_order FROM construction_phases WHERE active=1 ORDER BY sort_order,name"
            ).fetchall()]
        grouped={p['phase_id']:{'phase_id':p['phase_id'],'phase':p['name'],'estimate':0,'actual':0,'forecast':0,'variance':0,'_order':int(p.get('sort_order') or 0)} for p in phases}
        unclassified=None
        for r in self.report_rows():
            pid=r.get('phase_id')
            if pid=='UNCLASSIFIED':
                if unclassified is None:
                    unclassified={'phase_id':'UNCLASSIFIED','phase':r['phase'],'estimate':0,'actual':0,'forecast':0,'variance':0,'_order':10**9}
                g=unclassified
            else:
                g=grouped.setdefault(pid,{'phase_id':pid,'phase':r['phase'],'estimate':0,'actual':0,'forecast':0,'variance':0,'_order':10**8})
            for k in ('estimate','actual','forecast','variance'): g[k]+=int(r[k])
        rows=list(grouped.values())
        if unclassified is not None: rows.append(unclassified)
        rows.sort(key=lambda x:(int(x.get('_order') or 0),str(x.get('phase') or '')))
        for r in rows:r.pop('_order',None)
        return rows

    def _factors(self,est:dict[str,int],actual:dict[str,int],settings:dict[str,Any])->tuple[float,float]:
        started_est=sum(est.get(aid,0) for aid,v in actual.items() if v>0 and est.get(aid,0)>0)
        started_actual=sum(v for aid,v in actual.items() if v>0 and est.get(aid,0)>0)
        perf=(started_actual/started_est) if started_est>0 else 1.0
        months=max(0,int(settings.get('remaining_months') or 0)); rate=float(settings.get('monthly_inflation') or 0)/100.0
        if months<=0 or rate==0: infl=1.0
        else: infl=sum((1+rate)**m for m in range(1,months+1))/months
        return perf,infl

    def forecast(self)->ForecastSummary:
        settings=self.get_settings(); latest=self.latest_version(); first=self.first_version(); latest_est=self._estimate_map(latest['version_id'] if latest else None); first_est=self._estimate_map(first['version_id'] if first else None)
        actual,unclassified=self._actual_by_activity(); perf,infl=self._factors(latest_est,actual,settings)
        rows=self.report_rows(); forecast_base=sum(int(r['forecast']) for r in rows); actual_total=sum(actual.values())+unclassified
        with self.db.read() as con:
            phase_of={r['activity_id']:r['phase_name'] for r in con.execute('''SELECT a.activity_id,p.name phase_name FROM construction_activities a JOIN construction_phases p ON p.phase_id=a.phase_id''').fetchall()}
        land_forecast=sum(int(r['forecast']) for r in rows if is_land_phase(r['phase']))
        core_forecast=max(0,forecast_base-land_forecast)
        fee=manager_fee(core_forecast)
        misc=int(settings.get('unbudgeted_misc') or 0); construction=core_forecast+fee+misc; total=construction+land_forecast
        initial_land=sum(v for aid,v in first_est.items() if is_land_phase(phase_of.get(aid,'')))
        initial_core=max(0,sum(first_est.values())-initial_land); initial=initial_land+construction_with_manager(initial_core)+misc
        current_land=sum(v for aid,v in latest_est.items() if is_land_phase(phase_of.get(aid,'')))
        current_core=max(0,sum(latest_est.values())-current_land); current=current_land+construction_with_manager(current_core)+misc
        gross=float(settings.get('gross_area') or 0); saleable=float(settings.get('saleable_area') or 0)
        sold_area=0.0
        with self.db.read() as con:
            row=con.execute("SELECT COALESCE(SUM(u.area),0) FROM sales s JOIN units u ON u.unit_id=s.unit_id WHERE s.status IN ('ACTIVE','COMPLETED')").fetchone(); sold_area=float(row[0] or 0)
        remaining_area=max(0.0,saleable-sold_area)
        months=max(0,int(settings.get('remaining_months') or 0)); rate=float(settings.get('monthly_inflation') or 0)/100.0; presale=int(settings.get('presale_price_per_m2') or 0)
        automatic_end=round(presale*((1+rate)**months)) if presale else 0
        end_price=int(settings.get('end_sale_price_override') or automatic_end)
        buyer=self.revenue.buyer_dashboard(); contract_sales=int(buyer['contract_sales']); projected_revenue=contract_sales+round(remaining_area*end_price)
        profit=projected_revenue-total; profit_pct=(profit/total*100) if total else 0.0; target=float(settings.get('target_profit_percent') or 0)
        target_revenue=round(total*(1+target/100.0)); suggested=round(max(0,target_revenue-contract_sales)/remaining_area) if remaining_area>0 else 0
        actual_fee=self.db.manager_fee_accrued(); actual_recognized=actual_total+actual_fee; remaining_cost=max(0,total-actual_recognized); cash=self.db.cash_balance(); buyer_receivable=int(buyer['receivable']); funding_gap=max(0,round(remaining_cost-(cash+buyer_receivable))); area_needed=(funding_gap/presale) if presale>0 else 0.0
        total_acts=max(1,len(latest_est)); covered=sum(1 for v in latest_est.values() if v>0); coverage=covered/total_acts*100
        return ForecastSummary(
            initial_budget=initial,current_budget=current,actual_expenses=actual_total,cost_performance_factor=perf,inflation_factor=infl,
            forecast_base_cost=forecast_base,forecast_land_cost=land_forecast,forecast_construction_cost=construction,forecast_manager_fee=fee,forecast_total_cost=total,
            construction_cost_per_gross_m2=round(construction/gross) if gross>0 else 0,construction_cost_per_saleable_m2=round(construction/saleable) if saleable>0 else 0,
            total_cost_per_gross_m2=round(total/gross) if gross>0 else 0,total_cost_per_saleable_m2=round(total/saleable) if saleable>0 else 0,
            projected_revenue=projected_revenue,projected_profit=profit,projected_profit_percent=profit_pct,suggested_remaining_sale_price_per_m2=suggested,
            funding_gap=funding_gap,presale_area_needed_m2=area_needed,remaining_saleable_area_m2=remaining_area,end_sale_price_per_m2=end_price,budget_coverage_percent=coverage,
        )
