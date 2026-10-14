from __future__ import annotations

from typing import Any


def parse_edit_fields(text: str) -> dict[str, Any]:
    aliases = {
        "مبلغ": "amount",
        "مبلغ نهایی": "final_amount",
        "مبلغ فاکتور": "invoice_amount",
        "مبلغ پرداخت شده": "paid_amount",
        "مبلغ پرداخت‌شده": "paid_amount",
        "وضعیت پرداخت": "payment_state",
        "نوع": "detected_type",
        "بابت": "description",
        "دسته": "expense_category",
        "گیرنده": "receiver_name",
        "پرداخت کننده": "payer_name",
        "پرداخت‌کننده": "payer_name",
        "روش پرداخت": "payment_method",
        "سررسید": "due_date_shamsi",
        "سررسید چک": "due_date_shamsi",
        "تاریخ سررسید": "due_date_shamsi",
        "تاریخ سررسید چک": "due_date_shamsi",
        "موعد": "due_date_shamsi",
        "موعد چک": "due_date_shamsi",
        "صادر کننده چک": "issuer_name",
        "صادرکننده چک": "issuer_name",
        "بانک چک": "issuer_bank",
        "شماره چک": "cheque_serial",
        "شناسه صیادی": "cheque_serial",
        "نوع چک": "cheque_type",
        "توضیح": "notes",
    }
    type_map = {
        "هزینه": "EXPENSE", "هزینه ساخت": "EXPENSE",
        "ورودی": "INCOME", "خروجی": "OUTFLOW",
        "چک": "CHEQUE", "سند": "DOCUMENT", "نامشخص": "UNKNOWN",
    }
    payment_state_map = {
        "پرداخت کامل": "PAID", "پرداخت شده": "PAID", "پرداخت‌شده": "PAID", "کامل": "PAID",
        "جزئی": "PARTIAL", "پرداخت جزئی": "PARTIAL",
        "پرداخت نشده": "UNPAID", "پرداخت‌نشده": "UNPAID", "نشده": "UNPAID",
        "نامشخص": "UNKNOWN",
    }
    changes: dict[str, Any] = {}
    for raw in (text or "").splitlines():
        if ":" in raw:
            k, v = raw.split(":", 1)
        elif "=" in raw:
            k, v = raw.split("=", 1)
        else:
            continue
        key = aliases.get(k.strip())
        if not key:
            continue
        value = v.strip().replace(",", "").replace("،", "")
        if key in {"amount", "final_amount", "invoice_amount", "paid_amount"}:
            try:
                changes[key] = int(value)
            except ValueError:
                continue
        elif key == "detected_type":
            changes[key] = type_map.get(v.strip(), v.strip().upper())
        elif key == "payment_state":
            changes[key] = payment_state_map.get(v.strip(), v.strip().upper())
        elif key == "cheque_type":
            t=v.strip()
            changes[key] = "DIGITAL" if t in {"دیجیتال","الکترونیکی","DIGITAL"} else "PHYSICAL"
        elif key == "payment_method":
            method_map = {
                "نقد": "CASH", "نقدی": "CASH", "کارت": "CARD",
                "کارتخوان": "CARD", "حواله": "BANK_TRANSFER", "واریز": "BANK_TRANSFER",
                "چک": "CHEQUE", "نامشخص": "UNKNOWN",
            }
            changes[key] = method_map.get(v.strip(), v.strip().upper())
        else:
            changes[key] = v.strip()
    return changes
