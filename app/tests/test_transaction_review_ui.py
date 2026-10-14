"""«انتقال به دردست بررسی» on the screens: the question, the menu entries, the history step.

The default tests drive move_rows() with a stand-in message box over a
disposable project; the opt-in ones do it through the real dashboard and its
real right-click menus (BARKAV_RUN_UI_TESTS=1).
"""

import os
import sys
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_transaction_lifecycle_matrix import CASES, case_payload, m, register, runtime, views  # noqa: E402,F401

from action_history import TabHistory  # noqa: E402
from transaction_review import BACKUP_FOLDER, BACKUP_KEEP, MENU_LABEL, MovePlan, ReviewReturn  # noqa: E402
from transaction_review_ui import approved_only, move_rows, question  # noqa: E402

gui_only = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI opt-in')


class Box:
    """A message box that answers and remembers what it was asked."""

    def __init__(self, answer=True):
        self.answer, self.calls = answer, []

    def askyesno(self, title, text, **_kw):
        self.calls.append(('ask', title, text))
        return self.answer

    def showerror(self, title, text, **_kw):
        self.calls.append(('error', title, text))

    def showinfo(self, title, text, **_kw):
        self.calls.append(('info', title, text))


def approved(runtime, case=CASES[0], message_id=1):
    payload = case_payload(runtime, case)
    pid = register(runtime, payload, message_id)
    m.v18.submit_v18(pid, payload, runtime.rich)
    return pid


def approve_with(runtime):
    """The approval Undo uses, as the screens hand it over."""

    return lambda pid, payload: m.v18.submit_v18(pid, payload, runtime.rich)


def screen():
    log: list = []
    return SimpleNamespace(log=log, _push_history=log.append, refreshed=[], said=[])


# ----------------------------------------------------------------- the words

def test_the_question_counts_in_persian_digits_and_names_what_goes_along():
    plan = MovePlan(sources=['a', 'b'], scopes=[object()], dependents=['c'])
    text = question(plan)
    assert text.splitlines()[0] == '۳ ردیف به «در دست بررسی» منتقل شود؟'
    assert '۱ ثبت وابسته' in text and '۱ ردیف قدیمی سابقهٔ ثبت دیتا ندارد' in text
    assert 'ثبت می‌شود' in text
    plain = question(MovePlan(sources=['a']))
    assert 'وابسته' not in plain and 'قدیمی' not in plain and 'حذف شده' not in plain
    assert 'نسخهٔ پشتیبان' in plain, 'the question says a copy of the database is kept first'
    revived = question(MovePlan(sources=['a'], revived=['a']))
    assert '۱ ردیف قبلاً از ثبت دیتا حذف شده بود' in revived and 'هنوز در دفتر فعال است' in revived


def test_the_menu_title_is_the_one_the_operator_asked_for():
    assert MENU_LABEL == 'انتقال به دردست بررسی'


def test_data_entry_enables_it_only_for_approved_rows():
    approved_row = {'status': 'APPROVED'}
    assert approved_only([approved_row])
    assert approved_only([approved_row, approved_row])
    assert not approved_only([])
    assert not approved_only([approved_row, {'status': 'PENDING_REVIEW'}])
    assert not approved_only([{'status': 'REJECTED'}])
    assert not approved_only([{'status': 'APPROVED', '_lifecycle_decision_only187': True}])


# ------------------------------------------------------------------ the move

def test_accepting_moves_the_rows_asks_once_refreshes_and_records_a_step(runtime):
    pid = approved(runtime)
    row = runtime.db.get_pending_item(pid)
    box, win = Box(True), screen()
    result = move_rows(win, [row], runtime.db, box, refresh=lambda: win.refreshed.append(1),
                       approve=approve_with(runtime), announce=win.said.append)
    assert result.moved == [pid]
    assert [kind for kind, *_ in box.calls] == ['ask']
    assert box.calls[0][2].splitlines()[0] == '۱ ردیف به «در دست بررسی» منتقل شود؟'
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'
    assert runtime.db.snapshot().cash_balance == 0
    assert win.refreshed == [1] and win.said == ['۱ ردیف به دردست بررسی منتقل شد.']
    entry = win.log[0]
    assert entry['kind'] == 'lifecycle' and entry['action'].undoable
    assert entry['undone'] == '«انتقال به دردست بررسی» بازگردانی شد.'
    assert entry['redone'] == '«انتقال به دردست بررسی» دوباره اجرا شد.'


