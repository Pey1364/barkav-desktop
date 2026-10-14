"""Data Entry (ثبت دیتا): a row's status is its start-edge stripe, never a colour
over the whole row (operator round 2026-09-27, N1).

The table underneath (stage 18's PendingTable18, then 18.3's) tags every row
pending/approved/rejected - or tx183_<title> for a pending row with a title -
and repaints the pending/approved/rejected tags in raw yellow, green and red
each time set_rows() runs. DataEntryCenter187._row_colors_185 turns those tags
into stripe-only ones, but it ran once when the tab was built, so the first
rebuild afterwards - picking a status filter, an approval, a new receipt -
flooded every row.
"""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'stage187_data_entry_stripe.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'ui187-token')
os.environ.setdefault('GEMINI_API_KEY', 'ui187-gemini')
os.environ.setdefault('ADMIN_USER_ID', '187')
os.environ.setdefault('GROUP_CHAT_ID', '-100187')
os.environ.setdefault('STAGE4_SHEETS_ENABLED', 'false')

gui_only = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI tests opt-in')

# One row per status the review list holds; the pending one with a title is
# the case stage 18.3 paints with its own tx183_ tag.
STATUS_TAG = {
    'PENDING_REVIEW': 'status_pending', 'NEEDS_REVIEW': 'status_pending',
    'EDIT_PENDING': 'status_pending',
    'APPROVED': 'status_approved', 'REJECTED': 'status_rejected',
}
FILTERS = {
    'همه': None,
    'Pending': {'PENDING_REVIEW', 'NEEDS_REVIEW', 'EDIT_PENDING'},
    'تأییدشده': {'APPROVED'},
    'ردشده': {'REJECTED'},
}


def _rows():
    def row(number, status, title=''):
        return {
            'pending_id': f'DE-{number}', 'status': status,
            'message_date': '2026-09-05T10:00:00', 'raw_text': f'x{number}',
            'payload': {'v18_title': title, 'amount': 1_000_000 + number,
                        'description': f'ردیف {number}', 'receiver_name': 'آهن‌آلات',
                        'event_date_shamsi': '1405/06/11'},
        }
    return [
        row(1, 'PENDING_REVIEW', 'هزینه ساخت'), row(2, 'APPROVED'), row(3, 'REJECTED'),
        row(4, 'NEEDS_REVIEW'), row(5, 'APPROVED', 'ورودی'), row(6, 'PENDING_REVIEW'),
        row(7, 'REJECTED', 'خروجی'), row(8, 'EDIT_PENDING', 'یادداشت'),
    ]


def _expected(rows, chosen):
    wanted = FILTERS[chosen]
    return [row for row in rows if wanted is None or row['status'] in wanted]


def _assert_stripe_only(tree, table, rows):
    """Every row carries its status as the stripe tag and no colour of its own."""

    assert len(tree.get_children('')) == len(rows)
    for iid, row in table.iid_to_row.items():
        tags = set(tree.item(iid, 'tags'))
        assert STATUS_TAG[row['status']] in tags
        assert not tags & {'pending', 'approved', 'rejected'}, tags
        assert not [tag for tag in tags if tag.startswith('tx183_')], tags
        # The only tags with a background are the two alternating row colours:
        # a status tag with one is a slab over the row.
        for tag in tags - {'even', 'odd'}:
            assert not str(tree.tag_configure(tag, 'background')), (tag, tags)


# ---------------------------------------------------------------- the source

def test_refresh_normalises_the_row_tags_right_after_it_rebuilds_the_table():
    import dashboard_stage18_7 as d187

    source = inspect.getsource(d187.DataEntryCenter187.refresh)
    rebuilt = source.index('self.table.set_rows(rows, render)')
    retagged = source.index('self._row_colors_185()')
    # The overlay repaints on scroll and resize only; tags changing alone must
    # ask it to repaint too.
    repainted = source.index('overlay.schedule()')
    assert rebuilt < retagged < repainted < source.index('self._append_data_entry_columns_187()')


# -------------------------------------------------- the real table, no window

def _centre(d187, root, monkeypatch, rows):
    from dashboard_stage18_3 import PendingTable183

    noop = lambda *_a, **_k: None  # noqa: E731
    table = PendingTable183(root, *([noop] * 9))
    table.pack()
    centre = SimpleNamespace(
        table=table, rows=None, _skip_contractors_refresh187=True,
        _data_entry_sort187='registration',
        filter=SimpleNamespace(get=lambda: 'همه'),
        rich=SimpleNamespace(hidden_review_ids=lambda: set()),
        after_idle=noop, winfo_toplevel=lambda: SimpleNamespace(),
        _auto_phase_suggestions=noop, _update_status_buttons=noop,
        _append_data_entry_columns_187=noop, _fit_data_entry_table_187=noop,
        _sync_data_entry_checks_187=noop,
        _install_data_entry_row_separators_187=noop, _scroll_data_entry_right_187=noop,
        _refresh_data_entry_counts_187=noop, _pending_review_marker_187=lambda: None,
    )
    centre._row_colors_185 = lambda: d187.DataEntryCenter187._row_colors_185(centre)
    monkeypatch.setattr(d187.v182.APPROVAL, 'list_reviews', lambda **_kw: list(rows))
    return centre


