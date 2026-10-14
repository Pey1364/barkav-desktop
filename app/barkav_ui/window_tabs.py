"""Section 11 (operator-approved D1): the window's own tabs, like a browser's.

استارت and the open project sit at the top bar's right end. The selected
tab wears the same soft accent fill as the rail's selected item and the
content sub-tabs - one selected look everywhere - and a tab's text keeps its
colour whether or not it is selected. A tab that can close carries a small
cross at its end.

Each tab is one Canvas: a Tk frame cannot round two corners only, and the
plate, the label and the cross have to stay aligned together.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from barkav_themes.tokens import mix

from .line_icons import icon as line_icon
from .skin import rounded_plate_image
from .theme import font, palette

_CLOSE_ZONE = 24
_PAD = 16
_RADIUS = 8


class WindowTabs(tk.Frame):
    """``add`` tabs in reading order; the first one sits right-most.

    ``pill=True`` draws a selected or hovered tab as a whole rounded pill,
    for tabs that sit inside a framed tab area (operator round 2026-09-27)
    rather than on the bar's bottom edge.

    ``strip=True`` is AutoCAD's file tabs (operator round 2026-09-30): flat
    rectangles side by side with no gap between them, as tall as the row
    they sit in so they touch the line above and the line below, a hairline
    between two. A tab that is neither selected nor hovered is on a plate of
    its own, one step above the bar, instead of the bar's own colour - the
    black of the bar itself on a dark theme."""

    def __init__(self, parent: tk.Misc, *, background: str, height: int = 34, pill: bool = False,
                 page: str | None = None, strip: bool = False):
        super().__init__(parent, bg=background, bd=0, highlightthickness=0)
        p = palette()
        self._background = background
        self._height = int(height)
        self._pill = bool(pill)
        self._strip = bool(strip)
        # ``page``: AutoCAD's file tabs (operator round 2026-09-27) - tabs
        # side by side on the bar's bottom edge, one thin line between two,
        # the open one in the page's own colour so it reads as the top of
        # the content under it.
        self._page = page
        self._order: list[str] = []
        self._colours = {
            'active': p.get('tab_selected_fill') or mix(background, p['accent'], 0.17),
            # A strip's resting plate is the bar's colour lifted toward the
            # ink; the hover has to sit above it or pointing at a tab would
            # darken it.
            'rest': mix(background, p['text_primary'], 0.10) if strip else None,
            'hover': mix(background, p['text_primary'], 0.16 if strip else 0.07),
            'text': p['text_primary'],
            # A closed tab read as plain black next to the open one's full
            # ink (UI/UX review 2026-09-28): every label used 'text' - the
            # same weight regardless of selection, with nothing marking
            # which tab is actually open. The muted tone 'close' already
            # uses for its own unselected state does that here too.
            'text_inactive': p['text_secondary'],
            'close': p['text_secondary'],
            'close_hot': p['text_primary'],
            'separator': p['border'],
        }
        self._font = font('tab1', widget=self)
        self._measure = tkfont.Font(root=self, font=self._font)
        self._tabs: dict[str, dict] = {}
        self._plates: dict[tuple, object] = {}
        self.active: str | None = None

    # ------------------------------------------------------------ public
    def add(self, key: str, label: str, command, *, closable: bool = False, on_close=None) -> None:
        canvas = tk.Canvas(self, height=self._height, bg=self._background, bd=0,
                           highlightthickness=0, cursor='hand2')
        if self._strip:
            canvas.pack(side='right', fill='y')
        else:
            canvas.pack(side='right', padx=0 if self._page else (0, 2), anchor='s')
        self._order.append(key)
        tab = {'canvas': canvas, 'label': str(label), 'command': command,
               'closable': bool(closable and on_close is not None), 'on_close': on_close,
               'hover': False, 'close_hover': False, 'images': []}
        self._tabs[key] = tab
        canvas.bind('<Enter>', lambda e, k=key: self._pointer(k, e.x, True), add='+')
        canvas.bind('<Motion>', lambda e, k=key: self._pointer(k, e.x, True), add='+')
        canvas.bind('<Leave>', lambda e, k=key: self._pointer(k, -1, False), add='+')
        canvas.bind('<ButtonRelease-1>', lambda e, k=key: self._click(k, e.x), add='+')
        self._draw(key)

    def select(self, key: str | None) -> None:
        self.active = key
        for name in self._tabs:
            self._draw(name)

    def set_label(self, key: str, label: str) -> None:
        tab = self._tabs.get(key)
        if tab is not None:
            tab['label'] = str(label)
            self._draw(key)

    def tab_canvas(self, key: str) -> tk.Canvas | None:
        tab = self._tabs.get(key)
        return tab['canvas'] if tab else None

    # ---------------------------------------------------------- internals
    def _width(self, tab: dict) -> int:
        width = _PAD * 2 + self._measure.measure(tab['label'])
        if tab['closable']:
            width += _CLOSE_ZONE - 4
        return max(72, width)

    def _in_close_zone(self, tab: dict, x: int) -> bool:
        # The cross sits at the tab's end - its left edge in a right-to-left row.
        return tab['closable'] and 0 <= x <= _CLOSE_ZONE + 4

    def _pointer(self, key: str, x: int, inside: bool) -> None:
        tab = self._tabs.get(key)
        if tab is None:
            return
        close_hover = inside and self._in_close_zone(tab, x)
        if tab['hover'] != inside or tab['close_hover'] != close_hover:
            tab['hover'], tab['close_hover'] = inside, close_hover
            if self._page:
                for name in self._tabs:
                    self._draw(name)
            else:
                self._draw(key)

    def _click(self, key: str, x: int) -> None:
        tab = self._tabs.get(key)
        if tab is None:
            return
        if self._in_close_zone(tab, x):
            tab['on_close']()
            return
        if tab['command'] is not None:
            tab['command']()

    def _plate(self, width: int, height: int, fill: str, *, page: str | None = None,
               radius: int = _RADIUS):
        page = page or self._background
        key = (width, height, fill, page, radius)
        plate = self._plates.get(key)
        if plate is None:
            plate = rounded_plate_image(width, height, fill=fill, page=page,
                                        radius=radius, master=self)
            self._plates[key] = plate
        return plate

    def _draw_strip_plate(self, canvas: tk.Canvas, key: str, width: int, height: int,
                          fill: str) -> None:
        """A flat plate: the canvas itself is the colour, so no pixel of the
        bar can show between a tab and the line above it, the line below it or
        the next tab. A hairline on the tab's left edge divides it from the
        next tab; the first tab, at the strip's start, is closed on its right
        edge too."""
        canvas.configure(bg=fill)
        line = self._colours['separator']
        canvas.create_line(0, 0, 0, height, fill=line)
        if self._order and key == self._order[0]:
            canvas.create_line(width - 1, 0, width - 1, height, fill=line)

    def _draw(self, key: str) -> None:
        tab = self._tabs.get(key)
        if tab is None:
            return
        canvas = tab['canvas']
        width, height = self._width(tab), self._height
        try:
            canvas.configure(width=width)
            canvas.delete('all')
        except tk.TclError:
            return
        tab['images'] = []
        c = self._colours
        # Operator round 2026-09-28: the open tab used to fill with the page
        # colour itself (AutoCAD's "joined to its document" look), which
        # sits only a shade off this bar's own background - selected and
        # deselected read as the same colour. The selected tab now wears
        # the one accent fill every selected control in the kit shares
        # (rail item, content sub-tab), as the class docstring always said
        # it should; only the corner-blend colour below still uses the page.
        fill = c['active'] if key == self.active else (c['hover'] if tab['hover'] else c['rest'])
        if self._strip:
            self._draw_strip_plate(canvas, key, width, height, fill)
        elif self._page:
            # One thin line between two tabs, left out beside the open or
            # hovered one, whose plate already marks it.
            index = self._order.index(key) if key in self._order else -1
            neighbour = self._order[index + 1] if 0 <= index < len(self._order) - 1 else None
            quiet = fill is not None or (neighbour is not None and (
                neighbour == self.active or self._tabs[neighbour]['hover']))
            if not quiet:
                canvas.create_line(0, height * 0.28, 0, height * 0.78, fill=c['separator'])
            if key != self.active:
                # The bar's bottom edge runs under every tab but the open one.
                canvas.create_line(0, height - 1, width, height - 1, fill=c['separator'])
        plated = fill is not None and not self._strip
        if plated and self._pill:
            plate = self._plate(width, height - 4, fill)
            tab['images'].append(plate)
            canvas.create_image(0, 2, image=plate, anchor='nw')
        elif plated:
            # Taller than the tab, so only the top two corners show rounded:
            # the tab reads as joined to the bar's bottom edge.
            plate = self._plate(width, height + _RADIUS, fill)
            tab['images'].append(plate)
            canvas.create_image(0, 0, image=plate, anchor='nw')
        canvas.create_text(width - _PAD, height // 2 + 1, text=tab['label'], anchor='e',
                           fill=c['text'] if key == self.active else c['text_inactive'],
                           font=self._font)
        if tab['closable']:
            centre = _CLOSE_ZONE // 2 + 2
            if tab['close_hover']:
                ground = fill or self._background
                dot = self._plate(20, 20, mix(ground, c['text'], 0.14), page=ground, radius=10)
                tab['images'].append(dot)
                canvas.create_image(centre, height // 2, image=dot)
            image = line_icon('close', size=12, colour=c['close_hot'] if tab['close_hover'] else c['close'],
                              background=None, master=self)
            if image is not None:
                tab['images'].append(image)
                canvas.create_image(centre, height // 2, image=image)
