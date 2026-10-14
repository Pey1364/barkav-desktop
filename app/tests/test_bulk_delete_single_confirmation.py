"""A bulk delete asks once for the whole selection; a single-row delete still asks for itself."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

_BOOT = tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'bulk_delete.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'bulk-delete-token')
os.environ.setdefault('GEMINI_API_KEY', 'bulk-delete-gemini')
os.environ.setdefault('ADMIN_USER_ID', '1')
os.environ.setdefault('GROUP_CHAT_ID', '-100777')

import dashboard_stage12 as d12  # noqa: E402
import dashboard_stage18_7  # install the active table routes for standalone runs


class _Table:
    """The few members SmartTable._delete_selected_many uses - no Tk window needed."""

    def __init__(self, rows):
        self._rows = rows
        self.delete_handler = None
        self.window = SimpleNamespace()
        self.master = self.window

    def selected_rows(self):
        return list(self._rows)

    def winfo_toplevel(self):
        return self.window


def _recording(monkeypatch, answer=True):
    asked, errors = [], []
    monkeypatch.setattr(d12.messagebox, 'askyesno',
                        lambda title, message, **_kw: asked.append(title) or answer)
    monkeypatch.setattr(d12.messagebox, 'showerror',
                        lambda title, message, **_kw: errors.append(message))
    return asked, errors


def _asking_handler(table, deleted):
    def handler(row):
        if d12.Stage12Dashboard._confirm_row_action(table.window, 'حذف', 'یک ردیف حذف شود؟'):
            deleted.append(row['id'])
    return handler


def test_bulk_delete_asks_once_for_the_whole_selection(monkeypatch):
    asked, _errors = _recording(monkeypatch)
    deleted = []
    table = _Table([{'id': 1}, {'id': 2}, {'id': 3}])
    table.delete_handler = _asking_handler(table, deleted)

    d12.SmartTable._delete_selected_many(table)

    assert deleted == [1, 2, 3]
    assert asked == ['حذف']
    assert table.window._bulk_delete_confirmed is False


def test_single_row_delete_still_asks_for_itself(monkeypatch):
    asked, _errors = _recording(monkeypatch)
    deleted = []
    table = _Table([{'id': 7}])
    table.delete_handler = _asking_handler(table, deleted)

    d12.SmartTable._delete_selected_many(table)

    assert deleted == [7]
    assert asked == ['حذف']


def test_declining_the_group_prompt_deletes_nothing(monkeypatch):
    asked, _errors = _recording(monkeypatch, answer=False)
    deleted = []
    table = _Table([{'id': 1}, {'id': 2}])
    table.delete_handler = _asking_handler(table, deleted)

    d12.SmartTable._delete_selected_many(table)

    assert deleted == []
    assert asked == ['حذف']
    assert not hasattr(table.window, '_bulk_delete_confirmed')


def test_the_prompt_flag_is_released_when_a_handler_fails(monkeypatch):
    _asked, errors = _recording(monkeypatch)
    calls = []
    table = _Table([{'id': 1}, {'id': 2}, {'id': 3}])

    def handler(row):
        calls.append(row['id'])
        if row['id'] == 2:
            raise RuntimeError('boom')

    table.delete_handler = handler

    d12.SmartTable._delete_selected_many(table)

    assert calls == [1, 2]
    assert errors == ['boom']
    assert table.window._bulk_delete_confirmed is False


def test_real_delete_handler_skips_its_prompt_only_during_a_bulk_delete(monkeypatch):
    asked, _errors = _recording(monkeypatch)
    done = []
    monkeypatch.setattr(d12, 'SERVICE', SimpleNamespace(
        delete_posting=lambda pending_id: done.append(('posting', pending_id)),
        delete_manual_transaction=lambda transaction_id: done.append(('manual', transaction_id)),
    ))
    window = SimpleNamespace(refresh_all=lambda: None)
    window._confirm_row_action = lambda title, message: d12.Stage12Dashboard._confirm_row_action(
        window, title, message)

    d12.Stage12Dashboard._delete_tx_row(window, {'pending_id': 'PEN-1'})
    assert asked == ['حذف']

    window._bulk_delete_confirmed = True
    d12.Stage12Dashboard._delete_tx_row(window, {'transaction_id': 'TX-2'})

    assert asked == ['حذف']
    assert done == [('posting', 'PEN-1'), ('manual', 'TX-2')]


def test_sale_cancellation_also_asks_only_once_in_a_bulk_delete(monkeypatch):
    asked, _errors = _recording(monkeypatch)
    cancelled = []
    monkeypatch.setattr(d12, 'SERVICE', SimpleNamespace(
        revenue=SimpleNamespace(cancel_sale=lambda sale_id: cancelled.append(sale_id))))
    window = SimpleNamespace(refresh_all=lambda: None)
    window._confirm_row_action = lambda title, message: d12.Stage12Dashboard._confirm_row_action(
        window, title, message)

    d12.Stage12Dashboard._cancel_sale_row(window, {'sale_id': 'S-1', 'unit_number': '۱۲'})
    assert asked == ['لغو قرارداد']

    window._bulk_delete_confirmed = True
    d12.Stage12Dashboard._cancel_sale_row(window, {'sale_id': 'S-2', 'unit_number': '۱۳'})

    assert asked == ['لغو قرارداد']
    assert cancelled == ['S-1', 'S-2']
