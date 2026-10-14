"""The shell's search field (top bar) filters the open tab's table, and the rows
it lets through are the rows the table had: same cells, same tags, same
children; and the rows it holds back are never older than the table.

It used to put rows back with their cells only. In Data Entry that took away
the status stripe and the alternating colours of every row, which stayed gone
after the query was cleared; a row's children were deleted with it for good;
and the rows kept aside were a snapshot taken once, so a search after an
approval brought back rows that no longer exist.
"""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'stage187_shell_search.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'ui187-token')
os.environ.setdefault('GEMINI_API_KEY', 'ui187-gemini')
os.environ.setdefault('ADMIN_USER_ID', '187')
os.environ.setdefault('GROUP_CHAT_ID', '-100187')
os.environ.setdefault('STAGE4_SHEETS_ENABLED', 'false')

from barkav_ui.tree_filter import filter_rows, restore_all  # noqa: E402

gui_only = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI tests opt-in')

STATUS = ['status_pending', 'status_approved', 'status_rejected']


@pytest.fixture
def root():
    window = tk.Tk()
    window.withdraw()
    try:
        yield window
    finally:
        window.destroy()


def _table(root, count=8):
    """r1 .. r8, the way Data Entry lays rows out: a status tag and a stripe
    colour by position. Rows 3 and 5 are the ones that say 'keep'."""

    tree = ttk.Treeview(root, columns=('tick', 'kind', 'name'), show='headings')
    tree.pack()
    for n in range(1, count + 1):
        tree.insert('', 'end', iid=f'r{n}',
                    values=(f'☐ {n}', 'keep' if n in (3, 5) else 'skip', f'cell{n}'),
                    tags=(STATUS[n % 3], 'even' if (n - 1) % 2 == 0 else 'odd'))
    return tree


def _ids(tree):
    return tuple(tree.get_children(''))


def _tags(tree, iid):
    return tuple(tree.tk.splitlist(tree.item(iid, 'tags')))


def _owner_rebuilds(tree, rows):
    """What a table does when its data changes: delete what is showing, then
    insert the new rows under ids it numbers again from r1."""

    for iid in tree.get_children(''):
        tree.delete(iid)
    for n, kind in enumerate(rows, start=1):
        tree.insert('', 'end', iid=f'r{n}', values=(f'☐ {n}', kind, f'fresh{n}'),
                    tags=(STATUS[n % 3], 'even' if (n - 1) % 2 == 0 else 'odd'))


# ------------------------------------------------ what the rows carry through

def test_rows_let_through_keep_their_tags_and_alternate_by_what_is_showing(root):
    tree = _table(root)
    before = {iid: _tags(tree, iid) for iid in _ids(tree)}
    filter_rows(tree, 'keep')
    assert _ids(tree) == ('r3', 'r5')
    # r3 and r5 were both 'even' in the full table; showing one under the
    # other they alternate, with their status tags as they were.
    assert _tags(tree, 'r3') == (STATUS[0], 'even')
    assert _tags(tree, 'r5') == (STATUS[2], 'odd')
    assert tree.item('r3', 'values') == ('☐ 3', 'keep', 'cell3')

    filter_rows(tree, '')
    assert _ids(tree) == tuple(f'r{n}' for n in range(1, 9))
    assert {iid: _tags(tree, iid) for iid in _ids(tree)} == before


def test_cells_made_of_digits_come_back_as_they_were(root):
    """item(iid) answers with ints for such cells: 009 becomes 9 and ۱۲۳ becomes
    123, which would rewrite a phone number or a Persian-digit amount."""

    tree = ttk.Treeview(root, columns=('a', 'b', 'c'), show='headings')
    cells = ('09121234567', '۱۲۳', '007')
    tree.insert('', 'end', iid='r1', values=cells)
    tree.insert('', 'end', iid='r2', values=('x', 'y', 'z'))
    filter_rows(tree, 'z')
    assert _ids(tree) == ('r2',)
    filter_rows(tree, '')
    assert tuple(str(cell) for cell in tree.item('r1', 'values')) == cells


