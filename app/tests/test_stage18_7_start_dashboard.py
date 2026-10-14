"""Operator-approved S1-S4 (استارت) and D1-D5 (dashboard and shell), 2026-09-27."""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'start187-token')
os.environ.setdefault('GEMINI_API_KEY', 'start187-key')
os.environ.setdefault('ADMIN_USER_ID', '1')
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'start187.sqlite3')
os.environ['STAGE4_SHEETS_ENABLED'] = 'false'


def _root():
    root = tk.Tk()
    root.geometry('900x200+0+0')
    return root


def test_window_tabs_close_only_from_the_cross():
    from barkav_ui.window_tabs import WindowTabs

    root = _root()
    try:
        calls = []
        tabs = WindowTabs(root, background='#101820')
        tabs.pack(side='right')
        tabs.add('project', 'بارکاو۲', lambda: calls.append('project'),
                 closable=True, on_close=lambda: calls.append('close'))
        tabs.add('start', 'استارت', lambda: calls.append('start'))
        tabs.select('project')
        root.update()
        project = tabs.tab_canvas('project')
        width = int(project.cget('width'))
        tabs._click('project', 8)            # the cross, at the tab's left end
        tabs._click('project', width - 10)   # the label
        tabs._click('start', 8)              # no cross on استارت
        assert calls == ['close', 'project', 'start']
        assert tabs.active == 'project'
        # Reading order: the first tab added sits right-most.
        assert project.winfo_rootx() > tabs.tab_canvas('start').winfo_rootx()
    finally:
        root.destroy()


