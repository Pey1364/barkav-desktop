"""Artwork pipeline - the product's answer to "Tkinter has no transparency".

Tk cannot composite a widget over its backdrop, but it can display a flat
image.  So the compositing happens here, in Pillow, against the theme colour
the art will actually sit on.  Because those backdrops are solid, the result
is arithmetically identical to real alpha - and it buys soft edges, glows and
shadows that ttk styling cannot express at all.

The source art arrives without an alpha channel (baked onto flat navy or
white), so each loader keys its own backdrop out first.  Keying uses a ramp
rather than a threshold: a hard cut clips the glow around the icons and
leaves a halo.

Every result is cached and kept referenced, because Tk drops a PhotoImage the
moment Python stops holding it.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageOps

ASSETS = Path(__file__).resolve().parent.parent / 'assets'

NAV_ICONS = ASSETS / 'nav_icons_3d.png'
LOGO = ASSETS / 'logo_barkav.png'
CONSTRUCTION_WATERMARK = ASSETS / 'watermark_construction.png'
UI_ICON_REFERENCES = ASSETS / 'ui_icons_187'

# The supplied dashboard reference is a five-card strip.  These crops contain
# only the visual mark at the left side of each card (no Persian title/value).
_DASHBOARD_REFERENCE_CROPS = {
    'calendar': (15, 120, 160, 285),
    'sales': (610, 120, 775, 285),
    'loans': (1230, 120, 1470, 285),
    'checks': (1750, 120, 2080, 285),
    'transactions': (2330, 120, 2630, 285),
}
_SHELL_REFERENCE_CROPS = {
    'file': ('file_reference.jfif', (250, 320, 710, 810)),
    'messages': ('messages_reference.jfif', (95, 275, 865, 1170)),
}

# Sprite order in nav_icons_3d.png, read left-to-right, top row first.
NAV_ICON_ORDER = (
    'داشبورد', 'ثبت دیتا', 'تراکنش‌ها',
    'درآمد', 'مدیریت پروژه', 'حساب مدیر',
)
NAV_ICON_GRID = (3, 2)

# The 3D sheet holds exactly the six original tabs.  Tabs added since have no
# artwork in that style yet, so they fall back to the older flat icons at the
# same size - visibly plainer, but not a broken glyph.
NAV_ICON_FALLBACKS = {
    'پیمانکاران': 'nav_market.png',
}

# Darkness below this is treated as background rather than ink; it clears the
# checkerboard some exported artwork carries in place of an alpha channel.
CHECKERBOARD_FLOOR = 24

_cache: dict[tuple, object] = {}
_cache_interpreters: set[int] = set()


def rgb(value: str) -> tuple[int, int, int]:
    text = str(value).lstrip('#')
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _ramp(mask: Image.Image, floor: int, gain: float) -> Image.Image:
    """Turn a difference mask into alpha: 0 below floor, then a soft ramp."""

    return mask.point(lambda v: 0 if v < floor else min(255, int((v - floor) * gain)))


def key_flat_backdrop(image: Image.Image, *, floor: int = 12, gain: float = 6.0) -> Image.Image:
    """Drop the solid colour the art was baked onto, keeping soft edges."""

    art = image.convert('RGB')
    backdrop = Image.new('RGB', art.size, art.getpixel((3, 3)))
    mask = ImageChops.difference(art, backdrop).convert('L')
    out = art.convert('RGBA')
    out.putalpha(_ramp(mask, floor, gain))
    return out


def key_white_backdrop(image: Image.Image, *, floor: int = 6, gain: float = 3.0) -> Image.Image:
    """Alpha from darkness - for line art and logos drawn on white."""

    art = image.convert('RGB')
    darkness = ImageOps.invert(art.convert('L'))
    out = art.convert('RGBA')
    out.putalpha(_ramp(darkness, floor, gain))
    return out


def tint(rgba: Image.Image, colour: str) -> Image.Image:
    """Replace hue while keeping the alpha shape."""

    solid = Image.new('RGBA', rgba.size, rgb(colour) + (255,))
    solid.putalpha(rgba.getchannel('A'))
    return solid


def _flatten(rgba: Image.Image, background: str) -> Image.Image:
    plate = Image.new('RGBA', rgba.size, rgb(background) + (255,))
    plate.alpha_composite(rgba)
    return plate.convert('RGB')


def _cached_photo(master, key: tuple):
    import tkinter as tk
    owner = master if master is not None else tk._default_root
    if owner is None:
        return None
    return _cache.get((id(owner.tk),) + key)


def _photo(image: Image.Image, master, key: tuple):
    import tkinter as tk
    from PIL import ImageTk
    photo = ImageTk.PhotoImage(image, master=master)
    interpreter = id(photo.tk)
    _cache[(interpreter,) + key] = photo
    if interpreter not in _cache_interpreters:
        owner = master if master is not None else tk._default_root
        root = owner._root()
        root_path = str(root)
        def release(event):
            if str(event.widget) != root_path:
                return
            for image_key in list(_cache):
                if image_key[0] == interpreter:
                    _cache.pop(image_key, None)
            _cache_interpreters.discard(interpreter)
        root.bind('<Destroy>', release, add='+')
        _cache_interpreters.add(interpreter)
    return photo


def _bright_ink(image: Image.Image, *, floor: int = 92) -> Image.Image:
    """Keep the supplied cyan/white line work and drop its dark screenshot plate."""

    rgba = image.convert('RGBA')
    light = rgba.convert('L')
    alpha = light.point(lambda value: 0 if value < floor else min(255, (value - floor) * 4))
    rgba.putalpha(alpha)
    return rgba


def _cyan_ink(image: Image.Image) -> Image.Image:
    """Keep cyan dashboard artwork while dropping white card borders/text."""

    rgba = image.convert('RGBA')
    red, green, blue, alpha = rgba.split()
    cyan = ImageChops.lighter(ImageChops.subtract(green, red), ImageChops.subtract(blue, red))
    # Keep the source line work crisp: a modest threshold removes JPEG haze
    # while retaining the complete cyan mark.
    cyan = cyan.point(lambda value: 0 if value < 42 else min(255, (value - 42) * 10))
    rgba.putalpha(ImageChops.multiply(alpha, cyan))
    return rgba


def _trim_transparent(image: Image.Image, *, padding: int = 4) -> Image.Image:
    """Discard the empty screenshot margin after the dark plate has been keyed out."""

    box = image.getchannel('A').getbbox()
    if box is None:
        return image
    left, top, right, bottom = box
    return image.crop((max(0, left - padding), max(0, top - padding),
                       min(image.width, right + padding), min(image.height, bottom + padding)))


def dashboard_reference_icon(kind: str, *, size: int, background: str, master=None):
    """Render one of the five user-supplied dashboard icons on a theme surface."""

    key = ('dashboard-reference', kind, int(size), background)
    cached = _cached_photo(master, key)
    if cached is not None:
        return cached
    bounds = _DASHBOARD_REFERENCE_CROPS.get(kind)
    source = UI_ICON_REFERENCES / 'dashboard_cards_reference.jfif'
    if bounds is None or not source.is_file():
        return None
    try:
        cropped = Image.open(source).crop(bounds)
        # The first three source icons do not cross a card boundary.  The two
        # right-most icons need cyan-only filtering to remove that boundary.
        keyed = _cyan_ink(cropped) if kind in {'checks', 'transactions'} else _bright_ink(cropped)
        icon = _trim_transparent(keyed)
        icon.thumbnail((int(size), int(size)), Image.LANCZOS)
        return _photo(_flatten(icon, background), master, key)
    except OSError:
        return None


def shell_reference_icon(kind: str, *, size: int, background: str, master=None):
    """Render the supplied File or Messages mark without its photographed plate."""

    key = ('shell-reference', kind, int(size), background)
    cached = _cached_photo(master, key)
    if cached is not None:
        return cached
    spec = _SHELL_REFERENCE_CROPS.get(kind)
    if spec is None:
        return None
    filename, bounds = spec
    source = UI_ICON_REFERENCES / filename
    if not source.is_file():
        return None
    try:
        icon = _trim_transparent(_bright_ink(Image.open(source).crop(bounds)))
        icon.thumbnail((int(size), int(size)), Image.LANCZOS)
        # Shell controls use a square image plate.  Padding the supplied file
        # art to that same plate makes it exactly match Save/Undo/Redo.
        box = max(1, int(size) + 6)
        plate = Image.new('RGBA', (box, box), (0, 0, 0, 0))
        plate.alpha_composite(icon, ((box - icon.width) // 2, (box - icon.height) // 2))
        return _photo(_flatten(plate, background), master, key)
    except OSError:
        return None


def nav_icon(label: str, *, size: int, background: str, master=None):
    """One 3D rail icon, composited onto the tile colour it will sit on."""

    key = ('nav', label, size, background)
    cached = _cached_photo(master, key)
    if cached is not None:
        return cached
    if label not in NAV_ICON_ORDER:
        spare = NAV_ICON_FALLBACKS.get(label)
        if not spare or not (ASSETS / spare).is_file():
            return None
        icon = Image.open(ASSETS / spare).convert('RGBA')
        if icon.getchannel('A').getextrema()[0] == 255:   # opaque art on a plate
            icon = key_flat_backdrop(icon)
        icon.thumbnail((size, size), Image.LANCZOS)
        return _photo(_flatten(icon, background), master, key)
    if not NAV_ICONS.is_file():
        return None
    sheet = Image.open(NAV_ICONS)
    columns, rows = NAV_ICON_GRID
    cell_w, cell_h = sheet.width // columns, sheet.height // rows
    index = NAV_ICON_ORDER.index(label)
    row, column = divmod(index, columns)
    cell = sheet.crop((column * cell_w, row * cell_h,
                       (column + 1) * cell_w, (row + 1) * cell_h))
    icon = key_flat_backdrop(cell)
    icon.thumbnail((size, size), Image.LANCZOS)
    return _photo(_flatten(icon, background), master, key)


def _ink_bands(image: Image.Image, *, threshold: int = 200) -> list[tuple[int, int]]:
    """Row ranges that contain ink, top to bottom - one per line of artwork."""

    grey = image.convert('L')
    bands: list[tuple[int, int]] = []
    start = None
    for y in range(grey.height):
        row = grey.crop((0, y, grey.width, y + 1))
        has_ink = row.getextrema()[0] < threshold
        if has_ink and start is None:
            start = y
        elif not has_ink and start is not None:
            bands.append((start, y))
            start = None
    if start is not None:
        bands.append((start, grey.height))
    return bands


def _ink_span(image: Image.Image, *, threshold: int = 200) -> tuple[int, int] | None:
    """First and last column that carry ink, for aligning two lines of art."""

    grey = image.convert('L')
    columns = [x for x in range(grey.width)
               if grey.crop((x, 0, x + 1, grey.height)).getextrema()[0] < threshold]
    return (columns[0], columns[-1]) if columns else None


def _letter_runs(image: Image.Image, *, threshold: int = 200) -> list[tuple[int, int]]:
    """Column ranges that carry ink, one per letter."""

    grey = image.convert('L')
    runs: list[tuple[int, int]] = []
    start = None
    for x in range(grey.width):
        has_ink = grey.crop((x, 0, x + 1, grey.height)).getextrema()[0] < threshold
        if has_ink and start is None:
            start = x
        elif not has_ink and start is not None:
            runs.append((start, x))
            start = None
    if start is not None:
        runs.append((start, grey.width))
    return runs


def tighten_tracking(image: Image.Image, ratio: float = 0.5) -> Image.Image:
    """Close the gaps between letters without changing the letters.

    The wordmark is widely letter-spaced artwork, not live text, so tracking
    can only be changed by cutting the letters apart and re-seating them.
    Scaling the whole line horizontally would squash the glyphs instead.
    """

    runs = _letter_runs(image)
    if len(runs) < 2:
        return image
    gaps = [runs[i + 1][0] - runs[i][1] for i in range(len(runs) - 1)]
    width = (runs[-1][1] - runs[0][0]) - sum(round(g * (1 - ratio)) for g in gaps)
    out = Image.new('RGB', (max(1, width), image.height), image.getpixel((0, 0)))
    x = 0
    for index, (left, right) in enumerate(runs):
        out.paste(image.crop((left, 0, right, image.height)), (x, 0))
        x += right - left
        if index < len(gaps):
            x += round(gaps[index] * ratio)
    return out


def logo(*, height: int, background: str, colour: str, master=None,
         drop_tagline: bool = True, wordmark_scale: float = 1.0,
         align_wordmark: bool = False, transparent: bool = False):
    """The BARKAV mark, recoloured for the active theme.

    The supplied artwork is three stacked lines - the Persian mark, the Latin
    name, then an English tagline.  The tagline is dropped by finding the ink
    bands rather than by a hard-coded crop, so replacing the file with another
    three-line logo still works.

    ``wordmark_scale`` enlarges the Latin line alone, relative to the Persian
    mark above it.
    """

    key = ('logo', height, background, colour, drop_tagline,
           round(wordmark_scale, 2), align_wordmark, bool(transparent))
    cached = _cached_photo(master, key)
    if cached is not None:
        return cached
    if not LOGO.is_file():
        return None
    source = Image.open(LOGO).convert('RGB')
    bands = _ink_bands(source)

    if drop_tagline and len(bands) >= 3:
        keep_to = (bands[-2][1] + bands[-1][0]) // 2
        source = source.crop((0, 0, source.width, keep_to))
        bands = bands[:-1]

    if wordmark_scale != 1.0 and len(bands) >= 2:
        # Enlarge only the Latin wordmark.  The two/three lines are separate
        # pieces of art, so they are cut apart, the wordmark is scaled, and
        # the set is re-stacked centred - scaling the whole image would grow
        # all of it, tagline included.
        gap = max(2, bands[1][0] - bands[0][1])
        mark = source.crop((0, bands[0][0], source.width, bands[0][1]))
        word = source.crop((0, bands[1][0], source.width, bands[1][1]))
        word = word.resize(
            (max(1, int(word.width * wordmark_scale)),
             max(1, int(word.height * wordmark_scale))), Image.LANCZOS)
        if align_wordmark:
            word = tighten_tracking(word, 0.5)
        # The tagline's own ink is naturally about the same height as the
        # wordmark's - left alone it would not read as smaller once the
        # wordmark above it is enlarged, so it gets its own, deliberately
        # smaller scale rather than just being carried over at native size.
        tagline = None
        if not drop_tagline and len(bands) >= 3:
            tagline = source.crop((0, bands[2][0], source.width, bands[2][1]))
            tagline_height = max(1, int(word.height * 0.55))
            tagline = tagline.resize(
                (max(1, int(tagline.width * tagline_height / tagline.height)), tagline_height),
                Image.LANCZOS)
            if align_wordmark:
                tagline = tighten_tracking(tagline, 0.5)
        canvas_width = max(mark.width, word.width, tagline.width if tagline else 0)
        tagline_gap = max(2, gap // 2)
        canvas_height = mark.height + gap + word.height + (
            tagline_gap + tagline.height if tagline else 0)
        stacked = Image.new('RGB', (canvas_width, canvas_height), source.getpixel((3, 3)))
        mark_x = (canvas_width - mark.width) // 2
        word_x = (canvas_width - word.width) // 2
        if align_wordmark:
            # Line the two up by their left edges only. Centring them looked
            # balanced on paper but left the Latin line hanging past the mark
            # on both sides once it was enlarged.
            mark_span = _ink_span(mark)
            word_span = _ink_span(word)
            if mark_span and word_span:
                word_x = mark_x + mark_span[0] - word_span[0]
        stacked.paste(mark, (mark_x, 0))
        stacked.paste(word, (word_x, mark.height + gap))
        if tagline is not None:
            tagline_x = word_x
            if align_wordmark:
                word_span = _ink_span(word)
                tagline_span = _ink_span(tagline)
                if word_span and tagline_span:
                    tagline_x = word_x + word_span[0] - tagline_span[0]
            stacked.paste(tagline, (tagline_x, mark.height + gap + word.height + tagline_gap))
        source = stacked

    # The supplied artwork has a transparency checkerboard baked into it as
    # real pixels - light greys between levels 244 and 255, while the ink sits
    # below 200. A low floor treated that pattern as faint ink and it showed
    # as a box around the mark, so the floor clears the checker outright.
    art = tint(key_white_backdrop(source, floor=CHECKERBOARD_FLOOR, gain=6.0), colour)
    ratio = height / art.height
    art = art.resize((max(1, int(art.width * ratio)), height), Image.LANCZOS)
    # Transparent output is used by non-interactive overlays such as a
    # watermark - keeping alpha here prevents a rectangular background plate
    # from hiding whatever sits beneath the decorative mark.
    return _photo(art if transparent else _flatten(art, background), master, key)


def construction_watermark(*, max_width: int, max_height: int, background: str,
                           colour: str, transparent: bool = False, master=None):
    """The crane/building blueprint mark, cropped to its own ink and scaled to
    fit inside ``max_width`` x ``max_height`` without spilling past either.

    Same white-backdrop keying as ``logo()`` - the supplied art is plain line
    work on white, no checkerboard to clear, so the default ``key_white_backdrop``
    floor is enough.
    """

    key = ('construction_watermark', max_width, max_height, background, colour,
           bool(transparent))
    cached = _cached_photo(master, key)
    if cached is not None:
        return cached
    if not CONSTRUCTION_WATERMARK.is_file():
        return None
    source = Image.open(CONSTRUCTION_WATERMARK).convert('RGB')
    bands = _ink_bands(source)
    span = _ink_span(source)
    if not bands or not span:
        return None
    top = bands[0][0]
    bottom = bands[-1][1]
    source = source.crop((span[0], top, span[1], bottom))
    art = tint(key_white_backdrop(source), colour)
    ratio = min(max_width / art.width, max_height / art.height, 1.0)
    art = art.resize((max(1, int(art.width * ratio)), max(1, int(art.height * ratio))),
                      Image.LANCZOS)
    return _photo(art if transparent else _flatten(art, background), master, key)


def glyph(character: str, *, size: int, colour: str, background: str,
          family: str = 'Segoe MDL2 Assets', master=None):
    """Render one icon-font character as an image.

    A Tk label draws all of its text at one size, so an icon cannot be larger
    than the label beside it.  Drawing the glyph separately and using it as
    the button's image lifts that limit.
    """

    key = ('glyph', character, size, colour, background, family)
    cached = _cached_photo(master, key)
    if cached is not None:
        return cached
    from PIL import ImageDraw, ImageFont
    for candidate in (rf'C:\Windows\Fonts\{family}.ttf', rf'C:\Windows\Fonts\segmdl2.ttf'):
        try:
            font = ImageFont.truetype(candidate, size)
            break
        except OSError:
            continue
    else:
        return None
    box = max(size + 6, 1)
    plate = Image.new('RGB', (box, box), rgb(background))
    draw = ImageDraw.Draw(plate)
    left, top, right, bottom = draw.textbbox((0, 0), character, font=font)
    draw.text(((box - (right - left)) / 2 - left, (box - (bottom - top)) / 2 - top),
              character, font=font, fill=rgb(colour))
    return _photo(plate, master, key)


# Segoe MDL2 Assets private-use codepoints for the small, fixed set of action
# icons a screen needs first.  One font, one stroke weight, already the
# default UI icon font on every supported Windows version - no new asset
# format, license or dependency, and it renders through the same glyph()
# pipeline every other themed icon in the product already uses.
ACTION_ICON_GLYPHS = {
    'add': '',
    'edit': '',
    'delete': '',
}


def action_icon(name: str, *, size: int, colour: str, background: str, master=None):
    """One of the product's named action icons - see ACTION_ICON_GLYPHS.

    Returns ``None`` wherever :func:`glyph` would - a menu or button then
    falls back to its plain text label rather than showing a broken image.
    """

    character = ACTION_ICON_GLYPHS.get(name)
    if character is None:
        raise ValueError(f'Unknown action icon {name!r}; expected one of {sorted(ACTION_ICON_GLYPHS)}')
    return glyph(character, size=size, colour=colour, background=background, master=master)


def clear_cache() -> None:
    """Drop cached images after a theme change so they re-composite."""

    _cache.clear()
