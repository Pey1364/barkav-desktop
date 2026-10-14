"""Approved service costs, rejection/restore, and non-useful-area pricing."""
import pytest
from test_transaction_lifecycle_matrix import runtime
from test_price_plan_sync187 import approve_cost
from engineering_phase187 import ensure_groups, SUPERVISION_COST, SUPERVISION_TAX, group_of
from cost_allocation_stage18_7 import apply_actuals, suggest_plan_row
from project_plan_stage18_7 import project_actual_rows187, _rates, _quantities, _totals
from transaction_lifecycle import TransactionLifecycle


def line(runtime, title, rate=100):
    rid = runtime.rich.add_phase_item(4, 'نظام مهندسی', dict(description=title,
        cost_type='خدمات', unit='مقطوع', qty_estimate=1, qty_forecast=1,
        estimate_rate=rate, forecast_rate=rate))
    return runtime.rich.get_phase_item(rid)


@pytest.mark.parametrize('name', ['نظارت آتش‌نشانی', 'ناظر گاز', 'ناظر آبفا',
    'ناظر نقشه‌برداری', 'آزمایش میلگرد', 'آزمایش بتن'])
def test_paired_payment_reject_restore_and_price_by_area(runtime, name):
    principal = line(runtime, 'اصل ' + name)
    tax = line(runtime, 'مالیات 10٪ ' + name, 10)
    ensure_groups(runtime.rich)
    runtime.service.budget.save_settings(gross_area=200)
    chosen = suggest_plan_row(runtime.rich, text='پرداخت خدمات', cost_group='خدمات',
        phase_no=4, sub_phase=group_of(principal))
    assert chosen.plan_ref == principal['plan_ref']
    assert suggest_plan_row(runtime.rich, text='مالیات ' + name, cost_group='خدمات',
        phase_no=4, sub_phase=group_of(principal)).plan_ref == tax['plan_ref']
    assert group_of(principal) in [r['description'] for r in runtime.rich.subphase_candidates(4)]
    pid = approve_cost(runtime, principal, 1001, 901)
    apply_actuals(runtime.db)
    snapshot = runtime.db.snapshot()
    projected = {r['phase_item_id']: r for r in project_actual_rows187(runtime.rich.all_phase_items())}
    p, t = projected[principal['phase_item_id']], projected[tax['phase_item_id']]
    assert _totals(p)[2] == 901 and _totals(t)[2] == 100
    assert _rates(p)[2] == round(901 / 200)
    assert _quantities(p)[2] == 200
    assert runtime.rich.get_phase_item(principal['phase_item_id'])['qty_actual'] == 0
    assert apply_actuals(runtime.db) == 0
    assert runtime.db.snapshot() == snapshot
    TransactionLifecycle(runtime.db).reject(pid)
    apply_actuals(runtime.db)
    assert sum(r['total_actual'] for r in runtime.rich.list_phase_items(4)) == 0
    TransactionLifecycle(runtime.db).restore(pid)
    apply_actuals(runtime.db)
    assert sum(r['total_actual'] for r in runtime.rich.list_phase_items(4)) == 1001


def test_supervision_actuals_use_only_aggregate_rows(runtime):
    p = line(runtime, 'نظارت معماری')
    t = line(runtime, 'مالیات 10٪ نظارت معماری', 10)
    ensure_groups(runtime.rich)
    rows = runtime.rich.list_phase_items(4)
    refs = {r['description']: r['plan_ref'] for r in rows}
    ids = {r['description']: r['phase_item_id'] for r in rows}
    assert suggest_plan_row(runtime.rich, text='نظارت', cost_group='خدمات',
        phase_no=4, sub_phase='نظارت').plan_ref == refs[SUPERVISION_COST]
    pid = approve_cost(runtime, p, 2000, 902)
    tax_pid = approve_cost(runtime, t, 40, 903)
    apply_actuals(runtime.db)
    assert runtime.rich.get_phase_item(ids[SUPERVISION_COST])['total_actual'] == 1800
    assert runtime.rich.get_phase_item(ids[SUPERVISION_TAX])['total_actual'] == 240
    assert runtime.rich.get_phase_item(p['phase_item_id'])['total_actual'] == 0
    assert runtime.rich.get_phase_item(t['phase_item_id'])['total_actual'] == 0
    assert sum(r['total_actual'] for r in runtime.rich.list_phase_items(4)) == 2040
    ensure_groups(runtime.rich)
    assert len(runtime.rich.list_phase_items(4)) == len(rows)
    TransactionLifecycle(runtime.db).reject(pid)
    TransactionLifecycle(runtime.db).reject(tax_pid)
    apply_actuals(runtime.db)
    assert sum(r['total_actual'] for r in runtime.rich.list_phase_items(4)) == 0


def test_missing_area_does_not_invent_a_unit_price(runtime):
    principal = line(runtime, 'اصل ناظر آبفا')
    line(runtime, 'مالیات 10٪ ناظر آبفا', 10)
    ensure_groups(runtime.rich)
    approve_cost(runtime, principal, 1000, 904)
    apply_actuals(runtime.db)
    row = next(r for r in project_actual_rows187(runtime.rich.all_phase_items()) if r['phase_item_id'] == principal['phase_item_id'])
    assert _totals(row)[2] == 900
    assert _rates(row)[2] == _quantities(row)[2] == 0
