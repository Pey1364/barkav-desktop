"""What a ttk.Treeview cannot draw itself: an outline around every selected
row, and a real rendered checkbox in place of a ☐/☑ glyph.

A Treeview row is one text run per cell - no borders, no images outside the
tree column. Both looks are therefore small widgets placed over the tree and
kept in step with it: repainted after every selection change, scroll, resize
and row rebuild (the wrapped yscrollcommand fires on all three of the last).
The underlying cell text is never changed, so every screen that reads its
glyphs back (sales claims' ``startswith(CHECKBOX_CHECKED)`` and the like)
keeps working untouched.

Three more looks ride on the same repaint (operator-approved N1-N3):
a status stripe on the start edge of pending/approved/rejected rows, a
lighter row under the mouse, and an empty-state card when a table has no
rows at all.
"""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from .art import rgb
from .theme import palette
from .widget_lifetime import install_callback_cleanup

# A Treeview draws a row, not a cell, so a check state inside one is text, not
# a real widget - this pair is the product's one spelling of it. Anything
# outside this module that shows the same check state (an inherited table's
# own checkbox column) reads these rather than retyping the characters.
CHECKBOX_CHECKED = '☑'
CHECKBOX_UNCHECKED = '☐'
_GLYPHS = {CHECKBOX_UNCHECKED: False, CHECKBOX_CHECKED: True}

OUTLINE_WIDTH = 2
OUTLINE_RADIUS = 6
STRIPE_WIDTH = 4
# Every table's row check sits in one column of its own at the right edge
# (operator request, 2026-09-27). The column is appended to the tree's
# columns but never given values, so item values keep their length and
# every index screens read (values[-1] included) is unchanged.
CHECK_COLUMN = 'barkav_check'
CHECK_WIDTH = 40
# Status tag -> palette role of its stripe.
STATUS_STRIPES = {'pending': 'warning', 'approved': 'success', 'rejected': 'danger',
                  'status_pending': 'warning', 'status_approved': 'success',
                  'status_rejected': 'danger', 'status_hidden': 'cream'}
HOVER_PREFIX = 'barkav_hover_'
_HOVER_BINDTAG = 'BarkavRowHover'
_EMPTY_MIN_SIZE = (260, 150)
_SUPERSAMPLE = 4
# Tk drops a PhotoImage nothing references, so the ones built here are kept.
# Each belongs to the Tcl interpreter of the window it was built for: its key
# starts with that interpreter's id and its entries go when the root is
# destroyed, so a window never receives the photos of one that is gone.
_images: dict[tuple, object] = {}
_image_interpreters: set[int] = set()
# palette() reads the stored settings from the project database on every
# call; a repaint asks for it again and again while the mouse moves, so it
# is held for a moment. A theme change rebuilds the window anyway.
_PALETTE_SECONDS = 2.0
_palette_memo: list = [0.0, None]
# Text widths by (font, text): the check glyphs and row numbers repeat on
# every repaint, and measuring is the slowest step of one.
_measures: dict[tuple, int] = {}


def _palette() -> dict:
    now = time.monotonic()
    if _palette_memo[1] is None or now - _palette_memo[0] > _PALETTE_SECONDS:
        _palette_memo[0], _palette_memo[1] = now, palette()
    return _palette_memo[1]


def _measure(font: tkfont.Font, text: str) -> int:
    key = (id(font._tk), str(font), text)
    width = _measures.get(key)
    if width is None:
        if len(_measures) > 5000:
            _measures.clear()
        width = _measures[key] = font.measure(text)
    return width


def decorate(tree: ttk.Treeview) -> 'RowDecorator':
    """Attach (or refresh) the overlay for one tree. Safe to call repeatedly."""

    install_callback_cleanup(tree)
    current = getattr(tree, '_barkav_rows', None)
    if current is None or current.tree is not tree:
        current = RowDecorator(tree)
        tree._barkav_rows = current
    current.rewrap()
    current.schedule()
    return current


def _luma(colour: str) -> float:
    r, g, b = rgb(colour)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def _mix(a: str, b: str, ratio: float) -> str:
    ra, ga, ba = rgb(a)
    rb, gb, bb = rgb(b)
    return '#%02X%02X%02X' % (round(ra + (rb - ra) * ratio), round(ga + (gb - ga) * ratio),
                              round(ba + (bb - ba) * ratio))


