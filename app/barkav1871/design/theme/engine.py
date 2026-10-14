from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Callable

from .tokens import ThemeSpec, get_theme


@dataclass(frozen=True)
class ThemeSelection:
    theme_id: int = 1
    mode: str = "dark"

    def normalized(self) -> "ThemeSelection":
        theme_id = get_theme(self.theme_id).theme_id
        mode = str(self.mode or "dark").strip().lower()
        if mode not in {"dark", "light"}:
            mode = "dark"
        return ThemeSelection(theme_id, mode)


class ThemeManager:
    """Small future-facing controller; it does not persist or touch project data."""

    def __init__(self, selection: ThemeSelection | None = None):
        self._selection = (selection or ThemeSelection()).normalized()
        self._listeners: list[Callable[[ThemeSelection], None]] = []

    @property
    def selection(self) -> ThemeSelection:
        return self._selection

    @property
    def spec(self) -> ThemeSpec:
        return get_theme(self._selection.theme_id)

    @property
    def palette(self) -> dict[str, str]:
        return self.spec.palette(self._selection.mode)

    def subscribe(self, callback: Callable[[ThemeSelection], None]) -> Callable[[], None]:
        self._listeners.append(callback)

        def unsubscribe() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return unsubscribe

    def select(self, theme_id: int | None = None, mode: str | None = None) -> ThemeSelection:
        current = self._selection
        updated = ThemeSelection(
            current.theme_id if theme_id is None else theme_id,
            current.mode if mode is None else mode,
        ).normalized()
        if updated != current:
            self._selection = updated
            for callback in tuple(self._listeners):
                callback(updated)
        return updated


def legacy_palette(selection: ThemeSelection | None = None) -> dict[str, str]:
    """Return compatibility and semantic palette keys for the canonical UI."""

    normalized = (selection or ThemeSelection()).normalized()
    return get_theme(normalized.theme_id).palette(normalized.mode)


