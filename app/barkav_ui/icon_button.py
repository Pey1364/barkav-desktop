"""A command drawn as a line icon on a rounded tile; its word shows only as a hint under the pointer."""

from __future__ import annotations

import tkinter as tk

from barkav_themes.tokens import mix

from .line_icons import tile
from .theme import palette
from .window import attach_tooltip


class IconButton(tk.Button):
    """Icon only. The tile carries its own plate, so the button's colour never changes: a faint plate at rest, a
    stronger one and the accent ink under the pointer. The plate and ink are read from the active palette every
    time the button is mapped, so a theme change reaches it without rebuilding the window."""

    def __init__(self, parent, icon: str, hint: str, command, *, size: int = 16, box: int = 30,
                 radius: int = 8, hint_side: str = 'left', ground: str | None = None):
        super().__init__(parent, text='', compound='none', relief='flat', bd=0, highlightthickness=0,
                         cursor='hand2', padx=0, pady=0, takefocus=False, command=command)
        self.icon, self.hint = icon, hint
        self._shape = dict(size=size, box=box, radius=radius, weight=1.1)
        self._ground = ground
        self._images = (None, None, None)
        self._enabled = True
        self.restyle()
        self.bind('<Enter>', lambda _event: self._hover(True), add='+')
        self.bind('<Leave>', lambda _event: self._hover(False), add='+')
        self.bind('<Map>', lambda _event: self.restyle(), add='+')
        attach_tooltip(self, lambda: self.hint if self._enabled else '', delay_ms=300, side=hint_side)

    def _ground_colour(self, p: dict) -> str:
        if self._ground:
            return self._ground
        try:
            return str(self.master.cget('bg'))
        except (tk.TclError, AttributeError):
            return p['panel']

    def restyle(self) -> None:
        p = palette()
        ground = self._ground_colour(p)
        shape = dict(ground=ground, master=self, **self._shape)
        rest = tile(self.icon, colour=mix(p['text_secondary'], p['text_primary'], 0.45),
                    fill=mix(ground, p['text_primary'], 0.08), **shape)
        lit = tile(self.icon, colour=p['accent'], fill=mix(ground, p['text_primary'], 0.16), **shape)
        off = tile(self.icon, colour=mix(ground, p['text_secondary'], 0.4),
                   fill=mix(ground, p['text_primary'], 0.03), **shape)
        if rest is None:
            return
        self._images = (rest, lit, off)
        try:
            self.configure(image=rest if self._enabled else off, bg=ground, activebackground=ground)
        except tk.TclError:
            pass

    def _hover(self, on: bool) -> None:
        if not self._enabled:
            return
        rest, lit, _off = self._images
        try:
            self.configure(image=lit if on else rest)
        except tk.TclError:
            pass

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        rest, _lit, off = self._images
        try:
            self.configure(state='normal' if enabled else 'disabled',
                           image=rest if enabled else off, cursor='hand2' if enabled else 'arrow')
        except tk.TclError:
            pass
