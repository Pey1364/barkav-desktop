"""Real Tk edits and approvals on disposable projects for all price categories."""
import pytest
from test_project_table_actions187 import app, add, root, runtime
from test_transaction_lifecycle_matrix import m, register
from project_plan_stage18_7 import (PlanRowWindow187, PhasePlanWindow187,
    PRICE_COLUMNS, PLAN_COLUMNS, _rates, _quantities, _totals, project_actual_rows187)
from reports_stage18_7 import PriceEditor187, _refresh_plan_187, install_actual_cost_sync_187
from transaction_lifecycle import TransactionLifecycle
from data_entry_rules187 import LAND_TITLE, LAND_MODE_KEY
from ui_stage18_3 import en
from contractor_store_stage18_7 import (upsert_contract, upsert_statement,
    delete_contract, delete_statement)
from test_land_wizard_settlement187 import wizard_for

CATEGORIES = [('مصالح', 'MATERIAL'), ('اجرت', 'LABOR'),
              ('خدمات', 'SERVICE'), ('خرید زمین', 'LAND')]


def displayed_price(pane, price_id):
    iid = next(iid for iid, (_values, _state, key) in
               zip(pane.table.tree.get_children(), pane.table._sorted()) if key == price_id)
    return {key: pane.table.tree.set(iid, key) for key, _label in PRICE_COLUMNS}


def number(value):
    return float(str(en(str(value))).replace(',', '').replace('٬', '').replace('*', '').strip() or 0)


def displayed_plan(app, rid):
    panel = app.project_plan187
    for row in panel._all_rows():
        panel._open.update([('phase', row['phase_no']), ('kind', row['phase_no'], row['cost_type']),
                            ('section', row['phase_no'], row['cost_type'], row.get('section') or '')])
    panel.refresh()
    iid = next(iid for iid, (_values, _state, key) in
               zip(panel.table.tree.get_children(), panel.table._sorted()) if key == (None, rid))
    return {key: panel.table.tree.set(iid, key) for key, _label in PLAN_COLUMNS}


def approve_cost(runtime, line, amount, mid):
    title = LAND_TITLE if line['cost_type'] == LAND_TITLE else 'هزینه ساخت'
    payload = dict(v18_title=title, v18_subtype=LAND_TITLE if title == LAND_TITLE else 'نقدی',
        detected_type='EXPENSE', event_date_shamsi='1405/07/10', amount=amount,
        final_amount=amount, invoice_amount=amount, paid_amount=amount,
        payment_state='PAID', payment_method='BANK_TRANSFER',
        description=line['description'], construction_stage=line['phase_name'],
        plan_ref=line['plan_ref'], cost_group={'مصالح': 'مصالح', 'اجرت': 'پیمانکار', 'خدمات': 'خدمات'}.get(line['cost_type'], ''))
    if title == LAND_TITLE:
        payload.update(**{LAND_MODE_KEY: 'نقدی'}, total_debt=amount,
                       land_cash_amount=amount, land_cheque_amount=0, land_barter_amount=0)
    pid = register(runtime, payload, mid)
    m.v18.submit_v18(pid, payload, runtime.rich)
    return pid


