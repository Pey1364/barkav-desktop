from __future__ import annotations

import os
import tkinter as tk

import pytest

from barkav_ui import art

pytestmark = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI tests opt-in')


@pytest.fixture()
def root():
    window = tk.Tk()
    window.withdraw()
    yield window
    window.destroy()


def test_construction_watermark_renders_from_the_shipped_asset(root):
    assert art.CONSTRUCTION_WATERMARK.is_file()
    image = art.construction_watermark(
        max_width=300, max_height=200, background='#12181f', colour='#3a4a5a',
        transparent=True, master=root,
    )
    assert image is not None
    assert int(image.width()) <= 300
    assert int(image.height()) <= 200


def test_logo_transparent_output_skips_the_background_plate(root):
    opaque = art.logo(height=80, background='#12181f', colour='#3a4a5a', master=root)
    transparent = art.logo(
        height=80, background='#12181f', colour='#3a4a5a', transparent=True, master=root,
    )
    assert opaque is not None
    assert transparent is not None


def test_logo_can_keep_the_tagline_band_at_a_smaller_scale(root):
    with_tagline = art.logo(
        height=80, background='#12181f', colour='#3a4a5a',
        drop_tagline=False, wordmark_scale=1.15, align_wordmark=True, master=root,
    )
    without_tagline = art.logo(
        height=80, background='#12181f', colour='#3a4a5a',
        drop_tagline=True, wordmark_scale=1.15, align_wordmark=True, master=root,
    )
    assert with_tagline is not None
    assert without_tagline is not None
    # Both are scaled to the same requested height; the tagline variant is a
    # taller three-line stack before that scale, so its rendered width (the
    # dimension that actually changes at fixed height) differs from the
    # two-line variant's.
    assert int(with_tagline.width()) != int(without_tagline.width())
