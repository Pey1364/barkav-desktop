from __future__ import annotations

import re
from typing import Any


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _norm(text: str) -> str:
    return (text or "").translate(_DIGITS).replace("ي", "ی").replace("ك", "ک").replace("٬", ",")


def _amount(text: str) -> int:
    s = _norm(text).lower()
    candidates: list[int] = []

    # Explicit currency first. Iranian banking documents/messages often show rial.
    for m in re.finditer(r"(?<!\d)(\d{1,3}(?:[,،]\d{3})+|\d{1,15})(?!\d)\s*(ریال|تومان|تومن)", s):
        raw, currency = m.group(1), m.group(2)
        try:n=int(raw.replace(',', '').replace('،',''))
        except Exception:continue
        if currency == 'ریال': n //= 10
        if n>0:candidates.append(n)

    # Written magnitude. These are normally تومان in the project's chat unless ریال is explicit.
    for m in re.finditer(r"(?<!\w)(\d+(?:[\.,]\d+)?)\s*(میلیارد|میلیون|هزار)(?:\s*(ریال|تومان|تومن))?", s):
        raw, unit, currency = m.group(1), m.group(2), m.group(3) or ''
        try:value=float(raw.replace(',', '.'))
        except Exception:continue
        mult={'هزار':1_000,'میلیون':1_000_000,'میلیارد':1_000_000_000}[unit]
        n=int(round(value*mult)); n = n//10 if currency=='ریال' else n
        if n>0:candidates.append(n)

    # Grouped / long bare numbers, excluding card-like 16-digit values and Jalali dates.
    for raw in re.findall(r"(?<!\d)(?:\d{1,3}(?:[,،]\d{3}){1,4}|\d{5,13})(?!\d)", s):
        try:n=int(raw.replace(',','').replace('،',''))
        except Exception:continue
        if n>0:candidates.append(n)

    # Peymaan chat convention: a *standalone* 3-digit money token such as 350 means
    # 350 thousand toman. Do not apply to years/date fragments or larger documents.
    for m in re.finditer(r"(?<![\d/.-])(\d{3})(?![\d/.-])", s):
        n=int(m.group(1))
        if 100 <= n <= 999:
            around=s[max(0,m.start()-18):m.end()+18]
            if not re.search(r"(?:13|14|15|16)\d{2}", around) and not re.search(r"(?:ریال|تومان|تومن)", around):
                candidates.append(n*1_000)

    return max(candidates) if candidates else 0


def _due_date_shamsi(text: str) -> str:
    """Extract an explicit Jalali cheque due date from Persian text.

    Accepts Persian/Arabic digits through _norm and common forms such as:
    «سررسید 1405/05/22», «سر رسید: 1405-05-22», «تاریخ سررسید 1405/5/2».
    This is only a review suggestion; final validation/conversion happens in
    financial_posting.
    """
    s = _norm(text)
    # Prefer a date that is explicitly tied to a due-date keyword.
    labelled = re.search(
        r"(?:تاریخ\s*)?(?:سر\s*رسید|سررسید|موعد)(?:\s*چک)?\s*[:=،,-]?\s*"
        r"(1[23-6]\d{2})[/-](\d{1,2})[/-](\d{1,2})",
        s,
    )
    m = labelled
    # In an explicit cheque sentence, a standalone Jalali date is also useful.
    if m is None and "چک" in s:
        m = re.search(r"(?<!\d)(1[23-6]\d{2})[/-](\d{1,2})[/-](\d{1,2})(?!\d)", s)
    if not m:
        return ""
    y, mo, d = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if not (1 <= mo <= 12):
        return ""
    max_day = 31 if mo <= 6 else 30
    if not (1 <= d <= max_day):
        return ""
    return f"{y:04d}/{mo:02d}/{d:02d}"