@pytest.mark.parametrize('cost,category', CATEGORIES)
def test_real_edits_and_approved_actuals_sync_in_both_directions(app, runtime, cost, category):
    first = add(app, cost, qty_estimate=2, qty_forecast=3, qty_actual=4,
                factor=2, actual_rate=0)
    price_id = runtime.rich.get_phase_item(first)['price_id']
    second = runtime.rich.add_phase_item(2, 'فاز دوم', dict(description='نمونه مشترک',
        cost_type=cost, unit='عدد', price_id=price_id, qty_estimate=5,
        qty_forecast=0, qty_actual=2, factor=3, estimate_rate=100))
    unrelated = runtime.rich.add_phase_item(2, 'فاز دوم', dict(description='قیمت دیگر',
        cost_type=cost, unit='عدد', qty_estimate=900, qty_forecast=900,
        qty_actual=900, estimate_rate=999))
    ids = [first, second]
    approved = [approve_cost(runtime, runtime.rich.get_phase_item(rid), amount, mid)
                for rid, amount, mid in zip(ids, [870, 630], [1, 2])]
    install_actual_cost_sync_187(app)
    _refresh_plan_187(app)
    pane = app.price_panels187[category]
    shown = displayed_price(pane, price_id)
    assert tuple(number(shown[key]) for key in ('qty_estimate', 'qty_forecast', 'qty_actual')) == (7, 3, 6)
    assert number(shown['total_estimate']) == 1900
    assert number(shown['total_forecast']) == 1200
    assert number(shown['total_actual']) == 1500
    assert number(shown['actual_rate']) == 0
    plan_rows = [r for r in app.project_plan187._all_rows() if r['phase_item_id'] in ids]
    assert sum(_totals(row)[2] for row in plan_rows) == number(shown['total_actual'])
    snapshot = runtime.db.snapshot()

    # Save the actual plan editor, including Persian grouped amounts.
    editor = PlanRowWindow187(app, rich=runtime.rich,
        row=runtime.rich.get_phase_item(first), on_saved=lambda _id: _refresh_plan_187(app))
    assert number(editor._total_labels[2].cget('text')) == 870
    editor.values['estimate_rate'].set('۱,۰۰۰')
    editor.values['forecast_rate'].set('۱,۲۰۰')
    editor.values['actual_rate'].set('۷۷')
    editor.values['qty_estimate'].set('3.5')
    editor.values['qty_forecast'].set('4')
    assert number(editor._total_labels[2].cget('text')) == 870
    editor.save()
    shown = displayed_price(pane, price_id)
    assert tuple(number(shown[key]) for key in ('estimate_rate', 'forecast_rate', 'actual_rate')) == (1000, 1200, 77)
    assert number(shown['qty_estimate']) == 8.5
    assert number(shown['total_estimate']) == 22000
    assert number(shown['total_forecast']) == 9600
    assert number(shown['total_actual']) == 1500

    # Save the real price editor and check both linked plan rows, without
    # rewriting quantities, posted costs or the unrelated catalogue item.
    price_editor = PriceEditor187(app, runtime.rich, runtime.rich.get_price(price_id),
                                  lambda: _refresh_plan_187(app))
    price_editor.vars['estimate_rate'].set('2000')
    price_editor.vars['forecast_rate'].set('0')
    price_editor.vars['actual_rate'].set('88')
    price_editor.save()
    linked = [r for r in runtime.rich.all_phase_items() if r['phase_item_id'] in ids]
    assert all(_rates(row) == (2000, 0, 88) for row in linked)
    shown = displayed_price(pane, price_id)
    assert number(shown['total_estimate']) == 44000 and number(shown['total_forecast']) == 0
    assert number(shown['total_actual']) == 1500
    assert runtime.rich.get_phase_item(unrelated)['local_estimate_rate'] == 999
    assert runtime.db.snapshot() == snapshot

    # Removing a posted cost refreshes the derived price total exactly once.
    TransactionLifecycle(runtime.db).reject(approved[0])
    _refresh_plan_187(app)
    assert number(displayed_price(pane, price_id)['total_actual']) == 630
    _refresh_plan_187(app)
    assert number(displayed_price(pane, price_id)['total_actual']) == 630
    TransactionLifecycle(runtime.db).restore(approved[0])
    _refresh_plan_187(app)
    assert number(displayed_price(pane, price_id)['total_actual']) == 1500
    assert runtime.db.snapshot() == snapshot
    runtime.rich.delete_phase_item(second)
    _refresh_plan_187(app)
    shown = displayed_price(pane, price_id)
    assert number(shown['total_actual']) == 870
    assert number(shown['qty_estimate']) == 3.5
    assert runtime.db.snapshot() == snapshot


