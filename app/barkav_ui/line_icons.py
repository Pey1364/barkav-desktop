"""Section 11: one family of monochrome line icons.

The rail, the table toolbars, empty states and the command palette all draw
from this set, so every icon has the same stroke, corner and size and takes
its colour from the state it is in (idle, hover, active) instead of carrying
its own artwork colours.

Icons are drawn with PIL on a 24-unit grid at four times the target size and
reduced, then flattened onto the colour they will sit on - the same approach
``art.nav_icon`` uses, which keeps edges soft without relying on widget alpha.
Colours always come in from the caller; nothing here names one.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageTk

from .art import rgb

_SUPERSAMPLE = 4
_cache: dict[tuple, tuple] = {}


class _Pen:
    """Strokes on the 24-unit icon grid, scaled to the supersampled canvas."""

    def __init__(self, draw: ImageDraw.ImageDraw, size: int, colour: tuple, weight: float):
        self.draw = draw
        self.k = size * _SUPERSAMPLE / 24.0
        self.colour = colour
        self.width = max(2, round(1.8 * weight * self.k))

    def _p(self, x: float, y: float) -> tuple[float, float]:
        return x * self.k, y * self.k

    def _cap(self, x: float, y: float) -> None:
        r = self.width / 2
        self.draw.ellipse((x - r, y - r, x + r, y + r), fill=self.colour)

    def line(self, *points: tuple[float, float]) -> None:
        xy = [self._p(x, y) for x, y in points]
        self.draw.line(xy, fill=self.colour, width=self.width, joint='curve')
        # PIL ends lines square; a dot at each end gives the round cap the
        # rest of the family uses.
        self._cap(*xy[0])
        self._cap(*xy[-1])

    def rect(self, x0: float, y0: float, x1: float, y1: float, radius: float = 0) -> None:
        self.draw.rounded_rectangle(
            (*self._p(x0, y0), *self._p(x1, y1)), radius=radius * self.k,
            outline=self.colour, width=self.width,
        )

    def circle(self, cx: float, cy: float, r: float, *, fill: bool = False) -> None:
        box = (*self._p(cx - r, cy - r), *self._p(cx + r, cy + r))
        if fill:
            self.draw.ellipse(box, fill=self.colour)
        else:
            self.draw.ellipse(box, outline=self.colour, width=self.width)

    def arc(self, cx: float, cy: float, r: float, start: float, end: float) -> None:
        box = (*self._p(cx - r, cy - r), *self._p(cx + r, cy + r))
        self.draw.arc(box, start, end, fill=self.colour, width=self.width)

    def wedge(self, cx: float, cy: float, r: float, start: float, end: float) -> None:
        box = (*self._p(cx - r, cy - r), *self._p(cx + r, cy + r))
        self.draw.pieslice(box, start, end, fill=self.colour)


def _dashboard(p: _Pen) -> None:
    p.rect(3, 3, 10, 12, 1.6)
    p.rect(14, 3, 21, 8, 1.6)
    p.rect(14, 12, 21, 21, 1.6)
    p.rect(3, 16, 10, 21, 1.6)


def _data(p: _Pen) -> None:
    p.rect(5, 4, 19, 21, 2)
    p.rect(9, 2.5, 15, 5.5, 1)
    p.line((9, 10.5), (15, 10.5))
    p.line((9, 14.5), (15, 14.5))
    p.line((9, 18), (12, 18))


def _transactions(p: _Pen) -> None:
    p.line((4, 8), (18, 8))
    p.line((15, 5), (18, 8), (15, 11))
    p.line((20, 16), (6, 16))
    p.line((9, 13), (6, 16), (9, 19))


def _income(p: _Pen) -> None:
    p.line((4, 17), (9, 12), (13, 16), (20, 9))
    p.line((15, 9), (20, 9), (20, 14))


def _contractors(p: _Pen) -> None:
    p.rect(3, 7, 21, 20, 2)
    p.line((9, 7), (9, 5), (15, 5), (15, 7))
    p.line((3, 12.5), (21, 12.5))


def _project(p: _Pen) -> None:
    p.line((5, 20), (5, 12))
    p.line((10, 20), (10, 5))
    p.line((15, 20), (15, 14))
    p.line((20, 20), (20, 9))


def _account(p: _Pen) -> None:
    p.circle(12, 8, 4)
    p.arc(12, 21, 8, 180, 360)


def _folder(p: _Pen) -> None:
    p.line((3, 6.5), (9.5, 6.5), (11.5, 9), (21, 9), (21, 19), (3, 19), (3, 6.5))


def _theme(p: _Pen) -> None:
    p.circle(12, 12, 8)
    p.wedge(12, 12, 8, -90, 90)


def _settings(p: _Pen) -> None:
    p.line((4, 6), (12.5, 6))
    p.line((17.5, 6), (20, 6))
    p.circle(15, 6, 2.2)
    p.line((4, 12), (6.5, 12))
    p.line((11.5, 12), (20, 12))
    p.circle(9, 12, 2.2)
    p.line((4, 18), (14.5, 18))
    p.circle(17, 18, 2.2)


def _collapse(p: _Pen) -> None:
    p.line((13, 6), (19, 12), (13, 18))
    p.line((5, 6), (11, 12), (5, 18))


def _expand(p: _Pen) -> None:
    p.line((11, 6), (5, 12), (11, 18))
    p.line((19, 6), (13, 12), (19, 18))


def _plus(p: _Pen) -> None:
    p.line((12, 5), (12, 19))
    p.line((5, 12), (19, 12))


def _edit(p: _Pen) -> None:
    p.line((4, 20), (8, 20), (19, 9), (15, 5), (4, 16), (4, 20))
    p.line((13, 7), (17, 11))


def _copy(p: _Pen) -> None:
    p.rect(8, 8, 20, 20, 2)
    p.line((16, 8), (16, 4), (4, 4), (4, 16), (8, 16))


def _trash(p: _Pen) -> None:
    p.line((4, 7), (20, 7))
    p.line((9, 7), (9, 4), (15, 4), (15, 7))
    p.line((6, 7), (7, 20), (17, 20), (18, 7))
    p.line((10, 11), (10, 16))
    p.line((14, 11), (14, 16))


def _more(p: _Pen) -> None:
    for x in (5, 12, 19):
        p.circle(x, 12, 1.7, fill=True)


def _search(p: _Pen) -> None:
    p.circle(11, 11, 7)
    p.line((16.2, 16.2), (20, 20))


def _inbox(p: _Pen) -> None:
    p.line((3, 13), (6, 5), (18, 5), (21, 13), (21, 19), (3, 19), (3, 13))
    p.line((3, 13), (8, 13), (9.5, 15.5), (14.5, 15.5), (16, 13), (21, 13))


def _play(p: _Pen) -> None:
    p.line((7, 5), (19, 12), (7, 19), (7, 5))


def _export(p: _Pen) -> None:
    p.line((12, 4), (12, 15))
    p.line((8, 11), (12, 15), (16, 11))
    p.line((4, 17), (4, 20), (20, 20), (20, 17))


def _calendar(p: _Pen) -> None:
    p.rect(3, 5, 21, 21, 2)
    p.line((3, 10), (21, 10))
    p.line((8, 3), (8, 7))
    p.line((16, 3), (16, 7))


def _page(p: _Pen) -> None:
    p.rect(5, 3, 19, 21, 2)
    p.line((9, 8), (15, 8))
    p.line((9, 12), (15, 12))


def _upload(p: _Pen) -> None:
    p.line((12, 15), (12, 4))
    p.line((8, 8), (12, 4), (16, 8))
    p.line((4, 15), (4, 20), (20, 20), (20, 15))


def _sheet(p: _Pen) -> None:
    p.rect(4, 3, 20, 21, 2)
    p.line((4, 9), (20, 9))
    p.line((4, 15), (20, 15))
    p.line((10, 3), (10, 21))


def _attach(p: _Pen) -> None:
    # A paper clip tilted 40 degrees, as file-attach icons draw it: one
    # stroke - outer leg, bottom turn, long leg, top turn, inner leg.
    import math

    def turn(cx, cy, r, start, end, steps=10):
        return [(cx + r * math.cos(math.radians(start + (end - start) * i / steps)),
                 cy + r * math.sin(math.radians(start + (end - start) * i / steps)))
                for i in range(steps + 1)]

    path = ([(15.5, 7.5), (15.5, 17)] + turn(12.25, 17, 3.25, 0, 180)
            + [(9, 17), (9, 5.5)] + turn(11.25, 5.5, 2.25, 180, 360)
            + [(13.5, 5.5), (13.5, 15.5)])
    angle = math.radians(40)
    cos, sin = math.cos(angle), math.sin(angle)
    rotated = [(12 + (x - 12) * cos - (y - 12) * sin, 12 + (x - 12) * sin + (y - 12) * cos)
               for x, y in path]
    p.line(*rotated)


def _sheet_file(p: _Pen) -> None:
    # A spreadsheet page: folded corner, then a small grid.
    p.line((14, 3), (6, 3), (6, 21), (19, 21), (19, 8), (14, 3))
    p.line((14, 3), (14, 8), (19, 8))
    p.line((9, 12.5), (16, 12.5))
    p.line((9, 16.5), (16, 16.5))
    p.line((12.5, 11), (12.5, 18.5))


def _menu(p: _Pen) -> None:
    p.line((4, 7), (20, 7))
    p.line((4, 12), (20, 12))
    p.line((4, 17), (14, 17))


def _hamburger(p: _Pen) -> None:
    # Three bars of one length: the file menu's mark has to read at a glance,
    # and ``menu``'s shortened third bar reads as a text-alignment glyph.
    p.line((4, 6.5), (20, 6.5))
    p.line((4, 12), (20, 12))
    p.line((4, 17.5), (20, 17.5))


def _bell(p: _Pen) -> None:
    p.line((6, 16), (6, 11))
    p.arc(12, 11, 6, 180, 360)
    p.line((18, 11), (18, 16), (20, 18), (4, 18), (6, 16))
    p.arc(12, 19, 2, 0, 180)


def _print(p: _Pen) -> None:
    p.rect(7, 3, 17, 8, 1)
    p.rect(3, 8, 21, 17, 2)
    p.rect(7, 14, 17, 21, 1)


def _check(p: _Pen) -> None:
    p.line((5, 12.5), (10, 17.5), (19, 7))


def _save(p: _Pen) -> None:
    p.line((5, 4), (16, 4), (19, 7), (19, 20), (5, 20), (5, 4))
    p.line((8, 4), (8, 9), (15, 9), (15, 4))
    p.line((8, 20), (8, 14), (16, 14), (16, 20))


def _undo(p: _Pen) -> None:
    p.line((9, 6), (5, 10), (9, 14))
    p.line((5, 10), (14, 10))
    p.arc(14, 14.5, 4.5, 270, 90)
    p.line((14, 19), (10, 19))


def _redo(p: _Pen) -> None:
    p.line((15, 6), (19, 10), (15, 14))
    p.line((19, 10), (10, 10))
    p.arc(10, 14.5, 4.5, 90, 270)
    p.line((10, 19), (14, 19))


def _close(p: _Pen) -> None:
    p.line((7, 7), (17, 17))
    p.line((17, 7), (7, 17))


def _pin(p: _Pen) -> None:
    p.line((9, 4), (15, 4), (14, 10), (17, 13), (7, 13), (10, 10), (9, 4))
    p.line((12, 13), (12, 20))


def _cheque(p: _Pen) -> None:
    p.rect(2.5, 6, 21.5, 18, 2)
    p.line((6, 10), (18, 10))
    p.line((6, 14), (11, 14))
    p.line((14, 14), (18, 14))


def _bank(p: _Pen) -> None:
    p.line((3, 9), (12, 4), (21, 9), (3, 9))
    p.line((6, 11), (6, 17))
    p.line((10, 11), (10, 17))
    p.line((14, 11), (14, 17))
    p.line((18, 11), (18, 17))
    p.line((3, 20), (21, 20))


def _coins(p: _Pen) -> None:
    p.draw.ellipse((*p._p(5, 3), *p._p(19, 9)), outline=p.colour, width=p.width)
    p.line((5, 6), (5, 12))
    p.line((19, 6), (19, 12))
    p.arc(12, 9, 7, 0, 180)
    p.line((5, 12), (5, 18))
    p.line((19, 12), (19, 18))
    p.arc(12, 15, 7, 0, 180)


def _refresh(p: _Pen) -> None:
    p.arc(12, 12, 7.5, 200, 520)
    p.line((19.3, 5.5), (19.3, 10.2), (14.6, 10.2))


def _system(p: _Pen) -> None:
    p.rect(3, 4, 21, 16, 2)
    p.line((9, 20), (15, 20))
    p.line((12, 16), (12, 20))


def _file(p: _Pen) -> None:
    p.line((6, 3), (14, 3), (19, 8), (19, 21), (6, 21), (6, 3))
    p.line((14, 3), (14, 8), (19, 8))
    p.line((9, 13), (16, 13))
    p.line((9, 17), (14, 17))


def _chevron(p: _Pen) -> None:
    # Points left, where a flyout from the right-hand rail opens.
    p.line((14.5, 6), (8.5, 12), (14.5, 18))


def _chevron_right(p: _Pen) -> None:
    p.line((9.5, 6), (15.5, 12), (9.5, 18))


def _arrow_head(p: _Pen, *points: tuple[float, float]) -> None:
    p.draw.polygon([p._p(x, y) for x, y in points], fill=p.colour)


def _rotate_right(p: _Pen) -> None:
    # An open circle, clockwise, ending in a filled arrow head.
    p.arc(12, 12.5, 7.5, 40, 296)
    _arrow_head(p, (17.0, 2.9), (13.4, 8.2), (19.6, 8.4))


def _rotate_left(p: _Pen) -> None:
    p.arc(12, 12.5, 7.5, 244, 500)
    _arrow_head(p, (7.0, 2.9), (10.6, 8.2), (4.4, 8.4))


def _crop(p: _Pen) -> None:
    # Two crossing corner marks, the crop frame.
    p.line((6.5, 2), (6.5, 16), (8.5, 18), (22, 18))
    p.line((2, 6.5), (16, 6.5), (18, 8.5), (18, 22))


DRAWERS = {
    'dashboard': _dashboard,
    'data': _data,
    'transactions': _transactions,
    'income': _income,
    'contractors': _contractors,
    'project': _project,
    'account': _account,
    'folder': _folder,
    'theme': _theme,
    'settings': _settings,
    'collapse': _collapse,
    'expand': _expand,
    'plus': _plus,
    'edit': _edit,
    'copy': _copy,
    'trash': _trash,
    'more': _more,
    'search': _search,
    'inbox': _inbox,
    'play': _play,
    'export': _export,
    'calendar': _calendar,
    'page': _page,
    'upload': _upload,
    'sheet': _sheet,
    'attach': _attach,
    'sheet_file': _sheet_file,
    'menu': _menu,
    'hamburger': _hamburger,
    'bell': _bell,
    'check': _check,
    'print': _print,
    'save': _save,
    'undo': _undo,
    'redo': _redo,
    'close': _close,
    'pin': _pin,
    'cheque': _cheque,
    'bank': _bank,
    'coins': _coins,
    'file': _file,
    'refresh': _refresh,
    'system': _system,
    'chevron': _chevron,
    'chevron_left': _chevron,
    'chevron_right': _chevron_right,
    'rotate_right': _rotate_right,
    'rotate_left': _rotate_left,
    'crop': _crop,
}

NAMES = tuple(DRAWERS)


def render(name: str, *, size: int, colour: str, background: str | None,
           weight: float = 1.0) -> Image.Image:
    """The icon at ``size`` x ``size``: opaque RGB flattened onto
    ``background``, or RGBA with real transparency when that is None (for
    surfaces whose colour changes under it, such as a button on hover)."""

    drawer = DRAWERS[name]
    big = size * _SUPERSAMPLE
    layer = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    drawer(_Pen(ImageDraw.Draw(layer), size, rgb(colour) + (255,), weight))
    layer = layer.resize((size, size), Image.LANCZOS)
    if background is None:
        return layer
    plate = Image.new('RGBA', (size, size), rgb(background) + (255,))
    plate.alpha_composite(layer)
    return plate.convert('RGB')


def icon(name: str, *, size: int, colour: str, background: str | None, weight: float = 1.0,
         master=None) -> ImageTk.PhotoImage | None:
    """A cached PhotoImage of one icon, or None for an unknown name."""

    if name not in DRAWERS:
        return None
    # A PhotoImage belongs to one Tcl interpreter; after a restart the old
    # one is gone, so the cache is checked against the live interpreter.
    interp = getattr(master, 'tk', None)
    key = (name, int(size), colour, background, round(weight, 2), id(interp))
    cached = _cache.get(key)
    if cached is not None and cached[0] is interp:
        return cached[1]
    photo = ImageTk.PhotoImage(
        render(name, size=int(size), colour=colour, background=background, weight=weight),
        master=master,
    )
    _cache[key] = (interp, photo)
    return photo


def render_tile(name: str, *, size: int, box: int, colour: str, ground: str,
                fill: str | None = None, radius: int = 8, weight: float = 1.0) -> Image.Image:
    """The icon centred on a ``box`` x ``box`` rounded square of ``fill``,
    flattened onto ``ground`` - the colour of whatever the tile sits on.

    A button that changes plate under the pointer needs the plate to be part
    of its image: a Tk button's own background is a rectangle, so a hover
    colour set on the button shows square corners round the rounded shape."""

    big = box * _SUPERSAMPLE
    plate = Image.new('RGBA', (big, big), rgb(ground) + (255,))
    if fill:
        ImageDraw.Draw(plate).rounded_rectangle(
            (0, 0, big - 1, big - 1), radius=radius * _SUPERSAMPLE,
            fill=rgb(fill) + (255,))
    plate = plate.resize((box, box), Image.LANCZOS)
    glyph = render(name, size=size, colour=colour, background=None, weight=weight)
    offset = (box - size) // 2
    plate.alpha_composite(glyph, (offset, offset))
    return plate.convert('RGB')


def tile(name: str, *, size: int, box: int, colour: str, ground: str,
         fill: str | None = None, radius: int = 8, weight: float = 1.0,
         master=None) -> ImageTk.PhotoImage | None:
    """A cached PhotoImage of one icon on its rounded tile, or None for an
    unknown name."""

    if name not in DRAWERS:
        return None
    interp = getattr(master, 'tk', None)
    key = ('tile', name, int(size), int(box), colour, ground, fill, int(radius),
           round(weight, 2), id(interp))
    cached = _cache.get(key)
    if cached is not None and cached[0] is interp:
        return cached[1]
    photo = ImageTk.PhotoImage(
        render_tile(name, size=int(size), box=int(box), colour=colour, ground=ground,
                    fill=fill, radius=int(radius), weight=weight),
        master=master,
    )
    _cache[key] = (interp, photo)
    return photo


def clear_cache() -> None:
    _cache.clear()
