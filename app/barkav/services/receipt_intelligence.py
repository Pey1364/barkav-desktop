from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from finance_db import FinanceDB
from local_fallback_parser import analyze_locally

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except Exception:  # pragma: no cover
    Image = ImageEnhance = ImageFilter = ImageOps = None  # type: ignore

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_text(text: str) -> str:
    return (text or "").translate(_DIGITS).replace("ي", "ی").replace("ك", "ک").replace("‌", " ").strip()


def _int(v: Any) -> int:
    try:
        return max(0, int(float(str(v).replace(",", "").translate(_DIGITS))))
    except Exception:
        return 0


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_amount_candidates(text: str) -> list[int]:
    """Extract plausible TOMAN amount candidates from OCR/caption text.

    Explicit ریال values are converted to toman. Bare large numbers remain
    candidates only; the service never auto-posts from this list.
    """
    t = normalize_text(text)
    out: set[int] = set()

    # Grouped or plain number with an explicit currency. This is the safest
    # numeric OCR pattern and correctly converts Iranian rial -> toman.
    currency_pat = re.compile(
        r"(?<!\d)(\d{1,3}(?:[,،]\d{3})+|\d{5,15})(?!\d)\s*(ریال|تومان|تومن)"
    )
    for m in currency_pat.finditer(t):
        n = _int(m.group(1).replace("،", ","))
        if m.group(2) == "ریال":
            n //= 10
        if 10_000 <= n <= 10_000_000_000_000:
            out.add(n)

    # Explicit million/billion forms are normally spoken/written in toman in
    # the project's messages; if ریال is explicit we still convert.
    for m in re.finditer(r"(?<!\d)(\d+(?:\.\d+)?)\s*(میلیارد|میلیون|هزار)?\s*(ریال|تومان|تومن)?", t):
        raw, unit, currency = m.group(1), m.group(2) or "", m.group(3) or ""
        try:
            value = float(raw)
        except Exception:
            continue
        mul = 1
        if unit == "هزار": mul = 1_000
        elif unit == "میلیون": mul = 1_000_000
        elif unit == "میلیارد": mul = 1_000_000_000
        n = int(value * mul)
        if currency == "ریال":
            n //= 10
        if 10_000 <= n <= 10_000_000_000_000:
            out.add(n)

    # Bare grouped/long values. 16-digit card numbers are intentionally not
    # matched and implausibly large values are discarded.
    for raw in re.findall(r"(?<!\d)(?:\d{1,3}(?:[,،]\d{3}){1,4}|\d{6,13})(?!\d)", t):
        n = _int(raw.replace("،", ","))
        if 10_000 <= n <= 10_000_000_000_000:
            out.add(n)
    return sorted(out, reverse=True)[:20]



@dataclass
class OCRResult:
    text: str
    provider: str
    available: bool
    error: str = ""


class LocalOCREngine:
    """Optional local OCR. Works offline when Tesseract + Persian data exist.

    The app never requires OCR to start. If Tesseract is missing, the Vision
    model still receives the image directly and the item is left for review.
    """
    def __init__(self, lang: str | None = None):
        self.lang = lang or os.getenv("PEYMAAN_TESSERACT_LANG", "fas+eng")

    def _configure_tesseract(self):
        import pytesseract
        configured = os.getenv("PEYMAAN_TESSERACT_CMD", "").strip()
        if configured and Path(configured).exists():
            pytesseract.pytesseract.tesseract_cmd = configured
            return
        if os.name == "nt":
            candidates = [
                Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
                Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
            ]
            for candidate in candidates:
                if candidate.exists():
                    pytesseract.pytesseract.tesseract_cmd = str(candidate)
                    return

    def available(self) -> bool:
        try:
            import pytesseract
            self._configure_tesseract()
            return bool(pytesseract.get_tesseract_version())
        except Exception:
            return False

    def effective_lang(self) -> str:
        try:
            import pytesseract
            self._configure_tesseract()
            langs = set(pytesseract.get_languages(config=""))
            requested = [x for x in self.lang.split("+") if x]
            good = [x for x in requested if x in langs]
            if "fas" in langs and "fas" not in good:
                good.insert(0, "fas")
            if "eng" in langs and "eng" not in good:
                good.append("eng")
            if not good and "ara" in langs:
                good = ["ara"] + (["eng"] if "eng" in langs else [])
            return "+".join(good) if good else self.lang
        except Exception:
            return self.lang

    def preprocess(self, source: str | Path, destination: str | Path) -> Path:
        src, dst = Path(source), Path(destination)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if Image is None:
            shutil.copy2(src, dst)
            return dst
        im = Image.open(src)
        im = ImageOps.exif_transpose(im).convert("RGB")
        # Keep enough detail for tiny Persian receipt text while controlling API size.
        max_side = 3200
        if max(im.size) > max_side:
            scale = max_side / max(im.size)
            im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))))
        gray = ImageOps.grayscale(im)
        gray = ImageOps.autocontrast(gray, cutoff=1)
        gray = ImageEnhance.Contrast(gray).enhance(1.42)
        gray = ImageEnhance.Sharpness(gray).enhance(1.35)
        gray = gray.filter(ImageFilter.SHARPEN)
        gray.save(dst, quality=94)
        return dst

    def extract(self, path: str | Path) -> OCRResult:
        try:
            import pytesseract
            if not self.available():
                return OCRResult("", "TESSERACT", False, "tesseract unavailable")
            self._configure_tesseract()
            text = pytesseract.image_to_string(str(path), lang=self.effective_lang(), config="--psm 6")
            return OCRResult(normalize_text(text), "TESSERACT", True)
        except Exception as exc:
            return OCRResult("", "TESSERACT", False, f"{exc.__class__.__name__}: {exc}")


