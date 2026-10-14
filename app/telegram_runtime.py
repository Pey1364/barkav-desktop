from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime, timedelta
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import NetworkError, TimedOut
from telegram_resilience import (
    CONNECT_TIMEOUT, READ_TIMEOUT, WRITE_TIMEOUT, POOL_TIMEOUT,
    GET_UPDATES_CONNECT_TIMEOUT, GET_UPDATES_READ_TIMEOUT,
    GET_UPDATES_WRITE_TIMEOUT, GET_UPDATES_POOL_TIMEOUT,
    CONNECTION_POOL_SIZE, GET_UPDATES_CONNECTION_POOL_SIZE, POLLING_TIMEOUT,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import telegram_core as s6
from revenue_input import parse_received_payment_form, parse_sale_form
from revenue_service import RevenueService

CONFIG = s6.CONFIG
DB = s6.DB
REVENUE = RevenueService(DB)
BUYER_REMINDER_TASK = None

logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("peymaan.stage7")


def fmt_money(value: Any) -> str:
    try:
        return f"{int(value or 0):,} تومان"
    except Exception:
        return "-"


async def _safe_reply_text(message, text: str, *, retries: int = 3, **kwargs):
    """Send a private reply with short retries; return None if Telegram stays unavailable."""
    delays = (0, 2, 5)
    last_error = None
    for attempt in range(max(1, retries)):
        if attempt:
            await asyncio.sleep(delays[min(attempt, len(delays) - 1)])
        try:
            return await message.reply_text(
                text,
                read_timeout=READ_TIMEOUT,
                write_timeout=WRITE_TIMEOUT,
                connect_timeout=CONNECT_TIMEOUT,
                pool_timeout=POOL_TIMEOUT,
                **kwargs,
            )
        except (TimedOut, NetworkError) as exc:
            last_error = exc
            log.warning(
                "Telegram reply attempt %s/%s failed: %s",
                attempt + 1,
                max(1, retries),
                exc,
            )
    log.error("Telegram reply failed after retries; draft remains recoverable: %s", last_error)
    return None


async def _send_sale_draft_preview(message, context: ContextTypes.DEFAULT_TYPE):
    draft = context.user_data.get('stage7_sale_draft')
    if not draft:
        return False
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ ثبت قرارداد", callback_data="s7_saleok"),
        InlineKeyboardButton("❌ انصراف", callback_data="s7_salecancel"),
    ]])
    sent = await _safe_reply_text(message, _format_sale_preview(draft), parse_mode="HTML", reply_markup=kb)
    return sent is not None


async def _send_receipt_draft_preview(message, context: ContextTypes.DEFAULT_TYPE):
    draft = context.user_data.get('stage7_receipt_draft')
    if not draft:
        return False
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ ثبت وصول در تنخواه", callback_data="s7_rcvok"),
        InlineKeyboardButton("❌ انصراف", callback_data="s7_rcvdraftcancel"),
    ]])
    sent = await _safe_reply_text(message, _format_receipt_preview(draft), parse_mode="HTML", reply_markup=kb)
    return sent is not None


def _installment_status_fa(status: str) -> str:
    return {
        "UPCOMING": "آینده",
        "DUE": "سررسید امروز",
        "PARTIALLY_PAID": "پرداخت جزئی",
        "PAID": "تسویه",
        "OVERDUE": "معوق",
        "CANCELLED": "لغوشده",
    }.get((status or "").upper(), status or "-")


def _sale_status_fa(status: str) -> str:
    return {
        "ACTIVE": "فعال",
        "COMPLETED": "تسویه‌شده",
        "CANCELLED": "لغوشده",
    }.get((status or "").upper(), status or "-")


def _buyer_dashboard_text() -> str:
    d = REVENUE.buyer_dashboard()
    return (
        "🏢 <b>فروش و مطالبات خریداران</b>\n"
        f"📑 فروش قراردادی: <b>{html.escape(fmt_money(d['contract_sales']))}</b>\n"
        f"💵 وصول واقعی: <b>{html.escape(fmt_money(d['cash_received']))}</b>\n"
        f"🧮 مانده مطالبات: <b>{html.escape(fmt_money(d['receivable']))}</b>\n"
        f"⏳ مطالبات معوق: <b>{html.escape(fmt_money(d['overdue']))}</b>\n"
        f"🔗 وصول تطبیق‌نشده: <b>{html.escape(fmt_money(d['unmatched_received']))}</b>\n"
        f"🏠 فروش‌های فعال: <b>{d['active_sales']}</b>"
    )


