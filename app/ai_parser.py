from __future__ import annotations

import json
import re
from typing import Any, Optional


CONSTRUCTION_PHASES = (
    'خرید زمین', 'مطالعات اولیه', 'طراحی', 'نظام مهندسی', 'جواز', 'تجهیز کارگاه',
    'خاکی و تخریب', 'اسکلت', 'چاه', 'کف سازی', 'شاسی آسانسور', 'وال پست',
    'میلگرد بستر', 'وال مش', 'تیغه چینی', 'تاسیسات', 'عایق و بام', 'چهارچوب و فریم',
    'شاسی نما', 'آسانسور', 'درب ضدسرقت', 'کاشی و سنگ', 'سقف کاذب', 'گچکاری',
    'UPVC', 'نرده و هندریل', 'درب پارکینگ', 'نقاشی', 'درب اتاق', 'انشعابات',
    'پایان کار', 'سند و فروش',
)


def normalize_construction_stage(value: Any) -> str:
    normalized = str(value or '').replace('ي', 'ی').replace('ك', 'ک').strip()
    normalized = re.sub(r'^\d{1,2}\s*[-–:]?\s*', '', normalized).strip()
    labels = {label.replace('ي', 'ی').replace('ك', 'ک'): label for label in CONSTRUCTION_PHASES}
    return labels.get(normalized, '')

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "detected_type": {
            "type": "string",
            "enum": ["EXPENSE", "INCOME", "OUTFLOW", "CHEQUE", "DOCUMENT", "INFO", "UNKNOWN"],
        },
        "document_type": {
            "type": "string",
            "enum": ["INVOICE", "PAYMENT_RECEIPT", "CHEQUE", "TEXT", "OTHER"],
        },
        "transaction_type_fa": {"type": "string"},
        "amount": {"type": "integer"},
        "invoice_amount": {"type": "integer"},
        "final_amount": {"type": "integer"},
        "discount_amount": {"type": "integer"},
        "description": {"type": "string"},
        "expense_category": {"type": "string"},
        # No "" in the enum: Gemini rejects the whole request over an empty
        # enum value (400 INVALID_ARGUMENT, "enum[0]: cannot be empty"), which
        # silently sent every message to the local fallback parser. The field
        # is optional, so "no phase" is simply leaving it out.
        "construction_stage": {"type": "string", "enum": list(CONSTRUCTION_PHASES)},
        # Peyman's own transaction taxonomy (confirmed 2026-09-13). Gemini's
        # structured JSON output reliably omits optional enum fields even when
        # SYSTEM_PROMPT asks for them in free text - confirmed against live
        # pending_items, where expense_cost_type/income_source_type/
        # outflow_type/note_type were unset on essentially 100% of the
        # matching rows (0 of 90+ EXPENSE/INCOME/OUTFLOW rows, 1 of 47 INFO
        # rows). sub_category is the fix: ONE always-required field the model
        # must fill on every response, whose meaning depends on detected_type.
        # GeminiFinancialParser._normalize() routes its value into the
        # matching legacy field below (expense_cost_type/income_source_type/
        # outflow_type/note_type), which every downstream reader (e.g.
        # dashboard_stage18_7._outflow_type_187) already keys off unchanged.
        "sub_category": {
            "type": "string",
            "enum": [
                "مصالح", "پیمانکار", "خدمات",
                "تسهیلات", "فروش", "شرکا_یا_قرض",
                "اقساط",
                "تقویم_کارگاهی", "گزارش_روزانه", "داکیومنت", "یادآوری", "یادداشت", "اطلاع_رسانی",
                "فاکتور",
                "سایر", "هیچکدام",
            ],
        },
        "expense_cost_type": {
            "type": "string",
            "enum": ["مصالح", "پیمانکار", "خدمات", "سایر"],
        },
        "income_source_type": {
            "type": "string",
            "enum": ["تسهیلات", "فروش", "شرکا_یا_قرض", "سایر"],
        },
        "outflow_type": {
            "type": "string",
            "enum": ["اقساط", "سایر"],
        },
        "note_type": {
            "type": "string",
            "enum": ["تقویم_کارگاهی", "گزارش_روزانه", "داکیومنت", "یادآوری", "یادداشت", "اطلاع_رسانی",
                     "فاکتور"],
        },
        "payer_name": {"type": "string"},
        "receiver_name": {"type": "string"},
        "payment_method": {
            "type": "string",
            "enum": ["CASH", "BANK_TRANSFER", "CARD", "CHEQUE", "UNKNOWN"],
        },
        "payment_state": {
            "type": "string",
            "enum": ["PAID", "PARTIAL", "UNPAID", "CHEQUE_CLEARING", "UNKNOWN"],
        },
        "paid_amount": {"type": "integer"},
        "is_cheque": {"type": "boolean"},
        "cheque_serial": {"type": "string"},
        "issuer_bank": {"type": "string"},
        "issuer_name": {"type": "string"},
        "cheque_type": {"type": "string", "enum": ["PHYSICAL", "DIGITAL"]},
        "due_date_shamsi": {"type": "string"},
        "issue_date_shamsi": {"type": "string"},
        "cheque_registration_state": {"type": "string", "enum": ["REGISTERED", "UNREGISTERED"]},
        "is_guarantee": {"type": "boolean"},
        "document_group_hint": {"type": "string"},
        "currency_detected": {"type": "string"},
        "source_amount": {"type": "integer"},
        "cheques": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "amount": {"type": "integer"},
                    "issue_date_shamsi": {"type": "string"},
                    "due_date_shamsi": {"type": "string"},
                    "cheque_serial": {"type": "string"},
                    "issuer_bank": {"type": "string"},
                    "issuer_name": {"type": "string"},
                    "receiver_name": {"type": "string"},
                    "cheque_type": {"type": "string"},
                    "confidence": {"type": "number"},
                    "is_guarantee": {"type": "boolean"},
                    "registration_state": {"type": "string"}
                }
            }
        },
        "event_date_shamsi": {"type": "string"},
        "manager_fee_eligible": {"type": "boolean"},
        "notes": {"type": "string"},
        "tracking_number": {"type": "string"},
        "bank_name": {"type": "string"},
        "account_or_card": {"type": "string"},
        "raw_visible_text": {"type": "string"},
        "field_confidences": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "event_date_shamsi": {"type": "number"},
                "description": {"type": "number"},
                "payer_name": {"type": "number"},
                "receiver_name": {"type": "number"},
                "document_type": {"type": "number"},
                "payment_method": {"type": "number"},
                "tracking_number": {"type": "number"}
            }
        },
        "confidence": {"type": "number"},
    },
    "required": [
        "detected_type", "document_type", "transaction_type_fa", "amount",
        "description", "payment_method", "payment_state", "is_cheque", "manager_fee_eligible",
        "confidence", "sub_category",
    ],
}

