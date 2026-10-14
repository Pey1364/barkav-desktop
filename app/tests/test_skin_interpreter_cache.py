"""Tk images must not be reused across independent window interpreters."""
import tkinter as tk
from barkav_ui import skin


def test_identical_plates_belong_to_their_own_interpreter():
    first = tk.Tk(); first.withdraw()
    second = tk.Tk(); second.withdraw()
    try:
        a = skin._plate('#ffffff', radius=6, master=first, key='cache-regression')
        b = skin._plate('#ffffff', radius=6, master=second, key='cache-regression')
        assert a is not b and a.tk is first.tk and b.tk is second.tk
        assert skin._plate('#ffffff', radius=6, master=first, key='cache-regression') is a
        first.destroy()
        assert not any(k.startswith(f'{id(first.tk)}:') for k in skin._images)
        assert skin._plate('#ffffff', radius=6, master=second, key='cache-regression') is b
    finally:
        try:
            first.destroy()
        except tk.TclError:
            pass
        second.destroy()


def test_logo_cache_survives_independent_root_destruction(tmp_path, monkeypatch):
    from PIL import Image
    from barkav_ui import art
    source = tmp_path / 'public-test-logo.png'
    image = Image.new('RGB', (12, 12), 'white')
    image.putpixel((5, 5), (0, 0, 0))
    image.save(source)
    monkeypatch.setattr(art, 'LOGO', source)
    first = tk.Tk(); first.withdraw()
    second = tk.Tk(); second.withdraw()
    args = dict(height=24, background='#ffffff', colour='#000000')
    try:
        a = art.logo(master=first, **args)
        b = art.logo(master=second, **args)
        assert a is not b and a.tk is first.tk and b.tk is second.tk
        assert art.logo(master=first, **args) is a
        first.destroy()
        assert not any(k[0] == id(first.tk) for k in art._cache)
        assert art.logo(master=second, **args) is b
        label = tk.Label(second, image=b)
        label.pack()
        second.update_idletasks()
        assert label.winfo_exists()
    finally:
        try: first.destroy()
        except tk.TclError: pass
        second.destroy()


def test_missing_art_does_not_create_a_default_root(tmp_path, monkeypatch):
    from barkav_ui import art
    monkeypatch.setattr(art, 'LOGO', tmp_path / 'missing-public-logo.png')
    before = tk._default_root
    assert art.logo(height=24, background='#ffffff', colour='#000000') is None
    assert tk._default_root is before


def _overlay_photos(master):
    """One of each kind of photo the row overlay builds: a tick, the four
    corners of a selection outline, and the empty-state icon."""
    from barkav_ui import row_overlay
    palette = {'accent': '#3366cc', 'text_secondary': '#667788', 'bg': '#101820',
               'on_accent': '#ffffff'}
    return [
        row_overlay._checkbox_image(True, 16, '#ffffff', palette, master),
        *row_overlay._corner_images('#3366cc', '#ffffff', 6, 2, master),
        row_overlay._ring_icon('inbox', ring='#ccddee', colour='#3366cc',
                               background='#ffffff', master=master),
    ]


def test_row_overlay_photos_belong_to_their_own_interpreter():
    from barkav_ui import row_overlay
    first = tk.Tk(); first.withdraw()
    second = tk.Tk(); second.withdraw()
    try:
        a = _overlay_photos(first)
        b = _overlay_photos(second)
        assert all(x is not y and x.tk is first.tk and y.tk is second.tk for x, y in zip(a, b))
        assert all(x is y for x, y in zip(_overlay_photos(first), a))
        assert any(k[0] == id(first.tk) for k in row_overlay._images)
        first.destroy()
        assert not any(k[0] == id(first.tk) for k in row_overlay._images)
        assert all(x is y for x, y in zip(_overlay_photos(second), b))
    finally:
        try:
            first.destroy()
        except tk.TclError:
            pass
        second.destroy()
    assert not any(k[0] in (id(first.tk), id(second.tk)) for k in row_overlay._images)


def test_row_overlay_gives_a_new_root_no_photo_of_a_destroyed_one():
    """The first window's photos used to be handed to every window built after
    it, where the tick plates and status stripes then failed to paint."""
    first = tk.Tk(); first.withdraw()
    try:
        _overlay_photos(first)
    finally:
        first.destroy()
    second = tk.Tk(); second.withdraw()
    try:
        for photo in _overlay_photos(second):
            assert photo.tk is second.tk
            tk.Label(second, image=photo).pack()
        second.update_idletasks()
    finally:
        second.destroy()