def _sale_detail_text(sale_id: str) -> str:
    sale = REVENUE.get_sale(sale_id)
    if not sale:
        return "فروش پیدا نشد."
    summary = REVENUE.sale_summary(sale_id)
    installments = REVENUE.list_installments(sale_id)
    lines = [
        f"🏠 <b>واحد {html.escape(str(sale['unit_number']))}</b>",
        f"پروژه: {html.escape(str(sale.get('project_name') or '-'))}",
        f"بلوک: {html.escape(str(sale.get('block_name') or '-'))}",
        f"خریدار: <b>{html.escape(str(sale['buyer_name']))}</b>",
        f"موبایل: {html.escape(str(sale.get('buyer_phone') or '-'))}",
        f"تاریخ قرارداد: {html.escape(str(sale.get('contract_date_shamsi') or '-'))}",
        f"مبلغ قرارداد: <b>{html.escape(fmt_money(sale['contract_amount']))}</b>",
        f"وصول واقعی: <b>{html.escape(fmt_money(summary.cash_received))}</b>",
        f"مانده مطالبات: <b>{html.escape(fmt_money(summary.receivable))}</b>",
        f"معوق: <b>{html.escape(fmt_money(summary.overdue_amount))}</b>",
        f"وضعیت: {_sale_status_fa(str(sale['status']))}",
        f"Sale ID: <code>{html.escape(sale_id)}</code>",
        "",
        "<b>اقساط</b>",
    ]
    for ins in installments:
        remain = max(0, int(ins['amount']) - int(ins['paid_amount']))
        lines.append(
            f"• قسط {ins.get('sequence_no') or '-'} | {html.escape(str(ins.get('due_date_shamsi') or '-'))} | "
            f"{html.escape(fmt_money(ins['amount']))} | پرداخت {html.escape(fmt_money(ins['paid_amount']))} | "
            f"مانده {html.escape(fmt_money(remain))} | {_installment_status_fa(str(ins['status']))}"
        )
    if summary.next_due_shamsi:
        lines.extend([
            "",
            f"📅 سررسید بعدی: <b>{html.escape(summary.next_due_shamsi)}</b>",
            f"مبلغ باقی‌مانده آن: <b>{html.escape(fmt_money(summary.next_due_amount))}</b>",
        ])
    return "\n".join(lines)


def _sale_form_help() -> str:
    return (
        "🆕 <b>ثبت فروش واحد</b>\n"
        "فرم زیر را کپی و تکمیل کن. تاریخ‌ها فقط شمسی هستند:\n\n"
        "<pre>پروژه: بارکاو\n"
        "بلوک: A\n"
        "واحد: 12\n"
        "طبقه: 3\n"
        "متراژ: 120\n"
        "پارکینگ: P12\n"
        "انباری: S12\n"
        "خریدار: نام خریدار\n"
        "موبایل: 09...\n"
        "شماره قرارداد: 1405-12\n"
        "تاریخ قرارداد: 1405/05/20\n"
        "مبلغ قرارداد: 10 میلیارد\n"
        "اقساط:\n"
        "1405/05/20 = 3 میلیارد\n"
        "1405/06/20 = 3 میلیارد\n"
        "1405/07/20 = 4 میلیارد\n"
        "توضیحات: -</pre>\n"
        "✅ بعد از فرستادن فرم تکمیل‌شده، پیش‌نمایش و دکمه «ثبت قرارداد» می‌آید.\n"
        "⚠️ ثبت قرارداد به‌تنهایی تنخواه را تغییر نمی‌دهد؛ فقط وصول واقعی خریدار وارد تنخواه می‌شود."
    )


def _receipt_form_help() -> str:
    return (
        "💵 <b>ثبت وصول خریدار</b>\n"
        "فرم زیر را تکمیل کن:\n\n"
        "<pre>Sale ID: SALE-...\n"
        "مبلغ: 2 میلیارد\n"
        "تاریخ وصول: 1405/05/21\n"
        "پرداخت‌کننده: نام خریدار\n"
        "شرح: قسط دوم</pre>\n"
        "ابتدا وصول برای تأیید به تو نشان داده می‌شود؛ بعد از ثبت، برای بستن اقساط هم جداگانه تأیید می‌گیریم."
    )


