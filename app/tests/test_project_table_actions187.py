"""Acceptance on disposable SQLite and real Tk, never live project data."""
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import pytest
from test_transaction_lifecycle_matrix import runtime
from test_stage18_7_record_fields import root
from project_plan_stage18_7 import PlanRowWindow187, _rates, price_code
from project_table_actions187 import ensure_land_row_links, select_key, CATEGORIES
from reports_stage18_7 import install_project_plan_187, _refresh_plan_187, PriceEditor187, PhaseDetailDialog187
from barkav.features.dashboard import SmartTable
from ui_stage18_3 import en

@pytest.fixture
def app(root, runtime):
    root.rich = runtime.rich
    root.report_nb = ttk.Notebook(root); root.report_nb.pack(fill='both', expand=True)
    root.report_nb.add(ttk.Frame(root.report_nb), text='فازها')
    root.phase_table = SmartTable(root, [('phase_no', 'ردیف', 70), ('phase', 'فاز', 140)], title='فازها')
    root.phase_table.pack(fill='x')
    root.refresh_reports = lambda: root.phase_table.set_rows(runtime.rich.list_phase_summary(), lambda r: [r['phase_no'], r['phase']])
    root._phase_summary_live = runtime.rich.list_phase_summary
    root.open_phase_by_no = lambda no: None
    install_project_plan_187(root); root.refresh_reports(); root.update()
    return root

def add(app, cost='خدمات', **extra):
    data = dict(description='نمونه ' + cost, cost_type=cost, unit='عدد', qty_estimate=2,
        qty_forecast=3, qty_actual=1, factor=1, estimate_rate=100, forecast_rate=200, actual_rate=300)
    data.update(extra)
    rid = app.rich.add_phase_item(1, 'فاز نمونه', data); _refresh_plan_187(app)
    return rid

def test_land_missing_numbers_preserve_existing_refs_and_posted_cost(app):
    rid = add(app, 'خرید زمین'); other = add(app, 'مصالح')
    ref = app.rich.get_phase_item(other)['plan_ref']; pid = app.rich.get_phase_item(rid)['price_id']
    with app.rich.db.tx() as con:
        con.execute("UPDATE rich_price_items SET code='' WHERE price_id=?", (pid,))
        con.execute("UPDATE rich_phase_items SET plan_ref='',total_actual=77 WHERE phase_item_id=?", (rid,))
    assert ensure_land_row_links(app.rich) > 0
    row = next(r for r in app.rich.all_phase_items() if r['phase_item_id'] == rid)
    assert price_code(row) == 'D1' and row['plan_ref'] and row['total_actual'] == 77
    assert app.rich.get_phase_item(other)['plan_ref'] == ref
    assert ensure_land_row_links(app.rich) == 0

def test_land_missing_link_reuses_matching_price(app):
    rid = add(app, 'خرید زمین'); pid = app.rich.get_phase_item(rid)['price_id']
    with app.rich.db.tx() as con:
        con.execute("UPDATE rich_phase_items SET price_id=NULL,plan_ref='' WHERE phase_item_id=?", (rid,))
    ensure_land_row_links(app.rich); row = app.rich.get_phase_item(rid)
    assert row['price_id'] == pid and row['plan_ref']
    assert len(app.rich.list_prices('LAND')) == 1

@pytest.mark.parametrize('cost', list(CATEGORIES))
def test_both_directions_in_real_editors(app, cost):
    rid = add(app, cost); raw = app.rich.get_phase_item(rid); pid = raw['price_id']
    pane = app.price_panels187[CATEGORIES[cost]]
    editor = PlanRowWindow187(app, rich=app.rich, row=raw, on_saved=lambda _id: _refresh_plan_187(app))
    assert en(editor.values['forecast_rate'].get()) == '200'
    for key, value in zip(editor.RATES, (1230, 2340, 3450)): editor.values[key].set(str(value))
    editor.save(); app.update(); price = app.rich.get_price(pid)
    assert tuple(price[k] for k in editor.RATES) == (1230, 2340, 3450)
    assert tuple(en(v) for v in pane.table.sorted_rows()[0][4:7]) == ('1,230', '2,340', '3,450')
    dialog = PriceEditor187(app, app.rich, price, lambda: _refresh_plan_187(app))
    for key, value in zip(editor.RATES, (4560, 0, 6780)): dialog.vars[key].set(str(value))
    dialog.save(); app.update()
    row = next(r for r in app.rich.all_phase_items() if r['phase_item_id'] == rid)
    assert _rates(row) == (4560, 0, 6780)
    reopened = PlanRowWindow187(app, rich=app.rich, row=app.rich.get_phase_item(rid))
    assert tuple(en(reopened.values[k].get()).replace(',', '') for k in reopened.RATES) == ('4560', '0', '6780')
    reopened.close()

