from __future__ import annotations

import json
from typing import Any, Optional


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
        "construction_stage": {"type": "string"},
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
        "description", "payment_method", "payment_state", "is_cheque", "manager_fee_eligible", "confidence"
    ],
}

SYSTEM_PROMPT = """
تو موتور استخراج اسناد مالی یک پروژه ساختمانی هستی. وظیفه تو فقط استخراج و طبقه‌بندی است؛
تصمیم نهایی با مدیر پروژه است.

قواعد:
- مبلغ‌ها را فقط به تومان و به صورت عدد صحیح برگردان.
- EXPENSE یعنی هزینه واقعی ساخت پروژه.
- OUTFLOW یعنی خروج پولی که هزینه ساخت نیست، مثل قسط وام، قرض، سفر، هزینه خانوادگی یا حقوق مدیر پروژه.
- INCOME یعنی ورود واقعی وجه به تنخواه.
- CHEQUE وقتی خود سند یا متن اساساً یک چک است و هنوز ماهیت خرید/هزینه روشن نیست.
- DOCUMENT برای سندی مثل فاکتور یا رسید که به تنهایی نباید الزاماً تراکنش جدید بسازد.
- اگر تصویر فاکتور است document_type=INVOICE؛ اگر رسید بانکی است PAYMENT_RECEIPT.
- اگر فاکتور و رسید ممکن است مربوط به یک خرید باشند، آن را در notes ذکر کن ولی خودسرانه دو هزینه نساز.
- manager_fee_eligible فقط برای هزینه واقعی ساخت true باشد.
- برای چک، issuer_name نام صادرکننده و cheque_type یکی از PHYSICAL یا DIGITAL باشد. اگر نوع مشخص نیست PHYSICAL.
- payment_state وضعیت پرداخت همین هزینه را نشان می‌دهد: PAID یعنی کل مبلغ پرداخت شده، PARTIAL یعنی بخشی پرداخت شده، UNPAID یعنی هزینه/فاکتور ثبت شده ولی هنوز پرداخت نشده، UNKNOWN یعنی از متن قابل تشخیص نیست.
- اگر متن صریحاً می‌گوید «پرداخت کردم»، «واریز کردم»، «تسویه شد» یا مشابه آن، payment_state=PAID قرار بده حتی اگر روش دقیق پرداخت معلوم نیست.
- paid_amount فقط مبلغی است که واقعاً پرداخت شده؛ برای PAID معمولاً برابر مبلغ نهایی و برای PARTIAL برابر مبلغ پرداخت‌شده است.
- اگر یک هزینه ساخت فقط یک مبلغ روشن دارد و مبلغ فاکتور/مبلغ نهایی جداگانه‌ای ذکر نشده، final_amount را همان مبلغ قرار بده.
- اگر مطمئن نیستی detected_type=UNKNOWN و confidence پایین بده.
- هیچ اطلاعاتی را حدس قطعی نزن.

- اگر پیام فقط اطلاع‌رسانی/گزارش وضعیت است و هیچ رویداد مالی جدید ایجاد نمی‌کند (مثلاً «تا الان مجموعاً ... پرداخت شده»)، detected_type=INFO بگذار.
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
        self._types = types
        self.client = genai.Client(api_key=api_key)
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

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=self._types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ANALYSIS_SCHEMA,
                temperature=0,
            ),
        )
        raw = (response.text or "").strip()
        data = json.loads(raw)
        return self._normalize(data)

    @staticmethod
    def _normalize(data: dict[str, Any]) -> dict[str, Any]:
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
        return out