def test_undo_and_redo_of_the_step_in_a_tab_history(runtime):
    pid = approved(runtime)
    approved_views = views(runtime)
    box, win = Box(True), screen()
    move_rows(win, [runtime.db.get_pending_item(pid)], runtime.db, box, refresh=lambda: None,
              approve=approve_with(runtime))
    moved_views = views(runtime)
    history = TabHistory()
    history.push(win.log[0]['action'])

    assert history.undo() == '«انتقال به دردست بررسی» بازگردانی شد.' and history.changed
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert runtime.db.snapshot().cash_balance == -1000
    assert history.redo() == '«انتقال به دردست بررسی» دوباره اجرا شد.' and history.changed
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'
    assert views(runtime) == moved_views
    assert history.undo() == '«انتقال به دردست بررسی» بازگردانی شد.', 'and again'
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert approved_views['snapshot'] == views(runtime)['snapshot']


def test_undo_writes_no_step_of_its_own_into_the_journal(runtime):
    """A step that has its own Undo must not also be recorded as table edits."""

    import row_journal
    pid = approved(runtime)
    seen = []
    row_journal.install(lambda db, changes: seen.append(changes), gate=lambda: True)
    try:
        runtime.db.create_expense(event_date='2026-09-20', shamsi_date='1405/06/29', final_amount=5,
                                  description='کنترل', vendor_name='x', category='MATERIAL',
                                  status='APPROVED', source='LEGACY')
        assert seen, 'control: the journal sees an ordinary write'
        seen.clear()
        box, win = Box(True), screen()
        move_rows(win, [runtime.db.get_pending_item(pid)], runtime.db, box, refresh=lambda: None,
                  approve=approve_with(runtime))
        history = TabHistory()
        history.push(win.log[0]['action'])
        history.undo()
        history.redo()
    finally:
        row_journal.uninstall()
    assert seen == []


def test_undo_says_why_when_the_rows_changed_and_drops_the_step(runtime):
    pid = approved(runtime)
    payload = runtime.db.get_pending_item(pid)['payload']
    box, win = Box(True), screen()
    move_rows(win, [runtime.db.get_pending_item(pid)], runtime.db, box, refresh=lambda: None,
              approve=approve_with(runtime))
    runtime.db.update_pending(pid, payload={**payload, 'description': 'ویرایش پس از انتقال'})
    history = TabHistory()
    history.push(win.log[0]['action'])
    said = history.undo()
    assert said.startswith('«انتقال به دردست بررسی» بازگردانی نشد:') and 'تغییر کرده‌اند' in said
    assert 'از سابقه حذف شد' in said and not history.changed and not history.can_undo()
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'


def test_declining_changes_nothing(runtime):
    pid = approved(runtime)
    before = views(runtime)
    box, win = Box(False), screen()
    assert move_rows(win, [runtime.db.get_pending_item(pid)], runtime.db, box,
                     refresh=lambda: win.refreshed.append(1), approve=approve_with(runtime)) is None
    assert views(runtime) == before and not win.refreshed and not win.log
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'


def test_a_row_that_cannot_go_is_explained_before_anything_is_asked(runtime):
    pid = approved(runtime)
    before = views(runtime)
    box, win = Box(True), screen()
    stuck = {'expense_id': 'EX-none', 'cheque_id': 'C1'}
    assert move_rows(win, [runtime.db.get_pending_item(pid), stuck], runtime.db, box,
                     refresh=lambda: win.refreshed.append(1), approve=approve_with(runtime)) is None
    assert [kind for kind, *_ in box.calls] == ['error']
    assert 'تعیین تکلیف' in box.calls[0][2] and 'هیچ ردیفی منتقل نشد' in box.calls[0][2]
    assert views(runtime) == before and runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert not win.refreshed and not win.log


def test_rows_already_under_review_get_a_notice_not_a_question(runtime):
    pid = register(runtime, case_payload(runtime, CASES[0]))
    box, win = Box(True), screen()
    assert move_rows(win, [runtime.db.get_pending_item(pid)], runtime.db, box, refresh=lambda: None,
                     approve=approve_with(runtime)) is None
    assert [kind for kind, *_ in box.calls] == ['info']


