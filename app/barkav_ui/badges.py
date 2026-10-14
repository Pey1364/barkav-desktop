"""Section 11: small rendered pictures the dashboard and استارت share.

An icon on a rounded tile (operator-approved D2, the dashboard cards), a
progress ring (D3's overall progress, S2's project cards) and the استارت
actions' feature tiles. All are drawn with PIL at four times their size and
reduced, then flattened onto the colour they sit on - the approach line_icons
and row_overlay already use - so their edges stay soft without widget alpha.
Every colour comes in from the caller.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageTk

from .art import rgb
from .line_icons import render

_SUPERSAMPLE = 4
_cache: dict[tuple, tuple] = {}


def _cached(key: tuple, master, build):
    # A PhotoImage belongs to one Tcl interpreter; after a restart the old
    # one is gone, so the cache is checked against the live interpreter.
    interp = getattr(master, 'tk', None)
    key = key + (id(interp),)
    hit = _cache.get(key)
    if hit is not None and hit[0] is interp:
        return hit[1]
    photo = ImageTk.PhotoImage(build(), master=master)
    _cache[key] = (interp, photo)
    return photo


def icon_tile(name: str, *, size: int, colour: str, fill: str, background: str,
              radius: int | None = None, icon_size: int | None = None, master=None):
    """``name``'s line icon centred on a rounded square of ``fill``."""

    radius = max(4, size // 4) if radius is None else int(radius)
    icon_size = int(icon_size or max(12, round(size * 0.52)))

    def build():
        big = size * _SUPERSAMPLE
        plate = Image.new('RGBA', (big, big), rgb(background) + (255,))
        ImageDraw.Draw(plate).rounded_rectangle(
            (0, 0, big - 1, big - 1), radius=radius * _SUPERSAMPLE, fill=rgb(fill) + (255,))
        plate = plate.resize((size, size), Image.LANCZOS)
        glyph = render(name, size=icon_size, colour=colour, background=None)
        plate.alpha_composite(glyph, ((size - icon_size) // 2, (size - icon_size) // 2))
        return plate.convert('RGB')

    return _cached(('tile', name, size, colour, fill, background, radius, icon_size), master, build)


def progress_ring(fraction: float, *, size: int, width: int, colour: str, track: str,
                  background: str, master=None):
    """A ring filled clockwise from twelve o'clock by ``fraction`` (0..1),
    with round ends, on a square of ``background``."""

    try:
        fraction = max(0.0, min(1.0, float(fraction or 0)))
    except (TypeError, ValueError):
        fraction = 0.0
    sweep = round(fraction * 360)

    def build():
        big = size * _SUPERSAMPLE
        line = max(2, int(width) * _SUPERSAMPLE)
        image = Image.new('RGB', (big, big), rgb(background))
        draw = ImageDraw.Draw(image)
        half = line / 2
        box = (half, half, big - 1 - half, big - 1 - half)
        draw.ellipse(box, outline=rgb(track), width=line)
        if sweep:
            draw.arc(box, -90, -90 + sweep, fill=rgb(colour), width=line)
            centre = (big - 1) / 2
            radius = (box[2] - box[0]) / 2
            for angle in (-90, -90 + sweep):
                x = centre + radius * math.cos(math.radians(angle))
                y = centre + radius * math.sin(math.radians(angle))
                draw.ellipse((x - half, y - half, x + half, y + half), fill=rgb(colour))
        return image.resize((size, size), Image.LANCZOS)

    return _cached(('ring', sweep, size, width, colour, track, background), master, build)


class _Duo:
    """Filled shapes and round-capped strokes on a 24-unit grid - a glyph
    with a solid part and a see-through part, which one-weight line icons
    cannot draw."""

    def __init__(self, draw: ImageDraw.ImageDraw, size: int):
        self.draw = draw
        self.k = size * _SUPERSAMPLE / 24.0

    def _p(self, x: float, y: float) -> tuple[float, float]:
        return x * self.k, y * self.k

    def _dot(self, x: float, y: float, width: int, colour: tuple) -> None:
        r = width / 2
        self.draw.ellipse((x - r, y - r, x + r, y + r), fill=colour)

    def shape(self, points, *, fill: tuple | None = None, outline: tuple | None = None,
              width: float = 1.5) -> None:
        xy = [self._p(x, y) for x, y in points]
        if fill is not None:
            self.draw.polygon(xy, fill=fill)
        if outline is not None:
            stroke = max(2, round(width * self.k))
            self.draw.line(xy + [xy[0]], fill=outline, width=stroke, joint='curve')
            for x, y in xy:
                self._dot(x, y, stroke, outline)

    def line(self, points, colour: tuple, width: float = 1.5) -> None:
        xy = [self._p(x, y) for x, y in points]
        stroke = max(2, round(width * self.k))
        self.draw.line(xy, fill=colour, width=stroke, joint='curve')
        self._dot(*xy[0], stroke, colour)
        self._dot(*xy[-1], stroke, colour)

    def box(self, x0: float, y0: float, x1: float, y1: float, radius: float, colour: tuple) -> None:
        self.draw.rounded_rectangle((*self._p(x0, y0), *self._p(x1, y1)),
                                    radius=radius * self.k, fill=colour)

    def disc(self, cx: float, cy: float, r: float, colour: tuple) -> None:
        self.draw.ellipse((*self._p(cx - r, cy - r), *self._p(cx + r, cy + r)), fill=colour)


def _new_project(pen: _Duo, ink: tuple, glass: tuple, deep: tuple) -> None:
    # A sheet with its corner folded, and a plus on a disc over its foot.
    sheet = [(6, 3), (14.5, 3), (19, 7.5), (19, 20), (6, 20)]
    pen.shape(sheet, fill=glass)
    pen.shape(sheet, outline=ink)
    pen.line([(14.5, 3), (14.5, 7.5), (19, 7.5)], ink)
    pen.line([(9.5, 11), (15.5, 11)], ink, 1.3)
    pen.line([(12.5, 14.5), (15.5, 14.5)], ink, 1.3)
    pen.disc(7, 17.5, 5.2, ink)
    pen.line([(7, 15), (7, 20)], deep, 1.6)
    pen.line([(4.5, 17.5), (9.5, 17.5)], deep, 1.6)


def _open_project(pen: _Duo, ink: tuple, glass: tuple, deep: tuple) -> None:
    # A folder with a sheet showing, its front leaf tipped open.
    back = [(3, 6.5), (3, 19.5), (20, 19.5), (20, 8.5), (11.5, 8.5), (9.5, 6), (4, 6)]
    pen.shape(back, fill=glass)
    pen.shape(back, outline=ink)
    pen.box(7, 4, 17, 13, 1, ink)
    pen.line([(9.5, 7), (14.5, 7)], deep, 1.2)
    pen.line([(9.5, 9.5), (13, 9.5)], deep, 1.2)
    pen.shape([(3, 19.5), (6, 11.5), (22, 11.5), (19.5, 19.5)], fill=ink)


def _edit_project(pen: _Duo, ink: tuple, glass: tuple, deep: tuple) -> None:
    # A written sheet, and a pencil across its lower corner.
    sheet = [(4, 3), (16, 3), (16, 21), (4, 21)]
    pen.shape(sheet, fill=glass)
    pen.shape(sheet, outline=ink)
    pen.line([(7, 7.5), (13, 7.5)], ink, 1.3)
    pen.line([(7, 11), (13, 11)], ink, 1.3)
    pen.line([(7, 14.5), (10, 14.5)], ink, 1.3)
    top, tip = (20.5, 9.5), (11.5, 18.5)
    length = math.hypot(tip[0] - top[0], tip[1] - top[1])
    ux, uy = (tip[0] - top[0]) / length, (tip[1] - top[1]) / length
    nx, ny, half = -uy, ux, 2.1
    neck = (tip[0] - ux * 3.2, tip[1] - uy * 3.2)
    body = [(top[0] + nx * half, top[1] + ny * half), (neck[0] + nx * half, neck[1] + ny * half),
            tip, (neck[0] - nx * half, neck[1] - ny * half), (top[0] - nx * half, top[1] - ny * half)]
    # A rim in the tile's own colour keeps the pencil apart from the sheet.
    pen.shape(body, outline=deep, width=2.6)
    pen.shape(body, fill=ink)
    band = (top[0] + ux * 2.4, top[1] + uy * 2.4)
    pen.line([(band[0] + nx * half, band[1] + ny * half),
              (band[0] - nx * half, band[1] - ny * half)], deep, 1.0)


FEATURE_GLYPHS = {
    'new_project': _new_project,
    'open_project': _open_project,
    'edit_project': _edit_project,
}


def _shade(colour: tuple, amount: float) -> tuple:
    return tuple(round(channel * (1 - amount)) for channel in colour)


def _towards(colour: tuple, other: tuple, amount: float) -> tuple:
    return tuple(round(a + (b - a) * amount) for a, b in zip(colour, other))


def feature_tile(name: str, *, size: int, colour: str, ink: str, background: str, master=None):
    """A استارت action's picture (operator round 2026-09-27): ``name``'s
    two-tone glyph in ``ink`` on a rounded tile shaded from ``colour`` - lit
    at the top left, deeper at the bottom right - with a faint rim of light.
    """

    def build():
        big = size * _SUPERSAMPLE
        hue, light = rgb(colour), rgb(ink)
        lit, deep = _towards(hue, light, 0.05), _shade(hue, 0.42)
        # A small diagonal ramp, stretched: the light falls from the top left.
        steps = 64
        ramp = Image.new('L', (steps, steps))
        ramp.putdata([round(255 * (0.35 * x + 0.65 * y) / (steps - 1))
                      for y in range(steps) for x in range(steps)])
        ramp = ramp.resize((big, big), Image.BILINEAR)
        face = Image.composite(Image.new('RGBA', (big, big), deep + (255,)),
                               Image.new('RGBA', (big, big), lit + (255,)), ramp)
        mask = Image.new('L', (big, big), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.27, fill=255)
        plate = Image.new('RGBA', (big, big), rgb(background) + (255,))
        plate.paste(face, (0, 0), mask)
        rim = Image.new('RGBA', (big, big), (0, 0, 0, 0))
        edge = _SUPERSAMPLE // 2
        ImageDraw.Draw(rim).rounded_rectangle((edge, edge, big - 1 - edge, big - 1 - edge),
                                              radius=big * 0.26, outline=light + (46,),
                                              width=_SUPERSAMPLE)
        plate.alpha_composite(rim)
        inner = round(size * 0.6)
        glyph = Image.new('RGBA', (inner * _SUPERSAMPLE, inner * _SUPERSAMPLE), (0, 0, 0, 0))
        FEATURE_GLYPHS[name](_Duo(ImageDraw.Draw(glyph), inner), light + (255,), light + (64,),
                             _shade(hue, 0.25) + (255,))
        offset = (big - inner * _SUPERSAMPLE) // 2
        plate.alpha_composite(glyph, (offset, offset))
        return plate.resize((size, size), Image.LANCZOS).convert('RGB')

    return _cached(('feature', name, size, colour, ink, background), master, build)


GLASS_MARGIN = 3


def glass_tile(name: str, *, size: int, colour: str, ink: str, background: str,
               shadow: str, master=None):
    """A glassy, raised tile (operator round 2026-09-27, the rail and the
    dashboard cards): ``name``'s line icon in ``ink`` on a rounded square of
    ``colour`` that is lit from the top, with a gloss over its upper half, a
    rim of light and a soft ``shadow`` under it. The picture is the tile plus
    GLASS_MARGIN on every side for the shadow."""

    def build():
        from PIL import ImageChops, ImageFilter

        s = _SUPERSAMPLE
        total = size + 2 * GLASS_MARGIN
        big, tile_px = total * s, size * s
        hue, light, dark = rgb(colour), rgb(ink), rgb(shadow)
        out = Image.new('RGBA', (big, big), rgb(background) + (255,))
        radius = tile_px * 0.3
        origin = GLASS_MARGIN * s
        # The shadow falls a little below the tile, softly.
        falloff = Image.new('L', (big, big), 0)
        ImageDraw.Draw(falloff).rounded_rectangle(
            (origin, origin + s * 1.5, origin + tile_px, origin + tile_px + s * 1.5),
            radius=radius, fill=140)
        falloff = falloff.filter(ImageFilter.GaussianBlur(s * 1.6))
        out.paste(Image.new('RGBA', (big, big), dark + (255,)), (0, 0), falloff)
        # The face: lit at the top, deeper at the foot.
        shape = Image.new('L', (tile_px, tile_px), 0)
        ImageDraw.Draw(shape).rounded_rectangle((0, 0, tile_px - 1, tile_px - 1), radius=radius, fill=255)
        ramp = Image.linear_gradient('L').resize((tile_px, tile_px))
        face = Image.composite(Image.new('RGBA', (tile_px, tile_px), _shade(hue, 0.30) + (255,)),
                               Image.new('RGBA', (tile_px, tile_px), _towards(hue, light, 0.18) + (255,)),
                               ramp)
        tile = Image.new('RGBA', (tile_px, tile_px), (0, 0, 0, 0))
        tile.paste(face, (0, 0), shape)
        # Gloss over the upper half, fading downwards.
        gloss_shape = Image.new('L', (tile_px, tile_px), 0)
        ImageDraw.Draw(gloss_shape).rounded_rectangle(
            (s, s, tile_px - 1 - s, int(tile_px * 0.52)), radius=tile_px * 0.26, fill=255)
        fade = ramp.point(lambda v: max(0, 255 - v * 2))
        gloss_alpha = ImageChops.multiply(gloss_shape, fade).point(lambda v: int(v * 0.42))
        gloss = Image.new('RGBA', (tile_px, tile_px), light + (0,))
        gloss.putalpha(gloss_alpha)
        tile.alpha_composite(gloss)
        # A rim of light along the top edge.
        rim = Image.new('RGBA', (tile_px, tile_px), (0, 0, 0, 0))
        ImageDraw.Draw(rim).rounded_rectangle((0, 0, tile_px - 1, tile_px - 1), radius=radius,
                                              outline=light + (70,), width=s)
        rim.putalpha(ImageChops.multiply(rim.getchannel('A'), ramp.point(lambda v: 255 - v)))
        tile.alpha_composite(rim)
        out.alpha_composite(tile, (origin, origin))
        # The glyph, with a small shadow of its own so it sits on the glass.
        glyph_px = int(size * 0.6) * s
        glyph = render(name, size=glyph_px, colour=ink, background=None, weight=1.25)
        under = render(name, size=glyph_px, colour=shadow, background=None, weight=1.25)
        under.putalpha(under.getchannel('A').point(lambda v: int(v * 0.45)))
        offset = origin + (tile_px - glyph_px) // 2
        out.alpha_composite(under, (offset, offset + s))
        out.alpha_composite(glyph, (offset, offset))
        return out.resize((total, total), Image.LANCZOS).convert('RGB')

    return _cached(('glass', name, size, colour, ink, background, shadow), master, build)


def clear_cache() -> None:
    _cache.clear()
