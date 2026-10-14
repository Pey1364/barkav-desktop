"""Read-only access to one project's database for the web UI prototype.

The existing services cannot be pointed at the live database without side
effects: ``FinanceDB.__init__`` runs schema migrations, several services run
their own ``_migrate()`` in the constructor, and ``AttachmentService`` /
``ProjectService`` create folders under their ``base_dir``.  So every load
here copies the project database through SQLite's backup API from a
``mode=ro`` handle into a private temporary folder, builds the services on
that copy with the same folder as ``base_dir``, and deletes the folder
afterwards.  The live file is only ever opened read-only.

Secrets are never read: ``config_loader.load_config`` is deliberately not
used, because it requires the Telegram token and Gemini key.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator


# contractor_store_stage18_7.store_path() puts the contracts file beside the
# project database.  It is read here directly, not through load_contracts():
# that resolves the folder from the process-wide STAGE4_DB_PATH and mkdir()s
# it, which would read the wrong project (or create a folder) from a bridge
# thread.  tests/test_webui_bridge.py pins the file name to store_path()'s.
CONTRACTS_FILE_NAME = 'contractor_contracts_18_7.json'


def read_contracts_beside(db_path: str | Path) -> list[dict]:
    """The project's contractor contracts, read-only; [] like load_contracts()."""
    path = Path(db_path).parent / CONTRACTS_FILE_NAME
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    contracts = data.get('contracts') if isinstance(data, dict) else None
    return list(contracts) if isinstance(contracts, list) else []


class SnapshotError(RuntimeError):
    """A project or its database could not be read. ``code`` is stable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProjectRef:
    project_id: str
    name: str
    db_path: Path


def _registry_file(app_dir: Path) -> Path | None:
    # Same lookup order as project_registry.ProjectRegistry, without its
    # mkdir(): prefer a sibling data/ that owns the registry, else app/data.
    for candidate in (app_dir / 'data' / 'project_registry.json',
                      app_dir.parent / 'data' / 'project_registry.json'):
        if candidate.is_file():
            return candidate
    return None


def resolve_project(app_dir: str | Path, project_id: str | None = None,
                    registry_path: str | Path | None = None) -> ProjectRef:
    """Find a project in the registry without modifying the registry."""
    app_dir = Path(app_dir)
    path = Path(registry_path) if registry_path else _registry_file(app_dir)
    if path is None or not path.is_file():
        raise SnapshotError('PROJECT_REGISTRY_MISSING', 'فهرست پروژه‌ها پیدا نشد.')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise SnapshotError('PROJECT_REGISTRY_UNREADABLE', 'فهرست پروژه‌ها خوانده نشد.') from exc
    projects = [p for p in data.get('projects') or [] if isinstance(p, dict)]
    wanted = project_id or str(data.get('active_project_id') or '')
    chosen = next((p for p in projects if p.get('project_id') == wanted), None)
    if chosen is None and not project_id and projects:
        chosen = projects[0]
    if chosen is None:
        raise SnapshotError('PROJECT_NOT_FOUND', 'پروژهٔ انتخاب‌شده در فهرست نیست.')
    db_path = Path(str(chosen.get('db_path') or ''))
    if not db_path.is_absolute():
        db_path = path.parent / db_path
    return ProjectRef(str(chosen['project_id']), str(chosen.get('name') or ''), db_path)


@dataclass(frozen=True)
class Snapshot:
    db_path: Path       # the private copy
    base_dir: Path      # private folder the services may write into
    taken_at: datetime
    source_modified_at: datetime
    contracts: list        # contractor contracts read beside the source DB


@contextmanager
def read_only_snapshot(source: str | Path) -> Iterator[Snapshot]:
    """Yield a private copy of ``source``; the copy is deleted on exit."""
    source = Path(source)
    if not source.is_file():
        raise SnapshotError('DATABASE_MISSING', 'فایل دیتابیس پروژه پیدا نشد.')
    folder = Path(tempfile.mkdtemp(prefix='barkav_webui_'))
    copy = folder / 'snapshot.sqlite3'
    try:
        try:
            src = sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=15)
            try:
                dst = sqlite3.connect(copy)
                try:
                    src.backup(dst)  # includes committed WAL content
                finally:
                    dst.close()
            finally:
                src.close()
        except sqlite3.Error as exc:
            raise SnapshotError('DATABASE_UNREADABLE', 'خواندن دیتابیس پروژه ممکن نشد.') from exc
        yield Snapshot(
            db_path=copy, base_dir=folder, taken_at=datetime.now(),
            source_modified_at=datetime.fromtimestamp(source.stat().st_mtime),
            contracts=read_contracts_beside(source),
        )
    finally:
        shutil.rmtree(folder, ignore_errors=True)
