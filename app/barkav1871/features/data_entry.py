"""Canonical manual transaction entry over the audited FinanceDB write API."""

from __future__ import annotations

from datetime import date
import tkinter as tk
from tkinter import messagebox, ttk

from barkav1871.design.controls import fa, parse_int
from barkav1871.services import FinanceDB


class DataEntryPanel(ttk.Frame):
    """Posts one explicit, validated ledger transaction at a time.

    AI and Telegram pending approval remain separate integrations; this panel
    does not bypass their review flow.
    """

    _FIELDS = (
        ("event_date", "تاریخ میلادی (YYYY-MM-DD)"),
        ("shamsi_date", "تاریخ شمسی"),
        ("amount", "مبلغ (تومان)"),
        ("category", "دسته‌بندی"),
        ("party", "طرف حساب"),
        ("description", "شرح"),
    )

    def __init__(self, parent, *, db: FinanceDB, on_posted=None):
        super().__init__(parent, padding=12, style="Panel.TFrame")
        self.db = db
        self.on_posted = on_posted
        self.values = {key: tk.StringVar() for key, _label in self._FIELDS}
        self.direction = tk.StringVar(value="ورودی")
        self._build()
        self.reset()

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="Panel.TFrame")
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="ثبت تراکنش", style="Primary.TButton", command=self.post).pack(side="right")
        ttk.Button(toolbar, text="پاک‌کردن فرم", style="Toolbar.TButton", command=self.reset).pack(side="right", padx=4)
        ttk.Label(toolbar, text="ثبت دیتا", style="Title.TLabel", anchor="e").pack(side="right", fill="x", expand=True, padx=12)

        form = ttk.Frame(self, style="Panel.TFrame")
        form.pack(fill="x", anchor="ne")
        form.grid_columnconfigure(0, weight=1)
        ttk.Label(form, text="نوع تراکنش", style="Panel.TLabel", anchor="e").grid(row=0, column=1, sticky="e", padx=(12, 6), pady=6)
        direction = ttk.Combobox(form, textvariable=self.direction, values=("ورودی", "خروجی"), state="readonly", justify="right")
        direction.grid(row=0, column=0, sticky="ew", padx=(6, 12), pady=6)
        for index, (key, label) in enumerate(self._FIELDS, start=1):
            ttk.Label(form, text=label, style="Panel.TLabel", anchor="e").grid(row=index, column=1, sticky="e", padx=(12, 6), pady=6)
            ttk.Entry(form, textvariable=self.values[key], justify="right").grid(row=index, column=0, sticky="ew", padx=(6, 12), pady=6)

        review_head = ttk.Frame(self, style="Panel.TFrame")
        review_head.pack(fill="x", pady=(12, 4))
        ttk.Button(review_head, text="بروزرسانی صف", style="Toolbar.TButton", command=self.refresh_reviews).pack(side="right")
        ttk.Label(review_head, text="رکوردهای ثبت دیتا — در انتظار بازبینی", style="Title.TLabel", anchor="e").pack(
            side="right", fill="x", expand=True, padx=12)
        columns = ("date", "type", "text", "amount", "confidence", "status")
        self.review_tree = ttk.Treeview(self, columns=columns, show="headings", style="Barkav.Data.Treeview", selectmode="browse")
        for key, label, width in (
            ("date", "تاریخ", 120), ("type", "نوع", 105), ("text", "متن کاربر / بابت", 360),
            ("amount", "مبلغ AI", 140), ("confidence", "AI", 70), ("status", "وضعیت", 125),
        ):
            self.review_tree.heading(key, text=label, anchor="e")
            self.review_tree.column(key, anchor="e", width=width, stretch=True)
        self.review_tree.configure(displaycolumns=tuple(reversed(columns)))
        self.review_tree.pack(fill="both", expand=True, pady=(0, 2))

    def reset(self) -> None:
        for value in self.values.values():
            value.set("")
        self.direction.set("ورودی")
        self.values["event_date"].set(date.today().isoformat())
        self.values["category"].set("سایر")
        self.refresh_reviews()

    def refresh_reviews(self) -> None:
        for item in self.review_tree.get_children():
            self.review_tree.delete(item)
        for row in self.db.list_pending_reviews():
            payload = row.get("payload") or {}
            amount = payload.get("amount") or payload.get("final_amount") or 0
            confidence = row.get("confidence")
            self.review_tree.insert("", "end", iid=str(row.get("pending_id")), values=(
                row.get("message_date") or row.get("created_at") or "—",
                row.get("detected_type") or "—", row.get("raw_text") or payload.get("description") or "—",
                f"{fa(f'{int(amount):,}')} تومان" if amount else "—",
                fa(f"{float(confidence) * 100:.0f}٪") if confidence is not None else "—",
                row.get("status") or "—",
            ))

    def post(self) -> None:
        event_date = self.values["event_date"].get().strip()
        try:
            date.fromisoformat(event_date)
            amount = parse_int(self.values["amount"].get())
            if amount <= 0:
                raise ValueError("مبلغ باید بزرگ‌تر از صفر باشد.")
            category = self.values["category"].get().strip()
            if not category:
                raise ValueError("دسته‌بندی لازم است.")
            direction = "IN" if self.direction.get() == "ورودی" else "OUT"
            party = self.values["party"].get().strip() or None
            transaction_id = self.db.post_transaction(
                event_date=event_date, shamsi_date=self.values["shamsi_date"].get().strip() or None,
                direction=direction, amount=amount, category=category,
                payer_name=party if direction == "IN" else None,
                receiver_name=party if direction == "OUT" else None,
                description=self.values["description"].get().strip(), source_type="GUI_18_7_1", actor_id="GUI_18_7_1",
            )
        except (TypeError, ValueError) as exc:
            messagebox.showwarning("ثبت دیتا", str(exc), parent=self)
            return
        messagebox.showinfo("ثبت دیتا", f"تراکنش {transaction_id} ثبت شد.", parent=self)
        self.reset()
        if self.on_posted:
            self.on_posted()
