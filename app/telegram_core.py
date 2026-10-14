from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import jdatetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReactionTypeEmoji, Update
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

from ai_parser import GeminiFinancialParser
from ai_parser import apply_explicit_note_title
from local_fallback_parser import analyze_locally
from edit_field_parser import parse_edit_fields
from config_loader import load_config
from finance_db import FinanceDB
from edit_normalizer import normalize_financial_edit
from telegram_approval_workflow import TelegramStage5Workflow
from sheet_sync import GoogleSheetsMirror

BASE_DIR = Path(__file__).resolve().parent
CONFIG = load_config(BASE_DIR)
DB = FinanceDB(CONFIG.db_path)
WORKFLOW = TelegramStage5Workflow(DB)
SHEETS = GoogleSheetsMirror(
    DB,
    spreadsheet_name=CONFIG.spreadsheet_name,
    credentials_file=CONFIG.google_credentials_file,
) if CONFIG.sheets_enabled else None
SHEET_TASK = None
REMINDER_TASK = None
SHEET_ASYNC_LOCK = asyncio.Lock()
PARSER = GeminiFinancialParser(CONFIG.gemini_api_key, CONFIG.gemini_model)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
configure_telegram_network_logging()
log = logging.getLogger("peymaan.stage6")


def fmt_money(value: Any) -> str:
    try:
        return f"{int(value or 0):,} تومان"
    except Exception:
        return "-"


def type_label(value: str) -> str:
    return {
        "EXPENSE": "هزینه ساخت",
        "INCOME": "ورودی تنخواه",
        "OUTFLOW": "خروجی غیرساخت",
        "CHEQUE": "چک",
        "DOCUMENT": "سند/مدرک",
        "UNKNOWN": "نامشخص",
    }.get(value, value or "نامشخص")


def payment_state_label(value: str) -> str:
    return {
        "PAID": "پرداخت کامل",
        "PARTIAL": "پرداخت جزئی",
        "UNPAID": "پرداخت‌نشده",
        "UNKNOWN": "نامشخص",
    }.get((value or "UNKNOWN").upper(), value or "نامشخص")


def review_keyboard(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ ثبت قطعی", callback_data=f"s5_ok|{pending_id}"),
        InlineKeyboardButton("✏️ ویرایش قبل از ثبت", callback_data=f"s5_edit|{pending_id}"),
        InlineKeyboardButton("❌ رد", callback_data=f"s5_no|{pending_id}"),
    ]])


def posted_keyboard(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✏️ اصلاح همین ثبت", callback_data=f"s5_postedit|{pending_id}"),
        InlineKeyboardButton("🗑 حذف ثبت", callback_data=f"s5_delete|{pending_id}"),
    ]])


def revision_keyboard(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأیید اصلاح", callback_data=f"s5_revok|{pending_id}"),
        InlineKeyboardButton("↩️ رد اصلاح", callback_data=f"s5_revno|{pending_id}"),
    ]])


def delete_confirm_keyboard(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⚠️ بله، حذف شود", callback_data=f"s5_deleteyes|{pending_id}"),
        InlineKeyboardButton("انصراف", callback_data=f"s5_deletecancel|{pending_id}"),
    ]])


def _payload_summary(payload: dict[str, Any]) -> str:
    return (
        f"نوع: {html.escape(type_label(str(payload.get('detected_type') or 'UNKNOWN')))}\n"
        f"مبلغ: {html.escape(fmt_money(payload.get('amount')))}\n"
        f"مبلغ نهایی: {html.escape(fmt_money(payload.get('final_amount')))}\n"
        f"پرداخت‌شده: {html.escape(fmt_money(payload.get('paid_amount')))}\n"
        f"روش پرداخت: {html.escape(str(payload.get('payment_method') or 'UNKNOWN'))}\n"
        f"بابت: {html.escape(str(payload.get('description') or '-'))}\n"
        f"دسته: {html.escape(str(payload.get('expense_category') or '-'))}\n"
        f"سررسید: {html.escape(str(payload.get('due_date_shamsi') or '-'))}"
    )


def format_revision(old_payload: dict[str, Any], new_payload: dict[str, Any], pending_id: str, *, source: str) -> str:
    source_label = "ویرایش پیام گروه" if source == "GROUP_EDIT" else "اصلاح از چت خصوصی"
    return (
        f"✏️ <b>{source_label}</b>\n"
        "اثر مالی نسخه قبلی تا زمان تأیید اصلاح، بدون تغییر باقی می‌ماند.\n\n"
        "<b>نسخه ثبت‌شده فعلی</b>\n<blockquote>" + _payload_summary(old_payload) + "</blockquote>\n"
        "<b>نسخه پیشنهادی جدید</b>\n<blockquote>" + _payload_summary(new_payload) + "</blockquote>\n"
        f"<code>{html.escape(pending_id)}</code>"
    )


def format_review(original_text: str, payload: dict[str, Any], pending_id: str) -> str:
    original = html.escape(original_text or "(بدون متن؛ تصویر/سند ارسال شده)")
    desc = html.escape(str(payload.get("description") or "-"))
    cat = html.escape(str(payload.get("expense_category") or "-"))
    payer = html.escape(str(payload.get("payer_name") or "-"))
    receiver = html.escape(str(payload.get("receiver_name") or "-"))
    method = html.escape(str(payload.get("payment_method") or "UNKNOWN"))
    state = html.escape(payment_state_label(str(payload.get("payment_state") or "UNKNOWN")))
    notes = html.escape(str(payload.get("notes") or "-"))
    confidence = float(payload.get("confidence") or 0) * 100
    return (
        "🧾 <b>پیام اصلی شما</b>\n"
        f"<blockquote>{original}</blockquote>\n"
        "🤖 <b>فرمت پیشنهادی سیستم</b>\n"
        f"• نوع: <b>{html.escape(type_label(str(payload.get('detected_type') or 'UNKNOWN')))}</b>\n"
        f"• مبلغ: <b>{html.escape(fmt_money(payload.get('amount')))}</b>\n"
        f"• مبلغ فاکتور: {html.escape(fmt_money(payload.get('invoice_amount')))}\n"
        f"• مبلغ نهایی: {html.escape(fmt_money(payload.get('final_amount')))}\n"
        f"• مبلغ پرداخت‌شده: {html.escape(fmt_money(payload.get('paid_amount')))}\n"
        f"• وضعیت پرداخت: {state}\n"
        f"• بابت: {desc}\n"
        f"• دسته: {cat}\n"
        f"• پرداخت‌کننده: {payer}\n"
        f"• گیرنده: {receiver}\n"
        f"• روش پرداخت: {method}\n"
        f"• سررسید چک: {html.escape(str(payload.get('due_date_shamsi') or '-'))}\n"
        f"• صادرکننده چک: {html.escape(str(payload.get('issuer_name') or '-'))}\n"
        f"• نوع چک: {'دیجیتال' if str(payload.get('cheque_type') or 'PHYSICAL').upper() == 'DIGITAL' else 'فیزیکی'}\n"
        f"• مشمول حقوق مدیر پروژه ۱۰٪: {'بله' if payload.get('manager_fee_eligible') else 'خیر'}\n"
        f"• اطمینان تشخیص: {confidence:.0f}%\n"
        f"• توضیح: {notes}\n\n"
        f"<code>{html.escape(pending_id)}</code>\n"
        "⚠️ <i>Stage 5: دکمه «ثبت قطعی» روی SQLite و محاسبات مالی اثر واقعی دارد؛ Google Sheets به‌صورت صف همگام‌سازی از SQLite به تب‌های V2 متصل است.</i>"
    )


