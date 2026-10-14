from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


from finance_db import FinanceDB


@dataclass(frozen=True)
class PostingResult:
    pending_id: str
    posting_id: str
    posting_type: str
    primary_entity_type: Optional[str]
    primary_entity_id: Optional[str]
    expense_id: Optional[str]
    transaction_id: Optional[str]
    payment_id: Optional[str]
    cheque_id: Optional[str]


def _positive_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _normalize_shamsi(value: str | None) -> Optional[str]:
    if not value:
        return None
    raw = str(value).strip().replace("-", "/")
    raw = raw.split()[0]
    parts = raw.split("/")
    if len(parts) != 3:
        return None
    try:
        y, m, d = [int(x) for x in parts]
        if y < 1200 or y > 1700 or m < 1 or m > 12 or d < 1:
            return None
        max_day = 31 if m <= 6 else (30 if m <= 11 else 30)
        if d > max_day:
            return None
        return f"{y:04d}/{m:02d}/{d:02d}"
    except Exception:
        return None


def _jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    # Integer conversion derived from the standard 2820-year Jalali cycle
    # algorithm. Kept local so the posting/test core does not depend on a
    # third-party date package.
    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186

    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)
    month_days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    for md in month_days:
        if gd <= md:
            break
        gd -= md
        gm += 1
    return gy, gm, gd


def _shamsi_to_gregorian(shamsi_date: str | None) -> Optional[str]:
    normalized = _normalize_shamsi(shamsi_date)
    if not normalized:
        return None
    y, m, d = [int(x) for x in normalized.split("/")]
    try:
        gy, gm, gd = _jalali_to_gregorian(y, m, d)
        return f"{gy:04d}-{gm:02d}-{gd:02d}"
    except Exception:
        return None


def _event_dates(payload: dict[str, Any], telegram_message_date: str) -> tuple[str, Optional[str], Optional[str]]:
    shamsi = _normalize_shamsi(payload.get("event_date_shamsi"))
    if not shamsi:
        shamsi = _normalize_shamsi(telegram_message_date)
    gregorian = _shamsi_to_gregorian(shamsi)
    if not gregorian:
        # Stage 3 must always have a deterministic accounting date. When a
        # historical date is not supplied, the Telegram message timestamp is
        # expected to carry the Shamsi date; this fallback is only defensive.
        gregorian = datetime.now().date().isoformat()
    event_time = None
    if telegram_message_date and " " in telegram_message_date:
        event_time = telegram_message_date.split(" ", 1)[1].strip() or None
    return gregorian, shamsi, event_time


def _payment_state(payload: dict[str, Any], raw_text: str, final_amount: int) -> tuple[str, int]:
    state = str(payload.get("payment_state") or "").upper()
    paid_amount = _positive_int(payload.get("paid_amount"))

    if state not in {"PAID", "PARTIAL", "UNPAID", "UNKNOWN"}:
        state = "UNKNOWN"

    text = (raw_text or "").replace("ي", "ی").replace("ك", "ک")
    paid_markers = (
        "پرداخت کردم", "پرداخت شد", "واریز کردم", "واریز شد", "کارت به کارت",
        "تسویه کردم", "تسویه شد", "پرداختم", "انتقال دادم", "دادم",
    )
    partial_markers = ("علی الحساب", "علی‌الحساب", "بخشی", "قسمتی", "پرداخت جزئی")

    if state == "UNKNOWN":
        if any(marker in text for marker in partial_markers):
            state = "PARTIAL"
        elif any(marker in text for marker in paid_markers):
            state = "PAID"
        elif str(payload.get("document_type") or "").upper() == "INVOICE":
            state = "UNPAID"

    # Accounting invariant: PAID means the expense is fully settled.
    # A stale paid_amount can remain from the pre-edit payload (e.g. final
    # amount changes 100 -> 120 while paid_amount is still 100). Letting that
    # stale value through makes Expense=120 but Payment/Transaction=100.
    # Therefore a PAID expense always settles exactly its final amount.
    # If the user intentionally paid less than final_amount, the edit
    # normalizer marks the state PARTIAL and the explicit paid_amount is kept.
    if state == "PAID":
        if final_amount > 0:
            paid_amount = final_amount
        elif paid_amount <= 0:
            paid_amount = _positive_int(payload.get("amount"))
    elif state == "PARTIAL" and paid_amount <= 0:
        paid_amount = _positive_int(payload.get("amount"))

    if final_amount > 0 and paid_amount > final_amount and state in {"PAID", "PARTIAL"}:
        paid_amount = final_amount
    if state == "PARTIAL" and final_amount > 0 and paid_amount >= final_amount:
        state = "PAID"

    return state, paid_amount


