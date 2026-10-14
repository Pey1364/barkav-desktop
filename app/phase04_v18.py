from __future__ import annotations

from typing import Any
from finance_db import _now
from budget_rich_v163 import stable

MAIN_NAMES = [
    'نظارت معماری', 'نظارت سازه', 'نظارت مکانیک', 'نظارت برق', 'هماهنگ‌کننده نظارت'
]


def _norm(s: Any) -> str:
    return str(s or '').replace('\u200c',' ').replace('ي','ی').replace('ك','ک').strip()


def apply_phase04_rules_v18(rich) -> dict[str, Any]:
    """Idempotently adapt the rich Phase-04 budget to the approved V18 rules.

    * The five primary supervision booklets become one aggregate line:
      sum(base booklet rates) × project volume × 1.10 VAT; no organization share.
    * For every other Phase-04 item that has a dedicated 10% tax row, fold that
      tax into the principal estimate/forecast rate and hide the tax row.
      Organization-share rows stay independent and therefore remain based on the
      pre-VAT base imported from the workbook.

    This touches only the rich editable budget mirror, not historical financial
    transactions. Re-importing a workbook can safely be followed by this function.
    """
    db=rich.db;now=_now()
    with db.read() as con:
        # The rebuilt reference workbook states these rows itself: every tax
        # line is listed and numbered, and the five booklets are five rows.
        # Applying the rule on top of it collapses ten rows into one and folds
        # the tax back into the rates, so the screens stopped matching the
        # file. A numbered row is the workbook's own, and is left alone.
        numbered=int(con.execute("SELECT COUNT(*) FROM rich_phase_items WHERE phase_no=4 AND active=1 AND plan_ref<>''").fetchone()[0] or 0)
        if numbered:
            return {'changed':False,'reason':'workbook-states-phase-04-itself'}
        rows=[dict(r) for r in con.execute("SELECT * FROM rich_phase_items WHERE phase_no=4 AND active=1 ORDER BY sort_order").fetchall()]
    if not rows:return {'changed':False,'reason':'phase04-empty'}

    by_desc={_norm(r['description']):r for r in rows}
    main=[]
    for name in MAIN_NAMES:
        r=by_desc.get(_norm(name))
        if r:main.append(r)

    changed=False
    with db.tx() as con:
        # 1) Five primary supervision booklets => one aggregate price and one phase line.
        if main:
            qty=max(float(r.get('qty_estimate') or 0) for r in main) or 1.0
            phase_name=main[0].get('phase_name') or 'نظام مهندسی، نظارت و کنترل کیفی'
            price_id=stable('PRICE','PH04','MAIN_SUPERVISION')
            phase_item_id=stable('PHITEM',4,'حق الزحمه نظارت های اصلی')
            components=[]
            for idx,r in enumerate(main,1):
                base=int(r.get('local_estimate_rate') or 0)
                components.append((idx,r['description'],base))
            est_rate=int(round(sum(base*1.10 for _,_,base in components)))
            con.execute('''INSERT INTO rich_price_items(price_id,code,description,category,unit,estimate_rate,actual_rate,forecast_rate,status,source,visible,aggregate,group_key,active,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
                ON CONFLICT(price_id) DO UPDATE SET description=excluded.description,category=excluded.category,unit=excluded.unit,
                estimate_rate=excluded.estimate_rate,visible=1,aggregate=1,group_key=excluded.group_key,active=1,updated_at=excluded.updated_at''',
                (price_id,'','حق‌الزحمه نظارت‌های اصلی','SERVICE','مترمربع',est_rate,est_rate,est_rate,'V18','پنج دفترچه × 1.10 مالیات',1,1,'PH04_MAIN_SUPERVISION',now,now))
            # Preserve manual forecast component rates if already present; create missing ones with 1.10 coefficient.
            existing={_norm(r['description']):dict(r) for r in con.execute("SELECT * FROM rich_price_components WHERE price_id=?",(price_id,)).fetchall()}
            con.execute("UPDATE rich_price_components SET active=0,updated_at=? WHERE price_id=?",(now,price_id))
            forecast_base_total=0
            for idx,desc,base in components:
                cid=stable('PCOMP',price_id,desc)
                old=existing.get(_norm(desc))
                unit_rate=int(old.get('unit_rate') if old else base)
                total=unit_rate;forecast_base_total+=total
                con.execute('''INSERT INTO rich_price_components(component_id,price_id,description,unit,quantity,coefficient,unit_rate,total,source,sort_order,active,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?) ON CONFLICT(component_id) DO UPDATE SET description=excluded.description,unit=excluded.unit,quantity=1,
                    coefficient=1.0,unit_rate=CASE WHEN rich_price_components.unit_rate>0 THEN rich_price_components.unit_rate ELSE excluded.unit_rate END,
                    total=ROUND((CASE WHEN rich_price_components.unit_rate>0 THEN rich_price_components.unit_rate ELSE excluded.unit_rate END)*1.10),source=excluded.source,sort_order=excluded.sort_order,active=1,updated_at=excluded.updated_at''',
                    (cid,price_id,desc,'دفترچه',1.0,1.0,unit_rate,total,'نرخ پایه دفترچه؛ مالیات 10٪ روی جمع پنج دفترچه اعمال می‌شود',idx,now,now))
            con.execute("UPDATE rich_price_items SET forecast_rate=?,actual_rate=CASE WHEN actual_rate=0 THEN ? ELSE actual_rate END,updated_at=? WHERE price_id=?",(int(round(forecast_base_total*1.10)),est_rate,now,price_id))
            con.execute('''INSERT INTO rich_phase_items(phase_item_id,phase_no,phase_name,section,description,cost_type,unit,qty_estimate,qty_actual,qty_forecast,factor,price_id,local_estimate_rate,status,source,sort_order,active,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?) ON CONFLICT(phase_item_id) DO UPDATE SET phase_name=excluded.phase_name,section=excluded.section,description=excluded.description,
                cost_type=excluded.cost_type,unit=excluded.unit,qty_estimate=excluded.qty_estimate,factor=1,price_id=excluded.price_id,local_estimate_rate=excluded.local_estimate_rate,
                status=excluded.status,source=excluded.source,sort_order=excluded.sort_order,active=1,updated_at=excluded.updated_at''',
                (phase_item_id,4,phase_name,'حق‌الزحمه نظارت‌های اصلی','حق‌الزحمه نظارت‌های اصلی','خدمات','مترمربع',qty,0,qty,1.0,price_id,est_rate,'V18','جمع پنج دفترچه × حجم × 1.10؛ بدون سهم نظام',1,now,now))
            ids=[r['phase_item_id'] for r in main]
            # Hide the five individual principals and their five tax rows from Phase 04.
            for r in rows:
                d=_norm(r['description'])
                if r['phase_item_id'] in ids or (d.startswith('مالیات 10٪') and any(_norm(n) in d for n in MAIN_NAMES)):
                    con.execute("UPDATE rich_phase_items SET active=0,updated_at=? WHERE phase_item_id=?",(now,r['phase_item_id']));changed=True

        # 2) Other Phase-04 items: fold matching 10% tax into principal rate, keep org share separate.
        active=[dict(r) for r in con.execute("SELECT * FROM rich_phase_items WHERE phase_no=4 AND active=1 ORDER BY sort_order").fetchall()]
        taxes=[]
        for r in active:
            d=_norm(r['description'])
            if d.startswith('مالیات 10٪'):
                base_name=d.replace('مالیات 10٪','',1).strip();taxes.append((r,base_name))
        for tax,base_name in taxes:
            principal=None
            for r in active:
                d=_norm(r['description'])
                # Imported rows usually use "اصل X" while tax uses "X".
                if d==base_name or d==f'اصل {base_name}':principal=r;break
            if not principal:continue
            base=int(principal.get('local_estimate_rate') or 0)
            if base<=0:continue
            vat_rate=int(round(base*1.10))
            con.execute("UPDATE rich_phase_items SET local_estimate_rate=?,updated_at=? WHERE phase_item_id=?",(vat_rate,now,principal['phase_item_id']))
            if principal.get('price_id'):
                con.execute("UPDATE rich_price_items SET estimate_rate=?,forecast_rate=CASE WHEN forecast_rate=? OR forecast_rate=0 THEN ? ELSE forecast_rate END,updated_at=? WHERE price_id=?",(vat_rate,base,vat_rate,now,principal['price_id']))
            con.execute("UPDATE rich_phase_items SET active=0,updated_at=? WHERE phase_item_id=?",(now,tax['phase_item_id']))
            changed=True
    return {'changed':changed,'main_count':len(main)}
