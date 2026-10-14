"""Projection of legacy and active review rows into the ten visible columns."""
from __future__ import annotations


def map_data_entry_values_187(values, row, *, fa, cell_text, source_layout='legacy'):
    values = list(values or ())
    if source_layout == 'current':
        return tuple(cell_text(value) for value in values)
    row = row or {}
    payload = dict(row.get('payload') or {})
    review = len(values) == 12
    def cell(index, fallback='—'):
        return values[index] if index < len(values) else fallback
    event_date = str(payload.get('event_date_shamsi') or row.get('message_date') or cell(1)).split()[0]
    payer = (payload.get('payer_name') or payload.get('buyer_name') or
             payload.get('partner_name') or payload.get('issuer_name') or '—')
    title = (payload.get('v18_title') or payload.get('title') or
             payload.get('transaction_title') or (cell(2) if review else '—'))
    receiver = (payload.get('receiver_name') or payload.get('recipient_name') or
                payload.get('payee_name') or (cell(6) if review else '—'))
    projected = (
        cell(0, '☐'), fa(event_date), title,
        cell(3 if review else 2), cell(4 if review else 3), cell(5 if review else 4),
        fa(payer), fa(receiver),
        payload.get('construction_stage') or payload.get('main_phase') or
            payload.get('phase_name') or (cell(10) if review else '—'),
        payload.get('subphase') or payload.get('sub_phase') or
            payload.get('construction_substage') or (cell(11) if review else '—'),
    )
    return tuple(cell_text(value) for value in projected)
