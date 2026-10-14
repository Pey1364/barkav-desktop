from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable, Sequence

from .engine import ThemeSelection, stripe_tree
from .tokens import ThemeSpec, get_theme


def _theme(selection: ThemeSelection) -> tuple[ThemeSpec, dict[str, str]]:
    normalized = selection.normalized()
    spec = get_theme(normalized.theme_id)
    return spec, spec.palette(normalized.mode)


class ShellHeader(tk.Frame):
    """Two-level reference header. All product text and actions are injected."""

    def __init__(
        self,
        parent: tk.Misc,
        selection: ThemeSelection,
        *,
        product_text: str,
        date_text: str,
        time_text: str,
        commands: Sequence[tuple[str, Callable[[], None] | None]],
    ):
        spec, p = _theme(selection)
        super().__init__(parent, bg=p["surface"], bd=0, highlightbackground=p["line"], highlightthickness=1)
        self.selection = selection.normalized()

        brand = tk.Frame(self, bg=p["surface"])
        brand.pack(side="left", padx=(16, 14), fill="y")
        tk.Label(brand, text="◒", bg=p["surface"], fg=p["cyan"], font=("Segoe UI Symbol", 17)).pack(side="left", padx=(0, 8))
        tk.Label(brand, text=product_text, bg=p["surface"], fg=p["text"], font=("Segoe UI", 11), anchor="w").pack(side="left")

        action_host = tk.Frame(self, bg=p["surface"])
        action_host.pack(side="right", padx=10, pady=7, fill="y")
        for label, command in commands:
            tk.Button(
                action_host,
                text=label,
                command=command or (lambda: None),
                bg=p["glass"],
                fg=p["text"],
                activebackground=p["raised"],
                activeforeground=p["text"],
                highlightbackground=p["line"],
                highlightthickness=1,
                relief="flat",
                bd=0,
                padx=11,
                pady=6,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            ).pack(side="right", padx=3, fill="y")

        clock = tk.Frame(self, bg=p["surface"])
        clock.pack(side="left", padx=8, fill="y")
        for icon, value in (("▣", date_text), ("◷", time_text)):
            cell = tk.Frame(clock, bg=p["surface"])
            cell.pack(side="left", padx=7, fill="y")
            tk.Label(cell, text=icon, bg=p["surface"], fg=p["muted"], font=("Segoe UI Symbol", 14)).pack(side="left", padx=(0, 5), pady=10)
            tk.Label(cell, text=value, width=11, bg=p["surface"], fg=p["text"], font=("Segoe UI", 10), anchor="center").pack(side="left", pady=10)

        self.configure(height=spec.metrics["command_height"])
        self.pack_propagate(False)


class NavigationBar(tk.Frame):
    """Full-width navigation with an active cyan/blue edge like the references."""

    def __init__(
        self,
        parent: tk.Misc,
        selection: ThemeSelection,
        items: Sequence[tuple[str, str]],
        *,
        active: str,
        on_select: Callable[[str], None] | None = None,
    ):
        spec, p = _theme(selection)
        super().__init__(parent, bg=p["nav"], highlightbackground=p["line"], highlightthickness=1)
        self.selection = selection.normalized()
        self._p = p
        self._active = active
        self._on_select = on_select
        self._cells: dict[str, tuple[tk.Frame, tk.Button, tk.Frame]] = {}
        for index in range(len(items)):
            self.grid_columnconfigure(index, weight=1, uniform="reference_nav")
        for index, (label, icon) in enumerate(items):
            cell = tk.Frame(self, bg=p["nav"], highlightbackground=p["line_soft"], highlightthickness=1)
            cell.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 1, 0), pady=0)
            cell.grid_rowconfigure(0, weight=1)
            cell.grid_columnconfigure(0, weight=1)
            button = tk.Button(
                cell,
                text=f"{label}   {icon}",
                command=lambda value=label: self.select(value),
                bg=p["nav"],
                fg=p["text"],
                activebackground=p["nav_active"],
                activeforeground=p["cyan"],
                relief="flat",
                bd=0,
                font=("Segoe UI", 10, "bold"),
                cursor="hand2",
            )
            button.grid(row=0, column=0, sticky="nsew")
            indicator = tk.Frame(cell, bg=p["nav"], height=3)
            indicator.grid(row=1, column=0, sticky="ew")
            self._cells[label] = (cell, button, indicator)
        self.configure(height=spec.metrics["nav_height"])
        self.grid_propagate(False)
        self.select(active, emit=False)

    def select(self, label: str, *, emit: bool = True) -> None:
        self._active = label
        for key, (cell, button, indicator) in self._cells.items():
            active = key == label
            bg = self._p["nav_active"] if active else self._p["nav"]
            cell.configure(bg=bg, highlightbackground=self._p["line"])
            button.configure(bg=bg, fg=self._p["cyan"] if active else self._p["text"])
            indicator.configure(bg=self._p["cyan"] if active else bg)
        if emit and self._on_select:
            self._on_select(label)