def _format_sale_preview(data: dict[str, Any]) -> str:
    total = sum(int(x.get('amount') or 0) for x in data.get('installments', []))
    lines = [
        "🔎 <b>پیش‌نمایش فروش</b>",
        f"پروژه: {html.escape(data.get('project_name') or '-')}",
        f"بلوک: {html.escape(data.get('block_name') or '-')}",
        f"واحد: <b>{html.escape(data.get('unit_number') or '-')}</b>",
        f"خریدار: <b>{html.escape(data.get('buyer_name') or '-')}</b>",
        f"تاریخ قرارداد: {html.escape(data.get('contract_date_shamsi') or '-')}",
        f"مبلغ قرارداد: <b>{html.escape(fmt_money(data.get('contract_amount')))}</b>",
        f"جمع اقساط: <b>{html.escape(fmt_money(total))}</b>",
        "",
        "<b>اقساط</b>",
    ]
    for x in data.get('installments', []):
        lines.append(f"• {html.escape(x.get('due_date_shamsi') or '-')} → {html.escape(fmt_money(x.get('amount')))}")
    return "\n".join(lines)


def _format_receipt_preview(data: dict[str, Any]) -> str:
    sale = REVENUE.get_sale(data.get('sale_id') or '')
    buyer = sale.get('buyer_name') if sale else '-'
    unit = sale.get('unit_number') if sale else '-'
    return (
        "🔎 <b>پیش‌نمایش وصول</b>\n"
        f"خریدار: <b>{html.escape(str(buyer))}</b>\n"
        f"واحد: {html.escape(str(unit))}\n"
        f"مبلغ: <b>{html.escape(fmt_money(data.get('amount')))}</b>\n"
        f"تاریخ وصول: {html.escape(str(data.get('received_date_shamsi') or '-'))}\n"
        f"پرداخت‌کننده: {html.escape(str(data.get('payer_name') or buyer or '-'))}\n"
        f"شرح: {html.escape(str(data.get('description') or '-'))}\n"
        f"Sale ID: <code>{html.escape(str(data.get('sale_id') or '-'))}</code>\n\n"
        "⚠️ بعد از تأیید این مرحله، پول واقعاً وارد تنخواه می‌شود؛ ولی هیچ قسطی تا تأیید تطبیق بسته نمی‌شود."
    )


def _match_preview_text(received_payment_id: str) -> str:
    rp = REVENUE.get_received_payment(received_payment_id)
    if not rp:
        return "وصول پیدا نشد."
    sug = REVENUE.suggest_fifo_allocations(received_payment_id)
    lines = [
        "🔗 <b>پیشنهاد تطبیق وصول با اقساط</b>",
        f"خریدار: <b>{html.escape(str(rp['buyer_name']))}</b>",
        f"واحد: {html.escape(str(rp['unit_number']))}",
        f"وصول: <b>{html.escape(fmt_money(rp['amount']))}</b>",
        "",
    ]
    if not sug['allocations']:
        lines.append("قسط بازی برای تطبیق پیدا نشد.")
    else:
        for x in sug['allocations']:
            lines.append(
                f"• قسط {x.get('sequence_no') or '-'} | سررسید {html.escape(str(x.get('due_date_shamsi') or '-'))} "
                f"→ تخصیص <b>{html.escape(fmt_money(x['allocate']))}</b>"
            )
    if sug['unallocated']:
        lines.append(f"\n⚠️ مبلغ بدون تخصیص پس از این تطبیق: {html.escape(fmt_money(sug['unallocated']))}")
    lines.append("\nهیچ قسطی تا زدن «تأیید تطبیق» تغییر نمی‌کند.")
    return "\n".join(lines)


def _buyer_reminder_text(row: dict[str, Any]) -> str:
    remain = max(0, int(row['installment_amount']) - int(row['paid_amount']))
    return (
        "⏰ <b>یادآوری قسط خریدار</b>\n"
        f"خریدار: <b>{html.escape(str(row['buyer_name']))}</b>\n"
        f"واحد: {html.escape(str(row['unit_number']))} | بلوک: {html.escape(str(row.get('block_name') or '-'))}\n"
        f"سررسید: <b>{html.escape(str(row.get('due_date_shamsi') or '-'))}</b>\n"
        f"مبلغ قسط: {html.escape(fmt_money(row['installment_amount']))}\n"
        f"پرداخت‌شده: {html.escape(fmt_money(row['paid_amount']))}\n"
        f"مانده: <b>{html.escape(fmt_money(remain))}</b>\n"
        f"وضعیت: {_installment_status_fa(str(row['installment_status']))}"
    )