@pytest.mark.parametrize('cost,category', CATEGORIES)
def test_manual_actual_cost_and_quantities_match_visible_price_cells(app, runtime, cost, category):
    rid = add(app, cost, actual_rate=0, qty_actual=4)
    runtime.rich.save_phase_item(rid, total_actual=4500, qty_actual=5.5)
    _refresh_plan_187(app)
    price_id = runtime.rich.get_phase_item(rid)['price_id']
    shown = displayed_price(app.price_panels187[category], price_id)
    assert number(shown['actual_rate']) == 0
    assert number(shown['qty_actual']) == 5.5
    assert number(shown['total_actual']) == 4500
    row = next(r for r in app.project_plan187._all_rows() if r['phase_item_id'] == rid)
    assert _quantities(row)[2] == number(shown['qty_actual'])
    assert _totals(row)[2] == number(shown['total_actual'])

def test_land_record_keeps_its_plan_reference(root, runtime):
    rid = runtime.rich.add_phase_item(1, LAND_TITLE, dict(description='زمین آزمایشی',
        cost_type=LAND_TITLE, unit='متر', qty_estimate=2, estimate_rate=100))
    row = runtime.rich.get_phase_item(rid)
    pid = approve_cost(runtime, row, 500, 1)
    editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    assert editor.payload_from_form()['plan_ref'] == row['plan_ref']
    with runtime.db.read() as con:
        expense = con.execute('SELECT plan_ref FROM expenses WHERE expense_id=?',
                             (runtime.db.get_pending_item(pid)['payload']['land_expense_id187'],)).fetchone()
    assert expense['plan_ref'] == row['plan_ref']


@pytest.mark.parametrize('cost,category', CATEGORIES)
def test_lump_sum_price_is_total_paid_across_linked_plan_rows(app, runtime, cost, category):
    rid = add(app, cost, unit='مقطوع', qty_actual=0, actual_rate=999)
    first = runtime.rich.get_phase_item(rid)
    second = runtime.rich.add_phase_item(2, 'فاز دوم', dict(description='مقطوع مشترک',
        cost_type=cost, unit='مقطوع', price_id=first['price_id'], qty_actual=0))
    pids = [approve_cost(runtime, runtime.rich.get_phase_item(line), amount, mid)
            for line, amount, mid in [(rid, 1000, 1), (second, 2500, 2)]]
    install_actual_cost_sync_187(app)
    _refresh_plan_187(app)
    shown = displayed_price(app.price_panels187[category], first['price_id'])
    assert number(shown['actual_rate']) == number(shown['total_actual']) == 3500
    assert '*' not in shown['actual_rate']
    assert number(displayed_plan(app, rid)['rate_actual']) == 1000
    TransactionLifecycle(runtime.db).reject(pids[1])
    app.refresh_reports()
    assert number(displayed_price(app.price_panels187[category], first['price_id'])['actual_rate']) == 1000
    runtime.rich.delete_phase_item(rid)
    runtime.rich.delete_phase_item(second)
    app.refresh_reports()
    shown = displayed_price(app.price_panels187[category], first['price_id'])
    assert number(shown['actual_rate']) == number(shown['total_actual']) == 0