def apply_ttk_theme(
    root: tk.Misc,
    selection: ThemeSelection | None = None,
    *,
    palette_override: dict[str, str] | None = None,
    font_size: int = 10,
    row_height: int | None = None,
    font_family: str = "TkDefaultFont",
    font_weight: int = 400,
) -> ttk.Style:
    """Install the semantic Theme 1/2 style family on a Tk root."""

    selected = (selection or ThemeSelection()).normalized()
    spec = get_theme(selected.theme_id)
    # Settings may supply a UI-only background token.  Merge it over the
    # central palette so a Light background choice reaches real ttk widgets
    # without changing the selected theme, mode, or font configuration.
    p = dict(spec.palette(selected.mode))
    if palette_override:
        p.update(palette_override)
    metrics = spec.metrics
    fs = max(9, min(14, int(font_size or 10)))
    rh = max(28, min(46, int(row_height or metrics["row_height"])))
    control_weight = "bold" if int(font_weight or 400) >= 700 else "normal"
    title_font = (font_family, fs + 2, "bold")
    control_font = (font_family, fs, control_weight)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.option_add("*Font", (font_family, fs))
    root.option_add("*TCombobox*Listbox.background", p["input"])
    root.option_add("*TCombobox*Listbox.foreground", p["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["selection"])
    root.option_add("*TCombobox*Listbox.selectForeground", p["selection_text"])

    style.configure(".", font=(font_family, fs), background=p["bg"], foreground=p["text"])
    style.configure("TFrame", background=p["bg"])
    style.configure("App.TFrame", background=p["bg"])
    style.configure("Surface.TFrame", background=p["surface"])
    style.configure("Panel.TFrame", background=p["panel"])
    style.configure("Raised.TFrame", background=p["raised"])
    style.configure("Card.TFrame", background=p["card"], bordercolor=p["border_subtle"], relief="solid")

    style.configure("TLabel", background=p["bg"], foreground=p["text"])
    style.configure("Surface.TLabel", background=p["surface"], foreground=p["text"])
    style.configure("Panel.TLabel", background=p["panel"], foreground=p["text"])
    style.configure("Title.TLabel", background=p["panel"], foreground=p["text_primary"], font=title_font)
    style.configure("Muted.TLabel", background=p["panel"], foreground=p["text_muted"])
    style.configure("Accent.TLabel", background=p["panel"], foreground=p["accent"], font=control_font)
    style.configure("Success.TLabel", background=p["panel"], foreground=p["success"])
    style.configure("Warning.TLabel", background=p["panel"], foreground=p["warning"])
    style.configure("Danger.TLabel", background=p["panel"], foreground=p["danger"])
    style.configure("Summary.TLabel", background=p["panel2"], foreground=p["text"], padding=(10, 6), anchor="e")

    button_pad = (12, max(5, (metrics["button_height"] - fs - 8) // 2))
    style.configure("TButton", background=p["glass"], foreground=p["text"], bordercolor=p["line"], relief="flat", padding=button_pad)
    style.configure("Toolbar.TButton", background=p["glass"], foreground=p["text"], bordercolor=p["line_soft"], relief="flat", padding=(9, 6))
    style.configure("Ghost.TButton", background=p["panel"], foreground=p["text"], bordercolor=p["line"], relief="flat", padding=button_pad)
    style.configure("Primary.TButton", background=p["info"], foreground=p["on_accent"], bordercolor=p["info"], relief="flat", padding=button_pad, font=control_font)
    style.configure("Success.TButton", background=p["success"], foreground=p["on_accent"], bordercolor=p["success"], relief="flat", padding=button_pad)
    style.configure("Warning.TButton", background=p["warning"], foreground=p["on_warning"], bordercolor=p["warning"], relief="flat", padding=button_pad)
    style.configure("Danger.TButton", background=p["danger"], foreground=p["on_accent"], bordercolor=p["danger"], relief="flat", padding=button_pad)
    style.configure("Nav.TButton", background=p["nav"], foreground=p["text_primary"], bordercolor=p["border_subtle"], relief="flat", padding=(14, 10), font=control_font)
    style.configure("NavActive.TButton", background=p["nav_active"], foreground=p["accent"], bordercolor=p["accent"], relief="flat", padding=(14, 10), font=control_font)
    style.configure("Tab.TButton", background=p["surface_alt"], foreground=p["text_secondary"], bordercolor=p["border_subtle"], relief="flat", padding=(12, 7))
    style.configure("TabActive.TButton", background=p["raised"], foreground=p["text_primary"], bordercolor=p["accent"], relief="flat", padding=(12, 7), font=control_font)

    for name, active, pressed in (
        ("TButton", p["panel2"], p["raised"]),
        ("Toolbar.TButton", p["raised"], p["blue"]),
        ("Ghost.TButton", p["raised"], p["blue"]),
        ("Primary.TButton", p["blue_hover"], p["blue_hover"]),
        ("Nav.TButton", p["raised"], p["nav_active"]),
        ("NavActive.TButton", p["raised"], p["nav_active"]),
    ):
        style.map(name, background=[("active", active), ("pressed", pressed)])

    style.configure("TEntry", fieldbackground=p["input"], foreground=p["text_primary"], insertcolor=p["text_primary"], bordercolor=p["border"], lightcolor=p["border"], darkcolor=p["border"], padding=7)
    style.configure("TCombobox", fieldbackground=p["input"], background=p["input"], foreground=p["text_primary"], arrowcolor=p["text_muted"], bordercolor=p["border"], padding=6)
    style.map("TCombobox", fieldbackground=[("readonly", p["input"])], foreground=[("readonly", p["text_primary"])])

    style.configure("Treeview", rowheight=rh, background=p["row_even"], fieldbackground=p["row_even"], foreground=p["text_primary"], bordercolor=p["border_subtle"], relief="flat", font=(font_family, fs))
    style.configure("Treeview.Heading", background=p["heading"], foreground=p["text_primary"], bordercolor=p["border_subtle"], relief="flat", padding=(7, 8), font=control_font)
    style.map("Treeview", background=[("selected", p["selection"])], foreground=[("selected", p["selection_text"])])
    style.map("Treeview.Heading", background=[("active", p["raised"])])
    # Explicit data/report styles are assigned by the canonical presentation.
    # bridge to inherited SmartTable instances.  This prevents legacy widget
    # defaults from bypassing the selected application font.
    style.configure("Barkav.Data.Treeview", rowheight=rh, background=p["row_even"], fieldbackground=p["row_even"], foreground=p["text_primary"], bordercolor=p["border_subtle"], relief="flat", font=(font_family, fs))
    style.configure("Barkav.Data.Treeview.Heading", background=p["heading"], foreground=p["text_primary"], bordercolor=p["border_subtle"], relief="flat", padding=(7, 8), font=control_font)
    style.map("Barkav.Data.Treeview", background=[("selected", p["selection"])], foreground=[("selected", p["selection_text"])])
    style.map("Barkav.Data.Treeview.Heading", background=[("active", p["raised"])])

    style.configure("TNotebook", background=p["bg"], borderwidth=0, tabmargins=(0, 1, 0, 0))
    style.configure("TNotebook.Tab", background=p["surface_alt"], foreground=p["text_secondary"], padding=(14, 8), borderwidth=0, font=control_font)
    style.map("TNotebook.Tab", background=[("selected", p["raised"]), ("active", p["glass"])], foreground=[("selected", p["accent"]), ("active", p["text_primary"])])
    style.configure("Barkav.Data.TNotebook", background=p["bg"], borderwidth=0, tabmargins=(0, 1, 0, 0))
    style.configure("Barkav.Data.TNotebook.Tab", background=p["surface_alt"], foreground=p["text_secondary"], padding=(14, 8), borderwidth=0, font=control_font)
    style.map("Barkav.Data.TNotebook.Tab", background=[("selected", p["raised"]), ("active", p["glass"])], foreground=[("selected", p["accent"]), ("active", p["text_primary"])])
    style.configure("Hidden.TNotebook", background=p["bg"], borderwidth=0, tabmargins=0)
    try:
        style.layout("Hidden.TNotebook.Tab", [])
    except tk.TclError:
        pass

    style.configure("TLabelframe", background=p["panel"], bordercolor=p["line"], relief="solid")
    style.configure("TLabelframe.Label", background=p["panel"], foreground=p["text"], font=(font_family, fs, "bold"))
    style.configure("TPanedwindow", background=p["line"])
    style.configure("TScrollbar", background=p["scroll_thumb"], troughcolor=p["scroll_track"], bordercolor=p["line_soft"], arrowcolor=p["muted"])
    style.configure("Horizontal.TProgressbar", troughcolor=p["panel2"], background=p["cyan"], bordercolor=p["line_soft"], lightcolor=p["cyan"], darkcolor=p["cyan"])
    return style


def stripe_tree(tree: ttk.Treeview, selection: ThemeSelection | None = None) -> None:
    selected = (selection or ThemeSelection()).normalized()
    p = get_theme(selected.theme_id).palette(selected.mode)
    tree.tag_configure("even", background=p["row_even"], foreground=p["text"])
    tree.tag_configure("odd", background=p["row_odd"], foreground=p["text"])
    tree.tag_configure("pending", background=p["yellow"], foreground="#111827")
    tree.tag_configure("approved", background=p["green"], foreground="#FFFFFF")
    tree.tag_configure("rejected", background=p["red"], foreground="#FFFFFF")