def _is_manager_withdrawal(payload: dict[str, Any], raw_text: str) -> bool:
    text = " ".join([
        str(payload.get("description") or ""),
        str(payload.get("transaction_type_fa") or ""),
        raw_text or "",
    ])
    normalized = text.replace("ي", "ی").replace("ك", "ک")
    return any(x in normalized for x in ("حقوق مدیر پروژه", "برداشت حقوق مدیر پروژه", "حقوق پیمان", "حق پیمان"))


def build_posting_plan(*, payload: dict[str, Any], raw_text: str,
                       telegram_message_date: str) -> dict[str, Any]:
    detected_type = str(payload.get("detected_type") or "UNKNOWN").upper()
    if detected_type in {"UNKNOWN", "DOCUMENT"}:
        raise ValueError("این مورد هنوز ماهیت مالی قطعی ندارد؛ ابتدا نوع آن را ویرایش کنید.")

    event_date, shamsi_date, event_time = _event_dates(payload, telegram_message_date)
    amount = _positive_int(payload.get("amount"))
    description = str(payload.get("description") or raw_text or "").strip()
    method = str(payload.get("payment_method") or "UNKNOWN").upper()
    is_cheque = bool(payload.get("is_cheque")) or method == "CHEQUE" or detected_type == "CHEQUE"

    plan: dict[str, Any] = {
        "posting_type": detected_type,
        "event_date": event_date,
        "shamsi_date": shamsi_date,
        "event_time": event_time,
        "amount": amount,
        "description": description,
        "payer_name": str(payload.get("payer_name") or "").strip() or None,
        "receiver_name": str(payload.get("receiver_name") or "").strip() or None,
    }

    if detected_type == "EXPENSE":
        final_amount = _positive_int(payload.get("final_amount"))
        invoice_amount = _positive_int(payload.get("invoice_amount"))
        # Important Stage 3 correction: one clear amount in a construction
        # expense is the final expense amount unless a separate invoice/final
        # amount was explicitly extracted.
        if final_amount <= 0:
            final_amount = amount
        if final_amount <= 0:
            raise ValueError("مبلغ نهایی هزینه مشخص نیست.")
        if invoice_amount <= 0:
            invoice_amount = final_amount
        discount_amount = _positive_int(payload.get("discount_amount"))
        if discount_amount <= 0 and invoice_amount >= final_amount:
            discount_amount = invoice_amount - final_amount

        payment_state, paid_amount = _payment_state(payload, raw_text, final_amount)
        if is_cheque:
            payment_state = "UNPAID"  # cash does not move until cheque clears
            paid_amount = 0

        plan.update({
            "final_amount": final_amount,
            "invoice_amount": invoice_amount,
            "discount_amount": discount_amount,
            "expense_category": str(payload.get("expense_category") or "OTHER").strip() or "OTHER",
            "construction_stage": str(payload.get("construction_stage") or "").strip() or None,
            "manager_fee_eligible": bool(payload.get("manager_fee_eligible", True)),
            "payment_state": payment_state,
            "paid_amount": paid_amount,
            "payment_method": "CHEQUE" if is_cheque else method,
            "is_cheque": is_cheque,
        })
        if is_cheque:
            due_shamsi = _normalize_shamsi(payload.get("due_date_shamsi"))
            due_date = _shamsi_to_gregorian(due_shamsi)
            if not due_date:
                raise ValueError("سررسید چک مشخص نیست؛ قبل از تأیید آن را ویرایش کنید.")
            issue_shamsi = _normalize_shamsi(payload.get("issue_date_shamsi")) or shamsi_date
            issue_date = _shamsi_to_gregorian(issue_shamsi) or event_date
            plan.update({
                "cheque_amount": amount or final_amount,
                "issue_date": issue_date,
                "issue_date_shamsi": issue_shamsi,
                "due_date": due_date,
                "due_date_shamsi": due_shamsi,
                "cheque_serial": str(payload.get("cheque_serial") or "").strip() or None,
                "issuer_bank": str(payload.get("issuer_bank") or "").strip() or None,
                "issuer_name": str(payload.get("issuer_name") or "").strip() or None,
                "cheque_type": str(payload.get("cheque_type") or "PHYSICAL").strip().upper(),
                "cheque_registration_state": str(payload.get("cheque_registration_state") or "UNKNOWN").strip().upper(),
            })

    elif detected_type == "INCOME":
        if amount <= 0:
            raise ValueError("مبلغ ورودی مشخص نیست.")
        plan["transaction_category"] = "GENERAL_INCOME"

    elif detected_type == "OUTFLOW":
        if amount <= 0:
            raise ValueError("مبلغ خروجی مشخص نیست.")
        plan["transaction_category"] = (
            "CONTRACTOR_FEE" if _is_manager_withdrawal(payload, raw_text)
            else "NON_CONSTRUCTION_OUTFLOW"
        )

    elif detected_type == "CHEQUE":
        if amount <= 0:
            raise ValueError("مبلغ چک مشخص نیست.")
        due_shamsi = _normalize_shamsi(payload.get("due_date_shamsi"))
        due_date = _shamsi_to_gregorian(due_shamsi)
        if not due_date:
            raise ValueError("سررسید چک مشخص نیست؛ قبل از تأیید آن را ویرایش کنید.")
        issue_shamsi = _normalize_shamsi(payload.get("issue_date_shamsi")) or shamsi_date
        issue_date = _shamsi_to_gregorian(issue_shamsi) or event_date
        plan.update({
            "issue_date": issue_date,
            "issue_date_shamsi": issue_shamsi,
            "due_date": due_date,
            "due_date_shamsi": due_shamsi,
            "cheque_serial": str(payload.get("cheque_serial") or "").strip() or None,
            "issuer_bank": str(payload.get("issuer_bank") or "").strip() or None,
            "issuer_name": str(payload.get("issuer_name") or "").strip() or None,
            "cheque_type": str(payload.get("cheque_type") or "PHYSICAL").strip().upper(),
            "cheque_registration_state": str(payload.get("cheque_registration_state") or "UNKNOWN").strip().upper(),
        })
    else:
        raise ValueError(f"نوع مالی پشتیبانی نمی‌شود: {detected_type}")

    return plan


