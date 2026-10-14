"""Mixed land purchase payments through the existing audited FinanceDB APIs."""
from __future__ import annotations

import json
from finance_db import _now
from data_entry_rules187 import LAND_TITLE, LAND_PARTS


def debt_signature(payload, parse_amount):
    """Approval applies only to the exact amounts displayed in the warning."""
    return [str(payload.get('payment_state') or 'UNPAID'),
            parse_amount(payload.get('total_debt') or 0),
            *[parse_amount(payload.get(key) or 0) for key in LAND_PARTS]]


def debt_warning(payload, parse_amount):
    state, debt, *values = debt_signature(payload, parse_amount)
    paid = sum(values)
    if debt <= 0 or paid > debt:
        return 'کل بدهی باید مثبت و کمتر از مجموع پرداخت‌ها نباشد. برای اصلاح مبلغ برگردید یا با همین مقادیر تراکنش را ثبت کنید.'
    if state == 'PAID' and paid != debt:
        return 'در حالت تسویه، مجموع پرداخت‌ها با کل بدهی برابر نیست. برای اصلاح مبلغ برگردید یا تراکنش را ثبت کنید.'
    return ''


def approve(db, pending_id, payload, *, parse_amount, normalize_date, to_gregorian):
    """Called inside TransactionLifecycle.run: every component rolls back together."""
    item = db.get_pending_item(pending_id)
    if not item:
        raise KeyError(pending_id)
    values = [parse_amount(payload.get(key) or 0) for key in LAND_PARTS]
    cash, cheque, barter = values
    if any(value < 0 for value in values):
        raise ValueError('مبالغ نقدی، چک و معاوضه نمی‌توانند منفی باشند.')
    total_paid = sum(values)
    price = parse_amount(payload.get('total_debt') or 0) if payload.get('_debt_source_pending_id187') else parse_amount(payload.get('total_debt') or total_paid)
    # Older imports can omit debt entirely; their existing amount fallback is
    # retained. Explicitly acknowledged warnings are saved with the payload.
    checked = dict(payload, total_debt=price)
    warning = debt_warning(checked, parse_amount)
    override = payload.get('land_debt_override187') == debt_signature(payload, parse_amount)
    if warning and not override:
        raise ValueError(warning)
    if override and price <= 0:
        price = total_paid
    state = str(payload.get('payment_state') or 'UNPAID')
    if state == 'UNPAID' and (cash or barter):
        raise ValueError('برای ثبت مبلغ نقدی یا معاوضه، وضعیت پرداخت را تسویه یا علی‌الحساب انتخاب کنید.')
    shamsi = normalize_date(str(payload.get('event_date_shamsi') or ''))
    if not shamsi:
        raise ValueError('تاریخ خرید زمین را وارد کنید.')
    event_date = to_gregorian(shamsi)
    due = normalize_date(str(payload.get('due_date_shamsi') or '')) if cheque else ''
    if cheque and not due:
        raise ValueError('برای مبلغ چک، تاریخ سررسید را وارد کنید.')
    description = str(payload.get('description') or '').strip()
    barter_description = str(payload.get('land_barter_description') or '').strip()
    if barter and not barter_description:
        raise ValueError('شرح مورد معاوضه را وارد کنید.')
    method = {'CASH_POS': 'CASH', 'POS': 'CARD', 'CARD_TO_CARD': 'BANK_TRANSFER',
              'TRANSFER': 'BANK_TRANSFER'}.get(payload.get('payment_method'), payload.get('payment_method'))
    if cash and method not in {'CASH', 'CARD', 'BANK_TRANSFER', 'OTHER'}:
        raise ValueError('روش پرداخت بخش نقدی را انتخاب کنید.')
    source = 'GUI_187_LAND'
    common = dict(source=source, actor_id='GUI')
    tx = cid = None
    # A later advance settles the same land obligation instead of accruing its
    # outstanding balance as a second acquisition cost.
    previous_id = payload.get('_debt_source_pending_id187')
    previous = db.get_pending_item(str(previous_id)) if previous_id else None
    expense_id = (previous.get('payload') or {}).get('land_expense_id187') if previous else None
    if expense_id:
        with db.read() as con:
            expense = con.execute('SELECT status,deleted_at,construction_stage FROM expenses WHERE expense_id=?',
                                  (expense_id,)).fetchone()
        if not expense or expense['deleted_at'] or expense['status'] == 'CANCELLED' or expense['construction_stage'] != LAND_TITLE:
            raise ValueError('تعهد قبلی خرید زمین فعال نیست؛ ثبت انجام نشد.')
    else:
        expense_id = db.create_expense(event_date=event_date, shamsi_date=shamsi,
            final_amount=price, invoice_amount=price, description=description,
            vendor_name=payload.get('receiver_name'), category='LAND_PURCHASE',
            construction_stage=LAND_TITLE, manager_fee_eligible=False,
            plan_ref=str(payload.get('plan_ref') or ''), **common)
    if cash:
        tx = db.post_transaction(event_date=event_date, shamsi_date=shamsi,
            direction='OUT', amount=cash, category='LAND_PURCHASE_PAYMENT',
            payer_name=payload.get('payer_name'), receiver_name=payload.get('receiver_name'),
            description=description, source_type=source, expense_id=expense_id,
            telegram_chat_id=item.get('telegram_chat_id'), telegram_message_id=item.get('telegram_message_id'),
            actor_id='GUI')
        db.add_payment(expense_id=expense_id, payment_date=event_date, payment_date_shamsi=shamsi,
            amount=cash, method=method, transaction_id=tx, description=description, **common)
    if cheque:
        cid = db.create_cheque(amount=cheque, issue_date=event_date, issue_date_shamsi=shamsi,
            due_date=to_gregorian(due), due_date_shamsi=due, expense_id=expense_id,
            issuer_name=payload.get('issuer_name'), issuer_bank=payload.get('issuer_bank'),
            cheque_serial=payload.get('cheque_serial'), cheque_type=payload.get('cheque_type') or 'PHYSICAL',
            receiver_name=payload.get('receiver_name'), description=description, **common)
        db.add_payment(expense_id=expense_id, payment_date=event_date, payment_date_shamsi=shamsi,
            amount=cheque, method='CHEQUE', cheque_id=cid, status='PENDING', description=description, **common)
    if barter:
        db.add_payment(expense_id=expense_id, payment_date=event_date, payment_date_shamsi=shamsi,
            amount=barter, method='OTHER', description='معاوضه: ' + barter_description, **common)
    saved = dict(payload, land_expense_id187=expense_id, amount=total_paid, paid_amount=total_paid,
                 total_debt=price, remaining_debt=max(0, price-total_paid), manager_fee_eligible=False)
    # A conversion from an ordinary posting retains its original posting id
    # and audit history, now linked to this replacement land obligation.
    with db.tx() as con:
        old = con.execute('SELECT * FROM financial_postings WHERE pending_id=?', (pending_id,)).fetchone()
        if old:
            con.execute("UPDATE financial_postings SET posting_type='EXPENSE',primary_entity_type='expense',"
                "primary_entity_id=?,expense_id=?,transaction_id=?,cheque_id=?,payment_id=NULL,"
                "plan_json=?,status='ACTIVE',deleted_at=NULL,updated_at=? WHERE pending_id=?",
                (expense_id, expense_id, tx, cid, json.dumps(saved, ensure_ascii=False), _now(), pending_id))
            updated = dict(con.execute('SELECT * FROM financial_postings WHERE pending_id=?', (pending_id,)).fetchone())
            db._audit(con, 'financial_posting', old['posting_id'], 'REVISE', source,
                      before=dict(old), after=updated, actor_id='GUI')
            db._enqueue_sync(con, 'financial_posting', old['posting_id'], 'UPDATE', updated)
    db.update_pending(pending_id, payload=saved, detected_type='EXPENSE', status='APPROVED')
    db.update_telegram_message(chat_id=item['telegram_chat_id'], message_id=item['telegram_message_id'],
        state='APPROVED', linked_entity_type='EXPENSE', linked_entity_id=expense_id)
    db.relink_pending_attachments(pending_id, entity_type='EXPENSE', entity_id=expense_id)
    db.enqueue_integration_event('GUI_APPROVED', pending_id=pending_id,
        payload={'posting_type': 'LAND_PURCHASE', 'actor_id': 'GUI'})
    return 'خرید زمین با پرداخت نقدی، چک و معاوضه ثبت شد.'