def parse_edit_message(text: str) -> dict[str, Any]:
    return parse_edit_fields(text)


def snapshot_text() -> str:
    snap = DB.snapshot()
    return (
        f"💰 تنخواه: <b>{html.escape(fmt_money(snap.cash_balance))}</b>\n"
        f"🏗 هزینه ساخت: <b>{html.escape(fmt_money(snap.construction_cost))}</b>\n"
        f"👷 حقوق مدیر پروژه تحقق‌یافته: <b>{html.escape(fmt_money(snap.manager_fee_accrued))}</b>\n"
        f"💸 برداشت حقوق مدیر پروژه: <b>{html.escape(fmt_money(snap.manager_withdrawals))}</b>\n"
        f"⚖️ مانده حساب مدیر: <b>{html.escape(fmt_money(snap.manager_balance))}</b>\n"
        f"🧾 تعهد چک باز: <b>{html.escape(fmt_money(snap.open_cheque_commitments))}</b>\n"
        f"🟢 مانده آزاد پس از چک‌ها: <b>{html.escape(fmt_money(snap.free_cash_after_cheques))}</b>"
    )


def sheet_status_text() -> str:
    if not CONFIG.sheets_enabled:
        return "📄 Google Sheets: <b>غیرفعال</b>"
    counts = DB.sync_queue_counts()
    pending = counts.get("PENDING", 0)
    failed = counts.get("FAILED", 0)
    synced = counts.get("SYNCED", 0)
    last = DB.get_setting("sheets_last_sync_status", "هنوز اجرا نشده") or "هنوز اجرا نشده"
    last_error = DB.get_setting("sheets_last_error", "") or ""
    text = (
        f"📄 Google Sheets: <b>فعال</b> | صف: {pending} | خطا: {failed} | Synced: {synced}\n"
        f"آخرین وضعیت: {html.escape(last)}"
    )
    if last_error:
        text += f"\nآخرین خطا: <code>{html.escape(last_error[:400])}</code>"
    return text



def cheque_status_label(status: str) -> str:
    return {
        "ISSUED": "صادرشده",
        "PENDING_DUE": "نزدیک سررسید",
        "CASHED": "پاس‌شده",
        "RETURNED": "برگشتی",
        "CANCELLED": "لغوشده",
    }.get((status or "").upper(), status or "-")


def cheque_keyboard(cheque_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ پاس شد امروز", callback_data=f"s6_cash|{cheque_id}"),
            InlineKeyboardButton("↩️ برگشت خورد", callback_data=f"s6_return|{cheque_id}"),
        ],
        [InlineKeyboardButton("🚫 لغو چک", callback_data=f"s6_cancel|{cheque_id}")],
    ])


def format_cheque_card(chq: dict[str, Any], *, reminder: bool = False) -> str:
    head = "⏰ <b>یادآوری چک</b>" if reminder else "🧾 <b>چک</b>"
    return (
        f"{head}\n"
        f"• مبلغ: <b>{html.escape(fmt_money(chq.get('amount')))}</b>\n"
        f"• سررسید: <b>{html.escape(str(chq.get('due_date_shamsi') or chq.get('due_date') or '-'))}</b>\n"
        f"• گیرنده: {html.escape(str(chq.get('receiver_name') or '-'))}\n"
        f"• بابت: {html.escape(str(chq.get('description') or '-'))}\n"
        f"• وضعیت: <b>{html.escape(cheque_status_label(str(chq.get('status') or chq.get('cheque_status') or '')))}</b>\n"
        f"<code>{html.escape(str(chq.get('cheque_id') or chq.get('entity_id') or '-'))}</code>"
    )


def _today_gregorian_and_shamsi() -> tuple[str, str]:
    now = datetime.now()
    sh = jdatetime.datetime.fromgregorian(datetime=now)
    return now.strftime("%Y-%m-%d"), sh.strftime("%Y/%m/%d")


def _cheque_due_within_window(chq: dict[str, Any]) -> bool:
    try:
        due = datetime.fromisoformat(str(chq.get("due_date"))).date()
        today = datetime.now().date()
        delta = (due - today).days
        return 0 <= delta <= CONFIG.cheque_reminder_days_before
    except Exception:
        return False


async def prepare_cheque_reminders_once() -> int:
    if not CONFIG.cheque_reminders_enabled:
        return 0
    created = await asyncio.to_thread(
        DB.ensure_all_open_cheque_reminders,
        reminder_times=CONFIG.cheque_reminder_times,
        days_before=CONFIG.cheque_reminder_days_before,
        telegram=True,
        email=False,
    )
    # Mark newly-near-due issued cheques as PENDING_DUE for clearer status/reporting.
    for chq in await asyncio.to_thread(DB.list_cheques, open_only=True, limit=1000):
        if chq.get("status") == "ISSUED" and _cheque_due_within_window(chq):
            try:
                await asyncio.to_thread(
                    DB.mark_cheque_pending_due,
                    chq["cheque_id"],
                    source="REMINDER_ENGINE",
                    actor_id=str(CONFIG.admin_user_id),
                )
            except Exception:
                log.exception("Could not mark cheque PENDING_DUE: %s", chq.get("cheque_id"))
    return int(created)


async def send_due_cheque_reminders_once(application) -> dict[str, int]:
    if not CONFIG.cheque_reminders_enabled:
        return {"created": 0, "sent": 0, "failed": 0, "expired": 0}

    created = await prepare_cheque_reminders_once()
    stale_before = (datetime.now() - timedelta(hours=6)).isoformat(timespec="seconds")
    expired = await asyncio.to_thread(DB.expire_stale_cheque_reminders, stale_before)
    due = await asyncio.to_thread(DB.get_due_cheque_reminders, datetime.now().isoformat(timespec="seconds"), limit=20)
    sent = failed = 0
    for rem in due:
        cheque_id = str(rem["entity_id"])
        # Fetch current state again: it may have been cashed/cancelled after the query.
        chq = await asyncio.to_thread(DB.get_cheque, cheque_id)
        if not chq or chq.get("status") not in {"ISSUED", "PENDING_DUE"}:
            await asyncio.to_thread(DB.cancel_future_cheque_reminders, cheque_id)
            continue
        try:
            await application.bot.send_message(
                chat_id=CONFIG.admin_user_id,
                text=format_cheque_card(chq, reminder=True),
                parse_mode="HTML",
                reply_markup=cheque_keyboard(cheque_id),
                read_timeout=READ_TIMEOUT,
                write_timeout=WRITE_TIMEOUT,
                connect_timeout=CONNECT_TIMEOUT,
                pool_timeout=POOL_TIMEOUT,
            )
        except (TimedOut, NetworkError) as exc:
            failed += 1
            await asyncio.to_thread(DB.log_reminder_failure, rem["reminder_id"], channel="TELEGRAM", details=str(exc))
            log.warning("Cheque reminder delivery failed; will retry later: %s", exc)
            break
        except Exception as exc:
            failed += 1
            await asyncio.to_thread(DB.log_reminder_failure, rem["reminder_id"], channel="TELEGRAM", details=f"{exc.__class__.__name__}: {exc}")
            log.exception("Cheque reminder delivery error")
        else:
            sent += 1
            await asyncio.to_thread(DB.mark_reminder_sent, rem["reminder_id"], channel="TELEGRAM", details="private admin reminder")
    return {"created": created, "sent": sent, "failed": failed, "expired": expired}


