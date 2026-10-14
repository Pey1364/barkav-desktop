"""Per-tab Undo/Redo history for the main window.

Pure Python: no Tk and no database. The window keeps one :class:`HistoryHub`;
every tab (or sub-tab) is a *scope* with its own undo and redo stacks, so
pressing Undo in a table reverses that table's own last action and nothing
from another tab.

A scope can also delegate to a history that already exists elsewhere (the Data
Entry tab's in-memory stack, the budget's ``rich_change_history``), so those
keep working unchanged behind the same two toolbar buttons.

Every method that reverses something returns the Persian sentence the window
shows the user, so callers never build messages of their own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

HISTORY_LIMIT = 100

NOTHING_TO_UNDO = 'عملیاتی برای بازگردانی در این تب وجود ندارد.'
NOTHING_TO_REDO = 'عملیاتی برای اجرای دوباره در این تب وجود ندارد.'
NO_HISTORY_FOR_TAB = 'در این صفحه عملیات قابل بازگشتی وجود ندارد.'


class UndoRefused(Exception):
    """The action cannot be reversed safely right now.

    The message is shown to the user as is, so it must be a finished Persian
    sentence that says why (for example that the rows changed since).
    """


@dataclass
class HistoryAction:
    """One user action: how to reverse it and how to apply it again.

    ``undoable=False`` records an action that changed something we cannot
    reverse safely. It stays in the stack so that Undo can say so plainly
    instead of silently reversing an older action out of order.
    """

    label: str
    undo: Callable[[], None]
    redo: Callable[[], None]
    undoable: bool = True
    reason: str = ''


class TabHistory:
    """The undo and redo stacks of one scope."""

    def __init__(self, limit: int = HISTORY_LIMIT):
        self._limit = max(1, int(limit))
        self._undo: list[HistoryAction] = []
        self._redo: list[HistoryAction] = []
        #: True when the last undo()/redo() actually reversed or re-applied something.
        self.changed = False

    def push(self, action: HistoryAction) -> None:
        self._undo.append(action)
        del self._undo[:-self._limit]
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> str:
        self.changed = False
        if not self._undo:
            return NOTHING_TO_UNDO
        action = self._undo.pop()
        if not action.undoable:
            why = f' {action.reason}' if action.reason else ''
            return f'«{action.label}» قابل بازگشت نیست.{why}'
        try:
            action.undo()
        except UndoRefused as refusal:
            return f'«{action.label}» بازگردانی نشد: {refusal} این مورد از سابقه حذف شد.'
        self._redo.append(action)
        self.changed = True
        return f'«{action.label}» بازگردانی شد.'

    def redo(self) -> str:
        self.changed = False
        if not self._redo:
            return NOTHING_TO_REDO
        action = self._redo.pop()
        try:
            action.redo()
        except UndoRefused as refusal:
            return f'«{action.label}» دوباره اجرا نشد: {refusal} این مورد از سابقه حذف شد.'
        self._undo.append(action)
        self.changed = True
        return f'«{action.label}» دوباره اجرا شد.'


@dataclass
class _Delegate:
    undo: Callable[[], str]
    redo: Callable[[], str]
    can_undo: Callable[[], bool]
    can_redo: Callable[[], bool]


class HistoryHub:
    """All scopes of one window.

    ``scope_provider`` returns the scope of the tab the user is looking at
    right now; it is only consulted when a call names no scope.
    """

    def __init__(self, scope_provider: Callable[[], str] | None = None):
        self._provider = scope_provider
        self._histories: dict[str, TabHistory] = {}
        self._delegates: dict[str, _Delegate] = {}
        #: True when the last hub-level undo()/redo() changed stored data through
        #: a history of the hub's own (a delegate refreshes its own screen).
        self.changed = False

    def current_scope(self) -> str:
        if self._provider is None:
            return ''
        try:
            return str(self._provider() or '')
        except Exception:  # a broken tab lookup must never break a button
            return ''

    def delegate(self, scope: str, *, undo: Callable[[], str], redo: Callable[[], str],
                 can_undo: Callable[[], bool], can_redo: Callable[[], bool]) -> None:
        """Let ``scope`` use a history that lives elsewhere."""
        self._delegates[scope] = _Delegate(undo, redo, can_undo, can_redo)

    def has_scope(self, scope: str) -> bool:
        return scope in self._delegates or scope in self._histories

    def history(self, scope: str) -> TabHistory:
        return self._histories.setdefault(scope, TabHistory())

    def record(self, action: HistoryAction, scope: str | None = None) -> None:
        scope = self.current_scope() if scope is None else scope
        if not scope or scope in self._delegates:
            return
        self.history(scope).push(action)

    def undo(self, scope: str | None = None) -> str:
        scope = self.current_scope() if scope is None else scope
        self.changed = False
        delegate = self._delegates.get(scope)
        if delegate is not None:
            return delegate.undo()
        history = self._histories.get(scope)
        if history is None:
            return NOTHING_TO_UNDO if scope else NO_HISTORY_FOR_TAB
        message = history.undo()
        self.changed = history.changed
        return message

    def redo(self, scope: str | None = None) -> str:
        scope = self.current_scope() if scope is None else scope
        self.changed = False
        delegate = self._delegates.get(scope)
        if delegate is not None:
            return delegate.redo()
        history = self._histories.get(scope)
        if history is None:
            return NOTHING_TO_REDO if scope else NO_HISTORY_FOR_TAB
        message = history.redo()
        self.changed = history.changed
        return message

    def can_undo(self, scope: str | None = None) -> bool:
        scope = self.current_scope() if scope is None else scope
        delegate = self._delegates.get(scope)
        if delegate is not None:
            return bool(delegate.can_undo())
        history = self._histories.get(scope)
        return bool(history and history.can_undo())

    def can_redo(self, scope: str | None = None) -> bool:
        scope = self.current_scope() if scope is None else scope
        delegate = self._delegates.get(scope)
        if delegate is not None:
            return bool(delegate.can_redo())
        history = self._histories.get(scope)
        return bool(history and history.can_redo())