def test_every_status_filter_leaves_the_rows_stripe_only(monkeypatch):
    import dashboard_stage18_7 as d187

    rows = _rows()
    root = tk.Tk()
    root.withdraw()
    try:
        centre = _centre(d187, root, monkeypatch, rows)
        tree = centre.table.tree
        # Picking a filter, then another, then back: every rebuild counts.
        for chosen in ('همه', 'Pending', 'تأییدشده', 'ردشده', 'همه', 'Pending'):
            centre.filter = SimpleNamespace(get=lambda value=chosen: value)
            d187.DataEntryCenter187.refresh(centre)
            _assert_stripe_only(tree, centre.table, _expected(rows, chosen))
    finally:
        root.destroy()


def test_the_table_itself_still_floods_rows_which_is_why_refresh_must_undo_it(monkeypatch):
    """Guard the premise: if stage 18's set_rows ever stops tagging rows with
    the raw colours, the call in refresh() is dead weight and can go."""

    import dashboard_stage18_7 as d187

    rows = _rows()
    root = tk.Tk()
    root.withdraw()
    try:
        centre = _centre(d187, root, monkeypatch, rows)
        tree = centre.table.tree
        centre.table.set_rows(rows, lambda row, index: [f'☐ {index}'] + [''] * 11)
        flooded = [tree.item(iid, 'tags') for iid in tree.get_children('')]
        assert any(tag in {'pending', 'approved', 'rejected'} or tag.startswith('tx183_')
                   for tags in flooded for tag in tags)
    finally:
        root.destroy()


# ------------------------------------------------------ the whole dashboard

@pytest.fixture(scope='module')
def dashboard():
    import dashboard_stage18_7 as d187
    from barkav_ui import art

    art.clear_cache()
    d187.v186.v185.fetch_tgju_usd_toman = lambda timeout=6.0: (70_000, '2026-08-21T12:00:00')
    monkeypatch = pytest.MonkeyPatch()
    rows = _rows()
    monkeypatch.setattr(d187.v182.APPROVAL, 'list_reviews', lambda **_kw: list(rows))
    window = d187.Stage187Dashboard()
    window.update_idletasks()
    window.update()
    try:
        yield window, rows
    finally:
        window.destroy()
        monkeypatch.undo()
        art.clear_cache()


def _settle(window, rounds=6):
    """The row overlay repaints one idle after Tk redraws the tree, and the
    redraw is an idle itself: one update() can leave the last stripes up."""

    for _ in range(rounds):
        window.update_idletasks()
        window.update()
        time.sleep(0.03)


@gui_only
def test_picking_a_category_in_the_open_window_keeps_the_status_in_the_stripe(dashboard):
    from barkav_ui import row_overlay

    app, rows = dashboard
    centre = app.approval_center
    app.notebook.select(app.approval_tab)
    _settle(app)
    tree = centre.table.tree
    shown = {label: key for label, key in centre._STATUS_FILTERS_187}
    assert set(FILTERS) <= set(shown.values())
    for label, key in centre._STATUS_FILTERS_187:
        if key not in FILTERS:
            continue
        centre.status_filter187.set(label)
        centre._select_status_filter_187()
        _settle(app)
        expected = _expected(rows, key)
        _assert_stripe_only(tree, centre.table, expected)
        # The plates behind the row ticks follow the row's own colour: a status
        # colour there would read as a coloured block at the row's start.
        decorator = tree._barkav_rows
        palette = row_overlay._palette()
        plain = {str(tree.tag_configure(tag, 'background')).lower() for tag in ('even', 'odd')}
        for iid in tree.get_children(''):
            assert decorator._row_bg(iid, False, palette).lower() in plain
        # One stripe per row, in its status colour.
        stripes = [frame for frame in decorator._stripes if frame.winfo_ismapped()]
        assert len(stripes) == len(expected)
        roles = {'status_pending': 'warning', 'status_approved': 'success',
                 'status_rejected': 'danger'}
        assert sorted(str(frame.cget('bg')).lower() for frame in stripes) == sorted(
            palette[roles[STATUS_TAG[row['status']]]].lower() for row in expected)
