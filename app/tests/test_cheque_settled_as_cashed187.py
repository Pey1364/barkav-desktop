"""«عودتی به شرط تسویه» counts with the cashed cheques: nothing is owed through it any more (user's rule 2026-10-06)."""
import importlib
import json
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import pytest
from finance_db import FinanceDB
import cheque_status187 as rule
from test_advanced_search187 import search  # noqa: F401
from test_cheque_resolution_lifecycle187 import _resolve
from test_cheque_workflow187 import cheque_payload
from test_transaction_lifecycle_matrix import m, runtime, register  # noqa: F401

STATUSES = ('ISSUED', 'PENDING_DUE', 'CASHED', 'RETURNED', 'CANCELLED')
MODES = (None, 'NORMAL', 'RETURNED_ON_SETTLEMENT', 'REPLACED_BY_TRANSFER', 'VOIDED', 'RETURNED_SETTLED',
         'CHECKBOOK', 'TRANSFER_REPLACEMENT')
DETAILS = dict(return_disposition='عدم دریافت و عدم عودت سیستمی', return_account_holder='صاحب حساب معرفی‌شده',
               void_reason='دلیل ابطال')
gui_only = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI opt-in')


def _cheque(db, amount, days=5):
    return db.create_cheque(amount=amount, issue_date=date.today().isoformat(),
                            due_date=(date.today() + timedelta(days=days)).isoformat())


def _put(db, cheque_id, lifecycle):
    db.update_cheque_workflow_state(cheque_id, lifecycle=lifecycle, **DETAILS)


# ---- the rule itself ----------------------------------------------------------------------------------

@pytest.mark.parametrize('status,mode,owed,cashed', [
    ('ISSUED', None, True, False),
    ('PENDING_DUE', 'NORMAL', True, False),
    ('RETURNED', 'NORMAL', True, False),                    # «برگشتی»: the debt is still there
    ('RETURNED', None, True, False),
    ('RETURNED', 'RETURNED_ON_SETTLEMENT', False, True),    # «عودتی به شرط تسویه»: settled, counts as cashed
    ('RETURNED', 'REPLACED_BY_TRANSFER', False, False),     # paid by a transfer whose own row is the cashed one
    ('CASHED', 'NORMAL', False, True),
    ('CASHED', 'RETURNED_SETTLED', False, True),
    ('CASHED', 'TRANSFER_REPLACEMENT', False, True),
    ('CANCELLED', 'VOIDED', False, False),
    ('CANCELLED', 'NORMAL', False, False),
])
def test_what_is_owed_and_what_counts_as_cashed(status, mode, owed, cashed):
    row = {'status': status, 'settlement_mode': mode}
    assert rule.is_open(row) is owed
    assert rule.counts_as_cashed(row) is cashed


def test_the_sql_and_the_python_definitions_of_open_cannot_drift():
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE cheques (cheque_id INTEGER, status TEXT, settlement_mode TEXT)')
    rows = [(number, status, mode) for number, (status, mode)
            in enumerate((s, md) for s in STATUSES for md in MODES)]
    con.executemany('INSERT INTO cheques VALUES (?,?,?)', rows)
    plain = {row[0] for row in con.execute(f'SELECT cheque_id FROM cheques WHERE {rule.open_sql()}')}
    aliased = {row[0] for row in con.execute(f'SELECT c.cheque_id FROM cheques c WHERE {rule.open_sql("c")}')}
    expected = {number for number, status, mode in rows if rule.is_open({'status': status, 'settlement_mode': mode})}
    assert plain == aliased == expected and expected


# ---- the database and the dashboard figures --------------------------------------------------------------

@pytest.mark.parametrize('lifecycle,owed', [('ISSUED', True), ('CASHED', False), ('RETURNED', True),
                                            ('RETURNED_ON_SETTLEMENT', False), ('VOIDED', False)])