# detected_type -> which legacy payload field sub_category routes into, and
# which of sub_category's enum values are actually valid for that
# detected_type. A model output that doesn't match (wrong namespace, or
# detected_type has no sub-category at all - CHEQUE/UNKNOWN/etc.) is dropped
# rather than assigned, so a mismatched guess never lands in the wrong field.
_SUB_CATEGORY_ROUTES: dict[str, tuple[str, tuple[str, ...]]] = {
    "EXPENSE": ("expense_cost_type", ("مصالح", "پیمانکار", "خدمات", "سایر")),
    "INCOME": ("income_source_type", ("تسهیلات", "فروش", "شرکا_یا_قرض", "سایر")),
    "OUTFLOW": ("outflow_type", ("اقساط", "سایر")),
    "INFO": ("note_type", ("تقویم_کارگاهی", "گزارش_روزانه", "داکیومنت", "یادآوری", "یادداشت", "اطلاع_رسانی",
                          "فاکتور")),
    "DOCUMENT": ("note_type", ("تقویم_کارگاهی", "گزارش_روزانه", "داکیومنت", "یادآوری", "یادداشت", "اطلاع_رسانی",
                               "فاکتور")),
}

#: The seven non-financial categories and the ways the operator writes their
#: title. Longest spellings are tried first, so «گزارش روزانه» wins over «گزارش روز».
NOTE_TITLES: dict[str, tuple[str, ...]] = {
    "تقویم_کارگاهی": ("تقویم کارگاهی", "تقویم کاری", "تقویم"),
    "گزارش_روزانه": ("گزارش کار روزانه", "گزارش روزانه", "گزارش روز"),
    "یادآوری": ("یادآوری", "یاد آوری", "یادآور"),
    "یادداشت": ("یادداشت",),
    "اطلاع_رسانی": ("اطلاع رسانی", "اطلاعرسانی", "اطلاعیه"),
    "داکیومنت": ("داکیومنت", "مستندات", "مستند"),
    # A note about an invoice, distinct from document_type=INVOICE (the image
    # classification for an attached photo/scan) - this is the note_type for
    # the operator's own «فاکتور» title, unrelated to what kind of file, if
    # any, came with the message.
    "فاکتور": ("فاکتور",),
}
#: note_type -> the subtype the data-entry tab files it under (title «یادداشت»).
NOTE_TYPE_LABELS = {
    "تقویم_کارگاهی": "تقویم کارگاهی", "گزارش_روزانه": "گزارش روزانه",
    "یادآوری": "یادآوری", "یادداشت": "یادداشت",
    "اطلاع_رسانی": "اطلاع‌رسانی", "داکیومنت": "داکیومنت",
    "فاکتور": "فاکتور",
}
_TITLE_VARIANTS = sorted(((variant, key) for key, variants in NOTE_TITLES.items() for variant in variants),
                         key=lambda pair: -len(pair[0]))
