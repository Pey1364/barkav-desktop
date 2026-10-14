"""Canonical read-only manager-account view derived from FinanceDB."""

from __future__ import annotations

from datetime import date
from tkinter import ttk

from barkav1871.design.controls import fa
from barkav1871.services import FinanceDB, LedgerQueryService


def _toman(value: int) -> str:
    return f"{fa(f'{int(value or 0):,}')} تومان"


class ManagerAccountPanel(ttk.Frame):
    def __init__(self, parent, *, db: FinanceDB):
        super().__init__(parent, padding=12, style="Panel.TFrame")
        self.db = db
        self.query = LedgerQueryService(db)
        self.values: dict[str, ttk.Label] = {}
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="Panel.TFrame")
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="بروزرسانی", style="Toolbar.TButton", command=self.refresh).pack(side="right")
        ttk.Label(toolbar, text="حساب مدیر", style="Title.TLabel", anchor="e").pack(side="right", fill="x", expand=True, padx=12)
        grid = ttk.Frame(self, style="Panel.TFrame")
        grid.pack(fill="x")
        for column in range(2):
            grid.grid_columnconfigure(column, weight=1, uniform="manager")
        cards = (("حق‌الزحمهٔ تعلق‌گرفته", "fee"), ("برداشت مدیر", "withdrawals"), ("ماندهٔ حساب مدیر", "balance"), ("میانگین بستانکار ماه جاری", "creditor"), ("میانگین بدهکار ماه جاری", "debtor"))
        for index, (title, key) in enumerate(cards):
            card = ttk.Frame(grid, style="Card.TFrame", padding=16)
            card.grid(row=index // 2, column=1 - (index % 2), sticky="nsew", padx=6, pady=6)
            ttk.Label(card, text=title, style="Muted.TLabel", anchor="e").pack(fill="x")
            label = ttk.Label(card, text="—", style="Summary.TLabel", anchor="e")
            label.pack(fill="x", pady=(8, 0))
            self.values[key] = label

        table_box = ttk.LabelFrame(self, text="ریز برداشت‌های ثبت‌شده", padding=8, style="TLabelframe")
        table_box.pack(fill="both", expand=True, pady=(12, 0))
        columns = ("date", "amount", "receiver", "description", "source")
        self.withdrawals_tree = ttk.Treeview(table_box, columns=columns, show="headings", style="Barkav.Data.Treeview", selectmode="browse")
        for key, label, width in (
            ("date", "تاریخ", 130), ("amount", "مبلغ (تومان)", 180), ("receiver", "دریافت‌کننده", 210),
            ("description", "شرح", 420), ("source", "منبع", 140),
        ):
            self.withdrawals_tree.heading(key, text=label, anchor="e")
            self.withdrawals_tree.column(key, anchor="e", width=width, stretch=True)
        self.withdrawals_tree.configure(displaycolumns=tuple(reversed(columns)))
        self.withdrawals_tree.pack(fill="both", expand=True)

    def refresh(self) -> None:
        snapshot = self.db.snapshot()
        today = date.today()
        exposure = self.db.manager_exposure(today.replace(day=1).isoformat(), today.isoformat())
        self.values["fee"].configure(text=_toman(snapshot.manager_fee_accrued))
        self.values["withdrawals"].configure(text=_toman(snapshot.manager_withdrawals))
        self.values["balance"].configure(text=_toman(snapshot.manager_balance))
        self.values["creditor"].configure(text=_toman(exposure.average_creditor_balance))
        self.values["debtor"].configure(text=_toman(exposure.average_debtor_balance))
        for item in self.withdrawals_tree.get_children():
            self.withdrawals_tree.delete(item)
        for row in self.query.list_manager_withdrawals():
            self.withdrawals_tree.insert("", "end", values=(
                row.get("shamsi_date") or row.get("event_date") or "—", _toman(row.get("amount") or 0),
                row.get("receiver_name") or "—", row.get("description") or "—", row.get("source_type") or "—",
            ))
