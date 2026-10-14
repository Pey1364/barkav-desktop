from __future__ import annotations

import asyncio
import json
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from dashboard_stage12 import (
    Stage12Dashboard, SmartTable, COLORS, add_tooltip, money, DB, BASE_DIR, CONFIG
)
from approval_service import ApprovalCenterService
from ui_stage10 import parse_int
from finance_db import FinanceDB
from receipt_ai_provider import build_receipt_vision_parser

AI_PARSER = build_receipt_vision_parser(BASE_DIR, gemini_api_key=CONFIG.gemini_api_key, gemini_model=CONFIG.gemini_model)
APPROVAL = ApprovalCenterService(DB, BASE_DIR, parser=AI_PARSER)


def _ai_engine_mode_at_startup() -> str:
    """The AI Machine mode actually used to build AI_PARSER's provider chain
    above, read the same way build_receipt_vision_parser reads it.

    The Settings "AI Machine" box only takes effect on the next full app
    restart (AI_PARSER is a process-lifetime singleton built once, here).
    Capturing the mode active at that moment lets a later Gemini-status
    check tell "no key configured" apart from "a key exists and the
    *current* setting would include Gemini, but this process was built
    before that change and needs a restart" instead of showing the same
    generic message for both.
    """
    if not os.getenv("STAGE4_DB_PATH"):
        return "AUTO"
    try:
        from v18_store import load_ui
        return str(load_ui().get("ai_engine_mode") or "AUTO").strip().upper()
    except Exception:
        return "AUTO"


AI_ENGINE_MODE_AT_STARTUP = _ai_engine_mode_at_startup()

TYPE_LABELS = {
    "EXPENSE": "هزینه ساخت",
    "INCOME": "ورودی",
    "OUTFLOW": "خروجی",
    "CHEQUE": "چک",
    "DOCUMENT": "داکیومنت",
    "INFO": "اطلاع‌رسانی",
    "UNKNOWN": "نامشخص",
}
TYPE_VALUES = ["EXPENSE", "INCOME", "OUTFLOW", "CHEQUE", "DOCUMENT", "INFO", "UNKNOWN"]
PAYMENT_METHODS = ["CASH", "BANK_TRANSFER", "CARD", "CHEQUE", "UNKNOWN"]
PAYMENT_STATES = ["PAID", "PARTIAL", "UNPAID", "CHEQUE_CLEARING", "UNKNOWN"]


def _fmt_conf(v: Any) -> str:
    try:
        return f"{float(v) * 100:.0f}%"
    except Exception:
        return "-"