class ReceiptIntelligenceService:
    """Receipt/document intelligence orchestrator.

    Pipeline: immutable archive -> image preprocessing -> optional local OCR ->
    Vision extraction -> deterministic reconciliation -> duplicate suggestions.
    No financial posting happens here.
    """
    def __init__(self, db: FinanceDB, base_dir: str | Path, parser: Any | None = None):
        self.db = db
        self.base_dir = Path(base_dir)
        self.parser = parser
        self.ocr = LocalOCREngine()
        active_project = os.getenv("PEYMAAN_ACTIVE_PROJECT_ID", "").strip()
        archive_root = (self.base_dir / "data" / "projects" / active_project / "receipt_archive") if active_project else (self.base_dir / "data" / "receipt_archive")
        self.original_dir = archive_root / "original"
        self.processed_dir = archive_root / "processed"
        self.original_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def archive_bytes(self, *, data: bytes, suffix: str = ".jpg", stem: str = "receipt") -> tuple[Path, str]:
        digest = hashlib.sha256(data).hexdigest()
        suffix = suffix if suffix.startswith(".") else f".{suffix}"
        dst = self.original_dir / f"{stem}_{digest[:16]}{suffix.lower()}"
        if not dst.exists():
            dst.write_bytes(data)
        return dst, digest

    def archive_file(self, source: str | Path) -> tuple[Path, str]:
        src = Path(source)
        digest = _sha256(src)
        dst = self.original_dir / f"{src.stem}_{digest[:16]}{src.suffix.lower()}"
        if not dst.exists():
            shutil.copy2(src, dst)
        return dst, digest

    def preprocess(self, original: Path, digest: str) -> Path:
        dst = self.processed_dir / f"{digest[:16]}.jpg"
        if not dst.exists():
            self.ocr.preprocess(original, dst)
        return dst

    @staticmethod
    def _field_confidences(payload: dict[str, Any], *, caption_amount: int, ocr_amounts: list[int]) -> dict[str, float]:
        fc = dict(payload.get("field_confidences") or {})
        base = float(payload.get("confidence") or 0.0)
        for key in ("amount", "event_date_shamsi", "description", "payer_name", "receiver_name", "document_type"):
            try: fc[key] = float(fc.get(key, base))
            except Exception: fc[key] = base
        amount = _int(payload.get("amount") or payload.get("final_amount"))
        consensus = 0
        if amount and caption_amount and amount == caption_amount: consensus += 1
        if amount and amount in ocr_amounts: consensus += 1
        if consensus == 2: fc["amount"] = max(fc.get("amount", 0), 0.99)
        elif consensus == 1: fc["amount"] = max(fc.get("amount", 0), 0.93)
        elif amount: fc["amount"] = max(fc.get("amount", 0), 0.72)
        return {k: max(0.0, min(float(v), 1.0)) for k, v in fc.items()}

    @staticmethod
    def _conflicts(*, caption_payload: dict[str, Any], vision_payload: dict[str, Any], ocr_amounts: list[int]) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        ca = _int(caption_payload.get("amount") or caption_payload.get("final_amount"))
        va = _int(vision_payload.get("amount") or vision_payload.get("final_amount"))
        if ca and va and ca != va:
            conflicts.append({"field": "amount", "caption": ca, "receipt": va, "severity": "HIGH"})
        if va and ocr_amounts and va not in ocr_amounts:
            conflicts.append({"field": "amount_ocr", "receipt": va, "ocr_candidates": ocr_amounts[:8], "severity": "MEDIUM"})
        cd = str(caption_payload.get("event_date_shamsi") or "").strip()
        vd = str(vision_payload.get("event_date_shamsi") or "").strip()
        if cd and vd and cd != vd:
            conflicts.append({"field": "event_date_shamsi", "caption": cd, "receipt": vd, "severity": "MEDIUM"})
        return conflicts

    async def analyze_archived(self, *, pending_id: str, caption: str, image_path: str | Path,
                               message_date_shamsi: str = "", context_text: str = "") -> dict[str, Any]:
        source_path = Path(image_path)
        try:
            in_archive = source_path.resolve().parent == self.original_dir.resolve()
        except Exception:
            in_archive = False
        if in_archive:
            original, digest = source_path, _sha256(source_path)
        else:
            original, digest = self.archive_file(source_path)
        processed = self.preprocess(original, digest)
        ocr_result = self.ocr.extract(processed)
        ocr_text = ocr_result.text
        # ``caption`` is deliberately the text directly attached to this receipt.
        # Optional nearby Telegram context is kept separate so it can help the
        # multimodal model without ever becoming the persisted Wizard purpose.
        caption_payload = analyze_locally(caption or "")
        analysis_text = "\n\n".join(x for x in (str(caption or "").strip(), str(context_text or "").strip()) if x)
        if message_date_shamsi and not caption_payload.get("event_date_shamsi"):
            caption_payload["event_date_shamsi"] = message_date_shamsi.split()[0]
        provider = "LOCAL"
        raw_ai: dict[str, Any] = {}
        vision_status = "NOT_CONFIGURED"
        vision_error = ""
        # AI Vision must receive the ORIGINAL archived image, not the grayscale OCR
        # derivative.  Layout, logos, highlighted totals and Persian receipt
        # typography are often lost by OCR preprocessing and are valuable signals
        # for a multimodal model.
        original_bytes = original.read_bytes()
        suffix = original.suffix.lower()
        image_mime_type = {
            ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
            ".jpeg": "image/jpeg", ".jpg": "image/jpeg",
        }.get(suffix, "image/jpeg")
        if self.parser is not None:
            async def _vision_call(image_bytes: bytes, mime: str) -> tuple[dict[str, Any], str]:
                try:
                    result = await self.parser.analyze(
                        text=analysis_text, image_bytes=image_bytes, image_mime_type=mime,
                        ocr_text=ocr_text,
                    )
                except TypeError:
                    # Backward compatibility with parsers that don't yet accept OCR context.
                    result = await self.parser.analyze(text=analysis_text, image_bytes=image_bytes, image_mime_type=mime)
                result = dict(result or {})
                pname = str(result.pop("_vision_provider", "GEMINI") or "GEMINI").upper()
                return result, pname

            def _field_conf(raw: dict[str, Any], key: str) -> float:
                try:
                    fc = raw.get("field_confidences") or {}
                    return float(fc.get(key, raw.get("confidence") or 0.0) or 0.0)
                except Exception:
                    return 0.0

            def _weak(raw: dict[str, Any]) -> bool:
                amount = _int(raw.get("amount") or raw.get("final_amount") or raw.get("paid_amount"))
                dtype = str(raw.get("document_type") or raw.get("detected_type") or "UNKNOWN").upper()
                return amount <= 0 or _field_conf(raw, "amount") < 0.72 or dtype in {"", "UNKNOWN", "OTHER"}

            def _merge_retry(primary: dict[str, Any], retry: dict[str, Any]) -> dict[str, Any]:
                merged = dict(primary or {})
                pfc = dict(merged.get("field_confidences") or {})
                rfc = dict(retry.get("field_confidences") or {})
                protected = {"currency_detected"} if merged.get("currency_detected") else set()
                for key, value in retry.items():
                    if key in {"field_confidences", "confidence", "notes"} or key in protected:
                        continue
                    missing = merged.get(key) in (None, "", 0, False, "UNKNOWN", [])
                    pc = _field_conf(merged, key); rc = _field_conf(retry, key)
                    # Retry is allowed to replace only missing or weak AI fields. User edits
                    # are not part of this raw extraction object and are protected later in
                    # the approval/reprocess layer.
                    if missing or (pc < 0.65 and rc > pc + 0.05):
                        merged[key] = value
                        if key in rfc: pfc[key] = rfc[key]
                if retry.get("cheques") and (not merged.get("cheques") or len(retry.get("cheques") or []) > len(merged.get("cheques") or [])):
                    merged["cheques"] = retry["cheques"]
                if len(str(retry.get("visible_text") or "")) > len(str(merged.get("visible_text") or "")):
                    merged["visible_text"] = retry.get("visible_text")
                merged["field_confidences"] = pfc
                try: merged["confidence"] = max(float(merged.get("confidence") or 0), float(retry.get("confidence") or 0))
                except Exception: pass
                notes = " | ".join(x for x in (str(merged.get("notes") or "").strip(), str(retry.get("notes") or "").strip()) if x)
                if notes: merged["notes"] = notes
                return merged

            first_error = None
            try:
                raw_ai, provider_name = await _vision_call(original_bytes, image_mime_type)
                provider = f"{provider_name}_VISION+TESSERACT" if ocr_result.available else f"{provider_name}_VISION"
                vision_status = "OK"
            except Exception as exc:
                first_error = exc

            # A second visual pass uses a high-resolution, contrast/sharpness enhanced
            # image. It runs only when the first pass failed or returned weak critical
            # fields, which improves difficult bank slips without doubling every AI call.
            retry_needed = first_error is not None or _weak(raw_ai)
            if retry_needed:
                try:
                    retry_ai, retry_provider = await _vision_call(processed.read_bytes(), "image/jpeg")
                    if first_error is not None:
                        raw_ai = retry_ai
                    else:
                        raw_ai = _merge_retry(raw_ai, retry_ai)
                    provider = f"{retry_provider}_VISION_ENHANCED_RETRY" + ("+TESSERACT" if ocr_result.available else "")
                    vision_status = "OK"
                    raw_ai["vision_retry_used"] = True
                    raw_ai["vision_retry_reason"] = "PRIMARY_FAILED" if first_error is not None else "LOW_CONFIDENCE"
                except Exception as retry_exc:
                    raw_ai["vision_retry_used"] = True
                    raw_ai["vision_retry_error"] = f"{retry_exc.__class__.__name__}: {retry_exc}"
                    if first_error is not None:
                        # Both visual passes failed. Keep the item reviewable and expose
                        # diagnostics rather than silently pretending OCR read the receipt.
                        raw_ai = dict(caption_payload)
                        vision_status = "FAILED"
                        vision_error = f"primary={first_error.__class__.__name__}: {first_error}; retry={retry_exc.__class__.__name__}: {retry_exc}"
                        raw_ai["notes"] = ((raw_ai.get("notes") or "") + " | Vision failed after enhanced retry").strip(" |")
                        provider = "VISION_FAILED_AFTER_RETRY+TESSERACT" if ocr_result.available else "VISION_FAILED_AFTER_RETRY"
                if first_error is not None and vision_status == "OK":
                    vision_error = f"primary failed, enhanced retry succeeded: {first_error.__class__.__name__}"
        else:
            raw_ai = dict(caption_payload)

        # If Vision failed/not configured, OCR text can still materially improve
        # deterministic parsing. Caption is included in the local parse, so user
        # wording remains the strongest intent signal.
        if (vision_status != "OK" or provider in {"TESSERACT+LOCAL", "LOCAL"}) and ocr_text:
            ocr_payload = analyze_locally("\n".join(x for x in (caption, ocr_text) if x))
            for k, v in ocr_payload.items():
                if v not in (None, "", 0, False, "UNKNOWN") or not raw_ai.get(k):
                    raw_ai[k] = v

        payload = self.db.apply_learned_rules("\n".join((caption or "", ocr_text or "")), raw_ai)
        # Normalize Iranian banking receipts to TOMAN. Vision is instructed to
        # do this itself, but this deterministic guard prevents a clear RIAL
        # receipt from being posted ten times too large when a model returns the
        # printed value unchanged.
        currency=str(payload.get('currency_detected') or '').upper().strip()
        if currency in {'RIAL','IRR','ریال'}:
            src=_int(payload.get('source_amount'))
            cur=_int(payload.get('amount') or payload.get('final_amount'))
            if src<=0: src=cur
            already_converted = bool(src and cur and src >= cur*9 and src <= cur*11)
            if not already_converted and cur>0:
                payload['source_amount']=cur
                for key in ('amount','invoice_amount','final_amount','paid_amount','discount_amount'):
                    if _int(payload.get(key))>0: payload[key]=_int(payload.get(key))//10
            payload['currency_detected']='RIAL'
        elif not payload.get('currency_detected'):
            payload['currency_detected']='TOMAN'
        if not str(payload.get('payer_name') or '').strip() and str(payload.get('detected_type') or '').upper() in {'EXPENSE','OUTFLOW','CHEQUE','DOCUMENT'}:
            payload['payer_name']='تنخواه'
        if message_date_shamsi and not payload.get("event_date_shamsi"):
            payload["event_date_shamsi"] = message_date_shamsi.split()[0]
        ocr_amounts = extract_amount_candidates(ocr_text)
        caption_amount = _int(caption_payload.get("amount") or caption_payload.get("final_amount"))
        field_conf = self._field_confidences(payload, caption_amount=caption_amount, ocr_amounts=ocr_amounts)
        payload["field_confidences"] = field_conf
        payload["ocr_provider"] = ocr_result.provider if ocr_result.available else "NONE"
        payload["ocr_available"] = ocr_result.available
        payload["ocr_error"] = ocr_result.error
        payload["receipt_image_sha256"] = digest
        payload["vision_status"] = vision_status
        payload["vision_error"] = vision_error
        payload["vision_required"] = True
        # Preserve the exact caption/text attached to this receipt.  The UI uses
        # this field for the Wizard purpose (بابت) so nearby Telegram context
        # never leaks into the financial record.
        payload["receipt_caption"] = str(caption or "").strip()

        conflicts = self._conflicts(caption_payload=caption_payload, vision_payload=payload, ocr_amounts=ocr_amounts)
        if vision_status != "OK":
            conflicts.append({
                "field": "vision", "severity": "HIGH",
                "message": "تحلیل تصویری هوش مصنوعی انجام نشد؛ قبل از ثبت قطعی تصویر را بررسی کن.",
                "error": vision_error[:500],
            })
        amount = _int(payload.get("final_amount") or payload.get("amount"))
        dup = self.db.find_receipt_duplicate_candidates(amount=amount, description=str(payload.get("description") or caption))
        # Exact image-hash reuse is a very strong duplicate signal, even if the
        # caption or OCR amount differs.
        try:
            with self.db.read() as con:
                same = con.execute(
                    "SELECT pending_id,document_type,provider FROM receipt_analyses WHERE image_sha256=? AND pending_id<>? ORDER BY created_at",
                    (digest, pending_id),
                ).fetchall()
            for row in same:
                dup.insert(0, {
                    "entity_type": "PENDING_IMAGE", "entity_id": row["pending_id"], "amount": amount,
                    "event_date": "", "counterparty": "", "description": "همان تصویر قبلاً دریافت شده",
                    "match_score": 100,
                })
            if same:
                conflicts.append({"field": "image_sha256", "severity": "HIGH", "message": "همان تصویر رسید قبلاً دریافت شده است."})
        except Exception:
            pass
        status = "NEEDS_REVIEW" if (
            vision_status != "OK" or conflicts or field_conf.get("amount", 0) < 0.80
            or str(payload.get("detected_type") or "UNKNOWN") == "UNKNOWN"
        ) else "ANALYZED"
        self.db.upsert_receipt_analysis(
            pending_id=pending_id, provider=provider, document_type=str(payload.get("document_type") or "OTHER"),
            image_path=str(original), image_sha256=digest, ocr_text=ocr_text, raw_ai=raw_ai,
            field_confidences=field_conf, conflicts=conflicts, duplicate_candidates=dup, status=status,
        )
        return {
            "payload": payload, "provider": provider, "ocr_text": ocr_text, "ocr_available": ocr_result.available,
            "conflicts": conflicts, "duplicate_candidates": dup, "image_path": str(original), "image_sha256": digest,
            "status": status,
        }

    def learn_from_correction(self, *, source_text: str, before: dict[str, Any], after: dict[str, Any]) -> int:
        """Store only conservative, explicit aliases from user corrections.

        We learn counterparty -> category/stage links, not amounts/dates.
        """
        count = 0
        tokens = []
        for key in ("receiver_name", "payer_name"):
            value = str(after.get(key) or before.get(key) or "").strip()
            if len(value) >= 3:
                tokens.append(value)
        for pattern in tokens:
            for field in ("expense_category", "construction_stage"):
                b, a = str(before.get(field) or "").strip(), str(after.get(field) or "").strip()
                if a and a != b:
                    self.db.upsert_learned_rule(rule_type="COUNTERPARTY_ALIAS", pattern=pattern, target_field=field, target_value=a)
                    count += 1
        return count