class SectionCard(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        selection: ThemeSelection,
        *,
        title: str = "",
        icon: str = "",
        header: bool = True,
        padding: int = 10,
    ):
        spec, p = _theme(selection)
        super().__init__(parent, bg=p["card"], highlightbackground=p["line"], highlightthickness=1, bd=0)
        self.selection = selection.normalized()
        self.palette = p
        if header:
            head = tk.Frame(self, bg=p["card"], height=spec.metrics["card_header_height"])
            head.pack(fill="x", padx=padding, pady=(7, 0))
            head.pack_propagate(False)
            tk.Label(head, text=icon, bg=p["card"], fg=p["cyan"], font=("Segoe UI Symbol", 15)).pack(side="right", padx=(7, 0))
            tk.Label(head, text=title, bg=p["card"], fg=p["text"], font=("Segoe UI", 11, "bold"), anchor="e").pack(side="right", fill="x", expand=True)
        self.body = tk.Frame(self, bg=p["card"])
        self.body.pack(fill="both", expand=True, padx=padding, pady=(4, padding))


class MetricRow(tk.Frame):
    def __init__(self, parent: tk.Misc, selection: ThemeSelection, label: str, value: str, *, alternate: bool = False):
        _, p = _theme(selection)
        bg = p["row_odd"] if alternate else p["row_even"]
        super().__init__(parent, bg=bg, highlightbackground=p["line_soft"], highlightthickness=1)
        tk.Label(self, text="◆", bg=bg, fg=p["cyan"], font=("Segoe UI Symbol", 7)).pack(side="right", padx=(8, 3))
        tk.Label(self, text=label, bg=bg, fg=p["muted"], font=("Segoe UI", 9), anchor="e").pack(side="right", padx=3, pady=8)
        tk.Label(self, text=value, bg=bg, fg=p["text"], font=("Segoe UI", 10, "bold"), anchor="w").pack(side="left", padx=8, pady=8)


class Toolbar(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        selection: ThemeSelection,
        actions: Sequence[tuple[str, str, Callable[[], None] | None]],
        *,
        search_label: str = "فیلتر:",
    ):
        _, p = _theme(selection)
        super().__init__(parent, bg=p["panel"], highlightbackground=p["line_soft"], highlightthickness=1)
        action_host = tk.Frame(self, bg=p["panel"])
        action_host.pack(side="left", padx=6, pady=6)
        for label, icon, command in actions:
            tk.Button(
                action_host,
                text=f"{icon}  {label}" if label else icon,
                command=command or (lambda: None),
                bg=p["glass"],
                fg=p["text"],
                activebackground=p["raised"],
                activeforeground=p["text"],
                highlightbackground=p["line"],
                highlightthickness=1,
                relief="flat",
                bd=0,
                padx=9,
                pady=6,
                font=("Segoe UI", 9),
            ).pack(side="left", padx=2)

        search = tk.Frame(self, bg=p["panel"])
        search.pack(side="right", padx=8, pady=6)
        tk.Label(search, text=search_label, bg=p["panel"], fg=p["text"], font=("Segoe UI", 9)).pack(side="right", padx=(7, 0))
        self.search_var = tk.StringVar()
        entry = tk.Entry(
            search,
            textvariable=self.search_var,
            bg=p["input"],
            fg=p["text"],
            insertbackground=p["text"],
            highlightbackground=p["line"],
            highlightcolor=p["cyan"],
            highlightthickness=1,
            relief="flat",
            width=24,
            font=("Segoe UI", 10),
        )
        entry.pack(side="right", ipady=7)
        tk.Button(search, text="×", command=lambda: self.search_var.set(""), bg=p["glass"], fg=p["text"], activebackground=p["raised"], relief="flat", bd=0, padx=11, pady=5, font=("Segoe UI", 12, "bold")).pack(side="right", padx=(0, 5))