async def cheque_reminder_worker(application):
    while True:
        try:
            result = await send_due_cheque_reminders_once(application)
            if result["created"] or result["sent"] or result["failed"] or result["expired"]:
                log.info("Cheque reminders: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Cheque reminder worker crashed: %s", exc)
        await asyncio.sleep(CONFIG.reminder_check_interval_seconds)


async def cheques_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    rows = await asyncio.to_thread(DB.list_cheques, open_only=True, limit=20)
    if not rows:
        await update.effective_message.reply_text("🧾 چک باز ندارید.")
        return
    await update.effective_message.reply_text(
        f"🧾 چک‌های باز: {len(rows)} مورد\n"
        "برای هر چک می‌توانید وضعیت را از دکمه‌های زیر تغییر دهید."
    )
    for chq in rows:
        await context.bot.send_message(
            chat_id=CONFIG.admin_user_id,
            text=format_cheque_card(chq),
            parse_mode="HTML",
            reply_markup=cheque_keyboard(chq["cheque_id"]),
        )


async def reminders_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    created = await prepare_cheque_reminders_once()
    counts = await asyncio.to_thread(DB.reminder_counts)
    await update.effective_message.reply_text(
        "⏰ <b>وضعیت یادآورها</b>\n"
        f"یادآور جدید ساخته شد: {created}\n"
        f"Scheduled: {counts.get('SCHEDULED', 0)}\n"
        f"Sent: {counts.get('SENT', 0)}\n"
        f"Cancelled: {counts.get('CANCELLED', 0)}\n"
        f"زمان‌ها: <code>{html.escape(', '.join(CONFIG.cheque_reminder_times))}</code>\n"
        f"شروع: {CONFIG.cheque_reminder_days_before} روز قبل از سررسید",
        parse_mode="HTML",
    )


async def reminder_check_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    result = await send_due_cheque_reminders_once(context.application)
    await update.effective_message.reply_text(
        "⏱ بررسی دستی یادآورها انجام شد.\n"
        f"created={result['created']} | sent={result['sent']} | failed={result['failed']} | expired={result['expired']}"
    )


async def handle_cheque_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.from_user or q.from_user.id != CONFIG.admin_user_id:
        return
    await q.answer()
    try:
        action, cheque_id = (q.data or "").split("|", 1)
    except ValueError:
        return
    chq = await asyncio.to_thread(DB.get_cheque, cheque_id)
    if not chq:
        await q.edit_message_text("⚠️ چک پیدا نشد.")
        return

    try:
        if action == "s6_cash":
            g_date, sh_date = _today_gregorian_and_shamsi()
            tx_id = await asyncio.to_thread(
                DB.cash_cheque,
                cheque_id,
                cashed_date=g_date,
                cashed_date_shamsi=sh_date,
                source="TELEGRAM",
                actor_id=str(CONFIG.admin_user_id),
            )
            await asyncio.to_thread(DB.cancel_future_cheque_reminders, cheque_id)
            result = f"✅ چک پاس شد و Transaction خروجی ساخته شد.\n<code>{html.escape(tx_id)}</code>"
        elif action == "s6_return":
            changed = await asyncio.to_thread(
                DB.return_cheque, cheque_id, source="TELEGRAM", actor_id=str(CONFIG.admin_user_id)
            )
            result = "↩️ چک برگشتی ثبت شد؛ تنخواه کم نشد و هزینه ساخت/حقوق مدیر پروژه سر جای خود باقی ماند." if changed else "↩️ چک قبلاً برگشتی ثبت شده بود."
        elif action == "s6_cancel":
            changed = await asyncio.to_thread(
                DB.cancel_cheque, cheque_id, source="TELEGRAM", actor_id=str(CONFIG.admin_user_id)
            )
            result = "🚫 چک لغو شد؛ Payment چک لغو شد ولی Expense ساخت حذف نشد." if changed else "🚫 چک قبلاً لغو شده بود."
        else:
            return
    except Exception as exc:
        await q.edit_message_text(f"⚠️ عملیات چک انجام نشد: {html.escape(str(exc))}", parse_mode="HTML")
        return

    if SHEETS is not None:
        try:
            await run_sheet_sync_once()
        except Exception as exc:
            log.warning("Cheque action committed; Sheets remains queued: %s", exc)
    updated = await asyncio.to_thread(DB.get_cheque, cheque_id)
    await q.edit_message_text(
        result + "\n\n" + format_cheque_card(updated or chq) + "\n\n" + snapshot_text(),
        parse_mode="HTML",
    )


async def run_sheet_sync_once() -> str:
    if SHEETS is None:
        return "Google Sheets غیرفعال است."
    # Prevent the background worker and /sync from starting overlapping
    # to_thread jobs. GoogleSheetsMirror also has a thread-level lock.
    async with SHEET_ASYNC_LOCK:
        result = await asyncio.to_thread(SHEETS.sync_batch, CONFIG.sheets_sync_batch_size)
    if result.failed:
        DB.set_setting("sheets_last_sync_status", f"FAILED | synced={result.synced} remaining={result.remaining}")
        DB.set_setting("sheets_last_error", result.last_error)
    else:
        DB.set_setting("sheets_last_sync_status", f"OK | synced={result.synced} remaining={result.remaining}")
        DB.set_setting("sheets_last_error", "")
    return (
        f"Sheets sync: attempted={result.attempted}, synced={result.synced}, "
        f"failed={result.failed}, remaining={result.remaining}"
        + (f" | {result.last_error}" if result.last_error else "")
    )


