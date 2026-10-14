"""The documents of a cheque, from any window of any of its records.

A cheque has an issue record and, once it is resolved, a resolution record. Each brings its own receipts:
the issue's go onto the expense, the document or the cheque its approval made, the resolution's go onto the
cheque. Whichever of the two records is open (or the cheque's row in the tab), the viewer lists them all, side by
side and independent of each other: the count above the preview, the arrows between them.
"""
from __future__ import annotations

import json


def cheque_ids_for(db, pending_id='', row=None) -> list[str]:
    """The live cheques a record or a tab row belongs to, the one its own fields name first."""
    row = dict(row or {})
    found: list[str] = []
    if row.get('cheque_id'):
        found.append(str(row['cheque_id']))
    item = db.get_pending_item(str(pending_id)) if pending_id else None
    if item:
        payload = item.get('payload') or {}
        for key in ('selected_cheque_id187', 'cheque_id'):
            if payload.get(key):
                found.append(str(payload[key]))
        posting = db.get_financial_posting(str(pending_id))
        if posting and posting.get('cheque_id'):
            found.append(str(posting['cheque_id']))
        with db.read() as con:
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='transaction_lifecycle'").fetchone():
                record = con.execute('SELECT effects_json FROM transaction_lifecycle WHERE pending_id=?',
                                     (str(pending_id),)).fetchone()
                for effect in json.loads(record['effects_json'] or '[]') if record else []:
                    if effect.get('table') == 'cheques' and effect.get('key'):
                        found.append(str(effect['key'][0]))
    return [cid for cid in dict.fromkeys(found) if db.get_cheque(cid)]


def cheque_sources(db, pending_id='', row=None):
    """([pending ids], [(entity type, id)]) whose attachments belong with this record's: every record of
    the cheque, issue first, and what each of them made."""
    from cheque_record_edit187 import pending_ids
    pids: list[str] = []
    entities: list[tuple[str, str]] = []
    for cid in cheque_ids_for(db, pending_id, row):
        entities.append(('CHEQUE', cid))
        for pid in pending_ids(db, cid):
            pids.append(str(pid))
            posting = db.get_financial_posting(str(pid))
            if posting:
                for key, kind in (('expense_id', 'EXPENSE'), ('transaction_id', 'TRANSACTION'), ('payment_id', 'PAYMENT')):
                    if posting.get(key):
                        entities.append((kind, str(posting[key])))
            with db.read() as con:
                if con.execute("SELECT 1 FROM sqlite_master WHERE name='financial_documents'").fetchone():
                    for document in con.execute(
                            "SELECT document_id FROM financial_documents WHERE pending_id=? AND status='ACTIVE'", (str(pid),)):
                        entities.append(('DOCUMENT', str(document['document_id'])))
    return pids, entities


def _owned_paths(db, pending_id) -> list[str]:
    """The files one record brought: what is attached to it, to the documents and money rows its approval
    made, and what its resolution moved onto the cheque."""
    item = db.get_pending_item(str(pending_id)) or {}
    payload = item.get('payload') or {}
    paths = [attachment.get('local_path') for attachment in db.list_pending_attachments(str(pending_id))]
    if not payload.get('receipt_image_deleted187'):
        paths.append(payload.get('receipt_image_path'))
    posting = db.get_financial_posting(str(pending_id))
    if posting:
        for key, kind in (('expense_id', 'EXPENSE'), ('transaction_id', 'TRANSACTION'), ('payment_id', 'PAYMENT')):
            if posting.get(key):
                paths += [attachment.get('local_path') for attachment in db.list_entity_attachments(kind, str(posting[key]))]
    with db.read() as con:
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='financial_documents'").fetchone():
            for document in con.execute(
                    "SELECT document_id FROM financial_documents WHERE pending_id=? AND status='ACTIVE'", (str(pending_id),)):
                paths += [attachment.get('local_path')
                          for attachment in db.list_entity_attachments('DOCUMENT', str(document['document_id']))]
        for attachment_id in payload.get('_resolution_attachments187') or []:
            moved = con.execute('SELECT local_path FROM attachments WHERE attachment_id=?', (str(attachment_id),)).fetchone()
            if moved:
                paths.append(moved['local_path'])
    return [str(path) for path in paths if path]


def order_by_record(db, pending_id, row, paths) -> list[str]:
    """The order of a cheque's receipts. A record that is open lists its own first (a resolution record opens on
    the payment slip it was given, the issue on the cheque photo), then the cheque's others; the cheque's own view,
    with no record, lists the issue's first and then each resolution's. Only the order changes; what is listed does not."""
    from cheque_record_edit187 import pending_ids
    own = set(_owned_paths(db, pending_id)) if pending_id else set()
    rank: dict[str, int] = {}
    position = 0
    for cheque_id in cheque_ids_for(db, pending_id, row):
        for record in pending_ids(db, cheque_id):
            for path in _owned_paths(db, record):
                rank.setdefault(path, position)
            position += 1
    index = {path: number for number, path in enumerate(paths)}
    return sorted(paths, key=lambda path: (path not in own, rank.get(path, position), index[path]))