def test_open_commitments_and_the_free_cash_follow_the_rule(tmp_path, lifecycle, owed):
    db = FinanceDB(tmp_path / 'project.sqlite3')
    cheque_id = _cheque(db, 1000)
    _put(db, cheque_id, lifecycle)
    snapshot = db.snapshot()
    assert db.open_cheque_commitments() == snapshot.open_cheque_commitments == (1000 if owed else 0)
    assert snapshot.free_cash_after_cheques == snapshot.cash_balance - snapshot.open_cheque_commitments
    assert [row['cheque_id'] for row in db.list_cheques(open_only=True)] == ([cheque_id] if owed else [])


def test_a_cheque_replaced_by_a_transfer_is_not_owed_a_second_time(tmp_path):
    db = FinanceDB(tmp_path / 'project.sqlite3')
    cheque_id = _cheque(db, 1000)
    assert db.open_cheque_commitments() == 1000
    db.replace_cheque_by_transfer(cheque_id, settled_date='2026-10-05', settled_date_shamsi='1405/07/13',
                                  account_holder='گیرنده', description='بابت آزمون')
    assert db.open_cheque_commitments() == 0
    assert db.list_cheques(open_only=True) == []


@pytest.mark.parametrize('module', ['dashboard_service_stage12', 'dashboard_read_model'])
def test_the_thirty_day_figures_leave_out_a_cheque_returned_on_settlement(tmp_path, module):
    db = FinanceDB(tmp_path / 'project.sqlite3')
    owed, settled, returned = _cheque(db, 1000), _cheque(db, 2000), _cheque(db, 4000)
    _put(db, settled, 'RETURNED_ON_SETTLEMENT')
    _put(db, returned, 'RETURNED')
    service = importlib.import_module(module).DashboardServiceStage12(db, tmp_path)

    summary = service.cheque_30d_summary(30)
    assert sorted(row['cheque_id'] for row in summary['rows']) == sorted([owed, returned])
    assert (summary['count'], summary['amount']) == (2, 5000)
    assert service.overview().open_cheque_commitments == 5000
    # the volume of all the cheques of the project still counts the settled one
    assert service.cheque_total_summary() == {'count': 3, 'amount': 7000}
    assert sorted(row['cheque_id'] for row in service.list_cheques(open_only=True)) == sorted([owed, returned])


def test_the_base_service_lists_the_same_open_cheques(tmp_path):
    from dashboard_service import DashboardService
    db = FinanceDB(tmp_path / 'project.sqlite3')
    owed, settled = _cheque(db, 1000), _cheque(db, 2000)
    _put(db, settled, 'RETURNED_ON_SETTLEMENT')
    assert [row['cheque_id'] for row in DashboardService(db).list_cheques(open_only=True)] == [owed]


# ---- the search ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize('lifecycle,open_amount,received', [('ISSUED', 300, 200), ('RETURNED', 300, 200),
                                                            ('RETURNED_ON_SETTLEMENT', 0, 500), ('CASHED', 0, 500)])
def test_the_contract_statement_reads_a_settled_cheque_as_paid(search, lifecycle, open_amount, received):  # noqa: F811
    directory = Path(search.db.db_path).parent
    cheque_id = _cheque(search.db, 300, days=14)
    _put(search.db, cheque_id, lifecycle)
    (directory / 'contractor_contracts_18_7.json').write_text(json.dumps({'contracts': [
        {'contract_id': 'C1', 'family_name': 'نیکزاد', 'total_amount': 2000,
         'payments': [{'amount': 200}, {'amount': 300, 'cheque_id': cheque_id}]}]}), encoding='utf-8')
    (directory / 'contractor_statements_18_7.json').write_text(json.dumps({'statements': [
        {'statement_id': 'S1', 'contract_id': 'C1', 'statement_date': '1405/07/01', 'rows': [{'line_total': 1000}]}]}),
        encoding='utf-8')
    source = next(r for r in search.records() if r['_table'] == 'contract_statement_balance')
    assert source['جزئیات']['چک باز'] == open_amount
    assert source['جزئیات']['دریافتی'] == received


