from __future__ import annotations

import asyncio
import html
import logging
import re
from datetime import datetime
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

CONFIG = s7.CONFIG
DB = s7.DB
LOANS = LoanService(DB)
LOAN_REMINDER_TASK = None

logging.getLogger("httpx").setLevel(logging.WARNING)
configure_telegram_network_logging()
log = logging.getLogger("peymaan.stage10")


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


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat or user.id != CONFIG.admin_user_id or chat.type not in {"group", "supergroup"}:
        return
    text = message.caption or message.text or ""
    kind = _loan_message_kind(text)
    if not kind:
        await s6.handle_group_message(update, context)
        return
    if not await s6._maybe_learn_group(chat.id, context):
        return
    if CONFIG.require_test_tag and CONFIG.test_tag not in text:
        return
    if DB.get_telegram_message(chat.id, message.message_id):
        return
    date_naive = message.date.replace(tzinfo=None)
    shamsi = jdatetime.datetime.fromgregorian(datetime=date_naive)
    message_date = shamsi.strftime("%Y/%m/%d %H:%M")
    DB.register_telegram_message(
        chat_id=chat.id, message_id=message.message_id, raw_text=text,
        content_type="PHOTO" if message.photo else "TEXT", message_date=message_date, state="PENDING_REVIEW"
    )
    private_id = await _private_id()
    if message.photo:
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


async def post_init(application):
    global LOAN_REMINDER_TASK
    await s7.post_init(application)
    try:
        created = await asyncio.to_thread(LOANS.ensure_reminders)
        log.info("Loan reminder bootstrap OK: created=%s", created)
    except Exception as exc:
        log.warning("Loan reminder bootstrap failed: %s", exc)
    LOAN_REMINDER_TASK = asyncio.create_task(loan_reminder_worker(application), name="peymaan-loan-reminders")


async def post_shutdown(application):
    global LOAN_REMINDER_TASK
    if LOAN_REMINDER_TASK:
        LOAN_REMINDER_TASK.cancel()
        try:
            await LOAN_REMINDER_TASK
        except asyncio.CancelledError:
            pass
        LOAN_REMINDER_TASK = None
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
    app.add_handler(CallbackQueryHandler(s6.handle_callback, pattern=r"^s5_(ok|no|edit|postedit|delete|deleteyes|deletecancel|revok|revno)\|"))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, s6.handle_private_edit_text), group=1)
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.ChatType.GROUPS & (filters.TEXT | filters.PHOTO), handle_edited_group_message))
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & filters.ChatType.GROUPS & (filters.TEXT | filters.PHOTO), handle_group_message))
    app.add_error_handler(application_error_handler)
    log.info("Stage 13 bot starting. DB=%s", CONFIG.db_path)
    app.run_polling(timeout=POLLING_TIMEOUT, bootstrap_retries=-1, drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
