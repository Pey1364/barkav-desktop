"""Canonical read-only transaction workspaces over the audited ledger."""

from __future__ import annotations

from tkinter import ttk

from barkav1871.design.controls import fa
from barkav1871.services import FinanceDB, LedgerQueryService


def _money(value: int) -> str:
    return f"{fa(f'{int(value or 0):,}')} تومان"


class TransactionsPanel(ttk.Frame):
    """Read-only 18.7 transaction areas; this screen never posts financial records."""

    def __init__(self, parent, *, db: FinanceDB):
        super().__init__(parent, padding=8, style="Panel.TFrame")
        self.queries = LedgerQueryService(db)
        self.trees: dict[str, ttk.Treeview] = {}
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="Panel.TFrame")
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(toolbar, text="بروزرسانی", style="Toolbar.TButton", command=self.refresh).pack(side="right", padx=3)
        ttk.Label(toolbar, text="مدیریت تراکنش‌ها", style="Title.TLabel", anchor="e").pack(side="right", fill="x", expand=True, padx=12)

        self.notebook = ttk.Notebook(self, style="Barkav.TNotebook")
        self.notebook.pack(fill="both", expand=True)
        self._add_table("کلیه تراکنش‌ها", "all", (
            ("date", "تاریخ", 120), ("direction", "نوع", 90), ("amount", "مبلغ (تومان)", 150),
            ("category", "دسته", 150), ("party", "طرف حساب", 180), ("description", "شرح", 360),
        ))
        self._add_table("هزینه ساخت", "expenses", (
            ("date", "تاریخ", 120), ("amount", "مبلغ نهایی (تومان)", 160),
            ("category", "دسته", 160), ("vendor", "فروشنده", 190), ("status", "وضعیت", 130), ("description", "شرح", 360),
        ))
        self._add_table("چک‌ها", "cheques", (
            ("due", "سررسید", 120), ("amount", "مبلغ (تومان)", 150), ("receiver", "گیرنده", 180),
            ("bank", "بانک / سریال", 190), ("status", "وضعیت", 140), ("guarantee", "نوع", 125), ("description", "شرح", 280),
        ))
        self._add_table("ورودی‌ها", "incoming", (
            ("date", "تاریخ", 120), ("amount", "مبلغ (تومان)", 150), ("category", "دسته", 160),
            ("party", "پرداخت‌کننده", 200), ("description", "شرح", 420),
        ))
        self._add_table("خروجی‌ها", "outgoing", (
            ("date", "تاریخ", 120), ("amount", "مبلغ (تومان)", 150), ("category", "دسته", 160),
            ("party", "دریافت‌کننده", 200), ("description", "شرح", 420),
        ))
        self._add_table("تسهیلات", "loans", (
            ("date", "تاریخ دریافت", 130), ("lender", "وام‌دهنده", 200), ("principal", "اصل (تومان)", 150),
            ("paid", "پرداخت‌شده", 150), ("remaining", "مانده", 150), ("next_due", "سررسید بعدی", 130), ("status", "وضعیت", 110),
        ))
        self._add_table("داکیومنت‌ها", "documents", (
            ("created", "ثبت", 160), ("type", "نوع", 150), ("title", "عنوان", 260),
            ("notes", "یادداشت", 360), ("path", "مسیر فایل", 420),
        ))

    def _add_table(self, title: str, key: str, columns: tuple[tuple[str, str, int], ...]) -> None:
        page = ttk.Frame(self.notebook, padding=(4, 6), style="Panel.TFrame")
        names = tuple(column[0] for column in columns)
        tree = ttk.Treeview(page, columns=names, show="headings", style="Barkav.Data.Treeview", selectmode="browse")
        for name, label, width in columns:
            tree.heading(name, text=label, anchor="e")
            tree.column(name, anchor="e", width=width, stretch=True)
        tree.configure(displaycolumns=tuple(reversed(names)))
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        self.notebook.add(page, text=title)
        self.trees[key] = tree

    def _replace(self, key: str, rows: list[tuple[object, ...]]) -> None:
        tree = self.trees[key]
        for item in tree.get_children():
            tree.delete(item)
        for row in rows:
            tree.insert("", "end", values=row)

    def refresh(self) -> None:
        labels = {"IN": "ورودی", "OUT": "خروجی"}
        transactions = self.queries.list_transactions()
        self._replace("all", [
            (row.get("shamsi_date") or row.get("event_date") or "—", labels.get(row.get("direction"), "—"),
             _money(row.get("amount") or 0), row.get("category") or "—",
             (row.get("payer_name") if row.get("direction") == "IN" else row.get("receiver_name")) or "—",
             row.get("description") or "—")
            for row in transactions
        ])
        self._replace("expenses", [
            (row.get("shamsi_date") or row.get("event_date") or "—", _money(row.get("final_amount") or 0),
             row.get("category") or "—", row.get("vendor_name") or "—", row.get("status") or "—", row.get("description") or "—")
            for row in self.queries.list_expenses()
        ])
        self._replace("incoming", [
            (row.get("shamsi_date") or row.get("event_date") or "—", _money(row.get("amount") or 0),
             row.get("category") or "—", row.get("payer_name") or "—", row.get("description") or "—")
            for row in transactions if row.get("direction") == "IN"
        ])
        self._replace("outgoing", [
            (row.get("shamsi_date") or row.get("event_date") or "—", _money(row.get("amount") or 0),
             row.get("category") or "—", row.get("receiver_name") or "—", row.get("description") or "—")
            for row in transactions if row.get("direction") == "OUT"
        ])
        self._replace("cheques", [
            (row.get("due_date_shamsi") or row.get("due_date") or "—", _money(row.get("amount") or 0),
             row.get("receiver_name") or "—", " / ".join(part for part in (row.get("issuer_bank"), row.get("cheque_serial")) if part) or "—",
             row.get("status") or "—", "بابت ضمانت" if row.get("is_guarantee") else "چک مالی", row.get("description") or "—")
            for row in self.queries.list_cheques()
        ])
        self._replace("loans", [
            (row.get("received_date_shamsi") or "—", row.get("lender_name") or "—", _money(row.get("principal_amount") or 0),
             _money(row.get("paid_total") or 0), _money(max(0, int(row.get("total_repayment") or row.get("principal_amount") or 0) - int(row.get("paid_total") or 0))),
             row.get("next_due_shamsi") or "—", row.get("status") or "—")
            for row in self.queries.list_loans()
        ])
        self._replace("documents", [
            (row.get("created_at") or "—", row.get("document_type") or "—", row.get("title") or "—",
             row.get("notes") or "—", row.get("local_path") or "—")
            for row in self.queries.list_documents()
        ])
