from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

import jdatetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import NetworkError, TimedOut
from telegram_resilience import (
    CONNECT_TIMEOUT, READ_TIMEOUT, WRITE_TIMEOUT, POOL_TIMEOUT,
    GET_UPDATES_CONNECT_TIMEOUT, GET_UPDATES_READ_TIMEOUT,
    GET_UPDATES_WRITE_TIMEOUT, GET_UPDATES_POOL_TIMEOUT,
    CONNECTION_POOL_SIZE, GET_UPDATES_CONNECTION_POOL_SIZE, POLLING_TIMEOUT,
    configure_telegram_network_logging,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import telegram_stage6 as s6
import telegram_stage7 as s7
from loan_input import parse_loan_form, validate_loan_form
from loan_service import LoanService
from local_fallback_parser import analyze_locally
from telegram_history_import import list_imported_pending
from receipt_intelligence import ReceiptIntelligenceService
from approval_service import ApprovalCenterService
from receipt_ai_provider import build_receipt_vision_parser
from ai_parser import apply_explicit_note_title
from telegram_album import prepare_album_entries, telegram_document_kind

CONFIG = s7.CONFIG
DB = s7.DB
LOANS = LoanService(DB)
LOAN_REMINDER_TASK = None
INTEGRATION_EVENT_TASK = None
RECEIPT_PARSER = build_receipt_vision_parser(Path(__file__).resolve().parent, gemini_api_key=CONFIG.gemini_api_key, gemini_model=CONFIG.gemini_model)
RECEIPTS = ReceiptIntelligenceService(DB, Path(__file__).resolve().parent, parser=RECEIPT_PARSER)
APPROVAL = ApprovalCenterService(DB, Path(__file__).resolve().parent, parser=RECEIPT_PARSER)
_MEDIA_ALBUMS: dict[tuple[int, str], list[tuple[Update, ContextTypes.DEFAULT_TYPE]]] = {}
_MEDIA_ALBUM_TASKS: dict[tuple[int, str], asyncio.Task] = {}

logging.getLogger("httpx").setLevel(logging.WARNING)
configure_telegram_network_logging()
log = logging.getLogger("peymaan.stage15")

RUNTIME_DIR = Path(__file__).resolve().parent / "runtime"
INBOUND_HEARTBEAT_FILE = RUNTIME_DIR / "telegram_inbound_last.json"
RECEIPT_ERROR_FILE = RUNTIME_DIR / "telegram_receipt_last_error.json"

def _write_runtime_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp=path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        log.debug("Runtime status write failed for %s: %s", path.name, exc)

def _record_inbound(message, chat_id: int, *, state: str = "ACCEPTED") -> None:
    # Diagnostics-only heartbeat - must never be able to take down real
    # message handling. It already did once: a missing tzdata package made
    # ZoneInfo("Asia/Tehran") raise, which propagated straight through this
    # (uncaught) into _handle_regular_financial_message/handle_group_message,
    # aborting every single inbound group message before classification.
    try:
        content = "PHOTO" if getattr(message, "photo", None) else ("DOCUMENT" if getattr(message, "document", None) else "TEXT")
        _write_runtime_json(INBOUND_HEARTBEAT_FILE, {
            "timestamp": datetime.now(ZoneInfo(os.getenv("PEYMAAN_TIMEZONE", "Asia/Tehran"))).isoformat(),
            "chat_id": int(chat_id),
            "message_id": int(getattr(message, "message_id", 0) or 0),
            "content_type": content,
            "state": state,
        })
    except Exception:
        log.exception("_record_inbound heartbeat write failed - continuing without it")

def _record_receipt_error(message, chat_id: int, pending_id: str, exc: Exception) -> None:
    try:
        _write_runtime_json(RECEIPT_ERROR_FILE, {
            "timestamp": datetime.now(ZoneInfo(os.getenv("PEYMAAN_TIMEZONE", "Asia/Tehran"))).isoformat(),
            "chat_id": int(chat_id),
            "message_id": int(getattr(message, "message_id", 0) or 0),
            "pending_id": str(pending_id or ""),
            "error": f"{exc.__class__.__name__}: {exc}"[:1000],
        })
    except Exception:
        log.exception("_record_receipt_error heartbeat write failed - continuing without it")


def fmt_money(value: Any) -> str:
    try:
        return f"{int(value or 0):,} تومان"
    except Exception:
        return "-"


def _norm(text: str) -> str:
    return (text or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ").strip().lower()


def _loan_message_kind(text: str) -> str | None:
    t = _norm(text)
    if "وام" not in t and "تسهیلات" not in t:
        return None
    if any(x in t for x in ("قسط", "اقساط", "بازپرداخت", "باز پرداخت", "تسویه وام")):
        return "INSTALLMENT"
    if any(x in t for x in ("#ورودی", "ورودی", "دریافت", "گرفتم", "گرفتیم", "واریز", "تسهیلات")):
        return "RECEIVE"
    return None


def _infer_lender(text: str) -> str:
    t = (text or "").replace("ي", "ی").replace("ك", "ک")
    m = re.search(r"(بانک\s+[آ-یA-Za-z0-9_-]+)", t)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?:از|وام‌دهنده|وام دهنده)\s+([آ-یA-Za-z0-9_-]{2,30})", t)
    return m.group(1).strip() if m else ""


def _today_shamsi() -> str:
    return jdatetime.date.today().strftime("%Y/%m/%d")


def _loan_form_help(prefill: dict[str, Any] | None = None) -> str:
    p = prefill or {}
    lender = p.get("lender_name") or ""
    principal = p.get("principal_amount") or ""
    net = p.get("net_received_amount") or principal or ""
    rec_date = p.get("received_date_shamsi") or _today_shamsi()
    return (
        "🏦 <b>تکمیل مشخصات وام</b>\n"
        "این فرم را تکمیل و برای من بفرست. مبلغ واقعی واریزی همان عددی است که وارد تنخواه می‌شود.\n\n"
        "<pre>بانک / وام‌دهنده: " + html.escape(str(lender)) + "\n"
        "نوع وام: وام بانکی\n"
        "اصل وام: " + html.escape(str(principal)) + "\n"
        "مبلغ واقعی واریزی: " + html.escape(str(net)) + "\n"
        "تاریخ دریافت: " + html.escape(str(rec_date)) + "\n"
        "نرخ سود: \n"
        "کل سود: \n"
        "کارمزد: \n"
        "تعداد اقساط: \n"
        "مبلغ هر قسط: \n"
        "تاریخ اولین قسط: \n"
        "ضامنین: \n"
        "وثیقه: \n"
        "شماره قرارداد: \n"
        "توضیحات: </pre>\n"
        "بعد از ارسال فرم، پیش‌نمایش و دکمه تأیید می‌آید."
    )


def _loan_preview(d: dict[str, Any]) -> str:
    total_repayment = int(d.get("principal_amount") or 0) + int(d.get("total_interest") or 0) + int(d.get("bank_fees") or 0)
    return (
        "🏦 <b>پیش‌نمایش ثبت وام</b>\n"
        f"وام‌دهنده: <b>{html.escape(str(d.get('lender_name') or '-'))}</b>\n"
        f"اصل وام: <b>{html.escape(fmt_money(d.get('principal_amount')))}</b>\n"
        f"واریزی واقعی به تنخواه: <b>{html.escape(fmt_money(d.get('net_received_amount')))}</b>\n"
        f"تاریخ دریافت: {html.escape(str(d.get('received_date_shamsi') or '-'))}\n"
        f"نرخ سود: {d.get('interest_rate') or 0:g}%\n"
        f"کل سود: {html.escape(fmt_money(d.get('total_interest')))}\n"
        f"کارمزد: {html.escape(fmt_money(d.get('bank_fees')))}\n"
        f"کل بازپرداخت: <b>{html.escape(fmt_money(total_repayment))}</b>\n"
        f"اقساط: {int(d.get('installment_count') or 0)} قسط × {html.escape(fmt_money(d.get('installment_amount')))}\n"
        f"اولین قسط: {html.escape(str(d.get('first_due_date_shamsi') or '-'))}\n"
        f"ضامنین: {html.escape(str(d.get('guarantors') or '-'))}\n"
        f"وثیقه: {html.escape(str(d.get('collateral') or '-'))}\n"
        f"شماره قرارداد: {html.escape(str(d.get('contract_number') or '-'))}\n\n"
        "با تأیید، فقط <b>مبلغ واقعی واریزی</b> به ورودی تنخواه اضافه می‌شود و مشخصات کامل در پرونده وام ثبت می‌شود."
    )


def _loan_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ ثبت وام و ورودی", callback_data="s9_loanok"),
        InlineKeyboardButton("❌ انصراف", callback_data="s9_loancancel"),
    ]])