class ApprovalCenter(ttk.Frame):
    """GUI approval center for Telegram financial messages and receipts."""

    def __init__(self, parent: tk.Misc, on_posted=None):
        super().__init__(parent, padding=6)
        self.on_posted = on_posted
        self.rows: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.vars: dict[str, tk.StringVar] = {}
        self._build()
        self.refresh()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 4))
        ttk.Label(top, text="مرکز تأیید رسیدها و پیام‌های مالی", font=("Tahoma", 10, "bold")).pack(side="right")
        ttk.Label(top, text="روش تأیید:").pack(side="right", padx=(16, 3))
        self.channel = tk.StringVar(value=self._channel_label(DB.get_setting("approval_channels", "BOTH") or "BOTH"))
        cmb = ttk.Combobox(top, textvariable=self.channel, state="readonly", width=18,
                           values=["هر دو (برنامه + تلگرام)", "فقط برنامه", "فقط تلگرام"])
        cmb.pack(side="right")
        cmb.bind("<<ComboboxSelected>>", lambda e: self._save_channel())
        add_tooltip(cmb, "مشخص می‌کند کارت تأیید در خصوصی تلگرام هم ارسال شود یا فقط در برنامه دیده شود.")
        b = ttk.Button(top, text="🔄 بروزرسانی", command=self.refresh)
        b.pack(side="left")
        add_tooltip(b, "بارگذاری دوباره موارد در انتظار از SQLite")
        try:
            ocr_ok = APPROVAL.receipts.ocr.available()
            lang = APPROVAL.receipts.ocr.effective_lang() if ocr_ok else "-"
            ocr_text = f"OCR محلی: آماده ({lang})" if ocr_ok else "OCR محلی: نصب/در دسترس نیست"
            ttk.Label(top, text=ocr_text, foreground=COLORS["green"] if ocr_ok else COLORS["orange"]).pack(side="left", padx=10)
        except Exception:
            pass

        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True)
        left = ttk.Frame(pane, padding=(0, 0, 4, 0))
        right = ttk.Frame(pane, padding=(4, 0, 0, 0))
        pane.add(left, weight=3)
        pane.add(right, weight=4)

        self.table = SmartTable(left, [
            ("date", "تاریخ", 105),
            ("type", "نوع", 95),
            ("amount", "مبلغ", 125),
            ("desc", "بابت", 220),
            ("conf", "اطمینان مبلغ", 95),
            ("provider", "موتور", 115),
            ("warn", "هشدار", 70),
        ], title="موارد در انتظار تأیید")
        self.table.pack(fill="both", expand=True)
        self.table.tree.bind("<<TreeviewSelect>>", self._select, add="+")
        self.table.tree.bind("<Double-1>", lambda e: self.open_receipt(), add="+")

        # Right: compact source/receipt information
        src = ttk.LabelFrame(right, text="منبع و تحلیل رسید", padding=5)
        src.pack(fill="x", pady=(0, 4))
        self.source_text = tk.Text(src, height=5, wrap="word", font=("Tahoma", 8), bg="white")
        self.source_text.pack(fill="x")
        info = ttk.Frame(src)
        info.pack(fill="x", pady=(4, 0))
        self.receipt_info = tk.StringVar(value="موردی انتخاب نشده")
        ttk.Label(info, textvariable=self.receipt_info, foreground=COLORS["muted"]).pack(side="right")
        open_btn = ttk.Button(info, text="🖼 مشاهده رسید", command=self.open_receipt)
        open_btn.pack(side="left")
        add_tooltip(open_btn, "باز کردن فایل اصلی آرشیوشده رسید/فاکتور")
        ai_btn = ttk.Button(info, text="🤖 تحلیل AI این تصویر", command=self.analyze_current_ai)
        ai_btn.pack(side="left", padx=4)
        add_tooltip(ai_btn, "تصویر آرشیوشده را دوباره با AI Vision تحلیل می‌کند؛ برای موارد Import شده یا تحلیل ناموفق استفاده کن.")
        ai_all = ttk.Button(info, text="🤖 تحلیل همه تصاویر", command=self.analyze_all_ai)
        ai_all.pack(side="left", padx=2)
        add_tooltip(ai_all, "تمام تصاویر در انتظار را در پس‌زمینه با AI Vision تحلیل می‌کند. نتیجه‌ها قبل از ثبت همچنان نیازمند تأیید تو هستند.")

        edit = ttk.LabelFrame(right, text="اطلاعات قابل اصلاح قبل از ثبت", padding=5)
        edit.pack(fill="x", pady=(0, 4))
        fields = [
            ("detected_type", "نوع", "combo_type"),
            ("amount", "مبلغ", "entry"),
            ("invoice_amount", "مبلغ فاکتور", "entry"),
            ("final_amount", "مبلغ نهایی", "entry"),
            ("paid_amount", "پرداخت‌شده", "entry"),
            ("event_date_shamsi", "تاریخ", "entry"),
            ("description", "بابت", "entry"),
            ("expense_category", "نوع هزینه", "entry"),
            ("construction_stage", "مرحله ساخت", "entry"),
            ("payer_name", "واریزکننده", "entry"),
            ("receiver_name", "دریافت‌کننده", "entry"),
            ("payment_method", "روش پرداخت", "combo_method"),
            ("payment_state", "وضعیت پرداخت", "combo_state"),
            ("due_date_shamsi", "سررسید چک", "entry"),
        ]
        for i, (key, label, kind) in enumerate(fields):
            r, c = divmod(i, 2)
            cell = ttk.Frame(edit)
            cell.grid(row=r, column=c, sticky="ew", padx=3, pady=2)
            edit.columnconfigure(c, weight=1)
            ttk.Label(cell, text=label + ":", width=14, anchor="e").pack(side="right")
            var = tk.StringVar()
            self.vars[key] = var
            if kind == "combo_type":
                w = ttk.Combobox(cell, textvariable=var, values=TYPE_VALUES, state="readonly", width=24)
            elif kind == "combo_method":
                w = ttk.Combobox(cell, textvariable=var, values=PAYMENT_METHODS, state="readonly", width=24)
            elif kind == "combo_state":
                w = ttk.Combobox(cell, textvariable=var, values=PAYMENT_STATES, state="readonly", width=24)
            else:
                w = ttk.Entry(cell, textvariable=var, justify="right")
            w.pack(side="right", fill="x", expand=True)

        details = ttk.Panedwindow(right, orient="horizontal")
        details.pack(fill="both", expand=True, pady=(0, 4))
        cframe = ttk.LabelFrame(details, text="هشدارها / اختلاف‌ها", padding=4)
        dframe = ttk.LabelFrame(details, text="موارد مشابه احتمالی", padding=4)
        details.add(cframe, weight=1)
        details.add(dframe, weight=1)
        self.conflicts_text = tk.Text(cframe, height=6, wrap="word", font=("Tahoma", 8), bg="#FFF7E6")
        self.conflicts_text.pack(fill="both", expand=True)
        self.dupes_text = tk.Text(dframe, height=6, wrap="word", font=("Tahoma", 8), bg="#F4F9FD")
        self.dupes_text.pack(fill="both", expand=True)

        actions = ttk.Frame(right)
        actions.pack(fill="x")
        save = ttk.Button(actions, text="💾 ذخیره اصلاحات", command=self.save_edits)
        save.pack(side="right")
        add_tooltip(save, "اصلاحات را روی Pending ذخیره می‌کند؛ هنوز اثر مالی ایجاد نمی‌شود.")
        approve = ttk.Button(actions, text="✅ تأیید و ثبت قطعی", command=self.approve, style="Primary.TButton")
        approve.pack(side="right", padx=4)
        add_tooltip(approve, "همان ثبت قطعی مالی Telegram را از داخل GUI انجام می‌دهد.")
        reject = ttk.Button(actions, text="❌ رد", command=self.reject, style="Danger.TButton")
        reject.pack(side="right")
        add_tooltip(reject, "مورد رد می‌شود و هیچ اثر مالی در Ledger ندارد.")
        link = ttk.Button(actions, text="🔗 اتصال به ثبت موجود", command=self.link_existing)
        link.pack(side="right", padx=4)
        add_tooltip(link, "اگر رسید/فاکتور مربوط به ثبت مالی موجود است، فقط مدرک را متصل می‌کند و هزینه جدید نمی‌سازد.")
        self.status = tk.StringVar(value="")
        ttk.Label(actions, textvariable=self.status, foreground=COLORS["navy"]).pack(side="left")

    @staticmethod
    def _channel_label(v: str) -> str:
        return {"BOTH": "هر دو (برنامه + تلگرام)", "GUI": "فقط برنامه", "TELEGRAM": "فقط تلگرام"}.get(v.upper(), "هر دو (برنامه + تلگرام)")

    def _save_channel(self):
        value = {"هر دو (برنامه + تلگرام)": "BOTH", "فقط برنامه": "GUI", "فقط تلگرام": "TELEGRAM"}.get(self.channel.get(), "BOTH")
        DB.set_setting("approval_channels", value)
        self.status.set("روش تأیید ذخیره شد")

    def refresh(self):
        self.rows = APPROVAL.list_pending(limit=1000)
        def vals(r: dict[str, Any]):
            p = r.get("payload") or {}
            fc = r.get("field_confidences") or p.get("field_confidences") or {}
            conflicts = r.get("conflicts") or []
            amount = p.get("final_amount") or p.get("amount") or 0
            return [
                r.get("message_date") or "-",
                TYPE_LABELS.get(str(p.get("detected_type") or "UNKNOWN"), str(p.get("detected_type") or "UNKNOWN")),
                money(amount),
                p.get("description") or r.get("raw_text") or "-",
                _fmt_conf(fc.get("amount", p.get("confidence", 0))),
                r.get("receipt_provider") or ("متن" if r.get("content_type") == "TEXT" else "-"),
                f"⚠ {len(conflicts)}" if conflicts else "-",
            ]
        self.table.set_rows(self.rows, vals)
        self._update_tab_count()
        if self.current:
            pid = self.current.get("pending_id")
            fresh = next((x for x in self.rows if x.get("pending_id") == pid), None)
            if fresh:
                self.current = fresh
                self._load_current()
            else:
                self.current = None
                self._clear()

    def _update_tab_count(self):
        # Parent notebook tab text gets updated by Stage14Dashboard.
        root = self.winfo_toplevel()
        if hasattr(root, "_update_approval_tab_text"):
            root._update_approval_tab_text(len(self.rows))

    def _select(self, event=None):
        rows = self.table.selected_rows()
        if not rows:
            return
        self.current = rows[0]
        self._load_current()

    def _load_current(self):
        r = self.current or {}
        p = dict(r.get("payload") or {})
        self.source_text.configure(state="normal")
        self.source_text.delete("1.0", "end")
        self.source_text.insert("end", f"پیام اصلی:\n{r.get('raw_text') or '-'}\n")
        ocr = r.get("receipt_ocr_text") or ""
        if ocr:
            self.source_text.insert("end", f"\nOCR محلی:\n{ocr[:2500]}")
        self.source_text.configure(state="disabled")
        for key, var in self.vars.items():
            value = p.get(key, "")
            if key in {"amount", "invoice_amount", "final_amount", "paid_amount"}:
                try: value = f"{int(value or 0):,}"
                except Exception: value = str(value or "")
            var.set(str(value or ""))
        fc = r.get("field_confidences") or p.get("field_confidences") or {}
        vision=p.get("vision_status") or ("در انتظار" if str(r.get("receipt_provider") or "").startswith("PENDING") else "-")
        self.receipt_info.set(
            f"ID: {r.get('pending_id')} | منبع: {r.get('content_type') or '-'} | موتور: {r.get('receipt_provider') or '-'} | "
            f"Vision: {vision} | نوع سند: {r.get('receipt_document_type') or p.get('document_type') or '-'} | "
            f"اعتماد مبلغ: {_fmt_conf(fc.get('amount', p.get('confidence', 0)))}"
        )
        self.conflicts_text.delete("1.0", "end")
        conflicts = r.get("conflicts") or []
        if not conflicts:
            self.conflicts_text.insert("end", "اختلاف مهمی بین پیام، OCR و تحلیل تصویر ثبت نشده است.")
        else:
            for c in conflicts:
                self.conflicts_text.insert("end", "• " + json.dumps(c, ensure_ascii=False) + "\n")
        self.dupes_text.delete("1.0", "end")
        dupes = r.get("duplicate_candidates") or []
        if not dupes:
            self.dupes_text.insert("end", "مورد هم‌مبلغ ثبت‌شده‌ای پیدا نشد.")
        else:
            for d in dupes:
                self.dupes_text.insert(
                    "end", f"• {d.get('entity_type')} | {d.get('entity_id')} | {money(d.get('amount'))} | "
                           f"{d.get('event_date') or '-'} | {d.get('counterparty') or '-'} | امتیاز {d.get('match_score') or 0}\n"
                )

    def _clear(self):
        for v in self.vars.values(): v.set("")
        self.source_text.configure(state="normal"); self.source_text.delete("1.0", "end"); self.source_text.configure(state="disabled")
        self.conflicts_text.delete("1.0", "end"); self.dupes_text.delete("1.0", "end")
        self.receipt_info.set("موردی انتخاب نشده")

    def _payload_from_form(self) -> dict[str, Any]:
        if not self.current:
            raise ValueError("ابتدا یک مورد را انتخاب کن.")
        p = dict(self.current.get("payload") or {})
        for key, var in self.vars.items():
            raw = var.get().strip()
            if key in {"amount", "invoice_amount", "final_amount", "paid_amount"}:
                p[key] = parse_int(raw)
            else:
                p[key] = raw
        p["is_cheque"] = p.get("payment_method") == "CHEQUE" or p.get("detected_type") == "CHEQUE" or bool(p.get("is_cheque"))
        p["manager_fee_eligible"] = p.get("detected_type") == "EXPENSE"
        return p

    def _run_ai_ids(self, pending_ids: list[str]):
        if not pending_ids:
            self.status.set("تصویری برای تحلیل پیدا نشد")
            return
        self.status.set(f"AI: شروع تحلیل {len(pending_ids)} تصویر...")
        def worker():
            ok=fail=0;last_error=""
            for pid in pending_ids:
                try:
                    asyncio.run(APPROVAL.analyze_pending_with_ai(pid));ok+=1
                except Exception as exc:
                    fail+=1;last_error=f"{exc.__class__.__name__}: {exc}"
            def done():
                self.status.set(f"AI: {ok} موفق | {fail} ناموفق" + (f" | {last_error[:90]}" if fail else ""))
                self.refresh()
            self.after(0,done)
        threading.Thread(target=worker,daemon=True,name="peymaan-ai-receipts").start()

    def analyze_current_ai(self):
        if not self.current:
            messagebox.showwarning("تحلیل AI","ابتدا یک مورد تصویری را انتخاب کن.",parent=self);return
        self._run_ai_ids([str(self.current.get("pending_id"))])

    def analyze_all_ai(self):
        ids=[]
        for r in self.rows:
            path=str(r.get("receipt_image_path") or "")
            if not path:
                try:
                    atts=DB.list_pending_attachments(r.get("pending_id"))
                    path=next((str(a.get("local_path") or "") for a in atts if str(a.get("mime_type") or "").lower().startswith("image/")),"")
                except Exception:
                    path=""
            if path and Path(path).exists(): ids.append(str(r.get("pending_id")))
        if not ids:
            messagebox.showinfo("تحلیل AI","هیچ تصویر آرشیوشده‌ای در صف نیست.",parent=self);return
        if len(ids)>50 and not messagebox.askyesno("تحلیل AI",f"{len(ids)} تصویر در صف است. تحلیل همه ممکن است زمان‌بر و دارای هزینه API باشد. ادامه؟",parent=self):return
        self._run_ai_ids(ids)

    def save_edits(self):
        if not self.current:
            messagebox.showwarning("مرکز تأیید", "یک مورد را انتخاب کن.", parent=self)
            return
        try:
            payload = self._payload_from_form()
            APPROVAL.save_payload(self.current["pending_id"], payload, learn=True)
            self.status.set("اصلاحات ذخیره شد؛ هنوز ثبت مالی نشده است.")
            self.refresh()
        except Exception as exc:
            messagebox.showerror("خطا", str(exc), parent=self)

    def approve(self):
        if not self.current:
            messagebox.showwarning("مرکز تأیید", "یک مورد را انتخاب کن.", parent=self)
            return
        pid = self.current["pending_id"]
        try:
            payload = self._payload_from_form()
            APPROVAL.save_payload(pid, payload, learn=True)
            if (self.current.get("conflicts") or []) and not messagebox.askyesno(
                "هشدار اختلاف", "برای این رسید اختلاف بین پیام/OCR/تحلیل ثبت شده است. با همین اطلاعات ثبت قطعی شود؟", parent=self
            ):
                return
            result = APPROVAL.approve(pid, actor_id="GUI")
            self.status.set(f"ثبت شد: {result.posting.posting_type}")
            self.current = None
            self.refresh()
            if self.on_posted:
                self.on_posted()
        except Exception as exc:
            messagebox.showerror("ثبت انجام نشد", str(exc), parent=self)

    def link_existing(self):
        if not self.current:
            return
        candidates = [d for d in (self.current.get("duplicate_candidates") or []) if str(d.get("entity_type") or "").upper() in {"EXPENSE", "TRANSACTION", "CHEQUE"}]
        if not candidates:
            messagebox.showinfo("اتصال", "ثبت مالی مناسبی برای اتصال خودکار پیشنهاد نشده است.", parent=self)
            return
        d = candidates[0]
        msg = (
            "این رسید بدون ایجاد اثر مالی جدید به ثبت زیر متصل شود؟\n\n"
            f"نوع: {d.get('entity_type')}\nID: {d.get('entity_id')}\nمبلغ: {money(d.get('amount'))}\n"
            f"تاریخ: {d.get('event_date') or '-'}\nشرح: {d.get('description') or '-'}"
        )
        if not messagebox.askyesno("اتصال به ثبت موجود", msg, parent=self):
            return
        try:
            APPROVAL.link_existing(
                self.current["pending_id"], entity_type=str(d.get("entity_type")),
                entity_id=str(d.get("entity_id")), actor_id="GUI",
            )
            self.status.set("رسید به ثبت موجود متصل شد؛ هزینه جدید ساخته نشد.")
            self.current = None
            self.refresh()
            if self.on_posted:
                self.on_posted()
        except Exception as exc:
            messagebox.showerror("اتصال انجام نشد", str(exc), parent=self)

    def reject(self):
        if not self.current:
            return
        if not messagebox.askyesno("رد مورد", "این مورد رد شود و هیچ اثر مالی نداشته باشد؟", parent=self):
            return
        try:
            APPROVAL.reject(self.current["pending_id"], actor_id="GUI")
            self.current = None
            self.status.set("مورد رد شد")
            self.refresh()
        except Exception as exc:
            messagebox.showerror("خطا", str(exc), parent=self)

    def open_receipt(self):
        if not self.current:
            return
        path = str(self.current.get("receipt_image_path") or "")
        if not path:
            atts = DB.list_pending_attachments(self.current.get("pending_id"))
            path = str((atts[0] if atts else {}).get("local_path") or "")
        if not path or not Path(path).exists():
            messagebox.showinfo("رسید", "فایل تصویر آرشیوشده برای این مورد موجود نیست.", parent=self)
            return
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            messagebox.showerror("باز کردن فایل", str(exc), parent=self)


class Stage14Dashboard(Stage12Dashboard):
    def __init__(self):
        self.approval_center: ApprovalCenter | None = None
        self.approval_tab: ttk.Frame | None = None
        super().__init__()
        self.title("Peymaan V2 — Stage 14 Receipt Intelligence")
        self._build_approval_center()
        self.after(4000, self._approval_periodic)

    def _build_approval_center(self):
        tab = ttk.Frame(self.notebook)
        self.approval_tab = tab
        self.notebook.insert(1, tab, text="مرکز تأیید")
        self.approval_center = ApprovalCenter(tab, on_posted=self.refresh_all)
        self.approval_center.pack(fill="both", expand=True)

    def _update_approval_tab_text(self, count: int):
        if self.approval_tab is not None:
            try:
                self.notebook.tab(self.approval_tab, text=f"مرکز تأیید ({count})" if count else "مرکز تأیید")
            except Exception:
                pass

    def _approval_periodic(self):
        try:
            if self.approval_center:
                self.approval_center.refresh()
        finally:
            self.after(4000, self._approval_periodic)

    def refresh_all(self):
        super().refresh_all()
        if self.approval_center:
            self.approval_center.refresh()


if __name__ == "__main__":
    Stage14Dashboard().mainloop()