def test_a_row_keeps_its_children_its_text_its_image_and_whether_it_is_open(root):
    tree = ttk.Treeview(root, columns=('a',), show='tree headings')
    image = tk.PhotoImage(master=root, width=2, height=2)
    tree.insert('', 'end', iid='c1', text='claim one', values=('alpha',), open=True, image=image)
    tree.insert('c1', 'end', iid='c1s1', values=('↳ stage one',), tags=('child',))
    tree.insert('c1', 'end', iid='c1s2', values=('↳ stage two',))
    tree.insert('', 'end', iid='c2', values=('beta',))

    filter_rows(tree, 'beta')
    assert _ids(tree) == ('c2',)
    filter_rows(tree, 'alpha')
    assert _ids(tree) == ('c1',)
    assert tree.get_children('c1') == ('c1s1', 'c1s2')
    assert _tags(tree, 'c1s1') == ('child',)
    assert tree.item('c1', 'text') == 'claim one'
    assert tree.tk.splitlist(tree.item('c1', 'image')) == (str(image),)
    assert str(tree.item('c1', 'open')).lower() in ('1', 'true')

    filter_rows(tree, '')
    assert _ids(tree) == ('c1', 'c2')
    assert tree.get_children('c1') == ('c1s1', 'c1s2')


def test_the_selection_and_the_focus_follow_the_rows_that_stay(root):
    tree = _table(root)
    tree.selection_set(['r3', 'r5'])
    tree.focus('r5')
    filter_rows(tree, 'cell5')
    assert tree.selection() == ('r5',)
    assert tree.focus() == 'r5'
    filter_rows(tree, '')
    assert tree.selection() == ('r5',)


def test_the_row_overlay_is_asked_to_repaint_only_when_rows_changed(root):
    tree = _table(root)
    repaints = []
    tree._barkav_rows = SimpleNamespace(schedule=lambda: repaints.append(1))
    filter_rows(tree, 'keep')
    assert len(repaints) == 1
    filter_rows(tree, 'kee')  # the same two rows: nothing moved under the overlay
    assert len(repaints) == 1
    filter_rows(tree, '')
    assert len(repaints) == 2


def test_a_query_that_changes_nothing_leaves_the_table_alone(root):
    """The field is also written when it gains or loses focus (the prompt goes
    in and out), and each of those must not rebuild a table that is whole."""

    tree = _table(root)
    inserts = []
    original = tree.insert
    tree.insert = lambda *args, **kw: inserts.append(args) or original(*args, **kw)
    tree.selection_set(['r2'])
    filter_rows(tree, '')
    filter_rows(tree, 'cell')  # every row has it
    assert inserts == []
    assert tree.selection() == ('r2',)
    assert len(_ids(tree)) == 8


# -------------------------------------------- the rows held back stay current

def test_a_rebuilt_table_is_not_overtaken_by_the_rows_set_aside_before(root):
    tree = _table(root)
    filter_rows(tree, 'keep')
    assert _ids(tree) == ('r3', 'r5')
    # An approval: the owner rebuilds the table, now six rows, r2 and r4 'keep'.
    _owner_rebuilds(tree, ['skip', 'keep', 'skip', 'keep', 'skip', 'skip'])
    filter_rows(tree, 'keep')
    assert _ids(tree) == ('r2', 'r4')
    assert tree.item('r2', 'values') == ('☐ 2', 'keep', 'fresh2')
    filter_rows(tree, '')
    assert _ids(tree) == tuple(f'r{n}' for n in range(1, 7)), 'six rows, not the old eight'


def test_a_rebuild_that_lands_on_the_ids_left_showing_still_drops_the_old_rows(root):
    """Data Entry numbers its rows r1, r2 ...: the first row matches, the table
    is rebuilt to that one row, and the ids left in the tree are the same."""

    tree = _table(root)
    filter_rows(tree, 'cell1')
    assert _ids(tree) == ('r1',)
    _owner_rebuilds(tree, ['skip'])
    filter_rows(tree, '')
    assert _ids(tree) == ('r1',), 'r2 .. r8 are gone from the table and stay gone'


def test_a_row_added_behind_the_filter_stays_in_the_table(root):
    """Rows inserted without a rebuild cannot be told from a table the owner
    changed, so what is in the tree then counts as all of it."""

    tree = _table(root)
    filter_rows(tree, 'keep')
    tree.insert('', 'end', iid='r9', values=('☐ 9', 'keep', 'cell9'))
    filter_rows(tree, '')
    assert 'r9' in _ids(tree)
    filter_rows(tree, 'cell9')
    assert _ids(tree) == ('r9',)


def test_a_tick_on_a_row_showing_is_kept_and_the_rows_held_back_stay(root):
    tree = _table(root)
    filter_rows(tree, 'keep')
    tree.set('r3', 'tick', '☑ 3')
    filter_rows(tree, 'cell3')
    filter_rows(tree, '')
    assert _ids(tree) == tuple(f'r{n}' for n in range(1, 9))
    assert tree.item('r3', 'values')[0] == '☑ 3'
    assert tree.item('r1', 'values') == ('☐ 1', 'skip', 'cell1')