_TITLE_SEPARATORS = " \t-–—:/،,#*•|"
_TITLE_BREAKS = "-–—:/،,|"
_LETTER = re.compile(r"[A-Za-z؀-ۿ]")
_DATE_START = re.compile(r"^(?:(?:از|مورخ|تاریخ|روز)\s*)?[0-9۰-۹]")


def _title_norm(text: str) -> str:
    text = str(text or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ").replace("_", " ")
    return re.sub(r"[ \t]+", " ", text)


def _leading_titles(line: str) -> tuple[list[str], str, bool]:
    """Titles at the start of ``line`` («داکیومنت-تقویم: ...»), what follows them,
    and whether a separator («:», «-») came right after the last one."""
    found: list[str] = []
    rest = line
    separated = False
    while True:
        stripped = rest.lstrip(_TITLE_SEPARATORS)
        if found:
            separated = any(ch in _TITLE_BREAKS for ch in rest[:len(rest) - len(stripped)])
        for variant, key in _TITLE_VARIANTS:
            if stripped.startswith(variant):
                tail = stripped[len(variant):]
                if tail and _LETTER.match(tail[0]):
                    continue  # «تقویمی», «مستندسازی»: part of another word
                found.append(key)
                rest = tail
                break
        else:
            return found, stripped, separated


def explicit_note_title(text: str) -> tuple[str | None, bool]:
    """The non-financial category the operator named in the message, and how sure that is.

    The operator writes the category as the message's title: «گزارش روزانه ۵ مهر ۴۰۵:»,
    «تقویم کارگاهی:», or a group and its category, «داکیومنت-تقویم:» / «یادداشت- داکیومنت»,
    where the last part is the category. The title is *strong* (it decides, whatever
    the model thought) when a separator, a date or nothing follows it, when it is
    compound or a hashtag. It is *weak* (it only picks which of the
    six a non-financial message is) when the first line merely starts or ends with it,
    or when it stands on a later line of its own.
    """
    lines = [line.strip() for line in _title_norm(text).splitlines() if line.strip()]
    if not lines:
        return None, False
    for line in lines:
        for tag in re.findall(r"#(\S+(?: \S+)?)", line):
            found, _rest, _sep = _leading_titles(tag)
            if found:
                return found[-1], True
    found, rest, separated = _leading_titles(lines[0])
    if found:
        remainder = rest.strip()
        strong = len(found) > 1 or not remainder or separated or bool(_DATE_START.match(remainder))
        return found[-1], strong
    for line in lines[1:]:
        # A title on a later line of its own: the first line («هزینه ساخت») may
        # already have said what kind of message this is, so it only settles
        # which of the six a non-financial message is.
        found, rest, _sep = _leading_titles(line)
        if found and not rest.strip(_TITLE_SEPARATORS):
            return found[-1], False
    last_word = lines[0].rstrip(_TITLE_SEPARATORS).rsplit(" ", 1)[-1]
    for variant, key in _TITLE_VARIANTS:
        if " " not in variant and last_word == variant:
            return key, False
    if "تقویم" in "\n".join(lines):
        return "تقویم_کارگاهی", False
    return None, False


def apply_explicit_note_title(out: dict[str, Any], text: str) -> dict[str, Any]:
    """File the result under the category the message names as its title.

    Shared by every reader (Gemini, the other AI engines, the local fallback), so
    a «گزارش روزانه» lands in گزارش روزانه whichever of them answered.
    """
    category, strong = explicit_note_title(text)
    if not category:
        return out
    detected = str(out.get("detected_type") or "UNKNOWN").upper()
    non_financial = {"INFO", "DOCUMENT", "UNKNOWN"}
    if not strong and detected not in non_financial:
        return out
    if category == "داکیومنت":
        new_detected = "DOCUMENT"
    elif detected in {"INFO", "DOCUMENT"}:
        new_detected = detected
    else:
        new_detected = "INFO"
    out["detected_type"] = new_detected
    out["note_type"] = category
    out["sub_category"] = category
    out["transaction_type_fa"] = NOTE_TYPE_LABELS[category]
    out["note_type_source"] = "TITLE"
    # What the data-entry tab reads to place the row (title/subtype).
    out["transaction_title"] = "یادداشت"
    out["transaction_subtype"] = NOTE_TYPE_LABELS[category]
    if detected not in non_financial:
        # The title says this is not a money event: nothing here may post.
        out["manager_fee_eligible"] = False
        out["payment_state"] = "UNKNOWN"
    if strong:
        try:
            confidence = float(out.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        out["confidence"] = max(confidence, 0.9)
    return out


SYSTEM_PROMPT = """
تو موتور استخراج اسناد مالی یک پروژه ساختمانی هستی. وظیفه تو فقط استخراج و طبقه‌بندی است؛
تصمیم نهایی با مدیر پروژه است.

قواعد:
- مبلغ‌ها را فقط به تومان و به صورت عدد صحیح برگردان.
- EXPENSE یعنی هزینه واقعی ساخت پروژه. OUTFLOW یعنی خروج پولی که هزینه ساخت نیست، مثل
  قسط وام، قرض، سفر، هزینه خانوادگی یا حقوق مدیر پروژه. INCOME یعنی ورود واقعی وجه به
  تنخواه. CHEQUE وقتی خود سند یا متن اساساً یک چک است و هنوز ماهیت خرید/هزینه روشن نیست.
- sub_category یک فیلد اجباری است که در هر پاسخ باید دقیقاً یک مقدار داشته باشد - هرگز
  آن را حدس‌نزده رها نکن. معنای آن به detected_type بستگی دارد:
  - وقتی detected_type=EXPENSE: یکی از «مصالح» (خرید مصالح ساختمانی)، «پیمانکار»
    (دستمزد/مطالبات پیمانکار)، «خدمات» (خدمات جانبی مثل مهندسی، بیمه، نقشه‌کشی)، یا
    «سایر» اگر هیچ‌کدام جور نیست.
  - وقتی detected_type=OUTFLOW: «اقساط» (قسط وام/تسهیلات) یا «سایر».
  - وقتی detected_type=INCOME: یکی از «تسهیلات» (وام/تسهیلات بانکی دریافتی)، «فروش»
    (فروش واحد/ملک)، «شرکا_یا_قرض» (آورده شریک یا قرض دریافتی)، یا «سایر».
  - وقتی detected_type=INFO یا DOCUMENT: یکی از هفت مقدار «تقویم_کارگاهی»
    (برنامه‌ریزی/زمان‌بندی کار کارگر یا پیمانکار روی روزهای مشخص)، «گزارش_روزانه» (گزارش
    پیشرفت کار همان روز)، «داکیومنت» (فاکتور/رسید بدون رویداد مالی جدید)، «یادآوری»
    (یادآوری یک کار آینده)، «یادداشت» (یادداشت آزاد بدون قالب مشخص)، «اطلاع_رسانی»
    (گزارش وضعیت مالی تجمعی)، یا «فاکتور» (فقط وقتی عنوان صریح پیام «فاکتور» است؛ این
    از document_type=INVOICE که نوع تصویر پیوست را نشان می‌دهد جدا است).
  - برای detected_type=CHEQUE یا UNKNOWN، یا هر پیامی که هیچ‌کدام از موارد بالا برایش
    معنا ندارد، sub_category=هیچکدام بگذار.
- DOCUMENT برای سندی مثل فاکتور یا رسید که به تنهایی نباید الزاماً تراکنش جدید بسازد.
- اگر تصویر فاکتور است document_type=INVOICE؛ اگر رسید بانکی است PAYMENT_RECEIPT.
- اگر فاکتور و رسید ممکن است مربوط به یک خرید باشند، آن را در notes ذکر کن ولی خودسرانه دو هزینه نساز.
- manager_fee_eligible فقط برای هزینه واقعی ساخت true باشد.
- برای چک، issuer_name نام صادرکننده و cheque_type یکی از PHYSICAL یا DIGITAL باشد. اگر نوع مشخص نیست PHYSICAL.
- برای واریز نقدی/بانکی هم اگر رسید یا فیش پرداختی نشان می‌دهد شماره کارت یا حساب مقصد به نام شخصی غیر از گیرنده (receiver_name) است، نام صاحب همان کارت/حساب را در issuer_name بنویس؛ این برای وقتی است که پیمانکار مجبور شده شماره کارت شخص دیگری را برای دریافت وجه بدهد.
- payment_state وضعیت پرداخت همین هزینه را نشان می‌دهد: PAID یعنی کل مبلغ پرداخت شده، PARTIAL یعنی بخشی پرداخت شده، UNPAID یعنی هزینه/فاکتور ثبت شده ولی هنوز پرداخت نشده، UNKNOWN یعنی از متن قابل تشخیص نیست.
- اگر متن صریحاً می‌گوید «پرداخت کردم»، «واریز کردم»، «تسویه شد» یا مشابه آن، payment_state=PAID قرار بده حتی اگر روش دقیق پرداخت معلوم نیست.
- paid_amount فقط مبلغی است که واقعاً پرداخت شده؛ برای PAID معمولاً برابر مبلغ نهایی و برای PARTIAL برابر مبلغ پرداخت‌شده است.
- اگر یک هزینه ساخت فقط یک مبلغ روشن دارد و مبلغ فاکتور/مبلغ نهایی جداگانه‌ای ذکر نشده، final_amount را همان مبلغ قرار بده.
- اگر مطمئن نیستی detected_type=UNKNOWN و confidence پایین بده.
- هیچ اطلاعاتی را حدس قطعی نزن.

- اگر پیام فقط اطلاع‌رسانی/گزارش وضعیت است و هیچ رویداد مالی جدید ایجاد نمی‌کند (مثلاً «تا الان مجموعاً ... پرداخت شده»)، detected_type=INFO بگذار.
- توجه ویژه: پیامی که فقط برنامه‌ریزیِ چه‌کسی‌چه‌روزی‌کار‌می‌کند را توصیف می‌کند - مثلاً
  «کار کرد ناصر از ۹ شهریور تا ۱۳ شهریور برای ابراهیم» یا «هفته اول: ۱۱ و ۱۲ شهریور
  مجموع ۲ روز» - یک تقویم کارگاهی است (detected_type=INFO, sub_category=تقویم_کارگاهی)
  حتی اگر اعداد/تاریخ زیادی در آن باشد؛ تا وقتی متن صراحتاً مبلغ پرداخت‌شده یا
  دریافت‌شده را ذکر نکرده، آن را EXPENSE یا هیچ تراکنش مالی دیگری قرار نده.
- مدیر پروژه معمولاً عنوان/نوع پیام را خودش صریح زیر یا بالای متن می‌نویسد (مثلاً
  «تقویم کارگاهی»، «تقویم»، «گزارش روزانه»، «یادآوری»، «مصالح»، «پیمانکار»). این عنوانِ
  صریح قوی‌ترین سیگنال است و باید مستقیماً روی detected_type/sub_category اعمال شود، نه
  اینکه دوباره از محتوا حدس زده شود: اگر عنوان شامل «تقویم» است (با یا بدون کلمهٔ
  «کارگاهی») همیشه sub_category=تقویم_کارگاهی و detected_type=INFO بگذار، حتی اگر بدون
  این عنوان صریح ممکن بود به‌عنوان «اطلاع‌رسانی» یا هر چیز دیگری طبقه‌بندی شود. همین قاعده
  برای بقیهٔ عنوان‌های صریح هم برقرار است: عنوانِ متن، نه فقط محتوای آزاد، باید
  تعیین‌کنندهٔ نهایی detected_type و sub_category باشد. این قاعده مستقل از وجود یا نبود
  تصویر/سند پیوست است - چه پیام فقط متن باشد چه عکس/سند همراه داشته باشد، همین قاعده و
  همین مقادیر sub_category به‌طور یکسان اعمال می‌شود.
- قالب عنوان مدیر پروژه: عنوان در خط اول می‌آید و معمولاً با «:» یا تاریخ دنبال می‌شود،
  مثل «گزارش روزانه ۵ مهر ۴۰۵:» یا «تقویم کارگاهی:». گاهی گروه و دسته با خط تیره
  ترکیب می‌شوند، مثل «داکیومنت-تقویم:» یا «یادداشت- داکیومنت»؛ در این حالت بخش آخر
  دسته است (تقویم_کارگاهی و داکیومنت). هفت دسته‌ی غیرمالی: گزارش روزانه، تقویم کارگاهی،
  یادداشت، اطلاع‌رسانی، داکیومنت، یادآوری، فاکتور.
- اعداد سه‌رقمی بدون واحد در پیام متنی مدیر پروژه، وقتی در بافت مالی واضح هستند، معمولاً «هزار تومان» هستند؛ مثال 350 یعنی 350000 تومان. برای اعداد چاپ‌شده روی سند این قاعده را اعمال نکن.
- رسیدهای بانکی ایران معمولاً مبلغ را به ریال چاپ می‌کنند. واحد روی خود سند را تشخیص بده؛ اگر ریال است source_amount را مبلغ ریالی و amount/final_amount/paid_amount را تومان (تقسیم بر 10) برگردان. currency_detected را RIAL یا TOMAN بنویس.
- اگر تصویر شامل چند چک است، همه چک‌های قابل تشخیص را در آرایه cheques جداگانه استخراج کن؛ یک تصویر پنج‌چکی نباید به یک چک واحد تقلیل داده شود. برای هر چک مبلغ و تاریخ را مستقل بخوان؛ اگر نامطمئن است confidence همان چک را پایین بده.
- وضعیت ثبت صیادی اگر صریحاً معلوم نیست UNREGISTERED بگذار؛ UNKNOWN استفاده نکن.
- اگر متن یا سند نشان می‌دهد چک صرفاً «بابت ضمانت» است، is_guarantee=true بگذار. چک ضمانتی رویداد هزینه/پرداخت نیست.
- برای چک تاریخ صدور را در issue_date_shamsi و تاریخ سررسید را در due_date_shamsi استخراج کن. اگر ثبت صیادی/ثبت چک از سند یا متن معلوم است cheque_registration_state=REGISTERED یا UNREGISTERED وگرنه UNKNOWN.
- اگر متن/رسید نشان می‌دهد انتقال وجه صرفاً بابت «پاس کردن چک» قبلی است (مثل #چک ... #پاس)، payment_state=CHEQUE_CLEARING بگذار. این رویداد هزینه جدید نیست و باید به چک قبلی وصل شود.
- کپشن، Reply و پیام‌های نزدیک ممکن است توضیح یک تصویر باشند؛ متن زمینه‌ای را به عنوان شاهد قوی استفاده کن. کپشن مدیر پروژه برای «بابت»، گیرنده، فاز و نیت مالی از نوشته‌های تبلیغاتی چاپ‌شده داخل تصویر مهم‌تر است.
- receiver_name را با دقت از عبارت‌هایی مثل «به حساب ...»، «برای ...»، «واریز به ...» یا نام گیرنده روی رسید استخراج کن. payer_name برای هزینه اگر مشخص نیست «تنخواه» است.
- اگر چند رسید/قبض با یک توضیح مشترک یک هزینه واحد را تسویه می‌کنند، در notes این وابستگی را روشن ذکر کن و از ساخت هزینه‌های تکراری اجتناب کن. document_group_hint را با یک عبارت کوتاه مشترک مثل «هزینه دفترخانه» یا «جواز شهرداری» پر کن تا سیستم بتواند چند رسید را تجمیع کند.
- اگر سند فاکتور است ولی شاهد پرداخت وجود ندارد، payment_state=UNPAID و detected_type=EXPENSE باشد؛ اگر سند صرفاً رسید/پیوست پرداخت قبلی است و هزینه قبلاً شناخته شده، detected_type=DOCUMENT قرار بده.
- متن قابل مشاهده مهم سند را در raw_visible_text خلاصه/بازنویسی کن؛ لازم نیست تمام متن را کلمه‌به‌کلمه کپی کنی.
- اگر شماره پیگیری/مرجع بانکی دیده می‌شود در tracking_number، نام بانک در bank_name و شماره کارت/حساب قابل تشخیص در account_or_card برگردان.
- برای field_confidences اعتماد هر فیلد مهم را بین 0 و 1 جداگانه بده. اعتماد بالا فقط وقتی بده که همان فیلد در تصویر واضح است.
- اگر متن OCR کمکی داده شده با تصویر مقایسه کن؛ OCR فقط شاهد کمکی است و اگر با تصویر ناسازگار بود تصویر و عدم قطعیت را لحاظ کن.
"""


class GeminiFinancialParser:
    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-lite"):
        # Lazy import keeps the whole GUI usable even when the optional Gemini
        # SDK is missing; the diagnostics screen can then report the problem.
        from google import genai
        from google.genai import types
        self._genai = genai
        self._types = types
        self._api_key = api_key
        self.model = model

    async def analyze(self, *, text: str, image_bytes: Optional[bytes] = None,
                      image_mime_type: str = "image/jpeg", ocr_text: str = "") -> dict[str, Any]:
        contents: list[Any] = [SYSTEM_PROMPT]
        if image_bytes:
            # Vision is the primary evidence for receipts/invoices. OCR and caption
            # are supporting evidence only and are explicitly included in the same
            # request so the model can reconcile conflicts instead of parsing the
            # caption as if it were the document itself.
            contents.append(self._types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type))
            contents.append(f"متن/کپشن همراه سند:\n{text or '-'}")
            if ocr_text:
                contents.append(
                    "OCR محلی کمکی (ممکن است خطا داشته باشد؛ با خود تصویر تطبیق بده):\n"
                    + ocr_text[:12000]
                )
            contents.append(
                "این ورودی دارای تصویر واقعی است. ابتدا خود تصویر را بخوان، نوع سند و مبلغ نهایی/پرداختی را "
                "از چیدمان سند تشخیص بده و فقط سپس از کپشن و OCR برای تطبیق استفاده کن."
            )
        else:
            contents.append(f"پیام مدیر پروژه:\n{text}")

        # A fresh client per call, never one cached on self: genai.Client's
        # async transport binds to whichever asyncio event loop is running
        # when first used, but this parser is a long-lived module-level
        # singleton (AI_PARSER/RECEIPT_PARSER/PARSER) reused across many
        # separate asyncio.run() calls - every GUI reprocess click spawns its
        # own thread and a brand-new event loop
        # (dashboard_stage18_2.reprocess_rows). Reusing one client's transport
        # across loops raises "RuntimeError: Event loop is closed" on the
        # second and every later call in the same running process - confirmed
        # live (operator report, PEN-55036ECEA820) right after the reprocess
        # fixes above made calls reach Gemini far more often than before.
        # Client() construction is synchronous/cheap (no network I/O, no loop
        # dependency), so building one per call has no real cost.
        client = self._genai.Client(api_key=self._api_key)
        try:
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=self._types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ANALYSIS_SCHEMA,
                    temperature=0,
                ),
            )
        finally:
            try:
                await client.aio.aclose()
            except Exception:
                pass
        raw = (response.text or "").strip()
        data = json.loads(raw)
        return self._normalize(data, text=text)

    @staticmethod
    def _normalize(data: dict[str, Any], text: str = "") -> dict[str, Any]:
        out = dict(data)
        for key in ("amount", "invoice_amount", "final_amount", "discount_amount", "paid_amount"):
            value = out.get(key)
            try:
                out[key] = max(int(value or 0), 0)
            except (TypeError, ValueError):
                out[key] = 0
        try:
            confidence = float(out.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        out["confidence"] = max(0.0, min(confidence, 1.0))
        fc = out.get("field_confidences")
        if not isinstance(fc, dict):
            fc = {}
        clean_fc = {}
        for key, value in fc.items():
            try: clean_fc[str(key)] = max(0.0, min(float(value), 1.0))
            except Exception: pass
        out["field_confidences"] = clean_fc
        detected = str(out.get("detected_type") or "UNKNOWN").upper()
        if detected == "EXPENSE" and out.get("final_amount", 0) <= 0 and out.get("amount", 0) > 0:
            out["final_amount"] = out["amount"]
        if detected == "EXPENSE" and out.get("invoice_amount", 0) <= 0 and out.get("final_amount", 0) > 0:
            out["invoice_amount"] = out["final_amount"]
        state = str(out.get("payment_state") or "UNKNOWN").upper()
        if state not in {"PAID", "PARTIAL", "UNPAID", "CHEQUE_CLEARING", "UNKNOWN"}:
            state = "UNKNOWN"
        out["payment_state"] = state
        if state == "PAID" and out.get("paid_amount", 0) <= 0:
            out["paid_amount"] = out.get("amount", 0) or out.get("final_amount", 0)
        out['construction_stage'] = normalize_construction_stage(out.get('construction_stage'))
        # sub_category is required (see ANALYSIS_SCHEMA), so the model always
        # returns a value; route it into whichever legacy field matches this
        # detected_type. A value from the wrong namespace (e.g. "اقساط" on an
        # EXPENSE) is dropped rather than assigned.
        sub_category = str(out.get("sub_category") or "").strip()
        route = _SUB_CATEGORY_ROUTES.get(detected)
        if route:
            field, valid_values = route
            if sub_category in valid_values:
                out[field] = sub_category
        # SYSTEM_PROMPT says an explicit title («گزارش روزانه ...:», «تقویم
        # کارگاهی:», «داکیومنت-تقویم:») must win outright; the model does not
        # reliably do it, so it is enforced here, for every engine.
        return apply_explicit_note_title(out, text)