async def start_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    DB.set_setting("telegram_admin_private_chat_id", str(update.effective_chat.id))
    await update.effective_message.reply_text(
        "✅ Stage 7 آماده است.\n"
        "هزینه/چک/تنخواه مراحل قبل فعال‌اند. فروش واحد و وصول خریداران هم اضافه شده‌اند.\n"
        "دستورهای اصلی: /sales /newsale /receive /unmatched /buyerreminders"
    )


async def status_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    counts = DB.pending_counts()
    health = DB.health_check()
    await update.effective_message.reply_text(
        "🧪 <b>Stage 7 Status</b>\n"
        f"Pending: {counts.get('PENDING_REVIEW', 0)} | Needs review: {counts.get('NEEDS_REVIEW', 0)} | Approved: {counts.get('APPROVED', 0)}\n"
        f"SQLite: {health['sqlite_integrity']} | Schema: {health['schema_version']} | Sync queue: {health['pending_sync_items']}\n\n"
        + s6.snapshot_text()
        + "\n\n"
        + _buyer_dashboard_text()
        + "\n\n"
        + s6.sheet_status_text(),
        parse_mode="HTML",
    )


async def sales_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    sales = REVENUE.list_sales(active_only=False, limit=20)
    text = _buyer_dashboard_text()
    if sales:
        text += "\n\n<b>آخرین فروش‌ها</b>\n"
        for s in sales:
            summary = REVENUE.sale_summary(str(s['sale_id']))
            text += (
                f"• واحد {html.escape(str(s['unit_number']))} | {html.escape(str(s['buyer_name']))} | "
                f"قرارداد {html.escape(fmt_money(s['contract_amount']))} | مانده {html.escape(fmt_money(summary.receivable))}\n"
                f"  <code>{html.escape(str(s['sale_id']))}</code>\n"
            )
    else:
        text += "\n\nهنوز فروشی ثبت نشده است."
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def sale_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not context.args:
        await update.effective_message.reply_text("استفاده: /sale SALE-...")
        return
    await update.effective_message.reply_text(_sale_detail_text(context.args[0].strip()), parse_mode="HTML")


async def new_sale_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    context.user_data['stage7_mode'] = 'NEW_SALE'
    context.user_data.pop('stage7_sale_draft', None)
    await update.effective_message.reply_text(_sale_form_help(), parse_mode="HTML")


async def draft_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not update.effective_chat or update.effective_chat.type != 'private':
        return
    if context.user_data.get('stage7_sale_draft'):
        ok = await _send_sale_draft_preview(update.effective_message, context)
        if not ok:
            log.warning("/draft could not send sale preview because Telegram is unavailable")
        return
    if context.user_data.get('stage7_receipt_draft'):
        ok = await _send_receipt_draft_preview(update.effective_message, context)
        if not ok:
            log.warning("/draft could not send receipt preview because Telegram is unavailable")
        return
    await _safe_reply_text(update.effective_message, "پیش‌نویس بازی وجود ندارد. /newsale یا /receive را شروع کن.")


async def receive_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    context.user_data['stage7_mode'] = 'RECEIVE'
    context.user_data.pop('stage7_receipt_draft', None)
    await update.effective_message.reply_text(_receipt_form_help(), parse_mode="HTML")


async def unmatched_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    rows = REVENUE.list_unmatched_receipts(limit=20)
    if not rows:
        await update.effective_message.reply_text("✅ وصول تطبیق‌نشده‌ای وجود ندارد.")
        return
    await update.effective_message.reply_text(f"🔗 {len(rows)} وصول تطبیق‌نشده:")
    for r in rows:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔗 پیشنهاد تطبیق", callback_data=f"s7_matchshow|{r['received_payment_id']}"),
            InlineKeyboardButton("🚫 لغو وصول", callback_data=f"s7_rcvcancel|{r['received_payment_id']}"),
        ]])
        await update.effective_message.reply_text(
            f"خریدار: <b>{html.escape(str(r['buyer_name']))}</b> | واحد {html.escape(str(r['unit_number']))}\n"
            f"مبلغ: <b>{html.escape(fmt_money(r['amount']))}</b> | تاریخ: {html.escape(str(r.get('received_date_shamsi') or '-'))}\n"
            f"<code>{html.escape(str(r['received_payment_id']))}</code>",
            parse_mode="HTML", reply_markup=kb,
        )