async def _safe_send(bot, chat_id: int, text: str, *, retries: int = 3, **kwargs):
    delays = (0, 2, 5)
    last = None
    for attempt in range(max(1, retries)):
        if attempt:
            await asyncio.sleep(delays[min(attempt, len(delays)-1)])
        try:
            return await bot.send_message(
                chat_id=chat_id, text=text, read_timeout=READ_TIMEOUT, write_timeout=WRITE_TIMEOUT,
                connect_timeout=CONNECT_TIMEOUT, pool_timeout=POOL_TIMEOUT, **kwargs
            )
        except (TimedOut, NetworkError) as exc:
            last = exc
            log.warning("Telegram send retry %s/%s failed: %s", attempt+1, retries, exc)
    log.error("Telegram send failed after retries: %s", last)
    return None


async def _private_id() -> int:
    return int(await s6._get_admin_private_chat_id())


async def _start_loan_form(context: ContextTypes.DEFAULT_TYPE, *, origin: dict[str, Any] | None = None,
                           prefill: dict[str, Any] | None = None) -> None:
    context.user_data["stage9_loan_mode"] = "FORM"
    context.user_data["stage9_loan_origin"] = origin or {}
    context.user_data["stage9_loan_prefill"] = prefill or {}
    private_id = await _private_id()
    await _safe_send(context.bot, private_id, _loan_form_help(prefill), parse_mode="HTML")


async def loan_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    DB.set_setting("telegram_admin_private_chat_id", str(update.effective_chat.id))
    await _start_loan_form(context, prefill={"received_date_shamsi": _today_shamsi()})


async def loans_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    rows = await asyncio.to_thread(LOANS.list_loans)
    if not rows:
        await update.effective_message.reply_text("🏦 وام فعالی ثبت نشده است. برای ثبت وام: /loan")
        return
    lines = ["🏦 <b>وام‌های فعال</b>"]
    for r in rows[:20]:
        lines.append(
            f"• {html.escape(str(r.get('lender_name') or '-'))} | اصل {html.escape(fmt_money(r.get('principal_amount')))} | "
            f"پرداخت {html.escape(fmt_money(r.get('paid_total')))} | مانده <b>{html.escape(fmt_money(r.get('remaining_debt')))}</b> | "
            f"قسط بعدی {html.escape(str(r.get('next_due_shamsi') or '-'))}"
        )
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


async def loan_draft_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    d = context.user_data.get("stage9_loan_draft")
    if d:
        await update.effective_message.reply_text(_loan_preview(d), parse_mode="HTML", reply_markup=_loan_keyboard())
    elif context.user_data.get("stage9_loan_mode") == "FORM":
        await update.effective_message.reply_text(_loan_form_help(context.user_data.get("stage9_loan_prefill")), parse_mode="HTML")
    else:
        await update.effective_message.reply_text("پیش‌نویس وام فعالی وجود ندارد. /loan")


async def handle_stage9_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    mode = context.user_data.get("stage9_loan_mode")
    if mode == "FORM":
        d = parse_loan_form(update.effective_message.text or "")
        missing = validate_loan_form(d)
        if missing:
            await update.effective_message.reply_text(
                "⚠️ این موارد کامل نیست:\n• " + "\n• ".join(missing) + "\n\nفرم را اصلاح و دوباره ارسال کن."
            )
            return
        context.user_data["stage9_loan_draft"] = d
        context.user_data["stage9_loan_mode"] = "PREVIEW"
        await update.effective_message.reply_text(_loan_preview(d), parse_mode="HTML", reply_markup=_loan_keyboard())
        return
    # Stage 7 sale/receipt forms remain unchanged.
    await s7.handle_stage7_private_text(update, context)


def _active_installments(loan_id: str) -> list[dict[str, Any]]:
    return [r for r in LOANS.list_installments(loan_id) if r.get("status") in {"UPCOMING", "DUE", "PARTIALLY_PAID", "OVERDUE"}]


