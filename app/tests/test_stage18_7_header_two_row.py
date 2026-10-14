"""The shell's top bar as one frame of two rows (operator round 2026-09-30).

At the left the mark, at the size it always had, spans the bar's full height.
Beside it, above: the search, and at the right the file menu (a bare three-bar
mark) then save, undo, redo, refresh. A 1px rule. Below: the window tabs from
the right, شروع first, in AutoCAD's file-tab style - flat, side by side with no
gap, resting on the rule above and the bar's own edge below. The bar is a tenth
taller than the 67px it had, and a tab that is not selected is no longer the
bar's own black.
"""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'stage187_header_two_row.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'ui187-token')
os.environ.setdefault('GEMINI_API_KEY', 'ui187-gemini')
os.environ.setdefault('ADMIN_USER_ID', '187')
os.environ.setdefault('GROUP_CHAT_ID', '-100187')
os.environ.setdefault('STAGE4_SHEETS_ENABLED', 'false')

gui_only = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI tests opt-in')


def _luma(colour: str) -> float:
    red, green, blue = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _root():
    root = tk.Tk()
    root.geometry('900x200+0+0')
    return root


# ---------------------------------------------------------------- the source

def test_bar_is_a_tenth_taller_and_the_rows_add_up_to_it():
    import dashboard_stage18_7 as d187

    bar = d187.Stage187Dashboard
    assert bar._SHELL_BAR_HEIGHT_187 == 74
    assert abs(bar._SHELL_BAR_HEIGHT_187 / 67 - 1.10) < 0.01
    # inset + tools row + the 1px rule + tabs row + the bar's own 1px edge fill
    # the bar exactly, so the tabs rest on that edge with nothing between.
    assert (bar._SHELL_INSET_187 + bar._SHELL_TOOLS_ROW_187 + 1
            + bar._SHELL_TABS_ROW_187 + 1) == bar._SHELL_BAR_HEIGHT_187
    # The row holds the tiles it carries; icons are larger than the 18px before.
    assert bar._SHELL_TILE_187 <= bar._SHELL_TOOLS_ROW_187
    assert bar._SHELL_ICON_187 > 18
    # The mark keeps the 44px it always had: it does not shrink to fit a row.
    assert 'art.logo(height=44' in inspect.getsource(bar._install_brand_logo_187)


def test_shell_builds_tools_and_search_in_the_top_row_and_tabs_in_the_bottom_row():
    import dashboard_stage18_7 as d187

    shell = inspect.getsource(d187.Stage187Dashboard._install_shell_187)
    assert 'row1, row2 = self._build_shell_rows_187(top, p)' in shell
    assert 'self._build_window_tabs_187(row2, p)' in shell
    assert 'self._build_shell_search_187(row1, p)' in shell
    assert 'tk.Frame(row1' in shell
    # Right to left: the file menu is packed first, so it sits right-most, and
    # the four tools follow it.
    assert shell.index("self.quick_commands_host187.pack(side='right'") \
        < shell.index('self._shell_button_187(')
    # The file button carries no word.
    assert "text='فایل'" not in shell
    # The mark stays in the bar (first in its packing order) and takes its
    # full height; its old pady is replaced, not inherited.
    assert "brand.pack_configure(side='left', fill='y', padx=(14, 6), pady=2)" in shell
    assert 'in_=' not in shell

    tabs = inspect.getsource(d187.Stage187Dashboard._build_window_tabs_187)
    assert 'strip=True' in tabs and 'pill=True' not in tabs
    assert tabs.index("add('start'") < tabs.index("add('project'")
    assert 'edge = tk.Frame' not in tabs and 'rely=1.0' not in tabs, 'the old rule under the tabs is gone'

    # Packed from the bottom up: the tab row on the bar's edge, the rule on the
    # tab row, the tools row above.
    rows = inspect.getsource(d187.Stage187Dashboard._build_shell_rows_187)
    assert rows.index('row2 = ') < rows.index('rule = ') < rows.index('row1 = ')
    assert "side='bottom'" in rows and 'pady=(0, 1)' in rows
    assert 'height=1' in rows and "p['border']" in rows

    recolour = inspect.getsource(d187.Stage187Dashboard._round_shell_bars_187)
    assert '_barkav_keep_bg187' in recolour, 'the rule must survive the bar repaint'


# --------------------------------------------------------------------- icons