async def handle_stage7_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    if not update.effective_chat or update.effective_chat.type != 'private':
        return
    text = update.effective_message.text or ''
    if text.startswith('/'):
        return
    mode = context.user_data.get('stage7_mode')
    if mode == 'NEW_SALE':
        data = parse_sale_form(text)
        try:
            if not data['buyer_name'] or not data['unit_number']:
                raise ValueError("نام خریدار و شماره واحد الزامی است")
            if not data['contract_date_shamsi']:
                raise ValueError("تاریخ قرارداد شمسی مشخص نیست")
            if int(data['contract_amount'] or 0) <= 0:
                raise ValueError("مبلغ قرارداد مشخص نیست")
            if not data['installments']:
                raise ValueError("برنامه اقساط پیدا نشد")
            total = sum(int(x.get('amount') or 0) for x in data['installments'])
            if total != int(data['contract_amount']):
                raise ValueError(f"جمع اقساط {fmt_money(total)} با قرارداد {fmt_money(data['contract_amount'])} برابر نیست")
        except Exception as exc:
            await update.effective_message.reply_text(f"⚠️ فرم فروش کامل نیست: {exc}\n\n{_sale_form_help()}", parse_mode="HTML")
            return
        context.user_data['stage7_sale_draft'] = data
        ok = await _send_sale_draft_preview(update.effective_message, context)
        if not ok:
            # Draft is intentionally preserved. When Telegram connectivity returns, /draft re-displays it.
            log.warning("Sale form parsed and saved, but preview could not be delivered. Use /draft after connectivity returns.")
        return

    if mode == 'RECEIVE':
        data = parse_received_payment_form(text)
        sale = REVENUE.get_sale(data.get('sale_id') or '')
        try:
            if not sale or sale.get('status') == 'CANCELLED':
                raise ValueError("Sale ID معتبر نیست")
            if int(data.get('amount') or 0) <= 0:
                raise ValueError("مبلغ وصول مشخص نیست")
            if not data.get('received_date_shamsi'):
                raise ValueError("تاریخ وصول شمسی مشخص نیست")
        except Exception as exc:
            await update.effective_message.reply_text(f"⚠️ فرم وصول کامل نیست: {exc}\n\n{_receipt_form_help()}", parse_mode="HTML")
            return
        context.user_data['stage7_receipt_draft'] = data
        ok = await _send_receipt_draft_preview(update.effective_message, context)
        if not ok:
            log.warning("Receipt form parsed and saved, but preview could not be delivered. Use /draft after connectivity returns.")
        return


