from __future__ import annotations

import re
from typing import Any

from revenue_service import normalize_shamsi

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _norm(s: str) -> str:
    return (s or "").translate(_DIGITS).replace("ي", "ی").replace("ك", "ک").strip()


def parse_money(value: str) -> int:
    s = _norm(value).replace(",", "").replace("٬", "").lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(میلیارد|میلیون|هزار)?", s)
    if not m:
        return 0
    n = float(m.group(1))
    unit = m.group(2) or ""
    n *= {"میلیارد": 1_000_000_000, "میلیون": 1_000_000, "هزار": 1_000}.get(unit, 1)
    return int(round(n))


def _field(lines: list[str], *names: str) -> str:
    for line in lines:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = _norm(k).replace(" ", "")
        if any(key == _norm(n).replace(" ", "") for n in names):
            return v.strip()
    return ""


def parse_sale_form(text: str) -> dict[str, Any]:
    lines = [_norm(x) for x in (text or "").splitlines() if _norm(x)]
    installments: list[dict[str, Any]] = []
    in_installments = False
    seq = 0
    for line in lines:
        if line.replace(" ", "").startswith("اقساط:") or line == "اقساط":
            in_installments = True
            continue
        if not in_installments:
            continue
        m = re.match(r"(?:قسط\s*\d+\s*[:=-]\s*)?(1[23-6]\d{2}[/-]\d{1,2}[/-]\d{1,2})\s*[=:\-]\s*(.+)$", line)
        if not m:
            continue
        seq += 1
        installments.append({
            "sequence_no": seq,
            "due_date_shamsi": normalize_shamsi(m.group(1)),
            "amount": parse_money(m.group(2)),
            "description": f"قسط {seq}",
        })
    area_raw = _field(lines, "متراژ", "مساحت")
    try:
        area = float(_norm(area_raw).replace(",", "")) if area_raw else None
    except Exception:
        area = None
    return {
        "project_name": _field(lines, "پروژه"),
        "block_name": _field(lines, "بلوک"),
        "unit_number": _field(lines, "واحد", "شماره واحد"),
        "floor": _field(lines, "طبقه"),
        "area": area,
        "parking": _field(lines, "پارکینگ"),
        "storage": _field(lines, "انباری"),
        "buyer_name": _field(lines, "خریدار", "نام خریدار"),
        "buyer_phone": _field(lines, "موبایل", "تلفن", "شماره خریدار"),
        "contract_number": _field(lines, "شماره قرارداد", "قرارداد"),
        "contract_date_shamsi": normalize_shamsi(_field(lines, "تاریخ قرارداد")),
        "contract_amount": parse_money(_field(lines, "مبلغ قرارداد", "قیمت قرارداد")),
        "notes": _field(lines, "توضیحات"),
        "installments": installments,
    }


def parse_received_payment_form(text: str) -> dict[str, Any]:
    lines = [_norm(x) for x in (text or "").splitlines() if _norm(x)]
    return {
        "sale_id": _field(lines, "Sale ID", "sale id", "شناسه فروش", "فروش"),
        "amount": parse_money(_field(lines, "مبلغ", "مبلغ وصول", "وصول")),
        "received_date_shamsi": normalize_shamsi(_field(lines, "تاریخ وصول", "تاریخ", "تاریخ دریافت")),
        "payer_name": _field(lines, "پرداخت کننده", "پرداخت‌کننده", "واریزکننده", "خریدار"),
        "description": _field(lines, "شرح", "توضیحات", "بابت"),
    }