def test_hamburger_is_three_bars_of_one_length():
    from barkav_ui.line_icons import NAMES, render

    assert 'hamburger' in NAMES
    image = render('hamburger', size=48, colour='#FFFFFF', background='#000000').convert('L')
    inked_rows = [y for y in range(image.height)
                  if max(image.getpixel((x, y)) for x in range(image.width)) > 128]
    bars, current = [], [inked_rows[0]]
    for y in inked_rows[1:]:
        if y == current[-1] + 1:
            current.append(y)
        else:
            bars.append(current)
            current = [y]
    bars.append(current)
    assert len(bars) == 3
    spans = []
    for bar in bars:
        xs = [x for y in bar for x in range(image.width) if image.getpixel((x, y)) > 128]
        spans.append((min(xs), max(xs)))
    assert len({span[1] - span[0] for span in spans}) == 1, 'the bars are one length'


def test_tile_puts_the_icon_on_a_rounded_plate():
    from barkav_ui.line_icons import render_tile

    tile = render_tile('save', size=22, box=30, colour='#FFFFFF', ground='#000000',
                       fill='#334455', radius=9)
    assert tile.size == (30, 30)
    assert tile.getpixel((0, 0)) == (0, 0, 0), 'the corner shows the ground: the plate is round'
    plate = tile.getpixel((2, 15))
    assert all(abs(got - want) <= 6 for got, want in zip(plate, (0x33, 0x44, 0x55)))
    bare = render_tile('save', size=22, box=30, colour='#FFFFFF', ground='#000000', fill=None)
    assert bare.getpixel((2, 15)) == (0, 0, 0), 'no fill means no plate'


# ---------------------------------------------------------------- window tabs

def test_strip_tabs_are_flat_flush_and_not_the_bar_colour():
    from barkav_ui.window_tabs import WindowTabs

    root = _root()
    try:
        bar = '#111820'
        plain = WindowTabs(root, background=bar)
        strip = WindowTabs(root, background=bar, height=34, strip=True)
        for tabs in (plain, strip):
            tabs.pack(side='right')
            tabs.add('start', 'شروع', lambda: None)
            tabs.add('project', 'پروژه', lambda: None, closable=True, on_close=lambda: None)
            tabs.select('project')
        root.update()

        def kinds(tabs, key):
            canvas = tabs.tab_canvas(key)
            return [canvas.type(item) for item in canvas.find_all()]

        # The default keeps the bar's own colour behind an unselected tab.
        assert plain._colours['rest'] is None
        assert str(plain.tab_canvas('start').cget('bg')) == bar

        # A strip's unselected tab is not the bar's black: it is lifted toward
        # the ink, and pointing at it lifts it further.
        rest = strip._colours['rest']
        assert rest and rest != bar and _luma(rest) > _luma(bar)
        assert _luma(strip._colours['hover']) > _luma(rest)
        assert str(strip.tab_canvas('start').cget('bg')) == rest
        # The selected tab still wears the accent fill, not the resting one.
        assert str(strip.tab_canvas('project').cget('bg')) == strip._colours['active'] != rest
        # A tab that loses selection goes back to a plate of its own.
        strip.select('start')
        assert str(strip.tab_canvas('project').cget('bg')) == rest
        strip.select('project')

        # Flat: the canvas is the plate, so no rounded plate image is drawn.
        assert 'image' not in kinds(strip, 'start')
        # A hairline on each tab's left edge; the first tab is closed on its
        # right edge too, so the strip reads as one piece.
        assert kinds(strip, 'start').count('line') == 2
        assert kinds(strip, 'project').count('line') == 1

        # Flush: no gap between two tabs, and each is as tall as the strip.
        start, project = strip.tab_canvas('start'), strip.tab_canvas('project')
        assert start.winfo_rootx() == project.winfo_rootx() + project.winfo_width()
        assert start.winfo_height() == project.winfo_height() == 34
        assert start.winfo_rooty() == project.winfo_rooty()
    finally:
        root.destroy()


# ------------------------------------------------------ the whole dashboard

@pytest.fixture(scope='module')
def app():
    import dashboard_stage18_7 as d187
    from barkav_ui import art

    art.clear_cache()
    d187.v186.v185.fetch_tgju_usd_toman = lambda timeout=6.0: (70_000, '2026-08-21T12:00:00')
    window = d187.Stage187Dashboard()
    window.update_idletasks()
    window.update()
    try:
        yield window
    finally:
        window.destroy()
        art.clear_cache()