async def handle_stage7_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    data = query.data or ''

    if data == 's7_salecancel':
        context.user_data.pop('stage7_sale_draft', None)
        context.user_data.pop('stage7_mode', None)
        await query.answer("لغو شد")
        await query.edit_message_text("❌ ثبت فروش لغو شد.")
        return

    if data == 's7_saleok':
        draft = context.user_data.get('stage7_sale_draft')
        if not draft:
            await query.answer("پیش‌نویس فروش پیدا نشد؛ /newsale را دوباره بزن.", show_alert=True)
            return
        try:
            ids = await asyncio.to_thread(
                REVENUE.create_sale_bundle,
                **draft,
                source='PRIVATE_TELEGRAM',
                actor_id=str(CONFIG.admin_user_id),
            )
            if CONFIG.buyer_reminders_enabled:
                await asyncio.to_thread(
                    REVENUE.ensure_all_open_installment_reminders,
                    reminder_time=CONFIG.buyer_reminder_time,
                    days_before=CONFIG.buyer_reminder_days_before,
                    days_after=CONFIG.buyer_reminder_days_after,
                    telegram=True,
                    email=False,
                )
            sheet_result = await s6.run_sheet_sync_once() if s6.SHEETS is not None else 'Sheets off'
        except Exception as exc:
            await query.answer(str(exc)[:180], show_alert=True)
            return
        context.user_data.pop('stage7_sale_draft', None)
        context.user_data.pop('stage7_mode', None)
        await query.answer("فروش ثبت شد ✅")
        await query.edit_message_text(
            "✅ <b>قرارداد فروش ثبت شد.</b>\n"
            f"Sale ID: <code>{html.escape(ids['sale_id'])}</code>\n"
            f"Unit ID: <code>{html.escape(ids['unit_id'])}</code>\n"
            f"تعداد اقساط: {len(ids['installment_ids'])}\n"
            "💰 تنخواه تغییر نکرد؛ چون هنوز وصول واقعی ثبت نشده است.\n\n"
            + _sale_detail_text(ids['sale_id']),
            parse_mode='HTML',
        )
        return

    if data == 's7_rcvdraftcancel':
        context.user_data.pop('stage7_receipt_draft', None)
        context.user_data.pop('stage7_mode', None)
        await query.answer("لغو شد")
        await query.edit_message_text("❌ ثبت وصول لغو شد؛ هیچ اثر مالی ایجاد نشد.")
        return

    if data == 's7_rcvok':
        draft = context.user_data.get('stage7_receipt_draft')
        if not draft:
            await query.answer("پیش‌نویس وصول پیدا نشد؛ /receive را دوباره بزن.", show_alert=True)
            return
        try:
            ids = await asyncio.to_thread(
                REVENUE.record_received_payment,
                **draft,
                source='PRIVATE_TELEGRAM',
                actor_id=str(CONFIG.admin_user_id),
            )
            sheet_result = await s6.run_sheet_sync_once() if s6.SHEETS is not None else 'Sheets off'
        except Exception as exc:
            await query.answer(str(exc)[:180], show_alert=True)
            return
        context.user_data.pop('stage7_receipt_draft', None)
        context.user_data.pop('stage7_mode', None)
        rp_id = ids['received_payment_id']
        await query.answer("وصول ثبت شد ✅")
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔗 پیشنهاد تطبیق با اقساط", callback_data=f"s7_matchshow|{rp_id}"),
            InlineKeyboardButton("🚫 لغو این وصول", callback_data=f"s7_rcvcancel|{rp_id}"),
        ]])
        await query.edit_message_text(
            "✅ <b>وصول واقعی ثبت شد و وارد تنخواه شد.</b>\n"
            f"Received ID: <code>{html.escape(rp_id)}</code>\n"
            f"Transaction: <code>{html.escape(ids['transaction_id'])}</code>\n\n"
            "⚠️ هنوز هیچ قسطی بسته نشده؛ تطبیق مرحله جداگانه است.\n\n"
            + s6.snapshot_text(),
            parse_mode='HTML', reply_markup=kb,
        )
        return

    if data.startswith('s7_matchshow|'):
        rp_id = data.split('|', 1)[1]
        try:
            text = _match_preview_text(rp_id)
        except Exception as exc:
            await query.answer(str(exc)[:180], show_alert=True)
            return
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ تأیید تطبیق", callback_data=f"s7_matchok|{rp_id}"),
            InlineKeyboardButton("↩️ فعلاً نه", callback_data=f"s7_matchno|{rp_id}"),
        ]])
        await query.answer()
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=kb)
        return

    if data.startswith('s7_matchno|'):
        await query.answer("تطبیق انجام نشد")
        await query.edit_message_text("↩️ وصول در حالت تطبیق‌نشده باقی ماند. بعداً از /unmatched می‌توانی دوباره بررسی کنی.")
        return

    if data.startswith('s7_matchok|'):
        rp_id = data.split('|', 1)[1]
        rp = REVENUE.get_received_payment(rp_id)
        if not rp:
            await query.answer("وصول پیدا نشد", show_alert=True)
            return
        try:
            result = await asyncio.to_thread(REVENUE.match_receipt_fifo, rp_id, source='PRIVATE_TELEGRAM', actor_id=str(CONFIG.admin_user_id))
            if s6.SHEETS is not None:
                await s6.run_sheet_sync_once()
        except Exception as exc:
            await query.answer(str(exc)[:180], show_alert=True)
            return
        await query.answer("تطبیق انجام شد ✅")
        text = (
            "✅ <b>تطبیق اقساط انجام شد.</b>\n"
            f"تخصیص‌یافته: <b>{html.escape(fmt_money(result['allocated']))}</b>\n"
            f"بدون تخصیص: <b>{html.escape(fmt_money(result['unallocated']))}</b>\n\n"
            + _sale_detail_text(str(rp['sale_id']))
        )
        await query.edit_message_text(text, parse_mode='HTML')
        return

    if data.startswith('s7_rcvcancel|'):
        rp_id = data.split('|', 1)[1]
        try:
            changed = await asyncio.to_thread(REVENUE.cancel_unmatched_receipt, rp_id, source='PRIVATE_TELEGRAM', actor_id=str(CONFIG.admin_user_id))
            if s6.SHEETS is not None:
                await s6.run_sheet_sync_once()
        except Exception as exc:
            await query.answer(str(exc)[:180], show_alert=True)
            return
        await query.answer("وصول لغو شد" if changed else "قبلاً لغو شده")
        await query.edit_message_text("🚫 وصول لغو شد و Transaction ورودی آن VOID شد.\n\n" + s6.snapshot_text(), parse_mode='HTML')
        return