async def sheet_sync_worker(application):
    while True:
        try:
            if SHEETS is not None and DB.health_check()["pending_sync_items"]:
                msg = await run_sheet_sync_once()
                log.info(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Background Sheets sync crashed: %s", exc)
            DB.set_setting("sheets_last_sync_status", "WORKER_ERROR")
            DB.set_setting("sheets_last_error", f"{exc.__class__.__name__}: {exc}")
        await asyncio.sleep(CONFIG.sheets_sync_interval_seconds)


async def post_init(application):
    global SHEET_TASK, REMINDER_TASK
    if SHEETS is not None:
        try:
            async with SHEET_ASYNC_LOCK:
                titles = await asyncio.to_thread(SHEETS.bootstrap_worksheets)
            DB.set_setting("sheets_last_bootstrap", "OK: " + ", ".join(titles))
            log.info("Sheets bootstrap OK: %s", titles)
        except Exception as exc:
            detail = f"{exc.__class__.__name__}: {exc}"
            DB.set_setting("sheets_last_bootstrap", "FAILED: " + detail)
            DB.set_setting("sheets_last_error", detail)
            log.warning("Sheets bootstrap failed; queue remains safe in SQLite: %s", detail)
        SHEET_TASK = asyncio.create_task(sheet_sync_worker(application), name="peymaan-sheet-sync")
        log.info("Sheets worker enabled: spreadsheet=%s interval=%ss", CONFIG.spreadsheet_name, CONFIG.sheets_sync_interval_seconds)
    if CONFIG.cheque_reminders_enabled:
        try:
            created = await prepare_cheque_reminders_once()
            log.info("Cheque reminder bootstrap OK: created=%s times=%s", created, CONFIG.cheque_reminder_times)
        except Exception as exc:
            log.warning("Cheque reminder bootstrap failed: %s", exc)
        REMINDER_TASK = asyncio.create_task(cheque_reminder_worker(application), name="peymaan-cheque-reminders")
        log.info("Cheque reminder worker enabled: interval=%ss", CONFIG.reminder_check_interval_seconds)


async def post_shutdown(application):
    global SHEET_TASK, REMINDER_TASK
    if SHEET_TASK is not None and not SHEET_TASK.done():
        SHEET_TASK.cancel()
        try:
            await SHEET_TASK
        except asyncio.CancelledError:
            pass
        SHEET_TASK = None
    if REMINDER_TASK is not None and not REMINDER_TASK.done():
        REMINDER_TASK.cancel()
        try:
            await REMINDER_TASK
        except asyncio.CancelledError:
            pass
        REMINDER_TASK = None


async def sync_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    await update.effective_message.reply_text("⏳ در حال Sync با Google Sheets...")
    try:
        result = await run_sheet_sync_once()
        await update.effective_message.reply_text(result + "\n\n" + sheet_status_text(), parse_mode="HTML")
    except Exception as exc:
        DB.set_setting("sheets_last_sync_status", "COMMAND_ERROR")
        DB.set_setting("sheets_last_error", f"{exc.__class__.__name__}: {exc}")
        await update.effective_message.reply_text(
            "❌ Sync انجام نشد؛ ثبت‌های SQLite محفوظ هستند.\n"
            f"<code>{html.escape(str(exc)[:600])}</code>",
            parse_mode="HTML",
        )


async def rebuild_sheets_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    if SHEETS is None:
        await update.effective_message.reply_text("Google Sheets غیرفعال است.")
        return
    await update.effective_message.reply_text("🧹 در حال بازسازی فقط تب‌های V2 از روی SQLite...")
    try:
        async with SHEET_ASYNC_LOCK:
            counts = await asyncio.to_thread(SHEETS.rebuild_all_from_sqlite)
        DB.set_setting("sheets_last_rebuild", "OK")
        await update.effective_message.reply_text(
            "✅ تب‌های V2 از روی SQLite بازسازی شدند. ردیف‌های تکراری آزمایشی حذف شدند و تب چک‌ها هم ایجاد/اصلاح شد.\n"
            f"Transactions={counts.get('transaction',0)} | Expenses={counts.get('expense',0)} | "
            f"Payments={counts.get('payment',0)} | Cheques={counts.get('cheque',0)}"
        )
    except Exception as exc:
        detail = f"{exc.__class__.__name__}: {exc}"
        DB.set_setting("sheets_last_rebuild", "FAILED: " + detail)
        await update.effective_message.reply_text(
            "❌ بازسازی Sheets انجام نشد؛ SQLite تغییری نکرده است.\n" + detail
        )


async def repair_ledger_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    try:
        result = DB.repair_paid_expense_invariants(source="TELEGRAM_REPAIR", actor_id=str(CONFIG.admin_user_id))
        sheet_result = "Google Sheets غیرفعال است."
        if SHEETS is not None and result.get("repaired_count", 0):
            try:
                sheet_result = await run_sheet_sync_once()
            except Exception as exc:
                sheet_result = f"Sheets queued: {exc.__class__.__name__}: {exc}"
        await update.effective_message.reply_text(
            "🧰 <b>بررسی سازگاری Ledger انجام شد.</b>\n"
            f"موارد اصلاح‌شده: <b>{int(result.get('repaired_count', 0))}</b>\n"
            f"موارد ردشده از بررسی خودکار: {int(result.get('skipped', 0))}\n"
            f"Sheets: {html.escape(sheet_result)}\n\n" + snapshot_text() +
            "\n\n<i>فقط مواردی اصلاح می‌شوند که ثبت قطعی صراحتاً PAID باشد ولی Payment/Transaction از مبلغ نهایی عقب مانده باشند؛ پرداخت‌های PARTIAL دست‌نخورده می‌مانند.</i>",
            parse_mode="HTML",
        )
    except Exception as exc:
        await update.effective_message.reply_text(f"⚠️ Repair انجام نشد: {html.escape(str(exc))}", parse_mode="HTML")


async def reaction_test_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    configured = CONFIG.group_chat_id or DB.get_setting("telegram_group_chat_id")
    if not configured:
        await update.effective_message.reply_text("گروه هنوز ثبت نشده است.")
        return
    chat_id = int(configured)
    latest = DB.get_latest_telegram_message(chat_id)
    diagnostics = await _reaction_diagnostics(context, chat_id)
    if not latest:
        await update.effective_message.reply_text("پیام تستی ثبت‌شده‌ای از گروه ندارم.\n" + diagnostics)
        return
    ok, detail = await _try_set_check_reaction(context, chat_id, int(latest["message_id"]))
    await update.effective_message.reply_text(
        ("👍 Reaction تست با موفقیت روی آخرین پیام ثبت شد.\n" if ok else "❌ Reaction تست ثبت نشد.\n")
        + detail + "\n\n" + diagnostics
    )


async def _reaction_diagnostics(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> str:
    try:
        chat_info = await context.bot.get_chat(chat_id)
        available = getattr(chat_info, "available_reactions", None)
        permissions = getattr(chat_info, "permissions", None)
        default_can_react = getattr(permissions, "can_react_to_messages", None) if permissions else None
        member = await context.bot.get_chat_member(chat_id, context.bot.id)
        status = getattr(member, "status", "unknown")
        own_can_react = getattr(member, "can_react_to_messages", None)
        if available is None:
            available_text = "ALL_STANDARD (field omitted)"
        else:
            emojis = [getattr(r, "emoji", getattr(r, "custom_emoji_id", "?")) for r in available]
            available_text = ",".join(str(x) for x in emojis) if emojis else "EMPTY"
        return (
            f"bot_status={status}; default_can_react={default_can_react}; "
            f"bot_can_react={own_can_react}; available={available_text}"
        )
    except Exception as exc:
        return f"diagnostic_failed={exc.__class__.__name__}: {exc}"


async def _try_set_check_reaction(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> tuple[bool, str]:
    # Historical Telegram Desktop imports use a synthetic chat-id namespace;
    # they have no live Telegram message to react to.
    if int(chat_id) <= -8_900_000_000_000_000:
        return False, 'پیام تاریخی Import شده؛ Reaction ندارد'
    if not CONFIG.enable_reaction_in_test:
        return False, "Reaction در تنظیمات خاموش است"
    diagnostics = await _reaction_diagnostics(context, chat_id)
    try:
        chat_info = await context.bot.get_chat(chat_id)
        available = getattr(chat_info, "available_reactions", None)
        # Per Telegram: if available_reactions is omitted (None), all standard
        # emoji reactions are allowed. A present list is authoritative.
        if available is not None:
            allowed = [r for r in available if isinstance(r, ReactionTypeEmoji)]
            if not any(getattr(r, "emoji", None) == "👍" for r in allowed):
                reason = f"واکنش 👍 در این گروه مجاز نیست | {diagnostics}"
                DB.set_setting("telegram_reaction_last_error", reason)
                return False, reason

        member = await context.bot.get_chat_member(chat_id, context.bot.id)
        member_status = str(getattr(member, "status", ""))
        if member_status == "restricted" and getattr(member, "can_react_to_messages", None) is False:
            reason = f"بات اجازه Reaction ندارد؛ دسترسی گروه محدودش کرده | {diagnostics}"
            DB.set_setting("telegram_reaction_last_error", reason)
            return False, reason

        result = await context.bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji="👍")],
            is_big=False,
        )
        if result is not True:
            reason = f"Telegram پاسخ موفق قطعی برنگرداند: {result!r} | {diagnostics}"
            DB.set_setting("telegram_reaction_last_error", reason)
            return False, reason
        DB.set_setting("telegram_reaction_last_error", "")
        DB.set_setting("telegram_reaction_last_diagnostics", diagnostics)
        return True, "👍"
    except Exception as exc:
        reason = f"{exc.__class__.__name__}: {exc} | {diagnostics}"
        DB.set_setting("telegram_reaction_last_error", reason)
        DB.set_setting("telegram_reaction_last_diagnostics", diagnostics)
        log.warning("Reaction failed after successful posting: %s", reason)
        return False, reason