@pytest.mark.parametrize('cost,category', CATEGORIES)
def test_missing_actual_quantity_uses_current_unit_price_and_star(app, runtime, cost, category):
    rid = add(app, cost, qty_actual=0, actual_rate=123, factor=3)
    line = runtime.rich.get_phase_item(rid)
    runtime.rich.save_price_rates(line['price_id'], 100, 123, 600)
    approve_cost(runtime, line, 2500, 1)
    install_actual_cost_sync_187(app)
    _refresh_plan_187(app)
    pane = app.price_panels187[category]
    shown = displayed_price(pane, line['price_id'])
    assert number(shown['actual_rate']) == 600
    assert number(shown['qty_actual']) == pytest.approx(2500 / 600, rel=1e-5)
    assert number(shown['total_actual']) == 2500
    assert '*' in shown['actual_rate'] and '*' in shown['qty_actual']
    app.report_nb.select(pane)
    app.update()
    assert pane.actual_note187.winfo_ismapped()
    assert 'مبلغ کل واقعی ÷ قیمت واحد بروز' in pane.actual_note187.cget('text')
    shown_plan = displayed_plan(app, rid)
    assert number(shown_plan['rate_actual']) == 600
    assert number(shown_plan['qty_actual']) == number(shown['qty_actual'])
    assert number(shown_plan['total_actual']) == 2500
    snapshot = runtime.db.snapshot()
    # Merely opening and saving another field must not persist the inferred
    # quantity or copy the derived rate over a manually stored catalogue rate.
    editor = PlanRowWindow187(app, rich=runtime.rich, row=runtime.rich.get_phase_item(rid),
                              on_saved=lambda _id: _refresh_plan_187(app))
    assert number(editor.values['actual_rate'].get()) == 600
    editor.values['source'].set('یادداشت آزمایشی')
    editor.save()
    assert runtime.rich.get_phase_item(rid)['qty_actual'] == 0
    assert runtime.rich.get_price(line['price_id'])['actual_rate'] == 123
    phase = PhasePlanWindow187(app, rich=runtime.rich, phase_no=1,
                               on_saved=lambda: _refresh_plan_187(app))
    phase.name.set('فاز ویرایش‌شده')
    phase.save()
    assert runtime.rich.get_phase_item(rid)['qty_actual'] == 0
    assert runtime.rich.get_price(line['price_id'])['actual_rate'] == 123
    assert runtime.db.snapshot() == snapshot
    # Updated rates recompute the estimate; measured quantity removes the star.
    runtime.rich.save_price_rates(line['price_id'], 100, 123, 1000)
    app.refresh_reports()
    assert number(displayed_price(pane, line['price_id'])['qty_actual']) == 2.5
    runtime.rich.save_phase_item(rid, qty_actual=5)
    app.refresh_reports()
    shown = displayed_price(pane, line['price_id'])
    assert '*' not in shown['actual_rate'] and number(shown['qty_actual']) == 5
    assert number(shown['actual_rate']) == 123


@pytest.mark.parametrize('cost,category', CATEGORIES)
def test_contract_and_statement_work_define_actual_unit_price(app, runtime, cost, category):
    rid = add(app, cost, qty_actual=0, actual_rate=0)
    line = runtime.rich.get_phase_item(rid)
    approve_cost(runtime, line, 2000, 1)
    contract = upsert_contract(dict(title='قرارداد آزمایشی', total_amount='3600',
        rows=[dict(plan_ref=line['plan_ref'], description=line['description'],
                   unit_price='۳۰۰', quantity='۱۲', line_total='3600')]))
    cid = contract['contract_id']
    for no, qty, total, cumulative in [(1, 2.5, 875, 2.5), (2, 1.5, 525, 4)]:
        upsert_statement(dict(statement_id=f'S{no}', contract_id=cid,
            statement_date=f'1405/07/0{no}', rows=[dict(description=line['description'],
                worked_quantity=str(qty), unit_price='350', line_total=str(total),
                cumulative_quantity=str(cumulative), cumulative_amount=str(int(cumulative * 350)))]))
    # An unrelated statement with the same description cannot contribute.
    upsert_statement(dict(statement_id='OTHER', contract_id='UNRELATED',
        rows=[dict(description=line['description'], worked_quantity='900', line_total='999999')]))
    install_actual_cost_sync_187(app)
    _refresh_plan_187(app)
    pane = app.price_panels187[category]
    shown = displayed_price(pane, line['price_id'])
    assert number(shown['actual_rate']) == 350 and number(shown['qty_actual']) == 4
    assert '*' not in shown['actual_rate']
    plan = displayed_plan(app, rid)
    assert number(plan['rate_actual']) == 350 and number(plan['qty_actual']) == 4
    assert number(plan['total_actual']) == number(shown['total_actual'])
    snapshot = runtime.db.snapshot()
    # Refresh via the ordinary report callback, with no posted-total change.
    delete_statement('S2')
    app.refresh_reports()
    shown = displayed_price(pane, line['price_id'])
    assert number(shown['qty_actual']) == 2.5 and number(shown['actual_rate']) == 350
    upsert_statement(dict(statement_id='S1', contract_id=cid, rows=[dict(
        description=line['description'], worked_quantity='2.5', line_total='1000')]))
    app.refresh_reports()
    assert number(displayed_price(pane, line['price_id'])['actual_rate']) == 400
    delete_statement('S1')
    app.refresh_reports()
    shown = displayed_price(pane, line['price_id'])
    assert number(shown['actual_rate']) == 300 and number(shown['qty_actual']) == 12
    assert runtime.db.snapshot() == snapshot
    delete_contract(cid)
    app.refresh_reports()
    shown = displayed_price(pane, line['price_id'])
    assert '*' in shown['actual_rate'] and number(shown['total_actual']) == 2000


