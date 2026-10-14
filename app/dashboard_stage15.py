from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox

from dashboard_stage14 import Stage14Dashboard
from telegram_history_import import import_telegram_export
import dashboard_stage14 as d14


class Stage15Dashboard(Stage14Dashboard):
    def __init__(self):
        super().__init__()
        name=os.getenv("PEYMAAN_ACTIVE_PROJECT_NAME","").strip()
        pid=os.getenv("PEYMAAN_ACTIVE_PROJECT_ID","").strip()
        suffix=f" — {name} ({pid})" if name or pid else ""
        self.title("Peymaan V2 — Stage 15 Receipt Vision"+suffix)

    def import_old_telegram_history(self):
        path=filedialog.askopenfilename(
            title="انتخاب JSON خروجی Telegram Desktop",
            filetypes=[("Telegram JSON","*.json"),("JSON","*.json")],
            parent=self,
        )
        if not path:return
        try:
            result=import_telegram_export(d14.DB,path,receipt_service=d14.APPROVAL.receipts)
            msg=(
                f"چت‌ها: {result.chats:,}\n"
                f"کل پیام‌های بررسی‌شده: {result.scanned:,}\n"
                f"کاندیدهای واردشده: {result.candidates:,}\n"
                f"  • دارای عکس/رسانه: {result.media_candidates:,}\n"
                f"  • متن مالی محتمل: {result.text_candidates:,}\n"
                f"پیش‌نویس جدید: {result.created:,}\n"
                f"تکراری: {result.duplicates:,}\n"
                f"نادیده‌گرفته‌شده: {result.skipped:,}\n"
                f"فایل رسانه پیدا نشد: {result.media_missing:,}\n"
            )
            if result.media_missing:
                msg += "\n⚠️ برای موارد Media Missing، هنگام Export تلگرام گزینه Photos/Files را هم فعال کن و پوشه خروجی را جابه‌جا نکن.\n"
            if result.media_pending_ids:
                msg += f"\n{len(result.media_pending_ids):,} تصویر برای AI Vision آماده است."
            messagebox.showinfo("Import تاریخچه تلگرام",msg,parent=self)
            if self.approval_center:
                self.approval_center.refresh()
                if result.media_pending_ids and messagebox.askyesno(
                    "AI Vision",
                    f"{len(result.media_pending_ids):,} تصویر آرشیو شد. همین حالا تحلیل AI آنها در پس‌زمینه شروع شود؟\n\n"
                    "هیچ موردی خودکار ثبت مالی نمی‌شود؛ همه در مرکز تأیید باقی می‌مانند.",
                    parent=self,
                ):
                    self.approval_center._run_ai_ids(list(result.media_pending_ids))
        except Exception as exc:
            messagebox.showerror("Import تاریخچه تلگرام",str(exc),parent=self)


if __name__=="__main__":
    Stage15Dashboard().mainloop()
