from __future__ import annotations

import re
from typing import Any

from revenue_input import parse_money
from revenue_service import normalize_shamsi

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _norm(value: str) -> str:
    return (value or "").translate(_DIGITS).replace("ي", "ی").replace("ك", "ک").replace("٬", ",").strip()


def _key(value: str) -> str:
    return re.sub(r"[\s‌_-]+", "", _norm(value)).lower()


def _lines(text: str) -> list[str]:
    return [_norm(x) for x in (text or "").splitlines() if _norm(x)]


def _field(lines: list[str], *aliases: str) -> str:
    aliases_n = {_key(a) for a in aliases}
    for line in lines:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        if _key(k) in aliases_n:
            return v.strip()
    return ""


def _int(value: str) -> int:
    s = _norm(value).replace(",", "")
    m = re.search(r"-?\d+", s)
    return int(m.group(0)) if m else 0


def _float(value: str) -> float:
    s = _norm(value).replace("%", "").replace("٪", "").replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else 0.0


def parse_loan_form(text: str) -> dict[str, Any]:
    lines = _lines(text)
    principal = parse_money(_field(lines, "اصل وام", "مبلغ اصل وام", "مبلغ وام"))
    net = parse_money(_field(lines, "مبلغ واقعی واریزی", "دریافتی واقعی", "مبلغ دریافتی", "مبلغ واریزی"))
    if not net:
        net = principal
    count = _int(_field(lines, "تعداد اقساط", "تعداد قسط"))
    installment = parse_money(_field(lines, "مبلغ هر قسط", "مبلغ قسط"))
    fees = parse_money(_field(lines, "کارمزد", "هزینه بانکی", "کارمزد بانک"))
    interest = parse_money(_field(lines, "کل سود", "مبلغ کل سود", "سود کل"))
    # If total interest is omitted but a complete installment plan is supplied,
    # infer only the total financing cost from the user's own entered schedule.
    if not interest and count > 0 and installment > 0 and principal > 0:
        inferred = installment * count - principal - fees
        if inferred > 0:
            interest = inferred
    raw_type = _field(lines, "نوع وام", "نوع تسهیلات").strip() or "وام بانکی"
    loan_type = {
        "وام بانکی": "BANK", "بانکی": "BANK", "بانک": "BANK",
        "قرض شخصی": "PERSONAL", "قرض": "PERSONAL",
        "قرض شریک": "PARTNER", "شریک": "PARTNER",
        "تسهیلات پروژه": "PROJECT", "پروژه": "PROJECT",
    }.get(raw_type, raw_type.upper() if raw_type.isascii() else "OTHER")
    return {
        "lender_name": _field(lines, "بانک / وام‌دهنده", "بانک/وام‌دهنده", "وام‌دهنده", "بانک", "نام بانک"),
        "loan_type": loan_type,
        "principal_amount": principal,
        "net_received_amount": net,
        "received_date_shamsi": normalize_shamsi(_field(lines, "تاریخ دریافت", "تاریخ وام", "تاریخ واریز")),
        "interest_rate": _float(_field(lines, "نرخ سود", "سود سالیانه", "درصد سود")),
        "total_interest": interest,
        "bank_fees": fees,
        "installment_count": count,
        "installment_amount": installment,
        "first_due_date_shamsi": normalize_shamsi(_field(lines, "تاریخ اولین قسط", "اولین قسط", "سررسید اولین قسط")),
        "guarantors": _field(lines, "ضامنین", "ضامن‌ها", "ضامن"),
        "collateral": _field(lines, "وثیقه", "تضمین"),
        "contract_number": _field(lines, "شماره قرارداد", "شماره تسهیلات", "قرارداد"),
        "description": _field(lines, "توضیحات", "شرح", "بابت"),
    }


def validate_loan_form(data: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not str(data.get("lender_name") or "").strip():
        missing.append("بانک / وام‌دهنده")
    if int(data.get("principal_amount") or 0) <= 0:
        missing.append("اصل وام")
    if int(data.get("net_received_amount") or 0) < 0:
        missing.append("مبلغ واقعی واریزی")
    if not data.get("received_date_shamsi"):
        missing.append("تاریخ دریافت")
    if int(data.get("installment_count") or 0) > 0 and not data.get("first_due_date_shamsi"):
        missing.append("تاریخ اولین قسط")
    return missing