def test_an_empty_selection_does_nothing(runtime):
    box = Box()
    assert move_rows(screen(), [], runtime.db, box, refresh=lambda: None, approve=approve_with(runtime)) is None
    assert box.calls == []


def test_a_failure_while_moving_says_so_and_changes_nothing(runtime, monkeypatch):
    pid = approved(runtime)
    before = views(runtime)
    audit = runtime.db._audit

    def fail(con, entity, *args, **kwargs):
        if entity == 'pending':
            raise ValueError('injected failure')
        return audit(con, entity, *args, **kwargs)
    box, win = Box(True), screen()
    with monkeypatch.context() as patch:
        patch.setattr(runtime.db, '_audit', fail)
        assert move_rows(win, [runtime.db.get_pending_item(pid)], runtime.db, box,
                         refresh=lambda: win.refreshed.append(1), approve=approve_with(runtime)) is None
    assert [kind for kind, *_ in box.calls] == ['ask', 'error']
    assert 'هیچ ردیفی منتقل نشد' in box.calls[1][2]
    assert views(runtime) == before and not win.refreshed and not win.log


# ------------------------------------------------- a copy of the database comes first

def copies_of(runtime):
    return sorted((Path(runtime.db.db_path).parent / BACKUP_FOLDER).glob('*.pre-review-return.sqlite3'))


def test_a_copy_of_the_database_is_made_before_the_move_and_holds_the_state_before_it(runtime):
    import sqlite3
    from contextlib import closing
    pid = approved(runtime)
    posting = runtime.db.get_financial_posting(pid)
    box, win = Box(True), screen()
    assert move_rows(win, [runtime.db.get_pending_item(pid)], runtime.db, box, refresh=lambda: None,
                     approve=approve_with(runtime))
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'
    (copy,) = copies_of(runtime)
    with closing(sqlite3.connect(copy)) as before:
        assert before.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert before.execute('SELECT status FROM pending_items WHERE pending_id=?', (pid,)).fetchone()[0] == 'APPROVED'
        assert before.execute('SELECT status FROM expenses WHERE expense_id=?',
                              (posting['expense_id'],)).fetchone()[0] != 'CANCELLED'
        assert before.execute('SELECT COUNT(*) FROM financial_postings WHERE pending_id=?', (pid,)).fetchone()[0] == 1


def test_only_the_newest_copies_are_kept(runtime):
    mover = ReviewReturn(runtime.db)
    made = [mover.backup() for _ in range(BACKUP_KEEP + 3)]
    assert copies_of(runtime) == made[-BACKUP_KEEP:]
    assert not any(path.exists() for path in made[:-BACKUP_KEEP])


def test_a_move_stops_when_the_copy_cannot_be_made(runtime, monkeypatch):
    pid = approved(runtime)
    before = views(runtime)

    def refuse(self):
        raise OSError('disk full')
    monkeypatch.setattr(ReviewReturn, 'backup', refuse)
    box, win = Box(True), screen()
    assert move_rows(win, [runtime.db.get_pending_item(pid)], runtime.db, box,
                     refresh=lambda: win.refreshed.append(1), approve=approve_with(runtime)) is None
    assert [kind for kind, *_ in box.calls] == ['ask', 'error']
    assert 'پشتیبان' in box.calls[1][2] and 'هیچ ردیفی منتقل نشد' in box.calls[1][2]
    assert views(runtime) == before and runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert not win.refreshed and not win.log


def test_declining_makes_no_copy(runtime):
    pid = approved(runtime)
    assert move_rows(screen(), [runtime.db.get_pending_item(pid)], runtime.db, Box(False),
                     refresh=lambda: None, approve=approve_with(runtime)) is None
    assert copies_of(runtime) == []


def test_the_dashboard_installs_the_entry_on_data_entry_and_on_every_financial_table():
    """Wiring check without a window: the hooks the install leaves on the classes."""

    center, dashboard = m.DataEntryCenter187, m.Stage187Dashboard
    assert callable(center.move_to_review_rows_187)
    assert callable(dashboard.move_to_review_table_rows_187)
    assert {'all_tx_table', 'exp_table', 'in_table', 'out_table', 'loan_table', 'cheque_table',
            'document_table'} == set(dashboard._FINANCIAL_TABLE_NAMES_187)


# ---------------------------------------------------- the real dashboard, real menus

