"""Rounded ttk skin - contract sections 3, 4, 6 and 9.

ttk's built-in themes draw square, flat widgets; the reference design is
rounded.  Rather than replace each widget with a hand-drawn Canvas, this
renders the rounded plates once in Pillow and registers them as ttk *image
elements*, then re-lays the standard widget layouts on top of them.

That is what makes the rounding systemic: every ``ttk.Button``, ``Entry``,
``Combobox`` and notebook tab in the product picks it up, including the ones
inherited screens create, and changing the radius or a colour here changes
all of them at once.

Plates are drawn at 4x and downsampled so the corners are antialiased, which
Canvas arcs are not.  ``border=radius`` tells Tk to stretch only the middle
of each plate, so one small image skins a button of any width.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw

from .art import rgb

_SUPERSAMPLE = 4
_PLATE = 48                     # nominal plate size before stretching
# Geometry decision 1.3 / 3.2: controls are short pills.  The height is fixed
# here because the radius must be exactly half of it for the caps to be
# semicircles rather than squashed arcs.
PILL_HEIGHT = 28
# Every action button in the content area shares one height (operator-
# approved N7). Fields, tabs and the shell bars keep PILL_HEIGHT: forms and
# tab strips sized around 28px stay exactly as tall as they were.
# 32 -> 24 (operator round 2026-09-27: button rows 25% lower, the buttons
# smaller than the tab titles).
BUTTON_HEIGHT = 24
_COMPACT_BUTTON_ROLES = {'Shell.TButton', 'Footer.TButton'}
# A two-line readout - the footer clock - needs more room than a button.
PILL_TALL_HEIGHT = 42
SCROLLBAR_THICKNESS = 14
_images: dict[str, object] = {}  # Tk drops unreferenced PhotoImages

# Section 6: the semantic button roles - fill colour, label colour, and the
# surface the control sits on.
#
# That third value matters more than it looks.  A pill has transparent
# corners, and ttk paints the style's ``background`` behind the image, so a
# button whose background does not match its parent shows those corners as a
# rectangle - most visibly on hover, where the plate changes but the corners
# do not.  Naming the parent surface per role is what removes it.
BUTTON_ROLES = {
    'Primary.TButton':  ('info', 'on_accent', 'panel'),
    'Success.TButton':  ('success', 'on_accent', 'panel'),
    'Warning.TButton':  ('warning', 'on_warning', 'panel'),
    'Danger.TButton':   ('danger', 'on_accent', 'panel'),
    # 'glass' on 'panel' sat only 2/255 apart per channel in theme 2 - the
    # same near-invisible pairing ProjectSummary.TButton below was split off
    # to fix, except this shared role still backs every ordinary toolbar
    # button (ثبت دیتا's افزودن/ویرایش/حذف/کپی and dozens more). 'tab_inactive'
    # is the same fill already proven visible for that exact pairing.
    'Toolbar.TButton':  ('tab_inactive', 'text_primary', 'panel'),
    'Ghost.TButton':    ('panel', 'text_primary', 'surface_alt'),
    'TButton':          ('glass', 'text_primary', 'panel'),
    # The shell bars use their own surfaces.
    'Shell.TButton':    ('glass', 'text_primary', 'surface'),
    'Footer.TButton':   ('glass', 'text_primary', 'surface_alt'),
    # Tabs are raised rounded rectangles, not action-button pills.  The
    # inactive plate is one elevation above the strip/window surface.
    # One tab look everywhere (operator request, 2026-09-27): the window
    # tabs, every tab strip and the rail share it - an unselected tab sits
    # flush with its strip, the selected one is the rail's soft accent pill,
    # and the text colour never changes with selection.
    'Tab.TButton':      ('surface_alt', 'text_primary', 'surface_alt'),
    'TabActive.TButton': ('tab_selected_fill', 'text_primary', 'surface_alt'),
    'Subtab.TButton':   ('surface_alt', 'text_primary', 'surface_alt'),
    'SubtabActive.TButton': ('tab_selected_fill', 'text_primary', 'surface_alt'),
    'TabSelected.TButton': ('tab_selected_fill', 'text_primary', 'surface_alt'),
    'TabUnselected.TButton': ('surface_alt', 'text_primary', 'surface_alt'),
    # The دشبورد window's own استارت/پروژه tabs (dashboard_stage18_7's
    # window-tabs row) - two roles of their own rather than reusing
    # TabSelected/TabUnselected, whose relative prominence is backwards
    # for this one: 'raised' (TabSelected's plate) sits almost flush with
    # the header's own surface_alt background, while 'tab_inactive'
    # (TabUnselected's plate) is the more visibly-gray, standing-out one -
    # fine for a strip that lives *inside* a page, wrong for a toggle that
    # has to read as "this one is active" at a glance. Selected gets the
    # gray plate instead, unselected recedes into the header.
    'WindowTabSelected.TButton': ('tab_selected_fill', 'text_primary', 'surface_alt'),
    'WindowTabUnselected.TButton': ('surface_alt', 'text_primary', 'surface_alt'),
    # Semantic aliases retain the Claude token names: ('tab_indicator',) and ('tab_indicator_inactive',).
    # DataTable actions use their own neutral gray role.
    'TableToolbar.TButton': ('toolbar_fill', 'text_primary', 'panel'),
    # The overview's "مشخصات پروژه" button sits on the rounded project card
    # (parent surface 'panel', equal to 'card').  'glass' is only 2/255 per
    # channel away from that in the dark theme, so Toolbar.TButton's pill
    # was there but effectively invisible; 'tab_inactive' is the same fill
    # already proven visible for the tab strip and reads as a clear pill here.
    'ProjectSummary.TButton': ('tab_inactive', 'text_primary', 'panel'),
}


# Claude Bot3's rounded-rectangle tab contract; keep the active gray roles above.
ROUNDED_RECT_ROLES = {
    'TabSelected.TButton', 'TabUnselected.TButton',
    'WindowTabSelected.TButton', 'WindowTabUnselected.TButton',
}


_cache_interpreters: set[int] = set()


def _image_cache_key(master, key: str) -> str:
    """Images belong to one Tcl interpreter, even when their colors match."""
    master = master if master is not None else tk._get_default_root()
    interpreter = id(master.tk)
    prefix = f'{interpreter}:'
    if interpreter not in _cache_interpreters:
        root = master._root()
        root_path = str(root)
        def release(event):
            if str(event.widget) != root_path:
                return
            for image_key in list(_images):
                if image_key.startswith(prefix):
                    _images.pop(image_key, None)
            _cache_interpreters.discard(interpreter)
        root.bind('<Destroy>', release, add='+')
        _cache_interpreters.add(interpreter)
    return prefix + key


def _plate(fill: str, *, radius: int, border: str | None = None,
           border_width: int = 1, master=None, key: str = '',
           height: int | None = None,
           corners: tuple[bool, bool, bool, bool] | None = None):
    """One antialiased rounded rectangle, cached and kept referenced.

    ``height`` renders a shorter plate for pill shapes, where the radius is
    half the control height and only the horizontal middle may stretch.
    ``corners`` (top-left, top-right, bottom-right, bottom-left) rounds only
    the given corners instead of all four.
    """

    key = _image_cache_key(master, key)
    if key in _images:
        return _images[key]
    scale = _SUPERSAMPLE
    width = _PLATE * scale
    tall = (height or _PLATE) * scale
    image = Image.new('RGBA', (width, tall), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, width - 1, tall - 1), radius=radius * scale,
        fill=rgb(fill) + (255,),
        outline=(rgb(border) + (255,)) if border else None,
        width=border_width * scale if border else 0,
        corners=corners,
    )
    image = image.resize((_PLATE, height or _PLATE), Image.LANCZOS)
    from PIL import ImageTk
    photo = ImageTk.PhotoImage(image, master=master)
    _images[key] = photo
    return photo


def _arrow_plate(palette: dict[str, str], *, radius: int, master, key: str):
    """The combobox drop-arrow, on its own rounded plate.

    clam draws the arrow flat against the field, which read as a hole at the
    end of the control. Giving it a plate of its own makes it look like the
    button it behaves as.
    """

    key = _image_cache_key(master, key)
    if key in _images:
        return _images[key]
    scale = _SUPERSAMPLE
    width, height = 26 * scale, PILL_HEIGHT * scale
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # The arrow is integrated into the field instead of sitting on a second
    # button-like tile (the old shuttered/segmented look).
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius * scale,
                           fill=rgb(palette['input']) + (255,))
    mid_x, mid_y = width // 2, height // 2
    arm = 5 * scale
    draw.polygon(
        [(mid_x - arm, mid_y - arm // 2), (mid_x + arm, mid_y - arm // 2), (mid_x, mid_y + arm)],
        fill=rgb(palette['text_secondary']) + (255,),
    )
    image = image.resize((26, PILL_HEIGHT), Image.LANCZOS)
    from PIL import ImageTk
    photo = ImageTk.PhotoImage(image, master=master)
    _images[key] = photo
    return photo


def _check_plate(fill: str, *, checked: bool, radius: int, mark: str | None,
                 master, key: str, outline: str | None = None):
    """A 20x20 checkbox indicator, rendered at its real size.

    Unlike :func:`_plate`, this is never stretched by ttk's border-slicing,
    so there is no reason to render it at ``_PLATE`` width first - it is
    drawn once at the size it will actually show at.

    With ``outline`` the box is drawn as a ring on a see-through middle -
    the tables' own unticked box - so it reads on whatever it sits on.
    """

    key = _image_cache_key(master, key)
    if key in _images:
        return _images[key]
    scale = _SUPERSAMPLE
    size = 20 * scale
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if outline is not None and not checked:
        inset = scale
        draw.rounded_rectangle((inset, inset, size - 1 - inset, size - 1 - inset),
                               radius=radius * scale, outline=rgb(outline) + (255,),
                               width=max(2, round(1.6 * scale)))
    else:
        draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius * scale,
                               fill=rgb(fill) + (255,))
    if checked and mark:
        pad = size * 0.24
        draw.line(
            [(pad, size * 0.53), (size * 0.42, size - pad), (size - pad, pad * 0.9)],
            fill=rgb(mark) + (255,), width=max(2, round(size * 0.09)), joint='curve',
        )
    image = image.resize((20, 20), Image.LANCZOS)
    from PIL import ImageTk
    photo = ImageTk.PhotoImage(image, master=master)
    _images[key] = photo
    return photo


def _scrollbar_track(
    palette: dict[str, str], *, orientation: str, master, key: str
):
    """Create a track image that gives an arrowless scrollbar real thickness.

    A layout containing only clam's native trough and thumb reports a natural
    size of one pixel after its arrow elements are removed.  Supplying a track
    image keeps the arrowless design while giving Tk a measurable 14px cross
    axis on both orientations.
    """
    key = _image_cache_key(master, key)
    if key in _images:
        return _images[key]
    scale = _SUPERSAMPLE
    if orientation == 'Vertical':
        width, height = SCROLLBAR_THICKNESS * scale, 32 * scale
    else:
        width, height = 32 * scale, SCROLLBAR_THICKNESS * scale
    image = Image.new('RGBA', (width, height), rgb(palette['scroll_track']) + (255,))
    image = image.resize((width // scale, height // scale), Image.LANCZOS)
    from PIL import ImageTk
    photo = ImageTk.PhotoImage(image, master=master)
    _images[key] = photo
    return photo


def _mix(a: str, b: str, ratio: float) -> str:
    from barkav_themes.tokens import mix
    return mix(a, b, ratio)


def install_rounded_skin(style: ttk.Style, palette: dict[str, str],
                         metrics: dict[str, int], master: tk.Misc) -> None:
    """Re-skin ttk buttons, fields and tabs as rounded, themed shapes.

    Safe to call on every restyle: element names are versioned by the values
    they were built from, so a theme change makes new elements rather than
    colliding with the old ones.
    """

    radius = max(4, int(metrics.get('radius', 6)))
    # Keep the toolbar role available across legacy palettes.
    palette.setdefault('toolbar_fill', palette.get('raised', palette.get('panel2', palette['bg'])))
    # Include the semantic tab surfaces in the element token.  Without them,
    # an in-process theme restyle can keep using a previously cached plate,
    # making the inactive/active contrast appear unchanged on screen.
    token = (
        f"{palette['bg']}{palette['accent']}{palette.get('raised', '')}"
        f"{palette.get('tab_inactive', '')}{palette.get('subtab_inactive', '')}"
        f"{radius}"
    ).replace('#', '')

    def element(name: str, fill: str, *, hover: str, pressed: str,
                border: str | None = None, pill: bool = False,
                compact_round: bool = False, radius_override: int | None = None,
                tall: bool = False, focusable: bool = False, padding: int = 0,
                corners: tuple[bool, bool, bool, bool] | None = None,
                pill_height: int | None = None) -> str | None:
        """Create a three-state image element; returns its name or None.

        ``pill`` gives the stadium shape the design calls for: straight top
        and bottom, a semicircular cap at each end.  Only the horizontal
        middle is declared stretchable, so widening a control lengthens the
        straight part instead of flattening its caps.

        ``focusable`` adds a fourth, ``focus``-state plate outlined in the
        theme's ``focus_ring`` token. The token existed in every palette and
        was contract-tested, but nothing ever consumed it: every image
        element here replaces ttk's native focus rectangle with a borderless
        picture, so tabbing through a form gave no visual sign of where
        focus was. Scoped to the field element (Entry/Combobox/Spinbox),
        where a keyboard user actually tabs between controls.
        """
        full = f'{name}{token}'
        pill_height = pill_height or (PILL_TALL_HEIGHT if tall else PILL_HEIGHT)
        height = pill_height if (pill or compact_round) else None
        # Contract reference: height = pill_height if pill else None; compact_round keeps Bot2 field geometry.
        rounding = (
            radius_override if radius_override is not None
            else ((pill_height // 2) if pill else radius)
        )
        edges = (rounding, 0, rounding, 0) if (pill or compact_round) else radius
        def plate(colour, suffix, *, outline=None, outline_width=1):
            return _plate(colour, radius=rounding,
                          border=outline if outline else border,
                          border_width=outline_width if outline else 1,
                          master=master, key=f'{full}{suffix}', height=height,
                          corners=corners)
        states = [
            ('pressed', plate(pressed, 'p')),
            ('active', plate(hover, 'a')),
            ('disabled', plate(palette['disabled_bg'], 'd')),
        ]
        if focusable:
            states.insert(0, ('focus', plate(
                fill, 'f', outline=palette['focus_ring'], outline_width=2)))
        try:
            style.element_create(
                full, 'image', plate(fill, 'n'), *states,
                border=edges, sticky='nsew', padding=padding,
            )
        except tk.TclError:
            return full if full in style.element_names() else None
        return full

    # --- buttons ----------------------------------------------------------
    for name, (fill_key, text_key, parent_key) in BUTTON_ROLES.items():
        fill = palette[fill_key]
        is_tab = name in {
            'Tab.TButton', 'TabActive.TButton',
            'Subtab.TButton', 'SubtabActive.TButton',
            'TabSelected.TButton', 'TabUnselected.TButton',
            'WindowTabSelected.TButton', 'WindowTabUnselected.TButton',
        }
        is_window_tab = name in {
            'WindowTabSelected.TButton', 'WindowTabUnselected.TButton',
        }
        created = element(
            f'{name.replace(".", "")}.plate', fill,
            hover=_mix(fill, palette['text_primary'], 0.12),
            pressed=_mix(fill, palette['shadow'], 0.18),
            border=palette['border_subtle'] if fill_key in ('glass', 'panel') else None,
            pill=not is_tab, compact_round=is_tab,
            radius_override=radius if name in ROUNDED_RECT_ROLES else None,
            corners=(True, True, False, False) if is_window_tab else None,
            pill_height=(BUTTON_HEIGHT if not is_tab and name not in _COMPACT_BUTTON_ROLES
                         else None),
        )
        if not created:
            continue
        try:
            style.layout(name, [(created, {
                'sticky': 'nsew',
                'children': [('Button.padding', {
                    'sticky': 'nsew',
                    'children': [('Button.label', {'sticky': 'nsew'})],
                })],
            })])
            style.configure(name, foreground=palette[text_key],
                            background=palette[parent_key],
                            borderwidth=0, relief='flat',
                            padding=(12, 2) if is_tab else (10, 0),
                            anchor='center', justify='center')
            style.map(
                name,
                foreground=[('disabled', palette['disabled_fg'])],
                # Hold the background steady across states so the pill's
                # transparent corners never reveal a different colour.
                background=[('active', palette[parent_key]),
                            ('pressed', palette[parent_key]),
                            ('disabled', palette[parent_key])],
            )
        except tk.TclError:
            continue

    # --- entry and combobox fields ---------------------------------------
    # Fields keep the compact control height but use a restrained corner
    # radius.  They read as professional rounded rectangles, not pills.
    field = element(
        'BarkavField.plate', palette['input'],
        hover=palette['input'], pressed=palette['input'],
        border=palette['border'], compact_round=True, focusable=True)
    if field:
        try:
            style.layout('TEntry', [(field, {'sticky': 'nsew', 'children': [
                ('Entry.padding', {'sticky': 'nsew', 'children': [
                    ('Entry.textarea', {'sticky': 'nsew'})]})]})])
            style.configure('TEntry', foreground=palette['text_primary'],
                            fieldbackground=palette['input'], background=palette['bg'], borderwidth=0,
                            padding=(10, 2))
            style.map('TEntry', background=[
                ('readonly', palette['bg']), ('disabled', palette['bg'])])
        except tk.TclError:
            pass
        try:
            # RTL: the arrow sits on the left, and it is declared before the
            # text area so it keeps its width instead of being squeezed out.
            style.layout('TCombobox', [(field, {'sticky': 'nsew', 'children': [
                ('Combobox.downarrow', {'side': 'left', 'sticky': 'ns'}),
                ('Combobox.padding', {'sticky': 'nsew', 'children': [
                    ('Combobox.textarea', {'sticky': 'nsew'})]})]})])
            # clam draws its own bevel around the arrow; flattening every
            # edge colour to the field colour is what removes the extra box.
            style.configure('TCombobox', foreground=palette['text_primary'],
                            fieldbackground=palette['input'], background=palette['input'],
                            borderwidth=0, relief='flat', padding=(10, 2),
                            arrowcolor=palette['text_secondary'], arrowsize=13,
                            bordercolor=palette['input'], lightcolor=palette['input'],
                            darkcolor=palette['input'], insertcolor=palette['text_primary'])
            arrow = _arrow_plate(palette, radius=radius, master=master,
                                 key=f'BarkavArrow{token}')
            if arrow is not None:
                try:
                    style.element_create(f'BarkavArrow{token}', 'image', arrow,
                                         border=radius, sticky='ns', padding=0)
                    style.layout('TCombobox', [(field, {'sticky': 'nsew', 'children': [
                        (f'BarkavArrow{token}', {'side': 'left', 'sticky': 'ns'}),
                        ('Combobox.padding', {'sticky': 'nsew', 'children': [
                            ('Combobox.textarea', {'sticky': 'nsew'})]})]})])
                except tk.TclError:
                    pass
            style.map('TCombobox',
                      fieldbackground=[('readonly', palette['input'])],
                      background=[('readonly', palette['input']), ('active', palette['input'])],
                      foreground=[('readonly', palette['text_primary'])])

            # Output format is intentionally a compact rectangular field. It
            # sits beside the pill-shaped خروجی action, so the two controls
            # remain visually distinct while sharing the selected theme.
            output_field = element(
                'BarkavOutputField', palette['panel2'],
                hover=palette['panel2'], pressed=palette['panel2'],
                border=palette['line_soft'], compact_round=True,
                radius_override=0,
            )
            if output_field is not None:
                style.layout('Output.TCombobox', [(output_field, {
                    'sticky': 'nsew', 'children': [
                        ('Combobox.downarrow', {'side': 'left', 'sticky': 'ns'}),
                        ('Combobox.padding', {'sticky': 'nsew', 'children': [
                            ('Combobox.textarea', {'sticky': 'nsew'})]})]})])
                style.configure(
                    'Output.TCombobox', foreground=palette['text_primary'],
                    fieldbackground=palette['panel2'], background=palette['panel2'],
                    borderwidth=0, relief='flat', padding=(10, 2),
                    arrowcolor=palette['text_secondary'], arrowsize=13,
                    bordercolor=palette['panel2'], lightcolor=palette['panel2'],
                    darkcolor=palette['panel2'], insertcolor=palette['text_primary'],
                )
                style.map(
                    'Output.TCombobox',
                    fieldbackground=[('readonly', palette['panel2'])],
                    background=[('readonly', palette['panel2']), ('active', palette['panel2'])],
                    foreground=[('readonly', palette['text_primary'])],
                )
        except tk.TclError:
            pass
        try:
            # A spinbox is an entry with steppers, so it takes the same plate.
            # Left unstyled it kept clam's pale field, and light text on it was
            # unreadable - the value simply could not be seen.
            style.layout('TSpinbox', [(field, {'sticky': 'nsew', 'children': [
                ('Spinbox.uparrow', {'side': 'left', 'sticky': 'n'}),
                ('Spinbox.downarrow', {'side': 'left', 'sticky': 's'}),
                ('Spinbox.padding', {'sticky': 'nsew', 'children': [
                    ('Spinbox.textarea', {'sticky': 'nsew'})]})]})])
            style.configure('TSpinbox', foreground=palette['text_primary'],
                            fieldbackground=palette['input'], background=palette['input'],
                            borderwidth=0, relief='flat', padding=(10, 2),
                            arrowcolor=palette['text_secondary'], arrowsize=11,
                            bordercolor=palette['input'], lightcolor=palette['input'],
                            darkcolor=palette['input'], insertcolor=palette['text_primary'])
            style.map('TSpinbox',
                      fieldbackground=[('readonly', palette['input'])],
                      background=[('readonly', palette['input']), ('active', palette['input'])],
                      foreground=[('readonly', palette['text_primary'])])
        except tk.TclError:
            pass

    # --- checkbox -----------------------------------------------------
    # The one widget install_rounded_skin() never reached: every button,
    # field, scrollbar and tab above picks up the rounded dark skin, but
    # TCheckbutton was left at ttk's stock light/square look - a foreign
    # widget dropped into an otherwise fully re-skinned dark screen.
    check_radius = min(6, radius)
    # Accent, not success-green: the same fill the tables' rendered ticks use
    # (row_overlay), so every checkbox in the product is one control - and
    # green already means "approved" in the status tints.
    r, g, b = rgb(palette['accent'])
    check_mark = (palette['bg'] if (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.5
                  else palette['on_accent'])
    try:
        # Unticked is a ring, not a filled square: the filled one was drawn
        # in 'glass', which on a bar in the page colour was the page colour
        # - the export preview's «نمایش سند» box simply vanished (operator
        # report, 2026-09-27).
        off = _check_plate(palette['glass'], checked=False, radius=check_radius,
                           mark=None, master=master, key=f'BarkavCheckOff{token}',
                           outline=_mix(palette['text_secondary'], palette['panel'], 0.25))
        on = _check_plate(palette['accent'], checked=True, radius=check_radius,
                          mark=check_mark, master=master,
                          key=f'BarkavCheckOn{token}')
        dis = _check_plate(palette['disabled_bg'], checked=False, radius=check_radius,
                           mark=None, master=master, key=f'BarkavCheckDis{token}',
                           outline=palette['disabled_fg'])
        check_name = f'BarkavCheckInd{token}'
        style.element_create(check_name, 'image', off, ('selected', on),
                             ('disabled', dis), width=20, height=20, sticky='')
        style.layout('TCheckbutton', [('Checkbutton.padding', {
            'sticky': 'nsew', 'children': [
                (check_name, {'side': 'right', 'sticky': ''}),
                ('Checkbutton.label', {'side': 'right', 'sticky': 'w'}),
            ],
        })])
        style.configure('TCheckbutton', background=palette['panel'],
                        foreground=palette['text_primary'], padding=(4, 2))
        style.map('TCheckbutton',
                  background=[('active', palette['panel'])],
                  foreground=[('disabled', palette['disabled_fg'])])
    except tk.TclError:
        pass

    # --- notebook client --------------------------------------------------
    # clam draws every notebook's client area with its own built-in
    # bordercolor/lightcolor/darkcolor (a near-white trio) whatever
    # borderwidth says - the pale square frame round every tab page and
    # sub-tab page. A rounded plate in the page's own colour replaces that element,
    # so the frame becomes a soft rounded outline in the theme's border
    # token. The plate's padding insets the pages just enough for its
    # corners to show.
    # The inset must stay close to what clam's own 1-2px border already took:
    # tab pages nest three notebooks deep (main -> مدیریت پروژه -> its
    # sub-tabs), and every extra pixel is height pack() takes from the last
    # non-expanding row of a page - the price-update action bar first. So
    # the main frame gets the full radius on a 3px inset, nested sub-tab
    # frames a smaller radius that clears a 2px one.
    for names, corner, inset in (
        (('TNotebook', 'Hidden.TNotebook'), radius, 3),
        (('BarkavHiddenTabs.TNotebook', 'Barkav.Data.TNotebook'), min(4, radius), 2),
    ):
        client = element(f'BarkavNotebookClient{corner}.plate', palette['bg'],
                         hover=palette['bg'], pressed=palette['bg'],
                         border=palette['border_subtle'], radius_override=corner,
                         padding=inset)
        if not client:
            continue
        for name in names:
            try:
                style.layout(name, [(client, {'sticky': 'nsew'})])
            except tk.TclError:
                continue

    # --- menu buttons -----------------------------------------------------
    # Decision 1.5: the footer controls are pills too.  A Menubutton has its
    # own layout, so it needs the plate applied separately from TButton.
    menu_plate = element(
        'BarkavMenu.plate', palette['glass'],
        hover=_mix(palette['glass'], palette['text_primary'], 0.12),
        pressed=_mix(palette['glass'], palette['shadow'], 0.18),
        border=palette['border_subtle'], pill=True)
    if menu_plate:
        try:
            style.layout('TMenubutton', [(menu_plate, {'sticky': 'nsew', 'children': [
                ('Menubutton.padding', {'sticky': 'nsew', 'children': [
                    ('Menubutton.label', {'sticky': 'nsew'})]})]})])
            style.configure('TMenubutton', foreground=palette['text_primary'],
                            background=palette['surface'], borderwidth=0,
                            relief='flat', padding=(12, 2),
                            anchor='center', justify='center')
            style.map('TMenubutton',
                      background=[('active', palette['surface']),
                                  ('pressed', palette['surface'])])
            style.configure('Footer.TMenubutton', background=palette['surface_alt'])
            style.map('Footer.TMenubutton',
                      background=[('active', palette['surface_alt']),
                                  ('pressed', palette['surface_alt'])])
        except tk.TclError:
            pass
    # The one "خروجی ▾" control that replaced a format dropdown plus a
    # separate export title/button: a toolbar pill at the action height.
    export_plate = element(
        'BarkavExportMenu.plate', palette['tab_inactive'],
        hover=_mix(palette['tab_inactive'], palette['text_primary'], 0.12),
        pressed=_mix(palette['tab_inactive'], palette['shadow'], 0.18),
        pill=True, pill_height=BUTTON_HEIGHT)
    if export_plate:
        try:
            style.layout('Export.TMenubutton', [(export_plate, {'sticky': 'nsew', 'children': [
                ('Menubutton.padding', {'sticky': 'nsew', 'children': [
                    ('Menubutton.label', {'sticky': 'nsew'})]})]})])
            style.configure('Export.TMenubutton', foreground=palette['text_primary'],
                            background=palette['panel'], borderwidth=0, relief='flat',
                            padding=(14, 2), anchor='center', justify='center')
            style.map('Export.TMenubutton',
                      background=[('active', palette['panel']), ('pressed', palette['panel'])])
        except tk.TclError:
            pass

    # --- pill labels ------------------------------------------------------
    # Non-interactive readouts - the footer clock - need the same pill so the
    # bar reads as one row of shapes rather than a mix of pills and plain text.
    for style_name, tall in (('Pill.TLabel', False), ('PillTall.TLabel', True)):
        plate_name = 'BarkavPillTall.plate' if tall else 'BarkavPill.plate'
        pill_label = element(
            plate_name, palette['glass'],
            hover=palette['glass'], pressed=palette['glass'],
            border=palette['border_subtle'], pill=True, tall=tall)
        if not pill_label:
            continue
        try:
            style.layout(style_name, [(pill_label, {'sticky': 'nsew', 'children': [
                ('Label.padding', {'sticky': 'nsew', 'children': [
                    ('Label.label', {'sticky': 'nsew'})]})]})])
            style.configure(style_name, foreground=palette['text_primary'],
                            background=palette['surface_alt'], borderwidth=0,
                            anchor='center', justify='center', padding=(10, 1))
        except tk.TclError:
            continue

    # A caption sits beside a field and must not look like one, so it keeps
    # the default label layout and only takes the card's colour.
    try:
        style.configure('Caption.TLabel', background=palette['card'],
                        foreground=palette['text_secondary'], borderwidth=0,
                        padding=(2, 0))
    except tk.TclError:
        pass

    # --- containers -------------------------------------------------------
    # Frames that hold a table or a form get the same rounded plate, so a
    # panel's corners match the controls sitting inside it.
    for name, fill_key in (
        ('Card.TFrame', 'card'),
        ('Panel.TFrame', 'panel'),
        ('Surface.TFrame', 'surface'),
        ('Raised.TFrame', 'raised'),
    ):
        plate = element(
            f'{name.replace(".", "")}.plate', palette[fill_key],
            hover=palette[fill_key], pressed=palette[fill_key],
            border=palette['border_subtle'])
        if not plate:
            continue
        try:
            style.layout(name, [(plate, {'sticky': 'nsew'})])
            style.configure(name, background=palette[fill_key], borderwidth=0)
        except tk.TclError:
            continue

    group = element('BarkavGroup.plate', palette['panel'],
                    hover=palette['panel'], pressed=palette['panel'],
                    border=palette['border_subtle'])
    if group:
        try:
            style.layout('TLabelframe', [(group, {'sticky': 'nsew'})])
            style.configure('TLabelframe', background=palette['panel'], borderwidth=0)
            style.configure('TLabelframe.Label', background=palette['panel'],
                            foreground=palette['text_primary'])
        except tk.TclError:
            pass

    # A table draws its own square edge, so it is flattened and the rounded
    # corner is provided by the frame around it instead.
    for tree_style in ('Treeview', 'Barkav.Data.Treeview'):
        try:
            style.configure(tree_style, borderwidth=0, relief='flat',
                            bordercolor=palette['panel'],
                            lightcolor=palette['panel'], darkcolor=palette['panel'])
        except tk.TclError:
            continue

    # Headings sit tight against their column: the width comes from the text,
    # so a wide inset here would only push neighbouring headings apart.
    try:
        style.configure('Barkav.Data.Treeview.Heading', padding=(4, 8))
    except tk.TclError:
        pass

    # Scrollbars are slim rounded-track controls without the old square arrow
    # boxes.  The image track supplies a real cross-axis size; a native trough
    # collapses to one pixel when both arrows are removed on Windows/clam.
    # Keeping the native thumb element preserves drag/page behaviour.
    for orientation in ('Vertical', 'Horizontal'):
        try:
            track_name = f'Barkav{orientation}Scrollbar.track{token}'
            track = _scrollbar_track(
                palette, orientation=orientation, master=master,
                key=track_name,
            )
            border = (
                (0, SCROLLBAR_THICKNESS // 2, 0, SCROLLBAR_THICKNESS // 2)
                if orientation == 'Vertical'
                else (SCROLLBAR_THICKNESS // 2, 0, SCROLLBAR_THICKNESS // 2, 0)
            )
            try:
                style.element_create(
                    track_name, 'image', track, border=border,
                    sticky='ns' if orientation == 'Vertical' else 'ew',
                )
            except tk.TclError:
                if track_name not in style.element_names():
                    continue
            style.layout(f'{orientation}.TScrollbar', [
                (track_name, {
                    'sticky': 'ns' if orientation == 'Vertical' else 'ew',
                    'children': [(f'{orientation}.Scrollbar.thumb', {
                        'expand': '1', 'sticky': 'nswe',
                    })],
                }),
            ])
            style.configure(
                f'{orientation}.TScrollbar',
                background=palette['scroll_thumb'],
                troughcolor=palette['scroll_track'],
                bordercolor=palette['scroll_track'],
                lightcolor=palette['scroll_thumb'],
                darkcolor=palette['scroll_thumb'],
                borderwidth=0,
                relief='flat',
                width=SCROLLBAR_THICKNESS,
            )
            style.map(
                f'{orientation}.TScrollbar',
                background=[
                    ('disabled', palette['scroll_thumb']),
                    ('active', palette['scroll_thumb']),
                ],
                lightcolor=[('disabled', palette['scroll_thumb'])],
                darkcolor=[('disabled', palette['scroll_thumb'])],
                bordercolor=[('disabled', palette['scroll_track'])],
            )
        except tk.TclError:
            continue

    # --- notebook tabs ----------------------------------------------------
    # Tabs take a rounded rectangle rather than the stadium the buttons use,
    # so a strip of tabs reads as a row of cards instead of a row of buttons.
    tab = element(
        'BarkavTab.plate', palette['surface_alt'],
        hover=palette['glass'], pressed=palette['raised'])
    if tab:
        try:
            style.element_create(f'BarkavTabSel{token}', 'image',
                                 _plate(palette['raised'], radius=radius, master=master,
                                        key=f'tabsel{token}'),
                                 border=radius, sticky='nsew', padding=0)
        except tk.TclError:
            pass
        for name in ('TNotebook.Tab', 'Barkav.Data.TNotebook.Tab'):
            try:
                style.layout(name, [(tab, {
                    'sticky': 'nsew',
                    'children': [('Notebook.padding', {
                        'side': 'top', 'sticky': 'nsew',
                        'children': [('Notebook.label', {'side': 'top', 'sticky': ''})],
                    })],
                })])
                style.configure(name, padding=(16, 3), borderwidth=0)
            except tk.TclError:
                continue


def match_checkbutton_background(widget: ttk.Checkbutton) -> None:
    """Give a ttk checkbox the colour of what it sits on.

    TCheckbutton is styled for a panel; dropped on a bar in the page colour
    (a dialog's top bar) it showed as a lighter slab behind its own label.
    Each container colour gets one derived style, shared by every checkbox
    on it; a checkbox with a style of its own is left alone.
    """

    try:
        current = str(widget.cget('style') or '')
        if current and not current.startswith('BarkavOn'):
            return
        parent = widget.master
        style = ttk.Style(widget)
        if isinstance(parent, ttk.Widget):
            name = str(parent.cget('style') or parent.winfo_class())
            colour = style.lookup(name, 'background')
        else:
            colour = parent.cget('background')
        if not colour:
            return
        r, g, b = (value // 257 for value in widget.winfo_rgb(colour))
    except (tk.TclError, AttributeError):
        return
    name = 'BarkavOn%02X%02X%02X.TCheckbutton' % (r, g, b)
    if name != current:
        try:
            style.configure(name, background=colour)
            style.map(name, background=[('active', colour)])
            widget.configure(style=name)
        except tk.TclError:
            pass


def rounded_plate_image(width: int, height: int, *, fill: str, page: str, radius: int,
                        border: str | None = None, band: tuple[int, str] | None = None,
                        master=None, border_width: int = 1):
    """An opaque rounded card of exactly ``width`` x ``height``: ``fill``
    inside, ``page`` in the corners, an optional 1px ``border``.

    ``band`` is ``(height, colour)``: the top of the card in another colour,
    a header strip that keeps the card's rounded top corners, with a hairline
    in the border colour under it.

    A Canvas paints its own background, so it cannot sit on a rounded_backdrop
    label the way a frame's children do; it draws this as its first item
    instead.
    """

    scale = _SUPERSAMPLE
    image = Image.new('RGBA', (width * scale, height * scale), (0, 0, 0, 0))
    shape = (0, 0, width * scale - 1, height * scale - 1)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(shape, radius=radius * scale, fill=rgb(fill) + (255,))
    if band is not None and band[0] > 0:
        strip = Image.new('RGBA', image.size, (0, 0, 0, 0))
        ImageDraw.Draw(strip).rounded_rectangle(shape, radius=radius * scale,
                                                fill=rgb(band[1]) + (255,))
        keep = Image.new('L', image.size, 0)
        ImageDraw.Draw(keep).rectangle((0, 0, width * scale, band[0] * scale), fill=255)
        image.paste(strip, (0, 0), keep)
        if border:
            draw.rectangle((0, band[0] * scale, width * scale, band[0] * scale + scale - 1),
                           fill=rgb(border) + (255,))
    if border:
        draw.rounded_rectangle(shape, radius=radius * scale, outline=rgb(border) + (255,),
                               width=scale * max(1, int(border_width)))
    plate = Image.new('RGBA', image.size, rgb(page) + (255,))
    plate.alpha_composite(image)
    plate = plate.resize((width, height), Image.LANCZOS)
    from PIL import ImageTk
    return ImageTk.PhotoImage(plate.convert('RGB'), master=master)


def rounded_backdrop(container: tk.Misc, *, fill: str, page: str, radius: int,
                     border: str | None = None, band: tuple[int, str] | None = None,
                     master=None, border_width: int = 1):
    """Give a classic ``tk.Frame`` rounded corners.

    A ``tk.Frame`` cannot take a ttk style and cannot be rounded, so the
    corner is faked: the frame itself is painted the *page* colour, a rounded
    plate is placed to fill it, and the frame's real content is inset by a
    few pixels so the plate's corners show around it.

    Returns the backdrop label, or None when the container is unusable.
    """

    try:
        width = max(1, container.winfo_width())
        height = max(1, container.winfo_height())
    except tk.TclError:
        return None
    if width < 40 or height < 40:
        return None

    existing = getattr(container, '_barkav_backdrop', None)
    photo = rounded_plate_image(width, height, fill=fill, page=page, radius=radius,
                                border=border, band=band, master=master or container,
                                border_width=border_width)
    label = existing if existing is not None and existing.winfo_exists() else tk.Label(container, bd=0)
    label.configure(image=photo, bg=page)
    label._barkav_photo = photo
    label.place(x=0, y=0, relwidth=1, relheight=1)
    label.lower()
    container.configure(bg=page)
    container._barkav_backdrop = label
    return label


def clear() -> None:
    _images.clear()