def test_zero_updated_price_cannot_infer_quantity(app, runtime):
    rid = add(app, 'خرید زمین', qty_actual=0, actual_rate=0)
    line = runtime.rich.get_phase_item(rid)
    runtime.rich.save_price_rates(line['price_id'], 100, 0, 0)
    runtime.rich.save_phase_item(rid, total_actual=4500)
    _refresh_plan_187(app)
    shown = displayed_price(app.price_panels187['LAND'], line['price_id'])
    assert number(shown['qty_actual']) == number(shown['actual_rate']) == 0
    assert number(shown['total_actual']) == 4500 and '*' not in shown['actual_rate']


def test_shared_price_weights_contract_and_inferred_rows(app, runtime):
    rid = add(app, 'اجرت', qty_actual=0, actual_rate=0)
    first = runtime.rich.get_phase_item(rid)
    runtime.rich.save_price_rates(first['price_id'], 100, 0, 500)
    second = runtime.rich.add_phase_item(2, 'دوم', dict(description='کار دوم',
        cost_type='اجرت', unit='عدد', price_id=first['price_id'], qty_actual=0))
    runtime.rich.save_phase_item(second, total_actual=1000)
    upsert_contract(dict(rows=[dict(plan_ref=first['plan_ref'], description=first['description'],
        unit_price='300', quantity='4')]))
    _refresh_plan_187(app)
    shown = displayed_price(app.price_panels187['LABOR'], first['price_id'])
    assert number(shown['qty_actual']) == 6
    assert number(shown['actual_rate']) == 367  # (4 * 300 + 2 * 500) / 6
    assert '*' in shown['actual_rate']
    assert number(displayed_plan(app, second)['rate_actual']) == 500


def test_legacy_cumulative_statements_do_not_double_count(runtime):
    rid = runtime.rich.add_phase_item(1, 'نمونه', dict(description='کار آزمایشی', cost_type='اجرت', unit='متر'))
    line = runtime.rich.get_phase_item(rid)
    contract = upsert_contract(dict(rows=[dict(plan_ref=line['plan_ref'], description=line['description'],
        unit_price='100', quantity='50')]))
    for no, qty in [(1, 10), (2, 15)]:
        upsert_statement(dict(statement_id=f'S{no}', contract_id=contract['contract_id'],
            statement_date=f'1405/07/0{no}', rows=[dict(description=line['description'],
                cumulative_quantity=str(qty), cumulative_amount=str(qty * 100))]))
    projected = project_actual_rows187(runtime.rich.all_phase_items())[0]
    assert _quantities(projected)[2] == 15 and _rates(projected)[2] == 100


def test_multiple_contracts_for_one_row_use_weighted_unit_price(runtime):
    rid = runtime.rich.add_phase_item(1, 'نمونه', dict(description='کار مشترک', cost_type='اجرت', unit='متر'))
    line = runtime.rich.get_phase_item(rid)
    for qty, price in [(2, 200), (3, 400)]:
        upsert_contract(dict(rows=[dict(plan_ref=line['plan_ref'], description=line['description'],
            unit_price=str(price), quantity=str(qty))]))
    projected = project_actual_rows187(runtime.rich.all_phase_items())[0]
    assert _quantities(projected)[2] == 5 and _rates(projected)[2] == 320


