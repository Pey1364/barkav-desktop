"""Canonical ledger report with XLSX and PDF output from one read-only query."""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from barkav1871.design.controls import fa
from barkav1871.services import FinanceDB, LedgerQueryService
from barkav1871.services.exports import export_pdf, export_xlsx


HEADERS = ["تاریخ", "نوع", "مبلغ (تومان)", "دسته", "طرف حساب", "شرح"]


def report_rows(query: LedgerQueryService) -> list[list[str]]:
    labels = {"IN": "ورودی", "OUT": "خروجی"}
    rows: list[list[str]] = []
    for item in query.list_transactions(limit=2_000):
        party = item.get("payer_name") if item.get("direction") == "IN" else item.get("receiver_name")
        rows.append([
            str(item.get("shamsi_date") or item.get("event_date") or "—"),
            labels.get(str(item.get("direction") or ""), "—"),
            f"{fa(f'{int(item.get('amount') or 0):,}')} تومان",
            str(item.get("category") or "—"), str(party or "—"), str(item.get("description") or "—"),
        ])
    return rows


class ReportsPanel(ttk.Frame):
    def __init__(self, parent, *, db: FinanceDB):
        super().__init__(parent, padding=8, style="Panel.TFrame")
        self.query = LedgerQueryService(db)
        self._rows: list[list[str]] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="Panel.TFrame")
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(toolbar, text="خروجی Excel", style="Toolbar.TButton", command=lambda: self.export("xlsx")).pack(side="right", padx=2)
        ttk.Button(toolbar, text="خروجی PDF", style="Toolbar.TButton", command=lambda: self.export("pdf")).pack(side="right", padx=2)
        ttk.Button(toolbar, text="بروزرسانی", style="Toolbar.TButton", command=self.refresh).pack(side="right", padx=2)
        ttk.Label(toolbar, text="گزارش‌گیری", style="Title.TLabel", anchor="e").pack(side="right", fill="x", expand=True, padx=12)
        self.tree = ttk.Treeview(self, columns=tuple(range(len(HEADERS))), show="headings", style="Barkav.Data.Treeview")
        for index, header in enumerate(HEADERS):
            self.tree.heading(index, text=header, anchor="e")
            self.tree.column(index, anchor="e", width=160, stretch=True)
        self.tree.configure(displaycolumns=tuple(reversed(tuple(range(len(HEADERS))))))
        self.tree.pack(fill="both", expand=True)

    def refresh(self) -> None:
        self._rows = report_rows(self.query)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in self._rows:
            self.tree.insert("", "end", values=row)

    def export(self, kind: str) -> None:
        extension = ".xlsx" if kind == "xlsx" else ".pdf"
        path = filedialog.asksaveasfilename(parent=self, title="ذخیرهٔ گزارش", defaultextension=extension, filetypes=[("Excel" if kind == "xlsx" else "PDF", f"*{extension}")])
        if not path:
            return
        try:
            writer = export_xlsx if kind == "xlsx" else export_pdf
            writer(Path(path), HEADERS, self._rows, title="گزارش تراکنش‌ها")
        except (OSError, RuntimeError, ValueError, ImportError) as exc:
            messagebox.showerror("گزارش‌گیری", str(exc), parent=self)
            return
        messagebox.showinfo("گزارش‌گیری", "خروجی آماده شد.", parent=self)
