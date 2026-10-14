"""Window-level wiring for the toolbar's Undo and Redo buttons.

* which tab the user is looking at (the *scope* of a history),
* which database writes are a user's action, and which are the app's own
  refreshing (only writes made just after a click or a key press are recorded),
* how one user action, however many transactions it commits, becomes a single
  undo step (all writes of one Tk event-loop turn are merged),
* the Data Entry tab, which keeps the in-memory history it always had.

The pure history lives in ``action_history``; what a write changed lives in
``row_journal``. This module only connects them to a Tk window.
"""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Callable

import file_journal
import row_journal
from action_history import HistoryHub

#: A write counts as the user's own when a click or key press was this recent.
USER_ACTION_WINDOW = 2.0
DATA_ENTRY_SCOPE = 'data_entry'
DATA_ENTRY_NOTHING_TO_UNDO = 'عملیات قابل بازگشتی در ثبت دیتا وجود ندارد.'
DATA_ENTRY_NOTHING_TO_REDO = 'عملیات قابل Redo در ثبت دیتا وجود ندارد.'
_INPUT_EVENTS = ('<ButtonPress>', '<KeyPress>')
_MAX_TAB_DEPTH = 6


def _first_notebook(page: tk.Misc) -> ttk.Notebook | None:
    """The first notebook laid out inside ``page`` (breadth first)."""
    queue = [page]
    while queue:
        widget = queue.pop(0)
        try:
            children = widget.winfo_children()
        except tk.TclError:
            continue
        for child in children:
            try:
                if not child.winfo_manager():
                    continue
            except tk.TclError:
                continue
            if isinstance(child, ttk.Notebook):
                try:
                    if child.tabs():
                        return child
                except tk.TclError:
                    pass
                continue
            queue.append(child)
    return None


def active_scope(window: tk.Misc) -> str:
    """A stable key for the tab (and sub-tab) the user is on; '' on the start page."""
    if getattr(window, '_window_view187', 'project') == 'start':
        return ''
    center = getattr(window, 'approval_center', None)
    try:
        if center is not None and center.winfo_ismapped():
            return DATA_ENTRY_SCOPE
    except tk.TclError:
        pass
    parts: list[str] = []
    notebook = getattr(window, 'notebook', None)
    for _depth in range(_MAX_TAB_DEPTH):
        if notebook is None:
            break
        try:
            current = notebook.select()
            if not current:
                break
            parts.append(str(current))
            page = notebook.nametowidget(current)
        except (tk.TclError, KeyError):
            break
        notebook = _first_notebook(page)
    return '>'.join(parts)


class WindowHistory:
    """One window's Undo/Redo: a hub, the journal feeding it, and the two buttons."""

    def __init__(self, window: tk.Misc, *,
                 scope: Callable[[], str] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 schedule: Callable[[Callable[[], None]], object] | None = None):
        self.window = window
        self._clock = clock
        self._schedule = schedule or self._schedule_on_window
        self.hub = HistoryHub(scope or (lambda: active_scope(window)))
        self._last_input = -USER_ACTION_WINDOW * 2
        self._pending: list[tuple[str, object, list]] = []
        self._pending_files: list[tuple[str, object]] = []
        self._flush_scheduled = False
        self.hub.delegate(
            DATA_ENTRY_SCOPE,
            undo=self._data_entry_undo, redo=self._data_entry_redo,
            can_undo=lambda: self._data_entry('can_undo'), can_redo=lambda: self._data_entry('can_redo'),
        )

    # ------------------------------------------------------------ wiring
    def start(self) -> 'WindowHistory':
        for sequence in _INPUT_EVENTS:
            self.window.bind_all(sequence, self._mark_input, add='+')
        self.window.bind('<Destroy>', self._on_destroy, add='+')
        row_journal.install(self._submit, gate=self._user_is_acting)
        file_journal.install(self._submit_file, gate=self._user_is_acting)
        return self

    def _on_destroy(self, event) -> None:
        if event.widget is self.window:
            row_journal.uninstall()
            file_journal.uninstall()

    def _schedule_on_window(self, callback: Callable[[], None]) -> object:
        try:
            return self.window.after_idle(callback)
        except tk.TclError:
            callback()
            return None

    def _mark_input(self, _event=None) -> None:
        self._last_input = self._clock()

    def _user_is_acting(self) -> bool:
        return self._clock() - self._last_input < USER_ACTION_WINDOW

    # ------------------------------------------------------ recording
    def _submit(self, db, changes) -> None:
        scope = self.hub.current_scope()
        if not scope or scope == DATA_ENTRY_SCOPE:
            return
        self._pending.append((scope, db, list(changes)))
        if not self._flush_scheduled:
            self._flush_scheduled = True
            self._schedule(self.flush)

    def _submit_file(self, change) -> None:
        scope = self.hub.current_scope()
        if not scope or scope == DATA_ENTRY_SCOPE:
            return
        self._pending_files.append((scope, change))
        if not self._flush_scheduled:
            self._flush_scheduled = True
            self._schedule(self.flush)

    def flush(self) -> None:
        """Merge everything committed this event-loop turn into one step per tab."""
        self._flush_scheduled = False
        pending, self._pending = self._pending, []
        files, self._pending_files = self._pending_files, []
        by_scope: dict[str, list] = {}
        for scope, change in files:
            by_scope.setdefault(scope, []).append(change)
        for scope, changes in by_scope.items():
            for change in file_journal.merge(changes):
                self.hub.record(file_journal.build_action(change), scope)
        groups: dict[tuple[str, int], tuple[str, object, list]] = {}
        for scope, db, changes in pending:
            groups.setdefault((scope, id(db)), (scope, db, []))[2].extend(changes)
        for scope, db, changes in groups.values():
            action = row_journal.build_action(db, changes)
            if action is not None:
                self.hub.record(action, scope)

    # --------------------------------------------------- data entry
    def _data_entry(self, method: str):
        center = getattr(self.window, 'approval_center', None)
        return getattr(center, method)() if center is not None else False

    def _data_entry_undo(self) -> str:
        center = getattr(self.window, 'approval_center', None)
        if center is None or not center.can_undo():
            return DATA_ENTRY_NOTHING_TO_UNDO
        return center.undo_data_entry()

    def _data_entry_redo(self) -> str:
        center = getattr(self.window, 'approval_center', None)
        if center is None or not center.can_redo():
            return DATA_ENTRY_NOTHING_TO_REDO
        return center.redo_data_entry()

    # ------------------------------------------------------- buttons
    def undo(self) -> str:
        return self._step(self.hub.undo)

    def redo(self) -> str:
        return self._step(self.hub.redo)

    def _step(self, action: Callable[[], str]) -> str:
        self.flush()
        message = action()
        if self.hub.changed:
            self._refresh()
        return message

    def _refresh(self) -> None:
        refresh = getattr(self.window, 'refresh_all', None)
        if callable(refresh):
            # The refresh re-derives statuses; none of that is the user's action.
            with row_journal.suspended():
                refresh()


def install(window: tk.Misc) -> WindowHistory:
    """Create (once) and start ``window``'s history."""
    history = getattr(window, '_window_history', None)
    if history is None:
        history = window._window_history = WindowHistory(window).start()
    return history
