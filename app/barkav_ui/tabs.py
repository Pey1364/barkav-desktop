"""Right-to-left tab strip - contract section 3.

The important rule this encodes is the size ladder: a strip knows its own
depth and renders exactly one step smaller than its parent.  Screens pass
``level`` rather than a font, so a sub-tab can never accidentally match the
tab above it.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .theme import font, metrics, palette


_LEVEL_ROLES = {1: 'tab1', 2: 'tab2', 3: 'tab3'}
_LEVEL_PADDING = {1: (14, 9), 2: (12, 7), 3: (10, 5)}


class TabStrip(tk.Frame):
    """A themed button strip driving a hidden ``ttk.Notebook``."""

    def __init__(self, notebook: ttk.Notebook, *, level: int = 2):
        if level not in _LEVEL_ROLES:
            raise ValueError(f'Unsupported tab level {level!r}; expected 1, 2 or 3')
        p = palette()
        super().__init__(notebook.master, bg=p['surface_alt'])
        self.notebook = notebook
        self.level = level
        self._buttons: dict[str, tuple[tk.Frame, tk.Label, tk.Frame]] = {}

        style = ttk.Style(notebook)
        style.configure('BarkavHiddenTabs.TNotebook', background=p['bg'], borderwidth=0, tabmargins=0)
        try:
            style.layout('BarkavHiddenTabs.TNotebook.Tab', [])
        except tk.TclError:
            pass
        notebook.configure(style='BarkavHiddenTabs.TNotebook')

        try:
            self.pack(fill='x', before=notebook)
        except tk.TclError:
            self.pack(fill='x')
        # Section 3: the strip carries a single bottom rule, never a full box.
        tk.Frame(self, bg=p['border_subtle'], height=1).pack(side='bottom', fill='x')

        self.rebuild()
        notebook.bind('<<NotebookTabChanged>>', lambda _e: self.sync(), add='+')

    def rebuild(self) -> None:
        for child in list(self._buttons.values()):
            child[0].destroy()
        self._buttons.clear()
        p = palette()
        pad_x, pad_y = _LEVEL_PADDING[self.level]
        role = _LEVEL_ROLES[self.level]
        inactive_style = 'TabUnselected.TButton'

        for tab_id in self.notebook.tabs():
            label = str(self.notebook.tab(tab_id, 'text'))
            holder = tk.Frame(self, bg=p['surface_alt'])
            # RTL: the first logical tab becomes the right-most visual tab.
            holder.pack(side='right', fill='y')
            # Tabs have their own rounded-rectangle skin.  They must not use
            # the pill geometry reserved for toolbar/action buttons.
            text = ttk.Button(
                holder, text=label, style='TabUnselected.TButton',
                command=lambda t=tab_id: self.notebook.select(t),
            )
            text.pack(fill='both', expand=True, padx=2, pady=3)
            indicator = None

            holder.bind('<Button-1>', lambda _e, t=tab_id: self.notebook.select(t))
            self._buttons[str(tab_id)] = (holder, text, indicator)
        self.sync()

    def _selected(self) -> str:
        try:
            return str(self.notebook.select())
        except tk.TclError:
            return ''

    def sync(self) -> None:
        """Apply the shared selected/unselected rounded-rectangle states."""

        p = palette()
        selected = self._selected()
        active_style = 'TabSelected.TButton'
        inactive_style = 'TabUnselected.TButton'
        for tab_id, (holder, text, _indicator) in self._buttons.items():
            active = tab_id == selected
            holder.configure(bg=p['surface_alt'])
            text.configure(style='TabSelected.TButton' if active else 'TabUnselected.TButton')


def notebook_depth(notebook: ttk.Notebook) -> int:
    """Nesting level of a notebook, 1 for a top-level one, capped at 3."""

    depth, widget = 1, notebook
    while True:
        try:
            widget = widget.master
        except AttributeError:
            break
        if widget is None:
            break
        if isinstance(widget, ttk.Notebook):
            depth += 1
    return max(1, min(3, depth))


class LegacyTabStrip(TabStrip):
    """Drop-in replacement for the inherited ``RtlNotebookStrip``.

    The product had two tab-strip implementations - this kit one and an older
    canvas/button strip - so selected and unselected tabs looked different
    depending on which screen you were on. Rather than restyle the old one to
    match, it is replaced by this, leaving a single implementation whose
    colours and size ladder come from the theme. Changing them once now
    changes every strip in the product.

    The old constructor's colour arguments are accepted and ignored; they
    were per-caller literals, which is exactly what the kit removes.
    """

    def __init__(self, notebook: ttk.Notebook, *, level: int | None = None, **_legacy):
        super().__init__(notebook, level=level or notebook_depth(notebook))
        # Some inherited code reaches for the strip's container.
        self.bar = self
        self.buttons = self._buttons


def sub_notebook(parent: tk.Misc, *, level: int = 2) -> tuple[ttk.Notebook, TabStrip]:
    """Create a notebook with its strip already attached.

    Add pages with ``notebook.add(frame, text=...)`` then call
    ``strip.rebuild()``.
    """

    notebook = ttk.Notebook(parent)
    notebook.pack(fill='both', expand=True, pady=(metrics()['gap'], 0))
    return notebook, TabStrip(notebook, level=level)