if os.environ.get('BARKAV_RUN_UI_TESTS') == '1':
    from test_transaction_lifecycle_ui import window  # noqa: F401  (the dashboard on a disposable project)
    from test_transaction_review_return import old_expense, shape  # noqa: F401
else:  # the fixtures are only resolved by the opt-in tests below
    window = None


def _case(name):
    return next(case for case in CASES if case[0] == name)


def _popup(monkeypatch):
    """tk_popup blocks until a menu is dismissed: keep the menu instead of posting it."""

    shown = []
    monkeypatch.setattr(tk.Menu, 'tk_popup', lambda self, *a, **k: shown.append(self))
    return shown


@gui_only
def test_the_data_entry_menu_entry_follows_the_rows_selected(runtime, window):
    center, menu = window.approval_center, window.approval_center.table.menu
    approved_id = approved(runtime, message_id=1)
    pending_id = register(runtime, case_payload(runtime, CASES[0]), 2)
    rejected_id = approved(runtime, message_id=3)
    from transaction_lifecycle import TransactionLifecycle
    TransactionLifecycle(runtime.db).reject(rejected_id)
    window.refresh_all()
    window.update()

    def states(pid, shown):
        center.filter.set(shown)
        center.refresh()
        window.update()
        iid = next(i for i, r in center.table.iid_to_row.items() if r['pending_id'] == pid)
        center.table.tree.selection_set(iid)
        menu.tk.call(menu.cget('postcommand'))
        return menu.entrycget(MENU_LABEL, 'state'), menu.entrycget('بازگردانی / Restore', 'state')

    assert states(approved_id, 'تأییدشده') == ('normal', 'disabled')
    assert states(pending_id, 'Pending') == ('disabled', 'disabled')
    assert states(rejected_id, 'ردشده') == ('disabled', 'normal'), 'the Restore entry still follows its own rule'
    center.table.tree.selection_set(())
    menu.tk.call(menu.cget('postcommand'))
    assert menu.entrycget(MENU_LABEL, 'state') == 'disabled'


@gui_only
def test_the_data_entry_entry_moves_approved_rows_to_review(runtime, window, monkeypatch):
    center, menu = window.approval_center, window.approval_center.table.menu
    baseline = views(runtime)
    ids = [approved(runtime, CASES[0], 1), approved(runtime, _case('income'), 2)]
    asked = []
    monkeypatch.setattr(m.messagebox, 'askyesno', lambda title, text, **kw: asked.append(text) or True)
    window.refresh_all()
    center.filter.set('تأییدشده')
    center.refresh()
    window.update()
    center.table.tree.selection_set(list(center.table.iid_to_row))
    menu.tk.call(menu.cget('postcommand'))
    assert menu.entrycget(MENU_LABEL, 'state') == 'normal'
    menu.invoke(MENU_LABEL)
    window.update()

    assert asked[0].splitlines()[0] == '۲ ردیف به «در دست بررسی» منتقل شود؟'
    assert {runtime.db.get_pending_item(pid)['status'] for pid in ids} == {'PENDING_REVIEW'}
    assert views(runtime) == baseline
    assert not center.table.iid_to_row, 'nothing is left in the approved list'
    assert center.action.get() == '۲ ردیف به دردست بررسی منتقل شد.'
    center.filter.set('Pending')
    center.refresh()
    assert {r['pending_id'] for r in center.table.iid_to_row.values()} >= set(ids)
    assert not window._test_errors


def _show_tab(window, table):
    """Bring the tab that holds a Transactions table to the front, as a click on it does."""

    window.notebook.select(window.fin_nb.master)
    tabs = {str(tab) for tab in window.fin_nb.tabs()}
    widget = table
    while widget is not None and str(widget) not in tabs:
        widget = widget.master
    assert widget is not None, 'the table is not on a tab of the financial notebook'
    window.fin_nb.select(widget)
    window.update()


def _right_click(window, tree, iid=None):
    """The real <Button-3> event, on a row (or below the rows): what the table's own binding answers.

    Calling a table's _context_menu() directly is not the same: the Transactions
    tables answer the event with a menu of their own."""

    window.update()
    if iid is None:
        x, y = 8, max(tree.winfo_height() - 4, 1)
    else:
        left, top, _width, height = tree.bbox(iid)
        x, y = left + 8, top + height // 2
    tree.event_generate('<Button-3>', x=x, y=y, rootx=tree.winfo_rootx() + x, rooty=tree.winfo_rooty() + y)
    window.update()


