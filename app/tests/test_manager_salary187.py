"""Manager payouts change cash/receipts, never construction phase costs."""
import pytest
from test_transaction_lifecycle_matrix import runtime, register, m
from test_stage18_7_record_fields import root, record
from test_land_wizard_settlement187 import wizard_for
from transaction_lifecycle import TransactionLifecycle
from transaction_titles187 import MANAGER_TITLE, TRANSACTION_TITLES, transaction_title
from construction_cost_rules187 import is_land_phase
from financial_posting import build_posting_plan


def test_manager_form_has_no_phase_category_or_contract():
    assert MANAGER_TITLE in TRANSACTION_TITLES
    assert 'سایر' not in TRANSACTION_TITLES
    assert m.v18._backend_type(MANAGER_TITLE, 'نقدی') == 'OUTFLOW'
    assert m.v18._title_type_from_payload({'v18_title': MANAGER_TITLE, 'v18_subtype': 'نقدی'}) == (MANAGER_TITLE, 'نقدی')
    for fields in (m._special_fields_187(MANAGER_TITLE, 'نقدی'),
                   [f for page in m._wizard_steps_187(MANAGER_TITLE, 'نقدی') for f in page]):
        keys = {f.key for f in fields}
        assert not keys & {'main_phase', 'sub_phase', 'construction_stage', 'activity_name', 'plan_ref', 'cost_group', 'contract_id'}
        assert {'payer_name', 'receiver_name', 'description', 'payment_method', 'payment_state'} <= keys


@pytest.mark.parametrize('form_kind', ['wizard', 'record'])
def test_manager_fields_render_without_phase_or_category(root, runtime, form_kind):
    payload = record(runtime)['payload']
    payload.update(v18_title=MANAGER_TITLE, transaction_title=MANAGER_TITLE,
                   v18_subtype='نقدی', transaction_subtype='نقدی', detected_type='OUTFLOW',
                   amount=250, construction_stage='08 — اسکلت', main_phase='08',
                   sub_phase='08-1', cost_group='مصالح', plan_ref='08-1', contract_id='fake')
    pid = register(runtime, payload, 2)
    row = runtime.db.get_pending_item(pid)
    if form_kind == 'wizard':
        form = wizard_for(root, runtime, row['payload'])
        visible_pages = range(len(form.pages) - 1)
    else:
        form = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
        visible_pages = (0,)

    forbidden = {'construction_stage', 'main_phase', 'sub_phase', 'activity_name', 'plan_ref'}
    for page in visible_pages:
        if form_kind == 'wizard':
            if page:
                form._capture()
            form.page_index = page
            form._show_page()
        root.update()
        assert not forbidden.intersection(form.vars)
        assert not forbidden.intersection(form.widgets)
        for key in ('cost_group', 'contract_id'):
            widget = form.widgets.get(key)
            assert widget is None or not widget.winfo_viewable()
        if form_kind == 'wizard':
            assert not forbidden.intersection(fd.key for fd in form.pages[page])
    if form_kind == 'wizard':
        form._capture()
        payload_from_form = form._payload_from_vars(MANAGER_TITLE, 'نقدی')
    else:
        payload_from_form = form.payload_from_form()
    assert not (forbidden | {'cost_group', 'contract_id'}).intersection(payload_from_form)
    assert MANAGER_TITLE in TRANSACTION_TITLES
    assert 'سایر' not in TRANSACTION_TITLES
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'
    form.destroy()


@pytest.mark.parametrize('stage,ref,category', [
    ('خرید زمین', '', ''), ('۰۱ — خرید زمین', '', ''),
    ('هزینه دفترخانه', '01-2', ''), ('هزینه بنگاه', '', 'LAND_PURCHASE'),
    ('01 — هزینه زمین', '', ''),
])
def test_all_phase_one_costs_are_excluded(runtime, stage, ref, category):
    runtime.db.create_expense(event_date='2026-01-01', final_amount=1000, construction_stage='اسکلت', description='ساخت')
    runtime.db.create_expense(event_date='2026-01-02', final_amount=500, description='زمین',
                              construction_stage=stage, plan_ref=ref, category=category or 'CONSTRUCTION')
    assert runtime.db.construction_cost() == 1000
    assert runtime.db.snapshot().construction_cost == 1100
    assert runtime.db.land_purchase_cost() == 500
    assert runtime.db.project_cost() == 1600
    assert runtime.db.project_cost('2026-01-01') == 1100
    assert not is_land_phase('11 — نما', '11-1')