@pytest.mark.parametrize('lifecycle,committed', [('ISSUED', 1000), ('RETURNED', 1000), ('RETURNED_ON_SETTLEMENT', 0)])
def test_the_expense_balance_commits_only_what_is_still_owed(search, lifecycle, committed):  # noqa: F811
    expense = search.db.create_expense(event_date='2026-09-23', shamsi_date='1405/07/01', final_amount=1000,
                                       description='سیمان', construction_stage='اسکلت')
    cheque_id = search.db.create_cheque(amount=1000, issue_date='2026-09-23', due_date='2026-10-23',
                                        expense_id=expense)
    _put(search.db, cheque_id, lifecycle)
    row = next(r for r in search.records(include_analytics=True) if r['_table'] == 'expense_balance')
    assert row['جزئیات']['چک باز'] == committed


# ---- the cheque tab and the dashboard cards (opt-in GUI) -----------------------------------------------------------

@pytest.fixture
def dashboard(runtime, monkeypatch):
    from barkav_ui import art
    art.clear_cache()
    monkeypatch.setattr(m.v186.v185, 'fetch_tgju_usd_toman', lambda timeout=6: (70000, '2026-10-05'))
    monkeypatch.setattr(m.DataEntryCenter187, '_start_gemini_probe_187', lambda self: None)
    monkeypatch.setattr(m.DataEntryCenter187, '_start_telegram_probe_187', lambda self: None)
    monkeypatch.setattr(m.Stage187Dashboard, '_show_startup_reminders_187', lambda self: None)
    app = m.Stage187Dashboard()
    app.update()
    yield app
    app.destroy()


def _recorded_cheque(runtime, number, status=None):
    known = {row['cheque_id'] for row in runtime.db.list_cheques(open_only=False)}
    payload = dict(cheque_payload(), cheque_serial=str(900000 + number))
    pending = register(runtime, payload, number)
    m.v18.submit_v18(pending, payload, runtime.rich)
    cheque_id = next(row['cheque_id'] for row in runtime.db.list_cheques(open_only=False) if row['cheque_id'] not in known)
    if status:
        _resolve(runtime, cheque_id, status, 100 + number)
    return cheque_id


@gui_only
def test_the_cheque_tab_files_a_settled_cheque_with_the_cashed_ones(dashboard, runtime):
    issued = _recorded_cheque(runtime, 1)
    cashed = _recorded_cheque(runtime, 2, 'پاس‌شده')
    returned = _recorded_cheque(runtime, 3, 'برگشتی')
    settled = _recorded_cheque(runtime, 4, 'عودتی به شرط تسویه')
    assert runtime.db.get_cheque(settled)['settlement_mode'] == 'RETURNED_ON_SETTLEMENT'

    def listed(label):
        dashboard.ch_filter.set(label)
        dashboard.update()
        return {row['cheque_id'] for row in dashboard.cheque_table.all_rows}

    assert listed('همه') == {issued, cashed, returned, settled}
    assert listed('پاس‌شده') == {cashed, settled}
    assert listed('عودتی به شرط تسویه') == {settled}
    assert listed('برگشتی') == {returned}
    assert listed('صادرشده') == {issued}
    # the column still says what the settled cheque is
    dashboard.ch_filter.set('همه')
    dashboard.update()
    table = dashboard.cheque_table
    row = next(row for row in table.all_rows if row['cheque_id'] == settled)
    shown = dict(zip(table.tree['columns'], table.row_values(row)))['status']
    assert shown.lstrip('‏') == 'عودتی به شرط تسویه'  # cells carry a right-to-left mark in front


@gui_only
def test_the_dashboard_cards_leave_the_settled_cheque_out_of_the_unpaid_total(dashboard, runtime):
    _recorded_cheque(runtime, 1)
    _recorded_cheque(runtime, 2, 'پاس‌شده')
    _recorded_cheque(runtime, 3, 'برگشتی')
    _recorded_cheque(runtime, 4, 'عودتی به شرط تسویه')
    dashboard.refresh_overview()
    dashboard.update()
    each = int(cheque_payload()['cheque_amount'])
    assert dashboard.cards['ch_open_total'].var.get() == m.fa(f'{2 * each:,}')      # issued + plainly returned
    assert dashboard.cards['ch_all_total'].var.get() == m.fa(f'{4 * each:,}')       # the volume keeps all four
