"""Undo and redo for the contractor JSON stores.

Contractor contracts, statements and the archive live in three JSON files, not
in SQLite. Each save rewrites a whole file, so what an action did is exactly
the file's text before and after. Undo writes the earlier text back, redo the
later text, and either is refused, with a Persian reason, when the file no
longer holds what the action left (someone changed it since).

Recording follows the same rules as ``row_journal``: only on the main thread,
only while the window says the user is acting, and never while suspended.
The archive's silent refresh from other sources is not a user action and is
skipped.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import row_journal
from action_history import HistoryAction, UndoRefused

log = logging.getLogger(__name__)

#: (save function, path function, what the file holds) in contractor_store_stage18_7.
STORES = (
    ('save_contracts', 'store_path', 'قرارداد پیمانکار'),
    ('save_statements', 'statements_path', 'صورت‌وضعیت'),
    ('save_profiles', 'archive_path', 'پروندهٔ آرشیو پیمانکار'),
)
_SILENT_CALLERS = frozenset({'sync_archive_from_sources'})
_STATE = SimpleNamespace(sink=None, gate=lambda: True, originals={})


@dataclass(frozen=True)
class FileChange:
    """One file's text before and after a save (``before`` is None if it did not exist)."""

    path: Path
    before: str | None
    after: str | None
    noun: str


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return None


def _write(path: Path, text: str) -> None:
    temporary = path.with_suffix('.undo.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def _count(text: str | None) -> int:
    try:
        data = json.loads(text or '')
    except ValueError:
        return 0
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return len(value)
    return len(data) if isinstance(data, list) else 0


def _called_from(names: frozenset[str]) -> bool:
    frame = sys._getframe(2)
    for _depth in range(12):
        if frame is None:
            return False
        if frame.f_code.co_name in names:
            return True
        frame = frame.f_back
    return False


def _watching() -> bool:
    if _STATE.sink is None or getattr(row_journal._LOCAL, 'suspended', False):
        return False
    if threading.current_thread() is not threading.main_thread():
        return False
    try:
        return bool(_STATE.gate())
    except Exception:
        return False


def _wrap(store, save_name: str, path_name: str, noun: str) -> Callable[[list], None]:
    original = _STATE.originals[save_name]

    def save(items: list[Any]) -> None:
        if not _watching() or _called_from(_SILENT_CALLERS):
            return original(items)
        path = getattr(store, path_name)()
        before = _read(path)
        original(items)
        after = _read(path)
        if before != after:
            try:
                _STATE.sink(FileChange(path, before, after, noun))
            except Exception:
                log.exception('File journal sink failed')

    save.__wrapped__ = original
    return save


def install(sink: Callable[[FileChange], None], gate: Callable[[], bool] | None = None) -> None:
    """Start recording the contractor stores; ``sink`` receives each changed save."""
    try:
        import contractor_store_stage18_7 as store
    except ImportError:
        log.exception('Contractor store not importable; its files will not be undoable')
        return
    uninstall()
    _STATE.sink = sink
    _STATE.gate = gate or (lambda: True)
    for save_name, path_name, noun in STORES:
        _STATE.originals[save_name] = getattr(store, save_name)
        setattr(store, save_name, _wrap(store, save_name, path_name, noun))


def uninstall() -> None:
    if _STATE.originals:
        import contractor_store_stage18_7 as store

        for save_name, original in _STATE.originals.items():
            setattr(store, save_name, original)
    _STATE.originals = {}
    _STATE.sink = None
    _STATE.gate = lambda: True


def merge(changes: list[FileChange]) -> list[FileChange]:
    """Several saves of one file in a turn are one change: first ``before``, last ``after``."""
    merged: dict[Path, FileChange] = {}
    for change in changes:
        first = merged.get(change.path)
        merged[change.path] = change if first is None else FileChange(
            change.path, first.before, change.after, change.noun)
    return [change for change in merged.values() if change.before != change.after]


def _verb(change: FileChange) -> str:
    before, after = _count(change.before), _count(change.after)
    if after < before:
        return 'حذف'
    if after > before:
        return 'افزودن'
    return 'ویرایش'


def _restore(change: FileChange, expect: str | None, target: str | None) -> None:
    if _read(change.path) != expect:
        raise UndoRefused('فایل پس از این عملیات دوباره تغییر کرده است.')
    _write(change.path, target)


def build_action(change: FileChange) -> HistoryAction:
    label = f'{_verb(change)} {change.noun}'
    if change.before is None or change.after is None:
        return HistoryAction(label, lambda: None, lambda: None, undoable=False,
                             reason='فایل داده برای اولین بار ساخته شده است.')
    return HistoryAction(
        label,
        lambda: _restore(change, change.after, change.before),
        lambda: _restore(change, change.before, change.after),
    )