def _clean_financial_description(text: str, detected: str) -> str:
    s = _norm(text)
    s = re.sub(r"#(?:تست|هزینه|ورودی|خروجی|چک)\b", "", s).strip()
    # Remove explicit due-date tails and payment mechanics from the human-facing purpose.
    s = re.sub(r"(?:،|,)?\s*(?:تاریخ\s*)?(?:سر\s*رسید|سررسید|موعد)(?:\s*چک)?\s*[:=،,-]?\s*1[23-6]\d{2}[/-]\d{1,2}[/-]\d{1,2}.*$", "", s).strip()
    s = re.sub(r"\b(?:با\s*چک|چکی|نقدی?|کارت\s*به\s*کارت|حواله|واریز)\b", "", s).strip(" ،,-")
    # For phrases like '100 میلیون بابت خرید سیمان پرداخت کردم', keep only the purpose.
    m = re.search(r"\bبابت\s+(.+)$", s)
    if m:
        s = m.group(1).strip()
    s = re.sub(r"^(?:خرید|هزینه|پرداخت(?:\s+بابت)?)\s+", "", s).strip()
    s = re.sub(r"\s+(?:پرداخت کردم|پرداخت شد|واریز کردم|واریز شد|تسویه کردم|تسویه شد|پرداختم|دادم)\s*$", "", s).strip()
    # Remove a leading monetary amount if it survived because there was no 'بابت'.
    s = re.sub(r"^\d+(?:[\.,]\d+)?\s*(?:میلیارد|میلیون|هزار)?(?:\s*تومان)?\s*", "", s).strip()
    return s or ("هزینه ساخت" if detected == "EXPENSE" else "")

def analyze_locally(text: str) -> dict[str, Any]:
    """Deterministic text-only fallback, filed under the message's own title
    («گزارش روزانه ...:», «داکیومنت-تقویم:») when it names one."""
    from ai_parser import apply_explicit_note_title

    return apply_explicit_note_title(_analyze_locally(text), text)


