"""A loan-installment receipt posted in the group becomes an ordinary Data Entry record, with its receipt attached.

The Stage 9 guided flow took the amount from the caption text alone («مبلغ قسط از پیام تشخیص داده نشد» when a receipt
photo carried only «خروجی / پرداخت قسط اول / وام ۴۱۸۸»), never archived the photo, made no record and paid the instalment
straight away, outside the approval pipeline. Here an instalment message goes through the regular receipt pipeline
(a pending record is made first, the photo is archived and read) and its payload is completed from the caption:
title «خروجی» / «اقساط», the loan named by its number or its bank, the amount read from the receipt (or the
instalment's own amount when the receipt gives none) and one instalment paid now. The person approves it in
«ثبت دیتا» like any record; nothing is paid before that.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

log = logging.getLogger(__name__)

SOURCE = 'TELEGRAM_LOAN_INSTALLMENT_187'
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
_ORDINALS = {
    'اول': 1, 'یکم': 1, 'دوم': 2, 'سوم': 3, 'چهارم': 4, 'پنجم': 5, 'ششم': 6, 'هفتم': 7, 'هشتم': 8, 'نهم': 9,
    'دهم': 10, 'یازدهم': 11, 'دوازدهم': 12,
}
_BANK_WORDS = {'بانک', 'موسسه', 'مؤسسه', 'وام', 'تسهیلات', 'قسط', 'اقساط', 'پرداخت'}


def normalize(text: str) -> str:
    return (str(text or '').translate(_DIGITS).replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ').strip().lower())


def installment_number(text: str) -> int | None:
    """The instalment a caption names: «قسط دوم» or «قسط 3» (None when it names none)."""
    t = normalize(text)
    for word, number in _ORDINALS.items():
        if re.search(rf'قسط\s*{word}\b', t):
            return number
    found = re.search(r'قسط\s*(\d{1,3})', t)
    return int(found.group(1)) if found else None


def match_loan(text: str, loans: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The one loan a caption points at: the loan named by its number («وام ۴۱۸۸»); only when no loan carries that
    name, the one loan whose principal starts with it; else the loan of its bank."""
    t = normalize(text)
    active = [loan for loan in loans if str(loan.get('status') or 'ACTIVE').upper() not in {'CANCELLED', 'CLOSED', 'PAID'}]
    for number in re.findall(r'\d{3,}', t):
        named = [loan for loan in active
                 if normalize(str(loan.get('loan_name') or '')) == number
                 or (str(loan.get('loan_id') or '').lower() and str(loan.get('loan_id')).lower() in t)]
        if len(named) == 1:
            return named[0]
        if named:
            continue
        if len(number) >= 4:
            by_principal = [loan for loan in active if str(int(loan.get('principal_amount') or 0)).startswith(number)]
            if len(by_principal) == 1:
                return by_principal[0]
    by_bank = []
    for loan in active:
        words = [w for w in normalize(str(loan.get('lender_name') or '')).split() if w not in _BANK_WORDS]
        if words and all(w in t for w in words):
            by_bank.append(loan)
    if len(by_bank) == 1:
        return by_bank[0]
    return active[0] if len(active) == 1 else None


def next_open_installment(installments: list[dict[str, Any]]) -> dict[str, Any] | None:
    rows = [row for row in installments
            if str(row.get('status') or '').upper() in {'UPCOMING', 'DUE', 'PARTIALLY_PAID', 'OVERDUE'}]
    return min(rows, key=lambda row: int(row.get('installment_number') or 0)) if rows else None


def enrich(payload: dict[str, Any], text: str, loans: list[dict[str, Any]],
           installments_of: Callable[[str], list[dict[str, Any]]]) -> dict[str, Any]:
    """Complete a payload read from an instalment receipt. Always returns a payload; a loan it cannot name is left
    for the person to pick."""
    out = dict(payload or {})
    out.update(v18_title='خروجی', v18_subtype='اقساط', detected_type='OUTFLOW', source=SOURCE)
    out.setdefault('payment_method', 'BANK_TRANSFER')
    loan = match_loan(text, loans)
    number = installment_number(text)
    notes = [str(out.get('notes') or '').strip()]
    amount = int(out.get('amount') or 0)
    if loan:
        loan_id = str(loan['loan_id'])
        open_row = next_open_installment(installments_of(loan_id))
        paid = int(loan.get('paid_installments') or 0)
        out.update(
            loan_id=loan_id, selected_loan_name=str(loan.get('loan_name') or '').strip() or str(int(loan.get('principal_amount') or 0))[:4] or loan_id,
            loan_bank=loan.get('lender_name') or '', loan_total_amount=int(loan.get('principal_amount') or 0),
            installment_count=int(loan.get('installment_count') or 0), paid_installments_before=paid,
            installments_paid_now=1,
            remaining_installments=max(int(loan.get('installment_count') or 0) - paid - 1, 0),
        )
        if open_row is not None:
            remain = max(0, int(open_row.get('amount') or 0) - int(open_row.get('paid_amount') or 0))
            if amount <= 0:
                amount = remain
                notes.append('مبلغ از رسید خوانده نشد؛ مانده قسط بعدی گذاشته شد')
            if number and number != int(open_row.get('installment_number') or 0):
                notes.append(f"در متن قسط {number} آمده، ولی قسط باز بعدی این وام قسط {int(open_row.get('installment_number') or 0)} است")
    else:
        notes.append('وام این پرداخت از متن مشخص نشد؛ در ثبت دیتا انتخاب کن')
    out['amount'] = amount
    out['notes'] = ' | '.join(note for note in notes if note)
    out['description'] = f"پرداخت قسط وام {out.get('selected_loan_name') or ''}".strip()
    return out


def install(legacy) -> None:
    """Route instalment messages through the regular pipeline and complete their payloads (called by
    telegram_stage18_7 before the legacy bot starts)."""
    original_title = legacy.apply_explicit_note_title
    original_group = legacy.handle_group_message
    original_review = legacy._send_private_review_if_enabled

    def is_installment(text: str) -> bool:
        return legacy._loan_message_kind(text) == 'INSTALLMENT'

    def apply_title(payload, text):
        payload = original_title(payload, text)
        if not is_installment(text):
            return payload
        try:
            return enrich(payload, text, legacy.LOANS.list_loans(), legacy.LOANS.list_installments)
        except Exception:  # noqa: BLE001 - the record is still made; the person completes it
            log.exception('installment caption could not be completed')
            return payload

    async def handle_group_message(update, context):
        message = update.effective_message
        text = (getattr(message, 'caption', None) or getattr(message, 'text', None) or '') if message else ''
        if message is not None and is_installment(text):
            return await legacy._handle_regular_financial_message(update, context)
        return await original_group(update, context)

    async def send_review(message, context, pending_id, payload):
        if str((payload or {}).get('source') or '') != SOURCE:
            return await original_review(message, context, pending_id, payload)
        # Telegram's approve button would post a plain outflow; an instalment is paid only from «ثبت دیتا».
        private_id = await legacy._private_id()
        lines = ['💸 رسید قسط وام در «ثبت دیتا» ثبت شد؛ برای تأیید آنجا بازش کن.',
                 f"وام: {payload.get('selected_loan_name') or '—'}",
                 f"مبلغ: {legacy.fmt_money(payload.get('amount'))}"]
        if payload.get('notes'):
            lines.append(f"توضیح: {payload['notes']}")
        await legacy._safe_send(context.bot, private_id, '\n'.join(lines))

    legacy.apply_explicit_note_title = apply_title
    legacy.handle_group_message = handle_group_message
    legacy._send_private_review_if_enabled = send_review
