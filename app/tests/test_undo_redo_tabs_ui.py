"""The toolbar's Undo/Redo, end to end on the real (18.7) dashboard window.

A delete made in one table is undone from that same table, and only there.
Opt-in like the other GUI tests (BARKAV_RUN_UI_TESTS=1); throwaway database.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from tkinter import ttk

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytestmark = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI tests opt-in')
_BOOT = tempfile.TemporaryDirectory()
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'undo-token')
os.environ.setdefault('GEMINI_API_KEY', 'undo-key')
os.environ.setdefault('ADMIN_USER_ID', '1')
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'undo_tabs.sqlite3')
os.environ['STAGE4_SHEETS_ENABLED'] = 'false'

os.environ.setdefault('GROUP_CHAT_ID', '-100777')

import dashboard_stage18_7 as m  # noqa: E402  (the active layer users actually run)


@pytest.fixture(scope='module')
def app():
    m.v186.v185.fetch_tgju_usd_toman = lambda timeout=6.0: (70_000, '2026-08-21T12:00:00')  # no network
    from barkav_ui import art
    art.clear_cache()
    window = m.Stage187Dashboard()
    window.geometry('1500x950+0+0')
    window.update()
    window.update_idletasks()
    yield window
    try:
        pending = window.tk.call('after', 'info')
        if isinstance(pending, str):
            pending = (pending,) if pending else ()
        for job in pending:
            try:
                window.after_cancel(job)
            except Exception:
                pass
    except Exception:
        pass
    try:
        window.destroy()
    except Exception:
        pass


def _show(app, widget):
    """Bring ``widget`` into view by selecting every notebook tab that holds it."""
    chain = []
    node = widget
    while node is not None and node is not app:
        chain.append(node)
        node = node.master
    for node in reversed(chain):
        if isinstance(node.master, ttk.Notebook):
            node.master.select(node)
    app.update()
    app.update_idletasks()


def _click(app):
    """What a real click does before its command runs: it opens the user-action window."""
    app._window_history._mark_input()


@pytest.fixture()
def messages(app, monkeypatch):
    seen = []
    monkeypatch.setattr(m.messagebox, 'showinfo', lambda title, message, **_kw: seen.append(message))
    monkeypatch.setattr(m.messagebox, 'askyesno', lambda *_a, **_kw: True)
    monkeypatch.setattr(app.rich, 'undo_last',
                        lambda: (_ for _ in ()).throw(AssertionError('the global stack must not run')))
    monkeypatch.setattr(app.rich, 'redo_last',
                        lambda: (_ for _ in ()).throw(AssertionError('the global stack must not run')))
    return seen


def _status(table, column, value):
    with m.DB.read() as con:
        return con.execute(f'SELECT status FROM {table} WHERE {column}=?', (value,)).fetchone()[0]


def _source(app,mid,amount,*,cheque=False):
    """Financial table actions act on an approved Data Entry source."""
    m.DB.register_telegram_message(chat_id=-992,message_id=mid,raw_text='Undo source',content_type='TEXT',message_date='2026-09-01T10:00:00')
    payload={'detected_type':'EXPENSE' if cheque else 'OUTFLOW','v18_title':'هزینه ساخت' if cheque else 'خروجی',
        'v18_subtype':'چک' if cheque else 'سایر','event_date_shamsi':'1405/07/08','amount':amount,
        'final_amount':amount,'description':'آزمون سابقه','cost_group':'مصالح','payment_state':'PAID',
        'payment_method':'CHEQUE' if cheque else 'BANK_TRANSFER','is_cheque':cheque,'cheque_status':'ISSUED',
        'due_date_shamsi':'1405/08/08'}
    pid=m.DB.create_or_replace_pending(telegram_chat_id=-992,telegram_message_id=mid,detected_type=payload['detected_type'],payload=payload,confidence=1,status='PENDING_REVIEW')
    m.v18.submit_v18(pid,payload,app.rich)
    return m.DB.get_financial_posting(pid)


def _confirm(app):
    """Accept the real deletion dialog without replacing its contract."""
    def answer():
        from tkinter import Toplevel
        def walk(widget):
            yield widget
            for child in widget.winfo_children():yield from walk(child)
        dialogs=[w for w in app.winfo_children() if isinstance(w,Toplevel) and w.title()=='تأیید حذف']
        if not dialogs:app.after(50,answer);return
        button=next(w for w in walk(dialogs[-1]) if isinstance(w,ttk.Button) and w.cget('text')=='تأیید حذف')
        button.invoke()
    app.after(50,answer)


def test_a_delete_in_the_transactions_tab_is_undone_and_redone_there(app, messages):
    tx = _source(app,1,1000)['transaction_id']
    _show(app, app.all_tx_table)
    app.refresh_all()

    _click(app)
    _confirm(app)
    app._delete_tx_row({'transaction_id': tx})
    assert _status('transactions', 'transaction_id', tx) == 'VOIDED'

    app.undo()
    assert messages[-1] == '«حذف ثبت و آثار وابسته» بازگردانی شد.'
    assert _status('transactions', 'transaction_id', tx) == 'POSTED'

    app.redo()
    assert messages[-1] == '«حذف ثبت و آثار وابسته» دوباره اجرا شد.'
    assert _status('transactions', 'transaction_id', tx) == 'VOIDED'


def test_undo_in_another_tab_leaves_that_delete_alone(app, messages):
    tx = _source(app,2,2000)['transaction_id']
    _show(app, app.all_tx_table)
    _click(app)
    _confirm(app)
    app._delete_tx_row({'transaction_id': tx})

    _show(app, app.cheque_table)
    app.undo()
    assert messages[-1] == 'عملیاتی برای بازگردانی در این تب وجود ندارد.'
    assert _status('transactions', 'transaction_id', tx) == 'VOIDED'

    _show(app, app.all_tx_table)
    app.undo()
    assert messages[-1] == '«حذف ثبت و آثار وابسته» بازگردانی شد.'
    assert _status('transactions', 'transaction_id', tx) == 'POSTED'


def test_cancelling_a_cheque_is_undone_from_the_cheques_table(app, messages):
    cheque = _source(app,3,5_000_000,cheque=True)['cheque_id']
    old = _status('cheques', 'cheque_id', cheque)
    _show(app, app.cheque_table)
    app.refresh_all()

    _click(app)
    _confirm(app)
    app._cancel_cheque_row({'cheque_id': cheque})
    assert _status('cheques', 'cheque_id', cheque) == 'CANCELLED'

    app.undo()
    assert messages[-1] == '«حذف ثبت و آثار وابسته» بازگردانی شد.'
    assert _status('cheques', 'cheque_id', cheque) == old