async def prepare_buyer_reminders_once() -> int:
    if not CONFIG.buyer_reminders_enabled:
        return 0
    return await asyncio.to_thread(
        REVENUE.ensure_all_open_installment_reminders,
        reminder_time=CONFIG.buyer_reminder_time,
        days_before=CONFIG.buyer_reminder_days_before,
        days_after=CONFIG.buyer_reminder_days_after,
        telegram=True,
        email=False,
    )


async def send_due_buyer_reminders_once(application) -> dict[str, int]:
    if not CONFIG.buyer_reminders_enabled:
        return {'created': 0, 'sent': 0, 'failed': 0, 'expired': 0}
    created = await prepare_buyer_reminders_once()
    # Do not replay slots from much earlier after a long downtime.
    stale_before = (datetime.now() - timedelta(hours=18)).isoformat(timespec='seconds')
    expired = await asyncio.to_thread(REVENUE.expire_stale_installment_reminders, stale_before)
    due = await asyncio.to_thread(REVENUE.get_due_installment_reminders, datetime.now().isoformat(timespec='seconds'), limit=20)
    sent = failed = 0
    for rem in due:
        try:
            await application.bot.send_message(
                chat_id=CONFIG.admin_user_id,
                text=_buyer_reminder_text(rem),
                parse_mode='HTML',
                read_timeout=READ_TIMEOUT,
                write_timeout=WRITE_TIMEOUT,
                connect_timeout=CONNECT_TIMEOUT,
                pool_timeout=POOL_TIMEOUT,
            )
        except (TimedOut, NetworkError) as exc:
            await asyncio.to_thread(DB.log_reminder_failure, rem['reminder_id'], channel='TELEGRAM', details=str(exc))
            failed += 1
        except Exception as exc:
            await asyncio.to_thread(DB.log_reminder_failure, rem['reminder_id'], channel='TELEGRAM', details=f"{exc.__class__.__name__}: {exc}")
            failed += 1
        else:
            await asyncio.to_thread(DB.mark_reminder_sent, rem['reminder_id'], channel='TELEGRAM', details='buyer installment reminder')
            sent += 1
    return {'created': created, 'sent': sent, 'failed': failed, 'expired': expired}


async def buyer_reminder_worker(application):
    while True:
        try:
            result = await send_due_buyer_reminders_once(application)
            if any(result.values()):
                log.info("Buyer reminders: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Buyer reminder worker crashed: %s", exc)
        await asyncio.sleep(CONFIG.reminder_check_interval_seconds)


async def reminders_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    cheque_created = await s6.prepare_cheque_reminders_once()
    buyer_created = await prepare_buyer_reminders_once()
    counts = await asyncio.to_thread(DB.reminder_counts)
    await update.effective_message.reply_text(
        "⏰ <b>وضعیت Reminderها</b>\n"
        f"چک: از {CONFIG.cheque_reminder_days_before} روز قبل | زمان‌ها: <code>{html.escape(', '.join(CONFIG.cheque_reminder_times))}</code>\n"
        f"خریدار: {CONFIG.buyer_reminder_days_before} روز قبل، روز سررسید، تا {CONFIG.buyer_reminder_days_after} روز بعد | زمان: <code>{html.escape(CONFIG.buyer_reminder_time)}</code>\n"
        f"ساخته‌شده در این اجرا: چک {cheque_created} | خریدار {buyer_created}\n"
        f"Scheduled: {counts.get('SCHEDULED',0)} | Sent: {counts.get('SENT',0)} | Cancelled: {counts.get('CANCELLED',0)}",
        parse_mode='HTML',
    )


async def reminder_check_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    cheque = await s6.send_due_cheque_reminders_once(context.application)
    buyer = await send_due_buyer_reminders_once(context.application)
    await update.effective_message.reply_text(
        "✅ Reminder check اجرا شد.\n"
        f"چک: {cheque}\n"
        f"خریداران: {buyer}"
    )


