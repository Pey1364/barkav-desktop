"""«انتقال به دردست بررسی» on the screens: where it sits in the menus, what it asks, what it records.

The entry is in the right-click menu of Data Entry (live only when every row
selected is approved) and in the menu of every table of the Transactions tab.
Both go through move_rows(): the selection is worked out first without changing
anything (an old row, a row that cannot go, the records that would go with it),
the operator is asked once with the numbers, the move runs in one SQL
transaction, and the screens refresh. The move is one step of the Undo and Redo
history of the tab it was made in (Data Entry keeps a list of its own): Undo
approves the records again, Redo returns them to review, and both refuse with a
sentence when the records changed in between (see ReviewReturn.undo_move).
"""

from __future__ import annotations

import sqlite3

import transaction_lifecycle_ui
from action_history import HistoryAction, UndoRefused
from transaction_lifecycle import LifecycleDecision
from transaction_review import MENU_LABEL, MovePlan, MoveResult, ReviewReturn

TITLE = MENU_LABEL
UNDO_SOURCE = 'GUI_REVIEW_UNDO'
REDO_SOURCE = 'GUI_REVIEW_REDO'
_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def _fa(number) -> str:
    return str(number).translate(_DIGITS)


def question(plan: MovePlan) -> str:
    lines = [f'{_fa(len(plan.sources) + len(plan.scopes))} ردیف به «در دست بررسی» منتقل شود؟', '',
             'اثر مالی آن‌ها از تراکنش‌ها، قراردادها، پیشرفت فاز و گزارش‌ها برداشته می‌شود '
             'و با تأیید دوباره ثبت می‌شود.']
    if plan.revived:
        lines.append(f'{_fa(len(plan.revived))} ردیف قبلاً از ثبت دیتا حذف شده بود، ولی اثر مالی‌اش هنوز '
                     'در دفتر فعال است؛ اثرش برداشته می‌شود و خود ردیف دوباره در دست بررسی دیده می‌شود.')
    if plan.dependents:
        lines.append(f'{_fa(len(plan.dependents))} ثبت وابسته (مثل رسید پاس‌کردن چک) هم همراه آن‌ها منتقل می‌شود.')
    if plan.scopes:
        lines.append(f'{_fa(len(plan.scopes))} ردیف قدیمی سابقهٔ ثبت دیتا ندارد: از دفتر مالی برداشته می‌شود '
                     'و از روی اطلاعاتش یک ردیف در دست بررسی ساخته می‌شود.')
    lines.append('پیش از انتقال، یک نسخهٔ پشتیبان از پایگاه‌داده کنار آن ذخیره می‌شود.')
    return '\n'.join(lines)


def _record_history(owner, db, result: MoveResult, approve) -> None:
    """Make the move a step of the Undo and Redo of the tab it was made in."""

    import row_journal

    def step(source, work):
        # A step of its own: what it writes is not another action for the journal.
        try:
            with row_journal.suspended():
                work(ReviewReturn(db, source=source))
        except (LifecycleDecision, ValueError, KeyError) as exc:
            raise UndoRefused(str(exc)) from exc

    action = HistoryAction(TITLE,
                           lambda: step(UNDO_SOURCE, lambda mover: mover.undo_move(result, approve)),
                           lambda: step(REDO_SOURCE, lambda mover: mover.redo_move(result)))
    if hasattr(owner, '_push_history'):
        # Data Entry's own list; the sentences are the ones the window's tabs say.
        owner._push_history({'kind': 'lifecycle', 'action': action,
                             'undone': f'«{TITLE}» بازگردانی شد.', 'redone': f'«{TITLE}» دوباره اجرا شد.'})
        return
    history = getattr(owner, '_window_history', None)
    if history:
        history.flush()
        history.hub.record(action)