def test_the_filters_own_deletes_do_not_count_as_the_owner_rebuilding(root):
    tree = _table(root)
    filter_rows(tree, 'keep')
    filter_rows(tree, 'cell3')
    filter_rows(tree, 'keep')
    filter_rows(tree, '')
    assert len(_ids(tree)) == 8


# ------------------------------------- one field, every tab: clearing it

def test_clearing_the_query_gives_back_the_rows_of_every_table_it_narrowed(root):
    first, second, untouched = _table(root), _table(root), _table(root)
    filter_rows(first, 'keep')
    filter_rows(second, 'cell6')
    assert _ids(first) == ('r3', 'r5') and _ids(second) == ('r6',)
    inserts = []
    original = untouched.insert
    untouched.insert = lambda *args, **kw: inserts.append(args) or original(*args, **kw)
    restore_all()
    assert len(_ids(first)) == 8 and len(_ids(second)) == 8
    assert _tags(first, 'r3') == (STATUS[0], 'even')
    assert inserts == [], 'a table the query never narrowed is not touched'
    restore_all()  # and nothing is left to give back


def test_restore_all_does_not_bring_back_rows_of_a_table_the_owner_rebuilt(root):
    tree = _table(root)
    filter_rows(tree, 'keep')
    _owner_rebuilds(tree, ['skip', 'skip', 'keep'])
    restore_all()
    assert _ids(tree) == ('r1', 'r2', 'r3')


def test_restore_all_survives_a_table_whose_tab_was_closed():
    closing = tk.Tk()
    closing.withdraw()
    tree = _table(closing)
    filter_rows(tree, 'keep')
    closing.destroy()
    restore_all()  # the table is gone: nothing to give back, and no error


# ------------------------------------------------ the shell's search field

def _shell(tree, text, placeholder=False):
    tab = object()
    return SimpleNamespace(
        _search_placeholder_active187=placeholder,
        shell_search187=SimpleNamespace(get=lambda: text),
        notebook=SimpleNamespace(select=lambda: 'tab', nametowidget=lambda _name: tab),
        _find_tree_187=lambda widget: tree if widget is tab else None,
    )


def test_the_shell_search_filters_the_open_tabs_table_and_reads_the_prompt_as_no_query(root):
    import dashboard_stage18_7 as d187

    tree = _table(root)
    d187.Stage187Dashboard._apply_shell_search_187(_shell(tree, '  KEEP '))
    assert _ids(tree) == ('r3', 'r5')
    # The field holds its faint prompt while empty: that is no query.
    d187.Stage187Dashboard._apply_shell_search_187(_shell(tree, 'جستجو', placeholder=True))
    assert len(_ids(tree)) == 8
    assert _tags(tree, 'r3') == (STATUS[0], 'even')


def test_the_shell_search_cleared_on_another_tab_restores_the_tab_it_narrowed(root):
    import dashboard_stage18_7 as d187

    narrowed, other = _table(root), ttk.Treeview(root, columns=('a',), show='headings')
    d187.Stage187Dashboard._apply_shell_search_187(_shell(narrowed, 'keep'))
    assert _ids(narrowed) == ('r3', 'r5')
    # The operator goes to another tab, whose table has nothing to do with it,
    # and clears the field there.
    d187.Stage187Dashboard._apply_shell_search_187(_shell(other, ''))
    assert len(_ids(narrowed)) == 8


def test_the_shell_search_finds_persian_and_latin_digits_alike(root):
    import dashboard_stage18_7 as d187

    tree = ttk.Treeview(root, columns=('a',), show='headings')
    tree.insert('', 'end', iid='r1', values=('ردیف ۱۲',))
    tree.insert('', 'end', iid='r2', values=('ردیف ۳۴',))
    d187.Stage187Dashboard._apply_shell_search_187(_shell(tree, '34'))
    assert _ids(tree) == ('r2',)
    d187.Stage187Dashboard._apply_shell_search_187(_shell(tree, '۱۲'))
    assert _ids(tree) == ('r1',)