async def buyer_reminders_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != CONFIG.admin_user_id:
        return
    created = await prepare_buyer_reminders_once()
    rows = REVENUE.get_due_installment_reminders(datetime.now().isoformat(timespec='seconds'), limit=20)
    await update.effective_message.reply_text(
        f"👥 Reminder خریداران فعال است: {'بله' if CONFIG.buyer_reminders_enabled else 'خیر'}\n"
        f"قاعده: {CONFIG.buyer_reminder_days_before} روز قبل + روز سررسید + تا {CONFIG.buyer_reminder_days_after} روز بعد\n"
        f"ساعت: {CONFIG.buyer_reminder_time}\n"
        f"Reminder جدید ساخته شد: {created}\n"
        f"الان آماده ارسال: {len(rows)}"
    )


async def post_init(application):
    global BUYER_REMINDER_TASK
    await s6.post_init(application)
    # RevenueService migration is already complete at module import.
    if CONFIG.buyer_reminders_enabled:
        try:
            created = await prepare_buyer_reminders_once()
            log.info("Buyer reminder bootstrap OK: created=%s", created)
        except Exception as exc:
            log.warning("Buyer reminder bootstrap failed: %s", exc)
        BUYER_REMINDER_TASK = asyncio.create_task(buyer_reminder_worker(application), name='peymaan-buyer-reminders')


async def post_shutdown(application):
    global BUYER_REMINDER_TASK
    if BUYER_REMINDER_TASK:
        BUYER_REMINDER_TASK.cancel()
        try:
            await BUYER_REMINDER_TASK
        except asyncio.CancelledError:
            pass
        BUYER_REMINDER_TASK = None
    await s6.post_shutdown(application)


async def application_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, (TimedOut, NetworkError)):
        log.warning("Telegram network error handled: %s", err)
        return
    log.error("Unhandled Stage 7 Telegram error", exc_info=(type(err), err, err.__traceback__) if err else None)


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

    # Stage 7 commands
    app.add_handler(CommandHandler('sales', sales_private))
    app.add_handler(CommandHandler('sale', sale_private))
    app.add_handler(CommandHandler('newsale', new_sale_private))
    app.add_handler(CommandHandler('draft', draft_private))
    app.add_handler(CommandHandler('receive', receive_private))
    app.add_handler(CommandHandler('unmatched', unmatched_private))
    app.add_handler(CommandHandler('buyerreminders', buyer_reminders_private))
    app.add_handler(CallbackQueryHandler(handle_stage7_callback, pattern=r'^s7_'))
    # Stage 7 form handler in group 0; legacy private edit handler is group 1.
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handle_stage7_private_text), group=0)

    # Existing Stage 4-6 commands/workflows
    app.add_handler(CommandHandler('start', start_private))
    app.add_handler(CommandHandler('status', status_private))
    app.add_handler(CommandHandler('sync', s6.sync_private))
    app.add_handler(CommandHandler('repairledger', s6.repair_ledger_private))
    app.add_handler(CommandHandler('rebuildsheets', s6.rebuild_sheets_private))
    app.add_handler(CommandHandler('reactiontest', s6.reaction_test_private))
    app.add_handler(CommandHandler('cheques', s6.cheques_private))
    app.add_handler(CommandHandler('reminders', reminders_private))
    app.add_handler(CommandHandler('remindercheck', reminder_check_private))
    app.add_handler(CallbackQueryHandler(s6.handle_cheque_callback, pattern=r'^s6_(cash|return|cancel)\|'))
    app.add_handler(CallbackQueryHandler(s6.handle_callback, pattern=r'^s5_(ok|no|edit|postedit|delete|deleteyes|deletecancel|revok|revno)\|'))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, s6.handle_private_edit_text), group=1)
    app.add_handler(MessageHandler(
        filters.UpdateType.EDITED_MESSAGE & filters.ChatType.GROUPS & (filters.TEXT | filters.PHOTO),
        s6.handle_edited_group_message,
    ))
    app.add_handler(MessageHandler(
        filters.UpdateType.MESSAGE & filters.ChatType.GROUPS & (filters.TEXT | filters.PHOTO),
        s6.handle_group_message,
    ))
    app.add_error_handler(application_error_handler)
    log.info("Stage 7 bot starting. DB=%s", CONFIG.db_path)
    app.run_polling(timeout=POLLING_TIMEOUT, bootstrap_retries=-1, drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