async def _prepare_installment_preview(context: ContextTypes.DEFAULT_TYPE, loan_id: str) -> None:
    origin = context.user_data.get("stage9_loanpay_origin") or {}
    amount = int(origin.get("amount") or 0)
    rows = await asyncio.to_thread(_active_installments, loan_id)
    private_id = await _private_id()
    if not rows:
        await _safe_send(context.bot, private_id, "✅ این وام قسط باز ندارد.")
        return
    ins = rows[0]
    remain = max(0, int(ins.get("amount") or 0) - int(ins.get("paid_amount") or 0))
    if amount <= 0:
        await _safe_send(context.bot, private_id, "⚠️ مبلغ قسط از پیام تشخیص داده نشد. پرداخت را از تب «وام‌ها» ثبت کن.")
        return
    if amount > remain:
        await _safe_send(
            context.bot, private_id,
            f"⚠️ مبلغ پیام ({fmt_money(amount)}) از مانده قسط بعدی ({fmt_money(remain)}) بیشتر است. برای تقسیم روی چند قسط از تب «وام‌ها» استفاده کن."
        )
        return
    loan = await asyncio.to_thread(LOANS.get_loan, loan_id)
    draft = {
        "loan_id": loan_id,
        "loan_installment_id": ins["loan_installment_id"],
        "installment_number": ins["installment_number"],
        "due_date_shamsi": ins.get("due_date_shamsi") or "-",
        "amount": amount,
        "remaining_before": remain,
        "lender_name": (loan or {}).get("lender_name") or "-",
        "paid_date_shamsi": origin.get("paid_date_shamsi") or _today_shamsi(),
        "description": origin.get("raw_text") or "پرداخت قسط وام",
    }
    context.user_data["stage9_loanpay_draft"] = draft
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ ثبت پرداخت قسط", callback_data="s9_payok"),
        InlineKeyboardButton("❌ انصراف", callback_data="s9_paycancel"),
    ]])
    text = (
        "💸 <b>پیش‌نمایش پرداخت قسط وام</b>\n"
        f"وام‌دهنده: <b>{html.escape(str(draft['lender_name']))}</b>\n"
        f"قسط: {draft['installment_number']}\n"
        f"سررسید: {html.escape(str(draft['due_date_shamsi']))}\n"
        f"مبلغ پرداخت: <b>{html.escape(fmt_money(amount))}</b>\n"
        f"مانده قبل از پرداخت: {html.escape(fmt_money(remain))}\n"
        f"تاریخ پرداخت: {html.escape(str(draft['paid_date_shamsi']))}\n\n"
        "این پرداخت خروجی غیرساخت است و حقوق مدیر پروژه ایجاد نمی‌کند."
    )
    await _safe_send(context.bot, private_id, text, parse_mode="HTML", reply_markup=kb)


