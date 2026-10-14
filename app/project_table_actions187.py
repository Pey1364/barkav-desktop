"""Project estimate row links, navigation and clipboard actions."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from finance_db import _id, _now
from budget_rich_v163 import as_float

CATEGORIES = {'مصالح': 'MATERIAL', 'اجرت': 'LABOR', 'خدمات': 'SERVICE', 'خرید زمین': 'LAND'}
KINDS = {value: key for key, value in CATEGORIES.items()}
FIELDS = ('description', 'unit', 'section', 'cost_type', 'estimate_rate', 'forecast_rate',
          'actual_rate', 'qty_estimate', 'qty_forecast', 'qty_actual', 'factor', 'source')


def ensure_land_row_links(rich):
    """Repair missing estimate identifiers on existing land rows, keeping IDs.

    Existing numbered plan rows are never renumbered. These are budget links;
    no payment, expense, contract or posted actual total is changed.
    """
    # A retired LAND row is a deliberate deletion, never a missing default.
    with rich.db.read() as con:
        retired = con.execute("SELECT 1 FROM rich_price_items WHERE category='LAND' AND active=0 LIMIT 1").fetchone()
    if not retired:
        rich.ensure_land_price()
    changed = 0
    with rich.db.atomic() as con:
        rows = con.execute("SELECT * FROM rich_phase_items WHERE active=1 AND cost_type='خرید زمین'").fetchall()
        for stored in rows:
            row = dict(stored); before = dict(row)
            price = con.execute('SELECT * FROM rich_price_items WHERE price_id=?', (row.get('price_id'),)).fetchone()
            if not price:
                matches = con.execute("SELECT * FROM rich_price_items WHERE category='LAND' AND active=1 AND visible=1 AND description=? AND unit=? AND estimate_rate=?",
                    (row.get('description'), row.get('unit'), int(row.get('local_estimate_rate') or 0))).fetchall()
                if len(matches) == 1:
                    price = matches[0]
                    con.execute('UPDATE rich_phase_items SET price_id=?,updated_at=? WHERE phase_item_id=?', (price['price_id'], _now(), row['phase_item_id']))
                    changed += 1
            if not price or (price['active'] and (price['category'] != 'LAND' or not str(price['code'] or '').strip() or not price['visible'])):
                free = con.execute("""SELECT * FROM rich_price_items p WHERE category='LAND' AND active=1
                    AND visible=1 AND code='1' AND description='خرید زمین'
                    AND estimate_rate=0 AND forecast_rate=0 AND actual_rate=0
                    AND NOT EXISTS(SELECT 1 FROM rich_phase_items pi WHERE pi.price_id=p.price_id AND pi.active=1)""").fetchone()
                if free and not price:
                    pid = free['price_id']
                else:
                    shared = price and con.execute("SELECT COUNT(*) FROM rich_phase_items WHERE price_id=? AND active=1 AND cost_type<>'خرید زمین'", (price['price_id'],)).fetchone()[0]
                    pid = price['price_id'] if price and not shared else _id('PRICE')
                    if free and free['price_id'] != pid:
                        con.execute('UPDATE rich_price_items SET active=0,updated_at=? WHERE price_id=?', (_now(), free['price_id']))
                        rich._log('PRICE', free['price_id'], 'REPLACE_UNUSED_LAND_DEFAULT_187', dict(free), rich.get_price(free['price_id']))
                old_price = rich.get_price(pid) or {}
                codes = con.execute("SELECT code FROM rich_price_items WHERE category='LAND' AND active=1 AND visible=1 AND price_id<>?", (pid,)).fetchall()
                code = '1' if free else str(int(max((as_float(r['code']) for r in codes), default=0)) + 1)
                estimate = int((price['estimate_rate'] if price else row.get('local_estimate_rate')) or 0)
                forecast = int(price['forecast_rate'] or 0) if price else estimate
                actual = int((price['actual_rate'] if price else row.get('local_actual_rate')) or 0)
                now = _now()
                con.execute("""INSERT INTO rich_price_items(price_id,code,description,category,unit,
                    estimate_rate,actual_rate,forecast_rate,status,source,visible,aggregate,group_key,active,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,1,0,'',1,?,?) ON CONFLICT(price_id) DO UPDATE SET
                    code=excluded.code,category='LAND',visible=1,active=1,description=excluded.description,
                    unit=excluded.unit,estimate_rate=excluded.estimate_rate,actual_rate=excluded.actual_rate,
                    forecast_rate=excluded.forecast_rate,updated_at=excluded.updated_at""",
                    (pid, code, row.get('description') or 'خرید زمین', 'LAND', row.get('unit') or 'مترمربع',
                     estimate, actual, forecast, 'ثبت دستی', str(row.get('phase_no') or ''), now, now))
                con.execute('UPDATE rich_phase_items SET price_id=?,updated_at=? WHERE phase_item_id=?', (pid, now, row['phase_item_id']))
                rich._log('PRICE', pid, 'REPAIR_LAND_LINK_187', old_price, rich.get_price(pid))
                changed += 1
            if not str(row.get('plan_ref') or '').strip():
                refs = con.execute('SELECT plan_ref FROM rich_phase_items WHERE phase_no=? AND active=1', (row['phase_no'],)).fetchall()
                numbers = [int(str(r['plan_ref']).split('-')[1]) for r in refs
                           if len(str(r['plan_ref'] or '').split('-')) > 1 and str(r['plan_ref']).split('-')[1].isdigit()]
                ref = f"{int(row['phase_no']):02d}-{max(numbers, default=0) + 1}"
                con.execute('UPDATE rich_phase_items SET plan_ref=?,updated_at=? WHERE phase_item_id=?', (ref, _now(), row['phase_item_id']))
                changed += 1
            after = rich.get_phase_item(row['phase_item_id'])
            if after != before:
                rich._log('PHASE_ITEM', row['phase_item_id'], 'REPAIR_LAND_LINK_187', before, after)
    return changed


def key_at(table, iid):
    """Resolve a row under the pointer in the table's current sort order."""
    return next((key for item, (_v, _s, key) in zip(table.tree.get_children(), table._sorted()) if item == iid), None)