def move_rows(owner, rows, db, messagebox, *, refresh, approve, announce=None):
    """Ask, move, record, refresh. Returns the MoveResult, or None when nothing moved.

    ``approve(pending_id, payload)`` is the approval of the screens, which Undo uses."""

    rows = [row for row in rows or () if row]
    if not rows:
        return None
    mover = ReviewReturn(db)
    try:
        plan = mover.plan_move(rows)
    except (LifecycleDecision, ValueError, KeyError) as exc:
        messagebox.showerror(TITLE, f'{exc}\nهیچ ردیفی منتقل نشد.', parent=owner)
        return None
    if plan.nothing_to_do:
        messagebox.showinfo(TITLE, 'ردیف‌های انتخاب‌شده از قبل در دست بررسی هستند.', parent=owner)
        return None
    if not messagebox.askyesno(TITLE, question(plan), parent=owner):
        return None
    try:
        mover.backup()
    except (OSError, sqlite3.Error) as exc:
        messagebox.showerror('انتقال انجام نشد', f'پشتیبان پیش از انتقال ساخته نشد: {exc}\nهیچ ردیفی منتقل نشد.',
                             parent=owner)
        return None
    import row_journal
    try:
        with row_journal.suspended():
            result = mover.run_move(plan)
    except (LifecycleDecision, ValueError, KeyError) as exc:
        messagebox.showerror('انتقال انجام نشد', f'{exc}\nهیچ ردیفی منتقل نشد.', parent=owner)
        return None
    _record_history(owner, db, result, approve)
    refresh()
    if announce is not None:
        announce(f'{_fa(len(result.moved))} ردیف به دردست بررسی منتقل شد.')
    return result


def approved_only(rows) -> bool:
    """The Data Entry rule: every row selected is an approved one."""

    rows = list(rows or ())
    return bool(rows) and all(
        row.get('status') == 'APPROVED' and not row.get('_lifecycle_decision_only187') for row in rows)


def install(dashboard, center, runtime) -> None:
    """Add the entry to Data Entry's menu and to every financial table's menu.

    Runs after transaction_lifecycle_ui.install_runtime, whose menus it sits on."""

    def move_data_entry_rows(owner, rows):
        def refresh():
            owner.refresh()
            if callable(getattr(owner, 'on_posted', None)):
                owner.on_posted()
        action = getattr(owner, 'action', None)
        return move_rows(owner, rows, runtime.DB, runtime.messagebox, refresh=refresh,
                         approve=lambda pid, payload: runtime.v18.submit_v18(pid, payload, owner.rich),
                         announce=action.set if action is not None else None)

    center.move_to_review_rows_187 = move_data_entry_rows

    original_menu = center._install_data_entry_context_actions_187

    def menu(owner):
        original_menu(owner)
        table_menu = owner.table.menu
        table_menu.add_command(label=MENU_LABEL, state='disabled',
                               command=lambda: owner.move_to_review_rows_187(owner.table.selected_rows()))
        # An earlier layer (the Restore entry) set the menu's postcommand: keep it.
        previous = str(table_menu.cget('postcommand') or '')

        def update():
            if previous:
                table_menu.tk.call(previous)
            table_menu.entryconfigure(
                MENU_LABEL, state='normal' if approved_only(owner.table.selected_rows()) else 'disabled')
        table_menu.configure(postcommand=update)

    center._install_data_entry_context_actions_187 = menu

    def move_table_rows(window, table):
        return move_rows(window, list(table.selected_rows() or []), runtime.DB, runtime.messagebox,
                         refresh=window.refresh_all,
                         approve=lambda pid, payload: runtime.v18.submit_v18(pid, payload, window.rich))

    dashboard.move_to_review_table_rows_187 = move_table_rows

    def provide(table):
        """The entry for the seven tables of the Transactions tab and no other table."""

        window = table.winfo_toplevel()
        if not isinstance(window, dashboard) or not any(
                getattr(window, name, None) is table for name in window._FINANCIAL_TABLE_NAMES_187):
            return ()
        return [{'label': MENU_LABEL,
                 'command': lambda: window.move_to_review_table_rows_187(table),
                 'enabled': lambda: bool(table.selected_rows())}]

    provide._barkav_review_move187 = True
    # A module reloaded in a test installs again: keep one provider.
    transaction_lifecycle_ui.MENU_EXTRAS[:] = [
        item for item in transaction_lifecycle_ui.MENU_EXTRAS
        if not getattr(item, '_barkav_review_move187', False)]
    transaction_lifecycle_ui.MENU_EXTRAS.append(provide)