def test_ambiguous_statement_name_requires_its_explicit_plan_reference(runtime):
    ids = [runtime.rich.add_phase_item(no, 'نمونه', dict(description='کار مشترک',
        cost_type='اجرت', unit='متر')) for no in (1, 2)]
    lines = [runtime.rich.get_phase_item(rid) for rid in ids]
    contract = upsert_contract(dict(rows=[dict(plan_ref=line['plan_ref'], description='کار مشترک',
        unit_price='100', quantity='10') for line in lines]))
    upsert_statement(dict(contract_id=contract['contract_id'], rows=[
        dict(description='کار مشترک', worked_quantity='900', line_total='999999'),
        dict(plan_ref=lines[1]['plan_ref'], description='کار مشترک', worked_quantity='2', line_total='300')]))
    projected = project_actual_rows187(runtime.rich.all_phase_items())
    assert _quantities(projected[0])[2] == 10 and _rates(projected[0])[2] == 100
    assert _quantities(projected[1])[2] == 2 and _rates(projected[1])[2] == 150


def test_contract_line_total_can_supply_unit_price_and_statement_missing_amount(runtime):
    rid = runtime.rich.add_phase_item(1, 'نمونه', dict(description='کار آزمایشی', cost_type='اجرت', unit='متر'))
    line = runtime.rich.get_phase_item(rid)
    contract = upsert_contract(dict(rows=[dict(plan_ref=line['plan_ref'], description=line['description'],
        quantity='۲٫۵', line_total='۱,۰۰۰')]))
    projected = project_actual_rows187(runtime.rich.all_phase_items())[0]
    assert _rates(projected)[2] == 400 and _quantities(projected)[2] == 2.5
    upsert_statement(dict(contract_id=contract['contract_id'], rows=[dict(
        description=line['description'], worked_quantity='2')]))
    projected = project_actual_rows187(runtime.rich.all_phase_items())[0]
    assert _rates(projected)[2] == 400 and _quantities(projected)[2] == 2


def test_contract_without_volume_still_requires_inferred_quantity_and_star(runtime):
    rid = runtime.rich.add_phase_item(1, 'نمونه', dict(description='کار آزمایشی', cost_type='اجرت',
        unit='متر', qty_actual=0, forecast_rate=250))
    line = runtime.rich.get_phase_item(rid)
    runtime.rich.save_phase_item(rid, total_actual=1000)
    upsert_contract(dict(rows=[dict(plan_ref=line['plan_ref'], description=line['description'],
        quantity='0', unit_price='300')]))
    projected = project_actual_rows187(runtime.rich.all_phase_items())[0]
    assert _rates(projected)[2] == 250 and _quantities(projected)[2] == 4
    assert projected['_actual_projection187'] == 'ESTIMATED'


def test_explicit_zero_contract_rate_with_known_quantity_is_preserved(runtime):
    rid = runtime.rich.add_phase_item(1, 'نمونه', dict(description='کار آزمایشی', cost_type='اجرت',
        unit='متر', actual_rate=999))
    line = runtime.rich.get_phase_item(rid)
    upsert_contract(dict(rows=[dict(plan_ref=line['plan_ref'], description=line['description'],
        quantity='2', unit_price='0', line_total='0')]))
    projected = project_actual_rows187(runtime.rich.all_phase_items())[0]
    assert _rates(projected)[2] == 0 and _quantities(projected)[2] == 2
    assert projected['_actual_projection187'] == 'CONTRACT'


@pytest.mark.parametrize('form', ['wizard', 'record'])
@pytest.mark.parametrize('before,after', [(LAND_TITLE, 'هزینه ساخت'), ('هزینه ساخت', LAND_TITLE)])
def test_changing_between_land_and_construction_clears_the_old_plan_reference(root, runtime, form, before, after):
    payload = dict(v18_title=before, v18_subtype=LAND_TITLE if before == LAND_TITLE else 'نقدی',
        description='تست تغییر عنوان', amount=100, event_date_shamsi='1405/07/10',
        detected_type='EXPENSE', payment_state='PAID', plan_ref='OLD-REF',
        construction_stage=LAND_TITLE if before == LAND_TITLE else 'اسکلت')
    snapshot = runtime.db.snapshot()
    if form == 'wizard':
        editor = wizard_for(root, runtime, payload)
        editor._title_changed(after)
    else:
        pid = register(runtime, payload)
        editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
        editor.title_var.set(after)
        editor._title_changed()
    assert editor.payload.get('plan_ref') != 'OLD-REF'
    assert runtime.db.snapshot() == snapshot
