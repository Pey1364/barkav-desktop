"""Generates the Inno Setup wizard images from the app's own logo art.

Reuses barkav_ui.art's real keying/tinting pipeline (the same one the app
itself uses to draw its own logo) instead of re-deriving the checkerboard
removal by hand - so the installer matches the product's actual dark/cyan
look, not an approximation of it. Run once whenever assets/logo_barkav.png
changes; the two output BMPs are committed (BARKAV.iss references them
directly, and Inno Setup's compiler cannot regenerate them itself).

Usage: python tools/make_installer_art.py
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))

from PIL import Image

from barkav_ui.art import LOGO, CHECKERBOARD_FLOOR, _ink_bands, _ink_span, key_white_backdrop, tint, _flatten

BG = '#FFFFFF'
ACCENT = '#1B2A4A'  # سرمه‌ای تیره - dark navy, reads clearly on the white
                    # wizard page background instead of floating as a dark
                    # square/banner on it.

# Inno Setup's documented sizes for WizardStyle=modern.
BANNER_SIZE = (192, 386)
SMALL_SIZE = (55, 58)

OUT_DIR = APP_ROOT / 'assets'


def clean_logo() -> Image.Image:
    """The BARKAV wordmark alone (tagline dropped), cyan-on-transparent."""
    source = Image.open(LOGO).convert('RGB')
    bands = _ink_bands(source)
    if len(bands) >= 3:
        keep_to = (bands[-2][1] + bands[-1][0]) // 2
        source = source.crop((0, 0, source.width, keep_to))
    return tint(key_white_backdrop(source, floor=CHECKERBOARD_FLOOR, gain=6.0), ACCENT)


def mark_only_logo() -> Image.Image:
    """Just the Persian glyph mark (the artwork's first ink band) - for a
    square-ish slot too small to fit the full wordmark legibly."""
    source = Image.open(LOGO).convert('RGB')
    bands = _ink_bands(source)
    top, bottom = bands[0]
    pad = max(1, (bottom - top) // 6)
    mark = source.crop((0, max(0, top - pad), source.width, min(source.height, bottom + pad)))
    span = _ink_span(mark)
    if span:
        left, right = span
        pad_x = max(1, (right - left) // 10)
        mark = mark.crop((max(0, left - pad_x), 0, min(mark.width, right + pad_x), mark.height))
    return tint(key_white_backdrop(mark, floor=CHECKERBOARD_FLOOR, gain=6.0), ACCENT)


def make_banner(logo: Image.Image) -> Image.Image:
    # Maximize within the banner on whichever axis binds first (margin=12px)
    # rather than a fixed width fraction - modern-style banners only show on
    # the welcome/finished pages, which read top-to-bottom, so a centred
    # mark reads as a title card.
    margin = 12
    max_w, max_h = BANNER_SIZE[0] - margin, BANNER_SIZE[1] - margin
    ratio = min(max_w / logo.width, max_h / logo.height)
    resized = logo.resize((max(1, int(logo.width * ratio)), max(1, int(logo.height * ratio))), Image.LANCZOS)
    x = (BANNER_SIZE[0] - resized.width) // 2
    y = BANNER_SIZE[1] // 3 - resized.height // 2
    plate = Image.new('RGBA', BANNER_SIZE, (*_hex(BG), 255))
    plate.alpha_composite(resized, (x, y))
    return plate.convert('RGB')


def make_small(mark: Image.Image) -> Image.Image:
    canvas = Image.new('RGBA', SMALL_SIZE, (*_hex(BG), 255))
    margin = 4
    max_w, max_h = SMALL_SIZE[0] - margin, SMALL_SIZE[1] - margin
    ratio = min(max_w / mark.width, max_h / mark.height)
    resized = mark.resize((max(1, int(mark.width * ratio)), max(1, int(mark.height * ratio))), Image.LANCZOS)
    x = (SMALL_SIZE[0] - resized.width) // 2
    y = (SMALL_SIZE[1] - resized.height) // 2
    canvas.alpha_composite(resized, (x, y))
    return canvas.convert('RGB')


def _hex(colour: str) -> tuple[int, int, int]:
    text = colour.lstrip('#')
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def main() -> None:
    if not LOGO.is_file():
        raise SystemExit(f'Logo not found: {LOGO}')
    banner = make_banner(clean_logo())
    small = make_small(mark_only_logo())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    banner.save(OUT_DIR / 'installer_banner.bmp')
    small.save(OUT_DIR / 'installer_small.bmp')
    print(f'Wrote {OUT_DIR / "installer_banner.bmp"} {banner.size}')
    print(f'Wrote {OUT_DIR / "installer_small.bmp"} {small.size}')


if __name__ == '__main__':
    main()