def test_the_shell_search_no_longer_repaints_the_tables_stripe_colours():
    """stripe_tree() sets even/odd in the theme engine's palette, which is not
    the one Data Entry paints its rows in; now that rows keep their even/odd
    tags, calling it here would recolour them on the first search."""

    import dashboard_stage18_7 as d187

    source = inspect.getsource(d187.Stage187Dashboard._apply_shell_search_187)
    assert 'filter_tree_rows_187(tree, term, en)' in source
    assert 'restore_tree_rows_187()' in source
    code = '\n'.join(line for line in source.splitlines() if not line.lstrip().startswith('#'))
    assert 'stripe_tree' not in code
    assert not hasattr(d187.Stage187Dashboard, '_shell_search_rows_187')


# --------------------------------------------------------- the whole dashboard

def _review_rows():
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


@pytest.fixture(scope='module')
def dashboard():
    import dashboard_stage18_7 as d187
    from barkav_ui import art

    art.clear_cache()
    d187.v186.v185.fetch_tgju_usd_toman = lambda timeout=6.0: (70_000, '2026-08-21T12:00:00')
    monkeypatch = pytest.MonkeyPatch()
    rows = _review_rows()
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
    for _ in range(rounds):
        window.update_idletasks()
        window.update()
        time.sleep(0.03)


def _type(app, text):
    app._search_placeholder_active187 = False
    app.shell_search187.set(text)
    _settle(app)


def _stripes_drawn(tree):
    return len([frame for frame in tree._barkav_rows._stripes if frame.winfo_ismapped()])


def _stripes(app, tree, expected, patience=5.0):
    """How many stripes are up once the overlay has had its turn. It repaints
    one idle after the tree changes, and on a machine busy with other work that
    can take longer than a fixed number of update() rounds."""

    end = time.time() + patience
    while _stripes_drawn(tree) != expected and time.time() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.03)
    return _stripes_drawn(tree)


def _reseed(app, rows):
    rows[:] = _review_rows()
    app.approval_center.refresh()
    app.notebook.select(app.approval_tab)
    _settle(app)


@gui_only
def test_searching_in_data_entry_keeps_the_status_stripes_and_never_shows_old_rows(dashboard):
    app, rows = dashboard
    centre = app.approval_center
    _reseed(app, rows)
    tree = centre.table.tree
    assert app._find_tree_187(app.notebook.nametowidget(app.notebook.select())) is tree
    before = {iid: _tags(tree, iid) for iid in _ids(tree)}
    assert len(before) == 8 and _stripes(app, tree, 8) == 8

    _type(app, 'خروجی')  # row 7, rejected
    shown = _ids(tree)
    assert len(shown) == 1
    assert 'status_rejected' in _tags(tree, shown[0])
    assert _stripes(app, tree, 1) == 1, 'the row keeps its stripe'

    _type(app, '')
    assert {iid: _tags(tree, iid) for iid in _ids(tree)} == before
    assert _stripes(app, tree, 8) == 8, 'and every stripe is back once the query is cleared'

    # The operator searches, then the data changes under the search (an
    # approval and a deletion rebuild the table), then searches again.
    _type(app, 'خروجی')
    assert len(_ids(tree)) == 1
    rows[:] = [row for row in rows if row['pending_id'] != 'DE-3']
    rows[0] = dict(rows[0], status='APPROVED')
    centre.refresh()
    _settle(app)
    _type(app, 'ورودی')  # row 5
    assert len(_ids(tree)) == 1
    assert tree.item(_ids(tree)[0], 'values')[5] == '۱,۰۰۰,۰۰۵'
    assert _stripes(app, tree, 1) == 1
    _type(app, '')
    amounts = {tree.item(iid, 'values')[5] for iid in _ids(tree)}
    assert len(_ids(tree)) == 7
    assert '۱,۰۰۰,۰۰۳' not in amounts, 'the deleted row is not brought back'
    assert 'status_approved' in _tags(tree, _ids(tree)[0]), 'the approval shows'
    assert _stripes(app, tree, 7) == 7


@gui_only
def test_clearing_the_field_on_another_tab_does_not_leave_data_entry_short(dashboard):
    app, rows = dashboard
    _reseed(app, rows)
    tree = app.approval_center.table.tree
    before = {iid: _tags(tree, iid) for iid in _ids(tree)}

    _type(app, 'خروجی')
    assert len(_ids(tree)) == 1
    elsewhere = next(tab for tab in app.notebook.tabs()
                     if app.notebook.nametowidget(tab) is not app.approval_tab)
    app.notebook.select(elsewhere)
    _settle(app)
    _type(app, '')
    app.notebook.select(app.approval_tab)
    _settle(app)
    assert {iid: _tags(tree, iid) for iid in _ids(tree)} == before
    assert _stripes(app, tree, 8) == 8, 'the stripes are back on the tab that was not showing'
