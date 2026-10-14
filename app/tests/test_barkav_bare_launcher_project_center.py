from __future__ import annotations

import os

import pytest

from project_registry import ProjectEntry

pytestmark = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI tests opt-in')


@pytest.fixture()
def hub(tmp_path):
    from barkav_bare_launcher_187 import ProjectHub187
    from barkav_ui import art

    # art.py caches every PhotoImage by (kind, size, colours, ...) - keyed
    # across Tk interpreters. Each test here builds its own fresh
    # ProjectHub187 (its own tk.Tk() root), so a cache hit from a previous
    # test's already-destroyed root raises "image ... doesn't exist"
    # instead of recompositing under the new one.
    art.clear_cache()
    window = ProjectHub187(str(tmp_path))
    window.update_idletasks()
    yield window
    window.destroy()
    art.clear_cache()


def test_start_tab_is_pinned_rightmost_and_not_closable(hub):
    assert hub.active_tab_key == 'start'
    button = hub.tab_buttons['start']
    # A pinned tab never grew a close ('×') label - _add_tab only appends
    # one when closable=True.
    assert len(button.winfo_children()) == 1


def test_opening_a_project_tab_creates_a_closable_summary_tab_and_selects_it(hub, tmp_path):
    db = tmp_path / 'finance.sqlite3'
    db.write_bytes(b'')
    project = ProjectEntry(project_id='PRJ-CENTER-1', name='پروژه مرکز آزمایشی', db_path=str(db))

    hub._open_project_tab(project)

    key = 'project:PRJ-CENTER-1'
    assert hub.active_tab_key == key
    assert key in hub.tab_pages
    button = hub.tab_buttons[key]
    # Closable tabs get a second widget - the '×' label - beyond the label.
    assert len(button.winfo_children()) == 2

    hub._close_tab(key)
    assert key not in hub.tab_pages
    assert hub.active_tab_key == 'start'


def test_recent_card_renders_a_phase_progress_strip_and_completion_summary(hub, tmp_path):
    shortcut = tmp_path / 'demo.brk'
    shortcut.write_text('{}', encoding='utf-8')

    hub._build_recent_card(
        hub.recent_list_inner, shortcut,
        {'name': 'پروژه نمونه', 'project_id': 'PRJ-CENTER-2', 'db_path': ''},
    )

    cards = hub.recent_list_inner.winfo_children()
    assert len(cards) == 1
    card = cards[0]
    # header + progress strip + footer summary, in that pack order.
    header, strip, footer = card.winfo_children()[:3]
    assert len(strip.winfo_children()) == hub.PHASE_COUNT
    assert 'تکمیل‌شده' in footer.cget('text')


def test_project_hub_brand_header_and_empty_state_watermarks_render(hub):
    # Regression guard for the construction_watermark()/logo(transparent=)
    # port: both calls sit behind their own try/except in
    # barkav_bare_launcher_187.py, so a missing art.py function fails
    # silently instead of raising here - assert the actual image refs
    # instead of just "no exception".
    assert getattr(hub, '_brand_logo_ref', None) is not None
    assert getattr(hub, '_logo_ref', None) is not None