class FinancialPostingService:
    def __init__(self, db: FinanceDB):
        self.db = db

    def post_pending(self, pending_id: str, *, actor_id: str | None = None) -> PostingResult:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)

        existing = self.db.get_financial_posting(pending_id)
        if existing:
            if str(existing.get("status") or "ACTIVE") != "ACTIVE":
                raise ValueError("این ثبت قبلاً حذف شده است و با تأیید دوباره نباید احیا شود.")
            return self._result(existing)

        tg = self.db.get_telegram_message(item["telegram_chat_id"], item["telegram_message_id"])
        if not tg:
            raise KeyError((item["telegram_chat_id"], item["telegram_message_id"]))

        plan = build_posting_plan(
            payload=item["payload"],
            raw_text=tg.get("raw_text") or "",
            telegram_message_date=tg.get("message_date") or "",
        )
        posted = self.db.apply_financial_posting(
            pending_id=pending_id,
            plan=plan,
            source="TELEGRAM",
            actor_id=actor_id,
        )
        return self._result(posted)

    def revise_pending(self, pending_id: str, *, actor_id: str | None = None) -> PostingResult:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        tg = self.db.get_telegram_message(item["telegram_chat_id"], item["telegram_message_id"])
        if not tg:
            raise KeyError((item["telegram_chat_id"], item["telegram_message_id"]))
        plan = build_posting_plan(
            payload=item["payload"],
            raw_text=tg.get("raw_text") or "",
            telegram_message_date=tg.get("message_date") or "",
        )
        row = self.db.revise_financial_posting(
            pending_id=pending_id,
            plan=plan,
            source="TELEGRAM_EDIT",
            actor_id=actor_id,
        )
        return self._result(row)

    def delete_pending(self, pending_id: str, *, actor_id: str | None = None, reason: str = "") -> PostingResult:
        row = self.db.delete_financial_posting(
            pending_id=pending_id,
            source="TELEGRAM",
            actor_id=actor_id,
            reason=reason,
        )
        return self._result(row)

    @staticmethod
    def _result(row: dict[str, Any]) -> PostingResult:
        return PostingResult(
            pending_id=str(row["pending_id"]),
            posting_id=str(row["posting_id"]),
            posting_type=str(row["posting_type"]),
            primary_entity_type=row.get("primary_entity_type"),
            primary_entity_id=row.get("primary_entity_id"),
            expense_id=row.get("expense_id"),
            transaction_id=row.get("transaction_id"),
            payment_id=row.get("payment_id"),
            cheque_id=row.get("cheque_id"),
        )