async def start_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    DB.set_setting("telegram_admin_private_chat_id", str(update.effective_chat.id))
    await update.effective_message.reply_text(
        "✅ Stage 5 آماده است.\n"
        "فقط پیام‌های دارای #تست پردازش می‌شوند. تأیید نهایی در SQLite ثبت واقعی انجام می‌دهد؛ "
        "Google Sheets فقط به‌عنوان Mirror از SQLite همگام می‌شود."
    )


async def status_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    counts = DB.pending_counts()
    posting_counts = DB.financial_posting_counts()
    health = DB.health_check()
    reaction_error = DB.get_setting("telegram_reaction_last_error", "") or ""
    reaction_line = "✅ Reaction گروه آماده" if not reaction_error else f"⚠️ Reaction: {html.escape(reaction_error[:300])}"
    await update.effective_message.reply_text(
        "🧪 <b>Stage 5 Status</b>\n"
        f"Pending: {counts.get('PENDING_REVIEW', 0)}\n"
        f"Needs review: {counts.get('NEEDS_REVIEW', 0)}\n"
        f"Approved: {counts.get('APPROVED', 0)}\n"
        f"Rejected: {counts.get('REJECTED', 0)}\n"
        f"Edit pending: {counts.get('EDIT_PENDING', 0)}\n"
        f"ثبت فعال: {posting_counts.get('ACTIVE', 0)} | حذف‌شده: {posting_counts.get('DELETED', 0)}\n"
        f"SQLite: {health['sqlite_integrity']} | Schema: {health['schema_version']}\n"
        f"Sync queue: {health['pending_sync_items']}\n"
        f"{reaction_line}\n\n"
        + snapshot_text()
        + "\n\n"
        + sheet_status_text(),
        parse_mode="HTML",
    )


async def _get_admin_private_chat_id() -> int | None:
    # In a one-to-one Telegram chat, the private chat id is the user's id.
    # Stage 4 uses a fresh SQLite database, so the private-chat id learned in
    # Stage 3 may not exist yet. Fall back to the configured admin user id;
    # sending will still fail normally if the user has never started the bot.
    value = DB.get_setting("telegram_admin_private_chat_id")
    if value:
        return int(value)
    return int(CONFIG.admin_user_id)


