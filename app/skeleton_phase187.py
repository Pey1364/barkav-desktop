"""Phase 08 (اسکلت) sub-phase groups: «میلگرد» with its sizes and «آزمایشگاه» with the two tests.

The groups live in the plan lines' ``section`` (what the project management tab already groups by) and in the
Data Entry sub-phase choices; no financial posting is touched. A line keeps its ``plan_ref``, so costs already
allocated to it stay where they are.
"""
from __future__ import annotations

PHASE_NO = 8
REBAR = 'میلگرد'
LAB = 'آزمایشگاه'
LAB_LINES = ('آزمایشگاه بتن', 'آزمایشگاه میلگرد')
LAB_UNIT = 'مورد'
LAB_COST_TYPE = 'خدمات'


def normalized(text):
    return ' '.join(str(text or '').replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ').split())


def group_of(row):
    """The group a phase-08 line belongs to: '' for every other line."""
    if int(row.get('phase_no') or 0) != PHASE_NO:
        return ''
    title = normalized(row.get('description'))
    if title in {normalized(name) for name in LAB_LINES}:
        return LAB
    if title.startswith(REBAR):
        return REBAR
    return ''


def members(rows, group):
    """The lines of one group, for a sub-phase chosen by the group's name."""
    wanted = normalized(group)
    return [row for row in rows if wanted and normalized(group_of(row)) == wanted]


def _new_line(phase_name, description, ref, sort_order):
    return dict(phase_no=PHASE_NO, phase_name=phase_name, section=LAB, description=description,
                cost_type=LAB_COST_TYPE, unit=LAB_UNIT, qty=0, qty_current=0, qty_actual=0,
                rate=0, rate_current=0, rate_actual=0, factor=1, total=0, status='', source='',
                sort_order=sort_order, ref=ref)


def _next_ref(taken):
    numbers = [int(ref.split('-')[1]) for ref in taken
               if ref.startswith(f'{PHASE_NO:02d}-') and ref.split('-')[1].isdigit()]
    return f'{PHASE_NO:02d}-{max(numbers, default=0) + 1}'


def grouped_import_rows(rows):
    """A freshly imported workbook gets the same groups: the sizes under «میلگرد», the two lab lines added."""
    phase = [row for row in rows if int(row.get('phase_no') or 0) == PHASE_NO]
    if not phase:
        return rows
    for row in phase:
        if group_of(row):
            row['section'] = group_of(row)
    present = {normalized(row['description']) for row in phase}
    taken = {str(row.get('ref') or '') for row in phase}
    anchor = max((i for i, row in enumerate(phase) if group_of(row) == REBAR), default=len(phase) - 1)
    for description in LAB_LINES:
        if normalized(description) in present:
            continue
        ref = _next_ref(taken)
        taken.add(ref)
        anchor += 1
        phase.insert(anchor, _new_line(phase[0]['phase_name'], description, ref, 0))
    for index, row in enumerate(phase, 1):
        row['sort_order'] = index
    others = [row for row in rows if int(row.get('phase_no') or 0) != PHASE_NO]
    return sorted(others + phase, key=lambda row: (row['phase_no'], row['sort_order']))


def ensure_groups(rich):
    """Adapt an already imported plan: group the rebar sizes, add the lab lines. Idempotent, keeps all prices."""
    rows = rich.list_phase_items(PHASE_NO)
    if not rows:
        return
    from budget_rich_v163 import stable
    from finance_db import _now
    now = _now()
    present = {normalized(row['description']) for row in rows}
    taken = {str(row.get('plan_ref') or '') for row in rows}
    with rich.db.tx() as con:
        for row in rows:
            if group_of(row) == REBAR and row.get('section') != REBAR:
                con.execute('UPDATE rich_phase_items SET section=?,updated_at=? WHERE phase_item_id=?',
                            (REBAR, now, row['phase_item_id']))
        missing = [name for name in LAB_LINES if normalized(name) not in present]
        for description in missing:
            ref = _next_ref(taken)
            taken.add(ref)
            con.execute('''INSERT INTO rich_phase_items(phase_item_id,phase_no,phase_name,section,description,
                cost_type,unit,qty_estimate,qty_actual,qty_forecast,factor,local_estimate_rate,sort_order,
                plan_ref,active,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,0,0,0,1,0,?,?,1,?,?)''',
                (stable('PHITEM', ref), PHASE_NO, rows[0]['phase_name'], LAB, description, LAB_COST_TYPE,
                 LAB_UNIT, max(int(r.get('sort_order') or 0) for r in rows) + 1, ref, now, now))
        if missing:
            current = [dict(r) for r in con.execute(
                'SELECT * FROM rich_phase_items WHERE phase_no=? AND active=1 ORDER BY sort_order', (PHASE_NO,)).fetchall()]
            base = [r for r in current if group_of(r) != LAB]
            lab = [r for r in current if group_of(r) == LAB]
            last = max((i for i, r in enumerate(base) if group_of(r) == REBAR), default=len(base) - 1)
            ordered = base[:last + 1] + lab + base[last + 1:]
            for index, row in enumerate(ordered, 1):
                if int(row['sort_order']) != index:
                    con.execute('UPDATE rich_phase_items SET sort_order=?,updated_at=? WHERE phase_item_id=?',
                                (index, now, row['phase_item_id']))


def entry_choices(rows):
    """The sub-phase box offers each group by name, followed by its own lines."""
    result, seen = [], set()
    for row in rows:
        group = group_of(row)
        if group and group not in seen:
            seen.add(group)
            result.append({**row, 'description': group, 'section': group})
        result.append(row)
    return result
