"""Window wiring for Undo/Redo: tab scopes, the user-action gate, and one step per action.

Uses a bare Tk window (no dashboard, no project data) and a throwaway database.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace

import pytest

import history_scope
import row_journal
from dashboard_service_stage9 import DashboardServiceStage9
from finance_db import FinanceDB


@pytest.fixture()
def root():
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip('no display available for Tk')
    window.withdraw()
    yield window
    row_journal.uninstall()
    try:
        window.destroy()
    except tk.TclError:
        pass


@pytest.fixture()
def db_and_service(tmp_path):
    db = FinanceDB(Path(tmp_path) / 'scope.sqlite3')
    return db, DashboardServiceStage9(db, Path(tmp_path))


def _new_transaction(db, amount=1000):
    return db.post_transaction(event_date='2026-09-01', direction='OUT', amount=amount,
                               category='مصالح', description='خرید')


def _status(db, tx):
    with db.read() as con:
        return con.execute('SELECT status FROM transactions WHERE transaction_id=?', (tx,)).fetchone()[0]


def _history(root, scope, clock):
    root.refreshed = []
    root.refresh_all = lambda: root.refreshed.append(row_journal._LOCAL.suspended)
    queued = []
    history = history_scope.WindowHistory(root, scope=lambda: scope['now'], clock=lambda: clock['t'],
                                          schedule=lambda callback: queued.append(callback))
    history.start()
    return history, queued


def test_each_nested_tab_gets_its_own_scope(root):
    top = ttk.Notebook(root)
    money = ttk.Frame(top)
    plan = ttk.Frame(top)
    top.add(money, text='تراکنش‌ها')
    top.add(plan, text='مدیریت پروژه')
    sub = ttk.Notebook(money)
    sub.pack()
    all_tab, loans_tab = ttk.Frame(sub), ttk.Frame(sub)
    sub.add(all_tab, text='همه')
    sub.add(loans_tab, text='وام')
    top.pack()
    root.notebook = top
    root.update_idletasks()

    top.select(money)
    sub.select(all_tab)
    root.update_idletasks()
    first = history_scope.active_scope(root)
    sub.select(loans_tab)
    root.update_idletasks()
    second = history_scope.active_scope(root)
    top.select(plan)
    root.update_idletasks()
    third = history_scope.active_scope(root)

    assert first and second and third
    assert len({first, second, third}) == 3
    assert str(loans_tab) in second and str(plan) in third


def test_the_start_page_and_data_entry_have_their_own_scopes(root):
    root.notebook = ttk.Notebook(root)
    root._window_view187 = 'start'
    assert history_scope.active_scope(root) == ''

    root._window_view187 = 'project'
    root.approval_center = SimpleNamespace(winfo_ismapped=lambda: False)
    assert history_scope.active_scope(root) != history_scope.DATA_ENTRY_SCOPE
    root.approval_center = SimpleNamespace(winfo_ismapped=lambda: True)
    assert history_scope.active_scope(root) == history_scope.DATA_ENTRY_SCOPE


def test_one_action_over_two_writes_is_one_undo_step_in_its_own_tab(root, db_and_service):
    db, service = db_and_service
    first, second = _new_transaction(db, 100), _new_transaction(db, 200)
    scope, clock = {'now': 'tab:all'}, {'t': 100.0}
    history, queued = _history(root, scope, clock)

    history._mark_input()
    service.delete_manual_transaction(first)
    service.delete_manual_transaction(second)
    assert len(queued) == 1  # both writes wait for the same event-loop turn
    history.flush()

    scope['now'] = 'tab:loans'
    assert history.undo() == 'عملیاتی برای بازگردانی در این تب وجود ندارد.'
    assert _status(db, first) == _status(db, second) == 'VOIDED'

    scope['now'] = 'tab:all'
    assert history.undo() == '«حذف ۲ تراکنش» بازگردانی شد.'
    assert _status(db, first) == _status(db, second) == 'POSTED'
    assert root.refreshed == [True]  # refreshed once, outside the history
    assert history.redo() == '«حذف ۲ تراکنش» دوباره اجرا شد.'
    assert _status(db, first) == 'VOIDED'


def test_a_write_without_a_recent_click_or_key_is_not_a_user_action(root, db_and_service):
    db, service = db_and_service
    tx = _new_transaction(db)
    scope, clock = {'now': 'tab:all'}, {'t': 100.0}
    history, queued = _history(root, scope, clock)

    history._mark_input()
    clock['t'] += history_scope.USER_ACTION_WINDOW + 1
    service.delete_manual_transaction(tx)  # e.g. a timer-driven refresh

    assert queued == []
    assert history.undo() == 'عملیاتی برای بازگردانی در این تب وجود ندارد.'
    assert _status(db, tx) == 'VOIDED'


def test_data_entry_keeps_its_own_history_and_the_journal_ignores_its_writes(root, db_and_service):
    db, service = db_and_service
    tx = _new_transaction(db)
    scope, clock = {'now': history_scope.DATA_ENTRY_SCOPE}, {'t': 100.0}
    history, queued = _history(root, scope, clock)
    root.approval_center = SimpleNamespace(
        can_undo=lambda: True, can_redo=lambda: False,
        undo_data_entry=lambda: 'حذف سطرها بازگردانی شد.', redo_data_entry=lambda: 'x')

    history._mark_input()
    service.delete_manual_transaction(tx)
    history.flush()

    assert history.undo() == 'حذف سطرها بازگردانی شد.'
    assert root.refreshed == []  # the data-entry tab refreshes itself
    assert history.redo() == history_scope.DATA_ENTRY_NOTHING_TO_REDO
    assert _status(db, tx) == 'VOIDED'


def test_destroying_the_window_stops_recording(root, db_and_service):
    db, service = db_and_service
    tx = _new_transaction(db)
    scope, clock = {'now': 'tab:all'}, {'t': 100.0}
    original = type(db).tx
    _history(root, scope, clock)
    assert type(db).tx is not original

    root.destroy()

    assert type(db).tx is original
    service.delete_manual_transaction(tx)
    assert _status(db, tx) == 'VOIDED'


def test_contractor_file_saves_become_one_undo_step_in_their_tab(root, tmp_path, monkeypatch):
    import contractor_store_stage18_7 as store

    monkeypatch.setenv('STAGE4_DB_PATH', str(Path(tmp_path) / 'project.sqlite3'))
    scope, clock = {'now': 'tab:contractors'}, {'t': 100.0}
    history, queued = _history(root, scope, clock)
    try:
        store.upsert_contract({'contract_id': 'C1', 'title': 'اولی'})  # not a user action yet
        history._mark_input()
        store.upsert_contract({'contract_id': 'C2', 'title': 'دومی'})
        store.upsert_contract({'contract_id': 'C3', 'title': 'سومی'})
        assert len(queued) == 1
        history.flush()

        scope['now'] = 'tab:sales'
        assert history.undo() == 'عملیاتی برای بازگردانی در این تب وجود ندارد.'
        scope['now'] = 'tab:contractors'
        assert history.undo() == '«افزودن قرارداد پیمانکار» بازگردانی شد.'
        assert [c['contract_id'] for c in store.load_contracts()] == ['C1']
        assert root.refreshed == [True]
        assert history.redo().endswith('دوباره اجرا شد.')
        assert [c['contract_id'] for c in store.load_contracts()] == ['C1', 'C2', 'C3']
    finally:
        history_scope.file_journal.uninstall()