async def _start_installment_flow(message, context: ContextTypes.DEFAULT_TYPE, message_date_shamsi: str) -> None:
    text = message.caption or message.text or ""
    amount = int(analyze_locally(text).get("amount") or 0)
    loans = await asyncio.to_thread(LOANS.list_loans)
    private_id = await _private_id()
    if not loans:
        await _safe_send(context.bot, private_id, "⚠️ پیام پرداخت قسط تشخیص داده شد، ولی هیچ وام فعالی در سیستم وجود ندارد. ابتدا /loan")
        return
    norm = _norm(text)
    matched = [r for r in loans if _norm(str(r.get("lender_name") or "")) and _norm(str(r.get("lender_name") or "")) in norm]
    if not matched:
        # Match on distinctive lender tokens too (e.g. 'ملت' inside 'بانک ملت').
        for r in loans:
            tokens = [x for x in _norm(str(r.get("lender_name") or "")).split() if x not in {"بانک", "موسسه", "مؤسسه"}]
            if tokens and all(t in norm for t in tokens):
                matched.append(r)
    candidates = matched or loans
    context.user_data["stage9_loanpay_origin"] = {
        "chat_id": message.chat_id, "message_id": message.message_id,
        "raw_text": text, "amount": amount, "paid_date_shamsi": message_date_shamsi,
    }
    if len(candidates) == 1:
        await _prepare_installment_preview(context, candidates[0]["loan_id"])
        return
    buttons = []
    for r in candidates[:12]:
        label = f"{r.get('lender_name') or 'وام'} | مانده {fmt_money(r.get('remaining_debt'))}"
        buttons.append([InlineKeyboardButton(label[:58], callback_data=f"s9_paypick|{r['loan_id']}")])
    await _safe_send(
        context.bot, private_id,
        "💸 پرداخت قسط تشخیص داده شد. این پرداخت مربوط به کدام وام است؟",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def handle_stage9_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.from_user or q.from_user.id != CONFIG.admin_user_id:
        return
    data = q.data or ""
    await q.answer()
    if data == "s9_loancancel":
        context.user_data.pop("stage9_loan_draft", None)
        context.user_data.pop("stage9_loan_origin", None)
        context.user_data.pop("stage9_loan_mode", None)
        await q.edit_message_text("❌ ثبت وام لغو شد.")
        return
    if data == "s9_loanok":
        d = context.user_data.get("stage9_loan_draft")
        if not d:
            await q.edit_message_text("⚠️ پیش‌نویس وام پیدا نشد. /loandraft")
            return
        origin = context.user_data.get("stage9_loan_origin") or {}
        try:
            loan = await asyncio.to_thread(
                LOANS.create_loan, **d, source="TELEGRAM", register_cash=True,
                telegram_chat_id=origin.get("chat_id"), telegram_message_id=origin.get("message_id")
            )
            await asyncio.to_thread(LOANS.ensure_reminders)
        except Exception as exc:
            await q.edit_message_text(f"❌ ثبت وام انجام نشد: {html.escape(str(exc))}", parse_mode="HTML")
            return
        if origin.get("chat_id") and origin.get("message_id"):
            try:
                DB.update_telegram_message(
                    chat_id=origin["chat_id"], message_id=origin["message_id"], state="APPROVED",
                    linked_entity_type="LOAN", linked_entity_id=loan["loan_id"], reaction_state="NONE"
                )
                if CONFIG.enable_reaction_in_test:
                    ok, _ = await s6._try_set_check_reaction(context, origin["chat_id"], origin["message_id"])
                    if ok:
                        DB.update_telegram_message(chat_id=origin["chat_id"], message_id=origin["message_id"], reaction_state="CHECKED")
            except Exception as exc:
                log.warning("Loan posted but group reaction/state update failed: %s", exc)
        context.user_data.pop("stage9_loan_draft", None)
        context.user_data.pop("stage9_loan_origin", None)
        context.user_data.pop("stage9_loan_mode", None)
        await q.edit_message_text(
            "✅ <b>وام ثبت شد.</b>\n"
            f"وام‌دهنده: {html.escape(str(loan.get('lender_name') or '-'))}\n"
            f"ورودی واقعی تنخواه: <b>{html.escape(fmt_money(loan.get('net_received_amount')))}</b>\n"
            f"تعداد اقساط: {loan.get('installment_count') or 0}\n"
            f"Loan ID: <code>{html.escape(str(loan.get('loan_id')))}</code>", parse_mode="HTML"
        )
        return
    if data.startswith("s9_paypick|"):
        _, loan_id = data.split("|", 1)
        await _prepare_installment_preview(context, loan_id)
        return
    if data == "s9_paycancel":
        context.user_data.pop("stage9_loanpay_draft", None)
        context.user_data.pop("stage9_loanpay_origin", None)
        await q.edit_message_text("❌ ثبت پرداخت قسط لغو شد.")
        return
    if data == "s9_payok":
        d = context.user_data.get("stage9_loanpay_draft")
        origin = context.user_data.get("stage9_loanpay_origin") or {}
        if not d:
            await q.edit_message_text("⚠️ پیش‌نویس پرداخت پیدا نشد.")
            return
        try:
            result = await asyncio.to_thread(
                LOANS.pay_installment, d["loan_installment_id"], amount=d["amount"],
                paid_date_shamsi=d["paid_date_shamsi"], source="TELEGRAM", description=d["description"],
                telegram_chat_id=origin.get("chat_id"), telegram_message_id=origin.get("message_id")
            )
        except Exception as exc:
            await q.edit_message_text(f"❌ ثبت پرداخت انجام نشد: {html.escape(str(exc))}", parse_mode="HTML")
            return
        if origin.get("chat_id") and origin.get("message_id"):
            try:
                DB.update_telegram_message(
                    chat_id=origin["chat_id"], message_id=origin["message_id"], state="APPROVED",
                    linked_entity_type="LOAN_INSTALLMENT", linked_entity_id=d["loan_installment_id"], reaction_state="NONE"
                )
                if CONFIG.enable_reaction_in_test:
                    ok, _ = await s6._try_set_check_reaction(context, origin["chat_id"], origin["message_id"])
                    if ok:
                        DB.update_telegram_message(chat_id=origin["chat_id"], message_id=origin["message_id"], reaction_state="CHECKED")
            except Exception as exc:
                log.warning("Loan installment posted but reaction/state failed: %s", exc)
        context.user_data.pop("stage9_loanpay_draft", None)
        context.user_data.pop("stage9_loanpay_origin", None)
        await q.edit_message_text(
            "✅ <b>پرداخت قسط ثبت شد.</b>\n"
            f"مبلغ خروجی: <b>{html.escape(fmt_money(d['amount']))}</b>\n"
            f"وضعیت قسط: {html.escape(str(result.get('status') or '-'))}\n"
            "این مبلغ هزینه ساخت و مشمول حقوق مدیر پروژه نیست.", parse_mode="HTML"
        )


async def _approval_channels() -> str:
    value = (DB.get_setting("approval_channels", "BOTH") or "BOTH").upper()
    return value if value in {"BOTH", "GUI", "TELEGRAM"} else "BOTH"


async def _download_media_archive(message, context: ContextTypes.DEFAULT_TYPE, pending_id: str) -> str | None:
    """Download and archive Telegram images and common invoice documents.

    Stage 15 treats attachment preservation as mandatory: a Pending row may be
    created before networking, but a media download failure is explicitly
    recorded instead of silently turning the item into a text-only receipt.
    """
    file_id = file_unique_id = ""
    suffix = ".jpg"
    mime = "image/jpeg"
    is_image = False
    if message.photo:
        media = message.photo[-1]
        file_id, file_unique_id = media.file_id, media.file_unique_id
        is_image = True
    elif getattr(message, "document", None):
        media = message.document
        mime = str(getattr(media, "mime_type", None) or "application/octet-stream")
        name = str(getattr(media, "file_name", None) or "")
        suffix = Path(name).suffix.lower()
        kind = telegram_document_kind(mime, name, getattr(media, 'file_size', 0))
        if kind is None:
            if int(getattr(media, 'file_size', 0) or 0) > 20 * 1024 * 1024:
                log.warning('Telegram supporting document exceeds the 20 MB archive limit: %s', name)
            return None
        is_image = kind == 'IMAGE'
        file_id, file_unique_id = media.file_id, media.file_unique_id
        suffix = suffix or {
            "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf",
        }.get(mime.lower(), ".jpg" if is_image else ".bin")
    else:
        return None

    last_exc = None
    for attempt in range(3):
        try:
            tg_file = await context.bot.get_file(file_id)
            temp_dir = Path(__file__).resolve().parent / "data" / "tmp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp = temp_dir / f"{file_unique_id}{suffix}"
            await tg_file.download_to_drive(custom_path=temp)
            try:
                archived, _ = RECEIPTS.archive_file(temp)
                DB.attach_file_to_pending(
                    pending_id=pending_id, local_path=str(archived), mime_type=mime,
                    document_type="RECEIPT" if is_image else "SUPPORTING_DOCUMENT",
                    telegram_file_id=file_id,
                    telegram_file_unique_id=file_unique_id,
                )
                return str(archived)
            finally:
                try: temp.unlink(missing_ok=True)
                except Exception: pass
        except (TimedOut, NetworkError) as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep((2, 5)[attempt])
        except Exception as exc:
            last_exc = exc
            break
    if last_exc:
        DB.upsert_receipt_analysis(
            pending_id=pending_id, provider="TELEGRAM_MEDIA_DOWNLOAD_FAILED", document_type="OTHER",
            field_confidences={}, conflicts=[{
                "field":"media", "severity":"HIGH",
                "message":"دریافت سند از Telegram انجام نشد؛ در مرکز تأیید دوباره تلاش یا فایل را دستی بررسی کن.",
                "error":f"{last_exc.__class__.__name__}: {last_exc}"[:500],
            }], status="NEEDS_REVIEW",
        )
    return None


async def _send_private_review_if_enabled(message, context: ContextTypes.DEFAULT_TYPE, pending_id: str, payload: dict[str, Any]) -> None:
    if await _approval_channels() not in {"BOTH", "TELEGRAM"}:
        return
    await s6._send_review(message, context, pending_id, payload)


async def _handle_regular_financial_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        log.debug("GROUP UPDATE IGNORED | missing effective message/user/chat")
        return
    if user.id != CONFIG.admin_user_id:
        log.info("GROUP MESSAGE IGNORED | unauthorized user=%s expected=%s chat=%s message=%s", user.id, CONFIG.admin_user_id, chat.id, message.message_id)
        return
    if chat.type not in {"group", "supergroup"}:
        log.debug("MESSAGE IGNORED | non-group chat type=%s chat=%s message=%s", chat.type, chat.id, message.message_id)
        return
    if not await s6._maybe_learn_group(chat.id, context):
        log.info("GROUP MESSAGE IGNORED | group mapping rejected chat=%s message=%s", chat.id, message.message_id)
        return
    text = message.caption or message.text or ""
    if CONFIG.require_test_tag and CONFIG.test_tag not in text:
        log.info("GROUP MESSAGE SKIPPED BY TEST TAG | chat=%s message=%s", chat.id, message.message_id)
        return
    log.info("GROUP MESSAGE ACCEPTED | chat=%s message=%s content=%s", chat.id, message.message_id, "PHOTO" if message.photo else ("DOCUMENT" if getattr(message,"document",None) else "TEXT"))
    _record_inbound(message, chat.id)
    if DB.get_telegram_message(chat.id, message.message_id):
        log.info("Duplicate Telegram update ignored: %s/%s", chat.id, message.message_id)
        return

    date_local = message.date.astimezone(ZoneInfo(os.getenv('PEYMAAN_TIMEZONE','Asia/Tehran'))) if getattr(message.date,'tzinfo',None) else message.date
    date_naive = date_local.replace(tzinfo=None)
    shamsi = jdatetime.datetime.fromgregorian(datetime=date_naive)
    message_date = shamsi.strftime("%Y/%m/%d %H:%M")

    if message.photo or (getattr(message, "document", None) and str(getattr(message.document, "mime_type", "") or "").lower().startswith("image/")):
        # Create the Pending row first, before any slow OCR/AI call. This makes
        # every receipt recoverable in the GUI even if AI/network fails midway.
        provisional = analyze_locally(text)
        provisional["event_date_shamsi"] = message_date.split()[0]
        provisional["notes"] = ((provisional.get("notes") or "") + " | تصویر در حال تحلیل رسید است").strip(" |")
        review = s6.WORKFLOW.receive_message(
            chat_id=chat.id, message_id=message.message_id, raw_text=text,
            content_type="PHOTO" if message.photo else "IMAGE_DOCUMENT", message_date=message_date, analysis=provisional,
        )
        image_path = None
        try:
            image_path = await _download_media_archive(message, context, review.pending_id)
            if image_path:
                intel = await RECEIPTS.analyze_archived(
                    pending_id=review.pending_id, caption=text, image_path=image_path,
                    message_date_shamsi=message_date,
                )
                # The caption's title («گزارش روزانه ...:») decides the category
                # whichever engine read the image.
                payload = apply_explicit_note_title(dict(intel["payload"]), text)
                detected = str(payload.get("detected_type") or "UNKNOWN").upper()
                status = "NEEDS_REVIEW" if intel.get("status") == "NEEDS_REVIEW" or detected == "UNKNOWN" else "PENDING_REVIEW"
                DB.update_pending(
                    review.pending_id, payload=payload, detected_type=detected,
                    confidence=float(payload.get("confidence") or 0), status=status,
                )
                DB.update_telegram_message(chat_id=chat.id, message_id=message.message_id, state=status)
            else:
                payload = provisional
        except Exception as exc:
            log.exception("Receipt intelligence failed; pending retained for GUI review: %s", exc)
            _record_receipt_error(message, chat.id, review.pending_id, exc)
            payload = dict(provisional)
            payload["notes"] = ((payload.get("notes") or "") + f" | Receipt engine error: {exc.__class__.__name__}").strip(" |")
            DB.update_pending(review.pending_id, payload=payload, status="NEEDS_REVIEW")
            DB.update_telegram_message(chat_id=chat.id, message_id=message.message_id, state="NEEDS_REVIEW")
        # Every receipt stays its own review item with only the text attached to
        # it; nearby messages are never joined to it.
        await _send_private_review_if_enabled(message, context, review.pending_id, payload)
        return

    # Text-only messages still use the proven deterministic/Gemini flow, but
    # private approval delivery obeys the Stage 14 approval-channel setting.
    payload = await s6._analyze_message_payload(message, context, text, message_date)
    payload = DB.apply_learned_rules(text, payload)
    # Applied after the learned rules: the title is the operator's own word
    # about this very message.
    payload = apply_explicit_note_title(payload, text)
    review = s6.WORKFLOW.receive_message(
        chat_id=chat.id, message_id=message.message_id, raw_text=text,
        content_type="DOCUMENT" if getattr(message, 'document', None) else "TEXT",
        message_date=message_date, analysis=payload,
    )
    if getattr(message, 'document', None):
        await _download_media_archive(message, context, review.pending_id)
    await _send_private_review_if_enabled(message, context, review.pending_id, review.payload)


async def handle_finance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Keep Telegram approval behavior while synchronizing Stage 14 receipt metadata."""
    data = (update.callback_query.data if update.callback_query else "") or ""
    try:
        action, pending_id = data.split("|", 1)
    except ValueError:
        return await s6.handle_callback(update, context)
    if action == 's5_ok':
        pending = DB.get_pending_item(pending_id)
        if pending and pending.get('status') == 'LINKED':
            if update.callback_query:
                await update.callback_query.answer(
                    'این پیام به رسید دیگری پیوست شده و جداگانه ثبت نمی‌شود.', show_alert=True,
                )
            return
    await s6.handle_callback(update, context)
    try:
        if action == "s5_ok":
            post = DB.get_financial_posting(pending_id)
            if post and str(post.get("status") or "ACTIVE") == "ACTIVE":
                if post.get("expense_id"):
                    DB.relink_pending_attachments(pending_id, entity_type="EXPENSE", entity_id=post["expense_id"])
                elif post.get("transaction_id"):
                    DB.relink_pending_attachments(pending_id, entity_type="TRANSACTION", entity_id=post["transaction_id"])
                elif post.get("cheque_id"):
                    DB.relink_pending_attachments(pending_id, entity_type="CHEQUE", entity_id=post["cheque_id"])
                DB.update_receipt_analysis_status(pending_id, "APPROVED")
        elif action == "s5_no":
            DB.update_receipt_analysis_status(pending_id, "REJECTED")
    except Exception as exc:
        log.warning("Stage 14 receipt metadata sync after Telegram callback failed: %s", exc)


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        log.debug("GROUP UPDATE IGNORED | missing effective message/user/chat")
        return
    if user.id != CONFIG.admin_user_id:
        log.info("GROUP MESSAGE IGNORED | unauthorized user=%s expected=%s chat=%s message=%s", user.id, CONFIG.admin_user_id, chat.id, message.message_id)
        return
    if chat.type not in {"group", "supergroup"}:
        log.debug("MESSAGE IGNORED | non-group chat type=%s chat=%s message=%s", chat.type, chat.id, message.message_id)
        return
    text = message.caption or message.text or ""
    kind = _loan_message_kind(text)
    if not kind:
        group_id = str(getattr(message, 'media_group_id', '') or '')
        if group_id:
            key = (int(chat.id), group_id)
            _MEDIA_ALBUMS.setdefault(key, []).append((update, context))
            old_task = _MEDIA_ALBUM_TASKS.get(key)
            if old_task and not old_task.done():
                old_task.cancel()
            _MEDIA_ALBUM_TASKS[key] = asyncio.create_task(_flush_media_album(key))
            return
        await _handle_regular_financial_message(update, context)
        return
    # Loan-specific guided forms remain intact in Stage 14.
    if not await s6._maybe_learn_group(chat.id, context):
        return
    if CONFIG.require_test_tag and CONFIG.test_tag not in text:
        log.info("GROUP MESSAGE SKIPPED BY TEST TAG | chat=%s message=%s", chat.id, message.message_id)
        return
    log.info("GROUP MESSAGE ACCEPTED | chat=%s message=%s content=%s", chat.id, message.message_id, "PHOTO" if message.photo else ("DOCUMENT" if getattr(message,"document",None) else "TEXT"))
    _record_inbound(message, chat.id)
    if DB.get_telegram_message(chat.id, message.message_id):
        return
    date_local = message.date.astimezone(ZoneInfo(os.getenv('PEYMAAN_TIMEZONE','Asia/Tehran'))) if getattr(message.date,'tzinfo',None) else message.date
    date_naive = date_local.replace(tzinfo=None)
    shamsi = jdatetime.datetime.fromgregorian(datetime=date_naive)
    message_date = shamsi.strftime("%Y/%m/%d %H:%M")
    DB.register_telegram_message(
        chat_id=chat.id, message_id=message.message_id, raw_text=text,
        content_type="PHOTO" if message.photo else ("IMAGE_DOCUMENT" if getattr(message, "document", None) else "TEXT"), message_date=message_date, state="PENDING_REVIEW"
    )
    private_id = await _private_id()
    if (message.photo or getattr(message, "document", None)) and await _approval_channels() in {"BOTH", "TELEGRAM"}:
        try:
            await context.bot.copy_message(chat_id=private_id, from_chat_id=chat.id, message_id=message.message_id)
        except Exception as exc:
            log.warning("Could not copy loan source photo: %s", exc)
    if kind == "RECEIVE":
        amount = int(analyze_locally(text).get("amount") or 0)
        prefill = {
            "lender_name": _infer_lender(text), "principal_amount": amount,
            "net_received_amount": amount, "received_date_shamsi": message_date.split()[0]
        }
        origin = {"chat_id": chat.id, "message_id": message.message_id, "raw_text": text}
        await _start_loan_form(context, origin=origin, prefill=prefill)
    else:
        await _start_installment_flow(message, context, message_date.split()[0])


#: How long Telegram's separate updates for one album are collected before the
#: album is processed. Each photo of an album is its own update and, on a slow
#: link, they can arrive seconds apart; 0.8 s split real albums in two.
ALBUM_SETTLE_SECONDS = 2.5
#: An album part arriving later than this after its album was processed is
#: treated as a new message (Telegram never delivers an album that late).
ALBUM_LATE_WINDOW_SECONDS = 600.0
#: key -> {'pending_id': str|None, 'lead_id': int, 'late': list, 'at': float}.
#: ``pending_id`` is None while the lead is still being analysed; parts that
#: arrive meanwhile wait in ``late`` and are attached as soon as it is known.
_MEDIA_ALBUM_STATE: dict[tuple[int, str], dict] = {}


def _album_text(item) -> str:
    return str(getattr(item, 'caption', None) or getattr(item, 'text', None) or '').strip()


async def _attach_album_items(key: tuple[int, str], items, pending: dict, lead_id: int, context) -> None:
    """Register every non-lead album message as another document of ``pending``."""
    pending_id = str(pending['pending_id'])
    captions = [_album_text(item) for item in items if _album_text(item)]
    if captions:
        fresh = DB.get_pending_item(pending_id) or pending
        payload = dict(fresh.get('payload') or {})
        known = list(payload.get('related_document_captions') or [])
        payload['related_document_captions'] = known + [c for c in captions if c not in known]
        DB.update_pending(pending_id, payload=payload)
    for item in items:
        if int(item.message_id) == int(lead_id):
            continue
        if DB.get_telegram_message(key[0], int(item.message_id)):
            continue
        local_date = item.date.astimezone(ZoneInfo(os.getenv('PEYMAAN_TIMEZONE', 'Asia/Tehran'))) if getattr(item.date, 'tzinfo', None) else item.date
        jalali = jdatetime.datetime.fromgregorian(datetime=local_date.replace(tzinfo=None)).strftime('%Y/%m/%d %H:%M')
        media = getattr(item, 'document', None)
        media_mime = str(getattr(media, 'mime_type', '') or '').lower()
        content_type = (
            'PHOTO' if getattr(item, 'photo', None)
            else 'IMAGE_DOCUMENT' if media_mime.startswith('image/')
            else 'DOCUMENT'
        )
        inserted = DB.register_telegram_message(
            chat_id=key[0], message_id=int(item.message_id), raw_text=_album_text(item),
            content_type=content_type, message_date=jalali, state=str(pending.get('status') or 'PENDING_REVIEW'),
        )
        if not inserted:
            continue
        DB.update_telegram_message(
            chat_id=key[0], message_id=int(item.message_id),
            linked_entity_type='PENDING', linked_entity_id=pending_id,
        )
        if getattr(item, 'photo', None) or media:
            archived = await _download_media_archive(item, context, pending_id)
            if not archived:
                log.warning('MEDIA ALBUM ATTACHMENT FAILED | chat=%s message=%s', key[0], item.message_id)


async def _flush_media_album(key: tuple[int, str]) -> None:
    """Coalesce Telegram's several updates for one photo album into one review row."""
    try:
        await asyncio.sleep(ALBUM_SETTLE_SECONDS)
    except asyncio.CancelledError:
        return
    entries = _MEDIA_ALBUMS.pop(key, [])
    _MEDIA_ALBUM_TASKS.pop(key, None)
    if not entries:
        return
    now = asyncio.get_running_loop().time()
    for old_key in [k for k, v in _MEDIA_ALBUM_STATE.items() if now - v['at'] > ALBUM_LATE_WINDOW_SECONDS]:
        _MEDIA_ALBUM_STATE.pop(old_key, None)
    messages = tuple(sorted((entry[0].effective_message for entry in entries if entry[0].effective_message),
                            key=lambda item: int(item.message_id)))
    state = _MEDIA_ALBUM_STATE.get(key)
    if state is not None:
        # A late part of an album already turned into a review row: one more
        # document of the same transaction, never a transaction of its own.
        if state['pending_id']:
            pending = DB.get_pending_item(state['pending_id'])
            if pending:
                await _attach_album_items(key, messages, pending, state['lead_id'], entries[0][1])
                log.info('MEDIA ALBUM LATE PART ATTACHED | chat=%s album=%s messages=%s pending=%s',
                         key[0], key[1], len(messages), state['pending_id'])
                return
        else:
            state['late'].extend(entries)
            return
    lead, _extras = prepare_album_entries(
        entries, require_tag=bool(CONFIG.require_test_tag), test_tag=str(CONFIG.test_tag or ''))
    if not lead:
        if CONFIG.require_test_tag:
            log.info('MEDIA ALBUM SKIPPED BY TEST TAG | chat=%s group=%s', key[0], key[1])
        return
    state = {'pending_id': None, 'lead_id': int(lead.message_id), 'late': [], 'at': now}
    _MEDIA_ALBUM_STATE[key] = state
    lead_update, lead_context = next(
        (u, c) for u, c in entries if u.effective_message and int(u.effective_message.message_id) == int(lead.message_id)
    )
    try:
        await _handle_regular_financial_message(lead_update, lead_context)
    finally:
        pending = DB.get_pending_by_message(key[0], int(lead.message_id))
        state['pending_id'] = str(pending['pending_id']) if pending else None
    if not pending:
        _MEDIA_ALBUM_STATE.pop(key, None)
        log.warning('MEDIA ALBUM LEAD DID NOT CREATE A REVIEW ROW | chat=%s message=%s', key[0], lead.message_id)
        return
    late = [entry[0].effective_message for entry in state['late'] if entry[0].effective_message]
    state['late'] = []
    items = tuple(sorted({int(m.message_id): m for m in (*messages, *late)}.values(),
                         key=lambda item: int(item.message_id)))
    await _attach_album_items(key, items, pending, int(lead.message_id), lead_context)
    log.info('MEDIA ALBUM GROUPED | chat=%s album=%s messages=%s pending=%s',
             key[0], key[1], len(items), state['pending_id'])


async def handle_edited_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.edited_message
    if not message or not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    row = DB.get_telegram_message(message.chat_id, message.message_id)
    if row and row.get("linked_entity_type") in {"LOAN", "LOAN_INSTALLMENT"}:
        DB.update_telegram_message(chat_id=message.chat_id, message_id=message.message_id, raw_text=message.caption or message.text or "", mark_edited=True)
        private_id = await _private_id()
        await _safe_send(
            context.bot, private_id,
            "⚠️ پیام مربوط به وام/قسط بعد از ثبت ویرایش شد. رکورد مالی به‌صورت خودکار تغییر نکرد تا سابقه خراب نشود. ویرایش را از تب «وام‌ها» در GUI انجام بده."
        )
        return
    await s6.handle_edited_group_message(update, context)


async def start_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await s7.start_private(update, context)
    if update.effective_user and update.effective_user.id == CONFIG.admin_user_id and update.effective_chat and update.effective_chat.type == "private":
        await update.effective_message.reply_text(
            "🏦 Stage 9: /loan ثبت وام | /loans فهرست وام‌ها | /loandraft بازیابی فرم وام\n"
            "پیام «ورودی وام» در گروه نیز به‌صورت خودکار فرم تکمیل وام را در خصوصی باز می‌کند."
        )


async def _send_due_loan_reminders_once(application) -> dict[str, int]:
    created = await asyncio.to_thread(LOANS.ensure_reminders)
    rows = await asyncio.to_thread(LOANS.due_reminders, datetime.now())
    private_id = await _private_id()
    sent = failed = 0
    for r in rows[:30]:
        remain = max(0, int(r.get("amount") or 0) - int(r.get("paid_amount") or 0))
        text = (
            "🏦 <b>یادآوری قسط وام</b>\n"
            f"وام‌دهنده: {html.escape(str(r.get('lender_name') or '-'))}\n"
            f"قسط: {r.get('installment_number') or '-'}\n"
            f"سررسید: <b>{html.escape(str(r.get('due_date_shamsi') or '-'))}</b>\n"
            f"مانده قسط: <b>{html.escape(fmt_money(remain))}</b>"
        )
        try:
            msg = await _safe_send(application.bot, private_id, text, parse_mode="HTML")
            if not msg:
                raise NetworkError("loan reminder delivery failed")
        except Exception as exc:
            await asyncio.to_thread(DB.log_reminder_failure, r["reminder_id"], channel="TELEGRAM", details=str(exc))
            failed += 1
        else:
            await asyncio.to_thread(DB.mark_reminder_sent, r["reminder_id"], channel="TELEGRAM", details="loan installment reminder")
            sent += 1
    return {"created": created, "sent": sent, "failed": failed}


async def loan_reminders_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    created = await asyncio.to_thread(LOANS.ensure_reminders)
    due = await asyncio.to_thread(LOANS.due_reminders, datetime.now())
    await update.effective_message.reply_text(
        f"🏦 Reminder وام‌ها فعال است.\nReminder جدید ساخته شد: {created}\nالان آماده ارسال: {len(due)}\nقاعده: ۳ روز قبل + روز سررسید + تا ۷ روز بعد."
    )


async def reminder_check_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    cheque = await s6.send_due_cheque_reminders_once(context.application)
    buyer = await s7.send_due_buyer_reminders_once(context.application)
    loan = await _send_due_loan_reminders_once(context.application)
    await update.effective_message.reply_text(
        "✅ Reminder check اجرا شد.\n"
        f"چک: {cheque}\nخریداران: {buyer}\nوام‌ها: {loan}"
    )


async def reminders_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    await s7.reminders_private(update, context)
    created = await asyncio.to_thread(LOANS.ensure_reminders)
    due = await asyncio.to_thread(LOANS.due_reminders, datetime.now())
    await update.effective_message.reply_text(f"🏦 وام‌ها: {created} Reminder جدید | {len(due)} آماده ارسال")


async def loan_reminder_worker(application):
    while True:
        try:
            result = await _send_due_loan_reminders_once(application)
            if any(result.values()):
                log.info("Loan reminders: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Loan reminder worker crashed: %s", exc)
        await asyncio.sleep(CONFIG.reminder_check_interval_seconds)


async def _process_integration_events_once(application) -> int:
    rows = await asyncio.to_thread(DB.get_integration_events, limit=25)
    done = 0
    for ev in rows:
        try:
            pending_id = ev.get("pending_id")
            item = DB.get_pending_item(pending_id) if pending_id else None
            if not item:
                await asyncio.to_thread(DB.mark_integration_event, ev["event_id"], done=True)
                continue
            event_type = str(ev.get("event_type") or "")
            if event_type == "GUI_APPROVED":
                reaction_ok, _ = await s6._try_set_check_reaction(
                    type("C", (), {"bot": application.bot})(), item["telegram_chat_id"], item["telegram_message_id"]
                )
                if reaction_ok:
                    s6.WORKFLOW.mark_reaction(pending_id, True)
                private_id = await s6._get_admin_private_chat_id()
                source = DB.get_telegram_message(item["telegram_chat_id"], item["telegram_message_id"])
                mid = (source or {}).get("private_review_message_id")
                if private_id and mid:
                    try:
                        await application.bot.edit_message_text(
                            chat_id=private_id, message_id=int(mid),
                            text=f"✅ <b>در برنامه تأیید و ثبت شد.</b>\n<code>{pending_id}</code>",
                            parse_mode="HTML"
                        )
                    except Exception as exc:
                        log.warning("Could not update private review after GUI approval: %s", exc)
            elif event_type == "GUI_REJECTED":
                try:
                    await application.bot.set_message_reaction(item["telegram_chat_id"], item["telegram_message_id"], reaction=[])
                    s6.WORKFLOW.mark_reaction(pending_id, False)
                except Exception:
                    pass
                private_id = await s6._get_admin_private_chat_id()
                source = DB.get_telegram_message(item["telegram_chat_id"], item["telegram_message_id"])
                mid = (source or {}).get("private_review_message_id")
                if private_id and mid:
                    try:
                        await application.bot.edit_message_text(
                            chat_id=private_id, message_id=int(mid),
                            text=f"❌ <b>در برنامه رد شد؛ اثر مالی ندارد.</b>\n<code>{pending_id}</code>",
                            parse_mode="HTML"
                        )
                    except Exception as exc:
                        log.warning("Could not update private review after GUI rejection: %s", exc)
            await asyncio.to_thread(DB.mark_integration_event, ev["event_id"], done=True)
            done += 1
        except Exception as exc:
            await asyncio.to_thread(DB.mark_integration_event, ev["event_id"], done=False, error=f"{exc.__class__.__name__}: {exc}")
    return done


async def integration_event_worker(application):
    while True:
        try:
            await _process_integration_events_once(application)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Integration outbox worker error: %s", exc)
        await asyncio.sleep(3)


BOT_READY_FILE = Path(__file__).resolve().parent / "runtime" / "telegram_bot_ready.flag"

async def post_init(application):
    global LOAN_REMINDER_TASK, INTEGRATION_EVENT_TASK
    await s7.post_init(application)
    try:
        BOT_READY_FILE.parent.mkdir(parents=True, exist_ok=True)
        BOT_READY_FILE.write_text(
            f"READY\nDB={CONFIG.db_path}\nGROUP={CONFIG.group_chat_id}\nADMIN={CONFIG.admin_user_id}\nTEST_TAG={CONFIG.require_test_tag}\n",
            encoding="utf-8"
        )
        log.info("BOT READY | group=%s | admin=%s | require_test_tag=%s", CONFIG.group_chat_id, CONFIG.admin_user_id, CONFIG.require_test_tag)
    except Exception as exc:
        log.warning("Could not write bot-ready flag: %s", exc)
    try:
        created = await asyncio.to_thread(LOANS.ensure_reminders)
        log.info("Loan reminder bootstrap OK: created=%s", created)
    except Exception as exc:
        log.warning("Loan reminder bootstrap failed: %s", exc)
    LOAN_REMINDER_TASK = asyncio.create_task(loan_reminder_worker(application), name="peymaan-loan-reminders")
    INTEGRATION_EVENT_TASK = asyncio.create_task(integration_event_worker(application), name="peymaan-gui-approval-outbox")


async def post_shutdown(application):
    global LOAN_REMINDER_TASK, INTEGRATION_EVENT_TASK
    try:
        BOT_READY_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    for task in (LOAN_REMINDER_TASK, INTEGRATION_EVENT_TASK):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    LOAN_REMINDER_TASK = None
    INTEGRATION_EVENT_TASK = None
    await s7.post_shutdown(application)


async def application_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, (TimedOut, NetworkError)):
        log.warning("Telegram network error handled: %s", err)
        return
    log.error("Unhandled Stage 10 Telegram error", exc_info=(type(err), err, err.__traceback__) if err else None)