def test_phase_strip_fills_from_progress_or_spending_and_opens_a_phase():
    """Operator round 2026-09-27: one row of 32 cells across the card, the
    names under them; a phase with no recorded progress fills to the share
    of its budget already spent, so the row follows the recorded costs."""

    from barkav_ui.phase_groups import PhaseGroups, PhaseLegend

    root = _root()
    try:
        opened, edited = [], []
        colours = {'NOT_STARTED': '#2A3440', 'ACTIVE': '#3BB273', 'PAUSED': '#E0A030',
                   'COMPLETED': '#2E9E62', 'track': '#1D2833', 'text': '#E6EDF3',
                   'muted': '#8B98A5', 'accent': '#4FD1E0', 'ring': '#4FD1E0'}
        groups = PhaseGroups(root, background='#131C24', colours=colours,
                             on_open=opened.append, on_edit=edited.append)
        groups.pack(fill='x')
        root.update()
        groups.set_data({1: {'status': 'COMPLETED', 'physical_progress': 0},
                         5: {'status': 'ACTIVE', 'physical_progress': 35},
                         9: {'status': 'PAUSED', 'physical_progress': 10}},
                        {5: 'جواز'},
                        spending={5: (900, 1000), 7: (50, 100), 8: (30, 0)})
        root.update()
        assert groups.status(1) == ('COMPLETED', 100.0), 'a finished phase reads full'
        assert groups.status(5) == ('ACTIVE', 35.0), 'recorded progress wins over spending'
        assert groups.status(7) == ('ACTIVE', 50.0), 'spent half its budget, nothing recorded'
        assert groups.status(8) == ('ACTIVE', 0.0), 'spent with no budget: started'
        assert groups.status(2) == ('NOT_STARTED', 0.0)
        assert groups.started() == 5
        # Budget-weighted: (35 x 1000 + 50 x 100) / 1100 = 36.4%.
        assert round(groups.overall(), 3) == round((35 * 1000 + 50 * 100) / 1100 / 100, 3)
        assert len(groups._cells) == 32
        # One row, phase 1 on the right where the row starts.
        tops = {cell[1] for cell in groups._cells.values()}
        assert len(tops) == 1
        assert groups._cells[1][0] > groups._cells[2][0] > groups._cells[32][0]
        texts = [groups.itemcget(item, 'text') for item in groups.find_all() if groups.type(item) == 'text']
        # Operator round 2026-09-27: the phase number under each cell, its
        # percent above it, the name only on hover.
        for number in range(1, 33):
            assert format(number, '02d').translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')) in texts
        assert '۱۰۰' in texts or '۱۰۰٪' in texts, 'the percent above a finished phase'
        assert not any(float(groups.itemcget(item, 'angle') or 0) for item in groups.find_all()
                       if groups.type(item) == 'text'), 'no diagonal names'
        assert not any('کلیک' in text for text in texts), 'no click hint'
        assert any(text.startswith('\u200f') and 'فاز شروع شده' in text for text in texts)
        x0, y0, x1, y1 = groups._cells[5]
        groups._click(SimpleNamespace(x=(x0 + x1) // 2, y=(y0 + y1) // 2))
        groups._double(SimpleNamespace(x=(x0 + x1) // 2, y=(y0 + y1) // 2))
        assert opened == [5] and edited == [5]
        legend = PhaseLegend(root, background='#131C24', colours=colours)
        assert int(legend.cget('width')) > 100
    finally:
        root.destroy()


def test_costs_filed_under_a_phase_but_on_no_plan_line_count_for_it():
    import sqlite3
    from contextlib import contextmanager

    import dashboard_stage18_7 as d187

    con = sqlite3.connect(':memory:')
    con.execute("""CREATE TABLE expenses (construction_stage TEXT, final_amount INTEGER,
                   status TEXT, plan_ref TEXT, deleted_at TEXT)""")
    con.executemany('INSERT INTO expenses VALUES (?, ?, ?, ?, ?)', [
        ('۰۵ — جواز', 100, 'APPROVED', '', None),
        ('اسکلت', 50, 'PAID', '', None),
        ('05 — جواز', 7, 'PARTIALLY_PAID', '', None),
        ('۰۵ — جواز', 999, 'DRAFT', '', None),          # not approved yet
        ('۰۵ — جواز', 888, 'APPROVED', 'P-05-01', None),  # already on the plan
        ('۰۵ — جواز', 777, 'APPROVED', '', '2026-01-01'),  # deleted
        ('نامعلوم', 5, 'APPROVED', '', None),
    ])

    class FakeDB:
        @contextmanager
        def read(self):
            yield con

    totals = d187.unplanned_phase_costs_187(FakeDB(), {5: 'جواز', 9: 'اسکلت'})
    assert totals == {5: 107, 9: 50}
    source = inspect.getsource(d187.Stage187Dashboard._refresh_phase_groups_187)
    assert 'unplanned_phase_costs_187(DB, names)' in source


def test_rail_is_one_list_and_the_theme_item_opens_on_pointing():
    import dashboard_stage18_7 as d187

    assert len(d187.Stage187Dashboard.NAV_GROUPS_187) == 1
    assert d187.Stage187Dashboard.NAV_GROUPS_187[0][0] == ''
    rebuild = inspect.getsource(d187.Stage187Dashboard._rebuild_navbar)
    assert "{'chevron': True, 'on_hover': self._rail_theme_hover_187}" in rebuild
    post = inspect.getsource(d187.Stage187Dashboard._post_rail_theme_menu_187)
    assert 'compact=True' in post and 'hover_close=True' in post

    from barkav_ui.rail import NavRail

    root = _root()
    try:
        host = tk.Frame(root, width=NavRail.EXPANDED_WIDTH, height=300)
        host.pack(side='right', fill='y')
        host.pack_propagate(False)
        hovered = []
        rail = NavRail(host, groups=[('', [('a', 'داشبورد', 'dashboard', None, ''),
                                          ('b', 'ثبت دیتا', 'data', None, '')])],
                       footer=[('theme', 'تم و حالت نمایش', 'theme', None, '',
                                {'chevron': True, 'on_hover': lambda item, inside: hovered.append(inside)})])
        root.update()
        assert not any(isinstance(w, tk.Label) for w in rail.top.winfo_children()), 'no group heading'
        item = rail.footer_items['theme']
        assert item.chevron
        item._enter()
        item._leave()
        assert hovered == [True, False]
    finally:
        root.destroy()


def test_tiles_and_rings_render_at_their_size():
    from barkav_ui.badges import icon_tile, progress_ring

    root = _root()
    try:
        tile = icon_tile('cheque', size=34, colour='#4FD1E0', fill='#1E3A40',
                         background='#131C24', master=root)
        ring = progress_ring(0.35, size=54, width=5, colour='#4FD1E0', track='#1D2833',
                             background='#131C24', master=root)
        assert (tile.width(), tile.height()) == (34, 34)
        assert (ring.width(), ring.height()) == (54, 54)
    finally:
        root.destroy()


def test_dashboard_is_sized_to_fit_and_wears_one_icon_family():
    import dashboard_stage18_7 as d187

    fit = inspect.getsource(d187.Stage187Dashboard._fit_overview_187)
    assert 'max(240, min(300,' in fit, 'readable charts; the page scrolls to them'
    restyle = inspect.getsource(d187.Stage187Dashboard._restyle_dashboard_187)
    assert '_card_tile_187(' in restyle and 'dashboard_reference_icon' not in restyle
    # Each card's own colour; transactions and sales match the rail's tiles.
    from barkav_ui.rail import TILE_HUES
    hues = d187.Stage187Dashboard._CARD_HUES_187
    assert hues['transactions'] == TILE_HUES['transactions'] and hues['sales'] == TILE_HUES['income']
    assert len(set(hues.values())) == 5
    rounding = inspect.getsource(d187.Stage187Dashboard._round_overview_containers_187)
    assert 'band=band' in rounding and 'children[0].pack_configure(padx=radius' in rounding
    assert 'text=rtl_187(label.cget(' in restyle, '«۳۰ روز آینده» reads from the right'
    # Grid options on the packed 32-phase card took it out of the page.
    assert "if section.winfo_manager() == 'grid':" in restyle
    assert set(d187.Stage187Dashboard._CARD_ICONS_187.values()) == {
        'transactions', 'cheque', 'bank', 'coins', 'calendar'}


def test_start_pins_keep_a_project_on_top():
    import dashboard_stage18_7 as d187
    from v18_store import load_ui

    refreshed = []
    fake = SimpleNamespace(_refresh_start_view_187=lambda: refreshed.append(True))
    d187.Stage187Dashboard._start_toggle_pin_187(fake, 'p-one')
    d187.Stage187Dashboard._start_toggle_pin_187(fake, 'p-two')
    assert load_ui().get('start_pins187') == ['p-two', 'p-one']
    d187.Stage187Dashboard._start_toggle_pin_187(fake, 'p-two')
    assert load_ui().get('start_pins187') == ['p-one']
    d187.Stage187Dashboard._start_toggle_pin_187(fake, 'p-one')
    assert load_ui().get('start_pins187') == []
    assert len(refreshed) == 4

    build = inspect.getsource(d187.Stage187Dashboard._build_start_view_187)
    assert "text='خوش آمدید'" in build and 'self.start_query187' in build


def test_start_lower_half_is_two_frames_with_the_search_in_the_list_heading():
    """Operator round 2026-09-27: the recent projects in a frame drawn all
    the way round, the earlier watermark back in a frame beside it, and the
    search opposite «پروژه‌های اخیر» on that frame's left."""

    import dashboard_stage18_7 as d187

    build = inspect.getsource(d187.Stage187Dashboard._build_start_view_187)
    assert "recent.grid(row=0, column=1, sticky='nsew'" in build
    assert "mark.grid(row=0, column=0, sticky='nsew'" in build
    head = build[build.index('head = tk.Frame(recent'):build.index('self.start_recent_host187 = ')]
    assert "text='پروژه‌های اخیر'" in head and "search.pack(side='left')" in head
    assert build.count('self._paint_resizable_backdrop_187(') == 3, 'hero and both halves are framed'
    assert 'self._schedule_start_mark_187' in build
    painter = inspect.getsource(d187.Stage187Dashboard._paint_start_mark_187)
    assert 'art.logo(' in painter and 'drop_tagline=False' in painter
    assert 'art.construction_watermark(' in painter
    # Title case: no trailing ellipsis on the open action.
    assert "'باز کردن پروژه'," in build and 'باز کردن پروژه…' not in build


def test_recent_projects_scroll_and_a_cross_takes_one_off_the_list(monkeypatch):
    import dashboard_stage18_7 as d187

    root = tk.Tk()
    root.geometry('500x300+0+0')
    try:
        dashboard = d187.Stage187Dashboard.__new__(d187.Stage187Dashboard)
        dashboard.tk = root.tk
        dashboard._w = '.'
        # A real root widget's own `.master` is None; the wheel binding now
        # arms with `bind_all` at build time (no more <Enter>/<Leave> to
        # defer it to), whose `_root()` walk needs this attribute to find
        # where the interpreter's own tag lives.
        dashboard.master = None
        host = tk.Frame(root, width=400, height=200)
        host.pack_propagate(False)
        host.pack(anchor='nw')
        d187.Stage187Dashboard._build_start_scroll_list_187(dashboard, host, d187.palette_187())
        inner = dashboard.start_recent_list187
        for _ in range(7):
            tk.Frame(inner, height=75, width=380).pack(fill='x', pady=(8, 0))
        root.update()
        canvas = dashboard.start_recent_canvas187
        bars = [w for w in host.pack_slaves() if isinstance(w, ttk.Scrollbar)]
        assert bars, 'seven 75px cards in 200px: the list scrolls'
        canvas.yview_moveto(1.0)
        assert canvas.yview()[1] == 1.0
        # The cross: off the list, kept in the settings, nothing deleted.
        stored = {}
        monkeypatch.setattr(d187, 'load_ui', lambda: dict(stored))
        monkeypatch.setattr(d187, 'save_ui', lambda data: stored.update(data))
        dashboard._refresh_start_view_187 = lambda: None
        dashboard._start_hide_project_187('p-3')
        assert stored['start_hidden187'] == ['p-3']
        assert dashboard._start_hidden_187() == ['p-3']
    finally:
        root.destroy()


def test_start_action_tiles_and_the_bar_order():
    import dashboard_stage18_7 as d187
    from barkav_ui.badges import FEATURE_GLYPHS, feature_tile

    assert set(FEATURE_GLYPHS) == {'new_project', 'open_project', 'edit_project'}
    root = _root()
    try:
        tile = feature_tile('open_project', size=38, colour='#F79A2E', ink='#FFFFFF',
                            background='#141C25', master=root)
        assert (tile.width(), tile.height()) == (38, 38)
    finally:
        root.destroy()
    # استارت reads first from the bar's right end; the mark sits at the left.
    tabs = inspect.getsource(d187.Stage187Dashboard._build_window_tabs_187)
    assert tabs.index("add('start'") < tabs.index("add('project'")
    brand = inspect.getsource(d187.Stage187Dashboard._install_brand_logo_187)
    assert "host.pack_configure(side='left'" in brand


def test_footer_status_names_the_last_save_and_telegram():
    import dashboard_stage18_7 as d187

    Path(d187.DB.db_path).touch()
    root = _root()
    try:
        saved, telegram = tk.Label(root), tk.Label(root)
        fake = SimpleNamespace(
            footer_saved187=saved, footer_telegram187=telegram,
            approval_center=SimpleNamespace(bot=tk.StringVar(master=root, value='تلگرام: آنلاین و آماده')),
            after=lambda *_a, **_k: None, _refresh_footer_status_187=lambda: None,
        )
        d187.Stage187Dashboard._refresh_footer_status_187(fake)
        assert saved.cget('text').startswith('● ذخیره شد، ')
        assert telegram.cget('text') == 'تلگرام: متصل'
        fake.approval_center.bot.set('تلگرام: قطع — اتصال برقرار نیست')
        d187.Stage187Dashboard._refresh_footer_status_187(fake)
        assert telegram.cget('text') == 'تلگرام: قطع'
    finally:
        root.destroy()