def _analyze_locally(text: str) -> dict[str, Any]:
    """Deterministic text-only fallback.

    This parser is intentionally conservative. It only proposes a record for
    review; it never posts money without the user's Telegram confirmation.
    """
    t = _norm(text)
    low = t.lower()
    amount = _amount(t)

    explicit_expense = any(x in low for x in ("#هزینه", "هزینه ساخت"))
    explicit_income = any(x in low for x in ("#ورودی", "ورودی"))
    explicit_outflow = any(x in low for x in ("#خروجی", "خروجی"))
    explicit_cheque = any(x in low for x in ("#چک", "چک"))
    cheque_clearing = explicit_cheque and any(x in low for x in ("#پاس", "پاس شد", "پاس کردن", "پاس کردم", "وصول چک"))
    info_markers = ("تا الان", "تا اینجا", "مجموعاً", "جمع پرداخت", "اطلاع رسانی", "اطلاع‌رسانی", "گزارش وضعیت")

    nonconstruction_words = (
        "حقوق مدیر پروژه", "برداشت حقوق مدیر پروژه", "حقوق پیمان", "حق پیمان", "قسط وام", "اقساط وام", "قرض دادم",
        "سفر", "خانوادگی", "هزینه خانواده", "برداشت شخصی",
    )
    construction_words = (
        "بتن", "سیمان", "میلگرد", "آجر", "بلوک", "گچ", "شن", "ماسه",
        "مصالح", "کاشی", "سرامیک", "لوله", "کابل", "برقکار", "بنا",
        "کارگر", "پیمانکار", "خرید", "اجرت", "ساخت",
    )
    income_words = (
        "دریافت کردم", "دریافت شد", "واریز به حسابم", "واریز به حساب پروژه",
        "آورده", "واریزی شریک", "پرداخت خریدار", "از خریدار", "وصول شد",
    )
    paid_words = (
        "پرداخت کردم", "پرداخت شد", "واریز کردم", "واریز شد", "کارت به کارت",
        "تسویه کردم", "تسویه شد", "انتقال دادم", "پرداختم",
    )

    detected = "UNKNOWN"
    confidence = 0.35
    if any(x in low for x in info_markers) and not any(x in low for x in ("پرداخت کردم","واریز کردم","دریافت کردم")):
        detected, confidence = "INFO", 0.82
    elif cheque_clearing:
        detected, confidence = "CHEQUE", 0.90
    elif explicit_income:
        detected, confidence = "INCOME", 0.90
    elif explicit_outflow:
        detected, confidence = "OUTFLOW", 0.90
    elif explicit_expense:
        detected, confidence = "EXPENSE", 0.90
    elif explicit_cheque:
        # If purchase/construction context is also clear, treat this as an
        # expense paid by cheque; otherwise it remains a cheque record.
        if any(w in low for w in construction_words):
            detected, confidence = "EXPENSE", 0.78
        else:
            detected, confidence = "CHEQUE", 0.75
    elif any(w in low for w in nonconstruction_words):
        detected, confidence = "OUTFLOW", 0.78
    elif any(w in low for w in income_words):
        detected, confidence = "INCOME", 0.75
    elif amount and any(w in low for w in construction_words) and any(w in low for w in paid_words):
        detected, confidence = "EXPENSE", 0.75

    payment_method = "UNKNOWN"
    if "چک" in low:
        payment_method = "CHEQUE"
    elif any(x in low for x in ("کارت به کارت", "کارت‌به‌کارت", "کارت")):
        payment_method = "CARD"
    elif any(x in low for x in ("حواله", "واریز", "انتقال")):
        payment_method = "BANK_TRANSFER"
    elif "نقد" in low:
        payment_method = "CASH"

    payment_state = "CHEQUE_CLEARING" if cheque_clearing else "UNKNOWN"
    if payment_state != "CHEQUE_CLEARING" and any(w in low for w in paid_words):
        payment_state = "PAID"
    if any(w in low for w in ("علی الحساب", "علی‌الحساب", "بخشی", "قسمتی")):
        payment_state = "PARTIAL"

    due_date_shamsi = _due_date_shamsi(t)

    category = ""
    if detected == "EXPENSE":
        if any(w in low for w in ("بتن", "سیمان", "میلگرد", "آجر", "بلوک", "گچ", "شن", "ماسه", "مصالح")):
            category = "مصالح"
        else:
            category = "هزینه ساخت"

    manager_fee = detected == "EXPENSE"
    final_amount = amount if detected == "EXPENSE" else 0
    paid_amount = amount if payment_state == "PAID" and detected == "EXPENSE" else 0

    return {
        "detected_type": detected,
        "document_type": "TEXT",
        "transaction_type_fa": {
            "EXPENSE": "هزینه ساخت",
            "INCOME": "ورودی",
            "OUTFLOW": "خروجی",
            "CHEQUE": "چک",
            "DOCUMENT": "داکیومنت",
            "INFO": "اطلاع‌رسانی",
        }.get(detected, "نامشخص"),
        "amount": amount,
        "invoice_amount": final_amount,
        "final_amount": final_amount,
        "discount_amount": 0,
        "paid_amount": paid_amount,
        "payment_state": payment_state,
        "description": _clean_financial_description(t, detected),
        "expense_category": category,
        "construction_stage": "",
        "payer_name": "تنخواه",
        "receiver_name": ((re.search(r"(?:به\s*حساب|واریز\s*به|برای)\s+([آ-یA-Za-z][آ-یA-Za-z\s]{2,40})", t).group(1).strip(" ،,-") if re.search(r"(?:به\s*حساب|واریز\s*به|برای)\s+([آ-یA-Za-z][آ-یA-Za-z\s]{2,40})", t) else "")),
        "payment_method": payment_method,
        "is_cheque": payment_method == "CHEQUE",
        "cheque_serial": "",
        "issuer_bank": "",
        "issuer_name": "",
        "cheque_type": "DIGITAL" if any(x in low for x in ("چک دیجیتال","چک الکترونیکی","صیاد دیجیتال")) else "PHYSICAL",
        "issue_date_shamsi": "",
        "due_date_shamsi": due_date_shamsi,
        "cheque_registration_state": "UNREGISTERED",
        "is_guarantee": "ضمانت" in low,
        "document_group_hint": "",
        "currency_detected": "TOMAN",
        "source_amount": amount,
        "cheques": [],
        "event_date_shamsi": "",
        "manager_fee_eligible": manager_fee,
        "notes": "تحلیل جایگزین محلی؛ Gemini در دسترس نبود. قبل از ثبت قطعی بررسی شود.",
        "confidence": confidence,
        "fallback_used": True,
    }