def _rect(widget):
    return (widget.winfo_rootx(), widget.winfo_rooty(),
            widget.winfo_rootx() + widget.winfo_width(),
            widget.winfo_rooty() + widget.winfo_height())


def _settle(window):
    window.update_idletasks()
    window.update()


def _logo(app):
    labels = [child for child in app._brand_host_186.winfo_children() if child.cget('image')]
    assert len(labels) == 1
    return labels[0]


@gui_only
def test_bar_is_two_rows_split_by_a_one_pixel_rule_that_the_tabs_rest_on(app):
    _settle(app)
    top = app._shell_bars187[0]
    assert top.winfo_height() == 74
    row1, rule, row2 = app.shell_tools_row187, app.shell_rule187, app.shell_tabs_row187
    assert row1.winfo_rooty() < rule.winfo_rooty() < row2.winfo_rooty()
    assert rule.winfo_height() == 1
    # Row above, rule, row below: no gap and no overlap.
    assert row1.winfo_rooty() + row1.winfo_height() == rule.winfo_rooty()
    assert rule.winfo_rooty() + 1 == row2.winfo_rooty()
    inset = app._SHELL_INSET_187
    assert (row1.winfo_rooty() - top.winfo_rooty()) == inset
    # The tab row ends one pixel short of the bar's bottom: that pixel is the
    # bar's own edge line, so the tabs rest on it with nothing between.
    assert (top.winfo_rooty() + top.winfo_height()
            - (row2.winfo_rooty() + row2.winfo_height())) == 1
    # The rule is its own colour, not the bar's, so it can be seen.
    assert str(rule.cget('bg')) != str(row1.cget('bg'))


@gui_only
def test_the_mark_keeps_its_size_and_spans_both_rows_and_the_rule_stops_at_it(app):
    _settle(app)
    top = app._shell_bars187[0]
    logo, rule = _logo(app), app.shell_rule187
    assert app._brand_logo_image187.height() == 44
    left, y0, right, y1 = _rect(logo)
    # It crosses the line between the rows: it belongs to the top frame and
    # the bottom one alike.
    assert y0 < app.shell_tools_row187.winfo_rooty() + app.shell_tools_row187.winfo_height()
    assert y1 > app.shell_tabs_row187.winfo_rooty()
    assert y0 < rule.winfo_rooty() < y1
    # Centred in the bar's full height.
    assert abs((y0 + y1) / 2 - (top.winfo_rooty() + top.winfo_height() / 2)) <= 2
    # The rule and both rows begin where the mark ends: nothing crosses it.
    assert rule.winfo_rootx() >= right
    assert app.shell_tools_row187.winfo_rootx() >= right
    assert app.shell_tabs_row187.winfo_rootx() >= right


@gui_only
def test_top_row_reads_search_beside_the_mark_and_file_then_tools_at_the_right(app):
    _settle(app)
    row1 = app.shell_tools_row187
    top_row = _rect(row1)

    def inside_top_row(widget):
        left, y0, right, y1 = _rect(widget)
        return left >= top_row[0] and right <= top_row[2] and y0 >= top_row[1] and y1 <= top_row[3]

    search = app.shell_search_host187
    assert inside_top_row(search)
    assert _rect(_logo(app))[2] <= search.winfo_rootx(), 'the search sits beside the mark'
    # Right to left: file menu, save, undo, redo, refresh.
    file_button = app.file_button187
    order = [file_button, *app.command_buttons]
    xs = [button.winfo_rootx() for button in order]
    assert xs == sorted(xs, reverse=True), 'file menu right-most, then the four tools'
    assert all(inside_top_row(button) for button in order)
    assert file_button.winfo_rootx() > search.winfo_rootx() + search.winfo_width()
    # No word on the file button; every command shows an image, larger than 18px.
    assert file_button.cget('text') == ''
    for button in order:
        assert button.cget('image')
        assert int(app.tk.call('image', 'height', button.cget('image'))) >= app._SHELL_TILE_187
        assert button.winfo_height() >= app._SHELL_TILE_187


