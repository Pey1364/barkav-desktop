"""Check a project database against the red line: no financial row without a Data Entry record.

    python tools/audit_ledger_ownership.py                      # read-only, on a copy of the project database
    python tools/audit_ledger_ownership.py --db path\\to\\project.brk
    python tools/audit_ledger_ownership.py --remove-leftovers --apply

It lists (ids only, never names or amounts)
  * orphans:   live rows that no approved record owns  (the red line itself; nothing here deletes them)
  * leftovers: cheque rows an approval took back and that no record refers to any more; they show in no tab
               and nothing can bring them back. --remove-leftovers --apply deletes exactly these, after a
               verified backup next to the database, in one transaction. Close BARKAV first.

The exit code is 1 when there is an orphan, so the check can run in a script.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from finance_db import FinanceDB  # noqa: E402
from record_ownership187 import leftover_cheques, orphan_rows, remove_leftover_cheques  # noqa: E402


def registry_database(project_id: str | None, registry_file: Path | None = None) -> Path:
    registry = json.loads((registry_file or APP / 'data' / 'project_registry.json').read_text(encoding='utf-8'))
    projects = registry.get('projects') if isinstance(registry, dict) else registry
    if isinstance(projects, dict):
        projects = list(projects.values())
    for project in projects:
        if project_id is None or str(project.get('project_id') or project.get('id')) == project_id:
            return Path(project['db_path'])
    raise SystemExit('project not found in the registry')


def read_only_copy(path: Path) -> Path:
    target = Path(tempfile.gettempdir()) / f'ownership-audit-{os.getpid()}.sqlite3'
    with closing(sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)) as source, \
            closing(sqlite3.connect(target)) as destination:
        source.backup(destination)
    return target


def backup(path: Path) -> Path:
    folder = path.parent / '.barkav-migration-backups'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'{path.name}.{datetime.now():%Y%m%d-%H%M%S}.pre-ownership-repair.sqlite3'
    with closing(sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)) as source, \
            closing(sqlite3.connect(target)) as destination:
        source.backup(destination)
        if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SystemExit('the backup is not sound; nothing was changed')
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--db', type=Path, help='project database (default: the registry\'s first project)')
    parser.add_argument('--project', help='project id in the registry')
    parser.add_argument('--registry', type=Path, help='project_registry.json (default: app/data next to this tool)')
    parser.add_argument('--remove-leftovers', action='store_true')
    parser.add_argument('--apply', action='store_true', help='really change the database (with --remove-leftovers)')
    args = parser.parse_args(argv)
    path = args.db or registry_database(args.project, args.registry)
    live = bool(args.remove_leftovers and args.apply)
    work = path if live else read_only_copy(path)
    if live:
        print('backup:', backup(path))
    try:
        db = FinanceDB(work)
        orphans = orphan_rows(db)
        leftovers = leftover_cheques(db)
        print(f'orphans: {len(orphans)}')
        for row in orphans:
            print('  ', row['table'], row['key'], row['status'])
        print(f'leftover cheques: {len(leftovers)}')
        for row in leftovers:
            print('  ', row['cheque_id'], row['status'], row['created_at'])
        if live and leftovers:
            removed = remove_leftover_cheques(db, [row['cheque_id'] for row in leftovers])
            print('removed:', ', '.join(removed) or '-')
        elif args.remove_leftovers and not args.apply:
            print('dry run: nothing was changed (add --apply)')
        return 1 if orphans else 0
    finally:
        if not live:
            for suffix in ('', '-wal', '-shm'):
                try:
                    os.remove(str(work) + suffix)
                except OSError:
                    pass


if __name__ == '__main__':
    raise SystemExit(main())
