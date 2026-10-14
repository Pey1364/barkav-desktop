"""Canonical dashboard using the approved 18.7 executive card layout."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from barkav1871.design import ThemeManager
from barkav1871.design.controls import fa
from barkav1871.core import PHASES
from barkav1871.services import FinanceDB

from .financial_calendar import FinancialCalendarDialog, FinancialMessagesDialog


def toman(value: int | None) -> str:
    return f"{fa(f'{int(value or 0):,}')} تومان"


class DashboardPanel(ttk.Frame):
    """Read-only financial overview; source data stays in ``FinanceDB``."""

    def __init__(self, parent, *, db: FinanceDB):
        super().__init__(parent, padding=0, style="Panel.TFrame")
        self.db = db
        self.theme = ThemeManager()
        self._values: dict[str, list[tk.Label]] = {}
        self._chart_canvases: list[tk.Canvas] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        p = self.theme.palette
        command = tk.Frame(self, bg=p["panel"], height=54, highlightbackground=p["line"], highlightthickness=1)
        command.pack(fill="x", padx=1, pady=(1, 8))
        command.pack_propagate(False)
        tk.Button(command, text="پیام‌های مالی", command=self.open_messages, bg=p["glass"], fg=p["text"], activebackground=p["panel2"], activeforeground=p["text"], relief="flat", padx=10, pady=5).pack(side="right", padx=(8, 3), pady=10)
        tk.Button(command, text="تقویم مالی", command=self.open_calendar, bg=p["glass"], fg=p["text"], activebackground=p["panel2"], activeforeground=p["text"], relief="flat", padx=10, pady=5).pack(side="right", padx=3, pady=10)
        tk.Button(command, text="بروزرسانی", command=self.refresh, bg=p["blue"], fg="#FFFFFF", activebackground=p["blue_hover"], activeforeground="#FFFFFF", relief="flat", padx=11, pady=5).pack(side="right", padx=3, pady=10)
        tk.Label(command, text="نمای کلی پروژه", bg=p["panel"], fg=p["text"], anchor="e", font=("Segoe UI", 10, "bold")).pack(side="right", fill="x", expand=True, padx=14)

        cards = tk.Frame(self, bg=p["panel"])
        cards.pack(fill="x", padx=10)
        for column in range(5):
            cards.grid_columnconfigure(column, weight=1, uniform="dashboard-kpi")
        definitions = (
            ("تراکنش‌ها", "↔", (("کل ورودی (تومان)", "cash_in"), ("هزینه کل ساخت (تومان)", "construction_cost"), ("کل خروجی (تومان)", "cash_out"), ("تنخواه فعلی (تومان)", "cash_balance"), ("مانده آزاد (تومان)", "free_cash_after_cheques"))),
            ("چک‌ها", "▱", (("کل چک‌ها (تومان)", "open_cheque_commitments"), ("چک‌های پاس‌نشده (تومان)", "open_cheque_commitments"), ("سررسید ۳۰ روز", "due_soon"), ("مبلغ سررسید (تومان)", "due_soon_amount"))),
            ("تسهیلات", "▣", (("اصل تسهیلات (تومان)", "loan_principal"), ("اقساط پرداختی (تومان)", "loan_paid"), ("مانده تسهیلات (تومان)", "loan_balance"))),
            ("فروش و مطالبات", "◉", (("کل قرارداد فروش (تومان)", "sales_total"), ("وصول خریداران (تومان)", "sales_received"), ("مطالبات (تومان)", "sales_claims"), ("مطالبات معوق (تومان)", "sales_overdue"))),
            ("روز آینده ۳۰", "□", (("تعهد ۳۰ روز (تومان)", "due_soon_amount"), ("وصول ۳۰ روز (تومان)", "incoming_soon"), ("تراز ۳۰ روز (تومان)", "net_soon"), ("مطالبات ۳۰ روز (تومان)", "sales_claims"), ("اقساط ۳۰ روز (تومان)", "loan_due"))),
        )
        for index, (title, icon, rows) in enumerate(definitions):
            self._kpi_card(cards, p, title, icon, rows).grid(row=0, column=4 - index, sticky="nsew", padx=3, pady=3)

        # This strip is part of the active 18.7 dashboard hierarchy.  The
        # canonical phase catalog is non-financial, so rendering it here never
        # posts or alters ledger data.
        phase = tk.Frame(self, bg=p["panel"], highlightbackground=p["line"], highlightthickness=1)
        phase.pack(fill="x", padx=10, pady=(10, 2))
        phase_head = tk.Frame(phase, bg=p["panel"], height=34)
        phase_head.pack(fill="x", padx=8, pady=(5, 0))
        phase_head.pack_propagate(False)
        tk.Label(phase_head, text="پیشرفت مراحل پروژه — ۳۲ فاز", bg=p["panel"], fg=p["text"],
                 anchor="e", font=("Segoe UI", 10, "bold")).pack(side="right", fill="x", expand=True)
        self._phase_status = tk.StringVar(value="برای مشاهدهٔ جزئیات، یک فاز را انتخاب کنید.")
        tk.Label(phase_head, textvariable=self._phase_status, bg=p["panel"], fg=p["muted"],
                 anchor="w", font=("Segoe UI", 8)).pack(side="left")
        strip = tk.Frame(phase, bg=p["panel"])
        strip.pack(fill="x", padx=8, pady=(2, 7))
        for column in range(len(PHASES)):
            strip.grid_columnconfigure(column, weight=1, uniform="phase-32")
        self._phase_buttons: dict[int, tk.Button] = {}
        for phase_item in PHASES:
            button = tk.Button(
                strip, text=fa(f"{phase_item.number:02d}"),
                command=lambda item=phase_item: self._select_phase(item.number, item.title_fa),
                bg=p["panel2"], fg=p["muted"], activebackground=p["blue"], activeforeground="#FFFFFF",
                relief="flat", bd=0, padx=0, pady=5, font=("Segoe UI", 7, "bold"), cursor="hand2",
            )
            button.grid(row=0, column=phase_item.number - 1, sticky="nsew", padx=1)
            self._phase_buttons[phase_item.number] = button

        charts = tk.Frame(self, bg=p["panel"])
        charts.pack(fill="both", expand=True, padx=10, pady=(18, 10))
        for column in range(3):
            charts.grid_columnconfigure(column, weight=1, uniform="dashboard-chart")
        for index, title in enumerate(("مقایسه فازها", "روند تجمیعی برآورد / واقعی / پیش‌بینی", "ترکیب برآورد فازها")):
            canvas = tk.Canvas(charts, bg=p["card"], highlightbackground=p["line"], highlightthickness=1, height=220)
            canvas.grid(row=0, column=2 - index, sticky="nsew", padx=4)
            canvas.bind("<Configure>", lambda _event, target=canvas, text=title: self._draw_chart(target, text), add="+")
            self._chart_canvases.append(canvas)
            canvas.after_idle(lambda target=canvas, text=title: self._draw_chart(target, text))

    def _kpi_card(self, parent: tk.Misc, p: dict[str, str], title: str, icon: str, rows: tuple[tuple[str, str], ...]) -> tk.Frame:
        card = tk.Frame(parent, bg=p["card"], highlightbackground=p["line"], highlightthickness=1)
        header = tk.Frame(card, bg=p["card"], height=43)
        header.pack(fill="x", padx=7, pady=(6, 3)); header.pack_propagate(False)
        tk.Label(header, text=title, bg=p["card"], fg=p["text"], anchor="e", font=("Segoe UI", 10, "bold")).pack(side="right", fill="x", expand=True)
        tk.Label(header, text=icon, bg=p["card"], fg=p["cyan"], anchor="w", font=("Segoe UI Symbol", 13)).pack(side="left", padx=3)
        for label, key in rows:
            row = tk.Frame(card, bg=p["surface_alt"], height=39, highlightbackground=p["line_soft"], highlightthickness=1)
            row.pack(fill="x", padx=7, pady=3); row.pack_propagate(False)
            tk.Label(row, text=label, bg=p["surface_alt"], fg=p["muted"], anchor="e", font=("Segoe UI", 8)).pack(side="right", fill="x", expand=True, padx=7)
            value = tk.Label(row, text="—", bg=p["surface_alt"], fg=p["text"], anchor="w", font=("Segoe UI", 9, "bold"))
            value.pack(side="left", padx=7)
            self._values.setdefault(key, []).append(value)
        return card

    def _draw_chart(self, canvas: tk.Canvas, title: str) -> None:
        p = self.theme.palette
        width, height = max(canvas.winfo_width(), 220), max(canvas.winfo_height(), 160)
        canvas.delete("all")
        canvas.create_text(width - 12, 16, text=title, anchor="ne", fill=p["text"], font=("Segoe UI", 9, "bold"))
        if "ترکیب" in title:
            radius, center_x, center_y = min(54, height // 4), width // 2, height // 2 + 15
            for start, color in ((90, p["blue"]), (-30, p["green"]), (-150, p["orange"])):
                canvas.create_arc(center_x-radius, center_y-radius, center_x+radius, center_y+radius, start=start, extent=-120, fill=color, outline=p["card"])
            return
        x0, y0, x1, y1 = 28, 48, width - 16, height - 30
        canvas.create_line(x0, y1, x1, y1, fill=p["line_soft"], dash=(2, 4)); canvas.create_line(x0, y0, x0, y1, fill=p["line_soft"])
        if "روند" in title:
            canvas.create_line(x0, y1-12, x0+(x1-x0)*.24, y1-24, x0+(x1-x0)*.48, y1-66, x0+(x1-x0)*.72, y1-74, x1, y0+26, fill=p["blue"], width=2, smooth=True)
        else:
            for offset, color in enumerate((p["muted"], p["green"], p["blue"])):
                x = x0 + (x1-x0) * (.35 + offset*.11); canvas.create_rectangle(x, y1-(38+offset*26), x+12, y1, fill=color, outline="")

    def refresh(self) -> None:
        snapshot = self.db.snapshot()
        values = {
            "cash_in": max(0, snapshot.cash_balance + snapshot.construction_cost), "cash_out": snapshot.construction_cost,
            "construction_cost": snapshot.construction_cost, "cash_balance": snapshot.cash_balance,
            "free_cash_after_cheques": snapshot.free_cash_after_cheques, "open_cheque_commitments": snapshot.open_cheque_commitments,
        }
        for key, labels in self._values.items():
            value = values.get(key)
            for label in labels:
                label.configure(text=toman(value) if value is not None else "—")

    def _select_phase(self, number: int, title: str) -> None:
        p = self.theme.palette
        for phase_number, button in self._phase_buttons.items():
            active = phase_number == number
            button.configure(bg=p["blue"] if active else p["panel2"], fg="#FFFFFF" if active else p["muted"])
        self._phase_status.set(f"فاز {fa(number)}: {title}")

    def open_calendar(self) -> None:
        FinancialCalendarDialog(self, self.db)

    def open_messages(self) -> None:
        FinancialMessagesDialog(self, self.db)
