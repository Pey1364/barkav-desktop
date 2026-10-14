"""Data Entry extras on the transaction tables and on the table of records.

* Every table of the Transactions tab gets «رفتن به رکورد متناظر در ثبت دیتا» on its right-click menu. It opens
  Data Entry on the row's record; for a cheque that has been resolved it first asks whether the issue record
  or the resolution record is wanted.
* «حذف» in Data Entry asks what to do with the rows. «فقط پنهان شود» takes them off the table and nothing else:
  the record, its registered transaction and its financial effect stay, and the rows are in the cream
  «پنهان‌شده» category beside «تأییدشده», from where they come back. «حذف کامل» removes the record's
  transaction and its financial effect for good.
"""
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

import transaction_lifecycle_ui
from barkav_ui.bidi import fa_grouped_number as fa
from cheque_record_edit187 import pending_ids
from transaction_lifecycle import TransactionLifecycle, LifecycleDecision, is_resolution_payload

GO_LABEL = 'رفتن به رکورد متناظر در ثبت دیتا'
HIDDEN_LABEL = 'پنهان شده'
HIDDEN_FILTER = 'پنهان‌شده'
HIDDEN_MENU_LABEL = '🗂 پنهان‌شده‌ها'
SHOW_AGAIN_LABEL = '↩ نمایش دوباره در جدول'
ISSUE_LABEL = 'رکورد صدور'
RESOLUTION_LABEL = 'رکورد تعیین تکلیف'


@dataclass(frozen=True)
class DeleteDecision:
    action: str          # 'hide', 'delete', or 'reject' (the older question of a table without Tk)
    grouped: bool = True


def records_for_row(db, row):
    """The Data Entry records a table row came from: [(label, pending_id)], issue before resolution."""
    row = dict(row or {})
    lifecycle = TransactionLifecycle(db)
    if row.get('cheque_id'):
        issue, resolutions = [], []
        for pid in pending_ids(db, str(row['cheque_id'])):
            item = db.get_pending_item(pid) or {}
            (resolutions if is_resolution_payload(item.get('payload')) else issue).append(pid)
        found = [(ISSUE_LABEL, pid) for pid in issue[:1]] + [(RESOLUTION_LABEL, pid) for pid in resolutions[:1]]
        if found:
            return found
    return [('رکورد ثبت', lifecycle.pending_for_row(row))]


def choose_record(parent, options):
    """Ask which of several records to open; None when the question is cancelled."""
    if len(options) == 1:
        return options[0][1]
    from barkav_ui.window import BarkavWindow
    window = BarkavWindow(parent, 'کدام رکورد؟', size_class='tiny', show_footer=False)
    chosen = {'pid': None}
    tk.Label(window.body, text='این چک تعیین تکلیف شده است. کدام رکورد باز شود؟', padx=20, pady=14, anchor='e',
             justify='right').pack(fill='x')
    actions = tk.Frame(window.body)
    actions.pack(fill='x', padx=16, pady=(0, 14))
    for label, pid in options:
        tk.Button(actions, text=label, relief='flat', padx=14, pady=7,
                  command=lambda p=pid: (chosen.update(pid=p), window.destroy())).pack(side='right', padx=4)
    tk.Button(actions, text='انصراف', relief='flat', padx=14, pady=7, command=window.destroy).pack(side='left', padx=4)
    window.grab_set()
    window.wait_window()
    return chosen['pid']


# ---------------------------------------------------------------------------------------------- hiding
def unhide(db, pending_ids_):
    """Show hidden records in the Data Entry table again."""
    ids = [str(pid) for pid in pending_ids_]
    if not ids:
        return 0
    from finance_db import _now
    marks = ','.join('?' for _ in ids)
    with db.tx() as con:
        cursor = con.execute(f"""UPDATE rich_ui_hidden_reviews SET hidden=0,updated_at=? WHERE hidden=1 AND pending_id IN ({marks})
                                 AND pending_id NOT IN (SELECT pending_id FROM transaction_lifecycle WHERE state='PURGED')""",
                             (_now(), *ids))
        return max(0, cursor.rowcount)