def test_navigation_and_filters(app):
    rid = add(app, 'خرید زمین', section='بخش زمین'); row = app.rich.get_phase_item(rid)
    pane = app.price_panels187['LAND']; pane.filter_text.set('پنهان'); actions = app.project_table_actions187
    actions.plan_to_price(row)
    assert app.report_nb.select() == str(pane) and pane.table.selected_key() == row['price_id']
    plan = app.project_plan187; plan.filter_field.set('مصالح')
    actions.price_to_plan(app.rich.get_price(row['price_id']))
    assert app.report_nb.select() == str(plan) and plan.table.selected_key() == (None, rid)
    actions.phase_to_plan(1)
    assert plan.table.selected_key() == (('phase', 1), None)

def test_shared_price_navigation(app):
    a = add(app, 'مصالح'); pid = app.rich.get_phase_item(a)['price_id']
    b = add(app, 'مصالح', price_id=pid, section='بخش دوم')
    app.project_table_actions187.price_to_plan(app.rich.get_price(pid))
    assert {rid for _g, rid in app.project_plan187.table.selected_keys()} == {a, b}

def test_plan_copy_paste_codes_and_no_duplicate_actual(app):
    first = add(app); second = add(app)
    with app.rich.db.tx() as con: con.execute('UPDATE rich_phase_items SET total_actual=77 WHERE phase_item_id=?', (first,))
    app.project_plan187._reveal(first); actions = app.project_table_actions187
    actions.copy_plan(); actions.paste_plan(); rows = app.rich.list_phase_items(1)
    assert len(rows) == 3 and [price_code(r) for r in rows] == ['C1', 'C2', 'C3']
    clone = next(r for r in rows if r['phase_item_id'] not in (first, second))
    assert clone['plan_ref'] and clone['total_actual'] == 0 and _rates(clone) == (100, 200, 300)

def test_price_and_phase_copy_paste(app):
    rid = add(app, 'خرید زمین'); row = app.rich.get_phase_item(rid); pane = app.price_panels187['LAND']
    select_key(pane.table, row['price_id']); actions = app.project_table_actions187
    actions.copy_prices(pane); actions.paste_prices(pane)
    assert [r[1] for r in pane.table.sorted_rows()] == ['D1', 'D2']
    app.refresh_reports(); app.phase_table.tree.selection_set(app.phase_table.tree.get_children()[0])
    actions.copy_phases(); actions.paste_phases(); clone = app.rich.list_phase_items(2)
    assert len(clone) == 1 and clone[0]['price_id'] == row['price_id']
    assert clone[0]['total_actual'] == 0 and clone[0]['plan_ref']

def test_all_context_menus(app, monkeypatch):
    rid = add(app, 'خرید زمین'); plan = app.project_plan187; plan._reveal(rid); menus = []
    monkeypatch.setattr(tk.Menu, 'tk_popup', lambda menu, *_: menus.append([menu.entrycget(i, 'label') for i in range(menu.index('end') + 1)]))
    event = SimpleNamespace(y=0, x_root=5, y_root=5)
    plan._context_menu(event)
    for pane in app.price_panels187.values(): pane._context_menu(event)
    app.project_table_actions187.phase_menu(event)
    assert len(menus) == 6
    assert all({'افزودن', 'کپی', 'پیست', 'حذف'} <= set(labels) for labels in menus)
    assert 'رفتن به تب قیمت' in menus[0] and all('رفتن به پلان کلی' in labels for labels in menus[1:])