async def _maybe_learn_group(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    configured = CONFIG.group_chat_id
    saved = DB.get_setting("telegram_group_chat_id")
    saved_id = int(saved) if saved else None
    target = configured or saved_id
    if target is not None:
        return int(chat_id) == int(target)

    DB.set_setting("telegram_group_chat_id", str(chat_id))
    private_id = await _get_admin_private_chat_id()
    if private_id:
        await context.bot.send_message(
            private_id,
            f"📌 گروه تست به‌صورت خودکار ثبت شد.\nChat ID: <code>{chat_id}</code>",
            parse_mode="HTML",
        )
    log.info("Learned group chat id: %s", chat_id)
    return True


async def _extract_image_bytes(message, context: ContextTypes.DEFAULT_TYPE):
    if not message.photo:
        return None, None
    photo = message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    temp_dir = BASE_DIR / "data" / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    path = temp_dir / f"{photo.file_unique_id}.jpg"
    await tg_file.download_to_drive(custom_path=path)
    try:
        return path.read_bytes(), "image/jpeg"
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


async def _send_review(message, context: ContextTypes.DEFAULT_TYPE, pending_id: str, payload: dict[str, Any]):
    private_id = await _get_admin_private_chat_id()
    if not private_id:
        log.warning("No admin private chat id is available.")
        return

    original_text = message.caption or message.text or ""
    if message.photo:
        try:
            await context.bot.copy_message(
                chat_id=private_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id,
            )
        except Exception as exc:
            log.warning("Could not copy original photo to private chat: %s", exc)

    sent = await context.bot.send_message(
        chat_id=private_id,
        text=format_review(original_text, payload, pending_id),
        parse_mode="HTML",
        reply_markup=review_keyboard(pending_id),
        disable_web_page_preview=True,
    )
    WORKFLOW.mark_private_review_message(pending_id, sent.message_id)


async def _analyze_message_payload(message, context: ContextTypes.DEFAULT_TYPE, text: str, message_date: str) -> dict[str, Any]:
    try:
        image_bytes, mime = await _extract_image_bytes(message, context)
        return await PARSER.analyze(text=text, image_bytes=image_bytes, image_mime_type=mime or "image/jpeg")
    except Exception as exc:
        log.warning("Gemini analysis unavailable; using deterministic fallback: %s", exc)
        if message.photo:
            # Even unread, a photo captioned «گزارش روزانه ...:» files there.
            return apply_explicit_note_title({
                "detected_type": "UNKNOWN", "document_type": "OTHER",
                "transaction_type_fa": "نامشخص", "amount": 0, "invoice_amount": 0,
                "final_amount": 0, "discount_amount": 0, "paid_amount": 0,
                "payment_state": "UNKNOWN", "description": text, "expense_category": "",
                "construction_stage": "", "payer_name": "", "receiver_name": "",
                "payment_method": "UNKNOWN", "is_cheque": False, "cheque_serial": "",
                "issuer_bank": "", "due_date_shamsi": "",
                "event_date_shamsi": message_date.split()[0],
                "manager_fee_eligible": False,
                "notes": f"AI در دسترس نبود؛ تصویر نیاز به بررسی دستی دارد. {exc.__class__.__name__}",
                "confidence": 0.0, "fallback_used": True,
            }, text)
        payload = analyze_locally(text)
        payload["event_date_shamsi"] = message_date.split()[0]
        payload["notes"] = (payload.get("notes") or "") + f" | AI error: {exc.__class__.__name__}"
        return payload


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return
    if user.id != CONFIG.admin_user_id:
        return
    if chat.type not in {"group", "supergroup"}:
        return
    if not await _maybe_learn_group(chat.id, context):
        return

    text = message.caption or message.text or ""
    if CONFIG.require_test_tag and CONFIG.test_tag not in text:
        return

    existing = DB.get_telegram_message(chat.id, message.message_id)
    if existing:
        log.info("Duplicate Telegram update ignored: %s/%s", chat.id, message.message_id)
        return

    date_naive = message.date.replace(tzinfo=None)
    shamsi = jdatetime.datetime.fromgregorian(datetime=date_naive)
    message_date = shamsi.strftime("%Y/%m/%d %H:%M")

    payload = await _analyze_message_payload(message, context, text, message_date)

    review = WORKFLOW.receive_message(
        chat_id=chat.id,
        message_id=message.message_id,
        raw_text=text,
        content_type="PHOTO" if message.photo else "TEXT",
        message_date=message_date,
        analysis=payload,
    )
    await _send_review(message, context, review.pending_id, review.payload)


async def handle_edited_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.edited_message
    user = update.effective_user
    if not message or not user or user.id != CONFIG.admin_user_id:
        return
    row = DB.get_telegram_message(message.chat_id, message.message_id)
    if not row:
        return
    pending = DB.get_pending_by_message(message.chat_id, message.message_id)
    if not pending:
        return

    text = message.caption or message.text or ""
    DB.update_telegram_message(
        chat_id=message.chat_id, message_id=message.message_id,
        raw_text=text, reaction_state="NONE", mark_edited=True,
    )
    if CONFIG.enable_reaction_in_test:
        try:
            await context.bot.set_message_reaction(message.chat_id, message.message_id, reaction=[])
        except Exception:
            log.exception("Could not clear reaction after edit")

    message_date = row.get("message_date") or ""
    payload = await _analyze_message_payload(message, context, text, message_date)

    if row.get("state") in {"APPROVED", "EDIT_PENDING"} and DB.get_financial_posting(pending["pending_id"]):
        try:
            revision = WORKFLOW.begin_posted_revision(
                pending["pending_id"], payload, source="GROUP_EDIT", actor_id=str(CONFIG.admin_user_id)
            )
        except Exception as exc:
            private_id = await _get_admin_private_chat_id()
            if private_id:
                await context.bot.send_message(private_id, f"⚠️ ویرایش پیام ثبت‌شده آماده نشد: {html.escape(str(exc))}", parse_mode="HTML")
            return
        private_id = await _get_admin_private_chat_id()
        if private_id:
            await context.bot.send_message(
                private_id,
                format_revision(revision["old_payload"], revision["new_payload"], pending["pending_id"], source="GROUP_EDIT"),
                parse_mode="HTML",
                reply_markup=revision_keyboard(pending["pending_id"]),
            )
        return

    # Before first approval, an edited group message simply refreshes the proposal.
    DB.update_pending(
        pending["pending_id"], payload=payload,
        detected_type=str(payload.get("detected_type") or "UNKNOWN"),
        confidence=float(payload.get("confidence") or 0),
        status="PENDING_REVIEW" if str(payload.get("detected_type") or "UNKNOWN") != "UNKNOWN" else "NEEDS_REVIEW",
    )
    DB.update_telegram_message(
        chat_id=message.chat_id, message_id=message.message_id,
        state="PENDING_REVIEW" if str(payload.get("detected_type") or "UNKNOWN") != "UNKNOWN" else "NEEDS_REVIEW",
    )
    await _send_review(message, context, pending["pending_id"], payload)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user or query.from_user.id != CONFIG.admin_user_id:
        return
    try:
        action, pending_id = (query.data or "").split("|", 1)
    except ValueError:
        await query.answer()
        return

    item = DB.get_pending_item(pending_id)
    if not item:
        await query.answer("این مورد پیدا نشد.", show_alert=True)
        return

    if action == "s5_ok":
        try:
            approval = WORKFLOW.approve_and_post(pending_id, actor_id=str(CONFIG.admin_user_id))
        except Exception as exc:
            log.warning("Stage 5 posting blocked for %s: %s", pending_id, exc)
            await query.answer(str(exc)[:180], show_alert=True)
            return
        await query.answer("ثبت شد ✅")
        reaction_ok, reaction_detail = await _try_set_check_reaction(
            context, item["telegram_chat_id"], item["telegram_message_id"]
        )
        if reaction_ok:
            WORKFLOW.mark_reaction(pending_id, True)
        sheet_result = "Google Sheets غیرفعال است."
        if SHEETS is not None:
            try:
                sheet_result = await run_sheet_sync_once()
            except Exception as exc:
                sheet_result = f"Sheets queued: {exc.__class__.__name__}: {exc}"
        ids = approval.posting
        await query.edit_message_text(
            "✅ <b>ثبت قطعی انجام شد.</b>\n"
            f"نوع: {html.escape(type_label(ids.posting_type))}\n"
            f"Expense: <code>{html.escape(ids.expense_id or '-')}</code>\n"
            f"Transaction: <code>{html.escape(ids.transaction_id or '-')}</code>\n"
            f"Payment: <code>{html.escape(ids.payment_id or '-')}</code>\n"
            f"Cheque: <code>{html.escape(ids.cheque_id or '-')}</code>\n"
            f"Reaction: {'👍' if reaction_ok else html.escape(reaction_detail)}\n"
            f"Sheets: {html.escape(sheet_result)}\n\n" + snapshot_text(),
            parse_mode="HTML",
            reply_markup=posted_keyboard(pending_id),
        )

    elif action == "s5_no":
        await query.answer("رد شد")
        try:
            WORKFLOW.reject(pending_id)
        except Exception as exc:
            await query.edit_message_text(f"⚠️ رد انجام نشد: {html.escape(str(exc))}", parse_mode="HTML")
            return
        if CONFIG.enable_reaction_in_test:
            try:
                await context.bot.set_message_reaction(item["telegram_chat_id"], item["telegram_message_id"], reaction=[])
                WORKFLOW.mark_reaction(pending_id, False)
            except Exception:
                pass
        await query.edit_message_text(
            "❌ این مورد رد شد و هیچ اثر مالی ندارد.\n" f"<code>{pending_id}</code>",
            parse_mode="HTML",
        )

    elif action == "s5_edit":
        await query.answer()
        try:
            WORKFLOW.begin_preapproval_edit(pending_id)
        except Exception as exc:
            await query.edit_message_text(f"⚠️ ویرایش ممکن نیست: {html.escape(str(exc))}", parse_mode="HTML")
            return
        context.user_data["stage5_edit_pending_id"] = pending_id
        payload = dict(item.get("payload") or {})
        is_cheque_edit = bool(payload.get("is_cheque")) or str(payload.get("payment_method") or "").upper() == "CHEQUE" or str(payload.get("detected_type") or "").upper() == "CHEQUE"
        example = (
            "<code>مبلغ: 95000000\nمبلغ نهایی: 95000000\nوضعیت پرداخت: پرداخت کامل\n"
            "روش پرداخت: حواله\nبابت: خرید بتن با تخفیف</code>"
        )
        if is_cheque_edit:
            example = (
                "<code>مبلغ: 50,000,000\nروش پرداخت: چک\n"
                "سررسید چک: 1405/05/22\nصادرکننده چک: پیمان\nنوع چک: فیزیکی\nبابت: خرید سیمان با چک</code>"
            )
        await query.edit_message_text(
            "✏️ <b>ویرایش قبل از ثبت قطعی</b>\n"
            "فیلدهای موردنظر را در خصوصی بفرست. مثال:\n\n" + example +
            "\n\nبرای چک می‌توانی از «سررسید»، «صادرکننده چک» و «نوع چک: فیزیکی/دیجیتال» استفاده کنی.",
            parse_mode="HTML",
        )

    elif action == "s5_postedit":
        post = DB.get_financial_posting(pending_id)
        if not post or str(post.get("status") or "ACTIVE") != "ACTIVE":
            await query.answer("این ثبت فعال نیست.", show_alert=True)
            return
        await query.answer()
        context.user_data["stage5_posted_edit_pending_id"] = pending_id
        item_payload = dict(item.get("payload") or {})
        is_cheque_edit = bool(item_payload.get("is_cheque")) or str(item_payload.get("payment_method") or "").upper() == "CHEQUE" or bool(post.get("cheque_id"))
        example = "<code>مبلغ: 120000000\nمبلغ نهایی: 120000000\nبابت: خرید بتن اصلاح‌شده</code>"
        if is_cheque_edit:
            example = "<code>مبلغ: 50,000,000\nسررسید چک: 1405/05/22\nصادرکننده چک: پیمان\nنوع چک: فیزیکی\nبابت: خرید سیمان با چک</code>"
        await query.edit_message_text(
            "✏️ <b>اصلاح ثبت قطعی</b>\n"
            "اثر مالی فعلی تا زمان تأیید اصلاح حفظ می‌شود. فقط فیلدهای تغییرکرده را بفرست:\n\n" +
            example +
            "\n\nتغییر «نوع اصلی ثبت» در این مرحله مجاز نیست؛ برای آن باید ثبت قبلی حذف و مورد جدید ثبت شود.",
            parse_mode="HTML",
        )

    elif action == "s5_delete":
        post = DB.get_financial_posting(pending_id)
        if not post or str(post.get("status") or "ACTIVE") != "ACTIVE":
            await query.answer("این ثبت قبلاً حذف شده یا پیدا نشد.", show_alert=True)
            return
        await query.answer()
        await query.edit_message_text(
            "🗑 <b>حذف ثبت مالی</b>\n"
            "این عملیات Soft Delete است: اثر مالی از محاسبات حذف می‌شود، اما Audit در SQLite باقی می‌ماند و Sheets هم وضعیت لغو/ابطال را می‌گیرد.\n\n"
            "آیا مطمئنی؟",
            parse_mode="HTML",
            reply_markup=delete_confirm_keyboard(pending_id),
        )

    elif action == "s5_deletecancel":
        await query.answer("لغو شد")
        await query.edit_message_text(
            "✅ ثبت بدون تغییر باقی ماند.\n\n" + snapshot_text(),
            parse_mode="HTML",
            reply_markup=posted_keyboard(pending_id),
        )

    elif action == "s5_deleteyes":
        try:
            deleted = WORKFLOW.delete_posting(
                pending_id, actor_id=str(CONFIG.admin_user_id), reason="حذف با تأیید مدیر در تلگرام"
            )
        except Exception as exc:
            await query.answer(str(exc)[:180], show_alert=True)
            return
        await query.answer("حذف شد")
        try:
            await context.bot.set_message_reaction(item["telegram_chat_id"], item["telegram_message_id"], reaction=[])
        except Exception:
            log.exception("Could not clear reaction after delete")
        sheet_result = "Google Sheets غیرفعال است."
        if SHEETS is not None:
            try:
                sheet_result = await run_sheet_sync_once()
            except Exception as exc:
                sheet_result = f"Sheets queued: {exc.__class__.__name__}: {exc}"
        await query.edit_message_text(
            "🗑 <b>ثبت حذف/ابطال شد.</b>\n"
            f"Posting: <code>{html.escape(deleted.posting_id)}</code>\n"
            f"Sheets: {html.escape(sheet_result)}\n\n" + snapshot_text() +
            "\n\n<i>سابقه Audit حذف نشده است.</i>",
            parse_mode="HTML",
        )

    elif action == "s5_revok":
        try:
            ids = WORKFLOW.approve_posted_revision(pending_id, actor_id=str(CONFIG.admin_user_id))
        except Exception as exc:
            await query.answer(str(exc)[:180], show_alert=True)
            return
        await query.answer("اصلاح ثبت شد ✅")
        reaction_ok, reaction_detail = await _try_set_check_reaction(
            context, item["telegram_chat_id"], item["telegram_message_id"]
        )
        if reaction_ok:
            WORKFLOW.mark_reaction(pending_id, True)
        sheet_result = "Google Sheets غیرفعال است."
        if SHEETS is not None:
            try:
                sheet_result = await run_sheet_sync_once()
            except Exception as exc:
                sheet_result = f"Sheets queued: {exc.__class__.__name__}: {exc}"
        await query.edit_message_text(
            "✅ <b>اصلاح ثبت قطعی شد؛ IDهای قبلی حفظ شدند.</b>\n"
            f"Expense: <code>{html.escape(ids.expense_id or '-')}</code>\n"
            f"Transaction: <code>{html.escape(ids.transaction_id or '-')}</code>\n"
            f"Payment: <code>{html.escape(ids.payment_id or '-')}</code>\n"
            f"Cheque: <code>{html.escape(ids.cheque_id or '-')}</code>\n"
            f"Reaction: {'👍' if reaction_ok else html.escape(reaction_detail)}\n"
            f"Sheets: {html.escape(sheet_result)}\n\n" + snapshot_text(),
            parse_mode="HTML",
            reply_markup=posted_keyboard(pending_id),
        )

    elif action == "s5_revno":
        try:
            WORKFLOW.reject_posted_revision(pending_id, actor_id=str(CONFIG.admin_user_id))
        except Exception as exc:
            await query.answer(str(exc)[:180], show_alert=True)
            return
        await query.answer("اصلاح رد شد")
        reaction_ok, reaction_detail = await _try_set_check_reaction(
            context, item["telegram_chat_id"], item["telegram_message_id"]
        )
        if reaction_ok:
            WORKFLOW.mark_reaction(pending_id, True)
        await query.edit_message_text(
            "↩️ <b>اصلاح رد شد.</b> اثر مالی نسخه قبلی بدون تغییر حفظ شد.\n"
            f"Reaction: {'👍' if reaction_ok else html.escape(reaction_detail)}\n\n" + snapshot_text(),
            parse_mode="HTML",
            reply_markup=posted_keyboard(pending_id),
        )


async def handle_private_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    text = update.effective_message.text or ""
    if text.startswith("/"):
        return

    posted_id = context.user_data.get("stage5_posted_edit_pending_id")
    pre_id = context.user_data.get("stage5_edit_pending_id")
    pending_id = posted_id or pre_id
    if not pending_id:
        return
    changes = parse_edit_message(text)
    if not changes:
        await update.effective_message.reply_text("هیچ فیلد قابل‌تشخیصی پیدا نشد. با قالب «نام فیلد: مقدار» بفرست.")
        return

    if posted_id:
        item = DB.get_pending_item(posted_id)
        if not item:
            context.user_data.pop("stage5_posted_edit_pending_id", None)
            await update.effective_message.reply_text("ثبت پیدا نشد.")
            return
        new_payload = normalize_financial_edit(dict(item["payload"]), changes)
        try:
            revision = WORKFLOW.begin_posted_revision(
                posted_id, new_payload, source="PRIVATE_EDIT", actor_id=str(CONFIG.admin_user_id)
            )
        except Exception as exc:
            await update.effective_message.reply_text(f"⚠️ اصلاح آماده نشد: {exc}")
            return
        try:
            await update.effective_message.reply_text(
                format_revision(revision["old_payload"], revision["new_payload"], posted_id, source="PRIVATE_EDIT"),
                parse_mode="HTML",
                reply_markup=revision_keyboard(posted_id),
                read_timeout=READ_TIMEOUT,
                write_timeout=WRITE_TIMEOUT,
                connect_timeout=CONNECT_TIMEOUT,
                pool_timeout=POOL_TIMEOUT,
            )
        except (TimedOut, NetworkError) as exc:
            # Keep edit context so the user can resend the same edit text after connectivity recovers.
            log.warning("Revision was prepared but private confirmation could not be delivered (%s): %s", posted_id, exc)
            return
        context.user_data.pop("stage5_posted_edit_pending_id", None)
        return

    try:
        result = WORKFLOW.apply_preapproval_edit(pre_id, changes)
    except Exception as exc:
        await update.effective_message.reply_text(f"⚠️ ویرایش انجام نشد: {exc}")
        return
    item = DB.get_pending_item(pre_id)
    tg = DB.get_telegram_message(item["telegram_chat_id"], item["telegram_message_id"])
    original = tg["raw_text"] if tg else ""
    try:
        sent = await update.effective_message.reply_text(
            format_review(original, result.payload, pre_id),
            parse_mode="HTML",
            reply_markup=review_keyboard(pre_id),
            read_timeout=READ_TIMEOUT,
            write_timeout=WRITE_TIMEOUT,
            connect_timeout=CONNECT_TIMEOUT,
            pool_timeout=POOL_TIMEOUT,
        )
    except (TimedOut, NetworkError) as exc:
        # apply_preapproval_edit already updated the pending payload. Keep the edit context
        # so resending the same edit text re-renders the review card instead of losing the flow.
        log.warning("Pending edit was saved but private review could not be delivered (%s): %s", pre_id, exc)
        return
    context.user_data.pop("stage5_edit_pending_id", None)
    WORKFLOW.mark_private_review_message(pre_id, sent.message_id)


async def application_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Keep transient Telegram/network failures from crashing an update handler.

    Financial state is never rolled back here: handlers persist state before UI delivery,
    so a timeout only means the acknowledgement card may need to be sent again.
    """
    err = context.error
    if isinstance(err, (TimedOut, NetworkError)):
        log.warning("Telegram network error handled without aborting financial state: %s", err)
        return
    log.error(
        "Unhandled Telegram update error",
        exc_info=(type(err), err, err.__traceback__) if err else None,
    )


def main():
    app = (
        ApplicationBuilder()
        .token(CONFIG.telegram_bot_token)
        .connection_pool_size(CONNECTION_POOL_SIZE)
        .connect_timeout(CONNECT_TIMEOUT)
        .read_timeout(READ_TIMEOUT)
        .write_timeout(WRITE_TIMEOUT)
        .pool_timeout(POOL_TIMEOUT)
        .get_updates_connection_pool_size(GET_UPDATES_CONNECTION_POOL_SIZE)
        .get_updates_connect_timeout(GET_UPDATES_CONNECT_TIMEOUT)
        .get_updates_read_timeout(GET_UPDATES_READ_TIMEOUT)
        .get_updates_write_timeout(GET_UPDATES_WRITE_TIMEOUT)
        .get_updates_pool_timeout(GET_UPDATES_POOL_TIMEOUT)
        .http_version("1.1")
        .get_updates_http_version("1.1")
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start", start_private))
    app.add_handler(CommandHandler("status", status_private))
    app.add_handler(CommandHandler("sync", sync_private))
    app.add_handler(CommandHandler("repairledger", repair_ledger_private))
    app.add_handler(CommandHandler("rebuildsheets", rebuild_sheets_private))
    app.add_handler(CommandHandler("reactiontest", reaction_test_private))
    app.add_handler(CommandHandler("cheques", cheques_private))
    app.add_handler(CommandHandler("reminders", reminders_private))
    app.add_handler(CommandHandler("remindercheck", reminder_check_private))
    app.add_handler(CallbackQueryHandler(handle_cheque_callback, pattern=r"^s6_(cash|return|cancel)\|"))
    app.add_handler(CallbackQueryHandler(handle_callback, pattern=r"^s5_(ok|no|edit|postedit|delete|deleteyes|deletecancel|revok|revno)\|"))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handle_private_edit_text))
    app.add_handler(MessageHandler(
        filters.UpdateType.EDITED_MESSAGE & filters.ChatType.GROUPS & (filters.TEXT | filters.PHOTO),
        handle_edited_group_message,
    ))
    app.add_handler(MessageHandler(
        filters.UpdateType.MESSAGE & filters.ChatType.GROUPS & (filters.TEXT | filters.PHOTO),
        handle_group_message,
    ))
    app.add_error_handler(application_error_handler)
    log.info("Stage 6 bot starting. DB=%s", CONFIG.db_path)
    app.run_polling(timeout=POLLING_TIMEOUT, bootstrap_retries=-1, drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
