"""Stable Data Entry ordering and debt carry-forward, without schema changes."""
from __future__ import annotations

import json
import re
import unicodedata

ORDER_SETTING = 'data_entry_row_order187'
SORT_SETTING = 'data_entry_sort187'
LAND_TITLE = 'خرید زمین'
LAND_MIXED = 'نقدی، چک، معاوضه'
LAND_PARTS = ('land_cash_amount', 'land_cheque_amount', 'land_barter_amount')
LAND_MODE_KEY = 'land_payment_mode187'
LAND_MODES = ('نقدی', 'چکی', 'معاوضه', 'همه موارد')


def land_payment_mode(payload):
    value = str(payload.get(LAND_MODE_KEY) or payload.get('v18_subtype')
                or payload.get('transaction_subtype') or '')
    return {'چک': 'چکی', LAND_MIXED: 'همه موارد'}.get(value,
        value if value in LAND_MODES else 'همه موارد')


def land_payment_subtype(payload):
    """Compatibility vocabulary for the existing payment-component renderer."""
    mode = land_payment_mode(payload)
    return {'چکی': 'چک', 'همه موارد': LAND_MIXED}.get(mode, mode)


def normalize_land_record(payload):
    result = dict(payload)
    result.update(v18_title=LAND_TITLE, v18_subtype=LAND_TITLE,
                  transaction_title=LAND_TITLE, transaction_subtype=LAND_TITLE,
                  construction_stage=LAND_TITLE, main_phase=LAND_TITLE,
                  detected_type='EXPENSE', manager_fee_eligible=False,
                  **{LAND_MODE_KEY: land_payment_mode(payload)})
    return result


def normalize_land_parts(payload, parse_amount):
    result = normalize_land_record(payload)
    subtype = land_payment_subtype(result)
    active = set(LAND_PARTS) if subtype == LAND_MIXED else {
        {'نقدی': LAND_PARTS[0], 'چک': LAND_PARTS[1], 'معاوضه': LAND_PARTS[2]}[subtype]}
    if not any(key in payload for key in LAND_PARTS):
        first = next(key for key in LAND_PARTS if key in active)
        result[first] = parse_amount(payload.get('amount') or payload.get('paid_amount') or 0)
    if subtype == 'نقدی':
        result[LAND_PARTS[0]] = parse_amount(payload.get('amount') if payload.get('amount') is not None
                                          else payload.get(LAND_PARTS[0]) or 0)
        result['land_barter_description'] = ''
    for key in LAND_PARTS:
        result[key] = parse_amount(result.get(key) or 0) if key in active else 0
    result['amount'] = result['paid_amount'] = sum(result[key] for key in LAND_PARTS)
    return result


def row_order(db):
    stored = json.loads(db.get_setting(ORDER_SETTING) or '[]')
    with db.read() as con:
        registered = [str(row[0]) for row in con.execute(
            'SELECT pending_id FROM pending_items ORDER BY rowid')]
    present = set(registered)
    ordered = list(dict.fromkeys(str(pid) for pid in stored if str(pid) in present))
    known = set(ordered)
    ordered.extend(pid for pid in registered if pid not in known)
    return ordered


def insert_after(db, pending_ids, target_id=None):
    ids = list(dict.fromkeys(str(pid) for pid in pending_ids))
    wanted = set(ids)
    ordered = [pid for pid in row_order(db) if pid not in wanted]
    index = ordered.index(str(target_id)) + 1 if str(target_id) in ordered else len(ordered)
    ordered[index:index] = ids
    db.set_setting(ORDER_SETTING, json.dumps(ordered))


def purpose_key(value):
    value = unicodedata.normalize('NFKC', str(value or '')).translate(
        str.maketrans('يك۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', 'یک01234567890123456789'))
    return re.sub(r'\s+', ' ', value.replace('\u200c', ' ')).strip().casefold()


def previous_debt(db, pending_id, payload, date_key, title_type):
    """Nearest earlier approved event with the same title and payment purpose."""
    purpose = purpose_key(payload.get('payment_purpose') or payload.get('description'))
    if not purpose:
        return None
    title = title_type(payload)[0]
    with db.read() as con:
        candidates = [dict(row) for row in con.execute(
            'SELECT pending_id,payload_json,status,created_at,rowid AS position '
            'FROM pending_items ORDER BY rowid')]
    positions = {pid: index for index, pid in enumerate(row_order(db))}
    current_date = date_key({'payload': payload})
    current = (current_date, positions.get(str(pending_id), float('inf')))
    matches = []
    for row in candidates:
        if str(row['pending_id']) == str(pending_id) or row['status'] != 'APPROVED':
            continue
        previous = json.loads(row['payload_json'] or '{}')
        key = (date_key({'payload': previous}), positions[str(row['pending_id'])])
        if key >= current or title_type(previous)[0] != title:
            continue
        if purpose_key(previous.get('payment_purpose') or previous.get('description')) != purpose:
            continue
        # An explicitly saved zero balance is a real balance, not a missing one.
        if previous.get('remaining_debt') is not None:
            matches.append((key, str(row['pending_id']), previous))
    return max(matches, key=lambda match: match[0]) if matches else None