def test_salary_approval_revision_rejection_restore(runtime):
    runtime.db.create_expense(event_date='2026-01-01', final_amount=1000, construction_stage='اسکلت', description='ساخت')
    payload = {'v18_title': MANAGER_TITLE, 'v18_subtype': 'نقدی', 'detected_type': 'EXPENSE',
               'amount': 60, 'event_date_shamsi': '1405/07/08', 'description': 'پرداخت آزمون',
               'payment_method': 'BANK_TRANSFER', 'payment_state': 'PAID',
               'construction_stage': 'اسکلت', 'main_phase': '08', 'sub_phase': '08-1',
               'plan_ref': '08-1', 'cost_group': 'مصالح'}
    pid = register(runtime, payload)
    assert runtime.db.manager_withdrawals() == 0
    m.v18.submit_v18(pid, payload, runtime.rich)
    m.v18.submit_v18(pid, payload, runtime.rich)
    assert runtime.db.manager_withdrawals() == 60
    assert runtime.db.manager_account_balance() == 40
    assert runtime.db.cash_balance() == -60
    assert runtime.db.snapshot().construction_cost == 1100
    with runtime.db.read() as con:
        assert con.execute("SELECT COUNT(*) FROM expenses WHERE deleted_at IS NULL").fetchone()[0] == 1
        row = dict(con.execute("SELECT * FROM transactions WHERE status='POSTED' AND deleted_at IS NULL").fetchone())
    assert transaction_title(row) == MANAGER_TITLE
    m.v18.submit_v18(pid, {**payload, 'amount': 150}, runtime.rich)
    assert runtime.db.manager_withdrawals() == 150
    assert runtime.db.manager_account_balance() == -50
    assert runtime.db.snapshot().construction_cost == 1100
    lifecycle = TransactionLifecycle(runtime.db)
    lifecycle.reject(pid)
    assert runtime.db.manager_withdrawals() == 0
    assert runtime.db.manager_account_balance() == 100
    assert runtime.db.cash_balance() == 0
    lifecycle.restore(pid)
    assert runtime.db.manager_withdrawals() == 150
    assert runtime.db.manager_account_balance() == -50


def test_explicit_salary_title_does_not_require_description_keywords():
    plan = build_posting_plan(payload={'v18_title': MANAGER_TITLE, 'detected_type': 'EXPENSE',
                                      'amount': 100, 'event_date_shamsi': '1405/07/08'},
                              raw_text='پرداخت', telegram_message_date='2026-09-30')
    assert plan['transaction_category'] == 'CONTRACTOR_FEE'
    assert plan['posting_type'] == 'OUTFLOW'


def test_construction_and_finished_per_area_exclude_land_from_fee(runtime, monkeypatch):
    budget = runtime.service.budget
    budget.save_settings(gross_area=200, saleable_area=100, remaining_months=0, unbudgeted_misc=0)
    # Report rows represent phase totals, with the existing raw prices unchanged.
    rows = [{'phase': '۰۱ — خرید زمین', 'forecast': 5000},
            {'phase': '08 — اسکلت', 'forecast': 10000}]
    monkeypatch.setattr(budget, 'report_rows', lambda: rows)
    runtime.db.set_setting('manager_fee_bps', '2000')
    forecast = budget.forecast()
    assert forecast.forecast_land_cost == 5000
    assert forecast.forecast_manager_fee == 1000
    assert forecast.forecast_construction_cost == 11000
    assert forecast.forecast_total_cost == 16000
    assert forecast.construction_cost_per_gross_m2 == 55
    assert forecast.total_cost_per_saleable_m2 == 160
    assert rows[1]['forecast'] == 10000


@pytest.mark.parametrize('actual, difference', [(0, 300), (300, 0), (500, -200)])
def test_petty_cash_difference_uses_costs_once_and_user_signs(runtime, actual, difference):
    db = runtime.db
    db.post_transaction(event_date='2026-01-01', direction='IN', amount=2000, category='CAPITAL')
    db.post_transaction(event_date='2026-01-01', direction='OUT', amount=100, category='NON_CONSTRUCTION_OUTFLOW')
    db.create_expense(event_date='2026-01-01', final_amount=1000, description='ساخت', construction_stage='اسکلت')
    db.create_expense(event_date='2026-01-01', final_amount=500, description='زمین', construction_stage='خرید زمین')
    for category, amount in [('CONSTRUCTION_PAYMENT', 1000), ('LAND_PURCHASE_PAYMENT', 500), ('CONTRACTOR_FEE', 60)]:
        db.post_transaction(event_date='2026-01-01', direction='OUT', amount=amount, category=category)
    result = db.petty_cash_reconciliation(actual)
    assert result['total_out'] == 100
    assert result['expected_cash'] == 300
    assert result['account_difference'] == difference
    summary = m.manager_account_summary_187(construction_cost=1500, land_purchase_cost=500,
        manager_receipts=60, transaction_cash=db.cash_balance(), actual_cash=actual,
        manager_percent=10, expected_petty_cash=result['expected_cash'])
    assert summary['account_difference'] == difference
    assert summary['with_difference'] == 40 - difference
    assert db.petty_cash_reconciliation(actual, '2025-12-31')['expected_cash'] == 0


def test_manager_tab_formula_text_matches_requested_terms_and_rtl_amounts():
    formula = m._manager_formula_text_187(
        {'eligible_costs': 1_000_000, 'manager_fee': 100_000}, 10,
        {'total_in': 2_000_000, 'total_out': 100_000, 'construction_cost': 1_100_000,
         'land_purchase_cost': 500_000, 'actual_cash': 200_000, 'account_difference': 100_000},
    )
    assert 'اختلاف حساب = کل ورودی − خروجی غیرساخت − هزینه ساخت − هزینه فاز خرید زمین − موجودی تنخواه' in formula
    assert '۲,۰۰۰,۰۰۰ − ۱۰۰,۰۰۰ − ۱,۱۰۰,۰۰۰ − ۵۰۰,۰۰۰ − ۲۰۰,۰۰۰ = ۱۰۰,۰۰۰' in formula
    assert 'حقوق مدیر: ۱۰٪ × ۱,۰۰۰,۰۰۰ = ۱۰۰,۰۰۰' in formula