def hidden_rows(db, rich):
    """The rows of the «پنهان‌شده» category, as the table lists them. A record deleted completely
    is no row of any category any more (it stays in the database, which is all)."""
    hidden = {str(pid) for pid in rich.hidden_review_ids()}
    if not hidden:
        return []
    rows = db.list_pending_reviews(
        statuses=('PENDING_REVIEW', 'NEEDS_REVIEW', 'APPROVED', 'REJECTED', 'EDIT_PENDING'),
        limit=3000, newest_first=True)
    return [row for row in rows if str(row['pending_id']) in hidden]


def hide_rows(center, ids):
    """Take rows off the table; the records and their effects are untouched. Undoable."""
    from action_history import HistoryAction
    ids = list(dict.fromkeys(str(pid) for pid in ids))
    center.rich.hide_review(ids)
    db = center.rich.db
    action = HistoryAction('پنهان کردن ردیف‌های ثبت دیتا', lambda: unhide(db, ids), lambda: center.rich.hide_review(ids))
    if hasattr(center, '_push_history'):
        center._push_history({'kind': 'lifecycle', 'action': action,
                              'undone': 'ردیف‌ها دوباره در جدول نمایش داده شدند.', 'redone': 'ردیف‌ها دوباره پنهان شدند.'})
    center.refresh()
    if callable(getattr(center, 'on_posted', None)):
        center.on_posted()
    if getattr(center, 'action', None):
        center.action.set(f'{fa(len(ids))} ردیف پنهان شد؛ رکورد و اثر مالی آن در دیتابیس ماند.')
    return ids


def show_rows_again(center, ids):
    from action_history import HistoryAction
    ids = list(dict.fromkeys(str(pid) for pid in ids))
    db = center.rich.db
    unhide(db, ids)
    action = HistoryAction('نمایش دوبارهٔ ردیف‌های پنهان', lambda: center.rich.hide_review(ids), lambda: unhide(db, ids))
    if hasattr(center, '_push_history'):
        center._push_history({'kind': 'lifecycle', 'action': action,
                              'undone': 'ردیف‌ها دوباره پنهان شدند.', 'redone': 'ردیف‌ها دوباره در جدول نمایش داده شدند.'})
    center.refresh()
    if getattr(center, 'action', None):
        center.action.set(f'{fa(len(ids))} ردیف دوباره در جدول نمایش داده شد.')
    return ids


def ask_delete(parent, rows, *, messagebox, notice=''):
    """«حذف» in Data Entry: hide only, or delete the record and its transaction. None when cancelled."""
    rows = list(rows)
    count = len(rows)
    posted = any(row.get('status') in ('APPROVED', 'EDIT_PENDING') for row in rows)
    already_hidden = all(row.get('_hidden187') for row in rows)
    if not hasattr(parent, 'tk'):
        # a table without Tk (the tests of the lifecycle): the older single question, which rejects
        return DeleteDecision('reject') if messagebox.askyesno('حذف', f'{count} ردیف انتخاب‌شده حذف شوند؟', parent=parent) else None
    from barkav_ui.window import BarkavWindow
    dialog = BarkavWindow(parent, 'حذف از جدول ثبت دیتا', size_class='small', show_footer=False)
    result = [None]
    action = tk.StringVar(dialog, value='delete' if already_hidden else 'hide')
    scope = tk.StringVar(dialog, value='group' if count > 1 else 'single')
    body = ttk.Frame(dialog.body)
    body.pack(fill='both', expand=True, padx=16, pady=12)
    ttk.Label(body, text=f'با {fa(count)} ردیف انتخاب‌شده چه شود؟', anchor='e').pack(fill='x', pady=(2, 8))
    hide = ttk.Radiobutton(body, text='فقط پنهان شود', variable=action, value='hide',
                           state='disabled' if already_hidden else 'normal')
    hide.pack(anchor='e', pady=(4, 0))
    ttk.Label(body, anchor='e', justify='right', wraplength=430,
              text=('رکورد و اثر مالی آن در دیتابیس می‌ماند و از دستهٔ «پنهان‌شده» دوباره به جدول برمی‌گردد.'
                    if posted else
                    'رکورد در دیتابیس می‌ماند و از دستهٔ «پنهان‌شده» دوباره به جدول برمی‌گردد.')).pack(fill='x', padx=(0, 22))
    ttk.Radiobutton(body, text='رکورد و تراکنش ثبت‌شده حذف شود' if posted else 'رکورد حذف کامل شود',
                    variable=action, value='delete').pack(anchor='e', pady=(10, 0))
    ttk.Label(body, anchor='e', justify='right', wraplength=430,
              text=('اثر مالی از بخش‌های مرتبط برداشته می‌شود. این کار قابل بازگردانی نیست.'
                    if posted else 'این کار قابل بازگردانی نیست.')).pack(fill='x', padx=(0, 22))
    if notice:
        ttk.Label(body, text=notice, anchor='e', wraplength=430, justify='right').pack(fill='x', pady=(10, 0))
    if count > 1:
        ttk.Separator(body).pack(fill='x', pady=10)
        ttk.Radiobutton(body, text=f'همهٔ {fa(count)} ردیف انتخاب‌شده', variable=scope, value='group').pack(anchor='e', pady=2)
        ttk.Radiobutton(body, text='فقط اولین ردیف انتخاب‌شده', variable=scope, value='single').pack(anchor='e', pady=2)

    def accept():
        result[0] = DeleteDecision(action.get(), scope.get() == 'group')
        dialog.close()

    actions = ttk.Frame(body)
    actions.pack(fill='x', pady=(12, 4))
    ttk.Button(actions, text='تأیید', command=accept, style='Toolbar.TButton').pack(side='right', padx=4)
    ttk.Button(actions, text='انصراف', command=dialog.close, style='Toolbar.TButton').pack(side='left', padx=4)
    dialog._ask_delete_accept187 = accept
    dialog._ask_delete_action187 = action
    dialog.grab_set()
    parent.wait_window(dialog)
    return result[0]