class ReferenceTable(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        selection: ThemeSelection,
        columns: Sequence[tuple[str, str, int]],
        *,
        height: int = 10,
    ):
        _, p = _theme(selection)
        super().__init__(parent, bg=p["panel"], highlightbackground=p["line"], highlightthickness=1)
        self.selection = selection.normalized()
        identifiers = [column_id for column_id, _, _ in columns]
        self.tree = ttk.Treeview(self, columns=identifiers, show="headings", height=height)
        for column_id, title, width in columns:
            self.tree.heading(column_id, text=title, anchor="center")
            self.tree.column(column_id, width=width, minwidth=70, stretch=True, anchor="center")
        ybar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        stripe_tree(self.tree, self.selection)

    def insert_rows(self, rows: Iterable[Sequence[str]]) -> None:
        for index, row in enumerate(rows):
            self.tree.insert("", "end", values=tuple(row), tags=("even" if index % 2 == 0 else "odd",))


class KpiCard(tk.Frame):
    def __init__(self, parent: tk.Misc, selection: ThemeSelection, title: str, value: str, icon: str, *, status: str = "success"):
        _, p = _theme(selection)
        super().__init__(parent, bg=p["card"], highlightbackground=p["line"], highlightthickness=1)
        icon_bg = p["raised"]
        tk.Label(self, text=icon, bg=icon_bg, fg=p["violet" if status == "violet" else "blue"], font=("Segoe UI Symbol", 18), width=3, pady=8).pack(side="right", padx=10, pady=10)
        words = tk.Frame(self, bg=p["card"])
        words.pack(side="right", fill="both", expand=True, padx=6, pady=10)
        tk.Label(words, text=title, bg=p["card"], fg=p["text"], font=("Segoe UI", 9), anchor="e").pack(fill="x")
        tk.Label(words, text=value, bg=p["card"], fg=p["green" if status == "success" else p["cyan"]], font=("Segoe UI", 11, "bold"), anchor="e").pack(fill="x", pady=(8, 0))


class ServiceBadge(tk.Frame):
    def __init__(self, parent: tk.Misc, selection: ThemeSelection, text: str, *, status: str = "success"):
        _, p = _theme(selection)
        color = p["green"] if status == "success" else p["yellow"] if status == "warning" else p["red"]
        super().__init__(parent, bg=p["panel"], highlightbackground=p["line"], highlightthickness=1)
        tk.Label(self, text="●", bg=p["panel"], fg=color, font=("Segoe UI Symbol", 8)).pack(side="right", padx=(8, 4), pady=7)
        tk.Label(self, text=text, bg=p["panel"], fg=color, font=("Segoe UI", 9, "bold")).pack(side="right", padx=(0, 8), pady=7)


class PhaseStrip(tk.Frame):
    def __init__(self, parent: tk.Misc, selection: ThemeSelection, *, completed: int = 2, count: int = 32):
        _, p = _theme(selection)
        super().__init__(parent, bg=p["card"])
        for column in range(count):
            self.grid_columnconfigure(column, weight=1, uniform="phase")
        for number in range(1, count + 1):
            active = number <= completed
            button = tk.Button(
                self,
                text=f"{number:02d}",
                bg=p["green"] if active else p["panel2"],
                fg="#FFFFFF" if active else p["muted"],
                activebackground=p["blue"],
                activeforeground="#FFFFFF",
                highlightbackground=p["line"],
                highlightthickness=1,
                relief="flat",
                bd=0,
                font=("Segoe UI", 8, "bold"),
                padx=0,
                pady=8,
            )
            button.grid(row=0, column=number - 1, sticky="nsew", padx=1)


class EmptyState(tk.Frame):
    def __init__(self, parent: tk.Misc, selection: ThemeSelection, text: str):
        _, p = _theme(selection)
        super().__init__(parent, bg=p["panel"])
        tk.Label(self, text="▱", bg=p["panel"], fg=p["empty"], font=("Segoe UI Symbol", 44)).pack(pady=(30, 5))
        tk.Label(self, text=text, bg=p["panel"], fg=p["empty"], font=("Segoe UI", 10)).pack(pady=(0, 30))


class BottomActionBar(tk.Frame):
    def __init__(self, parent: tk.Misc, selection: ThemeSelection, actions: Sequence[tuple[str, str]]):
        _, p = _theme(selection)
        super().__init__(parent, bg=p["panel"], highlightbackground=p["line_soft"], highlightthickness=1)
        color_map = {"primary": p["blue"], "success": p["green"], "warning": p["yellow"], "danger": p["red"]}
        text_map = {"warning": "#111827"}
        for label, role in actions:
            color = color_map.get(role, p["glass"])
            tk.Button(self, text=label, bg=color, fg=text_map.get(role, "#FFFFFF"), activebackground=p["blue_hover"], relief="flat", bd=0, padx=24, pady=9, font=("Segoe UI", 10, "bold")).pack(side="right", padx=5, pady=8)