@gui_only
def test_tabs_are_a_flush_strip_on_the_rule_and_the_bar_edge_from_the_right(app):
    _settle(app)
    top = app._shell_bars187[0]
    rule = app.shell_rule187
    row2 = _rect(app.shell_tabs_row187)
    start = app.window_tabs187.tab_canvas('start')
    project = app.window_tabs187.tab_canvas('project')
    assert start.winfo_rootx() > project.winfo_rootx(), 'شروع first from the right'
    # No gap between the two tabs.
    assert start.winfo_rootx() == project.winfo_rootx() + project.winfo_width()
    for canvas in (start, project):
        left, y0, right, y1 = _rect(canvas)
        # They touch the rule above and the bar's edge line below.
        assert y0 == rule.winfo_rooty() + 1
        assert y1 == top.winfo_rooty() + top.winfo_height() - 1
        assert y0 >= row2[1] and y1 <= row2[3] and right <= row2[2]
    # The first tab's right edge lines up with the file menu's above it.
    assert _rect(start)[2] == _rect(app.file_button187)[2]
    # Nothing but the tabs is in the bottom row.
    assert not [child for child in app.shell_tabs_row187.winfo_children()
                if child is not app.tab_area187]


@gui_only
def test_unselected_tab_is_a_plate_not_the_bar_black(app):
    _settle(app)
    tabs = app.window_tabs187
    bar = str(app.shell_tabs_row187.cget('bg'))
    app._show_project_view_187()
    _settle(app)
    assert tabs.active == 'project'
    rest = tabs._colours['rest']
    assert rest and rest != bar
    assert str(tabs.tab_canvas('start').cget('bg')) == rest
    app._show_start_view_187()
    _settle(app)
    assert tabs.active == 'start'
    assert str(tabs.tab_canvas('project').cget('bg')) == rest
    assert str(tabs.tab_canvas('start').cget('bg')) == tabs._colours['active']
    app._show_project_view_187()
    _settle(app)


@gui_only
def test_starting_view_hides_only_the_tools_and_moves_nothing(app):
    _settle(app)
    app._show_project_view_187()
    _settle(app)
    before = {
        'file': _rect(app.file_button187),
        'start': _rect(app.window_tabs187.tab_canvas('start')),
        'search': _rect(app.shell_search_host187),
        'mark': _rect(_logo(app)),
        'top': app._shell_bars187[0].winfo_height(),
    }
    assert app.shell_tools_host187.winfo_ismapped() == 1

    app._show_start_view_187()
    _settle(app)
    assert app.shell_tools_host187.winfo_ismapped() == 0
    assert app.file_button187.winfo_ismapped() == 1
    assert app.shell_search_host187.winfo_ismapped() == 1
    assert _rect(app.file_button187) == before['file']
    assert _rect(app.window_tabs187.tab_canvas('start')) == before['start']
    assert _rect(app.shell_search_host187) == before['search']
    assert _rect(_logo(app)) == before['mark']
    assert app._shell_bars187[0].winfo_height() == before['top']

    app._show_project_view_187()
    _settle(app)
    assert app.shell_tools_host187.winfo_ismapped() == 1
    xs = [button.winfo_rootx() for button in app.command_buttons]
    assert xs == sorted(xs, reverse=True)
    assert max(button.winfo_rootx() + button.winfo_width() for button in app.command_buttons) \
        < app.file_button187.winfo_rootx()
    assert _rect(app.file_button187) == before['file']


@gui_only
def test_the_rule_keeps_its_own_colour_after_the_bar_is_repainted(app):
    from ui_stage18_7 import palette_187

    _settle(app)
    app._round_shell_bars_187()
    _settle(app)
    rule = app.shell_rule187
    assert str(rule.cget('bg')).lower() == palette_187()['border'].lower()
    assert str(app.shell_tools_row187.cget('bg')).lower() == palette_187()['surface'].lower()


@gui_only
def test_pointing_at_a_command_swaps_its_tile_and_leaving_restores_it(app):
    _settle(app)
    for button in (app.file_button187, *app.command_buttons):
        rest = str(button.cget('image'))
        app._bar_hover_187(button, True)
        assert str(button.cget('image')) != rest
        app._bar_hover_187(button, False)
        assert str(button.cget('image')) == rest


@gui_only
def test_file_menu_still_opens_from_the_three_bar_button_and_closes(app):
    _settle(app)
    app._show_project_view_187()
    _settle(app)
    app.file_button187.invoke()
    _settle(app)
    menu = app.file_menu187
    assert menu is not None and menu.winfo_exists()
    labels = set()
    for widget in app._walk_187(menu):
        try:
            labels.add(str(widget.cget('text')).lstrip('‏'))
        except tk.TclError:
            continue
    assert {'ذخیره', 'تنظیمات'} <= labels
    app._close_file_menu_187()
    _settle(app)
    assert app.file_menu187 is None