# ------------------------------------------------------------------------------------- go to the record
def go_to_record(window, runtime, pid):
    """Open Data Entry on a record: all statuses shown (the hidden category for a hidden one), the row
    selected and scrolled into view."""
    center = window.approval_center
    hidden = str(pid) in {str(p) for p in window.rich.hidden_review_ids()}
    if getattr(window, 'approval_tab', None) is not None:
        window.notebook.select(window.approval_tab)
    center.filter.set(HIDDEN_FILTER if hidden else 'همه')
    center.status_filter187.set(HIDDEN_LABEL if hidden else 'همه')
    center.refresh()
    center._select_pending_ids([pid])
    return True


def install(dashboard, center, runtime):
    """Add the entries; runs after transaction_review_ui.install, whose menus it sits on."""
    original_menu = center._install_data_entry_context_actions_187

    def menu(owner):
        original_menu(owner)
        table_menu = owner.table.menu
        table_menu.insert_command(0, label=HIDDEN_MENU_LABEL, command=lambda: owner.show_hidden_187())
        table_menu.insert_separator(1)
        table_menu.add_command(label=SHOW_AGAIN_LABEL, state='disabled',
                               command=lambda: owner.show_selected_again_187())
        previous = str(table_menu.cget('postcommand') or '')

        def update():
            if previous:
                table_menu.tk.call(previous)
            rows = owner.table.selected_rows()
            allowed = bool(rows) and all(row.get('_hidden187') for row in rows)
            table_menu.entryconfigure(SHOW_AGAIN_LABEL, state='normal' if allowed else 'disabled')

        table_menu.configure(postcommand=update)

    center._install_data_entry_context_actions_187 = menu

    def provide(table):
        window = table.winfo_toplevel()
        if not isinstance(window, dashboard) or not any(
                getattr(window, name, None) is table for name in window._FINANCIAL_TABLE_NAMES_187):
            return ()

        def command():
            rows = list(table.selected_rows() or [])
            try:
                options = records_for_row(runtime.DB, rows[0])
            except (ValueError, KeyError, LifecycleDecision) as exc:
                runtime.messagebox.showerror('رکورد متناظر', str(exc), parent=window)
                return
            pid = choose_record(window, options)
            if pid:
                go_to_record(window, runtime, pid)

        return [{'label': GO_LABEL, 'command': command, 'enabled': lambda: len(table.selected_rows() or []) == 1}]

    provide._barkav_go_to_record187 = True
    transaction_lifecycle_ui.MENU_EXTRAS[:] = [
        item for item in transaction_lifecycle_ui.MENU_EXTRAS if not getattr(item, '_barkav_go_to_record187', False)]
    transaction_lifecycle_ui.MENU_EXTRAS.append(provide)