def _hex(widget, colour: str) -> str:
    """Any Tk colour spelling as #RRGGBB, so it can be mixed."""

    colour = str(colour or '')
    if len(colour) == 7 and colour.startswith('#'):
        return colour
    try:
        r, g, b = widget.winfo_rgb(colour)
    except tk.TclError:
        return colour
    return '#%02X%02X%02X' % (r // 257, g // 257, b // 257)


def _cached_image(master, key: tuple):
    """The photo (or photos) kept for ``key`` in ``master``'s interpreter."""

    return _images.get((id(master.tk),) + key)


def _keep_image(master, key: tuple, photo):
    """Keep ``photo`` for ``master``'s interpreter until its root is destroyed."""

    interpreter = id(master.tk)
    _images[(interpreter,) + key] = photo
    if interpreter not in _image_interpreters:
        root = master._root()
        root_path = str(root)

        def release(event):
            # A child's <Destroy> reaches the root's bindings as well; only
            # the root's own ends the interpreter.
            if str(event.widget) != root_path:
                return
            for cache in (_images, _measures):
                for image_key in list(cache):
                    if image_key[0] == interpreter:
                        cache.pop(image_key, None)
            _image_interpreters.discard(interpreter)

        root.bind('<Destroy>', release, add='+')
        _image_interpreters.add(interpreter)
    return photo


def _corner_images(outline: str, fill: str, radius: int, width: int, master):
    """Four quarter-arcs of a rounded outline, composited onto ``fill``."""

    outline, fill = _hex(master, outline), _hex(master, fill)
    key = ('corner', outline, fill, radius, width)
    cached = _cached_image(master, key)
    if cached is not None:
        return cached
    scale = _SUPERSAMPLE
    size = radius * 2
    image = Image.new('RGB', (size * scale, size * scale), rgb(fill))
    ImageDraw.Draw(image).rounded_rectangle(
        (0, 0, size * scale - 1, size * scale - 1), radius=radius * scale,
        outline=rgb(outline), width=width * scale)
    image = image.resize((size, size), Image.LANCZOS)
    boxes = ((0, 0, radius, radius), (radius, 0, size, radius),
             (0, radius, radius, size), (radius, radius, size, size))
    photos = tuple(ImageTk.PhotoImage(image.crop(box), master=master) for box in boxes)
    return _keep_image(master, key, photos)


def _checkbox_image(checked: bool, size: int, background: str, p: dict, master):
    background = _hex(master, background)
    accent = p['accent']
    key = ('tick', checked, size, background, accent, p['text_secondary'], p['bg'], p['on_accent'])
    cached = _cached_image(master, key)
    if cached is not None:
        return cached
    scale = _SUPERSAMPLE
    side = size * scale
    image = Image.new('RGB', (side, side), rgb(background))
    draw = ImageDraw.Draw(image)
    radius = max(3, size // 4) * scale
    if checked:
        draw.rounded_rectangle((0, 0, side - 1, side - 1), radius=radius, fill=rgb(accent))
        # A bright accent (every dark theme's cyan) takes the page's own
        # dark ground as its tick; a deep one (the light themes') takes white.
        mark = p['bg'] if _luma(accent) > 0.5 else p['on_accent']
        pad = side * 0.24
        draw.line([(pad, side * 0.53), (side * 0.42, side - pad), (side - pad, pad * 0.95)],
                  fill=rgb(mark), width=max(2, round(side * 0.11)), joint='curve')
    else:
        edge = _mix(p['text_secondary'], background, 0.25)
        draw.rounded_rectangle((scale, scale, side - 1 - scale, side - 1 - scale), radius=radius,
                               outline=rgb(edge), width=max(2, round(1.6 * scale)))
    photo = ImageTk.PhotoImage(image.resize((size, size), Image.LANCZOS), master=master)
    return _keep_image(master, key, photo)


class RowDecorator:
    def __init__(self, tree: ttk.Treeview):
        self.tree = tree
        self._job = None
        self._outlines: list[list[tk.Widget]] = []
        self._ticks: list[tk.Label] = []
        self._stripes: list[tk.Frame] = []
        self._empty: tk.Frame | None = None
        self._empty_key = None
        self._wrapped: dict[str, str] = {}
        self._hover_iid = ''
        self._hover_saved: dict[str, list[str]] = {}
        self._hover_tags: set[str] = set()
        # The boxes and patches painted over each row, so a hover can
        # recolour its two rows at once instead of waiting for a repaint.
        self._row_pieces: dict[str, list[tuple]] = {}
        self._parked = False
        for sequence in ('<<TreeviewSelect>>', '<Configure>', '<Map>', '<ButtonRelease-1>',
                         '<KeyRelease>', '<MouseWheel>', '<Button-4>', '<Button-5>',
                         '<Shift-MouseWheel>'):
            tree.bind(sequence, self.schedule, add='+')
        tree.bind('<Motion>', self._motion, add='+')
        tree.bind('<Destroy>', self._destroyed, add='+')
        # A hovered row has its colour tag swapped for a lighter one (a ttk
        # tag created later can never out-rank an earlier one, so adding a
        # tag cannot recolour a striped row). Screens read row tags on click
        # and on key presses, so the swap is undone first: this bindtag runs
        # ahead of the tree's own bindings.
        tags = tuple(tree.bindtags())
        if _HOVER_BINDTAG not in tags:
            tree.bindtags((_HOVER_BINDTAG,) + tags)
        tree.bind_class(_HOVER_BINDTAG, '<ButtonPress>', _hover_reset)
        tree.bind_class(_HOVER_BINDTAG, '<ButtonPress-1>', _check_press)
        tree.bind_class(_HOVER_BINDTAG, '<KeyPress>', _hover_reset)
        tree.bind_class(_HOVER_BINDTAG, '<Leave>', _hover_reset)

    # ------------------------------------------------------------ plumbing

    def rewrap(self) -> None:
        """Route the tree's scroll callbacks through a repaint.

        Tk calls yscrollcommand whenever the visible rows change - a scroll,
        a resize, and every delete/insert of a refresh - so this one hook
        covers what no single event does. Re-run after anything that may
        have replaced the command (a screen adding its own scrollbar).
        """

        for option in ('yscrollcommand', 'xscrollcommand'):
            try:
                current = str(self.tree.cget(option) or '')
            except tk.TclError:
                return
            if current and current == self._wrapped.get(option):
                continue
            original = self.tree.tk.splitlist(current) if current else ()

            def relay(*args, _original=original):
                if _original:
                    try:
                        self.tree.tk.call(*_original, *args)
                    except tk.TclError:
                        pass
                self.schedule()

            name = self.tree.register(relay)
            self._wrapped[option] = name
            self.tree.configure(**{option: name})

    def _destroyed(self, event):
        # A repaint still queued for a tree that is gone would call a
        # deleted Tcl command; cancel it with the tree.
        if event.widget is self.tree and self._job is not None:
            try:
                self.tree.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def schedule(self, _event=None):
        if self._job is None:
            try:
                self._job = self.tree.after_idle(self._paint)
            except tk.TclError:
                self._job = None

    def _forward_click(self, event):
        tree = self.tree
        x = event.x_root - tree.winfo_rootx()
        y = event.y_root - tree.winfo_rooty()
        tree.event_generate('<ButtonPress-1>', x=x, y=y)
        tree.event_generate('<ButtonRelease-1>', x=x, y=y)
        return 'break'

    def _forward_wheel(self, event):
        if getattr(event, 'num', None) == 4:
            steps = -1
        elif getattr(event, 'num', None) == 5:
            steps = 1
        else:
            steps = -int(event.delta / 120) if event.delta else 0
        if steps:
            self.tree.yview_scroll(steps, 'units')
        return 'break'

    def _overlay(self, widget):
        for sequence in ('<Button-1>',):
            widget.bind(sequence, self._forward_click)
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            widget.bind(sequence, self._forward_wheel)
        return widget

    # ------------------------------------------------------------ geometry

    def _shows(self) -> set[str]:
        value = self.tree.cget('show')
        items = value if isinstance(value, (tuple, list)) else self.tree.tk.splitlist(value)
        return {str(v) for v in items}

    def _heading_height(self) -> int:
        """Bottom edge of the heading row. The first pixel rows are the
        widget's own border (region 'nothing'), so find where the heading
        starts before looking for where it ends."""

        tree = self.tree
        try:
            if 'headings' not in self._shows():
                return 0
            x = max(10, tree.winfo_width() // 2)
            seen = False
            for y in range(0, 120):
                if tree.identify_region(x, y) == 'heading':
                    seen = True
                elif seen:
                    return y
        except tk.TclError:
            return 0
        return 0

    def _visible_rows(self, top: int):
        tree = self.tree
        rows = []
        bottom = tree.winfo_height()
        y = top + 1
        while y < bottom and len(rows) < 120:
            iid = tree.identify_row(y)
            if not iid:
                if rows:
                    break
                y += 3
                continue
            box = tree.bbox(iid)
            if not box:
                break
            rows.append((iid, box))
            y = box[1] + box[3] + 1
        return rows

    def _display_columns(self):
        tree = self.tree

        def as_list(value):
            if isinstance(value, str):
                return [str(v) for v in tree.tk.splitlist(value)]
            return [str(v) for v in value]

        shown = as_list(tree.cget('displaycolumns'))
        if not shown or shown[0] == '#all':
            shown = as_list(tree.cget('columns'))
        return shown

    def _style(self) -> str:
        return str(self.tree.cget('style') or 'Treeview')

    def _font(self, heading: bool = False) -> tkfont.Font:
        style = ttk.Style(self.tree)
        name = f'{self._style()}.Heading' if heading else self._style()
        spec = style.lookup(name, 'font') or ('TkHeadingFont' if heading else 'TkDefaultFont')
        cache = getattr(self, '_font_cache', {})
        if spec not in cache:
            try:
                cache[spec] = tkfont.Font(self.tree, font=spec)
            except tk.TclError:
                cache[spec] = tkfont.nametofont('TkDefaultFont')
            self._font_cache = cache
        return cache[spec]

    def _selected_bg(self, p) -> str:
        style = ttk.Style(self.tree)
        try:
            colour = style.lookup(self._style(), 'background', ('selected',))
        except tk.TclError:
            colour = ''
        return str(colour or p['row_selected'])

    def _row_bg(self, iid, selected: bool, p) -> str:
        if selected:
            return self._selected_bg(p)
        tree = self.tree
        for tag in tree.item(iid, 'tags') or ():
            try:
                colour = tree.tag_configure(tag, 'background')
            except tk.TclError:
                continue
            if colour:
                return str(colour)
        style = ttk.Style(tree)
        return str(style.lookup(self._style(), 'fieldbackground')
                   or style.lookup(self._style(), 'background') or p['row_even'])

    @staticmethod
    def _glyph_x(text: str, font: tkfont.Font, left: int, width: int, anchor: str, pad: int):
        """Centre x of a leading or trailing check glyph inside a cell."""

        text_width = _measure(font, text)
        if anchor in ('e', 'ne', 'se'):
            start = left + width - pad - text_width
        elif anchor in ('w', 'nw', 'sw'):
            start = left + pad
        else:
            start = left + (width - text_width) / 2
        if text[:1] in _GLYPHS:
            return start + _measure(font, text[0]) / 2
        return start + text_width - _measure(font, text[-1]) / 2

    # --------------------------------------------------------------- paint

    def _paint(self):
        self._job = None
        tree = self.tree
        try:
            if not tree.winfo_exists():
                return
            live = bool(tree.winfo_ismapped())
        except tk.TclError:
            return
        used_outlines = used_ticks = used_stripes = 0
        empty_shown = False
        self._row_pieces = {}
        if live:
            try:
                self._ensure_check_column()
                self._park_right()
                p = _palette()
                top = self._heading_height()
                rows = self._visible_rows(top)
                used_outlines = self._paint_outlines(rows, p)
                used_ticks = self._paint_ticks(rows, top, p)
                used_stripes = self._paint_stripes(rows, p)
                empty_shown = self._paint_empty(top, p)
            except tk.TclError:
                pass
        for pieces in self._outlines[used_outlines:]:
            for piece in pieces:
                piece.place_forget()
        for label in self._ticks[used_ticks:]:
            label.place_forget()
        for stripe in self._stripes[used_stripes:]:
            stripe.place_forget()
        if not empty_shown and self._empty is not None:
            self._empty.place_forget()

    def _park_right(self) -> None:
        """A table wider than its pane opens at its right edge, where an RTL
        row starts - once, the first time it overflows; after that the view
        is wherever the operator scrolled it."""

        if self._parked:
            return
        try:
            first, last = (float(v) for v in self.tree.xview())
        except (tk.TclError, ValueError, TypeError):
            return
        if last >= 0.999:
            return  # it all fits; nothing to park yet
        self._parked = True
        if first <= 0.001:
            self.tree.xview_moveto(1.0)

    def _paint_outlines(self, rows, p) -> int:
        tree = self.tree
        selected = set(tree.selection())
        if not selected:
            return 0
        colour = p['focus_ring']
        fill = self._selected_bg(p)
        width = tree.winfo_width()
        t = OUTLINE_WIDTH
        used = 0
        for iid, (x, y, w, h) in rows:
            if iid not in selected:
                continue
            x0, x1 = max(x, 0) + 1, min(x + w, width) - 1
            y0, y1 = y + 1, y + h - 1
            if x1 - x0 < 20 or y1 - y0 < 8:
                continue
            r = min(OUTLINE_RADIUS, (y1 - y0) // 2)
            if used == len(self._outlines):
                self._outlines.append(
                    [self._overlay(tk.Frame(tree, bd=0, highlightthickness=0)) for _ in range(4)]
                    + [self._overlay(tk.Label(tree, bd=0, highlightthickness=0, padx=0, pady=0))
                       for _ in range(4)])
            top, bottom, left, right, *corners = self._outlines[used]
            for edge in (top, bottom, left, right):
                edge.configure(bg=colour)
            top.place(x=x0 + r, y=y0, width=x1 - x0 - 2 * r, height=t)
            bottom.place(x=x0 + r, y=y1 - t, width=x1 - x0 - 2 * r, height=t)
            left.place(x=x0, y=y0 + r, width=t, height=y1 - y0 - 2 * r)
            right.place(x=x1 - t, y=y0 + r, width=t, height=y1 - y0 - 2 * r)
            images = _corner_images(colour, fill, r, t, tree)
            spots = ((x0, y0), (x1 - r, y0), (x0, y1 - r), (x1 - r, y1 - r))
            for label, image, (cx, cy) in zip(corners, images, spots):
                label.configure(image=image, bg=fill)
                label.place(x=cx, y=cy, width=r, height=r)
            used += 1
        return used

    def _tick_label(self, index):
        while len(self._ticks) <= index:
            self._ticks.append(self._overlay(
                tk.Label(self.tree, bd=0, highlightthickness=0, padx=0, pady=0, cursor='hand2')))
        return self._ticks[index]

    def _cell_text(self, iid, column) -> str:
        # Several inherited tables keep their check in the tree column (#0,
        # the item's own text) rather than in a value column.
        if column == '#0':
            return str(self.tree.item(iid, 'text') or '')
        return str(self.tree.set(iid, column))

    def _paint_ticks(self, rows, top, p) -> int:
        tree = self.tree
        columns = self._display_columns()
        candidates = (['#0'] if 'tree' in self._shows() else []) + columns
        visible_width = tree.winfo_width()
        own = CHECK_COLUMN in columns
        tick_columns = []
        for column in candidates:
            if column == CHECK_COLUMN:
                continue
            sample = [self._cell_text(iid, column) for iid, _box in rows[:6]]
            heading = str(tree.heading(column, 'text') or '')
            if any(str(v)[:1] in _GLYPHS for v in sample) or heading[:1] in _GLYPHS \
                    or heading[-1:] in _GLYPHS:
                tick_columns.append(column)
        selected = set(tree.selection())
        used = self._paint_own_checks(rows, top, p, columns, selected) if own else 0
        if not tick_columns:
            return used
        font = self._font()
        for column in tick_columns:
            anchor = str(tree.column(column, 'anchor') or 'w')
            span = None
            for iid, (_x, _y, _w, h) in rows:
                text = self._cell_text(iid, column)
                if text[:1] not in _GLYPHS:
                    continue
                try:
                    cell = tree.bbox(iid, column=column)
                except tk.TclError:
                    cell = None
                if not cell:
                    continue
                cx, cy, cw, ch = cell
                span = (cx, cw)
                size = max(14, min(18, ch - 12))
                if len(text.strip()) == 1 and anchor in ('center', ''):
                    # A centred glyph-only cell: centre the box in it and
                    # cover the whole middle, wherever Tk's own item padding
                    # put the glyph.
                    centre = cx + cw / 2
                    box_w = max(size + 4, min(cw - 2 * OUTLINE_RADIUS - 2, size + 16))
                elif len(text.strip()) == 1:
                    # Right- or left-aligned (the messages window's ردیف):
                    # the box goes where Tk drew the glyph, or both show.
                    centre = self._glyph_x(text.strip(), font, cx, cw, anchor, 4)
                    box_w = max(size + 6, font.measure(text.strip()) + 8)
                else:
                    centre = self._glyph_x(text, font, cx, cw, anchor, 4)
                    box_w = size + 6
                if not size / 2 <= centre <= visible_width - size / 2:
                    continue  # scrolled out of view sideways
                box_h = max(size, min(ch - 2 * OUTLINE_WIDTH - 2, size + 4))
                bg = self._row_bg(iid, iid in selected, p)
                label = self._tick_label(used)
                if own and len(text.strip()) > 1:
                    # The check lives in its own column now; the glyph in
                    # front of the row number is simply covered.
                    glyph_w = _measure(font, text[0]) + 4
                    label.configure(image='', bg=bg)
                    label.place(x=round(centre - glyph_w / 2), y=cy + 2, width=glyph_w, height=max(4, ch - 4))
                    self._row_pieces.setdefault(iid, []).append((label, None, 0))
                else:
                    label.configure(image=_checkbox_image(_GLYPHS[text[0]], size, bg, p, tree), bg=bg)
                    label.place(x=round(centre - box_w / 2), y=cy + (ch - box_h) // 2,
                                width=box_w, height=box_h)
                    self._row_pieces.setdefault(iid, []).append((label, _GLYPHS[text[0]], size))
                used += 1
            heading = str(tree.heading(column, 'text') or '')
            glyph = heading[:1] if heading[:1] in _GLYPHS else heading[-1:]
            if top > 12 and glyph in _GLYPHS:
                if span is None:
                    span = self._column_span(column, columns)
                if span is not None:
                    style = ttk.Style(tree)
                    hfont = self._font(heading=True)
                    hanchor = str(tree.heading(column, 'anchor') or 'center')
                    hbg = str(style.lookup(f'{self._style()}.Heading', 'background') or p['heading'])
                    size = max(14, min(18, top - 14))
                    if len(heading.strip()) == 1:
                        centre = span[0] + span[1] / 2
                    else:
                        centre = self._glyph_x(heading, hfont, span[0], span[1], hanchor,
                                               self._heading_pad(style))
                    if not size / 2 <= centre <= visible_width - size / 2:
                        continue
                    box_w, box_h = size + 6, min(top - 2, size + 6)
                    label = self._tick_label(used)
                    if own and len(heading.strip()) > 1:
                        glyph_w = _measure(hfont, glyph) + 4
                        label.configure(image='', bg=hbg)
                        label.place(x=round(centre - glyph_w / 2), y=3, width=glyph_w,
                                    height=max(4, top - 6))
                    else:
                        label.configure(image=_checkbox_image(_GLYPHS[glyph], size, hbg, p, tree), bg=hbg)
                        label.place(x=round(centre - box_w / 2), y=(top - box_h) // 2,
                                    width=box_w, height=box_h)
                    used += 1
        return used

    # ------------------------------------------------------- check column

    def _hash0(self) -> bool:
        """18.4 gave this table its tick in ttk's tree column (#0)."""

        return bool(getattr(self.tree, '_barkav_checkboxes_184', False))

    def _hash0_shown(self) -> bool:
        return self._hash0() and 'tree' in self._shows()

    def _mirror_columns(self) -> set[str]:
        """Value columns that only echo the selection as ☐/☑ (reports'
        ``_check187``); the right-hand check column replaces them."""

        return {str(c) for c in (getattr(self.tree, '_barkav_selection_mirror_columns', ()) or ())}

    def _detect_check_mode(self):
        """How this table shows its row check, and so where it should go:

        'column' - a ☐-only column with a state of its own (sales claims'
                   انتخاب): moved to the right edge as it is;
        'own'    - the check is the selection (18.4's tree column, a ☐ in
                   front of the row number, a mirror column): drawn in a
                   column of our own at the right edge;
        None     - no check, or no rows yet to tell from.
        """

        tree = self.tree
        hash0 = self._hash0()
        mirrors = self._mirror_columns()
        display = self._display_columns()
        kids = tree.get_children('')[:5]
        if not kids:
            # A table's own ☐ column (sales claims' انتخاب) only shows once
            # there are rows; deciding before that could add a second one.
            # 18.4's lone heading box on the far left goes meanwhile.
            if self._hash0_shown():
                tree.configure(show='headings')
            return None, None
        for column in display:
            if column in mirrors or column == CHECK_COLUMN:
                continue
            marked = [v for v in (self._cell_text(iid, column) for iid in kids) if v[:1] in _GLYPHS]
            if not marked:
                continue
            if all(len(v.strip()) == 1 for v in marked):
                return 'column', column
            return 'own', column
        if hash0 or mirrors.intersection(display):
            return 'own', None
        return None, None

    def _ensure_check_column(self) -> None:
        tree = self.tree
        if getattr(tree, '_barkav_no_check_column', False):
            return
        columns = list(tree['columns'])
        if CHECK_COLUMN in columns:
            display = self._display_columns()
            mirrors = self._mirror_columns()
            wanted = [c for c in display if c != CHECK_COLUMN and c not in mirrors] + [CHECK_COLUMN]
            if display != wanted:
                tree.configure(displaycolumns=wanted)
            if self._hash0_shown():
                tree.configure(show='headings')
            return
        mode, column = self._detect_check_mode()
        if mode is None:
            return
        if mode == 'column':
            display = self._display_columns()
            if display[-1] != column:
                tree.configure(displaycolumns=[c for c in display if c != column] + [column])
            if self._hash0_shown():
                # The table's own column already carries the check; 18.4's
                # extra one in the tree column would be a second.
                tree.configure(show='headings')
            tree._barkav_check_mode = 'column'
            return
        self._install_check_column(mode)

    def _install_check_column(self, mode) -> None:
        tree = self.tree
        columns = list(tree['columns'])
        mirrors = self._mirror_columns()
        display = [c for c in self._display_columns() if c not in mirrors]
        try:
            # A table wider than its pane is parked at its right edge, where
            # an RTL row starts; the new column must not push that edge (and
            # the ticks with it) out of view.
            at_edge = float(tree.xview()[1]) >= 0.999
        except (tk.TclError, ValueError, IndexError):
            at_edge = True
        saved = {}
        for column in columns:
            try:
                heading = {key: tree.heading(column, key) for key in ('text', 'anchor', 'command')}
                image = tree.heading(column, 'image')
                if image:
                    heading['image'] = image
                config = {key: tree.column(column, key) for key in ('width', 'minwidth', 'stretch', 'anchor')}
            except tk.TclError:
                return
            saved[column] = (heading, config)
        # Changing -columns resets every column's heading and width, so they
        # are put back exactly as they were.
        tree.configure(columns=columns + [CHECK_COLUMN])
        for column, (heading, config) in saved.items():
            try:
                tree.heading(column, **heading)
                tree.column(column, **config)
            except tk.TclError:
                continue
        tree.configure(displaycolumns=display + [CHECK_COLUMN])
        # The cell itself stays empty (the box is drawn over it); 'e' keeps
        # it inside the contract's every-column-right-aligned rule.
        tree.column(CHECK_COLUMN, width=CHECK_WIDTH, minwidth=CHECK_WIDTH, stretch=False, anchor='e')
        tree.heading(CHECK_COLUMN, text='', anchor='e', command=self.toggle_all)
        tree._barkav_check_mode = mode
        if self._hash0_shown():
            # 18.4's ☐ lives in ttk's tree column, which Tk always draws on the
            # left; hide it - the check state is the selection either way.
            tree.configure(show='headings')
        if at_edge:
            tree.after_idle(lambda: tree.winfo_exists() and tree.xview_moveto(1.0))

    def toggle_all(self) -> None:
        tree = self.tree
        kids = tree.get_children('')
        if not kids:
            return
        if set(tree.selection()) >= set(kids):
            tree.selection_remove(*kids)
        else:
            tree.selection_set(kids)
        sync = getattr(tree, '_barkav_checkbox_sync', None)
        if callable(sync):
            sync()
        self.schedule()

    def check_click(self, event):
        tree = self.tree
        if CHECK_COLUMN not in tree['columns']:
            return None
        try:
            region = tree.identify_region(event.x, event.y)
            column_id = tree.identify_column(event.x)
            display = self._display_columns()
            column = display[int(column_id[1:]) - 1]
        except (tk.TclError, ValueError, IndexError):
            return None
        if column != CHECK_COLUMN or region == 'heading':
            return None
        iid = tree.identify_row(event.y)
        if not iid:
            return 'break'
        if iid in tree.selection():
            tree.selection_remove(iid)
        else:
            tree.selection_add(iid)
        tree.focus(iid)
        sync = getattr(tree, '_barkav_checkbox_sync', None)
        if callable(sync):
            sync()
        self.schedule()
        return 'break'

    def _paint_own_checks(self, rows, top, p, columns, selected) -> int:
        tree = self.tree
        visible_width = tree.winfo_width()
        # xview fractions do not reliably describe the final partially clipped
        # column in a Treeview. Read the overlay column's real screen geometry
        # from a visible row so the custom check stays over its cell at either
        # end of a horizontal scroll.
        span = None
        for iid, _box in rows:
            try:
                cell = tree.bbox(iid, column=CHECK_COLUMN)
            except tk.TclError:
                cell = None
            if cell and len(cell) == 4 and int(cell[2]) > 0:
                left, _y, width, _height = (int(value) for value in cell)
                if left < visible_width and left + width > 0:
                    span = (left, width)
                    break
        if span is None:
            # An empty table still gets its heading tick. There is no row cell
            # to query, so retain the estimate only for that header-only case.
            if rows:
                return 0
            span = self._column_span(CHECK_COLUMN, columns)
        if span is None:
            return 0
        centre = span[0] + span[1] / 2
        if not 8 <= centre <= visible_width - 8:
            return 0
        used = 0
        for iid, (_x, y, _w, h) in rows:
            size = max(14, min(18, h - 12))
            box_w = max(size + 4, min(span[1] - 4, size + 12))
            box_h = max(size, min(h - 2 * OUTLINE_WIDTH - 2, size + 4))
            bg = self._row_bg(iid, iid in selected, p)
            label = self._tick_label(used)
            label.configure(image=_checkbox_image(iid in selected, size, bg, p, tree), bg=bg)
            label.place(x=round(centre - box_w / 2), y=y + (h - box_h) // 2, width=box_w, height=box_h)
            self._row_pieces.setdefault(iid, []).append((label, iid in selected, size))
            used += 1
        if top > 12:
            kids = tree.get_children('')
            style = ttk.Style(tree)
            hbg = str(style.lookup(f'{self._style()}.Heading', 'background') or p['heading'])
            size = max(14, min(18, top - 14))
            box_w, box_h = size + 6, min(top - 2, size + 6)
            label = self._tick_label(used)
            label.configure(image=_checkbox_image(bool(kids) and selected >= set(kids), size, hbg, p, tree),
                            bg=hbg)
            label.place(x=round(centre - box_w / 2), y=(top - box_h) // 2, width=box_w, height=box_h)
            used += 1
        return used

    def _heading_pad(self, style) -> int:
        try:
            value = style.lookup(f'{self._style()}.Heading', 'padding')
            parts = self.tree.tk.splitlist(value) if isinstance(value, str) else tuple(value or ())
            return int(float(str(parts[0]))) if parts else 4
        except (tk.TclError, ValueError, IndexError, TypeError):
            return 4

    def _column_span(self, column, columns):
        tree = self.tree
        x = 0
        tree_width = int(tree.column('#0', 'width')) if 'tree' in self._shows() else 0
        total = tree_width + sum(int(tree.column(c, 'width')) for c in columns)
        try:
            offset = int(float(tree.xview()[0]) * total)
        except (tk.TclError, ValueError, IndexError):
            offset = 0
        if column == '#0':
            return (-offset, tree_width) if tree_width else None
        x = tree_width
        for c in columns:
            w = int(tree.column(c, 'width'))
            if c == column:
                return (x - offset, w)
            x += w
        return None

    # ------------------------------------------------------- status stripe

    def _row_tags(self, iid) -> list[str]:
        try:
            tags = [str(tag) for tag in (self.tree.item(iid, 'tags') or ())]
        except tk.TclError:
            return []
        if iid == self._hover_iid:
            tags += self._hover_saved.get(iid, [])
        return tags

    def _paint_stripes(self, rows, p) -> int:
        tree = self.tree
        width = tree.winfo_width()
        selected = set(tree.selection())
        used = 0
        for iid, (x, y, w, h) in rows:
            role = next((STATUS_STRIPES[tag] for tag in self._row_tags(iid)
                         if tag in STATUS_STRIPES), None)
            if role is None or h < 10:
                continue
            # The status stripe marks the RTL row start, which is the viewport
            # edge. A scrolled column's bbox may be clipped or off-screen.
            edge = width - 1
            # Inside the selection outline when there is one.
            inset = OUTLINE_WIDTH + 1 if iid in selected else 0
            if used == len(self._stripes):
                self._stripes.append(self._overlay(tk.Frame(tree, bd=0, highlightthickness=0)))
            stripe = self._stripes[used]
            stripe.configure(bg=p[role])
            stripe.place(x=edge - inset - STRIPE_WIDTH, y=y + 3, width=STRIPE_WIDTH, height=h - 6)
            used += 1
        return used

    # --------------------------------------------------------------- hover

    def _background_tags(self, tags) -> list[str]:
        found = []
        for tag in tags:
            if str(tag).startswith(HOVER_PREFIX):
                continue
            try:
                if self.tree.tag_configure(tag, 'background'):
                    found.append(str(tag))
            except tk.TclError:
                continue
        return found

    def _motion(self, event):
        try:
            iid = self.tree.identify_row(event.y)
        except tk.TclError:
            return
        if iid == self._hover_iid:
            return
        try:
            self.hover_off()
            if iid and iid not in self.tree.selection():
                self._hover_on(iid)
        except (tk.TclError, ValueError):
            pass

    def _hover_on(self, iid) -> None:
        tree = self.tree
        try:
            tags = [str(tag) for tag in (tree.item(iid, 'tags') or ())]
        except tk.TclError:
            return
        p = _palette()
        base = _hex(tree, self._row_bg(iid, False, p))
        removed = self._background_tags(tags)
        foreground = ''
        for tag in removed:
            try:
                foreground = str(tree.tag_configure(tag, 'foreground') or '')
            except tk.TclError:
                foreground = ''
            if foreground:
                break
        colour = _mix(base, p['text_primary'], 0.08)
        name = f"{HOVER_PREFIX}{colour.lstrip('#')}_{foreground.lstrip('#')}"
        if name not in self._hover_tags:
            options = {'background': colour}
            if foreground:
                options['foreground'] = foreground
            tree.tag_configure(name, **options)
            self._hover_tags.add(name)
        kept = [tag for tag in tags if tag not in removed and not tag.startswith(HOVER_PREFIX)]
        tree.item(iid, tags=tuple(kept + [name]))
        self._hover_iid = iid
        self._hover_saved[iid] = removed
        self._recolour(iid)

    def hover_off(self) -> None:
        iid, self._hover_iid = self._hover_iid, ''
        if iid:
            self._restore(iid)
        # Any other row still wearing a hover tag (a screen copied a hovered
        # row's tags, or kept them through a refresh) gets its colour back.
        for name in list(self._hover_tags):
            try:
                items = self.tree.tag_has(name)
            except tk.TclError:
                continue
            for other in items:
                if other != self._hover_iid:
                    self._restore(other)

    def _restore(self, iid) -> None:
        tree = self.tree
        removed = self._hover_saved.pop(iid, [])
        try:
            if not tree.exists(iid):
                return
            tags = [str(tag) for tag in (tree.item(iid, 'tags') or ())]
        except tk.TclError:
            return
        kept = [tag for tag in tags if not tag.startswith(HOVER_PREFIX)]
        if not self._background_tags(kept):
            if removed:
                kept += [tag for tag in removed if tag not in kept]
            else:
                parity = 'even' if tree.index(iid) % 2 == 0 else 'odd'
                try:
                    if tree.tag_configure(parity, 'background'):
                        kept.append(parity)
                except tk.TclError:
                    pass
        if kept != tags:
            tree.item(iid, tags=tuple(kept))
            self._recolour(iid)

    def _recolour(self, iid) -> None:
        """Give the boxes and patches over one row its current colour now,
        in the same turn as the row itself. Left to the next repaint they
        trailed the mouse by up to a second on Windows (operator report,
        2026-09-27). A row with nothing painted over it yet gets a repaint."""

        pieces = self._row_pieces.get(iid)
        if not pieces:
            self.schedule()
            return
        tree = self.tree
        p = _palette()
        try:
            bg = self._row_bg(iid, iid in tree.selection(), p)
            for label, checked, size in pieces:
                if checked is None:
                    label.configure(bg=bg)
                else:
                    label.configure(image=_checkbox_image(checked, size, bg, p, tree), bg=bg)
        except tk.TclError:
            self.schedule()

    # --------------------------------------------------------- empty state

    def _find_add_button(self):
        """The nearest visible Add action around this table, if any."""

        node = self.tree.master
        inside_tree = str(self.tree) + '.'
        for _level in range(4):
            if node is None:
                return None
            for widget in _walk(node):
                if not isinstance(widget, (tk.Button, ttk.Button)):
                    continue
                # The empty-state card's own Add button lives inside the
                # tree; finding it would have it invoke itself forever.
                if str(widget).startswith(inside_tree):
                    continue
                try:
                    text = str(widget.cget('text') or '')
                    mapped = widget.winfo_ismapped()
                    state = str(widget.cget('state'))
                except tk.TclError:
                    continue
                if mapped and state != 'disabled' and ('افزودن' in text or text.strip().startswith('+')):
                    return widget
            node = node.master
        return None

    def _paint_empty(self, top: int, p) -> bool:
        tree = self.tree
        if getattr(tree, '_barkav_own_empty_state', False):
            return False
        if tree.get_children(''):
            return False
        if 'headings' not in self._shows():
            return False
        width, height = tree.winfo_width(), tree.winfo_height()
        if width < _EMPTY_MIN_SIZE[0] or height - top < _EMPTY_MIN_SIZE[1]:
            return False
        style = ttk.Style(tree)
        background = _hex(tree, style.lookup(self._style(), 'fieldbackground')
                          or style.lookup(self._style(), 'background') or p['row_even'])
        button = self._find_add_button()
        key = background
        if self._empty is None or self._empty_key != key:
            if self._empty is not None:
                self._empty.destroy()
            # Built once per colour; its Add button looks the screen's own
            # Add action up when clicked, so the card never goes stale.
            self._empty = empty_card(tree, background=background, p=p, button=button,
                                     resolve=self._find_add_button)
            self._empty_key = key
        _show_cta(self._empty, button is not None)
        self._empty.place(relx=0.5, y=top + (height - top) // 2, anchor='center')
        return True


def _walk(widget):
    yield widget
    try:
        children = widget.winfo_children()
    except tk.TclError:
        return
    for child in children:
        yield from _walk(child)


def _hover_reset(event):
    decorator = getattr(event.widget, '_barkav_rows', None)
    if decorator is not None:
        decorator.hover_off()


def _check_press(event):
    # Button 1 matches this more specific binding instead of <ButtonPress>,
    # so it resets the hover itself before handling a click on the check.
    decorator = getattr(event.widget, '_barkav_rows', None)
    if decorator is None:
        return None
    decorator.hover_off()
    return decorator.check_click(event)


def _show_cta(card, visible: bool) -> None:
    cta = getattr(card, '_barkav_cta', None)
    if cta is None:
        return
    try:
        if visible and not cta.winfo_manager():
            cta.pack(pady=(10, 0))
        elif not visible and cta.winfo_manager():
            cta.pack_forget()
    except tk.TclError:
        pass


def empty_card(parent, *, background: str, p: dict, title: str = 'ردیفی برای نمایش نیست',
               hint: str | None = None, button=None, command=None, action_text: str | None = None,
               resolve=None):
    """Section 11: icon, title, one line of help and, when the screen has
    one, the button that fills the table - instead of a lone grey sentence.

    ``resolve`` finds the screen's Add button at click time; screens rebuild
    their toolbars, so a button captured when the card was made can be gone.
    """

    from .theme import font

    if button is not None and command is None:
        def command(_fallback=button):
            target = resolve() if resolve is not None else None
            target = target or _fallback
            # Never this card's own button: invoking it would come straight
            # back here.
            if target is None or str(target).startswith(str(card) + '.'):
                return
            try:
                target.invoke()
            except tk.TclError:
                pass
        try:
            action_text = action_text or str(button.cget('text') or '').strip()
        except tk.TclError:
            action_text = action_text or 'افزودن'
    if hint is None:
        hint = ('ردیف تازه اضافه کن، یا اگر فیلتری فعال است آن را تغییر بده.' if command
                else 'وقتی داده‌ای ثبت شود یا فیلتر تغییر کند، اینجا دیده می‌شود.')
    card = tk.Frame(parent, bg=background, bd=0, highlightthickness=0)
    ring = _mix(background, p['accent'], 0.16)
    image = _ring_icon('inbox', ring=ring, colour=p['accent'], background=background, master=card)
    badge = tk.Label(card, image=image, bg=background, bd=0)
    badge.image = image
    badge.pack(pady=(0, 6))
    tk.Label(card, text=title, bg=background, fg=p['text_primary'],
             font=font('body', bold=True), anchor='e', justify='right').pack(fill='x')
    tk.Label(card, text=hint, bg=background, fg=p['text_secondary'], font=font('small'),
             wraplength=320, anchor='e', justify='right').pack(fill='x', pady=(2, 0))
    card._barkav_cta = None
    if command is not None:
        card._barkav_cta = ttk.Button(card, text=action_text or 'افزودن', style='Success.TButton',
                                      command=command)
        card._barkav_cta.pack(pady=(10, 0))
    return card


def _ring_icon(name: str, *, ring: str, colour: str, background: str, master, size: int = 44):
    from .line_icons import render

    key = ('ring', name, ring, colour, background, size)
    cached = _cached_image(master, key)
    if cached is not None:
        return cached
    scale = _SUPERSAMPLE
    plate = Image.new('RGBA', (size * scale, size * scale), rgb(background) + (255,))
    ImageDraw.Draw(plate).ellipse((0, 0, size * scale - 1, size * scale - 1), fill=rgb(ring) + (255,))
    plate = plate.resize((size, size), Image.LANCZOS)
    inner = size // 2
    glyph = render(name, size=inner, colour=colour, background=ring)
    plate.paste(glyph, ((size - inner) // 2, (size - inner) // 2))
    photo = ImageTk.PhotoImage(plate.convert('RGB'), master=master)
    return _keep_image(master, key, photo)
