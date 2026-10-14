"""Phase 04 grouping and actual-cost allocation; no new financial postings."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

SUPERVISION = 'نظارت'
SUPERVISION_COST = 'کل هزینه نظارت'
SUPERVISION_TAX = 'کل مالیات نظارت'
MAIN = ('نظارت معماری', 'نظارت سازه', 'نظارت مکانیک', 'نظارت برق', 'هماهنگ کننده نظارت')
PAIRS = (
    ('آتش نشانی', 'اصل آتش‌نشانی + مالیات'),
    ('گاز', 'اصل گاز + مالیات'),
    ('آبفا', 'اصل آبفا + مالیات'),
    ('نقشه برداری', 'اصل نقشه‌برداری + مالیات'),
    ('آزمایش میلگرد', 'اصل آزمایش میلگرد + مالیات'),
    ('آزمایش بتن', 'اصل آزمایش بتن + مالیات'),
)


def normalized(text):
    return ' '.join(str(text or '').replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', ' ').split())


def group_of(row):
    if int(row.get('phase_no') or 0) != 4:
        return ''
    title = normalized(row.get('description'))
    if title in (normalized(SUPERVISION_COST), normalized(SUPERVISION_TAX)):
        return SUPERVISION
    if any(title == name or (title.startswith('مالیات') and name in title) for name in MAIN):
        return SUPERVISION
    if title.startswith(('اصل ', 'مالیات ')):
        return next((label for token, label in PAIRS if token in title), '')
    return ''


def grouped_import_rows(rows):
    """Keep workbook leaf refs stable, with zero-budget actual-only summaries."""
    phase = [r for r in rows if int(r.get('phase_no') or 0) == 4]
    if not any(group_of(r) for r in phase):
        return rows
    for r in phase:
        r['section'] = group_of(r) or r.get('section', '')
    for ref, title in (('04-34', SUPERVISION_COST), ('04-35', SUPERVISION_TAX)):
        if any(normalized(r['description']) == normalized(title) for r in phase):
            continue
        # Refuse a custom workbook's conflicting number rather than steal its costs.
        if any(r.get('ref') == ref for r in phase):
            raise ValueError(f'شمارهٔ {ref} برای ردیف دیگری استفاده شده است.')
        phase.append(dict(phase_no=4, phase_name=phase[0]['phase_name'], section=SUPERVISION,
            description=title, cost_type='خدمات', unit='مترمربع', qty=0, qty_current=0,
            qty_actual=0, rate=0, rate_current=0, rate_actual=0, factor=1, total=0,
            status='', source='', sort_order=0, ref=ref))
    order = [SUPERVISION] + [label for _, label in PAIRS]
    indexed = list(enumerate(phase))
    indexed.sort(key=lambda pair: (order.index(pair[1]['section']) if pair[1]['section'] in order else len(order), pair[0]))
    for index, (_, r) in enumerate(indexed, 1):
        r['sort_order'] = index
    result = [r for r in rows if int(r.get('phase_no') or 0) != 4] + [r for _, r in indexed]
    return sorted(result, key=lambda r: (r['phase_no'], r['sort_order']))


def ensure_groups(rich):
    """Adapt an already imported numbered plan without reimporting user prices."""
    rows = rich.list_phase_items(4)
    if not any(group_of(r) for r in rows):
        return
    from budget_rich_v163 import stable
    from finance_db import _now
    now = _now()
    with rich.db.tx() as con:
        for r in rows:
            group = group_of(r)
            if group and r.get('section') != group:
                con.execute('UPDATE rich_phase_items SET section=?,updated_at=? WHERE phase_item_id=?',
                            (group, now, r['phase_item_id']))
        for ref, title in (('04-34', SUPERVISION_COST), ('04-35', SUPERVISION_TAX)):
            if any(normalized(r['description']) == normalized(title) for r in rows):
                continue
            if any(r.get('plan_ref') == ref for r in rows):
                continue
            con.execute('''INSERT INTO rich_phase_items(phase_item_id,phase_no,phase_name,
                section,description,cost_type,unit,qty_estimate,qty_actual,qty_forecast,
                factor,local_estimate_rate,sort_order,plan_ref,active,created_at,updated_at)
                VALUES(?,4,?,?,?,'خدمات','مترمربع',0,0,0,1,0,?,?,1,?,?)''',
                (stable('PHITEM', ref), rows[0]['phase_name'], SUPERVISION, title,
                 max(int(r.get('sort_order') or 0) for r in rows) + (1 if ref == '04-34' else 2), ref, now, now))
        current = [dict(r) for r in con.execute('SELECT * FROM rich_phase_items WHERE phase_no=4 AND active=1 ORDER BY sort_order').fetchall()]
        order = [SUPERVISION] + [label for _, label in PAIRS]
        current.sort(key=lambda r: order.index(group_of(r)) if group_of(r) in order else len(order))
        for index, row in enumerate(current, 1):
            if int(row['sort_order']) != index:
                con.execute('UPDATE rich_phase_items SET sort_order=?,updated_at=? WHERE phase_item_id=?', (index, now, row['phase_item_id']))


def allocate_actuals(rows, totals):
    """Split inclusive principal amounts once, retaining every toman and source."""
    result = dict(totals)
    groups = {}
    for row in rows:
        group = group_of(row)
        if group:
            groups.setdefault(group, []).append(row)
    for group, members in groups.items():
        if group == SUPERVISION:
            principal = next((r for r in members if r['description'] == SUPERVISION_COST), None)
            tax = next((r for r in members if r['description'] == SUPERVISION_TAX), None)
        else:
            principal = next((r for r in members if normalized(r['description']).startswith('اصل ')), None)
            tax = next((r for r in members if normalized(r['description']).startswith('مالیات ')), None)
        if not principal or not tax:
            continue
        base = vat = 0
        sources = set()
        for row in members:
            ref = str(row.get('plan_ref') or '')
            entry = result.pop(ref, None)
            if entry is None:
                continue
            amount, source = entry
            sources.add(source)
            if normalized(row['description']).startswith(('مالیات ', 'کل مالیات ')):
                vat += int(amount)
            else:
                share = int((Decimal(int(amount)) * Decimal('0.9')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                base += share
                vat += int(amount) - share
        if sources:
            source = 'CONTRACTS' if sources == {'CONTRACTS'} else 'EXPENSES'
            result[str(principal['plan_ref'])] = (base, source)
            result[str(tax['plan_ref'])] = (vat, source)
    return result


def entry_choices(rows):
    """Offer the subphase for paired services, rather than competing leaf rows."""
    result, seen = [], set()
    for row in rows:
        group = group_of(row)
        if not group:
            result.append(row)
        elif group not in seen:
            seen.add(group)
            result.append({**row, 'description': group, 'section': group})
        if group == SUPERVISION and row['description'] == SUPERVISION_TAX:
            result.append(row)
    return result
