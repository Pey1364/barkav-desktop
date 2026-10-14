from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import BinaryIO


def safe_project_key(project_id: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', str(project_id or '').strip())[:80] or 'project'


class ProjectInstanceGuard:
    """OS-backed non-blocking lock that prevents duplicate bot/dashboard runners."""

    def __init__(self, runtime_dir: str | Path, project_id: str):
        self.path = Path(runtime_dir) / f'project_{safe_project_key(project_id)}_18_5.lock'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle: BinaryIO | None = None

    def acquire(self) -> bool:
        handle = self.path.open('a+b')
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()).encode('ascii'))
            handle.flush()
            self.handle = handle
            return True
        except (OSError, BlockingIOError):
            handle.close()
            return False

    def owner_pid(self) -> int | None:
        """Return the PID recorded by the process holding this project lock."""
        try:
            value = self.path.read_text(encoding='ascii').strip()
            pid = int(value)
            return pid if pid > 0 else None
        except (OSError, ValueError, UnicodeError):
            return None

    def release(self) -> None:
        handle = self.handle
        self.handle = None
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            handle.close()

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError('این پروژه هم‌اکنون در یک پنجره دیگر باز است.')
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.release()


def bring_process_window_to_front(pid: int | None, *, retries: int = 3,
                                  delay_ms: int = 180) -> bool:
    """Restore and focus the visible top-level window owned by ``pid``.

    Windows prevents an arbitrary background process from stealing focus in
    some cases, so this is deliberately retried after the project runner has
    created its Tk window.  The non-Windows fallback is harmless and keeps the
    helper usable by source-level tests and development environments.
    """
    try:
        pid = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if not sys.platform.startswith('win'):
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_SHOWWINDOW = 0x0040
        found = {'hwnd': 0}
        enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @enum_proc_type
        def enum_proc(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            window_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if int(window_pid.value) == pid:
                found['hwnd'] = hwnd
                return False
            return True

        for attempt in range(max(1, retries)):
            found['hwnd'] = 0
            user32.EnumWindows(enum_proc, 0)
            hwnd = found['hwnd']
            if hwnd:
                user32.ShowWindow(hwnd, SW_RESTORE)
                # Briefly mark it topmost so Windows accepts the foreground
                # request even when the launcher itself is behind another app.
                # The second call immediately restores normal z-order.
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                    SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                                    SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
                user32.SetActiveWindow(hwnd)
                return True
            if attempt + 1 < max(1, retries):
                time.sleep(max(0, delay_ms) / 1000.0)
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    return False