def select_key(table, key):
    for iid, (_values, _state, row_key) in zip(table.tree.get_children(), table._sorted()):
        if row_key == key:
            table.tree.selection_set(iid)
            table.tree.focus(iid)
            table.tree.see(iid)
            return True
    return False


def popup_menu(parent, event, commands):
    menu = tk.Menu(parent, tearoff=0)
    menu.bind('<Unmap>', lambda e: menu.after_idle(menu.destroy) if e.widget is menu else None, add='+')
    for label, command in commands:
        menu.add_command(label=label, command=command)
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()
    return 'break'


class ProjectTableActions:
    def __init__(self, app, refresh):
        self.app = app; self.rich = app.rich; self.refresh = refresh
        self.clipboard = None

    def context_selection(self, table, event):
        iid = table.tree.identify_row(event.y)
        if iid:
            if iid not in table.tree.selection():
                table.tree.selection_set(iid)
            table.tree.focus(iid)
        return iid

    def _copy(self, kind, rows):
        if not rows:
            return
        if kind != 'price':
            from project_plan_stage18_7 import _rates
            rows = [dict(row, **dict(zip(('estimate_rate', 'forecast_rate', 'actual_rate'), _rates(row)))) for row in rows]
        text = '\n'.join('\t'.join(str(row.get(key) if row.get(key) is not None else '') for key in FIELDS) for row in rows)
        self.app.clipboard_clear(); self.app.clipboard_append(text)
        self.clipboard = (kind, [dict(row) for row in rows], text)

    def _read(self):
        try:
            return self.clipboard[:2] if self.clipboard and self.app.clipboard_get() == self.clipboard[2] else (None, [])
        except tk.TclError:
            return None, []

    def plan_rows(self):
        selected = self.app.project_plan187.table.selected_keys()
        all_rows = self.rich.all_phase_items()
        result = []
        for row in all_rows:
            for group, rid in selected:
                if rid == row['phase_item_id'] or (group and int(group[1]) == int(row['phase_no'])
                    and (group[0] == 'phase' or (group[2] == row['cost_type']
                        and (group[0] == 'kind' or group[3] == row.get('section'))))):
                    result.append(row); break
        return result

    def copy_plan(self):
        self._copy('plan', self.plan_rows())

    def copy_prices(self, panel):
        rows = [self.rich.get_price(pid) for pid in panel.table.selected_keys()]
        self._copy('price', [row for row in rows if row])

    def paste_plan(self, *, phase_no=None, phase_name=None, after=None):
        kind, rows = self._read()
        if not rows:
            return
        plan = self.app.project_plan187
        selected = plan._selected_row() or {}
        node = plan._selected_node()
        phase_no = int(phase_no or selected.get('phase_no') or (node[1] if node else 1))
        phase_name = phase_name if phase_name is not None else next((r.get('phase_name') or '' for r in self.rich.all_phase_items() if int(r['phase_no']) == phase_no), '')
        after = after or selected.get('phase_item_id')
        created = None
        try:
            with self.rich.db.atomic():
                for row in rows:
                    data = {key: row.get(key) for key in FIELDS if row.get(key) is not None}
                    if kind == 'price':
                        data.update(cost_type=KINDS.get(row.get('category'), 'خدمات'), price_id=row['price_id'], qty_estimate=0, qty_forecast=0, qty_actual=0, factor=1)
                    created = self.rich.add_phase_item(phase_no, phase_name, data)
                    self.rich.place_phase_item(created, after, renumber_price=kind != 'price')
                    after = created
        except Exception as exc:
            messagebox.showerror('پیست ردیف', str(exc), parent=self.app); return
        self.refresh()
        if created:
            self.app.report_nb.select(plan); plan._reveal(created)

    def paste_prices(self, panel):
        _kind, rows = self._read()
        if not rows:
            return
        try:
            with self.rich.db.atomic() as con:
                existing = panel._codes(); selected = panel.selected()
                position = next((i + 1 for i, (_code, pid) in enumerate(existing) if selected and pid == selected['price_id']), len(existing))
                order = [pid for _code, pid in existing]
                for offset, row in enumerate(rows):
                    pid = _id('PRICE'); now = _now()
                    con.execute("""INSERT INTO rich_price_items(price_id,code,description,category,unit,
                        estimate_rate,actual_rate,forecast_rate,status,source,visible,aggregate,group_key,active,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,1,0,'',1,?,?)""",
                        (pid, '', row.get('description') or 'ردیف جدید', panel.category, row.get('unit') or '',
                         int(row.get('estimate_rate') or 0), int(row.get('actual_rate') or 0), int(row.get('forecast_rate') or 0),
                         'ثبت دستی', row.get('source') or 'GUI', now, now))
                    order.insert(position + offset, pid)
                    self.rich._log('PRICE', pid, 'CREATE_COPY_187', {}, self.rich.get_price(pid))
                for code, pid in enumerate(order, 1):
                    con.execute('UPDATE rich_price_items SET code=?,updated_at=? WHERE price_id=?', (str(code), _now(), pid))
            self.refresh(); panel.filter_text.set(''); select_key(panel.table, order[position])
        except Exception as exc:
            messagebox.showerror('پیست قیمت', str(exc), parent=self.app)

    def plan_to_price(self, row):
        if not row:
            return
        price = self.rich.get_price(row.get('price_id')) or {}
        panel = self.app.price_panels187.get(price.get('category'))
        if panel is None:
            messagebox.showinfo('تب قیمت', 'قیمت متناظر در تب‌های قیمت ثبت نشده است.', parent=self.app); return
        panel.filter_text.set(''); panel.refresh()
        self.app.report_nb.select(panel)
        select_key(panel.table, price['price_id'])
        self.app._last_plan_item187 = row['phase_item_id']

    def price_to_plan(self, price):
        if not price:
            return
        rows = [r for r in self.rich.all_phase_items() if r.get('price_id') == price['price_id']]
        if not rows:
            messagebox.showinfo('پلان کلی', 'این قیمت هنوز در پلان کلی استفاده نشده است.', parent=self.app); return
        plan = self.app.project_plan187
        self.app.report_nb.select(plan)
        plan.filter_field.set('همه'); plan.filter_value.set('همه')
        prior = getattr(self.app, '_last_plan_item187', None)
        row = next((r for r in rows if r['phase_item_id'] == prior), rows[0])
        for linked in rows:
            number = int(linked['phase_no']); cost = linked['cost_type']
            plan._open.update({('phase', number), ('kind', number, cost)})
            if linked.get('section'):
                plan._open.add(('section', number, cost, linked['section']))
        plan._cache = None; plan.refresh()
        ids = {r['phase_item_id'] for r in rows}
        displayed = {rid: iid for iid, (_v, _s, (_g, rid))
                     in zip(plan.table.tree.get_children(), plan.table._sorted()) if rid in ids}
        plan.table.tree.selection_set(list(displayed.values()))
        target = displayed.get(row['phase_item_id'])
        if target:
            plan.table.tree.focus(target); plan.table.tree.see(target)

    def phase_to_plan(self, phase_no):
        plan = self.app.project_plan187
        plan.filter_field.set('همه'); plan.filter_value.set('همه')
        self.app.report_nb.select(plan)
        plan._open.add(('phase', int(phase_no)))
        for row in self.rich.list_phase_items(int(phase_no)):
            plan._open.add(('kind', int(phase_no), row['cost_type']))
        plan._cache = None; plan.refresh()
        select_key(plan.table, (('phase', int(phase_no)), None))

    def phase_selected(self):
        return list(self.app.phase_table.selected_rows())

    def add_phase(self):
        from project_plan_stage18_7 import PlanRowWindow187
        number = max((int(r['phase_no']) for r in self.rich.all_phase_items()), default=0) + 1
        PlanRowWindow187(self.app, rich=self.rich, row={'phase_no': number, 'phase_name': '', 'factor': 1}, on_saved=lambda _id: self.refresh())

    def copy_phases(self):
        numbers = {int(row['phase_no']) for row in self.phase_selected()}
        self._copy('phase', [r for r in self.rich.all_phase_items() if int(r['phase_no']) in numbers])

    def paste_phases(self):
        kind, rows = self._read()
        if kind != 'phase' or not rows:
            return
        number = max((int(r['phase_no']) for r in self.rich.all_phase_items()), default=0) + 1
        groups = {}
        for row in rows:
            groups.setdefault(int(row['phase_no']), []).append(row)
        try:
            with self.rich.db.atomic():
                for offset, group in enumerate(groups.values()):
                    for row in group:
                        data = {key: row.get(key) for key in FIELDS if row.get(key) is not None}
                        data['price_id'] = row.get('price_id')
                        self.rich.add_phase_item(number + offset, row.get('phase_name') or '', data)
            self.refresh(); self.phase_to_plan(number)
        except Exception as exc:
            messagebox.showerror('پیست فاز', str(exc), parent=self.app)

    def delete_phases(self):
        rows = self.phase_selected()
        if not rows:
            return
        from table_actions import select_delete_rows
        rows = select_delete_rows(self.app, rows, messagebox=messagebox)
        if not rows:
            return
        try:
            with self.rich.db.atomic():
                for phase in rows:
                    for row in self.rich.list_phase_items(int(phase['phase_no'])):
                        self.rich.delete_phase_item(row['phase_item_id'])
            self.refresh()
        except Exception as exc:
            messagebox.showerror('حذف فاز', str(exc), parent=self.app)

    def phase_menu(self, event):
        iid = self.context_selection(self.app.phase_table, event)
        rows = self.phase_selected()
        target = getattr(self.app.phase_table, '_iid_to_row', {}).get(iid) or (rows[0] if rows else None)
        return popup_menu(self.app, event, [
            ('افزودن', self.add_phase), ('کپی', self.copy_phases), ('پیست', self.paste_phases),
            ('حذف', self.delete_phases),
            ('رفتن به پلان کلی', lambda: self.phase_to_plan(int(target['phase_no'])) if target else None),
        ])
