from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'stage187_window_tabs.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'ui187-token')
os.environ.setdefault('GEMINI_API_KEY', 'ui187-gemini')
os.environ.setdefault('ADMIN_USER_ID', '187')
os.environ.setdefault('GROUP_CHAT_ID', '-100187')
os.environ['PEYMAAN_ACTIVE_PROJECT_ID'] = 'PRJ-WINDOWTABS'
os.environ['PEYMAAN_ACTIVE_PROJECT_NAME'] = 'پروژه آزمایشی'
pytestmark = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI tests opt-in')


@pytest.fixture()
def app():
    import dashboard_stage18_7 as d187
    from barkav_ui import art

    # art.py caches every PhotoImage by (kind, size, colours, ...) across
    # Tk interpreters. Each test here builds its own fresh
    # Stage187Dashboard (its own tk.Tk() root), so a cache hit from a
    # previous test's already-destroyed root raises "image ... doesn't
    # exist" instead of recompositing under the new one.
    art.clear_cache()
    d187.v186.v185.fetch_tgju_usd_toman = lambda timeout=6.0: (70_000, '2026-08-21T12:00:00')
    window = d187.Stage187Dashboard()
    window.update_idletasks()
    window.update()
    yield window
    window.destroy()
    art.clear_cache()


def test_start_tab_is_fixed_and_selectable_and_project_tab_shows_the_open_project(app):
    assert set(app._window_tab_buttons187) == {'start', 'project'}
    assert app._window_view187 == 'project'
    assert app._window_tab_buttons187['project'].cget('text') == 'پروژه آزمایشی'


def test_single_window_never_spawns_a_second_toplevel_or_project_hub(app):
    import tkinter as tk

    toplevels_before = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
    app._show_start_view_187()
    app.update_idletasks()
    app.update()
    toplevels_after = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
    assert len(toplevels_after) == len(toplevels_before)
    assert app.winfo_exists()


def test_switching_to_start_hides_navbar_and_notebook_and_shows_the_start_view(app):
    app._show_start_view_187()
    app.update_idletasks()
    app.update()

    assert app._window_view187 == 'start'
    assert app.navbar.winfo_ismapped() == 0
    assert app.notebook.winfo_ismapped() == 0
    assert app.start_view187.winfo_ismapped() == 1
    assert app.quick_commands_host187.winfo_ismapped() == 0
    assert app.shell_search_host187.winfo_ismapped() == 0


def test_returning_to_project_restores_navbar_notebook_and_shell_tools(app):
    app._show_start_view_187()
    app.update_idletasks()
    app.update()

    app._show_project_view_187()
    app.update_idletasks()
    app.update()

    assert app._window_view187 == 'project'
    assert app.navbar.winfo_ismapped() == 1
    assert app.notebook.winfo_ismapped() == 1
    assert app.quick_commands_host187.winfo_ismapped() == 1
    assert app.shell_search_host187.winfo_ismapped() == 1
    # The seven navbar tabs (_VISIBLE_NAV) must still be intact, not
    # collapsed or dropped by the rebuild.
    assert len(app.nav_buttons) == len(app._VISIBLE_NAV)


def test_navbar_survives_repeated_start_project_round_trips(app):
    # Regression guard for the exact bug master's own history hit: an
    # ordering mistake between flipping _window_view187 and calling
    # _rebuild_navbar() left the navbar permanently unmapped after a
    # round trip. One switch passing is not enough evidence against that
    # class of bug - it has to survive several.
    for _ in range(3):
        app._show_start_view_187()
        app.update_idletasks()
        app.update()
        app._show_project_view_187()
        app.update_idletasks()
        app.update()
    assert app.navbar.winfo_ismapped() == 1
    assert app.notebook.winfo_ismapped() == 1


def test_start_view_shows_empty_state_message_with_no_registered_projects(app, tmp_path, monkeypatch):
    from project_registry import ProjectRegistry

    # _start_registry_187() defaults to ProjectRegistry(BASE_DIR), which
    # reads/writes this checkout's real (gitignored, but still real)
    # data/project_registry.json. Every test here must use its own
    # tmp_path registry instead, never the real one.
    monkeypatch.setattr(app, '_start_registry_187', lambda: ProjectRegistry(tmp_path))

    app._show_start_view_187()
    app.update_idletasks()
    app.update()
    children = app.start_recent_host187.winfo_children()
    assert len(children) == 1
    assert 'هنوز پروژه‌ای ثبت نشده است' in children[0].cget('text')


def test_start_view_renders_a_recent_card_and_opening_the_current_project_switches_back(app, tmp_path, monkeypatch):
    from project_registry import ProjectEntry, ProjectRegistry

    registry = ProjectRegistry(tmp_path)
    monkeypatch.setattr(app, '_start_registry_187', lambda: registry)
    db_path = tmp_path / 'demo.sqlite3'
    db_path.touch()
    entry = ProjectEntry(project_id='PRJ-WINDOWTABS', name='پروژه آزمایشی', db_path=str(db_path))
    registry.data['projects'] = [entry.__dict__]
    registry.save()

    app._show_start_view_187()
    app.update_idletasks()
    app.update()
    cards = app.start_recent_host187.winfo_children()
    assert len(cards) == 1
    # _paint_resizable_backdrop_187 inserts its own rounded-corner Label
    # into the card ahead of table/strip in winfo_children() - identify
    # the phase strip by its 32 children instead of a fixed index.
    strip = next(
        child for child in cards[0].winfo_children()
        if len(child.winfo_children()) == app._START_PHASE_COUNT187
    )

    app._start_open_project_187(entry)
    app.update_idletasks()
    app.update()
    assert app._window_view187 == 'project'
    assert app.navbar.winfo_ismapped() == 1
