"""Canonical contractor directory over the existing market data service."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from barkav1871.design.controls import fa
from barkav1871.services import FinanceDB, MarketService


def _money(value: int) -> str:
    return f"{fa(f'{int(value or 0):,}')} تومان"


class ContractorsPanel(ttk.Frame):
    def __init__(self, parent, *, db: FinanceDB, base_dir):
        super().__init__(parent, padding=8, style="Panel.TFrame")
        self.service = MarketService(db, base_dir)
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="Panel.TFrame")
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(toolbar, text="پیمانکار جدید", style="Primary.TButton", command=self.open_new_contractor).pack(side="right")
        ttk.Button(toolbar, text="بروزرسانی", style="Toolbar.TButton", command=self.refresh).pack(side="right", padx=4)
        ttk.Label(toolbar, text="پیمانکاران", style="Title.TLabel", anchor="e").pack(side="right", fill="x", expand=True, padx=12)
        self.notebook = ttk.Notebook(self, style="Barkav.TNotebook")
        self.notebook.pack(fill="both", expand=True)
        directory_page = ttk.Frame(self.notebook, padding=(4, 6), style="Panel.TFrame")
        contracts_page = ttk.Frame(self.notebook, padding=(4, 6), style="Panel.TFrame")
        statements_page = ttk.Frame(self.notebook, padding=(4, 6), style="Panel.TFrame")
        self.notebook.add(directory_page, text="پیمانکاران")
        self.notebook.add(contracts_page, text="قراردادها")
        self.notebook.add(statements_page, text="صورت‌وضعیت‌ها")
        columns = ("name", "national", "category", "phone", "documents", "paid", "balance", "rating")
        self.tree = ttk.Treeview(directory_page, columns=columns, show="headings", style="Barkav.Data.Treeview")
        for key, label, width in (
            ("name", "نام / شرکت", 210), ("national", "کد ملی", 120), ("category", "تخصص", 150),
            ("phone", "تماس", 130), ("documents", "کارکرد (تومان)", 155), ("paid", "واریزی (تومان)", 155),
            ("balance", "مانده (تومان)", 155), ("rating", "امتیاز", 85),
        ):
            self.tree.heading(key, text=label, anchor="e")
            self.tree.column(key, anchor="e", width=width, stretch=True)
        self.tree.configure(displaycolumns=tuple(reversed(columns)))
        self.tree.pack(fill="both", expand=True)

        self.contract_tree = self._make_table(contracts_page, (
            ("date", "تاریخ", 120), ("contractor", "پیمانکار", 220), ("subject", "موضوع", 300),
            ("phase", "فاز", 80), ("amount", "مبلغ قرارداد", 160), ("accrued", "کارکرد", 160),
            ("paid", "پرداخت", 160), ("balance", "مانده", 160), ("status", "وضعیت", 120),
        ))
        self.statement_tree = self._make_table(statements_page, (
            ("date", "تاریخ", 120), ("contractor", "پیمانکار", 220), ("subject", "قرارداد", 260),
            ("number", "شماره", 120), ("net", "خالص صورت‌وضعیت", 170), ("paid", "پرداخت", 160),
            ("balance", "مانده", 160), ("status", "وضعیت", 120),
        ))

    @staticmethod
    def _make_table(parent, columns: tuple[tuple[str, str, int], ...]) -> ttk.Treeview:
        names = tuple(column[0] for column in columns)
        tree = ttk.Treeview(parent, columns=names, show="headings", style="Barkav.Data.Treeview", selectmode="browse")
        for key, label, width in columns:
            tree.heading(key, text=label, anchor="e")
            tree.column(key, anchor="e", width=width, stretch=True)
        tree.configure(displaycolumns=tuple(reversed(names)))
        tree.pack(fill="both", expand=True)
        return tree

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in self.service.list_entities("CONTRACTOR"):
            name = row.get("company_name") or " ".join(filter(None, (row.get("first_name"), row.get("last_name")))) or "—"
            self.tree.insert("", "end", iid=row["entity_id"], values=(
                name, row.get("national_id") or row.get("foreign_id") or "—", row.get("category") or "—",
                row.get("phone") or "—", _money(row.get("document_total") or 0), _money(row.get("paid_total") or 0),
                _money(row.get("balance") or 0), fa(row.get("rating_total") or 0),
            ))
        for tree in (self.contract_tree, self.statement_tree):
            for item in tree.get_children():
                tree.delete(item)
        for contract in self.service.list_contracts():
            contractor = contract.get("company_name") or " ".join(filter(None, (contract.get("first_name"), contract.get("last_name")))) or "—"
            self.contract_tree.insert("", "end", iid=contract["contract_id"], values=(
                contract.get("contract_date_shamsi") or "—", contractor, contract.get("subject") or "—",
                fa(contract.get("phase_no") or "—"), _money(contract.get("contract_amount") or 0),
                _money(contract.get("statement_total") or 0), _money(contract.get("paid_total") or 0),
                _money(contract.get("balance") or 0), contract.get("status") or "—",
            ))
            for statement in self.service.list_statements(contract["contract_id"]):
                self.statement_tree.insert("", "end", values=(
                    statement.get("statement_date_shamsi") or "—", contractor, contract.get("subject") or "—",
                    statement.get("statement_no") or "—", _money(statement.get("net_amount") or 0),
                    _money(statement.get("paid_amount") or 0), _money(statement.get("balance") or 0), statement.get("status") or "—",
                ))

    def open_new_contractor(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("پیمانکار جدید")
        dialog.transient(self)
        dialog.grab_set()
        fields = (("company_name", "نام شرکت یا پیمانکار"), ("national_id", "کد ملی"), ("category", "تخصص"), ("phone", "شماره تماس"))
        values = {key: tk.StringVar() for key, _label in fields}
        dialog.grid_columnconfigure(0, weight=1)
        for index, (key, label) in enumerate(fields):
            ttk.Label(dialog, text=label, anchor="e").grid(row=index, column=1, padx=(12, 6), pady=5, sticky="e")
            ttk.Entry(dialog, textvariable=values[key], justify="right").grid(row=index, column=0, padx=(6, 12), pady=5, sticky="ew")

        def save() -> None:
            name = values["company_name"].get().strip()
            if not name:
                messagebox.showwarning("پیمانکاران", "نام پیمانکار لازم است.", parent=dialog)
                return
            self.service.save_entity({"entity_type": "CONTRACTOR", **{key: value.get().strip() for key, value in values.items()}})
            dialog.destroy()
            self.refresh()

        ttk.Button(dialog, text="ثبت", style="Primary.TButton", command=save).grid(row=len(fields), column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 12))