async def history_pending_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send historical Telegram-export pending items to the private review chat."""
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    try:
        limit=int(context.args[0]) if context.args else 10
    except Exception:
        limit=10
    limit=max(1,min(limit,20))
    rows=await asyncio.to_thread(list_imported_pending,DB,limit)
    if not rows:
        await update.effective_message.reply_text('✅ مورد تاریخیِ در انتظار بررسی نداریم.')
        return
    sent_count=0
    for row in rows:
        try:
            sent=await update.effective_message.reply_text(
                '🕘 <b>پیام تاریخی Import شده</b>\n'+s6.format_review(row.get('raw_text') or '',row.get('payload') or {},row['pending_id']),
                parse_mode='HTML',reply_markup=s6.review_keyboard(row['pending_id'])
            )
            try:s6.WORKFLOW.mark_private_review_message(row['pending_id'],sent.message_id)
            except Exception:pass
            sent_count+=1
        except (TimedOut,NetworkError):
            log.warning('Network interruption while sending historical review cards; retry /historypending later.')
            break
    await update.effective_message.reply_text(f'📚 {sent_count} مورد تاریخی برای بررسی ارسال شد. بعد از تأییدها دوباره /historypending بزن.')

def main():
    app = (
        ApplicationBuilder()
        .token(CONFIG.telegram_bot_token)
        .connection_pool_size(CONNECTION_POOL_SIZE)
        .connect_timeout(CONNECT_TIMEOUT).read_timeout(READ_TIMEOUT).write_timeout(WRITE_TIMEOUT).pool_timeout(POOL_TIMEOUT)
        .get_updates_connection_pool_size(GET_UPDATES_CONNECTION_POOL_SIZE)
        .get_updates_connect_timeout(GET_UPDATES_CONNECT_TIMEOUT).get_updates_read_timeout(GET_UPDATES_READ_TIMEOUT)
        .get_updates_write_timeout(GET_UPDATES_WRITE_TIMEOUT).get_updates_pool_timeout(GET_UPDATES_POOL_TIMEOUT)
        .http_version("1.1").get_updates_http_version("1.1")
        .post_init(post_init).post_shutdown(post_shutdown).build()
    )

    # Stage 9 loan flows
    app.add_handler(CommandHandler("loan", loan_private))
    app.add_handler(CommandHandler("loans", loans_private))
    app.add_handler(CommandHandler("loandraft", loan_draft_private))
    app.add_handler(CommandHandler("loanreminders", loan_reminders_private))
    app.add_handler(CallbackQueryHandler(handle_stage9_callback, pattern=r"^s9_"))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handle_stage9_private_text), group=0)

    # Stage 7 sales/receivables commands
    app.add_handler(CommandHandler("sales", s7.sales_private))
    app.add_handler(CommandHandler("sale", s7.sale_private))
    app.add_handler(CommandHandler("newsale", s7.new_sale_private))
    app.add_handler(CommandHandler("draft", s7.draft_private))
    app.add_handler(CommandHandler("receive", s7.receive_private))
    app.add_handler(CommandHandler("unmatched", s7.unmatched_private))
    app.add_handler(CommandHandler("buyerreminders", s7.buyer_reminders_private))
    app.add_handler(CallbackQueryHandler(s7.handle_stage7_callback, pattern=r"^s7_"))

    # Historical Telegram Desktop JSON review queue
    app.add_handler(CommandHandler("historypending", history_pending_private))

    # Existing finance/cheque workflow
    app.add_handler(CommandHandler("start", start_private))
    app.add_handler(CommandHandler("status", s7.status_private))
    app.add_handler(CommandHandler("sync", s6.sync_private))
    app.add_handler(CommandHandler("repairledger", s6.repair_ledger_private))
    app.add_handler(CommandHandler("rebuildsheets", s6.rebuild_sheets_private))
    app.add_handler(CommandHandler("reactiontest", s6.reaction_test_private))
    app.add_handler(CommandHandler("cheques", s6.cheques_private))
    app.add_handler(CommandHandler("reminders", reminders_private))
    app.add_handler(CommandHandler("remindercheck", reminder_check_private))
    app.add_handler(CallbackQueryHandler(s6.handle_cheque_callback, pattern=r"^s6_(cash|return|cancel)\|"))
    app.add_handler(CallbackQueryHandler(handle_finance_callback, pattern=r"^s5_(ok|no|edit|postedit|delete|deleteyes|deletecancel|revok|revno)\|"))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, s6.handle_private_edit_text), group=1)
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.ChatType.GROUPS & (filters.TEXT | filters.PHOTO), handle_edited_group_message))
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & filters.ChatType.GROUPS & (filters.TEXT | filters.PHOTO | filters.Document.ALL), handle_group_message))
    app.add_error_handler(application_error_handler)
    log.info("Stage 14 bot starting. DB=%s", CONFIG.db_path)
    app.run_polling(timeout=POLLING_TIMEOUT, bootstrap_retries=-1, drop_pending_updates=False, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
