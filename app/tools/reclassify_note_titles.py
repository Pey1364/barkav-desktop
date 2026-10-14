"""File review items that are still waiting under the category their title names.

Messages received before the title rule existed («گزارش روزانه ۵ مهر ۴۰۵:»,
«داکیومنت-تقویم:», ...) sit in the data-entry tab as «نامشخص» or under the
wrong subtype. This applies the same rule the bot now uses
(``ai_parser.apply_explicit_note_title``) to those rows.

Only rows still awaiting review (PENDING_REVIEW / NEEDS_REVIEW) are touched;
approved and rejected rows are left exactly as they are. Close BARKAV first.

    python tools/reclassify_note_titles.py            # show what would change
    python tools/reclassify_note_titles.py --apply    # back up, then change
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from ai_parser import apply_explicit_note_title  # noqa: E402

OPEN_STATUSES = ('PENDING_REVIEW', 'NEEDS_REVIEW')


def _project_db(project_id: str | None) -> Path:
    registry = json.loads((APP / 'data' / 'project_registry.json').read_text(encoding='utf-8'))
    projects = registry.get('projects') or []
    wanted = project_id or registry.get('active_project_id') or (projects[0]['project_id'] if projects else '')
    for project in projects:
        if project.get('project_id') == wanted:
            return Path(project['db_path'])
    raise SystemExit(f'Project {wanted!r} is not in data/project_registry.json')


def planned_changes(con: sqlite3.Connection) -> list[tuple[sqlite3.Row, dict, str]]:
    """(row, new payload, new status) for every open row its title would move."""
    rows = con.execute(
        "SELECT p.pending_id, p.telegram_chat_id AS chat_id, p.telegram_message_id AS message_id, "
        "p.detected_type, p.status, p.confidence, p.payload_json, t.raw_text "
        "FROM pending_items p LEFT JOIN telegram_messages t "
        "ON t.chat_id = p.telegram_chat_id AND t.message_id = p.telegram_message_id "
        f"WHERE p.status IN ({','.join('?' * len(OPEN_STATUSES))})", OPEN_STATUSES).fetchall()
    out = []
    for row in rows:
        payload = json.loads(row['payload_json'] or '{}')
        new = apply_explicit_note_title({**payload, 'detected_type': row['detected_type']}, row['raw_text'] or '')
        if new.get('note_type_source') != 'TITLE':
            continue
        if (new['detected_type'], new.get('note_type')) == (row['detected_type'], payload.get('note_type')):
            continue
        status = row['status']
        # The bot only holds UNKNOWN rows in NEEDS_REVIEW; a titled row is known.
        if row['detected_type'] == 'UNKNOWN' and status == 'NEEDS_REVIEW':
            status = 'PENDING_REVIEW'
        out.append((row, new, status))
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--project', help='project id (default: the active or first project)')
    parser.add_argument('--apply', action='store_true', help='back up the database, then write the changes')
    args = parser.parse_args()

    db_path = _project_db(args.project)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    changes = planned_changes(con)
    for row, new, status in changes:
        text = (row['raw_text'] or '').replace('\n', ' // ')[:60]
        print(f"{row['status']} | {row['detected_type']} -> {new['detected_type']} "
              f"{new.get('note_type')} | {text}")
    print(f'{len(changes)} row(s) to update in {db_path}')
    if not args.apply or not changes:
        if changes:
            print('Nothing written. Run again with --apply to update them.')
        return

    backups = APP / 'data' / 'backups'
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / f"before_note_titles_{datetime.now():%Y%m%d_%H%M%S}{db_path.suffix}"
    target = sqlite3.connect(backup)
    con.backup(target)
    target.close()
    print(f'Backup: {backup}')

    now = datetime.now().replace(microsecond=0).isoformat()
    with con:
        for row, new, status in changes:
            con.execute(
                'UPDATE pending_items SET payload_json=?, detected_type=?, confidence=?, status=?, updated_at=? '
                'WHERE pending_id=?',
                (json.dumps(new, ensure_ascii=False), new['detected_type'],
                 float(new.get('confidence') or row['confidence'] or 0), status, now, row['pending_id']))
            con.execute('UPDATE telegram_messages SET state=?, updated_at=? WHERE chat_id=? AND message_id=?',
                        (status, now, row['chat_id'], row['message_id']))
    con.close()
    print(f'Updated {len(changes)} row(s).')


if __name__ == '__main__':
    main()
