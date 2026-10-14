"""Section 11: the web-style navigation rail on the right edge.

One list of items (the روزانه/پروژه headings went in the operator round of
2026-09-27), a rounded "pill" behind the active item, a soft hover, a footer
block (active project, theme, settings, collapse) and a collapsed icons-only
mode whose items explain themselves in hover hints. Each item wears a glassy
raised tile in its own colour; the footer's tiles are neutral.

Each item is one Canvas: a Tk frame cannot be rounded, and drawing the pill,
the tile and the label on one canvas keeps them aligned in both modes.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from barkav_themes.tokens import mix

from .badges import GLASS_MARGIN, glass_tile
from .line_icons import icon as line_icon
from .skin import rounded_plate_image
from .theme import font, palette
from .window import attach_tooltip


# Each item's tile colour, by icon: a palette role. Unlisted icons (the
# footer's) take the neutral one.
TILE_HUES = {
    'dashboard': 'blue', 'data': 'accent', 'transactions': 'green', 'account': 'violet',
    'income': 'orange', 'contractors': 'yellow', 'project': 'red',
}
NEUTRAL_HUE = 'text_secondary'


class RailItem:
    def __init__(self, rail: 'NavRail', parent: tk.Misc, key, label: str, icon_name: str,
                 command, hint: str = '', options: dict | None = None):
        self.rail = rail
        self.key = key
        self.label = label
        self.icon_name = icon_name
        self.command = command
        self.hint = hint
        options = options or {}
        # A chevron at the item's far end says it opens something beside
        # the rail; on_hover(item, inside) lets that open on pointing.
        self.chevron = bool(options.get('chevron'))
        self.on_hover = options.get('on_hover')
        self.active = False
        self.hover = False
        self._images = []
        self.canvas = tk.Canvas(parent, height=rail.item_height, bg=rail.colours['nav'],
                                bd=0, highlightthickness=0, cursor='hand2')
        self.canvas.pack(side='top', fill='x', padx=rail.pad, pady=1)
        self.canvas.bind('<Enter>', self._enter, add='+')
        self.canvas.bind('<Leave>', self._leave, add='+')
        self.canvas.bind('<Button-1>', self._click, add='+')
        self.canvas.bind('<Configure>', lambda _e: self.draw(), add='+')
        attach_tooltip(self.canvas, self.tooltip, delay_ms=rail.tooltip_delay, side='left')

    def tooltip(self) -> str:
        if self.rail.collapsed:
            return f'{self.label}   {self.hint}'.strip()
        return self.hint

    def _enter(self, _event=None) -> None:
        self.hover = True
        self.draw()
        if self.on_hover is not None:
            self.on_hover(self, True)

    def _leave(self, _event=None) -> None:
        self.hover = False
        self.draw()
        if self.on_hover is not None:
            self.on_hover(self, False)

    def _click(self, _event=None) -> None:
        if self.command is not None:
            self.command()

    def set_label(self, label: str) -> None:
        self.label = label
        self.draw()

    def draw(self) -> None:
        canvas = self.canvas
        try:
            width = canvas.winfo_width()
        except tk.TclError:
            return
        if width <= 1:
            return
        rail = self.rail
        c = rail.colours
        height = rail.item_height
        canvas.delete('all')
        self._images = []
        if self.active:
            fill, ink, text = c['active'], c['accent'], c['text_hot']
        elif self.hover:
            fill, ink, text = c['hover'], c['text_hot'], c['text_hot']
        else:
            fill, ink, text = None, c['text_hot'], c['text_hot']
        base = fill or c['nav']
        if fill:
            plate = rail.plate(width, height, fill)
            self._images.append(plate)
            canvas.create_image(0, 0, image=plate, anchor='nw')
        image = rail.tile(self.icon_name, base)
        span = rail.tile_size + 2 * GLASS_MARGIN
        if image is not None:
            self._images.append(image)
        if rail.collapsed:
            if image is not None:
                canvas.create_image(width // 2, height // 2, image=image)
            return
        icon_x = width - 6 - span // 2
        if image is not None:
            canvas.create_image(icon_x, height // 2, image=image)
        text_right = icon_x - span // 2 - 4
        text_left = 6
        if self.chevron:
            mark = line_icon('chevron', size=13, colour=c['text'] if not self.hover else ink,
                             background=None, master=canvas)
            if mark is not None:
                self._images.append(mark)
                canvas.create_image(12, height // 2, image=mark)
                text_left = 22
        label_font = rail.font_active if self.active else rail.font_item
        canvas.create_text(text_right, height // 2, anchor='e', fill=text,
                           text=rail.fit(self.label, label_font, text_right - text_left),
                           font=label_font)


class NavRail:
    """The rail inside ``host`` (a fixed-width ``tk.Frame``)."""

    # 208 since the items' glassy tiles (2026-09-27) took room from the labels.
    EXPANDED_WIDTH = 208
    COLLAPSED_WIDTH = 64

    def __init__(self, host: tk.Frame, *, groups, footer, collapsed: bool = False,
                 on_collapse=None, widget_for_font: tk.Misc | None = None):
        p = palette()
        self.host = host
        self.collapsed = bool(collapsed)
        self.on_collapse = on_collapse
        self.item_height = 38
        self.tile_size = 24
        self.pad = 8
        self.radius = 10
        self.colours = {
            'nav': p['nav'],
            'hover': mix(p['nav'], p['text_primary'], 0.07),
            'active': p.get('tab_selected_fill') or mix(p['nav'], p['accent'], 0.17),
            'accent': p['accent'],
            'text': p['text_secondary'],
            'text_hot': p['text_primary'],
            'heading': mix(p['text_secondary'], p['nav'], 0.35),
            'divider': p['border_subtle'],
            'ink': p['on_accent'],
            'shadow': p['shadow'],
        }
        self._hues = {icon: p.get(role) or p['accent'] for icon, role in TILE_HUES.items()}
        self._neutral = mix(p[NEUTRAL_HUE], p['nav'], 0.25)
        # The rail reads at the tab titles' size, in bold (operator round
        # 2026-09-27: one size for both, the rail set apart by weight only);
        # weight and colour stay the same when an item is active.
        family, size, _style = font('tab1', widget=widget_for_font)
        self.font_item = (family, size, 'bold')
        self.font_active = self.font_item
        self.font_heading = font('small', widget=widget_for_font)
        self._plates: dict[tuple, object] = {}
        self._measure: dict[tuple, tkfont.Font] = {}
        self.items: dict[object, RailItem] = {}
        self.footer_items: dict[object, RailItem] = {}
        self._headings: list[tuple[tk.Label, tk.Frame]] = []

        host.configure(bg=p['nav'], width=self.width)
        self.top = tk.Frame(host, bg=p['nav'])
        self.top.pack(side='top', fill='x', pady=(8, 0))
        self.bottom = tk.Frame(host, bg=p['nav'])
        self.bottom.pack(side='bottom', fill='x', pady=(0, 8))
        tk.Frame(self.bottom, bg=self.colours['divider'], height=1).pack(
            side='top', fill='x', padx=12, pady=(0, 6))

        self._group_sizes: list[int] = []
        for heading, entries in groups:
            if heading:
                label = tk.Label(self.top, text=heading, bg=p['nav'], fg=self.colours['heading'],
                                 font=self.font_heading, anchor='e', padx=14)
                divider = tk.Frame(self.top, bg=self.colours['divider'], height=1)
                self._headings.append((label, divider))
            else:
                self._headings.append(None)
            count = 0
            for key, text, icon_name, command, hint, *extra in entries:
                self.items[key] = RailItem(self, self.top, key, text, icon_name, command, hint,
                                           *extra[:1])
                count += 1
            self._group_sizes.append(count)
        for key, text, icon_name, command, hint, *extra in footer:
            self.footer_items[key] = RailItem(self, self.bottom, key, text, icon_name, command, hint,
                                              *extra[:1])
        self._apply_mode()

    # -- geometry and helpers -------------------------------------------
    @property
    def width(self) -> int:
        return self.COLLAPSED_WIDTH if self.collapsed else self.EXPANDED_WIDTH

    def tooltip_delay(self) -> int:
        return 250 if self.collapsed else 700

    def tile(self, icon_name: str, background: str):
        """The item's glassy tile on ``background`` (the pill under it or
        the rail itself)."""
        colour = self._hues.get(icon_name, self._neutral)
        return glass_tile(icon_name, size=self.tile_size, colour=colour, ink=self.colours['ink'],
                          background=background, shadow=self.colours['shadow'], master=self.host)

    def plate(self, width: int, height: int, fill: str):
        key = (width, height, fill)
        plate = self._plates.get(key)
        if plate is None:
            plate = rounded_plate_image(width, height, fill=fill, page=self.colours['nav'],
                                        radius=self.radius, master=self.host)
            self._plates[key] = plate
        return plate

    def fit(self, text: str, font_spec, width: int) -> str:
        key = tuple(font_spec)
        measure = self._measure.get(key)
        if measure is None:
            measure = tkfont.Font(root=self.host, font=font_spec)
            self._measure[key] = measure
        if width <= 0 or measure.measure(text) <= width:
            return text
        while text and measure.measure(text + '…') > width:
            text = text[:-1]
        return text + '…'

    def alive(self) -> bool:
        try:
            return bool(self.host.winfo_exists())
        except tk.TclError:
            return False

    # -- state ------------------------------------------------------------
    def set_active(self, key) -> None:
        for item_key, item in self.items.items():
            active = str(item_key) == str(key)
            if item.active != active:
                item.active = active
                item.draw()

    def set_collapsed(self, collapsed: bool) -> None:
        collapsed = bool(collapsed)
        if collapsed == self.collapsed:
            return
        self.collapsed = collapsed
        self._apply_mode()
        if self.on_collapse is not None:
            self.on_collapse(collapsed)

    def toggle(self) -> None:
        self.set_collapsed(not self.collapsed)

    def _apply_mode(self) -> None:
        self.host.configure(width=self.width)
        for heading in self._headings:
            if heading is not None:
                heading[0].pack_forget()
                heading[1].pack_forget()
        # Headings sit before the first item of their group; re-pack them
        # in that position for the current mode.
        for heading, first in zip(self._headings, self._group_starts()):
            if heading is None or first is None:
                continue
            label, divider = heading
            if self.collapsed:
                divider.pack(side='top', fill='x', padx=16, pady=(9, 5), before=first.canvas)
            else:
                label.pack(side='top', fill='x', pady=(8, 2), before=first.canvas)
        collapse = self.footer_items.get('collapse')
        if collapse is not None:
            collapse.icon_name = 'expand' if self.collapsed else 'collapse'
            collapse.label = 'باز کردن نوار' if self.collapsed else 'جمع کردن نوار'
        for item in list(self.items.values()) + list(self.footer_items.values()):
            item.draw()

    def _group_starts(self) -> list:
        order = list(self.items.values())
        starts, index = [], 0
        for count in self._group_sizes:
            starts.append(order[index] if count and index < len(order) else None)
            index += count
        return starts
