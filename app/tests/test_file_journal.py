"""Contractor JSON stores: saves are recorded and can be undone and redone.

Points the store at a throwaway folder; never touches a real project's files.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

import contractor_store_stage18_7 as store
import file_journal
import row_journal
from action_history import TabHistory, UndoRefused


@pytest.fixture()
def seen(tmp_path, monkeypatch):
    monkeypatch.setenv('STAGE4_DB_PATH', str(Path(tmp_path) / 'project.sqlite3'))
    changes = []
    file_journal.install(changes.append)
    yield changes
    file_journal.uninstall()


def _contract(seen_id='C1', title='قرارداد اسکلت'):
    return {'contract_id': seen_id, 'title': title}


def _titles():
    return [c['title'] for c in store.load_contracts()]


def test_adding_a_contract_is_undone_to_the_previous_file(seen):
    store.upsert_contract(_contract('C1'))
    seen.clear()

    store.upsert_contract(_contract('C2', 'قرارداد نما'))
    (change,) = file_journal.merge(seen)
    action = file_journal.build_action(change)
    assert action.label == 'افزودن قرارداد پیمانکار' and action.undoable
    assert _titles() == ['قرارداد اسکلت', 'قرارداد نما']

    action.undo()
    assert _titles() == ['قرارداد اسکلت']
    action.redo()
    assert _titles() == ['قرارداد اسکلت', 'قرارداد نما']


def test_deleting_and_editing_are_named_and_reversed(seen):
    store.upsert_contract(_contract('C1'))
    store.upsert_contract(_contract('C2', 'قرارداد نما'))
    seen.clear()

    store.upsert_contract({'contract_id': 'C1', 'title': 'اصلاح‌شده'})
    edit = file_journal.build_action(file_journal.merge(seen)[0])
    assert edit.label == 'ویرایش قرارداد پیمانکار'
    seen.clear()
    store.delete_contract('C2')
    delete = file_journal.build_action(file_journal.merge(seen)[0])
    assert delete.label == 'حذف قرارداد پیمانکار'

    delete.undo()
    assert sorted(_titles()) == sorted(['اصلاح‌شده', 'قرارداد نما'])
    edit.undo()
    assert sorted(_titles()) == sorted(['قرارداد اسکلت', 'قرارداد نما'])


def test_several_saves_of_one_file_in_one_action_are_one_step(seen):
    store.upsert_contract(_contract('C1'))
    seen.clear()

    store.upsert_contract(_contract('C2', 'الف'))
    store.upsert_contract(_contract('C3', 'ب'))
    changes = file_journal.merge(seen)

    assert len(changes) == 1
    action = file_journal.build_action(changes[0])
    action.undo()
    assert _titles() == ['قرارداد اسکلت']


def test_undo_is_refused_when_the_file_changed_since(seen):
    store.upsert_contract(_contract('C1'))
    seen.clear()
    store.upsert_contract(_contract('C2', 'قرارداد نما'))
    action = file_journal.build_action(file_journal.merge(seen)[0])

    store.upsert_contract(_contract('C9', 'کار دیگری'))  # a later save, not recorded here

    with pytest.raises(UndoRefused):
        action.undo()
    assert 'C9' in [c['contract_id'] for c in store.load_contracts()]
    history = TabHistory()
    history.push(action)
    assert 'دوباره تغییر کرده' in history.undo()


def test_the_first_ever_save_is_not_undoable(seen):
    store.upsert_contract(_contract('C1'))
    action = file_journal.build_action(file_journal.merge(seen)[0])
    assert not action.undoable and 'اولین بار' in action.reason


def test_a_save_that_changes_nothing_records_nothing(seen):
    store.upsert_contract(_contract('C1'))
    seen.clear()
    store.upsert_contract(_contract('C1'))
    assert seen == []


def test_the_silent_archive_refresh_and_background_saves_are_not_recorded(seen):
    seen.clear()
    store.sync_archive_from_sources()
    worker = threading.Thread(target=store.upsert_contract, args=(_contract('C7'),))
    worker.start()
    worker.join()
    with row_journal.suspended():
        store.upsert_contract(_contract('C8'))
    assert seen == []


def test_a_closed_gate_and_uninstall_stop_recording(tmp_path, monkeypatch):
    monkeypatch.setenv('STAGE4_DB_PATH', str(Path(tmp_path) / 'project.sqlite3'))
    changes = []
    original = store.save_contracts
    file_journal.install(changes.append, gate=lambda: False)
    try:
        store.upsert_contract(_contract('C1'))
    finally:
        file_journal.uninstall()
    assert changes == [] and store.save_contracts is original
    assert json.loads(store.store_path().read_text(encoding='utf-8'))['contracts']