def _labels(menu):
    return [(menu.entrycget(i, 'label'), menu.entrycget(i, 'state')) for i in range(menu.index('end') + 1)
            if menu.type(i) not in ('separator', 'cascade')]


@gui_only
def test_a_real_right_click_on_every_transactions_tab_offers_it_and_undo_redo_work(runtime, window, monkeypatch):
    from transaction_lifecycle import TransactionLifecycle
    life = TransactionLifecycle(runtime.db)
    shown = _popup(monkeypatch)
    asked = []
    monkeypatch.setattr(m.messagebox, 'askyesno', lambda title, text, **kw: asked.append(text) or True)
    history = window._window_history
    wanted = {'all_tx_table': CASES[0], 'exp_table': CASES[0], 'in_table': _case('income'),
              'out_table': _case('out'), 'cheque_table': _case('cheque'), 'loan_table': _case('loan'),
              'document_table': _case('note-0')}
    assert set(wanted) == set(window._FINANCIAL_TABLE_NAMES_187)

    def maps_to(row, pid):
        try:
            return life.pending_for_row(row) == pid
        except Exception:
            return False

    for index, (name, case) in enumerate(wanted.items()):
        table = getattr(window, name)
        payload = case_payload(runtime, case)
        baseline = views(runtime)
        pid = register(runtime, payload, 100 + index)
        m.v18.submit_v18(pid, payload, runtime.rich)
        approved_views = views(runtime)
        window.refresh_all()
        _show_tab(window, table)
        iid = next((i for i, r in table._iid_to_row.items() if maps_to(r, pid)), None)
        assert iid is not None, f'{name} shows no row for the record'

        # Nothing selected yet: the right-click picks the row under it, and the entry is live.
        table.tree.selection_set(())
        shown.clear()
        _right_click(window, table.tree, iid)
        assert shown, f'{name}: the right-click showed no menu'
        entries = dict(_labels(shown[-1]))
        assert entries.get(MENU_LABEL) == 'normal', f'{name}: {entries}'
        shown[-1].invoke(MENU_LABEL)
        window.update()
        assert asked[-1].splitlines()[0] == '۱ ردیف به «در دست بررسی» منتقل شود؟', name
        assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW', name
        assert views(runtime) == baseline, name

        # Undo and Redo, from the same tab, as the toolbar buttons do them.
        assert history.undo() == '«انتقال به دردست بررسی» بازگردانی شد.', name
        window.update()
        assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED', name
        assert shape(views(runtime)) == shape(approved_views), name
        assert history.redo() == '«انتقال به دردست بررسی» دوباره اجرا شد.', name
        window.update()
        assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW', name
        assert views(runtime) == baseline, name

        # A right-click where there is no row: the entry is there but not live.
        table.tree.selection_set(())
        shown.clear()
        _right_click(window, table.tree)
        assert dict(_labels(shown[-1])).get(MENU_LABEL) == 'disabled', f'{name}: nothing is selected'
    # Other tables of the app have no such entry: the manager's account is not part of the Transactions tab.
    other = window.manager_withdraw_table
    shown.clear()
    other._context_menu(SimpleNamespace(x=0, y=0, x_root=0, y_root=0))
    assert MENU_LABEL not in [label for label, _state in _labels(shown[-1])]
    assert not window._test_errors


@gui_only
def test_a_real_right_click_in_data_entry_and_its_own_undo_list(runtime, window, monkeypatch):
    center = window.approval_center
    shown = _popup(monkeypatch)
    monkeypatch.setattr(m.messagebox, 'askyesno', lambda title, text, **kw: True)
    pid = approved(runtime, message_id=1)
    approved_views = views(runtime)
    window.refresh_all()
    window.notebook.select(window.approval_tab)
    center.filter.set('تأییدشده')
    center.refresh()
    window.update()
    iid = next(i for i, r in center.table.iid_to_row.items() if r['pending_id'] == pid)
    center.table.tree.selection_set(())
    _right_click(window, center.table.tree, iid)
    menu = shown[-1]
    assert menu is center.table.menu
    menu.tk.call(menu.cget('postcommand'))  # Tk runs it when it posts the menu
    assert menu.entrycget(MENU_LABEL, 'state') == 'normal'
    menu.invoke(MENU_LABEL)
    window.update()
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'

    history = window._window_history
    assert center.can_undo(), 'the step is on the Data Entry list'
    assert history.undo() == '«انتقال به دردست بررسی» بازگردانی شد.'
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert shape(views(runtime)) == shape(approved_views)
    assert history.redo() == '«انتقال به دردست بررسی» دوباره اجرا شد.'
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'
    assert not window._test_errors