def test_phase_detail_shared_editor(app):
    rid = add(app, 'خرید زمین')
    dialog = PhaseDetailDialog187(app, app.rich, 1, 'فاز نمونه', lambda: _refresh_plan_187(app))
    dialog.edit_item(app.rich.list_phase_items(1)[0])
    editor = next(w for w in dialog.winfo_children() if isinstance(w, PlanRowWindow187))
    editor.values['forecast_rate'].set('987'); editor.save()
    assert app.rich.get_price(app.rich.get_phase_item(rid)['price_id'])['forecast_rate'] == 987
    dialog.destroy()


def test_land_repair_does_not_restore_deleted_price(app):
    rid = add(app, 'خرید زمین'); pid = app.rich.get_phase_item(rid)['price_id']
    with app.rich.db.tx() as con:
        con.execute('UPDATE rich_price_items SET active=0 WHERE price_id=?', (pid,))
        con.execute("UPDATE rich_phase_items SET plan_ref='' WHERE phase_item_id=?", (rid,))
    ensure_land_row_links(app.rich)
    assert app.rich.get_price(pid)['active'] == 0
    assert app.rich.get_phase_item(rid)['price_id'] == pid
    assert app.rich.get_phase_item(rid)['plan_ref']
    assert app.rich.list_prices('LAND') == []


def test_price_paste_into_plan_keeps_shared_link(app):
    rid = add(app, 'مصالح'); row = app.rich.get_phase_item(rid); pane = app.price_panels187['MATERIAL']
    select_key(pane.table, row['price_id']); actions = app.project_table_actions187
    actions.copy_prices(pane); app.project_plan187._reveal(rid); actions.paste_plan()
    rows = app.rich.list_phase_items(1)
    assert len(rows) == 2 and all(r['price_id'] == row['price_id'] for r in rows)
    app.rich.save_price_rates(row['price_id'], 111, 333, 222)
    assert all(_rates(r) == (111, 222, 333) for r in app.rich.list_phase_items(1))
    assert all(r['total_actual'] == 0 for r in rows)


def test_phase_delete_is_soft_and_keeps_price(app, monkeypatch):
    rid = add(app, 'خرید زمین'); pid = app.rich.get_phase_item(rid)['price_id']
    app.refresh_reports(); app.phase_table.tree.selection_set(app.phase_table.tree.get_children()[0])
    import table_actions
    monkeypatch.setattr(table_actions, 'select_delete_rows', lambda _app, rows, **_kw: rows)
    app.project_table_actions187.delete_phases()
    assert app.rich.list_phase_items(1) == []
    assert app.rich.get_phase_item(rid)['active'] == 0
    assert app.rich.get_price(pid)['active'] == 1


def test_context_navigation_targets_clicked_row_in_multiselection(app, monkeypatch):
    a = add(app, 'مصالح'); b = add(app, 'مصالح')
    plan = app.project_plan187; plan._reveal(a); plan._reveal(b)
    actions = app.project_table_actions187; menus = []; destinations = []
    monkeypatch.setattr(tk.Menu, 'tk_popup', lambda menu, *_: menus.append(menu))
    monkeypatch.setattr(actions, 'plan_to_price', lambda row: destinations.append(row['phase_item_id']))
    item_ids = {key[1]: iid for iid, (_v, _s, key) in zip(plan.table.tree.get_children(), plan.table._sorted()) if key[1]}
    plan.table.tree.selection_set([item_ids[a], item_ids[b]])
    monkeypatch.setattr(plan.table.tree, 'identify_row', lambda _y: item_ids[b])
    event = SimpleNamespace(y=0, x_root=5, y_root=5); plan._context_menu(event)
    menus[-1].invoke(menus[-1].index('end'))
    assert destinations == [b]
    pane = app.price_panels187['MATERIAL']; pid = app.rich.get_phase_item(b)['price_id']
    price_ids = {key: iid for iid, (_v, _s, key) in zip(pane.table.tree.get_children(), pane.table._sorted())}
    pane.table.tree.selection_set(list(price_ids.values()))
    monkeypatch.setattr(pane.table.tree, 'identify_row', lambda _y: price_ids[pid])
    monkeypatch.setattr(actions, 'price_to_plan', lambda row: destinations.append(row['price_id']))
    pane._context_menu(event); menus[-1].invoke(menus[-1].index('end'))
    assert destinations[-1] == pid and len(pane.table.tree.selection()) == 2
