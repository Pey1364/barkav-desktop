from __future__ import annotations

import os
import re
from pathlib import Path
from typing import BinaryIO


def safe_project_key(project_id: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', str(project_id or '').strip())[:80] or 'project'


class ProjectInstanceGuard:
    """OS-backed non-blocking lock that prevents duplicate bot/dashboard runners."""

    def __init__(self, runtime_dir: str | Path, project_id: str):
        self.path = Path(runtime_dir) / f'project_{safe_project_key(project_id)}_18_7_1.lock'
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
