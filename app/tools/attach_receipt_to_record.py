"""Attach a receipt file that is already in the project's receipt archive to a Data Entry record.

    python tools/attach_receipt_to_record.py --record PEN-... --file path\\to\\receipt.jpg            # shows what it would do
    python tools/attach_receipt_to_record.py --record PEN-... --file path\\to\\receipt.jpg --apply    # does it

The record keeps the file as one of its own receipts, which every window of the record (and of the cheque it
belongs to) lists; on the record's next approval the receipt moves onto what the record made, as for any receipt
a person adds in the record window. Nothing else changes: the file is not copied, moved or deleted, and no
other row is touched. --apply first makes a verified backup next to the database, in one transaction after it;
close BARKAV first. Attaching the same file twice does nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from contextlib import closing
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

MIME = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.pdf': 'application/pdf'}
OPEN_STATES = ('APPROVED', 'EDIT_PENDING', 'PENDING_REVIEW', 'NEEDS_REVIEW')


def registry_database(project_id: str | None, registry_file: Path | None = None) -> Path:
    registry = json.loads((registry_file or APP / 'data' / 'project_registry.json').read_text(encoding='utf-8'))
    projects = registry.get('projects') if isinstance(registry, dict) else registry
    if isinstance(projects, dict):
        projects = list(projects.values())
    for project in projects:
        if project_id is None or str(project.get('project_id') or project.get('id')) == project_id:
            return Path(project['db_path'])
    raise SystemExit('project not found in the registry')


def backup(path: Path) -> Path:
    folder = path.parent / '.barkav-migration-backups'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'{path.name}.{datetime.now():%Y%m%d-%H%M%S}.pre-receipt-attach.sqlite3'
    with closing(sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)) as source, \
            closing(sqlite3.connect(target)) as destination:
        source.backup(destination)
        if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SystemExit('the backup is not sound; nothing was changed')
    return target


def plan(path: Path, record: str, file: Path) -> dict:
    """What attaching would do, read from the database; raises SystemExit when it should not be done."""
    if not file.is_file():
        raise SystemExit(f'the file is not there: {file}')
    with closing(sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        item = con.execute('SELECT status,payload_json FROM pending_items WHERE pending_id=?', (record,)).fetchone()
        if item is None:
            raise SystemExit(f'no such record: {record}')
        if item['status'] not in OPEN_STATES:
            raise SystemExit(f"the record is {item['status']}: a rejected record keeps no receipts")
        try:
            payload = json.loads(item['payload_json'] or '{}')
        except (TypeError, ValueError):
            payload = {}
        cheque = str(payload.get('selected_cheque_id187') or payload.get('cheque_id') or '')
        already = con.execute(
            "SELECT attachment_id,entity_type,entity_id FROM attachments WHERE local_path=? AND "
            "((entity_type='PENDING' AND entity_id=?) OR (entity_type='CHEQUE' AND entity_id=? AND ?<>''))",
            (str(file), record, cheque, cheque)).fetchall()
    return {'status': item['status'], 'cheque': cheque, 'already': [tuple(row) for row in already]}


def attach(path: Path, record: str, file: Path) -> str:
    attachment_id = 'ATT-' + uuid.uuid4().hex[:12].upper()
    with closing(sqlite3.connect(path, timeout=15)) as con:
        con.execute('PRAGMA busy_timeout=15000')
        con.execute(
            'INSERT INTO attachments(attachment_id,entity_type,entity_id,document_type,local_path,mime_type,created_at) '
            'VALUES(?,?,?,?,?,?,?)',
            (attachment_id, 'PENDING', record, 'RECEIPT', str(file), MIME.get(file.suffix.lower(), 'application/octet-stream'),
             datetime.now().isoformat(timespec='seconds')))
        con.commit()
    return attachment_id


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--record', required=True, help='the Data Entry record, PEN-...')
    parser.add_argument('--file', required=True, type=Path, help='a receipt file, normally inside the receipt archive')
    parser.add_argument('--db', type=Path, help="project database (default: the registry's first project)")
    parser.add_argument('--project', help='project id in the registry')
    parser.add_argument('--registry', type=Path, help='project_registry.json (default: app/data next to this tool)')
    parser.add_argument('--apply', action='store_true', help='really attach it (a backup comes first)')
    args = parser.parse_args(argv)
    path = args.db or registry_database(args.project, args.registry)
    file = args.file.resolve()
    state = plan(path, args.record, file)
    print(f"record {args.record}: {state['status']}" + (f", cheque {state['cheque']}" if state['cheque'] else ''))
    print(f'file: {file.name}')
    if state['already']:
        print('already attached, nothing to do:', ', '.join(f'{kind} {owner}' for _id, kind, owner in state['already']))
        return 0
    if not args.apply:
        print('dry run: nothing was changed (add --apply, with BARKAV closed)')
        return 0
    print('backup:', backup(path).name)
    print('attached:', attach(path, args.record, file))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
