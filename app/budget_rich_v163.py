from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from finance_db import FinanceDB, _id, _now
from xlsx_simple import list_sheet_names, read_sheet

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')

def norm(s: Any) -> str:
    return re.sub(r'\s+',' ',str(s or '').translate(_DIGITS).replace('ي','ی').replace('ك','ک').replace('\u200c',' ').strip()).lower()

def stable(prefix: str, *parts: Any) -> str:
    raw='|'.join(norm(x) for x in parts).encode('utf-8')
    return f"{prefix}-{hashlib.sha1(raw).hexdigest()[:14].upper()}"

def as_int(v: Any) -> int:
    try:return max(0,int(round(float(v or 0))))
    except Exception:return 0

def as_float(v: Any) -> float:
    try:return float(v or 0)
    except Exception:return 0.0

@dataclass
class ImportResult:
    import_id: str
    source_file: str
    phase_count: int
    phase_item_count: int
    price_item_count: int
    total_estimate: int

class RichBudgetService:
    """Quantity/rate-aware budget layer used by Peymaan 16.3.

    It does not replace the Stage-15 BudgetService.  It mirrors the same workbook
    into richer tables so the new UI can edit quantities, rates and quote details
    without changing the proven V15 posting/accounting path.
    """

    # Bumped whenever the reader would now produce different rows from the
    # same workbook. Data carrying an older number is re-read on open, so a
    # correction to the reader reaches screens without the user knowing there
    # was one to reach. Forgetting to bump it is the obvious failure, which is
    # why _reread_if_stale does not rely on it alone.
    READER_VERSION=8
    def __init__(self, db: FinanceDB, base_dir: str | Path):
        self.db=db;self.base_dir=Path(base_dir)
        self.quote_dir=self.base_dir/'data'/'price_quotes';self.quote_dir.mkdir(parents=True,exist_ok=True)
        self._migrate()
        with self.db.read() as con:
            n=int(con.execute('SELECT COUNT(*) FROM rich_phase_items WHERE active=1').fetchone()[0] or 0)
        if n==0:
            p=self.base_dir/'phase_budget_current.xlsx'
            if p.exists():
                try:self.import_workbook(p, title='برآورد مبنا 16.3', preserve_manual=False)
                except Exception:pass
        else:
            self._reread_if_stale()
        from engineering_phase187 import ensure_groups
        ensure_groups(self)
        from skeleton_phase187 import ensure_groups as ensure_skeleton_groups
        ensure_skeleton_groups(self)

    def _reread_if_stale(self):
        """Re-read the reference workbook when what is stored no longer matches it.

        The workbook is edited in Excel between sessions, and the screens are
        meant to follow it. Until now they only followed it when the user
        remembered to import: a phase split into its own lines in the file
        went on showing as one aggregated line in the app, with no sign that
        anything was out of date.
        """

        with self.db.read() as con:
            row=con.execute('SELECT source_file,source_hash,reader_version,phase_item_count FROM rich_budget_imports ORDER BY created_at DESC LIMIT 1').fetchone()
        if not row:return
        source=Path(str(row['source_file'] or ''))
        if not source.is_file() or self.workbook_layout(source) not in {'v2','v2_overall'}:return
        # Two reasons to read the file again: this build reads it better than
        # the build that last did, or the file itself has been edited since.
        # The second is the common one - the reference workbook is worked on
        # in Excel between sessions, and the screens should follow it without
        # the user having to remember to import.
        outdated=int(row['reader_version'] or 0)<self.READER_VERSION
        changed=self._hash(source)!=str(row['source_hash'] or '')
        # An import records how many rows it read. Fewer than that are active,
        # and the import did not land what it says it did - which is what a
        # half-finished build leaves behind, and what a forgotten version bump
        # would otherwise hide.
        with self.db.read() as con:
            live=int(con.execute('SELECT COUNT(*) FROM rich_phase_items WHERE active=1').fetchone()[0] or 0)
        short=live<int(row['phase_item_count'] or 0)
        if not (outdated or changed or short):return
        try:self.import_workbook(source,title=f'بازخوانی {source.stem}',preserve_manual=True)
        except Exception:pass

    def _migrate(self):
        with self.db.tx() as con:
            con.executescript('''
            CREATE TABLE IF NOT EXISTS rich_budget_imports(
              import_id TEXT PRIMARY KEY,title TEXT NOT NULL,source_file TEXT,source_hash TEXT,
              phase_count INTEGER NOT NULL DEFAULT 0,phase_item_count INTEGER NOT NULL DEFAULT 0,
              price_item_count INTEGER NOT NULL DEFAULT 0,total_estimate INTEGER NOT NULL DEFAULT 0,
              reader_version INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rich_price_items(
              price_id TEXT PRIMARY KEY,code TEXT,description TEXT NOT NULL,category TEXT NOT NULL,
              unit TEXT,estimate_rate INTEGER NOT NULL DEFAULT 0,actual_rate INTEGER NOT NULL DEFAULT 0,
              forecast_rate INTEGER NOT NULL DEFAULT 0,status TEXT,source TEXT,visible INTEGER NOT NULL DEFAULT 1,
              aggregate INTEGER NOT NULL DEFAULT 0,group_key TEXT,active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rich_price_desc ON rich_price_items(description,category,active);
            CREATE TABLE IF NOT EXISTS rich_price_components(
              component_id TEXT PRIMARY KEY,price_id TEXT NOT NULL REFERENCES rich_price_items(price_id),
              description TEXT NOT NULL,unit TEXT,quantity REAL NOT NULL DEFAULT 1,coefficient REAL NOT NULL DEFAULT 1,
              unit_rate INTEGER NOT NULL DEFAULT 0,total INTEGER NOT NULL DEFAULT 0,source TEXT,
              sort_order INTEGER NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rich_comp_price ON rich_price_components(price_id,active,sort_order);
            CREATE TABLE IF NOT EXISTS rich_price_attachments(
              attachment_id TEXT PRIMARY KEY,price_id TEXT NOT NULL REFERENCES rich_price_items(price_id),
              local_path TEXT NOT NULL,file_name TEXT,mime_type TEXT,quoted_total INTEGER NOT NULL DEFAULT 0,
              notes TEXT,created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rich_phase_items(
              phase_item_id TEXT PRIMARY KEY,phase_no INTEGER NOT NULL,phase_name TEXT NOT NULL,section TEXT,
              description TEXT NOT NULL,cost_type TEXT,unit TEXT,qty_estimate REAL NOT NULL DEFAULT 0,
              qty_actual REAL NOT NULL DEFAULT 0,qty_forecast REAL NOT NULL DEFAULT 0,factor REAL NOT NULL DEFAULT 1,
              price_id TEXT REFERENCES rich_price_items(price_id),local_estimate_rate INTEGER NOT NULL DEFAULT 0,
              status TEXT,source TEXT,sort_order INTEGER NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1,
              plan_ref TEXT NOT NULL DEFAULT '',
              total_actual INTEGER NOT NULL DEFAULT 0,
              actual_source TEXT NOT NULL DEFAULT '',
              local_actual_rate INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rich_phase_items ON rich_phase_items(phase_no,active,sort_order);
            CREATE TABLE IF NOT EXISTS rich_ui_hidden_reviews(
              pending_id TEXT PRIMARY KEY,hidden INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rich_change_history(
              change_id TEXT PRIMARY KEY,scope TEXT NOT NULL,entity_id TEXT NOT NULL,action TEXT NOT NULL,
              before_json TEXT,after_json TEXT,undone INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS financial_documents(
              document_id TEXT PRIMARY KEY,pending_id TEXT,document_type TEXT NOT NULL DEFAULT 'OTHER',
              event_date_shamsi TEXT,description TEXT,amount INTEGER NOT NULL DEFAULT 0,raw_text TEXT,
              status TEXT NOT NULL DEFAULT 'ACTIVE',created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS financial_document_links(
              document_id TEXT NOT NULL REFERENCES financial_documents(document_id),entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,
              created_at TEXT NOT NULL,PRIMARY KEY(document_id,entity_type,entity_id)
            );
            CREATE TABLE IF NOT EXISTS expense_payment_links(
              link_id TEXT PRIMARY KEY,expense_id TEXT NOT NULL,payment_id TEXT,transaction_id TEXT,cheque_id TEXT,
              source_pending_id TEXT,amount INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS phase_progress_v163(
              phase_no INTEGER PRIMARY KEY,status TEXT NOT NULL DEFAULT 'NOT_STARTED',physical_progress REAL NOT NULL DEFAULT 0,
              actual_start_shamsi TEXT,actual_end_shamsi TEXT,notes TEXT,updated_at TEXT NOT NULL
            );
            ''')
            # The workbook numbers its own rows ('25-4-1'); that number is what
            # the plan sheet shows, so a database made before it existed gains
            # the column rather than being rebuilt.
            import_cols={r[1] for r in con.execute('PRAGMA table_info(rich_budget_imports)').fetchall()}
            if 'reader_version' not in import_cols:
                con.execute('ALTER TABLE rich_budget_imports ADD COLUMN reader_version INTEGER NOT NULL DEFAULT 0')
            phase_cols={r[1] for r in con.execute('PRAGMA table_info(rich_phase_items)').fetchall()}
            if 'plan_ref' not in phase_cols:
                con.execute("ALTER TABLE rich_phase_items ADD COLUMN plan_ref TEXT NOT NULL DEFAULT ''")
            # What was actually spent is not always a quantity times a rate. A
            # payment can be recorded against a row with no quantity known -
            # the total is the figure that matters - so it is stored rather
            # than always derived.
            if 'total_actual' not in phase_cols:
                con.execute('ALTER TABLE rich_phase_items ADD COLUMN total_actual INTEGER NOT NULL DEFAULT 0')
            # Who put that figure there. Blank means a person typed it and it
            # is theirs to keep; EXPENSES means the transactions tab owns it
            # and may rewrite or clear it when the payments behind it change.
            if 'actual_source' not in phase_cols:
                con.execute("ALTER TABLE rich_phase_items ADD COLUMN actual_source TEXT NOT NULL DEFAULT ''")
            # What a contract says one unit of this work actually costs. Only
            # a contract states it; otherwise the واقعی rate is the money
            # spent divided by the quantity, which is not the same thing.
            if 'local_actual_rate' not in phase_cols:
                con.execute('ALTER TABLE rich_phase_items ADD COLUMN local_actual_rate INTEGER NOT NULL DEFAULT 0')
            cols={r[1] for r in con.execute('PRAGMA table_info(cheques)').fetchall()}
            if 'registration_state' not in cols:
                con.execute("ALTER TABLE cheques ADD COLUMN registration_state TEXT NOT NULL DEFAULT 'UNREGISTERED'")
            if 'is_guarantee' not in cols:
                con.execute("ALTER TABLE cheques ADD COLUMN is_guarantee INTEGER NOT NULL DEFAULT 0")
            if 'guarantee_status' not in cols:
                con.execute("ALTER TABLE cheques ADD COLUMN guarantee_status TEXT NOT NULL DEFAULT 'HELD'")
            if 'linked_market_entity_id' not in cols:
                con.execute("ALTER TABLE cheques ADD COLUMN linked_market_entity_id TEXT")
            # Normalize legacy unknown registration to the operator's requested default.
            con.execute("UPDATE cheques SET registration_state='UNREGISTERED' WHERE registration_state IS NULL OR registration_state='' OR registration_state='UNKNOWN'")

    def _log(self,scope:str,entity_id:str,action:str,before:dict|None,after:dict|None):
        with self.db.tx() as con:
            con.execute('INSERT INTO rich_change_history(change_id,scope,entity_id,action,before_json,after_json,undone,created_at) VALUES(?,?,?,?,?,?,0,?)',
                        (_id('CHG'),scope,entity_id,action,json.dumps(before or {},ensure_ascii=False),json.dumps(after or {},ensure_ascii=False),_now()))

    @staticmethod
    def _hash(path: Path)->str:
        h=hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        return h.hexdigest()

    def _main_price_rows(self,path:Path)->list[dict[str,Any]]:
        rows=read_sheet(path,name='شیت اصلی')
        out=[]
        groups=[(0,'MATERIAL'),(7,'LABOR'),(14,'SERVICE')]
        for base,cat in groups:
            for r in rows[5:]:
                if len(r)<=base+5:continue
                code=str(r[base] or '').strip();desc=str(r[base+1] or '').strip()
                if not code or not desc:continue
                out.append({'code':code,'description':desc,'category':cat,'unit':str(r[base+2] or '').strip(),
                            'rate':as_int(r[base+3]),'status':str(r[base+4] or '').strip(),'source':str(r[base+5] or '').strip(),
                            'visible':1,'aggregate':0,'group_key':''})
        return out

    def _phase_rows(self,path:Path)->list[dict[str,Any]]:
        names=list_sheet_names(path);cover=read_sheet(path,name='روکش');out=[]
        for row in cover[3:]:
            try:no=int(float(row[0]))
            except Exception:continue
            if no<1 or no>32:continue
            pname=str(row[1] or '').strip()
            sheet=next((n for n in names if n.startswith(f'{no:02d}-')),None)
            if not sheet:continue
            rows=read_sheet(path,name=sheet)
            for i,r in enumerate(rows[3:],1):
                if len(r)<11:continue
                desc=str(r[2] or '').strip()
                if not desc or desc=='شرح' or str(r[0] or '').strip()=='جمع کل فاز':continue
                out.append({'phase_no':no,'phase_name':pname,'section':str(r[1] or '').strip(),'description':desc,
                            'cost_type':str(r[3] or '').strip(),'unit':str(r[4] or '').strip(),'qty':as_float(r[5]),
                            'rate':as_int(r[6]),'factor':as_float(r[7]) or 1.0,'total':as_int(r[8]),'status':str(r[9] or '').strip(),
                            'source':str(r[10] or '').strip(),'sort_order':i})
        return out

    # --- the second workbook layout ---------------------------------------
    # The reference file was rebuilt: one price sheet per category instead of
    # three column groups on 'شیت اصلی', a cover called 'روکش مالی', and each
    # phase sheet carrying اولیه/بروز/واقعی for quantity and rate rather than
    # a single column with وضعیت and منبع beside it.  Both layouts are read;
    # which one a file is decided by the sheets it carries.

    PRICE_SHEETS_V2={'قیمت مصالح':'MATERIAL','قیمت پیمانکار':'LABOR','قیمت خدمات':'SERVICE'}
    OPTIONAL_PRICE_SHEETS_V2={'قیمت زمین':'LAND'}
    OVERALL_ESTIMATE_SHEETS=('براورد کلی','برآورد کلی')

    @staticmethod
    def workbook_layout(path:str|Path)->str:
        names=set(list_sheet_names(path))
        if {'شیت اصلی','روکش'} <= names:return 'v1'
        if set(RichBudgetService.PRICE_SHEETS_V2) <= names:return 'v2'
        if any(sheet in names for sheet in RichBudgetService.OVERALL_ESTIMATE_SHEETS):return 'v2_overall'
        return ''

    def _main_price_rows_v2(self,path:Path)->list[dict[str,Any]]:
        """One sheet per category: ردیف, عنوان, واحد, then the three rates."""

        out=[]
        names=set(list_sheet_names(path))
        for sheet,cat in {**self.PRICE_SHEETS_V2,**self.OPTIONAL_PRICE_SHEETS_V2}.items():
            if sheet not in names:continue
            for r in read_sheet(path,name=sheet)[3:]:
                if len(r)<4:continue
                desc=str(r[1] or '').strip()
                if not desc or desc=='عنوان':continue
                out.append({'code':str(r[0] or '').strip(),'description':desc,'category':cat,
                            'unit':str(r[2] or '').strip(),'rate':as_int(r[3]),
                            # The rebuilt workbook keeps its own بروز and واقعی
                            # rates; discarding them would have left the two
                            # columns beside برآورد showing the estimate back.
                            'rate_current':as_int(r[4]) if len(r)>4 else 0,
                            'rate_actual':as_int(r[5]) if len(r)>5 else 0,'status':'',
                            # The workbook lists which phases use a price where
                            # the old one carried a source; it is the more
                            # useful of the two, so it takes that column.
                            'source':str(r[6] or '').strip() if len(r)>6 else '',
                            'visible':1,'aggregate':0,'group_key':''})
        return out

    # 'براورد کلی' is where the workbook presents the estimate: cost-type
    # headings, its own row numbering, and a further level of detail the
    # per-phase sheets do not carry - 1217 rows against their 635.  It is the
    # sheet the estimate is read from, so it is the one imported.
    KIND_OF_LETTER_V2={'A':'مصالح','B':'اجرت','C':'خدمات','D':'خرید زمین'}

    def _phase_rows_v2(self,path:Path)->list[dict[str,Any]]:
        sheet_names=set(list_sheet_names(path))
        overall_sheet=next((name for name in self.OVERALL_ESTIMATE_SHEETS if name in sheet_names),None)
        if overall_sheet is None:
            raise ValueError('شیت «براورد کلی» یا «برآورد کلی» در فایل پیدا نشد.')
        rows=read_sheet(path,name=overall_sheet);out=[]
        # The cover names every phase; a block heading may not - 'فاز 07' has
        # no name beside it - so the number is taken from the heading and the
        # name from the cover, with the heading's own as a fallback.
        cover={}
        if 'روکش مالی' in sheet_names:
            for row in read_sheet(path,name='روکش مالی')[3:]:
                try:cover[int(float(str(row[1]).strip()))]=str(row[2] or '').strip()
                except (TypeError,ValueError,IndexError):continue
        phase_no=0;phase_name='';kind='خدمات';order=0
        titles={}
        for r in rows:
            ref=str(r[1] or '').strip() if len(r)>1 else ''
            if not ref:continue
            head=re.match(r'^فاز\s*(\d+)\s*(?:[—\-–]\s*(.+))?$',ref)
            if head:
                phase_no=int(head.group(1))
                phase_name=cover.get(phase_no) or (head.group(2) or '').strip()
                order=0;titles={};continue
            letter=re.match(r'^([A-Z])\.',ref)
            if letter:
                kind=self.KIND_OF_LETTER_V2.get(letter.group(1),'خدمات');continue
            if not re.match(r'^\d+(-\d+)+$',ref) or not phase_no:continue
            title=str(r[2] or '').strip()
            if not title:continue
            titles[ref]=title
            order+=1
            qty=as_float(r[8]);rate=as_int(r[5]);total=as_int(r[11])
            # A few rows carry a coefficient folded into their total, so it is
            # derived to keep each line's total equal to the workbook's. Rates
            # are whole tomans here and fractional in the file, which puts a
            # little noise on that division - 1.00002 where the workbook means
            # 1. Anything within half a percent of 1 is 1.
            factor=round(total/(qty*rate),4) if qty and rate and total else 1.0
            if abs(factor-1)<0.005:factor=1.0
            out.append({'phase_no':phase_no,'phase_name':phase_name,
                        # An 'NN-i-j' row belongs under 'NN-i'; that parent's
                        # title is what groups it.
                        'section':titles.get(ref.rsplit('-',1)[0],'') if ref.count('-')>1 else '',
                        'description':title,'cost_type':kind,
                        'unit':str(r[4] or '').strip(),'qty':qty,
                        'qty_current':as_float(r[9]),'qty_actual':as_float(r[10]),
                        'rate':rate,'rate_current':as_int(r[6]),'rate_actual':as_int(r[7]),
                        'factor':factor or 1.0,'total':total,'status':'','source':'',
                        'sort_order':order,'ref':ref})
        # A row other rows hang off carries their sum, not a cost of its own -
        # it has no unit, quantity or rate in the workbook. Counting it as well
        # as its children would double every phase that has one.
        parents={r['ref'].rsplit('-',1)[0] for r in out if r['ref'].count('-')>1}
        from engineering_phase187 import grouped_import_rows
        from skeleton_phase187 import grouped_import_rows as skeleton_import_rows
        return skeleton_import_rows(grouped_import_rows([r for r in out if r['ref'] not in parents]))

    def import_workbook(self,path:str|Path,title:str='',preserve_manual:bool=True)->ImportResult:
        path=Path(path).resolve()
        if not path.exists():raise FileNotFoundError(path)
        layout=self.workbook_layout(path)
        if not layout:
            raise ValueError('این فایل ساختار برآورد ۳۲ فاز Peymaan را ندارد '
                             '(نه «روکش/شیت اصلی»، نه شیت «براورد کلی/برآورد کلی» و نه سه شیت «قیمت مصالح/پیمانکار/خدمات» پیدا شد).')
        if layout=='v2':
            main=self._main_price_rows_v2(path);phases=self._phase_rows_v2(path)
        elif layout=='v2_overall':
            main=[r for r in self._main_price_rows_v2(path) if r['category']=='LAND'];phases=self._phase_rows_v2(path)
        else:
            main=self._main_price_rows(path);phases=self._phase_rows(path)
        now=_now()
        # Preserve actual/forecast rates and actual/forecast quantities by stable IDs.
        old_prices={};old_phase={}
        if preserve_manual:
            with self.db.read() as con:
                old_prices={r['price_id']:dict(r) for r in con.execute('SELECT * FROM rich_price_items').fetchall()}
                old_phase={r['phase_item_id']:dict(r) for r in con.execute('SELECT * FROM rich_phase_items').fetchall()}
        price_by_norm={}
        with self.db.tx() as con:
            con.execute('UPDATE rich_price_items SET active=0,updated_at=?',(now,));con.execute('UPDATE rich_phase_items SET active=0,updated_at=?',(now,))
            for p in main:
                pid=stable('PRICE',p['category'],p['code'] or p['description'])
                old=old_prices.get(pid,{})
                # A workbook that carries بروز and واقعی columns is stating
                # them, and a zero there is a statement too - the screen must
                # show what the file shows. Only a workbook without those
                # columns falls back to the estimate.
                if 'rate_actual' in p:
                    actual=as_int(p.get('rate_actual'));forecast=as_int(p.get('rate_current'))
                else:
                    actual=int(old.get('actual_rate') or p['rate'])
                    forecast=int(old.get('forecast_rate') or p['rate'])
                con.execute('''INSERT INTO rich_price_items(price_id,code,description,category,unit,estimate_rate,actual_rate,forecast_rate,status,source,visible,aggregate,group_key,active,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?) ON CONFLICT(price_id) DO UPDATE SET code=excluded.code,description=excluded.description,category=excluded.category,unit=excluded.unit,
                    estimate_rate=excluded.estimate_rate,status=excluded.status,source=excluded.source,visible=1,aggregate=0,group_key='',active=1,updated_at=excluded.updated_at''',
                    (pid,p['code'],p['description'],p['category'],p['unit'],p['rate'],actual,forecast,p['status'],p['source'],1,0,'',now,now))
                if 'rate_actual' in p:
                    # ON CONFLICT deliberately leaves these two alone - they are
                    # the user's to set. A workbook that states them overrules
                    # that, or a correction to the file could never land.
                    con.execute('UPDATE rich_price_items SET actual_rate=?,forecast_rate=? WHERE price_id=?',(actual,forecast,pid))
                elif pid not in old_prices:
                    con.execute('UPDATE rich_price_items SET actual_rate=?,forecast_rate=? WHERE price_id=?',(p['rate'],p['rate'],pid))
                price_by_norm[(norm(p['description']),p['category'])]=pid
            # Phase 16 material rows become hidden unit-price records plus visible aggregate section rows.
            agg_sections={}
            for r in phases:
                cat={'مصالح':'MATERIAL','اجرت':'LABOR','خدمات':'SERVICE','خرید زمین':'LAND'}.get(r['cost_type'],'SERVICE')
                pid=price_by_norm.get((norm(r['description']),cat))
                if r['phase_no']==16 and cat=='MATERIAL':
                    pid=stable('PRICE','INSTALL16',r['section'],r['description'])
                    old=old_prices.get(pid,{})
                    # Same rule as the catalogue: a workbook that states بروز
                    # and واقعی is stating them, zero included.
                    if 'rate_actual' in r:
                        actual=as_int(r.get('rate_actual'));forecast=as_int(r.get('rate_current'))
                    else:
                        actual=int(old.get('actual_rate') or r['rate']);forecast=int(old.get('forecast_rate') or r['rate'])
                    con.execute('''INSERT INTO rich_price_items(price_id,code,description,category,unit,estimate_rate,actual_rate,forecast_rate,status,source,visible,aggregate,group_key,active,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?) ON CONFLICT(price_id) DO UPDATE SET description=excluded.description,unit=excluded.unit,estimate_rate=excluded.estimate_rate,status=excluded.status,source=excluded.source,visible=0,active=1,updated_at=excluded.updated_at''',
                        (pid,'',r['description'],'INSTALLATION_COMPONENT',r['unit'],r['rate'],actual,forecast,r['status'],r['source'],0,0,r['section'],now,now))
                    if 'rate_actual' in r:con.execute('UPDATE rich_price_items SET actual_rate=?,forecast_rate=? WHERE price_id=?',(actual,forecast,pid))
                    elif pid not in old_prices:con.execute('UPDATE rich_price_items SET actual_rate=?,forecast_rate=? WHERE price_id=?',(r['rate'],r['rate'],pid))
                    agg_sections.setdefault(r['section'],[]).append((r,pid))
                elif not pid:
                    # Formula/secondary row not directly present in main price sheet: keep a hidden local rate record.
                    pid=stable('PRICE','LOCAL',r['phase_no'],r['section'],r['description'])
                    old=old_prices.get(pid,{})
                    # Same rule as the catalogue: a workbook that states بروز
                    # and واقعی is stating them, zero included.
                    if 'rate_actual' in r:
                        actual=as_int(r.get('rate_actual'));forecast=as_int(r.get('rate_current'))
                    else:
                        actual=int(old.get('actual_rate') or r['rate']);forecast=int(old.get('forecast_rate') or r['rate'])
                    con.execute('''INSERT INTO rich_price_items(price_id,code,description,category,unit,estimate_rate,actual_rate,forecast_rate,status,source,visible,aggregate,group_key,active,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?) ON CONFLICT(price_id) DO UPDATE SET description=excluded.description,category=excluded.category,unit=excluded.unit,estimate_rate=excluded.estimate_rate,status=excluded.status,source=excluded.source,active=1,updated_at=excluded.updated_at''',
                        (pid,'',r['description'],cat,r['unit'],r['rate'],actual,forecast,r['status'],r['source'],0,0,'',now,now))
                    if 'rate_actual' in r:con.execute('UPDATE rich_price_items SET actual_rate=?,forecast_rate=? WHERE price_id=?',(actual,forecast,pid))
                    elif pid not in old_prices:con.execute('UPDATE rich_price_items SET actual_rate=?,forecast_rate=? WHERE price_id=?',(r['rate'],r['rate'],pid))
                # The workbook numbers its own rows, and that number survives a
                # description being reworded; it identifies the line when there is one.
                item_id=(stable('PHITEM',r['ref']) if r.get('ref')
                         else stable('PHITEM',r['phase_no'],r['section'],r['description'],r['sort_order']))
                old=old_phase.get(item_id,{})
                if 'qty_actual' in r:
                    qa=as_float(r.get('qty_actual'));qf=as_float(r.get('qty_current'))
                else:
                    qa=float(old.get('qty_actual') or 0)
                    qf=float(old.get('qty_forecast') or r['qty'])
                con.execute('''INSERT INTO rich_phase_items(phase_item_id,phase_no,phase_name,section,description,cost_type,unit,qty_estimate,qty_actual,qty_forecast,factor,price_id,local_estimate_rate,status,source,sort_order,plan_ref,active,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?) ON CONFLICT(phase_item_id) DO UPDATE SET phase_name=excluded.phase_name,section=excluded.section,description=excluded.description,cost_type=excluded.cost_type,unit=excluded.unit,
                    qty_estimate=excluded.qty_estimate,factor=excluded.factor,price_id=excluded.price_id,local_estimate_rate=excluded.local_estimate_rate,status=excluded.status,source=excluded.source,sort_order=excluded.sort_order,plan_ref=excluded.plan_ref,active=1,updated_at=excluded.updated_at''',
                    # total_actual is deliberately absent from that list: it
                    # records what was spent, which the workbook does not know
                    # and a re-import must not erase.

                    (item_id,r['phase_no'],r['phase_name'],r['section'],r['description'],r['cost_type'],r['unit'],r['qty'],qa,qf,r['factor'],pid,r['rate'],r['status'],r['source'],r['sort_order'],str(r.get('ref') or ''),now,now))
                if not old or 'qty_actual' in r:con.execute('UPDATE rich_phase_items SET qty_actual=?,qty_forecast=? WHERE phase_item_id=?',(qa,qf,item_id))
            # Aggregate visible installation groups and their components.
            for sec,items in agg_sections.items():
                apid=stable('PRICE','INSTALL16_GROUP',sec);desc=f'لوازم تأسیسات {sec} — جمع کل'
                est=sum(as_int(r['total']) for r,_ in items)
                old=old_prices.get(apid,{})
                actual=int(old.get('actual_rate') or est);forecast=int(old.get('forecast_rate') or est)
                con.execute('''INSERT INTO rich_price_items(price_id,code,description,category,unit,estimate_rate,actual_rate,forecast_rate,status,source,visible,aggregate,group_key,active,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?) ON CONFLICT(price_id) DO UPDATE SET description=excluded.description,estimate_rate=excluded.estimate_rate,visible=1,aggregate=1,group_key=excluded.group_key,active=1,updated_at=excluded.updated_at''',
                    (apid,'',desc,'INSTALLATION_GROUP','مقطوع',est,actual,forecast,'از اکسل','فاز 16',1,1,sec,now,now))
                if apid not in old_prices:con.execute('UPDATE rich_price_items SET actual_rate=?,forecast_rate=? WHERE price_id=?',(est,est,apid))
                con.execute('UPDATE rich_price_components SET active=0,updated_at=? WHERE price_id=?',(now,apid))
                for idx,(r,cpid) in enumerate(items,1):
                    cid=stable('PCOMP',apid,r['description'])
                    total=as_int(r['total'])
                    con.execute('''INSERT INTO rich_price_components(component_id,price_id,description,unit,quantity,coefficient,unit_rate,total,source,sort_order,active,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?) ON CONFLICT(component_id) DO UPDATE SET description=excluded.description,unit=excluded.unit,quantity=excluded.quantity,unit_rate=excluded.unit_rate,total=excluded.total,source=excluded.source,sort_order=excluded.sort_order,active=1,updated_at=excluded.updated_at''',
                        (cid,apid,r['description'],r['unit'],r['qty'],r['factor'],r['rate'],total,r['source'],idx,now,now))
            if layout=='v2':
                # Every row this reader produces carries the workbook's own
                # number. An active row without one is a leftover from an
                # older reader, and no amount of re-importing removes it -
                # nothing in the file matches it, so nothing overwrites it.
                # It is deleted rather than deactivated: it has no source to
                # come back from.
                con.execute("DELETE FROM rich_phase_items WHERE plan_ref=''")
            import_id=_id('BUDRICH');tot=sum(as_int(r['total']) for r in phases)
            con.execute('INSERT INTO rich_budget_imports(import_id,title,source_file,source_hash,phase_count,phase_item_count,price_item_count,total_estimate,reader_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (import_id,title or path.stem,str(path),self._hash(path),len(set(r['phase_no'] for r in phases)),len(phases),len(main)+len(agg_sections),tot,self.READER_VERSION,now))
        return ImportResult(import_id,str(path),len(set(r['phase_no'] for r in phases)),len(phases),len(main)+len(agg_sections),tot)

    def ensure_land_price(self):
        """Provide the default D1 estimate item without requiring a land sheet."""
        now=_now();pid=stable('PRICE','LAND','1')
        with self.db.tx() as con:
            existing=con.execute("SELECT price_id,code FROM rich_price_items WHERE category='LAND' AND active=1 AND visible=1").fetchall()
            first=next((r for r in existing if as_float(r['code'])==1),None)
            if first:return first['price_id']
            reserved=con.execute('SELECT category,code FROM rich_price_items WHERE price_id=?',(pid,)).fetchone()
            if reserved and (reserved['category']!='LAND' or as_float(reserved['code'])!=1):pid=_id('PRICE')
            con.execute("""INSERT INTO rich_price_items(price_id,code,description,category,unit,
                estimate_rate,actual_rate,forecast_rate,status,source,visible,aggregate,group_key,active,created_at,updated_at)
                VALUES(?, '1', 'خرید زمین', 'LAND', 'مترمربع', 0, 0, 0, 'ثبت دستی', 'GUI', 1, 0, '', 1, ?, ?)
                ON CONFLICT(price_id) DO UPDATE SET active=1,visible=1,updated_at=excluded.updated_at""",(pid,now,now))
        return pid

    def list_prices(self,category:str|None=None,visible_only:bool=True)->list[dict[str,Any]]:
        where=['active=1'];args=[]
        if visible_only:where.append('visible=1')
        if category:where.append('category=?');args.append(category)
        with self.db.read() as con:rows=con.execute(f"SELECT * FROM rich_price_items WHERE {' AND '.join(where)} ORDER BY CASE category WHEN 'MATERIAL' THEN 1 WHEN 'LABOR' THEN 2 WHEN 'SERVICE' THEN 3 WHEN 'INSTALLATION_GROUP' THEN 4 ELSE 5 END,description",args).fetchall()
        return [dict(r) for r in rows]

    def get_price(self,price_id:str)->dict[str,Any]|None:
        with self.db.read() as con:r=con.execute('SELECT * FROM rich_price_items WHERE price_id=?',(price_id,)).fetchone()
        return dict(r) if r else None

    def list_components(self,price_id:str)->list[dict[str,Any]]:
        with self.db.read() as con:rows=con.execute('SELECT * FROM rich_price_components WHERE price_id=? AND active=1 ORDER BY sort_order,created_at',(price_id,)).fetchall()
        return [dict(r) for r in rows]

    def ensure_single_component(self,price_id:str)->list[dict[str,Any]]:
        rows=self.list_components(price_id)
        if rows:return rows
        p=self.get_price(price_id)
        if not p:return []
        now=_now();cid=stable('PCOMP',price_id,'base')
        rate=int(p.get('forecast_rate') or p.get('estimate_rate') or 0)
        with self.db.tx() as con:
            con.execute('INSERT OR REPLACE INTO rich_price_components(component_id,price_id,description,unit,quantity,coefficient,unit_rate,total,source,sort_order,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?)',
                        (cid,price_id,p['description'],p.get('unit') or '',1.0,1.0,rate,rate,'نرخ پایه',1,now,now))
        return self.list_components(price_id)

    def save_price_rates(self,price_id:str,estimate:int,actual:int,forecast:int):
        before=self.get_price(price_id) or {}
        estimate,actual,forecast=max(0,int(estimate)),max(0,int(actual)),max(0,int(forecast))
        with self.db.tx() as con:
            con.execute('UPDATE rich_price_items SET estimate_rate=?,actual_rate=?,forecast_rate=?,updated_at=? WHERE price_id=?',(estimate,actual,forecast,_now(),price_id))
            con.execute('UPDATE rich_phase_items SET local_estimate_rate=?,local_actual_rate=?,updated_at=? WHERE price_id=?',(estimate,actual,_now(),price_id))
        self._log('PRICE',price_id,'UPDATE_RATES',before,self.get_price(price_id))

    def upsert_component(self,price_id:str,data:dict[str,Any],component_id:str|None=None)->str:
        now=_now();cid=component_id or _id('PCOMP')
        before=None
        if component_id:
            with self.db.read() as con:r=con.execute('SELECT * FROM rich_price_components WHERE component_id=?',(component_id,)).fetchone();before=dict(r) if r else None
        q=as_float(data.get('quantity') or 1);coef=as_float(data.get('coefficient') or 1);rate=as_int(data.get('unit_rate'));total=as_int(round(q*coef*rate))
        with self.db.tx() as con:
            con.execute('''INSERT INTO rich_price_components(component_id,price_id,description,unit,quantity,coefficient,unit_rate,total,source,sort_order,active,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?) ON CONFLICT(component_id) DO UPDATE SET description=excluded.description,unit=excluded.unit,quantity=excluded.quantity,coefficient=excluded.coefficient,unit_rate=excluded.unit_rate,total=excluded.total,source=excluded.source,active=1,updated_at=excluded.updated_at''',
                (cid,price_id,str(data.get('description') or '').strip() or 'قلم',str(data.get('unit') or '').strip(),q,coef,rate,total,str(data.get('source') or '').strip(),int(data.get('sort_order') or 999),now,now))
        self.recalc_from_components(price_id);self._log('PRICE_COMPONENT',cid,'UPSERT',before,data);return cid

    def delete_component(self,component_id:str):
        with self.db.read() as con:r=con.execute('SELECT * FROM rich_price_components WHERE component_id=?',(component_id,)).fetchone()
        if not r:return
        before=dict(r)
        with self.db.tx() as con:con.execute('UPDATE rich_price_components SET active=0,updated_at=? WHERE component_id=?',(_now(),component_id))
        self.recalc_from_components(before['price_id']);self._log('PRICE_COMPONENT',component_id,'DELETE',before,{})

    def recalc_from_components(self,price_id:str)->int:
        p=self.get_price(price_id) or {};rows=self.list_components(price_id);base_total=sum(int(r.get('total') or 0) for r in rows)
        # V18 Phase 04: operator enters the five booklet base rates; VAT 10% is
        # applied once to their sum, exactly as the Engineering Organization bill.
        total=as_int(round(base_total*1.10)) if p.get('group_key')=='PH04_MAIN_SUPERVISION' else base_total
        # Components define the forecast/current quotation. Estimate remains the imported baseline.
        if rows:
            with self.db.tx() as con:con.execute('UPDATE rich_price_items SET forecast_rate=?,updated_at=? WHERE price_id=?',(total,_now(),price_id))
        return total

    def add_quote_attachment(self,price_id:str,source_path:str|Path,quoted_total:int=0,notes:str='')->dict[str,Any]:
        src=Path(source_path);aid=_id('PQUOTE');dst=self.quote_dir/f'{aid}_{src.name}';shutil.copy2(src,dst)
        if not quoted_total and src.suffix.lower()=='.xlsx':quoted_total=self._detect_excel_total(dst)
        with self.db.tx() as con:
            con.execute('INSERT INTO rich_price_attachments(attachment_id,price_id,local_path,file_name,mime_type,quoted_total,notes,created_at) VALUES(?,?,?,?,?,?,?,?)',
                        (aid,price_id,str(dst),src.name,mimetypes.guess_type(src.name)[0] or '',int(quoted_total or 0),notes,_now()))
            if quoted_total>0:con.execute('UPDATE rich_price_items SET forecast_rate=?,updated_at=? WHERE price_id=?',(int(quoted_total),_now(),price_id))
        return {'attachment_id':aid,'local_path':str(dst),'quoted_total':int(quoted_total or 0)}

    def _detect_excel_total(self,path:Path)->int:
        # Search all sheets for a row containing جمع/total and use the largest numeric value on it.
        best=0
        try:
            for name in list_sheet_names(path):
                for r in read_sheet(path,name=name):
                    txt=' '.join(norm(x) for x in r if isinstance(x,str))
                    if any(k in txt for k in ('جمع کل','جمع','total','grand total')):
                        nums=[as_int(x) for x in r if isinstance(x,(int,float))]
                        if nums:best=max(best,max(nums))
            if best:return best
            # Fallback: largest plausible numeric value in workbook.
            for name in list_sheet_names(path):
                for r in read_sheet(path,name=name):
                    for x in r:
                        if isinstance(x,(int,float)):best=max(best,as_int(x))
        except Exception:pass
        return best

    def list_attachments(self,price_id:str)->list[dict[str,Any]]:
        with self.db.read() as con:rows=con.execute('SELECT * FROM rich_price_attachments WHERE price_id=? ORDER BY created_at DESC',(price_id,)).fetchall()
        return [dict(r) for r in rows]

    def list_phase_items(self,phase_no:int)->list[dict[str,Any]]:
        with self.db.read() as con:
            # The price's code and category come across too: they are what the
            # screens show as the catalogue code, and a row cannot build it
            # from its own columns.
            rows=con.execute('''SELECT pi.*,p.estimate_rate,p.actual_rate,p.forecast_rate,
              p.description price_description,p.code code,p.category category
              FROM rich_phase_items pi LEFT JOIN rich_price_items p ON p.price_id=pi.price_id
              WHERE pi.phase_no=? AND pi.active=1 ORDER BY pi.sort_order,pi.description''',(int(phase_no),)).fetchall()
        return self._engineering_actual_area([dict(r) for r in rows])

    def _engineering_actual_area(self, rows):
        if not any(int(r.get('phase_no') or 0) == 4 for r in rows):
            return rows
        with self.db.read() as con:
            exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='report_settings'").fetchone()
            settings = con.execute("SELECT gross_area FROM report_settings WHERE setting_id='MAIN'").fetchone() if exists else None
        from engineering_phase187 import group_of
        area = float(settings['gross_area'] or 0) if settings else 0
        for row in rows:
            if group_of(row):
                row['_engineering_area187'] = area
        return rows

    def all_phase_items(self)->list[dict[str,Any]]:
        """Every phase's lines in one read, in the order the phases run.

        list_phase_items opens its own connection, and on this database that
        first statement costs about five milliseconds - so asking it thirty-two
        times, seven times over during one refresh, was most of the four
        seconds a refresh took. The rows are identical; only the number of
        connections changes.
        """

        with self.db.read() as con:
            rows=con.execute('''SELECT pi.*,p.estimate_rate,p.actual_rate,p.forecast_rate,
              p.description price_description,p.code code,p.category category
              FROM rich_phase_items pi LEFT JOIN rich_price_items p ON p.price_id=pi.price_id
              WHERE pi.active=1 ORDER BY pi.phase_no,pi.sort_order,pi.description''').fetchall()
        return self._engineering_actual_area([dict(r) for r in rows])

    def list_phase_summary(self)->list[dict[str,Any]]:
        out=[];grouped:dict[int,list[dict[str,Any]]]={};names:dict[int,str]={}
        for row in self.all_phase_items():
            no=int(row.get('phase_no') or 0)
            grouped.setdefault(no,[]).append(row)
            names[no]=str(row.get('phase_name') or names.get(no) or '')
        phases=[{'phase_no':no,'phase_name':names.get(no,'')} for no in sorted(grouped)]
        for p in phases:
            items=grouped[int(p['phase_no'])];est=act=fc=0
            for r in items:
                factor=float(r.get('factor') or 1);qe=float(r.get('qty_estimate') or 0);qa=float(r.get('qty_actual') or 0);qf=float(r.get('qty_forecast') or qe)
                er=int(r.get('estimate_rate') or r.get('local_estimate_rate') or 0);ar=int(r.get('actual_rate') or er);fr=int(r.get('forecast_rate') or er)
                est+=int(round(qe*factor*er));fc+=int(round(qf*factor*fr))
                # What a phase has actually cost is the money paid against its
                # lines, and nothing else. Falling back to quantity times rate
                # reported a phase as spent the moment it was priced and
                # metred, before a single payment had been made.
                act+=int(r.get('total_actual') or 0)
            out.append({'phase_no':int(p['phase_no']),'phase':p['phase_name'],'phase_id':f"PH-{int(p['phase_no']):02d}",
                        'estimate':est,'actual':act,'remaining_base':max(est-act,0),'forecast':max(fc,act),'variance':max(fc,act)-est})
        return out

    def save_phase_item(self,item_id:str,**changes)->dict[str,Any]:
        with self.db.read() as con:r=con.execute('SELECT * FROM rich_phase_items WHERE phase_item_id=?',(item_id,)).fetchone()
        if not r:raise KeyError(item_id)
        before=dict(r);allowed={'description','section','cost_type','unit','qty_estimate','qty_actual','qty_forecast','factor','price_id','status','source','total_actual','local_actual_rate','phase_name'};fields=[];vals=[]
        for k,v in changes.items():
            if k not in allowed:continue
            if k in {'qty_estimate','qty_actual','qty_forecast','factor'}:v=float(v or 0)
            if k in {'total_actual','local_actual_rate'}:v=as_int(v)
            fields.append(f'{k}=?');vals.append(v)
        if fields:
            vals += [_now(),item_id]
            with self.db.tx() as con:con.execute(f"UPDATE rich_phase_items SET {','.join(fields)},updated_at=? WHERE phase_item_id=?",vals)
        after=self.get_phase_item(item_id) or {};self._log('PHASE_ITEM',item_id,'UPDATE',before,after);return after

    def get_phase_item(self,item_id:str)->dict[str,Any]|None:
        with self.db.read() as con:r=con.execute('SELECT * FROM rich_phase_items WHERE phase_item_id=?',(item_id,)).fetchone()
        return dict(r) if r else None

    def add_phase_item(self,phase_no:int,phase_name:str,data:dict[str,Any])->str:
        iid=_id('PHITEM');now=_now();desc=str(data.get('description') or '').strip()
        if not desc:raise ValueError('شرح فعالیت الزامی است.')
        cost=str(data.get('cost_type') or 'خدمات');cat={'مصالح':'MATERIAL','اجرت':'LABOR','خدمات':'SERVICE','خرید زمین':'LAND'}.get(cost,'SERVICE')
        # The default D1 is an unused zero-price placeholder until the first
        # land row is entered. Reuse it instead of creating duplicate land.
        pid=str(data.get('price_id') or '')
        with self.db.tx() as con:
            rate=as_int(data.get('estimate_rate'))
            actual=as_int(data.get('actual_rate',rate));forecast=as_int(data.get('forecast_rate',rate))
            if not pid and cat=='LAND':
                default=con.execute("""SELECT price_id FROM rich_price_items p
                    WHERE category='LAND' AND active=1 AND visible=1 AND source='GUI' AND description='خرید زمین'
                    AND estimate_rate=0 AND forecast_rate=0 AND actual_rate=0
                    AND NOT EXISTS (SELECT 1 FROM rich_phase_items pi WHERE pi.price_id=p.price_id AND pi.active=1)""",
                    ()).fetchone()
                if default:
                    pid=default['price_id']
                    con.execute('UPDATE rich_price_items SET description=?,unit=?,estimate_rate=?,actual_rate=?,forecast_rate=?,source=?,updated_at=? WHERE price_id=?',
                        (desc,str(data.get('unit') or ''),rate,actual,forecast,f'{int(phase_no):02d}',now,pid))
            if not pid:
                pid=_id('PRICE')
                codes=con.execute('SELECT code FROM rich_price_items WHERE category=? AND active=1 AND visible=1',(cat,)).fetchall()
                code=str(int(max((as_float(r['code']) for r in codes),default=0))+1)
                con.execute('INSERT INTO rich_price_items(price_id,code,description,category,unit,estimate_rate,actual_rate,forecast_rate,status,source,visible,aggregate,group_key,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)',
                    (pid,code,desc,cat,str(data.get('unit') or ''),rate,actual,forecast,'ثبت دستی',f'{int(phase_no):02d}',1,0,'',now,now))
            mx=int(con.execute('SELECT COALESCE(MAX(sort_order),0)+1 FROM rich_phase_items WHERE phase_no=?',(phase_no,)).fetchone()[0])
            qf=data.get('qty_forecast') if data.get('qty_forecast') is not None else data.get('qty_estimate')
            con.execute('INSERT INTO rich_phase_items(phase_item_id,phase_no,phase_name,section,description,cost_type,unit,qty_estimate,qty_actual,qty_forecast,factor,price_id,local_estimate_rate,status,source,sort_order,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)',
                (iid,int(phase_no),phase_name,str(data.get('section') or ''),desc,cost,str(data.get('unit') or ''),float(data.get('qty_estimate') or 0),float(data.get('qty_actual') or 0),float(qf or 0),float(data.get('factor') or 1),pid,rate,'ثبت دستی',str(data.get('source') or 'GUI'),mx,now,now))
        self.place_phase_item(iid)
        self._log('PHASE_ITEM',iid,'CREATE',{},self.get_phase_item(iid));return iid

    def renumber_phase(self,phase_no:int):
        """Rewrite a phase's row numbers as 'NN-i' and 'NN-i-j', in order.

        A run of consecutive rows sharing a section is one numbered group with
        its members beneath it, which is how the workbook writes them. The
        group's own line is not stored - it holds the sum of its members and
        nothing of its own - so the run itself is what carries the number.
        """

        rows=self.list_phase_items(int(phase_no));now=_now();updates=[]
        top=0;child=0;current=None
        for index,r in enumerate(rows,1):
            section=str(r.get('section') or '').strip()
            if not section:
                top+=1;current=None;child=0
                ref=f'{int(phase_no):02d}-{top}'
            else:
                if section!=current:
                    top+=1;current=section;child=0
                child+=1
                ref=f'{int(phase_no):02d}-{top}-{child}'
            updates.append((ref,index,now,r['phase_item_id']))
        with self.db.tx() as con:
            con.executemany('UPDATE rich_phase_items SET plan_ref=?,sort_order=?,updated_at=? WHERE phase_item_id=?',updates)

    def place_phase_item(self,item_id:str,after_id:str|None=None,*,renumber_price:bool=False):
        """Insert into the own cost group; same-kind anchors allow copy-below."""

        item=self.get_phase_item(item_id)
        if not item:return
        phase_no=int(item.get('phase_no') or 0)
        rows=[r for r in self.list_phase_items(phase_no) if r['phase_item_id']!=item_id]
        order=[r['phase_item_id'] for r in rows]
        anchor=next((r for r in rows if r['phase_item_id']==after_id),None)
        same_anchor=anchor is not None and anchor.get('cost_type')==item.get('cost_type')
        own=[r for r in rows if r.get('cost_type')==item.get('cost_type')]
        ranks={'مصالح':0,'اجرت':1,'خدمات':2,'خرید زمین':3}
        if same_anchor:position=order.index(after_id)+1
        elif own:position=order.index(own[-1]['phase_item_id'])+1
        else:
            position=next((i for i,r in enumerate(rows)
                if ranks.get(r.get('cost_type'),4)>ranks.get(item.get('cost_type'),4)),len(order))
        order.insert(position,item_id)
        now=_now()
        with self.db.tx() as con:
            for index,pid in enumerate(order,1):
                con.execute('UPDATE rich_phase_items SET sort_order=?,updated_at=? WHERE phase_item_id=?',
                            (index,now,pid))
        if renumber_price:
            price_anchor=anchor if same_anchor else (own[-1] if own else None)
            self._place_new_price_after(item,price_anchor)
        self.renumber_phase(phase_no)

    def _place_new_price_after(self,item,anchor):
        """Assign the new catalogue number and shift later codes, keeping IDs."""
        with self.db.tx() as con:
            price=con.execute('SELECT * FROM rich_price_items WHERE price_id=?',(item.get('price_id'),)).fetchone()
            previous=con.execute('SELECT * FROM rich_price_items WHERE price_id=?',(anchor.get('price_id'),)).fetchone() if anchor else None
            uses=con.execute('SELECT COUNT(*) FROM rich_phase_items WHERE price_id=? AND active=1',(item.get('price_id'),)).fetchone()[0]
            if not price or uses!=1 or price['status']!='ثبت دستی' or price['created_at']!=item.get('created_at'):
                return
            if previous:
                if price['category']!=previous['category']:return
                previous_code=as_float(previous['code'])
                if previous_code<=0:return
                target=int(previous_code)+1
            else:target=1
            if as_float(price['code'])==target:return
            now=_now()
            prices=con.execute('SELECT price_id,code FROM rich_price_items WHERE active=1 AND visible=1 AND category=? AND price_id<>?',(price['category'],price['price_id'])).fetchall()
            for other in prices:
                number=as_float(other['code'])
                if number>=target:
                    con.execute('UPDATE rich_price_items SET code=?,updated_at=? WHERE price_id=?',(str(int(number)+1),now,other['price_id']))
            con.execute('UPDATE rich_price_items SET code=?,updated_at=? WHERE price_id=?',(str(target),now,price['price_id']))

    def delete_phase_item(self,item_id:str):
        before=self.get_phase_item(item_id)
        if not before:return
        with self.db.tx() as con:con.execute('UPDATE rich_phase_items SET active=0,updated_at=? WHERE phase_item_id=?',(_now(),item_id))
        self._log('PHASE_ITEM',item_id,'DELETE',before,{})

    def get_phase_progress(self)->dict[int,dict[str,Any]]:
        with self.db.read() as con:
            rows=con.execute('SELECT * FROM phase_progress_v163 ORDER BY phase_no').fetchall()
        return {int(r['phase_no']):dict(r) for r in rows}

    def set_phase_progress(self,phase_no:int,status:str,progress:float,start:str='',end:str='',notes:str=''):
        progress=max(0.0,min(float(progress or 0),100.0));status=str(status or 'NOT_STARTED').upper()
        if status not in {'NOT_STARTED','ACTIVE','PAUSED','COMPLETED'}:status='NOT_STARTED'
        if progress>=100:status='COMPLETED'
        sql=('INSERT INTO phase_progress_v163(phase_no,status,physical_progress,actual_start_shamsi,actual_end_shamsi,notes,updated_at) VALUES(?,?,?,?,?,?,?) '             'ON CONFLICT(phase_no) DO UPDATE SET status=excluded.status,physical_progress=excluded.physical_progress,actual_start_shamsi=excluded.actual_start_shamsi,actual_end_shamsi=excluded.actual_end_shamsi,notes=excluded.notes,updated_at=excluded.updated_at')
        with self.db.tx() as con:
            con.execute(sql,(int(phase_no),status,progress,start or None,end or None,notes,_now()))

    def overall_physical_progress(self)->float:
        p=self.get_phase_progress();summ=self.list_phase_summary()
        if not summ:return 0.0
        total_w=sum(max(1,int(r.get('estimate') or 0)) for r in summ);acc=0.0
        for r in summ:
            pr=float((p.get(int(r['phase_no'])) or {}).get('physical_progress') or 0);w=max(1,int(r.get('estimate') or 0));acc += w*pr
        return acc/total_w if total_w else 0.0

    def phase_candidates(self,query:str,limit:int=8)->list[dict[str,Any]]:
        q=norm(query)
        if not q:return []
        scores=[]
        with self.db.read() as con:
            phases=con.execute('SELECT phase_no,MAX(phase_name) phase_name FROM rich_phase_items WHERE active=1 GROUP BY phase_no').fetchall()
        for p in phases:
            no=int(p['phase_no']);name=str(p['phase_name']);items=self.list_phase_items(no);hay=norm(name)+' '+' '.join(norm(x['description'])+' '+norm(x['section']) for x in items)
            score=0
            if q in norm(name):score+=100
            for tok in q.split():
                if tok in norm(name):score+=25
                if tok in hay:score+=8
            if score:scores.append((score,{'phase_no':no,'phase_name':name,'phase_id':f'PH-{no:02d}'}))
        return [x[1] for x in sorted(scores,key=lambda x:(-x[0],x[1]['phase_no']))[:limit]]

    def subphase_candidates(self,phase_no:int|None,query:str='')->list[dict[str,Any]]:
        q=norm(query);rows=[]
        if phase_no:rows=self.list_phase_items(int(phase_no))
        else:
            with self.db.read() as con:r=con.execute('SELECT DISTINCT phase_no FROM rich_phase_items WHERE active=1 ORDER BY phase_no').fetchall()
            for x in r:rows.extend(self.list_phase_items(int(x['phase_no'])))
        from engineering_phase187 import entry_choices
        from skeleton_phase187 import entry_choices as skeleton_entry_choices
        rows = skeleton_entry_choices(entry_choices(rows))
        if q:
            scored=[]
            for r in rows:
                hay=norm(r['description'])+' '+norm(r.get('section'))
                score=100 if q in norm(r['description']) else sum(15 for tok in q.split() if tok in hay)
                if score:scored.append((score,r))
            rows=[x[1] for x in sorted(scored,key=lambda x:-x[0])]
        return rows[:120]

    def add_financial_document(self,pending_id:str,payload:dict[str,Any],raw_text:str='',links:list[tuple[str,str]]|None=None)->str:
        now=_now();did=_id('DOC')
        with self.db.tx() as con:
            con.execute('INSERT INTO financial_documents(document_id,pending_id,document_type,event_date_shamsi,description,amount,raw_text,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (did,pending_id,str(payload.get('document_type') or 'OTHER'),str(payload.get('event_date_shamsi') or ''),str(payload.get('description') or raw_text or ''),as_int(payload.get('amount') or payload.get('final_amount')),raw_text,'ACTIVE',now,now))
            for et,eid in links or []:
                con.execute('INSERT OR IGNORE INTO financial_document_links(document_id,entity_type,entity_id,created_at) VALUES(?,?,?,?)',(did,str(et).upper(),str(eid),now))
        return did

    def list_documents(self)->list[dict[str,Any]]:
        sql=("SELECT d.*,GROUP_CONCAT(l.entity_type||':'||l.entity_id,' | ') links "
             "FROM financial_documents d LEFT JOIN financial_document_links l ON l.document_id=d.document_id "
             "WHERE d.status='ACTIVE' GROUP BY d.document_id ORDER BY d.created_at DESC")
        with self.db.read() as con:
            rows=con.execute(sql).fetchall()
        return [dict(r) for r in rows]

    def link_document(self,document_id:str,entity_type:str,entity_id:str):
        with self.db.tx() as con:
            con.execute('INSERT OR IGNORE INTO financial_document_links(document_id,entity_type,entity_id,created_at) VALUES(?,?,?,?)',(document_id,entity_type.upper(),entity_id,_now()))

    def delete_document(self,document_id:str):
        with self.db.tx() as con:
            con.execute("UPDATE financial_documents SET status='DELETED',updated_at=? WHERE document_id=?",(_now(),document_id))

    def undo_last(self)->str:
        with self.db.read() as con:
            r=con.execute("SELECT * FROM rich_change_history WHERE undone=0 ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
        if not r:return 'چیزی برای Undo وجود ندارد.'
        row=dict(r);before=json.loads(row.get('before_json') or '{}');scope=row['scope'];eid=row['entity_id'];action=row['action']
        with self.db.tx() as con:
            if scope=='PRICE' and before:
                con.execute('UPDATE rich_price_items SET estimate_rate=?,actual_rate=?,forecast_rate=?,updated_at=? WHERE price_id=?',(int(before.get('estimate_rate') or 0),int(before.get('actual_rate') or 0),int(before.get('forecast_rate') or 0),_now(),eid))
            elif scope=='PHASE_ITEM':
                if action=='CREATE':con.execute('UPDATE rich_phase_items SET active=0,updated_at=? WHERE phase_item_id=?',(_now(),eid))
                elif action=='DELETE':con.execute('UPDATE rich_phase_items SET active=1,updated_at=? WHERE phase_item_id=?',(_now(),eid))
                elif before:
                    keys=['description','section','cost_type','unit','qty_estimate','qty_actual','qty_forecast','factor','price_id','status','source','active']
                    vals=[before.get(k) for k in keys]+[_now(),eid]
                    con.execute('UPDATE rich_phase_items SET '+','.join(k+'=?' for k in keys)+',updated_at=? WHERE phase_item_id=?',vals)
            elif scope=='PRICE_COMPONENT':
                if action=='UPSERT' and not before:con.execute('UPDATE rich_price_components SET active=0,updated_at=? WHERE component_id=?',(_now(),eid))
                elif action=='DELETE':con.execute('UPDATE rich_price_components SET active=1,updated_at=? WHERE component_id=?',(_now(),eid))
                elif before:
                    keys=['description','unit','quantity','coefficient','unit_rate','total','source','sort_order','active'];vals=[before.get(k) for k in keys]+[_now(),eid]
                    con.execute('UPDATE rich_price_components SET '+','.join(k+'=?' for k in keys)+',updated_at=? WHERE component_id=?',vals)
            con.execute('UPDATE rich_change_history SET undone=1 WHERE change_id=?',(row['change_id'],))
        return 'Undo انجام شد.'

    def redo_last(self)->str:
        with self.db.read() as con:
            r=con.execute("SELECT * FROM rich_change_history WHERE undone=1 ORDER BY created_at ASC, rowid ASC LIMIT 1").fetchone()
        if not r:return 'چیزی برای Redo وجود ندارد.'
        row=dict(r);after=json.loads(row.get('after_json') or '{}');scope=row['scope'];eid=row['entity_id'];action=row['action']
        with self.db.tx() as con:
            if scope=='PRICE' and after:
                con.execute('UPDATE rich_price_items SET estimate_rate=?,actual_rate=?,forecast_rate=?,updated_at=? WHERE price_id=?',(int(after.get('estimate_rate') or 0),int(after.get('actual_rate') or 0),int(after.get('forecast_rate') or 0),_now(),eid))
            elif scope=='PHASE_ITEM':
                if action=='CREATE':con.execute('UPDATE rich_phase_items SET active=1,updated_at=? WHERE phase_item_id=?',(_now(),eid))
                elif action=='DELETE':con.execute('UPDATE rich_phase_items SET active=0,updated_at=? WHERE phase_item_id=?',(_now(),eid))
                elif after:
                    keys=['description','section','cost_type','unit','qty_estimate','qty_actual','qty_forecast','factor','price_id','status','source','active'];vals=[after.get(k) for k in keys]+[_now(),eid]
                    con.execute('UPDATE rich_phase_items SET '+','.join(k+'=?' for k in keys)+',updated_at=? WHERE phase_item_id=?',vals)
            elif scope=='PRICE_COMPONENT':
                if action=='DELETE':con.execute('UPDATE rich_price_components SET active=0,updated_at=? WHERE component_id=?',(_now(),eid))
                elif after:
                    keys=['description','unit','quantity','coefficient','unit_rate','total','source','sort_order','active'];vals=[after.get(k) for k in keys]+[_now(),eid]
                    con.execute('UPDATE rich_price_components SET '+','.join(k+'=?' for k in keys)+',updated_at=? WHERE component_id=?',vals)
            con.execute('UPDATE rich_change_history SET undone=0 WHERE change_id=?',(row['change_id'],))
        return 'Redo انجام شد.'

    def hide_review(self,pending_ids:list[str]):
        with self.db.tx() as con:
            for pid in pending_ids:con.execute('INSERT INTO rich_ui_hidden_reviews(pending_id,hidden,updated_at) VALUES(?,1,?) ON CONFLICT(pending_id) DO UPDATE SET hidden=1,updated_at=excluded.updated_at',(pid,_now()))
    def hidden_review_ids(self)->set[str]:
        with self.db.read() as con:r=con.execute('SELECT pending_id FROM rich_ui_hidden_reviews WHERE hidden=1').fetchall()
        return {x[0] for x in r}