@gui_only
def test_a_data_entry_undo_that_cannot_be_done_says_why_and_leaves_older_steps_reachable(runtime, window, monkeypatch):
    center = window.approval_center
    monkeypatch.setattr(m.messagebox, 'askyesno', lambda title, text, **kw: True)
    pid = approved(runtime, message_id=1)
    payload = runtime.db.get_pending_item(pid)['payload']
    window.refresh_all()
    center.filter.set('تأییدشده')
    center.refresh()
    window.update()
    older = {'kind': 'paste', 'pending_ids': []}
    center._push_history(older)
    iid = next(i for i, r in center.table.iid_to_row.items() if r['pending_id'] == pid)
    center.table.tree.selection_set(iid)
    center.move_to_review_rows_187(center.table.selected_rows())
    runtime.db.update_pending(pid, payload={**payload, 'description': 'ویرایش پس از انتقال'})

    said = center.undo_data_entry()
    assert 'تغییر کرده‌اند' in said and said.endswith('این مورد از سابقه حذف شد.')
    assert center._undo_stack == [older], 'the step is dropped, so the older one is not stuck behind it'
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'
    assert not window._test_errors


@gui_only
def test_an_old_expense_row_without_a_record_goes_to_review_from_its_table(runtime, window, monkeypatch):
    shown = _popup(monkeypatch)
    asked = []
    monkeypatch.setattr(m.messagebox, 'askyesno', lambda title, text, **kw: asked.append(text) or True)
    baseline = views(runtime)
    expense, _ = old_expense(runtime)
    window.refresh_all()
    window.update()
    table = window.exp_table
    iid = next(i for i, r in table._iid_to_row.items() if r.get('expense_id') == expense)
    _show_tab(window, table)
    table.tree.selection_set(())
    _right_click(window, table.tree, iid)
    shown[-1].invoke(MENU_LABEL)
    window.update()

    assert 'سابقهٔ ثبت دیتا ندارد' in asked[-1]
    assert views(runtime) == baseline
    made = [r for r in runtime.approval.list_reviews(statuses=('PENDING_REVIEW',))
            if r['payload'].get('legacy_expense_id') == expense]
    assert len(made) == 1
    center = window.approval_center
    center.filter.set('Pending')
    center.refresh()
    assert made[0]['pending_id'] in {r['pending_id'] for r in center.table.iid_to_row.values()}
    assert not window._test_errors


@gui_only
def test_a_record_deleted_for_good_with_live_rows_comes_back_from_its_expense_tab(runtime, window, monkeypatch):
    """The case found in a real project: no row in Data Entry, a live expense in the tab."""

    from test_transaction_review_return import half_deleted
    shown = _popup(monkeypatch)
    asked = []
    monkeypatch.setattr(m.messagebox, 'askyesno', lambda title, text, **kw: asked.append(text) or True)
    baseline = views(runtime)
    pid, _ = half_deleted(runtime)
    window.refresh_all()
    window.update()
    center = window.approval_center
    for shown_filter in ('همه', 'Pending', 'تأییدشده', 'ردشده'):
        center.filter.set(shown_filter)
        center.refresh()
        assert pid not in {r['pending_id'] for r in center.table.iid_to_row.values()}, shown_filter
    table = window.exp_table
    iid = next(i for i, r in table._iid_to_row.items() if r.get('pending_id') == pid)
    _show_tab(window, table)
    table.tree.selection_set(())
    _right_click(window, table.tree, iid)
    shown[-1].invoke(MENU_LABEL)
    window.update()

    assert 'قبلاً از ثبت دیتا حذف شده بود' in asked[-1]
    assert views(runtime) == baseline
    center.filter.set('Pending')
    center.refresh()
    assert pid in {r['pending_id'] for r in center.table.iid_to_row.values()}, 'the record is in review'
    # Undo, from the tab it was made in: the record is approved again, and Data Entry shows it.
    assert window._window_history.undo() == '«انتقال به دردست بررسی» بازگردانی شد.'
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert runtime.db.snapshot().construction_cost == 1000
    assert not window._test_errors
